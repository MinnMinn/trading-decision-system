const fs=require('fs'), T=require(process.argv[2]);
const params=JSON.parse(fs.readFileSync(process.argv[3],'utf8')).project_defined;
const series=JSON.parse(fs.readFileSync(process.argv[4],'utf8'));   // [{sym,tf,rows,cfg}]
const BUY=k=>k==='BSL'||k==='OLD-H'||k==='ERL-high', SELL=k=>k==='SSL'||k==='OLD-L'||k==='ERL-low';
const bad=[], cnt={series:0,pools:0,fvg:0,mss:0,ote:0,std:0};
for(const s of series){
  const rows=s.rows; if(!rows.length) continue;
  const a=T.ictAnalyze(rows,s.cfg,params); cnt.series++;
  const H=r=>r[1],L=r=>r[2],C=r=>r[3];
  const n=rows.length, last=C(rows[n-1]), id=`${s.sym} ${s.tf}`;
  if(a.hi>a.lo){ if(Math.abs((last-a.lo)/(a.hi-a.lo)-a.pct)>1e-6) bad.push(id+': pct is not the close inside lo..hi');
                 if(Math.abs(a.eq-(a.lo+a.hi)/2)>1e-6) bad.push(id+': eq is not the midpoint'); }
  const uns=(a.pools||[]).filter(p=>p.swept<0);
  const above=uns.filter(p=>BUY(p.kind)&&p.level>last&&p.kind!=='ERL-high').map(p=>p.level);
  const below=uns.filter(p=>SELL(p.kind)&&p.level<last&&p.kind!=='ERL-low').map(p=>p.level);
  const wantHi=above.length?Math.min(...above):a.whi, wantLo=below.length?Math.max(...below):a.wlo;
  if(Math.abs(wantHi-a.hi)>1e-6) bad.push(id+': range high is not the nearest unswept buyside above');
  if(Math.abs(wantLo-a.lo)>1e-6) bad.push(id+': range low is not the nearest unswept sellside below');
  const wantSrc=(above.length&&below.length)?'pools':((above.length||below.length)?'mixed':'window');
  if(a.drSource!==wantSrc) bad.push(id+': drSource '+a.drSource+' should be '+wantSrc);
  for(const pl of (a.pools||[])){ cnt.pools++;
    if(pl.at==null){ bad.push(id+': pool '+pl.kind+' has no forming bar (`at`)'); continue; }
    if(pl.kind==='ERL-high'||pl.kind==='ERL-low') continue;
    const isH=BUY(pl.kind); let sw=-1;
    for(let j=pl.at+1;j<n;j++){ const hit=isH?(H(rows[j])>pl.level&&C(rows[j])<pl.level):(L(rows[j])<pl.level&&C(rows[j])>pl.level); if(hit){sw=j;break;} }
    if(sw!==pl.swept) bad.push(id+': '+pl.kind+' '+pl.level+' swept flag disagrees with the rows'); }
  for(const f of (a.fvgs||[])){ if(f.mitigated) continue; cnt.fvg++; const i=f.i;
    const ok=i>=1&&i<n-1&&(f.type==='bull'?(H(rows[i-1])<L(rows[i+1])&&Math.abs(f.lo-H(rows[i-1]))<1e-6&&Math.abs(f.hi-L(rows[i+1]))<1e-6)
                                          :(L(rows[i-1])>H(rows[i+1])&&Math.abs(f.lo-H(rows[i+1]))<1e-6&&Math.abs(f.hi-L(rows[i-1]))<1e-6));
    if(!ok) bad.push(id+': an open FVG is not the three-candle gap at its own index'); }
  for(const m of (a.mss||[])){ cnt.mss++;
    if(!(m.i>=0&&m.i<n&&(m.type==='bull'?C(rows[m.i])>m.level:C(rows[m.i])<m.level))) bad.push(id+': MSS is not a body close beyond its swing');
    if(m.extI!=null&&m.originI!=null&&!(m.originI<=m.extI&&m.extI<=m.i)) bad.push(id+': MSS legs out of order'); }
  const o=a.ote;
  if(o&&o.levels){ cnt.ote++; const rs=o.levels.map(x=>x.r), ps=o.levels.map(x=>x.price);
    if(JSON.stringify(rs)!==JSON.stringify([0.62,0.705,0.79])) bad.push(id+': OTE ratios are not 0.62/0.705/0.79');
    const mono=o.type==='bull'?(ps[0]>ps[1]&&ps[1]>ps[2]):(ps[0]<ps[1]&&ps[1]<ps[2]);
    if(!mono) bad.push(id+': OTE prices do not deepen with the ratio');
    if(Math.abs(ps[1]-(ps[0]+ps[2])/2)>1e-6) bad.push(id+': OTE 0.705 is not midway'); }
  const sd=a.std;
  if(sd&&sd.levels){ cnt.std++;
    if(JSON.stringify(sd.levels.map(x=>x.k))!==JSON.stringify([2,2.5,4])) bad.push(id+': STDEV projections are not -2/-2.5/-4');
    const ps=sd.levels.map(x=>x.price);
    const mono=sd.type==='bull'?(ps[0]<ps[1]&&ps[1]<ps[2]):(ps[0]>ps[1]&&ps[1]>ps[2]);
    if(!mono) bad.push(id+': STDEV projections are not ordered'); }
}
process.stdout.write(JSON.stringify({cnt,bad}));
