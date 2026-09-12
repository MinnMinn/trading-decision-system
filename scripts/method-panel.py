#!/usr/bin/env python3
"""Render the method control panel -- the page where the human taps a method preset and the instruments to run,
per market (spec docs/specs/2026-09-12-method-switch-design.md §4.4, §4.6).

Usage: method-panel.py --out FILE [--check-only]

Inputs (all read-only; each has exactly one writer elsewhere):
  docs/architecture/methods.json          presets, dimensions, runner methods   (registry, scripts/methods.py)
  docs/architecture/instruments.json      the allowlist + display metadata      (scripts/instruments.py)
  docs/architecture/automation-config.json  applied state at build time         (scripts/automation.py, single writer)
  data/live/<market-data|mt5-bridge>/      which symbols actually have candles   (scanner / MT5 EA)
  data/live/pilot-futures/top5-state.json which symbols hold an open position    (scripts/strategy-runner.py, its
                                           only writer -- STATE at strategy-runner.py:51; positions{} is keyed by
                                           symbol across BOTH markets, since one runner trades crypto futures
                                           testnet and CFD MT5 demo)

Task B1 only: this module has no `db` capability and does not publish. It renders a static HTML fragment
(no <!doctype>/<html>/<head> -- the Artifact tool supplies those) from the registry and a config dict.
"""
import argparse, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import methods as M    # noqa: E402
import instruments as I  # noqa: E402

CONFIG_PATH = os.path.join(ROOT, "docs", "architecture", "automation-config.json")
# scripts/automation.py:169 -- DATA_DIR = {"crypto": "market-data", "cfd": "mt5-bridge"}. Kept as a local
# constant rather than importing automation.py (build-artifact.py does that only where it needs automation.py's
# TIERS table; this module needs nothing else from it, and automation.py is out of scope for Task B1).
DATA_DIR = {"crypto": "market-data", "cfd": "mt5-bridge"}
PILOT_STATE_PATH = os.path.join(ROOT, "data", "live", "pilot-futures", "top5-state.json")


# ------------------------------------------------------------------------------------------- disk-probed defaults
def _real_data_present(root=ROOT):
    """Symbols with a 15m candle file on disk. Mirrors the probe automation.py already uses
    (mt5_freshness/cmd_instrument: os.path.exists(.../ohlcv.<SYM>.15m.json), automation.py:1124, :921).
    A market whose export directory does not exist at all is UNKNOWN, not "nothing present" -- degrading every
    symbol in that market to a confident "no data" badge would be a wrong answer dressed as a real one, so those
    symbols are folded into the present set instead (judgement call, see task report)."""
    present = set()
    for market, dirname in DATA_DIR.items():
        base = os.path.join(root, "data", "live", dirname)
        symbols = I.analysis(market)
        if not os.path.isdir(base):
            present.update(symbols)
            continue
        for sym in symbols:
            if os.path.exists(os.path.join(base, f"ohlcv.{sym}.15m.json")):
                present.add(sym)
    return present


_BACKTEST_CAVEAT_RE = re.compile(r"backtested on ([A-Z0-9/]+) only")


def _real_backtested(root=ROOT):
    """The set of symbols the pilot rules are actually validated on, read from the caveat recorded in
    docs/architecture/instruments.json's history (instruments.json:68, dated 2026-09-12) rather than
    hard-coded here -- there is no structured field for it yet, only the prose history entry the CAVEAT was
    written into when the six extra crypto symbols were added to execution. If the file is missing/corrupt or
    the caveat text is not found, the honest default is "unknown", not "assume nobody is backtested" (that
    would badge every allowlisted symbol, crypto and CFD alike, as unvalidated on no evidence) -- so this
    degrades to "everyone counts as backtested" (no badge) rather than a confident wrong warning."""
    try:
        with open(I.PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return set(I.ALL_ANALYSIS)
    text = " ".join((h.get("reason", "") + " " + h.get("change", "")) for h in (data.get("history") or []))
    m = _BACKTEST_CAVEAT_RE.search(text)
    if not m:
        return set(I.ALL_ANALYSIS)
    return set(m.group(1).split("/"))


def _real_open_positions(root=ROOT):
    """Symbols the top5 runner currently holds a position in, read from its own state file
    (data/live/pilot-futures/top5-state.json, strategy-runner.py:51, the runner's only writer;
    positions{} is keyed by symbol and spans both markets). Missing/corrupt state is UNKNOWN; this degrades to
    "assume no open position" rather than "assume everyone is open" -- the actual safety property (an open
    position keeps getting candles/management even if its symbol is unticked) is enforced by the runner's own
    grandfather logic (strategy-runner.py:766-767) independently of what this badge shows, so the badge erring
    quiet here is a display-honesty gap, not a trading-safety one."""
    path = os.path.join(root, "data", "live", "pilot-futures", "top5-state.json") \
        if root != ROOT else PILOT_STATE_PATH
    try:
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, ValueError):
        return set()
    positions = state.get("positions")
    return set(positions.keys()) if isinstance(positions, dict) else set()


# ------------------------------------------------------------------------------------------------------- facts()
def _flags_for_market(market, dims_cfg):
    """The four booleans /automation actually means for this market, given a possibly-partial dimensions dict.
    Mirrors methods.py:170's preset_flags rule (dispatch_plan): a key missing from a market's OWN possible
    dimensions defaults to on (an unconfigured dimension dispatches, same convention as dispatch_plan's
    config-missing fallback); a dimension this market cannot structurally have is always off, so a stray key
    left over from the other market's config block can never leak in and misname the preset."""
    have = set(M.dimensions(market))
    return {d: (bool(dims_cfg.get(d, True)) if d in have else False) for d in M.ALL_DIMENSIONS}


def facts(config_path=None, root=ROOT):
    """Every fact the page needs, computed once, from disk. render() displays this; it does not re-derive it --
    except when called directly by a test with a synthetic config, in which case render() runs the same pure
    computation itself (there is no file to read facts() from in that case)."""
    path = config_path or CONFIG_PATH
    try:
        with open(path, encoding="utf-8") as fh:
            config = json.load(fh)
        config_problem = None
    except FileNotFoundError:
        config, config_problem = {"enabled": False, "execution": {"environment": "demo"},
                                   "markets": {m: {"enabled": False, "instruments": [],
                                                    "dimensions": {}} for m in ("crypto", "cfd")}}, "missing"
    except (OSError, ValueError) as exc:
        config, config_problem = {"enabled": False, "execution": {"environment": "demo"},
                                   "markets": {m: {"enabled": False, "instruments": [],
                                                    "dimensions": {}} for m in ("crypto", "cfd")}}, f"corrupt: {exc}"

    data_present = _real_data_present(root)
    backtested = _real_backtested(root)
    open_positions = _real_open_positions(root)
    environment = ((config.get("execution") or {}).get("environment")) or "demo"

    symbols_by_market = {}
    for market in ("crypto", "cfd"):
        mcfg = (config.get("markets", {}) or {}).get(market, {}) or {}
        selected = set(mcfg.get("instruments") or [])
        symbols_by_market[market] = [
            {"symbol": s, "selected": s in selected, "data_present": s in data_present,
             "orderable": s in I.execution(market), "backtested": s in backtested,
             "open_position": s in open_positions}
            for s in I.analysis(market)
        ]

    presets_by_market = {market: M.PRESETS for market in ("crypto", "cfd")}
    return {"config": config, "config_problem": config_problem, "environment": environment,
            "presets_by_market": presets_by_market, "symbols_by_market": symbols_by_market}


# --------------------------------------------------------------------------------------------------------- style
def esc(s):
    import html as _html
    return _html.escape(str(s), quote=True)


_STYLE = """<style>
:root {
  --bg: #eef1f5; --surface: #ffffff; --surface-2: #e3e8ee; --border: #c7d0da;
  --text: #1b2430; --text-dim: #5b6675;
  --accent: #9a6b0f; --accent-ink: #2a1900; --accent-soft: #f3e6c8;
  --good: #1f7a4c; --good-soft: #d9f0e3;
  --locked: #8a94a1; --locked-soft: #e7eaee;
  --nodata: #b8541b; --nodata-soft: #fbe6d8;
  --unvalidated: #6d4aa8; --unvalidated-soft: #ece4f7;
  --open: #1c6dd0; --open-soft: #dce9fb;
  --danger: #b3261e; --danger-soft: #f8dcda;
  --focus: #1c6dd0;
  --font-ui: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  --font-mono: ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #12161c; --surface: #1a2029; --surface-2: #222a35; --border: #313b48;
    --text: #e7ecf2; --text-dim: #9aa7b5;
    --accent: #e0aa4a; --accent-ink: #241a05; --accent-soft: #3a2e12;
    --good: #4fd398; --good-soft: #123527;
    --locked: #5b6675; --locked-soft: #232b35;
    --nodata: #ef8f57; --nodata-soft: #3a2418;
    --unvalidated: #b79bef; --unvalidated-soft: #2c2440;
    --open: #6fa8ec; --open-soft: #172a42;
    --danger: #ef6b62; --danger-soft: #3a1613;
    --focus: #6fa8ec;
  }
}
:root[data-theme="dark"] {
  --bg: #12161c; --surface: #1a2029; --surface-2: #222a35; --border: #313b48;
  --text: #e7ecf2; --text-dim: #9aa7b5;
  --accent: #e0aa4a; --accent-ink: #241a05; --accent-soft: #3a2e12;
  --good: #4fd398; --good-soft: #123527;
  --locked: #5b6675; --locked-soft: #232b35;
  --nodata: #ef8f57; --nodata-soft: #3a2418;
  --unvalidated: #b79bef; --unvalidated-soft: #2c2440;
  --open: #6fa8ec; --open-soft: #172a42;
  --danger: #ef6b62; --danger-soft: #3a1613;
  --focus: #6fa8ec;
}
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--text); margin: 0; font-family: var(--font-ui); }
.panel { max-width: 960px; margin: 0 auto; padding: 1rem 1rem 3rem; display: flex; flex-direction: column; gap: 1rem; }
.panel-head { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: .5rem; }
.panel-head h1 { font-size: 1.15rem; margin: 0; text-wrap: balance; }
.env-pill { font-family: var(--font-mono); font-size: .72rem; letter-spacing: .04em; text-transform: uppercase;
  padding: .28rem .6rem; border-radius: 999px; background: var(--surface-2); border: 1px solid var(--border); }
.env-pill[data-env="real"] { background: var(--danger-soft); color: var(--danger); border-color: var(--danger); }
.markets { display: grid; grid-template-columns: 1fr; gap: 1.25rem; }
@media (min-width: 720px) { .markets { grid-template-columns: 1fr 1fr; } }
.market-col { display: flex; flex-direction: column; gap: .75rem; min-width: 0; }
.market-col h2 { font-size: .95rem; margin: 0; display: flex; align-items: center; gap: .4rem; }
.market-col h2 .ticker { font-family: var(--font-mono); color: var(--text-dim); font-size: .78rem; }
.group-label { font-size: .68rem; text-transform: uppercase; letter-spacing: .07em; color: var(--text-dim);
  margin: .2rem 0 -.15rem; }
.preset-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: .55rem; }
.preset-card { text-align: left; font-family: inherit; color: var(--text); background: var(--surface);
  border: 1px solid var(--border); border-radius: 10px; padding: .65rem .7rem; min-height: 44px;
  display: flex; flex-direction: column; gap: .35rem; cursor: pointer; }
.preset-card:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.preset-card[aria-pressed="true"] { border-color: var(--accent); background: var(--accent-soft); }
.preset-card[disabled] { cursor: not-allowed; opacity: .62; }
.preset-card[data-tier="research"] { border-style: dashed; }
.preset-head { display: flex; align-items: baseline; justify-content: space-between; gap: .4rem; }
.preset-label { font-weight: 600; font-size: .88rem; }
.tier-badge { font-size: .62rem; text-transform: uppercase; letter-spacing: .05em; padding: .1rem .4rem;
  border-radius: 5px; white-space: nowrap; }
.tier-badge[data-tier="trade"] { background: var(--good-soft); color: var(--good); }
.tier-badge[data-tier="research"] { background: var(--unvalidated-soft); color: var(--unvalidated); }
.preset-dims { font-family: var(--font-mono); font-size: .74rem; color: var(--text-dim); }
.preset-note { font-size: .72rem; color: var(--text-dim); line-height: 1.35; }
.preset-note.locked { color: var(--nodata); }
.preset-note.research { color: var(--unvalidated); }
.preset-note.realgate { color: var(--danger); }
.preset-methods { font-family: var(--font-mono); font-size: .68rem; color: var(--text-dim); }
.custom-note { font-size: .78rem; color: var(--text-dim); background: var(--surface-2); border: 1px solid var(--border);
  border-radius: 8px; padding: .5rem .6rem; }
.custom-note code { font-family: var(--font-mono); }
.chip-grid { display: flex; flex-wrap: wrap; gap: .45rem; list-style: none; margin: 0; padding: 0; }
.chip-item { margin: 0; }
.chip { font-family: var(--font-mono); font-size: .78rem; min-height: 44px; padding: 0 .65rem;
  border-radius: 8px; border: 1px solid var(--border); background: var(--surface); color: var(--text);
  display: inline-flex; align-items: center; gap: .3rem; cursor: pointer; }
.chip[aria-pressed="true"] { border-color: var(--accent); background: var(--accent-soft); color: var(--accent-ink); }
.chip:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.badge { font-size: .62rem; padding: .05rem .3rem; border-radius: 4px; line-height: 1.5; }
.badge-nodata { background: var(--nodata-soft); color: var(--nodata); }
.badge-unvalidated { background: var(--unvalidated-soft); color: var(--unvalidated); }
.badge-open { background: var(--open-soft); color: var(--open); }
.badge-locked { background: var(--locked-soft); color: var(--locked); }
.empty-note { font-size: .78rem; color: var(--text-dim); background: var(--surface-2); border: 1px dashed var(--border);
  border-radius: 8px; padding: .5rem .6rem; }
</style>"""

_TIER_LABEL = {"trade": "Đủ điều kiện vào lệnh", "research": "Chỉ nghiên cứu"}
_RESEARCH_NOTE = ("/analyze luôn NO TRADE — dưới tối thiểu 2 dimension của NORMAL (§6.1); "
                   "chỉ pilot cơ học còn bắn.")
_WYCKOFF_HONESTY = ("pilot chạy luật cơ học `scripts/wyckoff_rules.py` (CHoCH, TR từ SC/AR, "
                     "Spring vs Shakeout, VP veto), không phải bài đọc Wyckoff đầy đủ của skill.")
_REAL_GATE_NOTE = "pilot không chạy ở REAL (`strategy-runner.py:167`) — chỉ nửa phân tích của preset còn hiệu lực."
_COINGLASS_NOTE = ("Khoá ở CFD — CoinGlass là nguồn order-flow cho footprint/heatmap, "
                    "chỉ có cho crypto-derivatives (SYSTEM-DESIGN.md §12 mục 3).")
_EMPTY_NOTE = ("không cặp nào được chọn — không mở lệnh mới ở thị trường này; "
               "vị thế và lệnh chờ đang mở vẫn được quản lý.")


def _preset_card(market, preset, selected_id, environment):
    pid, tier = preset["id"], preset["tier"]
    locked = preset not in M.presets_for(market)
    pressed = "true" if (not locked and pid == selected_id) else "false"
    dims_label = " + ".join(M.DIMENSIONS[d]["label"] for d in preset["dimensions"])
    attrs = [f'data-market="{market}"', f'data-preset="{esc(pid)}"', f'data-tier="{tier}"',
             f'aria-pressed="{pressed}"']
    if locked:
        attrs += ["disabled", 'aria-disabled="true"']
    parts = [f'<button type="button" class="preset-card" {" ".join(attrs)}>']
    parts.append('<div class="preset-head">'
                 f'<span class="preset-label">{esc(preset["label"])}</span>'
                 f'<span class="tier-badge" data-tier="{tier}">{"Trade" if tier == "trade" else "Research"}</span>'
                 '</div>')
    parts.append(f'<div class="preset-dims">{esc(dims_label)}</div>')
    if locked:
        parts.append(f'<div class="preset-note locked">{esc(_COINGLASS_NOTE)}</div>')
    elif environment == "real":
        parts.append(f'<div class="preset-note realgate">{esc(_REAL_GATE_NOTE)}</div>')
    else:
        methods = sorted(M.runner_methods(M.flags_for(pid)))
        parts.append(f'<div class="preset-methods">runner: {esc(", ".join(methods) or "(không có)")}</div>')
        parts.append(f'<div class="preset-note">{esc(_WYCKOFF_HONESTY)}</div>')
    if tier == "research":
        parts.append(f'<div class="preset-note research">{esc(_RESEARCH_NOTE)}</div>')
    parts.append("</button>")
    return "".join(parts)


def _symbol_chip(market, fact):
    sym = fact["symbol"]
    li_attrs = [f'data-market="{market}"', f'data-symbol="{esc(sym)}"',
                f'data-nodata="{0 if fact["data_present"] else 1}"',
                f'data-unvalidated="{0 if fact["backtested"] else 1}"',
                f'data-orderable="{1 if fact["orderable"] else 0}"',
                f'data-open="{1 if fact["open_position"] else 0}"']
    label = I.display(sym)["label"]
    badges = []
    if not fact["data_present"]:
        badges.append('<span class="badge badge-nodata" title="Chưa có dữ liệu nến trên đĩa">chưa có dữ liệu</span>')
    if not fact["backtested"]:
        badges.append('<span class="badge badge-unvalidated" title="Chưa kiểm định bằng backtest">chưa kiểm định</span>')
    if not fact["orderable"]:
        badges.append('<span class="badge badge-locked" title="Chỉ phân tích, không đặt lệnh được">không đặt lệnh</span>')
    if fact["open_position"]:
        badges.append('<span class="badge badge-open" title="Đang có lệnh mở">đang mở</span>')
    pressed = "true" if fact["selected"] else "false"
    return (f'<li class="chip-item" {" ".join(li_attrs)}>'
            f'<button type="button" class="chip" data-symbol="{esc(sym)}" aria-pressed="{pressed}">'
            f'<span class="chip-label">{esc(label)}</span>{"".join(badges)}</button></li>')


def _market_column(market, config, data_present, backtested, open_positions, environment):
    mcfg = (config.get("markets", {}) or {}).get(market, {}) or {}
    dims_cfg = mcfg.get("dimensions") or {}
    flags = _flags_for_market(market, dims_cfg)
    selected_id = M.profile_of(flags)

    trade_cards = "".join(_preset_card(market, p, selected_id, environment)
                           for p in M.PRESETS if p["tier"] == "trade")
    research_cards = "".join(_preset_card(market, p, selected_id, environment)
                              for p in M.PRESETS if p["tier"] == "research")

    selected_syms = set(mcfg.get("instruments") or [])
    facts_syms = [
        {"symbol": s, "selected": s in selected_syms, "data_present": s in data_present,
         "orderable": s in I.execution(market), "backtested": s in backtested,
         "open_position": s in open_positions}
        for s in I.analysis(market)
    ]
    chips = "".join(_symbol_chip(market, f) for f in facts_syms)

    custom_note = ""
    if selected_id == "custom":
        bool_line = ", ".join(f"{d}={flags[d]}" for d in M.ALL_DIMENSIONS if d in M.dimensions(market))
        custom_note = ('<div class="custom-note">Preset hiện tại: <code>custom</code> — '
                        f'{esc(bool_line)}. đặt từ terminal — chạm một preset để ghi đè.</div>')

    empty_note = f'<div class="empty-note">{esc(_EMPTY_NOTE)}</div>' if not selected_syms else ""

    market_label = "Crypto" if market == "crypto" else "CFD"
    ticker_hint = "/".join(I.analysis(market)[:3]) + ("…" if len(I.analysis(market)) > 3 else "")
    return (
        f'<section class="market-col" data-market="{market}">'
        f'<h2>{market_label} <span class="ticker">{esc(ticker_hint)}</span></h2>'
        f'{custom_note}'
        f'<div class="group-label">{_TIER_LABEL["trade"]}</div>'
        f'<div class="preset-grid">{trade_cards}</div>'
        f'<div class="group-label">{_TIER_LABEL["research"]}</div>'
        f'<div class="preset-grid">{research_cards}</div>'
        f'<div class="group-label">Cặp theo dõi</div>'
        f'{empty_note}'
        f'<ul class="chip-grid">{chips}</ul>'
        f'</section>'
    )


def render(config, data_present=None, backtested=None, open_positions=None):
    """config: the automation-config.json shape (a dict, injected directly by tests or read by facts()).
    data_present/backtested/open_positions: sets of symbols; default to a live filesystem/state probe so tests
    can inject any combination without touching disk."""
    data_present = _real_data_present() if data_present is None else set(data_present)
    backtested = _real_backtested() if backtested is None else set(backtested)
    open_positions = _real_open_positions() if open_positions is None else set(open_positions)
    environment = ((config.get("execution") or {}).get("environment")) or "demo"

    columns = "".join(_market_column(m, config, data_present, backtested, open_positions, environment)
                       for m in ("crypto", "cfd"))
    env_label = "REAL (tiền thật)" if environment == "real" else "DEMO (testnet, tiền giả)"
    header = (
        '<div class="panel-head"><h1>Công tắc phương pháp</h1>'
        f'<span class="env-pill" data-env="{esc(environment)}">{esc(env_label)}</span></div>'
    )
    return f'{_STYLE}\n<main class="panel">{header}<div class="markets">{columns}</div></main>'


# --------------------------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Render the method control panel from the registry and the live "
                                              "config (docs/specs/2026-09-12-method-switch-design.md §4.4, §4.6).")
    ap.add_argument("--out", help="write the rendered HTML fragment to this path")
    ap.add_argument("--check-only", action="store_true", help="render but do not write; exit 0 on success")
    args = ap.parse_args()

    f = facts()
    out_html = render(f["config"])
    if f["config_problem"]:
        print(f"note: automation-config.json {f['config_problem']} -- rendered with the safe default config",
              file=sys.stderr)

    if args.check_only:
        print(f"OK ({len(out_html)} bytes)")
        return 0
    if not args.out:
        print("error: --out FILE is required unless --check-only", file=sys.stderr)
        return 1
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(out_html)
    print(f"wrote {args.out} ({len(out_html)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
