# Wyckoff forward stage for W-C-long-15m (Spring / Shakeout long) -- pre-registration (2026-10-04, sealed 2026-10-05) [WY-F1]

Status: SEALED

Sealing record (coordinator, 2026-10-05).
- The seal is the commit that adds this file, together with the fingerprint and nothing else; its committer date is
  the seal instant, the start of the forward window (§3). Its parent is the fingerprinted commit c61739ed646099e86cf30764e77abd295732bd25.
- Fingerprint: `docs/experiments/wyckoff-forward-wc15/fingerprint.json`, digest
  12b870ccdee54cf58a4ab46a3ff4c9f210d313d4edce5a8229d77f27ade365ad (file sha256
  cffe6a61149ae7f723d9788af0ebe047da2696b2934e1bc1d0f9656cd8c39dfc): 17 executed, 19 loaded, 151 data files; canary 10
  events; r0_drift empty. Interpreter `/opt/homebrew/opt/python@3.14/bin/python3.14` (3.14.5); `brew pin python@3.14`
  run 2026-10-05 with the owner's permission.
- Decisions: the §14 record as written above it (2026-10-04 and 2026-10-05). Owner, 2026-10-05: seal on the history
  already committed, without waiting for a re-export ("Nếu mày không tự làm được thì niêm phong data đang có đến 28/09
  đi").
- State at the seal: US500, US30, USTEC and DE40 end their committed 15m history at 2026-09-28 16:45Z and their live
  files start later, so they are NOT ADVANCING until an export bridges the hole (the coordinator put them on the MT5
  export list); JP225 and AUS200 have no live 15m file (STALLED). Late-logged events are read and disclosed (§4, §7).
- Scope (§1): this stage measures the re-test's engine as R0 read it. A later change to scripts/wyckoff_rules.py does not
  enter it; a test of a changed engine would be a separate registration (WY-F2).
- The draft (`docs/plans/2026-10-04-wyckoff-forward-wc15-preregistration-DRAFT.md`) stays as history; this file is the
  registration.

**No forward bar exists yet, and no outcome was read to write this.** The code was tested on synthetic bars only
(`scripts/tests/test_wyckoff_forward.py`). The power numbers in §9 use the R0 counts (outcome-blind), the published R1
summary line, and WX's outcome-blind X0 counts for the three added symbols.

Abbreviations. WF = `scripts/research/wyckoff_forward.py`, EW = `scripts/research/edge_wyckoff.py`, RT = the sealed
re-test `docs/plans/2026-10-04-wyckoff-retest-preregistration.md` [WY-P1], AU = its results
`docs/audits/2026-10-04-wyckoff-retest.md`, R0 = its counts record `docs/experiments/wyckoff-retest-r0/edge-wyckoff-R0.json`,
WX = the WY-X1 draft `docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md`. Cites are `file:line`, or
`file` + function name. The code cites this file as "[WY-F1 §n]".

---

## 1. Origin (disclosed), question and scope

- Owner, 2026-10-04: *"thu thập dữ liệu forward cho Spring/Shakeout 15m"*.
- In the sealed re-test, W-C-long-15m read **INCONCLUSIVE**: n 63, net excess +0.25R, p = 0.18, 95 % upper bound +0.72R
  (AU:20). By type, on the same net line: Shakeouts +0.54R (n 14), Springs +0.17R (n 49), descriptive. AU:39's +0.64 and
  +0.26 are the GROSS excess (WX §1, "A correction to carry"); the earlier text of this section repeated them.
- RT runs its forward read R4 for survivors only (RT:245). An inconclusive cell is not a survivor. So this cell needs its
  own forward rule (AU:66-68). RT:323: INCONCLUSIVE "never licenses new variants on history. Only forward bars can settle
  it."
- **Selection, disclosed (CLAUDE.md §43).** This cell is followed BECAUSE it was the only positive confirmatory cell of
  four. Forward bars are untouched by that choice, so the forward test is fair. But +0.25R is a winner's-curse estimate.
  Plan for a smaller true effect.
- **Question.** On FTMO 15m bars of the 10 symbols (§2) that close after the seal, is the mean net excess R of the
  W-C-long-15m trade above 0?
- **Scope: the engine as R0 and R1 read it** (lead decision, 2026-10-04, §14 item 8). WY-F1 measures the sealed re-test's
  cell on the Wyckoff engine exactly as R0 and R1 ran it: the files `r0_drift` pins (§5), run from the sealed extract.
  - Another session ("Khám phá hệ thống FTMO") will soon merge a change to `scripts/wyckoff_rules.py` that alters Wyckoff
    SEMANTICS: CHoCH must sit inside or near the TR box, the run-away guard runs first, LPS[C] requires Phase C, Phase E
    timing. Under CLAUDE.md §59 that is potentially Trading System version significant ("never make a local
    implementation change that silently changes historical research semantics").
  - That change does NOT enter WY-F1 and does not apply to it. Before the seal, `r0_drift` refuses a fingerprint on a
    tree that carries it (§5, §12 step 2). After the seal, every cycle and look runs the sealed extract.
  - So WY-F1's verdict is a statement about the OLD detector only (§11).
  - A forward test of the changed engine is a SEPARATE registration (proposed name WY-F2, not drafted now). It is never
    a re-seal of WY-F1, and it never reads WY-F1's bars or log for a choice about this cell before WY-F1 ends.

## 2. What is collected (fixed now)

- **The cell, unchanged.** W-C-long exactly as RT §3.2 (RT:95-124): Spring and Shakeout pooled, long only. Entry at the
  open after the signal bar. Stop = spring low x (1 - 0.0005). Target = `tr_hi`. Cap H = 96 bars. No new variant.
- **The detector, imported, not copied.** DET-PO: EW `BASE_CFG` (EW:186), `det_params`, `window_fire` (EW:676), loaded
  from EW unmodified (WF `ew`, `det_ctx`). De-duplication as EW `detect_series` (EW:759): per leg on (side, SC, AR), here
  keyed by bar TIME (WF `fire`).
- **Symbols (10)** (WF `SYMBOLS` = `RT_SYMBOLS` + `ADDED_SYMBOLS`; test
  `test_symbols_are_the_retests_seven_and_the_three_cheap_replication_indices`):
  - **RT's seven:** XAUUSD, XAGUSD, US500, US30, USTEC, DE40, AUS200. These are RT's 8 tradeable symbols (EW:135) minus
    FRA40. R0 gives FRA40 15m no dense start (R0 `dense["FRA40|15m"].start` = null), so R1 and R3 never read FRA40 at 15m.
    Adding it would need a new dense rule. Not done (§14 item 2).
  - **Added 2026-10-04 (lead decision, §14 item 3; WX §12.2 (a)):** US2000, UK100, JP225, three of RT's replication
    symbols (EW `REPLICATION`). They are cheap: entry-hour spread proxy 0.06-0.09R median, 0.07-0.23R mean (WX §12.2 (a)).
    WY-F1 decides on RT's NET line, so a symbol whose spread eats the edge would lower its power. XPTUSD and XPDUSD stay
    out (about 0.9R a trade, WX §12.2 (a)). FRA40, EU50 and HK50 stay out (no dense-rule change).
  - Only bars after the seal are scored for the added three. RT's R2 window for them (before 2024-03-01) stays unread for
    Wyckoff, as RT:243 keeps it, and WY-X1 is not run (WX §13).
  - Each scored row carries its set, `rt` or `added` (WF `measure`). The split is reported, never decisive.
- **Dense rule.** R0's dense starts and EW's per-day rule (EW `dense_days`, EW:396). An event counts only if the server
  day before its signal bar was dense (EW `kept`, EW:898).
  - R0's 15m dense starts of the added three: US2000 2018-01-01, UK100 2021-09-01, JP225 2021-09-01 (R0
    `dense["<SYM>|15m"].start`). R0 computed them with RT §4's rule (EW `dense_table`, EW:1834; `dense_start`, EW:355).
  - Re-checked 2026-10-04, outcome-blind: EW `dense_table` on the committed 15m history, with every price removed before
    the call, gives the same start, reference median and hole count for all three; the history files are the ones R0
    hashed (R0 `provenance.sha256`). Test: `test_the_added_symbols_dense_starts_are_the_retests_rule_outcome_blind`.
  - The pin: R0 itself, sha256 `09e215902f012f14210577684f34e0c3fac50a6a0df76d55076992fa726655f9`, is in the fingerprint
    (§5). WF reads the starts from R0 (WF `r0_dense`); every store bar lies after them.
- **Decided at the signal bar.** Every logged decision field is known at the close of the signal bar k (§4, §8).
- **Logged, never tested (§6).** At each resolve: MFE and MAE in R, bars to MFE, the planned R:R, the entry-hour spread,
  and the ICT HTF gate flag at the signal. A later variant may be pre-registered on these fields and read on LATER
  forward bars only (WX §12.2 (c)).
- **PAPER ONLY.** No order, no account, no live configuration. Nothing here feeds the demo executor.

## 3. From when

- The forward window starts at the **seal instant**: the committer date of the commit that ADDS the sealed file (WF
  `seal_info`). This is RT's own convention (EW `_seal`, EW:1483; RT:623). Nobody chooses it.
- An event is forward iff its signal bar CLOSES at or after the seal instant (WF `scan_symbol`). A test checks the
  boundary to the second (`test_only_a_signal_bar_closing_at_or_after_the_seal_is_forward`).
- Bars before the seal are context only. Each store starts 90 days before the seal (WF `WARMUP_DAYS`): at least 60
  dense-rule days, one 300-bar window, and the de-duplication context. A test shows a store cut 90 days before the seal
  decides exactly as the full history (`test_a_store_starting_ninety_days_before_the_seal_decides_as_the_full_history`).
- **The seal commit must stay in history.** Merge it; never squash, rebase or amend it. A new SHA is a different seal, and
  every record made under the old one is refused (§8).

## 4. How bars and events are logged

**Bars** (WF `accumulate_symbol`, `plan_init`, `plan_append`):
- One append-only JSONL store per symbol: `data/live/forward/wyckoff-wc15/bars/<SYM>.15m.jsonl` (gitignored, per
  machine). Each line carries `ch` = sha256(previous `ch` | record). An edited, removed, inserted or reordered line
  refuses every later step (WF `read_chain`).
- First: the SEALED history (the extract's `data/history/ftmo`, §5) from seal - 90 days.
- Then: the bridge's 15m file `data/live/mt5-bridge/ohlcv.<broker symbol>.15m.json`. ExportOHLCV copies from shift 0
  (`integrations/mt5/ExportOHLCV.mq5:91`), so the file's last bar may still be forming. It is dropped.
- Times are snapped to the 15-minute grid, +-60 s (the v1.02 bridge stamps `...:00:01Z`). A source with one unreadable or
  off-grid bar, or two bars on one label, is not used at all.
- A source appends only when it holds the store's last bar and the times of its last 4 bars, and is ALIGNED (WF
  `plan_append`): of the store's last 96 bars that it holds, it agrees on all of them, or, where some differ, on at
  least 4 and on at least as many as differ. A bar it shows at another price is a **revision** (below). A hole, a gap in
  the overlap, a shifted clock (the bridge after a DST change: nearly every bar differs) or another series appends
  nothing, and a note says why.
- **Revisions** (lead decision 2026-10-04, §14 item 11; review item 2). The broker can revise a bar after the store took
  it. The first design needed the store's last 4 bars at identical prices, so one revised bar refused every later
  source, live file and history export alike (a revised bar never leaves a 4-bar overlap), nothing was ever appended
  again, and the symbol was dropped whole from every later look. Now:
  - the store keeps the bar AS FIRST STORED. Every decision, every window hash and every resolve uses it (point in
    time, CLAUDE.md §8);
  - the new bars are appended, and a chained `revision` record goes to the log: the symbol, the bar time, the source, the
    bar as stored and as shown (`store`, `source`), the fields that differ, when it was seen (WF `revision_record`). One
    record per distinct revised price, not one per cycle;
  - every look lists the revision records (count, per symbol, whether the bar lies in a sampled event's span, §8), flags
    each store-versus-export difference that one explains, and `status` shows their number. A blinded look 1 lists them
    too;
  - frequency: 0 differences in 537 overlapping live and history 15m bars (review, 2026-10-04), so this is a safety net
    for a rare event, not a routine one;
  - one edge, disclosed: a worker killed between the bars' append and the log's append loses that cycle's revision
    record (never an event: the scan cache is written last, so the next cycle re-detects it). The look still lists every
    difference between store and export, then without the flag that a record explains it (§8).
  Tests: `test_a_revised_bar_never_wedges_a_store`, `test_a_revised_bar_is_logged_once_per_price_the_store_keeps_it_and_resolves_stay_point_in_time`
  (the entry bar of a logged event is revised; the resolve the log holds is the one the first-stored bar gives, and the
  revised bar would give another), `test_the_old_wedge_a_revised_bar_among_the_last_four_does_not_stop_the_store`,
  `test_every_look_reports_the_revision_records`.
- The live file holds about 300 bars (about 3 trading days). After a longer outage, a re-exported FTMO history
  (ExportHistory.mq5 + `scripts/import-mt5-history.py`) bridges the hole. Whenever the live file brings no new bar (a
  hole, a shifted clock, a stale or stopped feed, a missing file), the cycle reads the history export and appends the
  bars it holds after the store's end, under the same alignment rule. Then the live file continues.
- Every bar records its source (`live` / `history`) and the time it was appended.
- **A missing or unusable live file is STALLED, never an empty market** (CLAUDE.md §20: MISSING is not EMPTY; WF
  `live_source`, `accumulate_symbol`). Missing, unreadable, with one bad bar, or with no closed bar: the file gives no bar
  list at all, so nothing is appended from it. The cycle summary (`stalled`) and `status` list the symbol. A history
  export can still fill its store; the symbol stays listed while its feed is down. A stalled store that no export fills
  does not advance, so no look counts it complete (§7). Today JP225 and AUS200 have no live 15m file (§12 step 4). At a
  look the export of all 10 symbols fills such a store and the symbol is READ, its events late-logged and disclosed
  (§7, §8); only the registered fallback drops one. Tests: `test_a_missing_or_unusable_live_file_is_stalled_never_an_empty_market`,
  `test_a_stalled_symbol_is_filled_by_the_looks_export_and_read_with_its_events_late`.
- **NOT ADVANCING** (lead decision 2026-10-04, §14 item 13; review item 4). STALLED covers a missing or unusable file.
  Two more states are visible in the cycle summary and in `status`, with the reason and the store's last bar (WF
  `accumulate_symbol`, `status`):
  - the live file exists and holds bars after the store's last one, but no source gave the store a bar: `plan_append`'s
    reason (a hole, a gap, a shifted clock, too few agreeing bars). This is the four indices after the seal (§12 step 3);
  - the live file is stale: its newest closed bar closed more than 72 hours (`STALE_LIVE_HOURS`) before the cycle (the
    EA may have stopped; a weekend is about 49 hours, a long holiday can show).
  The bars an empty store starts from are not an advance. A flag is a note, never a refusal.
  Tests: `NotAdvancing` (a hole, a stale file, a store that advanced from the export), `test_a_shifted_live_clock_appends_nothing_and_says_why`.

**Events** (WF `fire`, `decision`, `scan_symbol`):
- Each cycle scans only the windows it has not scanned, plus window - 1 earlier windows for the de-duplication context.
  A structure's SC lies inside every window that sees it, so that context is exact. A test shows bar-by-bar scans equal
  one full replay.
- Each event is logged ONCE, id `SYM|15m|<SC time>|<AR time>`, in the append-only hash-chained log
  `data/live/forward/wyckoff-wc15/log.jsonl`. The record (WF `DECISION_KEYS`) holds:
  - the structure: SC, AR, spring, reclaim and test times; type; `tr_lo`, `tr_hi`, ceiling; Phase-B tests; path;
  - the trade: spring low, stop, target;
  - the facts at k: signal time and close, store line, previous day dense, ATR20;
  - **the detection inputs' hashes:** `window_sha256` (time + OHLC of the 300 bars the detector read) and
    `chain_at_signal` (the store's chain hash at the signal bar);
  - the seal SHA, the fingerprint digest (§5), the Python version, `logged_at`.

**Torn writes** (WF `read_chain`, `cycle_core`, `drop_torn`):
- Every chain line ends with a newline. A worker killed during `commit` (the launcher kills it at 120 s) can leave an
  UNTERMINATED last line. Those bytes were never part of the chain.
- The read and `anchor` refuse such a file; `status` names it as pending. Nothing is appended after it: the torn bytes
  would join the new line into a terminated, broken one, and that refuses forever.
- The next cycle drops it, and only it:
  - under each file's writer lock (WF `_flock`), so a live writer is never cut;
  - only if the bytes after the last newline are exactly the planned ones, with no newline among them;
  - after logging them in `data/live/forward/wyckoff-wc15/repairs.jsonl`, hash-chained: the file, the offset, the records
    and head that remain, the bytes and their sha256.
- One cut can go unlogged. A worker killed after cutting `repairs.jsonl`'s own torn tail, and before appending the new
  records, leaves that cut without a record. Those bytes were an incomplete repair record. The drops it described were
  not done, so the next cycle plans and logs them (WF `drop_torn`).
- A terminated line that does not verify is never dropped. It refuses every step, as before: collection stops
  (`last_cycle.json`, the cycle log) until a person looks. It is evidence, not a torn write.
- Nothing is lost. Lines the killed worker appended whole stay. The scan cache is written last, so the next cycle
  appends the rest again and re-detects a dropped event; its later `logged_at` shows in the lag (§8).
- Tests: `test_an_unterminated_last_line_is_dropped_and_logged_and_a_terminated_one_never`,
  `test_a_live_writer_is_never_cut_and_the_repair_log_heals_itself`.

**Anchors.** `wyckoff_forward.py anchor` appends the chains' lengths and heads to
`docs/experiments/wyckoff-forward-wc15/anchors.jsonl`. The coordinator commits it monthly.
- The read takes the anchors from **git history**, not from the file on disk: every line ever committed, on any branch
  (WF `committed_anchors`). A later commit that deletes or edits a line does not remove its pin.
- The read refuses if the file on disk differs from HEAD's (an uncommitted anchor pins nothing), or if any anchored head
  is no longer on its chain (WF `verify_anchors`).
- Anchors are not required. The read reports how many it verified and the last one's commit date. With none, it says
  the log's timing (`logged_at`, the lag) is unanchored.
- `anchor` writes under the file's lock and fsyncs. It refuses a file that does not end with a newline, or that holds a
  line that is not an anchor record (WF `anchor_lines`). So a new line never joins a torn one.
- A committed line that is not an anchor record refuses the read, naming its commit. Git keeps it, so it is evidence,
  like a terminated chain line that does not verify. Commit `anchors.jsonl` only after `anchor` printed its new line.
  Test: `test_an_anchor_never_joins_a_torn_line_and_a_committed_non_record_refuses_by_its_commit`.

## 5. The code fingerprint: pinned by commit, not by freezing the repository

**Problem.** EW's guard needs all 52 CODE files byte-identical to R0 (EW:111-126). That will not hold for months. Other
studies will edit `instruments.json`, `real_costs.py` and more. Another session will change `scripts/wyckoff_rules.py`
(§1 scope).

**Design.**
- **Pin the code by its commit.** `cycle` and `read` never run the working tree. They run WF from a read-only `git
  archive` extract of the seal commit, `data/live/forward/wyckoff-wc15/code/<sha>/` (WF `materialize`), in a fresh
  interpreter with `-E -s -B` (WF `_worker_cmd`). After the seal, every other file of the repository may change.
- **The fingerprint IS the scope (§1).** It pins the engine R0 and R1 ran. A later change to a fingerprinted file -- for
  example the pending `scripts/wyckoff_rules.py` semantics change -- cannot enter WY-F1: before the seal `r0_drift`
  refuses the fingerprint, and after it every cycle and look verifies the extract against the fingerprint and runs it.
  The e2e run of 2026-10-04 checks both: a fingerprint on a commit that changed `scripts/wyckoff_rules.py` refuses, and
  after the seal a cycle runs the sealed extract while that file differs in the working tree (§15).
- **What the extract holds** (WF `SNAPSHOT_ROOTS`): `scripts/`, `docs/architecture/`, `data/history/costs/`, the 10
  symbols' 15m history, the R0 record, the fingerprint, the sealed file, and the two MT5 adapter files that
  `docs/architecture/providers.json` names. `scripts/providers.py:63` refuses the registry when a named adapter file does
  not exist.
- **The narrow fingerprint.** `docs/experiments/wyckoff-forward-wc15/fingerprint.json`, committed in the seal commit. It is
  what the forward path actually runs, traced on a synthetic canary through every step (store init, live append, scan,
  resolve with the log-only fields and the HTF gate, both looks' read core with the export check):
  - `exec`, 17 files whose functions run: WF, EW, `scripts/wyckoff_rules.py`, `scripts/backtest-methods.py`,
    `scripts/real_costs.py`, `scripts/research/edge_census.py`, `scripts/history_store.py`, `scripts/instruments.py`,
    `scripts/mt5_time.py`, `scripts/normalized.py`, `scripts/providers.py`, `scripts/broker_symbols.py`, and the HTF
    gate's five: `scripts/live_rules.py` (the bias reader), `scripts/ict-scan.py`, `scripts/structures.py`,
    `scripts/htf_context.py`, `scripts/i18n.py` (§6);
  - `load`, 19 modules imported only (EW's import chain);
  - `data`, the configs and cost tables opened, R0, and the 127 sealed 15m history files of the 10 symbols;
  - real_costs' `price_ref` per symbol, the canary's digest (an exact and a derived part, below) and the time-zone pin
    (below).
  - 17 executed files against the re-test's 52 frozen ones; 15 of the 17 are in the frozen list, the other two are WF
    and `scripts/broker_symbols.py` (a blob of R0's `git_head`). The HTF gate's methods are pinned in WF
    (`HTF_METHODS`, §6), so the forward path never reads the live automation config.
  - **The canary runs the HTF gate on a real window** (lead decision 2026-10-04, §14 item 14; review item 5). The first
    canary had 323 1H bars at its signals; the gate's live window is 480 (`scripts/live_rules.py:83`,
    `automation.SCAN_WINDOW["1H"]`), so every canary gate read "unknown" and the gate's four files were only imported,
    never executed. The statement "exec, 13 files ... every step" was false: a real store with 90 days of warm-up runs
    them on every resolve, and neither the canary digest nor `extract_check` covered the gate. The canary's prefix is now
    2000 bars: 523 1H bars at each signal, the bias path runs (a real "short" bias, `htf_gate` False, never None), the
    four files are `exec`, and the canary digest and `extract_check` cover the gate. A traced probe of 240 gate calls
    over six synthetic regimes (trend, range, sine, spikes) opened no file outside the fingerprint. Tests:
    `CanaryGate`, `test_the_fingerprint_is_the_narrow_executed_set_and_inside_the_extract`.
- **Every cycle and look** (WF `worker_cycle`, `worker_read`):
  1. verify every fingerprinted file in the extract (refuse on any difference);
  2. require the extract's `fingerprint.json` to be, byte for byte, the seal commit's (`git cat-file`, WF
     `require_committed_fingerprint`). Git is the trust root: an extract rebuilt with a fingerprint that matches its
     own files is refused;
  3. require the seal commit to have ONE parent, the commit the fingerprint was taken at (`git_head`), and to add
     exactly the sealed file and the fingerprint (WF `_require_seal`);
  4. require the pinned Python minor version (below);
  5. trace the run;
  6. refuse to write when it executed, loaded or opened a file the fingerprint does not name (WF `check_touched`), or
     opened a file of the live tree outside its inputs and outputs, or imported a module from it (WF `check_outside`).
  Every record carries the fingerprint digest. A look refuses records made under another digest or seal.
  Every worker also requires the sealed time-zone instants (below).
- **Numbers: no look depends on a last-ulp value of the OS library** (lead decision 2026-10-04, §14 item 10; review
  blocker 1). Python's `math` module takes `erfc`, `exp`, `log`, `lgamma`, `sin` and `asin` from the operating system's C
  library (on this Mac `/usr/lib/libSystem`). `brew pin python@3.14` pins Python, not macOS. The first design hashed
  p-values and boundaries bit for bit (the canary digest, the look-1 commitment) and compared look 1's boundary with
  `!=`; one macOS update that moved any of them by one ulp would have made every look refuse for three years, and
  nothing could be fixed after the seal. Now:
  - **Exact:** every scored row (R, placebo, excess, cost), every count and label, the log, the stores. The detector,
    the walk, the placebo draw and the cost use only `+ - * /`, comparisons and `sqrt`, which IEEE 754 rounds exactly on
    every platform. They are hashed as they are.
  - **Rounded:** every DERIVED float that enters a hash, a commitment or a comparison -- the summary's p-values, bounds,
    means and standard errors, the boundaries (`t`, alpha, `z`, rho) -- is rounded to 10 significant digits (WF `sig10`,
    `SIG_DIGITS`): Python's own correctly rounded formatting (`'%.9e'`), no OS function, the same on every platform. 10
    digits is 1e-10 relative: far above a few ulps (1e-16), far below any difference that matters.
  - **Ties:** a derived float within 1e-12 relative of a rounding midpoint (about 1 in 130) verifies under either
    rounding (WF `tie_variants`, `TIE_REL`; at most 12 such floats in one body, so at most 4,096 digests). So a drift of
    up to about 4,500 ulps can never change what verifies.
  - **Compared with a tolerance:** look 2 recomputes look 1's boundary from its recomputed count and compares it with
    the committed one by `math.isclose(rel_tol=1e-9)` (WF `boundary_matches`); look 2's own boundary is computed from
    look 1's COMMITTED floats. The pass test compares the rounded p with the rounded threshold (WF `crossed`).
  - **The canary** hashes its exact part (the log's records, each look's rows, label and sample) as it is, and its
    derived part (each look's summary and boundary, and a fixed 24-row statistic over 12 weeks that runs the Student-t
    tail, which the canary's own ten same-week events cannot) rounded. A look accepts the sealed digest when the
    recomputed one is among the tie variants (WF `canary_verifies`). The look-1 commitment (`statistic_sha256`) is built
    the same way (WF `statistic_sha256`, `statistic_verifies`).
  - **What stays OS-dependent, disclosed (§11):** the derived floats themselves differ by ulps between systems, so a look
    record's p-values can differ in the 16th digit from the same look run elsewhere. The verdict does not, except for a
    p within 1e-10 relative of its threshold (a probability of about 1e-10). A library change that moves a value by more
    than 1e-9 relative (another algorithm) still refuses every look through the canary; the pin cannot prevent that.
  Tests, class `Numbers`: one ulp on a derived float never changes what a commitment verifies (3,000 random values, both
  directions); a float on a rounding midpoint verifies under either rounding; a changed ROW value (one ulp) never
  verifies and a real change of a derived float does not either; the Student-t p one ulp off still verifies; the
  boundary within `isclose`; a look 2 over a look 1 made under an ulp-different `norm_cdf` runs, and over one whose row
  moved by an ulp it refuses; the canary digest survives an ulp and refuses a 0.1 % change.
- **Time zone: pinned by behaviour** (lead decision 2026-10-04, §14 item 17; review note 8). Server days (`prev_dense`, a
  decision field), placebo slots and cost hours use America/New_York's DST rules (`ZoneInfo`, from the OS time-zone
  database; the extract holds no `tzdata` package and the tracer ignores files outside it). The fingerprint records
  America/New_York's 12 DST transition instants of 2025-2030 and the 12 of the FTMO server zone built on them (EET-sized
  steps at the same instants), as computed at the seal (WF `tz_pin`; the fingerprint's `tz`, part of its digest). Every
  cycle and look recomputes them and refuses on any difference (WF `require_tz`). The pin is the behaviour, not the file
  bytes: a database update that changes no instant in those years changes nothing. The study ends by 2030 at the latest
  (never-due close, seal + 48 months). Tests: `TimeZonePin`, `test_a_fingerprint_whose_time_zone_pin_differs_cannot_run`.
- **Each look runs in a FRESH extract**, rebuilt from git at `code/<sha>.read/` (WF `cmd_read`, `materialize(fresh=True)`),
  never in the cycles' cached one.
- **Before sealing** (WF `cmd_fingerprint`):
  - hashes are taken on committed bytes only. The bytes on disk must be the git blob (WF `_require_clean`), which also
    catches a `core.autocrlf` checkout (`docs/plans/2026-09-20-windows-migration.md` §5);
  - **the measurement must be R1's** (WF `r0_drift`). Every fingerprinted file that R0's `meta.code_sha256` names must
    have that hash. Every other one (the FTMO cost tables, `scripts/broker_symbols.py`, `scripts/method_purity.py`)
    must be the blob of R0's `meta.git_head`. Exempt: WF, the R0 record and the 15m history (a later export replaces it,
    §12 step 3). Otherwise "RT §5, unchanged" (§7) would be false. Re-checked on 2026-10-04 with the 10 symbols and the
    HTF gate on the lengthened canary (17 executed files): `r0_drift` is empty;
  - the extract is built from HEAD and the canary runs in it alone, in a fresh process. Its digest must equal the working
    tree's (WF `extract_check`). This check found a real defect in the first version of this code: the extract lacked
    the `.mq5` adapter files, so every cycle would have failed after the seal. A committed test repeats it on a
    throwaway clone (`ExtractCheck`).
- **The interpreter is pinned, by a stable versioned path** (WF `interpreter_pin`, `stable_interpreter`).
  - The fingerprint records `sys.executable`, its real path and its version. Every worker is started with that command,
    never another Python (WF `_interpreter`).
  - The sealing run refuses a command that a patch upgrade would delete or re-point. It must be absolute and named
    `python<minor>` (`python3` follows the package manager's default minor). No part of it may name a patch release
    (`3.14.5`) or be Homebrew's `Cellar`. It must also run this very Python.
  - On this Mac, `sys.executable` is `/opt/homebrew/opt/python@3.14/bin/python3.14`, also when launchd's
    `/opt/homebrew/bin/python3` starts the process. Brew keeps that link on 3.14 across patch upgrades. The real path,
    `/opt/homebrew/Cellar/python@3.14/3.14.5/...`, goes with the next patch upgrade: it is recorded, never run.
  - **Python stays pinned from the seal to the end** (owner decision 2026-10-04, §14 item 6): the coordinator runs
    `brew pin python@3.14` at the seal (§12 step 5), so `brew upgrade` skips it (`brew help pin`) and each look runs
    under the sealed release. Homebrew warns that packages needing a newer version of a pinned formula may not install or
    run. It is unpinned only after WY-F1 ends (§12 steps 11-13).
  - **A patch upgrade anyway (3.14.5 -> 3.14.6) keeps collecting.** A look's canary still refuses any numeric change
    (its digest leaves the version string out). If Homebrew removed the sealed release and a patch changed the canary's
    digest, no look could run any more: INVALID. The pin prevents that.
  - **A minor change (3.15) refuses loudly** (WF `require_interpreter`). Every cycle FAILS, `last_cycle.json` records
    it, the next `spawn` puts it in the cycle log, and `status` flags the interpreter. A missing command fails the same
    way. Nothing is collected under another minor version.
  - Tests:
    - `test_the_pin_names_a_stable_versioned_interpreter`;
    - `test_a_patch_upgrade_keeps_collecting_and_a_minor_change_refuses_loudly`: shim interpreters present this Python
      as 3.14.6 and as 3.15.0, and run the whole forward path in an extract;
    - `test_a_minor_python_change_fails_every_cycle_loudly`.
- **Not pinned.**
  - The launcher: `spawn`, `cycle`'s seal lookup and `status` run from the working tree. They decide nothing. The worker
    in the extract checks everything.
  - The bridge. Its bars are data, hashed into the chain and checked against a later history export (§8).
  - The operating system's math library and time-zone database. They are held by rounding and by behaviour (above), not
    by bytes. A change of either beyond those bounds refuses the cycles and looks loudly; it never changes a result
    silently.

## 6. Resolve, log-only fields, and no interim look

- **Resolve** (WF `resolve_record`). Once an event's exit is known (stop, target, or 96 bars), a `resolve` record is
  appended to the log: entry at the next open, skip when that open is at or beyond the stop or the target, EW
  `walk_from` under `walk_opts` (EW:920-941). Gross R only. Placebo and cost need the whole look window; they are
  computed at a look only.
- **Log-only fields** (WF `LOG_ONLY_KEYS`; lead decision 2026-10-04, §14 item 7). Every resolve record also carries,
  None where they do not apply:
  - `mfe_r`, `mae_r`: the highest high above and the lowest low below the entry, over the walk's own bars (entry bar to
    exit bar), in R of the planned risk; `bars_to_mfe`: entry bar = 0 to the first bar at that high (WF `trade_path`);
  - `planned_rr`: (target - entry) / (entry - stop) at the entry open;
  - `spread_r_entry`: the round-trip spread priced at the entry hour, median and p90, no night held (`real_costs.cost_r`
    with the entry time at both ends, RT's cost profile; WX's X0 convention; WF `entry_spread`);
  - `htf_gate` (and `htf_gate_error`): the ICT HTF gate at the signal, as the ablation's A3 arm applies it
    (`scripts/research/wyckoff_ablation.py:152`): `scripts/backtest-methods.py:894` `htf_bias_gate`, imported, never
    modified, on the next rung (1H), decision time = the signal bar's CLOSE, with the engine's base options and `htf` on,
    and the bias methods the engine's scan resolves for RT's seven symbols (`scripts/backtest-methods.py:1189`
    `resolve_methods`: market "cfd", `("ict",)` on 2026-10-04), pinned in WF as `HTF_METHODS`. Its 1H bars are built from
    the store's own 15m bars up to the signal bar, the hour that bar does not complete left out (WF `htf_candles`,
    `htf_gate`). An exception is logged as `htf_gate_error`, never raised: a log-only field cannot stop collection.
- **They use no bar beyond what the resolve already reads**: the walk's bars for the trade path, the store up to the
  signal bar for the gate, the cost tables for the spread. Test
  `test_the_log_only_fields_use_no_bar_beyond_the_walk_and_the_gate_none_after_the_signal`: a store cut right after the
  exit, or with every later bar changed, logs the same record; bars after the signal leave the gate unchanged. Test
  `test_the_htf_gate_is_the_engines_own_function_as_the_a3_arm_applies_it` pins the call and the methods.
- **They are never tested in WY-F1** and never reach `status` or a cycle summary (test
  `test_the_log_only_fields_never_reach_status_or_a_cycle_summary`). Each look recomputes every logged resolve from the
  stored bars, log-only fields included, and reports the mismatches (WF `log_only_check`); that is not a WY-F1 check.
- **No interim look, by procedure.** Nothing technical can stop one. The bar stores on disk show every outcome to anyone
  who draws the chart, and the log holds each resolved gross R as tamper evidence (each look checks every scored trade
  against it). Nothing records who opens these files, so a look cannot disclose a peek.
- What protects the looks is that a peek cannot change them: the cutoffs are outcome-blind and fixed now (§7), and the
  sample, the placebo, the cost and the boundaries are mechanical. A peek could only tempt the owner to stop or change
  the study. That is not allowed after the seal (§14).
- **Look 1 is blinded unless it passes** (§7): its record shows no estimate and nothing from which the number of
  resolved trades could be derived (lead decision 2026-10-04, §14 item 16; review note 7: the first record kept the log's
  record count, and records minus events is the resolve count that `status` hides on purpose). `blind` now keeps an
  allowlist (WF `BLIND_KEEP`): the log's head hash only, no anchored log length, no repair list, no log-only
  recomputation. Test `test_a_blinded_look_one_gives_no_resolve_count_and_no_estimate`. So the months between the looks
  are not read with look 1's mean in view.
- The tools do not show outcomes in passing (tests `test_status_never_prints_an_outcome`,
  `test_status_counts_the_rule_from_the_entry_open_as_the_read_does`):
  - `status` prints counts only. It shows no resolve count: a resolve a few bars after its entry is a stop or a target.
    It shows events entered and events past their longest walk (entry + 96 bars), which are times, not outcomes. The
    counted events come from the entry open, as a look counts.
  - The cycle summary (the cycle log, `last_cycle.json`) counts new bars and new events, and lists stalled symbols. Never
    resolves.
  - Repairs (§4) appear by file name only, in `status` and in the cycle summary. The dropped bytes can hold an R; they
    stay in `repairs.jsonl`.

## 7. The read: two looks, rule and measurement (fixed now)

**What is fixed now** (WF constants; test `test_the_read_rule_is_the_fixed_one`):
- one-sided alpha **0.10 in total** over both looks (`ALPHA`), RT's forward bar (RT:245; EW `FORWARD_P`, EW:168);
- **two looks**: look 1 at seal + 12 calendar months, look 2 (final) at seal + 36 calendar months (`LOOK_MONTHS`,
  `look_plan`). Lead decision 2026-10-04 (§14 item 1); it replaces "100 events or 12 months, read once";
- **Lan-DeMets O'Brien-Fleming-type spending** (Lan and DeMets 1983, Biometrika 70:659-663; WF `obf_spend`):
  alpha(t) = 2 (1 - Phi(z_{1-alpha/2} / sqrt(t))), alpha(0) = 0, alpha(1) = alpha;
- the information unit is the **event**: the events a look scores. The planning rate is 14 events a year (§9), so 28
  events are planned between the looks (`PLAN_RATE`, `N_REST_PLAN`);
- the decision statistic and its test: RT §5, unchanged (below);
- the look's export of ALL 10 symbols (below), the per-look fallback for a symbol that is still incomplete (3 months,
  `GRACE_MONTHS`, only when at least 5 of the 10 are complete, `DROP_MIN_COMPLETE`), and the never-due close (seal + 48
  months, `NEVER_DUE_MONTHS`; procedural);
- the rounding of derived floats (10 significant digits, §5).

**How each look's boundary is computed** -- from the ACTUAL event counts, all outcome-blind:
- **Look 1** (WF `look1_boundary`). n1 = the events look 1 scores (its rows; a skip -- entry beyond stop or target, no
  ATR20, no placebo -- is outcome-blind). t1 = n1 / (n1 + 28). alpha1 = alpha(t1). z1 = Phi^-1(1 - alpha1). With
  n1 = 0, alpha1 = 0 and look 1 cannot pass.
- **Look 2** (WF `look2_boundary`). n2 = the events look 2 scores; n12 = those also scored at look 1 (n1, unless a
  symbol read at look 1 is dropped at look 2). rho = n12 / sqrt(n1 n2). z2 solves P0(Z1 < z1, Z2 < z2) = 1 - alpha, where (Z1, Z2) is
  standard bivariate normal with correlation rho (WF `bvn_lower`). Look 2 spends alpha - alpha1.
- For normal z statistics the false-pass probability over both looks is exactly 0.10 for any n1 and n2: a slow or fast
  first year moves alpha1, and look 2 takes the rest at the correlation the counts actually give. **The registered
  statistic is not a normal z statistic, so its level is not exactly 0.10** (below; corrected 2026-10-04, §14 item 15).
- At the planning counts (14, 42): look 1 passes at a nominal one-sided p < 0.0044 (z 2.62), look 2 at p < 0.0986
  (z 1.29), as WX §12.2 (b) has them. Other counts: (8, 32) 0.0005 / 0.0999; (20, 53) 0.0108 / 0.0962; (4, 46)
  < 0.00001 / 0.1000; (30, 42) 0.0222 / 0.0975.
- **Checked** (tests in `TwoLooks`):
  - `test_the_spending_and_both_boundaries_match_an_independent_computation`: the bivariate normal against an
    independent Simpson-rule integral; the classic one-sided 0.025 design at t = 0.5 and 1 gives 2.963 and 1.969; the
    total false-pass probability is 0.10 for steady and unsteady counts;
  - `test_the_type_one_error_stays_at_alpha_under_a_non_steady_event_rate`: under the null, with Poisson counts that do
    not arrive at the planning rate -- a slow first year (4 events, then 50) and a fast one (30, then 6) -- the rule
    falsely passes 0.103 and 0.101 of 30,000 runs each (z statistics; within 3.5 standard errors of 0.10), and 0.1005 of
    8,000 runs with the registered Student-t p-value on INDEPENDENT NORMAL per-event values. That is the normal model,
    nothing more. The boundaries are right for the model they assume: the review also matched them to 1e-15 for five
    other count pairs.
- **Approximation, disclosed -- the registered statistic does NOT hold the level** (lead decision 2026-10-04, §14 item
  15; review item 6; the earlier text said "0.100-0.101 on normal values, conservative on skewed R values" and "exactly
  0.10 for any n1 and n2"). The boundaries are exact for normal z statistics whose information is proportional to the
  event count and whose events are independent. A look applies them as nominal one-sided p thresholds to RT §5's p
  (CR1 by ISO week, Student-t with G - 1 df). That statistic, kept as RT §5 has it, is not a normal z. The two looks draw
  their placebos from different windows, so the looks' correlation is approximate too. The review simulated the null with
  the production statistic, boundaries and pass test: 20,000 runs per case, 14 events a year, values with mean 0, look 2
  re-scoring look 1's events with a placebo mean that differs by N(0, 0.05^2); the fix round reproduced the table to four
  digits on 2026-10-05, with the corrected code (a reduced run is `TypeOneError`).

  | null | false pass over both looks | at look 1 (nominal 0.0044) |
  |---|---|---|
  | independent normal values | 0.1025 | 0.0049 |
  | same-week bursts (40 % of the events in bursts of 2-4, as the US indices fire together; within a burst a value is shared with probability 0.6), normal | 0.111 | 0.008 |
  | the same with 60 % in bursts, shared with probability 0.9 | 0.117 | 0.010 |
  | heavy tails (t with 3 df), bursts | 0.113 | 0.006 |
  | left-skewed R (win 0.5 with probability 2/3, lose 1 with 1/3), independent | 0.122 | 0.012 |
  | left-skewed R, bursts | 0.136 | 0.019 |
  | slow first year (4 events, then 25 a year), bursts, normal | 0.107 | 0.0002 |
  | fast first year (30 events, then 3 a year), bursts, normal | 0.108 | 0.026 |
  | right-skewed R (R:R 1-5), bursts | 0.074 | 0.002 |
  | mixed R:R 0.5-4, bursts | 0.077 | 0.002 |

  One read at 36 months at alpha 0.10 gives 0.097 (independent normal), 0.105 (bursts), 0.112 (left-skewed,
  independent) and 0.081 (mixed R:R, bursts): the second look adds about 0.006-0.010 to the statistic's own error.
  - **What this means.** With same-week correlation (US500, US30, USTEC and DE40 share events), heavy tails and left
    skew, the false-pass rate is 0.11-0.14, not 0.10, and at look 1 up to 0.019 against a nominal 0.0044 (1 in 53, not 1
    in 230). With right-skewed R it is lower (0.074-0.077). The R of this trade is skewed by construction: it targets
    `tr_hi` from a stop under the spring, and its direction depends on the planned R:R, which the log records
    (`planned_rr`, log-only). So the level of the registered rule is about 0.07-0.14 depending on the shape of R, and
    0.10 is its level only for independent, symmetric values.
  - **The rule is kept as registered.** RT §5's statistic is not changed (decision 2026-10-04: keep it); the inflation is
    disclosed here and in §10, §11. A PASS therefore carries a false-pass probability that may be up to about 0.14, not
    0.10; a NOT PASSED is, if anything, more conservative than stated for right-skewed R.

**Decision** (WF `crossed`, `read_core`):
- At each look: **PASS iff the mean net excess on the primary cost line is > 0 and its one-sided p is below the look's
  nominal threshold.**
- **Look 1:** PASS is the verdict and ends WY-F1. Otherwise **CONTINUE**. Look 1 never says NOT PASSED.
- **Look 1 is BLINDED unless it passes** (WF `blind`, `look_record`, `statistic_sha256`). Its record holds the
  decision facts (n1, t1, alpha1, z1, the threshold, CONTINUE) and `statistic_sha256`, the sha256 of its scored rows and
  summary. No estimate, no p, no row, on disk or on screen (WF `look_line`). Tests:
  `test_a_look_one_that_does_not_cross_is_blinded_and_look_two_reproduces_its_commitment`,
  `test_the_look_files_round_trip_a_blinded_look_one_into_look_two_and_a_pass_ends_it` (the written files: look 2 reads
  the blinded look-1 file back, and its disclosed look-1 rows reproduce the committed sha256).
- **Look 2** runs only on look 1's COMMITTED record (git HEAD, equal to the file on disk), made under this seal and this
  fingerprint, and only after a CONTINUE (WF `committed_record`, `require_prior`; test
  `test_look_two_needs_look_ones_committed_continue_record_of_this_seal`). It recomputes the look-1 statistic on look 1's
  cutoff and symbols and refuses (INVALID) unless it reproduces the committed sha256 (rows exactly, derived floats to 10
  significant digits, §5) and boundary (`math.isclose`, 1e-9), and unless that statistic does not cross the committed
  boundary (look 1 said CONTINUE). Look 2's boundary is computed from look 1's COMMITTED floats. Then it discloses
  look 1.
- **Look 2:** PASS or **NOT PASSED**. NOT PASSED exists only at look 2.

**Cutoffs and the export** (WF `due`, `export_problems`, `read_core`; lead decisions 2026-10-04, §14 items 12 and 20):
- Each look's cutoff is fixed by the seal alone: seal + 12 months (look 1), seal + 36 months (look 2). Every symbol must
  have 96 bars after the cutoff, so every walk is complete.
- **Every look needs a FTMO 15m history export of ALL 10 symbols**: taken (`_exported_at_utc`) at or after the close of
  the last bar a read symbol's window needs (its cutoff bar + 96 bars), imported (`scripts/import-mt5-history.py`), and
  taken INTO the stores by one `cycle`. A look refuses while an export is missing, too early, unusable, or would still
  extend a store (WF `export_problems`). So no symbol is left out by not exporting it, and no symbol is read or dropped
  on the strength of an export it did not get. A symbol the broker no longer offers blocks the look; that ends in the
  never-due close below.
- **A symbol complete through the cutoff after that export is READ**, whether its live file was alive or not. JP225 and
  AUS200 (no live file today) are filled from the export, and every event of theirs is logged LATE (up to about 12
  months) and disclosed: the late-logged count and ids, the lag's median and maximum, the events whose window holds
  history-sourced bars (§8). Their detection is mechanical and replayed, so they stay in the sample. Whether a stalled
  symbol is read is decided by the data the broker has, not by anyone's choice. Tests:
  `test_a_stalled_symbol_is_filled_by_the_looks_export_and_read_with_its_events_late`,
  `test_every_look_needs_an_export_of_all_ten_symbols_taken_after_the_window_and_into_the_stores`.
- **Otherwise it is DROPPED whole**, and only by the registered fallback, per look (option A, §14 item 4; lead, item
  20). If not every symbol is complete through the cutoff after the export, but some symbol is complete through that
  cutoff + 3 months (the look's time reference is data, never a wall clock), **and at least 5 of the 10 symbols are
  complete through the cutoff**, every symbol not complete through the cutoff is dropped whole from that look: all its
  events leave that look's sample before any walk or cost is computed. With fewer than 5 complete the look WAITS, however
  long: a look on a handful of symbols is not a look at this cell. A symbol dropped at look 1 can be back at look 2. The
  rule reads data times only, never a wall clock or an outcome. Each look lists the dropped symbols. Test
  `test_a_symbol_stalled_three_months_past_a_looks_cutoff_is_dropped_whole_from_that_look` (9, 6 and 5 complete drop; 4,
  1 and 0 wait).
- **Never due.** If look 2 is still not due 48 months after the seal, WY-F1 closes with no verdict (INVALID: never due).
  **That close is procedural**: `status` shows the date (`never_due_close`); the coordinator records it in the ledger's
  study entry (§13); the code does not refuse a later look, and a look that is due later still computes (test
  `test_the_never_due_close_is_procedural_and_the_code_does_not_refuse_a_later_look`). No partial read, no new rule. A
  look-1 CONTINUE stays blinded for good.
- A look before its cutoff refuses **before any walk, placebo or cost is computed** (test
  `test_an_early_look_refuses_before_any_walk_or_cost_is_computed`). The log already holds the resolves' gross R (§6);
  the test proves a look computes nothing from them early, not that no outcome exists.
- **Reported, not decisive:** the other three cost lines, the 95 % upper bound, AGAINST (look 2: two-sided p < 0.05 with a
  negative mean), below delta (upper bound < 0.20R), splits by symbol, group, type and set (`rt` / `added`), the log lag,
  the late-logged count and ids, the dropped symbols, the exports used (time and file hashes), every bar difference
  between store and export (§8), the revision records (§4), the anchors verified, the repairs (§4: file, offset, size,
  sha256), the log-only recomputation (§6).
- Output: `docs/experiments/wyckoff-forward-wc15/wyckoff-forward-look1.json` and `...-look2.json` (WF `LOOK_OUT`).
  Never overwritten: a look whose file exists, or has git history, refuses. A look also runs ONCE when its file is gone:
  see the look attempt (§8 item 8).

**Measurement: RT §5, unchanged.**
- Scored with EW `score` (EW:999) and `summarise` (EW:1179), the functions R1 used.
- Gross R from the walk. A gap can lose more than 1R.
- **Placebo.** Up to 200 entry bars from the same forward window, same symbol, same server-clock slot, previous day
  dense. Each gets the event's stop and target distances in ATR20 multiples. Seed sha256(`WY-P0|sym|tf|signal_time`).
- excess = R - mean(placebo R). net = excess - cost.
- **Cost.** `real_costs.cost_r` with `ftmo_demo_2026_09_relspread`, the server-table hour frame (asserted, EW
  `_require_hour_frame`). The cost tables and `price_ref` are the sealed ones in the extract. A look refuses if
  `price_ref` differs from the fingerprint's.
- **Primary line:** median spread, today's swap.
- **Statistics.** CR1 by ISO week of the signal bar, Student-t with G - 1 df, one-sided in the book's direction.
- **Window.** An event, or a placebo bar, belongs to a look iff its signal closes at or after the seal and its entry bar
  closes by that look's cutoff (WF `member`, EW `in_window`). Walks run to their own exit, which must be in the store.

## 8. The look's validity checks and point in time (CLAUDE.md §8, §37, §38)

**A look is INVALID and writes nothing unless all hold** (WF `read_core`, `worker_read`):
1. every chain intact and ending with a newline (a `cycle` drops an unterminated last line first, §4); every committed
   `anchors.jsonl` line an anchor record, and every anchor (from git history) on its chain; every record made under
   this seal and this fingerprint;
2. the full replay of every window equals the log: nothing missing, nothing extra, no decision field changed;
3. the truncation probe finds 0 violations, and checks at least one event when the sample is not empty;
4. the look's FTMO 15m history export of ALL 10 symbols (§7: taken after the cutoff + 96 bars and taken into the
   stores) confirms the forward bars, **both ways, bar by bar** (WF `history_check`, `export_replay`, `export_walks`,
   `history_problem`). Window = the store's bars from the seal to 96 bars after the cutoff bar. Per read symbol:
   - the export reaches the window's last bar (an export taken too early checks nothing after its end);
   - it holds >= 95 % of the window's store bars, and >= 99 % of those at the same prices;
   - the store lacks <= 1 % of the export's bars inside the window (`HIST_MISSING_MAX`). A hole the live file skipped
     is MISSING, not EMPTY (CLAUDE.md §20);
   - **the detector replayed on the export** (lead decision 2026-10-04, §14 item 19; review note 10) over the store's span
     gives the SAME event ids as the log for the events whose signal bar closes in [seal, cutoff], and for each the same
     decision fields (not the store's line index, window hash or chain hash). The first check passed a doctored bar that
     suppresses an event: the event is not in the log, so it has no span, and one bar differing in about 60,000 is 99.998
     % agreement. Now it is caught, in the store or in the export (`only_in_export`, `only_in_log`, `changed`);
   - **inside an event's span** (its 300-bar window to 96 bars after its entry, the longest walk) a difference is
     tolerated only when it changes no decision field (the replay above) and no trade: each sampled trade walked on the
     export has the same outcome, R, exit time and entry as the store's (WF `export_walks`; an OUTCOME comparison, so it
     runs after the look attempt, item 8, and reports counts, never an R). The first check made the look INVALID on one
     harmless difference inside any of about 40 spans (about 17,000 bars);
   - **every difference is reported** (`differences`): the bar time, its kind (price, the store lacks the bar, the export
     lacks it), the fields that differ, the spans it lies in, and whether a logged revision explains it (§4). No price;
   - the look records the export's `_exported_at_utc` and the sha256 of every file it read;
   Tests, `ExportCheck`: a harmless difference in a span is reported and the look runs; a difference that changes a
   decision, an export that suppresses an event, and a store that suppressed one (caught by the export; the old check
   passed it) are refused; a difference that changes a trade is refused after the attempt.
5. every logged resolve equals the scored trade;
6. the canary (both looks, on synthetic bars) reproduces its sealed digest (exact part exactly, derived part to 10
   significant digits, §5); the extract's fingerprint is the seal commit's; the time-zone instants are the sealed ones
   (§5); the seal commit is one commit on the fingerprinted one, adding exactly the sealed file and the fingerprint; the
   sealed file is committed and clean; the look's file has no history, and the log holds no attempt of this look or a
   later one (item 8);
7. look 2 only: look 1's committed record is a CONTINUE of this seal and fingerprint, and its statistic and boundary
   reproduce (§7);
8. **the look attempt** (lead decision 2026-10-04, §14 item 18; review note 9). The first check for "each look ONCE" was
   that the look's file exists or has git history, so an uncommitted look-1 file could be deleted and look 1 run again
   after filling a dropped symbol (a per-symbol lever). When every outcome-blind check above has passed, and BEFORE the
   first outcome is computed (the export walks, then the sealed §5 measurement), the look appends a chained
   `look_attempt` record to the log: the look, the cutoff, the rule, the symbols read and dropped, the exports' times, the
   output path, the seal, the fingerprint, the time (WF `append_attempt`). From then on the look is SPENT: a second
   attempt refuses (WF `require_no_attempt`) even if the first one's output file was deleted or never written, or the
   first one refused after computing an outcome (a walk that differs, a resolve that disagrees: INVALID). `status` shows
   attempted looks and any spent without a record. The cost: a look that fails an outcome-dependent check ends for good,
   and the coordinator records WY-F1 as INVALID at that look (§13). A look that refuses earlier (an export too early, a
   symbol incomplete, a replay that does not match) leaves no record and may run later. Tests, `LookAttempts`.

A look cites the pre-registration by the sha256 of its text **at the seal** (`git show <seal>:<file>`), plus the current
committed text's hash and every later commit that changed it (errata, disclosed; WF `prereg_record`).

**Point in time.**
- Every decision field is computed from bars that closed by the signal close. Bar-by-bar scans equal the full replay
  (test).
- **Truncation probe** (WF `probe`). Each event is re-detected on the store CUT at its signal bar, with the window
  finding its own pivots. Every decision field must be identical. A detector that reads the next bar is caught (test
  `test_a_detector_that_reads_the_next_bar_is_caught`).
- **Log lag.** A look reports lag = `logged_at` - signal close, its median and maximum. Events logged more than 1 day
  late (a hole or a stalled feed bridged by a history export) are counted and listed as late-logged (WF `LATE_LOG_S`),
  and the events whose window holds history-sourced bars after the seal are counted. They stay in the sample: their
  detection is mechanical, replayed, and replayed again on the export. Both counts are disclosed, also in a blinded look
  1. Test `test_the_owners_case_a_seal_on_history_that_ends_before_the_live_files_then_a_later_export_bridges_it`: four
  symbols bridged late, six on time, all ten read, both looks.
- **Revisions.** The store keeps each bar as first stored, so a decision or a resolve never uses a bar the broker revised
  later; a look lists the revision records and flags the differences they explain (§4). A revised bar that changes a
  decision field or a trade inside a sampled span makes the look INVALID (item 4): the first-stored record then differs
  from what the broker finally holds in a way that matters.

## 9. Power (counts only, before any forward bar)

**Event rate.**
- RT's seven: R3, 2024-03 to 2026-09, 29 placeable events in 2.58 years, about 11 a year (R0 `reads.R3`); R1 gives the
  same rate (63 events in 39.8 symbol-years).
- The added three: about 2.3 a year after 2024-03-01 (WX §12.2 (a), X0, outcome-blind).
- **About 14 events a year in all** (WX §12.3: 35 events in 2.57 years on the ten). Look 1 (12 months): about 14 events,
  8 to 20 (5 % to 95 %, Poisson). Look 2 (36 months): about 42 events, 32 to 53.

**Spread of the net excess per event.**
- 1.4R: RT §13's planning value.
- 2.2R: implied by R1's published line (+0.25, p 0.18, upper bound +0.72: SE 0.28 over 63 events). R1's measured net SD
  was 2.03R (WX §12.2 (b)), so the 2.2 rows are the realistic ones.

**Power, one-sided alpha 0.10 in total.** Single looks: Student-t with n - 1 df (as before). Two looks: normal
approximation with the boundaries of §7 at the planning counts (14, 42); in brackets, the same averaged over Poisson
counts (14 a year). Computed with WF `look1_boundary` / `look2_boundary` (`wyf1fin/power.py` in the coordinator's
scratchpad; counts only):

| SD | true edge | look 1 alone (n 14) | look 2 alone (n 42) | **two looks (n 14 / 42)** | P(stop at look 1) |
|---|---|---|---|---|---|
| 1.4 | +0.25R | 0.25 | 0.44 | **0.45** (0.45) | 0.03 |
| 1.4 | +0.50R | 0.49 | 0.84 | **0.85** (0.84) | 0.10 |
| 2.2 | +0.25R | 0.19 | 0.29 | **0.29** (0.29) | 0.01 |
| 2.2 | +0.50R | 0.31 | 0.57 | **0.57** (0.57) | 0.04 |

- Minimum detectable edge at 80 % power, two looks: 0.46R (SD 1.4), 0.72R (SD 2.2). Look 1 alone: 0.83R / 1.31R.
- Under the null, in the normal approximation: P(PASS) = 0.10, of which 0.0044 at look 1. For the registered statistic
  the simulated false-pass rate is 0.074-0.136 and 0.0002-0.026 at look 1, by the shape of R and the clustering of
  events (§7 table). The powers above are the normal approximation's too; they move with the same shape effects.
- The seven symbols alone (11 / 34 events): two looks 0.40 / 0.27 for +0.25R (SD 1.4 / 2.2). The added three buy about
  0.02-0.05 of power.

**What this means.**
- The two-look rule keeps the 36-month power and adds an early exit for a large edge. Spending 0.0044 at 12 months
  costs almost nothing at look 2.
- At look 1 only a very large edge (about 1R or more) passes. A CONTINUE at look 1 says nothing yet.
- If the true edge is the R1 estimate (+0.25R), WY-F1 most likely ends NOT PASSED at look 2 (power 0.29-0.45).
- So NOT PASSED means "not shown". It does not mean "no edge".

## 10. What each result means for the owner

| Result | Plain meaning | Next step |
|---|---|---|
| **PASS at look 1** | After 12 months, the 15m Spring/Shakeout long beat random entries with the same stop and target, after real FTMO cost, by a margin a fluke reaches nominally 1 time in 230 (p < about 0.0044); simulated, 1 in 125 with same-week clustering and up to 1 in 53 with left-skewed R (§7). | WY-F1 ends. It becomes a forward-confirmed candidate. The owner may then decide to build it as an engine setup in a NEW Trading System version (CLAUDE.md §47), first on demo, with the 2.5R floor and the HTF gate as separate policy layers (RT §9). Nothing goes live from this study. |
| **CONTINUE (look 1)** | Look 1 did not cross its (strict) boundary. Its estimate stays sealed. | Keep collecting to look 2. Nothing else changes. |
| **PASS at look 2** | After 36 months, the same, with the whole remaining alpha. Over both looks a fluke passes nominally 1 time in 10; simulated 1 in 7 to 1 in 14, by the shape of R and the clustering of events (§7). | As PASS at look 1. |
| **NOT PASSED (look 2)** | No edge was shown on the forward bars. At this power it does not exclude +0.25R. | The cell stays unconfirmed. No new variant is tried on history (RT:323). Wyckoff's price-mechanical setups get no further forward stage unless the owner registers a new one (for the changed engine: WY-F2, §1). |
| **NOT PASSED, AGAINST** (reported) | Price kept going through the shake, as on the metals before. | As NOT PASSED; logged for the edge families. |
| **INVALID** (a §8 check failed) | The forward record cannot be trusted (a gap, a rewrite, a broken probe, a bar difference that changes an event or a trade, a look-1 commitment that does not reproduce). | No verdict. The coordinator reports which check failed. Nothing is re-read on other data. A look that failed after its attempt record (§8 item 8) is spent and never runs again. |
| **Never due** (§7) | Look 2 was still not due 48 months after the seal. | WY-F1 closes with no verdict. The ledger records it (§13). |

## 11. Threats to validity

- **Selection (§1).** Winner's curse: the forward effect is likely smaller than +0.25R.
- **Power (§9).** At look 1 only a very large edge can pass; at look 2 power is 0.29-0.45 for +0.25R.
- **The engine changes after the seal (§1 scope).** The pending `scripts/wyckoff_rules.py` change, and any later engine
  change, never enters WY-F1. WY-F1's verdict is then a statement about the OLD detector only, which may no longer be the
  engine the system runs. It cannot license the changed engine. A test of the changed engine is a separate registration
  (WY-F2).
- **The registered statistic does not hold the level (§7, corrected 2026-10-04).** The boundaries are exact for normal
  z statistics; the registered t / CR1 p-value is applied as a nominal threshold. Simulated with the production code:
  0.1025 on independent normal values, 0.111 with same-week bursts, 0.113 with heavy tails, 0.122-0.136 with left-skewed
  R, 0.074-0.077 with right-skewed R; at look 1 up to 0.019 against 0.0044. A PASS carries a false-pass probability of up
  to about 0.14. The statistic is kept as registered.
- **The operating system's libraries (§5).** The math library and the time-zone database are not pinned by bytes. Derived
  floats are rounded to 10 significant digits and the DST instants of 2025-2030 are pinned by behaviour, so an ulp-level
  library change or a database update that moves no instant changes nothing. A library change beyond those bounds
  refuses every cycle or look loudly (never silently). The look records' p-values can differ in the 16th digit from the
  same look run on another system.
- **Revisions (§4).** A bar the broker revises after the store took it stays as first stored and is logged; no decision or
  resolve uses the revised bar. The look checks the store against the final export: a revision that changes a decision or
  a trade inside a sampled span makes the look INVALID.
- **Late logging (§7, §8).** Events of a symbol bridged by an export are logged late (the four indices after the seal,
  JP225 and AUS200 until their live files exist). They are detected mechanically and replayed on the export, and the
  look discloses their count, ids and lag. Late logging cannot move an event, but the log's timing for them proves
  nothing; the committed anchors (monthly) do not cover them.
- **A look is spent by an outcome-dependent failure (§8 item 8).** After the look-attempt record a failed outcome check
  (a trade that differs on the export, a resolve that disagrees) ends that look for good: the price of making a second
  attempt impossible. Early refusals leave no record.
- **Never due is procedural (§7).** The code does not refuse a look after seal + 48 months; the coordinator closes the
  study.
- **A blinded look still says something.** CONTINUE tells everyone that look 1's estimate did not cross its strict
  boundary. That is inherent to any interim look.
- **Costs.** The looks use the sealed 2026-09 spread tables and today's swap, as RT did. Real forward spreads are not
  recorded per bar. A change in FTMO's pricing would not be seen. The added three are cheap (§2), but UK100's mean
  spread proxy (0.23R) is the highest of the ten.
- **Data revisions.** Each look checks the forward bars against a later history export, bar by bar, and replays the
  detector on it (§8 item 4).
- **Clock.** The bridge's measured offset can be wrong after a DST change. A shifted bar appends nothing (§4). A history
  re-export bridges it.
- **Downtime.** A stalled or holed symbol is filled by the look's export of all 10 symbols and READ, its events
  late-logged (§7). It is dropped only if it is still incomplete after that export, once another symbol is complete
  through the cutoff + 3 months and at least 5 of the 10 are complete (§7). JP225 and AUS200 have no live 15m file today
  (§12 step 4); until the owner attaches ExportOHLCV they are STALLED (§4).
- **A deliberate stall.** Someone who peeked at outcomes could stop a symbol's feed to drop it. A look needs an export of
  all 10 symbols, so not exporting one blocks the look instead of dropping the symbol; an export fills a stalled store,
  so only a symbol the broker cannot supply is dropped; at least 5 must be complete; a look cannot be run twice to try
  another export (§8 item 8). Each look lists dropped symbols, and the store shows when its last bar came.
- **The seal date is the committer's clock.** A back-dated seal would show up as large log lags on the first events
  (§8), and the committed anchors pin the history from then on.
- **The tracer sees opens and executions, not `stat()` calls.** `extract_check` covers that gap before sealing (§5).
- **Interim peek.** The bars and the log on disk show outcomes; only procedure prevents a peek (§6).
- **Anchors depend on the coordinator.** Without monthly commits the log's timing is unanchored. Each look says so.
- **A torn write.** A worker killed during `commit` leaves an unterminated last line. The next cycle drops it, logged
  (§4). Only bytes after the last newline can go; a terminated line never does.
- **A Python upgrade.** Python is pinned (§5). If it changes anyway: a patch upgrade keeps collecting; a minor change
  stops collection until Python 3.14 is back at the pinned path. Bars missed meanwhile come from a history re-export
  (§4). A patch that changes the canary's digest makes every later look INVALID once Homebrew has removed the sealed
  release.
- **Log-only fields** (§6) are computed by the sealed code at each resolve. They carry no test here; a later study that
  uses them must pre-register on bars after its own seal.

## 12. Sealing and wiring steps

OWNER = an action in MT5 on the owner's machine. COORDINATOR = a repository or shell action. Nothing here is done by
the drafting session.

1. **Decisions.** Taken and recorded in §14 (2026-10-04). Nothing is open.
2. **Commit** (COORDINATOR) WF, its tests and this draft. Every fingerprinted file must be committed and unchanged on
   disk. **Order with the engine change (§1 scope):** take the fingerprint (step 5) and the seal (step 6) on a commit
   whose fingerprinted files are still R0's. If the pending `scripts/wyckoff_rules.py` change is merged into the
   sealing branch first, `fingerprint` refuses (`r0_drift`: "scripts/wyckoff_rules.py: differs from R0's code_sha256");
   then seal on a branch without it. After the seal the change may land freely: WY-F1 runs its extract.
3. **History: seal on what is committed** (owner decision 2026-10-04, §14 item 9). Nobody waits for a re-export. The
   committed 15m history of the 10 symbols is the sealed history; the stores start from it (seal - 90 days). In the e2e
   run (§15) the history of US500, US30, USTEC and DE40 ends 2026-09-28 16:45Z, before their live files start
   (2026-09-29 15:00Z): the first cycles report a hole for them and flag them NOT ADVANCING (§4). XAUUSD, XAGUSD,
   US2000 and UK100 connect (their stores reach 2026-10-02). AUS200 and JP225 have no live file (step 4). **A later
   export bridges the hole after the seal** (OWNER: ExportHistory.mq5 for the 15m bars; the coordinator added
   US500.cash, US30.cash, US100.cash and GER40.cash to the MT5 export list; COORDINATOR: `scripts/import-mt5-history.py`,
   the commit, then one `cycle`). The cycle takes in the bars after each store's end when the export holds the store's
   last bars at the same prices, and the live file continues. The events the hole hid are logged LATE and disclosed at
   each look (§7, §8); late logging moves no event. Until then the four stores wait. Test:
   `test_the_owners_case_a_seal_on_history_that_ends_before_the_live_files_then_a_later_export_bridges_it`; e2e §15.
4. **Live files** (OWNER). Attach ExportOHLCV to a 15m chart of **JP225.cash** and of **AUS200.cash**. Today
   `data/live/mt5-bridge/` has neither `ohlcv.JP225.cash.15m.json` nor `ohlcv.AUS200.cash.15m.json` (UK100 and US2000 have
   theirs). Without them both are STALLED (§4): nothing is collected from a live file for them. Their stores stay at the
   sealed history until a history export fills them. At each look the export of all 10 symbols fills them and they are
   READ, every event of theirs logged late and disclosed (§7). Attaching ExportOHLCV changes what a look reads by
   nothing; it makes their events timely and the lag small.
5. **Pin Python, then fingerprint** (COORDINATOR; the owner allowed the pin, §14 item 6). Run `brew pin python@3.14`.
   Then, with the stable versioned interpreter (§5), run
   `/opt/homebrew/opt/python@3.14/bin/python3.14 scripts/research/wyckoff_forward.py fingerprint --out docs/experiments/wyckoff-forward-wc15/fingerprint.json`.
   It pins that interpreter: every worker runs it. It refuses, first, a command that a patch upgrade would delete or
   re-point (a `Cellar` path, a patch release in the path) or that is not named `python3.14`. Then it refuses on
   uncommitted bytes, on any input that is not R1's (`r0_drift`) or on a broken extract (`extract_check`). launchd's
   `/opt/homebrew/bin/python3` reports the same `sys.executable` today; the explicit path does not depend on that.
6. **Seal** (COORDINATOR). Copy this file to the sealed name, with "Status: SEALED" and a sealing record (date,
   fingerprint digest, the §14 record). Commit the sealed file and the fingerprint in ONE commit on top of the
   fingerprinted HEAD, with nothing else. That commit is the seal. Every worker checks this shape (§5); a seal commit with
   anything else, or on another parent, collects nothing.
7. **Ledger** (COORDINATOR; §13), by hand, in the next commit, never in the seal commit: the study entry
   `wyckoff_forward_wc15` only. No `oos.periods` entry (§14 item 5). Then run `test_research_ledger`, one module per call.
8. **Wire the cycle** (COORDINATOR; `scripts/forward_cycle.py`). After the demo-tick loop (lines 97-98,
   `for account_id in tick_order(fd.executor_accounts()):` and its `_step`), still inside the `try` (before line 99,
   `finally:`), add ONE line at the loop's indentation:
   ```python
           _step("wyckoff WY-F1", lambda: _mod("wyckoff_forward", "scripts/research/wyckoff_forward.py").cmd_spawn())
   ```
   Add to the docstring list after line 10:
   `5. wyckoff_forward.py spawn   WY-F1 paper log, started DETACHED after the ticks (research; never waited for)`.
   - **Detached, not inline.** In `data/live/forward/cycle.log` (2026-10-04) launchd starts the next cycle about 300 s
     after the previous one ENDS: the last 175 cycle starts are a median 485 s apart (p90 675 s). So every second spent
     inline delays the next demo tick. `cmd_spawn` starts `cycle` in its own session (`start_new_session`, so launchd's
     end-of-job kill of the job's process group does not reach it) and returns at once (CLAUDE.md §40).
   - The `_mod` call sits inside the lambda, so an import error is logged as FAIL by `_step` and cannot raise out of
     `main()`.
   - The child runs at lower CPU priority (`nice 10`). A launcher lock makes a second `cycle` a skip, not a failure.
     Its output goes to `data/live/forward/wyckoff-wc15/spawn.log` (rotated at 1 MB).
   - Before the seal, the child logs "not sealed: nothing collected". After it, if the checked-out branch lacks the seal
     while the stores exist, the cycle FAILS ("collection is PAUSED") instead of pausing silently.
   - The cycle log shows "OK wyckoff WY-F1: 'WY-F1: spawned pid N'". If the PREVIOUS cycle failed, the step is an EXIT
     line with that error, one cycle late. `status` shows the last cycle.
9. Run `python3 scripts/research/wyckoff_forward.py cycle` once by hand (COORDINATOR). It builds the extract. Then run
   `status`: US500, US30, USTEC and DE40 show NOT ADVANCING (the hole, step 3) and JP225 and AUS200 show STALLED (step
   4) until a later export or the live files fix them.
10. **Monthly** (COORDINATOR): `wyckoff_forward.py anchor`. Commit `anchors.jsonl` only after it printed the new line (§4).
11. **Look 1** (seal + 12 months). **Every look needs a history export of ALL 10 symbols** (§7). OWNER: after the
    cutoff + 96 bars (about one trading day after the cutoff; `status` prints the cutoff), re-export the 15m history of
    all 10 symbols with ExportHistory.mq5. COORDINATOR: import and commit it (`scripts/import-mt5-history.py`), run one
    `cycle` (it takes the export into the stores and drops an unterminated last line, §4), run `status` (look 1 due; the
    symbols the hole or a missing live file held back are now complete), then run
    `python3 scripts/research/wyckoff_forward.py read --look 1 --out docs/experiments/wyckoff-forward-wc15/wyckoff-forward-look1.json`.
    The look refuses, naming the reason, when an export is missing, too early, unusable or not yet taken in; such a
    refusal spends nothing. Once its outcome-blind checks pass, the look is SPENT (§8 item 8): run it once, and do not
    delete its file to run it again. Commit the look-1 record (blinded unless PASS) with the study entry's update (§13).
    On PASS, WY-F1 ends: remove the step-8 line and run `brew unpin python@3.14`.
12. **Look 2** (seal + 36 months, only after a committed look-1 CONTINUE). The same, with a fresh export of all 10
    symbols after look 2's cutoff + 96 bars, and `read --look 2 --out
    docs/experiments/wyckoff-forward-wc15/wyckoff-forward-look2.json`. Commit the record with the study entry's update.
    WY-F1 ends: remove the step-8 line and run `brew unpin python@3.14`.
13. **Never due** (seal + 48 months, when `status` shows look 2 not due): record the close in the study entry (§13),
    remove the step-8 line, `brew unpin python@3.14`. The close is procedural (§7): the code would still run a look that
    became due later; the coordinator does not run it.

## 13. Budget and OOS exposure (CLAUDE.md §43, §44)

- One hypothesis, one test (two pre-registered looks of it, alpha 0.10 in total), its own family, m = 1. No other cell
  is collected. No variant. The log-only fields carry no test (§6).
- The forward window is untouched data. Bars before the seal are context only and produce no event.
- **The ledger** (`docs/architecture/research-ledger.json`) is edited by hand by the coordinator, never by the script,
  starting in the commit after the seal (§12 step 7). `research_ledger.expose()` changes only the loaded copy and never
  writes the file (`scripts/research_ledger.py:191-209`).
- **Ledger = the study entry only** (lead decision 2026-10-04, §14 item 5). The study `wyckoff_forward_wc15`: this
  pre-registration, the cell, the two-look rule (§7), status collecting, and the reservation, in words: FTMO 15m bars of
  the 10 symbols (§2) that close at or after the seal instant, reserved for this cell's two looks.
- **No `oos.periods` entry.** A plain `oos_untouched` period is global; "reserved" in its `why` is only words:
  - `periods()` sets `validation_available` for ANY untouched or holdout period (`scripts/research_ledger.py:186`);
  - then `blocked_by()` stops blocking the §41 approval of ANY proposal (`scripts/outcomes.py:404-411`);
  - `validation.oos()` lets any study validate on it (`scripts/validation.py:136`);
  - other studies use the same prices in the same months (`fvg_forward`: XAUUSD, US500 5m; the CAL draft: US500, US30,
    USTEC 5m). So this window can be untouched only FOR THIS CELL.
  Without a period, nothing can validate on these bars: `assert_untouched` raises `NotDeclared`, and `validation.oos()`
  refuses (`scripts/validation.py:136-140`).
- **Unless the ledger's reader gains a `reserved_for` field** (it has none today): `periods()` keeping a reserved period
  out of `validation_available`, `assert_untouched` refusing it to every caller that does not name the reserved study,
  the loader refusing a `reserved_for` that names an unknown study, with tests in `test_research_ledger`, `test_outcomes`,
  `test_validation`, `test_improve_loop`. That is its own stream (those files are not WY-F1's). If it lands before look
  1, the period may be added then, in the commit that lands it: `id` `cfd-forward-wyf1-wc15`, `state` `oos_untouched`,
  `reserved_for` {"study": "wyckoff_forward_wc15", "cell": "W-C-long-15m"}, `range` [the seal INSTANT, null], and a `why`
  that never contains the letters "read" (`scripts/research_ledger.py:80-83` refuses an untouched period whose reason
  says it was read -- not even inside "already", "spread" or "ready").
- **Before a look**, any use of these bars that informs a choice about this cell (§44's five triggers) is recorded first,
  by hand, in the study entry: the trigger and a note naming the use. The coordinator then reports the look as exposed,
  not as untouched validation. No look consults the ledger.
- **At each look** (§12 steps 11-12), in the commit that adds the look's file, the study entry records: the look, the
  label (CONTINUE, PASS or NOT PASSED), the file and its sha256. After a PASS or look 2: status read. A look attempted
  without a record on disk (§8 item 8, `status` says so) is recorded the same way: INVALID, the look spent, the check
  that refused it.
- **If WY-F1 closes without a verdict** (§7 "never due", seal + 48 months): the study entry records status closed,
  INVALID: never due. The reservation is closed, not released: other studies use the same prices, and the log holds this
  cell's resolves, so the window never becomes validation data for this cell's choices.

## 14. Decisions (recorded 2026-10-04)

The owner delegated independent work to the lead (the coordinating session) on 2026-10-04. Each item names who decided.

1. **The read rule** -- lead, 2026-10-04. Two looks: look 1 at seal + 12 months, look 2 (final) at seal + 36 months.
   Lan-DeMets O'Brien-Fleming-type spending, one-sided alpha 0.10 in total. Boundaries from the ACTUAL event counts, so
   an unsteady event rate keeps the total alpha (§7). PASS = net excess > 0 and the boundary crossed at a look; NOT PASSED
   only at look 2. It replaces the draft's options (A) "100 events or 12 months", (B) "100 events or 36 months" and (C)
   "100 events, no time limit" (WX §12.2 (b)).
2. **FRA40** -- lead, 2026-10-04. Stays out: R0 gives it no 15m dense start, and no dense rule is changed.
3. **Symbols** -- lead, 2026-10-04. US2000, UK100 and JP225 are added unconditionally (WX §12.2 (a); WX §13 item 6):
   10 symbols. XPTUSD and XPDUSD stay out (spread). FRA40, EU50 and HK50 stay out (no dense-rule change).
4. **A symbol that never completes** -- lead, 2026-10-04. Option (A), 3 months' grace, applied per look (§7), with the
   minimum of item 20. The never-due close moves from seal + 24 months to seal + 48 months.
5. **The forward window in the ledger** -- lead, 2026-10-04. The study entry only; no reserved OOS period unless the
   ledger's reader gains a `reserved_for` field later (§13). It replaces the draft's options (A) `oos_untouched`, (B)
   `final_holdout` and (C) "a period once `reserved_for` exists".
6. **Homebrew pin** -- owner, 2026-10-04. `brew pin python@3.14` at the seal; the coordinator runs it (§12 step 5) and
   unpins after WY-F1 ends.
7. **Log-only fields at resolve** -- lead, 2026-10-04. MFE and MAE in R, bars to MFE, the ICT HTF gate flag at the
   signal (as the ablation's A3 arm applies it), the planned R:R, the entry-hour spread: logged from bars the resolve
   already uses, never tested in WY-F1, never in `status` or a cycle summary (§6).
8. **Engine scope** -- lead, 2026-10-04. WY-F1 measures the cell on the engine as R0 and R1 read it, through its sealed
   extract. The pending `scripts/wyckoff_rules.py` semantics change from the "Khám phá hệ thống FTMO" session must not
   enter WY-F1 and does not apply to it (§1, §5, §11). A forward test of the changed engine is a separate registration
   (proposed name WY-F2, not drafted now), never a re-seal of WY-F1.

9. **Seal on the committed history** -- owner, 2026-10-04. Seal on the history already committed (US500, US30, USTEC and
   DE40 end 2026-09-28 16:45Z; the live 15m files start 2026-09-29 15:00Z) without waiting for a re-export. A later
   export bridges the hole after the seal (§12 step 3); the coordinator added US500.cash, US30.cash, US100.cash and
   GER40.cash to the MT5 export list. JP225 and AUS200 have no live file yet (§12 step 4).

The decisions below answer the final review of 2026-10-04 (11 items; its evidence is in the coordinator's scratchpad).
Each is the lead's, taken on 2026-10-04.

10. **Numbers** -- lead, 2026-10-04 (review item 1, the blocker). No look depends on a last-ulp value of the OS library.
    Rows, counts and labels are hashed exactly. Every derived float that enters a hash, a commitment or a comparison (p,
    upper_95, t, alpha, z, rho, the boundaries) is rounded to 10 significant digits. Look 1's boundary is compared with
    `math.isclose(rel_tol=1e-9)`. The OS-library dependence is disclosed (§5, §11). The tie rule (a float within 1e-12 of
    a rounding midpoint verifies under either rounding) is the implementation's way to keep the rounding itself from
    being the last-ulp dependence.
11. **Revisions** -- lead, 2026-10-04 (item 2). When the source holds the store's last bar and is contiguous but
    disagrees on price, append the new bars and write a chained REVISION record (old and new values). Decisions and
    resolves keep using the bars as first stored (point in time). Every look reports the revision records (§4). The
    alignment rule that separates a revision from a shifted clock (agree on all held bars, or on at least 4 and on at
    least as many as differ) is the implementation's.
12. **The look's export** -- lead, 2026-10-04 (item 3). Fixed now, no discretion: every look requires a history export of
    ALL 10 symbols taken after cutoff + 96 bars; a symbol complete through the cutoff after that export is read (its
    events late-logged and disclosed); otherwise it is dropped whole (§7). §4, §7, §11 and §12 are aligned with the code.
13. **NOT ADVANCING** -- lead, 2026-10-04 (item 4). `status` and the cycle summary flag a store that does not advance
    while its live file exists, with `plan_append`'s reason and the store's last bar, and a stale live file (§4). The
    72-hour staleness threshold (`STALE_LIVE_HOURS`) is the implementation's.
14. **The canary's window** -- lead, 2026-10-04 (item 5). The canary's prefix is lengthened so the HTF gate runs on a
    real-length window (at least 480 1H bars at the signal; now 523). The fingerprint has 17 executed files (§5).
15. **Type-I statements** -- lead, 2026-10-04 (item 6). Every type-I statement in this draft is corrected with the
    reviewer's simulated numbers. RT §5's statistic is kept; the inflation under same-week correlation, heavy tails and
    left skew is disclosed (§7, §9, §10, §11).
16. **Blinded look 1** -- lead, 2026-10-04 (item 7). `blind` drops the log record count and anything else from which the
    resolve count can be derived (§6).
17. **Time zone** -- lead, 2026-10-04 (item 8). The fingerprint records America/New_York's DST instants for 2025-2030 as
    computed at the seal; every cycle and look refuses if the running system computes other instants (§5).
18. **Look attempt** -- lead, 2026-10-04 (item 9). A chained look-attempt record is appended before a look computes any
    outcome; a second attempt of the same look refuses even if the first output file was deleted (§8 item 8).
19. **Export replay** -- lead, 2026-10-04 (item 10). The history check replays the detector on the export and requires the
    same event ids as the log. Inside event spans a difference is tolerated if it changes no decision field and no R.
    Every difference is reported (§8 item 4).
20. **Late logging, never due, the fallback's minimum** -- lead, 2026-10-04 (item 11). A test reads late-logged events
    (§8). The never-due close at seal + 48 months is procedural: the code does not refuse a later look (§7). The
    3-month fallback may drop symbols only if at least 5 of the 10 are complete through the cutoff; otherwise the look
    waits (§7).

Recorded in WX §13 and noted here because they bear on WF1: the owner keeps forex parked, also for research ("Giữ forex
đóng"); the lead does not run WY-X1 now. Neither changes WF1.

## 15. Code

- `scripts/research/wyckoff_forward.py`: commands `spawn`, `cycle [--only accumulate|scan|resolve]`, `status [--json]`,
  `anchor`, `fingerprint`, `read --look 1|2`. EW is imported, never modified. Until the seal, a test asserts every
  fingerprinted input is what R1 ran (`test_every_fingerprinted_input_is_what_the_sealed_retest_ran`); `cmd_fingerprint`
  refuses otherwise.
- `scripts/tests/test_wyckoff_forward.py` (118 tests): synthetic and hand-built bars only. It covers:
  - the store: alignment, revisions and the old wedge, a missing or unusable live file (STALLED, never empty), NOT
    ADVANCING (a hole, a stale file, a store that advanced from the export), the chain, torn writes (an unterminated last
    line dropped and logged; never a terminated line, never under a live writer);
  - detection equivalence, the seal boundary, resolve and its log-only fields (no bar beyond the walk; the HTF gate as A3
    applies it, on a full window; never in `status` or a cycle summary);
  - the two looks: the spending and boundaries against an independent computation; the type-I error under unsteady
    event rates and, with the production statistic, under clustering and left skew; the blinded look 1 (no estimate, no
    resolve count) and its commitment; the look files' round trip; look 2 only on a committed CONTINUE;
  - the numbers (one ulp on a derived float, a rounding midpoint, a changed row, the Student-t tail, the boundary, a
    look 2 over an ulp-different look 1, the canary digest) and the time-zone pin;
  - each look's cutoff, its export rule (all 10 symbols, taken after the window and into the stores) and its per-look
    fallback (at least 5 of 10), the early-look refusal, the truncation probe (including a leaky detector), replay and
    resolve mismatches;
  - the bar-by-bar history check and the detector replayed on the export (a harmless difference reported; a decision
    change, a suppressed event in the export or in the store, and a changed trade refused);
  - the look attempt (before any outcome; a second attempt refuses with no file), late-logged events read (the owner's
    case, both looks), a stalled symbol filled at a look, the never-due close as procedure;
  - anchors from git (`anchor` never appends after a torn line; a committed line that is not an anchor record refuses by
    its commit), the fingerprint (R0 pin, the 17 executed files, both trace checks), the added symbols' dense starts (RT's
    rule, outcome-blind), the interpreter pin (a stable versioned path; a patch upgrade collects, a minor change fails
    every cycle), `extract_check` on a throwaway clone (and the extract without the `.mq5` adapters, and with another
    time-zone pin), the seal commit's shape, the sealed pre-registration's hash, `status` without resolve counts, and
    the launcher (detached spawn, the previous failure, a skip on a held lock, a checkout without the seal).
- End to end, 2026-10-05, in a throwaway `--shared` clone of the real repository (nothing committed in the real
  repository; the coordinator's scratchpad `wyf1fix/e2e_v4.py` with `e2e_synth.py` and `e2e_look.py`, log
  `wyf1fix/e2e_v4.log`), all 73 checks passed. The clone's seal instant is back-dated to 2026-10-02T21:00Z, after the last
  real bar the clone uses. Real committed history and live bars exist only before it (the real bridge keeps writing; the
  clone's live copies are cut at that instant); everything after it is a SYNTHETIC scaled copy of the canary's Spring
  scenario, so no market outcome is read from real data:
  - the fingerprint (17 executed, 19 loaded, 151 data files, the DST instants pinned, `r0_drift` empty) and
    `extract_check` pass; a fingerprint on a commit that changed `scripts/wyckoff_rules.py` refuses and writes nothing;
  - the owner's case, first half: US500, US30, USTEC and DE40 (history ends 2026-09-28T16:45Z, their live files start
    later) are NOT ADVANCING, with the hole and the store's last bar; AUS200 and JP225 are STALLED; the six others advance;
  - after commits that change `edge_wyckoff.py`, `instruments.json`, `real_costs.py` and `wyckoff_rules.py`, a cycle still
    runs the sealed extract; so does one with PYTHONPATH at the live tree; a tampered extract, a rebuilt extract with a
    matching fingerprint, an extract that pins other DST instants, an edited store and a checkout without the seal all
    refuse; `read` refuses (not due, no look-1 record, a non-canonical `--out`) and spends nothing;
  - the owner's case, second half: a later export of nine symbols bridges the four holes (911 bars each) and fills AUS200;
    JP225, not yet exported, keeps the look from being due and the refusal spends nothing; after its export the next cycle
    fills it, and all ten post-seal events are logged 29 hours after their signal close;
  - look 1 and look 2 run through the sealed `worker_read` under a synthetic plan (the plan is the only thing replaced;
    every guard runs for real): all ten symbols read, the ten late-logged events disclosed, the export replay and the
    export walks equal the store's, look 1 is blinded (no estimate, no resolve count) and its attempt record is the log's
    last record; deleting look 1's file does not allow a second run; look 2 reproduces look 1's commitment.
