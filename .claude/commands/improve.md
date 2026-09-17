---
description: System-wide controlled-improvement proposal (Observe -> Measure -> Pattern -> Propose -> KEEP/TEST/ADOPT/REJECT). Never silently applies a change.
argument-hint: [optional focus, e.g. "Spring type 1 win rate" or "STRICT mode threshold"]
---

**Model gate (SYSTEM-DESIGN.md §14).** This command reasons (the safety-critical-rule check below is a judgment). If you are running as Haiku, do not execute it in this session: dispatch one `general-purpose` subagent with `model: sonnet` to run this command with the same `$ARGUMENTS` and relay its output verbatim.

Dispatch **learning-agent** for the `/improve` procedure (`.claude/skills/learning-skill/SKILL.md`), scoped to the focus in `$ARGUMENTS` if given, else a general scan of `trades/index.jsonl` for the most statistically-notable pattern. Require the agent to state sample size and whether it's adequate for the specific claim before proposing anything. Present the full proposal template (Current Rule / Observed Problem / Evidence / Proposed Change / Expected Benefit / Potential Risk / Validation Required / Recommendation) to the user verbatim — do not summarize away the KEEP/TEST/ADOPT/REJECT recommendation. If the proposal touches a safety-critical rule (risk ceiling, instrument allowlist, invalidation requirements, Analysis≠Execution separation), say so explicitly and stop — do not edit `docs/architecture/SYSTEM-DESIGN.md` or `risk-config.json` yourself even if the user says "sounds good," without their explicit follow-up instruction to make that specific edit.
