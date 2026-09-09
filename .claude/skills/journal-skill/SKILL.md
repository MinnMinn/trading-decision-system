---
name: journal-skill
description: Use whenever a trade plan, open position, or closed trade needs to be written or updated in the trades/ store, or whenever the Edge Log / Mistake DB rollup views need regenerating. Invoked by /journal, /status, /review, and at the end of every /analyze that reaches a TRADE or WAIT verdict.
---

# JournalSkill

Storage design: `docs/architecture/SYSTEM-DESIGN.md` §8. Format: `trades/README.md`. Schema: `docs/architecture/schemas/trade-file.schema.json`.

## Procedure

### Writing a new trade (at plan time, from `/analyze` or `/journal`)
1. Allocate an id: `<YYYY-MM-DD>-<INSTRUMENT>-<seq>` (seq increments per instrument per day).
2. Write `trades/<id>.md` with YAML frontmatter matching the schema exactly — every required field present, `status: PLANNED` (or `OPEN` if entry already filled), `rehearsal_mode: true` if any data source feeding this decision was `MOCK`.
3. Body = the full Decision Output (master spec §23) verbatim, not summarized.
4. Regenerate `trades/index.jsonl` (step below).

### Updating on close (from `/review`)
1. Read the existing trade file, don't create a new one.
2. Fill `date_closed`, `status: CLOSED`, `result`, `r_multiple`, `mfe`, `mae`, `exit_reason`, `root_cause`, `is_mistake` (true if `root_cause` is anything other than `n/a_win_as_planned` AND the trade was a loss or a mismanaged win), `lessons`.
3. Append the Post-Trade Review section to the body per `trades/README.md`'s template.
4. Regenerate `trades/index.jsonl`.

### Regenerating `trades/index.jsonl`
Scan every `trades/*.md` file, extract its frontmatter, write one JSON line per file. This file is fully derived — never hand-edit it, never partially update it; always rebuild from scratch so it can't drift from the source `.md` files.

### Regenerating the rollup views
- `docs/edge-log/EDGE-LOG.md`: every `status: CLOSED` and `rehearsal_mode: false` entry from `trades/index.jsonl`, formatted as a table (Setup Type, Market, Regime, Mode, Confluence, Entry, Stop, Targets, Result, R-Multiple, Lessons) sorted by `date_closed` descending.
- `docs/mistakes/MISTAKE-DB.md`: every entry with `is_mistake: true`, grouped by `root_cause`, with a frequency count per category and a "repeated?" flag if a `root_cause` appears more than once — per the master spec's §28 instruction to prioritize repeated mistakes.

## Hard rules

- Never fabricate a trade record. If asked to journal a trade that wasn't actually run through `/analyze` (missing Confluence Score, missing RiskSkill output), refuse and say what's missing.
- Never let `trades/index.jsonl` or the rollup views become the source of truth — they are always regenerated from the `.md` files, never the reverse.
