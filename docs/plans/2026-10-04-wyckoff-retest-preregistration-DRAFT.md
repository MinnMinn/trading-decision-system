# Wyckoff re-test -- pre-registration [WY-P0 DRAFT]

**Status: DRAFT -- not yet committed as a pre-registration; no Wyckoff outcome read for it.**
Written 2026-10-04 from a read-only review: book, engine, data, three designs and two critiques. Nothing in this file has been
run on prices. It becomes a pre-registration only when it is committed, without `-DRAFT`, together with the R0 counts
(§4) and the code SHA (§10), and after the owner signs the items in §12.4.

Abbreviations. W = `scripts/wyckoff_rules.py`, B = `scripts/backtest-methods.py`, RC = `scripts/real_costs.py`,
EC = `scripts/research/edge_census.py`, WA = `knowledge/wyckoff/advance.md`, WMT = `knowledge/wyckoff/modern-tools.md`.
Cites are `file:line`.

---

## 1. Question

Owner, 2026-10-04: *"Tao không tin một phương pháp nổi tiếng (Wyckoff) lại không có bất kì một kết quả tốt nào."*

**Question.** Do the book's Wyckoff trades predict forward return in the direction the book gives? The trades are the
Phase-C Spring or Shakeout, the Phase-D BU/LPS, the same trades inside a higher-timeframe range, and the full campaign.
Each trade is detected at its decision bar and judged net of real FTMO cost, against a placebo with the same trade
geometry.

A second question is reported but not gated: did the engine's departures from the book, or the way past tests were
scored, hide an edge? See §7.

**Scope.**
- This tests mechanical, point-in-time readings of the books.
- It does not test a discretionary trader.
- A null result is stated as "no mechanical edge of at least δ at this power". It is never stated as "Wyckoff is false" (§9).

---

## 2. What was tested before, and why it may have been unfair

| Prior read | Result | Why it cannot settle the question |
|---|---|---|
| Prop search, 2024-03-01 to 2025-03-01 (`docs/backtests/2026-09-27-prop-setup-search.md`) | 0 of 180 passed (90 Wyckoff) | The The5ers inactivity rule was breached by all 180 records, so 0/180 was certain before any edge was measured (`docs/audits/2026-10-02-strategic-diagnosis.md:37`). Cost was a flat 0.05 %/side, several times FTMO's recorded spread (`:38`). The prop horizon counted only days with a trade (`:40`). Even a true +0.5R/trade strategy passes with probability ≤ 0.08 (`:46`). |
| Method diagnosis (`docs/audits/2026-09-28-method-diagnosis.md`) | 686 trades, gross −0.036R, median planned R 1.89 (`:97`, `:312`) | Absolute R on fixed targets, with no placebo, so "≈ 0" only says targets were hit about as often as their R:R implies. 80 % of trades are Phase-D legs on the LPS[C] path (`:88`). The 2R floor refused 359 of 686, and the trades it kept were worse: gross −0.145R (`:100`, `:371`). |
| "73 % of springs are Shakeouts, never traded" | 569 of 781 (`:83-84`) | That label is read at the last window, so it counts closes after the reclaim (W:558-560). At the decision bar the Shakeout gate removed 64 of 897 structures (`:85-86`). The skip at B:1403 contradicts both books (WA:331, WA2-12 at WA:1083), but trading Shakeouts can add only about 50 % to the 136-trade Spring leg. |
| Fidelity funnel and fx variants (`docs/audits/2026-09-29-wyckoff-fidelity-funnel.md`) | Mixed signs, e.g. `fx_w2`: XAU −16.8 → +19.5R but DE40 +22.6 → −8.3R | 15m only, 3 symbols. The fixes do not add up (all four on XAU: −33.9R). They were adopted after the outcomes were read, so they are a forking path. |
| Real-cost reprice, re-run 2026-10-04 (`docs/audits/2026-10-04-real-costs-reprice-rerun.md:16-34`) | DE40 +23.5R (n=24), US500 +6.0R (n=26), XAU −35.6R (n=114); 15m, development data | 2 of 6 cells, seen after the fact. The doc itself calls them "a lead for the pre-registered Wyckoff re-test, not evidence" (`:32-33`). L1 (§7.3) handles this lead. |
| Engine departures from the books (engine review, 18 rows) | -- | All of these were present in every past read: <br>• the R:R floor of 2.5, an ICT rule (`analysis-params.json` `ict.min_rr`, B:2120); <br>• the ICT higher-timeframe gate (B:1522); <br>• an invented Phase-D target of ceiling + 1×TR (B:1455; fidelity W-20); <br>• a tight BU stop (B:1431); <br>• fills at the signal close (B:1429/1457); <br>• tick volume driving CHoBEV, Test, SOS and BU (W:443, 594, 604, 610). |

**Never done.**
- No read has scored a Wyckoff event against a placebo.
- No read has scored the book's campaign: a partial entry at the Spring, adds at the Test and LPS, and a hold to the higher-timeframe target (WA:1082, 1086, 1090).
- No read has tested the volume-dependent half of the method on real volume.

---

## 3. Hypotheses and point-in-time definitions

Base design: the Skeptic design, with the fixes that both critiques require. In summary:
- a small family, one-sided in the book's direction;
- one event per structure;
- a placebo in ATR multiples;
- an owner-signed δ and a three-way verdict;
- perturbations that can veto a result but never select one.

### 3.1 Detector DET-PO: the engine's structure, read on price only

**Windows.**
- Each decision bar k gets one window: the 300 bars ending at k, inclusive (B:1289 `WYCKOFF_WINDOW`).
- `W.detect_accumulations` (W:367) runs on the window for longs, and `W.detect_distributions` (W:623) for shorts.
- Pivots come from `W.window_pivots` (W:189-200). It keeps only pivots whose ±`pivot` bars lie inside the window. Every field of a record is therefore known at the close of k.

**Parameters.** P is a per-call copy of `W.PARAMS` (W:118-140) with these changes:
- **`price_only=True`.** This is a new key, default False (§10). It makes the six volume clauses count as satisfied:
  - W:443, the CHoBEV effort clause;
  - W:523, the LPS[C] SOS effort clause;
  - W:544, the LPS[C] pullback;
  - W:594, the Test;
  - W:604, the SOS effort clause;
  - W:610, the BU pullback.

  Volume type, the VP/LVN abandon rule and SOT are still computed, but nothing in this family reads them. CHoBEV becomes "spread larger than the mean of the last reactions" (W:425-443), and its effort leg is dropped. This is disclosed as a departure from WA:274-277.
- **`spring_max_bars_outside=12`.** This sets the reclaim search window. 12 is `PARAMS.test_window` reused, not a tuned value. Spring/Shakeout typing is redone in §3.2 with the engine's per-timeframe `sob`.
- **`fx_w1/w2/w3/w5` off** (v1 detection). The owner-adopted fixes were picked after their outcomes were read, so they appear only as perturbation P1.
- **Everything else stays at engine defaults:**
  - pivot 3;
  - `downtrend_swings` 2;
  - `chobev_needed` 3;
  - `min_phase_b_swings` 2;
  - the ceiling raised by Phase-B swing highs (WY-3);
  - the ran-away guard;
  - `phase_d_window` 40;
  - `commitment_bars` 2 (`docs/architecture/analysis-params.json`).

**Gates added in the harness.** Both are fixed now and never tuned.
- **Cause gate (WA:333 "thường xảy ra trễ"; WA2-10 at WA:1081).** The record's `phase_b_tests` (counted at W:497-506) must show at least one confirmed Phase-B swing in an outer third of the TR before the Phase-C event. One is the minimum non-zero value. W_TOUCH_MIN=2 (B:190) is not used.
- **Horizontal gate (WA2-42 at WA:1113).** Records with `sloped=True` are excluded.

**De-duplication.** One event per structure and leg. The key is (symbol, timeframe, side, absolute SC bar, absolute AR bar). Later windows that re-detect the same structure do not fire again.

### 3.2 W-C-long: Phase-C shake, long (Spring + Shakeout)

**Event definition.**
- **Break bar.** `s` = the record's `spring`: the first bar after Phase B whose low is below `tr_lo`.
- **Reclaim.** `r` = the first bar in [s, s+12] that closes above `tr_lo`. If there is none, there is no event, and the case is logged.
- **Type, decided at the close of r** (the engine's R6 at W:558-560, read at the decision bar):
  - SPRING if r − s ≤ `sob[tf]` and #{q ∈ [s, r) with C[q] < `tr_lo`} ≤ (r − s + 1)/2;
  - otherwise SHAKEOUT.
  - `sob` is set at B:96-97: 15m 6, 1H 4, 4H 3.
- **Spring low.** `spring_low` = min L[s..r].
- **Signal bar.**
  - A SPRING signals at r (WA2-11 at WA:1082).
  - A SHAKEOUT signals at its Test t, because a Shakeout means supply remains and the book says to expect a longer test (WA2-12 at WA:1083).
  - t = the first q ∈ (r, r+12] with L[q] ≤ `tr_lo` + TR/3 and C[q] ≥ (H[q]+L[q])/2. This is the engine's R8 (W:589-595) without its volume clause.
  - Any bar in (r, q] with a low below `spring_low` cancels the event.
  - No Test means no event, and the case is logged.

**Trade.**
- **Entry:** the open of the bar after the signal bar.
- **Stop:** `spring_low` × (1 − 0.0005). The buffer is B:99 `STOP_BUFFER_PCT`; the placement follows WMT p271.
- **Target:** `tr_hi`, the AR, i.e. the opposite side of the range (WA2-36 at WA:1107; WMT:185). The Phase-B raised ceiling is a descriptive variant.
- **Time cap:** H = `bt.P[tf]["H"]` (B:96-97): 15m 96 bars, 1H 72, 4H 30.
- **Skips:** if the entry open is already at or beyond the stop or the target, the trade is skipped and the skip is counted.
- **Walk:** `bt.walk` (B:596) with:
  - `fx_gap_fill` on, so a gap through the stop fills at the open (B:577);
  - `mgmt` none;
  - stop checked before target on the same bar (B:651-661);
  - `flat_before_rollover` off, with swap paid.

**Hypothesis H-WC.** The mean net excess R is greater than 0.

### 3.3 W-D: Phase-D BU/LPS long and LPSY short, pooled

**Event.** The record's `bu.bar` equals k. This covers both the spring path (W:606-614) and the lps_c path (W:541-549). Longs come from accumulations, and shorts from distributions as their mirror. Shorts at LPSY are the book's preferred short (WA2-24/25 at WA:1095-1096).

**Trade.**
- **Entry:** the open of k+1.
- **Stop:**
  - spring path: `spring_low` −0.05 % (WMT p271);
  - lps_c path: `tr_lo` −0.05 %. This is a project choice, because a structure with no Spring has no Spring low.
  - Shorts are mirrored.
- **Target: W7 with a containment check.** This is the only target the book gives (WA2-19 at WA:1090).
  - The higher timeframe is h = `HTF_OF[tf]` (B:789).
  - DET-PO runs on the h prefix available at the close of k (`pit.series_as_of`, `scripts/pit.py:139`).
  - From the same-side records found there, take the latest one where:
    - [`tr_lo`, `ceiling` + TR] contains C[k], and
    - its target lies beyond the entry. The target is C[`sos`] if a SOS exists, else `tr_hi`, mirrored for shorts, as at B:1050-1054.
  - If no such record exists, the trade exits on time at H.
  - Today's engine takes `recs[-1]` with no containment check (B:1052, B:1078). The rule above is the fix.
- **Cap:** H.

**Hypothesis H-WD.** The mean net excess R is greater than 0.

### 3.4 W-CTX: the Phase-C shake in higher-timeframe context

**Events.** W-C-long events from all three timeframes, pooled, where both of these hold at the signal close:
- a DET-PO accumulation record on `HTF_OF[tf]` contains C[signal] in [`tr_lo`, `ceiling` + TR];
- no HTF distribution record contains it.

Book basis: WA2-18/19 at WA:1089-1090.

**Trade.** The same as W-C-long.

**Hypothesis H-CTX.** The mean net excess R is greater than 0.

### 3.5 W-CAMP: the campaign

This is the method as the owner means it. It is pooled across timeframes. Each accumulation structure with a W-C-long event gets up to three tranches of equal quantity.

**Tranches.**
- **T1:** the W-C-long entry.
- **T2:** for a SPRING only, the Test of §3.2, if it comes within 12 bars of r. Entry is at the next open. For a SHAKEOUT, T1 already is the Test, so there is no T2.
- **T3:** the record's BU/LPS bar, the W-D long event of the same structure, if it comes before the campaign has exited.

**Shared exits.**
- **Stop:** one stop for all tranches, at `spring_low` −0.05 %.
- **Target:** the W-D target, as in §3.3, evaluated at T1's signal close.
- **Time exit:** if there is no target, exit on time H bars after the last filled tranche.
- **Order of events:** a tranche whose entry open is already beyond the stop is skipped. Once the target or stop is hit, later tranches do not fill.

**Score.**
- R = Σ_k (X − e_k) / Σ_k (e_k − stop) over filled tranches, where X is the exit price and e_k each tranche's entry.
- Cost = Σ_k `cost_r`_k · (e_k − stop) / Σ_k (e_k − stop).

**Hypothesis H-CAMP.** The mean net excess R is greater than 0.

### 3.6 G-C: generic sweep control (diagnostic, not in BH)

This checks whether the Wyckoff range adds anything beyond a plain sweep and reclaim. That plain pattern is the one behind E1/E3 (`docs/audits/2026-10-02-edge-census.md`).

**Setup (R0).** For each timeframe, R0 measures N = the median of (break bar − SC bar) over R1's W-C-long events. This uses no outcomes.

**Event.** A control event fires at bar r when all of these hold:
- some s ∈ [r−12, r] has L[s] below ℓ = min L[s−N, s);
- r is the first bar that closes above ℓ;
- no W-C-long event of the same symbol and timeframe that is ALREADY SIGNALLED at bar r has its break bar within N bars
  before r (point in time: a control is never chosen with later bars). The literal "±N bars" variant, which also excludes
  on W-C-long breaks after r, is reported beside it as a diagnostic only (`gc_contrast` vs the deciding `gc_contrast_known`);
- at most one control event per N bars.

**Trade.**
- **Entry:** the open of r+1.
- **Stop:** min L[s..r] −0.05 %.
- **Target:** max H[s−N, s).
- **Cap:** H.
- Placebo, cost and statistics are as in §5.

**Attribution.** Δ = mean net excess (W-C) − mean net excess (G-C), with a one-sided p from a week-cluster bootstrap.

### 3.7 Descriptive only (never gated, never selected)

- **W-C-short.** The UT/UTAD entered at the reclaim. The book hedges this trade (WA2-24 at WA:1095), and the engine's shorts were −0.052R.
- **Subsets of W-C-long.** The SPRING and SHAKEOUT subsets separately, plus the Shakeout entered at its reclaim.
- ~~Shakeout through a lower timeframe~~ and ~~σ-unit time exit~~: struck before sealing. The books do not define the
  first precisely enough to implement without inventing rules, and the census σ unit drops almost every multi-day hold.
- **1D.** Too few events: about 18 springs on the 8 tradeable symbols.
- **Variants.** The flatten-before-rollover variant, a placebo matched on the sign of the 20-day trend, and per-symbol tables.

---

## 4. Data, symbols, timeframes, windows, reads

| | |
|---|---|
| Venue / feed | FTMO-Demo MT5 exports, `data/history/ftmo/ohlcv.<SYM>.<tf>`; the volume field is MT5 tick count and DET-PO does not read it |
| Tradeable (R1, R3) | XAUUSD, XAGUSD (metals); US500, US30, USTEC, DE40, FRA40, AUS200 (indices) |
| Replication (R2), never read for Wyckoff | XPTUSD, XPDUSD (metals); US2000 (US); EU50, UK100 (EU); JP225, HK50 (Asia) |
| Excluded on data quality, decided now | N25 (about 260 bars a month, and a 376-day hole from 2022-08-05); SPN35 (half-session coverage) |
| Timeframes | 15m, 1H, 4H. 1D descriptive only. |
| Real-volume family V | Binance BTCUSDT, ETHUSDT, SOLUSDT: `binance_um` 1h and 5m, 2020-01-01 → 2022-07-31 (SOL from 2020-09-14); `binance_spot` 5m, 2017-08-17 → 2019-12-31. 15m and 1H are resampled from 5m where needed. |

**Dense-data rule.** This rule is fixed now and applied in R0 on counts only.

- **Why it is needed.** Before 2021, the index 15m/1H/4H files hold about one bar a day (coverage log). Detection must therefore start at each series' dense month, not at `index.json` `first`.
- **Dense month.** For each symbol and timeframe, this is the first month from which every later month has a median daily bar count of at least 0.8 × that series' 2023 median. A hole longer than 7 days restarts the clock; this matters for XPT/XPD and their 124-day hole from 2016-06-10.
- **Dense days.** After the start, a day is dense if its count is at least 0.8 × the median of the previous 60 calendar days. This is point-in-time, and it adapts to the EU50/FRA40 session cut of 2024-12/2025-01.
- **Which events count.** An event counts only if the server day before its signal bar was dense, as in EC:108-114 `prev_dense`.
- **Provisional dense starts** (`cov.log` from the data review):
  - 1H: XAU 2004-07, XAG 2008-11, US30/AUS200 2019-03, US500/USTEC/FRA40 2021-02, DE40 2021-06;
  - 15m indices: about 2021-09 (DE40 2022-01).
  - R0 pins the exact table, and it is committed with the pre-registration.

**Reads.** Each runs once. The script refuses to run a read out of order (§10).

| Read | Data | Role |
|---|---|---|
| **R0 COUNTS** | All of the above | Reads no outcomes. It records: <br>• events per cell, per group and per symbol; <br>• the distribution of planned R:R (target distance ÷ stop distance), known at entry; <br>• N for G-C; <br>• the HTF containment rate; <br>• the dense table; <br>• the point-in-time truncation probe. <br>It also fixes which cells are confirmatory (§6.1). Committed before sealing. |
| **R1 PRIMARY** | 8 tradeable symbols, dense days, all bars before 2024-03-01 | This is the first measurement of placebo excess for these definitions. The window is not pristine: the engine and E1/E3 have already read it (ledger period `cfd-development-pre-2024-03`). No 60/40 split: the direction is fixed by the book, so a discovery half would choose nothing and would halve power. |
| **R2 PARTIAL REPLICATION** | The 7 replication symbols, before 2024-03-01 | Read only for R1 survivors, so these symbols stay unread for Wyckoff otherwise. They share macro days with R1, and the fund search read XPT/XPD (ledger). Pass needs both: <br>• pooled net excess > 0; <br>• at least 3 of the evaluable clusters (each with ≥ 10 events, and at least 2 evaluable) show the book's sign. |
| **R3 EXPOSED** | 8 tradeable symbols, 2024-03-01 → end of data (metals 2026-10-01, indices 2026-09-28) | Read only for survivors, and it can only veto: <br>• The prop search read 2024-03 → 2025-03 (`oos_exposed` in the ledger). <br>• The stability files scored WYCKOFF-BOOK from 2025-03 on (`data/history/stability/cfd-*.json`). <br>A survivor is vetoed if net excess ≤ 0. FRA40 rows after 2024-12 are flagged for the session cut. |
| **R4 FORWARD** | FTMO bars exported after sealing; the window starts at the seal commit's committer date, never chosen by the analyst, through the edge-followup export path (`docs/plans/2026-10-02-edge-followup-preregistration.md:41-50`) | The only path that can confirm. It is read once per surviving cell, at ≥ 100 forward events or 12 months, whichever comes first. Pass: net > 0 and one-sided p < 0.10. |
| **V** | Binance window above | One read, family V (§6.3). These spans were read by the H7x and C1 studies but never for Wyckoff. The improve-crypto Wyckoff records start at 2022-09-05 (`docs/experiments/2026-09-24-improve-crypto-*-WYCKOFF-BOOK.json`). |
| **L1** | §7.3 | One read on exposed data, veto only. Needs the committed R0 record (`--counts`). |
| **ABL** | §7.1-7.2, R1 window only | One read, descriptive. Takes its dense starts from the committed R0 record (`--counts`). |

---

## 5. Measurement (house style, as in EC / F3 / F4 / H7x)

**Outcome.** The R of the book trade (§3), net of cost. Gross R comes from `bt.walk`. R uses the planned stop distance, so a gap fill can produce a loss beyond −1R.

**Placebo** (it removes drift, hour-of-day effects and the payoff geometry behind the earlier absolute-R reads):
- **Sample.** For each event, 200 bars are drawn with a fixed seed (sha256 of `WY-P0|sym|tf|signal_time`) from the same symbol, timeframe and read, the same server-clock bar-of-day slot, and the same side, on days whose previous day was dense.
- **Placebo trade.** Each placebo bar p gets the event's stop and target distances in ATR20 multiples, using ATR20 at p−1 (mean true range over 20 bars). The event's own distances are measured with ATR20 at the signal bar. Each placebo trade has the same cap and walk rules, and the same tranche offsets for W-CAMP. For a trade with no target, the placebo also has stop and cap only.
- **Excess.** excess = R_event − mean(R_placebo), both gross. Then net = excess − cost_event.

**Cost (FTMO).**
- `RC.cost_r(entry, stop, t_in, t_out, sym, side, "ftmo_demo_2026_09_relspread", spread_stat)` (RC:471). Spread is half at the entry hour and half at the exit hour, plus swap for each night held.
- The harness asserts `RC.HOUR_FRAME == "server_table"` (RC:295-296; fixed in commit 1666367).
- Each cell has four cost lines: {median, p90 spread} × {today's swap, zero swap}. Today's swap points stand in for 2004-2024, when rates went from 0 % to 5 %. The zero-swap line is there so that swap cannot decide the verdict.
- Commission is 0/UNKNOWN (RC:463), and this is disclosed.
- W-CAMP adds up the cost of each tranche (§3.5).

**Cost (Binance, family V).**
- `COST_RT` = 12 bp per round trip: taker 5 bp + slippage 1 bp per side. The stress line is 14 bp (`scripts/research/edge_h7x.py:104-106`). Cost is converted to R through the stop distance.
- Funding is charged on perp holds with `edge_h7x.funding_paid` (:377).
- Spot-era bars carry perp cost, the convention of `edge_h7x.merge_candles` (:165).

**Statistics.**
- Standard errors are CR1, clustered by ISO week of the signal bar (`EC.cr1` :432). Holds overlap across days, and the three timeframes are pooled in some cells.
- The test is Student-t with G−1 df (`EC.t_sf` :448), where G = weeks with events.
- BH uses `EC.bh` (:490).
- The one-sided 95 % upper bound uses the same SE.
- Bootstrap CIs resample whole weeks, 2,000 resamples, fixed seed.

---

## 6. Tests, family size, decision rule

### 6.1 Family W (FTMO CFDs, R1): at most 8 confirmatory cells

| Cell | Timeframes | Hypothesis |
|---|---|---|
| W-C-long-15m, W-C-long-1H, W-C-long-4H | one each | H-WC |
| W-D-15m, W-D-1H, W-D-4H | one each | H-WD |
| W-CTX | pooled | H-CTX |
| W-CAMP | pooled | H-CAMP |

- **Count gate (R0, before any outcome).** A cell with fewer than 30 R1 events becomes descriptive, and m shrinks to match. The final m is written into the sealed pre-registration.
- **Test.** One-sided, in the book's direction, on mean net excess at median spread and today's swap. BH at q = 0.10 over the m confirmatory cells.

### 6.2 Gates and verdicts (per cell)

**R1 SURVIVOR** needs all of:
1. BH rejection;
2. net > 0 on all four cost lines (§5);
3. **breadth:** net excess > 0 in metals and in indices separately, each with at least 20 events. If either group has fewer than 20, breadth cannot be met, and the cell is at best INCONCLUSIVE;
4. the sign holds (net excess > 0) in at least 5 of the 6 perturbations below. Each runs in a fresh process, because `_WY_CANDIDATES` keys only the fx keys (B:1636). Perturbations can only veto.
   - P1: `fx_w1/w2/w3` on (the owner-adopted fixes);
   - P2: tick-volume clauses on, with tick volume ÷ its trailing 20-day median at the same server hour (point-in-time);
   - P3: 600-bar window;
   - P4: pivot 4;
   - P5: Shakeout reclaim window 24;
   - P6: time cap 2 × H.

**EDGE-CANDIDATE** needs all of:
- an R1 survivor;
- an R2 pass;
- no R3 veto.

It then goes to R4 forward. Nothing goes live from this study.
- **Wyckoff-attributed** if Δ ≥ 0 against G-C (§3.6).
- **Otherwise it is labelled "the shake works, but the Wyckoff range adds nothing measurable".** This is still a positive answer for the owner, and it is handed to the edge families.

**AGAINST THE BOOK.** Two-sided p < 0.05 with a negative sign, as with E1/E3 continuation. It is logged and handed to the edge families, never credited to Wyckoff. For the closing rule below, it counts as "no Wyckoff edge" for that cell.

**NO MECHANICAL EDGE at this power.** The one-sided 95 % upper bound of net excess is below δ (§12.4; proposed δ = 0.20R per trade, owner to sign), or the cell is AGAINST THE BOOK.

**INCONCLUSIVE.** Anything else. It never licenses new variants on history. Only forward bars can settle it.

**Closing rule.** "Wyckoff closed as a price-mechanical setup family on these CFDs" requires all of:
- W-C-long-15m and W-C-long-1H both read NO MECHANICAL EDGE;
- W-CAMP reads NO MECHANICAL EDGE;
- no cell reads EDGE-CANDIDATE;
- G-C has been read out.

"Closed overall" also needs family V to be null at its own power. That cannot happen in this study (§6.3), so the volume half stays open.

### 6.3 Family V (Binance, real volume): at most 4 cells, its own BH at q = 0.10

The detector is the engine's, unchanged: real volume, `volume_kind="traded"`, `price_only` off, and the 12-bar reclaim and typing of §3.2. 15m and 1H are pooled, clustered by ISO week.

- **V1 W-C-long:** as in §3.2.
- **V2 W-D:** as in §3.3, with the HTF resampled from 1h.
- **V3 low-volume Spring:** within V1, the engine's `vol_type` 1 minus types 2-3 (W:270; WMT Bảng 2.1; WA2-11 "on LOW volume"). One-sided ≥ 0, using a week-cluster bootstrap.
- **V4 effort vs result** (WA:192-194):
  - **Long event:** C[i−1] < C[i−21]; V[i] ≥ 2 × the median volume of the same UTC hour over the previous 20 days; the range of bar i ≤ the median range of the previous 20 bars; and C[i] > min C[i−20, i).
  - **Trade:** stop at L[i] −0.05 %, time exit at H. Shorts are mirrored, at most one event per 20 bars per side.

V reports EDGE-CANDIDATE (then forward on new Binance bars), AGAINST THE BOOK, or INCONCLUSIVE. Its power (§8) is too low for a closing verdict.

---

## 7. Engine ablation (descriptive) and the L1 lead

### 7.1 Purpose and rules

- **Purpose.** Explain why past absolute-R reads were negative, and whether the engine's deviations hid anything.
- **Data.** Development data only: the R1 window and the 8 tradeable symbols, at 15m, 1H and 4H.
- **No gates.**
  - Nothing here enters a BH family.
  - Nothing here is selected.
  - No arm can become a candidate except through a new pre-registration on forward data.
- **Arms.**
  - Each arm changes exactly one variable from ENGINE-BOOK.
  - Each runs in a fresh process.
  - Each is scored with §5 (placebo excess, real cost, CR1 by week) and also as absolute R.
- **Output per arm, per leg (spring, phase_d), per timeframe:**
  - n, mean gross R and mean net excess;
  - ENGINE-BOOK minus the arm, with a week-bootstrap 90 % CI.

### 7.2 Arms

**Reference arms.**
- **LEGACY-as-scored.** The engine as it was judged:
  - fx keys off and Shakeouts skipped;
  - the 2.5R floor and the ICT HTF gate;
  - a Phase-D target of ceiling + 1×TR;
  - fills at the signal close and a flat 0.05 %/side fee;
  - absolute R.
- **LEGACY-rescored.** The same signals scored with §5. LEGACY-as-scored vs LEGACY-rescored isolates the scoring.
- **ENGINE-BOOK.**
  - `fx_w1/w2/w3/w5` on;
  - `fx_w_shakeout=test` (new key, §10);
  - no floor and no ICT gate;
  - `fx_w7_htf_target` with `fx_w7_contain=on` (new key);
  - fill at the next open, `fx_gap_fill` on, real cost.

**One-variable arms**, each a single change from ENGINE-BOOK:

| Arm | Change |
|---|---|
| A1 | skip Shakeouts |
| A2 | 2.5R floor, applied in the harness with the cost known at entry |
| A3 | ICT HTF gate |
| A4 | Phase-D target ceiling + 1×TR |
| A5 | 600-bar window |
| A6 | `fx_w_stop=spring_low` |
| A7 | tick volume normalised by hour |
| A8 | `fx_w_spt=ceiling` |
| A9 | fill at the signal close |
| A10 | `flat_before_rollover` |

**Limitation.** The engine's Test still needs tick volume (W:594). Its Shakeouts also only reclaim within `sob`, so A1 covers only that subset. The 12-bar Shakeout is tested only in family W.

### 7.3 L1: the 15m index lead (one confirmatory test, its own family m = 1)

- **Hypothesis.** The engine's config A, exactly as in `scripts/research/reprice_real_costs.py` at the sealed SHA, has mean net R per trade > 0 on the 6 indices pooled.
- **Scope.**
  - 15m, real cost in the fixed hour frame, no flatten.
  - The 6 indices are pooled so that the read does not cherry-pick DE40 and US500. DE40, US500 and XAU are reported separately as descriptive.
  - Read once on the exposed window, 2024-03-01 → end.
- **Gate.** One-sided p < 0.10 (CR1 by date) and net > 0.
  - Pass: forward stage only.
  - Fail: the DE40/US500 lead is closed.
- **Labelled exposed.** The prop search and the stability files have already read this window.

---

## 8. Power (counts only, no outcomes)

**Planning counts.**
- **Basis.** The engine funnel gives about 1 spring per 1,000 bars and 1 structure per 180-290 bars per symbol (`method-diagnosis`; coverage review). For example, XAUUSD 1H: 114,563 bars → 464 structures and 114 springs.
- **Not yet measured.** How many extra events the price-only detector adds, and how many the cause gate and horizontal gate remove. R0 measures both and the sealed version restates this table.

**Assumptions for the table.**
- Design effect 2, for the clusters XAU/XAG, US500/US30/USTEC and DE40/FRA40.
- Worst-case BH for one true effect at m = 8: one-sided α = 0.0125, so 80 % power needs 3.08 SE.
- R's standard deviation is about √(mean planned R:R) under the null. At the past median planned R of 1.89 that is ≈ 1.4R; at a planned R:R of about 4 it is ≈ 2.0R. R0 measures the planned R:R without reading outcomes.

| Cell | n events (R1) | n_eff | MDE (R), SD 1.4 / 2.0 | Bound half-width (1.645·SE), SD 1.4 / 2.0 |
|---|---|---|---|---|
| W-C-long-15m (≈1.28M bars pre-2024-03, ~70 % metals) | ~640 | ~320 | 0.24 / 0.34 | 0.13 / 0.18 |
| W-C-long-1H (336k bars) | 170-340 | 85-170 | 0.33-0.47 / 0.47-0.67 | 0.18-0.25 / 0.25-0.36 |
| W-C-long-4H (87k bars) | ~45-90 | ~22-45 | 0.64-0.92 / 0.92-1.31 | 0.34-0.49 / 0.49-0.70 |
| W-D (per timeframe) | assumed ≥ W-C (550 of 686 past trades were Phase-D) | -- | ≤ the W-C row | -- |
| V1 (15m + 1H pooled, 3 coins) | ~200 | ~70 | ~0.5 / ~0.7 | -- |
| R4 forward, per cell | 100 | ~50 | 0.42 (SD 1.4, one-sided 0.10) | -- |

**What this means.**
- **Closing a cell needs enough data.** To get the upper bound below δ = 0.20R at a point estimate of 0, a cell needs n_eff ≥ 133 at SD 1.4, or n_eff ≥ 271 at SD 2.0.
- **15m can close.** 1H can close only if its point estimate is at most about +0.02R. 4H and V cannot close and are expected to read INCONCLUSIVE.
- **The past effect sizes are below most MDEs.** E1's metals excess was about 0.1 z, and the past gross was −0.036R. Only a large hidden edge is detectable on history.
- **Data agent's counts check.** The data review's counts give about 62 % metals at 1H. This is why breadth requires both groups.
- **R0 must restate this table.** If R0 shows that 15m or 1H cannot reach the closing bound, the sealed pre-registration must say so before any outcome is read.

---

## 9. What each result means for the owner

| Result | Plain meaning | Next step |
|---|---|---|
| EDGE-CANDIDATE, Wyckoff-attributed | A book-defined Wyckoff trade beats random entries with the same stop and target, after real FTMO cost, in both metals and indices, on symbols never used for Wyckoff, and is not contradicted by the exposed years. | A sealed forward read (R4). Only after a forward pass is it built as an engine setup, with the 2.5R floor and the HTF gate added as separate policy layers. The floor is the owner's live rule (`analysis-params.json` `ict.min_rr`); it is measured, not dropped. |
| EDGE-CANDIDATE, shake only | The Spring/Shakeout reclaim works, but the Wyckoff range adds nothing over a plain sweep and reclaim. | The same forward path, credited to the sweep family. |
| AGAINST THE BOOK | Price continues through the shake instead of reversing, as E1/E3 found on metals. | Handed to the edge families. Not a Wyckoff result. |
| NO MECHANICAL EDGE at this power | For these definitions, the net edge is below δ with 95 % confidence. | Wyckoff is closed as a price-mechanical setup family on these CFDs. It is **not** "Wyckoff is false". This study does not cover: <br>• the discretionary read; <br>• real-volume typing; <br>• the 1D timeframe; <br>• anything smaller than δ. <br>Family V or forward data can reopen it. |
| INCONCLUSIVE | Not enough data to tell. This is expected for 4H and for family V. | Forward bars only. No new variants are tried on history. |
| ABL / L1 | Which engine deviations or scoring choices moved past results, and whether the 15m index lead survives the exposed years. | Explanation only. L1 pass → forward stage. |

---

## 10. Code to write (none exists yet)

1. **`scripts/wyckoff_rules.py`: add `PARAMS["price_only"]`** (default False). It guards the six volume clauses (W:443, 523, 544, 594, 604, 610).
   - Test: the default output stays byte-identical. Use `scripts/tests/test_wyckoff_detect_equivalence.py` and the `ab_wyckoff_detect.py` pattern.
   - Test: on synthetic bars with `price_only=True`, records do not change under any permutation or rescaling of V.
2. **`scripts/backtest-methods.py`: add `fx_w_shakeout` {off, test} at B:1403 and `fx_w7_contain` {off, on} at B:1052/B:1078.**
   - Both default to off, and the default output must stay byte-identical.
   - Both are ablation-only (§7). The family-W harness does not use `bt.scan`.
   - The fx-key registries name them too (the cross-file contract `scripts/tests/test_fx_registry_complete.py`):
     `scripts/snapshot.py` (scan-relevant fx keys), `scripts/stability-report.py` (`config_opts` defaults and
     `_SCAN_RELEVANT_KEYS`). Defaults off.
3. **New `scripts/research/edge_wyckoff.py`** with the commands `counts` (R0), `run --read {R1,R2,R3,V,L1}`, `forward` and `report`.
   - Guards copied from `edge_h7x`:
     - `_require_committed` (:678): the pre-registration and the code must be committed at the sealed SHA;
     - `_require_registration` (:697): a ledger entry must exist;
     - `_check_order` (:716): R1 before R2/R3, and R2/R3 only for survivors.
   - Parts:
     - a dense loader for 15m, 1H and 4H (`EC.Series` assumes 5m);
     - per-window DET-PO detection with dedup;
     - the event builders of §3;
     - the containment rule for HTF targets;
     - walks through `bt.walk` with `fx_gap_fill`;
     - the ATR-multiple placebo;
     - `RC.cost_r` with the hour-frame assert;
     - CR1, BH and the δ bound;
     - a Binance loader reusing `edge_h7x.load_candles` (:180) and `funding_paid`.
4. **New `scripts/research/wyckoff_ablation.py`** (`count` / `run` / `report`, one arm per process). It takes signals from `bt.scan(only=("WYCKOFF-BOOK",), opts=arm)` (B:1583) and re-walks each trade from the next open.
5. **Tests in `scripts/tests/test_edge_wyckoff.py`**, on synthetic bars only. They must pass before sealing.
   - **Point-in-time truncation probe.** 200 random events are re-detected on the series cut at the signal bar, with identical results. This also covers `phase_b_tests`, the cause gate and the Spring/Shakeout typing at the reclaim. The pattern is `leakage_probe_fund.py`.
   - Spring/Shakeout typing at the reclaim, and Test cancellation on a lower low.
   - Placebo geometry: ATR multiples, the slot match and the fixed seed.
   - The cost call, the hour-frame assert, and all four cost lines.
   - The W-CAMP R and cost aggregation.
   - Same-bar stop before target, and gap fills.
   - The G-C exclusion window.
6. **Paperwork.**
   - Commit this file without `-DRAFT`, together with the R0 table and the code SHA, before any `run`.
   - Write §42 records to `docs/experiments/wyckoff-retest-<seal date>/`.
   - Add ledger entries to `docs/architecture/research-ledger.json`:
     - families W, V and L1;
     - the perturbations;
     - the ablation count;
     - **the missing 2025-03-01 → 2026-09-28 period**, as `oos_exposed`. Today it is called exposed only in prose: the stability files read WYCKOFF-BOOK there, and other families read it as well.

---

## 11. Threats to validity

1. **No pristine history.**
   - R1 was read by the method diagnosis, the funnel, both reprices and E1/E3.
   - R3 was read by the prop search and the stability files.
   - R2 shares macro days with R1.
   - This design was written knowing E1/E3 (continuation on metals) and the DE40 lead. Directions come from the book, not from those results.
   - Only R4 is clean.
2. **The definitions are ours.** The books give no thresholds (`knowledge/footprint/wyckoff-logic.md:299`). The verdict covers DET-PO and §3, and the owner accepts them as "the book" before the run. Perturbations can veto but never select.
3. **Price-only is not the whole book.** Dropping the effort legs turns CHoBEV, SOS and BU into price patterns. The tick-volume arm (P2) and family V are the only checks on the volume half.
4. **Tick volume.** Spearman between the FTMO and MetaQuotes tick counts is 0.65-0.97 after normalising by hour. That may reflect a shared liquidity-provider feed, not traded size. P2 is weak evidence.
5. **Metals dominate.** About 62-70 % of events are metals, and E1/E3 showed continuation there. That is why breadth requires both groups.
6. **Correlated symbols** shrink the effective sample (design effect 2 assumed). The G-C contrast reuses the same days.
7. **Cost history.** The 2026-09 spread table is rescaled to history. Today's swap stands in for 2004-2024 (the zero-swap line guards this). Commission is unknown.
8. **Data hazards.**
   - Index files before 2021 hold about one bar a day.
   - EU50/FRA40 changed session around 2024-12.
   - XPT/XPD have a 124-day hole.
   - Binance spot volume (2017-2019) is a different venue from the perp.
9. **Regime selection.** Requiring a prior downtrend selects market states. The trend-matched placebo is reported.
10. **Several study families with no overall error control.** This study's count is recorded (§12) so it can be audited.
11. **Fixes chosen after results.** ENGINE-BOOK uses `fx_w2` (adopted after XAU +19.5R, with DE40 −8.3R). That is why the ablation is descriptive and why family W runs with the fixes off.

---

## 12. Experiment budget (§43) and sign-off

**12.1 Confirmatory tests.**
- Family W: at most 8, after the R0 count gate.
- Family V: at most 4.
- L1: 1.
- Total: at most 13, in three separate BH families.

**12.2 Veto-only checks**, applied to R1 survivors only:
- 6 perturbations;
- R2, R3 and four cost lines.

These cannot create a survivor.

**12.3 Diagnostic and descriptive, never gated:**
- G-C, one contrast per W-C cell and for W-CTX;
- the §3.7 list;
- 1D;
- per-symbol tables;
- ablation: 13 arms × 2 legs × 3 timeframes = 78 cells.

**Reads.**
- R0 once (no outcomes); R1, R2, R3, V, L1 and ABL once each; R4 once per survivor.
- Dataset reuse is recorded:
  - development window: at least the 6th Wyckoff read;
  - 2024-03 → 2025-03: the 2nd;
  - 2025-03 → 2026-09: the 2nd, counting the stability files.

**12.4 Owner sign-off before sealing:**
1. δ, proposed at 0.20R net per trade, and the closing rule in §6.2.
2. The `price_only` key in `wyckoff_rules.py` and the two ablation keys in `backtest-methods.py`. All default off, with byte-identical tests.
3. Whether family V and L1 stay in this pre-registration or move to separate ones.
4. Acceptance that the verdict covers DET-PO and §3 as "the book's mechanical core", and nothing wider.
