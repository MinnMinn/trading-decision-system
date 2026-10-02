# Engine-realism census (counts only), 2026-10-02

Scope: the symbols and decision timeframes of the declared cells (1m-metals, 1m-indices, 5m-metals), bars BEFORE the development cutoff 2024-03-01T00:00:00Z, read from `data/history/ftmo` by `scripts/research/engine_realism_census.py`. Counts only: no price, return, R, expectancy or win rate appears here.

Definitions: **flat** = open == high == low == close; **zero-vol** = `volume` is 0 or absent; **gap > 4d** = two consecutive bars more than 4 days apart (credited to the year of the bar that ends the gap; the weekend is ~2 days, so a count here is a holiday closure or a hole in the series).

## Findings (counts; for the coordinator)

1. **1m index series are sparse before 2021.** Bars per year before the series becomes dense (table "Bars"): US500 1 / 258 / 259 / 259 bars in
   2017-2020, then 109,335 in 2021; USTEC and FRA40 about the same; DE40 3 / 135 / 234 / 257 / 6,746 in 2017-2021 and 344,038 in 2022. First month with at
   least 10,000 1m bars: US500, USTEC, FRA40 2021-09; DE40 2022-01; US30 2019-02 (no sparse years); XAUUSD 2012-06, XAGUSD 2012-05. The plan prints
   `1m-indices dev start 2017-12-27T23:00:00Z (from data)`: that is the FIRST bar (a single 2017 bar for US500/USTEC/FRA40), not the first dense
   month, so folds 0-1 of the 1m-indices cell are almost empty for four of its five symbols. Reported, NOT changed (cells file, folds and thresholds
   are out of scope here): the owner/coordinator should decide whether `dev_start_override` for 1m-indices should be set to the first dense month before `declare`.
2. **Flat bars (O == H == L == C) are common in the early series.** XAUUSD 5m: 26 % of the bars in 2004, 27 % in 2005, 15 % in 2006, 5 % in 2007, then
   under 1 %; XAGUSD 1m: 4.1 % of all development bars (166,456), 10.7 % in 2014; XPDUSD 5m 4-6 % in 2017-2020; FRA40 1m 4.4 % and US500 1m 3.5 % in 2023.
   They are the sweep-extreme / first-FVG-candle cause of the zero-risk candidates (`docs/audits/2026-10-01-zero-risk.md`), already counted and refused by item 12.
3. **Zero-volume bars: none** (volume is tick volume, always at least 1).
4. **Gaps longer than 4 days** are few and mostly in the sparse start of a series: US30 1m 3 (2019, longest 17.1 d), DE40 1m 13 (2018-2023, longest 199 d in 2018;
   3 of them in the dense years 2022-2023), FRA40 1m 7 (2 in 2022-2023), XAUUSD 5m 2 (2005, 2006), XPTUSD and XPDUSD 5m 2 and 3 (2015-2016, longest 124.3 d). XAUUSD/XAGUSD 1m: none (longest 3.2 d).

## Flat bars (O == H == L == C)

| symbol | tf | total | 2004 | 2005 | 2006 | 2007 | 2008 | 2009 | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| XAUUSD | 1m | 16561 |  |  |  |  |  |  |  |  | 668 | 1792 | 3468 | 3481 | 928 | 566 | 831 | 2552 | 771 | 566 | 424 | 452 | 62 |
| XAGUSD | 1m | 166456 |  |  |  |  |  |  |  |  | 6691 | 17230 | 36486 | 28360 | 15275 | 9020 | 7776 | 15314 | 7607 | 7307 | 5277 | 8299 | 1814 |
| US500 | 1m | 19494 |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 | 0 | 1 | 0 | 2173 | 2477 | 11974 | 2869 |
| US30 | 1m | 7102 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 1522 | 2269 | 2064 | 226 | 899 | 122 |
| USTEC | 1m | 43 |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 | 0 | 1 | 0 | 6 | 8 | 25 | 3 |
| DE40 | 1m | 11409 |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 | 1 | 5 | 1 | 147 | 5626 | 4640 | 989 |
| FRA40 | 1m | 30205 |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 | 0 | 0 | 0 | 5627 | 8988 | 13362 | 2228 |
| XAUUSD | 5m | 34193 | 7461 | 13978 | 8448 | 3064 | 574 | 362 | 120 | 78 | 27 | 4 | 34 | 22 | 1 | 0 | 0 | 4 | 12 | 4 | 0 | 0 | 0 |
| XAGUSD | 5m | 5716 |  |  |  |  | 635 | 2093 | 1346 | 254 | 225 | 133 | 395 | 155 | 46 | 23 | 32 | 119 | 24 | 105 | 19 | 90 | 22 |
| XPTUSD | 5m | 551 |  |  |  |  |  |  |  |  |  |  |  | 0 | 0 | 208 | 102 | 24 | 24 | 101 | 2 | 90 | 0 |
| XPDUSD | 5m | 15018 |  |  |  |  |  |  |  |  |  |  |  | 0 | 0 | 3243 | 3439 | 3148 | 2809 | 1005 | 380 | 854 | 140 |

## Zero-volume bars

| symbol | tf | total | 2004 | 2005 | 2006 | 2007 | 2008 | 2009 | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| XAUUSD | 1m | 0 |  |  |  |  |  |  |  |  | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| XAGUSD | 1m | 0 |  |  |  |  |  |  |  |  | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| US500 | 1m | 0 |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| US30 | 1m | 0 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 | 0 | 0 | 0 | 0 | 0 |
| USTEC | 1m | 0 |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| DE40 | 1m | 0 |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| FRA40 | 1m | 0 |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| XAUUSD | 5m | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| XAGUSD | 5m | 0 |  |  |  |  | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| XPTUSD | 5m | 0 |  |  |  |  |  |  |  |  |  |  |  | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| XPDUSD | 5m | 0 |  |  |  |  |  |  |  |  |  |  |  | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## Gaps longer than 4 days

| symbol | tf | total | 2004 | 2005 | 2006 | 2007 | 2008 | 2009 | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| XAUUSD | 1m | 0 |  |  |  |  |  |  |  |  | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| XAGUSD | 1m | 0 |  |  |  |  |  |  |  |  | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| US500 | 1m | 0 |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| US30 | 1m | 3 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 3 | 0 | 0 | 0 | 0 | 0 |
| USTEC | 1m | 0 |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| DE40 | 1m | 13 |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 | 2 | 5 | 1 | 2 | 1 | 2 | 0 |
| FRA40 | 1m | 7 |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 | 1 | 1 | 1 | 1 | 1 | 2 | 0 |
| XAUUSD | 5m | 2 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| XAGUSD | 5m | 0 |  |  |  |  | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| XPTUSD | 5m | 2 |  |  |  |  |  |  |  |  |  |  |  | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| XPDUSD | 5m | 3 |  |  |  |  |  |  |  |  |  |  |  | 2 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## Bars (denominator)

| symbol | tf | total | 2004 | 2005 | 2006 | 2007 | 2008 | 2009 | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| XAUUSD | 1m | 4096182 |  |  |  |  |  |  |  |  | 190919 | 348910 | 348720 | 346977 | 350507 | 349307 | 349988 | 349777 | 351518 | 351264 | 350345 | 349508 | 58442 |
| XAGUSD | 1m | 4097904 |  |  |  |  |  |  |  |  | 231110 | 342646 | 340161 | 340403 | 348598 | 348575 | 348221 | 347131 | 350693 | 349011 | 348685 | 345776 | 56894 |
| US500 | 1m | 852695 |  |  |  |  |  |  |  |  |  |  |  |  |  | 1 | 258 | 259 | 259 | 109335 | 348342 | 338482 | 55759 |
| US30 | 1m | 1729779 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 268871 | 350450 | 353926 | 349309 | 349090 | 58133 |
| USTEC | 1m | 867342 |  |  |  |  |  |  |  |  |  |  |  |  |  | 1 | 258 | 259 | 259 | 109349 | 349364 | 349626 | 58226 |
| DE40 | 1m | 747188 |  |  |  |  |  |  |  |  |  |  |  |  |  | 3 | 135 | 234 | 257 | 6746 | 344038 | 339029 | 56746 |
| FRA40 | 1m | 801548 |  |  |  |  |  |  |  |  |  |  |  |  |  | 1 | 255 | 254 | 258 | 109588 | 334587 | 306010 | 50595 |
| XAUUSD | 5m | 1316783 | 28408 | 51717 | 56015 | 64111 | 68165 | 68321 | 64429 | 65596 | 66496 | 70077 | 70079 | 69841 | 70370 | 70070 | 70213 | 70174 | 70587 | 70427 | 70089 | 69909 | 11689 |
| XAGUSD | 5m | 1054081 |  |  |  |  | 8798 | 65929 | 63532 | 66334 | 66538 | 70045 | 70032 | 69759 | 70367 | 70071 | 70210 | 70178 | 70531 | 70196 | 69996 | 69893 | 11672 |
| XPTUSD | 5m | 494217 |  |  |  |  |  |  |  |  |  |  |  | 1965 | 3880 | 54171 | 70415 | 70911 | 70836 | 70558 | 69930 | 69870 | 11681 |
| XPDUSD | 5m | 480765 |  |  |  |  |  |  |  |  |  |  |  | 2000 | 3833 | 52067 | 66071 | 69038 | 67879 | 69809 | 69650 | 68865 | 11553 |

## Largest gap per symbol and timeframe (days)

| symbol | tf | max gap (d) | year |
|---|---|---:|---|
| XAUUSD | 1m | 3.21 | 2015 |
| XAGUSD | 1m | 3.21 | 2015 |
| US500 | 1m | 4.0 | 2018 |
| US30 | 1m | 17.08 | 2019 |
| USTEC | 1m | 4.0 | 2018 |
| DE40 | 1m | 199.0 | 2018 |
| FRA40 | 1m | 5.0 | 2018 |
| XAUUSD | 5m | 4.56 | 2005 |
| XAGUSD | 5m | 3.59 | 2010 |
| XPTUSD | 5m | 124.29 | 2016 |
| XPDUSD | 5m | 124.29 | 2016 |

## Leakage probe (I9): `scripts/leakage.py` on the fund engine configuration

Tool: `scripts/research/leakage_probe_fund.py` (new; it drives the repo's own `leakage.probe`: replace every bar strictly after a cut
with a mutated future -- `scale`, `freeze`, `invert` -- and require every decision at or before the cut to come back byte-identical on
`entry, stop, target, side, event, R_planned`; outcome fields may move, CLAUDE.md §37). Overlay under test: the fund overlay
(`fixed_opts()`: flat-before-rollover and ALL eleven `ADOPTED_F_KEYS` ON, including `fx_admission_entry_cost` and `fx_gap_fill`), run through
`bt.scan` on real FTMO slices of XAUUSD at the two fund decision timeframes (1m and 5m), 15,000 decision bars each, with a fresh engine
instance per run (no cache can carry a baseline value into a mutated run).

What it covers that the existing probe tests (`scripts/tests/test_backtesting.py`, BTCUSDT 15m, default OPTS) do not: (1) the 1m/5m decision
timeframes, (2) every adopted key ON, (3) the HIGHER-TIMEFRAME series: the future of every context series (30m, 1H, 4H, 1D, 1W) is mutated
too, from the first bar that had not CLOSED by the cut bar's close (`normalized.available_time`, the engine's own rule), where the existing
tests hand the decision series to every timeframe; (4) the HTF-dependent values: W7 (`fx_w7_htf_target`, inside the adopted overlay, Wyckoff),
B3 (`fx_b3 = tfa_p5`, ICT, bias read on the paired timeframe 15m for 1m, 1H for 5m) and B-POOL (`fx_b_pool = on`, ICT). Cuts are ANCHORED on
decisions the baseline produced (entry bar == cut bar), because a probe cut at an arbitrary bar only has power for the few decisions within
one HTF bar of the cut.

| decision tf | method | variant | cuts | decisions checked | violations | result |
|---|---|---|---:|---:|---:|---|
| 5m | ICT | adopted keys | 6 | 84 | 0 | PASS |
| 5m | ICT | + B-POOL on | 6 | 84 | 0 | PASS |
| 5m | ICT | + B3 tfa_p5 | 2 | 3 | 0 | PASS (3 decisions only: weak) |
| 5m | WYCKOFF-BOOK | adopted keys (W7 on) | 6 | 66 | 0 | PASS |
| 1m | ICT | adopted keys | 6 | 123 | 0 | PASS |
| 1m | ICT | + B-POOL on | 6 | 123 | 0 | PASS |
| 1m | ICT | + B3 tfa_p5 | 5 | 25 | 0 | PASS |
| 1m | WYCKOFF-BOOK | adopted keys (W7 on) | 6 | 66 | 0 | PASS |

Earlier single-cut runs (one cut at 70 % of the series; 15,000 bars on 5m and 1m, 60,000 on XAUUSD 5m and 40,000 on 1m for B3/W7; US500 5m 6,000
bars): every non-control row PASSes with checked > 0 (decisions checked: XAUUSD 5m ICT 18, + B-POOL 18, + B3 2 at 15,000 bars and 14 at 60,000, WYCKOFF 13 at
15,000 and 63 at 60,000; XAUUSD 1m ICT 27, + B-POOL 27, + B3 5 at 15,000 and 11 at 40,000, WYCKOFF 13; US500 5m ICT 5, WYCKOFF 4). Total across all batches: 0 violations
outside the positive control.

**Positive controls (does the probe see a leak at all?).** The control makes the engine read every higher-timeframe bar TWO periods early
(a full future bar). Results: ICT 5m + B3: DETECTED (3 violations, a decision "decided -> gone" under `invert`): the probe has power against an
HTF-future read for B3. NOT detected: ICT 1m + B3 (25 decisions), WYCKOFF 5m and 1m (66 decisions each, W7 on). So the clean B3 rows at 1m
and every W7 row are weaker evidence than the 5m B3 row: at this sample size no decision was sensitive enough to the HTF bar for the control to
flip it (W7 only acts on Phase-D legs, a small share of the decisions). The W7/B3-at-1m PASSes mean "nothing found", not "proved absent". A
dedicated W7 PIT test with many Phase-D legs (or a larger slice) is the open follow-up; the engine's own W7 code already restricts the HTF series
to the PIT prefix (`_HtfSeries.prefix_len`, `pit.series_as_of`) and `test_w7_htf_cache` / `test_speed_equivalence` pin that path.

Not covered: symbols other than XAUUSD (US500 5m only in the single-cut batch), the 15m decision timeframe, the news calendar (the harness reads none),
and decisions near the very start of a series. No R, expectancy or win rate is computed or printed by the tool.
