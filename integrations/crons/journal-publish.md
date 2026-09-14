---
name: journal-publish
cron: "7,22,37,52 * * * *"
model: sonnet
market: crypto
timeframe: 15m
layer: pilot
artifact: https://claude.ai/code/artifact/289eb6a2-1781-439b-8ae4-fbca672bb94d
note: Publishes the journal page after the pilot loop's mechanical sync (scripts/pilot-loop.sh runs `journal.py all` every tick). Mechanical only; runs on Sonnet since 2026-09-11 (SYSTEM-DESIGN.md section 14). 2026-09-12 — the read/publish/cp moved into the main session like publish-tick; the old subagent dispatch was the last template still violating the main-session rule in .claude/commands/automation.md step 6, and it tripped the subagent security classifier on every tick.
---
RUNTIME GATE (no judgement, do this first, in this session): run `python3 scripts/automation.py allows pilot scalping`. If it exits 2, skip silently and do nothing else. Only if it exits 0: JOURNAL PUBLISH tick (read-only; no trading; no subagent; no reasoning about the market). In this session run `python3 scripts/journal.py all`; then compare data/live/.journal-vi.html against data/live/.journal-vi.published (`cmp -s`); if identical, reply "nothing to publish" and stop. Otherwise do all three steps yourself, in THIS session — never dispatch an Agent, a subagent's read does not satisfy the publish precondition: (1) Artifact action='read' with url=https://claude.ai/code/artifact/289eb6a2-1781-439b-8ae4-fbca672bb94d (the result may say the HTML was saved to a file — fine, do not Read that file). (2) Artifact action='publish' with file_path=data/live/.journal-vi.html AND that same url, no favicon; if refused because a newer version exists, read once more and publish once more, then stop. Never pass force. (3) `cp data/live/.journal-vi.html data/live/.journal-vi.published`. Reply in ONE line: `journal: published <url>` or `journal: <error>`.
