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
import argparse, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import methods as M    # noqa: E402
import instruments as I  # noqa: E402

# PANEL-01/PANEL-08 (docs/security/2026-09-12-method-panel.md): the bare {"db": {}} default lets every
# viewer of an org-internal artifact WRITE the shared control docs, and the `user` capability is not on this
# account's roster, so no viewer identity exists to gate on instead. The only remaining control is the write
# rule below, pinning both read and write to the artifact owner. Task B4's publish call MUST pass this
# constant verbatim (or omit `capabilities` to carry the stored declaration forward) -- it must never pass a
# bare `{"db": {}}`, which would restore the permissive default on republish (PANEL-08).
CAPABILITIES = {"db": {"rules": [{"path": "", "read": "owner", "write": "owner"}]}}

# PANEL-02: printed once, visibly, near the top of the rendered page -- a tap changes live trading
# configuration and the panel structurally cannot record who tapped (no `user` capability on this account).
_DISCLOSURE = ("Chạm vào đây thay đổi cấu hình giao dịch đang chạy. Trang này KHÔNG THỂ ghi nhận ai đã chạm "
               "-- nhật ký chỉ ghi actor \"artifact-panel\".")

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


def _real_backtested(root=ROOT):
    """The set of symbols the pilot rules are actually validated on, read from the structured
    docs/architecture/instruments.json -> backtested field via scripts/instruments.py (the single source,
    checked against docs/architecture/pilot-top5.json's own per-setup symbol lists when the field was written).

    This used to regex a prose sentence out of instruments.json's history; that broke silently the moment
    anyone reworded the sentence, and worse, degraded a MISS to "assume backtested" -- exactly backwards for a
    warning whose entire point is that six of nine tradeable crypto symbols were never validated. The
    structured field removes the parsing risk, and I.backtested() already answers "not backtested" for any
    symbol absent from it (or if the field is missing entirely) -- there is nothing further to soften here."""
    return set(I.backtested())


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
.disclosure { font-size: .74rem; color: var(--text-dim); margin: 0; }
.db-banner { font-size: .78rem; padding: .5rem .7rem; border-radius: 8px; border: 1px solid var(--border);
  background: var(--surface-2); color: var(--text-dim); }
.db-banner[data-kind="ready"] { color: var(--good); border-color: var(--good); background: var(--good-soft); }
.db-banner[data-kind="readonly"] { color: var(--nodata); border-color: var(--nodata); background: var(--nodata-soft); }
.heartbeat-banner { font-size: .78rem; padding: .5rem .7rem; border-radius: 8px; border: 1px solid var(--danger);
  background: var(--danger-soft); color: var(--danger); }
.request-status { font-size: .72rem; color: var(--text-dim); }
.preset-card.is-desired { outline: 2px dashed var(--accent); outline-offset: 2px; }
.chip.is-desired { outline: 2px dashed var(--accent); outline-offset: 1px; }
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
        f'<div class="request-status" data-market="{market}" aria-live="polite">chưa gửi</div>'
        f'</section>'
    )


# --------------------------------------------------------------------------------------------------------- db JS
# Wiring per docs/plans/2026-09-12-method-panel.md Task B2 and the runtime-contract-0.2.46 db.d.ts call
# contract (loaded via the artifact-capabilities skill before this was written -- not from memory).
#
# Design notes (see the task report for the fuller reasoning):
#  - `window.claude.use("db")` is awaited inside an IIFE placed at the end of the document; the browser has
#    already painted the static (build-time) markup by the time this script tag runs, and the promise itself
#    never resolves during this script's first synchronous pass (per claude.d.ts) -- so the page always shows
#    the baked state first, then lights up. Controls start DISABLED (inert) until the promise settles, one way
#    or the other: `null` (or no `window.claude` at all, e.g. a saved file opened directly) keeps them
#    disabled and shows a read-only banner; a real namespace enables them and starts the three kinds of
#    subscriptions.
#  - Optimistic vs confirmed: tapping a preset/chip only ever sets a LOCAL "desired" indicator (a dashed
#    outline via the `is-desired` class) and a per-market status line. `aria-pressed` on preset cards and
#    chips is driven exclusively by the live `control/applied.<market>` snapshot -- never by a tap -- so a
#    request can never be mistaken for something already in force.
#  - A request document is always the full three-key desired set (PANEL-10): `{preset, instruments,
#    requested_at}`, never a delta. Rapid taps within DEBOUNCE_MS collapse into a single `.set()`.
#  - Write failures: `unavailable`/`resource_exhausted` retry once after a short randomized delay (db.d.ts's
#    own guidance for verbs); `not_granted`/`revoked` permanently degrade to read-only; anything else clears
#    the pending "desired" indicator and shows an inline failure -- a failed write never leaves a card looking
#    selected.
#  - Every value read from `db` is compared as a plain string/array against what the page itself already
#    rendered from the registry (PANEL-03): no db string is ever used to build a CSS selector, an attribute,
#    or markup -- only `===` comparisons and `textContent` assignments.
_SCRIPT = """<script>
(function () {
  "use strict";

  var MARKETS = ["crypto", "cfd"];
  var STALE_MS = 12 * 60 * 1000;
  var DEBOUNCE_MS = 400;
  var RETRY_DELAY_MS = 600;
  // Literal per-market document paths (CRON-06/PANEL-06: touch only the known control documents --
  // never build a path by concatenating a runtime value into it).
  var APPLIED_DOC_PATH = { "crypto": "control/applied.crypto", "cfd": "control/applied.cfd" };
  var REQUEST_DOC_PATH = { "crypto": "control/request.crypto", "cfd": "control/request.cfd" };
  var HEARTBEAT_DOC_PATH = "control/heartbeat";

  var db = null;
  var dbReady = false;
  var applied = {};          // market -> {preset, instruments, applied_at, requested_at} | null
  var request = {};          // market -> {preset, instruments, requested_at} | null
  var pendingDesired = {};   // market -> {preset, instruments} | null -- unsent/in-flight local edits
  var writeTimer = {};
  var heartbeatAt = null;    // Date | null

  function qa(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }
  function q(sel) { return document.querySelector(sel); }

  function marketPresetCards(market) { return qa('.preset-card[data-market="' + market + '"]'); }
  function marketChips(market) { return qa('.chip-item[data-market="' + market + '"] .chip'); }
  function statusEl(market) { return q('.request-status[data-market="' + market + '"]'); }
  function dbBanner() { return q(".db-banner"); }
  function heartbeatBanner() { return q(".heartbeat-banner"); }

  function setStatusText(market, text) {
    var el = statusEl(market);
    if (el) { el.textContent = text; }
  }

  function setDbBanner(kind, text) {
    var el = dbBanner();
    if (!el) return;
    el.setAttribute("data-kind", kind);
    el.textContent = text;
  }

  function setControlsEnabled(enabled) {
    MARKETS.forEach(function (market) {
      marketPresetCards(market).forEach(function (card) {
        if (card.getAttribute("aria-disabled") === "true") return; // CoinGlass lock stays locked regardless
        card.disabled = !enabled;
      });
      marketChips(market).forEach(function (chip) { chip.disabled = !enabled; });
    });
  }

  function isPlainObject(v) { return v !== null && typeof v === "object" && !Array.isArray(v); }

  // PANEL-03: never trust shape or content. A field of the wrong type is simply dropped, never coerced.
  function validDoc(data) {
    if (!isPlainObject(data)) return null;
    return {
      preset: typeof data.preset === "string" ? data.preset : null,
      instruments: Array.isArray(data.instruments)
        ? data.instruments.filter(function (s) { return typeof s === "string"; })
        : [],
      requested_at: typeof data.requested_at === "string" ? data.requested_at : null,
      applied_at: typeof data.applied_at === "string" ? data.applied_at : null
    };
  }

  function sameInstrumentSet(a, b) {
    if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false;
    var sa = a.slice().sort(), sb = b.slice().sort();
    for (var i = 0; i < sa.length; i++) { if (sa[i] !== sb[i]) return false; }
    return true;
  }

  function formatTs(raw) {
    if (typeof raw !== "string") return "(không rõ)";
    var d = new Date(raw);
    return isNaN(d.getTime()) ? "(không rõ)" : d.toLocaleString("vi-VN");
  }

  // The build-time baked selection (what B1 rendered from automation-config.json), used only until the
  // first live applied/request snapshot arrives -- read from the page's OWN rendered attributes, never from
  // a db value, so this is always a trusted starting point.
  function bakedState(market) {
    var preset = null;
    marketPresetCards(market).forEach(function (c) {
      if (c.getAttribute("aria-pressed") === "true") preset = c.getAttribute("data-preset");
    });
    var instruments = [];
    marketChips(market).forEach(function (c) {
      if (c.getAttribute("aria-pressed") === "true") instruments.push(c.getAttribute("data-symbol"));
    });
    return { preset: preset, instruments: instruments };
  }

  function desiredBase(market) {
    if (pendingDesired[market]) return pendingDesired[market];
    if (applied[market]) return { preset: applied[market].preset, instruments: applied[market].instruments.slice() };
    if (request[market]) return { preset: request[market].preset, instruments: request[market].instruments.slice() };
    return bakedState(market);
  }

  function renderMarket(market) {
    var doc = applied[market];
    var pending = pendingDesired[market];
    marketPresetCards(market).forEach(function (card) {
      var pid = card.getAttribute("data-preset");
      if (card.getAttribute("aria-disabled") !== "true") {
        card.setAttribute("aria-pressed", (doc && doc.preset === pid) ? "true" : "false");
      }
      card.classList.toggle("is-desired", !!pending && pending.preset === pid);
    });
    var appliedSymbols = doc ? doc.instruments : [];
    marketChips(market).forEach(function (chip) {
      var sym = chip.getAttribute("data-symbol");
      chip.setAttribute("aria-pressed", appliedSymbols.indexOf(sym) !== -1 ? "true" : "false");
      chip.classList.toggle("is-desired", !!pending && pending.instruments.indexOf(sym) !== -1);
    });
    updateStatusLine(market);
  }

  function requestMatchesApplied(market) {
    var req = request[market], doc = applied[market];
    if (!req || !doc) return false;
    return doc.preset === req.preset && sameInstrumentSet(doc.instruments, req.instruments)
      && doc.requested_at === req.requested_at;
  }

  function updateStatusLine(market) {
    if (pendingDesired[market]) { setStatusText(market, "chưa gửi"); return; }
    var req = request[market], doc = applied[market];
    if (!req) {
      setStatusText(market, doc ? "đã áp dụng lúc " + formatTs(doc.applied_at) : "chưa gửi");
      return;
    }
    setStatusText(market, requestMatchesApplied(market)
      ? "đã áp dụng lúc " + formatTs(doc.applied_at)
      : "đang chờ áp dụng (≤ 5 phút)");
  }

  function pendingMinutesAcrossMarkets() {
    var max = null;
    MARKETS.forEach(function (market) {
      if (!request[market] || requestMatchesApplied(market)) return;
      var reqAt = Date.parse(request[market].requested_at);
      if (isNaN(reqAt)) return;
      var minutes = Math.max(0, Math.round((Date.now() - reqAt) / 60000));
      if (max === null || minutes > max) max = minutes;
    });
    return max;
  }

  function renderHeartbeatBanner() {
    var el = heartbeatBanner();
    if (!el) return;
    var age = heartbeatAt ? (Date.now() - heartbeatAt.getTime()) : Infinity;
    if (age <= STALE_MS) { el.hidden = true; el.textContent = ""; return; }
    el.hidden = false;
    var mins = pendingMinutesAcrossMarkets();
    el.textContent = (mins === null)
      ? "không có tiến trình áp dụng — bộ áp dụng không phản hồi"
      : "không có tiến trình áp dụng — yêu cầu đang treo " + mins + " phút";
  }

  function scheduleWrite(market) {
    if (writeTimer[market]) clearTimeout(writeTimer[market]);
    writeTimer[market] = setTimeout(function () { flushWrite(market, 1); }, DEBOUNCE_MS);
  }

  function flushWrite(market, attempt) {
    if (!db || !dbReady) return;
    var desired = pendingDesired[market];
    if (!desired) return;
    var doc = { preset: desired.preset, instruments: desired.instruments.slice(),
                requested_at: new Date().toISOString() };
    db.doc(REQUEST_DOC_PATH[market]).set(doc).then(function () {
      if (pendingDesired[market] === desired) pendingDesired[market] = null;
      request[market] = doc;
      renderMarket(market);
    }).catch(function (err) { handleWriteError(market, err, attempt, desired); });
  }

  function handleWriteError(market, err, attempt, desired) {
    var code = err && err.code;
    if ((code === "unavailable" || code === "resource_exhausted") && attempt < 2) {
      setTimeout(function () { flushWrite(market, attempt + 1); },
        RETRY_DELAY_MS + Math.floor(Math.random() * RETRY_DELAY_MS));
      return;
    }
    if (code === "not_granted" || code === "revoked") {
      dbReady = false;
      setControlsEnabled(false);
      setDbBanner("readonly", "Chỉ xem — quyền ghi đã bị thu hồi.");
    } else {
      setStatusText(market, "gửi thất bại — thử lại");
    }
    // A failed write must never leave the card looking selected: drop the pending desired state and
    // repaint from the last known applied snapshot.
    if (pendingDesired[market] === desired) pendingDesired[market] = null;
    renderMarket(market);
  }

  function onPresetClick(market, presetId) {
    if (!dbReady) return;
    var base = desiredBase(market);
    pendingDesired[market] = { preset: presetId, instruments: base.instruments.slice() };
    renderMarket(market);
    scheduleWrite(market);
  }

  function onChipClick(market, symbol) {
    if (!dbReady) return;
    var base = desiredBase(market);
    var instruments = base.instruments.slice();
    var idx = instruments.indexOf(symbol);
    if (idx === -1) { instruments.push(symbol); } else { instruments.splice(idx, 1); }
    pendingDesired[market] = { preset: base.preset, instruments: instruments };
    renderMarket(market);
    scheduleWrite(market);
  }

  document.addEventListener("click", function (evt) {
    var card = evt.target.closest ? evt.target.closest(".preset-card") : null;
    if (card) {
      if (!card.disabled) onPresetClick(card.getAttribute("data-market"), card.getAttribute("data-preset"));
      return;
    }
    var chip = evt.target.closest ? evt.target.closest(".chip") : null;
    if (chip && !chip.disabled) {
      var li = chip.closest(".chip-item");
      if (li) onChipClick(li.getAttribute("data-market"), chip.getAttribute("data-symbol"));
    }
  });

  function subscribeMarket(market) {
    db.doc(APPLIED_DOC_PATH[market]).onSnapshot(function (snap) {
      applied[market] = snap.exists ? validDoc(snap.data()) : null;
      renderMarket(market);
      renderHeartbeatBanner();
    }, function () { applied[market] = null; renderMarket(market); });

    db.doc(REQUEST_DOC_PATH[market]).onSnapshot(function (snap) {
      request[market] = snap.exists ? validDoc(snap.data()) : null;
      updateStatusLine(market);
      renderHeartbeatBanner();
    }, function () { request[market] = null; });
  }

  function subscribeHeartbeat() {
    db.doc(HEARTBEAT_DOC_PATH).onSnapshot(function (snap) {
      var data = snap.exists ? snap.data() : null;
      var at = (isPlainObject(data) && typeof data.at === "string") ? Date.parse(data.at) : NaN;
      heartbeatAt = isNaN(at) ? null : new Date(at);
      renderHeartbeatBanner();
    }, function () { heartbeatAt = null; renderHeartbeatBanner(); });
  }

  function boot() {
    setControlsEnabled(false); // inert until claude.use("db") settles, one way or the other
    if (!window.claude || typeof window.claude.use !== "function") {
      setDbBanner("readonly", "Chỉ xem — trình xem này không hỗ trợ bộ nhớ điều khiển.");
      return;
    }
    window.claude.use("db").then(function (namespace) {
      if (!namespace) {
        db = null; dbReady = false;
        setDbBanner("readonly",
          "Chỉ xem — không có quyền ghi (chưa được cấp hoặc trình xem không hỗ trợ).");
        return;
      }
      db = namespace; dbReady = true;
      setDbBanner("ready", "Đã kết nối — chạm để thay đổi cấu hình đang chạy.");
      setControlsEnabled(true);
      MARKETS.forEach(subscribeMarket);
      subscribeHeartbeat();
    }).catch(function () {
      db = null; dbReady = false;
      setDbBanner("readonly", "Chỉ xem — không kết nối được bộ nhớ điều khiển.");
    });
  }

  setInterval(renderHeartbeatBanner, 30000);
  boot();
})();
</script>"""


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
    # PANEL-02: printed unconditionally, static text -- never derived from db.
    disclosure = f'<p class="disclosure">{esc(_DISCLOSURE)}</p>'
    # PANEL-06/PANEL-07: connectivity + stale-applier banners. Both start inert/hidden; the script block
    # fills them in once claude.use("db") settles and the control/heartbeat subscription reports.
    db_banner = '<div class="db-banner" data-kind="connecting" role="status" aria-live="polite">' \
                'Đang kết nối tới bộ nhớ điều khiển…</div>'
    heartbeat_banner = '<div class="heartbeat-banner" data-kind="unknown" role="alert" aria-live="assertive" ' \
                        'hidden></div>'
    return (f'{_STYLE}\n<main class="panel">{header}{disclosure}{db_banner}{heartbeat_banner}'
            f'<div class="markets">{columns}</div></main>\n{_SCRIPT}')


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
