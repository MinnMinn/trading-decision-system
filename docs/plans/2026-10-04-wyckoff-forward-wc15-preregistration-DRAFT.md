# Wyckoff forward stage for W-C-long-15m (Spring / Shakeout long) -- pre-registration DRAFT (2026-10-04) [WY-F1]

Status: DRAFT. Not sealed. Sealing = the coordinator commits this text, after the owner's decisions in §14, as
`docs/plans/2026-10-04-wyckoff-forward-wc15-preregistration.md` with "Status: SEALED" in place of this line, in ONE commit
with the code fingerprint (§12). Until that commit exists, `scripts/research/wyckoff_forward.py cycle` collects nothing
and `read` refuses (`cmd_cycle`, `cmd_read`).

**No forward bar exists yet, and no outcome was read to write this.** The code was tested on synthetic bars only
(`scripts/tests/test_wyckoff_forward.py`). The power numbers in §9 use the R0 counts (outcome-blind) and the published
R1 summary line.

Abbreviations. WF = `scripts/research/wyckoff_forward.py`, EW = `scripts/research/edge_wyckoff.py`, RT = the sealed
re-test `docs/plans/2026-10-04-wyckoff-retest-preregistration.md` [WY-P1], AU = its results
`docs/audits/2026-10-04-wyckoff-retest.md`. Cites are `file:line`, or `file` + function name. The code cites this file as
"[WY-F1 §n]".

---

## 1. Origin (disclosed) and question

- Owner, 2026-10-04: *"thu thập dữ liệu forward cho Spring/Shakeout 15m"*.
- In the sealed re-test, W-C-long-15m read **INCONCLUSIVE**: n 63, net excess +0.25R, p = 0.18, 95 % upper bound +0.72R
  (AU:20). Shakeouts +0.64 (n 14), Springs +0.26 (n 49), descriptive (AU:39).
- RT runs its forward read R4 for survivors only (RT:245). An inconclusive cell is not a survivor. So this cell needs its
  own forward rule (AU:66-68). RT:323: INCONCLUSIVE "never licenses new variants on history. Only forward bars can settle
  it."
- **Selection, disclosed (CLAUDE.md §43).** This cell is followed BECAUSE it was the only positive confirmatory cell of
  four. Forward bars are untouched by that choice, so the forward test is fair. But +0.25R is a winner's-curse estimate.
  Plan for a smaller true effect.
- **Question.** On FTMO 15m bars that close after the seal, is the mean net excess R of the W-C-long-15m trade above 0?

## 2. What is collected (fixed now)

- **The cell, unchanged.** W-C-long exactly as RT §3.2 (RT:95-124): Spring and Shakeout pooled, long only. Entry at the
  open after the signal bar. Stop = spring low x (1 - 0.0005). Target = `tr_hi`. Cap H = 96 bars. No new variant.
- **The detector, imported, not copied.** DET-PO: EW `BASE_CFG` (EW:186), `det_params`, `window_fire` (EW:676), loaded
  from EW unmodified (WF `ew`, `det_ctx`). De-duplication as EW `detect_series` (EW:759): per leg on (side, SC, AR), here
  keyed by bar TIME (WF `fire`).
- **Symbols (7).** XAUUSD, XAGUSD, US500, US30, USTEC, DE40, AUS200 (WF `SYMBOLS`). These are RT's 8 tradeable symbols
  (EW:135) minus FRA40. R0 gives FRA40 15m no dense start (`docs/experiments/wyckoff-retest-r0/edge-wyckoff-R0.json`
  `dense["FRA40|15m"].start` = null), so R1 and R3 never read FRA40 at 15m (R0 `reads.R1.W-C-long-15m.by_symbol` lists
  the 7). Adding it would need a new dense rule. Not done (§14 item 2). A test pins the list to R0.
- **Dense rule.** R0's dense starts (all before 2023) and EW's per-day rule (EW `dense_days`, EW:396). An event counts
  only if the server day before its signal bar was dense (EW `kept`, EW:898).
- **Decided at the signal bar.** Every logged field is known at the close of the signal bar k (§4, §8).
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
studies will edit `instruments.json`, `real_costs.py` and more.

**Design.**
- **Pin the code by its commit.** `cycle` and `read` never run the working tree. They run WF from a read-only `git
  archive` extract of the seal commit, `data/live/forward/wyckoff-wc15/code/<sha>/` (WF `materialize`), in a fresh
  interpreter with `-E -s -B` (WF `_worker_cmd`). After the seal, every other file of the repository may change.
- **What the extract holds** (WF `SNAPSHOT_ROOTS`): `scripts/`, `docs/architecture/`, `data/history/costs/`, the 7
  symbols' 15m history, the R0 record, the fingerprint, the sealed file, and the two MT5 adapter files that
  `docs/architecture/providers.json` names. `scripts/providers.py:63` refuses the registry when a named adapter file does
  not exist.
- **The narrow fingerprint.** `docs/experiments/wyckoff-forward-wc15/fingerprint.json`, committed in the seal commit. It is
  what the forward path actually runs, traced on a synthetic canary through every step (store init, live append, scan,
  resolve, the read's core):
  - `exec`, 12 files whose functions run: WF, EW, `scripts/wyckoff_rules.py`, `scripts/backtest-methods.py`,
    `scripts/real_costs.py`, `scripts/research/edge_census.py`, `scripts/history_store.py`, `scripts/instruments.py`,
    `scripts/mt5_time.py`, `scripts/normalized.py`, `scripts/providers.py`, `scripts/broker_symbols.py`;
  - `load`, 24 modules imported only (EW's import chain);
  - `data`, the configs and cost tables opened, R0, and the 95 sealed history files;
  - real_costs' `price_ref` per symbol, and the canary's digest.
  - 12 executed files against the re-test's 52 frozen ones.
- **Every cycle and the read** (WF `worker_cycle`, `worker_read`):
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
  Every record carries the fingerprint digest. The read refuses records made under another digest or seal.
- **The read runs in a FRESH extract**, rebuilt from git at `code/<sha>.read/` (WF `cmd_read`, `materialize(fresh=True)`),
  never in the cycles' cached one.
- **Before sealing** (WF `cmd_fingerprint`):
  - hashes are taken on committed bytes only. The bytes on disk must be the git blob (WF `_require_clean`), which also
    catches a `core.autocrlf` checkout (`docs/plans/2026-09-20-windows-migration.md` §5);
  - **the measurement must be R1's** (WF `r0_drift`). Every fingerprinted file that R0's `meta.code_sha256` names must
    have that hash. Every other one (the FTMO cost tables, `scripts/broker_symbols.py`, `scripts/method_purity.py`)
    must be the blob of R0's `meta.git_head`. Exempt: WF, the R0 record and the 15m history (re-exported in §12 step 3).
    Otherwise "RT §5, unchanged" (§7) would be false. On 2026-10-04 every one matches;
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
  - **A patch upgrade (3.14.5 -> 3.14.6) keeps collecting.** The read's canary still refuses any numeric change (its
    digest leaves the version string out).
  - The old patch release does not stay. `brew upgrade` runs `brew cleanup` unless `HOMEBREW_NO_INSTALL_CLEANUP` is set,
    and `brew cleanup` removes old versions (`brew help upgrade`, `brew help cleanup`). If a patch changed the canary's
    digest, the read could not run under the sealed release any more: INVALID. §12 step 5 recommends `brew pin`.
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

## 6. Resolve, and no interim look

- **Resolve** (WF `resolve_record`). Once an event's exit is known (stop, target, or 96 bars), a `resolve` record is
  appended to the log: entry at the next open, skip when that open is at or beyond the stop or the target, EW
  `walk_from` under `walk_opts` (EW:920-941). Gross R only. Placebo and cost need the whole read window; they are
  computed at the read only.
- **No interim look, by procedure.** Nothing technical can stop one. The bar stores on disk show every outcome to anyone
  who draws the chart, and the log holds each resolved gross R as tamper evidence (the read checks every scored trade
  against it). Nothing records who opens these files, so the read cannot disclose a look.
- What protects the read is that a look cannot change it: the cutoff is outcome-blind and fixed now (§7), and the
  sample, the placebo and the cost are mechanical. A look could only tempt the owner to stop or change the study. That
  is not allowed after the seal (§14).
- The tools do not show outcomes in passing (tests `test_status_never_prints_an_outcome`,
  `test_status_counts_the_rule_from_the_entry_open_as_the_read_does`):
  - `status` prints counts only. It shows no resolve count: a resolve a few bars after its entry is a stop or a target.
    It shows events entered and events past their longest walk (entry + 96 bars), which are times, not outcomes. The
    rule's count comes from the entry open, as the read counts.
  - The cycle summary (the cycle log, `last_cycle.json`) counts new bars and new events, never resolves.
  - Repairs (§4) appear by file name only, in `status` and in the cycle summary. The dropped bytes can hold an R; they
    stay in `repairs.jsonl`.

## 7. The read: rule and measurement (fixed now)

**Rule** (WF `due`, `read_core`):
- **Read ONCE**, at the earlier of two outcome-blind cutoffs:
  - **N:** the 100th counted forward event. Counted = previous server day dense, entry open strictly between stop and
    target, ATR20 known. The cutoff is that event's entry-bar close.
  - **T:** seal + 12 calendar months.
  - Every symbol must have 96 bars after the cutoff, so every walk is complete. A stalled symbol delays the read.
- **Fallback for a stalled symbol (T-drop, §14 item 3, option A registered).** If no rule is met, but some symbol is
  complete through seal + 15 months (12 + `GRACE_MONTHS` 3), the cutoff is the T one and every symbol not complete
  through it is **dropped whole**: all its events leave the sample before any walk or cost is computed (WF `due`,
  `read_core`). The rule reads data times only, never a wall clock or an outcome. The read lists the dropped symbols.
- **Never due.** If the read is still not due 24 months after the seal (every symbol stalled), WY-F1 closes with no
  verdict (INVALID: never due). The coordinator records that in the ledger (§13): the study closed; the forward window,
  if registered, ended at seal + 24 months and kept reserved. No partial read, no new rule.
- A read before the cutoff refuses **before any walk, placebo or cost is computed** (test
  `test_an_early_read_refuses_before_any_walk_or_cost_is_computed`). The log already holds the resolves' gross R
  (§6); the test proves the read computes nothing from them early, not that no outcome exists.
- **PASS iff** mean net excess > 0 **and** one-sided p < 0.10, on the primary cost line. This is RT's R4 rule (RT:245;
  EW:168-169).
- **Reported, not decisive:** the other three cost lines, the 95 % upper bound, AGAINST (two-sided p < 0.05 with a
  negative mean), below delta (upper bound < 0.20R), splits by symbol, group and type, the log lag, the late-logged count,
  the dropped symbols, the anchors verified, the repairs (§4: file, offset, size, sha256).
- Output: `docs/experiments/wyckoff-forward-wc15/wyckoff-forward-read.json`. Never overwritten.

**Measurement: RT §5, unchanged.**
- Scored with EW `score` (EW:999) and `summarise` (EW:1179), the functions R1 used.
- Gross R from the walk. A gap can lose more than 1R.
- **Placebo.** Up to 200 entry bars from the same forward window, same symbol, same server-clock slot, previous day
  dense. Each gets the event's stop and target distances in ATR20 multiples. Seed sha256(`WY-P0|sym|tf|signal_time`).
- excess = R - mean(placebo R). net = excess - cost.
- **Cost.** `real_costs.cost_r` with `ftmo_demo_2026_09_relspread`, the server-table hour frame (asserted, EW
  `_require_hour_frame`). The cost tables and `price_ref` are the sealed ones in the extract. The read refuses if
  `price_ref` differs from the fingerprint's.
- **Primary line:** median spread, today's swap.
- **Statistics.** CR1 by ISO week of the signal bar, Student-t with G - 1 df, one-sided in the book's direction.
- **Window.** An event, or a placebo bar, belongs to the read iff its signal closes at or after the seal and its entry
  bar closes by the cutoff (WF `member`, EW `in_window`). Walks run to their own exit, which must be in the store.

## 8. The read's validity checks and point in time (CLAUDE.md §8, §37, §38)

**The read is INVALID and writes nothing unless all hold** (WF `read_core`, `worker_read`):
1. every chain intact and ending with a newline (a `cycle` drops an unterminated last line first, §4); every committed
   `anchors.jsonl` line an anchor record, and every anchor (from git history) on its chain; every record made under
   this seal and this fingerprint;
2. the full replay of every window equals the log: nothing missing, nothing extra, no decision field changed;
3. the truncation probe finds 0 violations, and checks at least one event when the sample is not empty;
4. a FTMO 15m history export re-exported after the cutoff confirms the forward bars, **both ways** (WF `history_check`,
   `history_problem`). Window = the store's bars from the seal to 96 bars after the cutoff bar. Per read symbol:
   - the export reaches the window's last bar (an export taken too early checks nothing after its end);
   - it holds >= 95 % of the window's store bars, and >= 99 % of those at the same prices;
   - the store lacks <= 1 % of the export's bars inside the window (`HIST_MISSING_MAX`). A hole the live file skipped
     is MISSING, not EMPTY (CLAUDE.md §20);
   - for every sampled event, from the first bar of its 300-bar window to 96 bars after its entry (its longest walk, so
     no exit is needed), store and export hold the same bars at the same prices;
   - the read records the export's `_exported_at_utc` and the sha256 of every file it read;
5. every logged resolve equals the scored trade;
6. the canary reproduces its sealed digest; the extract's fingerprint is the seal commit's; the seal commit is one
   commit on the fingerprinted one, adding exactly the sealed file and the fingerprint; the sealed file is committed and
   clean; the read file has no history.

The read cites the pre-registration by the sha256 of its text **at the seal** (`git show <seal>:<file>`), plus the
current committed text's hash and every later commit that changed it (errata, disclosed; WF `prereg_record`).

**Point in time.**
- Every decision field is computed from bars that closed by the signal close. Bar-by-bar scans equal the full replay
  (test).
- **Truncation probe** (WF `probe`). Each event is re-detected on the store CUT at its signal bar, with the window
  finding its own pivots. Every decision field must be identical. A detector that reads the next bar is caught (test
  `test_a_detector_that_reads_the_next_bar_is_caught`).
- **Log lag.** The read reports lag = `logged_at` - signal close. Events logged more than 1 day late (a hole bridged by a
  history re-export) are counted and listed as late-logged (WF `LATE_LOG_S`). They stay in the sample: their detection is
  mechanical and replayed. The count is disclosed.

## 9. Power (counts only, before any forward bar)

**Event rate.**
- R3, 2024-03 to 2026-09: 29 placeable events in 2.58 years, about **11 per year** (R0 `reads.R3`).
- R1: 63 events in 39.8 symbol-years, the same 11 per year for the 7 symbols.
- 12 months: expect about 11 events (5 % to 95 %: 6 to 17, Poisson).
- 100 events take about **9 years**. **The 12-month clause will decide the read.**

**Spread of the net excess per event.**
- 1.4R: RT §13's planning value.
- 2.2R: implied by R1's published line (+0.25, p 0.18, upper bound +0.72: SE 0.28 over 63 events).

**One-sided alpha 0.10, Student-t with n - 1 df (events rarely share a week at this rate):**

| n | MDE at 80 % power (R), SD 1.4 / 2.2 | power if the true edge is +0.25R | power if +0.50R |
|---|---|---|---|
| 6 | 1.37 / 2.15 | 0.17 / 0.14 | 0.29 / 0.20 |
| **11 (12 months, expected)** | **0.95 / 1.49** | **0.23 / 0.17** | **0.43 / 0.28** |
| 17 | 0.75 / 1.17 | 0.28 / 0.20 | 0.55 / 0.35 |
| 34 (36 months) | 0.52 / 0.82 | 0.40 / 0.26 | -- |
| 50 | 0.43 / 0.67 | 0.49 / 0.31 | 0.89 / 0.62 |
| 100 | 0.30 / 0.47 | 0.69 / 0.44 | 0.99 / 0.84 |

**What this means.**
- At 12 months this read can only find a very large edge, about 1R per trade or more.
- If the true edge is the R1 estimate (+0.25R), the read will most likely say NOT PASSED (power about 0.2).
- So NOT PASSED at 12 months means "not shown". It does not mean "no edge".
- 100 events would give power 0.44-0.69 for +0.25R, but only after about 9 years.
- This is the owner's main decision before sealing (§14 item 1).

## 10. What each result means for the owner

| Result | Plain meaning | Next step |
|---|---|---|
| **PASS** | On new bars, the 15m Spring/Shakeout long beat random entries with the same stop and target, after real FTMO cost. With about 11 trades this is weak evidence: a fluke passes 1 time in 10. | It becomes a forward-confirmed candidate. The owner may then decide to build it as an engine setup in a NEW Trading System version (CLAUDE.md §47), first on demo, with the 2.5R floor and the HTF gate as separate policy layers (RT §9). Nothing goes live from this study. |
| **NOT PASSED** | No edge was shown on the forward bars. At this power it does not exclude +0.25R. | The cell stays unconfirmed. No new variant is tried on history (RT:323). Wyckoff's price-mechanical setups get no further forward stage unless the owner registers a new one. |
| **NOT PASSED, AGAINST** (reported) | Price kept going through the shake, as on the metals before. | As NOT PASSED; logged for the edge families. |
| **INVALID** (a §8 check failed) | The forward record cannot be trusted (a gap, a rewrite, a broken probe). | No verdict. The coordinator reports which check failed. Nothing is re-read on other data. |

## 11. Threats to validity

- **Selection (§1).** Winner's curse: the forward effect is likely smaller than +0.25R.
- **Power (§9).** At 12 months, only a very large edge can pass.
- **Costs.** The read uses the sealed 2026-09 spread tables and today's swap, as RT did. Real forward spreads are not
  recorded per bar. A change in FTMO's pricing would not be seen.
- **Data revisions.** The read checks the forward bars against a later history export (§8 item 4).
- **Clock.** The bridge's measured offset can be wrong after a DST change. A shifted bar appends nothing (§4). A history
  re-export bridges it.
- **Downtime.** A stalled symbol delays the read, and after 15 months it is dropped whole (§7). AUS200 has no live 15m
  file today (§12 step 4).
- **A deliberate stall.** Someone who looked at outcomes could stop a symbol's export to drop it (§7 fallback). The read
  lists dropped symbols, and the store shows when its last bar came.
- **The seal date is the committer's clock.** A back-dated seal would show up as large log lags on the first events
  (§8), and the committed anchors pin the history from then on.
- **The tracer sees opens and executions, not `stat()` calls.** `extract_check` covers that gap before sealing (§5).
- **Interim look.** The bars and the log on disk show outcomes; only procedure prevents a look (§6).
- **Anchors depend on the coordinator.** Without monthly commits the log's timing is unanchored. The read says so.
- **A torn write.** A worker killed during `commit` leaves an unterminated last line. The next cycle drops it, logged
  (§4). Only bytes after the last newline can go; a terminated line never does.
- **A Python upgrade.** A patch upgrade keeps collecting; a minor change stops collection until Python 3.14 is back at
  the pinned path (§5). Bars missed meanwhile come from a history re-export (§4). A patch that changes the canary's
  digest makes the read INVALID once Homebrew has removed the sealed release; `brew pin python@3.14` prevents that
  (§12 step 5).

## 12. Sealing and wiring steps (coordinator)

1. The owner decides §14.
2. Commit WF, its tests and this draft. Every fingerprinted file must be committed and unchanged on disk.
3. **History.** Re-export and import the FTMO 15m history of the 7 symbols, then commit it, so each series ends inside the
   live file's ~3-day span. The seal freezes this history as the stores' start. Today the index series end 2026-09-28
   16:45Z while the live files start 2026-09-29 (an end-to-end run reported a hole for US500, US30, USTEC, DE40).
   Without the re-export the first cycle reports a hole and waits.
4. **AUS200.** Attach ExportOHLCV to an AUS200.cash 15m chart. Today `data/live/mt5-bridge/` has no
   `ohlcv.AUS200.cash.15m.json`. Without it AUS200 stalls, and the read can never be due.
5. With the stable versioned interpreter (§5), run
   `/opt/homebrew/opt/python@3.14/bin/python3.14 scripts/research/wyckoff_forward.py fingerprint --out docs/experiments/wyckoff-forward-wc15/fingerprint.json`.
   It pins that interpreter: every worker runs it. It refuses, first, a command that a patch upgrade would delete or
   re-point (a `Cellar` path, a patch release in the path) or that is not named `python3.14`. Then it refuses on
   uncommitted bytes, on any input that is not R1's (`r0_drift`) or on a broken extract (`extract_check`). launchd's
   `/opt/homebrew/bin/python3` reports the same `sys.executable` today; the explicit path does not depend on that.
   **Recommended (owner, §14 item 5):** `brew pin python@3.14` before the seal, `brew unpin python@3.14` after the
   read. `brew upgrade` then skips it (`brew help pin`), so the read runs under the sealed release (§5). Homebrew
   warns that packages needing a newer version of a pinned formula may not install or run.
6. Copy this file to the sealed name, with "Status: SEALED" and a sealing record (date, fingerprint digest, the owner's
   §14 answers). Commit the sealed file and the fingerprint in ONE commit on top of the fingerprinted HEAD, with nothing
   else. That commit is the seal. Every worker checks this shape (§5); a seal commit with anything else, or on another
   parent, collects nothing.
7. **Ledger** (§13), by hand, in the next commit, never in the seal commit (step 6).
   - Always: the study entry `wyckoff_forward_wc15`, with the reservation.
   - The forward window as an `oos.periods` entry ONLY if option (C) is in place (§13, §14 item 4). Without (C), the
     study entry alone records the reservation, and the period is added in the commit that lands (C).
   - With the period, the same commit updates every statement that "no period is untouched": the ledger's
     `_no_untouched_period_exists` note, `scripts/research_ledger.py:28-31`, `scripts/outcomes.py:398-403`,
     `docs/architecture/SYSTEM-DESIGN.md:629` and `:862`, `docs/architecture/SPEC-COMPLIANCE.md:107`, and the
     `TheHonestCurrentState` tests in `scripts/tests/test_research_ledger.py` that pin it (four fail under (A); under
     (C) at least `test_every_declared_period_is_development_or_exposed`). Under (C), "nothing can validate a
     candidate" stays true; "no period is untouched" does not.
   - Then run every consumer's tests, one module per call: `test_research_ledger`, `test_outcomes`, `test_validation`,
     `test_improve_loop`. Under (C), `test_outcomes` must pass unchanged: a reserved period does not open §41.
8. **Wire the cycle** (coordinator; `scripts/forward_cycle.py`). After the demo-tick loop (lines 97-98,
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
9. Run `python3 scripts/research/wyckoff_forward.py cycle` once by hand. It builds the extract. Then run `status`.
10. Monthly: `wyckoff_forward.py anchor`. Commit `anchors.jsonl` only after it printed the new line (§4).
11. At the cutoff, re-export the 15m history (§8 item 4) and run one `cycle` (it also drops an unterminated last line,
    §4). Then run
    `python3 scripts/research/wyckoff_forward.py read --out docs/experiments/wyckoff-forward-wc15/wyckoff-forward-read.json`.
    In the commit that adds the read file, edit the ledger by hand (§13 "At the read") and run the four ledger
    consumers' tests (step 7).

## 13. Budget and OOS exposure (CLAUDE.md §43, §44)

- One hypothesis, one test, its own family, m = 1. No other cell is collected. No variant.
- The forward window is untouched data. Bars before the seal are context only and produce no event.
- **The ledger** (`docs/architecture/research-ledger.json`) is edited by hand by the coordinator, never by the script,
  starting in the commit after the seal (§12 step 7). `research_ledger.expose()` changes only the loaded copy and never
  writes the file (`scripts/research_ledger.py:191-209`). So every state change below is a hand edit of the JSON.
  1. **The study** `wyckoff_forward_wc15`: this pre-registration, the cell, the read rule (§7), status collecting, and
     the reservation: FTMO 15m bars of the 7 symbols (§2) that close at or after the seal instant.
  2. **The forward window, in `oos.periods`, reserved for WY-F1, only once option (C) exists** (§14 item 4). CLAUDE.md
     §44: untouched OOS data must be told apart from exposed data.
     - `id` `cfd-forward-wyf1-wc15`; `state` `oos_untouched`; `reserved_for` {"study": "wyckoff_forward_wc15", "cell":
       "W-C-long-15m"}; `instruments`: FTMO 15m, XAUUSD, XAGUSD, US500, US30, USTEC, DE40, AUS200 (§2);
     - `range` [the seal INSTANT, null]: UTC, to the second, as WF `seal_info` gives it. Not the seal date: bars of the
       seal day that close before the seal are context only (§3). Nothing in `scripts/` parses `range`;
     - `why`, for example: "WY-F1 forward window: FTMO 15m bars that close at or after the WY-F1 seal. Reserved for its
       one pre-registered test (docs/plans/2026-10-04-wyckoff-forward-wc15-preregistration.md). No other study may use
       these bars for a choice about this cell before WY-F1 ends."
- **The `why` must not contain the letters "read"**, not even inside "already", "spread" or "ready".
  `scripts/research_ledger.py:80-83` refuses an `oos_untouched` period whose reason says it was read.
- **Why a plain `oos_untouched` period is not enough.** A period's state is global, and "reserved" in `why` is only
  words:
  - `periods()` sets `validation_available` for ANY untouched or holdout period (`scripts/research_ledger.py:186`);
  - then `blocked_by()` stops blocking the §41 approval of ANY proposal (`scripts/outcomes.py:404-411`; no stage is
    absent), as `test_outcomes.py:288` shows for a walked proposal;
  - `validation.oos()` lets any study validate on it (`scripts/validation.py:136`), and `improve-loop.py` lists it as
    available OOS (`scripts/improve-loop.py:246-255`);
  - other studies use the same prices in the same months: `fvg_forward` (XAUUSD, US500 5m) and the CAL draft (US500,
    US30, USTEC 5m). So this window can be untouched only FOR THIS CELL.
  Measured on 2026-10-04 with the period added in memory: `test_research_ledger` fails 4 tests and `test_outcomes` 3.
- **Option (C): what the ledger's reader must do first.** Its own stream, built and tested before §12 step 7
  (`scripts/research_ledger.py` and its consumers are not WY-F1's files):
  - `periods()` keeps a reserved period out of `validation_available` and lists it apart;
  - `assert_untouched` refuses a reserved period to every caller that does not name the reserved study;
  - the loader refuses a `reserved_for` that names a study the ledger does not hold;
  - tests: `test_research_ledger`, `test_outcomes` (a reserved period still blocks approval), `test_validation`
    (`oos()` refuses it to another study), `test_improve_loop` (not listed as available).
- **Without (C) at step 7**, no period is added. The study entry alone records the reservation. Nothing can validate
  on an undeclared period: `assert_untouched` raises `NotDeclared`, and `validation.oos()` refuses
  (`scripts/validation.py:136-140`). The period is added in the commit that lands (C), before the read.
- **Before the read**, any use of these bars that informs a choice about this cell (§44's five triggers) exposes the
  period first, by hand: `state` `oos_exposed`, plus an `exposures` entry {trigger, `experiment_id` null, a note naming
  the use}. Without (C), the study entry records the same. The coordinator then reports the read as exposed, not as
  untouched validation. The read itself does not consult the ledger.
- **At the read** (§12 step 11), in the commit that adds the read file, edit the period by hand, as
  `cfd-prop-search-2024-03-2025-03` records its exposure:
  - `state` `oos_exposed`;
  - `range` end = the close of the last bar the read used: the latest `history_check.<symbol>.window_last` in the read
    file (an open time) + 15 minutes. That bar is 96 bars after the cutoff bar. The walks and the history check use
    bars up to it, so they are exposed too;
  - append to `exposures`: {"trigger": "candidate_selection", "experiment_id": null, "note": the read file's path and
    sha256}. The read selects or closes the cell.
  - Without (C), the study entry records the same: status read, the file and its sha256.
- **If WY-F1 closes without a read** (§7 "never due", 24 months after the seal), in the commit that records the close:
  - the study: status closed, INVALID: never due;
  - the period, if registered: `range` end = seal instant + 24 months. The reservation is closed, not released. Other
    studies use the same prices, and the log holds this cell's resolves, so the window never becomes validation data
    for anyone. Under (C) a reserved period is never available, so it never opens §41. The `why` adds "WY-F1 closed
    with no verdict (never due) on <date>", which has no "read" in it.

## 14. Open decisions (owner, before sealing)

1. **The read rule's power (§9).** The rule given was "100 events or 12 months". At about 11 events a year, 12 months
   decides with about 11 trades: about 20 % power for +0.25R. Options:
   - (A) "Keep 100 events or 12 months": an answer in a year, but it can only find an edge of about 1R or more.
   - (B) "100 events or 36 months": about 34 trades, power 0.26-0.40 for +0.25R.
   - (C) "100 events, no time limit": about 9 years, power 0.44-0.69 for +0.25R.
   This draft registers (A), as given. Changing it after the seal is not allowed.
2. **FRA40 (§2).** It is excluded because R0 gave it no 15m dense start. Keep it out ("7 symbols"), or register a dense
   rule for it now, before any forward bar.
3. **A symbol that never completes (§7).** The rule needs every symbol complete through the cutoff. A delisted symbol,
   a missing AUS200 file or a hole that cannot be bridged would leave the read undue forever, while the log already
   holds outcomes. That invites a rule change after the fact. Options:
   - (A) "Drop stalled symbols after 3 months' grace": once any symbol is complete through seal + 15 months, every
     symbol not complete through seal + 12 months is dropped whole, before any outcome is computed. The read lists them.
   - (B) "No fallback": the read stays not due; 24 months after the seal WY-F1 closes with no verdict.
   This draft registers (A) (WF `GRACE_MONTHS = 3`; (B) is `GRACE_MONTHS = None`). Either way, 24 months after the seal
   with no read due, WY-F1 closes with no verdict.
4. **The forward window in the ledger (§13).** It would be the repository's first untouched period. The ledger's own
   note calls carving one out "a decision about what the pilot trades, not a documentation change". Options:
   - (A) `oos_untouched`, with "reserved for WY-F1" in its `why` only. No code honors a reservation in `why`. The window
     becomes validation data for EVERY study, and the §41 gate approves ANY fully walked proposal (§13). Not
     recommended.
   - (B) `final_holdout`. The same two effects, and it claims the system's last holdout, which a one-cell forward test
     is not. Not recommended.
   - Under (A) or (B), §12 step 7 must also change `scripts/tests/test_outcomes.py:280`, `:326` and `:331` (they pin
     that no proposal can be approved) and `docs/architecture/ui-fields.json:42`.
   - (C) `oos_untouched` with a `reserved_for` field that the ledger's reader enforces (§13): never counted as
     available, refused to any other study. Built and tested in its own stream before §12 step 7. Until it exists,
     the study entry alone records the reservation.
   This draft registers (C). (A) and (B) both open the §41 approval gate.
5. **Homebrew pin (§5, §12 step 5).** Keep `python@3.14` pinned from the seal to the read (`brew pin`), or let it
   upgrade. A pinned Python gets no patch fixes for up to 24 months. An unpinned one risks an INVALID read if a patch
   changes the canary's digest after Homebrew removed the sealed release. This draft recommends the pin.

## 15. Code

- `scripts/research/wyckoff_forward.py`: commands `spawn`, `cycle [--only accumulate|scan|resolve]`, `status [--json]`,
  `anchor`, `fingerprint`, `read`. EW is imported, never modified. Until the seal, a test asserts every fingerprinted
  input is what R1 ran (`test_every_fingerprinted_input_is_what_the_sealed_retest_ran`); `cmd_fingerprint` refuses
  otherwise.
- `scripts/tests/test_wyckoff_forward.py`: synthetic and hand-built bars only. It covers the store, the chain, torn
  writes (an unterminated last line dropped and logged; never a terminated line, never under a live writer), detection
  equivalence, the seal boundary, resolve, the read rule and its fallback, the early-read refusal, the truncation probe
  (including a leaky detector), replay and resolve mismatches, the two-way history check (an early export, a store
  hole, one changed bar in an event's span), anchors from git (`anchor` never appends after a torn line; a committed
  line that is not an anchor record refuses by its commit), the fingerprint (R0 pin, both trace checks), the
  interpreter pin (a stable versioned path; a patch upgrade collects, a minor change fails every cycle), `extract_check`
  on a throwaway clone (and the extract without the `.mq5` adapters), the seal commit's shape, the sealed
  pre-registration's hash, `status` without resolve counts, and the launcher (detached spawn, the previous failure, a
  skip on a held lock, a checkout without the seal).
