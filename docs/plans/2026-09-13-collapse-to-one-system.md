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

### Task 2: Collapse the style vocabulary to three horizons

**Files:**
- Modify: `scripts/automation.py:105,119-123,162-164,178,287,377-386,601,989,1068` (leave `PAGE_RUNGS:159` alone)
- Modify: `scripts/htf_context.py:47,50`
- Modify: `scripts/check-narrative.py:29,108`
- Modify: `scripts/tests/test_one_system.py` (add the vocabulary class)
- Modify: `docs/architecture/automation-config.json` (timeframes), `docs/architecture/timeframe-mapping.md`

- [ ] **Step 1: Write the failing test**

Append to `scripts/tests/test_one_system.py`:

```python
HORIZONS = ("scalping", "day", "swing")
HORIZON_TF = {"scalping": "15m", "day": "1h", "swing": "4h"}


class OneStyleVocabulary(unittest.TestCase):
    """Before 2026-09-13 there were two: automation.STYLE mapped (market, tf) to ten labels
    (scalping/daytrade/1h/4h/swing + five gold-*), while rank-setups.HORIZONS mapped three horizon names to
    timeframe sets. They overlapped and DISAGREED -- `scalping` was 1m in one and 15m in the other, `swing` was
    1D in one and 4H in the other. One vocabulary, one mapping."""

    def setUp(self):
        import importlib
        self.auto = importlib.import_module("automation")

    def test_the_ten_value_style_map_is_gone(self):
        self.assertFalse(hasattr(self.auto, "STYLE"), "automation.STYLE is the superseded vocabulary")
        self.assertFalse(hasattr(self.auto, "STYLE_MARKET_TF"))

    def test_horizons_are_the_only_names(self):
        self.assertEqual(tuple(self.auto.HORIZONS), HORIZONS)

    def test_each_horizon_maps_to_exactly_one_timeframe(self):
        self.assertEqual(self.auto.HORIZON_TF, HORIZON_TF)

    def test_no_gold_prefixed_names_survive(self):
        """The cfd market is distinguished by its `market` field, the way pilot-top5.json already did it."""
        for path, src in sources().items():
            for i, line in enumerate(src.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                self.assertIsNone(re.search(r'"gold-[a-z0-9]+"', line), f"{path}:{i} keeps a gold-* style name")

    def test_daytrade_is_not_a_name_any_more(self):
        """`daytrade` (15m) and `day` (1H) were two names one keystroke apart for different timeframes."""
        for path, src in sources().items():
            for i, line in enumerate(src.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                self.assertNotIn("daytrade", line, f"{path}:{i} keeps the superseded `daytrade` name")

    def test_every_horizon_still_has_a_full_context_ladder(self):
        """Dropping 1D from the SCANNED set must not leave swing without a bias tier -- PAGE_RUNGS keeps 1D and
        1W as context-only rungs, and this asserts that the distinction actually holds."""
        for hz in HORIZONS:
            tiers = self.auto.TIERS[hz]
            self.assertIsNotNone(tiers["structure"], f"{hz} lost its structure tier")
            self.assertIsNotNone(tiers["bias"], f"{hz} lost its bias tier")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=scripts python3 -m pytest scripts/tests/test_one_system.py::OneStyleVocabulary -q -p no:cacheprovider`
Expected: failures on `test_the_ten_value_style_map_is_gone` (STYLE exists), `test_horizons_are_the_only_names` (no `HORIZONS` attribute), `test_each_horizon_maps_to_exactly_one_timeframe`, `test_no_gold_prefixed_names_survive`, `test_daytrade_is_not_a_name_any_more`.

- [ ] **Step 3: Replace STYLE with the horizon vocabulary**

In `scripts/automation.py` replace lines 119-123 with:

```python
# One style vocabulary (user decision 2026-09-13): three horizons, shared by both markets, one timeframe each.
# Replaces the ten-value STYLE map, which disagreed with rank-setups.HORIZONS about what `scalping` and `swing`
# meant (1m vs 15m, 1D vs 4H) and carried a parallel gold-* set for cfd that the `market` field already covers.
HORIZONS = ["scalping", "day", "swing"]
HORIZON_TF = {"scalping": "15m", "day": "1h", "swing": "4h"}
TF_HORIZON = {tf: hz for hz, tf in HORIZON_TF.items()}
```

Change line 105 to the scanned set:

```python
MARKET_TIMEFRAMES = {"crypto": ["15m", "1h", "4h"], "cfd": ["15m", "1h", "4h"]}
```

Leave `PAGE_RUNGS` (line 159) exactly as it is — it is the context ladder, not the scanned set, and Task 2 Step 1's ladder test depends on it keeping `1D` and `1W`.

Replace the `TIERS` build (lines 162-164) with:

```python
TIERS = {}
for _hz in HORIZONS:
    _s, _b = ladder(HORIZON_TF[_hz], PAGE_RUNGS["crypto"])
    TIERS[_hz] = {k: ({"tf": t, "style": TF_HORIZON.get(t)} if t else None)
                  for k, t in (("structure", _s), ("bias", _b))}
```

(Both markets now share `PAGE_RUNGS` above `15m`, so one build covers both.)

- [ ] **Step 4: Update every STYLE consumer in automation.py**

Line 287 (config migration) becomes:

```python
        mk["timeframes"] = {t: bool(old_styles.get(TF_HORIZON[t], True)) for t in MARKET_TIMEFRAMES[m]}
```

Lines 377-386: the function is `enabled_styles(cfg=None)` — **keep that name and that signature**, including the
`load(require_readable=False)` fallback, because `scan-loop.sh` and `local-eval-brief.py` call it with no
argument. Replace only the body:

```python
def enabled_styles(cfg=None):
    """The horizons the scanner and the local read are permitted to run, in HORIZONS order."""
    if cfg is None:
        cfg, _, _ = load(require_readable=False)
    out = set()
    for m in MARKETS:                       # MARKETS is defined at automation.py:89
        mk = cfg.get("markets", {}).get(m, {})
        if not mk.get("enabled", True):
            continue
        for tf in MARKET_TIMEFRAMES[m]:
            if mk.get("timeframes", {}).get(tf, True):
                out.add(TF_HORIZON[tf])
    return [h for h in HORIZONS if h in out]
```

Then check its callers still get what they expect — the return is now three horizon names, not up to ten style
labels:

Run: `grep -rn "enabled_styles" scripts/ | grep -v __pycache__`
Expected: every hit either iterates the list or passes each element to something that accepts a horizon name.
Fix any caller that indexes it positionally or compares against a literal `"daytrade"` / `"gold-*"`.

Line 601 becomes `styles = [TF_HORIZON[tf] for tf in MARKET_TIMEFRAMES[m] if mk["timeframes"].get(tf, True)]`; line 989 becomes `f"-> horizons {', '.join(TF_HORIZON[t] for t in on_tfs)}"`; line 1068 becomes `print("  horizons affected: " + TF_HORIZON[a.name])`.

- [ ] **Step 5: Follow through in htf_context.py and check-narrative.py**

`scripts/htf_context.py:50` becomes:

```python
STYLE_TF = dict(_auto.HORIZON_TF)    # horizon -> timeframe label as /automation spells it
```

Line 47 keeps `CONTEXT_STYLE = _auto.CONTEXT_STYLE` unchanged (that alias is built from `TIERS`, which Step 3 rebuilt). `scripts/check-narrative.py` needs no edit if `CONTEXT_STYLE` still resolves — confirm with the Step 7 run rather than assuming.

- [ ] **Step 6: Shrink the scanned timeframes in the live config**

Edit `docs/architecture/automation-config.json` so both markets' `timeframes` read exactly:

```json
   "timeframes": { "15m": true, "1h": true, "4h": true }
```

- [ ] **Step 7: Run the tests and the real commands**

Run: `PYTHONPATH=scripts python3 -m pytest scripts/tests/test_one_system.py -q -p no:cacheprovider`
Expected: PASS.

Run: `python3 -m pytest scripts/tests/ -q -p no:cacheprovider`
Expected: all pass. Tests asserting `daytrade`, `gold-*` or a `1m` tier must be updated to the new vocabulary, not deleted wholesale — read each failure before changing it.

Run: `python3 scripts/automation.py status`
Expected: exit 0; the crypto and cfd blocks list three timeframes each and horizons `scalping, day, swing`.

Run: `python3 scripts/check-narrative.py --help`
Expected: exit 0 (proves `CONTEXT_STYLE` still resolves).

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "one-system: one style vocabulary -- three horizons, one timeframe each"
```

---

### Task 3: Make the horizon→timeframe mapping single-valued in rank-setups

**Files:**
- Modify: `scripts/rank-setups.py:40,212`
- Modify: `scripts/tests/test_rank_setups_horizons.py`

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
