---
description: Fine-grained entry-signal check for an already-identified setup (steps 5-10 of the pipeline). Requires a prior /bias or /analyze context for the same instrument.
argument-hint: <INSTRUMENT> <setup location/level> [mock]
---

**Model gate (SYSTEM-DESIGN.md §14).** This command reasons. If you are running as Haiku, do not execute it in this session: dispatch one `general-purpose` subagent with `model: sonnet` to run this command with the same `$ARGUMENTS` and relay its output verbatim.

Run steps 5–10 of `/analyze` for the instrument and setup location given in `$ARGUMENTS`. If no prior `/bias` or `/analyze` context exists for this instrument in this session, run steps 1–4 first rather than assuming a stale bias. Dispatch structure-agent (to confirm the setup is still valid), flow-agent (order-flow at the specific candle/bar), and liquidity-agent, then run the Independent-Confluence Check, Contradiction Analysis, and Confluence Score exactly as `/analyze` does. If the verdict could be TRADE, dispatch risk-agent for sizing. Produce the same Decision Output format as `/analyze` and journal the result the same way. This command exists for "I already have a thesis, is *this specific bar* the entry" — it still runs the full scoring discipline, it just skips re-deriving the HTF bias if one was already established this session.
