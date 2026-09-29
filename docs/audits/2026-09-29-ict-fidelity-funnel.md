# ICT fidelity funnel (B2a, B2b, B1, B-RAID) — 2026-09-29

Scope: dev data only (bars before 2024-03-01, `DEV_CUTOFF`), 15m, config A, method ICT. Branch `b1-ict-fidelity`.
Command: `BT_HISTORY_ROOT=data/history/ftmo PYTHONPATH=. python scripts/diagnose-methods.py run --symbol <S> --tf 15m --method ICT --config A --out <f.json> [--set fx_key ...]`.
Raw JSONs are not committed (scratch). This is a funnel/diagnostic, **not evidence of edge**. Every variant run counts toward N (ICT 41 per candidate cell).

Labels: **OBSERVED** = read from the run JSON (`outcomes`, `account`, `funnel`). **INFERRED** = my reading, not tested.
"sumR" = gross R over booked trades. "net" = `account.simulate_taken_mean_net_R` (mean R after the run's fee model; the JSON records `fee_per_side` 0.0005 and `entry_order_type` taker, on trades passing the 2R floor; `taken` = their count).

## Results (OBSERVED)

| Symbol | Variant (`fx_` key) | Trades | sumR | Win % | Taken | Mean net R |
|---|---|---|---|---|---|---|
| XAUUSD | v1 | 139 | 13.27 | 34.5 | 96 | -0.334 |
| XAUUSD | b2a `fx_b2a_fvg_in_leg` | 93 | 5.68 | 32.3 | 65 | -0.319 |
| XAUUSD | b2b `fx_b2b_ce_fail` | 133 | 19.27 | 36.1 | 91 | -0.276 |
| XAUUSD | b1p `fx_b1_pivot1` | 199 | 3.55 | 36.2 | 101 | -0.255 |
| XAUUSD | braid `fx_braid_optional` | 1309 | 151.16 | 36.3 | 744 | -0.213 |
| XAUUSD | all four | 736 | 3.26 | 33.6 | 400 | -0.333 |
| US500 | braid | 163 | 30.30 | 36.8 | 104 | -0.083 |
| US500 | all four | 100 | 0.86 | 29.0 | 64 | -0.286 |
| DE40 | all four | 83 | 7.21 | 33.7 | 59 | -0.319 |

Carried from the handoff (`docs/plans/2026-09-29-handoff-macbook.md`, trades / sumR, not re-run): US500 v1 34 / 4.04, b2a 23 / 2.01, b2b 33 / 2.90, b1p 48 / -4.31. DE40 v1 15 / 0.07, b2a 12 / -2.75, b2b 15 / 0.07 (identical to v1), b1p 31 / 11.89, braid 137 / -1.85.

## Findings

- **OBSERVED:** no variant has positive mean net R after costs in any run above (best: US500 braid -0.083). Gross sumR is positive on most cells but disappears after the 2R floor + fee model.
- **OBSERVED:** `braid` raises trade count ~9x on XAUUSD (139 -> 1309), ~4.8x on US500 (34 -> 163) and ~9x on DE40 (15 -> 137); the gross gain scales with volume, win rate stays ~36 %. `all four` on XAUUSD is 736 trades but sumR only 3.26, so the variants do not stack additively.
- **OBSERVED:** b2b on DE40 is identical to v1 (15 / 0.07); the key never changed a decision there.
- **INFERRED:** b2a filters trades (fewer trades, lower sumR on every symbol checked), consistent with being a stricter setup rule rather than an edge source. b1p and braid mostly add trades. Neither claim is tested here beyond the counts.
- **INFERRED (code review, unconfirmed):** under `fx_braid_optional`, `setup_candidate` (`scripts/ict-scan.py`) takes the last MSS with no recency bound when no matching raid exists, so a stale MSS in the window can seed a candidate once a later same-direction FVG forms. This may drive part of the ~9x trade explosion. Whether that is intended is an open question for the item's author; braid is not adopted and its numbers should not be read as fidelity to the source.
- **INFERRED:** sumR differences of a few R on 15-140 trades are inside noise; no significance test was run.

## Caveats

- Dev window only; the evaluation window was not touched and not changed.
- Costs are the generic fee model; the FTMO real commission is unknown and is not guessed.
- Selection risk: 9 new + 9 carried runs; N-adjustment belongs to `fund-search` (Batch 2), not this doc.
- No verdict on adopting any key: all remain default v1 and off.
- `diagnose-methods.py run --set` only checks the `fx_` prefix, so a mistyped key runs as v1 and is echoed in `overlay`. Validation against the union of ICT and Wyckoff key sets is scheduled for the merge; until then, check the `overlay` of each JSON.
