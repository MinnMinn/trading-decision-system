# Family M1 -- month-end pension-rebalancing pressure on index CFDs -- pre-registration (2026-10-03)

**Committed BEFORE any read of M1 outcomes.** Code: `scripts/research/edge_m1.py`; tests: `scripts/tests/test_edge_m1.py`
(hand-built bars only). Origin: docs/plans/2026-10-03-crypto-cfd-design.md (rank 2; CFD gap sweep item CFD-R1). Tradable on
FTMO, flat before the rollover (no swap, no weekend hold).

## 1. Hypothesis and source

Balanced (60/40-type) institutions rebalance at month-end; when stocks have beaten bonds month-to-date they must sell
equities in the last days of the month (and buy after the opposite), a price-insensitive flow that moves next-day equity
returns against the month's relative performance. Source: Harvey, Mazzoleni, Melone, "The Unintended Consequences of
Rebalancing" (NBER w33554, https://www.nber.org/system/files/working_papers/w33554/w33554.pdf): daily S&P 500 and 10-year
T-note futures 1997-09-10 -> 2023-03-17, predictability peaking in the last four days ("week4" = Dummy5Days), a one-SD rise in
the Calendar signal lowers next-day equity returns ~17 bp (a partial coefficient), one-day lag for international markets.
The traded object here (sign only, equity CFDs, FTMO costs) is NOT reported by the source: its size is unknown.

## 2. Data

- Prices: FTMO 1D server-day bars `data/history/ftmo/ohlcv.{SYM}.1D` (US500, USTEC, DE40, FRA40 from server day 2017-12-29;
  US30, AUS200 from 2019-02-08). Server day = 17:00 -> 17:00 New York; the 1D bar's open is the first quote after the daily
  break and its close the last quote before 17:00 New York.
- 10-year yield: FRED DGS10 (`scripts/import-fred-series.py` -> `data/history/fred/DGS10.json`), published ~16:15 ET (H.15);
  used with a ONE-business-day lag.
- NYSE business days: rule-based holiday calendar (New Year, MLK, Presidents, Good Friday, Memorial, Juneteenth from 2022,
  Independence, Labor, Thanksgiving, Christmas, with Saturday -> Friday and Sunday -> Monday observance) plus the two special
  closures in the window (2018-12-05, 2025-01-09; ICE press releases). Published in advance: point-in-time.
- Spreads: `ftmo_demo_2026_09_relspread` hourly median / p90 (scripts/real_costs.py).

## 3. Signal and events

- T(m) = the last NYSE business day of month m. For each NYSE business day t in {T-4, ..., T} of month m:
  R_E(t) = US500 close(t) / US500 close(T(m-1)) - 1; R_B(t) = -8.5 x (y(t-1) - y(T(m-1))) / 100 with y = DGS10 in percent
  (t-1 = the previous NYSE business day with a value; T(m-1) likewise); S(t) = 0.6 (1 + R_E) / (0.6 (1 + R_E) + 0.4 (1 + R_B))
  - 0.6. Position s(t) = -sign(S(t)) (no trade when S = 0).
- US members (US500, US30, USTEC) hold s(t) over the NEXT server day's open -> close; non-US members (DE40, FRA40, AUS200)
  over the server day after that (the source's one-day lag). Return days are therefore T-3 .. T+1 (US) and T-2 .. T+2 (non-US).
- A server day is used only if its 1D bar exists; a missing bar is a missing day, never filled.

## 4. Tests

- Per member, on its week-4 return days only: OLS r_d = c + gamma x s_d + e (r_d = open -> close server-day return). The
  intercept absorbs those calendar days' drift: that is the CALENDAR NULL (G7's positive month-end drift lands in c, not in
  gamma). H1: gamma > 0, one-sided, CR1 SE clustered by episode month.
- Net gate: mean(s_d x r_d) minus one round-trip spread (half at the entry UTC hour, half at the exit UTC hour) > 0.
- Family: T1 = US basket (equal-weight of US500, US30, USTEC on each day), T2 = US500, T3 = US30, T4 = USTEC, T5 = non-US basket.
  **BH m = 5, q = 0.10.** T1 is the decision test; T5 is promoted only by passing all three reads itself.

## 5. Reads (by episode month; each ONCE, each in its own commit)

| read | episodes | note |
|---|---|---|
| DISCOVERY | 2018-01 -> 2021-08 (44; US30 / AUS200 from 2019-03) | development data (research-ledger `cfd-development-pre-2024-03`); this signal never measured |
| CONFIRMATION | 2021-09 -> 2024-02 (30) | development data |
| EXPOSED | 2024-03 -> 2026-08 (30) | exposed by earlier selections; this signal never measured |

Thresholds: DISCOVERY -- CANDIDATE iff BH rejects T1 and net > 0. CONFIRMATION -- p < 0.05, net > 0, net > 0 at the p90 spread.
EXPOSED -- p < 0.10, net > 0. Zero survivors is a valid result.

## 6. Diagnostics outside the family

Equity-only signal (R_B = 0); the source's falsification (the same rule on non-week-4 days with the same weekday); the
first-business-day reversal (descriptive); return days T-3 .. T-1 only (days G7 never read); owner sizing: stop = 2.0 x the
trailing 20-server-day SD of open -> close returns (PIT), size = 1 % / stop, report stop hits and the net; daily P&L
correlation with fvg-book v3 (incl. crisis months).

## 7. Power

US500 open -> close SD ~114 bp per server day (unconditional; no outcome read). MDE at 80 % power ~21 bp (DISCOVERY), ~23 bp
(CONFIRMATION), ~20 bp (EXPOSED). Joint pass probability ~0.03 at a true 10 bp, ~0.13 at 15 bp, ~0.4 at 20 bp. A null is
"inconclusive at this power".

## 8. Prior reads (disclosed)

- G7 (F4) read days T and T+1 LONG in all three reads (positive nets US500 +4.1 / +9.1 / +6.6 bp; reframes R6(b)). The
  calendar null (intercept) is there so that drift cannot be credited to the signal.
- F3 H1 read the 20-day momentum sign on all days in all reads (momentum won in confirmation): relevant to the non-week-4
  diagnostic.
- The 2026-09-28 method diagnosis read ICT / Wyckoff full setups on 15m / 1H / 4H before 2024-03 (ledger: development).
- The design workflow computed unconditional SDs and episode counts only; the synthesis author read the NBER text, the H.15
  page and the head of the DGS10 file (1997), outside every window.
