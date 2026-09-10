# Session crons — the Claude-side chart layers

These eight templates are the prompts of the crons that keep the chart artifacts alive: the Sonnet local reads
(layer 2), the daily full analyses (layer 3), and the scalping publish tick. They used to exist only as
`CronCreate` calls inside one Claude session and died with it on 2026-09-10 (the local reads stopped at 12:09
while the launchd scanner kept running). Versioning them here is what lets `/automation on` bring them back.

| template | cron (local time) | model | gate (market / timeframe / layer) | what it does |
|---|---|---|---|---|
| `scalping-publish` | every 3 min | haiku | crypto / 1m / local_read | copy → patch → inject → publish the scalping artifact; applies a pending full analysis (`select-base.py`) |
| `scalping-local-read` | every 5 min (:01 :06 …) | sonnet | crypto / 1m / local_read | đánh giá cục bộ for scalping; skips when no new scalping event since the last read. Replaces the old Monitor-on-`events.jsonl` trigger: the scanner emits ~440 scalping events/day and re-emits the same MSS every minute as the window slides, so a fixed 5-min cadence with a "new event since last read" guard is the debounce the design asked for |
| `daytrade-local-read` | :03 :18 :33 :48 | sonnet | crypto / 15m / local_read | đánh giá cục bộ + publish, day-trade artifact |
| `swing-local-read` | :05 every 4 h | sonnet | crypto / 1D / local_read | đánh giá cục bộ + publish, swing artifact |
| `gold-local-read` | :04 :19 :34 :49 | sonnet | cfd / 15m / local_read | đánh giá cục bộ + publish, XAUUSD; skips when the MT5 bridge is stale |
| `scalping-daily-full` | 07:30 | sonnet | crypto / 1m / local_read | layer 3; hands off to `data/live/narrative/scalping.full.html` |
| `daytrade-daily-full` | 07:40 | sonnet | crypto / 15m / local_read | layer 3; publishes and rewrites `anchors.daytrade.json` |
| `gold-daily-full` | 07:45 | sonnet | cfd / 15m / local_read | layer 3; publishes and rewrites `anchors.gold.json` |
| `swing-daily-full` | 07:50 | sonnet | crypto / 1D / local_read | layer 3; publishes and rewrites `anchors.swing.json` |

Models follow `SYSTEM-DESIGN.md` §14: reads and full analyses reason, so Sonnet; the publish tick only copies,
patches and publishes, so Haiku. There is no template for the `1h` / `4h` styles because no chart artifact exists
for them yet — the scanner produces their facts, nothing publishes them.

## Two gates, not one

- **Render gate** (`cron-templates.py render-all`): a template is only turned into a cron when the config enables it.
- **Runtime gate** (first sentence of every template): each fire begins with `python3 scripts/automation.py allows
  local_read <style>`; exit 2 means skip silently. This is what makes `/automation off` effective **from any
  session**: crons are per-session and another session cannot delete them, but every one of them re-reads the
  config before doing anything. A stale cron in a forgotten session therefore costs one shell call, not a publish.

## How `/automation on` uses them

The launchd agents installed by `scripts/automation.py` cover only the scanner and the pilot. The crons below are
**session-scoped** (`CronCreate` is in-memory, gone when Claude exits, auto-expired after 7 days), so they must be
re-created in whichever Claude session is open:

Since 2026-09-10 23:00 the script does the rendering itself: `automation.py on|demo|real` ends its output with a
`SESSION CRONS -- ASSISTANT ACTION REQUIRED` block that lists one `CREATE <name> cron="…" prompt_file=…` line per
enabled template (prompts already rendered to files) and the exact steps. `off` prints the delete instruction. The
manual procedure below is the same thing spelled out, for reference.

1. `CronList`, then `CronDelete` every job whose prompt starts with `[trading-cron:` — re-running `on` must never
   double a tick.
2. `python3 scripts/cron-templates.py render-all --scratchpad <this session's scratchpad directory> --json` — emits
   only the templates enabled by `docs/architecture/automation-config.json` (master switch, `layers.local_read`,
   `markets.<m>.enabled`, `markets.<m>.timeframes.<tf>`), each with `{{SCRATCHPAD}}` substituted and the prompt
   prefixed `[trading-cron:<name>] ` so a later `CronList` can identify it.
3. For each emitted entry, `CronCreate` with its `cron` and `prompt` verbatim. Tell the user: these run only while
   this session is open and expire after 7 days; the scanner and the pilot keep running without the session.
4. If nothing is emitted, show the `# skipped` lines instead of continuing silently.

`/automation off`: `CronList`, `CronDelete` every `[trading-cron:` job, say how many.

`python3 scripts/cron-templates.py list` shows every template with its gate and whether the current config enables it.

## Editing a template

Front matter keys: `name`, `cron`, `model`, `market`, `timeframe`, `layer`, `artifact`, `note`. The body is the
prompt; `{{SCRATCHPAD}}` and `{{ROOT}}` are substituted at render time. Keep the three disciplines every prompt
already carries: numbers from code (`local-eval-brief.py` FACTS, `patch-arrays.py`, `inject-prelim.py`,
`check-model-prose.py`), one writer per file (the launchd scanner owns `data/live/market-data` and `prelim`; crons
never run `fetch-binance-klines.sh` or `ict-scan.py` against the live files), and read-only research (no orders).

Open item: moving these layers out of the session to launchd via `claude -p` would make them survive a closed
Claude window. Not done — the Artifact publish step and the permission classifier need to be verified headless first.
