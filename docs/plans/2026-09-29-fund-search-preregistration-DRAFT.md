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
9. **Cost model.** Real FTMO costs, profile `ftmo_demo_2026_09`, `spread_stat="median"`, swap from the export;
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

## B. OPEN owner questions

- **O1 (min_rr look-ahead).** DECIDED 2026-09-30 (owner): implemented as the engine key
  `fx_admission_entry_cost` (default False = v1 byte-identical; ON in every fund cell, in `ADOPTED_F_KEYS`, never
  settable by a grid item). With it on, `simulate()`'s min_rr admission subtracts only the cost knowable at the
  entry decision: the entry-hour half-spread plus an exit-leg half-spread estimated at the SAME entry hour, no swap
  (nights held depend on the exit), commission as recorded (0 / UNKNOWN). The reported net R still uses the real
  entry+exit costs; only the admission test changes.
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
