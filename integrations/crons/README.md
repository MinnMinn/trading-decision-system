# Session cron templates

Since 2026-09-11 (night) the chart pipeline is split in two:

| Where | What | Runs |
|---|---|---|
| launchd, outside any session | layer 1 scanner (`scripts/scan-loop.sh`) **and** the model layer: `scripts/model-read.sh <style> local|full` runs a headless Sonnet (`claude -p`) per style, in parallel, right after the scanner refreshed that style — layer-2 local reads on the old cadence (scalping/cfd-scalping 15 min; `day`/`swing` and their cfd twins have no headless prompt pair, so no local read runs for them) and the layer-3 daily full analysis once a day at 07:30–07:59Z. Prompts: `integrations/headless/<style>-{local-read,daily-full}.md`. Logs: `data/live/model-reads/`. | always, while `/automation` is on |
| this session (templates here) | `publish-tick` every 5 min: `scripts/publish-plan.py` lists the styles whose inputs changed, the tick builds (`scripts/build-artifact.py`) and publishes them — the Artifact tool exists only inside a session. `journal-publish` every 15 min. | while the session that ran `/automation on` is open |

Both templates run on Sonnet (user decision 2026-09-11: no Haiku anywhere). The retired per-style templates were deleted 2026-10-03 (git history keeps them). Artifact URLs live in `docs/architecture/artifacts.json` (written by `publish-plan.py --mark`).

## No subagents in a tick (2026-09-12)

Neither template may dispatch an `Agent`. Both do the Artifact read/publish in the cron turn itself, for two reasons:

1. A publish is refused unless *this conversation* has read or published the artifact, and a subagent's read does not count (`.claude/commands/automation.md` step 6).
2. Until 2026-09-12 `journal-publish` was the last template that still dispatched a subagent for read → publish → `cp`. Every one of those ticks came back with `SECURITY WARNING: This subagent performed actions that may violate security policy. Reason: Blocked by classifier`, even though the publish itself succeeded each time (`.journal-vi.published` matched `.journal-vi.html` afterwards). The warning was noise, but it made every unattended tick look like a failure. Moving the three steps into the main session removes the subagent surface entirely.

Separately, a `CronCreate` call is occasionally refused with "Blocked by classifier" on first attempt and accepted on an identical retry. Retry the same call once; if it is refused twice, stop and tell the user — do not reword the cron prompt to get around it.
