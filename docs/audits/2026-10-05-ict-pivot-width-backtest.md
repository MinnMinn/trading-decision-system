# ICT swing width 3 vs 1 bar — backtest, 2026-10-05

Owner request 2026-10-05: "chuyển sang 1 nến và chạy lại kết quả nghiên cứu. Nếu kết quả 1 nến tốt hơn thì ghi đè lên các kết quả cũ bị ảnh hưởng."

**Scope.** Dev data only (bars before 2024-03-01); evaluation window untouched. FTMO-Demo history, method ICT, config A, long and short, 8 CFD instruments × 15m/1H/4H × 2 variants = 48 runs. **p3** = the engine v1 default (`pivot_bars` 3); **p1** = `--set fx_b1_pivot1` (the deck's one bar each side, knowledge/ict/core-a.md §2.5).
Command: `BT_HISTORY_ROOT=data/history/ftmo PYTHONPATH=. python3.12 scripts/diagnose-methods.py run --symbol <S> --tf <TF> --method ICT --config A --out <f> [--set fx_b1_pivot1]`. Raw JSONs not committed. Diagnostic, **not evidence of edge**; the 48 runs count toward the ICT experiment budget (§43).

## Totals (OBSERVED)

| Variant | Trades | sum R (gross) | Taken (2.5R floor, net of fee) | Mean net R | Cells net R > 0 (of 24) |
|---|---|---|---|---|---|
| p3 | 595 | +88.38 | 329 | −0.071 | 8 |
| p1 | 869 | +18.11 | 277 | −0.296 | 8 |

| TF | p3 mean net R (taken) | p1 mean net R (taken) |
|---|---|---|
| 15m | −0.180 (250) | −0.370 (193) |
| 1H | +0.438 (63) | −0.215 (69) |
| 4H | −0.353 (16) | +0.276 (15) |

## Findings

- **OBSERVED:** one-bar swings add trades (595 → 869) but fewer pass the 2.5R floor (329 → 277), and mean net R falls from −0.071 to −0.296. p1 is better in 8 of 24 cells.
- **OBSERVED:** the only sizeable positive block is p3 1H (+0.438 over 63 taken trades, 8 instruments); p1 4H is positive on 15 trades. Neither is tested for significance; both are small samples on data that has been read before (dev window, several earlier funnels).
- **Verdict under the owner's rule:** one bar is **not** better, so no research result is overwritten and the engine's v1 default stays `pivot_bars` 3.

## What stays as decided

- The chart keeps drawing one-bar swings (owner 2026-10-05: the chart follows the book for discretionary review; `scripts/build-artifact.py` `CHART_ICT_OPTS`). The engine default and every stored research result are unchanged.
- Fund-search cells keep `fx_b1_pivot1` ON as pre-registered.
