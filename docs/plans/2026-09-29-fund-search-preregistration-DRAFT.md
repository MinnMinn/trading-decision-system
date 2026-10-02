# Fund-search pre-registration -- DRAFT, UNSEALED (2026-09-29)

**Status: DRAFT. Nothing here is sealed, `declare` has not been run, and no evaluation has been run.** This lists
what must be pre-registered before Batch 3, exactly as the harness (scripts/fund_stats.py, scripts/fund-search.py)
currently implements it, so the owner can accept or change each item BEFORE the ledger declaration seals it.
Parent: docs/plans/2026-09-28-methodology-improvement-plan.md §1.4, §3, §6. Any change after sealing is a ledger
event, and thresholds may only be tightened.

**Revised 2026-10-02 (red-team review, owner decisions of the same day).** Section 0 and section C are new; items A2,
A5, A7, A8, A9, A10, A11 and the open items in B were rewritten and are marked "(REPLACED 2026-10-02)". Where this
file still contains an older number or sentence that conflicts with section 0 or C, section 0 / C wins.

## 0. Red-team corrections and owner decisions of 2026-10-02 (binding once sealed)

The same decisions are recorded in docs/plans/2026-09-30-owner-decisions.md ('Owner decisions 2026-10-02 (red-team
review)'). Definitions in this section and in section C are sealed AT `declare` even where the code that computes them
follows later: the code is then pinned by the declaration like every other file, and a definition the code does not
implement is reported as "not implemented" in the report, never silently dropped.

### 0.1 (C5) The development window is NOT a pristine holdout, and what a PASS means

- **Registry status.** `docs/architecture/research-ledger.json`: everything before the development cutoff
  (2024-03-01) is `development` (period `cfd-development-pre-2024-03`; every choice below was made after reading
  outcomes on it). Data from 2024-03-01 on is `oos_exposed`: [2024-03-01, 2025-03-01) is the period
  `cfd-prop-search-2024-03-2025-03` (exposed by candidate selection: the 180 prop-search records), and every later
  date is exposed under ADR 0008 (docs/adr/0008-2026-09-26-criteria-based-selection-replaces-top-n.md) and plan §1.1
  ("No historical window is pristine"). The fund search reads nothing at or after 2024-03-01. Any earlier wording that
  called the data after 2024-03-01, or the development window itself, a pristine or untouched holdout is WITHDRAWN.
- **What a PASS is.** A development-window PASS is a NOMINATION for a separately pre-registered forward demo. It is NOT
  out-of-sample validation and it is not evidence of a live edge. The only pristine evidence available is a forward demo
  from the date its own pre-registration is sealed (plan §1.1, §6 item 1).
- **Every prior outcome read on this window (disclosed; none is folded into the family of six).** Outcome = any figure
  of R, win rate, sumR or expectancy for a candidate on development data. `PRIOR_COUNTS` in `scripts/fund-search.py`
  carries the counts (prop_search_records 180, diagnosis_slices 30, fidelity_funnel_rows_ict 18,
  fidelity_funnel_rows_wyckoff 11, real_cost_reprice_runs 1, min_rr_values_tried 3) and the plan echoes them.

  | # | Read (path) | What was read |
  |---|---|---|
  | 1 | `docs/audits/2026-09-28-method-diagnosis.md` | 30 slices, XAUUSD / US500 / DE40, funnel and outcomes, all history < 2024-03-01. Pooled: ICT gross +0.21 R, net -0.02 R, after the floor 120 trades net +0.06 R, 38 % wins; Wyckoff n = 686, gross -0.036 R, 40.2 % wins, median planned R 1.89. |
  | 2 | `docs/audits/2026-09-29-real-costs-reprice.md` (+ `.json`) | The ONE disclosed re-pricing of that baseline with the broker's own spread and swap (net R by slice). |
  | 3 | `docs/audits/2026-09-29-ict-fidelity-funnel.md` | 15m XAUUSD / US500 / DE40, < 2024-03-01: Trades, sumR, Win %, Taken, Mean net R for v1, b2a, b2b, b1p, braid, all-four (e.g. XAUUSD v1 139 / 13.27 / 34.5 % / 96 / -0.334; XAUUSD braid 1309 / 151.16 / 36.3 % / 744 / -0.213; US500 braid 163 / 30.30 / 36.8 % / 104 / -0.083; DE40 all-four 83 / 7.21 / 33.7 % / 59 / -0.319). 18 rows (9 re-run, 9 carried from docs/plans/2026-09-29-handoff-macbook.md). |
  | 4 | `docs/audits/2026-09-29-wyckoff-fidelity-funnel.md` | The same columns for v1, w2, w3, w5, all-four, w7 on the same three symbols (e.g. XAUUSD w2 679 / 19.49 / 48.9 % / 194 / -0.639; DE40 v1 61 / 22.62 / 37.7 % / 27 / +0.362; US500 all-four 119 / 43.94 / 52.9 % / 41 / +0.207). 11 rows. |
  | 5 | The F adoption (`docs/plans/2026-09-30-owner-decisions.md`, 'Adopted F set') | Taken AFTER reads 3 and 4 existed: five keys by the x1.5 trade-count rule, and `fx_braid_optional` (B-RAID, ~x9 trades), `fx_b1_pivot1` (B1), `fx_w2_st_below_sc` (W2), `fx_w7_htf_target` (W7) by explicit owner instruction beyond that rule. The evaluation baseline was therefore shaped with outcome tables available. |
  | 6 | `scripts/prop-search.py`, `docs/experiments/prop-search-2026-09-27/` (180 records, `ERRATUM-2026-09-28.md`) | Development metrics of all 180 candidates, and every trade of [2024-03-01, 2025-03-01) for candidate selection (period exposed). |
  | 7 | `scripts/stability-report.py`, `docs/architecture/pilot-selection.json`, `docs/architecture/ranking.json`, `docs/experiments/2026-09-24-improve-crypto-*.json` | Earlier stability, ranking, pilot-selection and improve-loop runs. They read OTHER windows (ledger periods `crypto-history-2023-2026`, `cfd-history-2026`) and are listed so the reader need not ask; two windows in pilot-selection.json carry their own "exposure" statement. |
  | 8 | `min_rr` history (`docs/architecture/analysis-params.json` `project_defined.ict.min_rr`, `_basis`) | 3.0 (owner, 2026-09-13; chosen on nine crypto instruments, 15m ICT, fee 0.05 %/side) -> 2.0 (2026-09-19; informed by `docs/audits/2026-09-19-knowledge-fidelity.md` section 8: with the -2 sigma target 9 of 20 reachable ICT trades cleared 3R and 16 of 20 cleared 2R, +0.95 R expectancy over the 20) -> 2.5 (owner, 2026-09-30, "R:R target when entering a trade must be at least 2.5R"; the `_basis` cites no performance figure, but the decision post-dates reads 1-4, so it is disclosed as possibly informed by them). |
  | 9 | `docs/audits/2026-10-01-trade-rates.md`, `...-cell-selection*.md`, `...-power-model*.md`, `...-zero-risk.md`, `2026-09-30-fund-search-engine-smoke.md` | Trade COUNTS, a power model and structural checks; their own text states no performance figure decided the three-cell plan. Listed for completeness, not as outcome reads. |

  The development symbols and the 2024-03-01 cutoff were chosen before the search; the symbol universe, the cell list
  and the folds were chosen on counts and power, not on performance (docs/plans/2026-09-30-owner-decisions.md).

### 0.2 (family A) The multiple-testing family is the six candidate procedures

REPLACES the per-method N (ICT 87, Wyckoff 48), the confidence `1 - 0.10/N` and any per-grid-value Bonferroni. The
family is the 6 candidate procedures (1m-metals, 1m-indices, 5m-metals, each for ICT and Wyckoff), tested with Holm's
step-down at FWER 0.10 on each candidate's PRIMARY BOUND. The nesting already handles value selection (values are chosen
on training folds only and scored on the next test fold), so grid values do not enter the family. Every other check stays
conjunctive. Full definition: item A2.

### 0.3 The 5m-metals history start is decided by a rule stated BEFORE looking

`dev_start` of `5m-metals` (docs/architecture/fund-search-cells.json) is currently null (data start, 17 folds). It is set
by this rule, applied by a later step AFTER the engine fixes and BEFORE `declare`, and not adjustable afterwards:

1. Measure the number of ADMITTED trades per test fold in the early-fold years for both methods with the final engine
   (counts only: no R, no win rate, no performance figure is read for this decision).
2. Candidate starts, earliest first: the data start (17 folds), 2009-03-01 (13 folds, XAUUSD + XAGUSD only), 2015-01-07
   (7 folds, all four symbols, the first XPTUSD / XPDUSD bar).
3. Take the EARLIEST candidate for which P(every test fold has >= 30 trades) >= 0.80 for BOTH methods under the
   availability-aware model (table T3-avail of docs/audits/2026-10-01-cell-selection.md: a late symbol is absent before
   its first bar, so early folds hold only XAUUSD and XAGUSD), recomputed on the measured admitted-trade counts.
4. If none qualifies, use 2015-01-07.

A non-null `dev_start` changes `plan_hash` (the cells file is hashed into it) and must re-run
`scripts/research/span_equivalence.py` for the cell (docs/plans/2026-09-30-owner-decisions.md, 2026-10-01 item 1).

## A. Choices to pre-register (the 12)

1. **Fold geometry.** `TEST_FOLD_DAYS=365`, `MIN_TRAIN_DAYS=730`, `MIN_TEST_FOLDS=2`, `MIN_TRAIN_TRADES=30`.
   Folds end exactly at the development cutoff (2024-03-01) and step back in 365-day folds while >= 730 days of
   training precede the fold. Resulting fold counts (reviewer-computed, printed by `plan --dry-run` from the data):
   metals 1m 9 folds; metals 5m/15m 17 (and 30m 17 until the 30m cells were removed, owner 2026-10-01); indices (all
   timeframes) 4. The plan output and the report carry these per cell. Not changed in this round. Since 2026-10-01 each
   cell's history START is a declared, pinned field (`docs/architecture/fund-search-cells.json` `dev_start`, null = from
   data); every cell currently keeps its original data start, so the counts above are unchanged.
2. **The statistic (REPLACED 2026-10-02, family A).** Primary metric = net expectancy per trade in R after REAL costs,
   computed on POOLED TEST-fold trades only. Per candidate there are five one-sided bounds at one common confidence
   level: the iid Student-t bound and the CR1 cluster-robust bounds by UTC entry date, by 30-day window, by calendar
   quarter, by half-year. CR1: `se = sqrt(G/(G-1) * sum_g S_g^2) / n`, `S_g = sum_{i in g}(r_i - mean)`, `df = G-1`,
   `G` = number of blocks; fewer than 2 blocks = no bound (fail). **PRIMARY BOUND = the MIN of the five bounds**; in
   p-value form (`t = mean / se`, one-sided p of H0 "mean <= 0" on that bound's df) the candidate's p = the MAX of the five
   p-values, so a candidate is significant at level `a` only if all five bounds are above 0 at `1 - a`.
   **FAMILY = the 6 candidate procedures** (3 cells x 2 methods). **Holm step-down at FWER 0.10** over the six
   candidate p-values: sort ascending `p(1) <= ... <= p(6)`; reject `H(k)` while `p(k) <= 0.10 / (6 - k + 1)`; stop at the
   first failure. A candidate's statistical check passes iff Holm rejects it. The **per-candidate floor confidence is
   `1 - 0.10/6 = 0.98333`** (Holm's strictest step): a candidate whose primary bound is above 0 at 0.98333 passes
   whatever the other five do, and Holm only REFINES that at report time (a candidate ranked k-th by p is judged at
   `0.10/(6-k+1)`, up to 0.10 for the last). 0.98333 is also the confidence of the perturbation-neighbour bounds
   (item A5), of the upper confidence bound and the minimum detectable edge (section C) and of the prop-pass shift
   (item A8). This REPLACES the per-method N (ICT 87 / Wyckoff 48, confidences 0.998851 / 0.997917) and any per-grid-value
   Bonferroni: the nested walk-forward already handles value selection (values chosen on the training window only, scored
   on the next test fold), so grid values are not hypotheses of the family; the number of grid values stays disclosed
   (`plan --dry-run`, `N per cell`). EVERY OTHER CHECK STAYS CONJUNCTIVE (stability, frequency, regime, perturbation,
   stress, prop-pass, sufficiency): a PASS needs all of them, and none is traded against another. Code: `fund_stats.py`
   and the verdict/report part of `fund-search.py` follow in a later step (the harness at this commit still prints the
   per-method N); the report must say which of the two it implements. Reason for the block bounds: with dependent trades the iid bound had a false
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
5. **Perturbation (REPLACED 2026-10-02).** ORDINAL components only, ONE at a time. For each ordinal component and each
   direction, in every fold, move the value the fold chose one step along the order below (an edge has no neighbour on that
   side; a fold that chose the value at that edge contributes nothing in that direction); pool the test trades of the
   moved value sets; the neighbour passes iff its pooled mean net R > 0 AND its robust lower bound (the primary bound,
   item A2) is > 0 at `1 - 0.10/6` (0.98333). Every (component, direction) neighbour must pass for the check to pass.
   The ordinal components and their orders:
   - ICT: B-BUF stop buffer `0 < 0.1 ATR < 0.25 ATR`; B-EX entry model `iofed < ce < fill`; B-EXIT target
     `-2.0 < -2.25 < -2.5` and, separately, time stop `H < 1.5H < 2H < none`; B-LB lookback `8 < 12 < 16` and, separately,
     expiry `K < 2K`.
   - Wyckoff: W6 structure window `300 < 600`; W-TW test window `8 < 12 < 20` and, separately, Phase-B swings `2 < 3`;
     W4a only between the explicit counts 3 and 4 (the v1-typed baseline is not an ordinal step: a fold that chose the
     baseline is NOT perturbed on W4a).
   Categorical components (every other grid item: B-PD, B-POOL, B6, B3, B4, B-MGMT, B7, W-STOP, W-SPT, W-TOUCH, W-MGMT; B4 and W4b
   are declared but not runnable) are flipped in the report ("value A -> value B: pooled mean net R, bound") and NOT gated.
6. **Frequency and stability.** Frequency: the longest gap between consecutive trade ENTRY dates on the pooled
   account, fold edges included, <= 30 days in >= 90% of folds (arithmetic per cell in the report). Stability:
   positive net expectancy on >= ceil(2m/3) of the m symbols with development data (a symbol with none counts as
   not positive, never dropped); no single trade above 25% of total net R (total <= 0 fails).
7. **Regime split (REPLACED 2026-10-02, closes O7).** Regime = the D1 ADX(14) (Wilder) of the last COMPLETED D1 bar
   at or before the entry time (a D1 bar is completed once its close time is <= the entry time; the entry day's own
   forming bar is never read); split at the MEDIAN of the pooled TEST trades' D1 ADX values (<= median low half, > median
   high half); BOTH halves must have positive mean net R; a trade with no D1 ADX value (warm-up) fails the check. The
   earlier definition (ADX(14) of the cell's own timeframe) is superseded; the code follows (`REGIME_SPLIT_DEFINITION`
   in `fund_stats.py` is pinned in `evaluation_config.regime_split`, so a declaration made before the code follows
   would show drift).
8. **Verdict precedence and prop-pass details.** `insufficient` (any test fold < 30 trades, or < 2 folds) overrides
   everything; otherwise `pass` only if EVERY check is ok, else `fail`. Timeout trades cut off by the end of the
   PIT-truncated series are excluded (outcome unknown). prop_pass_probability >= 0.70 for EVERY fund in
   `prop-search.FUNDS` at the 120-day horizon, sized with `live_parity_sizing=True`; `unavailable` (with reason) is
   recorded as its own status and blocks a PASS like a numeric fail; when `low_confidence` is set the MINIMUM of
   the bootstrap spread must also be >= 0.70. **Added 2026-10-02 (two more conjunctive conditions of a PASS):**
   (a) **stress gate:** the pooled mean net R must stay > 0 under the p90 spread (price-scaled) on BOTH legs plus the
   0.003 % commission margin (item O6) applied to the SAME admitted trades (no trade is added or removed by the stress);
   (b) **shifted prop pass:** prop_pass_probability must also be >= 0.70 for every fund with every trade's R shifted DOWN
   by `(pooled mean - primary lower bound at 0.98333)`, i.e. with the edge cut to what the bound can defend. The
   admitted trade list, the sizing and the 120-day horizon are unchanged by the shift.
9. **Cost model.** Real FTMO costs, profile `ftmo_demo_2026_09`, `spread_stat="median"`, swap from the export;
   flat before the daily server rollover (FIXED on; checked after every simulation; an entry-bar fill on the last bar
   of a server day is flattened at that bar's close, see O8). **FTMO commission is UNKNOWN**
   (`no_deals`): taken from the cost data only (0.0 with its status), so net R is NOT net of commission; the stress
   gate of item 8 applies a 0.003 % margin instead (O6).

   the bootstrap spread must also be >= 0.70.
9. **Cost model.** Real FTMO costs, profile `ftmo_demo_2026_09_relspread` (AMENDED 2026-10-02 by item 13: the recorded
   spread is scaled with the entry price; the absolute profile `ftmo_demo_2026_09` is no longer the fund profile and is
   kept only as the reported sensitivity), `spread_stat="median"`, swap from the export;
   flat before the daily server rollover (FIXED on; checked after every simulation). **FTMO commission is UNKNOWN**
   (`no_deals`): taken from the cost data only (0.0 with its status), so net R is NOT net of commission.
   Ruin handling: the harness sets `RUIN_FRAC=0.0` on its own engine instance (R does not depend on equity) and
   fails loud if any trade would have gone to `post_ruin`. **min_rr semantics: see item O1 (DECIDED).**
10. **Code SHAs, tree hashes and grid hashes (REPLACED 2026-10-02, red-team I5).** The declaration pins:
    - the last-commit SHA and dirty flag of every module in `FINGERPRINT_FILES` (`scripts/fund-search.py`): `fund_stats`,
      `fund-search`, `prop-search`, `backtest-methods`, `real_costs`, `performance`, `mt5_time`, `ict-scan`,
      `wyckoff_rules`, `live_rules`, `scan_many`, `structures`, plus `history_store`, `normalized`, `pit`, `quality`,
      `research_validity`, `account_profile`, `trading_env`, `instruments`, `event_risk`, `isolated_pool`, `experiment`,
      and the other modules on the import path (`sessions`, `methods`, `snapshot`, `trader_constraints`, `providers`,
      `risk_model`, `trading_system`, `scan_cache`, `research_ledger`, `repo_paths`, `automation`, `stability-report`);
    - the git TREE hashes (`git rev-parse HEAD:<path>`) of `scripts/`, `data/history/costs/ftmo` (the symbolspec files)
      and `data/history/ftmo` (the committed candles), and of `docs/architecture/` (analysis-params.json,
      account-profiles.json, the symbol map, the grids and every other reader's input) WITHOUT `research-ledger.json`
      (that file holds the declaration itself and every later ledger event, so a hash that included it could never
      equal itself after `declare`; it is pinned as a sha256 over the blob listing of the directory minus that one
      file), plus the repo HEAD sha;
    - the sha256 of both grid files and of the cells file, STABILITY_FRACTION, `live_parity_sizing`, `spread_stat`,
      FUNDS/horizon, `min_rr`, the regime-split definition and the verdict-precedence rule (`evaluation_config`);
    - the Python version and platform (informational).
    `run` and `scan` REFUSE (non-zero exit) when a fingerprint, a tree hash or an evaluation setting differs from the
    declaration; `--allow-drift` proceeds but stamps every record `drifted=true` and the report header says so. A different
    Python or platform is a NOTE printed to stderr, never a refusal (CI runs Python 3.12 on Linux, the owner's machine
    3.14 on macOS; the stamp must not make a shared cache or a rerun impossible; the NOTE names both versions). `declare`, `run` and `scan` also REFUSE when any tracked file is modified or any untracked file exists
    under `scripts/`, `docs/architecture/` or `data/history/` (the scoped check ignores `config/`, `.claude/` and every
    other path: a dirty `config/env.example` or an untracked `.claude/worktrees/` does not block); `--allow-dirty` exists
    for tests and dry runs only, prints a WARNING, and is never silent (declare: `allow_dirty` in the declaration; run:
    every record stamped `drifted=true`; scan: the dirty list is part of the cache stamp). The scan-cache stamp carries the
    same repo HEAD, tree hashes and fingerprint, so a cache made from other code, config or data is refused. The tree
    hash needs only git objects, so it is also valid in a shallow clone (tested); the per-file last-commit SHA needs
    history, which is why `.github/workflows/fund-search.yml` checks out with `fetch-depth: 0`. The report also flags
    records sealed under a different code_version or a dirty tree.
11. **What a PASS certifies, and the deployment rule.** A PASS certifies a SELECTION PROCEDURE (choose on each
    training fold, score on the next test fold), not a configuration. The report shows how often each item's chosen
    value changed between folds. **Deployment rule (REPLACED 2026-10-02, closes O4; red-team I6).** The proposal "the
    values chosen in the FINAL fold" is WITHDRAWN. The SAME selection rule (item 3) is re-run once on the TRAINING data
    through 2024-03-01 (the whole development span, one training window) and yields one configuration per passing
    candidate. If several candidates pass, the one with the highest primary bound at the common confidence level
    (`1 - 0.10/6`) is listed first; EVERY pass goes to a separately pre-registered forward demo. PLACEHOLDER (not this
    document): deployed configuration, news filter ON, measured commission, its own pre-registration stating the demo
    length and the trade target, sealed before the first demo trade. The deployable spec differs from the searched spec
    in these ways, and the report lists them next to every PASS: (i) the nine adopted F keys are ON in the search
    (`ADOPTED_F_KEYS`) while live stays v1 until the owner approves v2 (plan §1.6); (ii) O1, the engine key
    `fx_admission_entry_cost`, changes the min_rr admission test; (iii) gap-fill and (iv) relative spread, the
    engine-realism changes of the parallel step (their definitions live with that change, not here); (v) the
    zero-risk refusal of item 12; (vi) NO news filter in the search (the CLAUDE.md §24 blackout is not applied in
    the search; the deployed configuration has it ON). A PASS is evidence about the SEARCHED specification; the forward demo must run the deployed
    one.

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
- **O3 (fold size). DECIDED 2026-10-02.** Keep `TEST_FOLD_DAYS=365` / `MIN_TRAIN_DAYS=730` (fold counts 9 / 4 / 17 by
  cell; the 5m-metals start is subject to the rule in section 0.3).
- **O4 (deployment rule). DECIDED 2026-10-02:** per item 11 (the same selection rule re-run on the training data through
  2024-03-01; every pass to a separately pre-registered forward demo).
- **O5 (allow-list). DECIDED 2026-10-02:** the allow-list stays. The harness refuses a grid item whose OPTS key is
  neither an `fx_` key nor `mgmt` (`ALLOWED_EXISTING_OPTS`); extend it only by a reviewed edit.
- **O6 (commission). DECIDED 2026-10-02:** the FTMO commission is UNKNOWN; the search uses a stress margin of 0.003 % of
  notional per round turn (item 8a). It is a STRESS MARGIN, NOT an estimate of FTMO's commission. The owner may
  measure the actual commission with a demo round trip later; the report restates whichever figure applies.
- **O7 (regime split). DECIDED 2026-10-02:** per item 7 (D1 ADX(14) of the last completed D1 bar at or before the entry,
  median split of the pooled TEST trades).
- **O8 (ICT rollover gap). CLOSED 2026-10-02: the earlier text was stale.** `backtest-methods.py` `walk()` already asks
  about the boundary between the ENTRY (fill) bar and the first walked bar when `flat_before_rollover` is on (commit
  2869c35, 'flat-before-rollover also asks about the boundary between the fill bar and the first walked bar'): such a
  trade is closed flat at the entry bar's own close (`outcome = rollover_flat`, zero bars walked), so a limit fill inside
  the last bar of a server day is NOT held past midnight. No engine key is needed and none is added. The harness still
  compares on the walked-bar basis (entry label + one bar -> exit label) and still RECORDS, per V value set and per
  fold, how many entries sit on the last bar of a server day (report line "Entries on the last bar of a server day");
  that count is now the number of entries the check acts on, not a leak. `ROLLOVER_EDGE_NOTE` in `fund-search.py` was
  corrected to say so. (The flattened trade's R at the entry bar's close is a result like any other; the engine-realism
  step may refine how that exit is priced, and the report then states it.)
- **O9 (merge-time guards, implemented).** `run` refuses any grid item with `implemented:false` (plan/dry-run
  list it as "declared, not runnable, counted in N"), refuses a grid whose time-stop item declares "none" unless
  flat_before_rollover is fixed on (asserted for every candidate in `checked_simulate`), and refuses any V value
  the grid did not declare, before scanning.

## C. Report obligations (DEFINITIONS sealed 2026-10-02; the code may follow)

Every report of a candidate, PASS or not, states the following with the numbers the declared code produces. A definition
the code does not yet compute is printed as "not implemented in this build", never omitted. None of these figures changes
a verdict unless item 2, 5, 6, 7 or 8 says so; they exist so the owner can read the result against its own noise.

1. **Minimum detectable edge (MDE)** = `(t_crit + t_{0.80,df}) x se`, where `se` and `df = G - 1` are those of the BINDING
   half-year CR1 bound (the half-year blocks have the fewest clusters; if a different one of the five bounds is the
   numerically smallest, its MDE is printed too), `t_crit` is the one-sided Student-t quantile at the floor confidence
   0.98333 and `t_{0.80,df}` the quantile at 0.80 on the same `df`. It is the true mean R per trade at which that bound
   would clear 0 with probability 0.80.
2. **Upper confidence bound on the edge**, one-sided at 0.98333: `mean + t_crit x se` on the same binding block structure.
   Together with the lower bound it brackets what the data can defend; a "PASS" with an upper bound close to the lower one
   is a different statement from one with a wide interval.
3. **Every failed check with its margin.** For each check that fails (including sufficiency and stability): the measured
   value, the threshold and the distance to it, in the check's own unit. A PASS lists the margin of every check too.
4. **Fold-by-fold mean net R and mean `spread_R`** (the spread cost in R) for the chosen values, with the fold's trade count.
5. **Stability of the chosen values across folds**: per grid item, the chosen value in each fold and how often it changed
   (item 11 states this; here it is also listed per component of the perturbation orders of item 5).
6. **Placebo benchmark (report-only; changes no verdict).** For every real TEST trade, one random entry on the SAME
   symbol and the SAME UTC hour-of-day within the SAME fold, side drawn 50/50, with the SAME stop distance and `R_planned`
   as the real trade, run through the same `walk`, costs and fills. The seed is pinned (recorded in the report). The report
   gives the placebo's mean net R and its bound next to the candidate's: a candidate that does not beat its placebo has
   shown timing-free exposure to the market, not an edge.
7. **Overlap statement.** `1m-metals` and `5m-metals` share XAUUSD and XAGUSD, so passes in both are NOT independent
   evidence; the report says so whenever both metals cells appear, with the shared symbols and the shared calendar span.
8. **Scope statement.** Zero passes say nothing about the cells removed from the plan (5m-indices, 15m-metals,
   15m-indices, 30m-metals, 30m-indices), about other timeframes, symbols or methods, or about the live configuration; a
   pass says something only about its own cell, method and the searched specification (item 11).
9. **Window statement.** The report restates section 0.1: development window, nomination not validation, and the list of
   prior reads (`prior_counts_disclosed`).
