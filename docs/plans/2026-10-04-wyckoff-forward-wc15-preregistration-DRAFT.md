# Wyckoff forward stage for W-C-long-15m (Spring / Shakeout long) -- pre-registration DRAFT (2026-10-04) [WY-F1]

Status: DRAFT. Not sealed. The §14 decisions are taken (2026-10-04). Sealing = the coordinator commits this text as
`docs/plans/2026-10-04-wyckoff-forward-wc15-preregistration.md` with "Status: SEALED" in place of this line, in ONE commit
with the code fingerprint (§12). Until that commit exists, `scripts/research/wyckoff_forward.py cycle` collects nothing
and `read` refuses (`cmd_cycle`, `cmd_read`).

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
- A source appends only when it holds the store's last 4 bars at identical prices. A gap, a revised bar or a shifted
  clock (the bridge after a DST change) appends nothing, and a note says why.
- The live file holds about 300 bars (about 3 trading days). After a longer outage, a re-exported FTMO history
  (ExportHistory.mq5 + `scripts/import-mt5-history.py`) bridges the hole. Then the live file continues.
- Every bar records its source (`live` / `history`) and the time it was appended.
- **A missing or unusable live file is STALLED, never an empty market** (CLAUDE.md §20: MISSING is not EMPTY; WF
  `live_source`, `accumulate_symbol`). Missing, unreadable, with one bad bar, or with no closed bar: the file gives no bar
  list at all, so nothing is appended from it. The cycle summary (`stalled`) and `status` list the symbol, and its store
  does not advance. So no look counts it complete (§7); a look drops it only by the registered fallback, by name. A
  history re-export can still bridge bars; the symbol stays listed as stalled while its feed is down. Today JP225 and
  AUS200 have no live 15m file (§12 step 4). Test: `test_a_missing_or_unusable_live_file_is_stalled_never_an_empty_market`.

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
  resolve with the log-only fields, both looks' read core):
  - `exec`, 13 files whose functions run: WF, EW, `scripts/wyckoff_rules.py`, `scripts/backtest-methods.py`,
    `scripts/real_costs.py`, `scripts/research/edge_census.py`, `scripts/history_store.py`, `scripts/instruments.py`,
    `scripts/mt5_time.py`, `scripts/normalized.py`, `scripts/providers.py`, `scripts/broker_symbols.py`, and
    `scripts/live_rules.py` (the HTF gate's bias reader, §6);
  - `load`, 23 modules imported only (EW's import chain);
  - `data`, the configs and cost tables opened, R0, and the 127 sealed 15m history files of the 10 symbols;
  - real_costs' `price_ref` per symbol, and the canary's digest.
  - 13 executed files against the re-test's 52 frozen ones. The HTF gate's methods are pinned in WF (`HTF_METHODS`, §6),
    so the forward path never reads the live automation config.
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
- **Each look runs in a FRESH extract**, rebuilt from git at `code/<sha>.read/` (WF `cmd_read`, `materialize(fresh=True)`),
  never in the cycles' cached one.
- **Before sealing** (WF `cmd_fingerprint`):
  - hashes are taken on committed bytes only. The bytes on disk must be the git blob (WF `_require_clean`), which also
    catches a `core.autocrlf` checkout (`docs/plans/2026-09-20-windows-migration.md` §5);
  - **the measurement must be R1's** (WF `r0_drift`). Every fingerprinted file that R0's `meta.code_sha256` names must
    have that hash. Every other one (the FTMO cost tables, `scripts/broker_symbols.py`, `scripts/method_purity.py`)
    must be the blob of R0's `meta.git_head`. Exempt: WF, the R0 record and the 15m history (re-exported in §12 step 3).
    Otherwise "RT §5, unchanged" (§7) would be false. Re-checked on 2026-10-04 with the 10 symbols and the HTF gate:
    `r0_drift` is empty;
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
- **Look 1 is blinded unless it passes** (§7): its record shows no estimate, so the months between the looks are not
  read with look 1's mean in view.
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
- the per-look fallback for a stalled symbol (3 months, `GRACE_MONTHS`) and the never-due close (seal + 48 months,
  `NEVER_DUE_MONTHS`).

**How each look's boundary is computed** -- from the ACTUAL event counts, all outcome-blind:
- **Look 1** (WF `look1_boundary`). n1 = the events look 1 scores (its rows; a skip -- entry beyond stop or target, no
  ATR20, no placebo -- is outcome-blind). t1 = n1 / (n1 + 28). alpha1 = alpha(t1). z1 = Phi^-1(1 - alpha1). With
  n1 = 0, alpha1 = 0 and look 1 cannot pass.
- **Look 2** (WF `look2_boundary`). n2 = the events look 2 scores; n12 = those also scored at look 1 (n1, unless a
  symbol read at look 1 is dropped at look 2). rho = n12 / sqrt(n1 n2). z2 solves P0(Z1 < z1, Z2 < z2) = 1 - alpha, where (Z1, Z2) is
  standard bivariate normal with correlation rho (WF `bvn_lower`). Look 2 spends alpha - alpha1.
- So the false-pass probability over both looks is exactly 0.10 for any n1 and n2: a slow or fast first year moves
  alpha1, and look 2 takes the rest at the correlation the counts actually give.
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
    8,000 runs with the registered Student-t p-value on normal per-event values.
  - Before sealing, larger runs gave 0.1001-0.1008 for the Student-t p on normal values (60,000 runs each, three rate
    paths). On skewed R-like values (-1 or +4, mean 0) the one-sided t-test is conservative there (0.066-0.075).
- **Approximation, disclosed.** The boundaries are exact for normal z statistics whose information is proportional to the
  event count. A look applies them as nominal one-sided p thresholds to RT §5's p (CR1 by ISO week, Student-t), and the
  two looks draw their placebos from different windows, so the looks' correlation is approximate. The simulations above
  measure what that costs.

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
  cutoff and symbols and refuses (INVALID) unless it reproduces the committed sha256 and boundary. Then it discloses it.
- **Look 2:** PASS or **NOT PASSED**. NOT PASSED exists only at look 2.

**Cutoffs** (WF `due`, `read_core`):
- Each look's cutoff is fixed by the seal alone: seal + 12 months (look 1), seal + 36 months (look 2). Every symbol must
  have 96 bars after the cutoff, so every walk is complete. A stalled symbol delays the look.
- **Fallback for a stalled symbol, per look (option A, §14 item 4).** If not every symbol is complete through a look's
  cutoff, but some symbol is complete through that cutoff + 3 months, every symbol not complete through the cutoff is
  **dropped whole from that look**: all its events leave that look's sample before any walk or cost is computed. A
  symbol dropped at look 1 can be back at look 2. The rule reads data times only, never a wall clock or an outcome. Each
  look lists the dropped symbols.
- **Never due.** If look 2 is still not due 48 months after the seal, WY-F1 closes with no verdict (INVALID: never due).
  `status` shows the date (`never_due_close`). The coordinator records the close in the ledger's study entry (§13). No
  partial read, no new rule. A look-1 CONTINUE stays blinded for good.
- A look before its cutoff refuses **before any walk, placebo or cost is computed** (test
  `test_an_early_look_refuses_before_any_walk_or_cost_is_computed`). The log already holds the resolves' gross R (§6);
  the test proves a look computes nothing from them early, not that no outcome exists.
- **Reported, not decisive:** the other three cost lines, the 95 % upper bound, AGAINST (look 2: two-sided p < 0.05 with a
  negative mean), below delta (upper bound < 0.20R), splits by symbol, group, type and set (`rt` / `added`), the log lag,
  the late-logged count, the dropped symbols, the anchors verified, the repairs (§4: file, offset, size, sha256), the
  log-only recomputation (§6).
- Output: `docs/experiments/wyckoff-forward-wc15/wyckoff-forward-look1.json` and `...-look2.json` (WF `LOOK_OUT`).
  Never overwritten: a look whose file exists, or has git history, refuses.

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
4. a FTMO 15m history export re-exported after the look's cutoff confirms the forward bars, **both ways** (WF
   `history_check`, `history_problem`). Window = the store's bars from the seal to 96 bars after the cutoff bar. Per read
   symbol:
   - the export reaches the window's last bar (an export taken too early checks nothing after its end);
   - it holds >= 95 % of the window's store bars, and >= 99 % of those at the same prices;
   - the store lacks <= 1 % of the export's bars inside the window (`HIST_MISSING_MAX`). A hole the live file skipped
     is MISSING, not EMPTY (CLAUDE.md §20);
   - for every sampled event, from the first bar of its 300-bar window to 96 bars after its entry (its longest walk, so
     no exit is needed), store and export hold the same bars at the same prices;
   - the look records the export's `_exported_at_utc` and the sha256 of every file it read;
5. every logged resolve equals the scored trade;
6. the canary (both looks, on synthetic bars) reproduces its sealed digest; the extract's fingerprint is the seal
   commit's; the seal commit is one commit on the fingerprinted one, adding exactly the sealed file and the fingerprint;
   the sealed file is committed and clean; the look's file has no history;
7. look 2 only: look 1's committed record is a CONTINUE of this seal and fingerprint, and its statistic and boundary
   reproduce (§7).

A look cites the pre-registration by the sha256 of its text **at the seal** (`git show <seal>:<file>`), plus the current
committed text's hash and every later commit that changed it (errata, disclosed; WF `prereg_record`).

**Point in time.**
- Every decision field is computed from bars that closed by the signal close. Bar-by-bar scans equal the full replay
  (test).
- **Truncation probe** (WF `probe`). Each event is re-detected on the store CUT at its signal bar, with the window
  finding its own pivots. Every decision field must be identical. A detector that reads the next bar is caught (test
  `test_a_detector_that_reads_the_next_bar_is_caught`).
- **Log lag.** A look reports lag = `logged_at` - signal close. Events logged more than 1 day late (a hole bridged by a
  history re-export) are counted and listed as late-logged (WF `LATE_LOG_S`). They stay in the sample: their detection is
  mechanical and replayed. The count is disclosed.

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
- Under the null: P(PASS) = 0.10, of which 0.0044 at look 1.
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
| **PASS at look 1** | After 12 months, the 15m Spring/Shakeout long beat random entries with the same stop and target, after real FTMO cost, by a margin a fluke reaches about 1 time in 230 (p < about 0.0044). | WY-F1 ends. It becomes a forward-confirmed candidate. The owner may then decide to build it as an engine setup in a NEW Trading System version (CLAUDE.md §47), first on demo, with the 2.5R floor and the HTF gate as separate policy layers (RT §9). Nothing goes live from this study. |
| **CONTINUE (look 1)** | Look 1 did not cross its (strict) boundary. Its estimate stays sealed. | Keep collecting to look 2. Nothing else changes. |
| **PASS at look 2** | After 36 months, the same, with the whole remaining alpha. Over both looks a fluke passes 1 time in 10. | As PASS at look 1. |
| **NOT PASSED (look 2)** | No edge was shown on the forward bars. At this power it does not exclude +0.25R. | The cell stays unconfirmed. No new variant is tried on history (RT:323). Wyckoff's price-mechanical setups get no further forward stage unless the owner registers a new one (for the changed engine: WY-F2, §1). |
| **NOT PASSED, AGAINST** (reported) | Price kept going through the shake, as on the metals before. | As NOT PASSED; logged for the edge families. |
| **INVALID** (a §8 check failed) | The forward record cannot be trusted (a gap, a rewrite, a broken probe, a look-1 commitment that does not reproduce). | No verdict. The coordinator reports which check failed. Nothing is re-read on other data. |
| **Never due** (§7) | Look 2 was still not due 48 months after the seal. | WY-F1 closes with no verdict. The ledger records it (§13). |

## 11. Threats to validity

- **Selection (§1).** Winner's curse: the forward effect is likely smaller than +0.25R.
- **Power (§9).** At look 1 only a very large edge can pass; at look 2 power is 0.29-0.45 for +0.25R.
- **The engine changes after the seal (§1 scope).** The pending `scripts/wyckoff_rules.py` change, and any later engine
  change, never enters WY-F1. WY-F1's verdict is then a statement about the OLD detector only, which may no longer be the
  engine the system runs. It cannot license the changed engine. A test of the changed engine is a separate registration
  (WY-F2).
- **Two-look approximation (§7).** Exact for normal z statistics; the registered t / CR1 p-value is applied as a nominal
  threshold. Simulated: 0.100-0.101 on normal values, conservative on skewed R values.
- **A blinded look still says something.** CONTINUE tells everyone that look 1's estimate did not cross its strict
  boundary. That is inherent to any interim look.
- **Costs.** The looks use the sealed 2026-09 spread tables and today's swap, as RT did. Real forward spreads are not
  recorded per bar. A change in FTMO's pricing would not be seen. The added three are cheap (§2), but UK100's mean
  spread proxy (0.23R) is the highest of the ten.
- **Data revisions.** Each look checks the forward bars against a later history export (§8 item 4).
- **Clock.** The bridge's measured offset can be wrong after a DST change. A shifted bar appends nothing (§4). A history
  re-export bridges it.
- **Downtime.** A stalled symbol delays a look, and 3 months after that look's cutoff it is dropped whole from it (§7).
  JP225 and AUS200 have no live 15m file today (§12 step 4); until the owner attaches ExportOHLCV they are STALLED (§4).
- **A deliberate stall.** Someone who peeked at outcomes could stop a symbol's export to drop it (§7 fallback). Each look
  lists dropped symbols, and the store shows when its last bar came.
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
3. **History** (OWNER: ExportHistory.mq5 for the 15m bars of the 10 symbols; COORDINATOR: `scripts/import-mt5-history.py`
   and the commit). Each series must end inside its live file's ~3-day span. The seal freezes this history as the stores'
   start. In the e2e run of 2026-10-04 (§15), the history of US500, US30, USTEC and DE40 ended 2026-09-28 16:45Z, before
   their live files start (2026-09-29 15:00Z), so the first cycle reported a hole for them. XAUUSD, XAGUSD, US2000 and
   UK100 connected (their stores reached 2026-10-02). AUS200 and JP225 had no live file (step 4). Without the re-export
   the first cycle reports a hole and waits.
4. **Live files** (OWNER). Attach ExportOHLCV to a 15m chart of **JP225.cash** and of **AUS200.cash**. Today
   `data/live/mt5-bridge/` has neither `ohlcv.JP225.cash.15m.json` nor `ohlcv.AUS200.cash.15m.json` (UK100 and US2000 have
   theirs). Without them both are STALLED (§4): nothing is collected for them, and each look drops them whole 3 months
   after its cutoff (§7).
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
   `status`: JP225 and AUS200 show STALLED until step 4 is done.
10. **Monthly** (COORDINATOR): `wyckoff_forward.py anchor`. Commit `anchors.jsonl` only after it printed the new line (§4).
11. **Look 1** (seal + 12 months, once `status` shows look 1 due). OWNER: re-export the 15m history of the 10 symbols after
    the cutoff + 96 bars (§8 item 4). COORDINATOR: import and commit it, run one `cycle` (it also drops an unterminated
    last line, §4), then run
    `python3 scripts/research/wyckoff_forward.py read --look 1 --out docs/experiments/wyckoff-forward-wc15/wyckoff-forward-look1.json`.
    Commit the look-1 record (blinded unless PASS) with the study entry's update (§13). On PASS, WY-F1 ends: remove the
    step-8 line and run `brew unpin python@3.14`.
12. **Look 2** (seal + 36 months, only after a committed look-1 CONTINUE). The same, with `read --look 2 --out
    docs/experiments/wyckoff-forward-wc15/wyckoff-forward-look2.json`. Commit the record with the study entry's update.
    WY-F1 ends: remove the step-8 line and run `brew unpin python@3.14`.
13. **Never due** (seal + 48 months, when `status` shows look 2 not due): record the close in the study entry (§13),
    remove the step-8 line, `brew unpin python@3.14`.

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
  label (CONTINUE, PASS or NOT PASSED), the file and its sha256. After a PASS or look 2: status read.
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
4. **A symbol that never completes** -- lead, 2026-10-04. Option (A), 3 months' grace, applied per look (§7). The
   never-due close moves from seal + 24 months to seal + 48 months.
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

Recorded in WX §13 and noted here because they bear on WF1: the owner keeps forex parked, also for research ("Giữ forex
đóng"); the lead does not run WY-X1 now. Neither changes WF1.

## 15. Code

- `scripts/research/wyckoff_forward.py`: commands `spawn`, `cycle [--only accumulate|scan|resolve]`, `status [--json]`,
  `anchor`, `fingerprint`, `read --look 1|2`. EW is imported, never modified. Until the seal, a test asserts every
  fingerprinted input is what R1 ran (`test_every_fingerprinted_input_is_what_the_sealed_retest_ran`); `cmd_fingerprint`
  refuses otherwise.
- `scripts/tests/test_wyckoff_forward.py` (81 tests): synthetic and hand-built bars only. It covers the store, the
  chain, a missing or unusable live file (STALLED, never empty), torn writes (an unterminated last line dropped and
  logged; never a terminated line, never under a live writer), detection equivalence, the seal boundary, resolve and its
  log-only fields (no bar beyond the walk; the HTF gate as A3 applies it; never in `status` or a cycle summary), the two
  looks (the spending and boundaries against an independent computation; the type-I error under unsteady event rates;
  the blinded look 1 and its commitment; the look files' round trip; look 2 only on a committed CONTINUE), each look's
  cutoff and its per-look fallback, the early-look refusal, the truncation probe (including a leaky detector), replay
  and resolve mismatches, the two-way history check (an early export, a store hole, one changed bar in an event's span),
  anchors from git (`anchor` never appends after a torn line; a committed line that is not an anchor record refuses by
  its commit), the fingerprint (R0 pin, the 13 executed files, both trace checks), the added symbols' dense starts (RT's
  rule, outcome-blind), the interpreter pin (a stable versioned path; a patch upgrade collects, a minor change fails
  every cycle), `extract_check` on a throwaway clone (and the extract without the `.mq5` adapters), the seal commit's
  shape, the sealed pre-registration's hash, `status` without resolve counts, and the launcher (detached spawn, the
  previous failure, a skip on a held lock, a checkout without the seal).
- End to end, 2026-10-04, in a throwaway `--shared` clone of commit 0a0e87c plus this code (nothing committed in the
  real repository; the coordinator's scratchpad `wyf1fin/e2e_v3.py`, log `wyf1fin/e2e_v3.log`), all 23 checks passed:
  - a fingerprint on a commit that changed `scripts/wyckoff_rules.py` refuses (`r0_drift`) and writes nothing;
  - the fingerprint (13 executed, 23 loaded, 151 data files) and `extract_check` (550 files) pass; seal commit;
  - a detached cycle builds the stores of the 10 symbols and lists AUS200 and JP225 as STALLED; a second cycle adds
    nothing;
  - after commits that change `edge_wyckoff.py`, `instruments.json`, `real_costs.py` and `wyckoff_rules.py`, a cycle still
    runs the sealed extract; so does one with PYTHONPATH at the live tree;
  - a tampered extract, a rebuilt extract with a matching fingerprint, an edited store and a checkout without the seal
    all refuse;
  - `read --look 1` refuses (not due), `read --look 2` refuses (no committed look-1 record), a non-canonical `--out`
    refuses, and no look file is written; `status --json` shows no log-only field.
