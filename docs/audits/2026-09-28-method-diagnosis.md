# Method diagnosis on development data: ICT and WYCKOFF-BOOK (2026-09-28)

**Status:** read-only diagnosis. It changes no methodology and proposes no rule. It is step 1 of the owner's
2026-09-28 decision to *improve the methodology* after the pre-registered prop search
(`scripts/prop-search.py`, commit `bac685c`) evaluated 180/180 candidates and none passed.

**Data window (research integrity, CLAUDE.md §8/§9/§44):** only candles available before
**2024-03-01T00:00:00Z** (prop-search `VALIDATION_START`), enforced with the engine's own load-time seam
`bt.pit_cutoff("2024-03-01T00:00:00Z")`. `scripts/diagnose-methods.py` refuses a later cutoff and raises if
any trade or loaded bar is at/after it. Measured over all 30 slices: latest loaded bar
`2024-02-29T23:45:00Z`, latest trade exit `2024-02-28T12:45:00Z`. No validation-window bar or trade was read,
printed or summarised. History starts differ per series (XAUUSD 1H/4H from 2004, XAUUSD 15m from 2018-03,
US500/DE40 1H/4H from 2012-08, US500/DE40 15m from 2022), so the development window used is **all history up to
the cutoff**, not a one-year slice; sample sizes below are for those spans.

**Engine:** unmodified `scripts/backtest-methods.py` `scan(sym, tf, only=(method,), opts=config_opts(CONFIGS[c], "range"))`,
loaded through `scripts/stability-report.py` as `prop-search._load_sr()` does. Per-tf parameters `bt.P[tf]`
(15m R48 K16 H96; 1H R48 K12 H72; 4H R30 K8 H30). HTF bias methods resolved for CFDs: `('ict',)`.
`git diff --stat` on the five engine/methodology files is empty.

**How the funnel is counted:** counting pass-through wrappers are installed on engine and scanner functions from
outside, in the diagnostic process only (`bt.ict_setups_live`, `lr.read_at`, `ict_scan.setup_candidate`,
`lr.bias_at`, `bt.bias_allows`, `bt.htf_bias_gate`, `bt.fvg_fill`, `bt.walk`; for Wyckoff
`W.detect_accumulations/detect_distributions`, `bt._wyckoff_candidates`, `bt._fires_from`,
`bt.htf_bias_gate`, `bt.walk`). Each wrapper returns exactly what the original returned.
- **Instrumentation changes nothing:** instrumented trades == plain `bt.scan()` trades on a real full-dev
  slice, XAUUSD 4H config C: ICT 2 == 2, WYCKOFF-BOOK 26 == 26 (`equality.log`), and in the unit tests
  (XAUUSD 4H to 2007-01-01, both methods, config C).
- **OBSERVED vs INFERRED:** ICT's dedup / MSS-index / expiry checks and WYCKOFF-BOOK's per-record spring-leg
  conditions run inline, with no call to wrap. They are re-derived from the engine's own records using the same
  conditions and **cross-checked against an observed call** on every bar or window. Mismatch count across all 30
  slices: **0** (column "consist." = ok).
- **Not observable without editing the engine:** (1) ICT `setup_candidate` returning `None`. "No recent sweep",
  "no MSS after it", "MSS direction does not match the sweep" and "no target beyond entry" all return `None`
  with no distinguishing call, so they count as one stage. (2) For the WYCKOFF-BOOK phase-D leg, *why* a BU bar
  did not fire (placeability) is not separated. Only "structure has a BU" (detection) and "phase_d fired"
  (observed) are reported.
- Wyckoff "structures" are unique `(side, SC time, AR time)` over every live 300-bar window, with fields taken
  from the last window that still held the structure. One structure re-detected with a different AR would be
  counted twice, so treat those counts as approximate. The fire/dedup/booked counts are exact.

**Outcome numbers** are the engine's **gross** R (from `walk()`), with fees charged later by `simulate()`.
The "fees and the R:R floor" table re-prices each trade with the same `risk_model.cost_r` call `simulate()`
makes. Its "sim taken" column is `bt.simulate(..., live_parity_sizing=True)` itself, run without an account
profile, as prop-search's development population is. No trade was truncated by the cutoff (column "trunc" = 0).

Reproduce (from the worktree root):
```
python scripts/diagnose-methods.py batch --out-dir $TMP/runs --timeout 1800   # 30 slices, one subprocess each, sequential
python scripts/diagnose-methods.py equality --symbol XAUUSD --tf 4H --method ICT --config C
python scripts/diagnose-methods.py equality --symbol XAUUSD --tf 4H --method WYCKOFF-BOOK --config C
python scripts/diagnose-methods.py report --in-dir $TMP/runs                   # per-slice detail
python -m unittest scripts.tests.test_diagnose_methods
```
All 30 requested slices ran: ICT and WYCKOFF-BOOK × config A × 15m/1H/4H × XAUUSD/US500/DE40, plus B and C on
1H. None was skipped for time or a crash. The slowest was ICT XAUUSD 15m at 454 s.

---

## Findings

### (i) Where each method loses its candidates

**ICT (config A, 9 slices pooled, unique setups):**
4550 sweep→MSS candidates → 2707 with a displaced MSS (−41 %) → 1619 with a same-direction FVG (−40 %) →
751 with entry in discount/premium (**−54 %**) → 699 with LTF bias agreeing (−7 %) → 696 not expired → 345
not already triggered when first visible (**−50 %**) → 158 limit filled within K bars (**−54 %**) → 158 booked.
That is **3.5 %** of sweep→MSS candidates. Before those stages, a sweep→MSS candidate exists on only about 2-4 %
of scanned bars (XAUUSD 1H: 3891 of 114 084 bars), and that `None` branch cannot be split further (see above).
The biggest single cuts are therefore:
1. **P/D gate (R13), −54 %**
2. **the two execution gates together, 696 → 158 (−77 %)**: the limit had already been touched by the time the
   setup was detectable, or it never filled within K bars
3. displacement, −41 %
4. FVG, −40 %

Bias costs little in A/B (only `neutral` refusals, 2-15 per slice). **Config C's HTF gate removes 63 %** of the
setups that reach it (361 → 133 on 1H). The pooled 1H counts are 71 trades under B and 20 under C, over 12-20
years of 1H history. Per symbol-year that is about 1.5-1.9 trades on 1H under A/B, 5-8 on 15m, and 0.1-0.8
on 1H under C. That is consistent with 130/180 prop candidates having too few trades in their one-year window.

**WYCKOFF-BOOK (config A, 9 slices):**
- **The spring leg dies at detection.** Of about 781 spring-path structures, about 569 (73 %) are typed
  Shakeout. Of the 897 candidate structures (ones that could fire on some window's last bar), the spring-leg
  fate is: 555 on the LPS[C] path with no Spring leg at all, 136 fired, 103 refused by the VP/LVN abandon rule,
  64 shakeout, 16 with no volume type, 11 whose Test never came, 8 whose entry bar never fell on a window's last
  bar, 2 sot_too_strong and 2 not placeable.
- **Most trades come from the LPS[C] path's Phase-D BU entry, not from the Spring.** 550 of 686 trades
  (80 %) are `phase_d`. A BU is almost never reached on the Spring path (0-6 per slice).
- After a structure fires, nothing further is lost: dedup removes 1 fire, and `walk()` returns a trade for
  every fire.
- **The HTF gate in config C removes 58 % of fires** (1H: 120 of 288 pass).

### (ii) The dominant losing pattern

**WYCKOFF-BOOK: short planned R, too few wins at that R, and fees that are large relative to the stop.**
- Pooled A: n = 686, gross mean **−0.036 R**, win rate 40.2 %, median planned R **1.89**. The breakeven win
  rate at that R is 34.6 % gross, but the median fee is **0.25 R** (mean 0.31 R) because stops are tight
  (median 0.25-0.6 % of price on 15m/1H). Net of fees the mean is **−0.35 R**.
- 359 of 686 trades plan below the 2R floor even before fees and are refused by `simulate()`. The trades that do pass the floor
  (planned R ≥ 2 + fee) win only **21 %** (gross −0.145 R, net −0.52 R). Wyckoff trades with the farther
  target reach it much less often.
- The spring leg is worse than phase D: 136 trades, −0.157 R, 32 % wins; against phase D 550 trades,
  −0.006 R, 42 % wins. No side dominates (long −0.021 R, short −0.052 R).
- 103 of 410 losers (25 %) first went ≥ +1R in favour. With breakeven management (B, 1H) that falls to 4
  losers, but 50 trades become breakevens. The 1H mean is not consistently better: XAUUSD −0.031 → +0.006,
  DE40 +0.094 → +0.090, US500 −0.083 → −0.143.
- No loser reached its planned target's R before losing (1 case in 410). Losses are "never got there", not
  "got there and reversed".

**ICT: the gross edge is small and positive; the problems are frequency and fees on the lower timeframes.**
- Pooled A: n = 158, gross **+0.21 R**, win rate 41 %, median planned R 2.86. Net of fees −0.02 R. After the
  floor, 120 trades, net **+0.06 R**, 38 % wins.
- 15m fees are 0.25-0.33 R per trade (stop 0.3-0.4 % of price). That turns DE40 15m +0.15 R gross into −0.15 R
  net, and US500 15m −0.02 R into −0.40 R.
- The ICT losing pattern is the full −1R stop (90 of 158). Only 23 of 93 losers had MFE ≥ 1R, and none reached
  planned R.
- Time stops are profitable exits: 28 trades, mean **+1.30 R**. They were heading toward target when the
  H-bar horizon closed them.
- Results differ by symbol. US500 is ≤ 0 gross on 15m and 1H. XAUUSD 4H is −0.34 R on n = 7. Every per-slice n
  is 1-31, too small to separate a symbol effect from noise.
- Config C's pooled +0.48 R gross comes from 20 trades, one of which is +2.85 R on US500, so it is not evidence
  either way.

### (iii) Hypotheses, phrased as questions to check against `knowledge/`

These are questions to put to the methodology sources, not proposals. Anything that proceeds must go through the
§41/§42 experiment lifecycle, with the validation window treated as exposed.

**WYCKOFF-BOOK**
1. **Phase-D target (`ceiling + d_target_tr × TR`).** Does the source define it this way? Is `d_target_tr` a
   book value or a project parameter? The phase-D leg carries 80 % of trades at a median planned R under 2,
   and the far-target subset wins 21 %.
2. **Shakeout typing (R6, `spring_max_bars_outside = sob`, "more than half the bars outside").** Is the
   "more than half" test in the source (WA/WMT Spring vs Shakeout tables), and do the source's thresholds match
   `P[tf]["sob"]`? It removes 73 % of spring-path structures.
3. **VP/LVN abandon rule (R10).** Does the source state it as a veto or as a caution? It is the largest named
   refusal among fireable Spring candidates (103 vs 136 fired).
4. **LPS[C] path (structures without a Spring).** Does the source allow entering at the Phase-D BU when no
   Spring was identified? What is the book's entry, stop and target for that case? It is the source of most
   Wyckoff trades.
5. **Stop placement.** What stop does the source prescribe for a BU/LPS entry? `min(L[sos+1:entry+1])` minus a
   0.05 % buffer gives stops of 0.25-0.6 % of price, and fees then cost 0.2-0.4 R. Do the sources treat tight
   stops as intended, or place the stop elsewhere (for example under the LPS or the Spring)?
6. **Test for type-2 Springs.** What confirmation does the source require, and is the Test window
   (`test_window`) sourced? 11 structures never got an entry bar.

**ICT**
7. **P/D (R13).** Is premium/discount judged on the entry price against *this* dealing range (`a["lo"]`/`a["hi"]`
   from the live scanner window), as the deck frames it? Or is the deck's dealing range a different swing
   range? It removes 54 %.
8. **Entry model.** The engine's limit is at the FVG near edge (`iofed`) and must not have been touched before
   the setup is visible. Do the decks allow the other entry models the scanner already records (`ce`, `fill`),
   or a later re-entry? Together these two execution gates remove 77 % of what survives the structure gates.
   The "already triggered" gate is a live-runner semantic (CLAUDE.md §37), so changing it would also change live.
9. **Order expiry K.** Is the K-bar limit expiry (`P[tf]["K"]`) sourced or a project number? It causes 54 % of
   the remaining losses at the fill stage.
10. **Time stop H.** Do the decks specify a time-based exit? Timeouts average +1.30 R, so H may be cutting
    trades that are still progressing.
11. **Displacement ratios (`body_min_ratio`, `range_min_median_ratio` in `analysis-params.json` →
    `project_defined`).** These are project-defined numbers. Do the decks give any quantitative guidance? This
    gate removes 41 %.
12. **HTF gate (config C).** The HTF bias reads only the `ict` dimension for CFDs. Is that the deck's HTF
    narrative, and is the HTF rung (`next_rung`, ≥ 4×) the deck's pairing? It removes 58-63 % of both
    methods' candidates.

**Both methods**
13. **Fees in R.** The fee in R depends on stop width, not on the methodology. Does either source say anything
    about minimum stop distance or timeframe choice relative to trading costs? Or is timeframe selection
    (1H/4H over 15m) the only lever that does not invent a rule?

**Caveats**
- Samples are small for ICT (1-31 trades per slice) and for every config-C slice.
- Gross/net results are not independent across configs, because A/B/C share the same structures.
- Over the dev window these slices spread across 2004-2024 regimes; no regime split was done.

---

## Per-slice tables

### ICT funnel (unique setups; bars scanned / full window in first cols)

| slice | bars | sweep+MSS | displ. | FVG | P/D | LTF bias | HTF | not exp. | not trig. | filled | booked | consist. |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| DE40 15m A | 46853 | 347 | 199 | 126 | 50 | 45 | 45 | 45 | 25 | 16 | 16 | ok |
| US500 15m A | 43156 | 330 | 182 | 115 | 57 | 49 | 49 | 49 | 32 | 19 | 19 | ok |
| XAUUSD 15m A | 140276 | 809 | 492 | 270 | 130 | 115 | 115 | 115 | 66 | 31 | 31 | ok |
| DE40 1H A | 47775 | 560 | 311 | 167 | 86 | 82 | 82 | 82 | 45 | 22 | 22 | ok |
| US500 1H A | 48898 | 544 | 338 | 217 | 92 | 90 | 90 | 90 | 42 | 19 | 19 | ok |
| XAUUSD 1H A | 114563 | 1178 | 715 | 422 | 199 | 189 | 189 | 189 | 73 | 30 | 30 | ok |
| DE40 1H B | 47775 | 560 | 311 | 167 | 86 | 82 | 82 | 82 | 45 | 22 | 22 | ok |
| US500 1H B | 48898 | 544 | 338 | 217 | 92 | 90 | 90 | 90 | 42 | 19 | 19 | ok |
| XAUUSD 1H B | 114563 | 1178 | 715 | 422 | 199 | 189 | 189 | 189 | 73 | 30 | 30 | ok |
| DE40 1H C | 47775 | 560 | 311 | 167 | 86 | 82 | 35 | 35 | 17 | 9 | 9 | ok |
| US500 1H C | 48898 | 544 | 338 | 217 | 92 | 90 | 20 | 20 | 5 | 1 | 1 | ok |
| XAUUSD 1H C | 114563 | 1178 | 715 | 422 | 199 | 189 | 78 | 78 | 26 | 10 | 10 | ok |
| DE40 4H A | 13244 | 193 | 106 | 71 | 33 | 31 | 31 | 30 | 16 | 8 | 8 | ok |
| US500 4H A | 13390 | 177 | 122 | 83 | 32 | 29 | 29 | 29 | 16 | 6 | 6 | ok |
| XAUUSD 4H A | 30171 | 412 | 242 | 148 | 72 | 69 | 69 | 67 | 30 | 7 | 7 | ok |
| **sum A** | | 4550 | 2707 | 1619 | 751 | 699 | 699 | 696 | 345 | 158 | 158 | |
| **sum B** | | 2282 | 1364 | 806 | 377 | 361 | 361 | 361 | 160 | 71 | 71 | |
| **sum C** | | 2282 | 1364 | 806 | 377 | 361 | 133 | 133 | 48 | 20 | 20 | |

bias refusals (setups stopped at bias, by bias value):
- DE40 15m A: {'neutral': 5} htf=not applied (config has htf=False)
- US500 15m A: {'neutral': 8} htf=not applied (config has htf=False)
- XAUUSD 15m A: {'neutral': 15} htf=not applied (config has htf=False)
- DE40 1H A: {'neutral': 4} htf=not applied (config has htf=False)
- US500 1H A: {'neutral': 2} htf=not applied (config has htf=False)
- XAUUSD 1H A: {'neutral': 10} htf=not applied (config has htf=False)
- DE40 1H B: {'neutral': 4} htf=not applied (config has htf=False)
- US500 1H B: {'neutral': 2} htf=not applied (config has htf=False)
- XAUUSD 1H B: {'neutral': 10} htf=not applied (config has htf=False)
- DE40 1H C: {'neutral': 4} htf={'False': 116, 'True': 66}
- US500 1H C: {'neutral': 2} htf={'True': 37, 'False': 143}
- XAUUSD 1H C: {'neutral': 10} htf={'False': 281, 'True': 143}
- DE40 4H A: {'neutral': 2} htf=not applied (config has htf=False)
- US500 4H A: {'neutral': 3} htf=not applied (config has htf=False)
- XAUUSD 4H A: {'neutral': 3} htf=not applied (config has htf=False)

### WYCKOFF-BOOK funnel

| slice | bars | structs L/S | spring-path | shakeout | Spring reclaim | test | BU (spring path) | lps_c w/ BU | cand. structs | fires pre-dedup sp/D | after dedup sp/D | HTF T/F/None | booked sp/D | consist. |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|---|
| DE40 15m A | 46853 | 73/84 | 70 | 48 | 55 | 26 | 1 | 44 | 74 | 16/41 | 16/41 | – | 16/41 | ok |
| US500 15m A | 43156 | 70/71 | 58 | 41 | 45 | 18 | 1 | 50 | 64 | 8/39 | 8/39 | – | 8/39 | ok |
| XAUUSD 15m A | 140276 | 264/305 | 241 | 193 | 184 | 100 | 6 | 187 | 262 | 44/140 | 44/140 | – | 44/140 | ok |
| DE40 1H A | 47775 | 89/97 | 67 | 40 | 49 | 27 | 2 | 64 | 72 | 9/48 | 9/48 | – | 9/48 | ok |
| US500 1H A | 48898 | 78/94 | 78 | 49 | 54 | 34 | 1 | 58 | 82 | 19/45 | 19/45 | – | 19/45 | ok |
| XAUUSD 1H A | 114563 | 231/233 | 173 | 129 | 114 | 54 | 3 | 166 | 210 | 28/140 | 28/139 | – | 28/139 | ok |
| DE40 1H B | 47775 | 89/97 | 67 | 40 | 49 | 27 | 2 | 64 | 72 | 9/48 | 9/48 | – | 9/48 | ok |
| US500 1H B | 48898 | 78/94 | 78 | 49 | 54 | 34 | 1 | 58 | 82 | 19/45 | 19/45 | – | 19/45 | ok |
| XAUUSD 1H B | 114563 | 231/233 | 173 | 129 | 114 | 54 | 3 | 166 | 210 | 28/140 | 28/139 | – | 28/139 | ok |
| DE40 1H C | 47775 | 89/97 | 67 | 40 | 49 | 27 | 2 | 64 | 72 | 9/48 | 9/48 | 24/33/0 | 1/23 | ok |
| US500 1H C | 48898 | 78/94 | 78 | 49 | 54 | 34 | 1 | 58 | 82 | 19/45 | 19/45 | 28/36/0 | 5/23 | ok |
| XAUUSD 1H C | 114563 | 231/233 | 173 | 129 | 114 | 54 | 3 | 166 | 210 | 28/140 | 28/139 | 68/99/0 | 3/65 | ok |
| DE40 4H A | 13244 | 31/32 | 13 | 10 | 9 | 6 | 0 | 32 | 24 | 0/20 | 0/20 | – | 0/20 | ok |
| US500 4H A | 13390 | 25/29 | 25 | 15 | 18 | 8 | 1 | 17 | 31 | 3/19 | 3/19 | – | 3/19 | ok |
| XAUUSD 4H A | 30171 | 87/80 | 56 | 44 | 30 | 17 | 1 | 79 | 78 | 9/59 | 9/59 | – | 9/59 | ok |

spring-leg fate of candidate structures, summed per config:
- A: {'lps_c_path(no spring leg)': 555, 'fired': 136, 'abandon(VP/LVN)': 103, 'shakeout': 64, 'vol_type_None_excluded': 16, 'no_test(entry bar never exists)': 11, 'entry_bar_not_in_any_window': 8, 'sot_too_strong': 2, 'not_placeable(close beyond stop/target)': 2}
- B: {'lps_c_path(no spring leg)': 236, 'fired': 56, 'abandon(VP/LVN)': 40, 'shakeout': 21, 'no_test(entry bar never exists)': 4, 'vol_type_None_excluded': 3, 'entry_bar_not_in_any_window': 2, 'sot_too_strong': 1, 'not_placeable(close beyond stop/target)': 1}
- C: {'lps_c_path(no spring leg)': 236, 'fired': 56, 'abandon(VP/LVN)': 40, 'shakeout': 21, 'no_test(entry bar never exists)': 4, 'vol_type_None_excluded': 3, 'entry_bar_not_in_any_window': 2, 'sot_too_strong': 1, 'not_placeable(close beyond stop/target)': 1}

vol types (spring path) per slice:
- DE40 15m A: {'vol_type_3': 17, 'vol_type_2': 26, 'vol_type_1': 13, 'vol_type_None': 14}
- US500 15m A: {'vol_type_None': 15, 'vol_type_2': 20, 'vol_type_1': 6, 'vol_type_3': 17}
- XAUUSD 15m A: {'vol_type_2': 117, 'vol_type_3': 75, 'vol_type_1': 28, 'vol_type_None': 21}
- DE40 1H A: {'vol_type_3': 16, 'vol_type_2': 34, 'vol_type_1': 12, 'vol_type_None': 5}
- US500 1H A: {'vol_type_3': 17, 'vol_type_2': 35, 'vol_type_1': 11, 'vol_type_None': 15}
- XAUUSD 1H A: {'vol_type_3': 56, 'vol_type_2': 79, 'vol_type_1': 24, 'vol_type_None': 14}
- DE40 1H B: {'vol_type_3': 16, 'vol_type_2': 34, 'vol_type_1': 12, 'vol_type_None': 5}
- US500 1H B: {'vol_type_3': 17, 'vol_type_2': 35, 'vol_type_1': 11, 'vol_type_None': 15}
- XAUUSD 1H B: {'vol_type_3': 56, 'vol_type_2': 79, 'vol_type_1': 24, 'vol_type_None': 14}
- DE40 1H C: {'vol_type_3': 16, 'vol_type_2': 34, 'vol_type_1': 12, 'vol_type_None': 5}
- US500 1H C: {'vol_type_3': 17, 'vol_type_2': 35, 'vol_type_1': 11, 'vol_type_None': 15}
- XAUUSD 1H C: {'vol_type_3': 56, 'vol_type_2': 79, 'vol_type_1': 24, 'vol_type_None': 14}
- DE40 4H A: {'vol_type_3': 3, 'vol_type_1': 2, 'vol_type_2': 5, 'vol_type_None': 3}
- US500 4H A: {'vol_type_3': 6, 'vol_type_2': 7, 'vol_type_None': 10, 'vol_type_1': 2}
- XAUUSD 4H A: {'vol_type_1': 11, 'vol_type_2': 23, 'vol_type_None': 4, 'vol_type_3': 18}

### Outcomes (gross R, booked trades)

| slice | n | target | stop | BE | time | trunc | same-bar | mean R | median R | win% | MFE med / p75 | MAE med | R_plan med | bars med | losers MFE≥1R | losers MFE≥plan | long n/meanR | short n/meanR | sim taken / mean net R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---|---:|---|---|---|
| ICT DE40 15m A | 16 | 6 | 9 | 0 | 1 | 0 | 0 | 0.148 | -1.0 | 44 | 0.428 / 1.597 | -1.057 | 3.031 | 8.5 | 0/9 | 0 | 6/-0.593 | 10/0.592 | 11 / 0.015 |
| ICT US500 15m A | 19 | 3 | 12 | 0 | 3 | 0 | 1 | -0.02 | -1.0 | 26 | 1.027 / 2.182 | -1.103 | 2.882 | 18.0 | 5/14 | 1 | 7/-0.001 | 12/-0.031 | 13 / -0.466 |
| ICT XAUUSD 15m A | 31 | 7 | 16 | 0 | 7 | 0 | 1 | 0.43 | -1.0 | 42 | 1.225 / 2.699 | -1.008 | 2.927 | 42.0 | 5/18 | 0 | 17/0.259 | 14/0.639 | 29 / 0.188 |
| ICT DE40 1H A | 22 | 7 | 10 | 0 | 5 | 0 | 0 | 0.539 | 0.223 | 55 | 1.246 / 2.38 | -0.931 | 3.256 | 27.5 | 3/10 | 0 | 13/0.761 | 9/0.219 | 15 / 0.697 |
| ICT US500 1H A | 19 | 2 | 12 | 0 | 4 | 0 | 1 | -0.14 | -1.0 | 32 | 1.219 / 2.051 | -1.077 | 2.831 | 19.0 | 4/13 | 0 | 11/-0.209 | 8/-0.044 | 13 / -0.063 |
| ICT XAUUSD 1H A | 30 | 9 | 14 | 0 | 6 | 0 | 1 | 0.326 | -0.506 | 47 | 1.084 / 2.199 | -0.886 | 2.473 | 33.0 | 4/16 | 0 | 13/0.211 | 17/0.414 | 18 / 0.483 |
| ICT DE40 1H B | 22 | 6 | 7 | 7 | 2 | 0 | 0 | 0.362 | 0.0 | 36 | 1.122 / 2.338 | -0.717 | 3.256 | 20.0 | 0/7 | 0 | 13/0.444 | 9/0.244 | 15 / 0.47 |
| ICT US500 1H B | 19 | 1 | 9 | 5 | 3 | 0 | 1 | -0.148 | -1.0 | 21 | 1.03 / 1.916 | -1.0 | 2.831 | 19.0 | 1/10 | 0 | 11/-0.079 | 8/-0.244 | 13 / -0.076 |
| ICT XAUUSD 1H B | 30 | 9 | 10 | 6 | 4 | 0 | 1 | 0.374 | 0.0 | 40 | 1.013 / 2.067 | -0.469 | 2.473 | 31.0 | 0/12 | 0 | 13/0.519 | 17/0.263 | 18 / 0.554 |
| ICT DE40 1H C | 9 | 3 | 2 | 3 | 1 | 0 | 0 | 0.857 | 0.0 | 44 | 1.261 / 3.514 | -0.523 | 3.803 | 49.0 | 0/2 | 0 | 5/1.152 | 4/0.49 | 5 / 1.762 |
| ICT US500 1H C | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 2.85 | 2.85 | 100 | 3.877 / 3.877 | -0.194 | 4.223 | 72.0 | 0/0 | 0 | 1/2.85 | 0/None | 1 / 2.778 |
| ICT XAUUSD 1H C | 10 | 2 | 6 | 2 | 0 | 0 | 0 | -0.092 | -1.0 | 20 | 0.761 / 1.016 | -1.102 | 2.044 | 22.0 | 0/6 | 0 | 5/-0.186 | 5/0.002 | 5 / 0.444 |
| ICT DE40 4H A | 8 | 1 | 5 | 0 | 2 | 0 | 0 | 0.103 | -1.0 | 38 | 0.883 / 1.477 | -1.033 | 3.294 | 15.5 | 0/5 | 0 | 5/0.207 | 3/-0.072 | 7 / 0.203 |
| ICT US500 4H A | 6 | 3 | 3 | 0 | 0 | 0 | 0 | 0.104 | -0.349 | 50 | 0.556 / 0.957 | -0.55 | 2.906 | 3.5 | 1/3 | 0 | 3/0.649 | 3/-0.441 | 4 / -0.239 |
| ICT XAUUSD 4H A | 7 | 2 | 5 | 0 | 0 | 0 | 0 | -0.343 | -1.0 | 29 | 0.627 / 1.331 | -1.467 | 2.518 | 14.0 | 1/5 | 0 | 6/-0.233 | 1/-1.0 | 5 / -1.121 |
| WYC DE40 15m A | 57 | 15 | 38 | 0 | 4 | 0 | 0 | -0.026 | -1.0 | 28 | 0.767 / 1.773 | -1.125 | 2.014 | 18.0 | 11/41 | 0 | 31/-0.073 | 26/0.029 | 22 / -0.26 |
| WYC US500 15m A | 47 | 23 | 22 | 0 | 2 | 0 | 0 | 0.326 | 0.123 | 53 | 0.871 / 1.748 | -0.789 | 1.893 | 13.0 | 4/22 | 0 | 23/0.947 | 24/-0.269 | 20 / -0.148 |
| WYC XAUUSD 15m A | 184 | 67 | 107 | 0 | 10 | 0 | 0 | -0.169 | -1.0 | 41 | 0.689 / 1.412 | -1.037 | 1.655 | 10.0 | 27/109 | 1 | 75/-0.188 | 109/-0.155 | 63 / -1.087 |
| WYC DE40 1H A | 57 | 25 | 30 | 0 | 2 | 0 | 0 | 0.094 | -1.0 | 47 | 0.767 / 1.569 | -1.028 | 1.938 | 9.0 | 9/30 | 0 | 30/0.16 | 27/0.022 | 27 / -0.392 |
| WYC US500 1H A | 64 | 23 | 40 | 0 | 1 | 0 | 0 | -0.083 | -1.0 | 38 | 0.665 / 1.296 | -1.109 | 1.997 | 12.0 | 7/40 | 0 | 36/-0.147 | 28/-0.001 | 28 / -0.489 |
| WYC XAUUSD 1H A | 167 | 60 | 100 | 0 | 7 | 0 | 0 | -0.031 | -1.0 | 39 | 0.813 / 1.483 | -1.06 | 1.818 | 8.0 | 27/102 | 0 | 90/-0.105 | 77/0.056 | 69 / -0.439 |
| WYC DE40 1H B | 57 | 22 | 22 | 12 | 1 | 0 | 0 | 0.09 | 0.0 | 40 | 0.767 / 1.342 | -0.718 | 1.938 | 9.0 | 1/22 | 0 | 30/0.149 | 27/0.024 | 27 / -0.28 |
| WYC US500 1H B | 64 | 20 | 35 | 9 | 0 | 0 | 0 | -0.143 | -1.0 | 31 | 0.665 / 1.189 | -1.054 | 1.997 | 11.5 | 2/35 | 0 | 36/-0.198 | 28/-0.073 | 28 / -0.561 |
| WYC XAUUSD 1H B | 167 | 57 | 75 | 29 | 6 | 0 | 0 | 0.006 | 0.0 | 37 | 0.813 / 1.443 | -0.896 | 1.818 | 7.0 | 1/76 | 0 | 90/0.022 | 77/-0.013 | 69 / -0.393 |
| WYC DE40 1H C | 24 | 13 | 7 | 3 | 1 | 0 | 0 | 0.329 | 0.156 | 58 | 0.617 / 1.43 | -0.613 | 1.693 | 9.0 | 1/7 | 0 | 11/0.273 | 13/0.376 | 10 / -0.169 |
| WYC US500 1H C | 28 | 6 | 19 | 3 | 0 | 0 | 0 | -0.493 | -1.0 | 21 | 0.443 / 0.843 | -1.176 | 2.003 | 10.5 | 0/19 | 0 | 20/-0.457 | 8/-0.582 | 12 / -0.917 |
| WYC XAUUSD 1H C | 68 | 24 | 25 | 17 | 2 | 0 | 0 | 0.104 | 0.0 | 38 | 1.001 / 1.464 | -0.727 | 2.053 | 12.0 | 1/25 | 0 | 32/0.259 | 36/-0.033 | 31 / -0.261 |
| WYC DE40 4H A | 20 | 3 | 14 | 0 | 3 | 0 | 0 | -0.526 | -1.0 | 20 | 0.816 / 1.386 | -1.137 | 2.162 | 5.0 | 7/16 | 0 | 10/-0.698 | 10/-0.354 | 11 / -0.88 |
| WYC US500 4H A | 22 | 5 | 10 | 0 | 7 | 0 | 0 | 0.114 | -0.092 | 50 | 0.813 / 1.577 | -0.914 | 3.429 | 9.5 | 1/11 | 0 | 17/0.218 | 5/-0.239 | 14 / -0.172 |
| WYC XAUUSD 4H A | 68 | 20 | 36 | 0 | 12 | 0 | 0 | 0.08 | -1.0 | 43 | 0.839 / 1.816 | -1.024 | 2.126 | 8.0 | 10/39 | 0 | 40/0.008 | 28/0.184 | 34 / -0.172 |

### Pooled per method x config (all slices)

- ('ICT', 'A'): n=158 mean_R=0.211 win%=41.1 outcomes={'loss': 90, 'timeout': 28, 'win': 40} losers=93 losers_MFE>=1R=23 R_planned_median=2.8585209003215737 breakeven_winrate_needed=0.259
    long: n=81 mean_R=0.158
    short: n=77 mean_R=0.268
    timeouts: n=28 mean_R=1.298
- ('ICT', 'B'): n=71 mean_R=0.230 win%=33.8 outcomes={'timeout': 9, 'loss': 28, 'win': 16, 'breakeven': 18} losers=29 losers_MFE>=1R=1 R_planned_median=2.782608695652174 breakeven_winrate_needed=0.264
    long: n=37 mean_R=0.315
    short: n=34 mean_R=0.139
    timeouts: n=9 mean_R=1.420
- ('ICT', 'C'): n=20 mean_R=0.482 win%=35.0 outcomes={'timeout': 2, 'loss': 8, 'breakeven': 5, 'win': 5} losers=8 losers_MFE>=1R=0 R_planned_median=2.9041256446319705 breakeven_winrate_needed=0.256
    long: n=11 mean_R=0.698
    short: n=9 mean_R=0.219
    timeouts: n=2 mean_R=2.404
- ('WYCKOFF-BOOK', 'A'): n=686 mean_R=-0.036 win%=40.2 outcomes={'loss': 397, 'win': 241, 'timeout': 48} losers=410 losers_MFE>=1R=103 R_planned_median=1.886143169606869 breakeven_winrate_needed=0.346
    spring: n=136 mean_R=-0.157 win%=32.4 outcomes={'loss': 92, 'win': 42, 'timeout': 2}
    phase_d: n=550 mean_R=-0.006 win%=42.2 outcomes={'loss': 305, 'win': 199, 'timeout': 46}
    long: n=352 mean_R=-0.021
    short: n=334 mean_R=-0.052
    timeouts: n=48 mean_R=0.556
- ('WYCKOFF-BOOK', 'B'): n=288 mean_R=-0.011 win%=36.5 outcomes={'loss': 132, 'win': 99, 'timeout': 7, 'breakeven': 50} losers=133 losers_MFE>=1R=4 R_planned_median=1.8541360590182892 breakeven_winrate_needed=0.350
    spring: n=56 mean_R=-0.199 win%=25.0 outcomes={'breakeven': 10, 'loss': 32, 'win': 14}
    phase_d: n=232 mean_R=0.035 win%=39.2 outcomes={'loss': 100, 'win': 85, 'timeout': 7, 'breakeven': 40}
    long: n=156 mean_R=-0.004
    short: n=132 mean_R=-0.018
    timeouts: n=7 mean_R=0.609
- ('WYCKOFF-BOOK', 'C'): n=120 mean_R=0.010 win%=38.3 outcomes={'win': 43, 'loss': 51, 'timeout': 3, 'breakeven': 23} losers=51 losers_MFE>=1R=2 R_planned_median=2.04218496484588 breakeven_winrate_needed=0.329
    spring: n=9 mean_R=-0.477 win%=22.2 outcomes={'loss': 7, 'win': 2}
    phase_d: n=111 mean_R=0.049 win%=39.6 outcomes={'win': 41, 'loss': 44, 'timeout': 3, 'breakeven': 23}
    long: n=63 mean_R=0.034
    short: n=57 mean_R=-0.017
    timeouts: n=3 mean_R=0.747

PIT check: max exit_time 2024-02-28T12:45:00Z, max last_bar 2024-02-29T23:45:00Z, cutoffs {'2024-03-01T00:00:00Z'}

### Fees and the R:R floor (re-priced with risk_model.cost_r, as simulate() does; MIN_RR = 2.0)

```
MIN_RR 2.0
ICT DE40 15m A: booked=16 feeR_med=0.267 stop%_med=0.375 pass_floor=11 gross_mean_all=0.148 net_mean_all=-0.145 gross_mean_pass=0.332 net_mean_pass=0.015
ICT DE40 1H A: booked=22 feeR_med=0.110 stop%_med=0.909 pass_floor=17 gross_mean_all=0.539 net_mean_all=0.390 gross_mean_pass=0.646 net_mean_pass=0.494
ICT DE40 1H B: booked=22 feeR_med=0.110 stop%_med=0.909 pass_floor=17 gross_mean_all=0.362 net_mean_all=0.213 gross_mean_pass=0.446 net_mean_pass=0.294
ICT DE40 1H C: booked=9 feeR_med=0.148 stop%_med=0.674 pass_floor=7 gross_mean_all=0.857 net_mean_all=0.715 gross_mean_pass=1.089 net_mean_pass=0.966
ICT DE40 4H A: booked=8 feeR_med=0.048 stop%_med=2.174 pass_floor=8 gross_mean_all=0.103 net_mean_all=0.049 gross_mean_pass=0.103 net_mean_pass=0.049
ICT US500 15m A: booked=19 feeR_med=0.253 stop%_med=0.395 pass_floor=14 gross_mean_all=-0.020 net_mean_all=-0.397 gross_mean_pass=-0.176 net_mean_pass=-0.517
ICT US500 1H A: booked=19 feeR_med=0.148 stop%_med=0.677 pass_floor=14 gross_mean_all=-0.140 net_mean_all=-0.316 gross_mean_pass=0.043 net_mean_pass=-0.132
ICT US500 1H B: booked=19 feeR_med=0.148 stop%_med=0.677 pass_floor=14 gross_mean_all=-0.148 net_mean_all=-0.325 gross_mean_pass=0.031 net_mean_pass=-0.144
ICT US500 1H C: booked=1 feeR_med=0.072 stop%_med=1.392 pass_floor=1 gross_mean_all=2.850 net_mean_all=2.778 gross_mean_pass=2.850 net_mean_pass=2.778
ICT US500 4H A: booked=6 feeR_med=0.091 stop%_med=1.153 pass_floor=4 gross_mean_all=0.104 net_mean_all=-0.023 gross_mean_pass=-0.089 net_mean_pass=-0.239
ICT XAUUSD 15m A: booked=31 feeR_med=0.334 stop%_med=0.299 pass_floor=29 gross_mean_all=0.430 net_mean_all=0.067 gross_mean_pass=0.529 net_mean_pass=0.188
ICT XAUUSD 1H A: booked=30 feeR_med=0.128 stop%_med=0.780 pass_floor=18 gross_mean_all=0.326 net_mean_all=0.142 gross_mean_pass=0.688 net_mean_pass=0.483
ICT XAUUSD 1H B: booked=30 feeR_med=0.128 stop%_med=0.780 pass_floor=18 gross_mean_all=0.374 net_mean_all=0.189 gross_mean_pass=0.759 net_mean_pass=0.554
ICT XAUUSD 1H C: booked=10 feeR_med=0.099 stop%_med=1.016 pass_floor=5 gross_mean_all=-0.092 net_mean_all=-0.260 gross_mean_pass=0.617 net_mean_pass=0.444
ICT XAUUSD 4H A: booked=7 feeR_med=0.078 stop%_med=1.287 pass_floor=5 gross_mean_all=-0.343 net_mean_all=-0.447 gross_mean_pass=-1.000 net_mean_pass=-1.121
WYC DE40 15m A: booked=57 feeR_med=0.336 stop%_med=0.298 pass_floor=22 gross_mean_all=-0.026 net_mean_all=-0.413 gross_mean_pass=0.256 net_mean_pass=-0.260
WYC DE40 1H A: booked=57 feeR_med=0.170 stop%_med=0.588 pass_floor=27 gross_mean_all=0.094 net_mean_all=-0.104 gross_mean_pass=-0.136 net_mean_pass=-0.392
WYC DE40 1H B: booked=57 feeR_med=0.170 stop%_med=0.588 pass_floor=27 gross_mean_all=0.090 net_mean_all=-0.109 gross_mean_pass=-0.025 net_mean_pass=-0.280
WYC DE40 1H C: booked=24 feeR_med=0.148 stop%_med=0.679 pass_floor=10 gross_mean_all=0.329 net_mean_all=0.136 gross_mean_pass=0.086 net_mean_pass=-0.169
WYC DE40 4H A: booked=20 feeR_med=0.094 stop%_med=1.095 pass_floor=11 gross_mean_all=-0.526 net_mean_all=-0.659 gross_mean_pass=-0.726 net_mean_pass=-0.879
WYC US500 15m A: booked=47 feeR_med=0.346 stop%_med=0.289 pass_floor=20 gross_mean_all=0.326 net_mean_all=-0.129 gross_mean_pass=0.443 net_mean_pass=-0.148
WYC US500 1H A: booked=64 feeR_med=0.242 stop%_med=0.413 pass_floor=28 gross_mean_all=-0.083 net_mean_all=-0.381 gross_mean_pass=-0.130 net_mean_pass=-0.489
WYC US500 1H B: booked=64 feeR_med=0.242 stop%_med=0.413 pass_floor=28 gross_mean_all=-0.143 net_mean_all=-0.441 gross_mean_pass=-0.201 net_mean_pass=-0.561
WYC US500 1H C: booked=28 feeR_med=0.247 stop%_med=0.405 pass_floor=12 gross_mean_all=-0.493 net_mean_all=-0.810 gross_mean_pass=-0.550 net_mean_pass=-0.917
WYC US500 4H A: booked=22 feeR_med=0.094 stop%_med=1.061 pass_floor=14 gross_mean_all=0.114 net_mean_all=-0.009 gross_mean_pass=-0.022 net_mean_pass=-0.172
WYC XAUUSD 15m A: booked=184 feeR_med=0.398 stop%_med=0.251 pass_floor=63 gross_mean_all=-0.169 net_mean_all=-0.617 gross_mean_pass=-0.530 net_mean_pass=-1.087
WYC XAUUSD 1H A: booked=167 feeR_med=0.203 stop%_med=0.494 pass_floor=69 gross_mean_all=-0.031 net_mean_all=-0.277 gross_mean_pass=-0.121 net_mean_pass=-0.439
WYC XAUUSD 1H B: booked=167 feeR_med=0.203 stop%_med=0.494 pass_floor=69 gross_mean_all=0.006 net_mean_all=-0.240 gross_mean_pass=-0.075 net_mean_pass=-0.393
WYC XAUUSD 1H C: booked=68 feeR_med=0.190 stop%_med=0.526 pass_floor=31 gross_mean_all=0.104 net_mean_all=-0.114 gross_mean_pass=0.021 net_mean_pass=-0.261
WYC XAUUSD 4H A: booked=68 feeR_med=0.118 stop%_med=0.847 pass_floor=34 gross_mean_all=0.080 net_mean_all=-0.068 gross_mean_pass=0.036 net_mean_pass=-0.172

('ICT', 'A') n=158 feeR_med=0.184 feeR_mean=0.236 net_mean_all=-0.024 Rplan<MIN_RR=27 pass_floor=120 gross_pass=0.300 net_pass=0.062 win_pass=0.383
('ICT', 'B') n=71 feeR_med=0.126 feeR_mean=0.172 net_mean_all=0.059 Rplan<MIN_RR=16 pass_floor=49 gross_pass=0.442 net_pass=0.264 win_pass=0.327
('ICT', 'C') n=20 feeR_med=0.099 feeR_mean=0.152 net_mean_all=0.331 Rplan<MIN_RR=5 pass_floor=13 gross_pass=1.043 net_pass=0.905 win_pass=0.462
('WYCKOFF-BOOK', 'A') n=686 feeR_med=0.250 feeR_mean=0.310 net_mean_all=-0.347 Rplan<MIN_RR=359 pass_floor=288 gross_pass=-0.145 net_pass=-0.520 win_pass=0.212
('WYCKOFF-BOOK', 'B') n=288 feeR_med=0.204 feeR_mean=0.248 net_mean_all=-0.259 Rplan<MIN_RR=151 pass_floor=124 gross_pass=-0.093 net_pass=-0.406 win_pass=0.137
('WYCKOFF-BOOK', 'C') n=120 feeR_med=0.193 feeR_mean=0.237 net_mean_all=-0.227 Rplan<MIN_RR=60 pass_floor=53 gross_pass=-0.096 net_pass=-0.392 win_pass=0.132
```

_Generated from `$TMP/runs/*.json` by the commands above; per-slice raw funnels (incl. bar-level counts, incomplete reasons, bias refusals) are in those files and in `diagnose-methods.py report`._
