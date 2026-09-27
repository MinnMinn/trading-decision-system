---
description: Power switch for trading automation. `on` brings everything back (scanner, local read, pilot loops, keep-awake) in the active environment; `off` stops all of it like a shutdown; `demo` / `real` pick the environment first. Scoped per market, dimension, method preset, timeframe and instrument.
argument-hint: [status | env | allows <scanner|local_read|pilot|master> | demo | real | on | off | market <crypto|cfd> <on|off> | timeframe <15m|1h|4h> <on|off> [--market M] | dimension <wyckoff|ict|footprint|heatmap> <on|off> [--market M] | method <wyckoff|ict|wyckoff+ict|wyckoff+footprint|wyckoff+ict+footprint|full> [--market M] | instrument <SYMBOL> <on|off> | instrument set <SYM,SYM,...> --market <crypto|cfd> | layer <scanner|local_read|pilot> <on|off> | pilot <start|stop|status|adopt> [--market futures] | history]
---

**What this is:** the single writer of `docs/architecture/automation-config.json` (schema `docs/architecture/schemas/automation-config.schema.json`, `schema_version 3`) plus the process actions that make the config real — installing/removing the launchd agents for the scanner and the pilot loops, and the keep-awake. The deterministic work is `scripts/automation.py`; run it, show its output verbatim, do not hand-edit the JSON (except `execution.environment`, which is the human's switch).

**Model note (SYSTEM-DESIGN.md §14).** This is the one command Haiku may run, because it does not reason: it passes the argument through and displays the script's output. If you are Haiku and the output contains a `!` warning or `REFUSED`, relay it verbatim and suggest `/model sonnet` — do not interpret it. For the first `demo` / `real` bring-up, prefer Sonnet so the report is read correctly. Step 4 below (`/status`) carries its own model gate.

## The user's contract (2026-09-10)

- **`/automation on`** after a reboot = automation is fully back: scanner agent installed + bootstrapped, one pilot agent per market in `PILOT_MARKETS` (one venue, `futures`, since 2026-09-13), `caffeinate` keep-awake. **`STOP` files are removed only for the pilot markets `on` actually installs** (`automation.py:833`, inside the install loop) — with `layers.pilot` off it installs none and leaves any `STOP` file exactly where it is. **MT5 must already be open** for CFD data; `on` reports bridge freshness and does not block on it.
- **`/automation off`** = everything stops and stays stopped across a reboot: `STOP` files written, agents booted out **and their plists deleted**, keep-awake killed.
- **`/automation demo`** / **`/automation real`** = set `execution.environment`, apply the preset (both markets, every instrument that has data on disk, every timeframe ON: scalping 15m, day 1h, swing 4h — the three authored horizons, `HORIZON_TF` in `scripts/automation.py:142`), then `on`. Dimensions and the chosen method preset are left exactly as they are — switching environment no longer resets them (2026-09-12, `docs/specs/2026-09-12-method-switch-design.md` §4.1). `real` refuses (exit 2) only while `config/env.real` still has `__FILL_ME__` secrets.
- **Pilot selection (ADR 0008, owner decision 2026-09-26):** a plain `/automation on`, `demo` or `real` re-selects the pilot's systems with `scripts/rank-setups.py` (one mode, `criteria-oos6m`): every backtested system (stability row at a pilot horizon — scalping 15m, day 1H, swing 4H — with a RUNNABLE method) is **enabled only if it passes every criterion of its horizon in `docs/architecture/selection-criteria.json` on its in-sample window AND on its held-out OOS window** (plus the data-sufficiency preconditions: each window ≥ 90 days, in-sample trade minimums). Every passing system is enabled — no ranking, no top-N, no one-per-slot winner, no coverage fallback, no runner-up substitution. It writes `docs/architecture/pilot-selection.json` + `docs/backtests/pilot-selection-latest.md` and prints each enabled system with its in-sample and OOS monthly figures, and **a `!` line for every (market, horizon) with no enabled system — that horizon trades nothing**, which is the intended outcome when nothing qualifies, not an error. The OOS window is marked EXPOSED on every run (§44). There are no selection specs: any `setup …` words after `on`/`demo`/`real` are a usage error (exit 1). The rule set is always `scripts/strategy-runner.py` over that file (the legacy engine was deleted 2026-09-13; there is no profile switch); with no selection file it trades nothing.
- Everything narrower (`market`, `timeframe`, `dimension`, `method`, `instrument`, `layer`, `pilot`) is for running a subset.
- **`/automation method <preset> [--market crypto|cfd]`** (2026-09-12) — set the method preset, i.e. apply a named set of the dimension flags in one go. The presets are `wyckoff`, `ict`, `wyckoff+ict`, `wyckoff+footprint`, `wyckoff+ict+footprint`, `full`, and they live in `docs/architecture/methods.json` — the single source for the dimensions, the runner-method table and the presets (SYSTEM-DESIGN.md §6.2). A preset is only a **name** for a set of flags; nothing extra is stored, and `status` derives the name back from the flags. It **refuses (exit 2)** a preset whose dimensions the target market has no source for (`wyckoff+footprint --market cfd`: no CoinGlass for commodities, §12 item 3). With no `--market` it applies only to the markets that can hold that preset and prints which it skipped. Under the two single-dimension presets (`wyckoff`, `ict`) the engaged count is 1, below the NORMAL minimum of 2, so `/analyze` can never return TRADE — the mechanical pilot still fires. `scripts/strategy-runner.py` applies the preset to **new** signals only (tick step 3, `strategy-runner.py:877`); open positions and resting orders are grandfathered and still managed.
- **`/automation instrument set <SYM,SYM,...> --market <crypto|cfd>`** (2026-09-12) — declarative batch: **replace** that market's whole instrument list in **one** write and **one** history row, instead of N single-symbol calls costing N rows of a 200-row ring. All-or-nothing: any off-allowlist symbol or any duplicate refuses (exit 2) and leaves the config untouched. `--market` is required. An empty list is legal and means "no NEW entries in this market" — positions and pending orders already open are still managed. The single-symbol `instrument <SYMBOL> <on|off>` form stays for terminal use.
- **`/automation allows master`** (2026-09-12) — a shell gate, like `allows scanner|local_read|pilot`: exit 0 if the master switch permits, 2 if not. Unlike those three it fails **closed** — a missing or corrupt config reads as *not permitted*, not as *no policy* — because this is the gate an unattended cron trusts before it writes.
- **`/automation pilot <start|stop|status|adopt>`** — those four actions and no others (argparse `choices`, `automation.py:1501` area); `--market` accepts only `futures`, the single venue since 2026-09-13. There is **no `pilot profile`** subcommand: the loop always runs `scripts/strategy-runner.py` over `docs/architecture/pilot-selection.json` (crypto on Binance futures testnet, CFD on the MT5 demo account via the file order bridge; that file's `mode` is `criteria-oos6m` once `/automation on|demo|real` has run under ADR 0008 — every system passing its horizon's criteria on in-sample and OOS). It re-reads the file every tick. The CFD leg needs `integrations/mt5/OrderBridge.mq5` attached (`python3 scripts/mt5-order-bridge.py check`).

## Procedure

1. **No argument, or `status`** — safe any time: `python3 scripts/automation.py status`. `env` shows the active environment and whether its file is complete (never a secret value).
2. **Any other argument** — pass it straight through, always with the audit fields:
   `python3 scripts/automation.py <subcommand> --who "claude:<session>" --reason "<the user's own words>"`.
3. **Show the output verbatim** — it lists what was enabled, what was skipped, launchd status, MT5 verdict, and the SESSION CRONS block.
4. **Skip `/status`** — do not run it after `on` / `demo` / `real`. The script output is the final word.
5. When the environment is `real`, say **"REAL MONEY"** clearly in your answer.
6. **Session crons — mandatory if `on`.** (Three templates exist in `integrations/crons/`, all Sonnet — Haiku is retired. Each declares a `layer:` in its front matter and the script emits it only when that layer permits: `method-switch` every 5 min at `3-58/5` (`layer: none` — gated on the master switch alone, so it survives scanner/local_read being off), `publish-tick` every 5 min (`layer: local_read`), `journal-publish` at `7,22,37,52` (`layer: pilot` — **not emitted while `layers.pilot` is off**). The Sonnet reads and the daily full analyses run headless from the scanner loop instead, `scripts/model-read.sh`.) (2026-09-11: every template now builds, reads and publishes the artifact **in the main session** — the cron turn itself — because a publish is refused unless this conversation has read or published the artifact and a subagent's read does not count; the Sonnet subagents only write the model blocks and run the checkers. Crons live only in the session that created them: if that session closes, artifacts stop updating until `/automation on` is run in an open session.) The script prints a `SESSION CRONS:` block with one `CronCreate(...)` line per enabled template. Read each prompt file and call `CronCreate` exactly as printed. Then `CronList` to confirm count. Do not skip. If a CronCreate is refused with "Blocked by classifier", retry that same call once — it has succeeded on the identical retry (see the 2026-09-12 note in integrations/crons/README.md); if the retry is refused twice, stop and tell the user rather than rewording the prompt. Background: `integrations/crons/README.md`.

## Environments

| | `demo` | `real` |
|---|---|---|
| file | `config/env.demo` (Keychain references to the existing testnet keys) | `config/env.real` (`__FILL_ME__` until you fill it) |
| Binance | testnet.binance.vision / testnet.binancefuture.com | api.binance.com / fapi.binance.com |
| MT5 | data only (bridge); account fields carried for a future connector | same |
| switch | `/automation demo`, or edit `execution.environment` by hand | `/automation real`, or edit by hand |

Loaders: `scripts/trading-env.sh` (bash) and `scripts/trading_env.py` (python). Both clamp `PILOT_RISK_PCT` to `max_risk_pct` from `docs/architecture/risk-config.json` (1% today) — the per-trade ceiling is a hard rule in every environment, as is the instrument allowlist. Neither number is written here: the ceiling is read through `trading_env.MAX_RISK_PCT` and the allowlist through `scripts/instruments.py`. (This line said "the 7-instrument allowlist" while there were 13, and named a Forex ban that was lifted 2026-09-17 — both are why it now points instead of counting.)

## The v3 shape: markets, not a flat style list

| | `crypto` | `cfd` |
|---|---|---|
| dimensions | wyckoff, ict, footprint, heatmap | wyckoff, ict **only** (no CoinGlass source for commodities, §12 item 3) |
| timeframes | — both markets: **15m, 1h, 4h** and nothing else (`TIMEFRAMES`, `automation.py:117`; the schema allows no other key). These are the three authored horizons — scalping 15m, day 1h, swing 4h — not a free timeframe list — |
| instruments | — both columns: the `analysis` list for that market in %s (single source; `python3 scripts/automation.py status` prints the live set) — |
| data | Binance public REST, live | MT5 file bridge, one charted symbol at a time (per-chart EA) |

(A third column, `forex`, existed 2026-09-17..2026-09-27: wyckoff/ict only, no CoinGlass source; no MT5 chart was ever attached for any of the seven majors, so it shipped `enabled:false` and never produced a candle in its whole time on the registry. Removed 2026-09-27 -- see docs/architecture/instruments.json history.)

Check the live picture rather than trusting the right-hand column: `ls data/live/mt5-bridge/` for the sources, `python3 scripts/automation.py status` for what is enabled.

`(market, timeframe)` → chart style is derived, not authored (`STYLE` = `STYLE_PREFIX[market] + horizon`, `automation.py:145-149`): crypto keeps the bare horizon word, cfd takes a prefix — crypto `scalping`/`day`/`swing`, cfd `cfd-scalping`/`cfd-day`/`cfd-swing`. A market with no prefix would collide with crypto's names, so the module raises at import rather than allow it.

## What `on` / `off` actually touch

| piece | `on` | `off` |
|---|---|---|
| `com.tyme.trading.scanner` (layer 1) | plist copied to `~/Library/LaunchAgents`, `launchctl bootstrap` | `bootout` + plist deleted |
| `com.tyme.trading.pilot[.futures]` | one per market in `PILOT_MARKETS`, KeepAlive, `PILOT_END=never` | `bootout` + plist deleted; `STOP` files written |
| keep-awake | `caffeinate -dims`, pid recorded in `services.keepawake_pid` | killed |
| MT5 bridge | freshness reported (`MT5_BRIDGE_MAX_AGE_MIN`); not a gate | — |
| session crons: `method-switch`, `publish-tick`, `journal-publish` | emitted from `integrations/crons/*.md`, one `CronCreate(...)` line per template whose `layer:` is permitted — follow `integrations/crons/README.md` "How `/automation on` uses them"; all Sonnet | delete all `[trading-cron:` jobs — same README |

The pilot loop re-reads the config every tick: flipping `layer pilot off` idles it within 15 min without a restart; `on` resumes it. A loop running outside launchd (started by hand) is detected with `pgrep`; `on` and `pilot start` refuse to install a managed loop next to it (that would double-trade the same account) — stop it first (`touch data/live/pilot/STOP`, wait one tick) or `pilot adopt` it.

## Refusals (exit 2) — cite them, do not argue

- **Anything off the `analysis` list** in `docs/architecture/instruments.json` (SYSTEM-DESIGN.md §1). Until 2026-09-17 a currency pair was also refused on sight by a separate test; that test is gone and the allowlist is the only gate. Being on that list makes a symbol scannable and analysable, **not** tradeable: the pilot and `/execute` use the `execution` list, a strict subset.
- **`dimension footprint|heatmap ... --market cfd`** — impossible states, absent from the schema: only crypto has a CoinGlass source. (There is no longer a timeframe refusal of this kind: `15m|1h|4h` are the only values argparse accepts and all three markets hold all three, so no `(market, timeframe)` pair is impossible. Anything else — `1m`, `5m`, `1D` — is a **usage error, exit 1**, not a refusal.)
- **`method <preset> --market cfd`** for any preset containing `footprint` or `heatmap` — same structural reason, named per missing dimension.
- **`instrument set ...`** with an off-allowlist symbol, a duplicate, or with no `--market` — all-or-nothing; on a refusal the config is untouched.
- **`real` while `config/env.real` is incomplete** — correctness, not policy: say exactly which keys are still placeholders.
- **`pilot start` while a loop is already running** (recorded or not), or while a `STOP` file exists for that market — `pilot start` never clears a blocker for you (`automation.py:1294`). `on` removes a `STOP` file only for a pilot market it is actually installing, so with `layers.pilot` off it clears nothing: enable the layer first, or remove the file by hand.

Exit codes: `0` applied/no-op, `1` usage error, `2` refused.

## Notes to carry into your answer

- Disabling a dimension (directly, or by picking a narrower `method` preset) can only *lower* `engaged_count`; below the mode minimum (NORMAL ≥2, ENHANCED/STRICT ≥3, §6.2) no live TRADE verdict can pass. The dimension flags also gate agent dispatch: `/analyze`, `/bias`, `/entry` and `/exit` derive which read-only agents to dispatch from `python3 scripts/methods.py --dispatch-plan <INSTRUMENT>` rather than from a hardcoded agent list, and reproduce its `SKIP` lines verbatim. `/exit`'s own thesis-invalidation check always runs regardless of the preset; only the *re-dispatch* is narrowed.
- A narrowed preset filters **new** pilot signals only (`scripts/strategy-runner.py:877`, tick step 3); open positions and resting orders are grandfathered and keep being managed. Narrowing a preset is therefore not a way to flatten a book.
- `footprint` / `heatmap` depend on CoinGlass; a `MOCK` source can rehearse but never satisfies the Independent-Confluence Check.
- CFDs are capped at NORMAL mode (no CoinGlass source, so never more than wyckoff + ict). A cfd symbol newly added to the allowlist has no MT5 export until a chart is attached for it, so enabling one before that sets a flag, not a source. XAGUSD having data is not the same as it being enabled — `python3 scripts/automation.py status` prints the live instrument list, `ls data/live/mt5-bridge/` prints the live sources.
- When the environment is `real`, the pilot logs an `env` record on every live tick and every entry carries `market: spot_mainnet` / `futures_mainnet` and `env: real` (matches `trade-file.schema.json`).
- Acceptance test: `bash scripts/verify-automation-v3.sh` (dry run, no orders, no launchd, no STOP). Run it after any change to the env files or the loaders.
- **`forex` was a third market** (schema + config from commit `5826785`, 2026-09-17), wyckoff/ict only, 7 majors, shipped **disabled** the whole time -- no MT5 chart was ever attached for any pair. Removed 2026-09-27 (`docs/architecture/instruments.json` history): zero data, zero analysis, zero trades in its ten days on the registry.
- This file drifts faster than the code. Argparse is the contract: `python3 scripts/automation.py <sub> --help` and the `choices=` lists near `automation.py:1500` beat anything written here, and the script's own module docstring has been stale too. If a command in this file does not exist, say so rather than improvising a substitute.
