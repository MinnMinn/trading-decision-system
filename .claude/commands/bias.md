---
description: HTF directional bias only — steps 1-4 of the pipeline (Data Validation through HTF Context/Setup Detection). No scoring, no trade plan.
argument-hint: <INSTRUMENT> [mock]
---

**Model gate (SYSTEM-DESIGN.md §14).** This command reasons. If you are running as Haiku, do not execute it in this session: dispatch one `general-purpose` subagent with `model: sonnet` to run this command with the same `$ARGUMENTS` and relay its output verbatim.

Run only steps 1–4 of `/analyze` for the instrument in `$ARGUMENTS`: Data Validation, Event Risk, Market Regime, and HTF Context/Setup Detection. Dispatch `structure-agent` alone (not flow-agent or liquidity-agent — this command is intentionally lighter). Output: Data Validation status, Event Risk, Market Regime, Wyckoff phase read, ICT HTF bias, and a plain-language directional lean (Bullish/Bearish/Neutral) with the confidence caveats structure-agent flagged. Do **not** produce a Confluence Score, Trade Plan, or Final Verdict — this command answers "what's the lay of the land," not "should I trade." Same instrument-allowlist refusal as `/analyze`.
