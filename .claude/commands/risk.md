---
description: Standalone position-size / R:R calculator. Also the command for logging a throttle override.
argument-hint: <entry> <stop> [risk_pct override] [--override-throttle "reason"]
---

**Model gate (SYSTEM-DESIGN.md §14).** This command reasons (the override handling and what gets recorded are judgments). If you are running as Haiku, do not execute it in this session: dispatch one `general-purpose` subagent with `model: sonnet` to run this command with the same `$ARGUMENTS` and relay its output verbatim.

Dispatch **risk-agent** directly with the entry/stop (and optional target list) given in `$ARGUMENTS`, reading defaults from `docs/architecture/risk-config.json` unless overridden. If `--override-throttle` is present, this is an explicit, human-logged exception to the consecutive-loss throttle — risk-agent should still report the throttle was active, but proceed at the requested risk % (capped at the 1% absolute ceiling regardless) and note in its output that this was a logged override, which the main session should then record (via journal-skill, as a note on the resulting trade file if one exists, or as a standalone note in `docs/architecture/risk-config.json`'s history if not tied to a specific trade). Output the full `RiskCalculation` object. This command never itself opens a trade — it's a calculator, usable before or independent of `/analyze`.
