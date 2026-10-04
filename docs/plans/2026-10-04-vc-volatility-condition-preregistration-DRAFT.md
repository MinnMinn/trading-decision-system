# Family VC -- does the gold trend edge (H7, G9) concentrate on volatile days or on early entries? -- pre-registration DRAFT (2026-10-04) [VC-P1]

Status: DRAFT. Not sealed.

Sealing: the coordinator commits this text, after review, as
`docs/plans/2026-10-04-vc-volatility-condition-preregistration.md`, with the status line above replaced by a line that reads
exactly "Status: SEALED" and with §11's code manifest filled in. `scripts/research/edge_vc.py` refuses every read until then
(scripts/research/prereg_guard.py `require_sealed`, `require_fingerprint`).

**No outcome of this family has been read.** The code was tested on hand-built series only
(`scripts/tests/test_edge_vc.py`, `scripts/tests/test_pit_trend.py`, `scripts/tests/test_prereg_guard.py`). Ranked first in
docs/plans/2026-10-04-research-directions.md §1. Revised once after a review (2026-10-04: holdout partly exposed, guard,
drift bias of T1b, shared days, VC-X cost and windows, frozen hold cut).

## 0. Origin (disclosed) and question

- The lead is post hoc, on exposed data. G9 gold at stop 1.4, mean R by stop-width quartile "since 2018", narrowest to
  widest: -0.02 / +0.01 / +0.12 / +0.29; G9 silver -0.08 / +0.05 / +0.05 / +0.17; H7 gold +0.04-0.05 to +0.07-0.10
  (docs/audits/2026-10-04-personal-account.md:47-55).
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
  stop of ~100-110 bp at k = 1.4 (docs/audits/2026-10-04-personal-account.json `min_lot`, since 2024), about 0.006 R.
- **Question.** On data where this split was never computed, is mean R higher (a) on volatile days, (b) for early entries?
  (3) is not tested: a level filter in absolute bp would select years, not days.

## 1. The two conditions (fixed now)

- **(a) HIGH volatility day.** sigma_5m(D) > the median of sigma_5m over the previous 250 days that have one, given at
  least 125 of them. This is F3 H5's own regime rule (scripts/research/edge_f3.py:30, :99-116), reused unchanged. VR =
  sigma / that median. No VR -> excluded and counted.
  - Gold / silver: the research-mode dense-day sigma history (edge_census.Series `_vol` over `dense_days`, as H5).
  - Crypto: the [CX-P1] point-in-time sigma of each eligible day (scripts/research/pit_trend.py `context`).
- **(b) LONG HOLD (early entry).** The trade's entry server-clock slot (minutes from server midnight of the entry bar) is
  EARLIER than the median entry slot of the same component's VC-G trades. The FTMO server day ends at a fixed clock time
  (New York + 7 h), so an earlier slot means more bars to the end of the day. The slot is entry timing, known at entry.
  - The medians are computed ONCE, in the VC-G read, and recorded in its JSON (`hold_medians`). The forward read and any
    filter use those recorded constants, never a median of their own rows. The outcome-blind dry run reports them first.
- Each trade's day is its ENTRY server day (book_sim rows carry no signal index). VR uses only earlier days: point in time.

## 2. Outcome per trade

- The book's mechanics, unchanged (scripts/research/book_sim.py:38-82): entry at the next bar's open, protective stop k x
  sigma_5m x sqrt(planned bars), time exit at the server day's last bar, relative spread cost.
- **k = 1.4**, the stop of fvg-book v4 now on the demo (docs/architecture/trading-systems.json:272-273). k = 2.0 (v3) is
  report-only (with the k = 1.4 hold medians).
- **Primary statistic: R_gross** = side x (exit - entry) / stop distance. R_net = R_gross - cost / stop distance.
  Why gross: cost per unit of stop falls mechanically as the stop widens, so a NET gradient is partly guaranteed by
  arithmetic. The tradability gate uses R_net (§4).
- VC-X (crypto) charges the [CX-P1] cost model: half the recorded relative spread per leg at the leg's table bucket plus
  c_sym (pit_trend `SpecCost`). A crypto read without it is refused.

## 3. Reads (each once, each in its own commit)

Grades as in docs/plans/2026-10-04-research-directions.md §0.

| read | data | grade | tests |
|---|---|---|---|
| **VC-G gold holdout** | book_sim.trades of H7_XAUUSD_eod, G9_XAUUSD_eod, G9_XAGUSD_eod whose entry server day is in the chosen window (below) | see below. Label of a pass: "HOLDOUT-FOR-THE-CONDITION (components exposed)" | T1a, T1b, T2 |
| **VC-X crypto** | FTMO crypto CFDs: CX group A members over their whole history, CX group B members from 2024-03-01 only ([CX-P1] §3: H7x read B's underlying through 2024-02-29), to the CX amendment's end date; H7 / G9 by pit_trend ([CX-P1] §1: min_bars 230, calendar previous day); CX costs | UNREAD-FOR-H at read time (the CX reads come first, §5). Windows CX retired unread after a failed gate are read here: disclosed and logged (§5.4) | T3 |
| **VC-F forward** | the paper log's H7 / G9 XAUUSD rows (scripts/research/fvg_forward.py:36-38) entering on or after the seal date at stop_k 1.4 | FRESH | TF |

**The VC-G window -- owner decision before sealing** (`edge_vc.HOLDOUT`):

- **A (recommended):** entries before **2018-01-01** -- gold from 2004-06, silver from 2008-11.
  - Grade: UNREAD-FOR-H before 2008-12-10; **PARTLY EXPOSED** from 2008-12-10 to 2017-12-31.
  - Why partly exposed: the personal-account replays ran mode `skip` against `floor` on the common span 2008-12-10 ->
    2026-10-02 (docs/audits/2026-10-04-personal-account.json `meta.common_span`, `historical` keys), and `floor_cap` on the
    same span (docs/audits/2026-10-04-personal-account-cap.json, commit 4f803bf). `skip` drops every trade whose minimum lot risks more than r x balance at the 2026-09-30 price
    (`personal_account.py` `lots_for`), an absolute stop-width cut that moves with the balance (about 120 bp at r 1 % on
    5,000 USD for gold). The cells report compounded account metrics (terminal multiple, CAGR, drawdown), not mean R by
    stop width, and nobody computed "common span minus post-discovery". It is still a related cut on these years, so
    the window is not pristine for this question.
  - Under A, the sub-window before 2008-12-10 (window B) is reported separately, report-only.
- **B (strict):** gold entries before **2008-12-10** only (2004-06 -> 2008-12-09; no personal-account cell touched it).
  Silver has about one month there, so T2 becomes "not run (window)" and enters its Holm family with p = 1.
- 2018-01-01 onwards, gold and silver, are EXPOSED for VC (the hypothesis came from them). They are never a VC test.
- H7 / G9 on the indices, PGMs and research-only CFDs failed their own reads (edge-f3.md, edge-f4.md, edge-f5.md). They
  are not tested under this condition: a rescue by subgroup is fishing.

## 4. Tests and decision rule

**Test statistic (every test): the side-balanced difference** 1/2 [(mean R_gross True half - False half | long trades) +
(same | short trades)].

- Why balanced: under a constant drift mu, a trade's R carries side x mu x sqrt(bars) / (k x sigma). Early entries of
  the majority side then earn more R with no conditional effect. In a gold bull market (mostly long H7 trades) T1b would
  "pass" on drift alone. The balanced difference cancels that term (synthetic check:
  scripts/tests/test_edge_vc.py `test_constant_drift_does_not_pass_t1b`). It also removes the opposite bias in T1a (a
  given drift is fewer R on high-sigma days). The plain pooled difference is report-only.
- Variance: CR1 cluster-robust by server day for the contrast as a whole (each day's summed influence across the four
  side x half cells). This is exact when the halves share days: crypto symbols pooled on one server day, and an H7 and a
  G9 trade of one gold day in different T1b halves. The shared-day count is reported.
- Student-t with min(days in each of the four cells) - 1 df; one-sided (True > False). A test with an empty cell is not
  computable and enters its family with p = 1.

| test | data | condition | gate |
|---|---|---|---|
| T1a | VC-G, H7 + G9 XAUUSD pooled | (a) | Holm m = 2 over {T1a, T1b}, alpha 0.05; AND True-half mean R_net > 0; AND the balanced difference > 0 in BOTH gold components |
| T1b | VC-G, H7 + G9 XAUUSD pooled | (b) | same Holm; same two extra conditions |
| T2 | VC-G, G9 XAGUSD | (a) | Holm m = 2 over {T2, T3}, alpha 0.05 (secondary) |
| T3 | VC-X, crypto pooled | (a) | same secondary Holm; a test not run enters with p = 1 |
| TF | VC-F forward | only the T1 sub-test(s) that passed | Holm over those at alpha 0.10; AND True-half mean R_net > 0 |

- T1 is the decision test for the gold book. T2 / T3 inform the mechanism; they never adopt a filter.
- The forward read runs once, at >= 150 closed rows or 365 days after the seal, whichever comes first. It is scheduled only
  if T1a or T1b passed. TF's (b) uses the VC-G `hold_medians`.
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
   - the VC-G window as development data read once for this condition, with the partial exposure of 2008-12-10 ->
     2017-12-31 through the personal-account replays named (window A);
   - after VC-X: the CX windows it read that CX had retired unread (the read JSON lists them, `retired_windows_read`)
     become exposed for H7 / G9 on crypto (trigger `hypothesis_refinement`).

## 6. Report-only diagnostics (outside the family)

- The literal finding on the holdout: mean R_gross and R_net by stop-width quartile (cut points from the holdout's own
  stop_bp, a timing-and-volatility quantity).
- The pooled (unbalanced) difference of every test; the per side x half cells.
- The 2 x 2 of (a) x (b): which one carries the gradient.
- Long and short separately (drift check), and per year.
- Window A only: every test on the sub-window before 2008-12-10.
- k = 2.0 rerun of everything (the k = 1.4 hold medians).
- Counts: trades without a VR, shared days per test.

## 7. Power and prior (before any read; arithmetic, the dry run gives the counts)

- Per-trade sd of R at k = 1.4 ~0.75 (docs/audits/2026-10-03-vol-schedule.md:29). Balancing by side costs ~10 % in SE at
  a 60 / 40 side mix.
- Window A, gold: about 3,400 trades (F3 H7 discovery n 1,197 and F4 G9 gold discovery n 1,780, docs/audits/2026-10-02-
  edge-f3.md:14, edge-f4.md:13, plus part of confirmation, minus 2018-01-01 -> 2018-02-25). SE of the balanced half-split
  difference ~0.028 R; MDE at 80 % power, first Holm step (alpha 0.025) ~0.08 R. The 2018+ quartile table implies a
  half-split difference near 0.2 R for G9 gold: if 40 % of it is real, T1 sees it. Silver: ~1,500 trades (F4 G9
  XAGUSD discovery n 1,502, edge-f4.md:14), MDE ~0.12 R.
- Window B, gold: about 1,100 trades (4.5 of ~13.5 years); MDE ~0.14 R.
- VC-F: at 150 rows, SE ~0.13 R, MDE ~0.28 R at alpha 0.10. Forward has low power; it is a check against a large
  in-sample artefact, not a precise estimate.
- Prior: moderate that some gradient exists (~40 %); low (~15 %) that a filtered book beats the unfiltered book at equal
  risk after forward data. Literature: Gao, Han, Li, Zhou (2018, JFE) report stronger intraday momentum on high-volatility
  days (not verified here); the repo's E7 read that index outcome window (docs/plans/2026-10-03-crypto-cfd-design.md:251).

## 8. Budget

- VC: 4 historical tests (T1a, T1b, T2, T3) in 2 Holm families + 1-2 forward tests. Reads: VC-G 1, VC-X 1, VC-F 1.
- It refines H7 / G9 (CLAUDE.md §43-44). Cumulative tests before it: research-directions §3.

## 9. What a result changes

- T1a or T1b passes: a CANDIDATE filter for fvg-book (trade v4 only on HIGH days, or only entries before the recorded
  median slot of each component). It is a NEW setup version (CLAUDE.md §47). Its book is then evaluated descriptively with
  the vol_schedule / pass_policy machinery (POLICY-EXPOSED), and the demo uses it only after TF passes and the owner
  approves. On the personal account the owner may use a passed filter at his own discretion, labelled
  HOLDOUT-FOR-THE-CONDITION (open decision 4 in research-directions §4).
- Both fail: the 2018+ gradient is treated as a regime or chance effect. The research lead in personal-account.md §4.2 is
  closed. The owner's capped minimum-lot rule stands or falls on its own sizing study, not on this.
- T3 passes but T1 fails: the gradient is a property of crypto trends, not evidence for gold.

## 10. Sealing steps (coordinator)

1. Owner decision: window A or B (§3). Set `HOLDOUT` in `scripts/research/edge_vc.py` to match, if B.
2. Review this draft and the code (`scripts/research/edge_vc.py`, `pit_trend.py`, `prereg_guard.py`, the tests).
3. Outcome-blind dry run: `python3 scripts/research/edge_vc.py dry-run --out <scratch json>` (event counts per half, the
   median entry slots, events before 2008-12-10; no trade is simulated). Put the counts into §7 as an amendment, if wanted.
4. Commit the final code. Then `python3 scripts/research/edge_vc.py manifest` and paste its lines into §11.
5. Commit this text under the sealed name with the exact "Status: SEALED" line, and the ledger entries of §5.4.
6. Read: `python3 scripts/research/edge_vc.py run --read gold-holdout --out docs/audits/<date>-edge-vc-gold-holdout.json`,
   committed alone. Any code change after step 4 makes the guard refuse (re-print the manifest, re-seal by amendment).

## 11. Code and its fingerprint

- `scripts/research/edge_vc.py`: `vr_by_day`, `label`, `mark_hold`, `split_test` (side-balanced, joint CR1), `holm`,
  `t1_verdict`, `gold_read` (book_sim.trades + the research sigma history), `cx_closure`, `crypto_rows` (pit_trend + CX
  cost), `forward_rows` / `forward_tests`, `dry_counts`, `secondary_verdict`, CLI with the registration guard.
- `scripts/research/pit_trend.py`: the [CX-P1] §1 rules as a library. `scripts/research/prereg_guard.py`: the guard.
- Tests: `scripts/tests/test_edge_vc.py`, `scripts/tests/test_pit_trend.py`, `scripts/tests/test_prereg_guard.py`
  (hand-built bars; a truncation probe for the events and for VR; the drift and shared-day checks; a module-coverage check).
- The guard refuses a read unless every file in `edge_vc.CODE` is listed below with its current sha256, and refuses to
  write a result if the read executed a repository module not listed.

Code manifest (filled at sealing by `python3 scripts/research/edge_vc.py manifest`; empty in this draft):

```
(paste here)
```
