# Goal state — CLAUDE.md §1–§62 compliance

**Goal:** Every one of CLAUDE.md's 62 sections implemented and cumulatively verified, with real
browser verification (Playwright) of anything that reaches a page.

**Confirmation of record:** user pre-authorized ("Continue until all done", `/goal tiếp tục đến khi
toàn bộ 62 phần trong CLAUDE.md hoàn thành và test real với Playwright"). No confirmation round taken;
this file is the confirmation.

## Success criteria (all must pass)

1. `cd scripts/tests && python3 -m unittest discover -s . -p 'test_*.py'` exits 0 with no failures.
2. Every §1–§62 row in `docs/architecture/SPEC-COMPLIANCE.md` reads MET / CLOSED / POLICY / INVARIANT,
   or carries an explicit, argued verdict of what is deliberately not built and why.
3. `python3 scripts/sync-instruments.py --check`, `sync-methods.py --check`, `sync-sessions.py --check`
   all exit 0 (no registry drift).
4. Every page builder produces `BUILD OK` and the built page is opened in a real browser:
   `document.characterSet === "UTF-8"`, zero console errors, lane switching works.
5. `python3 scripts/strategy-runner.py --replay all --bars 500` exits 0 and emits its §20/§38
   data-quality flags.
6. Final full-system report naming any MISSING / PARTIAL / INCORRECT / UNVERIFIABLE item with evidence.

## Routing gate (rules/workflow-routing.md)

Trust boundary: NO new external surface, no new credential path, no new vendor — this is spec
compliance inside one repo. Domains: 1 (the trading codebase). → **Fast path**: implement directly with
per-section verification. Project `CLAUDE.md` §0.1 independently requires this ("Master Agent owns final
implementation"; "Do not spawn agents merely because they are available"). Re-run this gate if a section
turns out to need a new provider connector or a credential path.

## Method (per section N, from the user's original instruction)

IMPLEMENT N → VERIFY N → VERIFY 1…N (full suite) → browser-verify if it reaches a page → record in
`SYSTEM-DESIGN.md` + `SPEC-COMPLIANCE.md` → next.

## Status

Done and recorded: **§1–§62 — all 62 sections**.
Suite at last green: **1738 passed**. Final full-system pass run 2026-09-18 (see the Final verification section below). Browser-verified after §38 (crypto scalping: UTF-8, 297 canvases, 9 sections, lane + language
switch live, 0 mojibake; cfd-scalping: UTF-8, 66 canvases, XAU/XAG — USOIL/UKOIL left the execution list
on 2026-09-18 — Wyckoff header marked *analysis only*, ICT the only decision lane, no page console errors).

| § | title | state | verify |
|---|---|---|---|
| 1–23 | … | DONE | ledger rows MET/CLOSED; suite 927 |
| 24–32 | EVENT RISK (whole cluster) | **DONE** | `test_event_risk.py` 62 tests; 3 order-path defects closed |
| 33 | ACCOUNT PROFILE | **DONE** | `account-profiles.json` + `account_profile.py`; 63 tests incl. 5 through a real `tick()`; A1 closed |
| 34 | RISK MODEL | **DONE** | `risk_model.py`; net-of-fee R:R floor (live defect closed); 37 tests |
| 35 | TRADING SYSTEM | **DONE** | `trading-systems.json` + `trading_system.py`; 46 tests; classification enforced on the order path, not just declared |
| 36 | DECISION ENGINE | **DONE** | `decision-order.json` + `decision_order.py`; per-signal `decision_trace`; 33 tests; 3 live defects closed (step 3 absent, step 12 ran at 17, min_notional key order) |
| 37 | BACKTESTING | **DONE** | `leakage.py` mutate-the-future prober (mutation-tested); backtest column on all 17 steps; R:R floor moved to net — a §59 semantics change |
| 38 | BACKTEST INVALIDATION | **DONE** | `research-validity.json` + `research_validity.py`; 52 tests; verdict above the tables, `rank-setups` refuses INVALID sources; `--combined-entry hindsight` now invalidates |
| 39 | PERFORMANCE METRICS | **DONE** | `performance-metrics.json` + `performance.py`; 54 tests; MFE/MAE now measured in `walk()`; risk-of-ruin bootstrap bug found and fixed; no universal score |
| 40 | HOT PATH ISOLATION | **DONE** | `latency-model.json` + `latency.py`; 40 tests incl. 8 regression benchmarks; journal sync detached from the order loop; p50/p95/p99/max now exist |
| 41 | FAILURE LEARNING | **DONE** | `outcomes.json` + `outcomes.py`; 51 tests; 5 of 8 states were unrepresentable, 36 invisible evaluation states surfaced; approval structurally blocked until §44/§45 exist |
| 42 | EXPERIMENT INFRASTRUCTURE | **DONE** | `experiments.json` + `experiment.py`; 28 tests; sealed records, hash-checked, decision = successor not edit |
| 43–44 | EXPERIMENT BUDGET / OOS EXPOSURE | **DONE** | `research-ledger.json` + `research_ledger.py`; 32 tests; counters derived from the store, unrecorded≠zero, exposure one-way; **no period can validate anything today** |
| 45 | VALIDATION | **DONE** | `validation.json` + `validation.py`; 39 tests; NOT_RUN counts against; methods take an evaluator so they are testable |
| 46–47 | REPRODUCIBILITY / VERSIONING | **DONE** | `versioning.json` + `versioning.py`; 37 tests; §46 enforced at the COMPARISON; rejected candidate numbers stay spent |
| 48–49 | RANKING / NEWS A/B | **DONE** | `ranking.json` + `ranking.py`; 32 tests; lexicographic only, A/B refuses unequal arms and reaches no verdict |
| 50 | UI / UX | **DONE** | `ui-fields.json` + `ui_contract.py`; 27 tests that BUILD the pages; 22/22 on both chart styles, 6/6 panel, 5/5 journal; browser-verified, 0 console errors |
| 51 | EXECUTION SAFETY | **DONE** | `execution-safety.json` + `execution_safety.py`; 27 tests; the standing gap CLOSED — key scope is read from the provider and UNKNOWN never reads as NO_WITHDRAWAL; 4 DoNotWeaken tests |
| 52 | REALTIME DATA | **DONE** | `feed-health.json` + `feed_health.py`; 28 tests; 6 of 10 apply to a polling transport, 4 exempt with a stated trigger; **two false positives found by running it against the live feeds** |
| 53 | ADR | **DONE** | `docs/adr/` 11 decisions + generated index; `adr.py`; 20 tests; 32 rejected alternatives indexed, re-proposal raises |
| 54–55 | TESTING / ADVERSARIAL | **DONE** | `test-coverage.json` + `test_coverage.py`; 17 tests; 29/29 + 52/52, every citation resolved against a real test; the §62 critical invariant has 3 guards |
| 56–62 | POLICY / INVARIANT | **DONE** | `policy.json` + `policy.py`; 30 tests; §56 artifacts all present, §57 scan finds nothing (mutation-tested), §58 10 of 19 enforced and 9 declared conventions, §59 four semantics changes recorded with what each invalidates, **§60 35/35 questions resolve to a real test** (`python3 scripts/policy.py --review`), §61 16 items as data, §62 the same three guards §55 cites |

## User decisions on record (2026-09-18)

- **B1 CoinGlass `underlying_venues`** — user: "nợ sẽ trả sau". `["UNDECLARED"]` stays; it is the honest
  value until a real API response is read. No work scheduled.
- **B3 SPOT vs PERPETUAL (§20.1)** — user chose **(a)**: fetch perp klines and analyse the instrument that
  is actually traded, **done at §37** so every backtest is re-run in one pass. `fapi/v1/klines` is public and
  the same shape as the spot endpoint. Consequence accepted: existing backtest results stop being comparable
  and must be regenerated.
- **B4 CFD history (§23.1)** — **export DONE 2026-09-18** on MetaQuotes-Demo (the account the pilot trades).
  XAUUSD + XAGUSD, 1W/1D/4H/1H/15m, gold back to 2004 on 4H/1D/1W. Server timezone **measured from the data**
  (session frame, seasonal volatility peak, EU-vs-US DST test) = EET/EEST, EU rules, `Europe/Helsinki` — not
  assumed. Inventory + evidence in `docs/architecture/mt5-history-export.md`. **Oil is NOT on this account:**
  USOIL/UKOIL have no symbol, no bridge feed, and keep the Yahoo front-month futures proxy, so §23.1 comes off
  for metals only. **Registry question CLOSED 2026-09-18, user chose (c):** USOIL/UKOIL removed from
  `execution.cfd` (analysis unchanged), EA allowlist narrowed + recompiled, `rank-setups.py` symbol defaults
  derived from the registry so they cannot creep back. **`scripts/import-mt5-history.py` written** (24 tests):
  server time -> UTC with the zone read from `providers.json mt5_bridge.server_timezone`, four refusals
  (no zone / wrong server / a `Z` already present / a nonexistent-or-ambiguous local time), §20 check before
  anything is written, `--write` off by default. Dry run is clean for all 10 series.
  **Awaiting the user's go on `--write`** — it replaces the Yahoo futures history and makes every existing
  CFD backtest and ranking stale (§59).
- **A1 `MAX_OPEN` per-venue** — **CLOSED 2026-09-18** at §33: the cap is the MT5 account's `max_positions`
  rule, derived across every market routed to that venue (cfd + forex = 11, was len(CFD) = 4).
- **A2 provider selection / execution router** — folded into §36 (Decision Engine), so the router lands after
  the decision ordering that defines it.

## Known blockers / carried debt

- ~~§32 event-risk fail-open~~ — **CLOSED 2026-09-18**. Now fails closed with the configured action.
- §20.1 crypto analysis reads SPOT while the pilot executes PERPETUAL (recorded, not a defect to fix).
- §23.1 CFD backtests read Yahoo front-month futures, not the traded CFD (recorded).
- `underlying_venues: ["UNDECLARED"]` for coinglass until a real API response is read.

## Follow-ups (out of scope, do not expand into)

- Building a `trades_raw` feed (§22) — no provider declares it; would be speculative.
- Attaching MT5 charts for the 7 FX majors (§6) — a terminal action, not a code change.


## Final full-system verification (2026-09-18)

Run against the whole CLAUDE.md specification, not against the checklist above.

- `python3 -m pytest scripts/tests -q` -> **1738 passed, 90 subtests**.
- `python3 scripts/policy.py --review` -> **35/35** §60 questions resolve to a real test.
- `python3 scripts/policy.py` -> §56 artifacts all present; §57 speculative scan finds nothing.
- `python3 scripts/ui_contract.py --audit` -> chart 22/22 (both styles), panel 6/6, journal 5/5.
- Browser (Playwright, 127.0.0.1): 22 fields rendered with real values, 297 canvases, UTF-8, 0 mojibake, 0 console errors.
- `strategy-runner.py --report` and `--dry-run`: live path runs; halts on the STOP file, which is correct.
- `backtest-methods.py --symbols BTCUSDT --tf 1H`: research path runs and stamps a §38 **FLAGGED** verdict.

### Three defects the pass found (all fixed, all regression-tested)

1. **§8 had two implementations and the live path used the weaker one.** `event_risk._parse()` assumed UTC for
   a naive datetime; with both sides naive `visible()` answered a point-in-time question in an unnamed clock,
   and with one side aware it raised a bare `TypeError` instead of a §8 refusal. `pit._aware()` refuses a naive
   timestamp outright. `event_risk._parse` now IS `pit._aware`. 3 regression tests.
2. **The §9 bias register was stale in the safe direction** -- five rows still said NOT GUARDED for things
   §38-§45 had since built. Now 5 guarded, 2 accounted-not-prevented, 3 partial, 1 unguarded and structural
   (survivorship).
3. **The §3 layer map named three layers NO ARTIFACT that now have one** (Evidence, Account Profile, Execution
   Router) and two as absent that are §39/§44/§45/§48.

### What is still not MET, honestly

- **§2 provider SELECTION.** The registry lists what exists; nothing routes to a different market-data or
  execution provider for a market. There is one crypto market-data provider and one unattended execution
  provider per market, so building the router now would be speculative under §57.
- **§4 order submission stays venue-shaped** -- 6 `if venue == "mt5"` branches at the adapter boundary, which
  `SYSTEM-DESIGN.md` §16.1 says is where they belong. Down from ~12.
- **§9 survivorship bias** -- structural. Closing it needs a delisted-symbol universe this repository does not
  have.
