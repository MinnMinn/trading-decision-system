# Family VC -- does the gold trend edge (H7, G9) concentrate on volatile days or on early entries? -- pre-registration DRAFT (2026-10-04) [VC-P1]

Status: DRAFT. Not sealed.

Sealing: the coordinator commits this text, after review, as
`docs/plans/2026-10-04-vc-volatility-condition-preregistration.md`, with the status line above replaced by a line that reads
exactly "Status: SEALED" and with §11's code manifest filled in. `scripts/research/edge_vc.py` refuses every read until then
(scripts/research/prereg_guard.py `require_sealed`, `require_fingerprint`), and runs each read once
(`require_read_once`: one output name per read, refused if that read's output exists or was ever committed). A read also
refuses until the committed research ledger carries the study entry `vc_volatility_condition` (`edge_vc.require_ledger`,
§5.4), and the gold read refuses unless the stored 5m history matches §7's `dataset-sha256` lines
(`edge_vc.require_dataset`). This draft file stays in the repository beside the sealed text: the tests read it.

**No outcome of this family has been read.** The code was tested on hand-built series only
(`scripts/tests/test_edge_vc.py`, `scripts/tests/test_pit_trend.py`, `scripts/tests/test_prereg_guard.py`). Ranked first in
docs/plans/2026-10-04-research-directions.md §1. Revised four times after reviews (2026-10-04), and once on the lead's
decisions (2026-10-05). Revision 1: holdout partly exposed, guard, drift bias of T1b, shared days, VC-X cost and windows,
frozen hold cut. Revision 2: the lead decisions below,
T1b on R per sqrt(bar) (a constant per-bar edge alone passes a raw-R T1b), the exact stop figures, the density selection and
last-bar signals disclosed, the forward read's dataset snapshot, read-once enforcement, both account layers (§9).
Revision 3 (the review of revision 2): T1b's cell means are weighted by the planned bars, so the last-hour entries no
longer rule it (§2, §4, §7); a window-B pass is discovery grade and TF confirms it (§3); T1a's switch to R_bar has a fixed
trigger (§4); the forward read takes its start from the seal commit, checks its xau-holdout file and re-prices R_net at the
recorded cost profile (§2, §3); the H5 prior on the VR rule is cited (§1); the account layers need a row filter first (§9).
Revision 4 (the review of the seal preparation, lead decisions D1-D4 below, and a second adversarial review of the fix):
the decisive rows are point in time except the dense threshold (§1, §2); the power statements give the full rule's power
and T1a's regime-block sensitivity (§4, §7, §9); the stored history is pinned (§7, §10); the paper log's refusals are
counted (§2); the F4 G5 NR7 prior is disclosed (§1); three report-only sensitivities and a DATA-SENSITIVE label are
pre-registered (§4, §6); the read refuses when bytecode could load from outside the repository (§11).
Revision 5 (lead decisions 2026-10-05, below): T1a also needs its contrast with the VR runs as clusters at p <= 0.05
(option C, §4, §7); the whole-history dense rule, the report-only refusals and the fix round's additions are kept.

**Sealing amendment (2026-10-04; outcome-blind dry run, §7).** The sealing dry run, on the point-in-time definition (D2),
counts 762 gold trades with a VR in window B (H7 302, G9 460); 72 % fall on HIGH days. T1a's fixed switch fired: the HIGH
and LOW halves differ by 12.0 % in mean planned bars (> 10 %), so T1a uses T1b's nb-weighted R_bar (§4). MDE of the pooled
test in window B: T1a ~0.18 R, T1b ~0.16 R; up to ~0.21 / ~0.19 R if an H7 and a G9 trade of one day move together (§7). The
FULL pass rule also needs both gold components' differences > 0: its power is ~0.8 only for an equal effect of >= 0.2 R in
both components, and ~0.4-0.5 for an effect concentrated in G9 (the 2018+ shape) (§7). **T1a's halves are 8 runs of
consecutive days (4 HIGH, 4 LOW), almost calendar years, so its day-clustered SE can understate its error (§4, §7).** T1a
therefore also needs the same contrast with the VR runs as clusters at one-sided p <= 0.05 (lead decision 2026-10-05,
option C, §4): with no block effect its power at an equal 0.20 R_bar effect falls from 88.0 % to 82.1 %
(§7); a regime-level effect is for TF to confirm. No trade was simulated: a trace of the dry run shows that no exit walk,
cost or R ran (§7). A read also needs the ledger entry (§5.4, §10). VC-X's CX field contract is a refusal condition,
because `scripts/research/edge_cx.py` does not exist yet (§5.3).

**Lead decisions 2026-10-04** (owner-authorised independent work):
- Window B (gold before 2008-12-10) is the DECISIVE test; window A (to 2017-12-31) is report-only (§3). `HOLDOUT = "B"`.
  Window B is UNREAD-FOR-H, so a pass there is DISCOVERY-GRADE for the condition; TF on forward data confirms it.
- VC on the personal account: default NO; any use is an owner decision (§9).
- VC-X group B: from 2024-03-01 only, as CX (§3).
- **D1, lead decision 2026-10-04 (review item 1, power).** Window B stays decisive: window A is partly exposed (the
  personal-account replays compared skip against floor, outcomes that depend on the stop width, on 2008-12-10 ->
  2026-10-02). The power statements give the FULL rule: ~0.8 only for an equal effect of >= 0.2 R in both gold components;
  ~0.4-0.5 for a G9-concentrated effect (the 2018+ shape). A T1 fail therefore reads "NOT SHOWN (inconclusive for a
  G9-concentrated effect)", never "lead closed" (§7, §9; `edge_vc.t1_verdict` `reading`). TF (forward) stays the
  confirmation of a pass.
- **D2, lead decision 2026-10-04 (review items 2-3, point in time in window B).** The decisive statistic is point in time,
  built from the existing modules without editing any frozen file, EXCEPT the dense-day threshold (§1, §2): events and
  sigma from `edge_census.Series(..., sigma_every_day=True)` (no same-day completeness selection); planned bars nb from the
  entry-time CLOCK (`edge_vc.bars_to_day_end`, the paper log's count) for the stop width, R_bar, the T1a / T1b weights and
  the gap rule; the exit walk of book_sim with that stop, as `scripts/research/fvg_forward.py` `resolve_row` implements it.
  The dense threshold is the whole stored history's (edge_census.py:104-107); a causal one is possible without a frozen
  edit and is pre-registered as a sensitivity, with the inherited research-mode rows: if either gives another T1 verdict,
  the read is labelled "DATA-SENSITIVE: not decisive" (§4, §6; `edge_vc.with_sensitivities`). Items 2-3 are disclosed with
  their counts per window and component (§1, §2, §7).
- **D3, lead decision 2026-10-04 (review item 4, dataset).** The 5m XAUUSD / XAGUSD history is pinned: its digests are in the
  dry run's meta, in §7 (`dataset-sha256` lines) and in the ledger entry; the gold read refuses on any difference
  (`edge_vc.require_dataset`) and records `real_costs.price_ref_info` (the closes' sha256) in its meta.
- **D4, lead decision 2026-10-04 (review items 5-9).** The dry run was re-run after the code changes, outcome-blind and
  traced (§7, with the old and new counts); its git_head is disclosed (§7); F4 G5 NR7 is a disclosed prior beside F3 H5
  (§1); the sealed text's own paragraph names its four changes (§10); the read refuses when `sys.pycache_prefix` is set
  (§11).

**Lead decisions 2026-10-05** (on the open items of the seal preparation's fix round):
- **(1) T1a and regime blocks: option C, lead decision 2026-10-05.** T1a passes only if its day-clustered rule passes (Holm
  m = 2 and the gate of §4) AND the same contrast with the VR runs as clusters (`T1a_run_clustered`) has one-sided
  p <= 0.05; a run-clustered test that cannot be computed fails T1a (`edge_vc.t1_verdict`). The power cost is accepted:
  with no block effect, T1a's power at an equal 0.20 R_bar effect is 82.1 % instead of 88.0 %
  (§7, `vc-regime-sim.json`). A regime-level effect, one that window B's 8 runs cannot tell from regime noise, is for TF
  to confirm. T1b and TF are unchanged (§4).
- **(2) Dense threshold, lead decision 2026-10-05.** The whole-history rule stays decisive; the causal rule is a
  sensitivity (§1, §4).
- **(3) The paper log's refusals, lead decision 2026-10-05.** Report-only: the block without them stays (§2, §6); the
  decisive rows keep every trade.
- **(4) The fix round's additions, lead decision 2026-10-05.** All four are kept: the causal-density sensitivity (§1), the
  run-clustered T1a companion (now part of T1a's pass rule, (1)), the report-only block without the paper log's refusals
  (§2), and the evidence files (the allowlist probe, its trace, the regime simulation; §7), with the report-only guard
  `_guarded`.
- **(5) Earlier recommendations, lead decision 2026-10-05.** They stand: the dry-run JSON is committed with its evidence
  (`docs/experiments/vc-p1-dryrun/`, §10 step 5); the ledger gets the study entry plus a `hypothesis_refinement` record on
  the two `oos_exposed` periods (§5.4); VC-X's CX field contract is a refusal condition (§5.3); the manifest coupling is
  accepted: VC-G runs right after the seal, and an edit to a manifest file before the forward or crypto read means a
  re-seal by amendment (§10 step 6).

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

- **(a) HIGH volatility day.** sigma_5m(D) > the median of sigma_5m over the previous 250 DENSE days that have one, given at
  least 125 of them. This is F3 H5's own regime rule (scripts/research/edge_f3.py:30, :99-116), as known at the start of
  day D. sigma_5m(D) is the RMS of 5m log returns over the previous 20 dense days (scripts/research/edge_census.py:131-146),
  defined on every day (point in time, D2). VR = sigma / that median (`edge_vc.pit_vr_by_day`). No VR -> excluded and
  counted.
  - **Earlier uses of a volatility condition on gold (priors, disclosed).**
    1. F3 H5 kept E5's FVG retrace events only on this rule's HIGH days (by the signal day;
       scripts/research/edge_f3.py:99-116), gold 2005-2016, and tested their excess over a placebo: discovery p 0.0107, not
       BH-rejected; confirmation p 0.115 (docs/audits/2026-10-02-edge-f3.md:55). That is another detector and no
       HIGH-versus-LOW contrast.
    2. F4 G5 NR7 (lead decision 2026-10-04, D4) traded XAUUSD breakouts of the previous dense day's range only when that
       range was the narrowest of the last 7 dense days (scripts/research/edge_f4.py:135-154): discovery (2004-06 ->
       2016-11, which holds window B) n 374, p 0.0000, BH-rejected, +34.7 bp; confirmation n 264, p 0.0001; it failed the
       exposed read, n 98, p 0.28 (docs/audits/2026-10-02-edge-f4.md:73). That is a low-range condition on another
       detector, and no split of H7 / G9.
    No VR split of H7 / G9 was ever computed, so window B stays UNREAD-FOR-H for VC (§3).
  - Gold / silver: the point-in-time series (`edge_census.Series(..., sigma_every_day=True)`, as the paper log builds it,
    scripts/research/fvg_forward.py `_series`).
  - **The same-day completeness selection is gone (D2; review item 3).** In research mode a day has a sigma only if the
    whole day turns out dense (scripts/research/edge_census.py:121-124; the dense threshold is 0.8 x the median bars per day
    of the loaded history, :104-107), and F3's MOM20 too (scripts/research/edge_f3.py:48-54), so book_sim drops a signal on
    a day that later proves sparse. The decisive rows do not. The dry run counts what research mode would drop, by entry
    bar and side (`research_mode.only_point_in_time`; none appears in research mode alone):

    | window | H7 XAUUSD | G9 XAUUSD | G9 XAGUSD |
    |---|---|---|---|
    | B (to 2008-12-09) | 39 of 354 (11.0 %) | 59 of 544 (10.8 %) | 0 of 0 |
    | 2008-12-10 -> 2017-12-31 | 11 of 1,014 (1.1 %) | 13 of 1,502 (0.9 %) | 13 of 1,492 (0.9 %) |
    | 2018 onwards (not counted here) | ~5 | ~6 | ~8 |

    The last row is the full-history count of docs/audits/2026-10-04-density-selection-check.md (+55 H7, +78 G9, +21 G9
    silver) minus window A's. The earlier draft cited that check's full-history bound (mean R moves <= 0.002 R); it does
    not hold for window B, where the selection is ten times as dense. It also said "H7 never loses one": H7 loses its
    events earlier, in the detector, so research mode's `no_research_sigma` shows 0 for H7 and 75 for G9 (59 of them this
    selection, 16 the history's first 20 dense days, which have no sigma in either mode). The pooled mean R of the extra
    trades over the full history was read once by that check (+0.130 H7, +0.034 G9 at k = 1.4), not split by VR or entry
    time.
  - **Not point in time: the dense threshold (disclosed; second review of the fix, item 3).** Whether a day is dense uses
    the median bars per day of the WHOLE stored history (edge_census.py:104-107: 0.8 x 273 = 218.4 bars), in research, in
    this read and in the paper log alike. The early gold feed has fewer bars a day, so a 2004-2006 day is often "sparse"
    against the 2010s: dense days by year, whole-history rule -> a causal rule (the median of the days before each day):
    2004 39 % -> 67 %, 2005 39 % -> 88 %, 2006 70 % -> 94 %, 2007 94 % -> 98 %, 2008 98 % -> 99 %; window B 812 of 1,143
    days (71 %) -> 1,043 (91 %) (dry run `causal_density.XAUUSD_dense_days`). A day that is not dense has no sigma, so the
    sigma history, the VR and the events of the decisive window depend on the later years. The dependence is on bar counts,
    not on prices or outcomes, and the dataset digest pins it (D3). Under the causal rule window B would hold 1,053 trades
    with a VR (H7 432, G9 621; +38 %), 64 % of them HIGH instead of 72 %, and the VR would start 2005-03-21 instead of
    2005-12-13 (dry run `causal_density`). **Why the whole-history rule stays decisive:** it is the rule of the book, the
    paper log and every earlier read, so window B and TF share a definition (TF's era has no sparse days: 99-100 % dense
    from 2018); the causal rows are a pre-registered REPORT-ONLY sensitivity of the same read (`causal_density_report_only`,
    `edge_vc.causal_density`: it overrides `Series` attributes and rebuilds the sigma history with `Series._vol_by_day`,
    no frozen edit), and a different T1 verdict makes the read DATA-SENSITIVE: not decisive (§4). The decisive rows are
    therefore "point in time except the dense threshold", not "point in time".
  - Crypto: the [CX-P1] point-in-time sigma of each eligible day (scripts/research/pit_trend.py `context`).
- **(b) LONG HOLD (early entry).** The trade's entry server-clock slot (minutes from server midnight of the entry bar) is
  EARLIER than the median entry slot of the same component's VC-G trades in the decisive window. The FTMO server day ends at
  a fixed clock time (New York + 7 h), so an earlier slot means more bars to the end of the day. The slot is entry timing,
  known at entry.
  - The medians are computed ONCE, in the VC-G read, on window B, and recorded in its JSON (`hold_medians`). The
    report-only window, the forward read and any filter use those recorded constants, never a median of their own rows. A
    component without a recorded median (silver: no window-B trade with a VR) has no hold split. The outcome-blind dry run
    reports the medians first: H7 637.5, G9 875 server minutes (10:37:30, 14:35), over the same trades the read uses, so
    the read's `hold_medians` must equal them.
- Each trade's day is its ENTRY server day (the rows carry no signal day). VR uses only earlier days: point in time.
- **Signals on a server day's last bar (review item 21).** H7 / G9 enter at the bar after the signal. A signal on a day's
  last bar would enter at the next server day's first bar. The paper log drops it ("no same-day trade",
  scripts/research/fvg_forward.py `signals`), and so do the decisive rows (`edge_vc.pit_events`); research mode keeps it
  (book_sim, report-only). **Measured at the seal:** no gold signal on a day's last bar in either window; one silver signal
  in window A (`last_bar_signal`).

## 2. Outcome per trade

- **The paper log's trade geometry, on the stored bars (point in time; D2).** Entry at the open of the bar after the
  signal. The protective stop is k x sigma_5m(signal day) x sqrt(nb) x price, with nb = the 5m bars from the entry to
  the server rollover ON THE CLOCK (`edge_vc.bars_to_day_end`, the arithmetic of scripts/research/fvg_forward.py
  `bars_to_day_end`): what the live executor knows at entry (fvg_forward.py `signals`). The exit walk is book_sim's
  (scripts/research/book_sim.py:64-74), as `fvg_forward.resolve_row` implements it with that stop (`edge_vc.pit_trade`):
  the stop when a bar reaches it (filled at the stop, or at the open beyond it), else the close of the day's last stored
  bar. Cost: the relative spread round trip of edge_census.Costs at the read's cost profile.
- **k = 1.4**, the stop of fvg-book v4 now on the demo (docs/architecture/trading-systems.json:272-273). k = 2.0 (v3) is
  report-only (with the k = 1.4 hold medians).
- **The stored-bar count it replaces (review item 2, disclosed).** book_sim sized the stop on the bars from the entry to the
  day's last STORED bar (scripts/research/book_sim.py:52, :59). That count is not known at entry: it shrinks when bars are
  missing later in the day. In window B it is short of the clock count by 13 bars on average (141.2 against 128.0); 34 % of
  the trades are short by more than 12 bars; 81 % have missing bars between the entry and the day's last stored bar, 95 % on
  LOW days against 76 % on HIGH days. The gold session closes 1-2 bars before the rollover, so every stored day ends at
  least one bar early; 62 % of window B's entry days stop earlier than that. Window A, as a whole: 7 bars (182.0 against
  175.0), 12 % short by more than 12, 29 % with holes. Per component and half: §7 and the dry run's `nb_clock_vs_stored`.
  - What remains, outcome side: where stored bars are missing, the walk sees fewer bars (a stop reached inside a hole fills
    at the next stored bar's open or worse), and a day whose stored data stops early exits at its last stored bar, earlier
    than the live executor would. Both are data limits of the history, not look-ahead: no entry, stop or label uses them.
  - **Not applied: the paper log's data-quality refusals (second review of the fix, item 2).** The paper log refuses a
    signal when a data hole (a gap of 24 h or more that is not a weekend or holiday) lies in the 35 days before it, or
    fewer than 20 dense days lie in the 40 before it (fvg_forward.py `signals`, `holes`, `_vol_fresh`). The decisive rows
    keep those trades: the research book never applied the rules, and TF keeps only closed rows, so the two populations
    differ here. Counted outcome-blind with the paper log's own functions over every hole of the history (the paper log
    looks only since its forward start; `edge_vc.paper_log_refusals`): of window B's 762 gold trades 188 (24.7 %) would
    have been refused, 108 for a hole and 80 for stale volatility history (H7 75: 43 + 32; G9 113: 65 + 48), HIGH 146 of
    545 (26.8 %) and LOW 42 of 217 (19.4 %), long hold 89 of 378 and short hold 99 of 384 (dry run `refusable`). Window A:
    555 of 3,278 gold trades (16.9 %), 142 of 1,404 silver. The read repeats every test without them, report-only
    (`excluding_paper_log_refusals_report_only`). The stops and entries of the trades the paper log accepts equal the
    decisive rows' (test `test_the_paper_logs_signals_agree_with_pit_events_stops_and_refusals`).
- **R_gross** = side x (exit - entry) / stop distance. R_net = R_gross - cost / stop distance.
  Why gross: cost per unit of stop falls mechanically as the stop widens, so a NET gradient is partly guaranteed by
  arithmetic. The tradability gate uses R_net (§4).
  - The forward read re-prices R_net from each paper row's logged entry and exit (times and prices) at the cost profile the
    read records, with fvg_forward.resolve_row's formula. The log's own R was priced when the row resolved, and no profile
    was recorded then; it is kept as `R_net_log`, and the read counts the rows where the two differ.
- **R_bar** = R_gross x sqrt(144 / planned bars), the statistic of T1b, and of T1a since the sealing amendment (§4). The
  planned bars are nb, the stop's own horizon on the clock, in window B as in the paper log (`bars_to_day_end`): window B
  and TF now use the same quantity. 144 (half a 288-bar day) only sets the unit, "R at a 144-bar hold"; the p-value does not
  depend on it.
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
| **VC-G gold holdout** | the point-in-time rows of H7_XAUUSD_eod, G9_XAUUSD_eod, G9_XAGUSD_eod (§1-§2) by entry server day: window B decisive, window A report-only (below) | window B UNREAD-FOR-H. Label of a pass: "DISCOVERY-GRADE for the condition (components exposed)"; TF is its confirmation | T1a, T1b, T2 |
| **VC-X crypto** | FTMO crypto CFDs: CX group A members over their whole history, CX group B members from 2024-03-01 only ([CX-P1] §3: H7x read B's underlying through 2024-02-29; lead decision 2026-10-04), to the CX amendment's end date; H7 / G9 by pit_trend ([CX-P1] §1: min_bars 230, calendar previous day); CX costs | UNREAD-FOR-H at read time (the CX reads come first, §5). Windows CX retired unread after a failed gate are read here: disclosed and logged (§5.4) | T3 |
| **VC-F forward** | the paper log's H7 / G9 XAUUSD rows at stop_k 1.4 (scripts/research/fvg_forward.py:36-38) entering on a server day after the server day of the seal commit (git: `prereg_guard.first_forward_day`; no date is typed). The xau-holdout JSON it uses is checked: its read name, commit state, tag, read and window (`prereg_guard.require_read_json`, `edge_vc.xau_primary`) | FRESH | TF |

**The VC-G windows -- lead decision 2026-10-04** (`edge_vc.HOLDOUT = "B"`, `REPORT_WINDOW = "A"`):

- **B (DECISIVE):** gold entries before **2008-12-10** (2004-06 -> 2008-12-09). No personal-account replay touched it.
  Grade: UNREAD-FOR-H. Gold has a VR from 2005-12-13 (20 dense days for a sigma, then 125 dense days of sigma history;
  2004-05 has few dense days), so the split runs on 2005-12-13 -> 2008-12-09. The sealing dry run counts 762 trades with a
  VR: H7 302, G9 460 (§7).
  - "Decisive" means its verdict, not window A's, counts. Under the grades of research-directions §0, UNREAD-FOR-H data is
    valid as discovery: H7 / G9 were selected on these years, only this split was never computed. A pass here is therefore
    DISCOVERY-GRADE for the condition. TF on forward data is its confirmation.
  - Silver's 5m history starts 2008-11-07, so no silver trade has a VR before 2008-12-10: T2 is "not run (window)" and
    enters its Holm family with p = 1. The dry run confirms it: 0 silver trades with a VR (its 11 events before
    2008-12-10 have no sigma yet).
- **A (report-only):** entries before **2018-01-01** -- gold from 2004-06, silver from 2008-11 -- tested exactly as B, with
  B's hold medians. Dry run: 3,278 gold trades with a VR (H7 1,316, G9 1,962), 1,404 silver.
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
(same | short trades)], with y = R_bar for T1a and T1b (nb-weighted means, §2; T1a since the sealing amendment, below) and
y = R_gross for T2, T3.

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
- **T1a's statistic: the switch fired at the seal.** The rule was fixed before any count was seen: T1a keeps R_gross (it
  splits by volatility, not by bars) unless, in window B's dry-run counts, the pooled gold mean planned bars of the HIGH
  and LOW halves differ by more than 10 % of the smaller (`xau_pooled.decisive.vr_halves_bars_gap` > 0.10,
  `edge_vc.power_inputs`; §10.3). The sealing dry run measured HIGH 145.7 bars, LOW 130.1 on the clock count: a gap of
  0.120 (§7; the first dry run, on the stored count, measured 0.149, so the switch fires on either count). HIGH days enter
  earlier, so a per-bar edge equal on both halves would give HIGH more R. **T1a therefore uses T1b's statistic: R_bar with
  nb-weighted cell means** (`edge_vc.T1A_VALUE`, `T1A_WEIGHT`; synthetic check `test_a_timing_gap_does_not_pass_t1a`). The
  two extra gate conditions of T1a use it too (the components' differences). The R_gross T1a is report-only
  (`T1a_raw_R_report_only`). T2 and T3 keep R_gross: the rule names T1a only.
- **Variance.** CR1 cluster-robust by server day for the contrast as a whole (each day's summed influence across the four
  side x half cells; in a weighted cell a trade's influence is nb x (y - cell mean) / the cell's total nb). One cluster per
  day, so it stays valid when the halves share days: crypto symbols pooled on one
  server day (the probe found shared days), and an H7 and a G9 trade of one gold day in different T1b halves. Gold T1a and
  T2 never share a day across halves (one VR per day per symbol). The shared-day count is reported.
- Student-t with min(days in each of the four cells) - 1 df; one-sided (True > False). A test with an empty cell is not
  computable and enters its family with p = 1.
- **Regime blocks: T1a's halves are 8 runs (second review of the fix, item 1).** The VR is a 20-day sigma over a 250-day
  median, so its label persists: window B's 764 days with a VR form 8 runs of consecutive days with one label, 4 HIGH (10,
  131, 170 and 216 days) and 4 LOW (4, 12, 82 and 139 days) (dry run `regime_blocks`), and the halves are close to
  calendar years: the share of HIGH trades is 0 % in 2005 (0 of 9), 87 % in 2006 (186 of 215), 33 % in 2007 (85 of 260)
  and 99 % in 2008 (274 of 278), and 36 % of the trades are in 2008. The by-day CR1 SE counts days as independent
  clusters. If mean R_bar differs between years or regimes by more than the noise, T1a's contrast carries an error the
  by-day SE does not see. A synthetic check on this very layout (§7, `vc-regime-sim.json`) gives the by-day T1a a
  first-Holm-step false-positive rate of 5.2 % instead of 2.5 % when each year's mean R_bar has an sd of 0.05 R,
  and 10.0 % at 0.10 R; T1b stays at 2.1-2.9 % (its halves are intraday entry slots spread over every day).
  **What the pre-registration does (lead decision 2026-10-05, option C):** T1a passes only if the by-day rule of this
  section passes AND the same contrast with the VR runs as clusters (`T1a_run_clustered`: CR1 by run, Student-t with
  min(runs per side x half cell) - 1 df, 3 in window B) has one-sided p <= 0.05 (`edge_vc.t1_verdict`; the threshold is
  ALPHA_T1, not the Holm step). A run-clustered test that cannot be computed fails T1a. On this layout (§7) the rule's
  false-positive rate is 3.9 % / 6.5 % at a year effect of sd 0.05 / 0.10 R_bar (by day alone: 5.2 % / 10.0 %),
  and its power at a true 0.20 effect 82.1 % without a block effect (by day alone 88.0 %). With 8
  clusters the run-clustered SE is itself unreliable, so the rule narrows the regime problem without removing it. A by-day
  T1a pass the runs do not support is NOT SHOWN (the reading names it). Whether a T1a pass is a property of the VR
  condition or of the regimes window B happens to contain is for TF to confirm (lead decision 2026-10-05). TF's T1a has
  the same exposure: its rows (150, or the first 365 days) span only as many VR runs as that period holds, far fewer than
  rows (window B: 8 runs in 764 days, one per ~95 days; window A: 95 runs in 3,101 days, one per ~33). The limit is much
  smaller in window A.
- **Sensitivities and DATA-SENSITIVE (lead decision D2).** The same read computes, report-only, the T1 verdict on (i) the
  inherited research-mode rows and (ii) the causal-density rows (§1). If either gives another T1a / T1b verdict than the
  decisive rows, the reading adds "DATA-SENSITIVE: not decisive" (`edge_vc.with_sensitivities`). Which sub-tests passed and
  the forward read's scheduling do not change: the label says that the verdict depends on the data definition. A
  sensitivity that cannot be computed is named in the reading (SENSITIVITY UNAVAILABLE) and its failure sits in the JSON.

| test | data | condition | gate |
|---|---|---|---|
| T1a | VC-G window B, H7 + G9 XAUUSD pooled | (a), y = R_bar, nb-weighted cell means (the sealing amendment's switch) | Holm m = 2 over {T1a, T1b}, alpha 0.05; AND True-half mean R_net > 0; AND the balanced difference > 0 in BOTH gold components (on the same weighted R_bar); AND the same contrast with the VR runs as clusters at one-sided p <= 0.05 (option C, lead decision 2026-10-05) |
| T1b | VC-G window B, H7 + G9 XAUUSD pooled | (b), y = R_bar, nb-weighted cell means | same Holm; same two extra conditions (the components' differences on the weighted R_bar) |
| T2 | VC-G window B, G9 XAGUSD | (a) | Holm m = 2 over {T2, T3}, alpha 0.05 (secondary). Not run in window B: p = 1 |
| T3 | VC-X, crypto pooled | (a) | same secondary Holm; a test not run enters with p = 1 (with T2 at p = 1, T3 needs p <= 0.025) |
| TF | VC-F forward | only the T1 sub-test(s) that passed, on the same y | Holm over those at alpha 0.10; AND True-half mean R_net > 0 |

- T1 is the decision test for the gold book. T2 / T3 inform the mechanism; they never adopt a filter.
- **Reading of T1 (D1).** A pass: "PASS: DISCOVERY-GRADE for the condition; TF on forward data is its confirmation". No
  pass: "NOT SHOWN (inconclusive for a G9-concentrated effect)", never "lead closed" (`edge_vc.t1_verdict` `reading`; §7's
  full-rule power). A T1a whose by-day rule passed but whose run-clustered test did not (p > 0.05, or not computable) does
  not pass, and the reading says so (option C, lead decision 2026-10-05); the JSON keeps both (`T1a_by_day`,
  `T1a_run_clustered_p`). Either reading may end with "DATA-SENSITIVE: not decisive".
- The forward read runs once, at >= 150 closed rows or 365 days after the seal, whichever comes first, counting only rows
  that enter after the seal commit's server day. It is scheduled only if T1a or T1b passed. TF's (b) uses the VC-G
  `hold_medians`.
- Window A (report-only) never changes a verdict. Nor do the report-only blocks of §6, except the DATA-SENSITIVE label.
- Zero passes is a valid result.

## 5. Ordering constraints

1. VC-G may run right after sealing.
2. **VC-X runs only after every scheduled CX read is done.** A VC-X read computes both halves, which implies the pooled
   H7 / G9 mean on CX's windows: run earlier, it would expose them. The code checks the committed CX files, not just
   their existence (`edge_vc.cx_closure`): the screening amendment carries the tag, the end date and the members per
   group; every group-A read up to the first one where no test advanced, and the group-B read, must be present with the
   CX tag. Symbols and the end date come from the amendment, never from the command line.
3. VC-X uses pit_trend.py, written to [CX-P1] §1. `scripts/research/edge_cx.py` does not exist at the seal (checked
   2026-10-04), so nothing can be reconciled now. The contract is `cx_closure`'s, fixed here: amendment `tag`, `end`,
   `members.A/B`; read `meta.tag/group/read`, `verdicts.<test>.advances`. If CX's committed files differ, or edge_cx
   defines H7 / G9 differently from pit_trend, the VC-X read refuses or must not run. VC-X then waits for an amendment
   of this text and of the code (new manifest; the guard refuses every read until it is re-sealed). VC-G and VC-F do
   not depend on CX.
4. Ledger entries, committed with the seal (the read refuses without the study entry, `edge_vc.require_ledger`, and the gold
   read without its `dataset` digests, `edge_vc.require_dataset`). The exact entries are the seal's ledger file (§10 step
   5). None changes a period's state, and none declares an untouched period:
   - a study entry `vc_volatility_condition` (this file, the tag, the tests, the windows and their grades for VC, the
     dry run's file and sha256, the sha256 of its evidence files (probe, trace, regime simulation), the dataset digests of
     §7, the full-rule power of §7, the report-only sensitivities and the reading rules of §4);
   - gold / silver 2018-01-01 -> 2026-10-02: EXPOSED for VC (trigger `hypothesis_refinement`). The ledger's two
     `oos_exposed` periods there (2024-03-01 -> 2026-09-28) get an exposure record; its development part (before
     2024-03-01) cannot become exposed (scripts/research_ledger.py:201-204) and is recorded in the study entry;
   - window B (gold 2004-06 -> 2008-12-09) as development data read once for this condition;
   - window A's remainder (2008-12-10 -> 2017-12-31): read report-only for this condition, already partly exposed through
     all personal-account replays;
   - after VC-X: the CX windows it read that CX had retired unread (the read JSON lists them, `retired_windows_read`)
     become exposed for H7 / G9 on crypto (trigger `hypothesis_refinement`).

## 6. Report-only diagnostics (outside the family)

- Window A: every test, with window B's hold medians, and its counts.
- **The research-mode rows (D2):** the same tests on the inherited book_sim rows (research-mode sigma, the stored-bar count,
  last-bar signals entered on the next day), with window B's hold medians (`research_mode_report_only`). It links the read
  to the construction of the 2018+ finding. It never changes a verdict.
- **The causal-density rows (D2):** the same tests on the rows built with the causal dense-day rule
  (`causal_density_report_only`, §1), with window B's hold medians.
- **Without the paper log's refusals:** every test on window B's trades without the 188 the paper log would have refused
  (`excluding_paper_log_refusals_report_only`, §2).
- **T1a with the VR runs as clusters in window A** (`report_only_window_A.T1a_run_clustered`). In window B it is part of
  T1a's pass rule (`T1a_run_clustered`, §4; option C, lead decision 2026-10-05), not a diagnostic.
- The literal finding on the holdout: mean R_gross and R_net by stop-width quartile (cut points from the holdout's own
  stop_bp, a timing-and-volatility quantity).
- The R_gross T1a and T1b (`T1a_raw_R_report_only`, `T1b_raw_R_report_only`), and the pooled (unbalanced) difference and
  per side x half cells of every test.
- Mean planned bars in each half of every test.
- The 2 x 2 of (a) x (b): which one carries the gradient.
- Long and short separately (drift check), and per year.
- k = 2.0 rerun of everything (the k = 1.4 hold medians).
- Counts per window: trades with and without a VR, last-bar signals dropped, shared days per test.

## 7. Power and prior (sealing amendment: the dry run's counts; arithmetic, before any read)

**The sealing dry run (§10 step 3, 2026-10-04).** `python3 scripts/research/edge_vc.py dry-run` on the stored history, at
the code this text seals:
JSON sha256 `0d003b4ab0f22156ef9b85d71fd64935639b74a3014658553df90676e69c8fac`.
Its `meta.code_sha256` equals §11's manifest. It counts the decisive rows' events (`edge_vc.pit_events`), the events the
paper log would refuse (`paper_log_refusals`), research mode's events (`research_events`) and the causal-density sample, and
does the power arithmetic. It computes no exit, cost or R, and a trace shows it: a sys.monitoring hook recorded every
repository code object that started during the
run (127: 105 functions, 22 module or class bodies). The probe checks each against an ALLOWLIST.
Not on it, so none could start:
`edge_vc.pit_trade` and `pit_holdout_rows` (the walk); every function of `fvg_forward.py` but `holes`, `_dt` and
`_vol_fresh` (`resolve_row` is the walk's engine); `book_sim.trades`, `edge_census.Costs`, `outcome` and `t_sf`; the
real_costs pricing functions; edge_vc's R and test functions (`split_test`, `per_bar`, `diagnostics`). The probe also
allows only the configuration files and the 5m XAUUSD / XAGUSD history to be opened: no cost table, 15m history
(price_ref) or paper-log file was. **What this proves:** that no function outside the allowlist ran, and nothing outside
the allowed files was opened. The allowlisted functions were read by a reviewer (none walks an exit, prices a cost or
computes an R) and the unit test `test_the_dry_run_never_walks_a_trade` checks the same with every outcome function replaced
by a tripwire; a name probe cannot show that an allowlisted function holds no inline walk.
- **Evidence committed with the dry run (seal commit B, §10 step 5)**, `docs/experiments/vc-p1-dryrun/`:
  `edge-vc-dryrun.json` (the dry run), `vc_dryrun_probe.py` and `vc-dryrun-trace.json` (the probe and the trace it
  wrote: every code object that started, every file opened, the allowlist), `vc_regime_sim.py` and `vc-regime-sim.json`
  (§4's synthetic check). Their sha256 are in the ledger entry (§5.4). The two scripts run from the repository as
  committed.
- **Its git_head (review item 6).** The dry run ran on the working tree: its `meta.git_head` (6887d5f) does not hold
  `edge_vc.py` or its test, which `meta.code_uncommitted` lists. `meta.code_sha256` pins the code and equals §11's
  manifest. A re-run from the committed code (§10 step 2) must give identical `counts` and `dataset`.
- **The dataset (D3).** The stored history the dry run counted, and the gold read must load (`edge_vc.require_dataset`;
  history_store digests over every file of each series):

```
dataset-sha256 120866d22e351b68f1fe468b7d13d44f8bb1ce0e7f772307e47fffcd9bc5fb52 XAGUSD|5m
dataset-sha256 aab48876789b946e2b1a2176b0fe09c85be1505004285c1a54880b6ac2b55180 XAUUSD|5m
```

- **Not pinned (disclosed).** The cost spec and the 15m series that fixes `price_ref` are recorded in the read's meta
  (`cost_profile`: the spec's sha256 and `real_costs.price_ref_info`, the closes' sha256), not refused on. Gold's round trip
  is ~0.65 bp against a stop of ~100 bp (§0), about 0.006 R: another table could move a net mean by less than that. The
  dry run does not open them (it prices nothing).

- **The first dry run and this one (D4).** The first (sha256 `5874ae59...`, research-mode events, stored-bar counts) and the
  sealing dry run (point in time, clock counts), window B, gold:

  | count | first dry run | sealing dry run | why |
  |---|---|---|---|
  | trades with a VR | 710 (H7 279, G9 431) | 762 (H7 302, G9 460) | the events research mode drops on days that later prove sparse (§1): 52 of the 98 have a VR |
  | without a VR | 90 (36 / 54) | 136 (52 / 84) | the other 46 fall before 2005-12-13, the first day with a VR |
  | dropped, no sigma | G9 75 | G9 16 | 59 of the 75 were that selection; 16 are the history's first 20 dense days |
  | HIGH / LOW | 511 / 199 | 545 / 217 | |
  | median entry slot | H7 630, G9 875 | H7 637.5, G9 875 | the added H7 events |
  | planned bars q10 / q25 / q50 / q75 / q90 | 60 / 87 / 114 / 170 / 233 | 73 / 97 / 122 / 179 / 254 | the clock count is the larger (§2) |
  | HIGH-LOW bars gap | 0.149 | 0.120 | both above 0.10: the switch stands |
  | MDE T1a / T1b (same-day bound) | 0.19 / 0.18 (0.23 / 0.21) | 0.18 / 0.16 (0.21 / 0.19) | more trades, larger weights |

- Per-trade sd of R at k = 1.4 ~0.75 (docs/audits/2026-10-03-vol-schedule.md:29). MDE = 2.80 x 0.75 x `se_per_sd`
  (80 % power, one-sided alpha 0.025: the first Holm step).
- Two SEs per test (`edge_vc.power_inputs`): trades independent (`se_per_sd`), and in brackets the trades of one server day
  in one cell moving together (`se_per_sd_same_day`: an H7 and a G9 trade of one gold day, same side and half). The read's
  CR1 SE is the real one; within cells the two bracket it.
- **Window B (decisive), gold, H7 + G9 pooled:**

  | count | value |
  |---|---|
  | trades with a VR | 762: H7 302, G9 460 |
  | excluded, no VR yet | 136: H7 52, G9 84 |
  | dropped: no sigma / a signal on the day's last bar | G9 16, H7 0 / 0 (§1) |
  | research mode would drop (the same-day selection) | H7 39 of 354, G9 59 of 544 (§1) |
  | the paper log would refuse (§2) | 188 (24.7 %): hole 108, stale volatility 80; HIGH 146 of 545, LOW 42 of 217 |
  | causal-density sample (§1, a sensitivity) | 1,053 with a VR: H7 432, G9 621; 64 % HIGH; VR from 2005-03-21 |
  | HIGH / LOW | 545 / 217 (72 % HIGH) |
  | VR runs (regime blocks, §4) | 8: 4 HIGH (10, 131, 170 and 216 days), 4 LOW (4, 12, 82 and 139 days); HIGH share by year 0 / 87 / 33 / 99 % (2005-2008); 36 % of the trades in 2008 |
  | long / short | 410 / 352 |
  | median entry slot, server clock (the (b) cut) | H7 637.5 (10:37:30), G9 875 (14:35) |
  | planned bars (clock) q10 / q25 / q50 / q75 / q90 | 73 / 97 / 122 / 179 / 254; 6 entries under 24 bars |
  | mean planned bars | HIGH 145.7, LOW 130.1 (gap 0.120 > 0.10: T1a switched, §4); long hold 190.2, short hold 93.0 |
  | clock against stored bars (review item 2) | mean 141.2 against 128.0; short by > 12 bars 34 % (HIGH 29 %, LOW 48 %); holes after the entry 81 % (HIGH 76 %, LOW 95 %); day stops > 2 bars early 62 %. H7 164.1 against 149.4, holes 80 %; G9 126.2 against 113.9, holes 82 % |

  Trades / server days / planned bars per side x half:

  | half | long | short |
  |---|---|---|
  | HIGH | 286 / 206 / 43,146 | 259 / 196 / 36,235 |
  | LOW | 124 / 85 / 16,545 | 93 / 78 / 11,683 |
  | long hold | 207 / 168 / 40,733 | 171 / 147 / 31,145 |
  | short hold | 203 / 161 / 18,958 | 181 / 152 / 16,773 |

  Student-t df: T1a 77 (the fewest days in a cell: 78, short LOW), T1b 146.

  **The pooled test alone** (MDE; power from `rule_power` `pooled_alone`):

  | test | y | se / sd(R) | MDE (R) | power at 0.10 R | power at 0.20 R |
  |---|---|---|---|---|---|
  | **T1a** | nb-weighted R_bar | 0.084 [0.101] | **0.18** [0.21] | 0.34 [0.25] | 0.88 [0.73] |
  | **T1b** | nb-weighted R_bar | 0.078 [0.091] | **0.16** [0.19] | 0.40 [0.31] | 0.93 [0.84] |
  | T1a on R_gross (report-only) | R_gross | 0.081 [0.098] | 0.17 [0.21] | | |
  | T1b on R_gross (report-only) | R_gross | 0.073 [0.084] | 0.15 [0.18] | | |

  These treat days (or, in brackets, an H7 and a G9 trade of one day) as the independent units. **For T1a they are
  optimistic: its halves are 8 regime blocks (§4).** The table after the full pass rule gives its size and power when each
  year's or each run's mean R_bar varies.

  **The full pass rule (D1; review item 1).** A sub-test passes only if Holm rejects AND the balanced difference is > 0 in
  BOTH gold components (and the True half's net R > 0, taken as met here); T1a also needs its run-clustered p <= 0.05
  (option C, lead decision 2026-10-05). The by-day columns: by simulation from the cell counts above
  (`edge_vc.rule_power`: each component's cell means normal with sd 0.75 x sqrt(144 / bars); the other sub-test null;
  20,000 draws, seed 7; in brackets the same-day bound). The option-C column: the regime simulation below on window B's
  real layout (`vc-regime-sim.json` `full_rule`; trades independent, no block effect, 2,000 replications, the first
  Holm step); its own by-day figures, 0.87 / 0.35 / 0.46 / 0.35, agree with `rule_power`'s within Monte Carlo
  error; the same-day bound is not simulated for option C. For an effect in R at a 144-bar hold, as each component's
  half-split difference:

  | effect (H7 / G9) | T1a full rule, by day | T1a full rule, option C | T1b full rule |
  |---|---|---|---|
  | equal, 0.20 / 0.20 | 0.87 [0.74] | 0.81 | 0.92 [0.84] |
  | equal, 0.10 / 0.10 | 0.33 [0.25] | 0.30 | 0.39 [0.31] |
  | the 2018+ table's shape, 0.04 / 0.21 | 0.47 [0.40] | 0.41 | 0.52 [0.46] |
  | G9 only, 0 / 0.21 | 0.33 [0.30] | 0.32 | 0.37 [0.34] |

  - **What a T1 fail means.** Window B finds an equal effect of >= 0.2 R in both components with power ~0.8 (0.74-0.92).
    The 2018+ table implies an effect concentrated in G9 (its half split: G9 ~0.21, H7 ~0.04); window B finds that shape
    with power ~0.4-0.5 for the full rule (the pooled test alone: 0.43-0.62) and a G9-only effect with ~0.3-0.4. The
    both-components gate costs about 0.1 of it (independent days: T1a 0.57 -> 0.47, T1b 0.62 -> 0.52); the rest is the
    pooled test's own limit. T1a's run condition (option C, lead decision 2026-10-05) lowers its column further, to
    0.81 / 0.30 / 0.41 / 0.32 for the table's four effects (trades independent; by day in the same
    simulation 0.87 / 0.35 / 0.46 / 0.35), inside the ranges above. A T1 fail therefore reads **"NOT SHOWN (inconclusive
    for a G9-concentrated effect)"**, never "lead closed" (§9).
  - **The shapes are upper bounds.** The 2018+ table is a gradient by stop width, which mixes the volatility and the
    entry-time factors (§0). Each factor alone is smaller than the combined half-split difference, so the powers for "the
    2018+ shape" and "G9 only" are upper bounds for a single-factor effect of the size the table suggests.
  - R_bar's MDEs are in R at a 144-bar hold. At window B's mean planned bars (141) the same per-bar edge is ~0.99 of that
    in R per trade.
  - The review of the seal preparation (2026-10-04) estimated the same rule on the first dry run's cells, independence
    assumed: T1a / T1b 0.80 / 0.87 (equal 0.20), 0.42 / 0.47 (the 2018+ shape).

  **T1a and T1b under a block effect (§4; second review of the fix, item 1).** Synthetic outcomes on window B's real layout
  (762 trades, 8 VR runs; `docs/experiments/vc-p1-dryrun/vc_regime_sim.py`, result `vc-regime-sim.json`; no market outcome is
  read): R_bar noise of sd 0.75 x sqrt(144 / nb), a block effect of the sd shown drawn once per calendar year or per VR run
  and added to every trade of the block (R_bar units: R at a 144-bar hold), and, for the power columns, an effect of 0.20 in
  the tested half split (equal in both components). The read's own tests, 2,000 replications per cell (Monte Carlo
  error at most +/-1.1 points); the share with one-sided p <= 0.025 (the first Holm step; nominal 2.5 %). "Option C" is
  T1a's rule without its two sign conditions (lead decision 2026-10-05): by-day p <= 0.025 AND run-clustered p <= 0.05.

  | block effect (R_bar) | T1a size, by day | T1a size, option C | T1a power at 0.20, by day | at 0.20, option C | T1b size | T1b power at 0.20 |
  |---|---|---|---|---|---|---|
  | no block effect | 2.6 % | 2.1 % | 88.0 % | 82.1 % | 2.5 % | 92.1 % |
  | per year, sd 0.05 | 5.2 % | 3.9 % | 84.2 % | 77.4 % | 2.8 % | 92.7 % |
  | per year, sd 0.10 | 10.0 % | 6.5 % | 76.8 % | 67.0 % | 2.1 % | 91.9 % |
  | per year, sd 0.20 | 25.4 % | 13.6 % | 65.6 % | 51.0 % | 2.9 % | 91.1 % |
  | per VR run, sd 0.05 | 5.7 % | 3.6 % | 84.6 % | 74.5 % | 2.5 % | 91.7 % |
  | per VR run, sd 0.10 | 11.8 % | 5.9 % | 76.2 % | 55.1 % | 2.4 % | 92.7 % |
  | per VR run, sd 0.20 | 25.8 % | 10.2 % | 64.6 % | 32.2 % | 2.6 % | 89.9 % |

  - **Reading.** With no block effect the by-day T1a has its nominal size (2.6 %) and 88.0 % power at 0.20 R_bar, the
    pooled-alone figure above. A block effect of sd 0.05 R_bar doubles its false-positive rate (5.2 % per year, 5.7 % per
    run), 0.10 R_bar multiplies it by four (10.0 %, 11.8 %) and 0.20 R_bar by ten (25.4 %, 25.8 %); its power at 0.20
    falls to 84.2 %, 76.8 % and 65.6 % (per year) as the noise the SE does not see grows. The spread of the contrast over
    its reported SE is 1.19 / 1.63 / 2.79 (per year) and 1.24 / 1.75 / 2.97 (per run). T1b is not affected (size
    2.1-2.9 %, power 89.9-92.7 %).
  - **Option C (T1a's rule, lead decision 2026-10-05).** Without a block effect its size is 2.1 % and its power at
    0.20 82.1 % (by day alone 88.0 %): that is the power cost. Under a block effect it is less inflated than the
    by-day test (3.6-13.6 % in the cells above, against 5.2-25.8 %) but not conservative: with 8 clusters the
    run-clustered SE is itself unreliable (alone, at p <= 0.05, it rejects 7.2 % of the null replications
    without a block effect; nominal 5 %). Its power at 0.20 falls to 67.0 % at a year effect of 0.10 and
    51.0 % at 0.20 (by day alone 76.8 % and 65.6 %).
  - **What it means for a result.** The size of the block effect is not known (outcome-blind): the table brackets it.
    T1a's MDE of 0.18 R holds only if mean R_bar does not vary by regime. Under a year-level effect of sd 0.10 R_bar a
    by-day T1a pass would be about four times as likely under the null as its nominal level says; option C brings that
    to 6.5 %, at the power cost above. A T1a pass therefore still stands on 8 regime blocks: a regime-level
    effect is for TF to confirm (lead decision 2026-10-05), and a T1a-only pass is not evidence for a filter before TF.
    T1b is the cleaner of the two decisive tests.

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
  - A per-bar edge twice as large for early entries gives +0.08-0.09 on the weighted R_bar: at sd 0.75 and the dry run's
    SE, window B finds it ~30 % of the time. T1b is a test for a large timing effect.
- **Window A (report-only):** 3,278 gold trades with a VR (H7 1,316, G9 1,962; 136 without one); HIGH / LOW 1,474 / 1,804,
  bars gap 0.056. MDE: T1a 0.07 R [0.08], T1b 0.09 [0.10]. Silver: 1,404 trades with a VR (88 without, 11 without a sigma,
  1 last-bar signal); T2 on R_gross, MDE 0.12 R; no hold split (silver has no window-B median, §1). Research mode would
  drop H7 50, G9 72 and silver 13 events in window A. Window A never changes a verdict.
- VC-F: at 150 rows, SE ~0.13 R; MDE ~0.29-0.34 R for T1a (alpha 0.10 for one sub-test, 0.05 at the first Holm step of
  two; the weighted R_bar adds ~5 % to the R_gross figure, as in window B), ~0.30-0.39 for T1b. Forward has low power; it
  is a check against a large in-sample artefact, not a precise estimate.
- Prior: moderate that some gradient exists (~40 %); low (~15 %) that a filtered book beats the unfiltered book at equal
  risk after forward data. Literature: Gao, Han, Li, Zhou (2018, JFE) report stronger intraday momentum on high-volatility
  days (not verified here); the repo's E7 read that index outcome window (docs/plans/2026-10-03-crypto-cfd-design.md:251).

## 8. Budget

- VC: decisive T1a, T1b (Holm m = 2); secondary T2 (not run in window B, p = 1) and T3 (Holm m = 2); 1-2 forward tests.
  Reads: VC-G 1, VC-X 1, VC-F 1. Report-only: window A, the research-mode rows, the causal-density rows, every test without
  the paper log's refusals, the R_gross T1a and T1b, k = 2.0. T1a's run-clustered condition is part of T1a, not a further
  test (option C, lead decision 2026-10-05).
- It refines H7 / G9 (CLAUDE.md §43-44). Cumulative tests before it: research-directions §4.

## 9. What a result changes (both account layers; described, not run)

- **T1a or T1b passes (discovery grade):** a CANDIDATE filter for fvg-book (trade v4 only on HIGH days, or only entries
  before the recorded median slot of each component). It is a NEW setup version (CLAUDE.md §47).
  - A pass whose reading carries "DATA-SENSITIVE: not decisive" (§4) is a pointer for TF: the forward read still runs (the
    decisive verdict schedules it), and the filter is not replayed on either account layer before TF has read it. A T1a
    pass also stands on 8 regime blocks (§4): whether it is a property of the VR condition or of window B's regimes is for
    TF to confirm (lead decision 2026-10-05).
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
- **No T1 pass: NOT SHOWN (inconclusive for a G9-concentrated effect; D1).** VC adopts no filter and the forward read is
  not scheduled. The lead in personal-account.md §4.2 is NOT closed: window B would have found an equal effect of >= 0.2 R
  in both components with power ~0.8, but the 2018+ shape only with ~0.4-0.5 (§7). The 2018+ gradient stays unexplained:
  regime, timing, chance or a G9 effect too small for window B. Testing it again needs data not yet read (a new
  pre-registration on forward data). The owner's capped minimum-lot rule stands or falls on its own sizing study, not on
  this.
- **T3 passes but T1 fails:** the gradient is a property of crypto trends, not evidence for gold. Neither account layer
  changes.
- **Window A only (report-only) shows a gradient:** nothing changes; it is partly exposed. The same for the research-mode
  rows and the other report-only blocks (§6).

## 10. Sealing steps (coordinator)

1. Window: decided (lead decision 2026-10-04, window B decisive); `HOLDOUT = "B"` is already set in
   `scripts/research/edge_vc.py`.
2. Review this draft and the code (`scripts/research/edge_vc.py`, `pit_trend.py`, `prereg_guard.py`, the tests). Commit the
   final code and this draft (commit A, explicit paths only: other work is in the tree). A dry run from the committed code
   must give `counts` and `meta.dataset` identical to step 3's JSON.
3. Outcome-blind dry run: `python3 scripts/research/edge_vc.py dry-run --out <scratch json>` (per component and window:
   events by VR half, the median entry slot, the hold halves per VR half, last-bar signals and events without a sigma,
   research mode's events and drops, the clock against the stored bar count, planned-bar quantiles and the count under 24
   bars, and per side x half the events, planned bars and days, with `power_inputs`; pooled gold: `power_inputs` and
   `rule_power`; the events the paper log would refuse, the VR runs, the causal-density sample; no trade is simulated).
   Run it under the probe (`vc_dryrun_probe.py <json> <trace>`: it fails on any function or file off its allowlist).
   Amend §7 with the counts, the MDEs they give (MDE = 2.80 x 0.75 x
   `xau_pooled.decisive.se_per_sd`), the full-rule power and the `dataset-sha256` lines (`edge_vc.dataset_lines` of
   `meta.dataset`). If `xau_pooled.decisive.vr_halves_bars_gap` > 0.10, amend T1a to the weighted R_bar (§4). **Done
   2026-10-04:** §7 carries the counts; the gap was 0.120, so T1a stays switched (`edge_vc.T1A_VALUE`).
   JSON sha256 `0d003b4ab0f22156ef9b85d71fd64935639b74a3014658553df90676e69c8fac`.
4. Then `python3 scripts/research/edge_vc.py manifest` and paste its lines into §11.
5. Commit this text under the sealed name with the exact "Status: SEALED" line and, in the same commit, the ledger entries
   of §5.4 and the evidence of §7 (`docs/experiments/vc-p1-dryrun/`: the dry run `edge-vc-dryrun.json`, sha256 as in §7,
   the probe and its trace, the regime simulation and its script). **The sealed text differs from this draft in four places
   only:** the title ("pre-registration DRAFT" becomes "pre-registration"), the status line ("Status: SEALED"), the
   "Sealing:" paragraph (replaced by a "Sealed:" paragraph that names these four changes) and §11's code manifest (step 4's
   lines). The read refuses without the study entry (`edge_vc.require_ledger`) and without its `dataset` digests
   (`edge_vc.require_dataset`). Keep this draft file.
6. Read: `python3 scripts/research/edge_vc.py run --read xau-holdout --out docs/audits/<date>-edge-vc-xau-holdout.json`,
   committed alone. Any code change after step 4 makes the guard refuse (re-print the manifest, re-seal by amendment);
   that includes `scripts/research/fvg_forward.py` (the decisive walk) and the three test files, so the read runs before
   any of them changes. A re-import of the 5m XAUUSD / XAGUSD history refuses too (§7, D3). A second run of any read is
   refused, to any path. Its `primary.hold_medians` must equal the dry run's (H7 637.5, G9 875) and its `primary.counts`
   the dry run's trades with a VR (H7 302, G9 460, silver 0). The read runs the decisive rows, k = 2.0 and the three
   sensitivities of §4 / §6 in one pass (a few minutes). Then `python3 scripts/research/edge_vc.py verdict --xau <that
   file>` prints T1's verdict, its reading, the sensitivities' verdicts and the secondary Holm (T2 enters at p = 1).
7. Forward, when due: `python3 scripts/research/edge_vc.py run --read forward --xau
   docs/audits/<date>-edge-vc-xau-holdout.json --out docs/audits/<date>-edge-vc-forward.json`. No date is typed: the
   window starts on the server day after the commit that added the sealed text (an amendment does not move it).

## 11. Code and its fingerprint

- `scripts/research/edge_vc.py`: `vr_by_day`, `pit_vr_by_day` (the point-in-time VR), `label`, `mark_hold`, `per_bar`,
  `nb_weight`, `bars_to_day_end`, `pit_events` / `pit_trade` / `pit_holdout_rows` (the decisive rows: point-in-time series,
  the clock stop, `fvg_forward.resolve_row`), `causal_density` / `_pit_series(causal)` (the causal-density sensitivity),
  `paper_log_refusals` (the counterfactual refusals), `vr_runs` / `regime_blocks`, `research_events` / `holdout_rows` /
  `book_rows` (research mode, report-only), `split_test` (side-balanced, joint CR1, optional row weights, cluster key),
  `holm`, `t1_verdict` (Holm, the gate, T1a's run-clustered condition, the `reading`), `with_sensitivities`
  (DATA-SENSITIVE), `_guarded`, `xau_read` (decisive and report-only windows; `mode` "pit", "pit_causal" or "research"),
  `cx_closure`, `crypto_rows` (pit_trend +
  CX cost), `is_forward_row` / `forward_rows` (R_net re-priced) / `forward_tests`, `xau_primary`, `forward_snapshot`
  (paper-log sha256, merged-candle digest and sources, cost profile), `cost_profile` (with `real_costs.price_ref_info`),
  `dry_counts`, `power_inputs` (with the same-day bound), `rule_power` (T1's full rule), `secondary_verdict`,
  `T1A_GAP_RULE` / `T1A_VALUE` / `T1A_WEIGHT` (T1a's statistic, §4), `require_ledger` (the study's ledger entry),
  `require_dataset` / `dataset_lines` (the pinned history, D3), CLI with the registration guard (a dry run refuses a read's
  output name: there it would block that read for good; a read refuses when `sys.pycache_prefix` is set: bytecode outside
  the repository would hide executed code from `require_covered`).
- `scripts/research/pit_trend.py`: the [CX-P1] §1 rules as a library. `scripts/research/prereg_guard.py`: the guard,
  including `seal_time` / `first_forward_day` (the forward start, from git) and `require_read_json` (an earlier read's
  JSON is used only when its name, commit state, tag and read match).
- Tests: `scripts/tests/test_edge_vc.py`, `scripts/tests/test_pit_trend.py`, `scripts/tests/test_prereg_guard.py`
  (hand-built bars and synthetic trades; a truncation probe for the events and for VR; the market-drift, edge-drift,
  late-entry, weighted-SE and shared-day checks; the T1a timing-gap check; the same-day bound; the full-rule power; the
  point-in-time rows: on complete days they are book_sim's trades, a day that proves sparse keeps its event with the
  clock stop, the day view walks what the whole series walks, and the paper log's own `signals` agree with the rows'
  stops and with `paper_log_refusals` on a series with a hole and a sparse stretch; the causal density: point in time (the
  whole-history rule is not), the early thin era; the VR runs and regime blocks; T1a's run-clustered condition (option C)
  and the DATA-SENSITIVE reading; the report-only blocks; the first forward day and the gold read checks; read-once;
  the pinned dataset; a module-coverage check; a dry run with every outcome function replaced by a tripwire;
  `SealRehearsal`: in a temporary git repository, every refusal before the seal in the order the CLI checks them, one
  read, then the read-once and code-change refusals; a dry run refused at every read's output name).
- The guard refuses a read unless every file in `edge_vc.CODE` is listed below with its current sha256, and refuses to
  write a result if the read executed a repository module not listed.

Code manifest (filled at sealing by `python3 scripts/research/edge_vc.py manifest`; empty in this draft):

```
(paste here)
```
