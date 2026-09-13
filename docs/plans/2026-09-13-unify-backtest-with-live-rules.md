# Unify the backtest with the live analysis rules — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `scripts/backtest-methods.py` compute its ICT setups and its higher-timeframe bias with the same code the live analysis path runs (`scripts/ict-scan.py`, `scripts/htf_context.py`), so a backtest measures the system that actually trades.

**Architecture:** The backtest keeps its account simulation, reporting and trade shape. Only two things are replaced: (1) the higher-timeframe filter `htf_allows` — a rolling-range percentile proxy — becomes `htf_context.bias_of`; (2) the ICT setup detection (`all_pivots` / `find_ict` / `fvg_fill` / `ict_target`) becomes a point-in-time call to `ict_scan.analyze` + `ict_scan.setup_candidate` over the same trailing window the live scanner uses. The old engine stays reachable behind `--rules legacy` so old-vs-new can be compared rather than lost.

**Tech Stack:** Python 3 stdlib only. `unittest` run by `pytest`. No new dependencies.

**Run tests:** `python3 -m pytest scripts/tests/ -q` from the repo root. A task is done only when the **whole** directory is green, not just the new test.

---

## Context an implementer needs before starting

**Three code paths exist today. Two are live.**

| Path | Rules | Live? |
|---|---|---|
| Analysis / page (`ict-scan.py` + `htf_context.py`) | full ICT scanner; bias per engaged method | yes — renders the pages, drives verdicts and the Sonnet briefs |
| Execution (`strategy-runner.py`) | **imports `backtest-methods.py`** and calls it function for function | **paused 2026-09-13** — `layers.pilot` off at the user's request; it placed orders until then (`pilot_profile: top5`) |
| `demo-pilot.py` | `ict-scan` + `htf_context` | no — the `legacy` profile, not selected |

Because `strategy-runner.py:41` imports `backtest-methods.py`, **editing the backtest edits the order gate.** `strategy-runner.py:525` calls `bt.htf_allows` directly.

The user paused that pilot on 2026-09-13 (`layers.pilot off`), so nothing trades while this plan runs — but the coupling is still there and comes back the moment the layer is switched on. Treat every edit to `backtest-methods.py` as an edit to order gating.

**Already unified — do not touch.** The Wyckoff side is already shared: `backtest-methods.py:52` and `strategy-runner.py:42` both `import wyckoff_rules as W`. The Wyckoff *dimension* in `/automation` is a discretionary Sonnet read with no code path, so there is nothing to unify there. This plan changes the ICT side and the bias only.

**The seven divergences this plan closes** (measured 2026-09-13):

| | `backtest-methods.py` | `ict-scan.py` | Closed by |
|---|---|---|---|
| Pivot width | hardcoded `3` (`:75`) | `PIV` from `analysis-params.json` (`:58`) | Task 4 |
| Liquidity sweep | pierce of `min(L[i-R:i-5])` | equal-high/low BSL/SSL pools, `EQ_TOL`, ≥4 bars apart | Task 4 |
| MSS | body close beyond last pivot, within `K` bars | swing state machine, bias flips on HH/LL, no `K` | Task 4 |
| FVG | 3-candle gap, **no size filter** (`:137`) | `size ≥ FVG_MIN × med` + mitigation tracking | Task 4 |
| Displacement | median of previous `R` bars (`:118`) | median of the whole window (`:90`) | Task 4 |
| Dealing range / PD | rolling `R`-bar extremes | nearest unswept BSL/SSL | Task 4 |
| HTF bias | `htf_allows`: percentile of an `R`-bar range, thirds | `bias_of`: draw + MSS, per engaged method | Task 3 |

**Binding security rules.** `docs/security/2026-09-11-top5-pilot.md` rules PILOT-01..PILOT-07 govern anything `strategy-runner.py` does. This plan does not change activation, locking, reconciliation or client ids — but Task 7 re-verifies them, because the tick's setup list changes.

**Safety state at plan time.** Three independent locks, all confirmed 2026-09-13:
- `/automation` master switch OFF
- `layers.pilot` OFF (set 2026-09-13T04:58:52Z, "pause the top5 pilot while the backtest is unified")
- kill switches present: `data/live/pilot/STOP`, `data/live/pilot-futures/STOP`

`pilot_process.pid` is 0 and `pgrep` finds no loop. Do not lift any of these inside this plan; restarting is a separate, explicit user decision after the Task 6 comparison has been read.

**Measured cost of the new engine** (BTCUSDT 15m history, `analyze` with `methods=("ict",)`):

| window | ms/call |
|---|---|
| 240 | 0.31 |
| 360 | 0.52 |
| 480 | 0.78 |
| 576 | 0.93 |

One full run over 3 symbols × 5 timeframes ≈ **11.4 minutes**. All **nine** configured crypto instruments (see Task 5) is roughly 3× that — about 35 minutes. Acceptable for an offline job. Do not add caching until Task 6's timing shows it is actually needed.

**Symbol set.** Every run in this plan uses the nine instruments in `automation-config.json markets.crypto.instruments`, NOT `backtest-methods.py`'s three-symbol default. The default is how the 2026-09-13 comparison came to cover only BTC/ETH/SOL.

---

## File structure

| File | Responsibility after this plan |
|---|---|
| `scripts/automation.py` | gains `SCAN_WINDOW` — the one table of (bars, recent) per timeframe, today duplicated in `scan-loop.sh` |
| `scripts/scan-loop.sh` | reads the window table instead of hardcoding it |
| `scripts/live_rules.py` | **new.** The point-in-time adapter: given a candle series and a bar index, run the live scanner over the trailing window and return the live facts + bias. The only new file. |
| `scripts/backtest-methods.py` | keeps `simulate`, `walk`, `period_returns`, reporting, trade shape. `scan()`'s ICT branch and `htf_allows` delegate to `live_rules`. `--rules legacy` keeps the old engine reachable. |
| `scripts/tests/test_live_rules.py` | **new.** Point-in-time discipline (no look-ahead), window construction, bias parity with `htf_context`. |
| `scripts/tests/test_strategy_runner.py` | existing parity tests updated for the new setup source |
| `docs/backtests/2026-09-13-live-rules-vs-legacy.md` | **new.** The old-vs-new comparison this change must justify itself with. |

---

## Task 1: Single-source the scan window table

`scan-loop.sh` is the only place that knows the live scanner reads 360 bars of 1m, 576 of 15m, 480 of 1H, 360 of 4H, 240 of 1D. The backtest must use the *same* windows or it is not reproducing live. A bash-only table cannot be imported.

**Files:**
- Modify: `scripts/automation.py` (add `SCAN_WINDOW` next to `STYLE`, around line 119)
- Modify: `scripts/scan-loop.sh:84-94`
- Test: `scripts/tests/test_timeframe_ladder.py`

- [ ] **Step 1: Write the failing test**

Append to `scripts/tests/test_timeframe_ladder.py`, inside `class Ladder`:

```python
    def test_scan_window_table_matches_the_loop(self):
        """The window the live scanner reads is a number the backtest must reproduce exactly; it lived only in
        scan-loop.sh, where nothing could import it."""
        self.assertEqual(self.a.SCAN_WINDOW["1m"], {"bars": 360, "recent": 4})
        self.assertEqual(self.a.SCAN_WINDOW["15m"], {"bars": 576, "recent": 2})
        self.assertEqual(self.a.SCAN_WINDOW["1H"], {"bars": 480, "recent": 2})
        self.assertEqual(self.a.SCAN_WINDOW["4H"], {"bars": 360, "recent": 2})
        self.assertEqual(self.a.SCAN_WINDOW["1D"], {"bars": 240, "recent": 1})
        self.assertEqual(self.a.SCAN_WINDOW["5m"], {"bars": 576, "recent": 4})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest scripts/tests/test_timeframe_ladder.py -q`
Expected: FAIL with `AttributeError: module 'automation' has no attribute 'SCAN_WINDOW'`

- [ ] **Step 3: Write minimal implementation**

In `scripts/automation.py`, immediately after the `STYLE = {...}` block (around line 122):

```python
# How many bars the live scanner reads per timeframe, and how many count as "recent" for event detection.
# THE one table: scripts/scan-loop.sh reads it (it used to hardcode the numbers) and scripts/live_rules.py
# reproduces the live window from it, so a backtest sees exactly the window the scanner saw.
SCAN_WINDOW = {
    "1m":  {"bars": 360, "recent": 4},
    "5m":  {"bars": 576, "recent": 4},
    "15m": {"bars": 576, "recent": 2},
    "1H":  {"bars": 480, "recent": 2},
    "4H":  {"bars": 360, "recent": 2},
    "1D":  {"bars": 240, "recent": 1},
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest scripts/tests/test_timeframe_ladder.py -q`
Expected: PASS

- [ ] **Step 5: Make `scan-loop.sh` read the table**

Replace the hardcoded numbers in `scripts/scan-loop.sh`. Add near the top, after `ROOT` is set:

```bash
# The window table lives in scripts/automation.py (SCAN_WINDOW); read it rather than repeating the numbers here.
win() { python3 -c "
import importlib.util,sys
s=importlib.util.spec_from_file_location('a','$ROOT/scripts/automation.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
w=m.SCAN_WINDOW['$1']; print(w['bars'], w['recent'])"; }
```

Then change each call site to use it, e.g. line 84:

```bash
run_style 1m scalping $(win 1m)
```

`run_style`'s current signature is `tf n style recent [symbols]`, and `style` is load-bearing in the body (the `AUTO_STYLES` gate, `--style` to `ict-scan.py`, the `model_read` call, the log line) — keep it. Reorder to `tf style bars recent [symbols]` so the two words `$(win <tf>)` expands to land on `bars recent`, and keep `symbols` last for the MT5 bridge. Apply the same edit to every other `run_style` call in the file.

- [ ] **Step 6: Verify the loop still resolves the same numbers**

Run: `bash -n scripts/scan-loop.sh && ROOT=$PWD bash -c 'source /dev/stdin <<< "$(sed -n \"/^win()/,/^}/p\" scripts/scan-loop.sh)"; win 15m'`
Expected: `576 2`

- [ ] **Step 7: Run the whole suite**

Run: `python3 -m pytest scripts/tests/ -q`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add scripts/automation.py scripts/scan-loop.sh scripts/tests/test_timeframe_ladder.py
git commit -m "automation: the scan window table is one table, not a bash literal"
```

---

## Task 2: The point-in-time adapter

The live scanner sees one trailing window per tick. A backtest must reproduce that exactly, and must never see a bar that had not closed. This task creates the adapter and pins the no-look-ahead property.

**Files:**
- Create: `scripts/live_rules.py`
- Test: `scripts/tests/test_live_rules.py`

- [ ] **Step 1: Write the failing test**

Create `scripts/tests/test_live_rules.py`:

```python
"""The backtest must see exactly what the live scanner saw: the same trailing window, and not one bar more.

A look-ahead bug here is invisible in the results (it just makes them better), so it is pinned by construction:
read_at(i) must depend only on candles[:i+1], which is asserted by mutating the future and re-reading.
"""
import importlib.util, os, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load(name):
    p = os.path.join(ROOT, "scripts", name)
    spec = importlib.util.spec_from_file_location(name.replace("-", "_").replace(".py", ""), p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def candles(n=800, base=100.0):
    out = []
    for i in range(n):
        out.append({"time": f"2026-01-01T00:{i // 60:02d}:{i % 60:02d}Z", "open": base + (i % 3),
                    "high": base + 2 + (i % 7), "low": base - 2 - (i % 5), "close": base + (i % 3),
                    "volume": 10.0})
    return out


class Window(unittest.TestCase):
    def setUp(self):
        self.lr = load("live_rules.py")

    def test_window_is_the_live_scan_window_for_that_timeframe(self):
        c = candles()
        w = self.lr.window(c, 700, "15m")
        self.assertEqual(len(w), 576)
        self.assertIs(w[-1], c[700])

    def test_window_is_short_near_the_start_not_padded(self):
        c = candles(100)
        self.assertEqual(len(self.lr.window(c, 40, "15m")), 41)

    def test_read_at_is_none_before_there_are_enough_bars(self):
        self.assertIsNone(self.lr.read_at(candles(20), 10, "15m"))


class NoLookAhead(unittest.TestCase):
    def setUp(self):
        self.lr = load("live_rules.py")

    def test_future_bars_cannot_change_the_read(self):
        c = candles()
        before = self.lr.read_at(c, 700, "15m")
        for x in c[701:]:
            x["high"] += 5000; x["low"] -= 5000; x["close"] += 5000
        after = self.lr.read_at(c, 700, "15m")
        self.assertEqual(before, after)


class BiasMatchesHtfContext(unittest.TestCase):
    def setUp(self):
        self.lr = load("live_rules.py")
        self.htf = load("htf_context.py")

    def test_bias_at_uses_htf_context_not_a_reimplementation(self):
        c = candles()
        facts = self.lr.read_at(c, 700, "15m")
        self.assertEqual(self.lr.bias_at(c, 700, "15m", ("ict",)),
                         self.htf.bias_of(None, facts, methods=("ict",)))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest scripts/tests/test_live_rules.py -q`
Expected: FAIL — `FileNotFoundError` / `ModuleNotFoundError` for `scripts/live_rules.py`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/live_rules.py`:

```python
#!/usr/bin/env python3
"""Point-in-time adapter: run the LIVE analysis rules over stored candles, one bar at a time.

Why this exists: scripts/backtest-methods.py used to reimplement the ICT rules and the giảm-khung filter with
simplified proxies, so a backtest measured a system nobody trades (audit 2026-09-13). This module is the seam
that lets the backtest call the real thing — scripts/ict-scan.py for the structures and scripts/htf_context.py
for the bias — without the backtest having to know how either works.

The contract is point-in-time: read_at(candles, i, tf) may look at candles[:i+1] and nothing later. The live
scanner reads a fixed trailing window per timeframe (scripts/automation.py SCAN_WINDOW), so this reproduces that
window rather than the whole history — a backtest that fed the scanner 105,000 bars would not be reproducing
anything live ever does.
"""
import importlib.util, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, mod):
    spec = importlib.util.spec_from_file_location(mod, os.path.join(ROOT, "scripts", name))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


ict_scan = _load("ict-scan.py", "ict_scan")      # public on purpose: backtest-methods.py calls setup_candidate
htf = _load("htf_context.py", "htf_context")     # public on purpose: backtest-methods.py calls bias_of
_auto = _load("automation.py", "automation")

MIN_BARS = 60   # below this a window has no median range worth trusting; the scanner never runs that thin


def spec(tf):
    """(bars, recent) the live scanner uses for this timeframe. KeyError for a timeframe live never scans —
    deliberately loud: a backtest on such a timeframe cannot claim to reproduce live."""
    w = _auto.SCAN_WINDOW[tf]
    return w["bars"], w["recent"]


def window(candles, i, tf):
    """The trailing window the live scanner would have seen at bar i, inclusive. Short near the start, never padded."""
    bars, _ = spec(tf)
    return candles[max(0, i - bars + 1):i + 1]


def read_at(candles, i, tf, methods=("ict",)):
    """The live scanner's facts for bar i, or None when there are too few bars. Depends only on candles[:i+1]."""
    w = window(candles, i, tf)
    if len(w) < MIN_BARS:
        return None
    _, recent = spec(tf)
    return ict_scan.analyze(w, recent, tf=tf, methods=methods)


def setup_lookback(tf):
    """The window a setup's sweep must sit inside, as LIVE defaults it: ict-scan.py:466 uses
    `args.setup_lookback or max(12, args.recent * 6)`. The backtest must not substitute a parameter of its own —
    reproducing live is the whole point (user decision 2026-09-13: live defaults for everything)."""
    _, recent = spec(tf)
    return max(12, recent * 6)


def bias_at(candles, i, tf, methods=("ict",)):
    """(bias, basis) at bar i, from htf_context — the same function the pages and the checkers use."""
    facts = read_at(candles, i, tf, methods)
    if facts is None:
        return "unknown", "chưa đủ nến trong cửa sổ quét"
    return htf.bias_of(None, facts, methods=methods)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest scripts/tests/test_live_rules.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m pytest scripts/tests/ -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add scripts/live_rules.py scripts/tests/test_live_rules.py
git commit -m "live_rules: point-in-time adapter so a backtest can run the live scanner"
```

---

## Task 3: Replace the HTF bias filter

`bt.htf_allows` is called by `strategy-runner.py:525` — the live order gate. This task changes it. The old behaviour stays reachable so Task 6 can quantify the difference.

**Files:**
- Modify: `scripts/backtest-methods.py:232-257` (`htf_position`, `htf_allows`)
- Test: `scripts/tests/test_live_rules.py`

- [ ] **Step 1: Write the failing test**

Append to `scripts/tests/test_live_rules.py`:

```python
class HtfGate(unittest.TestCase):
    """The gate strategy-runner.py:525 calls. `legacy` is the pre-2026-09-13 percentile proxy, kept so the two
    can be compared; `live` is htf_context.bias_of."""

    def setUp(self):
        self.bt = load("backtest-methods.py")

    def test_live_gate_passes_only_when_the_bias_agrees(self):
        self.assertTrue(self.bt.bias_allows("long", "long"))
        self.assertTrue(self.bt.bias_allows("short", "short"))
        self.assertFalse(self.bt.bias_allows("short", "long"))

    def test_live_gate_refuses_neutral_and_unknown(self):
        self.assertFalse(self.bt.bias_allows("neutral", "long"))
        self.assertFalse(self.bt.bias_allows("unknown", "long"))

    def test_legacy_percentile_gate_is_still_reachable(self):
        self.assertTrue(self.bt.htf_allows([("t", 0.2)], "u", "long"))
        self.assertFalse(self.bt.htf_allows([("t", 0.5)], "u", "long"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest scripts/tests/test_live_rules.py -q`
Expected: FAIL with `AttributeError: module 'backtest-methods' has no attribute 'bias_allows'`

- [ ] **Step 3: Write minimal implementation**

In `scripts/backtest-methods.py`, immediately after `htf_allows` (around line 257):

```python
def bias_allows(bias, side):
    """The giảm-khung gate read from the LIVE bias (htf_context.bias_of via live_rules.bias_at).

    Only an explicit agreement opens the gate: `neutral` is a real reading that found no direction and `unknown`
    means no read was available, and neither is permission to take risk (capital preservation first). This
    replaces htf_allows, the rolling-percentile proxy, which is kept above so --rules legacy still runs."""
    return bias == side
```

And in `htf_allows`'s docstring, add a first line:

```python
    """LEGACY (pre-2026-09-13) proxy, reachable via --rules legacy. The live gate is bias_allows().
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest scripts/tests/test_live_rules.py -q`
Expected: PASS

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m pytest scripts/tests/ -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add scripts/backtest-methods.py scripts/tests/test_live_rules.py
git commit -m "backtest: the giảm-khung gate reads the live bias, legacy proxy kept behind a flag"
```

---

## Task 4: Drive the ICT branch from the live scanner

**Files:**
- Modify: `scripts/backtest-methods.py` — `scan()`, the `--- ICT ---` branch (around lines 390-428), and `main()`'s argument parser
- Test: `scripts/tests/test_live_rules.py`

- [ ] **Step 1: Write the failing test**

Append to `scripts/tests/test_live_rules.py`:

```python
class IctBranchUsesTheLiveScanner(unittest.TestCase):
    def setUp(self):
        self.bt = load("backtest-methods.py")

    def test_rules_flag_defaults_to_live(self):
        self.assertEqual(self.bt.OPTS["rules"], "live")

    def test_live_ict_setups_come_from_setup_candidate(self):
        """The live entry/stop/target rule is ict-scan.setup_candidate; the backtest must not re-derive one."""
        import inspect
        src = inspect.getsource(self.bt.ict_setups_live)
        self.assertIn("setup_candidate", src)
        self.assertNotIn("find_ict", src)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest scripts/tests/test_live_rules.py -q`
Expected: FAIL — `KeyError: 'rules'` and `AttributeError: ... 'ict_setups_live'`

- [ ] **Step 3: Write minimal implementation**

Add `"rules": "live"` to the `OPTS` dict in `scripts/backtest-methods.py`, and add this function next to `scan()`:

```python
def ict_setups_live(sym, tf, c, Tm, HZ, H, L, C, methods):
    """ICT trades for one symbol/timeframe using the LIVE rules: at each bar, run the scanner over the window the
    live scanner would have read and ask IT for the setup. No pivot/MSS/FVG logic of our own — that duplication is
    what made a backtest measure a system nobody trades (audit 2026-09-13).

    The entry is a LIMIT at the FVG near edge, exactly as live places it (strategy-runner.py: "LIMIT at the FVG
    near edge"). So a setup is NOT a trade: fvg_fill() decides whether price ever came back to that limit without
    first hitting the stop, and returns None when the order would simply never have filled. Skipping that check
    would enter every setup at a favourable price and make the whole backtest optimistic by construction."""
    out, seen = [], set()
    n = len(c)
    idx_of_time = {t: j for j, t in enumerate(Tm)}
    for i in range(n):
        a = lr.read_at(c, i, tf, methods)
        if a is None:            # window not yet the full live window — live would not have scanned here at all
            continue
        su = lr.ict_scan.setup_candidate(a, lr.window(c, i, tf), lr.setup_lookback(tf))
        if not su or not su.get("complete") or not su.get("pd_ok"):
            continue
        bias, _ = lr.bias_at(c, i, tf, methods, facts=a)      # facts reused: no second analyze()
        if not bias_allows(bias, su["side"]):
            continue
        key = (su["side"], su["sweep"]["time"], su["mss"]["time"])
        if key in seen:          # the same setup stays visible for many bars; take it once, at its first bar
            continue
        seen.add(key)
        mss_i = idx_of_time.get(su["mss"]["time"])
        if mss_i is None:
            continue
        entry = su["entry"]; stop = su["stop"]; target = su["target"]
        far = su["entries"]["fill"]
        fill = fvg_fill(su["side"], mss_i, entry, far, stop, H, L, P[tf]["K"], n)
        if fill is None:         # the limit never filled: live would hold an unfilled order, not a position
            continue
        w = walk(su["side"], entry, stop, target, H, L, C, fill + 1, HZ)
        if not w:
            continue
        out.append(dict(symbol=sym, tf=tf, side=su["side"], time=Tm[i], entry=entry, entry_time=Tm[fill],
                        stop=stop, target=target, exit_time=Tm[w["exit"]], vol_type=None, **w))
    return out
```

Add the module handles near the other importlib loads (around line 229):

```python
_lspec = _iu.spec_from_file_location("live_rules", os.path.join(ROOT, "scripts", "live_rules.py"))
lr = _iu.module_from_spec(_lspec); _lspec.loader.exec_module(lr)
```

In `scan()`, replace the body of the `--- ICT ---` branch with:

```python
    if OPTS["rules"] == "live":
        trades["ICT"] = ict_setups_live(sym, tf, c, Tm, HZ, H, L, C, OPTS["methods"])
    else:
        <the existing legacy ICT block, unchanged>
```

In `main()`'s parser add:

```python
    ap.add_argument("--rules", choices=["live", "legacy"], default="live",
                    help="live = the rules scripts/ict-scan.py + scripts/htf_context.py run (default); "
                         "legacy = the pre-2026-09-13 in-file proxies, kept for comparison")
```

and set `OPTS["rules"] = a.rules` where the other OPTS are assigned.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest scripts/tests/test_live_rules.py -q`
Expected: PASS

- [ ] **Step 5: Smoke-run one symbol end to end**

Run: `python3 scripts/backtest-methods.py --tf 1D --symbols BTCUSDT --json /tmp/bt-live-smoke.json`
Expected: exit 0, a report on stdout, `ICT` row present with a trade count

- [ ] **Step 6: Run the whole suite**

Run: `python3 -m pytest scripts/tests/ -q`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add scripts/backtest-methods.py scripts/tests/test_live_rules.py
git commit -m "backtest: ICT setups come from the live scanner, not a second implementation"
```

---

## Task 5: Fetch the missing history so all nine instruments can be tested

Six of the nine configured crypto instruments have **no 15m and no 1H history at all** — the two timeframes the
daytrade and 1h styles run on. A backtest over nine symbols would silently cover three of them on those rungs.

| symbol | 5m | 15m | 30m | 1H | 2H | 4H | 1D |
|---|---|---|---|---|---|---|---|
| BTCUSDT / ETHUSDT / SOLUSDT | 105k | 105k | 70k | 35k | 17k | 8k | 1k |
| ASTERUSDT | 98k | — | 16k | — | 4k | 2k | <1k |
| VIRTUALUSDT | 105k | — | 24k | — | 6k | 3k | <1k |
| SUIUSDT | 105k | — | 58k | — | 14k | 7k | 1k |
| TAOUSDT | 105k | — | 42k | — | 10k | 5k | <1k |
| RENDERUSDT | 105k | — | 37k | — | 9k | 4k | <1k |
| ONDOUSDT | 105k | — | 24k | — | 6k | 3k | <1k |

**Files:**
- Create: `data/history/ohlcv.<SYM>.15m.json`, `data/history/ohlcv.<SYM>.1H.json` for the six

- [ ] **Step 1: Fetch the two missing timeframes for the six instruments**

`scripts/fetch-history.py` takes positional arguments: `<symbol> <timeframe> <bars>`.

```bash
for s in ASTERUSDT VIRTUALUSDT SUIUSDT TAOUSDT RENDERUSDT ONDOUSDT; do
  python3 scripts/fetch-history.py "$s" 15m 105000
  python3 scripts/fetch-history.py "$s" 1H  35000
done
```

Expected: twelve files written. A young listing returns fewer bars than asked — that is fine and must be
reported, not padded.

- [ ] **Step 2: Verify coverage and record what is genuinely short**

```bash
python3 - <<'EOF'
import json, os
syms = json.load(open('docs/architecture/automation-config.json'))['markets']['crypto']['instruments']
for s in syms:
    for t in ("5m","15m","1H","4H","1D"):
        p=f"data/history/ohlcv.{s}.{t}.json"
        n=len(json.load(open(p))['candles']) if os.path.exists(p) else 0
        if n < 5000: print(f"SHORT {s} {t}: {n} bars")
EOF
```

Expected: a list of genuinely short series. Carry that list into the Task 6 report — a method with 40 trades on
one symbol and 4 on another is not comparable across them, and the report must say so rather than averaging it away.

- [ ] **Step 3: Commit**

`data/` is not tracked by git, so there is nothing to commit here. Record the coverage table in the Task 6 report instead.

---
## Task 6: Old vs new comparison report

The change has to justify itself with numbers, and every existing report in `docs/backtests/` was produced by the legacy engine.

**Files:**
- Create: `docs/backtests/2026-09-13-live-rules-vs-legacy.md`

- [ ] **Step 1: Produce both result sets**

```bash
SYMS=$(python3 -c "import json;print(','.join(json.load(open('docs/architecture/automation-config.json'))['markets']['crypto']['instruments']))")
python3 scripts/backtest-methods.py --rules legacy --tf 5m,15m,1H,4H,1D \
  --symbols "$SYMS" --json /tmp/bt-legacy.json > /tmp/bt-legacy.md
python3 scripts/backtest-methods.py --rules live   --tf 5m,15m,1H,4H,1D \
  --symbols "$SYMS" --json /tmp/bt-live.json   > /tmp/bt-live.md
```

Expected: both exit 0. Over nine instruments the live run takes roughly 35 minutes; the legacy run is under a minute.

- [ ] **Step 2: Write the comparison document**

Create `docs/backtests/2026-09-13-live-rules-vs-legacy.md` with, per timeframe and per method: trade count, win %, ΣR, PF, final equity, max drawdown, and the blow-up date if any — legacy column and live column side by side. State plainly which methods got better, which got worse, and that the legacy numbers describe rules nothing runs any more. Include the Task 5 coverage table and the SHORT list, so a reader can see which symbol/timeframe cells rest on thin samples.

- [ ] **Step 3: Mark the superseded reports**

Add one line at the top of every file in `docs/backtests/` dated before 2026-09-13:

```markdown
> **Superseded 2026-09-13.** Produced by the legacy in-file ICT rules, replaced by the live scanner
> (`docs/plans/2026-09-13-unify-backtest-with-live-rules.md`). Numbers here describe rules nothing runs.
```

- [ ] **Step 4: Commit**

```bash
git add docs/backtests/
git commit -m "backtests: live-rules vs legacy comparison; mark superseded reports"
```

---

## Task 7: Re-verify the paused runner

`strategy-runner.py` imports the functions Task 3 and Task 4 changed. The pilot layer is off, so nothing trades — but the parity tests and the security rules must be green before anyone ever lifts that pause.

**Files:**
- Modify: `scripts/tests/test_strategy_runner.py`
- Read: `docs/security/2026-09-11-top5-pilot.md`

- [ ] **Step 1: Run the existing parity tests and read the failures**

Run: `python3 -m pytest scripts/tests/test_strategy_runner.py -q`
Expected: `test_replay_matches_backtest_first_setup` and `test_fvg_complete_by_mss_close` fail — they assert the legacy setup shape.

- [ ] **Step 2: Update the parity tests to the live setup source**

Rewrite the failing assertions against `bt.ict_setups_live` output. Keep `test_risk_never_above_one_percent_and_notional_capped`, `test_refuses_real_environment`, `test_refuses_wrong_profile`, `test_refuses_master_off` **unchanged** — those pin PILOT-01..04 and must not move.

- [ ] **Step 3: Re-verify the binding security rules**

Read `docs/security/2026-09-11-top5-pilot.md` §4 and confirm by test run that PILOT-01..PILOT-07 still hold: environment pinned twice, no silent env override, fail-secure automation gate, profile exclusivity, single-flight lock, exchange reconciliation, client ids. None of these are touched by this plan; the point is to prove it, not assume it.

Run: `python3 -m pytest scripts/tests/test_strategy_runner.py -q`
Expected: all pass

- [ ] **Step 4: Run the whole suite**

Run: `python3 -m pytest scripts/tests/ -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add scripts/tests/test_strategy_runner.py
git commit -m "strategy-runner: parity tests follow the live setup source; PILOT-01..07 re-verified"
```

---

## Task 8: Remove the legacy engine — CONDITIONAL on Task 6

**Gate.** Do this task ONLY if the Task 6 report shows the live rules are better than legacy. "Better" must be
stated as evidence, not impression: ΣR, profit factor and blow-up count per method, over the nine instruments.
If live is worse or mixed, STOP and report — the user decided to delete legacy *if the new setup wins*, not
regardless. Deleting the comparison baseline while it still favours the old rules would destroy the evidence.

**Dependency map — VERIFIED 2026-09-13, read before deleting anything.**

Almost none of the "legacy" code is actually unused. Measured by call site:

| symbol | still called from | deletable? |
|---|---|---|
| `find_ict` | `:409` COMBINED/PARTIAL, `:465` COMBINED-BOOK, `:512` legacy ICT branch | **NO** — COMBINED needs it |
| `all_pivots`, `last_pivot` | `:350`, used for every method | **NO** |
| `ict_target`, `is_displacement` | COMBINED block and the legacy ICT branch | **NO** |
| `htf_allows`, `htf_position` | `:362`, `:445` WYCKOFF/COMBINED/PARTIAL, `:495`, and `strategy-runner.py:525` | **NO** |
| `fvg_fill` | **`ict_setups_live` itself** | **NO — the live path calls it** |
| `vtype` | Wyckoff volume typing, `strategy-runner.py:426` | **NO** |
| the legacy pure-ICT `else:` branch in `scan()` | nothing, once `--rules` goes | **yes** |
| `--rules` / `OPTS["rules"]` | only the comparison, now committed as a report | **yes** |

COMBINED is "Wyckoff Spring + ICT confirmation" and takes its ICT half from `find_ict`. Migrating COMBINED to the
live rules is a SEPARATE change with its own evidence requirement — the 2026-09-13 comparison shows COMBINED
byte-identical between the two engines, so there is currently no evidence either way. Do not fold it into this task.

So this task is: migrate `strategy-runner.py`'s ICT setup path off the legacy helpers (which is what unblocks the
pilot), then delete only the two genuinely dead things above.

**Files:**
- Modify: `scripts/strategy-runner.py` (ICT setup path and the HTF gate)
- Modify: `scripts/backtest-methods.py` (delete the legacy block, `--rules`, and the now-unused helpers)
- Modify: `scripts/tests/test_live_rules.py`, `scripts/tests/test_strategy_runner.py`

- [ ] **Step 1: Write the failing test**

Append to `scripts/tests/test_live_rules.py`:

```python
class LegacyEngineIsGone(unittest.TestCase):
    """Once live wins on evidence, the second implementation is dead weight that can silently drift back into
    use. These assertions are what make the removal real rather than a flag nobody sets."""

    def setUp(self):
        self.bt = load("backtest-methods.py")

    def test_rules_flag_is_gone(self):
        self.assertNotIn("rules", self.bt.OPTS)

    def test_the_helpers_other_methods_need_are_still_present(self):
        """COMBINED/PARTIAL/COMBINED-BOOK/WYCKOFF still call these, and ict_setups_live calls fvg_fill.
        Deleting them was in an earlier draft of this plan and would have broken four methods."""
        for name in ("all_pivots", "last_pivot", "find_ict", "fvg_fill", "is_displacement",
                     "ict_target", "htf_allows", "htf_position", "vtype"):
            self.assertTrue(hasattr(self.bt, name), f"{name} was removed but is still used")

    def test_the_helpers_the_wyckoff_side_needs_are_kept(self):
        for name in ("vtype", "walk", "scan", "simulate", "bias_allows"):
            self.assertTrue(hasattr(self.bt, name), f"{name} was removed but is still used")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest scripts/tests/test_live_rules.py -q`
Expected: FAIL — `all_pivots still present`, and `'rules' in OPTS`

- [ ] **Step 3: Migrate `strategy-runner.py` off the legacy helpers**

Replace the ICT setup construction at `strategy-runner.py:375-404` with a `live_rules` read at the tick's last
closed bar, and the gate at `:525` with `bt.bias_allows(bias, side)` where `bias` comes from
`lr.bias_at(candles, last_closed_index, tf)`. Keep every order-lifecycle behaviour untouched: PILOT-01..07 in
`docs/security/2026-09-11-top5-pilot.md` are binding and none of them are about setup detection.

- [ ] **Step 4: Delete the legacy engine**

From `scripts/backtest-methods.py` remove ONLY: the `--rules` argument, `OPTS["rules"]`, and the legacy pure-ICT
`else:` branch inside `scan()`. Keep every helper in the dependency map marked NOT deletable — COMBINED, PARTIAL,
COMBINED-BOOK and WYCKOFF all still call them, and `ict_setups_live` itself calls `fvg_fill`.

Also remove the now-dead `--ict-disp`, `--ict-pd`, `--std-origin` and `--ict-target` switches if they only fed
the deleted code, and delete their paragraphs from the module docstring. Verify with:

```bash
grep -n "ict_disp\|std_origin\|ict_target\|range_target" scripts/backtest-methods.py scripts/strategy-runner.py scripts/rank-setups.py
```

Expected: no hits outside comments describing history.

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest scripts/tests/test_live_rules.py -q`
Expected: PASS

- [ ] **Step 6: Run the whole suite**

Run: `python3 -m pytest scripts/tests/ -q`
Expected: all pass. `test_strategy_runner.py` will need its legacy-shaped assertions updated — do that here, but
do NOT weaken `test_risk_never_above_one_percent_and_notional_capped`, `test_refuses_real_environment`,
`test_refuses_wrong_profile` or `test_refuses_master_off`.

- [ ] **Step 7: Re-run the live backtest to prove nothing moved**

```bash
SYMS=$(python3 -c "import json;print(','.join(json.load(open('docs/architecture/automation-config.json'))['markets']['crypto']['instruments']))")
python3 scripts/backtest-methods.py --tf 5m,15m,1H,4H,1D --symbols "$SYMS" --json /tmp/bt-after-removal.json > /dev/null
python3 -c "
import json
a=json.load(open('/tmp/bt-live.json')); b=json.load(open('/tmp/bt-after-removal.json'))
print('IDENTICAL' if a==b else 'DIFFERS — removal changed behaviour, investigate')"
```

Expected: `IDENTICAL`. Deleting dead code must not move a single number; if it does, something live was still
reading the legacy path.

- [ ] **Step 8: Commit**

```bash
git add scripts/backtest-methods.py scripts/strategy-runner.py scripts/tests/
git commit -m "backtest: delete the legacy ICT engine; one implementation, shared with live"
```

**Not decided here — raise with the user instead.** `scripts/demo-pilot.py` is the `legacy` pilot profile and is
also unused. It is NOT covered by this task: removing it changes the `/automation pilot profile` choices and
PILOT-04 (profile exclusivity) names it explicitly. Report it as a follow-up question rather than deleting it.

---

## Out of scope — do not do these here

- **Do NOT restart the pilot or turn `/automation` on, and do NOT set `layers.pilot on`.** All three locks stay as they are; lifting them is a separate, explicit user decision after the Task 6 comparison has been read.
- **Do NOT re-rank `docs/architecture/pilot-top5.json`.** The user paused top5 on 2026-09-13 ("tạm dừng … sau này có nhu cầu thì sẽ làm lại sau"). The file stays on disk untouched as the record of what was selected under the legacy rules. Re-ranking (`scripts/rank-setups.py --horizons --window 1y`) belongs to whatever session brings the pilot back, because the selection must be made from the rules in force at that time.
- **Do NOT change `demo-pilot.py`.** It is the inactive `legacy` profile. Its pin (`BIAS_METHODS`) and the step-6 characterization tests in `scripts/tests/test_bias_methods.py` stay as they are.
- **Do NOT touch `wyckoff_rules.py` or the WYCKOFF / WYCKOFF-BOOK methods.** They already share code between backtest and runner.
- **Do NOT change the trade dict shape** returned by `scan()`. `simulate()`, the reporting code and `strategy-runner.py` all read it.
- **Do NOT delete the legacy ICT block or `htf_allows`.** `--rules legacy` is what makes the comparison in Task 5 possible.
- **Do NOT add result caching** unless Task 5's timing shows the run is unusable.

## Settled decisions (user, 2026-09-13)

- **`P[tf]["K"]` stays the fill-wait horizon.** How many bars a resting LIMIT is given to fill has NO live
  counterpart — live places the order and `strategy-runner.py` manages it per tick; `ict-scan.py` has no such
  parameter. So this is not a fork where live has a different value, it is a parameter only the backtest needs.
  Keep `P[tf]["K"]` and say so in the Task 6 report.
- **Live defaults everywhere.** Where the backtest has a parameter of its own and live has a different one, take live's. Concretely: `setup_candidate`'s lookback is `max(12, recent * 6)` (`ict-scan.py:466`) via `live_rules.setup_lookback(tf)`, NOT `P[tf]["K"]`. Same rule for any other such fork found during implementation — take live's value and note it in the Task 6 report.
- **`--rules live` is the default**, `legacy` exists only to produce the Task 6 comparison.
- **If live beats legacy in Task 6, delete the legacy engine** — see Task 8.
