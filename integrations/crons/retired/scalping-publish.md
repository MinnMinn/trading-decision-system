---
name: scalping-publish
cron: "*/5 * * * *"
model: main-session
market: crypto
timeframe: 1m
layer: local_read
artifact: https://claude.ai/code/artifact/59f0b15b-9d2c-4ac7-b15f-f630ae4a1c49
note: Mechanical publish only (build, read, publish), done by the cron turn itself in the main session -- no subagent, because a subagent's Artifact read does not satisfy the publish check (2026-09-11). scripts/build-artifact.py replaced patch-arrays/inject-prelim/select-base on 2026-09-11.
---
RUNTIME GATE (no judgement, do this first, in this session): run `python3 scripts/automation.py allows local_read scalping`. If it exits 2, skip silently and do nothing else — automation is OFF (or this market/timeframe/layer is off) in docs/architecture/automation-config.json, which `/automation off` may have set from ANY session; a cron that was created before that must not keep running. Only if it exits 0: Scalping PUBLISH tick (read-only research; no trading). If a previous scalping publish tick is still running, skip silently. Do NOT run ict-scan.py or fetch-binance-klines.sh here — the launchd scanner is the single writer of data/live/market-data, data/live/prelim and events.

PUBLISH — DO THIS IN THIS SESSION, NOT IN A SUBAGENT (fix 2026-09-11: a publish is refused unless THIS conversation has read or published the artifact, and a subagent's read does not count): run `python3 scripts/build-artifact.py scalping --out data/live/.tmp-scalping-vi.html --snapshot-dir {{SCRATCHPAD}}/publish-scalping-publish` — it must print `BUILD OK` (exit 2 = a method block leaked the other method's vocabulary: report it, do not publish, never pass --allow-impure). Then Artifact action='read' with url=https://claude.ai/code/artifact/59f0b15b-9d2c-4ac7-b15f-f630ae4a1c49 (the result may say the HTML was saved to a file — that is fine, do not Read that file), then Artifact action='publish' with file_path=data/live/.tmp-scalping-vi.html AND url=https://claude.ai/code/artifact/59f0b15b-9d2c-4ac7-b15f-f630ae4a1c49, no favicon. If the publish is refused because a newer version exists, read once more and publish once more, then stop. Never pass force. Report one line: BUILD OK line · published/error.
