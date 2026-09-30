# Scenario-tree method (candidate) — design, before any code or evaluation

Date: 2026-09-30. Status: DESIGN ONLY. No code, no backtest, no performance number. Nothing here is approved; every
choice that is not sourced is labelled project-defined and is an owner question in section 10.
Path convention: `knowledge/...` = knowledge/ in this repo; `CLAUDE.md §N` = /CLAUDE.md sections; "not verified" = I did not
read the code or source needed to assert it.

## 0. The owner's question, answered first

The owner asked which is more effective: (a) incremental sliding-window recomputation, or (b) the trader's scenario behaviour.
They are not competing answers to one question.

- (a) is a speed optimisation. It must return byte-identical results (docs/audits/2026-09-30-engine-speed-profile.md §2 rule;
  CLAUDE.md §40 "Optimization must NOT ... silently change methodology behavior"). It can never make the method better, only cheaper.
- (b) is a new METHOD. It changes which trades exist. Whether it is better is unknown, and it is a hypothesis that costs
  multiple-testing budget (section 5). It is not a speed-up: the profile shows ~95 % of a scan is the per-bar structure analysis
  (`analyze()`), and a scenario layer on top of that analysis does not reduce it (profile §1, §5).

Recommendation: do (a)-style structure sharing first (much of it is already done, profile §2 (A)/(B)), then evaluate (b) as a
separate pre-registered family. Section 9 has the full comparison.

## 1. Problem statement and what differs from today

**Today.** `live_rules.read_at()` re-scans the trailing window at every bar (scripts/live_rules.py:67-90; window sizes in
scripts/automation.py:185-197: 1m 360 bars, 5m 576, 15m 576, 30m 480). `analyze()` returns pools, MSS, FVGs, dealing range
(scripts/ict-scan.py:207 onward). `setup_candidate()` then looks for ONE fixed chain: latest swept pool inside `lookback`
-> MSS after it -> FVG after the sweep -> limit entry (scripts/ict-scan.py:584-755). Everything not on that chain is dropped.
A pool that was closed through, for example, is only removed from `unswept` (ict-scan.py:513-515) and generates nothing.

**What the trader does (owner's description, paraphrased).** Read the whole chart, predict the paths price may take, mark
the touch points, and for each touch point hold different cases depending on how price reacts there.

**Honest overlap first.** The engine already classifies the reaction at a pool: `add()` walks bars after the pool and marks it
`swept` (wick beyond, close back) or `closed_through` (first body close beyond), citing knowledge/ict/core-a.md §3.2 R6
(ict-scan.py:302-310). structures.py exposes them as separately timestamped `sweep` / `closed_through` objects
(scripts/structures.py:195-202). So "sweep-and-reclaim vs acceptance-through" is NOT new information. What is genuinely
different:

1. Levels become first-class, persistent expectation objects (CLAUDE.md §17), each with branches, invalidations and a declared
   action, instead of a transient pool list rebuilt per window.
2. The acceptance branch gets a declared action (continue toward the next level, or explicit no-trade) instead of being dropped.
3. Levels may outlive the 576-bar window (a deliberate departure from live-parity; open question section 10 Q3).
4. Evaluation is scheduled by events (price reaches a registered level), not by every bar.
5. "No touch" and "no trade" are recorded outcomes (CLAUDE.md §41: NO TRADE / BLOCKED ENTRY are evaluation states).

Items 1 and 5 add explainability and audit. Items 2 and 3 are the only places the method can produce trades the chain cannot.
Item 4 is scheduling. This is why section 8 objection 6 stays OPEN until a novelty count (section 7, slice 1) is read.

## 2. The model: an expectation / scenario tree (anchored on CLAUDE.md §17)

### 2.1 Objects

- **LevelNode** (a touch point): a price level of interest created from an engine structure object that already has
  `available_at <= t`: ICT pools (BSL/SSL; `old` and `equal` types), the dealing-range edges, FVG edges/CE, and the MSS level
  (structures.py kinds `pool`, `fvg`, `dealing_range`, `mss`; A1/A1b objects only, plan §2). With `fx_b_pool=on` also PDH/PDL
  and session highs/lows (plan §3 B-POOL, `V_ICT` in ict-scan.py:98-109). No level from chart.js, narrative, or any model-owned
  level (plan §2 A2).
- **Branch**: an edge keyed by an observable REACTION at the node. Each branch carries `(trigger predicate, invalidation,
  declared action ∈ {ENTER, WAIT, NO_TRADE}, expected path)`.
- **Tree**: one tree per (symbol, timeframe, methodology). Methodologies never share a tree (CLAUDE.md §17: "Multiple methodologies
  must maintain independent expectations"). The first slice is ICT only.

### 2.2 Reaction classes (mechanical, bar-close predicates) and source

| Reaction at a BSL level `L` (mirror for SSL) | Predicate on CLOSED bars only | Source | Declared action (slice) |
|---|---|---|---|
| NO_TOUCH | no bar since registration has `high >= L` (touch definition is a V item, section 5) | none needed | WAIT; record |
| SWEEP_RECLAIM | a bar with `high > L` and `close <= L` before any body close beyond `L` | knowledge/ict/core-a.md §3.2 R7, §3.3 R11 (line 197, 203); engine: pool state `swept` | reversal branch: arm the existing MSS -> FVG -> limit chain (slice 1) |
| ACCEPT | first bar with `close > L` | knowledge/ict/core-a.md §3.2 R6 (line 196); engine: pool state `closed_through` | continuation branch toward the next opposing level (slice 2); before slice 2: NO_TRADE |
| AMBIGUOUS_PENDING | touch bar is the newest closed bar and a K-bar reclaim window (V item) has not elapsed | K-window not defined by source; project-defined | WAIT |

The next-objective rule for ACCEPT after ERL uses knowledge/ict/core-b.md §3.1 R3 ("IF price has just taken external range
liquidity, THEN the next objective is internal range liquidity ... IF price has reached IRL, THEN the next ERL",
core-b.md line 146). What the sources do NOT define, and this design therefore does not pretend to: an entry model for a
continuation trade after ACCEPT, a reclaim window longer than one bar, an "approach" distance, and an age at which a level
goes stale. All four are project-defined V items or owner questions.

### 2.3 Expectation states and immutability (CLAUDE.md §17)

| State | Meaning here |
|---|---|
| POTENTIAL | LevelNode registered (its structure is available at `t`) |
| EXPECTED | price is inside the trigger zone of the node (branches now live) |
| CONFIRMED | a reaction class has been assigned from closed bars |
| REACHED | the branch's expected-path target level traded. Post-entry comparison only: research and visualisation, never a decision input |
| INVALIDATED | the branch's invalidation condition occurred (a price fact, e.g. a body close beyond the level for a SWEEP_RECLAIM branch, core-a.md R25 as cited at ict-scan.py:305) |
| CANCELLED | withdrawn by rule, not by price: level aged out (V item), superseded, or day-flat/rollover rule (plan §6 item 7) |
| UNKNOWN | a required input is not FRESH (CLAUDE.md §20); never silently mapped to POTENTIAL |

The original expectation record (methodology, source structure ids, creation time, availableTime, expected path,
invalidation condition, provenance) is written once and never edited. State changes are APPENDED events with their own
availableTime. The actual path never rewrites the expectation (CLAUDE.md §17).

## 3. PIT and integrity rules

1. **Freeze at creation.** A LevelNode stores `level`, `source_structure_id`, `formed_at`, `available_at`. `available_at` is
   copied from the engine's structure object, computed through `normalized.available_time()` (scripts/structures.py:128-131),
   never re-derived. A node whose `available_at > t` does not exist at `t`. Confirmation delays already encoded there stay:
   pivot `i+PIV`, FVG `i+1`, equal pool `to+PIV` (structures.py module docstring).
2. **Known prerequisite defect to fix before slice 1 (read, not yet tested).** structures.py sets `PIV = ict_scan.PIV`
   (structures.py:121) and `ict_structures()` has no `opts` parameter (structures.py:155), while the adopted baseline runs
   `fx_b1_pivot1` (scripts/fund-search.py:72), which makes `analyze()` use a 1-bar pivot (ict-scan.py, `piv_bars`). So a tree built
   through `ict_structures()` on a baseline analysis would use a pivot delay of 3 bars where the analysis used 1: `available_at`
   is late (conservative), not early, so it is not a leak, but the tree would also not match the baseline levels unless the SAME
   `analysis` is passed in. Rule: the tree builder takes an already-computed analysis with the same opts and derives the delay from
   the same `piv_bars`. Whether other consumers of `ict_structures()` hit this: not verified.
3. **Classification from closed bars only.** The reaction class at decision time `t` reads bars with `available_at <= t`
   (`pit.series_as_of`, scripts/pit.py:139; the still-forming bar never enters, structures.py docstring "never the forming bar").
   A reaction is not classified before its closing bar; the trader's intrabar "at the moment of touch" is approximated by bar
   close, so the method reacts up to one bar later than a discretionary trader. This is a stated limitation.
4. **No future data, no outcome-dependent pruning.** A node or branch may be removed only by a rule whose inputs are all
   available at `t` (invalidation, age cap, day-flat). No rule may look at what the trade did afterwards. The set of tree
   shapes is fixed by section 2 before evaluation; nothing is added after data is seen without a ledger event (plan §3).
5. **Tree immutability.** `tree(t+1) = tree(t) + appended events for bar t+1`. Tree snapshots are hashed at each decision; the
   hash goes into the decision record and the experiment record (CLAUDE.md §42, §46).
6. **One definition, backtest and live.** `tree(t)` is defined as a PURE function of `candles[t-H .. t]` and the config snapshot,
   with a declared warm-up horizon `H`. No hidden mutable state, so live (which polls, latency-model.json) and backtest compute
   the same tree by construction. Memoising it across bars is an optimisation and must equal the pure function (section 4).
7. **Level selection cannot peek.** Which levels are registered is decided by `available_at <= t`, never by "which levels later
   get touched". A test truncates the series after `t`, recomputes, and requires an identical tree (section 7, PIT test).
8. **No restated rules.** The touch and reaction predicates call the same functions the engine uses (single source,
   ADR 0009, `rules/single-source-of-truth`); a tree that re-implements the sweep test would silently drift. Equivalence to the
   engine's `swept` / `closed_through` states is a test (section 4).

## 4. Event-driven evaluation and equivalence strategy

**Trigger.** A node is evaluated only on a bar where one of: the bar's range reaches the node's trigger zone (touch
definition, V item), or a node's invalidation/age condition can newly hold. Live and backtest both use closed bars (tick-level
"approach" needs a tick feed; not verified available, out of scope).

**Incremental part (identical to the full recompute, must be proven).**
- New structure registration: when bar `t` closes, only structures whose `available_at == t` are appended as nodes. The
  reference is the full `ict_structures()` on the window; the incremental set must equal the set of structures in the full result
  whose `available_at <= t`, minus those older than the horizon.
- Touch and reaction: at a trigger bar, the class must equal what a full per-bar evaluation of the same predicate gives.

**Intentional differences from the per-bar window recompute (disclosed, not defects):**
1. Persistence: nodes older than the 576-bar window survive; the chain forgets them (live_rules.py:56-64).
2. Window-global normalisers: `analyze()` uses per-window quantities (`lo/hi`, median range `med` for FVG size and
   displacement, ict-scan.py:219-222). A node's FVG-size gate was evaluated when it was created; a rolling recompute may differ
   at the edge. The tree uses the creation-time value (frozen) by rule 3.1.
3. Non-trigger bars produce no evaluation record. Sound only if no class other than NO_TOUCH can occur off-trigger.

**Equivalence tests (all on development-period slices < 2024-03-01 or synthetic; none reads performance).**
| # | Property | Method |
|---|---|---|
| E1 | trigger soundness: off-trigger bars can only be NO_TOUCH | property test: per-bar full classification vs trigger-gated, real windows + adversarial synthetic (ties, gaps, equal highs) |
| E2 | incremental registration == full recompute where they must agree (same levels, ids, `available_at`) | differential test against `ict_structures()`, modelled on scripts/tests/test_speed_equivalence.py (its BASE-vs-NEW approach, profile §3) |
| E3 | tree class == engine pool state (`swept` / `closed_through`) for every pool inside the window | differential test |
| E4 | pure-function equivalence: replaying appended events to `t` equals recomputing from `candles[t-H..t]` | property test at random `t` |
| E5 | PIT truncation invariance (rule 3.7) | truncate/extend property test |
| E6 | worker-count and order independence if the tree is computed inside `scan_many` chunks | as profile §3 (`workers=1` vs `workers=4`) |
| E7 | documented differences (1-3 above) are exactly the only differences vs the chain | difference-set test: every diff is explained by persistence, frozen value, or off-trigger skip |

## 5. Plugging into the harness

**As a NEW method, not a change to ICT.** fund-search maps grid method -> bt runner method in `METHODS` and grid files in
`GRID_FILES` (scripts/fund-search.py:65-66). Proposed: `scenario` -> `SCENARIO-ICT`, grid file
`docs/architecture/v-grid-scenario.json`. The bt method registry in scripts/backtest-methods.py was not read for this design:
"not verified"; the wiring point is confirmed in slice 5.

**Shared key contract** (docs/plans/2026-09-29-execution-plan.md "Shared contract"): one `fx_` key per item; baseline first =
default = v1; defaults live in `backtest-methods._OPTS_BASE`; every key in `stability-report._SCAN_RELEVANT_KEYS` and
`config_opts`; the live runner never sets a key; `validate_grid` refuses any non-`fx_` key outside the allow-list
(fund-search.py:124-140) and any FIXED key (fund-search.py:74). The nine adopted F keys stay ON in the baseline overlay
(ADOPTED_F_KEYS, fund-search.py:72), so the scenario family is measured on the same F baseline.

**Proposed pre-declared V grid (baseline first; all project-defined unless a source is named):**

| Item | Key | Values | Source |
|---|---|---|---|
| SC-TOUCH | `fx_sc_touch` | `cross` · `approach_0.25atr` · `approach_0.5atr` | touch/approach distance unsourced; ATR period 14 reused (ict-scan.py:119) |
| SC-RECLAIM | `fx_sc_reclaim_k` | `1` · `2` · `3` bars | R7 says body fails to close beyond, no K defined (core-a.md:197) |
| SC-BRANCH | `fx_sc_branch` | `reversal_only` · `reversal_continuation` | R7 / R6 / core-b R3; continuation entry model NOT in sources |
| SC-AGE | `fx_sc_age` | `window` · `2x_window` · `until_invalidated` | none; project-defined |

Baseline = the values equal to today's chain behaviour where possible (`cross`, `1`, `reversal_only`, `window`), so the baseline
cell must reproduce the chain (this is the slice-1 equivalence gate).

**N accounting.** Per the harness formula (fund_stats.py:328-330, plan §3): N per cell = 1 baseline + non-baseline values +
1 combined. Non-baseline: 2 + 2 + 1 + 2 = 7, so **N_new = 1 + 7 + 1 = 9 per cell**, times the cell count. The cell count is
recorded in research-ledger.json before any evaluation (plan §6 item 7, fund-search.py docstring); its final value is not fixed
today ("not verified"). N is counted by the same CountingSource on first evaluation.

**Multiple-testing burden and family choice.** Adding a method raises the total number of comparisons made on the same
development history. Two options:
- Pooled: N_total = N_ICT + N_Wyckoff + N_new per cell. It would tighten the bound of the already-declared families after the
  fact. The plan allows tightening only in one direction and only for a check, and the prior families are pre-registered
  (plan §6 item 2 "may never be loosened"; changing their N mid-flight is a re-registration).
- Separate family: own N_new, own `FAMILY_ALPHA` (fund_stats.py:43 = 0.10), own pre-registration, run after the existing search is
  sealed.

**Recommendation: separate family**, with three disclosures: (i) the union-bound family-wise error across the two families is up
to 0.20 (0.10 + 0.10), stated in the record; (ii) the development window is already exposed by the first family's candidate
selection once that run happens (plan §1.1, CLAUDE.md §44), so the scenario family's only pristine confirmation is forward demo;
(iii) the scenario family's pass rule is paired against the ICT baseline trade set on the same bars, so "different trades" is
not mistaken for "better trades" (the paired statistic must be pre-declared; its design is an open item, not specified here).
Option for the owner: split alpha 0.05/0.05 for the new family only (stricter, allowed).

**Pre-registration steps before any evaluation** (all outcome-free): (1) commit this design; (2) freeze the grid file and its
test that the code-side registry equals the file (pattern: scripts/tests/test_v_items_ict.py, per the "declaration" field of docs/architecture/v-grid-ict.json); (3) declare the cell
count in the ledger; (4) seal the pass rules (plan §4, §1.4) plus the paired rule; (5) record the novelty count and funnel counts
(section 7) as pre-evaluation evidence; (6) `fund-search declare` again, because engine file fingerprints change
(profile §8). Then one evaluation, reported with the full count, including zero passes.

**Versioning** (CLAUDE.md §47, plan §1.6): the method is a candidate Trading System v1.x behind its keys (default off). It adds a
required-analysis dependency and changes decision semantics, so it is version-significant (CLAUDE.md §59). Approval as v2 is an
owner decision after human review; rejected candidates stay traceable.

## 6. Latency

CLAUDE.md §40 requires measuring p50/p95/p99/max and isolating research from the hot path; it does NOT set a threshold in
seconds. docs/architecture/latency-model.json says so explicitly ("Not a performance budget ... §40 does not set thresholds").
So a budget for 1m/5m does not exist in the repo. I propose one and mark it an owner decision (Q4), not a fact:

- Proposed project targets (not measured, not sourced): tree update + reaction classification on a closed bar <= 50 ms p99;
  whole decision stage (`decision_start` -> `decision_end` in latency-model.json) <= 1 s p99, both for 1m and 5m. The polling
  transport, not compute, dominates end-to-end (latency-model.json `_bound_why`).
- Compute reference: ICT analysis measured at 0.77 ms per bar on the 5m cells and 0.35 ms on 1m for the pool-off group
  (profile §7 model inputs), so a per-bar analysis already fits any second-scale budget. The extra work of the tree is
  O(active nodes) comparisons per closed bar; not measured yet, so "not verified".

**Dependency classes (CLAUDE.md §35-36):**
| Class | Items |
|---|---|
| REQUIRED_FOR_DECISION | the tree state at `t` for the active system's level sources; the reaction class at any node that a live branch depends on; freshness of the underlying candles; event-risk state; risk inputs |
| OPTIONAL_FOR_ANALYSIS | sibling branches not armed; another methodology's tree (Wyckoff/Footprint/Heatmap) |
| VISUALIZATION_ONLY | drawing the tree/expected paths (would need new engine objects and an A2 change; ADR needed) |
| RESEARCH_ONLY | branch statistics, novelty counts, REACHED-vs-actual-path comparisons |

"Precomputed off the hot path" applies to node registration (done when the previous bar closes) and to nothing else. The tree is
REQUIRED_FOR_DECISION, so a stale or missing tree yields WAIT / UNKNOWN, never a silent fall back to the chain
(CLAUDE.md §36, §62; plan §2 A2b). Precompute must not become "stale required data".

## 7. Staged implementation with review gates (TDD, outcome-free evidence first)

Each slice: tests first (red), then minimal code, then review. Review loop limits: max 2 fix rounds per category, 4 total
(rules/review-loop-limits.md); a slice that hits them is split. No slice reads R, expectancy, win rate or any performance metric.

| Slice | Scope | Outcome-free evidence required | Gate |
|---|---|---|---|
| S0 | Spec-as-tests: fixtures for the three reaction classes on synthetic candles; expectation schema and state machine (append-only) | unit tests citing knowledge/ict/core-a.md R6, R7, R11 (lines 196-203) and core-b R3 (line 146); a test that fails if a cited section is missing (pattern of `test_doc_citations`, which has 2 failures on BASE, profile §8) | G0: owner + reviewer accept the schema |
| S1 (smallest) | ICT only, ONE touch type (BSL/SSL pool, `cross`), TWO reactions (SWEEP_RECLAIM, ACCEPT-as-NO_TRADE), reversal action delegated to the existing chain. Full-recompute reference implementation (the pure function) | E3, E4, E5 pass; **novelty count**: for each bar, is the tree's ENTER set a subset of the chain's setup set? (counts only); funnel counts per class and per level type via scripts/diagnose-methods.py; chart images from scripts/build-pit-page.py (A3t; today it draws engine structures only and refuses T >= DEV_CUTOFF; drawing tree nodes needs a small extension, new code, own review) reviewed against knowledge/, never outcomes | G1: if the novelty count shows the reversal branch adds nothing beyond the chain, STOP the method claim (see objection 6) |
| S2 | ACCEPT continuation branch (next level per core-b R3) — only if the owner supplies or approves an entry model | tests, images, funnel counts of continuation candidates (counts) | G2 owner decides the entry model (Q2) |
| S3 | Level sources beyond pools: FVG edges/CE, dealing-range edges, `fx_b_pool=on` | E2, E7; images | G3 |
| S4 | Event-driven evaluator and incremental registration | E1, E2, E6, E7; wall-time table only (seconds, no results) | G4: equivalence suite green |
| S5 | Harness registration: method, grid file, keys in `_OPTS_BASE` / `_SCAN_RELEVANT_KEYS` / `config_opts`; `scan_many` support (until then a non-ICT/WYCKOFF-BOOK method falls back to a plain per-overlay loop, profile §2 fallback) | grid == code registry test; v1 proof: stability rows byte-identical with every `fx_sc_*` at default; ledger declaration | G5: pre-registration sealed |
| S6 | Evaluation: one run, full count, honest report | per plan §4 | owner review; then forward demo only on explicit go-ahead |
| Later | Wyckoff scenario (WA2-27 "prepare BOTH scenarios" at a lower-border break, knowledge/wyckoff/advance.md:1098; WA2-04) | separate design | separate |

## 8. Counter-arguments and resolutions

| # | Objection | Resolution | Status |
|---|---|---|---|
| 1 | Degrees of freedom explode and invite data snooping | Tree shape is fixed by sources, the grid is 4 items, N_new = 9 per cell, counted in the same way (fund_stats.py:328). Design choices before pre-registration (which levels, which branches) are still researcher freedom; slices S0-S5 are outcome-free and frozen at G5. | OPEN (residual: pre-registration design freedom cannot be counted) |
| 2 | Reaction classification is subjective | Mechanical closed-bar predicates from R6/R7/R11; the engine already classifies swept/closed_through (ict-scan.py:302-310). The parts sources do not define (K-bar reclaim, touch distance) are V items, counted. | Resolved for SWEEP/ACCEPT; OPEN for K and approach distance (unsourced) |
| 3 | Tree depth vs sample size at ~5-100 trades/yr | The user-stated frequency is not verified by me; the only counts I read are benchmark trade counts (e.g. 83 trades US500 5m over 2 years, 11 XAUUSD 15m over 2 years, profile §4 table). Splitting by branch shrinks per-branch n below the 30-trade fold minimum (plan §1.4). Mitigation: the method is judged as a whole, never per branch; branch statistics are descriptive (RESEARCH_ONLY). It may simply return "insufficient". | OPEN (primary risk) |
| 4 | Look-ahead through level selection | Nodes exist only when `available_at <= t`; E5 truncation test; classification from closed bars. Note the `PIV` / opts prerequisite (section 3.2). | Resolved by design + E5; prerequisite fix listed |
| 5 | Live/backtest divergence | `tree(t)` is a pure function of a trailing window (section 3.6); but persistence beyond the 576-bar window departs from live-parity that live_rules.py:5-22 insists on, and live would need `H` bars. | OPEN until owner decides Q3 (H = window keeps parity but loses persistence) |
| 6 | It is only a re-parameterisation of the same chain | Partly true. The reversal branch equals the chain by construction and swept/closed_through already exist. Genuinely different: ACCEPT branch, persistence, explicit no-trade, expectation objects. Measure the novelty count in S1; if the ENTER set adds nothing, drop the claim. | OPEN until S1 count |
| 7 | Stale levels | `invalidated_at` from structures (A1b), age cap V item, day-flat rule. No source defines a level's staleness age. | OPEN (age is project-defined) |
| 8 | Interaction with adopted F items | The tree is built on the F-ON analysis (ADOPTED_F_KEYS). `fx_braid_optional` lets an MSS with no raid form a candidate (ict-scan.py:620-632): such a setup has no touched level, so it is not on the tree. Declared rule: it is off-tree and not entered by the scenario method, which makes a real difference vs the chain (counted in E7). `fx_b1_pivot1` changes pivot width and hence the level set (section 3.2). `fx_b2a/b2b` act inside the FVG selection and are transparent. | Resolved by declaration; the braid difference is disclosed |
| 9 | Compute cost of many branches | Bounded by pools in the window; evaluation O(active nodes) per closed bar. Until `scan_many` support (S5) the method uses the slow per-overlay loop (profile §2 fallback), and the profile's BASE/NEW ratios do not transfer. Cost not measured. | Resolved in design; cost not verified |
| 10 | Two levels touched by the same bar | Needs a deterministic tie-break (project-defined: e.g. nearest to the bar's close, then earliest `available_at`); must be fixed before S1 and tested. | Resolved when frozen at G0 (not sourced) |
| 11 | The engine cannot replicate a holistic discretionary read | Correct. Only the mechanical subset is implemented; the claim is limited to "level-conditional reactions", not "trader emulation". | Resolved by scoping; the gap is permanent |
| 12 | Closed-bar reaction is later than a trader's | Stated limitation (section 3.3); 1m is most affected. | OPEN (accepted cost) |

## 9. Where each approach is better, and how they combine

**Incremental-window optimisation is better when:** the goal is feasibility and cost of the pre-registered search; results must
be byte-identical; it adds nothing to N and costs no alpha; it is verifiable with hashes (profile §3). Evidence it already works:
`scan_many` shares one analysis across value sets (profile §2 (A)) and the tail per value set is ~2.3 microseconds per bar
(profile §5). Caveat: a fully incremental `analyze()` is harder than it sounds because its outputs depend on window-global values
(`lo/hi`, median range); the profile lists series-level pivots/FVG-mitigation as the next lever (~35 % of `analyze`, profile §2
"Deliberately not done"), and full sliding-window incrementality is "not verified" as byte-identical-feasible.

**Scenario method is better when:** the question is decision quality and explainability, not speed: explicit expectations
with invalidation (CLAUDE.md §17), an explicit no-trade record (§41), a declared action for the acceptance case, persistent
levels, and a tree that makes REQUIRED_FOR_DECISION inputs explicit (§35-36). It is the only option of the two that can create
trades the chain cannot.

**Scenario method is NOT better when:** speed (it does not reduce the ~95 % analysis cost; profile §1); statistical power
(more structure per trade, fewer trades per branch); certainty of edge (unknown, and it consumes multiple-testing budget);
live-parity (persistence departs from the fixed-window live scan).

**Combination:** (a) first, as a prerequisite: the incremental/shared structure layer feeds node registration, and the
equivalence discipline of test_speed_equivalence.py is reused for E1-E7. (b) then runs on top: the tree consumes structures and
evaluates only on trigger events. Neither substitutes for the other; (a) never alters results, (b) always may.

## 10. Open owner questions

1. Family choice: separate family with disclosed union-bound 0.20, or a stricter split (e.g. 0.05 for the new family)? (section 5)
2. Is a continuation trade after ACCEPT in scope? The sources give the expectation (core-a R6) and next objective (core-b R3) but
   no entry model. Approve a project-defined one, or keep NO_TRADE (then the ACCEPT branch is a filter only).
3. Persistence horizon `H`: keep the live window (parity, no persistence) or allow a longer horizon (a live change, v2-significant)?
4. Latency budget: accept the proposed targets (tree <= 50 ms p99, decision stage <= 1 s p99) or set others; §40 sets none.
5. Touch and reclaim parameters: accept ATR-based approach distances (0.25 / 0.5) and K in {1,2,3} as project-defined and counted?
6. Which cells (timeframe x asset class) and the final count for N (ledger declaration).
7. Draw the tree on the chart? That needs new engine objects and an A2/ADR change (plan §2 A2: chart draws engine objects only).
8. Is Wyckoff (WA2-27 two-scenario at the lower border) a later slice or out of scope?

## Sources read for this design

CLAUDE.md (§8, §9, §13-§17, §18, §20, §35-§40, §41-§47, §59, §62); docs/plans/2026-09-28-methodology-improvement-plan.md;
docs/plans/2026-09-30-owner-decisions.md; docs/plans/2026-09-29-execution-plan.md (Shared contract section);
scripts/structures.py; scripts/live_rules.py; scripts/ict-scan.py (lines 86-150, 207-330, 584-755); scripts/automation.py:185-197;
scripts/fund-search.py (1-160); scripts/fund_stats.py (grep: FAMILY_ALPHA, n_per_method); scripts/build-pit-page.py (1-40);
docs/audits/2026-09-30-engine-speed-profile.md; docs/architecture/latency-model.json (head); docs/architecture/v-grid-ict.json (head);
knowledge/ict/core-a.md and core-b.md (grep of §3.2/§3.3/§3.x rules), knowledge/wyckoff/advance.md (grep WA2-04, WA2-27).
Not read: scripts/backtest-methods.py, scripts/scan_many.py body, scripts/pit.py body, scripts/diagnose-methods.py body,
scripts/wyckoff_rules.py, docs/adr/0009 text. Statements about them are "not verified".
