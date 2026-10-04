# Family VC -- does the gold trend edge (H7, G9) concentrate on volatile days or on early entries? -- pre-registration DRAFT (2026-10-04) [VC-P1]

Status: DRAFT. Not sealed.

Sealing: the coordinator commits this text, after review, as
`docs/plans/2026-10-04-vc-volatility-condition-preregistration.md`, with the status line above replaced by a line that reads
exactly "Status: SEALED" and with §11's code manifest filled in. `scripts/research/edge_vc.py` refuses every read until then
(scripts/research/prereg_guard.py `require_sealed`, `require_fingerprint`), and runs each read once
(`require_read_once`: one output name per read, refused if that read's output exists or was ever committed).

**No outcome of this family has been read.** The code was tested on hand-built series only
(`scripts/tests/test_edge_vc.py`, `scripts/tests/test_pit_trend.py`, `scripts/tests/test_prereg_guard.py`). Ranked first in
docs/plans/2026-10-04-research-directions.md §1. Revised three times after reviews (2026-10-04). Revision 1: holdout partly
exposed, guard, drift bias of T1b, shared days, VC-X cost and windows, frozen hold cut. Revision 2: the lead decisions below,
T1b on R per sqrt(bar) (a constant per-bar edge alone passes a raw-R T1b), the exact stop figures, the density selection and
last-bar signals disclosed, the forward read's dataset snapshot, read-once enforcement, both account layers (§9).
Revision 3 (the review of revision 2): T1b's cell means are weighted by the planned bars, so the last-hour entries no
longer rule it (§2, §4, §7); the trade counts are corrected (window B ~950, window A ~3,200; §7); a window-B pass is
discovery grade and TF confirms it (§3); T1a's switch to R_bar has a fixed trigger (§4); the forward read takes its start
from the seal commit, checks its xau-holdout file and re-prices R_net at the recorded cost profile (§2, §3); the H5 prior
on the VR rule is cited (§1); the account layers need a row filter first (§9).

**Lead decisions 2026-10-04** (owner-authorised independent work):
- Window B (gold before 2008-12-10) is the DECISIVE test; window A (to 2017-12-31) is report-only (§3). `HOLDOUT = "B"`.
  Window B is UNREAD-FOR-H, so a pass there is DISCOVERY-GRADE for the condition; TF on forward data confirms it.
- VC on the personal account: default NO; any use is an owner decision (§9).
- VC-X group B: from 2024-03-01 only, as CX (§3).

## 0. Origin (disclosed) and question

- The lead is post hoc, on exposed data. G9 gold at stop 1.4, mean R by stop-width quartile "since 2018", narrowest to
  widest: -0.02 / +0.01 / +0.12 / +0.29; G9 silver -0.08 / +0.05 / +0.05 / +0.17; H7 gold +0.04-0.05 to +0.07-0.10
  (docs/audits/2026-10-04-personal-account.md:47-55 at f76d6fa).
- **Provenance gap.** That table has no committed code and no JSON: commit e6a77ae adds only the .md and the .json, and the
  JSON has no quartile key. Its exact start is unknown. The personal-account bootstrap starts 2018-02-26
  (`scripts/research/personal_account.py` `POST_DISCOVERY_FROM`), but "since 2018" may mean 2018-01-01. This draft
  therefore treats ALL of 2018 onwards as the source of the finding.
- The stop is k x sigma_5m x sqrt(bars from entry to the server day's last bar) x price (scripts/research/book_sim.py:59).
  A "wide stop" is therefore three things at once:
  1. a volatile day (sigma_5m high);
  2. an early entry (many bars left in the day);
  3. in absolute bp, the high-volatility gold years (2020, 2024-26).
- Cost dilution does not explain it: gold's round trip is ~0.65 bp (docs/plans/2026-10-03-reframes.md:88) against a median
  stop since 2024 of 108 bp (H7) and 99 bp (G9) at k = 1.4 (docs/audits/2026-10-04-personal-account.json `min_lot`; the
  141-155 bp figures are k = 2.0): about 0.006 R.
- **Question.** On data where this split was never computed, is mean R higher (a) on volatile days, (b) for early entries,
  beyond what the stop's sqrt(bars) scaling gives them anyway? (3) is not tested: a level filter in absolute bp would select
  years, not days.

## 1. The two conditions (fixed now)

- **(a) HIGH volatility day.** sigma_5m(D) > the median of sigma_5m over the previous 250 days that have one, given at
  least 125 of them. This is F3 H5's own regime rule (scripts/research/edge_f3.py:30, :99-116), reused unchanged. VR =
  sigma / that median. No VR -> excluded and counted.
  - **Its earlier use on gold (a prior, disclosed).** F3 H5 kept E5's FVG retrace events only on this rule's HIGH days
    (by the signal day; scripts/research/edge_f3.py:99-116), gold 2005-2016, and tested their excess over a placebo:
    discovery p 0.0107, not BH-rejected; confirmation p 0.115 (docs/audits/2026-10-02-edge-f3.md:55). That is another
    detector and no HIGH-versus-LOW contrast. No VR split of H7 / G9 was ever computed, so window B stays UNREAD-FOR-H for
    VC (§3).
  - Gold / silver: the research-mode dense-day sigma history (edge_census.Series `_vol` over `dense_days`, as H5).
    **Inherited selection, disclosed (review item 21).** In research mode a day has a sigma only if the whole day turns out
    dense (scripts/research/edge_census.py:121-124; the dense threshold is 0.8 x the median bars per day of the loaded
    history, :104-107). book_sim drops a signal on a day without one, so the VC sample inherits a same-day completeness
    selection. Measured on this book: it removes 55 H7 and 78 G9 gold trades of ~6,000 and moves mean R by at most
    0.002 R (docs/audits/2026-10-04-density-selection-check.md). The dry run counts the events it drops per window
    (`no_research_sigma`).
  - Crypto: the [CX-P1] point-in-time sigma of each eligible day (scripts/research/pit_trend.py `context`).
- **(b) LONG HOLD (early entry).** The trade's entry server-clock slot (minutes from server midnight of the entry bar) is
  EARLIER than the median entry slot of the same component's VC-G trades in the decisive window. The FTMO server day ends at
  a fixed clock time (New York + 7 h), so an earlier slot means more bars to the end of the day. The slot is entry timing,
  known at entry.
  - The medians are computed ONCE, in the VC-G read, on window B, and recorded in its JSON (`hold_medians`). The
    report-only window, the forward read and any filter use those recorded constants, never a median of their own rows. A
    component without a recorded median (silver: no window-B trade with a VR) has no hold split. The outcome-blind dry run
    reports the medians first.
- Each trade's day is its ENTRY server day (book_sim rows carry no signal index). VR uses only earlier days: point in time.
- **Signals on a server day's last bar (review item 21).** H7 / G9 enter at the bar after the signal. book_sim keeps a
  signal on a day's last bar: it enters at the next server day's first bar and holds that whole day, with the stop sized by
  the SIGNAL day's sigma. Its VC row takes the ENTRY day's VR, slot and bars (`entry_next_day`). The dry run counts these
  events per window; the read counts them per component. The paper log drops such signals
  (scripts/research/fvg_forward.py `signals`: "no same-day trade"), so the forward read never has them.

## 2. Outcome per trade

- The book's mechanics, unchanged (scripts/research/book_sim.py:38-82): entry at the next bar's open, protective stop k x
  sigma_5m x sqrt(planned bars), time exit at the server day's last bar, relative spread cost.
- **k = 1.4**, the stop of fvg-book v4 now on the demo (docs/architecture/trading-systems.json:272-273). k = 2.0 (v3) is
  report-only (with the k = 1.4 hold medians).
- **R_gross** = side x (exit - entry) / stop distance. R_net = R_gross - cost / stop distance.
  Why gross: cost per unit of stop falls mechanically as the stop widens, so a NET gradient is partly guaranteed by
  arithmetic. The tradability gate uses R_net (§4).
  - The forward read re-prices R_net from each paper row's logged entry and exit (times and prices) at the cost profile the
    read records, with fvg_forward.resolve_row's formula. The log's own R was priced when the row resolved, and no profile
    was recorded then; it is kept as `R_net_log`, and the read counts the rows where the two differ.
- **R_bar** = R_gross x sqrt(144 / planned bars), the statistic of T1b. The planned bars are the stop's own horizon
  (book_sim: entry to the day's last bar; paper log: on the clock, `bars_to_day_end`). 144 (half a 288-bar day) only sets
  the unit, "R at a 144-bar hold"; the p-value does not depend on it.
  - **Each cell's mean of R_bar is weighted by the planned bars** (`edge_vc.nb_weight`): sum(R_bar x nb) / sum(nb) =
    12 x sum(R_gross x sqrt(nb)) / sum(nb). Why: Var(R_bar) = 144 / nb x Var(R), and Var(R) hardly depends on nb (the stop
    scales with sqrt(nb)). An entry 2 bars before the day's end gets 72 times the variance of a 144-bar entry, so a plain
    mean is ruled by the last-hour entries (§7). The weights are the inverse variance. The CR1 SE uses the weighted
    influence (`edge_vc._contrast`).
- VC-X (crypto) charges the [CX-P1] cost model: half the recorded relative spread per leg at the leg's table bucket plus
  c_sym (pit_trend `SpecCost`). A crypto read without it is refused.

## 3. Reads (each once, each in its own commit)

Grades as in docs/plans/2026-10-04-research-directions.md §0. Output names: `docs/audits/<YYYY-MM-DD>-edge-vc-<read>.json`
with read = xau-holdout, crypto or forward; any other path is refused.

| read | data | grade | tests |
|---|---|---|---|
| **VC-G gold holdout** | book_sim.trades of H7_XAUUSD_eod, G9_XAUUSD_eod, G9_XAGUSD_eod by entry server day: window B decisive, window A report-only (below) | window B UNREAD-FOR-H. Label of a pass: "DISCOVERY-GRADE for the condition (components exposed)"; TF is its confirmation | T1a, T1b, T2 |
| **VC-X crypto** | FTMO crypto CFDs: CX group A members over their whole history, CX group B members from 2024-03-01 only ([CX-P1] §3: H7x read B's underlying through 2024-02-29; lead decision 2026-10-04), to the CX amendment's end date; H7 / G9 by pit_trend ([CX-P1] §1: min_bars 230, calendar previous day); CX costs | UNREAD-FOR-H at read time (the CX reads come first, §5). Windows CX retired unread after a failed gate are read here: disclosed and logged (§5.4) | T3 |
| **VC-F forward** | the paper log's H7 / G9 XAUUSD rows at stop_k 1.4 (scripts/research/fvg_forward.py:36-38) entering on a server day after the server day of the seal commit (git: `prereg_guard.first_forward_day`; no date is typed). The xau-holdout JSON it uses is checked: its read name, commit state, tag, read and window (`prereg_guard.require_read_json`, `edge_vc.xau_primary`) | FRESH | TF |

**The VC-G windows -- lead decision 2026-10-04** (`edge_vc.HOLDOUT = "B"`, `REPORT_WINDOW = "A"`):

- **B (DECISIVE):** gold entries before **2008-12-10** (2004-06 -> 2008-12-09). No personal-account replay touched it.
  Grade: UNREAD-FOR-H. Gold has a VR from about 2005-01 (20 dense days for a sigma, then 125 days of sigma history), so
  about 950 trades (an estimate at the discovery rate, §7; the dry run replaces it).
  - "Decisive" means its verdict, not window A's, counts. Under the grades of research-directions §0, UNREAD-FOR-H data is
    valid as discovery: H7 / G9 were selected on these years, only this split was never computed. A pass here is therefore
    DISCOVERY-GRADE for the condition. TF on forward data is its confirmation.
  - Silver's 5m history starts 2008-11-07, so no silver trade has a VR before 2008-12-10: T2 is "not run (window)" and
    enters its Holm family with p = 1.
- **A (report-only):** entries before **2018-01-01** -- gold from 2004-06, silver from 2008-11 -- tested exactly as B, with
  B's hold medians.
  - Grade: **PARTLY EXPOSED** from 2008-12-10 to 2017-12-31. All personal-account replays (modes skip, floor, floor_cap,
    and the fixed 100 USD cap of b818e99) drop or size trades by an absolute stop width on the common span 2008-12-10 ->
    2026-10-02 (docs/audits/2026-10-04-personal-account.json `meta.common_span`). `skip` drops every trade whose minimum
    lot risks more than r x balance at the reference price (`personal_account.py` `lots_for`): about 120 bp of stop at
    r 1 % on 5,000 USD for gold. The cells report compounded account metrics (terminal multiple, CAGR, drawdown), not mean
    R by stop width, and nobody computed "common span minus post-discovery". It is still a related cut on these years.
- 2018-01-01 onwards, gold and silver, are EXPOSED for VC (the hypothesis came from them). They are never a VC test.
- H7 / G9 on the indices, PGMs and research-only CFDs failed their own reads (edge-f3.md, edge-f4.md, edge-f5.md). They
  are not tested under this condition: a rescue by subgroup is fishing.

## 4. Tests and decision rule

**Test statistic (every test): the side-balanced difference** 1/2 [(mean y True half - False half | long trades) +
(same | short trades)], with y = R_gross for T1a, T2, T3 and y = R_bar for T1b (nb-weighted means, §2).

- **Why balanced.** Under a constant MARKET drift mu, a trade's R carries side x mu x sqrt(bars) / (k x sigma): opposite
  signs for longs and shorts. Early entries of the majority side then earn more R with no conditional effect; in a gold bull
  market (mostly long trades) a pooled T1b would pass on drift alone. The balanced difference cancels that term (synthetic
  check: scripts/tests/test_edge_vc.py `test_constant_drift_does_not_pass_t1b`). It also removes the opposite bias in T1a
  (a given drift is fewer R on high-sigma days). The plain pooled difference is report-only.
- **Why R_bar for T1b (review item 11).** A constant per-bar EDGE in the trade's own direction adds c x sqrt(bars) to R for
  BOTH sides. Balancing by side does not remove it, so early entries win a raw-R T1b mechanically (§7: +0.03 to +0.05 R at
  a pooled mean R of about 0.09). R_bar has the same mean at every entry time under that edge, so T1b asks whether the
  per-bar edge is larger for early entries (`test_constant_edge_does_not_pass_t1b`). The raw-R T1b is report-only.
- **Why weighted (review of revision 2).** T1b's cell means are nb-weighted (§2). With 10 % of entries in the day's last
  19 bars, a plain mean of R_bar has an SE of ~0.090 at 950 trades and leans -0.018 under a constant edge; the weighted
  mean has ~0.057 and -0.008 (synthetic, §7; `test_late_entries_do_not_rule_t1b`).
- **T1a's statistic, fixed now.** T1a keeps R_gross: it splits by volatility, not by bars. T1a is amended to the weighted
  R_bar before sealing if, in window B's dry-run counts, the pooled gold mean planned bars of the HIGH and LOW halves differ
  by more than 10 % of the smaller (`xau_pooled.decisive.vr_halves_bars_gap` > 0.10, `edge_vc.power_inputs`; §10.3). The
  threshold is set before any count is seen.
- **Variance.** CR1 cluster-robust by server day for the contrast as a whole (each day's summed influence across the four
  side x half cells; in a weighted cell a trade's influence is nb x (y - cell mean) / the cell's total nb). One cluster per
  day, so it stays valid when the halves share days: crypto symbols pooled on one
  server day (the probe found shared days), and an H7 and a G9 trade of one gold day in different T1b halves. Gold T1a and
  T2 never share a day across halves (one VR per day per symbol). The shared-day count is reported.
- Student-t with min(days in each of the four cells) - 1 df; one-sided (True > False). A test with an empty cell is not
  computable and enters its family with p = 1.

| test | data | condition | gate |
|---|---|---|---|
| T1a | VC-G window B, H7 + G9 XAUUSD pooled | (a), y = R_gross | Holm m = 2 over {T1a, T1b}, alpha 0.05; AND True-half mean R_net > 0; AND the balanced difference > 0 in BOTH gold components |
| T1b | VC-G window B, H7 + G9 XAUUSD pooled | (b), y = R_bar, nb-weighted cell means | same Holm; same two extra conditions (the components' differences on the weighted R_bar) |
| T2 | VC-G window B, G9 XAGUSD | (a) | Holm m = 2 over {T2, T3}, alpha 0.05 (secondary). Not run in window B: p = 1 |
| T3 | VC-X, crypto pooled | (a) | same secondary Holm; a test not run enters with p = 1 (with T2 at p = 1, T3 needs p <= 0.025) |
| TF | VC-F forward | only the T1 sub-test(s) that passed, on the same y | Holm over those at alpha 0.10; AND True-half mean R_net > 0 |

- T1 is the decision test for the gold book. T2 / T3 inform the mechanism; they never adopt a filter.
- The forward read runs once, at >= 150 closed rows or 365 days after the seal, whichever comes first, counting only rows
  that enter after the seal commit's server day. It is scheduled only if T1a or T1b passed. TF's (b) uses the VC-G
  `hold_medians`.
- Window A (report-only) never changes a verdict.
- Zero passes is a valid result.

## 5. Ordering constraints

1. VC-G may run right after sealing.
2. **VC-X runs only after every scheduled CX read is done.** A VC-X read computes both halves, which implies the pooled
   H7 / G9 mean on CX's windows: run earlier, it would expose them. The code checks the committed CX files, not just
   their existence (`edge_vc.cx_closure`): the screening amendment carries the tag, the end date and the members per
   group; every group-A read up to the first one where no test advanced, and the group-B read, must be present with the
   CX tag. Symbols and the end date come from the amendment, never from the command line.
3. VC-X uses pit_trend.py, written to [CX-P1] §1. `scripts/research/edge_cx.py` does not exist yet. Before sealing, the
   coordinator reconciles: one rule definition (or an amendment here naming edge_cx's), and the field names that
   `cx_closure` reads (amendment `tag`, `end`, `members.A/B`; read `meta.tag/group/read`, `verdicts.<test>.advances`).
4. Ledger entries, committed with the seal:
   - gold / silver 2018-01-01 -> 2026-10-02: EXPOSED for VC (trigger `hypothesis_refinement`);
   - window B (gold 2004-06 -> 2008-12-09) as development data read once for this condition;
   - window A's remainder (2008-12-10 -> 2017-12-31): read report-only for this condition, already partly exposed through
     all personal-account replays;
   - after VC-X: the CX windows it read that CX had retired unread (the read JSON lists them, `retired_windows_read`)
     become exposed for H7 / G9 on crypto (trigger `hypothesis_refinement`).

## 6. Report-only diagnostics (outside the family)

- Window A: every test, with window B's hold medians, and its counts.
- The literal finding on the holdout: mean R_gross and R_net by stop-width quartile (cut points from the holdout's own
  stop_bp, a timing-and-volatility quantity).
- The raw-R T1b (`T1b_raw_R_report_only`), and the pooled (unbalanced) difference and per side x half cells of every test.
- Mean planned bars in each half of every test.
- The 2 x 2 of (a) x (b): which one carries the gradient.
- Long and short separately (drift check), and per year.
- k = 2.0 rerun of everything (the k = 1.4 hold medians).
- Counts per window: trades with and without a VR, `entry_next_day` rows, shared days per test.

## 7. Power and prior (before any read; arithmetic, the dry run gives the counts)

All counts below are estimates. Sealing step 3 replaces them with the dry run's (§10.3).

- Per-trade sd of R at k = 1.4 ~0.75 (docs/audits/2026-10-03-vol-schedule.md:29). Balancing by side costs ~2 % in SE at a
  60 / 40 side mix and ~9 % at 70 / 30.
- MDE = 2.80 x SE (80 % power, one-sided alpha 0.025: the first Holm step). Trades are treated as independent; an H7 and
  a G9 trade on one day share a CR1 cluster, so the read's SE can be larger. The dry run's cells carry the day counts.
- **Window B (decisive), gold: ~950 trades.** Gold's discovery span is 2004-06-14 -> 2016-11-29 (split 2016-11-30,
  docs/audits/2026-10-02-edge-census.json `meta.symbols.XAUUSD`). It holds 1,197 H7 and 1,780 G9 trades
  (docs/audits/2026-10-02-edge-f3.md:14, docs/audits/2026-10-02-edge-f4.md:13): ~240 a year. Window B with a VR runs
  ~2005-01 -> 2008-12-09, ~3.9 years. Revision 2 used the full-history rate (5,979 trades in 22 years, vol-schedule.md:6,
  ~270 a year). Later years pull that rate up (confirmation: ~300 a year), so it overstated window B (~1,050-1,100).
  - **T1a:** SE ~0.050 R (60 / 40 sides) to ~0.053 (70 / 30): **MDE ~0.14-0.15 R**.
  - **T1b (nb-weighted R_bar):** SE = sd(R) x sqrt(1/4 x sum over the four side x hold cells of 144 / (planned bars in
    the cell)) (`edge_vc.power_inputs`). Synthetic (below): SE 0.052 with entries spread evenly over 20-260 bars, 0.057
    with 10 % of entries in the last 19 bars, at the simulation's per-trade sd of 0.70. At sd 0.75 that is 0.056-0.061:
    **MDE ~0.16-0.17**, in R at a 144-bar hold.
  - The 2018+ quartile table implies a half-split difference near 0.2 R for G9 gold: window B sees it only if ~70-75 % of
    it is real.
- **Synthetic check (review item 11 and the review of revision 2).** Gaussian 1-sigma bars, stop at 1.4 x sqrt(planned
  bars) filled at the stop, time exit, 60 / 40 long / short; 60 replications of 2,000 trades, SEs scaled to 950 trades.
  The generator is `sim_rows` in scripts/tests/test_edge_vc.py. The reported CR1 SEs match the spread of the estimates
  across replications. Entries spread evenly over 20-260 bars / with 10 % in the last 19 bars:

  | per-bar edge in the trade's direction | raw-R T1b (report-only) | plain mean of R_bar | nb-weighted R_bar (T1b) |
  |---|---|---|---|
  | constant (pooled mean R ~0.09) | +0.031 / +0.046 | -0.020 / -0.018 | -0.013 / -0.008 |
  | twice as large for entries with > 140 bars | +0.153 / +0.148 | +0.089 / +0.056 | +0.090 / +0.082 |
  | SE at 950 trades | 0.046 / 0.046 | 0.057 / 0.090 | 0.052 / 0.057 |

  - The constant edge moves a raw-R T1b by 0.7-1.0 SE: it would pass on that alone ~10-17 % of the time, not 2.5 %.
    The reviewer's own estimate of that part was ~+0.02 R under other entry-time assumptions.
  - The weighted R_bar leans slightly against a pass under a constant edge (the stop caps losses at -1 R). The plain mean
    leans more, and the last-hour entries raise its SE from 0.057 to 0.090 (the weighted mean's: from 0.052 to 0.057).
  - A per-bar edge twice as large for early entries gives +0.08-0.09 on the weighted R_bar: at sd 0.75, window B would
    find it only ~25-35 % of the time. T1b is a test for a large timing effect.
- **Window A (report-only):** ~3,200 gold trades: the 2,977 discovery trades, less ~130 before a VR exists
  (2004-06 -> 2005-01), plus ~330 from 2016-11-30 to 2017-12-31 at the confirmation rate (H7 890, G9 1,282 over
  2016-11-30 -> 2024-02-29: edge-f3.md:15, edge-f4.md:13). MDE ~0.08 R. Silver ~1,400: F4 G9 XAGUSD discovery n 1,502
  (edge-f4.md:14) over 2008-11-10 -> 2018-02-25 (silver's split 2018-02-26), less ~6 months without a VR and less
  2018-01-01 -> 2018-02-25. MDE ~0.12 R.
- VC-F: at 150 rows, SE ~0.13 R; MDE ~0.27-0.31 R for T1a (alpha 0.10 for one sub-test, 0.05 at the first Holm step of
  two), ~0.30-0.39 for T1b. Forward has low power; it is a check against a large in-sample artefact, not a precise
  estimate.
- Prior: moderate that some gradient exists (~40 %); low (~15 %) that a filtered book beats the unfiltered book at equal
  risk after forward data. Literature: Gao, Han, Li, Zhou (2018, JFE) report stronger intraday momentum on high-volatility
  days (not verified here); the repo's E7 read that index outcome window (docs/plans/2026-10-03-crypto-cfd-design.md:251).

## 8. Budget

- VC: decisive T1a, T1b (Holm m = 2); secondary T2 (not run in window B, p = 1) and T3 (Holm m = 2); 1-2 forward tests.
  Reads: VC-G 1, VC-X 1, VC-F 1. Report-only: window A, the raw-R T1b, k = 2.0.
- It refines H7 / G9 (CLAUDE.md §43-44). Cumulative tests before it: research-directions §4.

## 9. What a result changes (both account layers; described, not run)

- **T1a or T1b passes (discovery grade):** a CANDIDATE filter for fvg-book (trade v4 only on HIGH days, or only entries
  before the recorded median slot of each component). It is a NEW setup version (CLAUDE.md §47).
  - Both replay tools take book_sim rows, so the filter is a ROW FILTER on them (the entry day's VR, or the entry slot
    against the recorded median), applied before the replay. Neither tool has one today.
  - **FTMO (challenge layer).** The filtered book is replayed with the existing book / challenge machinery against
    unfiltered v4 at equal risk per trade: `scripts/research/pass_policy.py` (`challenge`, `evaluate_hist`,
    `evaluate_boot`: Phase 1 +10 %, Phase 2 +5 %, the 5 % daily and 10 % total loss limits) and the 12-month value replay
    of `scripts/research/vol_schedule.py`; `book_sim compare` for the daily-R correlation. `pass_policy.prepare` takes
    book_sim rows per component (scripts/research/pass_policy.py:161-162), so the filter drops rows before it. Labelled
    POLICY-EXPOSED. The demo uses the filter only after TF passes and the owner approves.
  - **Personal 5,000 USD account (default NO, lead decision 2026-10-04).** No personal-account use follows from a pass.
    Any use is an owner decision, recorded before use (research-directions §5, decision 4), and comes after TF passes. If
    the owner says yes, the filtered rows are first replayed descriptively through `scripts/research/personal_account.py`
    (5,000 USD, the minimum lot, the owner's capped minimum-lot mode, compounding, ruin). That script loads whole book_sim
    components (its `BOOKS`, scripts/research/personal_account.py:241-243 at b818e99) and has no row filter; the
    personal-account workflow owns the file and would add one.
- **Both fail:** the 2018+ gradient is treated as a regime, timing or chance effect. The research lead in
  personal-account.md §4.2 is closed. The owner's capped minimum-lot rule stands or falls on its own sizing study, not on
  this.
- **T3 passes but T1 fails:** the gradient is a property of crypto trends, not evidence for gold. Neither account layer
  changes.
- **Window A only (report-only) shows a gradient:** nothing changes; it is partly exposed.

## 10. Sealing steps (coordinator)

1. Window: decided (lead decision 2026-10-04, window B decisive); `HOLDOUT = "B"` is already set in
   `scripts/research/edge_vc.py`.
2. Review this draft and the code (`scripts/research/edge_vc.py`, `pit_trend.py`, `prereg_guard.py`, the tests).
3. Outcome-blind dry run: `python3 scripts/research/edge_vc.py dry-run --out <scratch json>` (per component and window:
   events by VR half, the median entry slot, the hold halves per VR half, `entry_next_day`, `no_research_sigma`, planned-
   bar quantiles and the count under 24 bars, and per side x half the events, planned bars and days; pooled gold:
   `power_inputs`; no trade is simulated). Amend §7 with the counts and the MDEs they give (MDE = 2.80 x 0.75 x
   `xau_pooled.decisive.se_per_sd`). If `xau_pooled.decisive.vr_halves_bars_gap` > 0.10, amend T1a to the weighted
   R_bar (§4).
4. Commit the final code. Then `python3 scripts/research/edge_vc.py manifest` and paste its lines into §11.
5. Commit this text under the sealed name with the exact "Status: SEALED" line, and the ledger entries of §5.4.
6. Read: `python3 scripts/research/edge_vc.py run --read xau-holdout --out docs/audits/<date>-edge-vc-xau-holdout.json`,
   committed alone. Any code change after step 4 makes the guard refuse (re-print the manifest, re-seal by amendment). A
   second run of any read is refused, to any path.
7. Forward, when due: `python3 scripts/research/edge_vc.py run --read forward --xau
   docs/audits/<date>-edge-vc-xau-holdout.json --out docs/audits/<date>-edge-vc-forward.json`. No date is typed: the
   window starts on the server day after the commit that added the sealed text (an amendment does not move it).

## 11. Code and its fingerprint

- `scripts/research/edge_vc.py`: `vr_by_day`, `label`, `mark_hold`, `per_bar`, `nb_weight`, `bars_to_day_end`,
  `split_test` (side-balanced, joint CR1, optional row weights), `holm`, `t1_verdict`, `xau_read` (book_sim.trades + the
  research sigma history; decisive and report-only windows), `cx_closure`, `crypto_rows` (pit_trend + CX cost),
  `is_forward_row` / `forward_rows` (R_net re-priced) / `forward_tests`, `xau_primary`, `forward_snapshot` (paper-log
  sha256, merged-candle digest and sources, cost profile), `cost_profile`, `dry_counts`, `power_inputs`,
  `secondary_verdict`, CLI with the registration guard.
- `scripts/research/pit_trend.py`: the [CX-P1] §1 rules as a library. `scripts/research/prereg_guard.py`: the guard,
  including `seal_time` / `first_forward_day` (the forward start, from git) and `require_read_json` (an earlier read's
  JSON is used only when its name, commit state, tag and read match).
- Tests: `scripts/tests/test_edge_vc.py`, `scripts/tests/test_pit_trend.py`, `scripts/tests/test_prereg_guard.py`
  (hand-built bars and synthetic trades; a truncation probe for the events and for VR; the market-drift, edge-drift,
  late-entry, weighted-SE and shared-day checks; the first forward day and the gold read checks; read-once; a
  module-coverage check).
- The guard refuses a read unless every file in `edge_vc.CODE` is listed below with its current sha256, and refuses to
  write a result if the read executed a repository module not listed.

Code manifest (filled at sealing by `python3 scripts/research/edge_vc.py manifest`; empty in this draft):

```
(paste here)
```
