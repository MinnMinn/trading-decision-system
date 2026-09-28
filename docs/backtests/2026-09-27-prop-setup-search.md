# Prop-challenge pre-registered setup search -- report

_Source: `docs/plans/2026-09-27-prop-setup-search-preregistration.md`. Plan: `docs/experiments/prop-search-2026-09-27/plan.json` (180 candidates, hash 8137a8b1a76c)._

Budget spent: **180 / 200** candidates evaluated. Passes found: **0 / 5** (the target is a goal, not a stopping rule beyond whichever of the two comes first).

## Pass criteria (verbatim from the pre-registration, §2, and addendum §8)

1. `prop_pass_probability` >= 0.7 under BOTH `ftmo-challenge-phase1` AND `the5ers-high-stakes-step1`, each fund judged on its own, at a 120-trading-day horizon (addendum §8.1 -- [30, 60, 261]-day horizons are also recorded per candidate for information and never gate).
2. Each fund's OWN day-count rule: FTMO requires >= 4 days a trade was INITIATED; The5ers requires >= 3 PROFITABLE days (closed profit >= 0.5% of initial balance that day) and fails on 30 consecutive calendar days with no trade (addendum §8.3) -- and the bootstrap has the sample it needs to run at all (n >= 5).
3. The one-sided 90% bootstrap lower bound of mean net R on the validation trades is > 0. There is NO fixed minimum trade count beyond that. Validation trades whose true outcome would need a bar after the PIT cutoff are excluded from this and every other criterion (addendum §8.2).

## Multiple-testing caveat

180 candidates were evaluated on the SAME validation window in the search for these passes (CLAUDE.md §43/§45: repeated selection over one window inflates the apparent hit rate above what any single candidate's own numbers suggest). A PASS here is a candidate that cleared the pre-registered bar on the first and only look this search grants the validation window -- it is NOT yet forward-confirmed (`docs/plans/2026-09-27-prop-setup-search-preregistration.md` §4: forward confirmation on live demo is required before any funded attempt), and the validation window is EXPOSED as of 2026-09-28T03:21:17Z (first record: `ICT-A-15m-XAUUSD`).

## Every evaluated candidate

| # | id | method | config | tf | group | prop_pass_probability (FTMO / The5ers) | day count (FTMO trading / The5ers profitable) | excluded unfinished | expectancy LB (net R) | PASS |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | ICT-A-15m-AUS200 | ICT | A | 15m | instrument=AUS200 | n/a / n/a | 3 / 1 | 0 | n/a | fail |
| 2 | ICT-A-15m-DE40 | ICT | A | 15m | instrument=DE40 | n/a / n/a | 3 / 1 | 0 | n/a | fail |
| 3 | ICT-A-15m-FRA40 | ICT | A | 15m | instrument=FRA40 | n/a / n/a | 3 / 0 | 0 | n/a | fail |
| 4 | ICT-A-15m-US30 | ICT | A | 15m | instrument=US30 | n/a / n/a | 1 / 0 | 0 | n/a | fail |
| 5 | ICT-A-15m-US500 | ICT | A | 15m | instrument=US500 | 0.29 / 0.35 | 6 / 2 | 0 | -0.939 | fail |
| 6 | ICT-A-15m-USTEC | ICT | A | 15m | instrument=USTEC | 0.01 / 0.03 | 11 / 1 | 0 | -1.232 | fail |
| 7 | ICT-A-15m-XAGUSD | ICT | A | 15m | instrument=XAGUSD | 0.86 / 0.87 | 8 / 3 | 0 | -0.716 | fail |
| 8 | ICT-A-15m-XAUUSD | ICT | A | 15m | instrument=XAUUSD | 0.00 / 0.00 | 5 / 0 | 0 | -1.579 | fail |
| 9 | ICT-A-15m-indices | ICT | A | 15m | asset_class=indices | 0.08 / 0.12 | 23 / 5 | 0 | -0.796 | fail |
| 10 | ICT-A-15m-metals | ICT | A | 15m | asset_class=metals | 0.11 / 0.16 | 13 / 3 | 0 | -1.043 | fail |
| 11 | ICT-A-1H-AUS200 | ICT | A | 1H | instrument=AUS200 | n/a / n/a | 2 / 1 | 0 | n/a | fail |
| 12 | ICT-A-1H-DE40 | ICT | A | 1H | instrument=DE40 | n/a / n/a | 2 / 0 | 0 | n/a | fail |
| 13 | ICT-A-1H-FRA40 | ICT | A | 1H | instrument=FRA40 | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 14 | ICT-A-1H-US30 | ICT | A | 1H | instrument=US30 | n/a / n/a | 1 / 0 | 0 | n/a | fail |
| 15 | ICT-A-1H-US500 | ICT | A | 1H | instrument=US500 | n/a / n/a | 3 / 0 | 0 | n/a | fail |
| 16 | ICT-A-1H-USTEC | ICT | A | 1H | instrument=USTEC | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 17 | ICT-A-1H-XAGUSD | ICT | A | 1H | instrument=XAGUSD | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 18 | ICT-A-1H-XAUUSD | ICT | A | 1H | instrument=XAUUSD | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 19 | ICT-A-1H-indices | ICT | A | 1H | asset_class=indices | 0.00 / 0.00 | 8 / 1 | 0 | -1.374 | fail |
| 20 | ICT-A-1H-metals | ICT | A | 1H | asset_class=metals | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 21 | ICT-A-4H-AUS200 | ICT | A | 4H | instrument=AUS200 | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 22 | ICT-A-4H-DE40 | ICT | A | 4H | instrument=DE40 | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 23 | ICT-A-4H-FRA40 | ICT | A | 4H | instrument=FRA40 | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 24 | ICT-A-4H-US30 | ICT | A | 4H | instrument=US30 | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 25 | ICT-A-4H-US500 | ICT | A | 4H | instrument=US500 | n/a / n/a | 1 / 0 | 0 | n/a | fail |
| 26 | ICT-A-4H-USTEC | ICT | A | 4H | instrument=USTEC | n/a / n/a | 1 / 0 | 0 | n/a | fail |
| 27 | ICT-A-4H-XAGUSD | ICT | A | 4H | instrument=XAGUSD | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 28 | ICT-A-4H-XAUUSD | ICT | A | 4H | instrument=XAUUSD | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 29 | ICT-A-4H-indices | ICT | A | 4H | asset_class=indices | n/a / n/a | 2 / 0 | 0 | n/a | fail |
| 30 | ICT-A-4H-metals | ICT | A | 4H | asset_class=metals | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 31 | ICT-B-15m-AUS200 | ICT | B | 15m | instrument=AUS200 | n/a / n/a | 3 / 1 | 0 | n/a | fail |
| 32 | ICT-B-15m-DE40 | ICT | B | 15m | instrument=DE40 | n/a / n/a | 3 / 1 | 0 | n/a | fail |
| 33 | ICT-B-15m-FRA40 | ICT | B | 15m | instrument=FRA40 | n/a / n/a | 3 / 0 | 0 | n/a | fail |
| 34 | ICT-B-15m-US30 | ICT | B | 15m | instrument=US30 | n/a / n/a | 1 / 0 | 0 | n/a | fail |
| 35 | ICT-B-15m-US500 | ICT | B | 15m | instrument=US500 | 0.34 / 0.41 | 6 / 2 | 0 | -0.929 | fail |
| 36 | ICT-B-15m-USTEC | ICT | B | 15m | instrument=USTEC | 0.01 / 0.02 | 11 / 1 | 0 | -1.154 | fail |
| 37 | ICT-B-15m-XAGUSD | ICT | B | 15m | instrument=XAGUSD | 0.63 / 0.67 | 8 / 2 | 0 | -0.742 | fail |
| 38 | ICT-B-15m-XAUUSD | ICT | B | 15m | instrument=XAUUSD | 0.00 / 0.00 | 5 / 0 | 0 | -1.579 | fail |
| 39 | ICT-B-15m-indices | ICT | B | 15m | asset_class=indices | 0.06 / 0.10 | 23 / 5 | 0 | -0.817 | fail |
| 40 | ICT-B-15m-metals | ICT | B | 15m | asset_class=metals | 0.03 / 0.06 | 13 / 2 | 0 | -1.066 | fail |
| 41 | ICT-B-1H-AUS200 | ICT | B | 1H | instrument=AUS200 | n/a / n/a | 2 / 1 | 0 | n/a | fail |
| 42 | ICT-B-1H-DE40 | ICT | B | 1H | instrument=DE40 | n/a / n/a | 2 / 0 | 0 | n/a | fail |
| 43 | ICT-B-1H-FRA40 | ICT | B | 1H | instrument=FRA40 | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 44 | ICT-B-1H-US30 | ICT | B | 1H | instrument=US30 | n/a / n/a | 1 / 0 | 0 | n/a | fail |
| 45 | ICT-B-1H-US500 | ICT | B | 1H | instrument=US500 | n/a / n/a | 3 / 0 | 0 | n/a | fail |
| 46 | ICT-B-1H-USTEC | ICT | B | 1H | instrument=USTEC | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 47 | ICT-B-1H-XAGUSD | ICT | B | 1H | instrument=XAGUSD | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 48 | ICT-B-1H-XAUUSD | ICT | B | 1H | instrument=XAUUSD | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 49 | ICT-B-1H-indices | ICT | B | 1H | asset_class=indices | 0.00 / 0.00 | 8 / 1 | 0 | -1.020 | fail |
| 50 | ICT-B-1H-metals | ICT | B | 1H | asset_class=metals | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 51 | ICT-B-4H-AUS200 | ICT | B | 4H | instrument=AUS200 | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 52 | ICT-B-4H-DE40 | ICT | B | 4H | instrument=DE40 | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 53 | ICT-B-4H-FRA40 | ICT | B | 4H | instrument=FRA40 | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 54 | ICT-B-4H-US30 | ICT | B | 4H | instrument=US30 | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 55 | ICT-B-4H-US500 | ICT | B | 4H | instrument=US500 | n/a / n/a | 1 / 0 | 0 | n/a | fail |
| 56 | ICT-B-4H-USTEC | ICT | B | 4H | instrument=USTEC | n/a / n/a | 1 / 0 | 0 | n/a | fail |
| 57 | ICT-B-4H-XAGUSD | ICT | B | 4H | instrument=XAGUSD | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 58 | ICT-B-4H-XAUUSD | ICT | B | 4H | instrument=XAUUSD | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 59 | ICT-B-4H-indices | ICT | B | 4H | asset_class=indices | n/a / n/a | 2 / 0 | 0 | n/a | fail |
| 60 | ICT-B-4H-metals | ICT | B | 4H | asset_class=metals | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 61 | ICT-C-15m-AUS200 | ICT | C | 15m | instrument=AUS200 | n/a / n/a | 2 / 1 | 0 | n/a | fail |
| 62 | ICT-C-15m-DE40 | ICT | C | 15m | instrument=DE40 | n/a / n/a | 1 / 0 | 0 | n/a | fail |
| 63 | ICT-C-15m-FRA40 | ICT | C | 15m | instrument=FRA40 | n/a / n/a | 2 / 0 | 0 | n/a | fail |
| 64 | ICT-C-15m-US30 | ICT | C | 15m | instrument=US30 | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 65 | ICT-C-15m-US500 | ICT | C | 15m | instrument=US500 | n/a / n/a | 1 / 0 | 0 | n/a | fail |
| 66 | ICT-C-15m-USTEC | ICT | C | 15m | instrument=USTEC | n/a / n/a | 3 / 1 | 0 | n/a | fail |
| 67 | ICT-C-15m-XAGUSD | ICT | C | 15m | instrument=XAGUSD | n/a / n/a | 4 / 1 | 0 | n/a | fail |
| 68 | ICT-C-15m-XAUUSD | ICT | C | 15m | instrument=XAUUSD | n/a / n/a | 3 / 0 | 0 | n/a | fail |
| 69 | ICT-C-15m-indices | ICT | C | 15m | asset_class=indices | 0.40 / 0.46 | 9 / 2 | 0 | -0.861 | fail |
| 70 | ICT-C-15m-metals | ICT | C | 15m | asset_class=metals | 0.01 / 0.02 | 7 / 1 | 0 | -1.259 | fail |
| 71 | ICT-C-1H-AUS200 | ICT | C | 1H | instrument=AUS200 | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 72 | ICT-C-1H-DE40 | ICT | C | 1H | instrument=DE40 | n/a / n/a | 1 / 0 | 0 | n/a | fail |
| 73 | ICT-C-1H-FRA40 | ICT | C | 1H | instrument=FRA40 | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 74 | ICT-C-1H-US30 | ICT | C | 1H | instrument=US30 | n/a / n/a | 1 / 0 | 0 | n/a | fail |
| 75 | ICT-C-1H-US500 | ICT | C | 1H | instrument=US500 | n/a / n/a | 1 / 0 | 0 | n/a | fail |
| 76 | ICT-C-1H-USTEC | ICT | C | 1H | instrument=USTEC | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 77 | ICT-C-1H-XAGUSD | ICT | C | 1H | instrument=XAGUSD | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 78 | ICT-C-1H-XAUUSD | ICT | C | 1H | instrument=XAUUSD | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 79 | ICT-C-1H-indices | ICT | C | 1H | asset_class=indices | n/a / n/a | 3 / 0 | 0 | n/a | fail |
| 80 | ICT-C-1H-metals | ICT | C | 1H | asset_class=metals | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 81 | ICT-C-4H-AUS200 | ICT | C | 4H | instrument=AUS200 | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 82 | ICT-C-4H-DE40 | ICT | C | 4H | instrument=DE40 | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 83 | ICT-C-4H-FRA40 | ICT | C | 4H | instrument=FRA40 | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 84 | ICT-C-4H-US30 | ICT | C | 4H | instrument=US30 | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 85 | ICT-C-4H-US500 | ICT | C | 4H | instrument=US500 | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 86 | ICT-C-4H-USTEC | ICT | C | 4H | instrument=USTEC | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 87 | ICT-C-4H-XAGUSD | ICT | C | 4H | instrument=XAGUSD | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 88 | ICT-C-4H-XAUUSD | ICT | C | 4H | instrument=XAUUSD | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 89 | ICT-C-4H-indices | ICT | C | 4H | asset_class=indices | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 90 | ICT-C-4H-metals | ICT | C | 4H | asset_class=metals | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 91 | WYCKOFF-BOOK-A-15m-AUS200 | WYCKOFF-BOOK | A | 15m | instrument=AUS200 | 0.05 / 0.07 | 11 / 3 | 0 | -1.329 | fail |
| 92 | WYCKOFF-BOOK-A-15m-DE40 | WYCKOFF-BOOK | A | 15m | instrument=DE40 | n/a / n/a | 3 / 2 | 0 | n/a | fail |
| 93 | WYCKOFF-BOOK-A-15m-FRA40 | WYCKOFF-BOOK | A | 15m | instrument=FRA40 | 0.05 / 0.08 | 5 / 2 | 0 | -1.169 | fail |
| 94 | WYCKOFF-BOOK-A-15m-US30 | WYCKOFF-BOOK | A | 15m | instrument=US30 | n/a / n/a | 3 / 0 | 0 | n/a | fail |
| 95 | WYCKOFF-BOOK-A-15m-US500 | WYCKOFF-BOOK | A | 15m | instrument=US500 | 0.21 / 0.26 | 7 / 2 | 0 | -1.007 | fail |
| 96 | WYCKOFF-BOOK-A-15m-USTEC | WYCKOFF-BOOK | A | 15m | instrument=USTEC | 0.07 / 0.10 | 10 / 2 | 0 | -1.276 | fail |
| 97 | WYCKOFF-BOOK-A-15m-XAGUSD | WYCKOFF-BOOK | A | 15m | instrument=XAGUSD | 0.04 / 0.07 | 18 / 3 | 1 | -1.052 | fail |
| 98 | WYCKOFF-BOOK-A-15m-XAUUSD | WYCKOFF-BOOK | A | 15m | instrument=XAUUSD | 0.00 / 0.00 | 9 / 1 | 0 | -1.807 | fail |
| 99 | WYCKOFF-BOOK-A-15m-indices | WYCKOFF-BOOK | A | 15m | asset_class=indices | 0.05 / 0.09 | 36 / 11 | 0 | -0.830 | fail |
| 100 | WYCKOFF-BOOK-A-15m-metals | WYCKOFF-BOOK | A | 15m | asset_class=metals | 0.01 / 0.02 | 26 / 4 | 1 | -1.179 | fail |
| 101 | WYCKOFF-BOOK-A-1H-AUS200 | WYCKOFF-BOOK | A | 1H | instrument=AUS200 | 0.00 / 0.00 | 5 / 0 | 0 | -1.458 | fail |
| 102 | WYCKOFF-BOOK-A-1H-DE40 | WYCKOFF-BOOK | A | 1H | instrument=DE40 | n/a / n/a | 2 / 1 | 0 | n/a | fail |
| 103 | WYCKOFF-BOOK-A-1H-FRA40 | WYCKOFF-BOOK | A | 1H | instrument=FRA40 | 0.94 / 0.94 | 5 / 2 | 0 | -0.695 | fail |
| 104 | WYCKOFF-BOOK-A-1H-US30 | WYCKOFF-BOOK | A | 1H | instrument=US30 | n/a / n/a | 2 / 1 | 0 | n/a | fail |
| 105 | WYCKOFF-BOOK-A-1H-US500 | WYCKOFF-BOOK | A | 1H | instrument=US500 | n/a / n/a | 3 / 1 | 0 | n/a | fail |
| 106 | WYCKOFF-BOOK-A-1H-USTEC | WYCKOFF-BOOK | A | 1H | instrument=USTEC | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 107 | WYCKOFF-BOOK-A-1H-XAGUSD | WYCKOFF-BOOK | A | 1H | instrument=XAGUSD | 0.80 / 0.79 | 5 / 1 | 0 | -1.147 | fail |
| 108 | WYCKOFF-BOOK-A-1H-XAUUSD | WYCKOFF-BOOK | A | 1H | instrument=XAUUSD | n/a / n/a | 4 / 1 | 0 | n/a | fail |
| 109 | WYCKOFF-BOOK-A-1H-indices | WYCKOFF-BOOK | A | 1H | asset_class=indices | 0.38 / 0.45 | 17 / 5 | 0 | -0.701 | fail |
| 110 | WYCKOFF-BOOK-A-1H-metals | WYCKOFF-BOOK | A | 1H | asset_class=metals | 0.60 / 0.61 | 9 / 2 | 0 | -1.155 | fail |
| 111 | WYCKOFF-BOOK-A-4H-AUS200 | WYCKOFF-BOOK | A | 4H | instrument=AUS200 | n/a / n/a | 2 / 1 | 0 | n/a | fail |
| 112 | WYCKOFF-BOOK-A-4H-DE40 | WYCKOFF-BOOK | A | 4H | instrument=DE40 | n/a / n/a | 1 / 0 | 0 | n/a | fail |
| 113 | WYCKOFF-BOOK-A-4H-FRA40 | WYCKOFF-BOOK | A | 4H | instrument=FRA40 | n/a / n/a | 1 / 0 | 0 | n/a | fail |
| 114 | WYCKOFF-BOOK-A-4H-US30 | WYCKOFF-BOOK | A | 4H | instrument=US30 | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 115 | WYCKOFF-BOOK-A-4H-US500 | WYCKOFF-BOOK | A | 4H | instrument=US500 | n/a / n/a | 2 / 2 | 0 | n/a | fail |
| 116 | WYCKOFF-BOOK-A-4H-USTEC | WYCKOFF-BOOK | A | 4H | instrument=USTEC | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 117 | WYCKOFF-BOOK-A-4H-XAGUSD | WYCKOFF-BOOK | A | 4H | instrument=XAGUSD | n/a / n/a | 2 / 0 | 0 | n/a | fail |
| 118 | WYCKOFF-BOOK-A-4H-XAUUSD | WYCKOFF-BOOK | A | 4H | instrument=XAUUSD | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 119 | WYCKOFF-BOOK-A-4H-indices | WYCKOFF-BOOK | A | 4H | asset_class=indices | 0.96 / 0.96 | 6 / 3 | 0 | -0.591 | fail |
| 120 | WYCKOFF-BOOK-A-4H-metals | WYCKOFF-BOOK | A | 4H | asset_class=metals | n/a / n/a | 2 / 0 | 0 | n/a | fail |
| 121 | WYCKOFF-BOOK-B-15m-AUS200 | WYCKOFF-BOOK | B | 15m | instrument=AUS200 | 0.02 / 0.03 | 11 / 2 | 0 | -1.239 | fail |
| 122 | WYCKOFF-BOOK-B-15m-DE40 | WYCKOFF-BOOK | B | 15m | instrument=DE40 | n/a / n/a | 3 / 1 | 0 | n/a | fail |
| 123 | WYCKOFF-BOOK-B-15m-FRA40 | WYCKOFF-BOOK | B | 15m | instrument=FRA40 | 0.05 / 0.08 | 5 / 2 | 0 | -1.169 | fail |
| 124 | WYCKOFF-BOOK-B-15m-US30 | WYCKOFF-BOOK | B | 15m | instrument=US30 | n/a / n/a | 3 / 0 | 0 | n/a | fail |
| 125 | WYCKOFF-BOOK-B-15m-US500 | WYCKOFF-BOOK | B | 15m | instrument=US500 | 0.02 / 0.03 | 7 / 1 | 0 | -0.970 | fail |
| 126 | WYCKOFF-BOOK-B-15m-USTEC | WYCKOFF-BOOK | B | 15m | instrument=USTEC | 0.21 / 0.27 | 10 / 2 | 0 | -0.897 | fail |
| 127 | WYCKOFF-BOOK-B-15m-XAGUSD | WYCKOFF-BOOK | B | 15m | instrument=XAGUSD | 0.02 / 0.04 | 18 / 2 | 1 | -1.013 | fail |
| 128 | WYCKOFF-BOOK-B-15m-XAUUSD | WYCKOFF-BOOK | B | 15m | instrument=XAUUSD | 0.00 / 0.00 | 9 / 0 | 0 | -1.685 | fail |
| 129 | WYCKOFF-BOOK-B-15m-indices | WYCKOFF-BOOK | B | 15m | asset_class=indices | 0.03 / 0.04 | 36 / 8 | 0 | -0.807 | fail |
| 130 | WYCKOFF-BOOK-B-15m-metals | WYCKOFF-BOOK | B | 15m | asset_class=metals | 0.00 / 0.00 | 26 / 2 | 1 | -1.188 | fail |
| 131 | WYCKOFF-BOOK-B-1H-AUS200 | WYCKOFF-BOOK | B | 1H | instrument=AUS200 | 0.00 / 0.00 | 5 / 0 | 0 | -1.458 | fail |
| 132 | WYCKOFF-BOOK-B-1H-DE40 | WYCKOFF-BOOK | B | 1H | instrument=DE40 | n/a / n/a | 2 / 1 | 0 | n/a | fail |
| 133 | WYCKOFF-BOOK-B-1H-FRA40 | WYCKOFF-BOOK | B | 1H | instrument=FRA40 | 0.99 / 0.99 | 5 / 2 | 0 | -0.539 | fail |
| 134 | WYCKOFF-BOOK-B-1H-US30 | WYCKOFF-BOOK | B | 1H | instrument=US30 | n/a / n/a | 2 / 1 | 0 | n/a | fail |
| 135 | WYCKOFF-BOOK-B-1H-US500 | WYCKOFF-BOOK | B | 1H | instrument=US500 | n/a / n/a | 3 / 1 | 0 | n/a | fail |
| 136 | WYCKOFF-BOOK-B-1H-USTEC | WYCKOFF-BOOK | B | 1H | instrument=USTEC | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 137 | WYCKOFF-BOOK-B-1H-XAGUSD | WYCKOFF-BOOK | B | 1H | instrument=XAGUSD | 0.80 / 0.79 | 5 / 1 | 0 | -1.147 | fail |
| 138 | WYCKOFF-BOOK-B-1H-XAUUSD | WYCKOFF-BOOK | B | 1H | instrument=XAUUSD | n/a / n/a | 4 / 1 | 0 | n/a | fail |
| 139 | WYCKOFF-BOOK-B-1H-indices | WYCKOFF-BOOK | B | 1H | asset_class=indices | 0.54 / 0.59 | 17 / 5 | 0 | -0.555 | fail |
| 140 | WYCKOFF-BOOK-B-1H-metals | WYCKOFF-BOOK | B | 1H | asset_class=metals | 0.70 / 0.71 | 9 / 2 | 0 | -0.919 | fail |
| 141 | WYCKOFF-BOOK-B-4H-AUS200 | WYCKOFF-BOOK | B | 4H | instrument=AUS200 | n/a / n/a | 2 / 1 | 0 | n/a | fail |
| 142 | WYCKOFF-BOOK-B-4H-DE40 | WYCKOFF-BOOK | B | 4H | instrument=DE40 | n/a / n/a | 1 / 0 | 0 | n/a | fail |
| 143 | WYCKOFF-BOOK-B-4H-FRA40 | WYCKOFF-BOOK | B | 4H | instrument=FRA40 | n/a / n/a | 1 / 0 | 0 | n/a | fail |
| 144 | WYCKOFF-BOOK-B-4H-US30 | WYCKOFF-BOOK | B | 4H | instrument=US30 | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 145 | WYCKOFF-BOOK-B-4H-US500 | WYCKOFF-BOOK | B | 4H | instrument=US500 | n/a / n/a | 2 / 2 | 0 | n/a | fail |
| 146 | WYCKOFF-BOOK-B-4H-USTEC | WYCKOFF-BOOK | B | 4H | instrument=USTEC | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 147 | WYCKOFF-BOOK-B-4H-XAGUSD | WYCKOFF-BOOK | B | 4H | instrument=XAGUSD | n/a / n/a | 2 / 0 | 0 | n/a | fail |
| 148 | WYCKOFF-BOOK-B-4H-XAUUSD | WYCKOFF-BOOK | B | 4H | instrument=XAUUSD | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 149 | WYCKOFF-BOOK-B-4H-indices | WYCKOFF-BOOK | B | 4H | asset_class=indices | 1.00 / 1.00 | 6 / 3 | 0 | -0.190 | fail |
| 150 | WYCKOFF-BOOK-B-4H-metals | WYCKOFF-BOOK | B | 4H | asset_class=metals | n/a / n/a | 2 / 0 | 0 | n/a | fail |
| 151 | WYCKOFF-BOOK-C-15m-AUS200 | WYCKOFF-BOOK | C | 15m | instrument=AUS200 | n/a / n/a | 2 / 1 | 0 | n/a | fail |
| 152 | WYCKOFF-BOOK-C-15m-DE40 | WYCKOFF-BOOK | C | 15m | instrument=DE40 | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 153 | WYCKOFF-BOOK-C-15m-FRA40 | WYCKOFF-BOOK | C | 15m | instrument=FRA40 | n/a / n/a | 3 / 1 | 0 | n/a | fail |
| 154 | WYCKOFF-BOOK-C-15m-US30 | WYCKOFF-BOOK | C | 15m | instrument=US30 | n/a / n/a | 1 / 0 | 0 | n/a | fail |
| 155 | WYCKOFF-BOOK-C-15m-US500 | WYCKOFF-BOOK | C | 15m | instrument=US500 | n/a / n/a | 1 / 0 | 0 | n/a | fail |
| 156 | WYCKOFF-BOOK-C-15m-USTEC | WYCKOFF-BOOK | C | 15m | instrument=USTEC | 0.13 / 0.17 | 5 / 1 | 0 | -1.549 | fail |
| 157 | WYCKOFF-BOOK-C-15m-XAGUSD | WYCKOFF-BOOK | C | 15m | instrument=XAGUSD | 0.03 / 0.05 | 7 / 1 | 1 | -1.175 | fail |
| 158 | WYCKOFF-BOOK-C-15m-XAUUSD | WYCKOFF-BOOK | C | 15m | instrument=XAUUSD | 0.00 / 0.00 | 5 / 0 | 0 | -1.986 | fail |
| 159 | WYCKOFF-BOOK-C-15m-indices | WYCKOFF-BOOK | C | 15m | asset_class=indices | 0.03 / 0.06 | 12 / 3 | 0 | -1.194 | fail |
| 160 | WYCKOFF-BOOK-C-15m-metals | WYCKOFF-BOOK | C | 15m | asset_class=metals | 0.00 / 0.00 | 12 / 1 | 1 | -1.450 | fail |
| 161 | WYCKOFF-BOOK-C-1H-AUS200 | WYCKOFF-BOOK | C | 1H | instrument=AUS200 | n/a / n/a | 3 / 0 | 0 | n/a | fail |
| 162 | WYCKOFF-BOOK-C-1H-DE40 | WYCKOFF-BOOK | C | 1H | instrument=DE40 | n/a / n/a | 1 / 0 | 0 | n/a | fail |
| 163 | WYCKOFF-BOOK-C-1H-FRA40 | WYCKOFF-BOOK | C | 1H | instrument=FRA40 | n/a / n/a | 3 / 1 | 0 | n/a | fail |
| 164 | WYCKOFF-BOOK-C-1H-US30 | WYCKOFF-BOOK | C | 1H | instrument=US30 | n/a / n/a | 1 / 0 | 0 | n/a | fail |
| 165 | WYCKOFF-BOOK-C-1H-US500 | WYCKOFF-BOOK | C | 1H | instrument=US500 | n/a / n/a | 1 / 0 | 0 | n/a | fail |
| 166 | WYCKOFF-BOOK-C-1H-USTEC | WYCKOFF-BOOK | C | 1H | instrument=USTEC | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 167 | WYCKOFF-BOOK-C-1H-XAGUSD | WYCKOFF-BOOK | C | 1H | instrument=XAGUSD | n/a / n/a | 1 / 0 | 0 | n/a | fail |
| 168 | WYCKOFF-BOOK-C-1H-XAUUSD | WYCKOFF-BOOK | C | 1H | instrument=XAUUSD | n/a / n/a | 1 / 0 | 0 | n/a | fail |
| 169 | WYCKOFF-BOOK-C-1H-indices | WYCKOFF-BOOK | C | 1H | asset_class=indices | 0.00 / 0.00 | 9 / 1 | 0 | -1.223 | fail |
| 170 | WYCKOFF-BOOK-C-1H-metals | WYCKOFF-BOOK | C | 1H | asset_class=metals | n/a / n/a | 2 / 0 | 0 | n/a | fail |
| 171 | WYCKOFF-BOOK-C-4H-AUS200 | WYCKOFF-BOOK | C | 4H | instrument=AUS200 | n/a / n/a | 2 / 1 | 0 | n/a | fail |
| 172 | WYCKOFF-BOOK-C-4H-DE40 | WYCKOFF-BOOK | C | 4H | instrument=DE40 | n/a / n/a | 1 / 0 | 0 | n/a | fail |
| 173 | WYCKOFF-BOOK-C-4H-FRA40 | WYCKOFF-BOOK | C | 4H | instrument=FRA40 | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 174 | WYCKOFF-BOOK-C-4H-US30 | WYCKOFF-BOOK | C | 4H | instrument=US30 | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 175 | WYCKOFF-BOOK-C-4H-US500 | WYCKOFF-BOOK | C | 4H | instrument=US500 | n/a / n/a | 1 / 1 | 0 | n/a | fail |
| 176 | WYCKOFF-BOOK-C-4H-USTEC | WYCKOFF-BOOK | C | 4H | instrument=USTEC | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 177 | WYCKOFF-BOOK-C-4H-XAGUSD | WYCKOFF-BOOK | C | 4H | instrument=XAGUSD | n/a / n/a | 1 / 0 | 0 | n/a | fail |
| 178 | WYCKOFF-BOOK-C-4H-XAUUSD | WYCKOFF-BOOK | C | 4H | instrument=XAUUSD | n/a / n/a | 0 / 0 | 0 | n/a | fail |
| 179 | WYCKOFF-BOOK-C-4H-indices | WYCKOFF-BOOK | C | 4H | asset_class=indices | n/a / n/a | 4 / 2 | 0 | n/a | fail |
| 180 | WYCKOFF-BOOK-C-4H-metals | WYCKOFF-BOOK | C | 4H | asset_class=metals | n/a / n/a | 1 / 0 | 0 | n/a | fail |

## Passing candidates in detail

None of the 180 evaluated candidates passed. Reported as found -- no criterion was relaxed to manufacture a pass (docs/plans/2026-09-27-prop-setup-search-preregistration.md §3).
