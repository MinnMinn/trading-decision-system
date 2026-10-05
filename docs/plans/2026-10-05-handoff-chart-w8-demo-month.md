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

## Action 1 — W8 on the chart (small)

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
