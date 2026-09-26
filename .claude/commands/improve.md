---
description: System-wide controlled-improvement proposal (Observe -> Measure -> Pattern -> Propose -> KEEP/TEST/ADOPT/REJECT). Never silently applies a change.
argument-hint: [optional focus, e.g. "Spring type 1 win rate" or "STRICT mode threshold"]
---

**Model gate (SYSTEM-DESIGN.md §14).** This command reasons (the safety-critical-rule check below is a judgment). If you are running as Haiku, do not execute it in this session: dispatch one `general-purpose` subagent with `model: sonnet` to run this command with the same `$ARGUMENTS` and relay its output verbatim.

**Step 1 — run the evidence-producing loop, not just prose.** Before dispatching the learning agent, run
`scripts/improve-loop.py` (CLAUDE.md §41 stages 1-4 + §42, docs/plans/2026-09-18-close-feature-gaps.md §0.10)
for the market/timeframe/method the focus in `$ARGUMENTS` names, or a reasonable default (crypto 15m, the
method with the most closed trades in `trades/index.jsonl`) when no focus is given:

```
python3 scripts/improve-loop.py --market <market> --tf <tf> --symbols <symbols> --method <RUNNER_METHOD> \
  --out docs/backtests/<date>-improve-<market>-<tf>.md
```

This clusters repeated LOSSES from the baseline, runs every DECLARED candidate override
(`docs/architecture/improve-candidates.json`) against the same data, and seals one
`docs/experiments/<id>.json` record per candidate run (`decision: PENDING`) — the artifact §42 requires and
this repo did not produce before. It never touches `pilot-selection.json`, `methods.json`, or
`trading-systems.json`.

**Step 2 — reason over the report, do not re-derive it.** Dispatch **learning-agent** for the `/improve`
procedure (`.claude/skills/learning-skill/SKILL.md`), scoped to the focus in `$ARGUMENTS` if given, else a
general scan of `trades/index.jsonl` for the most statistically-notable pattern. Give the agent the report
path from Step 1 and the experiment record paths it names; the agent reasons over THAT evidence (outperformers
vs baseline, sample size, which clusters had no declared candidate) rather than re-running its own ad hoc
backtest. Require the agent to state sample size and whether it's adequate for the specific claim before
proposing anything. Present the full proposal template (Current Rule / Observed Problem / Evidence / Proposed
Change / Expected Benefit / Potential Risk / Validation Required / Recommendation) to the user verbatim — do
not summarize away the KEEP/TEST/ADOPT/REJECT recommendation, and cite the `docs/experiments/*.json` record(s)
the recommendation is built on. If the proposal touches a safety-critical rule (risk ceiling, instrument
allowlist, invalidation requirements, Analysis≠Execution separation), say so explicitly and stop — do not edit
`docs/architecture/SYSTEM-DESIGN.md` or `risk-config.json` yourself even if the user says "sounds good,"
without their explicit follow-up instruction to make that specific edit. Adopting a candidate (editing
`pilot-selection.json` / `methods.json` / `trading-systems.json`) is always this human decision, never an automatic
step of `/improve` or of `scripts/improve-loop.py`.
