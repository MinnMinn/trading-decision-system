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

## Tooling (2026-09-10)

`scripts/journal.py` is the one tool over this store — see `docs/architecture/SYSTEM-DESIGN.md` §8.1. Demo-pilot
trades enter via `journal.py sync-pilot` (source `pilot_spot` / `pilot_futures`, market `spot_testnet` /
`futures_testnet`); human/Claude review fields are set with `journal.py review <id> --set root_cause=... is_mistake=true
lessons="..." what_to_change="..."`. `journal.py all` refreshes everything (sync, index, views, review page). Fields
computed by code (R, P&L, hold time, session) must not be hand-edited; edit the review fields only.


Profile `top5` (2026-09-11): `scripts/strategy-runner.py` logs to `data/live/pilot-futures/top5-log.jsonl`; `journal.py sync-pilot --market futures-top5` ingests it with the optional frontmatter fields `strategy` (ict-30m | combined-30m | ict-1h) and `htf_pass` (2H boundary filter at signal time) plus tags `top5`, the strategy name and `htf_pass`/`htf_fail`, so config B vs C can be compared from the journal. Only filled limits become trade files; `market`, `risk_pct` and `timeframe` come from the record.

Auto-sync (2026-09-11): `scripts/pilot-loop.sh` runs `python3 scripts/journal.py all` after every pilot tick, so `trades/*.md`, `index.jsonl`, the rollup views and `data/live/.journal-vi.html` follow the pilot without a Claude session; the page is published by the `journal-publish` session cron. The page's first section ("Pilot có đang hoạt động không?") is computed from the pilot logs and the automation config.
