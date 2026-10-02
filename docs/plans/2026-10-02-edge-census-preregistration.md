# Edge census -- pre-registration (2026-10-02, committed BEFORE any run on real data)

Parent: docs/audits/2026-10-02-strategic-diagnosis.md §5 step 3 (owner decision: goal = pass FTMO with ANY validated method;
go straight to the edge census). Code: `scripts/research/edge_census.py` at the commit that adds this file; tests:
`scripts/tests/test_edge_census.py` (synthetic bars only). Any change to the code, the family or the rules below after the first
real-data run is a disclosed amendment in this file, never a silent edit.

## 1. Question

Do simple, low-parameter market primitives -- the building blocks ICT/Wyckoff dress up, plus a few published intraday effects --
carry a forward-return signal on the FTMO CFDs that survives the broker's real spread? This is a SCREEN for book components
(diagnosis §5 step 4), not a trading system: no stop, no target, a fixed time exit, so almost nothing can be tuned.

## 2. Data and periods

- Symbols: the CFD analysis allowlist only (docs/architecture/instruments.json): XAUUSD, XAGUSD (metals); US500, US30, USTEC,
  DE40, FRA40, AUS200 (indices). FTMO-Demo 5m bars, `data/history/ftmo`.
- Development window only: bars strictly before 2024-03-01. [2024-03-01, ...) stays untouched here (it is exposed anyway, and a
  forward demo is the only pristine test).
- Dense server days only (>= 80 % of the symbol's median bars per day). A DETECTOR may use only the PREVIOUS day's density
  (point-in-time; whether the current day is complete needs its future bars).
- Per-symbol split by dates only: DISCOVERY = the first 60 % of the symbol's dense development days; CONFIRMATION = the last 40 %.
- Prior exposure, disclosed: the development window was read before for ICT/Wyckoff full setups (fund-search §0.1 table,
  diagnosis §7). E1/E3 (sweep-reclaim) and E5 (FVG retrace) are ICT primitives whose full-setup versions were read there; as
  single primitives with a time exit they have not been measured. E2/E4/E6/E7/E9 have never been measured in this repo.

## 3. Events (signal on a CLOSED bar; entry at the next bar's OPEN unless stated; exit at the close h bars later)

| id | event | direction |
|---|---|---|
| E1 | bar trades beyond the previous server day's high (low) and closes back inside | reversal |
| E2 | first bar of the day to close beyond the previous day's high (low) | continuation |
| E3 | 07-16 UTC bar trades beyond the 00-07 UTC range and closes back inside | reversal |
| E4 | 07-16 UTC first bar to close beyond the 00-07 UTC range | continuation |
| E5 | displacement 3-bar FVG (middle body >= 0.6 range, range >= 1.5 x 20-bar median); first retrace to the near edge within 24 bars, filled at the edge (or the bar open if it opened beyond) | continuation |
| E6 | indices: first close beyond the 15-min cash-open range within 2.5 h (US 09:30 New York, DE40 09:00 Berlin, FRA40 09:00 Paris, AUS200 10:00 Sydney) | continuation |
| E7 | indices: sign of (previous cash close -> open + 30 min); traded from close - 30 min to the close (Gao, Han, Li, Zhou 2018) | same sign |
| E9 | bar range >= 3 x 48-bar median, body >= 0.7 range | continuation |

One event per (symbol, server day, event, side): the first. Horizons h = 6 / 12 / 24 bars (30 / 60 / 120 min); E7 has its
own fixed 30 min. Trades whose exit falls on another server day (the broker rollover) are skipped and counted.

## 4. Measurement

- Signed forward return s*r; in bp and in volatility units z = s*r / (sigma_5m * sqrt(h)), sigma_5m = RMS of 5m log returns over
  the previous 20 dense days.
- Placebo: same symbol, same server minute-of-day, same h, same direction, mean over every dense day of the same period;
  excess = s*r - placebo (removes intraday seasonality).
- Cost: one full spread per round trip (half at the entry UTC hour, half at the exit hour), the broker's recorded spread scaled
  relatively (`ftmo_demo_2026_09_relspread`); p90 spread as stress. Commission is unknown and not modelled (disclosed).
- Statistic: CR1 cluster-robust SE by UTC date, Student-t with G - 1 df.

## 5. Family and decision rule (fixed now)

- FAMILY = 40 tests: E1-E5, E9 x {metals, indices} x 3 horizons (36), E6 indices x 3, E7 indices x 1.
- DISCOVERY: direction d = sign of the pooled mean excess z. A test is a CANDIDATE iff
  (a) Benjamini-Hochberg over the 40 two-sided p-values of the excess z at FDR q = 0.10 rejects it;
  (b) its mean NET return in direction d is > 0 bp;
  (c) the excess z has sign d in >= ceil(2m/3) of the m group symbols with >= 20 discovery events.
- CONFIRMATION (the last 40 %, read once): a candidate is CONFIRMED iff, in direction d, the excess z has a one-sided
  p < 0.05, the mean net return is > 0 bp, and the mean net return under the p90 spread is > 0 bp.
- A reversed direction (d = -1) is allowed: the event then trades the other way, decided on discovery only.
- Zero confirmed tests is a valid, reported result; nothing is relaxed to produce one.

## 6. What a CONFIRMED test is and is not

It is a candidate COMPONENT for the book (diagnosis §5 step 4): it then needs a trade rule (stop/size), the FTMO policy
simulation (step 5) and a separately pre-registered forward demo (step 6). It is not a validated strategy and not evidence of
a live edge; the development window is not pristine (§2).
