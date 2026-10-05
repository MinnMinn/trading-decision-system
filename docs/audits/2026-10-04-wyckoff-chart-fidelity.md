# Wyckoff chart fidelity — fixes for the 2026-10-04 chart audit

Scope: the Wyckoff overlay of the chart pages (scripts/structures.py `wyckoff_structures`, scripts/build-artifact.py
`wy_ship`/`wy_json_engine`/`ladder`, scripts/chart.js `wyckoffAt`/`wyckoffShapes`/legend) and one PARAMS key in
scripts/wyckoff_rules.py. Regression tests: scripts/tests/test_wyckoff_chart_fidelity.py (plus updated
test_structures.py / test_build_artifact.py).

## Decision path: unchanged

`detect_accumulations` / `detect_distributions` return byte-identical records with the default PARAMS and with the
backtest's fx_w1..w5 bridged variants (428 old-vs-new comparisons over every data/history series, 0 differences).
Every new read (`record_extras`, `_wy_view`, `_wy_availability`) is chart-only. The one detection change, W8, is a
PARAMS key that is **False** for the decision path (backtest-methods.py / live runner never set it).

**W8 on the chart: a flag, not a filter (amended 2026-10-04 at merge review).** The first fix applied W8 to the chart
only (`ENVELOPE_PARAMS` with W8 on). That made the chart stricter than the decision path -- a v1 structure the pilot
can trade was simply not drawn -- which breaks ADR 0009 rule 1 (the chart draws what the decision reads). The chart
now detects with `W.PARAMS` (`structures.ENVELOPE_PARAMS is W.PARAMS`), every structure carries
`choch_outside_box` (W8's box test, `structures.choch_outside_box`), and chart.js marks that CHoCH flag in the warning
colour with "outside SC–AR box (WA p68–69)". `structures.W8_PARAMS` keeps the candidate setting for research and the
W8 tests. The engine-grammar regression (`NarrativeContractOnEngineOutput`) found one such structure (SUIUSDT 2H
distribution: CHoCH and an unconfirmed LPS[C] on one bar), which is exactly what the flag is for.

**Owner decision 2026-10-05: W8 stays OFF ("Đồng ý bỏ W8").** Turning it on would reduce detected structures over the full
history from 13,088 to 2,990 (−77 %) and structures reaching a BU entry from 4,989 to 832 (−83 %); the backtest
(docs/audits/2026-10-05-w8-backtest.md) found no improvement (mean net R negative in every variant, worse overall with
W8). So wyckoff_rules.PARAMS keeps `fx_w8_choch_in_box=False`, the chart keeps drawing such structures with the
`choch_outside_box` warning, and `fx_w8_choch_in_box` remains a research-only backtest key.

## Findings

| # | Fix | Test |
|---|-----|------|
| 1 | W8 `fx_w8_choch_in_box`: CHoCH swing high must be ≤ AR + `choch_box_tol_tr`·TR (WA p68–69); ran-away guard runs before the LPS[C]/SOS test. Decision-path key off; chart shows it as the `choch_outside_box` flag (above). | `W8ChochInsideBox` |
| 2 | `shakeout=True` → "Shakeout" (WA p80, p83; method.md §2 A6); distribution "UTAD (Shakeout)" (WA p107 names both mirrors UTAD). | `EventLabels` |
| 3, 4 | Every object's `available_at` = earliest bar k such that a re-run on candles[:k+1] (and every longer prefix) emits it in the same state (`structures._wy_availability`). Covers: record exists only once Spring/LPS[C] fires; CHoCH pivot confirmation; Spring vs Shakeout typing at the reclaim / end of window; SOS search runs to n−COMMIT (one bar past `sos`); '?' confirmation. Phases carry `state_available_at`; replay shows them open before it. | `PointInTimePrefixRedetection` |
| 5 | Engine invalidation (`record_extras`): R10 abandon (WMT p243–249 Step 4) at the bar R10's window closes, or the first close beyond the Spring low / UT high after typing (WMT p271). Rendered per ADR 0004 (labels kept, faded, × on the break). LPS[C] path: no book rule, none emitted. | `EngineObjectsOnData`, `ChartBuilders` |
| 6 | Distribution ST anchored at the high; accumulation CHoCH at the high. | `EventLabels.test_anchor_sides` |
| 7 | Phase "tested" only if closed, st_sign/phase_b_sign not "contradicts", not sloped, opening event confirmed; else "?" + first reason. | test_structures, `ChartBuilders` |
| 8 | Distribution: BU → LPSY, Phase-C test → UTAD, LPS[C] → LPSY[C]. | `EventLabels` |
| 9 | LPS[C] path draws A→B→C→D with an "LPS[C]" event. | `EngineObjectsOnData` |
| 10 | Phase E = first close beyond the SOS leg high after the BU (WA p85); TR ends at E start / invalidation / expiry. | `EngineObjectsOnData`, `ChartBuilders` |
| 11 | Compact tiers draw "Wyckoff: not established". | `ChartBuilders` |
| 12 | Ladder Wyckoff cell reads `wy_json_engine` (ADR 0009). | `LadderReadsTheEngine` |
| 13 | Volume-spike ratios get "(tick)" on tick feeds (method.md §4.1). | `I18nAndSource` |
| 14 | Engine labels pass check-narrative.py phase_grammar + confirmation_grammar + tick_volume_checks (distribution checked on mirrored candles: the checker's proxies are long-only). | `NarrativeContractOnEngineOutput` |
| 15, 16 | One SOS/SOW flag (sos_bar, `conf_bar`=sos); no "Reclaim" flag. | test_structures |
| 17 | Legend: side-aware TR border text; "engine-detected Wyckoff events". | `I18nAndSource` |
| 18 | Spring/UTAD label carries its R7 type (T1/T2/T3). | `EventLabels` |

## Project parameters and rules introduced (the books print no number for these)

- `choch_box_tol_tr = 0.1` — how far above the AR the CHoCH may sit and still count as "at the box edge".
- LPS[C] bar — lowest low between the last Phase-B swing high already confirmed at the SOS bar and the SOS bar (WA p82: the SOS rally starts from the LPS).
- SOS leg high — max high from the SOS bar up to (not including) the BU bar; Phase E searched within `phase_d_window` bars after the BU.
- Expiry of an open last phase — when the engine's own search window for its closing event has passed: C at anchor + `phase_d_window` + COMMIT − 1; D at SOS (or BU) + `phase_d_window`; E at its start + `phase_d_window`.
- '?' on Test / BU / LPS[C] — check-narrative.py's pullback proxy (a later close beyond the event bar), shared via `wyckoff_rules._pullback_confirmed`.
- An invalidated read drops phases and events after the invalidation bar.

## Not done / limits

- The swing page's Wyckoff lane is not analysed in the current config, and with W8 on no swing tier shows a structure; the CFD pages could not be built offline (no MT5 export), so tick labels were checked by test, not by eye.
- WA §2.11.7 (failure to maintain structure) defines no bar rule, so it is not used as an invalidation trigger.
