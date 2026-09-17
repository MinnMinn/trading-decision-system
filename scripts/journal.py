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
         "futures": os.path.join(ROOT, "data", "live", "pilot-futures", "log.jsonl"),
         "futures-top5": os.path.join(ROOT, "data", "live", "pilot-futures", "top5-log.jsonl"),   # scripts/strategy-runner.py (profile top5, crypto testnet)
         "cfd-mt5": os.path.join(ROOT, "data", "live", "pilot-futures", "top5-mt5-log.jsonl")}  # scripts/strategy-runner.py (profile top5, CFD on the MT5 demo account)
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
    """docs/architecture/session-model.md §2: windows in the exchange-local clock, converted per date (DST-aware); weekends = off."""
    import datetime as _dt, zoneinfo as _zi
    t = _dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if t.weekday() >= 5: return "off"
    def lh(tz):
        lt = t.astimezone(_zi.ZoneInfo(tz)); return lt.hour + lt.minute / 60
    if 8 <= lh("Europe/London") < 11: return "london"
    ny = lh("America/New_York")
    if 8.5 <= ny < 11: return "ny_am"
    if 13.5 <= ny < 16: return "ny_pm"
    if 20 <= ny < 24: return "asia"
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
def _risk_pct(entry_rec):
    """The risk fraction the pilot ACTUALLY sized with, or None.

    Never a default. This used to be `float(e.get("risk_pct", 0.005))`, so a log line without the field was
    written to trades/ as a 0.5 % trade -- a number nobody risked, in the file the learning system and every
    expectancy statistic read back. A fabricated input is worse than a missing one: `None` is visibly absent
    and can be excluded from a per-risk breakdown, whereas 0.005 silently joins the sample as fact."""
    v = entry_rec.get("risk_pct")
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if 0 < v <= 1 else None


def _risk_pct_label(v):
    """Prose for the Decision Output block. The old text said "0.5% vốn" unconditionally while risk_pct was
    whatever the runner used (PILOT_RISK_PCT, clamped to risk-config.json max_risk_pct)."""
    return f"{v * 100:g}% vốn" if v is not None else "tỉ lệ rủi ro không có trong log của pilot"


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
    mk = "spot_testnet" if market == "spot" else ("mt5_demo" if market == "cfd-mt5" else "futures_testnet")
    src = "pilot_spot" if market == "spot" else ("pilot_mt5" if market == "cfd-mt5" else "pilot_futures")
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
            strat = e.get("strategy")            # profile top5 records (scripts/strategy-runner.py) carry strategy/tf/htf_pass
            fm = {"id": tid, "instrument": sym, "date_opened": opened,
                  "setup_type": (f"Top5 {strat}: {'sweep SSL' if side=='LONG' else 'sweep BSL'} → MSS → limit tại mép FVG" + (" (Spring/Upthrust proxy làm bối cảnh)" if strat and strat.startswith("combined") else "")) if strat else
                                f"Pilot rules: {'SSL' if side=='LONG' else 'BSL'} sweep → MSS → FVG ({'discount' if side=='LONG' else 'premium'})",
                  "direction": side, "methodology_mode": "NORMAL", "market_regime": "UNCLEAR", "rehearsal_mode": False,
                  "confluence_score": None, "dimensions_used": ["wyckoff", "ict"], "entry": entry, "stop_loss": stop, "targets": [tp],
                  "risk_pct": _risk_pct(e), "position_size": float(e["qty"]), "status": "OPEN",
                  "market": e.get("market", mk), "source": src, "timeframe": e.get("tf", "15m"), "session": session_of(opened),
                  "leverage": e.get("leverage", 1), "planned_rr": planned_rr, "confidence": None, "followed_plan": True,
                  "tags": ["pilot", market, side.lower()] + ([strat, "top5", "htf_pass" if e.get("htf_pass") else "htf_fail"] + (["mt5"] if market == "cfd-mt5" else []) if strat else []),
                  **({"strategy": strat, "htf_pass": bool(e.get("htf_pass"))} if strat else {}),
                  "exchange_refs": {"entry_order": e.get("entry_order"), "tp_order": e.get("tp_order"), "stop_order": e.get("stop_order"), "oco_list": e.get("oco_list")},
                  "thesis": ((f"Luật top5 `{strat}` (scripts/strategy-runner.py = scripts/backtest-methods.py, không có model quyết định): quét pivot {'SSL' if side=='LONG' else 'BSL'} "
                              f"lúc {e.get('sweep_time')}, MSS đóng thân lúc {e.get('mss_time')}, lệnh limit post-only tại mép FVG, stop {stop}, TP {tp}, hoà vốn tại +1R; "
                              f"lọc khung lớn 2H: {'đạt' if e.get('htf_pass') else 'không đạt'}. Rủi ro {risk_usd} USDT.") if strat else
                             (f"Luật pilot (không có model quyết định): {'quét SSL/ERL-low trong 8 nến, MSS tăng trong 3 nến, FVG tăng sau cú quét, giá ở discount' if side=='LONG' else 'quét BSL/ERL-high trong 8 nến, MSS giảm trong 3 nến, FVG giảm sau cú quét, giá ở premium'}, "
                              f"volume nến quét/MSS ≥ 1.5× trung bình (Effort-vs-Result). Entry {entry} · stop {stop} · TP {tp} · rủi ro {risk_usd} USDT."))}
            body = ("\n## Decision Output (at plan time)\n\n"
                    f"Nguồn: pilot ({mk}), luật cố định trong `scripts/strategy-runner.py`; không có Confluence Score vì không chạy DecisionAgent.\n\n"
                    f"- Setup: {fm['setup_type']}\n- Entry {entry} · Stop {stop} · TP {tp} · R kế hoạch {planned_rr}\n- Rủi ro {risk_usd} USDT ({_risk_pct_label(fm['risk_pct'])}) · size {e['qty']}\n"
                    f"- Lệnh sàn: entry {e.get('entry_order')} · TP {e.get('tp_order')} · SL {e.get('stop_order')}\n\n"
                    "## Post-Trade Review (filled in at close time, master spec section 26)\n"
                    "- Original Thesis: (xem `thesis`)\n- Evidence:\n- Conditions:\n- Execution:\n- Outcome:\n- Root Cause:\n")
        if ex:
            pnl = float(ex.get("pnl") or 0); r = ex.get("r")
            fm.update({"status": "CLOSED", "date_closed": ex["closed_at"], "result": "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "BREAKEVEN"),
                       "r_multiple": r, "pnl_usd": round(pnl, 2), "exit_type": {"TP": "TP", "SL": "SL", "BE": "SL", "TIME": "TIME", "FLATTEN": "FLATTEN"}.get(ex.get("via"), "OTHER"),
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
    """Vietnamese review page — layout and markup live in scripts/journal_render.py (shared theme with the chart pages)."""
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import journal_render
    journal_render.render(rows, stats(rows), out, closed_real(rows))


def review(tid, sets):
    path = os.path.join(TRADES, f"{tid}.md")
    if not os.path.exists(path): sys.exit(f"no trade {tid}")
    fm, body = read_trade(path)
    for kv in sets:
        k, _, v = kv.partition("="); fm[k] = _scalar(v)
    write_trade(path, fm, body); print(f"updated {tid}: {', '.join(s.split('=')[0] for s in sets)}")


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync-pilot"); s.add_argument("--market", choices=["spot", "futures", "futures-top5", "cfd-mt5", "both"], default="both")
    r = sub.add_parser("review"); r.add_argument("id"); r.add_argument("--set", nargs="+", required=True)
    sub.add_parser("index"); sub.add_parser("views"); sub.add_parser("all")
    st = sub.add_parser("stats"); st.add_argument("--json", action="store_true")
    rd = sub.add_parser("render"); rd.add_argument("--out", default=os.path.join(ROOT, "data", "live", ".journal-vi.html"))
    a = ap.parse_args()
    if a.cmd == "sync-pilot":
        for m in (["spot", "futures", "futures-top5", "cfd-mt5"] if a.market == "both" else [a.market]): sync_pilot(m)
        build_index()
    elif a.cmd == "review": review(a.id, a.set); build_index()
    elif a.cmd == "index": build_index()
    elif a.cmd == "views": views(build_index())
    elif a.cmd == "stats":
        s_ = stats(build_index()); print(json.dumps(s_, ensure_ascii=False, indent=1) if a.json else "\n".join(f"{k}: {v}" for k, v in s_.items() if not k.startswith("by_")))
    elif a.cmd == "render": render(build_index(), a.out)
    elif a.cmd == "all":
        for m in ("spot", "futures", "futures-top5", "cfd-mt5"): sync_pilot(m)
        rows = build_index(); views(rows); render(rows, os.path.join(ROOT, "data", "live", ".journal-vi.html"))


if __name__ == "__main__":
    main()
