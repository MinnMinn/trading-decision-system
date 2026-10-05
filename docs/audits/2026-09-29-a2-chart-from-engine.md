# A1b / A2 / A2b -- the chart draws the engine's structure, nothing else (ADR 0009)

Date: 2026-09-29. Branch `b1-chart-structures` (base 3d52fae). Scope: plan items A1b, A2, A2b of
`docs/plans/2026-09-29-execution-plan.md`. Status: A1b and A2 done; A2b done on the page side, the
decision-side switch is NOT wired (see "Open item").

## What changed

### A1b -- new engine objects (`scripts/structures.py`)
- Pool objects carry `invalidated_at` (the availability time of the bar that closed through the level, only when the
  pool state is `closed_through`); FVG objects carry `invalidated_at` (from the mitigation bar, availability time).
  Both are never earlier than the object's own `formed_at` / `available_at` (PIT, CLAUDE.md §8).
- The Wyckoff trading-range dict carries `phases`: `[{kind:'phase', label, from, to, formed_at, available_at, status}]`,
  computed from the engine's own TR + event list (`_wy_phases`, `_wy_phase_bounds`, `_wy_bar`). Each phase's
  `available_at` is the confirming bar of the event that closes it, so a replay cursor cannot see a phase early.
- No detection rule was changed: the objects are derived from what `ict_structures` / `wyckoff_structures` already
  found.

### A2 -- the chart renders, it does not derive (`scripts/chart.js`, `scripts/build-artifact.py`)
- chart.js's own ICT detector (`ictParams`, `ictAnalyze`) is deleted. `ictFromStructures()` only regroups the
  engine's flat structure list by `kind`; hi/lo/eq come from the engine's dealing range, not from the rows.
- `build-artifact.py` ships engine objects per tier: `ict_json()` returns `{structures, dealing_range, bias}`,
  `wy_json_engine()` returns `{tr, events, phases}`.
- Replay (the R:R / play cursor) FILTERS the same engine objects by `available_at <= availableTimeOf(cursor)`; it
  does not re-detect. This is stricter than the old re-detection (a pivot confirmed after the cursor is excluded).
- An invalidated pool / FVG stops at `invalidated_at` (a pool's `to` comes from it).
- "Structure not established" is drawn when the engine found nothing (Wyckoff: no TR / events / phases; ICT: no
  pool / FVG / MSS). It is a right-edge note at the last close (i=null): an earlier version anchored it to a bar
  index / the window's high, and the capture review found it off-pane once the chart showed only the tail of the
  window -- fixed and pinned by `test_structure_not_established_is_shown_when_the_engine_found_none`.

### A2b -- HTF tiers against the entry tier's clock (page side)
- `tier_quality(sym, tf, clock_iso)` runs `quality.assess(series, tf, symbol=sym, now=clock)`; a tier whose data is
  older than `STALE_AFTER_BARS` (3) x its period vs the entry clock is STALE (never shown as FRESH, CLAUDE.md §20).
- Every HTF tier in the page data carries `quality = {state, reason, clock}`; the entry tier carries none. The page
  shows a badge `STALE · <reason>` (title: "vs entry clock ...") whenever a tier is not FRESH. In the six built pages
  every HTF tier was FRESH against its clock, so no badge is rendered in the samples; the STALE path is pinned by
  tests (`A2bStaleHtfTierIsMarkedStaleAgainstTheEntryClock`, 5 tests).

## Removed from the chart (engine does not compute them)
| Removed | Why |
|---|---|
| chart.js ICT detector (pivots, pools, FVG, sweeps, MSS, dealing range) | duplicate of `structures.py` (ADR 0009) |
| Order blocks (OB) | not computed by the engine |
| CISD | not computed by the engine |
| OTE zone | not computed by the engine |
| sigma targets | not computed by the engine |
| Session H/L, PDH/PDL | not computed by the engine |
| Model-owned anchors (e.g. the "BU" line) | narrative-owned level, not engine structure (CLAUDE.md §15/§17); entry tier `levels=[]` |
| Narrative TR / events / invalidation line ("invalidated" mark) | model-owned; the engine emits no Wyckoff invalidation yet |

Each item stays undrawn with "not computed by the engine" until the engine gains it; adding one is a detection change
and belongs to the ICT / Wyckoff workstreams, not to this item.

## Labelled VISUALIZATION_ONLY
- Killzone shading (`killzoneSpans` in chart.js, comment added): time-of-day bands from the tier's own clock, no market
  data, never feeds a decision (session-model.md project definition; unchanged behaviour).
- The Wyckoff event letters mirrored for distribution (`_WY_EVENT_LABEL` in build-artifact.py, already commented
  VISUALIZATION_ONLY): a chart-label choice, the letters never reach a decision.
- Plan (R:R) boxes are drawn from the plan's own numbers, not from structure; they were not touched here.

## Disclosures
- The "most recent TR" pick and the phase A-E cut points are a project convention, not a book-derived rule.
- The ICT MSS label "closed past the swing, displacement missing" is pre-existing i18n text; on busy windows the
  labels overlap and the lane looks cluttered (visible in `entry-btc.ict.png`). Left unchanged (out of scope).
- No engine-computed Wyckoff invalidation exists, so no Wyckoff invalidation is drawn.
- No HTF Wyckoff TR detector was added (new detection, Wyckoff workstream).

## Tests
- `scripts/tests/test_structures.py`: `A1bInvalidatedAt`, `A1bWyckoffPhases` (invalidated_at >= formed/available,
  phases PIT-ordered).
- `scripts/tests/test_build_artifact.py`: page data carries the engine objects; grep-based proof that chart.js has no
  ICT detection code (`test_ict_detector_is_gone_from_chart_js`); `ictFromStructures` purity; not-established labels;
  tier quality present on HTF tiers only; STALE tier vs the clock.
- Rewritten because they pinned the removed detector: `test_annotation_builders_are_pure`, `RangePctSeriesEngine`.
- Retired: `scripts/tests/ict-invariants.js` (a node script that fed chart.js's detector its own output; it has no
  subject any more) and the body of `scripts/tests/test_chart_ict_invariants.py`, now a two-test retirement notice.
  The invariants it protected -- ICT structures re-derive from the candles they came from, PIT ordering, byte-identity
  of chart data with the decision path -- are covered where the detector now lives: `test_audit_round2_ict.py`
  (ict-scan.py correctness) and `test_structures.py` (`IctStructuresMatchAnalyze`: `ict_structures()` byte-identical to a direct `ict_scan.analyze()`; `ConfirmationDelay`, `AvailableTimeInvariant`). The only
  remaining textual mention of `ict-invariants.js` is a historical sentence in that notice's docstring.
- Result: `python -m unittest scripts.tests.test_build_artifact scripts.tests.test_structures scripts.tests.test_methods`
  -> Ran 146, OK (skipped=1, environment: no mt5-bridge data in a worktree). Log: `$TMP/a2-tests.log`.

## v1 unchanged
No decision-path code changed. The stability-report AUS200 4H run (`--workers 1`) gives a byte-identical .md in the
worktree and on main at 3d52fae; the .json differs only in snapshot metadata. Log: `$TMP/a2-rows.log`.

## Open item -- decision-side A2b (`fx_a2b_stale_htf_block`)
Not implemented. It needs edits to `scripts/backtest-methods.py` (`_OPTS_BASE`, `htf_bias_gate`) and
`scripts/stability-report.py` (`_SCAN_RELEVANT_KEYS`, `config_opts`), which were outside the files granted to this
task; the edit was denied and not worked around. Design, ready to apply: add `fx_a2b_stale_htf_block: False` to
`_OPTS_BASE` (default = v1, so byte-identical rows); when True, `htf_bias_gate` treats a tier whose
`tier_quality` state is STALE as an unmet gate (WAIT / BLOCK ENTRY), never as passed; list the key in
`_SCAN_RELEVANT_KEYS` and `config_opts` so scans with the switch on and off are distinct cache/scan entries.

## Environment note
CFD pages cannot build inside a worktree (it has no `data/live/mt5-bridge`). They were built from a scratch copy of the
worktree plus main's mt5-bridge data (nothing written under `data/live`).

## Sample images
Root: `C:\Users\nguye\AppData\Local\Temp\claude\C--Trading-trading-decision-system\54d6b57d-fb96-4858-97dd-05e6e5886a88\scratchpad\charts-a2\`
(each style folder also has `manifest.json`; pages are in `..\pages-a2\<style>.html`).
- Crypto ICT: `scalping\entry-btc.ict.png`, `day\entry-btc.ict.png`, `swing\entry-btc.ict.png`
- Crypto Wyckoff (with TR/phases): `scalping\entry-eth.wyckoff.png`, `day\entry-eth.wyckoff.png`, `swing\entry-eth.wyckoff.png`
- Crypto Wyckoff "not established": `scalping\entry-btc.wyckoff.png`, `scalping\entry-sol.wyckoff.png`
- CFD ICT: `cfd-scalping\entry-xau.ict.png`, `cfd-scalping\entry-aus200.ict.png`, `cfd-day\entry-xau.ict.png`, `cfd-swing\entry-xau.ict.png`
- CFD Wyckoff: `cfd-scalping\entry-xau.wyckoff.png`, `cfd-day\entry-xau.wyckoff.png`, `cfd-swing\entry-xau.wyckoff.png`

## Correction (2026-10-04)

The "Removed from the chart" table above says CISD is "not computed by the engine". That is wrong: `scripts/ict-scan.py` `analyze()` does compute it -- every MSS record carries a `cisd` field (`level` = open of the first candle of the final opposing-colour run into the extreme, `time`, `confirmed`; knowledge/ict/core-b.md §2.3), on both the bull and the bear branch of the MSS state machine. What is true is that the chart does not DRAW it: `scripts/structures.py` copies the field verbatim onto each `mss` object and `scripts/chart.js` ignores it. Note for any future drawing of it: `cisd.confirmed` is found by a forward scan to the end of the window, so it would need its own availability time before it could be shown point-in-time. Recorded by the ICT chart-fidelity audit fix of 2026-10-04; the text above is left as written.
