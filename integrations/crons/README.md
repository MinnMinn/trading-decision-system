# Session cron templates

Since 2026-09-11 (night) the chart pipeline is split in two:

| Where | What | Runs |
|---|---|---|
| launchd, outside any session | layer 1 scanner (`scripts/scan-loop.sh`) **and** the model layer: `scripts/model-read.sh <style> local|full` runs a headless Sonnet (`claude -p`) per style, in parallel, right after the scanner refreshed that style — layer-2 local reads on the old cadence (scalping/gold-scalp 10 min, daytrade/gold 15 min, swing 6 h) and the layer-3 daily full analysis once a day at 07:30–07:59Z. Prompts: `integrations/headless/<style>-{local-read,daily-full}.md`. Logs: `data/live/model-reads/`. | always, while `/automation` is on |
| this session (templates here) | `publish-tick` every 5 min: `scripts/publish-plan.py` lists the styles whose inputs changed, the tick builds (`scripts/build-artifact.py`) and publishes them — the Artifact tool exists only inside a session. `journal-publish` every 15 min. | while the session that ran `/automation on` is open |

Both templates run on Sonnet (user decision 2026-09-11: no Haiku anywhere). The retired per-style templates are kept in `retired/` for history; `scripts/cron-templates.py` ignores that folder. Artifact URLs live in `docs/architecture/artifacts.json` (written by `publish-plan.py --mark`).
