# Real-cost reprice of the ICT / Wyckoff method engine -- re-run (2026-10-04)

**Informational only, development window.** This re-runs `scripts/research/reprice_real_costs.py` (commit 0f0428c) at today's
engine code. It is the same design as docs/audits/2026-09-29-real-costs-reprice.md:
- symbols XAUUSD, US500, DE40;
- 15m, config A;
- `pit_cutoff` 2024-03-01 (latest trade exit 2024-01-30);
- FTMO-Demo spreads and swap; commission UNKNOWN, priced at 0.

Each real-cost cell is priced in the fixed server-table hour frame and also in the legacy frame
(docs/audits/2026-10-04-cost-hour-erratum.md). Raw data: docs/audits/2026-10-04-real-costs-reprice-rerun.json.

Each cell reads n trades, net R (gross R in brackets). "Baseline" is the flat 0.05 %/side fee; "real" is FTMO costs; "real +
flat" closes every position before the rollover.

| symbol, method | baseline | real (fixed frame) | real + flat (fixed frame) | 2026-09-29 record, real / real + flat |
|---|---|---|---|---|
| XAUUSD ICT | 67, -14.9 (+9.2) | 82, -3.7 (+6.1) | 87, -1.3 (+5.2) | 100, -5.8 / 103, +3.2 |
| XAUUSD Wyckoff | 90, -62.3 (-15.8) | 114, -35.6 (-19.9) | 118, -11.1 (-1.4) | 145, -45.6 / 148, -10.3 |
| US500 ICT | 18, -3.3 (+1.5) | 21, +2.0 (+2.9) | 23, -2.4 (-1.8) | 28, +1.5 / 29, -1.8 |
| US500 Wyckoff | 22, +1.0 (+11.9) | 26, +6.0 (+7.9) | 26, +7.6 (+9.2) | 31, +5.3 / 33, +5.5 |
| DE40 ICT | 10, -3.4 (-0.1) | 10, -0.4 (-0.1) | 10, -4.2 (-3.9) | 11, +1.4 / 11, -2.0 |
| DE40 Wyckoff | 23, +15.2 (+26.8) | 24, +23.5 (+25.8) | 25, +26.3 (+27.9) | 31, +19.5 / 32, +25.0 |

## Reading

1. **The hour frame does not matter here.** Fixed and legacy differ by at most 0.2 R per cell.
2. **The 2026-09-29 table cannot be reproduced at today's code.** Today's engine takes 10-25 % fewer trades, because of the
   engine's fidelity and look-ahead fixes since then. Read this table as the current engine's numbers.
3. **Wyckoff on the indices is positive on small samples.** DE40 is +23.5 R on 24 trades and US500 +6.0 R on 26. On gold it
   is negative (-35.6 R on 114).
   - These are 2 of 6 cells, seen after the fact, on development data only. They are a lead for the pre-registered Wyckoff
     re-test, not evidence.
   - Index 15m history on FTMO starts in 2022, which is why the samples are small.
