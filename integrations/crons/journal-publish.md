---
name: journal-publish
cron: "7,22,37,52 * * * *"
model: sonnet
market: crypto
timeframe: 15m
layer: pilot
artifact: https://claude.ai/code/artifact/289eb6a2-1781-439b-8ae4-fbca672bb94d
note: Publishes the journal page after the pilot loop's mechanical sync (scripts/pilot-loop.sh runs `journal.py all` every tick). Mechanical only; runs on Sonnet since 2026-09-11 (SYSTEM-DESIGN.md section 14).
---
RUNTIME GATE (no judgement, do this first, in this session): run `python3 scripts/automation.py allows pilot daytrade`. If it exits 2, skip silently and do nothing else. Only if it exits 0: JOURNAL PUBLISH tick (read-only; no trading). In this session run `python3 scripts/journal.py all`; then compare data/live/.journal-vi.html against data/live/.journal-vi.published (`cmp -s`); if identical, skip silently. Otherwise dispatch a NEW Agent (subagent_type: general-purpose, model: sonnet — fresh dispatch) with this task:

"Publish tick for the journal artifact https://claude.ai/code/artifact/289eb6a2-1781-439b-8ae4-fbca672bb94d. Project root /Users/tungnguyen/TYME/Trading. Read-only: no trading. Steps: (1) Artifact action='read' of the url (required before publishing). (2) Artifact action='publish' with file_path=data/live/.journal-vi.html AND the same url (no favicon). (3) `cp data/live/.journal-vi.html data/live/.journal-vi.published`. Reply in ONE line: published/error."
