---
description: Power switch for trading automation. `on` brings everything back (scanner, local read, pilot loops, keep-awake) in the active environment; `off` stops all of it like a shutdown; `demo` / `real` pick the environment first. Scoped per market, dimension, timeframe and instrument.
argument-hint: [status | env | demo | real | on | off | market <crypto|cfd> <on|off> | timeframe <1m|15m|1h|4h|1D> <on|off> [--market M] | dimension <wyckoff|ict|footprint|heatmap> <on|off> [--market M] | instrument <SYMBOL> <on|off> | layer <scanner|local_read|pilot> <on|off> | pilot <start|stop|status|adopt|profile <legacy|top5>> [--market spot|futures] | history]
---

**What this is:** the single writer of `docs/architecture/automation-config.json` (schema `docs/architecture/schemas/automation-config.schema.json`, `schema_version 3`) plus the process actions that make the config real — installing/removing the launchd agents for the scanner and the pilot loops, and the keep-awake. The deterministic work is `scripts/automation.py`; run it, show its output verbatim, do not hand-edit the JSON (except `execution.environment`, which is the human's switch).

**Model note (SYSTEM-DESIGN.md §14).** This is the one command Haiku may run, because it does not reason: it passes the argument through and displays the script's output. If you are Haiku and the output contains a `!` warning or `REFUSED`, relay it verbatim and suggest `/model sonnet` — do not interpret it. For the first `demo` / `real` bring-up, prefer Sonnet so the report is read correctly. Step 4 below (`/status`) carries its own model gate.

## The user's contract (2026-09-10)

- **`/automation on`** after a reboot = automation is fully back: scanner agent installed + bootstrapped, one pilot agent per market in `PILOT_MARKETS`, `caffeinate` keep-awake, stale `STOP` files removed. **MT5 must already be open** for CFD data; `on` reports bridge freshness and does not block on it.
- **`/automation off`** = everything stops and stays stopped across a reboot: `STOP` files written, agents booted out **and their plists deleted**, keep-awake killed.
- **`/automation demo`** / **`/automation real`** = set `execution.environment`, apply the preset (both markets, every instrument that has data on disk, all dimensions each market has, every timeframe ON (scalping 1m/5m, day 15m, 1h/4h, swing 1D — 2026-09-11) — other timeframes left as they are), then `on`. `real` refuses (exit 2) only while `config/env.real` still has `__FILL_ME__` secrets.
- **Default pilot rule set (2026-09-11, night):** a plain `/automation on` or `demo` now selects **one setup per horizon — scalping / day / swing — for crypto and for CFD** (`scripts/rank-setups.py --horizons --window 1y`, ranked on the last 12 months), writes `docs/architecture/pilot-top5.json`, sets the pilot profile to `top5` and brings everything up; the pilot loop period follows the fastest selected timeframe. The legacy 15m rules run only after `/automation pilot profile legacy`. A negative-backtest pick is still included (user choice: coverage over evidence) and printed with `[BACKTEST ÂM]`.
- **`/automation on setup top N`** / **`/automation demo setup top N`** (2026-09-11): before bringing everything up, rank every backtested rule on the **last 12 months** (`scripts/rank-setups.py --window 1y`), keep the N best for crypto and the N best for CFD (one per timeframe × rule family), write `docs/architecture/pilot-top5.json` + `docs/backtests/top-setups-latest.md`, set the pilot profile to `top5`, and print the selection with each setup's 1-year figures (`[BACKTEST ÂM]` marks a negative one). `setup top 3` = 3 + 3, `setup top 5` = 5 + 5 (N ≤ 10). Without `setup …` the current profile is kept. Pass the words straight through: `python3 scripts/automation.py on setup top 3 --who … --reason …`.
- Everything narrower (`market`, `timeframe`, `dimension`, `instrument`, `layer`, `pilot`) is for running a subset.
- **`/automation pilot profile legacy|top5`** (2026-09-11) picks the rule set of the futures pilot loop: `legacy` = `scripts/demo-pilot.py`, `top5` = `scripts/strategy-runner.py` on the 10 setups in `docs/architecture/pilot-top5.json` (5 crypto on Binance testnet, 5 CFD on the MT5 demo account; SYSTEM-DESIGN §9.y). The command prints the selected setups with their backtest figures (selection mode 2026-09-11: one per horizon scalping/day/swing per market, `docs/backtests/2026-09-11-top-setups.md`). The loop reads it every tick; `status` shows it. Only the user flips it. With `top5` the CFD leg needs `integrations/mt5/OrderBridge.mq5` attached (`python3 scripts/mt5-order-bridge.py check`).

## Procedure

1. **No argument, or `status`** — safe any time: `python3 scripts/automation.py status`. `env` shows the active environment and whether its file is complete (never a secret value).
2. **Any other argument** — pass it straight through, always with the audit fields:
   `python3 scripts/automation.py <subcommand> --who "claude:<session>" --reason "<the user's own words>"`.
3. **Show the output verbatim** — it lists what was enabled, what was skipped, launchd status, MT5 verdict, and the SESSION CRONS block.
4. **Skip `/status`** — do not run it after `on` / `demo` / `real`. The script output is the final word.
5. When the environment is `real`, say **"REAL MONEY"** clearly in your answer.
6. **Session crons — mandatory if `on`.** (2026-09-11 night: only two remain — `publish-tick` every 5 min and `journal-publish` — because the Sonnet reads and the daily full analyses now run headless from the scanner loop (`scripts/model-read.sh`, `integrations/crons/README.md`); both templates are Sonnet, Haiku is retired.) (2026-09-11: every template now builds, reads and publishes the artifact **in the main session** — the cron turn itself — because a publish is refused unless this conversation has read or published the artifact and a subagent's read does not count; the Sonnet subagents only write the model blocks and run the checkers. Crons live only in the session that created them: if that session closes, artifacts stop updating until `/automation on` is run in an open session.) The script prints a `SESSION CRONS:` block with one `CronCreate(...)` line per enabled template. Read each prompt file and call `CronCreate` exactly as printed. Then `CronList` to confirm count. Do not skip. Background: `integrations/crons/README.md`.

## Environments

| | `demo` | `real` |
|---|---|---|
| file | `config/env.demo` (Keychain references to the existing testnet keys) | `config/env.real` (`__FILL_ME__` until you fill it) |
| Binance | testnet.binance.vision / testnet.binancefuture.com | api.binance.com / fapi.binance.com |
| MT5 | data only (bridge); account fields carried for a future connector | same |
| switch | `/automation demo`, or edit `execution.environment` by hand | `/automation real`, or edit by hand |

Loaders: `scripts/trading-env.sh` (bash) and `scripts/trading_env.py` (python). Both clamp `PILOT_RISK_PCT` to ≤ 0.01 — the 1% per-trade ceiling is a hard rule in every environment, as are the Forex ban and the 7-instrument allowlist.

## The v3 shape: markets, not a flat style list

| | `crypto` (BTCUSDT/ETHUSDT/SOLUSDT) | `cfd` (XAUUSD/XAGUSD/USOIL/UKOIL) |
|---|---|---|
| dimensions | wyckoff, ict, footprint, heatmap | wyckoff, ict **only** (no CoinGlass source for commodities, §12 item 3) |
| timeframes | 1m, 15m, 1h, 4h, 1D | **5m**, 15m, 1h, 4h, 1D — no 1m: CFD scalping runs on M5 (user decision 2026-09-11; the gold spread makes M1 noise). The EA must be recompiled with `ExportOne(PERIOD_M5, "5m")` / `PERIOD_W1` (integrations/mt5/ExportOHLCV.mq5) |
| data | Binance public REST, live | MT5 file bridge, one charted symbol at a time — today **XAUUSD only** |

`(market, timeframe)` → chart style (`scripts/automation.py` `STYLE`): `1m`→`scalping`, `5m`→`gold-scalp` (cfd only), `15m`→`daytrade`/`gold`, `1h`→`1h`/`gold-1h`, `4h`→`4h`/`gold-4h`, `1D`→`swing`/`gold-swing`. Pages: crypto scalping/day-trade/swing and gold scalping (M5)/day (M15)/swing (D1); 1h/4h are scanner-only context.

## What `on` / `off` actually touch

| piece | `on` | `off` |
|---|---|---|
| `com.tyme.trading.scanner` (layer 1) | plist copied to `~/Library/LaunchAgents`, `launchctl bootstrap` | `bootout` + plist deleted |
| `com.tyme.trading.pilot[.futures]` | one per market in `PILOT_MARKETS`, KeepAlive, `PILOT_END=never` | `bootout` + plist deleted; `STOP` files written |
| keep-awake | `caffeinate -dims`, pid recorded in `services.keepawake_pid` | killed |
| MT5 bridge | freshness reported (`MT5_BRIDGE_MAX_AGE_MIN`); not a gate | — |
| session crons: local read (layer 2), daily full analysis (layer 3), scalping publish tick, journal publish | re-created from `integrations/crons/*.md` — follow `integrations/crons/README.md` "How `/automation on` uses them"; Sonnet for reads/full, Haiku for the publish tick (§14) | delete all `[trading-cron:` jobs — same README |

The pilot loop re-reads the config every tick: flipping `layer pilot off` idles it within 15 min without a restart; `on` resumes it. A loop running outside launchd (started by hand) is detected with `pgrep`; `on` and `pilot start` refuse to install a managed loop next to it (that would double-trade the same account) — stop it first (`touch data/live/pilot/STOP`, wait one tick) or `pilot adopt` it.

## Refusals (exit 2) — cite them, do not argue

- **Forex** — any pair of two currency codes; and anything outside {BTCUSDT, ETHUSDT, SOLUSDT, XAUUSD, XAGUSD, USOIL, UKOIL}.
- **`dimension footprint|heatmap ... --market cfd`**, **`timeframe 1m ... --market cfd`** and **`timeframe 5m ... --market crypto`** — impossible states, absent from the schema.
- **`real` while `config/env.real` is incomplete** — correctness, not policy: say exactly which keys are still placeholders.
- **`pilot start` while a loop is already running** (recorded or not), or while a `STOP` file exists for that market — `on` removes STOP files as part of re-arming; `pilot start` alone does not.

Exit codes: `0` applied/no-op, `1` usage error, `2` refused.

## Notes to carry into your answer

- Disabling a dimension can only *lower* `engaged_count`; below the mode minimum (NORMAL ≥2, ENHANCED/STRICT ≥3, §6.2) no live TRADE verdict can pass. The dimension flags also gate agent dispatch in `/analyze` step 5.
- `footprint` / `heatmap` depend on CoinGlass; a `MOCK` source can rehearse but never satisfies the Independent-Confluence Check.
- CFDs are capped at NORMAL mode and today only XAUUSD has an MT5 export; enabling XAGUSD/USOIL/UKOIL sets a flag, not a source.
- When the environment is `real`, the pilot logs an `env` record on every live tick and every entry carries `market: spot_mainnet` / `futures_mainnet` and `env: real` (matches `trade-file.schema.json`).
- Acceptance test: `bash scripts/verify-automation-v3.sh` (dry run, no orders, no launchd, no STOP). Run it after any change to the env files or the loaders.
