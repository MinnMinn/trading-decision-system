# Deep CFD history from MT5 (CLAUDE.md §23.1)

Why this exists: CFD backtests currently read **Yahoo front-month futures** (`GC=F`, `SI=F`, `CL=F`, `BZ=F`),
not the CFD the system actually trades. Different session hours, real contract volume instead of tick volume,
a futures basis, and roll gaps. `providers.research_data_mismatch("cfd")` reports it and every CFD ranking
says so — but the honest fix is the broker's own history.

The live bridge cannot supply it: `ExportOHLCV.mq5` exports **600 bars** per timeframe on a 60-second timer,
which is a live feed, not a research dataset. `ExportHistory.mq5` is a separate one-shot **Script**.

## The timestamp trap — read this before running anything

`ExportOHLCV.mq5` converts every bar with `TimeCurrent() - TimeGMT()`: the offset **right now**. Correct for a
600-bar window; **wrong for years of history**. Most brokers run UTC+2 in winter and UTC+3 in summer, so
today's offset applied to a bar from six months ago shifts it by an hour — and an hour is the difference
between a 13:30Z NFP candle and the one before it.

MQL5 cannot report the offset that was in force for a historical bar. So `ExportHistory.mq5` writes **raw
server time with no `Z`**, plus the server name and the current offset, and the conversion happens in Python
where real tzdata exists — the same machinery `sessions.json` already uses for DST.

**This is why you must tell me your broker's server timezone before the import can run.** It is a declared
registry fact, not a guess.

## Steps in MetaTrader

1. **Tools → Options → Charts → "Max bars in chart" → `Unlimited`.** This is a terminal-wide cap, separate
   from anything the script asks for; leaving it at the default silently truncates the export.
2. Open a chart for the symbol **at each timeframe you want** (XAUUSD H1, XAUUSD H4, …). `CopyRates` returns
   only what the terminal has already **downloaded**, and the terminal downloads lazily.
3. On each chart, press **Home** repeatedly (or hold `Page Up`) until the bar count in the status bar stops
   growing. That forces the download. A CFD broker typically has years of H1/H4/D1 and much less M5/M15 —
   whatever it gives you is the ceiling, and no setting changes that.
4. Navigator → Scripts → drag **ExportHistory** onto the chart. Tick the timeframes you want, leave
   `InpBars` large (it asks for more than exists on purpose). Run it once per symbol.
5. Check **Toolbox → Experts** for the per-timeframe line: `XAUUSD 1H -> 43821 bars, 2019-03-04T00:00:00 ..
   2026-09-18T01:00:00 (server time)`. That line is the receipt — if it says 600, step 1 or 3 did not take.

Files land in the same `Common\Files` folder the live bridge uses, named `history.<SYMBOL>.<TF>.json`, so
they appear in `data/live/mt5-bridge/` through the existing symlink. They are **not** read from there: the
importer moves them into `data/history/`, which is where `backtest-methods.load()` looks.

## What the first export actually produced (2026-09-18)

Run on the **MetaQuotes-Demo** account — the same account the pilot's CFD setups trade through the order
bridge, which is what makes it the right history to backtest on: same venue, same instrument, same session
hours. It is *not* a real broker, so a later move to one means re-exporting; the numbers below belong to this
account and no other.

| Symbol | TF | Bars | Range (server time) |
|---|---|---|---|
| XAUUSD | 1W | 1,163 | 2004-06-06 → 2026-09-13 |
| XAUUSD | 1D | 5,723 | 2004-06-11 → 2026-09-18 |
| XAUUSD | 4H | 34,118 | 2004-06-11 → 2026-09-18 |
| XAUUSD | 1H | 100,000 | 2009-08-18 → 2026-09-18 |
| XAUUSD | 15m | 100,002 | 2022-06-17 → 2026-09-18 |
| XAGUSD | 4H | 27,516 | 2008-11-07 → 2026-09-18 |
| XAGUSD | 1H | 100,000 | 2009-09-07 → 2026-09-18 |
| XAGUSD | 15m | 100,000 | 2022-07-05 → 2026-09-18 |

**The round 100,000 was a stale cache, not the terminal setting.** `config/common.ini` already read
`MaxBars=100000000` (Unlimited), but MT5 serves `CopyRates` from the per-timeframe caches under
`Bases/<server>/history/<SYM>/cache/*.hc`, and those had been built at 00:04 that day — before the setting was
saved at 10:20. Restarting the terminal rebuilt them. Worth knowing for the next export; not worth much
otherwise, since 4H/1D/1W already reach 2004 and 17 years of hourly gold is far past what any backtest here
uses.

### The server timezone was MEASURED, not declared

`ExportOHLCV` would have applied today's offset to every historical bar. This export writes raw server time
precisely so the conversion can be made once, correctly, from evidence. Three measurements over the exported
XAUUSD 1H series:

1. The trading week opens **Monday 01:00** and closes **Friday 23:00** in server time, with hour 00 the daily
   break — the classic EET session frame.
2. The most volatile hour is **16:00 server in both summer and winter**. A fixed offset would move it by an
   hour between seasons; it does not, so the server observes daylight saving.
3. The decisive test between EU and US rules: in the **12–25 March** window, when the US is already on DST and
   the EU is not, the busiest hour drops to **15:00**, returning to 16:00 in April. That is the EU transition
   date, not the US one.

→ **EET/EEST — UTC+2 winter, UTC+3 summer, EU transition dates: IANA `Europe/Helsinki`.** Consistent with the
`_server_utc_offset_sec_now = 10800` the script recorded in September. This is the fact the importer needs, and
it is now derived from the data rather than assumed from the server's name.

### No oil on this account (2026-09-18) — resolved 2026-09-27

**Resolved:** USOIL and UKOIL were removed from the system on 2026-09-27 (owner decision; `instruments.json`
`history`), together with their Yahoo futures history. The record below is how it stood on 2026-09-18.

`USOIL` / `UKOIL` are not in this server's symbol list under those or any nearby names. Consequences, stated
rather than worked around:

- `instruments.json` lists four orderable `cfd` symbols; this account can feed and fill **two** (XAUUSD,
  XAGUSD). The order bridge has never exported an oil bar — `data/live/mt5-bridge/` holds none.
- `data/history/ohlcv.USOIL.*.json` and `ohlcv.UKOIL.*.json` remain Yahoo front-month futures
  (`_source: yahoo_finance_CL=F_research_only` / `BZ=F`). The §23.1 caveat **stays** for oil and comes off only
  for metals.
- Whether the execution list should still declare two symbols this account cannot trade is a registry
  decision, not a cleanup: it is the §6 "never invent a capability" question, and it is left open here rather
  than settled by an edit nobody asked for.

## Then tell me

Send back, or just say:

1. **The Experts-tab lines** (symbol, timeframe, bar count, date range) — that tells us what history actually
   exists before anything is built on it.
2. **The broker server name** the script printed (e.g. `ICMarketsSC-MT5`), or simply which timezone your
   broker's server runs on. Without it the import refuses rather than guessing — a wrong zone would put a
   silent one-hour error into every backtest, which is worse than the futures proxy we already label.

I will then write `scripts/import-mt5-history.py`: convert server → UTC with the declared zone, run the §20
quality check (holes, out-of-order bars, broken OHLC), and write `data/history/ohlcv.<SYMBOL>.<TF>.json`.
Existing CFD rankings get re-run against real CFD data, and the §23.1 caveat comes off.

## What this does not fix

- **Tick volume stays tick volume.** The broker reports price-change counts, not traded size. The
  `tick_volume_credit_multiplier` in `analysis-params.json` stays.
- **Survivorship (§9).** Broker history covers instruments that still exist. Same structural gap as crypto.

## Batch export for many symbols (2026-10-01)

For the FTMO symbol-universe import (many symbols, ExportSymbolList first, batch `InpSymbols` in ExportHistory v1.01) see
`docs/architecture/mt5-ftmo-symbol-universe-export.md`. That procedure is the single source; nothing is repeated here.
