# Fund-search pre-registration -- DRAFT, UNSEALED (2026-09-29)

**Status: DRAFT. Nothing here is sealed, `declare` has not been run, and no evaluation has been run.** This lists
what must be pre-registered before Batch 3, exactly as the harness (scripts/fund_stats.py, scripts/fund-search.py)
currently implements it, so the owner can accept or change each item BEFORE the ledger declaration seals it.
Parent: docs/plans/2026-09-28-methodology-improvement-plan.md §1.4, §3, §6. Any change after sealing is a ledger
event, and thresholds may only be tightened.

## A. Choices to pre-register (the 12)

1. **Fold geometry.** `TEST_FOLD_DAYS=365`, `MIN_TRAIN_DAYS=730`, `MIN_TEST_FOLDS=2`, `MIN_TRAIN_TRADES=30`.
   Folds end exactly at the development cutoff (2024-03-01) and step back in 365-day folds while >= 730 days of
   training precede the fold. Resulting fold counts (reviewer-computed, printed by `plan --dry-run` from the data):
   metals 1m 9 folds; metals 5m/15m 17 (and 30m 17 until the 30m cells were removed, owner 2026-10-01); indices (all
   timeframes) 4. The plan output and the report carry these per cell. Not changed in this round. Since 2026-10-01 each
   cell's history START is a declared, pinned field (`docs/architecture/fund-search-cells.json` `dev_start`, null = from
   data); every cell currently keeps its original data start, so the counts above are unchanged.
2. **The statistic.** Primary metric = net expectancy per trade in R after REAL costs. Lower bound =
   `min(iid one-sided Student-t bound, and CR1 cluster-robust bounds by UTC entry date, by 30-day window, by
   calendar quarter, by half-year)`, all at one-sided confidence `1 - 0.10/N`. CR1: `se = sqrt(G/(G-1) * sum_g S_g^2) / n`,
   `S_g = sum_{i in g}(r_i - mean)`, `df = G-1`, `G` = number of blocks; fewer than 2 blocks = no bound (fail).
   Computed on POOLED TEST-fold trades only. N = (1 + non-baseline values + 1 combined) per method x cells
   (ICT 29/cell after the 2026-09-30 removal of B-EXIT `no_floor`, Wyckoff 16/cell). Reason for the block bounds: with dependent trades the iid bound had a false
   positive rate 10-90x nominal in the reviewer's simulations; the quarter and half-year bounds were added after
   AR(1) 30-day and 180-day persistence scenarios still passed the first three (owner default: tighten).
   **DISCLOSED PRICE (power).** Measured by the harness author on 20 seeds of iid +0.30R at n=600: the five-way min
   passed 20/20 over 6 development years, 17/20 over 4, 9/20 over 2 (the reviewer's figures for a 90-day bound:
   0.99 -> 0.91; persistent-regime edges lose more). A cell with few quarters/half-years (e.g. indices, 4 folds)
   is structurally harder to pass. Not loosened.
3. **Selection rule.** One factor at a time against the baseline, on the TRAINING window only; a value is eligible
   with >= 30 training trades and is chosen only if its training expectancy STRICTLY beats the baseline's (ties keep
   the baseline); joint-group items are one factor (cartesian product); the combined candidate merges the winners.
4. **Purge / embargo.** Trade times are bar OPEN labels, so a training trade must have its exit label strictly
   before `test_start - one bar of the cell's timeframe` (purge). DECIDED 2026-09-30 (owner): implemented as an
   additional EMBARGO -- a training trade must also have exit label strictly before `test_start - 2 x H bars` of the
   cell's timeframe (H = the engine's own `bt.P[tf]["H"]`; 2H is the largest finite time stop of the declared V
   grid; a "none" time stop cannot be embargoed and is covered only by this same 2H). Stricter only; computed in
   `fund-search.py`, passed to `fund_stats.train_window` as a timedelta, recorded in the plan/declaration config.
5. **Perturbation.** For every item and each direction, in every fold, move the value the fold chose one step on the
   item's axis (numbers sorted ascending, other values in listed order; an edge has no neighbour that side); pool the
   test trades; the robust lower bound at the same confidence must stay > 0 for every (item, direction).
6. **Frequency and stability.** Frequency: the longest gap between consecutive trade ENTRY dates on the pooled
   account, fold edges included, <= 30 days in >= 90% of folds (arithmetic per cell in the report). Stability:
   positive net expectancy on >= ceil(2m/3) of the m symbols with development data (a symbol with none counts as
   not positive, never dropped); no single trade above 25% of total net R (total <= 0 fails).
7. **Regime split (pre-registered definition).** ADX(14) (Wilder) of the last bar that opened strictly before the
   entry; split at the MEDIAN of the pooled TEST trades' ADX values (<= median low half, > median high half); BOTH
   halves must have positive mean net R; a trade with no ADX value (warm-up) fails the check.
8. **Verdict precedence and prop-pass details.** `insufficient` (any test fold < 30 trades, or < 2 folds) overrides
   everything; otherwise `pass` only if EVERY check is ok, else `fail`. Timeout trades cut off by the end of the
   PIT-truncated series are excluded (outcome unknown). prop_pass_probability >= 0.70 for EVERY fund in
   `prop-search.FUNDS` at the 120-day horizon, sized with `live_parity_sizing=True`; `unavailable` (with reason) is
   recorded as its own status and blocks a PASS like a numeric fail; when `low_confidence` is set the MINIMUM of
   the bootstrap spread must also be >= 0.70.
9. **Cost model.** Real FTMO costs, profile `ftmo_demo_2026_09_relspread` (AMENDED 2026-10-02 by item 13: the recorded
   spread is scaled with the entry price; the absolute profile `ftmo_demo_2026_09` is no longer the fund profile and is
   kept only as the reported sensitivity), `spread_stat="median"`, swap from the export;
   flat before the daily server rollover (FIXED on; checked after every simulation). **FTMO commission is UNKNOWN**
   (`no_deals`): taken from the cost data only (0.0 with its status), so net R is NOT net of commission.
   Ruin handling: the harness sets `RUIN_FRAC=0.0` on its own engine instance (R does not depend on equity) and
   fails loud if any trade would have gone to `post_ruin`. **min_rr semantics: see item O1 (DECIDED).**
10. **Code SHAs and grid hashes.** The declaration pins the last-commit SHA and dirty flag of `fund_stats.py`,
    `fund-search.py`, `prop-search.py`, `backtest-methods.py`, `real_costs.py`, `performance.py`, `mt5_time.py`,
    `ict-scan.py`, `wyckoff_rules.py`, `live_rules.py`, the sha256 of both grid files, STABILITY_FRACTION, `live_parity_sizing`,
    `spread_stat`, FUNDS/horizon and the verdict-precedence rule. `run` REFUSES (non-zero exit) when the current fingerprint or
    evaluation settings differ from the declaration; `--allow-drift` proceeds but stamps every record
    `drifted=true` and the report header says so. The report also flags records sealed under a different
    code_version or a dirty tree.
11. **What a PASS certifies, and the deployment rule.** A PASS certifies a SELECTION PROCEDURE (choose on each
    training fold, score on the next test fold), not a configuration. The report shows how often each item's chosen
    value changed between folds. PROPOSED, NOT DECIDED: the deployment rule is "the values chosen in the FINAL
    fold".

12. **Planned-risk admission (zero-risk refusal; coordinator decision 2026-10-01, owner to ack before `declare`).** A
    candidate trade is REFUSED at admission, before any pricing, when its planned risk is not a valid stop distance:
    `backtest-methods.planned_risk_refusal(side, entry, stop, tick)` returns a cause when (a) entry or stop is not a finite
    number or entry is not positive (`invalid_price`), (b) entry == stop (`zero`), (c) the stop is on the profit side of the
    entry (`wrong_side`, risk < 0), or (d) 0 < risk < one tick (`sub_tick`; tick = the symbol's `tick_size` in its real-cost
    spec, compared with 1e-6 relative slack; with no cost profile only risk > 0 is asked). Why: such a trade has no
    position size (live refuses it: `risk_model.size` raises on a zero stop distance), `real_costs.cost_r` would raise
    `CostRefused: stop distance is zero` and abort the run, and the flat-fee path would divide by zero. Root cause: the
    ICT B-EX=`fill` entry model (far edge of the FVG) puts the entry ON the stop when the first candle of the gap is a flat
    (H == L) bar at the sweep extreme (docs/audits/2026-10-01-zero-risk.md). The refused candidates are counted: simulate()
    records `SIM_LAST["refused"]["zero_risk"]` (by cause in `SIM_LAST["zero_risk_by_cause"]`) and the harness records, per
    value set and per test fold, `refused_zero_risk` next to `candidates` / `refused_min_rr` in the record's `admission`
    block and in the report line "planned-risk admission". A refused candidate is never entered, never occupies the
    one-position-per-symbol slot and never produces an R. Every trade with a valid stop distance is unchanged: this is
    DEMONSTRATED FOR THE ZERO BRANCH (trade-list sha256 BEFORE == AFTER on slices without a zero-risk candidate; the
    difference on an affected slice is exactly the refused candidates). The `sub_tick` branch is a defensive guard
    that is not idle but is confined: on the data counted it refused candidates only in `B-EX=fill` + `B-BUF` value sets (an
    off-grid ATR-buffered stop within a fraction of a tick of the far-edge entry: XAGUSD 1m up to 395 in one set, XAUUSD 1m 10,
    XAUUSD 5m 4, none elsewhere; per-year counts in the audit) and none in the baseline value set; the other strict sub-tick
    cases found were one tick plus floating-point noise and are admitted by the 1e-6 slack. The equivalence evidence covers the
    ZERO branch only, and a `sub_tick` refusal in the BASELINE value set would be a method change (none seen).
    The rule changes no threshold, grid, cell, min_rr or statistic and does not change `plan_hash`; it changes pinned files
    `backtest-methods.py`, `real_costs.py`, `fund-search.py`.

13. **Engine realism: the harness's simulate-time OPTS, a relative spread, gap-aware fills (coordinator decision 2026-10-02, from the
    red-team review; owner to ack before `declare`).** Three corrections made BEFORE the declaration, none of which looks at a
    result (no R, expectancy or win rate was computed for any of them; counts and equivalence hashes only).
    - **(a) C1, a harness bug: `simulate()` ran under the v1 OPTS.** `BtEngine.trades_for` handed the candidate overlay to
      `bt.scan(opts=...)`, but `bt.simulate()` reads the MODULE-GLOBAL `OPTS`, so the harness applied the v1 min_rr admission (the
      EXIT-hour spread: the look-ahead of plan §37) although item O1 says it is off. `checked_simulate` now runs every simulate
      (`trades_for` and `prop_pass`) under `simulate_context` = `dict(bt._OPTS_BASE, **fixed_opts())`, restored exception-safe, and
      the harness' admission rows use the same entry-hour cost. The simulate-time OPTS reads were AUDITED over `simulate` and every
      function it calls (`planned_risk_refusal`, `_risk_scale`, `_account_stop`, `_venue_for_symbol`; `real_costs`,
      `risk_model`, `account_profile`, `event_risk`, `sessions` read no OPTS): exactly `min_rr` (not a V item), `fx_admission_entry_cost`
      (fixed ON) and the 2R-FLOOR TOKEN of `fx_b_exit` (the grid declares only `...|floor` values). `mgmt` is NOT read by
      `simulate()`: it is read by `walk()` at scan time. Because `prop_pass` pools trades of folds that chose different V values it
      uses the fixed set only; a candidate overlay that sets a simulate-time key (or an `fx_b_exit` without the `floor` token) is
      REFUSED, and `scripts/tests/test_simulate_time_opts.py` re-derives the read set from the source and fails if a new
      simulate-time OPTS key appears. Not a threshold, grid, cell, min_rr or statistic change.
    - **(b) C2, relative spread.** The recorded FTMO spreads are ABSOLUTE price units from 2022-07..2026-09. Charged unchanged
      against earlier prices they misstate `spread_R` by the price-level ratio and drift across folds. Measured (the symbol's
      `price_ref` over the yearly median daily close, development span; a price ratio, no R): XAUUSD 6.0 in 2004, 3.7 in 2007,
      about 1.5-2.1 in 2010-2019, 1.2-1.4 in 2020-2024; XAGUSD 2.9 in 2008, 1.2-1.9 later; USTEC 3.0 in 2017, 1.1-1.6 from 2021;
      US500 2.1 in 2017; XPDUSD 0.5-0.6 in 2020-2022 (palladium traded ABOVE its reference, so the absolute profile UNDERSTATED
      its spread there). The coordinator brief said 2-4x; the measured overstatement is 1.5-2x for most of the gold/silver
      folds and larger only before 2010. Profile `ftmo_demo_2026_09_relspread`
      (`scripts/real_costs.py`) scales both legs, median and p90 alike, by `entry / price_ref(symbol)`, where `price_ref` is the
      median CLOSE of the symbol's committed M15 bars (`data/history/ftmo`) over EXACTLY the spreads' recording window (spec
      `recorded_spread_m15.first_bar_server .. last_bar_server`, converted to UTC with the profile's server clock; 100,000 bars
      for XAUUSD, matching the spec's own `bars`). At `entry == price_ref` it equals the absolute profile. Swap is not rescaled (every trade is
      flat before the rollover). `ftmo_demo_2026_09` stays selectable and BYTE-IDENTICAL (cost_r and `profile_snapshot` sha256
      identical before/after on 180 priced trades) as the reported sensitivity. The plan core (`cost_profile`, `cost_profile_pin`)
      and the declaration's `evaluation_config` pin the profile, every cell symbol's `price_ref` and the sha256 of its
      provenance (window, bar count, closes hash); a changed history or spec is drift. `real_costs.mean_spread_r` returns the mean
      spread_R of a trade list (the per-fold cost report is a later step).
    - **(c) C3, gap-aware stop fills (new FIXED key `fx_gap_fill`, default False = v1 byte-identical, ON in every fund cell through
      `ADOPTED_F_KEYS`, never settable by a grid item, never set live).** v1 `walk()` fills a stop at exactly the stop price even when
      a bar OPENS beyond it. Sealed rules: a stop (the planned stop or the breakeven stop once moved) fills at the WORSE of the stop
      and the bar OPEN when the open is beyond the stop (long `min(stop, open)`, short `max(stop, open)`); an open exactly at the
      stop fills at the stop; targets and limit entries fill at their own price with NO price improvement; in a same-bar
      fill-and-stop case (ICT, COMBINED-BOOK) the stop leg obeys the same rule; the bar order is unchanged (stop before target inside
      one bar); `R_planned` and the min_rr admission use the PLANNED stop and are unchanged; the realised R is
      `(fill - entry) / planned risk` (below -1, or below 0 for a breakeven stop, on a gap) and such a trade's `outcome` is
      "loss". The key is read at scan time (`walk`), not by `simulate()`.
    - **Evidence (counts and hashes only).** C1: `scripts/tests/test_simulate_time_opts.py` (11 tests) goes through `BtEngine.trades_for` and `prop_pass` with a stubbed `bt.scan` and the REAL `simulate`: the harness-level O1 test FAILS on the pre-fix code (the trade is refused, the admission row carries the exit-hour cost 0.80 R instead of the entry-hour 0.75 R) and passes now. C2: `cost_r` and `profile_snapshot` of `ftmo_demo_2026_09` have identical sha256 before/after over 180 priced trades; 10 new tests in `test_real_costs.py` (price_ref = the median close over the window, reproducible; identity at `entry == price_ref`; a price level 2.5x lower gives a 2.5x smaller spread_R). C3: trade-list sha256, code of the base commit 5a6a355 (`git archive`) vs the new code with the key explicitly OFF, ICT and WYCKOFF-BOOK under the fund overlay on 8 real slices (XAUUSD 1m/5m/15m, XAGUSD 1m, US500 5m/1m, DE40 5m; 1,913 trades): IDENTICAL (296 trades `19ef8b88...`, 1,617 trades `9e051b9c...`), and `test_speed_equivalence` (42 tests, differential against the pre-speed reference commit 0ab0986) OK. With the key ON, 36 of the 1,913 trades differ (2 of 296, 34 of 1,617: 0.2 % to 2.1 % per slice), every one of them a trade whose exit bar OPENED beyond the stop in force (36 of 36, checked against the bar series), and only the fields `R`, `outcome`, `mae` differ (entries, times, stops, targets, `R_planned` identical); `scan_many` == `scan` byte-for-byte with the key ON and OFF (ICT and WYCKOFF-BOOK on 100,000 XAUUSD 5m and 120,000 US500 1m bars). Tests: `scripts/tests/test_gap_fill.py` (20 hand-built-bar cases: gap through a stop long/short, gap exactly at the stop, no gap, stop and target in one bar, gap through a target, breakeven stop gap, same-bar fill-and-stop, no `O_` refuses). The leakage probe and the flat-bar census are in `docs/audits/2026-10-02-engine-realism-census.md`.
    The three changes move pinned files: `scripts/backtest-methods.py`, `scripts/real_costs.py`, `scripts/fund-search.py`,
    `scripts/scan_many.py` (they are in or beside `FINGERPRINT_FILES`), and change `plan_hash` (new value in
    `docs/experiments/fund-search/plan.json`): `declare` must run AFTER them.

## B. OPEN owner questions

- **O1 (min_rr look-ahead).** DECIDED 2026-09-30 (owner): implemented as the engine key
  `fx_admission_entry_cost` (default False = v1 byte-identical; ON in every fund cell, in `ADOPTED_F_KEYS`, never
  settable by a grid item). With it on, `simulate()`'s min_rr admission subtracts only the cost knowable at the
  entry decision: the entry-hour half-spread plus an exit-leg half-spread estimated at the SAME entry hour, no swap
  (nights held depend on the exit), commission as recorded (0 / UNKNOWN). The reported net R still uses the real
  entry+exit costs; only the admission test changes.
  ENFORCED IN THE HARNESS since 2026-10-02 (item 13a): before that, `trades_for` ran `simulate()` under the v1 module OPTS, so the
  exit-hour admission was still applied although the key was in the overlay.
- **O2 (embargo).** DECIDED 2026-09-30 (owner): implemented as `2 x H` bars of the cell's timeframe before each
  test fold, on top of the one-bar purge (see A4).
- **O3 (fold size).** Keep 365/730 (fold counts differ 4 to 17 by cell) or re-declare? Not changed here.
- **O4 (deployment rule).** Accept "values chosen in the final fold", or another rule?
- **O5 (allow-list).** The harness refuses a grid item whose OPTS key is neither an `fx_` key nor `mgmt`
  (`ALLOWED_EXISTING_OPTS`); extend the list only by a reviewed edit when the real grids merge.
- **O6 (commission).** Provide the real FTMO commission (or accept the disclosed limitation).
- **O7 (regime split threshold).** Median of pooled TEST trades as defined in A7, or a fixed ADX level?
- **O8 (ICT rollover gap).** The engine asks about the daily rollover only after each WALKED bar, never for the
  entry bar. Wyckoff enters at the previous bar's label (legitimate). An ICT limit fill INSIDE the last bar of a
  server day can therefore be held past midnight although flat-before-rollover is on. The harness compares on the
  walked-bar basis (entry label + one bar -> exit label, so it neither false-trips on legitimate last-bar entries
  nor misses trades held across a walked bar) and RECORDS, per V value set and per fold, how many entries sit on
  the last bar of a server day (report line "Entries on the last bar of a server day"); it does not raise on
  them. OPTION for the owner: an engine fix behind an `fx_` key (default v1) that also flattens a fill inside the
  last bar, adopted before Batch 3.
- **O9 (merge-time guards, implemented).** `run` refuses any grid item with `implemented:false` (plan/dry-run
  list it as "declared, not runnable, counted in N"), refuses a grid whose time-stop item declares "none" unless
  flat_before_rollover is fixed on (asserted for every candidate in `checked_simulate`), and refuses any V value
  the grid did not declare, before scanning.
