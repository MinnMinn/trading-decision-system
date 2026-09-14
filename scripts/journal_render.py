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

e = html.escape
PILOT_DIRS = {"spot": "data/live/pilot", "futures": "data/live/pilot-futures"}
# profile top5 (scripts/strategy-runner.py): its logs sit next to the legacy futures log; "signal" records play the role of "eval"
TOP5_LOGS = {"top5 crypto (futures testnet)": ("data/live/pilot-futures", "top5-log.jsonl"), "top5 CFD (MT5 demo)": ("data/live/pilot-futures", "top5-mt5-log.jsonl")}


def f(v):
    if v is None or v == "":
        return "—"
    return f"{v:,.2f}" if isinstance(v, float) else (f"{v:,}" if isinstance(v, int) and not isinstance(v, bool) else str(v))


def when(iso):
    return f"{int(iso[8:10])}/{int(iso[5:7])} {iso[11:16]}Z" if iso and len(iso) >= 16 else "—"


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
            state, cls = ("DỪNG", "warn")
        elif last_t and (now - datetime.datetime.strptime(last_t, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)).total_seconds() < 1200:
            state, cls = ("ĐANG CHẠY", "long")
        else:
            state, cls = ("KHÔNG TICK", "short")
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
        return '<div class="empty">Chưa có lệnh đóng (không tính diễn tập) — đường R tích lũy sẽ xuất hiện sau lệnh đóng đầu tiên.</div>'
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
window.JournalChart = { rcurve(el, tip, pts){
  const cs=getComputedStyle(document.documentElement), v=k=>cs.getPropertyValue(k).trim(), mono=v('--mono')||'monospace';
  const C={accent:v('--accent'),line:v('--line'),lineStrong:v('--line-strong'),faint:v('--faint'),ink:v('--ink'),ink2:v('--ink-2'),surface:v('--surface'),up:v('--up'),down:v('--down')};
  const L=window.LightweightCharts, chart=L.createChart(el,{autoSize:true,layout:{background:{type:'solid',color:C.surface},textColor:C.faint,fontFamily:mono,fontSize:10,attributionLogo:false},
    grid:{vertLines:{color:C.line},horzLines:{color:C.line}},rightPriceScale:{borderColor:C.lineStrong,scaleMargins:{top:0.15,bottom:0.1}},timeScale:{borderColor:C.lineStrong,timeVisible:true,secondsVisible:false,rightOffset:2},
    crosshair:{mode:L.CrosshairMode.Normal},localization:{locale:'en-US',priceFormatter:x=>(x>=0?'+':'')+x.toFixed(2)+'R',timeFormatter:t=>new Date(t*1000).toISOString().slice(0,16).replace('T',' ')+'Z'},handleScale:{axisPressedMouseMove:true,mouseWheel:true,pinch:true},kineticScroll:{mouse:true,touch:true}});
  const s=chart.addSeries(L.AreaSeries,{lineColor:C.accent,lineWidth:2,topColor:C.accent+'33',bottomColor:C.accent+'05',priceLineVisible:false,lastValueVisible:true,crosshairMarkerRadius:4});
  s.setData(pts.map(p=>({time:p.time,value:p.value}))); s.createPriceLine({price:0,color:C.lineStrong,lineWidth:1,lineStyle:L.LineStyle.Solid,axisLabelVisible:false});
  L.createSeriesMarkers(s, pts.map(p=>({time:p.time,position:p.r>=0?'aboveBar':'belowBar',shape:'circle',color:p.r>=0?C.up:C.down,size:0.8})));
  chart.timeScale().fitContent();
  chart.subscribeCrosshairMove(q=>{ if(!q.point||!q.time){ tip.style.display='none'; return; } const p=pts.find(x=>x.time===q.time); if(!p){ tip.style.display='none'; return; }
    tip.innerHTML=`<div class="t">lệnh ${p.n} · ${new Date(p.time*1000).toISOString().slice(0,16).replace('T',' ')}Z</div><div><b>${p.id||''}</b></div><div>${p.setup||''}</div><div class="${p.r>=0?'u':'d'}">${p.r>=0?'+':''}${p.r.toFixed(2)}R · tích lũy ${p.value>=0?'+':''}${p.value.toFixed(2)}R</div>`;
    tip.style.display='block'; const r=el.getBoundingClientRect(), x=q.point.x; tip.style.left=(el.offsetLeft+(x>r.width*0.65?x-tip.offsetWidth-14:x+14))+'px'; tip.style.top=(el.offsetTop+q.point.y+12)+'px'; });
  el.addEventListener('mouseleave',()=>{ tip.style.display='none'; });
}};
"""


def vendor_script():
    with open(VENDOR_JS, encoding="utf-8") as fh:
        return "<script>\n" + fh.read() + "\n</script>\n<script>" + JOURNAL_JS + "</script>"


def chip(v, cls=None):
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


def render(rows, st, out, closed_real):
    now = datetime.datetime.now(datetime.timezone.utc)
    gen = now.strftime("%Y-%m-%d %H:%M UTC")
    # ---- pilot activity
    pcards = []
    for p in pilot_activity(now):
        why = []
        if p["stop"] or not p["enabled"]:
            why.append("automation đang TẮT" + (f" (dừng {when(p['stopped_at'])})" if p.get("stopped_at") else "") + " — pilot không tick nên không thể có lệnh mới")
        if p["n_eval"] and p["n_ok"] == 0:
            why.append(f"{p['n_eval']} lần đánh giá 15 phút từ {when(p['first'])}, <b>0 lần đủ điều kiện vào lệnh</b> → chưa có lệnh nào để ghi vào nhật ký")
        if p["n_entry"]:
            why.append(f"{p['n_entry']} lệnh vào / {p['n_exit']} lệnh thoát trong log — <code>journal.py sync-pilot</code> ghi chúng vào trades/")
        if not p["n_eval"]:
            why.append("chưa có bản ghi nào trong log")
        verdict = f'<div class="verdict">Nhật ký <b>{"hoạt động đúng" if (p["n_entry"] or p["n_ok"] == 0) else "cần kiểm tra"}</b>: ' + "; ".join(why) + ".</div>"
        top = max((n for _, n in p["reasons"]), default=1)
        reasons = "".join(f'<li><span class="n">{n}</span><span class="bar" style="width:{max(2, int(160 * n / top))}px"></span><span>{e(r)}</span></li>' for r, n in p["reasons"]) or '<li class="muted">—</li>'
        pcards.append(f'''<div class="pcard"><div class="pcard-head"><span class="mk">Pilot {p["market"]}</span><span class="chip chip-{p["cls"]} chip-lg">{p["state"]}</span><span class="env">env {e(p["env"])} · tick cuối {when(p["last"])}</span></div>
{verdict}
<div class="pgrid"><div class="pk"><div class="l">Đánh giá 24h</div><div class="v">{p["n_eval24"]}</div><div class="s">tổng {p["n_eval"]}</div></div><div class="pk"><div class="l">Đủ điều kiện</div><div class="v">{p["n_ok"]}</div><div class="s">luật: quét → MSS → FVG · KL ≥ 1.5×</div></div><div class="pk"><div class="l">Lệnh vào / thoát</div><div class="v">{p["n_entry"]} / {p["n_exit"]}</div><div class="s">từ log pilot</div></div></div>
<div><div class="eyebrow" style="margin-bottom:4px">Lý do bị loại nhiều nhất</div><ul class="reasons">{reasons}</ul></div></div>''')
    # ---- tiles
    wr = f"{st['win_rate'] * 100:.0f}%" if st["win_rate"] is not None else "—"
    tiles = [("Lệnh đã đóng", st["closed"], f"đang mở {st['open']} · kế hoạch {st['planned']} · diễn tập {st['rehearsal']}"),
             ("Tỷ lệ thắng", wr, f"{st['wins']} thắng / {st['losses']} thua"),
             ("R kỳ vọng", f(st["avg_r"]), f"thắng {f(st['avg_win_r'])} R · thua {f(st['avg_loss_r'])} R"),
             ("Profit factor", f(st["profit_factor"]), f"tổng {f(st['total_r'])} R · {f(st['pnl_usd'])} USDT"),
             ("Sụt giảm tối đa", f"{f(st['max_drawdown_r'])} R", f"chuỗi thua dài nhất {st['worst_losing_streak']}")]
    tiles_html = "".join(f'<div class="tile"><div class="l">{l}</div><div class="v">{v}</div><div class="s">{s}</div></div>' for l, v, s in tiles)
    # ---- breakdowns
    def table_by(key, title):
        g = st.get("by_" + key) or {}
        if not g:
            return ""
        rws = "".join(f"<tr><td>{e(k)}</td><td class='num'>{v['n']}</td><td class='num'>{v['win_rate'] * 100:.0f}%</td><td class='num'>{signed(v['avg_r'])}</td></tr>" for k, v in sorted(g.items(), key=lambda kv: -kv[1]['n']))
        return f"<div class='card'><h3>{title}</h3><div class='table-wrap'><table><thead><tr><th>Nhóm</th><th class='num'>Lệnh</th><th class='num'>Thắng</th><th class='num'>R TB</th></tr></thead><tbody>{rws}</tbody></table></div></div>"
    breakdown = "".join(table_by(k, t) for k, t in (("setup_type", "Theo loại setup"), ("instrument", "Theo mã"), ("session", "Theo phiên"), ("market", "Theo thị trường"), ("direction", "Theo chiều"), ("exit_type", "Theo cách thoát")))
    # ---- ledger
    order = sorted(rows, key=lambda r: r.get("date_opened") or "", reverse=True)
    trs = "".join("<tr>" + f"<td class='id'>{e(r['id'])}</td><td>{e(str(r.get('market') or '—'))}</td><td class='mono'>{e(str(r.get('instrument')))}</td><td>{chip(r.get('direction'), 'long' if r.get('direction') == 'LONG' else 'short')}</td>"
                  f"<td class='setup'>{e(str(r.get('setup_type') or ''))}{' <span class=\"chip chip-warn\">diễn tập</span>' if r.get('rehearsal_mode') else ''}</td><td>{e(str(r.get('session') or '—'))}</td><td class='num'>{f(r.get('entry'))}</td><td class='num'>{f(r.get('stop_loss'))}</td>"
                  f"<td class='num'>{e(f(r.get('targets')))}</td><td class='num'>{f(r.get('planned_rr'))}</td><td>{chip(r.get('status'))}</td><td>{e(str(r.get('exit_type') or ''))}</td><td>{chip(r.get('result'))}</td>"
                  f"<td class='num'>{signed(r.get('r_multiple'))}</td><td class='num'>{signed(r.get('pnl_usd'))}</td><td class='num'>{f(r.get('hold_minutes'))}</td></tr>" for r in order)
    # ---- reviews
    details = []
    for r in order:
        fields = [("Luận điểm", r.get("thesis")), ("Kế hoạch vs thực tế", r.get("plan_vs_actual")), ("Tuân thủ kế hoạch", r.get("followed_plan")),
                  ("Loại thoát", r.get("exit_type")), ("Lý do thoát", r.get("exit_reason")), ("Nguyên nhân gốc", r.get("root_cause")), ("Là sai lầm?", r.get("is_mistake")),
                  ("Bài học", r.get("lessons")), ("Ghi chú review", r.get("review_notes")), ("Thay đổi lần sau", r.get("what_to_change")),
                  ("Tự tin trước lệnh (1–5)", r.get("confidence")), ("Trạng thái cảm xúc", r.get("emotional_state")), ("Thẻ", ", ".join(r.get("tags") or [])), ("Ảnh chart", ", ".join(r.get("screenshots") or []))]
        dl = "".join(f"<dt>{e(k)}</dt><dd>{e(f(v)) if v not in (None, '', []) else '<span class=\"muted\">chưa ghi</span>'}</dd>" for k, v in fields)
        details.append(f"<details><summary><b>{e(r['id'])}</b> <span class='mono'>{e(str(r.get('instrument')))}</span> {chip(r.get('direction'), 'long' if r.get('direction') == 'LONG' else 'short')} {chip(r.get('status'))} {chip(r.get('result'))} <span class='mono muted'>R {e(f(r.get('r_multiple')))}</span></summary><dl>{dl}</dl></details>")
    page = f"""<title>Nhật ký giao dịch</title>
{theme.FONTS}
{CSS.replace('__TOKENS__', theme.TOKENS)}
<div class="topbar"><div class="topbar-in"><div><div class="brand-title">Nhật ký giao dịch</div><div class="brand-sub">trades/*.md → scripts/journal.py · sinh {gen}</div></div>
<nav class="nav"><a href="#pilot">Pilot</a><a href="#stats">Thống kê</a><a href="#ledger">Sổ lệnh</a><a href="#reviews">Review</a></nav></div></div>
<div class="page">
<div class="lede"><p class="eyebrow">nhật ký · số liệu do code tính · review do người hoặc Claude điền</p><h1>Nhật ký giao dịch</h1><p>Pilot chỉ vào lệnh khi luật cố định đủ điều kiện; nhật ký chỉ có bản ghi mới khi pilot vào lệnh hoặc khi <code>/journal</code> ghi một kế hoạch sau <code>/analyze</code>. Phần đầu trang cho biết pilot có đang chạy không và vì sao chưa có lệnh.</p></div>
<section id="pilot"><h2>Pilot có đang hoạt động không? <small>data/live/pilot*/log.jsonl (legacy) · top5-log.jsonl / top5-mt5-log.jsonl (profile top5) · docs/architecture/automation-config.json</small></h2><div class="pilot">{''.join(pcards)}</div></section>
<section id="stats"><h2>Bảng cân đối <small>không tính lệnh diễn tập</small></h2><div class="tiles">{tiles_html}</div></section>
{vendor_script() if any(isinstance(r.get("r_multiple"), (int, float)) for r in closed_real) else ''}
<section><h2>Đường R tích lũy <small>theo thời điểm đóng lệnh · lăn chuột = zoom · kéo = dịch</small></h2><div class="card">{r_curve(closed_real)}</div></section>
{('<section><h2>Phân rã</h2><div class="grid">' + breakdown + '</div></section>') if breakdown else ''}
<section id="ledger"><h2>Sổ lệnh <small>{len(rows)} bản ghi</small></h2><div class="table-wrap"><table><thead><tr><th>ID</th><th>Thị trường</th><th>Mã</th><th>Chiều</th><th>Setup</th><th>Phiên</th><th class="num">Entry</th><th class="num">Stop</th><th class="num">Targets</th><th class="num">R kế hoạch</th><th>Trạng thái</th><th>Thoát</th><th>Kết quả</th><th class="num">R</th><th class="num">P&amp;L USDT</th><th class="num">Giữ (phút)</th></tr></thead><tbody>{trs or '<tr><td colspan="16" class="muted">Chưa có lệnh nào.</td></tr>'}</tbody></table></div></section>
<section id="reviews"><h2>Review từng lệnh</h2>
<div class="note">Sau mỗi lệnh, trả lời năm câu: luận điểm còn đúng không · kế hoạch so với thực tế · có phá luật nào không (followed_plan) · nguyên nhân gốc (root_cause) · một thay đổi cụ thể cho lần sau (what_to_change). Sai lầm lặp lại được gom trong <code>docs/mistakes/MISTAKE-DB.md</code>; cập nhật bằng <code>scripts/journal.py review &lt;id&gt; --set key=value</code>.</div>
<div style="margin-top:12px">{''.join(details) or '<p class="muted">Chưa có lệnh nào.</p>'}</div></section>
<footer><b>Nguồn</b>: trades/index.jsonl (dẫn xuất từ trades/*.md) · log pilot · automation-config.json · <b>sinh</b> {gen} bởi scripts/journal.py render · đồng bộ tự động sau mỗi tick pilot (scripts/pilot-loop.sh) và bởi /journal, /status, /review.<br>Chart: TradingView Lightweight Charts™ · Copyright (c) 2025 TradingView, Inc. · <a href="https://www.tradingview.com/" rel="noopener">tradingview.com</a> · Apache-2.0 (scripts/vendor/NOTICE-lightweight-charts.txt)</footer>
</div>
"""
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"render: {os.path.relpath(out, ROOT)} ({len(rows)} trades)")
