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

## Amendment [M1-A1] (2026-10-04, before any read, outcome-blind)

Implementation choices where §2-§6 left room, fixed by the implementer and two adversarial reviewers BEFORE any M1 outcome
existed; also written into every read's meta (`scripts/research/edge_m1.py` RESOLVED_AMBIGUITIES). Two corrections to §2 are
among them: the DGS10 value for day d is posted by H.15 at 16:15 ET on the NEXT Board business day (not the same day), and the
FTMO spread table's hour buckets are server hour minus the export-time offset (not true UTC hours). The 1H-clock defect of
2021-01-20 .. 2021-03-26 (item 15) is kept as flagged and counted, not re-priced.

1. Return days (§3): US = the 1st NYSE business day after t; non-US = the 2nd WEEKDAY (Mon-Fri server day) after t, i.e. 'the server day after that' counted in the non-US markets' own server days, so the non-US lag is two sessions in every week (an NYSE-only holiday such as Memorial Day or Thanksgiving is a normal European / Australian session, not a skipped day). A missing member bar on that day is a missing day, never filled or shifted. The pre-registration's 'T-2 .. T+2 (non-US)' holds in NYSE-day terms except across an NYSE-only holiday; a CFD bar on an NYSE holiday is never a US return day. (Fix round 2026-10-03, before any read: NYSE counting held 31/264 discovery non-US decisions 3+ sessions.)
2. y(t-1) (§3) = DGS10 at the latest NYSE business day d < t that has a value AND whose H.15 posting day is <= t: the H.15 is 'posted daily Monday through Friday at 4:15pm' and 'not posted on holidays or in the event that the Board is closed' (federalreserve.gov/releases/h15, release of 2026-10-02, which holds data through 2026-10-01), so the value for d is posted at 16:15 ET on the next Board business day after d (BoardCalendar) and is usable at a decision at t's close (17:00 New York) only when that day is <= t. On an NYSE day the Board is closed (Columbus, Veterans, Juneteenth 2021, a Saturday New Year observed on Dec 31, Board closures) y(t-1) is therefore the value one day older. y(T(m-1)) = DGS10 at the latest NYSE business day ON OR before T(m-1) with a value (posted weeks before every t; asserted). Values dated on non-NYSE days are ignored. DGS10.json's `_pit` header ('published ~16:15 ET that day') is wrong and is NOT used.
3. A member's episode m counts only when the member's first 1D bar is on or before T(m-1) (its history covers the episode); this is what gives §5's 'US30 / AUS200 from 2019-03' (their first bar is server day 2019-02-08, a partial day).
4. Baskets (T1, T5): on each return day, the equal-weight mean of the members that have a bar that day (return and cost).
5. T1 is the decision test; T2-T4 carry their own BH / threshold verdicts for the record but decide nothing; T5 is promoted only by passing all three reads itself.
6. Entry / exit hours for the spread (§4 'half at the entry UTC hour, half at the exit UTC hour'): the SERVER-clock hours of the server day's FIRST and LAST 1H bar (the 1D open is the first quote after the daily break, its close the last quote before 17:00 New York) when the day has >= 4 1H bars; otherwise (the D1-filled early 1H history: one bar per day, US500 / USTEC / FRA40 to 2021-01, DE40 to 2021-05; or no 1H bar) the server-clock constants 01:00 / 23:00 (FALLBACK_SERVER_HOURS), which equal every member's modal intraday hours in every DST regime (QA, refused otherwise) -- no later-era data enters the cost hours. Cost hours only: the return always comes from the 1D bar. The true UTC hours are written to each row for audit.
7. Cost-table hour frame: the spread table (ExportSymbolSpec.mq5) buckets every M15 bar by `TimeToStruct(r[k].time - offset)` with offset = the server-GMT offset AT EXPORT (`_server_utc_offset_sec_now` = 10800 s, 2026-09-28) -- its header: 'the hour buckets use the CURRENT server-GMT offset ... (a DST shift moves a bucket by one hour -- disclosed, not corrected here)'. So table 'UTC hour' h holds SERVER hour (h + 3) mod 24 all year (US500 / DE40 bucket 21 = server 00:00, the daily break, n = 0). A leg at server hour H is priced at bucket (H - offset) mod 24 (TableCosts), i.e. (22, 20) for 01:00 / 23:00 in winter and summer alike, NOT at its true UTC hour (which would read server 02:00 / 00:00 in US standard time). A leg whose bucket has no recorded bars is priced at the symbol's overall spread (real_costs.spread_price 'overall_fallback'): counted per row (cost_fallback), per test and per member, never silent.
8. CR1 for the OLS slope = Cameron-Miller sandwich with G/(G-1) x (N-1)/(N-K), K = 2, Student-t with G-1 df (edge_census.cr1 on the influence values supplies the G/(G-1) part).
9. Falsification (§6): non-week-4 NYSE business days of the same month m with the same weekday as a week-4 day (t - 7k, k >= 1), with the same S(t) formula and month-to-date base T(m-1), held as in §3 -- and a placebo row of group g is kept only when its return day is BEFORE T-4 of month m (return_day(t, g) < week4[0]), so no placebo return lands in the month-end window it is meant to exclude (T-5 / T-6 hold over T-4 / T-3). Dropped rows are counted in `skipped`.
10. First-business-day reversal (§6, descriptive): the source's Sec. 4 rule 'on the first business day of a new month the modified Calendar signal is set to sign(Calendar Signal_-4)': position +sign(S(T-4)) decided at T+1, held over the next server day as in §3 (US: T+2; non-US: the 2nd weekday after T+1).
11. Return days T-3 .. T-1 only (§6): rows whose return day lies in [T-3, T-1] (dates, so a non-US return day on an NYSE-only holiday inside that range counts).
12. Owner sizing (§6): a stop hit when the day's adverse excursion from the open reaches the stop, filled AT the stop (a 1D bar cannot show a gap through it). The trailing 20-server-day SD uses WEEKDAY bars only, and for US members not NYSE holidays (stub CFD sessions that would shrink the SD); non-US exchange holidays are not modelled (no calendar).
13. Data quality: weekend-dated 1D bars (DE40: 20 Sunday-dated bars 2018-01-07 .. 2018-05-27, when its Monday open is not the first quote after the weekend) are FLAGGED, not excluded: meta.data_quality_flags lists the read's affected episodes and their row counts; any exclusion is a pre-registration decision for the lead.
14. Crisis months (§6): the months of the read's return-day span whose US500 SD of server-day open->close returns (sd-eligible days inside the span only) is in the top fifth (rounded up), counting only months with >= 10 such days (the span's partial edge months, 1-4 days, cannot be ranked by noise).
15. 1H clock QA (flagged, not corrected): the US500, USTEC and FRA40 1H files hold a whole session one hour early ((00:00, 22:00) server) on 2021-01-20 .. 2021-03-26, while US30 (same session, same broker) holds (01:00, 23:00) on the same days -- most likely a one-hour label shift in that 1H segment (outcome-blind dry run 2026-10-03). Those days are priced at their 1H hours as the rule above says (the 00:00 entry leg lands in the empty break bucket and is counted as an overall fallback); each read counts them per member (cost_hours_shifted_minus_1h_rows). Re-pricing them at the server-clock constant would be a pre-registered data-quality rule for the lead to decide. The same counter also counts AUS200's 84 (00:00, 22:00) days of 2025-11 .. 2026-03 (its Australian-summer regime, where such sessions are common: not this defect; AUS200's table has no empty bucket).
16. 1D bars whose server day had not ended at the file's _exported_at_utc are dropped as incomplete (counted).
17. Period edges: §5 assigns rows by EPISODE month, so a read's return days run past its last episode month (discovery to 2021-09-03, confirmation to 2024-03-05). The confirmation read's return days on/after 2024-03-01 lie in the ledger's oos_exposed period cfd-prop-search-2024-03-2025-03, outside 'cfd-development-pre-2024-03': each read writes them to meta.return_days_after_dev_cutoff and its exact return-day span to meta.return_day_span.
18. Snapshot: a confirmation / exposed read records whether each member's 1D / 1H / cost-spec digest and DGS10's digest equal the prior read's (meta.snapshot_matches_prior); a mismatch is recorded and printed, not refused (a re-export that only appends later bars changes the digest).
