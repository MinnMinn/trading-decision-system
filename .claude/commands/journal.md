---
description: Write or update a trade record in trades/, and regenerate the index/rollup views.
argument-hint: <new | update trade-id> [fields...]
---

**Model gate (SYSTEM-DESIGN.md §14).** This command reasons (it maps an analysis into the structured `wyckoff_event` and `contradictions` fields and decides what is valid to record). If you are running as Haiku, do not execute it in this session: dispatch one `general-purpose` subagent with `model: sonnet` to run this command with the same `$ARGUMENTS` and relay its output verbatim.

Invoke **journal-skill** directly (`.claude/skills/journal-skill/SKILL.md`).

- `new`: only valid immediately after an `/analyze` or `/entry` run in this session produced a TRADE or WAIT verdict with a full Confluence Score and (if TRADE) a Risk Calculation — refuse and explain if those aren't available; this command does not accept a hand-typed trade with no analysis behind it.
- `update <trade-id>`: apply the given fields (e.g. `status: OPEN` once actually filled, or the full close-out field set per `trade-file.schema.json` when closing — prefer `/review` for a proper close-out, since it runs the Post-Trade Review too).

After any write, regenerate `trades/index.jsonl` and the two rollup views (`docs/edge-log/EDGE-LOG.md`, `docs/mistakes/MISTAKE-DB.md`).
