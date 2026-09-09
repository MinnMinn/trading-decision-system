# Trades store

One Markdown file per trade: `<YYYY-MM-DD>-<PAIR>-<seq>.md` (e.g. `2026-09-09-BTCUSDT-01.md`). YAML frontmatter must validate against `docs/architecture/schemas/trade-file.schema.json`. This single file is the Journal entry, the Edge Log entry, and (if `is_mistake: true`) a Mistake-DB entry — see `docs/architecture/SYSTEM-DESIGN.md` §8.

Body structure (after the frontmatter):

```markdown
## Decision Output (at plan time)
<the full section-23 Decision Output from the master spec — Market State, HTF Context, Setup, Methodology Evidence, Independent Confluence, Confluence Score, Trade Decision, Invalidation & Management, Final Verdict>

## Post-Trade Review (filled in at close time, master spec section 26)
- Original Thesis:
- Evidence:
- Conditions:
- Execution:
- Outcome:
- Root Cause:
```

`trades/index.jsonl` is **generated, never hand-edited** — JournalSkill rebuilds it from every file's frontmatter on each `/journal` or `/status` call. Do not edit it directly; edit the source `.md` file and re-run `/journal` or `/status` instead.

`docs/edge-log/EDGE-LOG.md` and `docs/mistakes/MISTAKE-DB.md` are formatted views generated from `trades/index.jsonl` — same rule, edit the source trade file, not the generated view.

Rehearsal-mode trades (`rehearsal_mode: true`, produced while any data source was `MOCK`) are excluded from the consecutive-loss throttle and from Edge Log win-rate rollups, but still appear in the raw index for testing/reference.
