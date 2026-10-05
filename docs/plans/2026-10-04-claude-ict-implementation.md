# Implementation note: experiment IC, "can Claude trade ICT discretionarily with an edge?" (2026-10-04)

Implements `docs/plans/2026-10-04-claude-ict-discretionary-preregistration.md` (the pre-registration; not edited).
Research only: no account, no order path, no live configuration is touched. Written BEFORE any decision exists.
Nothing below changes the pre-registration. Where it leaves a choice open, the choice is fixed here, before the run,
and listed in §4 so it can be checked before the template is committed. Revised 2026-10-05 after an adversarial review
(findings and what was done about each: §11).

## 1. Files

| File | Role |
|---|---|
| `scripts/research/claude_ict_common.py` | window, instruments, killzones, decision points, FTMO server clock, time exit, spread snapshot, history loader and data pins, answer-JSON extraction, git / sha256 / shadow-log guards. Imported by both of the next two. |
| `scripts/research/claude_ict_harness.py` | `points`, `build`, `probe`, `selfcheck`, `init`, `run`, `status`. Builds the point-in-time prompts; `run` makes the isolated model calls. Never imports or opens the evaluator. |
| `scripts/research/claude_ict_eval.py` | `evaluate` (once), `feasibility` (arms M / T intents before the window, no outcome) and `calibrate` (test sizes under random directions, before the window). Answer validation, the §4 simulator, arms C / R / M / T, the §6 verdict. |
| `docs/experiments/claude-ict/prompt-template.md` | system block (instructions + `{{KNOWLEDGE_BASE}}` + the strict output schema) and user block (placeholders). |
| `scripts/tests/test_claude_ict.py` | 97 tests on synthetic data, a fake `claude` executable and temporary git repositories. |

Written by `build`: `docs/experiments/claude-ict/manifest.json` and `docs/experiments/claude-ict/prompts/`
(`system.txt` + one `<date>_<instrument>_<killzone>.txt` per decision point). Written by `init` and `run`:
`docs/experiments/claude-ict/decisions.jsonl` (and its shadow outside the repository, §4 item 29). Written once by
`evaluate`: `docs/experiments/claude-ict/evaluation.json`.

## 2. Pre-registration items and their implementation

| Pre-registration | Implementation |
|---|---|
| §2 window 2026-07-01 00:00 UTC -> 2026-10-02 20:45 UTC, FTMO-Demo 5m, XAUUSD + US500 | `WINDOW_START`, `WINDOW_LAST_BAR`, `HIST_ROOT` in `claude_ict_common.py`. A killzone is in the window when it opens at/after the start and ends at/before 20:50 UTC (the close of the 20:45 bar). |
| §2 no secondary window | none is read; `evaluate` reads the window only (plus earlier bars for M / T detection history). |
| §2 higher timeframes built from the 5m bars, closed only | `aggregate()` in `claude_ict_harness.py`. |
| §3 killzones (knowledge/ict/core-a.md §2.1), New York time with DST | `KILLZONES`, `et_instant()` in `claude_ict_common.py` (zoneinfo `America/New_York`; a wall time that does not exist or exists twice is refused). |
| §3 one decision per (instrument, killzone, trading day); days without data skipped and counted | `decision_points()` in `claude_ict_common.py`. Reads bar TIMES only. Real data: 338 points (68 weekdays x 5 killzones - 2), 2 skipped (US500 New York PM on 2026-07-03 and 2026-09-07, holiday early closes). The pre-registration's "about 325" assumed 65 days. |
| §3 inputs: 4H / 1H last 60, 15m last 96, 5m last 48; previous day, week-to-date, Asia high / low; instrument, spread | `prompt_values()` and `reference_levels()` in `claude_ict_harness.py`, `spread_snapshot()` in `claude_ict_common.py`. |
| §3 output schema, invalid = NO_TRADE counted | `validate()` / `judge()` in `claude_ict_eval.py`; `extract_answer()` in `claude_ict_common.py`. |
| §3 isolation, one fresh call per decision | `cli_command()` / `call_cli()` in `claude_ict_harness.py`; §3 of this note. |
| §3 decisions appended with the prompt sha256, file committed before the first evaluation | `Runner.process()` records; `preconditions()` in `claude_ict_eval.py`. |
| §3 run once; one logged retry of a technical failure; no re-run for a better sample | §4 items 13 and 26-31 of this note. |
| §4 simulator | `simulate()` / `exits()` in `claude_ict_eval.py`; rules in §4 items 14-19 below. |
| §5 arm R (2,000 permutations, same fill times / stop distance / R:R, random direction) | `control_pair()` and `permutation_test()` in `claude_ict_eval.py`; §4 items 20-21b. |
| §5 arm M (repo ICT rules, ICT preset, the pilot's 15m settings) | `m_scan()` / `m_probe()` in `claude_ict_eval.py`; §5 of this note. |
| §5 arm T (live book v3 on XAUUSD) | `t_scan()` in `claude_ict_eval.py`; §5 of this note. |
| §6 verdict and the reported metrics | `verdict()`, `metrics()`, `counts()`, `group_metrics()`, `sample_decisions()` in `claude_ict_eval.py`. |
| §7 prompt template committed before the run; no change after the first decision | `run` refuses unless it is committed and its sha256 equals the manifest's; `build` refuses once `decisions.jsonl` holds a record, was ever committed, or any shadow log holds one. |

## 3. Isolation of one decision

Each decision is one fresh process, exactly the command agreed with the reviewing session:

    claude -p --safe-mode --tools "" --strict-mcp-config --no-session-persistence --model claude-opus-5-5
           --system-prompt-file <file> --output-format json --effort high

The user prompt goes on stdin. The working directory is a new, empty temporary directory, checked empty before the call
and removed after it. The process runs in its own process group: a terminal Ctrl-C does not reach it, and a timeout kills
the whole group. `--fallback-model` is never passed. The system prompt file is a private copy of the committed
`prompts/system.txt`, verified against the manifest's sha256 before the first call.

What is impossible in that process. `--tools ""` leaves no built-in tool: no Read / Glob / Grep (no file read), no
WebFetch / WebSearch (no web access), no Bash. `--strict-mcp-config` without `--mcp-config` loads no MCP server.
`--safe-mode` disables CLAUDE.md, skills, plugins, hooks, custom agents and MCP. Server-side tools (web search / fetch,
code execution) run only when a request declares them, and none is declared. These statements rest on the CLI's help text
and docs (Claude Code 2.1.286); `--system-prompt-file` appears in that help only as `--system-prompt[-file]`, so the
`selfcheck` call (below) is the proof that this CLI accepts the command as written.

How the guard detects a violation anyway (`isolation_check()` in `claude_ict_harness.py`). The CLI's JSON result is
rejected as a technical failure (retried once, logged) when: `num_turns` is above 1 (a tool round trip adds a turn);
`permission_denials` is not empty (a tool use that was attempted and refused); `deferred_tool_use` is present; any counter
whose name matches web_search / web_fetch / server_tool / code_execution under `usage` or `modelUsage` is above 0
(server-side tool use). The result JSON has no list of tool calls, so these four signals are all it offers. A field the CLI
does not emit (or a non-integer `num_turns`) is recorded as `isolation_unverifiable` on the decision, not silently accepted.

Selfcheck. `selfcheck`, `init` and `run` (before the first call of every invocation, unless `--no-selfcheck`) make ONE call
through the same command with a fixed non-market prompt (no decision point, nothing written to the repository) and refuse
to go on when that call fails the guard or the model pin, so a CLI whose JSON differs from what the guard expects (e.g. a
second model in `modelUsage`, `num_turns` 2 for a plain answer) stops the run before any decision is asked. Its summary is
recorded in the `start` / `resume` event.

Model pin (`served_models()`, `classify()`). The served models are the keys of `modelUsage`. A set other than exactly
`{claude-opus-5-5}` (e.g. a fallback after an overload) is logged as a `technical_failure` of kind
`model_pin_mismatch` (it does not count toward the one retry) and the run PAUSES; the decision is asked again when `run`
resumes. A result with no model information is stored with `served_model_unverifiable: true` and counted in the report.

Recorded per decision: model pinned, served models, CLI version (`claude --version`), CLI arguments, UTC start / end,
prompt sha256, system-prompt sha256, template sha256, manifest sha256, the raw answer and its sha256, the CLI result
fields (type, subtype, num_turns, durations, total_cost_usd, usage, modelUsage, permission_denials, stop reason,
session id). Run events (`start`, `resume`, `pause`, `stop`) are separate records with UTC timestamps; `init` writes the
`start` event with the fingerprint of every input and the git HEAD.

## 4. Choices the pre-registration leaves open (fixed now)

Decision points and inputs
1. Trading day = a Monday-Friday New York calendar date. A killzone with no 5m bar in [open, end) is skipped and
   counted. The skip reads bar times only (outcome-blind); a market closed for the whole killzone could not have filled
   an order anyway.
2. "Closed bars strictly before the killzone open" = 5m bars whose OPEN time is before the open (each has closed by
   then: every killzone opens on a 5m boundary), at most 30 days back (`TAIL`).
3. Higher timeframes are built from those 5m bars on the FTMO server clock: 4H buckets start at server 00/04/08/12/16/20
   (the 4H bars FTMO's MT5 draws; 21:00 / 01:00 / ... UTC in US DST, 22:00 / 02:00 / ... in US standard time); 1H and
   15m on the clock. A bucket is kept only when it ends at or before the open. OHLC = first open / max / min / last close.
4. Day = the FTMO server day (server midnight = 17:00 New York, read from `real_costs.server_zone` -> `mt5_time`,
   never a fixed offset). knowledge/ict/core-a.md "Adaptation notes" asks for one fixed day boundary per instrument; the
   broker's daily bar is that boundary. Previous day = the latest earlier server day with bars (Friday for a Monday).
5. Week = the FTMO server week: Monday 00:00 server (Sunday 17:00 New York) up to the killzone open.
6. Asia = 20:00 -> 00:00 New York ending on the killzone's New York date (Sunday evening for a Monday).
7. A level without bars is printed `MISSING`, never 0 (CLAUDE.md §20).
8. Prices are the stored MT5 BID bars; ASK = BID + spread; printed with the instrument's digits (2); times are UTC bar
   OPEN labels at minute precision. No volume (the pre-registration asks for OHLC).
9. Spread = `real_costs` profile `ftmo_demo_2026_09` (the FTMO table as exported, absolute price units), median, table
   bucket of the killzone-open instant (`table_hour`, HOUR_FRAME `server_table`), rounded to 2 digits. The same number is
   in the prompt and in the simulator. Commission = `real_costs.commission_r` (0, state `no_deals`, never guessed). This
   is the pre-registered "current spread snapshot" (exported 2026-09-28): its medians span 2022-07..2026-09, so about 6 %
   of the bars behind them fall inside the window -- a cost constant per hour, not a price path, disclosed rather than
   hidden (CLAUDE.md §8). Not `ftmo_demo_2026_09_relspread`: its `price_ref` would add a second future read, a median
   CLOSE (a price level) over the same span. Cost of the choice: the medians come from lower-price years, so the spread
   may be understated for 2026 prices; it is small against ICT stop distances and identical for every arm.
10. The knowledge base is embedded verbatim, in `KB_FILES` order, each file in `<document path="...">`, inside
    `<reference_material>`. The system prompt tells the model to ignore the operational parts of the files (agents,
    scripts, the Confluence Score, other methods) and to read the bias with the ICT rules (the Wyckoff base is not part
    of H1). `build` refuses if knowledge/ict/ gains or loses a file.

The answer
11. Exactly the eleven keys of §3, no other key (so no confidence). NO_TRADE carries `null` order / entry / stop /
    target. LONG: stop < entry < target; SHORT: target < entry < stop; |target - entry| / |entry - stop| >= 1.0 (1e-9
    float tolerance). Prices are JSON numbers > 0. `reasoning` <= 120 words (whitespace split); "ICT vocabulary only"
    cannot be checked mechanically and is not checked. `valid_until` must be "killzone_end". The schema does not force
    a minimum stop distance: a stop closer than the spread is simulated as it would trade (item 16).
12. Parsing: the whole answer, or a fenced block, or one object embedded in prose. A duplicate key, NaN / Infinity, or
    two DIFFERENT objects carrying "decision" -> no object. The template asks for the bare object; the evaluator is
    lenient on the wrapper (a format slip must not cost a decision), records `answer_form` per decision and reports the
    count per form (`answer_forms`), so a pattern of format violations is visible; no form is penalised.
13. Technical failure (exactly one retry, logged) = timeout (900 s), non-zero exit, CLI output not a JSON result, a CLI
    error result, an empty answer, an answer with NO extractable JSON object, an isolation violation. A parseable answer
    that breaks the schema is an INVALID answer: never retried, counted as NO_TRADE and as an error. Not counted and only
    pausing: a usage limit / overload (the error TEXT matches, or `api_error_status` is 429 / 529; a number elsewhere in
    the JSON, e.g. a duration of 429 ms, or a stack-trace line number is not a limit), a call killed from outside, a
    model-pin mismatch. `status` lists decisions paused three or more times.

The §4 simulator (identical for every arm)
14. Placement is judged against the first 5m bar at / after the order's instant (C: the killzone open, and C needs a bar
    exactly there: with none the order is rejected as `no_price_at_placement`; all 338 real decision points have one). A
    pending order on the wrong side of the market is REJECTED, as MT5 rejects it ("invalid price"): buy limit not below
    the ASK, sell limit not above the BID, buy stop not above the ASK, sell stop not below the BID. A market order fills
    at that bar's open (ASK long, BID short) and is rejected when the BID (long) / ASK (short) is already at or beyond its
    stop or target.
15. Fills: buy limit when ASK <= entry, sell limit when BID >= entry, at the entry, never improved; buy stop when
    ASK >= entry, sell stop when BID <= entry, at the first trade through (the open on a gap). No fill at / after 16:00
    New York of the bar's server day (the hour before the rollover). Unfilled at `valid_until` = expired.
16. Exits: stop and target rest; a LONG exits at the BID, a SHORT at the ASK; stop and target in one bar = stop first; a
    bar opening beyond the stop exits at that open (worse); a target fills at the target (never improved). A stop already
    inside the spread at the fill (a LONG's BID, a SHORT's ASK at or beyond it) is hit at once at that market price,
    never at the better stop price. On the bar a pending order fills inside of, the extreme price travelled to after the
    fill is known to follow it; the other may precede or follow it, and that uncertainty is resolved against the trade:
    its stop is checked on the whole bar, its target only on the extreme known to follow the fill. The same rule scores C
    and every control trade at that fill, and no trade gains from an assumption about the unseen order of the bar (an
    earlier draft that assumed the other extreme came first favoured trades in the direction of the approach -- C's stop
    orders -- over their controls). A fill at the open sees the whole bar.
17. Time exit: 16:00 New York of the fill's server day, at the close of the last bar before it (a market closed early
    exits at its last close); every position is flat before the 17:00 New York rollover. No swap, commission 0.
18. R = net P&L / (|entry - stop| + spread), entry = the ORDER's price: a limit or stop order's own price (it fills there
    or worse, so a gap through a stop order shows as a loss beyond the unit), a market order's fill (its price is the
    market at placement; the answer's `entry` is only the model's estimate, and taking it would let a number one tick
    from the stop inflate |R| at will). C: the decision's stop; M: the FVG edge and the engine's stop; T: the live stop.
    Net P&L comes from the BID / ASK fills. The R-control trades use C's unit, so the comparison is unaffected.
    In the permutation test a label equal to C's direction scores C's own trade, so the identity permutation is C.
19. Every order is simulated alone. Decisions are independent (§3), so overlapping positions are allowed; no portfolio
    rule is applied to any arm.

Arm R and the statistics
20. Control trade for each FILLED C trade: entry at the trade's own fill instant at the market (the BID there, + spread
    for a LONG), with the trade's own distances fill -> stop and fill -> target (its planned distances when a gap fill left
    either <= 0), the same fill bar and path, and the trade's own R unit. The same-direction control IS the trade (checked
    and reported as `same_direction_differs_from_C`).
21. "Direction random; 2,000 permutations" = 2,000 seeded SHUFFLES of C's own direction labels over its filled trades,
    WITHIN each instrument. p = (1 + #{control mean >= C mean}) / 2,001, ties counted against C. Why within the
    instrument: a global shuffle lets one drift-aligned direction per instrument (35 shorts in one instrument and 35 longs
    in the other, each with the window's drift) reach p = 0.01 to 0.03 with no skill, where the within-instrument shuffle
    gives p = 1.0 (reproduced). Reported descriptively, not gating: the global shuffle, a within-killzone shuffle, and a
    sign-flip (a fair coin per trade). Consequence: an instrument whose C trades are all in one direction contributes
    nothing to the evidence (p = 1 there).
21b. Mirror-order control (reported; gates only if `MIRROR_CONTROL_GATES`, below). For every ORDER C placed, filled or
    not, the same order on the other side is simulated by the same code: same kind, mirrored around the mid price at
    placement (a limit 12 below the ASK becomes a limit 12 above the BID), same stop and target distances (a market order:
    from its own fill). Statistic = mean R per order (0 when it did not fill); the permutation shuffles C's direction
    labels within instrument; an order keeps C's outcome when its label is C's direction and takes its mirror's otherwise.
    Why it exists: the R-control of item 20 puts the opposite trade at C's FILL instant. For a LIMIT order that opposite
    trade enters in the direction of the move the limit just faded, so a direction-blind book is not a placebo there; the
    mirror of a fade is a fade. Calibration under random directions (item 32): the primary test rejects in 6.5 % (XAUUSD
    limit) and 13.1 % (US500 limit) of replicates against a nominal 5 %; the mirror test in 4.9 % and 5.0 %.
    `MIRROR_CONTROL_GATES` (`claude_ict_eval.py`) is True since amendment 1 (docs/plans/2026-10-05-claude-ict-amendment-1.md,
    decided 2026-10-05 before any decision, reviewer agreeing): a passing mirror test is a fourth PASS condition (a PASS
    needs both tests; otherwise NOT_PASS). The §6 primary test is unchanged and reported with the mirror p either way.
    The calibration figures are in the amendment (three runs; limit books 6.5-13.1 % for the primary test, 4.0-6.4 % for
    the mirror).
22. Bootstrap: 10,000 seeded percentile resamples of C's filled-trade R; the 2.5 % and 97.5 % points are reported. The
    PASS condition is "mean net R > 0"; §6 says the lower bound is reported, so it does not gate.
23. Seeds: fixed strings hashed with sha256 into `random.Random`, used through `random()` only (the one method whose
    sequence Python guarantees per seed). Tags in `SEEDS` (`claude_ict_eval.py`).
24. Verdict states: INSUFFICIENT (< 60 filled C trades), FAIL (the primary test does not pass), PASS (primary passes,
    mean > 0, C's mean net R > M's), "INCOMPLETE (C vs M not evaluable)" (M not evaluable, every other PASS condition
    holds), NOT_PASS (the primary passed but another PASS condition failed: the pre-registration names no state for it).
    M is not evaluable when its leakage probe fails OR it has no filled trade in the window ("unknown is a valid state",
    CLAUDE.md §9). Considered and rejected: counting an empty M as mean 0, which makes "C beats M" true whenever C > 0,
    i.e. loosens the gate exactly when the comparison has no content. Cost of the choice: with no filled M trade the
    verdict cannot be PASS (M had 10 intents in the three months before the window).
25. Reported: trade count, fill rate (filled / orders), win rate (R > 0), mean and median R, profit factor, max drawdown
    in R (cumulative R in exit order), per instrument and per (instrument, killzone); NO_TRADE rate (of valid answers, and
    with invalid answers and failures); invalid answers by reason; rejections by reason; answer forms; retried decisions;
    `served_model_unverifiable` count; a seeded sample of 10 decisions drawn among the valid answers.

Run discipline
26. The evaluator is frozen BEFORE the first decision: `init` and `run` refuse unless `claude_ict_eval.py` is committed;
    the `start` event records its git blob (git reads it; the harness never opens it); `run` and `evaluate` refuse if the
    blob differs.
27. `init` and `run` refuse unless the pre-registration, the template, the six knowledge files, the shared module, the
    harness, the evaluator, the manifest and every prompt file are committed and unchanged, and every sha256 equals the
    manifest's (the system prompt is also re-rendered from the committed template and knowledge files and compared). A
    resumed run refuses if the manifest, template, system prompt, harness, shared module or evaluator blob differ from its
    `start` event.
28. Concurrency <= 4 (default 4); call timeout 900 s; 30 s before the one retry.
29. The run cannot be silently redrawn. `init` writes ONE record, the `start` event, and asks nothing; `run` refuses until
    that is committed and, before every invocation, refuses an uncommitted decisions.jsonl: every record of one invocation
    is in git before the next one asks anything. Every record also goes to an append-only shadow outside the repository
    (`IC_SHADOW_DIR`, default `~/.local/state/trading-decision-system/claude-ict/decisions-<manifest>.jsonl`). `run` and
    `evaluate` refuse when the log lost records the shadow holds or the two differ, when a shadow of another build holds
    records, or when any committed version of decisions.jsonl is not a byte prefix of the current one; `build` refuses
    once any shadow holds a record; `evaluate` checks every stored answer against its sha256. A failed attempt is recorded
    with the sha256 and length of its answer, never the text, so no rejected answer is readable. Limit: the shadow lives on
    one machine and `IC_SHADOW_DIR` can redirect it; the guards stop accidents and tinkering after a result has been seen,
    not an operator who edits the log and its shadow together between two commits.
30. Circuit breaker: 3 consecutive counted technical failures of one kind (any decisions) stop new calls and pause the
    run, so a systematic fault (e.g. a guard misreading the CLI JSON) cannot turn hundreds of decisions into technical
    failures; the retries it defers happen on resume, so each decision still gets exactly one.
31. Frozen inputs. The evaluator pins more than its own file. `build` stores the sha256 of the stored 5m bars (first bar to
    the end of the window) and 15m bars (35 days before the window to its end) of both instruments (`data_pins`), the
    cost-table snapshot (`real_costs.profile_snapshot`) and the sha256 of `history_store.py`, `real_costs.py`,
    `mt5_time.py` and `providers.json`; `init` records the git HEAD. `evaluate` loads the engine and detector modules
    first, then refuses unless every repository .py file it executed and every non-history file it opened (e.g.
    `docs/architecture/analysis-params.json`, whose `min_rr` arm M reads) is committed and is the SAME git blob as at the
    start commit, and the bars, cost tables and build libraries match the manifest. It repeats the check after computing
    and records the blobs in the result. Bars appended after the window do not matter. If another stream changes a
    dependency during the run (the ICT engine's files change often), `evaluate` refuses and names the files: evaluate from
    a worktree with those files restored to the start commit (§8, tested on a scratch repository).
32. Calibration (`claude_ict_eval.py calibrate`; bars BEFORE the window only, seeded): random orders at real killzone
    opens (stop 2-8 x the median 5m range of the 48 bars before the open, reward / risk 1-2.5, a pending order 0.5-4 x that
    range from the market), BOTH sides simulated; each replicate flips a fair coin per order, calls the chosen side "C" and
    runs the primary test on 80 filled trades and the mirror test on 120 orders. Share of replicates with p < 0.05
    (600 replicates; limit rows re-run with 2,000), nominal 0.05:

    | | market | limit | stop |
    |---|---|---|---|
    | XAUUSD primary | 0.050 | 0.065 (2,000) | 0.047 |
    | XAUUSD mirror | 0.045 | 0.050 (2,000) | 0.050 |
    | US500 primary | 0.053 | 0.131 (2,000) | 0.020 |
    | US500 mirror | 0.067 | 0.049 (2,000) | 0.048 |

    The primary test is calibrated for market orders, conservative for stop orders and too liberal for limit orders (the
    usual ICT entry); the mirror test is calibrated everywhere (the standard error of a 600-replicate cell is 0.009).

## 5. Arms M and T

Arm M: the repo ICT engine, `scripts/backtest-methods.py` `ict_setups_live`, on the FTMO-Demo 15m series, at the pilot's
15m setting `cfd-scalping-ict-15m-range-a` (docs/architecture/pilot-selection.json) = `scripts/stability-report.py`
CONFIGS["A"] via its own `config_opts(..., "range")`: no management, no HTF filter. Bias methods pinned to `("ict",)`
(what `resolve_methods` returns today, recorded in the result). Settings B and C move the stop to breakeven, so their exit
is not a fixed stop / target; they are not used. The order intent is what `_ict_trade` would place: a LIMIT at the FVG
near edge, the engine's stop and target, alive from the close of the 15m bar where the setup is first seen to the close
of bar MSS + K (K = 16), refused when the edge already traded by then. Admission as `simulate()` does it: the
planned-risk rule (>= one tick, right sides) and the planned R:R floor `bt.MIN_RR` (2.5) net of the placement-hour
spread (the entry-knowable O1 form). The engine's own 96-bar mark-to-market exit is replaced by §4's time exit.

Arm M leakage probe (reviewing session): inside `evaluate`, after `decisions.jsonl` is committed, every M intent is
re-detected on the 15m series cut right after its detection bar; the same setup (side, sweep, MSS, entry, stop, target)
must appear and the edge must still be untouched. Detection only. If any intent fails, M is excluded and "C beats M" is
`not evaluable`. `feasibility` runs the same probe on bars before 2026-07-01 as a development check of the probe itself;
only the probe inside `evaluate` gates anything.

Arm T (report-only): the demo book's live executor rule (`scripts/fvg_demo.py` `_eod_breakout`) replayed on the stored
bars for H7 + G9 XAUUSD: a MARKET order when the signal bar closes, reference = its close, stop k x sigma_5m x
sqrt(5m bars to the rollover) x reference, target reference + side x tp_stop_multiple x stop distance, one trade per
(component, server day, side), refused on stale volatility, a data hole in the last 35 days or a signal within 10
minutes of the rollover. v3 = k 2.0, multiple 5 (as written); v4 = k 1.4, multiple 7 (descriptive row). Its own time
exit (rollover - 10 min) is replaced by §4's 16:00 New York, so signals between 16:00 and 17:00 New York cannot fill.
The news block of the live executor is not applied (no arm reads news, §3).

Feasibility, before the window only (no order simulated, no outcome), `claude_ict_eval.py feasibility`,
2026-04-01 -> 2026-07-01: M XAUUSD 2 and US500 8 fixed-exit LIMIT intents, leakage probe 10 / 10 identical; T 75 MARKET
intents (H7 30, G9 45) for v3 and v4. M is sparse: its window comparison may rest on a handful of trades.

## 6. Checks run without a model call

- `claude_ict_harness.py points` on the real data: 338 decision points (XAUUSD London 68, New York AM 68; US500 London
  68, New York AM 68, New York PM 66), 2 skipped.
- `claude_ict_harness.py build --out-dir <scratch>`: system prompt 264,393 characters, user prompts about 14,400
  characters each (median 14,404).
- `claude_ict_harness.py probe --n 12` on the real data: 12 / 12 decision points give byte-identical prompts from the full
  series, the series cut at the killzone open, and a series whose every later bar is changed.
- `claude_ict_eval.py calibrate` (item 32) and `feasibility` (§5) on bars before the window.
- `test_claude_ict` (97 tests): killzones across both DST changes, the FTMO clock against a fixed offset, decision
  points and skips, the truncation probe and a guard that fails on any price read at / after the open, the template
  placeholders, answer parsing and validation, every simulator rule incl. the fill-bar rule and the stop inside the
  spread, the R-control (seeded, reproducible, same-direction identity), the within-instrument shuffle, the mirror order
  and test, the verdict states, the arm M probe (a failed probe excludes M and the label is INCOMPLETE), the refusals (run before commit, before `init`, before the start event is committed,
  with an uncommitted log; evaluate before the decisions are committed, on an incomplete run, a second time, with a
  changed evaluator, a changed dependency, re-exported bars, an edited answer, a truncated / deleted / rewritten log), the
  isolation guard, the model pin, the circuit breaker, the selfcheck, `init`, retries, pauses and resumes with a fake
  `claude`, and one complete `evaluate` on a synthetic history (arms M / T stubbed: their detectors read the real
  history, and no outcome may be computed on the real window before the decisions exist).

## 7. Token and cost estimate (not measured: no model or API call was made)

Per call: system prompt about 75,500 tokens (264,393 characters at an assumed 3.5 characters per token) + user prompt
about 4,100 tokens; output = the JSON answer (a few hundred tokens) + thinking, whose size depends on the effort level
(not pinned by the agreed command). 338 calls, plus at most one retry each, plus one tiny selfcheck call per invocation.

Claude Opus 5.5 prices from the claude-api skill (cached 2026-09-25): input $4 / MTok, output $20 / MTok, cache read
$0.20 / MTok, 5-minute cache write $5 / MTok. With the system prompt cached (calls start less than 5 minutes apart at
concurrency 4): input about $0.035 per call, about $12 in total, plus a few cold writes of $0.38. Output at 1,000 to
15,000 tokens per call: $7 to $100. Total about $20 to $115; without any cache hit the input alone would be about
$110. Under a Claude subscription the run consumes usage limits instead; a limit only pauses the run.

## 8. Commands for the coordinator

From the repository root. The files under docs/experiments/ are hidden by a global ignore (`docs/*` in
~/.gitignore_global) and need `git add -f`; this note and the scripts do not.

    # 1. build the prompts and the manifest (no model call), check them, run the tests
    python3 scripts/research/claude_ict_harness.py points
    python3 scripts/research/claude_ict_harness.py build
    python3 scripts/research/claude_ict_harness.py probe --n 12
    (cd scripts/tests && PYTHONPATH=.. python3 -W ignore -m unittest test_claude_ict)
    # 2. commit everything the run checks (MIRROR_CONTROL_GATES is True: amendment 1)
    git add scripts/research/claude_ict_common.py scripts/research/claude_ict_harness.py \
            scripts/research/claude_ict_eval.py scripts/tests/test_claude_ict.py \
            docs/plans/2026-10-04-claude-ict-implementation.md
    git add -f docs/experiments/claude-ict/prompt-template.md docs/experiments/claude-ict/manifest.json \
               docs/experiments/claude-ict/prompts
    git commit -m "IC: harness, evaluator, template, prompts and manifest (before the first decision)"
    # 3. start the run: ONE selfcheck call, then the start event only (no decision); commit it
    python3 scripts/research/claude_ict_harness.py init
    git add -f docs/experiments/claude-ict/decisions.jsonl && git commit -m "IC: run started (start event)"
    # 4. the single run: a first batch of 4, inspect, commit; then the rest. After ANY pause: commit decisions.jsonl,
    #    fix the cause, run again, until "run complete"
    python3 scripts/research/claude_ict_harness.py run --concurrency 4 --max-decisions 4
    python3 scripts/research/claude_ict_harness.py status
    git add -f docs/experiments/claude-ict/decisions.jsonl && git commit -m "IC: decisions (first batch)"
    python3 scripts/research/claude_ict_harness.py run --concurrency 4
    python3 scripts/research/claude_ict_harness.py status
    # 5. commit the complete decision log, then evaluate once
    git add -f docs/experiments/claude-ict/decisions.jsonl && git commit -m "IC: decisions (complete)"
    python3 scripts/research/claude_ict_eval.py evaluate
    git add -f docs/experiments/claude-ict/evaluation.json && git commit -m "IC: evaluation"

`run` exits 0 when complete and 3 when paused (usage limit, pinned model not served, the circuit breaker, Ctrl-C: calls
in flight finish and are stored first, `--max-decisions N`). Committing decisions.jsonl at every pause puts each partial
log in git, `run` refuses to start from an uncommitted log, and `run` / `evaluate` refuse any later version that does not
extend a committed one.

If `evaluate` refuses because dependencies changed after the start commit (item 31), it lists the files. Evaluate from a
worktree of the commit that holds the complete decisions, with those files restored to the start commit (the start commit
is the `git_head` of the `start` event in decisions.jsonl):

    git worktree add -b ic-eval ../ic-eval <commit of "IC: decisions (complete)">
    cd ../ic-eval
    git checkout <start commit> -- <each file the refusal names>      # bars: data/history/ftmo
    git commit -m "IC: dependencies as at the run start"
    python3 scripts/research/claude_ict_eval.py evaluate
    cp docs/experiments/claude-ict/evaluation.json <main repository>/docs/experiments/claude-ict/

Nothing about the run changes: the same decisions, the same evaluator blob. The result records the blobs it used.

## 9. Research-ledger entry (to add to docs/architecture/research-ledger.json; not edited here)

```json
"claude_ict": {
  "preregistration": "docs/plans/2026-10-04-claude-ict-discretionary-preregistration.md",
  "implementation": "docs/plans/2026-10-04-claude-ict-implementation.md",
  "family": "IC",
  "hypotheses": 1,
  "confirmatory_tests": 1,
  "primary_test": "arm C mean net R vs 2,000 seeded shuffles of C's direction labels within each instrument (R-control), one-sided p < 0.05, needs >= 60 filled C trades",
  "gating_conditions": ["primary test", "mirror-order test (amendment 1, docs/plans/2026-10-05-claude-ict-amendment-1.md)", "C mean net R > 0", "C mean net R > arm M mean net R (M leakage probe must pass and M must have a filled trade)"],
  "report_only": ["arm T (fvg-book v3, v4 descriptive)", "global / within-killzone / sign-flip shuffles", "bootstrap 95 % interval"],
  "calibration": "claude_ict_eval.py calibrate on 2026-03-02..2026-06-30 bars (random directions), docs/experiments/claude-ict/calibration/: primary test size 0.043 / 0.052 market, 0.065-0.084 / 0.077-0.131 limit (XAUUSD / US500, three runs), 0.029 / 0.018 stop; mirror test 0.040-0.067 everywhere",
  "amendment": "docs/plans/2026-10-05-claude-ict-amendment-1.md (2026-10-05, before any decision)",
  "effort": "high",
  "window": ["2026-07-01T00:00:00Z", "2026-10-02T20:45:00Z"],
  "instruments": ["XAUUSD", "US500"],
  "decision_points": 338,
  "skipped_no_data": 2,
  "model": "claude-opus-5-5",
  "run_once": true,
  "data_state_for_arm_C": "after the model's training cutoff (June 2026, as stated by the platform; not independently verified); never shown to the model before its decision",
  "data_state_for_arms_M_T": "inside period cfd-2025-03-to-2026-09 (oos_exposed): the M and T rules were built and selected with data overlapping this window, so their rows are in-sample comparisons",
  "secondary_windows": "none for the verdict (pre-registration §2)"
}
```

## 10. Threats and open items (stated before the run)

- Decided 2026-10-05 before the freeze commit (amendment 1): `MIRROR_CONTROL_GATES` is True (item 21b). The
  pre-registered primary test is too liberal for limit books (item 32); the mirror test is calibrated.
- Effort level: pinned to `high` in `cli_command()` (amendment 1); the CLI result does not record it, so the pin is
  the record. `--effort` is accepted by `claude --help` 2.1.286; the selfcheck call is the proof it is honoured.
- The "June 2026 training cutoff" behind the window choice (pre-registration §2) is the platform's statement, not
  something this harness can verify; the window starts in July 2026.
- Arms M and T are in-sample on this window (their rules were selected with data overlapping it); arm C is not.
- M is sparse (10 intents in the three months before the window). "C beats M" may compare against very few trades;
  with no filled M trade the verdict cannot be PASS (item 24).
- The spread table's medians come from 2022-07..2026-09 (§4 item 9).
- The fill-bar path assumption (§4 item 16) is an assumption about unseen intrabar order; it is resolved against the
  trade and applied identically to C and to its control.
- The shadow log guards accident and hindsight tinkering, not a determined operator (item 29).
- `evaluation.json` will carry ten model answers verbatim; a malformed `knowledge/...` path inside one would trip
  `test_doc_citations` (it scans docs/**/*.json, and the prompts' `.txt` files). `decisions.jsonl` is not scanned.

## 11. Adversarial review (2026-10-05): findings and what was done

A code-reviewer agent, read-only, tried to find leakage, PASS-bias, simulator contradictions, re-draw routes and verdict
contradictions. Its numbers were reproduced before being acted on (the placebo sizes, the stratification probe, the
files executed / opened by a dry run of the arms on pre-window bars).

| Finding | Disposition |
|---|---|
| Leakage into a prompt or a pre-decision rule | none found (guarded-bar test, two real pre-window prompts built and read, M's `fvg_fill` call bounded by the detection bar). |
| C1 Critical: only the evaluator's own file was frozen; 38 repository files, 12 configuration files and the bars could change between the start and `evaluate` | item 31: blobs at the start commit, data pins, cost snapshot, build libraries; refusal before any outcome; worktree procedure (§8). |
| I1 Important: the R-control puts a follow trade against C's fade at a limit fill; placebo size 7.7-11.8 % | confirmed (item 32: 6.5 % / 13.1 % at 2,000 replicates); mirror-order control (item 21b), reported, with the switch to make it gate; `calibrate` command. |
| I2 Important: a global shuffle lets a static per-instrument direction pass (p 0.01-0.03) | confirmed; primary shuffle within instrument (item 21); global / killzone / sign-flip descriptive. |
| I3 Important: `evaluate` did not check `answer_sha256`; a log edited before the first commit passes; recreating a shadow from the log | answer hashes checked; `init` + commit of the start event before any decision; `run` refuses an uncommitted log (item 29); the remaining limit is stated. |
| I4 Important: PASS unreachable when M has no filled trade | decided and documented (item 24): not evaluable, at most INCOMPLETE; the alternative was rejected. |
| Minor: "429" inside `duration_ms` paused the run uncounted | error text and `api_error_status` only; raw-text numbers need a nearby HTTP / status / error / code word; `status` lists repeated pauses. |
| Minor: placement at the first bar after the open when the open bar is missing | C needs a bar exactly at the open (item 14); none is missing in the real data. |
| Minor: a stop inside the spread exits at the better stop price | hit at once at the market price (item 16); schema unchanged. |
| Minor: the template forbids a fence and prose, the evaluator accepts them | kept lenient on purpose, `answer_forms` reported (item 12). |
| Minor: the template's market-order rule said "that price" | rewritten to the evaluator's BID / ASK test. |
| Minor: run the selfcheck before the freeze | `selfcheck`, `init` and `run` make it; it needs a real call, so the coordinator runs it (§8 step 3). |
