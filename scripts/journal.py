#!/usr/bin/env python3
"""Trade journal ("notebook") tooling over the trades/ store — one Markdown file per trade with YAML frontmatter
(schema: docs/architecture/schemas/trade-file.schema.json; storage design: docs/architecture/SYSTEM-DESIGN.md §8).

Subcommands
  sync-pilot [--market spot|futures]   ingest the demo pilot's log (entry/exit/flatten records) into trades/*.md,
                                       idempotent (matched on exchange entry order id); computed fields filled,
                                       human review fields left for `review`
  review <id> --set k=v [k=v ...]      set frontmatter fields (root_cause, is_mistake, lessons, review_notes,
                                       what_to_change, followed_plan, confidence, emotional_state, tags...)
  index                                rebuild trades/index.jsonl from every trades/*.md (derived, never hand-edited)
  views                                rebuild docs/edge-log/EDGE-LOG.md and docs/mistakes/MISTAKE-DB.md from the index
  stats [--json]                       win rate, avg R, expectancy, profit factor, max drawdown (R), streaks,
                                       breakdowns by setup / instrument / session / market
  render [--out PATH]                  Vietnamese HTML review page (default data/live/.journal-vi.html) for publishing
  all                                  sync-pilot (both markets) + index + views + render

Numbers here are computed from the records; prose fields are for the human/Claude review. PyYAML is not
required — the frontmatter subset used by this project (scalars, [a, b] lists, quoted strings) is parsed here.
"""
import argparse, datetime, glob, html, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADES = os.path.join(ROOT, "trades")
INDEX = os.path.join(TRADES, "index.jsonl")
PILOT = {"spot": os.path.join(ROOT, "data", "live", "pilot", "log.jsonl"),
         "futures": os.path.join(ROOT, "data", "live", "pilot-futures", "log.jsonl")}
SCHEMA = json.load(open(os.path.join(ROOT, "docs", "architecture", "schemas", "trade-file.schema.json"), encoding="utf-8"))
FIELD_ORDER = list(SCHEMA["properties"].keys())


# ---------- minimal YAML (frontmatter subset) ----------
def _scalar(v):
    v = v.strip()
    if v == "" or v == "null" or v == "~": return None
    if v in ("true", "false"): return v == "true"
    if (v[0] == v[-1] == '"') or (v[0] == v[-1] == "'"): return v[1:-1]
    if re.fullmatch(r"-?\d+", v): return int(v)
    if re.fullmatch(r"-?\d+\.\d+(e-?\d+)?", v): return float(v)
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [] if not inner else [_scalar(x) for x in re.split(r",\s*(?=(?:[^\"']*[\"'][^\"']*[\"'])*[^\"']*$)", inner)]
    if v.startswith("{") and v.endswith("}"):
        try: return json.loads(v)
        except Exception: return v
    return v


def parse_frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m: return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"): continue
        k, _, v = line.partition(":")
        fm[k.strip()] = _scalar(v)
    return fm, m.group(2)


def _emit(v):
    if v is None: return "null"
    if isinstance(v, bool): return "true" if v else "false"
    if isinstance(v, (int, float)): return repr(v) if isinstance(v, float) else str(v)
    if isinstance(v, list): return "[" + ", ".join(_emit(x) for x in v) + "]"
    if isinstance(v, dict): return json.dumps(v, ensure_ascii=False)
    s = str(v)
    return json.dumps(s, ensure_ascii=False) if (":" in s or s != s.strip() or s == "" or s[0] in "[{#&*!|>'\"%@`") else s


def dump_frontmatter(fm):
    keys = [k for k in FIELD_ORDER if k in fm] + [k for k in fm if k not in FIELD_ORDER]
    return "---\n" + "\n".join(f"{k}: {_emit(fm[k])}" for k in keys) + "\n---\n"


def read_trade(path):
    fm, body = parse_frontmatter(open(path, encoding="utf-8").read()); return fm, body


def write_trade(path, fm, body):
    open(path, "w", encoding="utf-8").write(dump_frontmatter(fm) + body)


def all_trades():
    out = []
    for p in sorted(glob.glob(os.path.join(TRADES, "*.md"))):
        if os.path.basename(p) == "README.md": continue
        fm, body = read_trade(p); fm["_path"] = p; out.append(fm)
    return out


# ---------- helpers ----------
def session_of(iso):
    h = int(iso[11:13]); mi = int(iso[14:16]); t = h + mi / 60
    if 6 <= t < 9: return "london"
    if 11 <= t < 14: return "ny_am"
    if 14 <= t < 17: return "ny_pm"
    if 0 <= t < 6: return "asia"
    return "off"


def minutes_between(a, b):
    fa = datetime.datetime.strptime(a, "%Y-%m-%dT%H:%M:%SZ"); fb = datetime.datetime.strptime(b, "%Y-%m-%dT%H:%M:%SZ")
    return round((fb - fa).total_seconds() / 60, 1)


def next_seq(date, instrument):
    n = 0
    for p in glob.glob(os.path.join(TRADES, f"{date}-{instrument}-*.md")):
        m = re.search(rf"{date}-{instrument}-(\d+)\.md$", p)
        if m: n = max(n, int(m.group(1)))
    return n + 1


# ---------- sync-pilot ----------
def sync_pilot(market):
    log_path = PILOT[market]
    if not os.path.exists(log_path):
        print(f"{market}: no pilot log at {log_path}"); return 0
    recs = [json.loads(l) for l in open(log_path, encoding="utf-8") if l.strip()]
    entries = [r for r in recs if r.get("kind") == "entry"]
    exits = [r for r in recs if r.get("kind") in ("exit", "flatten")]
    existing = {}
    for fm in all_trades():
        ref = (fm.get("exchange_refs") or {}).get("entry_order")
        if ref is not None: existing[(fm.get("market"), str(ref))] = fm
    mk = "spot_testnet" if market == "spot" else "futures_testnet"
    n_new = n_upd = 0
    for e in entries:
        key = (mk, str(e.get("entry_order")))
        sym, opened = e["symbol"], e["opened_at"]
        side = e.get("side", "LONG")
        ex = next((x for x in exits if x["symbol"] == sym and x.get("opened_at") == opened), None)
        risk_usd = float(e.get("risk_usd") or 0); entry = float(e["entry"]); stop = float(e["stop"]); tp = float(e["tp"])
        r_dist = abs(entry - stop); planned_rr = round(abs(tp - entry) / r_dist, 2) if r_dist else None
        fm = existing.get(key)
        if fm:
            path = fm.pop("_path"); _, body = read_trade(path); n_upd += 1
        else:
            date = opened[:10]; seq = next_seq(date, sym); tid = f"{date}-{sym}-{seq:02d}"
            path = os.path.join(TRADES, f"{tid}.md"); n_new += 1
            fm = {"id": tid, "instrument": sym, "date_opened": opened,
                  "setup_type": f"Pilot rules: {'SSL' if side=='LONG' else 'BSL'} sweep → MSS → FVG ({'discount' if side=='LONG' else 'premium'})",
                  "direction": side, "methodology_mode": "NORMAL", "market_regime": "UNCLEAR", "rehearsal_mode": False,
                  "confluence_score": None, "dimensions_used": ["wyckoff", "ict"], "entry": entry, "stop_loss": stop, "targets": [tp],
                  "risk_pct": 0.005, "position_size": float(e["qty"]), "status": "OPEN",
                  "market": mk, "source": f"pilot_{market}", "timeframe": "15m", "session": session_of(opened),
                  "leverage": e.get("leverage", 1), "planned_rr": planned_rr, "confidence": None, "followed_plan": True,
                  "tags": ["pilot", market, side.lower()],
                  "exchange_refs": {"entry_order": e.get("entry_order"), "tp_order": e.get("tp_order"), "stop_order": e.get("stop_order"), "oco_list": e.get("oco_list")},
                  "thesis": (f"Luật pilot (không có model quyết định): {'quét SSL/ERL-low trong 8 nến, MSS tăng trong 3 nến, FVG tăng sau cú quét, giá ở discount' if side=='LONG' else 'quét BSL/ERL-high trong 8 nến, MSS giảm trong 3 nến, FVG giảm sau cú quét, giá ở premium'}, "
                             f"volume nến quét/MSS ≥ 1.5× trung bình (Effort-vs-Result). Entry {entry} · stop {stop} · TP {tp} · rủi ro {risk_usd} USDT.")}
            body = ("\n## Decision Output (at plan time)\n\n"
                    f"Nguồn: demo pilot ({mk}), luật cố định trong `scripts/demo-pilot.py`; không có Confluence Score vì không chạy DecisionAgent.\n\n"
                    f"- Setup: {fm['setup_type']}\n- Entry {entry} · Stop {stop} · TP {tp} · R kế hoạch {planned_rr}\n- Rủi ro {risk_usd} USDT (0.5% vốn) · size {e['qty']}\n"
                    f"- Lệnh sàn: entry {e.get('entry_order')} · TP {e.get('tp_order')} · SL {e.get('stop_order')}\n\n"
                    "## Post-Trade Review (filled in at close time, master spec section 26)\n"
                    "- Original Thesis: (xem `thesis`)\n- Evidence:\n- Conditions:\n- Execution:\n- Outcome:\n- Root Cause:\n")
        if ex:
            pnl = float(ex.get("pnl") or 0); r = ex.get("r")
            fm.update({"status": "CLOSED", "date_closed": ex["closed_at"], "result": "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "BREAKEVEN"),
                       "r_multiple": r, "pnl_usd": round(pnl, 2), "exit_type": {"TP": "TP", "SL": "SL", "TIME": "TIME", "FLATTEN": "FLATTEN"}.get(ex.get("via"), "OTHER"),
                       "exit_reason": f"pilot {ex.get('via')} @ {ex.get('exit')}", "hold_minutes": minutes_between(opened, ex["closed_at"])})
            if fm.get("result") == "WIN" and not fm.get("root_cause"): fm["root_cause"] = "n/a_win_as_planned"
            fm.setdefault("is_mistake", False)
        write_trade(path, fm, body)
    print(f"{market}: {len(entries)} entries in log → {n_new} new, {n_upd} updated trade files")
    return n_new + n_upd


# ---------- index / views / stats ----------
def build_index():
    rows = []
    for fm in all_trades():
        fm = {k: v for k, v in fm.items() if not k.startswith("_")}; rows.append(fm)
    with open(INDEX, "w", encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"index: {len(rows)} trades → {os.path.relpath(INDEX, ROOT)}")
    return rows


def closed_real(rows):
    return [r for r in rows if r.get("status") == "CLOSED" and not r.get("rehearsal_mode")]


def stats(rows):
    cl = closed_real(rows)
    rs = [r["r_multiple"] for r in cl if isinstance(r.get("r_multiple"), (int, float))]
    wins = [x for x in rs if x > 0]; losses = [x for x in rs if x <= 0]
    def avg(a): return round(sum(a) / len(a), 2) if a else None
    cum = peak = dd = 0.0
    for x in rs:
        cum += x; peak = max(peak, cum); dd = min(dd, cum - peak)
    streak = worst = 0
    for x in rs:
        streak = streak + 1 if x <= 0 else 0; worst = max(worst, streak)
    out = {"closed": len(cl), "wins": len(wins), "losses": len(losses),
           "win_rate": round(len(wins) / len(rs), 3) if rs else None, "avg_r": avg(rs), "avg_win_r": avg(wins), "avg_loss_r": avg(losses),
           "expectancy_r": avg(rs), "profit_factor": (round(sum(wins) / abs(sum(losses)), 2) if losses and sum(losses) < 0 else None),
           "total_r": round(sum(rs), 2) if rs else 0, "max_drawdown_r": round(dd, 2), "worst_losing_streak": worst,
           "pnl_usd": round(sum(float(r.get("pnl_usd") or 0) for r in cl), 2),
           "open": len([r for r in rows if r.get("status") == "OPEN"]), "planned": len([r for r in rows if r.get("status") == "PLANNED"]),
           "rehearsal": len([r for r in rows if r.get("rehearsal_mode")])}
    for key in ("setup_type", "instrument", "session", "market", "direction", "exit_type"):
        g = {}
        for r in cl:
            k = str(r.get(key)); x = r.get("r_multiple")
            d = g.setdefault(k, {"n": 0, "wins": 0, "sum_r": 0.0})
            d["n"] += 1; d["wins"] += 1 if (x or 0) > 0 else 0; d["sum_r"] += x or 0
        out["by_" + key] = {k: {"n": d["n"], "win_rate": round(d["wins"] / d["n"], 2), "avg_r": round(d["sum_r"] / d["n"], 2)} for k, d in g.items()}
    return out


def views(rows):
    cl = sorted(closed_real(rows), key=lambda r: r.get("date_closed") or "", reverse=True)
    os.makedirs(os.path.join(ROOT, "docs", "edge-log"), exist_ok=True); os.makedirs(os.path.join(ROOT, "docs", "mistakes"), exist_ok=True)
    st = stats(rows)
    lines = ["# Edge Log", "", "_Generated by `scripts/journal.py views` from `trades/index.jsonl` — do not edit; edit the trade file._", "",
             f"Closed (non-rehearsal): {st['closed']} · win rate {st['win_rate']} · avg R {st['avg_r']} · expectancy {st['expectancy_r']} R · profit factor {st['profit_factor']} · max DD {st['max_drawdown_r']} R", "",
             "| Closed | Instrument | Market | Setup | Dir | Session | Entry | Stop | Targets | Exit | Result | R | P&L USDT | Lessons |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in cl:
        lines.append(f"| {r.get('date_closed','')[:16]} | {r.get('instrument')} | {r.get('market','')} | {r.get('setup_type','')} | {r.get('direction')} | {r.get('session','')} | {r.get('entry')} | {r.get('stop_loss')} | {r.get('targets')} | {r.get('exit_type','')} | {r.get('result','')} | {r.get('r_multiple','')} | {r.get('pnl_usd','')} | {r.get('lessons','') or ''} |")
    open(os.path.join(ROOT, "docs", "edge-log", "EDGE-LOG.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    mis = [r for r in rows if r.get("is_mistake")]
    by = {}
    for r in mis: by.setdefault(r.get("root_cause") or "other", []).append(r)
    ml = ["# Mistake DB", "", "_Generated by `scripts/journal.py views` — do not edit; set `is_mistake`/`root_cause` in the trade file._", ""]
    for cause, items in sorted(by.items(), key=lambda kv: -len(kv[1])):
        ml.append(f"## {cause} — {len(items)} lần{' — LẶP LẠI' if len(items) > 1 else ''}")
        for r in items: ml.append(f"- {r['id']} · {r.get('instrument')} {r.get('direction')} · R {r.get('r_multiple')} · {r.get('lessons') or r.get('what_to_change') or ''}")
        ml.append("")
    open(os.path.join(ROOT, "docs", "mistakes", "MISTAKE-DB.md"), "w", encoding="utf-8").write("\n".join(ml) + "\n")
    print(f"views: EDGE-LOG ({len(cl)} rows), MISTAKE-DB ({len(mis)} entries)")


# ---------- render ----------
def render(rows, out):
    st = stats(rows); e = html.escape
    def f(v): return "" if v is None else (f"{v:,.2f}" if isinstance(v, float) else str(v))
    def card(label, val, sub=""): return f'<div class="card"><div class="lbl">{label}</div><div class="val">{val}</div><div class="sub">{sub}</div></div>'
    cards = [card("Lệnh đã đóng", st["closed"], f"đang mở {st['open']} · kế hoạch {st['planned']} · diễn tập {st['rehearsal']}"),
             card("Tỷ lệ thắng", f"{st['win_rate']*100:.0f}%" if st["win_rate"] is not None else "—", f"{st['wins']} thắng / {st['losses']} thua"),
             card("R trung bình (kỳ vọng)", f(st["avg_r"]) if st["avg_r"] is not None else "—", f"thắng {f(st['avg_win_r'])} R · thua {f(st['avg_loss_r'])} R"),
             card("Profit factor", f(st["profit_factor"]) if st["profit_factor"] else "—", f"tổng {f(st['total_r'])} R · {f(st['pnl_usd'])} USDT"),
             card("Sụt giảm tối đa", f"{f(st['max_drawdown_r'])} R", f"chuỗi thua dài nhất {st['worst_losing_streak']}")]
    def table_by(key, title):
        g = st.get("by_" + key) or {}
        if not g: return ""
        rws = "".join(f"<tr><td>{e(k)}</td><td class='num'>{v['n']}</td><td class='num'>{v['win_rate']*100:.0f}%</td><td class='num'>{v['avg_r']:+.2f}</td></tr>" for k, v in sorted(g.items(), key=lambda kv: -kv[1]['n']))
        return f"<h3>{title}</h3><div class='wrap'><table><thead><tr><th>Nhóm</th><th class='num'>Lệnh</th><th class='num'>Thắng</th><th class='num'>R TB</th></tr></thead><tbody>{rws}</tbody></table></div>"
    order = sorted(rows, key=lambda r: r.get("date_opened") or "", reverse=True)
    trs = []
    for r in order:
        trs.append("<tr>" + "".join(f"<td>{e(f(r.get(k)))}</td>" for k in ("id", "market", "instrument", "direction", "setup_type", "session", "entry", "stop_loss", "targets", "planned_rr", "status", "exit_type", "result", "r_multiple", "pnl_usd", "hold_minutes")) + "</tr>")
    details = []
    for r in order:
        fields = [("Luận điểm", r.get("thesis")), ("Kế hoạch vs thực tế", r.get("plan_vs_actual")), ("Tuân thủ kế hoạch", r.get("followed_plan")),
                  ("Loại thoát", r.get("exit_type")), ("Lý do thoát", r.get("exit_reason")), ("Nguyên nhân gốc", r.get("root_cause")), ("Là sai lầm?", r.get("is_mistake")),
                  ("Bài học", r.get("lessons")), ("Ghi chú review", r.get("review_notes")), ("Thay đổi lần sau", r.get("what_to_change")),
                  ("Tự tin trước lệnh (1–5)", r.get("confidence")), ("Trạng thái cảm xúc", r.get("emotional_state")), ("Thẻ", ", ".join(r.get("tags") or [])), ("Ảnh chart", ", ".join(r.get("screenshots") or []))]
        dl = "".join(f"<dt>{e(k)}</dt><dd>{e(f(v)) if v not in (None, '', []) else '<span class=\"muted\">chưa ghi</span>'}</dd>" for k, v in fields)
        details.append(f"<details><summary><b>{e(r['id'])}</b> · {e(str(r.get('instrument')))} {e(str(r.get('direction')))} · {e(str(r.get('status')))} · R {e(f(r.get('r_multiple')))}</summary><dl>{dl}</dl></details>")
    gen = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    # Design plan (utilitarian ledger): palette ledger-green on cool paper; IBM Plex Sans body, IBM Plex Mono for
    # every number (tabular), Source Serif 4 for the name only; one summary strip, then the ledger, then reviews.
    def chip(v):
        v = str(v or "")
        cls = {"WIN": "win", "LOSS": "loss", "OPEN": "open", "CLOSED": "closed", "PLANNED": "planned", "BREAKEVEN": "be"}.get(v, "")
        return f'<span class="chip {cls}">{e(v)}</span>' if v else ""
    def rr(v): return "" if v is None else (f'<span class="{"pos" if v > 0 else "neg"}">{v:+.2f}</span>' if isinstance(v, (int, float)) else e(str(v)))
    trs = []
    for r in order:
        trs.append("<tr>" + f"<td class='id'>{e(r['id'])}</td><td>{e(str(r.get('market') or '—'))}</td><td>{e(str(r.get('instrument')))}</td><td>{e(str(r.get('direction')))}</td>"
                   f"<td class='setup'>{e(str(r.get('setup_type') or ''))}</td><td>{e(str(r.get('session') or '—'))}</td><td class='num'>{f(r.get('entry'))}</td><td class='num'>{f(r.get('stop_loss'))}</td>"
                   f"<td class='num'>{e(f(r.get('targets')))}</td><td class='num'>{f(r.get('planned_rr'))}</td><td>{chip(r.get('status'))}</td><td>{e(str(r.get('exit_type') or ''))}</td><td>{chip(r.get('result'))}</td>"
                   f"<td class='num'>{rr(r.get('r_multiple'))}</td><td class='num'>{rr(r.get('pnl_usd'))}</td><td class='num'>{f(r.get('hold_minutes'))}</td></tr>")
    page = f"""<title>Nhật ký giao dịch</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&family=Source+Serif+4:opsz,wght@8..60,600&display=swap">
<style>
:root{{--bg:#EEF1EE;--paper:#FAFBF9;--ink:#15211B;--muted:#5E6E66;--line:#CFD8D2;--acc:#1F6F5B;--acc-ink:#155543;--win:#2E7D4F;--loss:#B23A3A;--warn:#B7791F;--zebra:#F3F6F3}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#101614;--paper:#161E1A;--ink:#E4EBE6;--muted:#93A29A;--line:#24302B;--acc:#4FB08E;--acc-ink:#7CCBB0;--win:#5FBF8A;--loss:#E07A7A;--warn:#D9A441;--zebra:#131A17}}}}
:root[data-theme="dark"]{{--bg:#101614;--paper:#161E1A;--ink:#E4EBE6;--muted:#93A29A;--line:#24302B;--acc:#4FB08E;--acc-ink:#7CCBB0;--win:#5FBF8A;--loss:#E07A7A;--warn:#D9A441;--zebra:#131A17}}
*{{box-sizing:border-box}} body{{background:var(--bg);color:var(--ink);font:14px/1.55 "IBM Plex Sans",-apple-system,system-ui,sans-serif;margin:0;padding:28px 24px 48px}}
.wrapper{{max-width:1180px;margin:0 auto;display:flex;flex-direction:column;gap:28px}}
header h1{{font:600 30px/1.1 "Source Serif 4",Georgia,serif;margin:0;text-wrap:balance;letter-spacing:-.01em}}
header .stamp{{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px;color:var(--muted);margin-top:6px}}
h2{{font:600 12px/1 "IBM Plex Sans",sans-serif;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin:0 0 12px;padding-bottom:8px;border-bottom:1px solid var(--line)}}
.strip{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:0;border:1px solid var(--line);background:var(--paper);border-radius:6px;overflow:hidden}}
.card{{padding:14px 16px;border-right:1px solid var(--line)}} .card:last-child{{border-right:0}}
.lbl{{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}} .val{{font:500 26px/1.2 "IBM Plex Mono",ui-monospace,monospace;margin:4px 0 2px;font-variant-numeric:tabular-nums}} .sub{{font-size:12px;color:var(--muted)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}}
h3{{font:600 13px/1.3 "IBM Plex Sans",sans-serif;margin:0 0 6px;color:var(--ink)}}
.wrap{{overflow-x:auto;border:1px solid var(--line);border-radius:6px;background:var(--paper)}}
table{{border-collapse:collapse;width:100%;font-size:12.5px}} th,td{{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap;vertical-align:top}}
th{{color:var(--muted);font-weight:600;font-size:11px;letter-spacing:.06em;text-transform:uppercase;background:var(--zebra)}} tbody tr:nth-child(even){{background:var(--zebra)}}
td.num,th.num{{font-family:"IBM Plex Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums;text-align:right}} td.id{{font-family:"IBM Plex Mono",ui-monospace,monospace}} td.setup{{white-space:normal;min-width:220px}}
.pos{{color:var(--win)}} .neg{{color:var(--loss)}}
.chip{{display:inline-block;font:500 11px/1 "IBM Plex Mono",monospace;letter-spacing:.04em;padding:4px 7px;border-radius:3px;border:1px solid var(--line);color:var(--muted)}}
.chip.win{{color:var(--win);border-color:var(--win)}} .chip.loss{{color:var(--loss);border-color:var(--loss)}} .chip.open{{color:var(--acc-ink);border-color:var(--acc)}} .chip.planned{{color:var(--warn);border-color:var(--warn)}}
details{{background:var(--paper);border:1px solid var(--line);border-radius:6px;padding:10px 14px}} details+details{{margin-top:8px}} summary{{cursor:pointer;font-family:"IBM Plex Mono",monospace;font-size:12.5px}} summary:focus-visible{{outline:2px solid var(--acc);outline-offset:2px}}
dl{{display:grid;grid-template-columns:200px 1fr;gap:6px 14px;margin:12px 0 4px;max-width:78ch}} dt{{color:var(--muted);font-size:12.5px}} dd{{margin:0}} .muted{{color:var(--muted)}}
.note{{border-left:3px solid var(--acc);padding:10px 14px;background:var(--paper);border-radius:0 6px 6px 0;font-size:13px;max-width:78ch}}
@media (max-width:640px){{dl{{grid-template-columns:1fr}} .card{{border-right:0;border-bottom:1px solid var(--line)}}}}
</style>
<div class="wrapper">
<header><h1>Nhật ký giao dịch</h1><div class="stamp">trades/*.md → scripts/journal.py · sinh {gen} · số liệu do code tính, phần review do người hoặc Claude điền sau mỗi lệnh</div></header>
<section><h2>Bảng cân đối</h2><div class="strip">{''.join(cards)}</div></section>
<section><h2>Phân rã</h2><div class="grid">
<div>{table_by('setup_type','Theo loại setup')}</div><div>{table_by('instrument','Theo mã')}</div><div>{table_by('session','Theo phiên (killzone)')}</div><div>{table_by('market','Theo thị trường')}</div><div>{table_by('direction','Theo chiều')}</div><div>{table_by('exit_type','Theo cách thoát')}</div>
</div></section>
<section><h2>Sổ lệnh</h2><div class="wrap"><table><thead><tr><th>ID</th><th>Thị trường</th><th>Mã</th><th>Chiều</th><th>Setup</th><th>Phiên</th><th class="num">Entry</th><th class="num">Stop</th><th class="num">Targets</th><th class="num">R kế hoạch</th><th>Trạng thái</th><th>Thoát</th><th>Kết quả</th><th class="num">R</th><th class="num">P&amp;L USDT</th><th class="num">Giữ (phút)</th></tr></thead><tbody>{''.join(trs) or '<tr><td colspan="16" class="muted">Chưa có lệnh nào.</td></tr>'}</tbody></table></div></section>
<section><h2>Review từng lệnh</h2>
<div class="note">Sau mỗi lệnh, trả lời năm câu: luận điểm còn đúng không · kế hoạch so với thực tế · có phá luật nào không (followed_plan) · nguyên nhân gốc (root_cause) · một thay đổi cụ thể cho lần sau (what_to_change). Sai lầm lặp lại được gom trong <code>docs/mistakes/MISTAKE-DB.md</code>; cập nhật bằng <code>scripts/journal.py review &lt;id&gt; --set key=value</code>.</div>
<div style="margin-top:12px">{''.join(details) or '<p class="muted">Chưa có lệnh nào.</p>'}</div></section>
</div>
"""
    open(out, "w", encoding="utf-8").write(page)
    print(f"render: {os.path.relpath(out, ROOT)} ({len(rows)} trades)")


def review(tid, sets):
    path = os.path.join(TRADES, f"{tid}.md")
    if not os.path.exists(path): sys.exit(f"no trade {tid}")
    fm, body = read_trade(path)
    for kv in sets:
        k, _, v = kv.partition("="); fm[k] = _scalar(v)
    write_trade(path, fm, body); print(f"updated {tid}: {', '.join(s.split('=')[0] for s in sets)}")


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync-pilot"); s.add_argument("--market", choices=["spot", "futures", "both"], default="both")
    r = sub.add_parser("review"); r.add_argument("id"); r.add_argument("--set", nargs="+", required=True)
    sub.add_parser("index"); sub.add_parser("views"); sub.add_parser("all")
    st = sub.add_parser("stats"); st.add_argument("--json", action="store_true")
    rd = sub.add_parser("render"); rd.add_argument("--out", default=os.path.join(ROOT, "data", "live", ".journal-vi.html"))
    a = ap.parse_args()
    if a.cmd == "sync-pilot":
        for m in (["spot", "futures"] if a.market == "both" else [a.market]): sync_pilot(m)
        build_index()
    elif a.cmd == "review": review(a.id, a.set); build_index()
    elif a.cmd == "index": build_index()
    elif a.cmd == "views": views(build_index())
    elif a.cmd == "stats":
        s_ = stats(build_index()); print(json.dumps(s_, ensure_ascii=False, indent=1) if a.json else "\n".join(f"{k}: {v}" for k, v in s_.items() if not k.startswith("by_")))
    elif a.cmd == "render": render(build_index(), a.out)
    elif a.cmd == "all":
        for m in ("spot", "futures"): sync_pilot(m)
        rows = build_index(); views(rows); render(rows, os.path.join(ROOT, "data", "live", ".journal-vi.html"))


if __name__ == "__main__":
    main()
