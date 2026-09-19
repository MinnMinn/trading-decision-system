# Close the 11 feature gaps (audit 2026-09-18) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn every PARTIAL / MISSING row of `docs/audits/2026-09-18-feature-audit.md` into code that is held by a test, without changing what any existing number means silently.

**Architecture:** Four dependency-ordered workstreams. WS-A (backtest core: HTF leak, account-aware run, calendar + session gates) and WS-C (System Ranking page) touch disjoint files and run in parallel. WS-B (expectation producer/renderer + chart decoupling) and WS-D (trader constraints + improve loop) both depend on WS-A's CLI and run in parallel after it. WS-E integrates: regenerates evidence, updates the ledger, runs the whole suite. The Master Agent (main session) owns the shared contracts in §0; workers implement against them and return NEEDS_CONTEXT rather than redefining one.

**Tech Stack:** Python 3 stdlib only, `unittest` under `pytest`, vanilla JS in `scripts/chart.js`, JSON registries in `docs/architecture/`.

**Granularity note.** The project's `CLAUDE.md` §0.1 ("smallest coordination structure", "specialists receive only the context necessary") outranks the writing-plans default of full code per step. Each task below fixes files, contract, tests and exit criteria; the worker writes the code under TDD. Anything a worker would have to guess is a contract gap — return NEEDS_CONTEXT.

**Spec:** `docs/audits/2026-09-18-feature-audit.md` (the gap list) · `CLAUDE.md` §8, §17, §21, §24–§32, §33, §37–§39, §41–§48, §50.

---

## 0. Shared contracts (owned by the Master Agent — do not redefine)

### 0.1 Account profiles (`docs/architecture/account-profiles.json`)

Two new profiles, `context_type: "PROP_CHALLENGE"`, `venue: "mt5"`, **`environment: "research"`** (the validator keys uniqueness on `(venue, environment)` — `scripts/account_profile.py:100` — and `for_venue("mt5","demo")` must keep returning `pilot-mt5-demo`; a research profile is never an order-path profile).

| id | initial_balance | max_daily_loss | max_total_drawdown | profit_target | min_trading_days | consistency_rules |
|---|---|---|---|---|---|---|
| `ftmo-challenge-phase1` | `{amount: 100000, currency: "USD"}` | `{pct: 0.05, basis: day_start_equity, action: HALT}` | `{pct: 0.10, basis: initial_balance, action: HALT}` | `{pct: 0.10, basis: initial_balance}` | 4 | `[]` |
| `the5ers-high-stakes-step1` | `{amount: 100000, currency: "USD"}` | `{pct: 0.05, basis: day_start_equity, action: HALT}` | `{pct: 0.10, basis: initial_balance, action: HALT}` | `{pct: 0.08, basis: initial_balance}` | 3 | `[]` |

Every other rule key `null` (or `[]` for list keys) exactly like `pilot-mt5-demo`; `max_positions: {mode: full_book}`; `max_trades_per_day_per_symbol: null`. Each profile carries `"_source": {"retrieved": "2026-09-18", "urls": [...], "verify": "values came from web search summaries, not the vendor page (fetch blocked); confirm at ftmo.com/en/trading-objectives and help.the5ers.com before treating a pass as real"}`. Sources: FTMO — propfirmatlas.io/guides/ftmo-challenge-rules-guide, ftmo.com/en/trading-objectives (5 % daily from day-open balance/equity, 10 % max, 10 % / 5 % targets; min trading days reported as 4 by 2024+ sources and 10 by older ones — 4 recorded, flagged). The5ers High Stakes — help.the5ers.com/what-is-the-drawdown-rule-for-high-stakes (5 % daily from previous day close, higher of balance/equity; 10 % absolute), the5ers.com/faqs/... (3 profitable days; Classic target 8 % step 1, 5 % step 2).

Replace `_no_prop_profile_why` with `_prop_profiles_why`: they exist for RESEARCH under §33/§37 (user decision 2026-09-18), are `environment: research`, and cannot be routed to by `for_venue`.

### 0.2 `initial_balance` shape

The vocabulary says `{amount, currency}`; `scripts/performance.py:_account_terms` accepts only a number. Fix `performance` to accept both (`amount` of a dict, or a bare number) — never the reverse.

### 0.3 Backtest CLI (`scripts/backtest-methods.py`)

```
--account <profile-id> | --account-file <path>   (mutually exclusive; same semantics as stability-report.py:79-92)
--calendar <path>        economic calendar JSON in event-calendar.json's shape; loaded via event_risk.load(path=...)
--sessions <a,b,...>     allowed session labels (validated against sessions.ORDER); entries outside are refused
```

`simulate(trades, fee_pct, account=None, calendar=None, sessions=None)`; `SIM_LAST` gains `"refused": {"news": n, "session": n}`. Refusal happens **in `simulate()`** at admission time using `entry_time` only (PIT: `ER.blocked(sym, at=entry_time, decision_time=entry_time, cal=cal)`, `S.primary(entry_time) in sessions`). A profile's own `session_restrictions` / `news_restrictions` apply on top (`AP.tighten_calendar`, `AP.entry_gate` session finding). The snapshot fields `news_rules` / `session_rules` (`scripts/snapshot.py`) record what was in force; `assess_run` stops calling `not_applicable("future_calendar_state", ...)` when a calendar is supplied and instead records the calendar snapshot id.

### 0.4 `decision-order.json`

Steps 3, 4, 14: `backtest` becomes `"scripts/backtest-methods.py simulate() -- admission-time refusal, entry_time only"`; step 4 `live` becomes `"scripts/strategy-runner.py tick() step 4 -- account_profile.entry_gate session_restrictions finding"` and the runner emits `tr.ok/block("session", ...)` from that finding instead of `tr.skip`.

### 0.5 Expectation producer (`scripts/expectation_producer.py`, new)

```python
def from_plan(plan: dict, methodology: str, *, series=None, created_at=None) -> dict   # expectation.create(...) record
def from_signal(sig: dict, st: dict, symbol: str, *, series=None, created_at=None) -> dict
```
`plan` = one `trades/index.jsonl` row (`entry`, `stop_loss`, `targets`, `direction`, `date_opened`, `setup_type`). `sig`/`st` = the runner's signal and setup rows (`sig["entry"|"stop"|"target"|"side"]`, `st["method"|"tf"]`). Kind: `ict` → `structural_objective`, `wyckoff` → `trading_range_objective` (both already in `methods.json expectation_kinds`). Path legs: `before_entry` = entry-area boundary (the entry itself when nothing finer is known, labelled `vùng vào lệnh`), `entry_area` = entry, `after_entry` = one leg per target `T1..Tn`. `invalidation = expectation.invalidation("stop", stop, owner=methodology)`. `methodology` for a runner method: `M.RUNNER_METHODS[st["method"]]` → its dimensions; COMBINED emits one record **per** dimension (§17: never merged). Records serialise with `expectation.to_json`.

### 0.6 Trade record carries expectations

`trades/index.jsonl` rows gain `expectations: [to_json(...)]` (schema already has `expectations`, `trade-file.schema.json:498`). `scripts/journal.py build_index()` copies the field; `build-artifact.py PLAN_FIELDS` gains `"expectations"`.

### 0.7 Chart decoupling (`scripts/build-artifact.py`, `scripts/chart.js`)

- `data_js[key]` gains `analysed=[...]` beside `engaged=[...]`.
- `chart.js` `drawnFor[key] = overlayLanes.includes(lane) && analysed.includes(lane)`; when drawn-but-not-engaged the legend shows i18n `chart.lane.not_in_confluence` (vi: "chỉ phân tích — không tính vào Confluence Score").
- `OVERLAY_LANES` is derived from the registry: `methods.json dimensions.<d>.overlay_engine: "ict" | "wyckoff" | null` (add the key; footprint/heatmap `null`). The four hard-coded `("wyckoff","ict")` sites (`build-artifact.py:151, :945, :1377, :1397`) read `OVERLAY_LANES` / `engaged` instead.
- New `expectationShapes(rows, plans, lane, fmt)`: for each plan expectation whose `original.methodology === lane`, one `hseg` per leg, label `${laneLabel}: ${phaseLabel} · ${leg.label} ${fmt(level)}`, `before_entry` legs drawn from the plan's index leftwards (i1 = max(0, idx-8)), `after_entry` rightwards to the edge, `entry_area` a short segment; the record's `status` is appended. Marker `data-ui-field="expected-path"` is kept where it is today.

### 0.8 System Ranking page (`scripts/system-ranking.py`, new)

Input: `docs/architecture/trading-systems.json` systems × `data/history/stability/*.json` rows matched by `(market, tf, method, cfg)` through `trading_system.setups(style)`. Row shape for `ranking.rank`: `{id, trading_system, setup_id, n, expectancy, max_drawdown, time_in_drawdown, not_ruined/ruin, account_failure_probability, prop_pass_probability, sortino, sharpe, positive_period_share, worst_period, objective, metrics, sample_size, validation_state, test_period, assumptions, robustness_status}` — §39 values copied from the stability row's `perf` block **unchanged** (an `unavailable` marker stays a marker). One table per objective in `ranking.json`, `exposure_report` rendered, no blended score. Output `data/live/.vi-system-ranking.html` (+ `en`), i18n through `scripts/i18n.py`. Register in `ui-fields.json`: `pages.ranking {built_by: scripts/system-ranking.py}`, area `System Performance & Ranking` `served_by: ["ranking"]`, markers `ranking-objective`, `ranking-sample-size`, `ranking-validation-state`, `ranking-test-period`, `ranking-assumptions`, `ranking-robustness`.

### 0.9 Trader constraints (`docs/architecture/trader-constraints.json`, `scripts/trader_constraints.py`, new)

```json
{"version": 1, "traders": {"tung": {"per_methodology": {"ict": [{"kind": "min_rr", "value": 3.0, "why": "..."}],
                                                        "wyckoff": [{"kind": "sessions", "value": ["london","ny_am"], "why": "..."}]}}}}
```
Kinds vocabulary (`_kinds`), each mapping to ONE existing knob: `min_rr → OPTS.min_rr` (only higher), `sessions → --sessions` (only narrower), `types → OPTS.types` (only subset), `htf → OPTS.htf` (only true), `ict_disp`, `ict_pd`, `sloped_gate` (only true), `max_trades_per_day → account rule` (only lower). Reader: `load()`, `for_trader(tid)`, `overlay(opts, tid, methodology)` → new OPTS dict, `refuses` when a value would LOOSEN. Backtest: `--trader <id>`; live: `strategy-runner.py` reads `automation-config.json execution.trader` (new key, default `null` = no overlay) and applies `overlay` at step 10. `trading_system.describe()["custom_constraints"]` resolves to the loaded list (`source` + `items`).

### 0.10 Improve loop (`scripts/improve-loop.py`, `docs/architecture/improve-candidates.json`, `docs/experiments/`, new)

`improve-loop.py --market crypto --tf 15m --symbols ... --method ICT --min-size 3 [--account ...] [--trader ...] --out docs/backtests/<date>-improve-<market>-<tf>.md`
1. Baseline: `scan` + `simulate` with the CLI's flags; record `research_ledger.periods()`; if `validation_available` is False every experiment records `validation_method = experiment.unavailable("in-sample only: no OOS period carved out (§44)")`.
2. Cluster LOSSES of the baseline by `(method, session=S.primary(entry_time), vol_type, via)` with `outcomes.cluster` semantics (`min_size`).
3. Candidates come from `improve-candidates.json`: a declared table `cluster_key_field → candidate OPTS/CLI override` (e.g. `session: asia → sessions: [london, ny_am, ny_pm]`; `vol_type: 3 → types: (1,2)`; `via: mss → ict_disp: true`). No candidate is invented at runtime; a cluster with no declared candidate is reported as such.
4. Run each candidate on the same data, same fee, same account; `experiment.Record(...)` per candidate with every §42 field set or `unavailable(reason)`; `experiment.write` into `docs/experiments/`; `decision` stays PENDING.
5. Report: baseline vs each candidate (n, expectancy, PF, max DD, failed_by, refused counts), ranked under `--objective` (default `expectancy`) via `ranking.rank`, an "outperformers" section = candidates better on the objective AND `n ≥ --min-trades`, and the sentence that a human decides (§41 stage 11). The script never writes `pilot-top5.json`, `methods.json`, or `trading-systems.json` (test greps for it).

---

## Phase 1 — WS-A ∥ WS-C

### WS-A — Backtest core (backend, one worker)

**Files:** Modify `scripts/backtest-methods.py`, `scripts/performance.py`, `scripts/snapshot.py`, `scripts/strategy-runner.py` (step 4 only), `docs/architecture/account-profiles.json`, `docs/architecture/decision-order.json`; tests `scripts/tests/test_backtesting.py`, `test_account_aware_backtest.py`, `test_performance.py`, `test_account_profile.py`, `test_decision_order.py` (exists? else `test_spec_priority.py`), new `scripts/tests/test_backtest_gates.py`.

#### Task A1: HTF filter leak
- [ ] Failing test in `test_backtesting.py`: build a synthetic 15m series + its 1H series where the *forming* 1H bar's close would flip `htf_allows`; assert `htf_allows` uses only bars whose **close time** `<= t`. Second test: the leakage probe (`leakage.probe`) runs with `OPTS["htf"]=True` on real BTCUSDT 15m and passes with `min_checked` > 0.
- [ ] Fix `htf_position` to key each row on the HTF bar's **close time** (`normalized.available_time` or `time + period`), keep `close` percentile; `htf_allows` docstring becomes true. Add `htf=True` to the probe matrix.
- [ ] `pytest scripts/tests/test_backtesting.py -q` green. Note in `docs/backtests/README` or the report caveat: stability config C rows produced before this fix are not comparable.

#### Task A2: prop profiles + performance shape + failure model
- [ ] Failing tests: `test_account_profile.py` — both ids load, `context_type == PROP_CHALLENGE`, `for_venue("mt5","demo")` still unique, `environment == "research"`; `test_performance.py` — `_account_terms` accepts `{"amount": 1e5, "currency": "USD"}`; `prop_pass_probability` for a profile with `max_daily_loss` is not `unavailable` and a synthetic R stream that loses 6 % in one day fails under it.
- [ ] Add profiles per §0.1. Fix `_account_terms`. Extend `_failure_thresholds` with `max_daily_loss` and `min_trading_days`; extend `_bootstrap` to a **day-block** resample when trades carry `entry_time` (group by UTC date; resample days; daily loss = day sum of `risk·R`), falling back to per-trade resampling with `max_daily_loss` reported `unavailable("no entry_time on trades")`.
- [ ] Suite green for those files.

#### Task A3: `--account` on the main report
- [ ] Failing test `test_backtest_gates.py`: run `backtest-methods.main()` (or `simulate` + report helper) with `--account ftmo-challenge-phase1` on the real 15m BTCUSDT history → report contains `failed_by` column and the profile id in the header; `SIM_LAST["account"]` is the profile.
- [ ] Implement per §0.3 (reuse `stability-report.py:84-95` loading; move that loader into `backtest-methods.py` as `load_account(args)` and have `stability-report.py` call it — one loader).
- [ ] Report table gains `Fail theo luật` column; caveat line names the account.

#### Task A4: calendar + session gates, both paths
- [ ] Failing tests (`test_backtest_gates.py`): (a) a calendar file with one HIGH event at T → a trade with `entry_time` inside `[T-10m, T+10m]` is refused, one at `T+11m` admitted, `SIM_LAST["refused"]["news"] == 1`; (b) `--sessions london` refuses an entry whose `S.primary` is `asia`; (c) a profile with `session_restrictions` refuses without `--sessions`; (d) refused trades never appear in `taken` and the equity curve is unchanged by them; (e) `snapshot` records `news_rules`/`session_rules`; (f) `assess_run` no longer marks `future_calendar_state` not-applicable when a calendar is given. Runner: `test_strategy_runner.py` — a profile with `session_restrictions` produces `tr.block("session", ...)`, otherwise `tr.ok("session")`.
- [ ] Implement §0.3 + §0.4.
- [ ] `pytest scripts/tests -q` green except the two pre-existing failures (`test_rank_setups_horizons`, `test_risk_model` fee) — report them unchanged.

**Exit criteria (WS-A):** `pytest scripts/tests/test_backtesting.py scripts/tests/test_backtest_gates.py scripts/tests/test_account_profile.py scripts/tests/test_performance.py scripts/tests/test_account_aware_backtest.py scripts/tests/test_strategy_runner.py -q` → 0 failed, log at `/tmp/ws-a.log`; `python3 scripts/backtest-methods.py --tf 15m --symbols XAUUSD --account ftmo-challenge-phase1 --sessions london,ny_am --out /tmp/ws-a-ftmo.md` exits 0 and the file names the account and refusal counts.

### WS-C — System Ranking page (backend+frontend, one worker)

**Files:** Create `scripts/system-ranking.py`, `scripts/tests/test_system_ranking.py`; modify `docs/architecture/ui-fields.json`, `docs/architecture/i18n.json` (new keys), `scripts/tests/test_ui_contract.py` (page build + markers), `scripts/publish-plan.py` only if it must know a new output (check `docs/architecture/artifacts.json` styles map — add `"system-ranking"` entry with `url: "PENDING"`).

#### Task C1: rows from registries
- [ ] Failing test: `system_ranking.rows()` returns one row per (trading system, selected setup) with every §48 exposure key present (value or `unavailable`), and `ranking.exposure_gaps(row) == []` for a row whose stability file carries a verdict stamp.
- [ ] Implement per §0.8. `validation_state` = the stability file's §38 verdict (`rank-setups.load_rows` logic — import it, do not copy); `test_period` = `first..last`; `assumptions` = fee + slippage from `risk_model`/`analysis-params.json` as the stability row states; `robustness_status` = `unavailable("no walk-forward / perturbation run recorded (§45)")` unless the row has one.

#### Task C2: the page
- [ ] Failing tests: page builds for both locales; contains one table per `ranking.json` objective in registry order; every `ranking-*` marker present; the string "best system" absent; an `unavailable` metric renders as `—` with its reason in `title=`; the exposure report lists rows missing exposures.
- [ ] Implement; `ui_contract.audit(html, "ranking")` clean. `test_ui_contract.py::test_an_area_with_no_page_says_why` updated (the area now has a page).

**Exit criteria (WS-C):** `pytest scripts/tests/test_system_ranking.py scripts/tests/test_ui_contract.py -q` → 0 failed, log `/tmp/ws-c.log`; `python3 scripts/system-ranking.py` writes `data/live/.vi-system-ranking.html` and `.en-system-ranking.html`.

## Phase 2 — WS-B ∥ WS-D (after WS-A merged into the tree)

### WS-B — Expectations + chart decoupling (frontend+backend, one worker)

**Files:** Create `scripts/expectation_producer.py`, `scripts/tests/test_expectation_producer.py`; modify `scripts/strategy-runner.py` (step 11 + the plan dict), `scripts/journal.py` (`build_index`), `scripts/build-artifact.py`, `scripts/chart.js`, `docs/architecture/methods.json` (`overlay_engine`), `docs/architecture/i18n.json`, `docs/architecture/trading-systems.json:142` (`produced_by` becomes true), `scripts/tests/test_ui_contract.py`, `scripts/tests/test_build_artifact.py`, `scripts/tests/test_methods.py`.

#### Task B1: producer
- [ ] Failing tests: `from_plan` returns a sealed record with 3 phases, `invalidation.owner == methodology`, `available_time` derived when `series` given; COMBINED signal yields two records (ict, wyckoff) that `paths_by_methodology` keeps apart; a plan with no targets raises (a path needs an after-entry leg).
- [ ] Implement §0.5.

#### Task B2: runner + index carry it
- [ ] Failing tests: `test_strategy_runner.py` — the plan the runner records has `expectations` (list of `to_json` blobs), one per dimension; `test_journal.py`-style test — `build_index` keeps `expectations`.
- [ ] Implement §0.6; step 11 `tr.ok("expectation", ...)` names the record ids.

#### Task B3: decouple overlays, registry lanes, draw expectations
- [ ] Failing tests: builder emits `analysed`; `OVERLAY_LANES == tuple(d for d in DIMENSIONS if overlay_engine)`; grepping `build-artifact.py` for `("wyckoff", "ict")` finds 0 hits; built page with a plan carrying expectations contains `expected-path` marker text with the methodology label and the phase label; a lane analysed-not-engaged renders `chart.lane.not_in_confluence`.
- [ ] Implement §0.7. Footprint/heatmap: **no** pane render branch (no live source, §57) — the registry key is `null` and the plan records the hook (`chart.js applyLane` pane switch) for when CoinGlass goes live.

**Exit criteria (WS-B):** `pytest scripts/tests/test_expectation_producer.py scripts/tests/test_ui_contract.py scripts/tests/test_build_artifact.py scripts/tests/test_methods.py scripts/tests/test_strategy_runner.py -q` → 0 failed, log `/tmp/ws-b.log`; `python3 scripts/build-artifact.py --check-only` (or the existing check flag) exits 0.

### WS-D — Trader constraints + improve loop (backend, one worker)

**Files:** Create `docs/architecture/trader-constraints.json`, `scripts/trader_constraints.py`, `docs/architecture/improve-candidates.json`, `scripts/improve-loop.py`, `docs/experiments/README.md`, `scripts/tests/test_trader_constraints.py`, `scripts/tests/test_improve_loop.py`; modify `scripts/backtest-methods.py` (`--trader`), `scripts/strategy-runner.py` (step 10 overlay), `scripts/trading_system.py` (`custom_constraints`), `docs/architecture/automation-config.json` (`execution.trader: null`), `.claude/commands/improve.md` (call the script, then reason over its report).

#### Task D1: constraints registry
- [ ] Failing tests: reader loads; unknown kind refused at import; a `min_rr` lower than the platform floor refused; `overlay(OPTS, "tung", "ict")` returns tightened OPTS and leaves the input untouched; `describe(style)["custom_constraints"]["items"]` lists them; backtest `--trader tung` changes `SIM_LAST["opts"]`.
- [ ] Implement §0.9.

#### Task D2: improve loop
- [ ] Failing tests (on a small real slice, e.g. BTCUSDT 15m last 90 days): the script writes ≥ 1 experiment record to a temp store with `decision == PENDING`; every record `seal()`s; the report lists baseline + candidates and the "human decides" line; the script source contains no write to `pilot-top5.json` / `methods.json` / `trading-systems.json`; a cluster with no declared candidate appears under "không có ứng viên khai báo".
- [ ] Implement §0.10. `docs/experiments/README.md` explains the store and that records are immutable.

**Exit criteria (WS-D):** `pytest scripts/tests/test_trader_constraints.py scripts/tests/test_improve_loop.py scripts/tests/test_trading_system.py -q` → 0 failed, log `/tmp/ws-d.log`; `python3 scripts/improve-loop.py --market crypto --tf 15m --symbols BTCUSDT --method ICT --out /tmp/ws-d-improve.md` exits 0.

## Phase 3 — WS-E integration (main session)

- [x] `pytest scripts/tests -q` full run; only the two pre-existing failures may remain, listed by name.
- [x] Evidence runs (FTMO: /tmp/ws-a-ftmo.md; ranking page; improve report docs/experiments/2026-09-18-improve-crypto-15m-ict-session-asia.json): FTMO backtest on XAUUSD 15m with sessions + calendar → `docs/backtests/2026-09-18-ftmo-xauusd-15m.md`; `system-ranking.py` page; `improve-loop.py` report.
- [x] Update `docs/architecture/SPEC-COMPLIANCE.md` rows §17, §21, §24–§32 (backtest), §33, §37, §41, §48, §50; update `docs/audits/2026-09-18-feature-audit.md` with a "Đã đóng" column.
- [x] §60 self-review checklist against `CLAUDE.md`; §61 final report to the user.

## Phase 4 — WS-F end-to-end drill: a real order from a real signal path (main session, user request 2026-09-18)

**Why.** Tests prove functions; they do not prove that a signal the Scalping/Day/Swing artifact shows becomes an order at the venue and comes back to the page as an OPEN trade. The user asked for that to be verified with real actions, not test cases.

**Preconditions (checked 2026-09-18, all true):** `automation-config.json execution.environment == "demo"`; `scripts/binance-futures-testnet-order.sh check` → ping ok, keys present, USDT ≈ 4990 on the futures TESTNET, no open position; `scripts/mt5-order-bridge.py check` → `trade_mode: demo`, EA attached, symbols XAGUSD/XAUUSD; pilot loop is STOPPED (`data/live/pilot-futures/STOP` since 2026-09-13) so nothing else places orders while the drill runs.

### Contract 0.11 — `strategy-runner.py --drill <setup-id>:<symbol>:<long|short>` (demo only)

- Refused unless ALL hold: `--live` given, `execution.environment == "demo"`, `automation_gate()` is None, the venue key is a testnet/demo key (`trading_env` environment file is `config/env.demo`). Any other state exits 2 with the reason. Refused in `--dry-run`.
- Effect: for exactly that (setup, symbol, side) the `sigs` list is replaced by ONE synthetic signal built from the last CLOSED bar: `entry = close`, `entry_now = True` (market), `stop = entry ∓ max(0.4 %, 1.5 × mean(true range, 20))`, `target = entry ± 3.0 × |entry − stop|` (so the R:R floor passes on its own), `time = mss_time = bar time`, `vol_type = 1`, `r_planned = 3.0`, `drill = True`. **Every other step of the decision walk runs unchanged** (data quality, event precheck, session, account, HTF gate, risk calculation and validation, final news, eligibility, `tr.verify()`), so a refusal is a real refusal and is logged with its trace.
- `client_id()` for a drill signal is `drill-` + the usual hash; the `signal`/`entry`/`exit` log rows carry `drill: true`; `journal.sync_pilot` copies `drill` into the trade file and index; `journal` rollups (EDGE-LOG, MISTAKE-DB) and `outcomes.ingest` exclude `drill: true` rows (a drill is not evidence of an edge).
- Tests (`scripts/tests/test_strategy_runner.py`): refused when environment is `real`; refused without `--live`; the synthetic signal has `r_planned == 3.0` and `entry_now`; the client id starts with `drill-`; a drill row is excluded from `journal` rollups and from `outcomes.ingest`.

### Steps (each with evidence written under `docs/audits/2026-09-18-e2e-drill/`)

- [x] F1 Implement 0.11 with TDD (2026-09-18: `strategy-runner.py --drill`, `drill_signal/parse_drill/drill_refusal`, journal + outcomes exclusion, schema `drill`; DRILL_RR raised to 3.5 gross because the R:R floor is NET of fees). `pytest scripts/tests/test_strategy_runner.py scripts/tests/test_outcomes.py -q` green.
- [x] F2 Crypto drill: `python3 scripts/strategy-runner.py --live --drill <crypto-scalping-setup>:BTCUSDT:<side aligned with htf_pass>`; save stdout + the new `top5-log.jsonl` rows (`signal` with `ok: true`, `entry` with order id) to `f2-runner.log`. Venue check: `binance-futures-testnet-order.sh position-risk BTCUSDT` shows the position; `order-by-client-id BTCUSDT drill-…` shows the order FILLED; save both JSON.
- [x] F3 CFD drill: `--drill <cfd-scalping-setup>:XAUUSD:<side>` → `mt5-order-bridge.py position-status <ticket>` shows the position with SL/TP; save JSON.
- [x] F4 Page round-trip: `python3 scripts/journal.py all` → `trades/<id>.md` status OPEN with the real order id and fill; `python3 scripts/build-artifact.py scalping` and `cfd-scalping` → open `file://…/data/live/.vi-scalping-live.html` and `.vi-cfd-scalping-live.html` in Playwright; assert the plan overlay label contains `LONG|SHORT <trade id> · R:R 3.00 · OPEN`, `data-ui-field="actual-path"` and `expected-path` present, entry/stop/T1 numbers equal the log row (to the venue's tick); screenshots `f4-scalping.png`, `f4-cfd-scalping.png`.
- [x] F5 Close: `python3 scripts/strategy-runner.py --flatten` → both positions closed (`position-risk` empty, `position-status` closed); `journal.py all` → trade files CLOSED with `drill: true`; page rebuilt shows no open plan; screenshots `f5-*.png`.
- [x] F6 Latency: `python3 scripts/latency.py` now has `order_submission` / `provider_acknowledgement` observations (n ≥ 2); paste the summary into `f6-latency.txt`.
- [x] F7 Write `docs/audits/2026-09-18-e2e-drill.md`: what was ordered, where, what the page showed, what refused (if anything), and the exact commands — so the drill can be repeated.

**Hard rules for the drill:** never on `real`; never while the pilot loop is running; one drill position per venue at a time; always flattened before the session ends; a drill that is REFUSED by the walk is reported as such, not retried with a looser signal.

## Out of scope (stated, not silently dropped)

- OKX / Bookmap providers (new adapters; §57 until data exists).
- Footprint/heatmap chart panes (no live source).
- Per-methodology parallel model reads (`model-read.sh` runs per style; the order path is unaffected — audit §2.3).
- Regenerating CFD stability data at the correct MT5 fee (fixes the pre-existing `test_risk_model` failure; a data run the user should schedule).
