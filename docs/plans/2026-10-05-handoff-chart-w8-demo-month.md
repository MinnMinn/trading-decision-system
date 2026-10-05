# Handoff — chart W8, FTMO demo month, open items (2026-10-05)

Written so another session can continue if this one stops. Branch `claude/funny-galileo-4fyyn8`, PR
MinnMinn/trading-decision-system#9 (open, not merged). Owner messages are quoted; everything else is state.

## Owner decisions in force (2026-10-05)

- "Vì hiện tại các phương pháp ICT/Wyckoff khi backtest đều chưa có kết quả khả quan, nên hãy bám sát theo sách để vẽ
  đúng trên chart. Tao sẽ review các chart này để tự vào lệnh rồi đánh giá." → charts follow the books; mechanical
  ICT/Wyckoff do not trade.
- "W8 cho chart, ok" → the chart applies W8 (CHoCH inside the SC–AR box, WA p68–69); the backtest engine keeps W8 off
  (`wyckoff_rules.PARAMS` / `backtest-methods.OPTS` stay False; docs/audits/2026-10-05-w8-backtest.md).
- "12/10, ok" → the one-month FTMO demo forward test starts Monday 2026-10-12 (FTMO server day), book v4
  (H7 + G9 XAUUSD, stop_k 1.4) on account `ftmo-demo-01`, plus the owner's own discretionary trades from the charts.
- Already done: ICT chart swings 1 bar (`scripts/build-artifact.py` `CHART_ICT_OPTS`); engine default stays 3
  (docs/audits/2026-10-05-ict-pivot-width-backtest.md: 1 bar not better, nothing overwritten). Sessions v3 (London
  02:00–05:00 New York, index killzones). W8 stays off for decisions.

## Action 1 — W8 on the chart — DONE (structures.ENVELOPE_PARAMS = W8_PARAMS; tests pass)

- `scripts/structures.py`: `ENVELOPE_PARAMS` is currently `W.PARAMS` (ADR 0009 "chart = decision"). Set it to
  `W8_PARAMS` (`dict(W.PARAMS, fx_w8_choch_in_box=True)`) and rewrite its comment: no mechanical Wyckoff system trades
  (pilot-selection.json `setups` empty), the chart is the owner's discretionary tool, so it follows the book.
  Record this as a stated exception to ADR 0009 rule 1 (a dated note in docs/audits/2026-10-04-wyckoff-chart-fidelity.md
  and the W8 audit's owner-decision section). Revert condition: if a Wyckoff Trading System is ever enabled, chart and
  decision must use the same PARAMS again.
- The `choch_outside_box` flag in chart.js then never fires (no such structure is drawn); keep the code (harmless).
- Tests to update: `scripts/tests/test_wyckoff_chart_fidelity.py`
  - `W8ChochInsideBox.test_chart_detects_with_the_decision_params_and_w8_stays_off` → assert
    `structures.ENVELOPE_PARAMS["fx_w8_choch_in_box"] is True`, `W.PARAMS[...] is False`, bt.OPTS False;
  - `NarrativeContractOnEngineOutput` should pass again without the `choch_outside_box` exemption (keep it, harmless).
- Run: `cd scripts/tests && PYTHONPATH=.. python3.12 -W ignore -m unittest test_wyckoff_chart_fidelity test_structures
  test_build_artifact test_doc_citations` (one module per call is safer; python3.12 only).

## Action 2 — pre-register the demo month (before 2026-10-12)

New file `docs/plans/2026-10-12-ftmo-demo-month-preregistration.md`, committed BEFORE the first trade of 10-12:
- What runs: book v4 (trading-systems.json on `claude/challenging-the-system`, assignment in accounts.json there), the
  owner's discretionary trades (logged with `/journal`: method, setup, chart screenshot at entry, plan, outcome).
- Expectations from backtest for v4 over ~21 trading days: expected trade count, mean R, R distribution, max
  drawdown, fill rate and slippage — take them from docs/audits/2026-10-04-a1-under-tolerance*.md /
  docs/audits/2026-10-02-pass-policy.md on that branch (read, do not recompute on new data).
- Decision rules fixed in advance: "consistent with backtest" vs "anomalous" bands (e.g. realised mean R outside the
  backtest's monthly 5–95 % band; slippage above the cost model), and the statement that ~20–40 trades is weak
  evidence (report, not verdict). FTMO rules (5 % daily, 10 % max) are hard stops.
- Discretionary trades are reported separately and never pooled with the mechanical book.

## Action 3 — monthly report script

`scripts/demo-month-report.py` (new): inputs = executor log/state under `data/live/accounts/ftmo-demo-01/`, MT5 deal
history export, `trades/` journal; outputs `docs/reports/2026-11-demo-month.md` with: per-trade table, realised vs
backtest expectation, fills/slippage vs cost model, FTMO rule headroom, discretionary trades by method/setup.
Tests: fixtures only, no venue access. Keep it read-only.

## Action 4 — get master to match the demo

Book v3/v4 live only on `claude/challenging-the-system` (session "Challenging the system"). Master still has book v2
(with E5). Merge order: PR #9 (this branch) and a PR for that branch; resolve conflicts in
trading-systems.json/accounts.json in favour of v4 (append-only assignments). Do not push to that branch from here.

## Open threads

- Claude ICT discretionary experiment (session "Challenging the system", branch `claude/challenging-the-system`):
  paused at 236/338 decisions (owner's machine off), decisions committed ebb2b4a, cost so far 34.74 USD. Resume
  generates the rest (no regeneration), then commit decisions.jsonl, then evaluate ONCE. Reviewer conditions are in
  amendment 2 (6fd200f). Review of harness/evaluator: no blocking issue.
- PR #9 test status: full suite was running on the head before the pivot audit; last known re-run of the affected
  modules passed after the sessions-v3 test updates (test_speed_equivalence IctPoolKeyChangesTrades now uses a
  30k-bar slice). Re-run the full suite before merge: scratchpad script equivalent =
  `cd scripts/tests && ls test_*.py | grep -v test_speed_equivalence | sed 's/\.py$//' | xargs -P 2 -I{} sh -c
  'PYTHONPATH=.. timeout 3000 python3.12 -W ignore -m unittest {} > /tmp/{}.log 2>&1 || echo FAIL {}'`, then
  `test_speed_equivalence` alone (~35–55 min). test_automation_integrity / test_automation_instrument_set can fail
  only when run in parallel with each other (they write the same config file) — run them alone before calling it real.
- Safety constraints unchanged: demo only, risk ≤ 1 % (risk-config.json), allowlist = instruments.json, never commit
  config/env.*.

## Status at handoff (end of 2026-10-05 session)

- Action 1 done. Full suite on the head before Action 1: 136/137 modules OK; the one failure (test_pit_page, the chart
  now reads 1-bar ICT swings) is fixed. test_speed_equivalence result of that run not yet read. After Action 1 the
  Wyckoff chart modules (test_wyckoff_chart_fidelity, test_structures, test_build_artifact, test_doc_citations,
  test_pit_page) pass.
- Actions 2, 3 and 4 not started. Action 2 must be committed before 2026-10-12.

## Owner decisions, later 2026-10-05 — supersede the W8/pivot lines above

- "chuyển mặc định sang 1 nến" → `analysis-params.json` `project_defined.ict.pivot_bars` = 1 (engine default; owner
  chose this knowing docs/audits/2026-10-05-ict-pivot-width-backtest.md favoured 3). `CHART_ICT_OPTS` is now redundant.
- "W8 ... bật cho cả setup hiện tại của Wyckoff" → `wyckoff_rules.PARAMS fx_w8_choch_in_box=True`,
  `backtest-methods.OPTS fx_w8_choch_in_box=True`, `stability-report.config_opts` True; `structures.ENVELOPE_PARAMS =
  W.PARAMS` again (chart = decision, ADR 0009 holds again). Both are Trading-System-version significant for any ICT /
  Wyckoff system (none is enabled). Past results stay reproducible from their recorded git sha.
- Code changed and pushed in commit "Owner 2026-10-05: ICT pivot default 1 bar, W8 ON for Wyckoff setups (tests pending)".

### Action 5 — update the tests that pinned the old defaults (PR #9 is NOT mergeable until done)

Failing after the change (each pins "v1 = pivot 3" or "W8 default off"); update each to the new defaults, keeping the
intent (a key still separates cache entries, the frozen copies are compared with the SAME params, etc.):
- test_wyckoff_chart_fidelity: test_chart_detects_with_the_decision_params_and_w8_stays_off (assert W8 ON everywhere,
  ENVELOPE_PARAMS is W.PARAMS), test_every_chart_record_has_its_choch_inside_the_box and
  test_outside_box_flag_matches_the_w8_filter (compare W8-on vs an explicit `dict(W.PARAMS, fx_w8_choch_in_box=False)`).
- test_wyckoff_fidelity: test_cache_key_is_widened_by_each_detection_key, test_cache_is_keyed_on_each_detection_fx_key
  (×5) — they flip each key False→True; for fx_w8 the baseline is now True (flip True→False).
- test_v_items_wyckoff: test_baseline_params_copy_is_exactly_the_v1_copy (`_fx_detection_opts()` is no longer all False).
- test_structures: 4 tests comparing structures.wyckoff_records with a direct detect_* call without P (pass the same P).
- test_wyckoff_detect_equivalence: test_random_series_match_frozen (frozen copy predates W8; pass P with W8 off to both,
  or add W8-on equivalence).
- test_ict_fidelity: test_v1_default_excludes_the_one_bar_pivot (v1 default is now 1 bar; fx_b1_pivot1 is a no-op).
- test_audit_round2_ict (2) and test_ict_candle_invariants (1): fixtures built for 3-bar pivots; rebuild for 1-bar or
  pass opts that reproduce the fixture's width.
- Expect more in the full suite (earlier run with pivot 1 also failed test_pit_w7_b3 vacuity guards — thresholds need
  re-measuring — and test_speed_equivalence ICT differentials: BaseSnapshot extracts BASE's analysis-params.json, so copy
  the CURRENT analysis-params.json into the snapshot like sessions.json, then re-check the b1/pool "changes trades" tests).
Then run the full suite (see "Open threads") and only then ask the owner to merge PR #9.
