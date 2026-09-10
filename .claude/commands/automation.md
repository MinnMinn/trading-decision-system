---
description: Power switch for trading automation. `on` brings everything back (scanner, local read, pilot loops, keep-awake) in the active environment; `off` stops all of it like a shutdown; `demo` / `real` pick the environment first. Scoped per market, dimension, timeframe and instrument.
argument-hint: [status | env | demo | real | on | off | market <crypto|cfd> <on|off> | timeframe <1m|15m|1h|4h|1D> <on|off> [--market M] | dimension <wyckoff|ict|footprint|heatmap> <on|off> [--market M] | instrument <SYMBOL> <on|off> | layer <scanner|local_read|pilot> <on|off> | pilot <start|stop|status|adopt> [--market spot|futures] | history]
---

**What this is:** the single writer of `docs/architecture/automation-config.json` (schema `docs/architecture/schemas/automation-config.schema.json`, `schema_version 3`) plus the process actions that make the config real — installing/removing the launchd agents for the scanner and the pilot loops, and the keep-awake. The deterministic work is `scripts/automation.py`; run it, show its output verbatim, do not hand-edit the JSON (except `execution.environment`, which is the human's switch).

**Model note (SYSTEM-DESIGN.md §14).** This is the one command Haiku may run, because it does not reason: it passes the argument through and displays the script's output. If you are Haiku and the output contains a `!` warning or `REFUSED`, relay it verbatim and suggest `/model sonnet` — do not interpret it. For the first `demo` / `real` bring-up, prefer Sonnet so the report is read correctly. Step 4 below (`/status`) carries its own model gate.

## The user's contract (2026-09-10)

- **`/automation on`** after a reboot = automation is fully back: scanner agent installed + bootstrapped, one pilot agent per market in `PILOT_MARKETS`, `caffeinate` keep-awake, stale `STOP` files removed. **MT5 must already be open** for CFD data; `on` reports bridge freshness and does not block on it.
- **`/automation off`** = everything stops and stays stopped across a reboot: `STOP` files written, agents booted out **and their plists deleted**, keep-awake killed.
- **`/automation demo`** / **`/automation real`** = set `execution.environment`, apply the preset (both markets, every instrument that has data on disk, all dimensions each market has, timeframes 15m/1h/4h ON — other timeframes left as they are), then `on`. `real` refuses (exit 2) only while `config/env.real` still has `__FILL_ME__` secrets.
- Everything narrower (`market`, `timeframe`, `dimension`, `instrument`, `layer`, `pilot`) is for running a subset.

## Procedure

1. **No argument, or `status`** — safe any time: `python3 scripts/automation.py status`. `env` shows the active environment and whether its file is complete (never a secret value).
2. **Any other argument** — pass it straight through, always with the audit fields:
   `python3 scripts/automation.py <subcommand> --who "claude:<session>" --reason "<the user's own words>"`.
3. **Show the output verbatim** — it lists what was enabled, what was skipped, launchd status, MT5 verdict, and the SESSION CRONS block.
4. **Skip `/status`** — do not run it after `on` / `demo` / `real`. The script output is the final word.
5. When the environment is `real`, say **"REAL MONEY"** clearly in your answer.
6. **Session crons — mandatory if `on`.** The script prints a `SESSION CRONS:` block with one `CronCreate(...)` line per enabled template. Read each prompt file and call `CronCreate` exactly as printed. Then `CronList` to confirm count. Do not skip. Background: `integrations/crons/README.md`.

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
| timeframes | 1m, 15m, 1h, 4h, 1D | 15m, 1h, 4h, 1D — **no 1m**, the MT5 EA does not export it (§12 item 6) |
| data | Binance public REST, live | MT5 file bridge, one charted symbol at a time — today **XAUUSD only** |

`(market, timeframe)` → chart style (`scripts/automation.py` `STYLE`): `1m`→`scalping`, `15m`→`daytrade`/`gold`, `1h`→`1h`/`gold-1h`, `4h`→`4h`/`gold-4h`, `1D`→`swing`/`gold-swing`.

## What `on` / `off` actually touch

| piece | `on` | `off` |
|---|---|---|
| `com.tyme.trading.scanner` (layer 1) | plist copied to `~/Library/LaunchAgents`, `launchctl bootstrap` | `bootout` + plist deleted |
| `com.tyme.trading.pilot[.futures]` | one per market in `PILOT_MARKETS`, KeepAlive, `PILOT_END=never` | `bootout` + plist deleted; `STOP` files written |
| keep-awake | `caffeinate -dims`, pid recorded in `services.keepawake_pid` | killed |
| MT5 bridge | freshness reported (`MT5_BRIDGE_MAX_AGE_MIN`); not a gate | — |
| session crons: local read (layer 2), daily full analysis (layer 3), scalping publish tick | re-created from `integrations/crons/*.md` — follow `integrations/crons/README.md` "How `/automation on` uses them"; Sonnet for reads/full, Haiku for the publish tick (§14) | delete all `[trading-cron:` jobs — same README |

The pilot loop re-reads the config every tick: flipping `layer pilot off` idles it within 15 min without a restart; `on` resumes it. A loop running outside launchd (started by hand) is detected with `pgrep`; `on` and `pilot start` refuse to install a managed loop next to it (that would double-trade the same account) — stop it first (`touch data/live/pilot/STOP`, wait one tick) or `pilot adopt` it.

## Refusals (exit 2) — cite them, do not argue

- **Forex** — any pair of two currency codes; and anything outside {BTCUSDT, ETHUSDT, SOLUSDT, XAUUSD, XAGUSD, USOIL, UKOIL}.
- **`dimension footprint|heatmap ... --market cfd`** and **`timeframe 1m ... --market cfd`** — impossible states, absent from the schema.
- **`real` while `config/env.real` is incomplete** — correctness, not policy: say exactly which keys are still placeholders.
- **`pilot start` while a loop is already running** (recorded or not), or while a `STOP` file exists for that market — `on` removes STOP files as part of re-arming; `pilot start` alone does not.

Exit codes: `0` applied/no-op, `1` usage error, `2` refused.

## Notes to carry into your answer

- Disabling a dimension can only *lower* `engaged_count`; below the mode minimum (NORMAL ≥2, ENHANCED/STRICT ≥3, §6.2) no live TRADE verdict can pass. The dimension flags also gate agent dispatch in `/analyze` step 5.
- `footprint` / `heatmap` depend on CoinGlass; a `MOCK` source can rehearse but never satisfies the Independent-Confluence Check.
- CFDs are capped at NORMAL mode and today only XAUUSD has an MT5 export; enabling XAGUSD/USOIL/UKOIL sets a flag, not a source.
- When the environment is `real`, the pilot logs an `env` record on every live tick and every entry carries `market: spot_mainnet` / `futures_mainnet` and `env: real` (matches `trade-file.schema.json`).
- Acceptance test: `bash scripts/verify-automation-v3.sh` (dry run, no orders, no launchd, no STOP). Run it after any change to the env files or the loaders.
