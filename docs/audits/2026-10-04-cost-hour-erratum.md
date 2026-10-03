# Erratum: spreads priced at the wrong hour bucket (2026-10-04)

**What.** The FTMO spread table (`integrations/mt5/ExportSymbolSpec.mq5`, `recorded_spread_m15.by_utc_hour`) buckets every M15
bar by server time minus the server-GMT offset AT EXPORT (+3 h). So bucket h holds server hour (h + 3) mod 24 all year. The
daily break (server 00:00) is bucket 21 in summer and in winter. `real_costs.cost_r` and `edge_census.Costs` priced each leg at
the leg's own UTC hour. In US summer time that is the same bucket; in US standard time it is the next server hour's spread.
First noticed in [M1-A1] item 7 (docs/plans/2026-10-03-edge-m1-month-end-preregistration.md), which M1 priced correctly.

**Reach.** Every research cost leg: census, F2-F7, the book studies (book_sim -> A1 / A3 / gap tails), the paper twin's net,
and the method engine's real-cost path (`backtest-methods.py` / `fund-search.py` through `cost_r`). Not reached:
- the flat-fee prop-search (no cost profile);
- the crypto families (Binance fees);
- M1;
- the demo executor (real fills).

**Fix (commit 1666367).** `real_costs.table_hour` maps an instant to the table bucket: (server hour - export offset) mod 24.
An offset within 60 s of a whole hour is that hour; five specs say 10799 s. `real_costs.HOUR_FRAME` is "server_table"; the
old "utc_legacy" still reproduces every record priced before the fix. `cost_r` records the frame it used. Records are not
edited (§42).

## Re-run (DESCRIPTIVE)

`python3 scripts/research/cost_hour_erratum.py all` ran each family's own `run` in both frames, on the same code and the same
data snapshot. Raw diff: docs/audits/2026-10-04-cost-hour-erratum.json.

Scope of the re-run:
- Only windows that were already read. F6 is discovery only, and the F2 forward stage is not run.
- The data now runs a few days past the original reads' end (2026-09-28), so F3 / F4 exposed nets differ from their records
  by the new days. That difference is the same in both frames.

| family | numbers changed | largest net change, bp per trade | verdict changes |
|---|---|---|---|
| census (dev, 40 tests) | 1,792 | -1.35 (AUS200 per-symbol row) | 0 |
| F2 exposed / history | 1,109 / 2,920 | -0.17 / -0.25 | 0 / 0 |
| F3 (30) | 718 | -0.64 | 0 |
| F4 (41) | 1,015 | -3.61 (a p90 stress figure) | 0 |
| F5 (27) | 524 | -3.08 (a p90 stress figure) | 0 |
| AMD (24) | 357 | +2.28 (a p90 stress figure) | 0 |
| hold (9) | 0 (gross increments, swap only) | 0 | 0 |
| F6 discovery | 166 | +0.14 | 0 |
| A1 vol schedule | 97 | -- | 0 (1.4/1.4: dE half edge +0.592, worst trade 1.386 %, unchanged) |
| A3 silver | 63 | -- | 0 (dE half edge +0.911 -> +0.903) |

How "verdict changes 0" was checked:
1. The excess statistics and their BH / p gates do not use costs. Only the net gates can move.
2. Thirty-eight net figures change sign (net bp, net z or t of net, counted separately). Each one was within 1.6 bp, or
   0.03 in z, of zero. Each sits in a per-symbol or per-year report row, or in a test that had already failed its p-gate in
   that read. The only BH candidate among them is the F5 G9 XPDUSD discovery: its net z moves around zero, its net stays at
   +26 bp, and its confirmation fails on p = 0.96.
3. One p-value crosses a threshold: F3 H2 DE40, confirmation net p 0.0999 -> 0.107. It is a report-only figure for a test
   that was never a BH candidate.
4. Each family's own `report` was run on both frames, and its verdict column is identical row for row.

The survivors do not move:

| survivor | discovery net (bp) | confirmation net (bp) | exposed net (bp) |
|---|---|---|---|
| H7 XAUUSD | +13.81 | +9.43 -> +9.42 | +8.30 |
| G9 XAUUSD | +28.13 | +24.96 | +10.11 |
| G9 XAGUSD | +43.07 -> +43.01 | +34.39 -> +34.31 | +25.07 -> +25.02 |

Gold and silver spreads are nearly flat across hours, so a one-hour shift barely moves them. The shift matters most next to
the daily break, which the intraday rules avoid.

## Conclusion

No verdict and no owner decision changes: v4, the A1 / A3 re-read and every family's survivor list stand. Open: the method
engine's real-cost results (fund-search) were never produced, so nothing there needs re-reading. Any future run prices in the
server-table frame.
