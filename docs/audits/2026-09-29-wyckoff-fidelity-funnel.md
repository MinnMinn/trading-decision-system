# Wyckoff fidelity funnel (W1, W2, W3, W5, W7) — 2026-09-29

Scope: dev data only (bars before 2024-03-01), 15m, config A, method WYCKOFF-BOOK. Branch `b1-wyckoff-fidelity`.
Command: `BT_HISTORY_ROOT=data/history/ftmo PYTHONPATH=. python scripts/diagnose-methods.py run --symbol <S> --tf 15m --method WYCKOFF-BOOK --config A --out <f.json> [--set fx_key ...]`.
Raw JSONs not committed. Diagnostic only, **not evidence of edge**. Each variant counts toward N (Wyckoff 16 per candidate cell).
**W7 (`fx_w7_htf_target`) is reported but NOT adopted; it needs owner sign-off.**

Labels: **OBSERVED** = read from run JSON. **INFERRED** = my reading, untested. "all four" = W1+W2+W3+W5 (W7 excluded). "net" = mean R after fee 0.0005/side on trades passing the 2R floor.

## Results (OBSERVED)

| Symbol | Variant | Trades | sumR | Win % | Taken | Mean net R |
|---|---|---|---|---|---|---|
| XAUUSD | v1 (handoff) | 416 | -16.79 | — | — | — |
| XAUUSD | w2 `fx_w2_st_below_sc` | 679 | 19.49 | 48.9 | 194 | -0.639 |
| XAUUSD | w3 `fx_w3_mSOW_spring` | 416 | -16.79 | 45.0 | 129 | -0.668 |
| XAUUSD | w5 `fx_w5_vp_abandon` | 415 | -17.89 | 44.8 | 129 | -0.668 |
| XAUUSD | all four | 776 | -33.90 | 42.9 | 245 | -0.659 |
| XAUUSD | w7 (not adopted) | 291 | 10.83 | 40.9 | 151 | -0.363 |
| US500 | v1 | 73 | 13.85 | 49.3 | 27 | -0.280 |
| DE40 | v1 | 61 | 22.62 | 37.7 | 27 | +0.362 |
| DE40 | w7 (not adopted) | 40 | 21.28 | 35.0 | 30 | +0.287 |
| US500 | all four | 119 | 43.94 | 52.9 | 41 | +0.207 |
| US500 | w7 (not adopted) | 45 | 11.68 | 42.2 | 27 | -0.133 |

Carried from the handoff (trades / sumR, not re-run): v1 US500 73 / 13.85, DE40 61 / 22.62. w1 identical to v1 on XAUUSD, US500, DE40. w3 and w5 identical to v1 on US500 and DE40. w2 US500 107 / 16.40, DE40 80 / -8.32. all-four DE40 103 / 8.38. w7 DE40 40 / 21.28.

## Re-run after code-review round 1 (OBSERVED)

The review fixed W7's decision time (bar close, not open), widened the HTF cache key and removed global `PARAMS` mutation. Re-run on the fixed code: v1 US500 / DE40 and W7 on XAUUSD / US500 / DE40 gave the same trades and sumR as before the fixes (v1 73 / 13.85 and 61 / 22.62; W7 291 / 10.83, 45 / 11.68, 40 / 21.28). So the fixes changed no result on this dev data.

## Findings

- **OBSERVED:** w3 on XAUUSD is identical to v1 (416 / -16.79); w1 is inert on all three symbols; w3 and w5 are inert on US500 and DE40. These keys change nothing on the dev data checked.
- **OBSERVED:** only w2 changes trade volume materially (XAUUSD 416 -> 679; US500 73 -> 107; DE40 61 -> 80), with mixed sign of sumR by symbol.
- **OBSERVED:** XAUUSD mean net R is strongly negative for every variant (-0.36 to -0.67). The single positive net cell is US500 all-four (+0.207 on 41 trades), and XAUUSD all-four on the same rules is -0.659.
- **INFERRED (code review):** XAUUSD all-four (776 / -33.90) is not the sum of its parts (w2 alone 679 / +19.49; w3, w5 near-inert), which implies interaction between keys; no attribution was run.
- **INFERRED:** the US500 all-four result is one small cell of a 16-run search and is not stable across symbols; it should not be read as an edge.
- **INFERRED:** w7 gives the least-bad XAUUSD net R (-0.363) but still negative; on US500 it lowers net R vs all-four. Adoption is the owner's call.

## Caveats

- Dev window only; evaluation window untouched and unchanged.
- FTMO real commission unknown, not guessed. No significance test was run.
- All keys stay default v1 / off. `wyckoff_rules.PARAMS` mutation between runs is checked at code-review, not here.
