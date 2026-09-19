#!/usr/bin/env python3
"""Vietnamese review page for the trade journal ("Nhật ký giao dịch"), rendered from code by scripts/journal.py render.

Design (2026-09-11, same tokens as the chart pages via artifact_theme.py): a trader reads this page to answer four
questions in order — is the pilot alive and why has it (not) traded · what is the account doing (R curve, stats) ·
what trades exist (ledger) · what did each trade teach (reviews). Every number is computed here from trades/index.jsonl,
the pilot logs and the automation config; prose fields are the human's/Claude's review text.
"""
import collections, datetime, html, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import artifact_theme as theme  # noqa: E402
# CLAUDE.md §50: the journal is the only page where a trade has an ACTUAL path, and the only one that can say
# whose account rules and which risk ceiling the numbers below were produced under. Which fields it owes is
# docs/architecture/ui-fields.json, read through scripts/ui_contract.py.
import ui_contract as UI  # noqa: E402
import account_profile as AP  # noqa: E402
import trading_env  # noqa: E402
import i18n  # noqa: E402

# Same contract as the chart pages: every user-facing string comes from docs/architecture/i18n.json, every
# fragment is rendered once per locale into `lang`-tagged siblings, and one CSS rule shows one. The per-trade
# REVIEW fields are the exception -- human/Claude prose, shown verbatim through i18n.vi_source and marked.
T, DUAL = i18n.t, i18n.dual

e = html.escape
PILOT_DIRS = {"spot": "data/live/pilot", "futures": "data/live/pilot-futures"}
# profile top5 (scripts/strategy-runner.py): its logs sit next to the legacy futures log; "signal" records play the role of "eval"
TOP5_LOGS = {"top5 crypto (futures testnet)": ("data/live/pilot-futures", "top5-log.jsonl"), "top5 CFD (MT5 demo)": ("data/live/pilot-futures", "top5-mt5-log.jsonl")}


def f(v):
    if v is None or v == "":
        return "—"
    return f"{v:,.2f}" if isinstance(v, float) else (f"{v:,}" if isinstance(v, int) and not isinstance(v, bool) else str(v))


def when(iso, lang=i18n.DEFAULT):
    """Displayed time, always carrying its zone name (EN -> UTC, VI -> VNT). Presentation only: the stored
    timestamps and everything journal.py computes from them are untouched."""
    return i18n.stamp(iso, lang, "%-d/%-m %H:%M") if iso and len(iso) >= 16 else "—"


def pilot_activity(now):
    """Per market: state + evaluation statistics from data/live/<pilot dir>/log.jsonl and the automation config."""
    cfg = {}
    try:
        cfg = json.load(open(os.path.join(ROOT, "docs/architecture/automation-config.json"), encoding="utf-8"))
    except Exception:
        pass
    out = []
    sources = [(m, d) for m, (d, _) in TOP5_LOGS.items()]
    for market, d in sources:
        p = os.path.join(ROOT, d, TOP5_LOGS[market][1] if market in TOP5_LOGS else "log.jsonl")
        recs = []
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                try:
                    recs.append(json.loads(line))
                except Exception:
                    pass
        evals = [r for r in recs if r.get("kind") in ("eval", "signal")]
        entries = [r for r in recs if r.get("kind") == "entry"]
        exits = [r for r in recs if r.get("kind") in ("exit", "flatten")]
        day_ago = (now - datetime.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
        ev24 = [r for r in evals if r.get("t", "") >= day_ago]
        reasons = collections.Counter(x for r in evals for x in (r.get("reasons") or []))
        last_t = max((r.get("t", "") for r in recs), default="")
        stop = os.path.exists(os.path.join(ROOT, d, "STOP"))
        enabled = cfg.get("enabled", True) and (cfg.get("layers") or {}).get("pilot", True)
        pp = cfg.get("pilot_process") or {}
        stopped_at = pp.get("stopped_at") if market == "spot" else None
        if stop or not enabled:
            state, cls = ("journal.state.stopped", "warn")
        elif last_t and (now - datetime.datetime.strptime(last_t, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)).total_seconds() < 1200:
            state, cls = ("journal.state.running", "long")
        else:
            state, cls = ("journal.state.not_ticking", "short")
        out.append(dict(market=market, state=state, cls=cls, stop=stop, enabled=enabled, stopped_at=stopped_at, last=last_t,
                        n_eval=len(evals), n_eval24=len(ev24), n_ok=sum(1 for r in evals if r.get("ok")), n_entry=len(entries), n_exit=len(exits),
                        first=min((r.get("t", "") for r in evals), default=""), reasons=reasons.most_common(5),
                        env=cfg.get("execution", {}).get("environment", "?")))
    return out


def r_curve(closed):
    """Cumulative-R chart (TradingView Lightweight Charts, same vendored build as the chart pages): an area series by close
    time, one marker per trade, crosshair tooltip with id / setup / R. Empty state when nothing is closed."""
    rs = [r for r in closed if isinstance(r.get("r_multiple"), (int, float))]
    if not rs:
        return f'<div class="empty">{i18n.tx("journal.r_curve.empty")}</div>'
    rs = sorted(rs, key=lambda r: r.get("date_closed") or r.get("date_opened") or "")
    cum, pts, last_t = 0.0, [], 0
    for k, r in enumerate(rs):
        cum += r["r_multiple"]
        t = _unix(r.get("date_closed") or r.get("date_opened")) or (last_t + 1)
        if t <= last_t:                      # the library needs strictly increasing times; same-second closes get +1s
            t = last_t + 1
        last_t = t
        pts.append(dict(time=t, value=round(cum, 4), r=r["r_multiple"], id=r.get("id"), setup=r.get("setup_type"), n=k + 1))
    data = json.dumps(pts, ensure_ascii=False)
    return (f'<div class="rcurve-wrap"><div class="rcurve" id="rcurve"></div><div class="tip" id="rcurve-tip"></div></div>'
            f'<script>JournalChart.rcurve(document.getElementById("rcurve"), document.getElementById("rcurve-tip"), {data});</script>')


def _unix(iso):
    if not iso:
        return None
    try:
        return int(datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


VENDOR_JS = os.path.join(ROOT, "scripts", "vendor", "lightweight-charts.standalone.production.js")
JOURNAL_JS = r"""
window.JournalChart = { I18N:{}, LOCALES:{}, DFLT:'en',
  lang(){ const l=document.documentElement.getAttribute('data-lang'); return (l&&this.LOCALES[l])?l:this.DFLT; },
  L(k,pa){ const m=this.I18N[k]||{}; let x=m[this.lang()]||m[this.DFLT]||k; if(pa) for(const q in pa) x=x.split('{'+q+'}').join(pa[q]); return x; },
  tz(){ return (this.LOCALES[this.lang()]||{}).tz||{name:'UTC',offset_minutes:0}; },
  numLocale(){ return ((this.LOCALES[this.lang()]||{}).number_locale)||'en-US'; },
  time(unixSec){ const t=this.tz(); return new Date((unixSec+t.offset_minutes*60)*1000).toISOString().slice(5,16).replace('T',' ')+' '+t.name; },
  rcurve(el, tip, pts){
  const cs=getComputedStyle(document.documentElement), v=k=>cs.getPropertyValue(k).trim(), mono=v('--mono')||'monospace';
  const C={accent:v('--accent'),line:v('--line'),lineStrong:v('--line-strong'),faint:v('--faint'),ink:v('--ink'),ink2:v('--ink-2'),surface:v('--surface'),up:v('--up'),down:v('--down')};
  const L=window.LightweightCharts, chart=L.createChart(el,{autoSize:true,layout:{background:{type:'solid',color:C.surface},textColor:C.faint,fontFamily:mono,fontSize:10,attributionLogo:false},
    grid:{vertLines:{color:C.line},horzLines:{color:C.line}},rightPriceScale:{borderColor:C.lineStrong,scaleMargins:{top:0.15,bottom:0.1}},timeScale:{borderColor:C.lineStrong,timeVisible:true,secondsVisible:false,rightOffset:2,tickMarkFormatter:t=>window.JournalChart.time(t)},
    crosshair:{mode:L.CrosshairMode.Normal},localization:{locale:window.JournalChart.numLocale(),priceFormatter:x=>(x>=0?'+':'')+x.toFixed(2)+'R',timeFormatter:t=>window.JournalChart.time(t)},handleScale:{axisPressedMouseMove:true,mouseWheel:true,pinch:true},kineticScroll:{mouse:true,touch:true}});
  const s=chart.addSeries(L.AreaSeries,{lineColor:C.accent,lineWidth:2,topColor:C.accent+'33',bottomColor:C.accent+'05',priceLineVisible:false,lastValueVisible:true,crosshairMarkerRadius:4});
  s.setData(pts.map(p=>({time:p.time,value:p.value}))); s.createPriceLine({price:0,color:C.lineStrong,lineWidth:1,lineStyle:L.LineStyle.Solid,axisLabelVisible:false});
  L.createSeriesMarkers(s, pts.map(p=>({time:p.time,position:p.r>=0?'aboveBar':'belowBar',shape:'circle',color:p.r>=0?C.up:C.down,size:0.8})));
  chart.timeScale().fitContent();
  // The tooltip re-resolves on every crosshair move, so it follows the language for free. The TIME AXIS does
  // not: the library caches its tick labels, so after a switch the axis would keep printing the boot
  // language's zone (UTC) under a Vietnamese page -- two zones on one page, which is the exact misread the
  // mandatory zone suffix exists to prevent. Re-applying the formatters invalidates that cache.
  new MutationObserver(()=>{ chart.applyOptions({timeScale:{tickMarkFormatter:t=>window.JournalChart.time(t)},
    localization:{timeFormatter:t=>window.JournalChart.time(t)}}); })
    .observe(document.documentElement,{attributes:true,attributeFilter:['data-lang']});
  chart.subscribeCrosshairMove(q=>{ if(!q.point||!q.time){ tip.style.display='none'; return; } const p=pts.find(x=>x.time===q.time); if(!p){ tip.style.display='none'; return; }
    const J=window.JournalChart;
    tip.innerHTML=`<div class="t">${J.L('journal.r_curve.tip',{n:p.n})} · ${J.time(p.time)}</div><div><b>${p.id||''}</b></div><div>${p.setup||''}</div><div class="${p.r>=0?'u':'d'}">${p.r>=0?'+':''}${p.r.toFixed(2)}R · ${J.L('journal.r_curve.cumulative')} ${p.value>=0?'+':''}${p.value.toFixed(2)}R</div>`;
    tip.style.display='block'; const r=el.getBoundingClientRect(), x=q.point.x; tip.style.left=(el.offsetLeft+(x>r.width*0.65?x-tip.offsetWidth-14:x+14))+'px'; tip.style.top=(el.offsetTop+q.point.y+12)+'px'; });
  el.addEventListener('mouseleave',()=>{ tip.style.display='none'; });
}};
"""


def vendor_script():
    """The vendored chart library, the journal's chart code, and the catalog slice that code resolves at runtime
    (the R-curve tooltip and its axis). Same route chart.js takes: a canvas label cannot be a lang sibling."""
    boot = ("window.JournalChart.I18N=" + json.dumps(i18n.js_catalog("journal.r_curve."), ensure_ascii=False)
            + ";window.JournalChart.LOCALES=" + json.dumps(i18n.js_locales(), ensure_ascii=False)
            + ";window.JournalChart.DFLT=" + json.dumps(i18n.DEFAULT) + ";")
    with open(VENDOR_JS, encoding="utf-8") as fh:
        return "<script>\n" + fh.read() + "\n</script>\n<script>" + JOURNAL_JS + boot + "</script>"


# The artifact's identity in the gallery and the browser tab. Kept STABLE across redeploys -- a changed title
# reads as a different page. The language toggle sets document.title at runtime instead, so the tab still reads
# in the chosen language.
TITLE = "Trade Journal & Performance"   # artifact-identity: stable across redeploys (renamed from "Nhật ký giao dịch" 2026-09-18, user decision; CLAUDE.md §50 area name)

# The pilot's volume gate, read from the registry rather than spelled into the page. It used to be the literal
# "KL ≥ 1.5×" in the card, a second source for a number analysis-params.json already owns.
VOL_HIGH = ((json.load(open(os.path.join(ROOT, "docs/architecture/analysis-params.json"), encoding="utf-8"))
             .get("project_defined", {}).get("volume", {}).get("high_min_ratio", 1.5)))


def LEDGER_LABEL(col):
    """A ledger column head. Entry, Stop, R and P&L are the trading vocabulary this journal is written in --
    Vietnamese traders say them in English too -- so they are spelled once here rather than duplicated in the
    catalog. Everything with a natural translation goes through the catalog, "Targets" included: it is a plain
    word, not a term of art, and leaving it here left one English column head standing in the Vietnamese page."""
    fixed = {"entry": "Entry", "stop": "Stop", "r": "R", "pnl": "P&amp;L USDT"}
    return fixed.get(col) or i18n.tx("journal.col." + col)


def chip(v, cls=None):
    """Trade-record values (LONG/SHORT/WIN/LOSS/OPEN/PLANNED) are machine values from the trade schema and read
    the same in both languages, so the chip prints them as stored."""
    v = str(v or "")
    if not v:
        return ""
    cls = cls or {"WIN": "long", "LOSS": "short", "OPEN": "setup", "CLOSED": "wait", "PLANNED": "wait", "BREAKEVEN": "wait", "CANCELLED": "wait"}.get(v, "wait")
    return f'<span class="chip chip-{cls}">{e(v)}</span>'


def signed(v):
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return e(f(v))
    return f'<span class="{"pos" if v > 0 else ("neg" if v < 0 else "")}">{v:+.2f}</span>'


CSS = r"""
<style>
__TOKENS__
__I18N__
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:14px;line-height:1.55;-webkit-font-smoothing:antialiased}
.mono,.num{font-family:var(--mono);font-variant-numeric:tabular-nums}
.muted{color:var(--muted)} .pos{color:var(--up)} .neg{color:var(--down)}
.topbar{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--surface) 92%,transparent);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
.topbar-in{max-width:1180px;margin:0 auto;padding:10px 20px;display:flex;align-items:center;gap:18px;flex-wrap:wrap}
.brand-title{font-weight:800;font-size:15px} .brand-sub{font-family:var(--mono);font-size:11px;color:var(--muted)}
.nav{display:flex;gap:4px;margin-left:auto} .nav a{font-family:var(--mono);font-size:12px;font-weight:700;text-decoration:none;color:var(--ink-2);padding:6px 10px;border-radius:6px;border:1px solid transparent}
.nav a:hover{background:var(--surface-2);border-color:var(--line)} .nav a:focus-visible,summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.page{max-width:1180px;margin:0 auto;padding:22px 20px 80px;display:flex;flex-direction:column;gap:22px}
h1{font-size:clamp(22px,3vw,30px);font-weight:800;letter-spacing:-.02em;margin:0;text-wrap:balance}
h2{font-size:15px;font-weight:800;margin:0 0 10px;display:flex;align-items:baseline;gap:10px} h2 small{font-family:var(--mono);font-size:11px;color:var(--muted);font-weight:500}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0 0 6px}
.lede p{margin:6px 0 0;color:var(--ink-2);max-width:70ch}
section{scroll-margin-top:64px}
.chip{display:inline-flex;align-items:center;font-family:var(--mono);font-size:11px;font-weight:700;letter-spacing:.03em;padding:3px 9px;border-radius:999px;border:1px solid transparent;white-space:nowrap}
.chip-wait{background:var(--surface-3);color:var(--ink-2);border-color:var(--line-strong)} .chip-long{background:var(--up-soft);color:var(--up);border-color:var(--up)}
.chip-short{background:var(--down-soft);color:var(--down);border-color:var(--down)} .chip-setup{background:var(--w-soft);color:var(--w);border-color:var(--w)} .chip-warn{background:var(--warn-soft);color:var(--warn);border-color:var(--warn)}
.chip-lg{font-size:12.5px;padding:5px 12px}
.pilot{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:12px}
.pcard{background:var(--surface);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);padding:16px 18px;display:flex;flex-direction:column;gap:10px}
.pcard-head{display:flex;align-items:center;gap:10px} .pcard-head .mk{font-family:var(--mono);font-weight:800;font-size:15px} .pcard-head .env{font-family:var(--mono);font-size:11px;color:var(--muted)}
.pgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.pk{background:var(--surface-2);border-radius:8px;padding:8px 10px} .pk .l{font-family:var(--mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--faint)} .pk .v{font-family:var(--mono);font-size:18px;font-weight:700;font-variant-numeric:tabular-nums} .pk .s{font-family:var(--mono);font-size:10.5px;color:var(--muted)}
.verdict{font-size:13.5px;border-left:3px solid var(--accent);padding:6px 12px;background:var(--surface-2);border-radius:0 8px 8px 0}
.reasons{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:4px;font-size:12.5px}
.reasons li{display:flex;gap:10px;align-items:center} .reasons .bar{height:6px;border-radius:3px;background:var(--i);opacity:.7;min-width:2px} .reasons .n{font-family:var(--mono);color:var(--muted);min-width:34px;text-align:right}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));border:1px solid var(--line);border-radius:10px;background:var(--surface);overflow:hidden}
.tile{padding:12px 16px;border-right:1px solid var(--line)} .tile:last-child{border-right:0}
.tile .l{font-family:var(--mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);margin-bottom:4px} .tile .v{font-family:var(--mono);font-size:22px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.2} .tile .s{font-family:var(--mono);font-size:11px;color:var(--muted);margin-top:2px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
.rcurve-wrap{position:relative} .rcurve{display:block;width:100%;height:240px}
.tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--line-strong);border-radius:6px;padding:6px 9px;font-family:var(--mono);font-size:11px;color:var(--ink);box-shadow:var(--shadow);display:none;z-index:5;white-space:nowrap;line-height:1.5}
.tip .t{color:var(--muted)} .tip .u{color:var(--up)} .tip .d{color:var(--down)}
.empty{color:var(--muted);font-size:13px;padding:18px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.card h3{margin:0 0 6px;font-size:13px;font-weight:800}
.table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:12.5px} th,td{padding:8px 12px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap;vertical-align:top}
th{font-family:var(--mono);font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:var(--faint);font-weight:600;background:var(--surface-2)}
tbody tr:hover{background:var(--surface-2)} td.num,th.num{font-family:var(--mono);font-variant-numeric:tabular-nums;text-align:right} td.id{font-family:var(--mono)} td.setup{white-space:normal;min-width:220px}
details{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:10px 14px} details+details{margin-top:8px} summary{cursor:pointer;font-family:var(--mono);font-size:12.5px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
dl{display:grid;grid-template-columns:200px 1fr;gap:6px 14px;margin:12px 0 4px;max-width:80ch} dt{color:var(--muted);font-size:12.5px} dd{margin:0}
.note{border-left:3px solid var(--w);padding:10px 14px;background:var(--surface);border-radius:0 8px 8px 0;font-size:13px;max-width:80ch}
.note code{font-family:var(--mono);font-size:12px;background:var(--surface-3);padding:1px 5px;border-radius:4px}
footer{font-family:var(--mono);font-size:11px;color:var(--faint);border-top:1px solid var(--line);padding-top:14px;line-height:1.7}
@media (max-width:700px){dl{grid-template-columns:1fr} .pgrid{grid-template-columns:1fr 1fr} .nav{margin-left:0}}
@media (prefers-reduced-motion: reduce){*{transition:none!important}}
</style>
"""


def account_line():
    """§33 + §34 on the performance page: whose rules these trades were placed under, and the one ceiling.

    Two venues, so two profiles -- printed separately rather than merged, because a merged line would imply a
    single set of account rules that does not exist. A venue with no declared profile is NAMED as undeclared;
    the runner refuses to trade it, and a blank here would read as "no rules apply".
    """
    parts = []
    for venue in ("futures", "mt5"):
        try:
            prof = AP.for_venue(venue, "demo")
            parts.append(f"{e(venue)} → <b>{e(prof['id'])}</b>")
        except ValueError:
            parts.append(f"{e(venue)} → <b>{i18n.tx('ctx.none')}</b>")
    pct = f"{trading_env.MAX_RISK_PCT * 100:g}"
    return (f'<div class="card"><div class="k">{i18n.tx("ctx.account_profile")}</div>'
            f'<div class="v mono"{UI.attr("account-profile")}>{" · ".join(parts)}</div>'
            f'<div class="k" style="margin-top:8px">{i18n.tx("ctx.risk")}</div>'
            f'<div class="v"{UI.attr("risk")}>'
            + DUAL(lambda l: T("ctx.risk_value", l, pct=pct)) + '</div></div>')


def render(rows, st, out, closed_real):
    now = datetime.datetime.now(datetime.timezone.utc)
    # The build time, per locale: the zone follows the language like every other displayed time, and it always
    # carries its zone name so a VNT stamp can never be read as a UTC one.
    iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    gen = {l: i18n.stamp(iso, l, "%Y-%m-%d %H:%M") for l in i18n.LOCALES}
    # ---- pilot activity
    def why_lines(p, lang):
        """Why the pilot has (not) traded. Built per locale; `state` arrived from pilot_activity() as a message
        key, not a sentence, so the state chip and this explanation can disagree about language but never about
        fact."""
        why = []
        if p["stop"] or not p["enabled"]:
            stopped = T("journal.why.stopped_at", lang, time=when(p["stopped_at"], lang)) if p.get("stopped_at") else ""
            why.append(T("journal.why.automation_off", lang, stopped=stopped))
        if p["n_eval"] and p["n_ok"] == 0:
            why.append(T("journal.why.no_qualifier", lang, n=p["n_eval"], first=when(p["first"], lang)))
        if p["n_entry"]:
            why.append(T("journal.why.entries", lang, entries=p["n_entry"], exits=p["n_exit"]))
        if not p["n_eval"]:
            why.append(T("journal.why.no_records", lang))
        return why

    pcards = []
    for p in pilot_activity(now):
        def verdict_html(lang, p=p):
            state = T("journal.verdict.ok" if (p["n_entry"] or p["n_ok"] == 0) else "journal.verdict.check", lang)
            return T("journal.verdict", lang, state=state, why="; ".join(why_lines(p, lang)))
        top = max((n for _, n in p["reasons"]), default=1)
        # A rejection reason is a machine-written rule id from the pilot log, not prose -- shown as recorded.
        reasons = "".join(f'<li><span class="n">{n}</span><span class="bar" style="width:{max(2, int(160 * n / top))}px"></span><span>{e(r)}</span></li>'
                          for r, n in p["reasons"]) or f'<li class="muted">{i18n.tx("ui.dash")}</li>'
        pcards.append(f'''<div class="pcard"><div class="pcard-head"><span class="mk">Pilot {p["market"]}</span><span class="chip chip-{p["cls"]} chip-lg">{i18n.tx(p["state"])}</span><span class="env">{DUAL(lambda l, p=p: T("journal.pilot.env", l, env=e(p["env"]), last=when(p["last"], l)))}</span></div>
<div class="verdict">{DUAL(verdict_html)}</div>
<div class="pgrid"><div class="pk"><div class="l">{i18n.tx("journal.pilot.evals24")}</div><div class="v">{p["n_eval24"]}</div><div class="s">{DUAL(lambda l, p=p: T("journal.pilot.evals_total", l, n=p["n_eval"]))}</div></div><div class="pk"><div class="l">{i18n.tx("journal.pilot.qualified")}</div><div class="v">{p["n_ok"]}</div><div class="s">{DUAL(lambda l: T("journal.pilot.rule", l, high=VOL_HIGH))}</div></div><div class="pk"><div class="l">{i18n.tx("journal.pilot.entries_exits")}</div><div class="v">{p["n_entry"]} / {p["n_exit"]}</div><div class="s">{i18n.tx("journal.pilot.from_log")}</div></div></div>
<div><div class="eyebrow" style="margin-bottom:4px">{i18n.tx("journal.pilot.top_reasons")}</div><ul class="reasons">{reasons}</ul></div></div>''')
    # ---- tiles
    wr = f"{st['win_rate'] * 100:.0f}%" if st["win_rate"] is not None else "—"
    tiles = [("journal.tile.closed", st["closed"], ("journal.tile.closed_sub", dict(open=st["open"], planned=st["planned"], rehearsal=st["rehearsal"]))),
             ("journal.tile.win_rate", wr, ("journal.tile.win_rate_sub", dict(wins=st["wins"], losses=st["losses"]))),
             ("journal.tile.expectancy", f(st["avg_r"]), ("journal.tile.expectancy_sub", dict(win=f(st["avg_win_r"]), loss=f(st["avg_loss_r"])))),
             ("journal.tile.profit_factor", f(st["profit_factor"]), ("journal.tile.profit_factor_sub", dict(total=f(st["total_r"]), usd=f(st["pnl_usd"])))),
             ("journal.tile.max_dd", f"{f(st['max_drawdown_r'])} R", ("journal.tile.max_dd_sub", dict(n=st["worst_losing_streak"])))]
    tiles_html = "".join(f'<div class="tile"><div class="l">{i18n.tx(k)}</div><div class="v">{v}</div>'
                         f'<div class="s">{DUAL(lambda l, sk=sk, sp=sp: T(sk, l, **sp))}</div></div>'
                         for k, v, (sk, sp) in tiles)

    # ---- breakdowns
    def table_by(key, title_key):
        g = st.get("by_" + key) or {}
        if not g:
            return ""
        rws = "".join(f"<tr><td>{e(k)}</td><td class='num'>{v['n']}</td><td class='num'>{v['win_rate'] * 100:.0f}%</td><td class='num'>{signed(v['avg_r'])}</td></tr>"
                      for k, v in sorted(g.items(), key=lambda kv: -kv[1]['n']))
        # The locale wrappers go INSIDE each <th>: a <span> between <tr> and <th> is invalid table markup and
        # the browser hoists it out of the table entirely.
        head = "".join(f"<th{' class=\'num\'' if c != 'group' else ''}>{i18n.tx('journal.col.' + c)}</th>"
                       for c in ("group", "trades", "wins", "avg_r"))
        return (f"<div class='card'><h3>{i18n.tx(title_key)}</h3><div class='table-wrap'><table><thead><tr>{head}</tr>"
                f"</thead><tbody>{rws}</tbody></table></div></div>")
    breakdown = "".join(table_by(k, "journal.by." + k) for k in
                        ("setup_type", "instrument", "session", "market", "direction", "exit_type"))

    # ---- ledger
    order = sorted(rows, key=lambda r: r.get("date_opened") or "", reverse=True)
    rehearsal_chip = f'<span class="chip chip-warn">{i18n.tx("journal.rehearsal")}</span>'
    trs = "".join("<tr>" + f"<td class='id'>{e(r['id'])}</td><td>{e(str(r.get('market') or '—'))}</td><td class='mono'{UI.attr('instrument')}>{e(str(r.get('instrument')))}</td><td>{chip(r.get('direction'), 'long' if r.get('direction') == 'LONG' else 'short')}</td>"
                  f"<td class='setup'>{e(str(r.get('setup_type') or ''))}{(' ' + rehearsal_chip) if r.get('rehearsal_mode') else ''}</td><td>{e(str(r.get('session') or '—'))}</td><td class='num'>{f(r.get('entry'))}</td><td class='num'>{f(r.get('stop_loss'))}</td>"
                  f"<td class='num'>{e(f(r.get('targets')))}</td><td class='num'>{f(r.get('planned_rr'))}</td><td>{chip(r.get('status'))}</td><td>{e(str(r.get('exit_type') or ''))}</td><td>{chip(r.get('result'))}</td>"
                  f"<td class='num'>{signed(r.get('r_multiple'))}</td><td class='num'>{signed(r.get('pnl_usd'))}</td><td class='num'>{f(r.get('hold_minutes'))}</td></tr>" for r in order)
    LEDGER_COLS = (("id", 0), ("market", 0), ("instrument", 0), ("direction", 0), ("setup", 0), ("session", 0),
                   ("entry", 1), ("stop", 1), ("targets", 1), ("planned_rr", 1), ("status", 0), ("exit", 0),
                   ("result", 0), ("r", 1), ("pnl", 1), ("hold", 1))
    ledger_head = "".join(f"<th{' class=\'num\'' if num else ''}>{LEDGER_LABEL(c)}</th>" for c, num in LEDGER_COLS)

    # ---- reviews
    REVIEW_FIELDS = (("thesis", "thesis"), ("plan_vs_actual", "plan_vs_actual"), ("followed_plan", "followed_plan"),
                     ("exit_type", "exit_type"), ("exit_reason", "exit_reason"), ("root_cause", "root_cause"),
                     ("is_mistake", "is_mistake"), ("lessons", "lessons"), ("review_notes", "review_notes"),
                     ("what_to_change", "what_to_change"), ("confidence", "confidence"),
                     ("emotional_state", "emotional_state"), ("tags", "tags"), ("screenshots", "screenshots"))
    details = []
    for r in order:
        dl = ""
        for field, key in REVIEW_FIELDS:
            v = ", ".join(r.get(field) or []) if field in ("tags", "screenshots") else r.get(field)
            if v in (None, "", []):
                body = f'<span class="muted">{i18n.tx("journal.field.empty")}</span>'
            else:
                # A review field is what a human (or Claude) WROTE about a trade. Shown verbatim and marked,
                # never translated -- the same rule the chart pages apply to model prose. Phase 2 gives these
                # an optional second-language field rather than machine-translating them.
                body = i18n.vi_source(e(f(v)))
            dl += f'<dt>{i18n.tx("journal.field." + key)}</dt><dd>{body}</dd>'
        details.append(f"<details><summary><b>{e(r['id'])}</b> <span class='mono'>{e(str(r.get('instrument')))}</span> {chip(r.get('direction'), 'long' if r.get('direction') == 'LONG' else 'short')} {chip(r.get('status'))} {chip(r.get('result'))} <span class='mono muted'>R {e(f(r.get('r_multiple')))}</span></summary><dl>{dl}</dl></details>")

    page = f"""<meta charset="utf-8">
<title>{TITLE}</title>
{i18n.switch_js("journal.title")}
{theme.FONTS}
{CSS.replace('__TOKENS__', theme.TOKENS).replace('__I18N__', i18n.switch_css())}
<div class="topbar"><div class="topbar-in"><div><div class="brand-title">{i18n.tx("journal.title")}</div><div class="brand-sub"{UI.attr("freshness")}>{DUAL(lambda l: T("journal.brand_sub", l, gen=gen[l]))}</div></div>
<nav class="nav"><a href="#pilot">{i18n.tx("journal.nav.pilot")}</a><a href="#stats">{i18n.tx("journal.nav.stats")}</a><a href="#ledger">{i18n.tx("journal.nav.ledger")}</a><a href="#reviews">{i18n.tx("journal.nav.reviews")}</a></nav>
{i18n.switch_html()}</div></div>
<div class="page">
<div class="lede"><p class="eyebrow">{i18n.tx("journal.eyebrow")}</p><h1>{i18n.tx("journal.title")}</h1><p>{i18n.tx("journal.lede")}</p>
<p class="i18n-authored">{i18n.tx("ui.vi_source.page")}</p></div>
<section id="pilot"><h2>{i18n.tx("journal.pilot.heading")} <small>data/live/pilot*/log.jsonl (legacy) · top5-log.jsonl / top5-mt5-log.jsonl (profile top5) · docs/architecture/automation-config.json</small></h2><div class="pilot">{''.join(pcards)}</div></section>
<section id="stats"><h2>{i18n.tx("journal.section.balance")} <small>{i18n.tx("journal.section.balance_sub")}</small></h2><div class="tiles">{tiles_html}</div></section>
{vendor_script() if any(isinstance(r.get("r_multiple"), (int, float)) for r in closed_real) else ''}
<section><h2>{i18n.tx("journal.section.r_curve")} <small>{i18n.tx("journal.section.r_curve_sub")}</small></h2><div class="card"{UI.attr("actual-path")}>{r_curve(closed_real)}</div></section>
<section id="account"><h2>{i18n.tx("journal.section.account")}</h2>{account_line()}</section>
{('<section><h2>' + i18n.tx("journal.section.breakdown") + '</h2><div class="grid">' + breakdown + '</div></section>') if breakdown else ''}
<section id="ledger"><h2>{i18n.tx("journal.section.ledger")} <small>{DUAL(lambda l: T("journal.section.ledger_sub", l, n=len(rows)))}</small></h2><div class="table-wrap"><table><thead><tr>{ledger_head}</tr></thead><tbody>{trs or f'<tr><td colspan="16" class="muted">{i18n.tx("journal.empty.trades")}</td></tr>'}</tbody></table></div></section>
<section id="reviews"><h2>{i18n.tx("journal.section.reviews")}</h2>
<div class="note">{i18n.tx("journal.reviews.note")}</div>
<div style="margin-top:12px">{''.join(details) or f'<p class="muted">{i18n.tx("journal.empty.trades")}</p>'}</div></section>
<footer>{DUAL(lambda l: f'<b>{T("journal.footer.sources", l)}</b>: ' + T("journal.footer.detail", l, gen=gen[l]))}<br>Chart: TradingView Lightweight Charts™ · Copyright (c) 2025 TradingView, Inc. · <a href="https://www.tradingview.com/" rel="noopener">tradingview.com</a> · Apache-2.0 (scripts/vendor/NOTICE-lightweight-charts.txt)</footer>
</div>
"""
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"render: {os.path.relpath(out, ROOT)} ({len(rows)} trades)")
