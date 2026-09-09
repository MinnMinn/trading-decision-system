---
description: HTF directional bias only — steps 1-4 of the pipeline (Data Validation through HTF Context/Setup Detection). No scoring, no trade plan.
argument-hint: <INSTRUMENT> [mock]
---

Run only steps 1–4 of `/analyze` for the instrument in `$ARGUMENTS`: Data Validation, Event Risk, Market Regime, and HTF Context/Setup Detection. Dispatch `structure-agent` alone (not flow-agent or liquidity-agent — this command is intentionally lighter). Output: Data Validation status, Event Risk, Market Regime, Wyckoff phase read, ICT HTF bias, and a plain-language directional lean (Bullish/Bearish/Neutral) with the confidence caveats structure-agent flagged. Do **not** produce a Confluence Score, Trade Plan, or Final Verdict — this command answers "what's the lay of the land," not "should I trade." Same instrument-allowlist refusal as `/analyze`.
