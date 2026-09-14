# Collapse to One System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Leave exactly one trading system — `strategy-runner.py` on three horizons (scalping 15m / day 1H / swing 4H), planned R:R ≥ 3, risk 3 %/trade — and delete every parallel, superseded or duplicate arrangement around it.

**Architecture:** Three deletions and one rename, in dependency order. (1) The dual-engine arrangement goes: `demo-pilot.py` and the `execution.pilot_profile` switch that chose between it and `strategy-runner.py`. (2) The two overlapping style vocabularies collapse into one — the ten `STYLE` values (`scalping`/`daytrade`/`1h`/`4h`/`swing` + five `gold-*`) become three horizons shared by both markets, which drops the `1m` (crypto) and `5m`/`1D` (both) scanned timeframes. (3) The before/after evidence docs that compared the old arrangement to the new one are deleted. Nothing about the method-preset switch (`/automation method`, the control panel, all six presets) is touched — the user keeps it.

**Tech Stack:** Python 3.14 stdlib only, `unittest` via `pytest`, bash launchd loops. No new dependencies.

---

## Decisions locked by the user (2026-09-13)

| # | Question | Decision |
|---|---|---|
| 1 | Which engine survives | `strategy-runner.py`. Delete `demo-pilot.py`, delete `execution.pilot_profile` and the `pilot-loop.sh` branching. |
| 2 | Style vocabulary | Collapse to `scalping` / `day` / `swing` only. Delete the `STYLE` timeframe-label map. |
| 3 | Horizon → timeframe | `scalping=15m`, `day=1H`, `swing=4H`. Drops `1m` (crypto), `5m` (cfd) and `1D` (both) from the scanned set. |
| 4 | CFD naming | Shares `scalping`/`day`/`swing`; the `gold-*` prefix is deleted. Markets stay distinguished by the `market` field. |
| 5 | Method presets | **Keep all six, keep the control panel.** Explicitly out of scope. |
| 6 | Superseded docs | Delete. Git history is the archive. |
| 7 | Sequencing | The R:R floor work is already committed as `dc4a475`. This plan is the second, separate commit. |

## Why `1D` can be dropped without losing higher-timeframe context

`PAGE_RUNGS` (`scripts/automation.py:159`) is a **separate** ladder from the scanned timeframes — its comment says `1W` is "fetched for the swing pages, never scanned". Keeping `1D` and `1W` as context-only rungs leaves every surviving horizon a full `ladder()`:

| horizon | entry | structure | bias |
|---|---|---|---|
| scalping | 15m | 1h | 4h |
| day | 1H | 4h | 1D |
| swing | 4H | 1D | 1W |

So `MARKET_TIMEFRAMES` (scanned) shrinks to three per market while `PAGE_RUNGS` (drawable/context) keeps `1D` and `1W`. Verify this holds in Task 2 Step 3 rather than assuming it.

## File structure

**Deleted outright:**
- `scripts/demo-pilot.py` — the legacy engine
- `docs/backtests/2026-09-13-legacy-full-run.md`, `-live-full-run.md`, `-live-rules-vs-legacy.md`, `-stability-cfd-live.md`, `-stability-crypto-live.md`, `-top-setups-live.md` — before/after comparisons of an arrangement that no longer exists

**Modified:**
- `scripts/pilot-loop.sh` — drop profile branching; one engine, one tick period
- `scripts/automation.py` — drop `PILOT_PROFILES`, `pilot_profile`, `STYLE`, `STYLE_MARKET_TF`, `gold-*`; shrink `MARKET_TIMEFRAMES` and `PILOT_MARKETS`
- `scripts/htf_context.py` — `STYLE_TF` / `CONTEXT_STYLE` aliases follow the new vocabulary
- `scripts/check-narrative.py` — reads `CONTEXT_STYLE`
- The six consumers that key off the flat style name and carry no `market` field (found by the symbol survey that
  rewrote Task 2, not in this plan's first draft): `scripts/local-eval-brief.py`, `scripts/build-artifact.py`,
  `scripts/scan-loop.sh`, `scripts/model-read.sh`, `scripts/event-ledger.py`,
  `docs/architecture/artifacts.json` — plus `docs/architecture/schemas/narrative.schema.json` and the twelve
  `integrations/headless/*.md` prompt files whose FILENAMES are style names (four renamed, eight deleted)
- `scripts/rank-setups.py` — `HORIZONS` becomes single-valued
- `scripts/strategy-runner.py` — drop the `pilot_profile != "top5"` gate (there is no other profile)
- `scripts/journal.py`, `scripts/journal_render.py` — drop profile-conditional prose
- `docs/architecture/automation-config.json`, `docs/architecture/schemas/automation-config.schema.json` — drop `pilot_profile`, shrink `timeframes`
- `docs/architecture/SYSTEM-DESIGN.md`, `docs/GETTING-STARTED.md`, `docs/architecture/timeframe-mapping.md` — describe one system
- `config/env.example` — `PILOT_MARKETS=futures`
- Tests: `scripts/tests/test_min_rr_and_risk.py`, `test_bias_methods.py`, `test_instruments_sync.py`, `test_strategy_runner.py`, `test_rank_setups_horizons.py`

**Created:**
- `scripts/tests/test_one_system.py` — the regression net for this collapse: asserts the deleted things stay deleted

---

### Task 1: Delete the legacy engine and the profile switch

**Files:**
- Create: `scripts/tests/test_one_system.py`
- Delete: `scripts/demo-pilot.py`
- Modify: `scripts/pilot-loop.sh:1-40`, `scripts/automation.py:79,182,247-251,581,871-913,1342-1345`, `scripts/strategy-runner.py:179`, `scripts/journal.py:168`, `scripts/journal_render.py:39`, `docs/architecture/automation-config.json`, `docs/architecture/schemas/automation-config.schema.json:70`, `config/env.example:39`
- Modify tests: `scripts/tests/test_min_rr_and_risk.py`, `scripts/tests/test_bias_methods.py`, `scripts/tests/test_instruments_sync.py`, `scripts/tests/test_strategy_runner.py`

- [ ] **Step 1: Write the failing test**

Create `scripts/tests/test_one_system.py`:

```python
"""One system: one engine, one style vocabulary, one risk decision.

User decision 2026-09-13: keep strategy-runner.py on three horizons (scalping 15m / day 1H / swing 4H) at
planned R:R >= 3 and 3 % risk; delete demo-pilot.py, the execution.pilot_profile switch, the ten-value STYLE
map and the gold-* names. These tests exist because every one of those was a SECOND way to express something
the system already expressed once, and the duplicates drifted: the floor drifted (2R vs 3R), the risk ceiling
drifted (1 % vs 3 %), and `scalping` meant 1m in one vocabulary and 15m in the other.

The method-preset switch is deliberately NOT covered here -- all six presets and the control panel stay.
"""
import json, os, re, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(ROOT, "scripts")
CONFIG = os.path.join(ROOT, "docs", "architecture", "automation-config.json")


def sources():
    """Every tracked python/bash source, minus this test file."""
    out = {}
    for d in (SCRIPTS, os.path.join(SCRIPTS, "tests")):
        for fn in sorted(os.listdir(d)):
            if fn.endswith((".py", ".sh")) and fn != "test_one_system.py":
                out[os.path.relpath(os.path.join(d, fn), ROOT)] = open(os.path.join(d, fn), encoding="utf-8").read()
    return out


class LegacyEngineIsGone(unittest.TestCase):
    def test_the_file_does_not_exist(self):
        self.assertFalse(os.path.exists(os.path.join(SCRIPTS, "demo-pilot.py")))

    def test_nothing_executes_it(self):
        """A dangling reference in the loop script is a crash at 3am, not a lint warning."""
        for path, src in sources().items():
            for i, line in enumerate(src.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                self.assertNotIn("demo-pilot.py", line, f"{path}:{i} still references the deleted engine")
                self.assertNotIn("demo_pilot", line, f"{path}:{i} still references the deleted engine")

    def test_the_profile_switch_is_gone(self):
        """Two profiles meant two rule sets on one account; there is one engine now, so a profile key can only
        select 'the engine' or 'nothing at all' -- and the second option is a footgun, not a feature."""
        for path, src in sources().items():
            for i, line in enumerate(src.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                self.assertNotIn("pilot_profile", line, f"{path}:{i} still reads the deleted profile key")

    def test_the_config_carries_no_profile_key(self):
        cfg = json.load(open(CONFIG, encoding="utf-8"))
        self.assertNotIn("pilot_profile", cfg.get("execution", {}))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest scripts/tests/test_one_system.py -q -p no:cacheprovider`
Expected: 4 failures — `test_the_file_does_not_exist` (the file exists), `test_nothing_executes_it` (`pilot-loop.sh:31`), `test_the_profile_switch_is_gone` (`automation.py:79`), `test_the_config_carries_no_profile_key`.

- [ ] **Step 3: Delete the engine**

```bash
git rm scripts/demo-pilot.py
```

- [ ] **Step 4: Rewrite the pilot loop with no branching**

Replace `scripts/pilot-loop.sh` lines 20-38 (the `while` body) with:

```bash
while :; do
  # One engine (user decision 2026-09-13): scripts/strategy-runner.py. There is no profile switch any more --
  # the previous arrangement chose between this and a second, unrelated rule set on the same account, which is
  # how the planned-R:R floor came to differ between the two paths (see commit dc4a475).
  python3 "$ROOT/scripts/strategy-runner.py" --live >> "$PD/loop.log" 2>&1 \
    || echo "tick error $(date -u +%FT%TZ)" >> "$PD/loop.log"
  period="$(python3 "$ROOT/scripts/strategy-runner.py" --tick-seconds 2>/dev/null || echo 1800)"
  sleep "$period"
done
```

Also delete the now-false comments on lines 2, 6 and 8 that name `demo-pilot.py` and the two periods, replacing line 2 with:

```bash
# Runs the pilot every tick-seconds (scripts/strategy-runner.py --tick-seconds: the fastest selected timeframe).
```

- [ ] **Step 5: Strip the profile from automation.py**

Delete line 79 (`PILOT_PROFILES = [...]`). At line 182 change `PILOT_MARKETS = ["spot", "futures"]` to:

```python
PILOT_MARKETS = ["futures"]   # one engine, one venue (user decision 2026-09-13); the spot loop ran the deleted legacy engine
```

In the config template near line 247 delete the `"pilot_profile": "top5",` entry and the `pilot_profile: ...` sentence in the `_note` at line 251. At line 581 delete the `pilot profile: ...` fragment from the status line. In the `on setup` function (lines 871-913) delete the three `cfg["execution"]["pilot_profile"] = "top5"` assignments and drop `; pilot profile = top5` from the line 892 message. Delete the whole `pilot profile` subcommand branch at lines 1342-1345.

- [ ] **Step 6: Drop the profile gate from the runner and the profile prose from the journal**

`scripts/strategy-runner.py:179` — delete the gate:

```python
    # (deleted 2026-09-13) the pilot_profile != "top5" refusal: there is one engine now, so the only thing this
    # key could still express is "run nothing", which layers.pilot already expresses.
```

`scripts/journal.py:168` — replace the conditional with the single engine:

```python
                    f"Nguồn: pilot ({mk}), luật cố định trong `scripts/strategy-runner.py`; không có Confluence Score vì không chạy DecisionAgent.\n\n"
```

`scripts/journal_render.py:39` — delete the `profile = ...` line and every use of `profile` in that function.

- [ ] **Step 7: Drop the key from the config and its schema, and fix the env template**

Remove `"pilot_profile": "top5"` from `execution` in `docs/architecture/automation-config.json`, remove the `pilot_profile` property block at `docs/architecture/schemas/automation-config.schema.json:70` (and from any `required` list that names it), and set `config/env.example:39` to:

```
PILOT_MARKETS=futures
```

- [ ] **Step 8: Remove the tests that protected the deleted engine**

In `scripts/tests/test_min_rr_and_risk.py` delete the whole `DemoPilotGate` class, and in `OneFloorReaderForBothOrderPaths` remove `demo-pilot` from both the `setUp` loads and the two file lists. In `scripts/tests/test_bias_methods.py` delete the `PilotHtfFilter` class (around lines 230-269) and the `demo-pilot.py` mention in the comment at line 88. In `scripts/tests/test_instruments_sync.py` delete the assertion at line 52. In `scripts/tests/test_strategy_runner.py` delete the `pilot_profile` assertions.

- [ ] **Step 9: Run the new test and the full suite**

Run: `python3 -m pytest scripts/tests/test_one_system.py -q -p no:cacheprovider`
Expected: PASS (4 tests).

Run: `python3 -m pytest scripts/tests/ -q -p no:cacheprovider`
Expected: all pass. The count drops from 398 by however many tests Step 8 removed; that is the point, not a regression.

- [ ] **Step 10: Prove the loop still parses and the runner still gates**

Run: `bash -n scripts/pilot-loop.sh && echo "loop syntax OK"`
Expected: `loop syntax OK`

Run: `PYTHONPATH=scripts python3 -c "import importlib.util as u; s=u.spec_from_file_location('sr','scripts/strategy-runner.py'); m=u.module_from_spec(s); s.loader.exec_module(m); print('MIN_RR', m.MIN_RR, '| gate on 2.9R:', m.rr_reason({'r_planned': 2.9}))"`
Expected: `MIN_RR 3.0 | gate on 2.9R: R/R kế hoạch 2.90 < 3.0 tối thiểu`

Run: `python3 scripts/automation.py status`
Expected: exit 0, no `pilot profile` line, `pilot agents` reported for futures only.

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "one-system: delete the legacy engine and the pilot-profile switch"
```

---

### Task 2: Collapse the style vocabulary to three horizons (REWRITTEN 2026-09-13)

**Executed 2026-09-13 as ONE commit (`385f034`), not two.** `scripts/build-artifact.py` resolves
`_auto.TIERS[style]` at MODULE IMPORT time, so the moment 2a rekeys `TIERS` the whole of
`build-artifact.py` raises `KeyError: 'daytrade'` — which `check-narrative.py` imports, which
`test_method_purity.py` imports, so pytest aborted during COLLECTION and ran zero tests. A 2a-only commit
is therefore a broken commit. The 2a/2b split below is kept as the reading order; the commit is single.

**Why this section was rewritten.** The first version of Task 2 scoped itself by line number
(`automation.py:105,119-123,162-164,...`) and listed five files. A symbol-scoped survey found the style names are a
**flat namespace** that six other consumers use as their only key — they have no `market` field, so the first
version's `HORIZON_TF = {scalping, day, swing}` (no market dimension) would have made crypto and cfd collide and
broken `scan-loop.sh`, `model-read.sh`, `build-artifact.py`, `artifacts.json`, `local-eval-brief.py` and the
narrative schema. Scoping by line number is what let two CRITICAL regressions through in Task 1; this section is
scoped by SYMBOL.

**User decision (2026-09-13, asked after the survey):** six market-qualified names. Crypto keeps the bare horizon
word, cfd takes a `cfd-` prefix. `gold-*` and `daytrade` are gone; `1D` and `5m`/`1m` leave the scanned set.

| new style | market | timeframe | replaces | artifact page it inherits | headless prompt |
|---|---|---|---|---|---|
| `scalping` | crypto | 15m | `daytrade` | `46b302c5…` (the 15m page) | `daytrade-*` renamed |
| `day` | crypto | 1h | `1h` | none yet → `PENDING` | none (none existed) |
| `swing` | crypto | 4h | `4h` | none yet → `PENDING` | none (none existed) |
| `cfd-scalping` | cfd | 15m | `gold` | `97773ba6…` (the 15m gold page) | `gold-*` renamed |
| `cfd-day` | cfd | 1h | `gold-1h` | none yet → `PENDING` | none (none existed) |
| `cfd-swing` | cfd | 4h | `gold-4h` | none yet → `PENDING` | none (none existed) |

Retired outright (their timeframe is no longer scanned): crypto `scalping`@1m, crypto `swing`@1D, `gold-scalp`@5m,
`gold-swing`@1D.

**THE HAZARD, stated once because it is the one thing here that can publish wrong content to a real page.** Two
names are being REUSED for a different timeframe: `scalping` moves 1m → 15m and `swing` moves 1D → 4h. Every table
keyed by style name therefore has a stale-value trap, and `docs/architecture/artifacts.json` is the dangerous one:
if key `scalping` keeps the URL it has today (`59f0b15b…`, the 1m page) the publish tick will push 15m content onto
the page the user knows as the 1m scalping page. `scalping` must inherit `46b302c5…` (today's `daytrade`) and the
1m/1D/5m URLs must leave the registry. A test asserts this rather than trusting the edit.

---

#### Task 2a: the vocabulary itself and everything that derives from it

**Symbols (not line numbers) to change in `scripts/automation.py`:** `MARKET_TIMEFRAMES`, `TIMEFRAMES`,
`PAGE_RUNGS`, `STYLE`, `STYLE_MARKET_TF`, `TIERS`, `market_of_style`, `enabled_styles`, the `timeframe`
subcommand's argparse `choices`, and every prose string naming `1m`, `5m`, `gold-scalp` or `daytrade`.

**Files:**
- Modify: `scripts/automation.py`, `scripts/htf_context.py`
- Modify: `docs/architecture/automation-config.json`, `docs/architecture/schemas/automation-config.schema.json`
- Modify: `scripts/tests/test_one_system.py`, `scripts/tests/test_timeframe_ladder.py`, `scripts/tests/test_bias_methods.py`

- [ ] **Step 1: Write the failing test**

Append to `scripts/tests/test_one_system.py`:

```python
HORIZONS = ("scalping", "day", "swing")
HORIZON_TF = {"scalping": "15m", "day": "1h", "swing": "4h"}
STYLES = {("crypto", "15m"): "scalping", ("crypto", "1h"): "day", ("crypto", "4h"): "swing",
          ("cfd", "15m"): "cfd-scalping", ("cfd", "1h"): "cfd-day", ("cfd", "4h"): "cfd-swing"}


class OneStyleVocabulary(unittest.TestCase):
    """Before 2026-09-13 there were two vocabularies: automation.STYLE mapped (market, tf) to ten HAND-WRITTEN
    labels (scalping/daytrade/1h/4h/swing + five gold-*), while rank-setups.HORIZONS mapped three horizon names to
    timeframe SETS. They overlapped and DISAGREED -- `scalping` was 1m in one and 15m in the other, `swing` was 1D
    in one and 4H in the other. Now there is one authored source (HORIZONS + HORIZON_TF) and STYLE is DERIVED from
    it, so a flat style name cannot drift from the horizon it belongs to."""

    def setUp(self):
        import importlib
        self.auto = importlib.import_module("automation")

    def test_horizons_are_the_only_authored_names(self):
        self.assertEqual(tuple(self.auto.HORIZONS), HORIZONS)

    def test_each_horizon_maps_to_exactly_one_timeframe(self):
        self.assertEqual(self.auto.HORIZON_TF, HORIZON_TF)

    def test_style_is_derived_from_the_horizon_table(self):
        """Six flat names, three horizons, two markets -- and each name's horizon half must map back through
        HORIZON_TF to the timeframe its own key carries. A hand-edited STYLE entry fails here."""
        self.assertEqual(self.auto.STYLE, STYLES)
        for (m, tf), style in self.auto.STYLE.items():
            hz = style[4:] if style.startswith("cfd-") else style
            self.assertIn(hz, HORIZONS, f"{style} is not one of the three horizons")
            self.assertEqual(HORIZON_TF[hz], tf, f"{style} claims {tf}, HORIZON_TF says {HORIZON_TF[hz]}")
            self.assertEqual(self.auto.market_of_style(style), m, f"market_of_style({style}) != {m}")

    def test_the_dropped_timeframes_are_not_scanned(self):
        """1m and 5m were entry windows; 1D was the swing entry. All three leave the SCANNED set (decision 3)."""
        for m, tfs in self.auto.MARKET_TIMEFRAMES.items():
            self.assertEqual(tfs, ["15m", "1h", "4h"], f"{m} still scans {tfs}")
        for gone in ("1m", "5m", "1D"):
            self.assertNotIn(gone, self.auto.TIMEFRAMES, f"{gone} is still a selectable timeframe")

    def test_no_gold_prefixed_names_survive(self):
        """The cfd market is distinguished by a `cfd-` prefix now, the way pilot-top5.json uses a market field."""
        for path in sources():
            for i, line in code_lines(path):
                self.assertIsNone(re.search(r'"gold(-[a-z0-9]+)?"', line), f"{path}:{i} keeps a gold-* style name")

    def test_daytrade_is_not_a_name_any_more(self):
        """`daytrade` (15m) and `day` (1H) were two names one keystroke apart for different timeframes."""
        for path in sources():
            for i, line in code_lines(path):
                self.assertNotIn("daytrade", line, f"{path}:{i} keeps the superseded `daytrade` name")

    def test_every_style_still_has_a_full_context_ladder(self):
        """Dropping 1D from the SCANNED set must not leave swing without a bias tier -- PAGE_RUNGS keeps 1D and
        1W as context-only rungs, and this asserts that the distinction actually holds."""
        for style in STYLES.values():
            tiers = self.auto.TIERS[style]
            self.assertIsNotNone(tiers["structure"], f"{style} lost its structure tier")
            self.assertIsNotNone(tiers["bias"], f"{style} lost its bias tier")

    def test_a_tier_never_points_at_the_other_market(self):
        """TIERS is built per market; a crypto style's structure tier must not resolve to a cfd style."""
        for (m, _tf), style in self.auto.STYLE.items():
            for name in ("structure", "bias"):
                t = self.auto.TIERS[style][name]
                if t and t["style"]:
                    self.assertEqual(self.auto.market_of_style(t["style"]), m,
                                     f"{style}.{name} points at {t['style']}, the other market")
```

`code_lines(rel)` already exists in this file — the `ast`-based helper that strips comments AND docstrings, so
these two source scans do not ban their own explanations. Use it, not a `startswith("#")` filter.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=scripts python3 -m pytest scripts/tests/test_one_system.py::OneStyleVocabulary -q -p no:cacheprovider`
Expected: FAIL on `test_horizons_are_the_only_authored_names` (no `HORIZONS` attribute), `test_each_horizon_maps_to_exactly_one_timeframe`, `test_style_is_derived_from_the_horizon_table`, `test_the_dropped_timeframes_are_not_scanned`, `test_no_gold_prefixed_names_survive`, `test_daytrade_is_not_a_name_any_more`.

- [ ] **Step 3: One authored vocabulary, STYLE derived from it**

Replace the hand-written `STYLE` table and its comment with:

```python
# ONE authored style vocabulary (user decision 2026-09-13): three horizons, one timeframe each, shared by both
# markets. The flat (market, timeframe) -> name table below is DERIVED from it, not authored a second time -- it
# exists because scan-loop.sh, model-read.sh, build-artifact.py, artifacts.json and local-eval-brief.py key off a
# single flat name and carry no market field. Crypto keeps the bare horizon word; cfd takes a `cfd-` prefix.
# This replaces the ten hand-written labels (scalping/daytrade/1h/4h/swing + five gold-*), which disagreed with
# rank-setups.HORIZONS about what `scalping` and `swing` meant (1m vs 15m, 1D vs 4H).
HORIZONS = ["scalping", "day", "swing"]
HORIZON_TF = {"scalping": "15m", "day": "1h", "swing": "4h"}
TF_HORIZON = {tf: hz for hz, tf in HORIZON_TF.items()}
STYLE_PREFIX = {"crypto": "", "cfd": "cfd-"}
STYLE = {(m, HORIZON_TF[h]): STYLE_PREFIX[m] + h for m in MARKETS for h in HORIZONS}
STYLE_MARKET_TF = {v: k for k, v in STYLE.items()}
```

`STYLE` must be defined AFTER `MARKETS` (it iterates it). Keep `STYLE` and `STYLE_MARKET_TF` as names: every
consumer of the flat namespace reads them, and keeping them derived is what makes one vocabulary true instead of
merely renamed.

Shrink the scanned set and the selectable list:

```python
# One scanned set for both markets (user decision 2026-09-13). 1m and 5m were the two scalping entry windows and
# 1D was the swing entry; all three leave the scanned set when the horizons become 15m/1h/4h. 1D and 1W stay in
# PAGE_RUNGS below as context-only rungs, which is what keeps swing a full ladder.
MARKET_TIMEFRAMES = {"crypto": ["15m", "1h", "4h"], "cfd": ["15m", "1h", "4h"]}
TIMEFRAMES = ["15m", "1h", "4h"]
```

`PAGE_RUNGS` drops the two retired entry rungs and keeps the context rungs:

```python
PAGE_RUNGS = {"crypto": ["15m", "1h", "4h", "1D", "1W"], "cfd": ["15m", "1h", "4h", "1D", "1W"]}
```

Dropping `1m`/`5m` from `PAGE_RUNGS` cannot change any ladder, because `next_rung` only ever looks upward from the
entry timeframe — Step 1's ladder test is what proves it.

Rebuild `TIERS` per market so a tier can never resolve to the other market's style:

```python
TIERS = {}
for (_mkt, _tf), _style in STYLE.items():
    _s, _b = ladder(_tf, PAGE_RUNGS[_mkt])
    TIERS[_style] = {k: ({"tf": t, "style": STYLE.get((_mkt, t))} if t else None)
                     for k, t in (("structure", _s), ("bias", _b))}
```

(That is the existing loop unchanged — it already keys `STYLE.get((_mkt, t))` by the same market. Verify it, do not
rewrite it.)

- [ ] **Step 4: The one function whose logic actually changes**

`market_of_style` keyed off the `gold` prefix. It becomes:

```python
def market_of_style(style):
    """Which market's dimension flags a chart style obeys. `cfd-` prefixed styles are the CFD market; everything
    else is crypto. One definition — build-artifact.py and htf_context.py both read it here rather than
    re-deriving it. (Before 2026-09-13 the prefix was `gold`, which named the instrument, not the market.)"""
    return "cfd" if (style or "").startswith("cfd-") else "crypto"
```

`enabled_styles(cfg=None)` — **keep the name, the signature and the `load(require_readable=False)` fallback**
(`scan-loop.sh` and `local-eval-brief.py` call it with no argument). Its body already iterates `STYLE.items()` and
returns names in `STYLE.values()` order, which is now the derived six. Re-read it and change it only if it names a
retired style; do not rewrite a working body.

Then check every consumer of the flat list still gets what it expects:

Run: `grep -rn "enabled_styles\|market_of_style\|STYLE_MARKET_TF" scripts/ | grep -v __pycache__`
Expected: every hit either iterates the value or passes it to something that accepts a style name. Fix any caller
that compares against a literal `"daytrade"`, `"gold"`, `"gold-scalp"`, `"1h"`-as-a-style or `"gold-swing"`.

- [ ] **Step 5: The prose that names retired timeframes**

These strings assert facts that stop being true. Find them by grep, not by line number:

Run: `grep -n '1m\|5m\|1D\|gold\|daytrade\|chart style' scripts/automation.py`

Each hit is one of: (a) the module docstring's description of the vocabulary, (b) the `MARKET_TIMEFRAMES` comment
about the MT5 export, (c) the `cmd_preset` loop comment listing "scalping (1m/5m), day (15m), 1h/4h, swing (1D)",
(d) the `skipped_msgs` line "cfd timeframe 1m does not exist -- CFD scalping runs on 5m (gold-scalp)…", (e) the
`SCAN_WINDOW` table. Rewrite (a)-(d) to the new vocabulary. **Leave `SCAN_WINDOW` alone** — `scan-loop.sh` reads it
and its `1m`/`5m`/`1D` rows are harmless unused rows; deleting them is Task 2b's call after its own grep, not a
guess here.

The `timeframe` subcommand's argparse `choices` must be the new `TIMEFRAMES`. Find it:

Run: `grep -n 'add_parser("timeframe"\|choices=TIMEFRAMES\|choices=\[.*1m' scripts/automation.py`
Expected: the choices list resolves to `["15m", "1h", "4h"]`. A retired timeframe must be a usage error (exit 1),
not a silent no-op — that is the same failure mode as the `pilot profile top5` bug Task 1 closed.

- [ ] **Step 6: Follow through in htf_context.py**

`scripts/htf_context.py` derives `STYLE_TF` from `_auto.STYLE`:

```python
STYLE_TF = {v: k[1] for k, v in _auto.STYLE.items()}   # style -> timeframe label as /automation spells it
```

That line needs no edit — it is already derived. Confirm by running the checks in Step 8 rather than assuming, and
confirm `CONTEXT_STYLE` still resolves (it is built from `TIERS`, which Step 3 rebuilt).

- [ ] **Step 7: Shrink the scanned timeframes in the live config and both schemas**

`docs/architecture/automation-config.json` — both markets' `timeframes` read exactly:

```json
   "timeframes": { "15m": true, "1h": true, "4h": true }
```

`docs/architecture/schemas/automation-config.schema.json` — the crypto and cfd `timeframes` property shapes and
their two `description` strings both enumerate the retired timeframes and the retired style names. Rewrite both to
the six new names. The crypto description currently claims the style names are "the vocabulary of
scripts/local-eval-brief.py's TF map, scripts/scan-loop.sh and scripts/patch-arrays.py's STYLES -- never rename
one": `patch-arrays.py` no longer exists (the headless prompts call it "retired"), so drop that reference, and the
"never rename one" clause is now false — this task renames them. Say instead that the names are derived from
`automation.HORIZON_TF` and that `docs/architecture/artifacts.json` keys off them.

- [ ] **Step 8: Run the tests and the real commands**

Run: `PYTHONPATH=scripts python3 -m pytest scripts/tests/test_one_system.py -q -p no:cacheprovider`
Expected: PASS.

Run: `python3 -m pytest scripts/tests/ -q -p no:cacheprovider > /tmp/t2a.log 2>&1; echo "EXIT=$?"; tail -30 /tmp/t2a.log`
Expected: `EXIT=0`. Check the exit code directly — piping into `tail` makes `$?` the pipe's, which is how a red
suite got committed earlier in this plan. `test_timeframe_ladder.py` asserts the ten-style ladder table and
`CONTEXT_STYLE["gold-scalp"]`; `test_bias_methods.py` asserts `engaged_methods("daytrade", …)` and
`("gold-scalp", …)`. Update them to the new vocabulary — read each failure before changing it, and do not delete a
case wholesale.

Run: `python3 scripts/automation.py status`
Expected: exit 0; crypto and cfd each list three timeframes, and the styles line reads `scalping, day, swing` for
crypto and `cfd-scalping, cfd-day, cfd-swing` for cfd.

Run: `python3 scripts/check-narrative.py --help`
Expected: exit 0 (proves `CONTEXT_STYLE` still resolves).

Run: `python3 scripts/automation.py timeframe 1D off --market crypto`
Expected: exit 1, a usage error naming the valid choices — NOT exit 0.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "one-system: one authored style vocabulary -- three horizons, six derived names"
```

---

#### Task 2b: the six consumers that key off the flat style name

**Symbols to change:** `TF` (`local-eval-brief.py`), `STYLES` + `TF_SPEC` use (`build-artifact.py`), the `styles`
object (`artifacts.json`), `AUTO_STYLES` + `run_style` + `model_read` calls (`scan-loop.sh`), the interval `case`
(`model-read.sh`), `STYLE_TF` use (`event-ledger.py`), the `style` enum (`narrative.schema.json`), and the twelve
`integrations/headless/*.md` filenames.

**Files:**
- Modify: `scripts/local-eval-brief.py`, `scripts/build-artifact.py`, `scripts/scan-loop.sh`,
  `scripts/model-read.sh`, `scripts/event-ledger.py`
- Modify: `docs/architecture/artifacts.json`, `docs/architecture/schemas/narrative.schema.json`
- Rename: `integrations/headless/daytrade-local-read.md` → `scalping-local-read.md`,
  `daytrade-daily-full.md` → `scalping-daily-full.md`, `gold-local-read.md` → `cfd-scalping-local-read.md`,
  `gold-daily-full.md` → `cfd-scalping-daily-full.md` (use `git mv`)
- Delete: `integrations/headless/scalping-local-read.md` and `scalping-daily-full.md` **as they exist today** (the
  1m pair), `swing-local-read.md`, `swing-daily-full.md` (1D), `gold-scalp-local-read.md`,
  `gold-scalp-daily-full.md` (5m), `gold-swing-local-read.md`, `gold-swing-daily-full.md` (1D)
- Modify: `scripts/tests/test_scan_loop.py`, `scripts/tests/test_build_artifact.py`, `scripts/tests/test_one_system.py`

**Rename order matters.** The 1m pair currently occupies the filenames the 15m pair must take. Delete the 1m pair
FIRST, then `git mv` the `daytrade` pair onto those names, or git will refuse / clobber. The same is not true for
`gold-*` → `cfd-scalping-*` (no collision).

- [ ] **Step 1: Write the failing test**

Append to `scripts/tests/test_one_system.py`:

```python
ARTIFACTS = os.path.join(ROOT, "docs", "architecture", "artifacts.json")
RETIRED_URLS = {                       # style -> the page that style USED to publish, before the 2026-09-13 collapse
    "scalping@1m": "59f0b15b-9d2c-4ac7-b15f-f630ae4a1c49",
    "swing@1D": "c5cb9060-4e2a-4a53-be8c-f4c911c28961",
    "gold-scalp@5m": "7238cd92-2b73-49c9-819f-02edba87018d",
    "gold-swing@1D": "7013f87b-0ee2-43c8-9372-7bb6d929d326",
}


class FlatStyleConsumersFollowTheVocabulary(unittest.TestCase):
    """Six consumers key off the flat style name and carry no market field. Two names were REUSED for a different
    timeframe (scalping 1m -> 15m, swing 1D -> 4h), so every one of these tables had a stale-value trap."""

    def setUp(self):
        import importlib
        self.auto = importlib.import_module("automation")
        with open(ARTIFACTS, encoding="utf-8") as f:
            self.artifacts = json.load(f)["styles"]

    def test_every_style_has_exactly_one_artifact_entry(self):
        self.assertEqual(sorted(self.artifacts), sorted(self.auto.STYLE.values()))

    def test_no_reused_name_inherited_a_retired_page(self):
        """THE hazard: `scalping` means 15m now. If its url were still the 1m page's, the publish tick would push
        15m content onto the page the user knows as the 1m scalping page."""
        for style, entry in self.artifacts.items():
            for what, uid in RETIRED_URLS.items():
                self.assertNotIn(uid, entry.get("url", ""),
                                 f"{style} inherited the retired {what} page")

    def test_scalping_inherited_the_fifteen_minute_page(self):
        self.assertIn("46b302c5", self.artifacts["scalping"]["url"])
        self.assertIn("97773ba6", self.artifacts["cfd-scalping"]["url"])

    def test_styles_with_no_page_yet_are_pending_not_wrong(self):
        for style in ("day", "swing", "cfd-day", "cfd-swing"):
            self.assertEqual(self.artifacts[style]["url"], "PENDING",
                             f"{style} has no page yet; the registry's own convention is PENDING")

    def test_local_eval_brief_covers_exactly_the_six_styles(self):
        import importlib
        self.assertEqual(sorted(importlib.import_module("local-eval-brief".replace("-", "_")).TF),
                         sorted(self.auto.STYLE.values()))

    def test_build_artifact_covers_exactly_the_six_styles(self):
        import importlib
        self.assertEqual(sorted(importlib.import_module("build-artifact".replace("-", "_")).STYLES),
                         sorted(self.auto.STYLE.values()))

    def test_every_headless_prompt_names_a_live_style(self):
        """A prompt file for a retired style is a cron pointing at nothing: model-read.sh exits 2 on a missing
        prompt, but a SURVIVING prompt for a deleted style would run a read no page consumes."""
        live = set(self.auto.STYLE.values())
        for fn in sorted(os.listdir(os.path.join(ROOT, "integrations", "headless"))):
            style = re.sub(r"-(local-read|daily-full)\.md$", "", fn)
            self.assertIn(style, live, f"integrations/headless/{fn} names a retired style")

    def test_scan_loop_default_styles_are_the_live_ones(self):
        src = open(os.path.join(ROOT, "scripts", "scan-loop.sh"), encoding="utf-8").read()
        m = re.search(r'AUTO_STYLES="\$\{AUTO_STYLES:-([^}"]*)\}"', src)
        self.assertIsNotNone(m, "AUTO_STYLES default not found")
        self.assertEqual(sorted(m.group(1).split(",")), sorted(self.auto.STYLE.values()))

    def test_narrative_schema_enumerates_the_six(self):
        with open(os.path.join(ROOT, "docs", "architecture", "schemas", "narrative.schema.json"),
                  encoding="utf-8") as f:
            enum = json.load(f)["properties"]["style"]["enum"]
        self.assertEqual(sorted(enum), sorted(self.auto.STYLE.values()))
```

If `sources()` / `code_lines()` in this file do not already import `json` or expose `ROOT`, add what is missing at
the top of the file rather than inlining a second path constant.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=scripts python3 -m pytest scripts/tests/test_one_system.py::FlatStyleConsumersFollowTheVocabulary -q -p no:cacheprovider`
Expected: FAIL on every test in the class.

- [ ] **Step 3: `local-eval-brief.py` — the (timeframe, window) table**

`TF` maps style → (timeframe label, bar count). Keep each surviving style's window; drop the retired rows:

```python
TF = {"scalping": ("15m", 288), "day": ("1H", 240), "swing": ("4H", 180),
      "cfd-scalping": ("15m", 288), "cfd-day": ("1H", 240), "cfd-swing": ("4H", 180)}
```

The window numbers are the ones those timeframes already used (15m→288, 1H→240, 4H→180), so no window changes
size. The comment above `TF` explains gold* = XAUUSD via the MT5 bridge — reword it for the `cfd-` prefix.

Then fix the symbol default, which keyed off the `gold` prefix:

Run: `grep -n 'startswith("gold")\|a.symbols' scripts/local-eval-brief.py`
Expected: one site defaulting `a.symbols` by prefix. It must use `_auto.market_of_style(a.style) == "cfd"`, not a
second prefix test — `market_of_style` is the one definition (Task 2a Step 4).

- [ ] **Step 4: `build-artifact.py` — the page registry**

`STYLES` has ten entries built by `_style(tf, syms, name, kz)`. It becomes six. `kz` is whether killzones apply;
keep each timeframe's existing answer (15m True, 1H True, 4H False):

```python
STYLES = {
    "scalping":     _style("15m", CRYPTO, "Crypto Scalping", True),
    "day":          _style("1H",  CRYPTO, "Crypto Day", True),
    "swing":        _style("4H",  CRYPTO, "Crypto Swing", False),
    "cfd-scalping": _style("15m", GOLD,   "CFD Scalping", True),
    "cfd-day":      _style("1H",  GOLD,   "CFD Day", True),
    "cfd-swing":    _style("4H",  GOLD,   "CFD Swing", False),
}
```

The module docstring's `style:` line lists the ten old names — rewrite it to the six. The `_S["tiers"]` loop below
reads `_auto.TIERS[_st]`, which Task 2a rebuilt; it needs no edit, but the run in Step 9 must prove it.

- [ ] **Step 5: `artifacts.json` — remap the URLs, do not just rename the keys**

Six entries, in `STYLE.values()` order. `scalping` takes the URL and `out` path of today's `daytrade`;
`cfd-scalping` takes today's `gold`. The four styles with no page yet get `"url": "PENDING"` (the registry's own
documented convention) and an `out` path named after the new style. The four retired URLs
(`59f0b15b…`, `c5cb9060…`, `7238cd92…`, `7013f87b…`) must not appear anywhere in the file.

```json
 "styles": {
  "scalping":     { "url": "https://claude.ai/code/artifact/46b302c5-3a72-45f4-89d3-0a7eef282453", "out": "data/live/.vi-scalping-live.html", "favicon": "⚡" },
  "day":          { "url": "PENDING", "out": "data/live/.vi-day-live.html", "favicon": "⚡" },
  "swing":        { "url": "PENDING", "out": "data/live/.vi-swing-live.html", "favicon": "⚡" },
  "cfd-scalping": { "url": "https://claude.ai/code/artifact/97773ba6-6903-412d-99dd-25fc33c690bb", "out": "data/live/.vi-cfd-scalping-live.html", "favicon": "⚡" },
  "cfd-day":      { "url": "PENDING", "out": "data/live/.vi-cfd-day-live.html", "favicon": "⚡" },
  "cfd-swing":    { "url": "PENDING", "out": "data/live/.vi-cfd-swing-live.html", "favicon": "⚡" }
 }
```

Match the file's existing indentation and key order style rather than this compact form. Update `_comment` if it
names a retired style. Do NOT publish anything — this task only edits the registry.

- [ ] **Step 6: `scan-loop.sh` — the schedule**

`AUTO_STYLES` default and every `run_style` / `model_read` call name styles. The old file ran nine `run_style`
calls across five timeframes plus a `FORCE=all` branch that repeats them. The new schedule has three timeframes ×
two markets:

- `AUTO_STYLES="${AUTO_STYLES:-scalping,day,swing,cfd-scalping,cfd-day,cfd-swing}"`
- delete the `5m` branch (`*1|*6` → `gold-scalp`) and the `1D` branch (`swing` / `gold-swing`) outright
- `15m` branch: `run_style 15m scalping …; run_style 15m cfd-scalping … "$AUTO_CFD"`
- `1H` branch: `run_style 1H day …; run_style 1H cfd-day … "$AUTO_CFD"`
- `4H` branch: `run_style 4H swing …; run_style 4H cfd-swing … "$AUTO_CFD"`
- the `1W` fetch on the old `1D` branch is **swing context and must survive** — move it to the `4H` branch, keeping
  its comment (`1W = swing context chart only, not scanned`). Losing it would leave swing's bias tier undrawable.
- the daily `model_read` list becomes `scalping cfd-scalping` only — those are the two styles that still have a
  prompt pair after Step 8. Do not list a style whose prompt was deleted.
- the `FORCE=all` branch: the same six `run_style` calls, no retired ones

`SCANWIN_BARS_5m` / `SCANWIN_RECENT_5m` / `SCANWIN_BARS_1D` / `SCANWIN_RECENT_1D` become unread. Grep before
deciding whether to delete them:

Run: `grep -rn 'SCANWIN_BARS_5m\|SCANWIN_RECENT_5m\|SCANWIN_BARS_1D\|SCANWIN_RECENT_1D\|SCAN_WINDOW' scripts/ | grep -v __pycache__`
If nothing outside `scan-loop.sh` and `automation.py`'s `SCAN_WINDOW` reads them, drop the `1m`/`5m`/`1D` rows from
`SCAN_WINDOW` too and say so in its comment. If something else reads them, leave both alone and note why.

- [ ] **Step 7: `model-read.sh` — the interval table**

The `case "$STYLE" in` line maps style → `MODEL_READ_INTERVAL`. It becomes the three horizons × two markets, and
the retired names go:

```bash
    case "$STYLE" in scalping|cfd-scalping) MODEL_READ_INTERVAL=900 ;; day|cfd-day) MODEL_READ_INTERVAL=3600 ;; swing|cfd-swing) MODEL_READ_INTERVAL=14400 ;; *) MODEL_READ_INTERVAL=21600 ;; esac
```

15m keeps the 900 s that `daytrade` had, 1H keeps 3600, 4H keeps 14400 — no cadence changes. Line 45's
`if [ "$STYLE" = scalping ] && [ "$KIND" = local ]` special case was written for the 1m style: read it, decide
whether it still applies at 15m, and say which in the commit message. Do not leave it unexamined.

- [ ] **Step 8: the headless prompt files**

Delete the 1m `scalping-*`, 1D `swing-*`, 5m `gold-scalp-*` and 1D `gold-swing-*` pairs. Then `git mv` the
`daytrade-*` pair to `scalping-*` and the `gold-*` pair to `cfd-scalping-*` (deletes first — see the note above the
steps). Inside the two surviving pairs, replace every occurrence of the old style token with the new one: the
`local-eval-brief.py <style>`, `check-model-prose.py <style>` and `data/live/prelim/<style>.<SYM>.model.html`
arguments all carry it. **Do not change the artifact URL inside a prompt** — `46b302c5…` and `97773ba6…` are the
pages those reads already feed, and they are the same pages Step 5 assigns to the new names. Do not rewrite any
trading instruction, window size or citation; this is a rename, not an authoring pass.

- [ ] **Step 9: `event-ledger.py` and `narrative.schema.json`**

`scripts/event-ledger.py` maps `{"1h": "1H", "4h": "4H"}` over `htf.STYLE_TF.get(style)`. `STYLE_TF` now yields
`15m`/`1h`/`4h` only, so the map still covers what it must — confirm by reading it, and extend the map only if a
surviving timeframe would fall through.

`docs/architecture/schemas/narrative.schema.json` — the `style` enum lists the ten old names; replace with the six.
Its `description` for the higher-timeframe chart says "e.g. 4H×180 for daytrade" — reword to a live style.

- [ ] **Step 10: Run the tests and the real commands**

Run: `PYTHONPATH=scripts python3 -m pytest scripts/tests/test_one_system.py -q -p no:cacheprovider`
Expected: PASS.

Run: `python3 -m pytest scripts/tests/ -q -p no:cacheprovider > /tmp/t2b.log 2>&1; echo "EXIT=$?"; tail -30 /tmp/t2b.log`
Expected: `EXIT=0`. Check `$?` directly, not through a pipe. `test_scan_loop.py` writes an `AUTO_STYLES` fixture
and `test_build_artifact.py` builds the `daytrade` page — both need the new names.

Run: `python3 scripts/local-eval-brief.py scalping --bars 10 2>&1 | head -5`
Expected: it runs or fails only for missing candle data — not with a `KeyError` on the style name.

Run: `bash -n scripts/scan-loop.sh && bash -n scripts/model-read.sh`
Expected: exit 0 from both (syntax only; do not execute the loops).

Run: `python3 -c "import json;d=json.load(open('docs/architecture/artifacts.json'));print(sorted(d['styles']))"`
Expected: the six new names.

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "one-system: the flat style consumers follow the one vocabulary"
```

---

### Task 3: Make the horizon→timeframe mapping single-valued in rank-setups

**Symbols to change** (not line numbers — the same symbol survey that rewrote Task 2 found two sites this
task's first draft missed): `HORIZONS`, `CFD_TFS`, and the membership tests that read them.

**Files:**
- Modify: `scripts/rank-setups.py` — `HORIZONS` (single-valued), `CFD_TFS`, and the table note naming `5m`
- Modify: `scripts/tests/test_rank_setups_horizons.py`

Two extra items, both of the failure classes this plan has already been bitten by:

- `CFD_TFS = {"5m", "15m", "30m", "1H", "2H", "4H", "1D"}` is a SECOND stale timeframe table naming four
  retired rungs. It is read at three sites, two of them the non-horizons modes, so it does not disappear
  with the horizons loop. Shrink it to `{"15m", "1H", "4H"}`. Behaviour does not change today (it is
  currently a superset of the live set) — which is precisely why it would have rotted unnoticed.
- `test_rank_setups_horizons.py` tests `r.get("tf") in RS.HORIZONS[hz]`. Once `HORIZONS[hz]` is a STRING
  that becomes a substring test: `"15m" in "15m"` is True, so the test keeps passing while asserting
  nothing — and `"5m" in "15m"` is ALSO True, so it would accept a retired timeframe. Make it `==`. This
  is the fourth vacuous-pass in this plan; watch it fail against the old value before trusting it.
- The Vietnamese note under the ranking table says "scalping 5m/15m bị phí và trượt giá ăn nhiều nhất".
  `5m` is retired; scalping is 15m only. Reword.

- [ ] **Step 1: Write the failing test**

Append to `scripts/tests/test_one_system.py`:

```python
class RankSetupsAgreesWithTheOneVocabulary(unittest.TestCase):
    """rank-setups.HORIZONS held timeframe SETS ({"5m","15m"}, {"30m","1H","2H"}, {"4H","1D"}) that ranged over
    timeframes the scanner no longer runs. It writes pilot-top5.json, which selects what the live engine trades,
    so a horizon that can select a 30m setup the scanner never scans is a selection nothing can execute."""

    def setUp(self):
        import importlib
        self.auto = importlib.import_module("automation")
        self.rank = _load_script("rank-setups.py", "rank")

    def test_one_timeframe_per_horizon(self):
        self.assertEqual(self.rank.HORIZONS, {"scalping": "15m", "day": "1H", "swing": "4H"})

    def test_it_agrees_with_automation_case_insensitively(self):
        """rank-setups spells timeframes 1H/4H, /automation spells them 1h/4h -- same rungs, different case."""
        self.assertEqual({h: tf.lower() for h, tf in self.rank.HORIZONS.items()},
                         {h: tf.lower() for h, tf in self.auto.HORIZON_TF.items()})
```

Add this helper next to `sources()` in the same file:

```python
def _load_script(fname, modname):
    import importlib.util
    spec = importlib.util.spec_from_file_location(modname, os.path.join(SCRIPTS, fname))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=scripts python3 -m pytest scripts/tests/test_one_system.py::RankSetupsAgreesWithTheOneVocabulary -q -p no:cacheprovider`
Expected: FAIL — `{'scalping': {'5m','15m'}, ...} != {'scalping': '15m', ...}`.

- [ ] **Step 3: Make the mapping single-valued**

`scripts/rank-setups.py:40` becomes:

```python
# One timeframe per horizon (user decision 2026-09-13), matching automation.HORIZON_TF. Was a SET per horizon,
# which could select a 30m or 1D setup the scanner does not run -- a selection nothing could execute.
HORIZONS = {"scalping": "15m", "day": "1H", "swing": "4H"}
```

At line 212 replace `for hz, tfs in HORIZONS.items():` with:

```python
    for hz, tf in HORIZONS.items():
```

and inside that loop replace every membership test of the form `row["tf"] in tfs` with `row["tf"] == tf`. Read the loop body before editing — do not blind-replace, the variable may be spelled differently.

- [ ] **Step 4: Run the tests**

Run: `PYTHONPATH=scripts python3 -m pytest scripts/tests/test_one_system.py scripts/tests/test_rank_setups_horizons.py -q -p no:cacheprovider`
Expected: PASS. Update `test_rank_setups_horizons.py` where it assumes a set.

- [ ] **Step 5: Re-rank the selection under the new mapping**

`docs/architecture/pilot-top5.json` currently holds a swing row selected at `4H` and scalping rows at `15m`, which already match — but it was ranked while `day` could mean 30m/1H/2H. Re-run the ranking so the stored selection is reproducible from the current code:

Run: `python3 scripts/rank-setups.py --horizons --window 1y`
Expected: writes `docs/architecture/pilot-top5.json`; the printed table lists exactly one timeframe per horizon.

If the file's `setups` list changes membership, say so in the commit message — it is a change to what the pilot would trade, not a refactor.

**Executed 2026-09-14.** Two corrections to this step, from the source rather than the plan:

- That command does **not** write the selection. `--select` defaults to `None` and `main_horizons()` only
  writes under `if a.select:`, so the bare command prints the table and writes nothing. The write path is
  `--select docs/architecture/pilot-top5.json`, which is how `automation.py` invokes it. Both were run: the
  bare command for the printed table, the `--select` form to re-rank the stored selection.
- `setups` membership did **not** change: the same six ids in the same ranks, and every `backtest` number
  byte-identical. Only `generated` (2026-09-13 → 2026-09-14) and `source` moved. The `source` move is the
  find worth recording — the committed file cited a per-session scratchpad temp path
  (`../../../../private/tmp/claude-502/.../scratchpad/stab/crypto-live.json`) that no longer exists, so the
  stored selection was not reproducible from anything on disk. Re-ranking off the repo's own
  `data/history/stability/{crypto,cfd}-live.json` replaces it with a reachable path, which is what "the
  stored selection is reproducible from the current code" asks for.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "one-system: one timeframe per horizon in the setup ranking"
```

---

### Task 4: Delete the superseded before/after evidence docs

**Files:**
- Delete: six files under `docs/backtests/`
- Modify: `scripts/tests/test_one_system.py`

- [ ] **Step 1: Write the failing test**

Append to `scripts/tests/test_one_system.py`:

```python
class NoBeforeAfterDocs(unittest.TestCase):
    """These compared the legacy arrangement to the live one. The legacy arrangement is deleted, so they
    describe a system that cannot be run -- and a reader cannot tell which file is the current state. Git
    history keeps them if the comparison is ever needed again."""

    SUPERSEDED = ("2026-09-13-legacy-full-run.md", "2026-09-13-live-full-run.md",
                  "2026-09-13-live-rules-vs-legacy.md", "2026-09-13-stability-cfd-live.md",
                  "2026-09-13-stability-crypto-live.md", "2026-09-13-top-setups-live.md")

    def test_they_are_deleted(self):
        for fn in self.SUPERSEDED:
            self.assertFalse(os.path.exists(os.path.join(ROOT, "docs", "backtests", fn)), f"{fn} still present")

    def test_nothing_links_to_them(self):
        """A dead evidence link is worse than no link: it reads as a citation."""
        for dirpath, _, files in os.walk(os.path.join(ROOT, "docs")):
            for fn in files:
                if not fn.endswith(".md"):
                    continue
                p = os.path.join(dirpath, fn)
                src = open(p, encoding="utf-8").read()
                for dead in self.SUPERSEDED:
                    self.assertNotIn(dead, src, f"{os.path.relpath(p, ROOT)} links to deleted {dead}")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest scripts/tests/test_one_system.py::NoBeforeAfterDocs -q -p no:cacheprovider`
Expected: FAIL on `test_they_are_deleted` (all six exist).

- [ ] **Step 3: Delete them**

```bash
git rm docs/backtests/2026-09-13-legacy-full-run.md \
       docs/backtests/2026-09-13-live-full-run.md \
       docs/backtests/2026-09-13-live-rules-vs-legacy.md \
       docs/backtests/2026-09-13-stability-cfd-live.md \
       docs/backtests/2026-09-13-stability-crypto-live.md \
       docs/backtests/2026-09-13-top-setups-live.md
```

- [ ] **Step 4: Fix whatever linked to them**

Run: `python3 -m pytest scripts/tests/test_one_system.py::NoBeforeAfterDocs -q -p no:cacheprovider`
Expected: if `test_nothing_links_to_them` fails, it names the file and the dead link. Rewrite each citation to point at the surviving evidence — `docs/backtests/2026-09-13-rr-floor-and-risk.md` for the floor/risk decision, `docs/backtests/2026-09-13-scalping-15m-per-pair-rr2-rr3.md` for the per-pair and per-floor measurements — or delete the sentence if the claim was only about the legacy comparison. Do not leave a bare "(deleted)".

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "one-system: delete the before/after evidence docs"
```

---

### Task 5: Make the architecture docs describe one system

**Files:**
- Modify: `docs/architecture/SYSTEM-DESIGN.md`, `docs/GETTING-STARTED.md`, `docs/architecture/timeframe-mapping.md`, `docs/security/2026-09-11-top5-pilot.md`, `docs/plans/2026-09-13-unify-backtest-with-live-rules.md`
- Modify: `docs/architecture/data-sources.md`, `docs/architecture/mt5-bridge.md` — the residue check after the
  Task 2 commit found retired style names in these two as well, and they appear in NO other task's file list.
  They are the last two places a reader can still find `gold-scalp` / `daytrade` described as live.

- [ ] **Step 1: Find every stale claim**

Run: `grep -rn "demo-pilot\|pilot_profile\|daytrade\|gold-scalp\|gold-swing\|legacy" docs/ --include=*.md | grep -v docs/plans/2026-09-13-collapse-to-one-system.md`
Expected: a list. Each hit is either (a) a description of the current system that is now false, or (b) a historical record that is still true of its own date.

- [ ] **Step 2: Rewrite the (a) hits, date-stamp the (b) hits**

`docs/architecture/SYSTEM-DESIGN.md`, `docs/GETTING-STARTED.md` and `docs/architecture/timeframe-mapping.md` describe the current system — rewrite them: one engine (`strategy-runner.py`), three horizons with the Task 2 timeframe table, no profile key, six method presets unchanged.

`docs/audits/*` and `docs/prompts/*` are dated records — leave their text alone.

- [ ] **Step 3: Amend the two documents that actively contradict this change**

`docs/plans/2026-09-13-unify-backtest-with-live-rules.md:825` says **"Do NOT change `demo-pilot.py`"**. That instruction was correct for that plan and is now superseded; a later session could revert this work on its authority. Append to that line:

```markdown
  **Superseded 2026-09-13 by docs/plans/2026-09-13-collapse-to-one-system.md:** demo-pilot.py is deleted. The
  user chose one engine (strategy-runner.py); this out-of-scope line no longer applies.
```

`docs/security/2026-09-11-top5-pilot.md` already carries the stale-as-of-2026-09-13 header note (added before
this plan started executing). This task closes it out. The user's decision was to **renumber**, and
`scripts/tests/test_doc_citations.py` (added the same day) is what keeps renumbering from rotting again: it
parses every `` `file.py:123` (`anchor`) `` citation in `docs/` outside the historical directories and fails
when the anchor is no longer within 3 lines of the cited number.

Renumber in that anchored form, then let the test prove it:

- [ ] **Step 3a: rewrite the surviving citations with anchors**

For every citation into a file that still exists (`strategy-runner.py`, `journal.py`, `automation.py`), change
`` `foo.py:123` `` to `` `foo.py:123` (`def bar(`) `` with the real current line and the real token on it. Find
each number with `grep -n` — do not carry a number over from the old text, and do not trust the numbers in the
2026-09-13 review transcript either: they were correct when it read and had already moved by the time it
reported.

- [ ] **Step 3b: retire the citations into the deleted engine**

PILOT-03/04/13/22/23/27/28/29/30 cite `demo-pilot.py`, which Task 1 deleted. Do **not** re-point these at
`strategy-runner.py` — the rules were written about a different engine's control flow and re-deriving them is a
security judgement, not a text edit. For each, replace the dead citation with:

```markdown
*(enforcement point retired 2026-09-13: cited demo-pilot.py, deleted in docs/plans/2026-09-13-collapse-to-one-system.md. Rule needs re-deriving against strategy-runner.py before layers.pilot is re-enabled.)*
```

Leave the rule text itself intact — it is the requirement, and it still stands.

- [ ] **Step 3c: prove it**

Run: `python3 -m pytest scripts/tests/test_doc_citations.py -q -p no:cacheprovider`
Expected: PASS. A failure names the doc, the citation and where the anchor actually is.

- [ ] **Step 4: Verify**

Run: `python3 -m pytest scripts/tests/ -q -p no:cacheprovider`
Expected: all pass.

Run: `grep -rn "demo-pilot" docs/architecture/ docs/GETTING-STARTED.md`
Expected: no hits.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "one-system: docs describe one engine and three horizons"
```

---

## Out of scope — do NOT do these in this plan

- **The six method presets and the control panel.** The user keeps all of `wyckoff`, `ict`, `wyckoff+ict`, `wyckoff+footprint`, `wyckoff+ict+footprint`, `full`, and keeps using the method switch to choose. Do not touch `scripts/methods.py`, `scripts/method-panel.py`, `integrations/crons/method-switch.md`, or the preset registries.
- **Re-enabling `layers.pilot`.** It stays off. The kill switches at `data/live/pilot/STOP` and `data/live/pilot-futures/STOP` stay.
- **PILOT-30** (`scripts/journal.py:156` defaults `risk_pct` to `0.005`, and `:169` hardcodes `"(0.5% vốn)"`, while the entry record carries no `risk_pct`). Real, pre-existing, and the 2026-09-13 security review lists it as a gate on re-enabling the pilot — but it is a risk-reporting decision, not part of this collapse.
- **PILOT-17** (the floor is measured against a forming 15m bar). Same reason.
- **Deleting `data/live/pilot/`** (the spot state directory). Leave the directory and its history on disk; only the code path that wrote it is deleted.

## Self-review

**Spec coverage.** Decision 1 → Task 1. Decision 2 and 4 → Task 2. Decision 3 → Task 2 Step 3/6 plus Task 3. Decision 5 → the out-of-scope section (no task, by design). Decision 6 → Task 4. Decision 7 → this plan is the second commit; `dc4a475` was the first.

**Placeholders.** Every code step carries the actual replacement text. Two steps deliberately say "read the loop body before editing" (Task 3 Step 3) and "read each failure before changing it" (Task 2 Step 7) — those are instructions to look, not deferred decisions, and the surrounding steps state the required end state.

**Type consistency.** `HORIZONS` is a `list` in `automation.py` and a `dict` in `rank-setups.py` — deliberate, they are different things (an ordered name registry vs. a name→timeframe map), and `RankSetupsAgreesWithTheOneVocabulary.test_it_agrees_with_automation_case_insensitively` pins them together across the `1h`/`1H` spelling difference. `HORIZON_TF` (automation) and `HORIZONS` (rank-setups) hold the same pairs in different case; the test asserts exactly that and nothing stronger.

**Known risk this plan does not remove.** Task 2 rebuilds `TIERS` from `PAGE_RUNGS["crypto"]` for both markets. That is correct only because both markets' `PAGE_RUNGS` are identical above `15m` — they are today (`["...","15m","1h","4h","1D","1W"]` for both). If they ever diverge, `TIERS` becomes market-dependent again and this collapse has to be revisited; `test_every_horizon_still_has_a_full_context_ladder` will not catch that, because it only checks the tiers exist.
