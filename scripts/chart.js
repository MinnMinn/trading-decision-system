/* scripts/chart.js — the chart layer of every page scripts/build-artifact.py renders (SYSTEM-DESIGN §15; design:
   docs/specs/2026-09-12-chart-lightweight-charts-design.md). Inlined at build time AFTER the vendored TradingView
   Lightweight Charts (scripts/vendor/). Drawing is the library's canvas; everything the project adds (ICT engine,
   Wyckoff overlays, trade plans, ruler, replay) is a list of shapes in (bar index, price) space rendered by ONE
   series primitive. Pure parts are exported for node tests (scripts/tests/test_build_artifact.py). */
(function (root, factory) {
  const api = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.TChart = api;
})(typeof window !== 'undefined' ? window : (typeof globalThis !== 'undefined' ? globalThis : null), function (root) {
'use strict';

// =============================================================================================== pure: engines
// ICT engine: price-only, computed from OHLC at render time. No volume input (the ICT corpus has none).
// Rules per knowledge/04-ttrades-core-A.md, 05-ttrades-core-B.md, 06-ttrades-models.md, page-checked against the PDFs on
// 2026-09-12 (docs/audits/2026-09-12-ict-pdf-recheck.md). Numeric thresholds are PROJECT PARAMETERS from
// analysis-params.json project_defined.ict (the decks define concepts, not numbers). Candle times are UTC ISO strings;
// sessions convert to the exchange-local zone per date (docs/architecture/session-model.md §1) so they follow DST.
const SESSIONS = [{key:'asia',name:'ASIA',tz:'America/New_York',a:20,b:24},{key:'london',name:'LDN',tz:'Europe/London',a:8,b:11},{key:'ny_am',name:'NY AM',tz:'America/New_York',a:8.5,b:11},{key:'ny_pm',name:'NY PM',tz:'America/New_York',a:13.5,b:16}];
const KZ_WEIGHT = {crypto:{london:'reduced',ny_am:'reduced',ny_pm:'none'}, metals:{london:'full',ny_am:'full',ny_pm:'full'}, oil:{london:'reduced',ny_am:'full',ny_pm:'full'}};
const utcDate = iso => new Date(/Z$/.test(iso)?iso:iso+'Z');
const unix = iso => Math.floor(utcDate(iso).getTime()/1000);
const localHour = (iso,tz) => { const parts=new Intl.DateTimeFormat('en-GB',{timeZone:tz,hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(utcDate(iso)); let h=0,m=0; parts.forEach(q=>{ if(q.type==='hour')h=(+q.value)%24; if(q.type==='minute')m=+q.value; }); return h+m/60; };
const weekKey = iso => { const d=utcDate(iso); const dow=(d.getUTCDay()+6)%7; return new Date(d.getTime()-dow*86400000).toISOString().slice(0,10); };
const ictParams = P => { const ICT=(P&&P.ict)||{}; return { PIV:(ICT.pivot_bars||{}).value ?? 3, EQTOL:((ICT.equal_level_tolerance_pct||{}).value ?? 0.08)/100, FVGMIN:(ICT.fvg_min_size_median_ratio||{}).value ?? 0.6, DISP:ICT.displacement||{body_min_ratio:0.6, range_min_median_ratio:1.2} }; };

function ictAnalyze(rows, cfg, P){
  const {PIV,EQTOL,FVGMIN,DISP} = ictParams(P);
  const n=rows.length, O=i=>rows[i][1], H=i=>rows[i][2], L=i=>rows[i][3], C=i=>rows[i][4], T=i=>rows[i][6];
  const tfMin=cfg.tfMin||0, mkt=cfg.market||'crypto';
  const wlo=Math.min(...rows.map(r=>r[3])), whi=Math.max(...rows.map(r=>r[2]));
  const sizes=rows.map(r=>r[2]-r[3]).sort((a,b)=>a-b), medRange=sizes[Math.floor(n/2)]||0;
  const firstAfter=(start,pred)=>{ for(let q=start;q<n;q++) if(pred(q)) return q; return -1; };
  const sh=[], sl=[];
  for(let i=PIV;i<n-PIV;i++){ let isH=true,isL=true; for(let j=i-PIV;j<=i+PIV;j++){ if(j===i)continue; if(H(j)>H(i))isH=false; if(L(j)<L(i))isL=false; } if(isH)sh.push(i); if(isL)sl.push(i); }
  // FVG: wick-based three-candle gap (k04 §2.21); CE = 0.5 of the gap, entry price and hold/fail line (k04 §2.23, §2.26); drawn until first mitigation
  let fvgs=[];
  for(let i=1;i<n-1;i++){ let f=null; if(H(i-1)<L(i+1)) f={type:'bull',i,lo:H(i-1),hi:L(i+1)}; else if(L(i-1)>H(i+1)) f={type:'bear',i,lo:H(i+1),hi:L(i-1)}; if(!f)continue;
    f.size=f.hi-f.lo; f.ce=(f.hi+f.lo)/2; f.end=n-1; f.mitigated=false; for(let j=i+2;j<n;j++){ if((f.type==='bull'&&L(j)<=f.hi)||(f.type==='bear'&&H(j)>=f.lo)){f.end=j;f.mitigated=true;break;} } fvgs.push(f); }
  fvgs=fvgs.filter(f=>f.size>=FVGMIN*medRange).sort((a,b)=>b.size-a.size).slice(0,10).sort((a,b)=>a.i-b.i);
  // liquidity pools (k04 §2.6-2.7): relatively-equal swing pairs, the nearest single old high / old low, window extremes as ERL
  const tol=((wlo+whi)/2)*EQTOL, liq=[];
  const sweptAt=(kind,level,last)=>firstAfter(last+1, j=>kind==='H'?(H(j)>level&&C(j)<level):(L(j)<level&&C(j)>level));
  const addPool=(kind,idxs,level)=>{ const first=Math.min(...idxs), last=Math.max(...idxs); const swept=sweptAt(kind==='BSL'||kind==='OLD-H'?'H':'L',level,last); liq.push({kind,level,from:first,to:swept>=0?swept:n-1,swept}); };
  for(let a=0;a<sh.length;a++){ for(let b=a+1;b<sh.length;b++){ if(Math.abs(H(sh[a])-H(sh[b]))<=tol&&sh[b]-sh[a]>=4){ addPool('BSL',[sh[a],sh[b]],Math.max(H(sh[a]),H(sh[b]))); break; } } }
  for(let a=0;a<sl.length;a++){ for(let b=a+1;b<sl.length;b++){ if(Math.abs(L(sl[a])-L(sl[b]))<=tol&&sl[b]-sl[a]>=4){ addPool('SSL',[sl[a],sl[b]],Math.min(L(sl[a]),L(sl[b]))); break; } } }
  const seen=[], pools=[]; for(const p of liq.sort((a,b)=>a.from-b.from)){ if(!seen.some(q=>Math.abs(q.level-p.level)<=tol)){seen.push(p);pools.push(p);} }
  const lastC=C(n-1);
  const oldH=[...sh].reverse().find(i=>H(i)>lastC&&!pools.some(p=>Math.abs(p.level-H(i))<=tol)), oldL=[...sl].reverse().find(i=>L(i)<lastC&&!pools.some(p=>Math.abs(p.level-L(i))<=tol));
  if(oldH!==undefined){ addPool('OLD-H',[oldH],H(oldH)); pools.push(liq[liq.length-1]); } if(oldL!==undefined){ addPool('OLD-L',[oldL],L(oldL)); pools.push(liq[liq.length-1]); }
  const hiIdx=rows.findIndex(r=>r[2]===whi), loIdx=rows.findIndex(r=>r[3]===wlo);
  pools.push({kind:'ERL-high',level:whi,from:hiIdx,to:n-1,swept:-1}); pools.push({kind:'ERL-low',level:wlo,from:loIdx,to:n-1,swept:-1});
  // dealing range = nearest unswept BSL above / SSL below the last close (k04 §2.18 "where buyside and sellside liquidity is resting"); fallback = window extremes, reported as such
  const above=pools.filter(p=>p.swept<0&&(p.kind==='BSL'||p.kind==='OLD-H')&&p.level>lastC).map(p=>p.level), below=pools.filter(p=>p.swept<0&&(p.kind==='SSL'||p.kind==='OLD-L')&&p.level<lastC).map(p=>p.level);
  const hi=above.length?Math.min(...above):whi, lo=below.length?Math.max(...below):wlo, eq=(lo+hi)/2, drSource=(above.length&&below.length)?'pools':(above.length||below.length)?'mixed':'window';
  // MSS = body close beyond the swing preceding the raid (k04 §2.17, k05 §2.2) + displacement test (k04 §2.16; thresholds are project parameters);
  // OB = last opposing-close candle before the leg: OPEN line + 0.5 mean threshold, mitigated when price trades back to the open (k05 §2.5);
  // CISD = open of the first candle of the final opposing-colour run into the extreme, confirmed by a close through it (k05 §2.3, k06 §2.3)
  const isDisp=j=>{ const rg=H(j)-L(j); return rg>0 && Math.abs(C(j)-O(j))>=DISP.body_min_ratio*rg && rg>=DISP.range_min_median_ratio*medRange; };
  const runStart=(e,down)=>{ let k=e; if(down?C(k)>=O(k):C(k)<=O(k)) k--; let r=k; while(r>=0&&(down?C(r)<O(r):C(r)>O(r))) r--; return r+1<=k?r+1:null; };
  const mss=[], obs=[], cisd=[]; const piv=[...sh.map(i=>({i,t:'H'})),...sl.map(i=>({i,t:'L'}))].sort((a,b)=>a.i-b.i);
  let lastH=null,lastL=null,bias=0;
  for(let k=0;k<piv.length;k++){ const p=piv[k];
    if(p.t==='H'){ if(lastH!==null&&H(p.i)>H(lastH))bias=+1; lastH=p.i; } else { if(lastL!==null&&L(p.i)<L(lastL))bias=-1; lastL=p.i; }
    const next=k+1<piv.length?piv[k+1].i:n;
    for(let j=p.i+1;j<next;j++){
      if(bias===-1&&lastH!==null&&C(j)>H(lastH)){ const from=lastL??0; let e=from; for(let q=from;q<j;q++) if(L(q)<L(e))e=q; const s0=lastH<=e?lastH:from; let oI=s0; for(let q=s0;q<=e;q++) if(H(q)>H(oI))oI=q;
        mss.push({type:'bull',i:j,level:H(lastH),disp:isDisp(j),ext:L(e),extI:e,origin:H(oI),originI:oI});
        for(let q=j-1;q>=Math.max(0,from);q--){ if(C(q)<O(q)){obs.push({type:'bull',i:q,open:O(q),close:C(q),mt:(O(q)+C(q))/2,until:j});break;} }
        const r=runStart(e,true); if(r!==null) cisd.push({type:'bull',i:r,level:O(r),confirmed:firstAfter(r+1,q=>C(q)>O(r))});
        bias=0; break; }
      if(bias===+1&&lastL!==null&&C(j)<L(lastL)){ const from=lastH??0; let e=from; for(let q=from;q<j;q++) if(H(q)>H(e))e=q; const s0=lastL<=e?lastL:from; let oI=s0; for(let q=s0;q<=e;q++) if(L(q)<L(oI))oI=q;
        mss.push({type:'bear',i:j,level:L(lastL),disp:isDisp(j),ext:H(e),extI:e,origin:L(oI),originI:oI});
        for(let q=j-1;q>=Math.max(0,from);q--){ if(C(q)>O(q)){obs.push({type:'bear',i:q,open:O(q),close:C(q),mt:(O(q)+C(q))/2,until:j});break;} }
        const r=runStart(e,false); if(r!==null) cisd.push({type:'bear',i:r,level:O(r),confirmed:firstAfter(r+1,q=>C(q)<O(r))});
        bias=0; break; }
    } }
  obs.forEach(o=>{ o.end=n-1; o.mitigated=false; for(let j=o.until+1;j<n;j++){ if((o.type==='bull'&&L(j)<=o.open)||(o.type==='bear'&&H(j)>=o.open)){o.end=j;o.mitigated=true;break;} } });
  // OTE on the impulse after the latest MSS (k04 §2.20: 1 at the origin, 0 at the terminus, band 0.62-0.79) and std-dev projections of the
  // manipulation leg (k05 §2.12; k06 §2.1.5: 1 at the sweep extreme, 0 at the high/low that made the highest high / lowest low before it),
  // only while the thesis is alive: no later close back beyond the swept extreme (k04 §3.6 R25)
  let ote=null, std=null; const m=mss[mss.length-1];
  if(m){ const dead=firstAfter(m.i+1, q=>m.type==='bull'?C(q)<m.ext:C(q)>m.ext)>=0;
    if(!dead){ let tI=m.i; for(let q=m.i;q<n;q++){ if(m.type==='bull'?H(q)>H(tI):L(q)<L(tI))tI=q; }
      const term=m.type==='bull'?H(tI):L(tI), leg=Math.abs(term-m.ext);
      if(tI>m.i&&leg>0) ote={from:tI,type:m.type,levels:[0.62,0.705,0.79].map(r=>({r,price:m.type==='bull'?term-r*leg:term+r*leg}))};
      const mleg=Math.abs(m.origin-m.ext); if(mleg>0) std={from:m.i,type:m.type,levels:[2,2.5,4].map(k=>({k,price:m.type==='bull'?m.origin+k*mleg:m.origin-k*mleg}))}; } }
  // sessions (PROJECT-DEFINED, session-model.md §2-4): killzone shading only for windows with a non-zero weight for this market, weekdays only;
  // Asia / London session highs & lows as liquidity levels (k04 §2.9; boundaries are the project's, the decks give none — k04 §6 item 9)
  const kz=[], sess=[]; const spans={};
  if(tfMin>0&&tfMin<=240){ SESSIONS.forEach(z=>{ let start=-1; const out=[]; for(let i=0;i<=n;i++){ let inZ=false; if(i<n){ const d=utcDate(T(i)).getUTCDay(), h=localHour(T(i),z.tz); inZ=d!==0&&d!==6&&h>=z.a&&h<z.b; } if(inZ&&start<0)start=i; if((!inZ||i===n)&&start>=0){out.push({from:start,to:i-1});start=-1;} } spans[z.key]=out; });
    if(cfg.kz){ ['london','ny_am','ny_pm'].forEach(k=>{ const w=(KZ_WEIGHT[mkt]||KZ_WEIGHT.crypto)[k]; if(w==='none')return; const z=SESSIONS.find(q=>q.key===k); (spans[k]||[]).forEach(sp=>kz.push({name:z.name,weight:w,from:sp.from,to:sp.to})); }); }
    if(tfMin<=60){ ['asia','london'].forEach(k=>{ const z=SESSIONS.find(q=>q.key===k); (spans[k]||[]).slice(-3).forEach(sp=>{ let h=-Infinity,l=Infinity; for(let i=sp.from;i<=sp.to;i++){ h=Math.max(h,H(i)); l=Math.min(l,L(i)); }
        const swH=sweptAt('H',h,sp.to), thH=firstAfter(sp.to+1,q=>C(q)>h), swL=sweptAt('L',l,sp.to), thL=firstAfter(sp.to+1,q=>C(q)<l);
        sess.push({name:z.name+' H',level:h,from:sp.from,to:swH>=0?swH:(thH>=0?thH:n-1),swept:swH,through:thH}); sess.push({name:z.name+' L',level:l,from:sp.from,to:swL>=0?swL:(thL>=0?thL:n-1),swept:swL,through:thL}); }); }); } }
  // previous-period levels (k04 §2.8, §2.12): PDH/PDL (day = UTC calendar day — project assumption, the decks use the platform's daily bar),
  // PWH/PWL (week from Monday 00Z), PMH/PML. Wick through + close back = failure to displace (×); body close through = the level was the draw (✓)
  const levels=[]; const periods=[]; if(tfMin>0&&tfMin<=240) periods.push(['PD',iso=>iso.slice(0,10),3]); if(tfMin>=60&&tfMin<=1440) periods.push(['PW',weekKey,2]); if(tfMin>=240) periods.push(['PM',iso=>iso.slice(0,7),2]);
  periods.forEach(([tag,keyOf,keep])=>{ const keys=[], idx={}; for(let i=0;i<n;i++){ const k=keyOf(T(i)); if(!(k in idx)){idx[k]={from:i,to:i,h:H(i),l:L(i)};keys.push(k);} else { const o=idx[k]; o.to=i; o.h=Math.max(o.h,H(i)); o.l=Math.min(o.l,L(i)); } }
    keys.slice(1).slice(-keep).forEach(k=>{ const prev=idx[keys[keys.indexOf(k)-1]], cur=idx[k];
      [['H',prev.h],['L',prev.l]].forEach(([kind,lv])=>{ let swept=-1,through=-1; for(let q=cur.from;q<=cur.to;q++){ if(kind==='H'){ if(C(q)>lv){through=q;break;} if(H(q)>lv){swept=q;break;} } else { if(C(q)<lv){through=q;break;} if(L(q)<lv){swept=q;break;} } }
        levels.push({name:tag+kind,level:lv,from:cur.from,to:cur.to,swept,through}); }); }); });
  const swept=pools.filter(p=>p.swept>=0).sort((a,b)=>b.swept-a.swept).slice(0,4);
  const keptPools=pools.filter(p=>p.swept<0).concat(swept).sort((a,b)=>a.from-b.from);
  const keptMss=mss.slice(-4), keptObs=obs.filter(o=>keptMss.some(q=>q.i===o.until)), keptCisd=cisd.slice(-4);
  return {lo,hi,eq,pct:(lastC-lo)/((hi-lo)||1),drSource,wlo,whi,fvgs:fvgs.slice(-8),pools:keptPools,mss:keptMss,obs:keptObs,cisd:keptCisd,kz,sess,levels,ote,std};
}

// Wyckoff volume read: rolling mean of the previous P.lookback completed bars (project parameter).
function volStats(rows, P){
  const n=rows.length, avg=new Array(n).fill(null), ratio=new Array(n).fill(null), lb=(P&&P.lookback)||20;
  for(let i=0;i<n;i++){ const a=Math.max(0,i-lb), k=i-a; if(k<3)continue; let s=0; for(let j=a;j<i;j++)s+=rows[j][5]; avg[i]=s/k; ratio[i]=avg[i]?rows[i][5]/avg[i]:null; }
  return {avg,ratio};
}
const idxOf=(rows,iso)=>{ if(!iso)return -1; let best=-1; for(let i=0;i<rows.length;i++){ if(rows[i][6]<=iso)best=i; else break; } return best>=0&&rows[best][6]===iso?best:(best>=0&&rows[best][6].slice(0,13)===iso.slice(0,13)?best:-1); };
const spanOf=(rows,iso)=>{ if(!iso)return -1; for(let i=0;i<rows.length;i++){ if(rows[i][6]>=iso)return i; } return rows.length; };

// =============================================================================================== pure: shapes
// Every overlay is a record in (bar index, price) space. Colours are TOKENS (names of CSS variables in artifact_theme.py)
// resolved by the renderer, so the same shape list works in both themes.
//   rect  {i1,i2|null,p1|null,p2|null, fill, alpha, stroke?, sw?, dash?, label?, labelColor?, labelPos:'tl'|'ml'}   (p null = full pane height)
//   hseg  {i1,i2|null, price, stroke, sw, dash, alpha?, label?, labelColor?, labelAt:'axis'|'start-above'|'start-below'|'end'}
//   vseg  {i, p1,p2, stroke, sw, dash}
//   label {i, price, text, color, anchor:'start'|'middle'|'end', dx, dy, bold?, alpha?}
//   mark  {i, price, glyph:'x'|'check'|'dot', color, r?}
//   flag  {i, price, text, up, color}      (event flag with collision avoidance, done in pixel space by the renderer)
const ictShapes = (rows, ict, cfg) => {
  const S=[], n=rows.length, compact=!!cfg.compact, fmt=cfg.fmt||(v=>String(v));
  ict.kz.forEach(z=>{ S.push({kind:'rect',i1:z.from-0.5,i2:z.to+0.5,p1:null,p2:null,fill:'i',alpha:z.weight==='full'?0.10:0.06, label:compact?null:z.name+(z.weight==='reduced'?' ½':''), labelColor:'faint', labelPos:'tl'}); });
  S.push({kind:'rect',i1:null,i2:null,p1:ict.hi,p2:ict.eq,fill:'down',alpha:0.04});
  S.push({kind:'rect',i1:null,i2:null,p1:ict.eq,p2:ict.lo,fill:'up',alpha:0.04});
  ict.fvgs.forEach(f=>{ const col=f.type==='bull'?'up':'down'; S.push({kind:'rect',i1:f.i-0.5,i2:f.end+0.5,p1:f.hi,p2:f.lo,fill:col,alpha:f.mitigated?0.14:0.28,stroke:col,sw:0.6});
    if(!f.mitigated) S.push({kind:'hseg',i1:f.i-0.5,i2:f.end+0.5,price:f.ce,stroke:col,sw:0.8,dash:[2,2],alpha:0.8}); });
  ict.obs.forEach(o=>{ const op=o.mitigated?0.35:1; S.push({kind:'rect',i1:o.i-0.5,i2:o.end+0.5,p1:Math.max(o.open,o.close),p2:Math.min(o.open,o.close),fill:'i',alpha:0.12*op});
    S.push({kind:'hseg',i1:o.i-0.5,i2:o.end+0.5,price:o.open,stroke:'i',sw:1.4,alpha:op}); S.push({kind:'hseg',i1:o.i-0.5,i2:o.end+0.5,price:o.mt,stroke:'i',sw:0.8,dash:[3,3],alpha:op});
    if(!compact) S.push({kind:'label',i:o.i-0.5,price:o.open,text:(o.type==='bull'?'+OB':'-OB')+' open · 0.5 MT',color:'i',anchor:'start',dx:3,dy:o.type==='bull'?-7:7,bold:true,alpha:op}); });
  ict.cisd.forEach(c=>{ const col=c.type==='bull'?'up':'down'; S.push({kind:'hseg',i1:c.i-0.5,i2:c.confirmed>=0?c.confirmed:null,price:c.level,stroke:col,sw:1.3,dash:[5,2]});
    if(c.confirmed>=0) S.push({kind:'mark',i:c.confirmed,price:c.level,glyph:'dot',color:col,r:2.6});
    if(!compact) S.push({kind:'label',i:c.i-0.5,price:c.level,text:'CISD'+(c.confirmed>=0?'':' (chưa đóng qua)'),color:col,anchor:'start',dx:2,dy:c.type==='bull'?8:-7,bold:true}); });
  S.push({kind:'hseg',i1:null,i2:null,price:ict.eq,stroke:'i',sw:1.4,dash:[6,4],label:'EQ '+fmt(ict.eq),labelAt:'axis'});
  S.push({kind:'label',i:null,price:ict.hi,text:'premium'+(ict.drSource==='window'?' (biên cửa sổ)':ict.drSource==='mixed'?' (1 biên = cửa sổ)':' (BSL↔SSL)'),color:'faint',anchor:'end',dx:-4,dy:7});
  S.push({kind:'label',i:null,price:ict.lo,text:'discount',color:'faint',anchor:'end',dx:-4,dy:-6});
  ict.pools.forEach(p=>{ const isHigh=p.kind==='BSL'||p.kind==='ERL-high'||p.kind==='OLD-H', col=isHigh?'down':'up', old=p.kind.startsWith('OLD');
    S.push({kind:'hseg',i1:p.from,i2:p.to,price:p.level,stroke:col,sw:old?0.9:1.2,dash:[2,3]});
    if(!compact) S.push({kind:'label',i:p.from,price:p.level,text:p.kind==='ERL-high'?'ERL (BSL)':p.kind==='ERL-low'?'ERL (SSL)':p.kind==='OLD-H'?'old high (BSL)':p.kind==='OLD-L'?'old low (SSL)':p.kind,color:col,anchor:'start',dx:0,dy:isHigh?-6:7});
    if(p.swept>=0) S.push({kind:'mark',i:p.swept,price:p.level,glyph:'x',color:col,r:4}); });
  const lvl=(l,col)=>{ S.push({kind:'hseg',i1:l.from-0.5,i2:Math.min(n-1,l.to)+0.5,price:l.level,stroke:col,sw:1,dash:[7,3],alpha:0.85});
    if(!compact) S.push({kind:'label',i:l.from-0.5,price:l.level,text:l.name,color:col,anchor:'start',dx:2,dy:-6});
    if(l.swept>=0) S.push({kind:'mark',i:l.swept,price:l.level,glyph:'x',color:col,r:3.5}); else if(l.through>=0) S.push({kind:'mark',i:l.through,price:l.level,glyph:'check',color:col,r:4}); };
  ict.levels.forEach(l=>lvl(l,'ink2')); ict.sess.forEach(l=>lvl(l,'muted'));
  ict.mss.forEach(m=>{ const col=m.type==='bull'?'up':'down', c=rows[m.i][4]; S.push({kind:'vseg',i:m.i,p1:m.level,p2:c,stroke:col,sw:m.disp?2:1,dash:m.disp?null:[3,2]});
    if(!compact) S.push({kind:'label',i:m.i,price:c,text:(m.disp?'MSS':'đóng qua swing, thiếu displacement')+(m.type==='bull'?'↑':'↓'),color:col,anchor:'middle',dx:0,dy:m.type==='bull'?-9:11,bold:true}); });
  if(ict.ote){ const col=ict.ote.type==='bull'?'up':'down'; ict.ote.levels.forEach(l=>{ S.push({kind:'hseg',i1:ict.ote.from,i2:null,price:l.price,stroke:col,sw:l.r===0.705?1.4:0.8,dash:[1,3]}); if(!compact) S.push({kind:'label',i:ict.ote.from,price:l.price,text:'OTE '+l.r,color:col,anchor:'start',dx:3,dy:-6}); }); }
  if(ict.std){ ict.std.levels.forEach(l=>{ S.push({kind:'hseg',i1:ict.std.from,i2:null,price:l.price,stroke:'i',sw:0.9,dash:[8,3,2,3],label:'−'+l.k+'σ '+fmt(l.price),labelAt:'axis'}); }); }
  if(!compact) ict.fvgs.filter(f=>!f.mitigated).sort((a,b)=>b.size-a.size).slice(0,2).forEach(f=>{ S.push({kind:'label',i:f.i+1,price:(f.hi+f.lo)/2,text:'FVG',color:f.type==='bull'?'up':'down',anchor:'start',dx:0,dy:0}); });
  const li=n-1; S.push({kind:'mark',i:li,price:rows[li][4],glyph:'dot',color:'ink',r:3,ring:true}); S.push({kind:'label',i:li,price:rows[li][4],text:'now '+(ict.pct*100).toFixed(0)+'%',color:'ink',anchor:'end',dx:-6,dy:-10,bold:true});
  return S;
};

const wyckoffShapes = (rows, wy, cfg) => {
  const S=[], n=rows.length, compact=!!cfg.compact, fmt=cfg.fmt||(v=>String(v)); wy=wy||{};
  (wy.phases||[]).forEach(ph=>{ const a=spanOf(rows,ph.from), b=ph.to?spanOf(rows,ph.to):n; if(a>=n||b<=0)return; const lbl=String(ph.label||'').replace(/^(pha|phase)\s*/i,'').slice(0,2);
    S.push({kind:'rect',i1:Math.max(0,a)-0.5,i2:Math.min(n,b)-0.5,p1:null,p2:null,fill:'w',alpha:0.07,stroke:'w',sw:1,dash:[2,4],strokeAlpha:0.6,leftOnly:true,label:lbl||null,labelColor:'w',labelPos:'tl',labelBold:true}); });
  if(wy.tr){ const a=Math.max(0,spanOf(rows,wy.tr.from));
    [[wy.tr.high,wy.tr.high_label||'AR'],[wy.tr.low,wy.tr.low_label||'SC']].forEach(([v,lb])=>{ if(v==null)return; S.push({kind:'hseg',i1:a-0.4,i2:null,price:v,stroke:'w',sw:1.6,dash:[5,3],label:lb+' '+fmt(v),labelAt:'axis'}); }); }
  (wy.events||[]).map(f=>({f,i:idxOf(rows,f.time)})).filter(o=>o.i>=0).sort((a,b)=>a.i-b.i).forEach(({f,i})=>{ const c=rows[i]; S.push({kind:'flag',i,price:f.up?c[2]:c[3],text:compact?String(f.label||'').split(' · ')[0]:String(f.label||''),up:!!f.up,color:'w'}); });
  const li=n-1; S.push({kind:'mark',i:li,price:rows[li][4],glyph:'dot',color:'ink',r:3,ring:true});
  return S;
};

const windowShape = (rows, fromIso) => { const a=spanOf(rows,fromIso); if(a>=rows.length) return []; return [{kind:'rect',i1:a-0.5,i2:null,p1:null,p2:null,fill:'accent',alpha:0.10,label:'vào lệnh →',labelColor:'accent',labelPos:'tl'}]; };

// Named levels (anchors) for the active lane: a dashed line from its time to the right edge, labelled on the price axis.
const levelShapes = (rows, levels, lane, fmt) => (levels||[]).filter(L=>L.method===lane||L.method==='neutral').map(L=>({kind:'hseg',i1:Math.max(0,spanOf(rows,L.time))-0.5,i2:null,price:L.price,stroke:L.method==='neutral'?'muted':lane==='ict'?'i':'w',sw:1.2,dash:[6,4],label:(L.short||'')+' '+fmt(L.price),labelAt:'axis'}));

// Trade plans from trades/index.jsonl (PLANNED/OPEN records for this instrument; read-only) + the narrative's invalidation level.
// Risk box entry↔stop, reward box entry↔target1, every target a line; R:R from planned_rr or computed.
const planShapes = (rows, plans, inv, cfg) => {
  const S=[], fmt=cfg.fmt||(v=>String(v)), n=rows.length;
  (plans||[]).forEach(p=>{ if(p.entry==null||p.stop_loss==null)return; const long=p.direction!=='SHORT', risk=Math.abs(p.entry-p.stop_loss); if(!(risk>0))return;
    const i1=Math.max(0,idxOf(rows,p.date_opened)>=0?idxOf(rows,p.date_opened):spanOf(rows,p.date_opened)); const from=Math.min(i1,n-1)-0.5;
    const tag=(p.rehearsal_mode?'diễn tập · ':'')+(p.id||''); const t1=(p.targets||[])[0];
    S.push({kind:'rect',i1:from,i2:null,p1:p.entry,p2:p.stop_loss,fill:'down',alpha:0.10});
    if(t1!=null) S.push({kind:'rect',i1:from,i2:null,p1:p.entry,p2:t1,fill:'up',alpha:0.10});
    S.push({kind:'hseg',i1:from,i2:null,price:p.entry,stroke:'ink',sw:1.2,label:'vào '+fmt(p.entry),labelAt:'axis'});
    S.push({kind:'hseg',i1:from,i2:null,price:p.stop_loss,stroke:'down',sw:1.2,label:'dừng '+fmt(p.stop_loss),labelAt:'axis'});
    (p.targets||[]).forEach((t,k)=>{ S.push({kind:'hseg',i1:from,i2:null,price:t,stroke:'up',sw:1,dash:[4,3],label:'T'+(k+1)+' '+fmt(t),labelAt:'axis'}); });
    const rr=p.planned_rr!=null?p.planned_rr:(t1!=null?Math.abs(t1-p.entry)/risk:null);
    S.push({kind:'label',i:from,price:p.entry,text:(long?'LONG ':'SHORT ')+tag+(rr!=null?' · R:R '+rr.toFixed(2):'')+' · '+(p.status||''),color:'ink',anchor:'start',dx:4,dy:long?-8:9,bold:true}); });
  if(inv&&inv.level!=null) S.push({kind:'hseg',i1:null,i2:null,price:inv.level,stroke:'warn',sw:1.2,dash:[3,3],label:'vô hiệu · '+(inv.owner||'?')+' '+fmt(inv.level),labelAt:'axis'});
  return S;
};

// Ruler (R:R measure): entry + stop chosen by the user → risk box, 1R/2R/3R ladder on the reward side. Never persisted.
const rulerShapes = (entry, stop, i1, i2, fmt) => {
  const S=[]; if(entry==null||stop==null)return S; const risk=Math.abs(entry-stop); if(!(risk>0))return S; const long=stop<entry, a=Math.min(i1,i2)-0.5, b=Math.max(i1,i2)+0.5;
  S.push({kind:'rect',i1:a,i2:b,p1:entry,p2:stop,fill:'down',alpha:0.18,stroke:'down',sw:1});
  [1,2,3].forEach(k=>{ const t=long?entry+k*risk:entry-k*risk; S.push({kind:'rect',i1:a,i2:b,p1:long?t-risk:t+risk,p2:t,fill:'up',alpha:0.16-0.03*k,stroke:'up',sw:0.6}); S.push({kind:'label',i:b,price:t,text:k+'R '+fmt(t),color:'up',anchor:'end',dx:-3,dy:long?7:-6,bold:true}); });
  S.push({kind:'label',i:a,price:entry,text:'vào '+fmt(entry),color:'ink',anchor:'start',dx:3,dy:long?-7:8,bold:true});
  S.push({kind:'label',i:a,price:stop,text:'dừng '+fmt(stop)+' · rủi ro '+fmt(risk)+' ('+(risk/entry*100).toFixed(2)+'%)',color:'down',anchor:'start',dx:3,dy:long?8:-7,bold:true});
  return S;
};

const api = {ictAnalyze, volStats, idxOf, spanOf, ictShapes, wyckoffShapes, windowShape, levelShapes, planShapes, rulerShapes, unix};
if(!root || typeof document==='undefined') return api;   // node: pure API only

// =============================================================================================== browser: rendering
const LWC = root.LightweightCharts;
const LANES = ['wyckoff','ict','footprint','heatmap'];
const fmtOf = k => k==='int' ? (v=>Math.round(v).toLocaleString('en-US')) : (v=>v.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}));
const TOKENS = {up:'--up',down:'--down',ink:'--ink',ink2:'--ink-2',muted:'--muted',faint:'--faint',line:'--line',lineStrong:'--line-strong',surface:'--surface',surface2:'--surface-2',surface3:'--surface-3',accent:'--accent',w:'--w',i:'--i',warn:'--warn',upSoft:'--up-soft',downSoft:'--down-soft'};
function colors(){ const cs=getComputedStyle(document.documentElement), C={}; for(const k in TOKENS) C[k]=cs.getPropertyValue(TOKENS[k]).trim()||'#888'; C.mono=cs.getPropertyValue('--mono').trim()||'monospace'; return C; }
const withAlpha=(hex,a)=>{ if(a==null||a>=1) return hex; const m=/^#([0-9a-f]{6})$/i.exec(hex); if(!m) return hex; const v=parseInt(m[1],16); return `rgba(${v>>16&255},${v>>8&255},${v&255},${a})`; };

// ONE series primitive renders the shape list of a chart in (bar index, price) space. Background fills go under the candles
// (zOrder bottom), lines/labels/marks above (top); axis labels come from priceAxisViews — TradingView-style price tags.
class Annotations {
  constructor(C){ this.C=C; this.shapes=[]; this._axis=[]; this._chart=null; this._series=null; this._req=null;
    this._bg={zOrder:()=>'bottom', renderer:()=>({draw:t=>this._draw(t,'bg')})}; this._fg={zOrder:()=>'top', renderer:()=>({draw:t=>this._draw(t,'fg')})}; this._views=[this._bg,this._fg]; }
  attached({chart,series,requestUpdate}){ this._chart=chart; this._series=series; this._req=requestUpdate; }
  detached(){ this._chart=null; this._series=null; this._req=null; }
  set(shapes){ this.shapes=shapes||[]; const C=this.C, self=this;
    const byPrice=new Map();   // one axis tag per price: "AR 77,425" from the TR and "AR" from the anchors become one tag, Spring + invalidation likewise
    this.shapes.filter(s=>s.kind==='hseg'&&s.labelAt==='axis'&&s.label).forEach(s=>{ const k=Math.round(s.price*1e6); const g=byPrice.get(k); if(g){ const base=t=>t.replace(/\s[\d.,]+$/,''); if(!g.parts.some(t=>base(t)===base(s.label))) g.parts.push(base(s.label)); } else byPrice.set(k,{price:s.price,stroke:s.stroke,parts:[s.label]}); });
    this._axis=[...byPrice.values()].map(g=>({ coordinate:()=>{ const y=self._series?self._series.priceToCoordinate(g.price):null; return y==null?-1e6:y; }, text:()=>g.parts.join(' · '), textColor:()=>'#FFFFFF', backColor:()=>C[g.stroke]||C.ink, visible:()=>!!self._series&&self._series.priceToCoordinate(g.price)!=null, tickVisible:()=>true }));
    if(this._req) this._req(); }
  setColors(C){ this.C=C; if(this._req) this._req(); }
  updateAllViews(){}
  paneViews(){ return this._views; }
  priceAxisViews(){ return this._axis; }
  _draw(target, layer){ const chart=this._chart, series=this._series; if(!chart||!series||!this.shapes.length) return;
    target.useMediaCoordinateSpace(({context:ctx, mediaSize})=>{
      const ts=chart.timeScale(), W=mediaSize.width, Hh=mediaSize.height, C=this.C, bs=ts.options().barSpacing;
      const X=i=>{ if(i==null) return null; const x=ts.logicalToCoordinate(i); return x==null?null:x; };
      const Y=p=>{ if(p==null) return null; const y=series.priceToCoordinate(p); return y==null?null:y; };
      const x1of=s=>s.i1==null?0:X(s.i1), x2of=s=>s.i2==null?W:X(s.i2);
      const font=(b,px)=>`${b?'700 ':''}${px||10}px ${C.mono}`;
      const placed=[];
      ctx.save(); ctx.lineCap='butt';
      for(const s of this.shapes){
        if(layer==='bg'){ if(s.kind!=='rect') continue;
          const x1=x1of(s), x2=x2of(s); if(x1==null||x2==null) continue; const y1=s.p1==null?0:Y(s.p1), y2=s.p2==null?Hh:Y(s.p2); if(y1==null||y2==null) continue;
          const l=Math.min(x1,x2), t=Math.min(y1,y2), w=Math.max(2,Math.abs(x2-x1)), h=Math.max(1,Math.abs(y2-y1));
          if(s.fill){ ctx.globalAlpha=s.alpha==null?1:s.alpha; ctx.fillStyle=C[s.fill]||s.fill; ctx.fillRect(l,t,w,h); }
          if(s.stroke){ ctx.globalAlpha=s.strokeAlpha==null?1:s.strokeAlpha; ctx.strokeStyle=C[s.stroke]||s.stroke; ctx.lineWidth=s.sw||1; ctx.setLineDash(s.dash||[]); if(s.leftOnly){ ctx.beginPath(); ctx.moveTo(l,t); ctx.lineTo(l,t+h); ctx.stroke(); } else ctx.strokeRect(l,t,w,h); ctx.setLineDash([]); }
          if(s.label&&l>=-1&&l<W){ ctx.globalAlpha=1; ctx.font=font(s.labelBold,s.labelBold?10:9.5); ctx.fillStyle=C[s.labelColor||'faint']; ctx.textAlign='left'; ctx.textBaseline='top'; const lx=Math.max(l,0)+4, ly=s.labelPos==='ml'?t+h/2-5:t+3; let row=0; while(row<3&&placed.some(p=>Math.abs(p.x-lx)<18&&Math.abs(p.y-(ly+row*12))<11)) row++; if(row<3){ placed.push({x:lx,y:ly+row*12}); ctx.fillText(s.label,lx,ly+row*12); } }
          continue; }
        if(s.kind==='rect') continue;
        ctx.globalAlpha=s.alpha==null?1:s.alpha;
        if(s.kind==='hseg'){ const x1=x1of(s), x2=x2of(s), y=Y(s.price); if(x1==null||x2==null||y==null) continue;
          ctx.strokeStyle=C[s.stroke]||s.stroke; ctx.lineWidth=s.sw||1; ctx.setLineDash(s.dash||[]); ctx.beginPath(); ctx.moveTo(x1,y); ctx.lineTo(x2,y); ctx.stroke(); ctx.setLineDash([]);
          if(s.label&&s.labelAt&&s.labelAt!=='axis'&&x1>=-1&&x1<W){ ctx.font=font(false,9.5); ctx.fillStyle=C[s.labelColor||s.stroke]||C.ink; ctx.textBaseline='middle'; if(s.labelAt==='end'){ ctx.textAlign='right'; ctx.fillText(s.label,x2-3,y-6); } else { ctx.textAlign='left'; ctx.fillText(s.label,x1+2,s.labelAt==='start-below'?y+7:y-7); } } }
        else if(s.kind==='vseg'){ const x=X(s.i), y1=Y(s.p1), y2=Y(s.p2); if(x==null||y1==null||y2==null) continue; ctx.strokeStyle=C[s.stroke]||s.stroke; ctx.lineWidth=s.sw||1; ctx.setLineDash(s.dash||[]); ctx.beginPath(); ctx.moveTo(x,y1); ctx.lineTo(x,y2); ctx.stroke(); ctx.setLineDash([]); }
        else if(s.kind==='label'){ const x=s.i==null?W:X(s.i), y=Y(s.price); if(x==null||y==null||x<-2||x>W+2||y<-2||y>Hh+2) continue; ctx.font=font(s.bold,s.bold?10:9.5); ctx.fillStyle=C[s.color]||s.color||C.ink; ctx.textAlign=s.anchor==='middle'?'center':s.anchor==='end'?'right':'left'; ctx.textBaseline='middle'; ctx.fillText(s.text,x+(s.dx||0),y+(s.dy||0)); }
        else if(s.kind==='mark'){ const x=X(s.i), y=Y(s.price); if(x==null||y==null) continue; const col=C[s.color]||s.color, r=s.r||3; ctx.strokeStyle=col; ctx.fillStyle=col; ctx.lineWidth=1.8;
          if(s.glyph==='x'){ ctx.beginPath(); ctx.moveTo(x-r,y-r); ctx.lineTo(x+r,y+r); ctx.moveTo(x+r,y-r); ctx.lineTo(x-r,y+r); ctx.stroke(); }
          else if(s.glyph==='check'){ ctx.beginPath(); ctx.moveTo(x-r,y); ctx.lineTo(x-r/4,y+r*0.75); ctx.lineTo(x+r,y-r*0.75); ctx.stroke(); }
          else { ctx.beginPath(); ctx.arc(x,y,r,0,Math.PI*2); ctx.fill(); if(s.ring){ ctx.strokeStyle=C.surface2; ctx.lineWidth=1.5; ctx.stroke(); } } }
        else if(s.kind==='flag'){ const x=X(s.i), ay=Y(s.price); if(x==null||ay==null) continue; const col=C[s.color]||s.color; ctx.font=font(true,10); const w=ctx.measureText(s.text).width;
          let lvl=0, fy; for(;;){ fy=ay+(s.up?-10-lvl*12:15+lvl*12); const clash=placed.some(p=>p.flag&&p.up===s.up&&Math.abs(p.y-fy)<11&&(x-w/2)<p.x2&&(x+w/2)>p.x1); if(!clash||lvl>=4) break; lvl++; }
          placed.push({flag:true,up:s.up,y:fy,x1:x-w/2,x2:x+w/2,x:x,y:fy});
          ctx.fillStyle=col; ctx.beginPath(); ctx.arc(x,ay,3,0,Math.PI*2); ctx.fill(); ctx.strokeStyle=C.surface2; ctx.lineWidth=1.5; ctx.stroke();
          if(lvl>0){ ctx.strokeStyle=col; ctx.lineWidth=0.8; ctx.globalAlpha=0.7; ctx.beginPath(); ctx.moveTo(x,ay); ctx.lineTo(x,fy+(s.up?3:-9)); ctx.stroke(); ctx.globalAlpha=1; }
          const ax=x+w/2>W-2?W-2:(x-w/2<2?2:x); ctx.textAlign=ax!==x?(ax>x?'right':'left'):'center'; ctx.textBaseline='middle'; ctx.fillStyle=C.ink; ctx.fillText(s.text,ax,fy-3); }
      }
      ctx.restore();
    }); }
}

// Pane primitive: a one-line note in the (empty) volume pane when the lane has no volume (ICT).
class PaneNote { constructor(C){ this.C=C; this.text=''; this._v=[{zOrder:()=>'bottom', renderer:()=>({draw:t=>{ if(!this.text) return; t.useMediaCoordinateSpace(({context:ctx,mediaSize})=>{ ctx.font=`9.5px ${this.C.mono}`; ctx.fillStyle=this.C.faint; ctx.textAlign='left'; ctx.textBaseline='middle'; ctx.fillText(this.text,8,mediaSize.height/2); }); }})}]; this._req=null; }
  attached({requestUpdate}){ this._req=requestUpdate; } detached(){ this._req=null; } set(text){ this.text=text; if(this._req) this._req(); } setColors(C){ this.C=C; if(this._req) this._req(); } updateAllViews(){} paneViews(){ return this._v; } }

const VOL_H=90;
function chartOptions(C, fmt){ return {
  autoSize:true,
  layout:{background:{type:'solid',color:C.surface2}, textColor:C.faint, fontFamily:C.mono, fontSize:10, attributionLogo:false /* attribution is the NOTICE line in the page footer (Apache-2.0 §4(d)) */, panes:{separatorColor:C.line, separatorHoverColor:withAlpha(C.accent,0.2), enableResize:false}},
  grid:{vertLines:{color:C.line, style:LWC.LineStyle.Solid}, horzLines:{color:C.line}},
  crosshair:{mode:LWC.CrosshairMode.Normal, vertLine:{color:withAlpha(C.ink,0.55), width:1, style:LWC.LineStyle.Dashed, labelBackgroundColor:C.ink2}, horzLine:{color:withAlpha(C.ink,0.55), width:1, style:LWC.LineStyle.Dashed, labelBackgroundColor:C.ink2}},
  rightPriceScale:{borderColor:C.lineStrong, scaleMargins:{top:0.08,bottom:0.06}, entireTextOnly:false},
  timeScale:{borderColor:C.lineStrong, timeVisible:true, secondsVisible:false, rightOffset:4, barSpacing:6, minBarSpacing:1.2, fixLeftEdge:false, fixRightEdge:false, lockVisibleTimeRangeOnResize:true},
  localization:{locale:'en-US', priceFormatter:fmt, timeFormatter:t=>new Date(t*1000).toISOString().slice(0,16).replace('T',' ')+'Z'},
  handleScroll:{mouseWheel:true, pressedMouseMove:true, horzTouchDrag:true, vertTouchDrag:true},
  handleScale:{axisPressedMouseMove:true, mouseWheel:true, pinch:true},
  kineticScroll:{mouse:true, touch:true},
}; }

// One chart per tier block. Created once; lane switches only swap overlays, so zoom/pan state survives (§4 of the spec).
function makeChart(block, d, t, P, C){
  const el=block.querySelector('.chart'), wrap=block.querySelector('.chart-wrap'), tip=wrap.querySelector('.tip');
  const rows=t.rows, fmt=fmtOf(d.fmt), N=rows.length;
  const chart=LWC.createChart(el, chartOptions(C,fmt));
  const candles=chart.addSeries(LWC.CandlestickSeries,{upColor:C.surface2, downColor:C.down, borderVisible:true, borderUpColor:C.up, borderDownColor:C.down, wickUpColor:C.up, wickDownColor:C.down, priceLineVisible:true, priceLineColor:withAlpha(C.ink,0.5), lastValueVisible:true});
  const vol=chart.addSeries(LWC.HistogramSeries,{priceScaleId:'vol', priceFormat:{type:'custom', formatter:v=>v.toLocaleString('en-US',{maximumFractionDigits:v>=100?0:2}), minMove:0.01}, lastValueVisible:false, priceLineVisible:false},1);
  const avg=chart.addSeries(LWC.LineSeries,{priceScaleId:'vol', color:withAlpha(C.ink2,0.8), lineWidth:1, lastValueVisible:false, priceLineVisible:false, crosshairMarkerVisible:false},1);
  const pane1=chart.panes()[1]; pane1.setHeight(VOL_H); pane1.priceScale('vol').applyOptions({scaleMargins:{top:0.15,bottom:0}});
  const ann=new Annotations(C), annVol=new Annotations(C), note=new PaneNote(C); candles.attachPrimitive(ann); vol.attachPrimitive(annVol); pane1.attachPrimitive(note);
  candles.setData(rows.map(r=>({time:unix(r[6]), open:r[1], high:r[2], low:r[3], close:r[4]})));
  chart.timeScale().fitContent();
  // engines run ONCE on the tier window (§2): overlays never depend on the zoom
  const cfg={kz:t.kz, tfMin:t.tfMin, market:d.market};
  const full={ict:ictAnalyze(rows,cfg,P), vs:volStats(rows,P)};
  const h={block, chart, candles, vol, avg, ann, annVol, note, rows, fmt, cfg, full, d, t, C, lane:'wyckoff', cursor:null, ruler:null, tip, el, wrap};
  // tooltip fed by the library's crosshair (OHLC, %, volume vs mean, % of dealing range)
  chart.subscribeCrosshairMove(p=>{ if(!p.point||p.logical==null){ tip.style.display='none'; return; } const i=Math.round(p.logical); if(i<0||i>=N){ tip.style.display='none'; return; }
    if(!h.view){ tip.style.display='none'; return; } const c=rows[i], up=c[4]>=c[1], vs=h.view.vs, ict=h.view.ict, ratio=vs.ratio[i];
    let s=`<div class="t">${c[6].slice(5,16).replace('T',' ')}Z</div><div>O ${fmt(c[1])} · H ${fmt(c[2])} · L ${fmt(c[3])}</div><div class="${up?'u':'d'}">C ${fmt(c[4])} (${((c[4]-c[1])/c[1]*100).toFixed(2)}%)</div>`;
    if(h.lane==='wyckoff') s+=`<div>KL ${c[5].toLocaleString('en-US',{maximumFractionDigits:2})}${ratio!=null?` · ${ratio.toFixed(2)}× TB`:''}</div>`;
    if(h.lane==='ict'&&ict&&i<ict.n) s+=`<div class="t">${((c[4]-ict.lo)/((ict.hi-ict.lo)||1)*100).toFixed(0)}% dealing range</div>`;
    if(h.cursor!=null) s+=`<div class="t">replay · nến ${i+1}/${h.cursor+1}</div>`;
    tip.innerHTML=s; tip.style.display='block'; const r=el.getBoundingClientRect(), x=p.point.x, y=p.point.y; tip.style.left=(el.offsetLeft+(x>r.width*0.65?x-tip.offsetWidth-14:x+14))+'px'; tip.style.top=(el.offsetTop+y+12)+'px'; });
  el.addEventListener('mouseleave',()=>{ tip.style.display='none'; });
  const ctl=block.querySelector('.zoom'); if(ctl){ const ts=chart.timeScale(), z=f=>{ const r=ts.getVisibleLogicalRange(); if(!r)return; const c=(r.from+r.to)/2, hw=(r.to-r.from)/2*f; ts.setVisibleLogicalRange({from:c-hw,to:c+hw}); };
    const q=k=>ctl.querySelector(`[data-z="${k}"]`); if(q('in')) q('in').onclick=()=>z(1/1.25); if(q('out')) q('out').onclick=()=>z(1.25); if(q('reset')) q('reset').onclick=()=>ts.fitContent();
    if(q('ruler')) q('ruler').onclick=()=>toggleRuler(h); if(q('replay')) q('replay').onclick=()=>toggleReplay(h); }
  // ruler + replay pointer handling on the chart element (library keeps its own drag; a click without drag is what we use)
  let down=null; el.addEventListener('pointerdown',e=>{ down={x:e.clientX,y:e.clientY}; }); el.addEventListener('pointerup',e=>{ if(!down)return; const moved=Math.hypot(e.clientX-down.x,e.clientY-down.y)>4; down=null; if(moved)return; const r=el.getBoundingClientRect(); onClick(h, e.clientX-r.left, e.clientY-r.top); });
  return h;
}

// The view = engines' results for the current mode: the full window, or the prefix up to the replay cursor (§5.3).
function viewFor(h){ if(h.cursor==null) return {ict:Object.assign({n:h.rows.length},h.full.ict), vs:h.full.vs};
  const rows=h.rows.slice(0,h.cursor+1); return {ict:Object.assign({n:rows.length},ictAnalyze(rows,h.cfg,h.P||{})), vs:volStats(rows,h.P||{})}; }

function applyLane(h, lane, P){
  h.lane=lane; h.P=P; const {rows,d,t,C,fmt}=h; const rowsV=h.cursor==null?rows:rows.slice(0,h.cursor+1); h.view=viewFor(h);
  const compact=!!t.compact, cfgS={compact,fmt};
  candlesData(h);
  const wy=h.cursor==null?(t.wy||{}):{...(t.wy||{}), events:((t.wy||{}).events||[]).filter(e=>idxOf(rows,e.time)<=h.cursor), phases:((t.wy||{}).phases||[]).filter(p=>spanOf(rows,p.from)<=h.cursor)};
  let S=[]; if(t.window) S=S.concat(windowShape(rowsV,t.window.from));
  if(lane==='ict') S=S.concat(ictShapes(rowsV,h.view.ict,cfgS)); else S=S.concat(wyckoffShapes(rowsV,wy,cfgS));
  S=S.concat(levelShapes(rowsV,t.levels,lane,fmt));
  if(!compact&&h.cursor==null) S=S.concat(planShapes(rows,d.plans,d.invalidation,cfgS));
  if(h.ruler&&h.ruler.entry!=null&&h.ruler.stop!=null) S=S.concat(rulerShapes(h.ruler.entry,h.ruler.stop,h.ruler.i1,h.ruler.i2,fmt));
  else if(h.ruler&&h.ruler.entry!=null) S=S.concat([{kind:'hseg',i1:h.ruler.i1-0.5,i2:h.ruler.i1+0.5,price:h.ruler.entry,stroke:'ink',sw:1.5,label:'vào '+fmt(h.ruler.entry),labelAt:'axis'}]);
  h.ann.set(S);
  const showVol=lane==='wyckoff'; h.vol.applyOptions({visible:showVol}); h.avg.applyOptions({visible:showVol});
  if(showVol){ const vs=h.view.vs, P_=P||{}, n=rowsV.length;
    h.vol.setData(rowsV.map((c,i)=>{ const r=vs.ratio[i], up=c[4]>=c[1]; const hi=r!=null&&r>=P_.high; return {time:unix(c[6]), value:c[5], color:withAlpha(hi?C.w:(up?C.up:C.down), hi?(r>=P_.spike?1:0.85):0.42)}; }));
    h.avg.setData(rowsV.map((c,i)=>vs.avg[i]==null?{time:unix(c[6])}:{time:unix(c[6]),value:vs.avg[i]}));
    const L=[]; if(!compact){ const spikes=rowsV.map((c,i)=>({i,r:vs.ratio[i]})).filter(o=>o.r!=null&&o.r>=P_.spike).sort((a,b)=>b.r-a.r), gapN=Math.ceil(n/40), labeled=[];
      spikes.forEach(o=>{ if(labeled.some(j=>Math.abs(j-o.i)<gapN))return; labeled.push(o.i); L.push({kind:'label',i:o.i,price:rowsV[o.i][5],text:o.r.toFixed(1)+'×',color:'w',anchor:'middle',dx:0,dy:-7}); });
      L.push({kind:'label',i:null,price:vs.avg.filter(v=>v!=null).slice(-1)[0]||0,text:'TB '+(P_.lookback||20)+' nến',color:'faint',anchor:'end',dx:-4,dy:-7}); }
    h.annVol.set(L); h.note.set(''); }
  else { h.vol.setData([]); h.avg.setData([]); h.annVol.set([]); h.note.set('khối lượng không thuộc ICT — pane để trống để chart giữ nguyên kích thước khi đổi phương pháp'); }
}
function candlesData(h){ const rows=h.cursor==null?h.rows:h.rows.slice(0,h.cursor+1); if(h._n===rows.length) return; h._n=rows.length; h.candles.setData(rows.map(r=>({time:unix(r[6]), open:r[1], high:r[2], low:r[3], close:r[4]}))); }

// ---- ruler (R) and replay (P): per-chart modes, never persisted
function setMode(h, msg){ const st=h.block.querySelector('.mode-status'); if(st){ st.textContent=msg||''; st.hidden=!msg; } h.block.classList.toggle('mode-ruler',!!h.ruler); h.block.classList.toggle('mode-replay',h.cursor!=null); }
function toggleRuler(h){ if(h.ruler){ h.ruler=null; setMode(h,''); } else { h.ruler={entry:null,stop:null,i1:null,i2:null}; setMode(h,'thước R:R — click 1 = vào lệnh, click 2 = dừng lỗ · Esc xoá'); } applyLane(h,h.lane,h.P); }
function toggleReplay(h){ if(h.cursor!=null){ stopAuto(h); h.cursor=null; setMode(h,''); } else { h.cursor=Math.max(30,Math.floor(h.rows.length*0.5)); setMode(h,`replay — click chọn nến bắt đầu · ← → từng nến · Space chạy · Esc thoát · nến ${h.cursor+1}/${h.rows.length}`); } applyLane(h,h.lane,h.P); if(h.cursor!=null) h.chart.timeScale().scrollToRealTime(); }
function stepReplay(h, k){ if(h.cursor==null)return; const c=Math.max(30,Math.min(h.rows.length-1,h.cursor+k)); if(c===h.cursor)return; h.cursor=c; setMode(h,`replay — ← → từng nến · Space ${h._auto?'dừng':'chạy'} · Esc thoát · nến ${c+1}/${h.rows.length}`); applyLane(h,h.lane,h.P); h.chart.timeScale().scrollToRealTime(); }
function stopAuto(h){ if(h._auto){ clearInterval(h._auto); h._auto=null; } }
function autoReplay(h){ if(h.cursor==null)return; if(h._auto){ stopAuto(h); setMode(h,`replay — ← → từng nến · Space chạy · Esc thoát · nến ${h.cursor+1}/${h.rows.length}`); return; } h._auto=setInterval(()=>{ if(h.cursor>=h.rows.length-1){ stopAuto(h); return; } stepReplay(h,1); },350); }
function onClick(h, x, y){ const ts=h.chart.timeScale(), i=Math.round(ts.coordinateToLogical(x)), price=h.candles.coordinateToPrice(y); if(price==null||!isFinite(i))return;
  if(h.ruler){ if(h.ruler.entry==null){ h.ruler.entry=price; h.ruler.i1=i; h.ruler.i2=i+6; setMode(h,'thước R:R — click 2 = dừng lỗ · Esc xoá'); } else if(h.ruler.stop==null){ h.ruler.stop=price; h.ruler.i2=Math.max(i,h.ruler.i1+2); const risk=Math.abs(price-h.ruler.entry); setMode(h,`thước R:R — rủi ro ${h.fmt(risk)} (${(risk/h.ruler.entry*100).toFixed(2)}%) · 1R/2R/3R vẽ phía lời · Esc xoá`); } else { h.ruler={entry:price,stop:null,i1:i,i2:i+6}; setMode(h,'thước R:R — click 2 = dừng lỗ · Esc xoá'); } applyLane(h,h.lane,h.P); return; }
  if(h.cursor!=null){ if(i>=0&&i<h.rows.length){ h.cursor=Math.max(30,i); stopAuto(h); setMode(h,`replay — ← → từng nến · Space chạy · Esc thoát · nến ${h.cursor+1}/${h.rows.length}`); applyLane(h,h.lane,h.P); } } }

// =============================================================================================== page
function init(DATA, P){
  let lane='wyckoff', C=colors(); const charts=[]; let focus=null;
  for(const key in DATA){ const d=DATA[key]; const entry=d.tiers.find(t=>t.key==='entry');
    d.tiers.forEach(t=>{ const block=document.getElementById(`${t.key}-${key}`); if(!block||!block.querySelector('.chart'))return; if(t.compact&&entry) t.window={from:entry.rows[0][6]};
      const h=makeChart(block,d,t,P,C); h.key=key; charts.push(h); block.addEventListener('pointerenter',()=>{ focus=h; }); }); }
  function render(){ document.body.dataset.lane=lane; document.querySelectorAll('.lane-btn').forEach(b=>b.classList.toggle('active',b.dataset.lane===lane));
    const drawn=lane==='wyckoff'||lane==='ict';
    for(const key in DATA){ const d=DATA[key];
      d.tiers.forEach(t=>{ const block=document.getElementById(`${t.key}-${key}`); if(!block)return; const wrap=block.querySelector('.chart-wrap'), st=block.querySelector('.lane-status'); if(!wrap)return;
        wrap.hidden=!drawn; st.hidden=drawn; if(!drawn){ st.innerHTML=`<span class="lane-dot"></span><span><b>${lane==='footprint'?'Footprint':'Heatmap'}</b> — ${d.dims[lane]}</span>`; } });
      const leg=document.getElementById(`legend-${key}`); if(leg){ leg.hidden=!drawn; if(drawn){ leg.innerHTML = lane==='wyckoff'
        ? `<span><i class="sw up"></i>nến đóng tăng</span><span><i class="sw down"></i>nến đóng giảm</span><span><i class="sw vol"></i>khối lượng${d.tick?' (tick, MT5)':''}</span><span><i class="sw volhi"></i>KL ≥ ${P.high}× TB ${P.lookback} nến (≥ ${P.spike}× ghi số)</span><span><i class="sw tr"></i>biên vùng giao dịch (AR / SC)</span><span><i class="sw ph"></i>pha A–E</span><span>● sự kiện Wyckoff do phân tích đầy đủ đặt</span>${d.plans&&d.plans.length?'<span><i class="sw plan"></i>kế hoạch lệnh từ trades/ (hộp đỏ = rủi ro, xanh = lời)</span>':''}`
        : `<span><i class="sw fvgb"></i>FVG tăng</span><span><i class="sw fvgs"></i>FVG giảm (nét chấm = CE 0.5)</span><span><i class="sw ob"></i>OB: đường open + 0.5 mean threshold (mờ = đã chạm open)</span><span><i class="sw liq"></i>BSL / SSL / old high-low / ERL (× = quét, thân không đóng qua)</span><span><i class="sw lvl"></i>PDH/PDL · PWH/PWL · ASIA/LDN H-L (× quét · ✓ đóng qua)</span><span><i class="sw eq"></i>EQ của dealing range BSL↔SSL gần nhất · premium trên / discount dưới</span><span><i class="sw cisd"></i>CISD (● = nến đóng qua)</span>${d.kz?'<span><i class="sw kz"></i>killzone LDN / NY AM / NY PM theo session-model (½ = trọng số giảm)</span>':'<span>killzone: không vẽ ở khung này</span>'}<span>MSS↑/↓ nét đậm = có displacement; nét đứt = đóng qua swing nhưng thiếu displacement</span><span>OTE .62/.705/.79 và −2σ/−2.5σ/−4σ chỉ vẽ cho MSS mới nhất còn hiệu lực</span><span class="muted">ngưỡng số là tham số dự án (analysis-params.json → project_defined.ict)</span>`; } } }
    if(drawn) charts.forEach(h=>applyLane(h,lane,P)); }
  function retheme(){ C=colors(); charts.forEach(h=>{ h.C=C; h.chart.applyOptions(chartOptions(C,h.fmt)); h.candles.applyOptions({upColor:C.surface2, downColor:C.down, borderUpColor:C.up, borderDownColor:C.down, wickUpColor:C.up, wickDownColor:C.down, priceLineColor:withAlpha(C.ink,0.5)}); h.avg.applyOptions({color:withAlpha(C.ink2,0.8)}); h.ann.setColors(C); h.annVol.setColors(C); h.note.setColors(C); }); render(); }
  new MutationObserver(retheme).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
  if(root.matchMedia){ const mq=root.matchMedia('(prefers-color-scheme: dark)'); (mq.addEventListener?mq.addEventListener('change',retheme):mq.addListener(retheme)); }
  root.setLane=l=>{ lane=l; render(); };
  document.addEventListener('keydown',e=>{ if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA')return; const k={'1':'wyckoff','2':'ict','3':'footprint','4':'heatmap'}[e.key]; if(k){ root.setLane(k); return; }
    const h=focus||charts[charts.length-1]; if(!h)return;
    if(e.key==='End'){ h.chart.timeScale().scrollToRealTime(); e.preventDefault(); }
    else if(e.key==='r'||e.key==='R'){ toggleRuler(h); }
    else if(e.key==='p'||e.key==='P'){ toggleReplay(h); }
    else if(e.key==='Escape'){ if(h.ruler){ h.ruler=null; setMode(h,''); applyLane(h,h.lane,h.P); } else if(h.cursor!=null){ toggleReplay(h); } }
    else if(h.cursor!=null&&e.key==='ArrowLeft'){ stepReplay(h,-1); e.preventDefault(); }
    else if(h.cursor!=null&&e.key==='ArrowRight'){ stepReplay(h,1); e.preventDefault(); }
    else if(h.cursor!=null&&e.key===' '){ autoReplay(h); e.preventDefault(); } });
  render();
  root.__charts=charts;   // for the Playwright smoke test only
  return charts;
}
api.init=init;
return api;
});
