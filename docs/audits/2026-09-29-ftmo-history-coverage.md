# FTMO-Demo research history -- import coverage (CLAUDE.md §20/§38)

Owner decision 2026-09-28/29 (`docs/plans/2026-09-28-methodology-improvement-plan.md` §6 items 3, 7): fund
setups are searched on 1m/5m/15m/30m against the fund's OWN feed. This is the §20 data-quality assessment
(`scripts/quality.py` `Q.assess()`, run via `scripts/backtest-methods.py` `bt.load()` with
`BT_HISTORY_ROOT=data/history/ftmo`) on every series imported by
`scripts/import-mt5-history.py --provider mt5_bridge_ftmo --symbol-map data/history/costs/ftmo/symbol-map.json
--dest-root data/history/ftmo --split-threshold-bytes 0`.

**Zone**: `mt5_bridge_ftmo:us_dst_dates_fixed_offset(std=7200s,dst=10800s)` -- see
`docs/audits/2026-09-29-ftmo-server-timezone.md`. **Server**: `FTMO-Demo`. Existing
`data/history/ohlcv.*.json` (MetaQuotes-Demo) files are untouched (`git diff --stat -- "data/history/ohlcv.*"`
is empty).

## Fix round 1 (owner, 2026-09-29): every series is now gzip-per-UTC-year split

The first import used the existing 45 MB single-file/split threshold, which left the smaller-but-still-large
series (5m/30m/15m/1H for several symbols) as plain, uncompressed JSON -- `data/history/ftmo` totalled
**674 MB**, too large for a public repo. `scripts/import-mt5-history.py` gained a `--split-threshold-bytes`
flag (`plan(..., split_threshold=)`); passing `0` forces EVERY series onto the gzip-per-UTC-year path
regardless of size, and `stream_write_split()` now removes any stale plain-file copy left by a prior run over
the same (symbol, tf) once the new split directory is safely committed (`backtest-methods.load()` checks the
plain-file path first, so an orphaned one would silently shadow the new data forever). The re-import is
byte-for-byte the same DATA as the first run (same bar counts, same first/last timestamps, same §20 states
below) -- only the on-disk SHAPE changed. The MetaQuotes-Demo default path (`mt5_bridge`, no
`--split-threshold-bytes`) is unaffected; its own 45 MB threshold and single-file shape for small series are
unchanged, and every existing test exercising the default path still passes with the default value.

```
$ du -sh data/history/ftmo
349M    data/history/ftmo

$ find data/history/ftmo -size +95M
(empty)

$ find data/history/ftmo -maxdepth 1 -name "*.json"
(empty -- no plain single-file series remain; every series is a split-gz directory)
```

Per-timeframe totals (`du -ch data/history/ftmo/ohlcv.*.<tf> | tail -1`), summed across all 7 symbols:

| TF | Total size |
|---|---|
| 1W | 409K |
| 1D | 744K |
| 4H | 2.3M |
| 1H | 7.4M |
| 30m | 14M |
| 15m | 25M |
| 5m | 65M |
| 1m | 236M |
| **Total** | **349M** |

## Symbol coverage

7 of the FTMO account's 8 mapped symbols (`data/history/costs/ftmo/symbol-map.json`) were imported. The
8th, **AUS200 (raw `AUS200.cash`), was not exported by the owner and is DROPPED by owner decision
(2026-09-29) -- not imported, not waited for.**

| Canonical | Raw FTMO symbol | Status |
|---|---|---|
| XAUUSD | XAUUSD | imported |
| XAGUSD | XAGUSD | imported |
| US500 | US500.cash | imported |
| US30 | US30.cash | imported |
| USTEC | US100.cash | imported |
| DE40 | GER40.cash | imported |
| FRA40 | FRA40.cash | imported |
| AUS200 | AUS200.cash | **dropped (no FTMO history)** |

Import log summary (`scripts/import-mt5-history.py --write ... --split-threshold-bytes 0`): **wrote 56
series, 59 refused**. The 56 are exactly 7 symbols x 8 timeframes; the 59 refusals are every OTHER
`history.*.json` export in the source folder (MetaQuotes-Demo's own files -- refused on server mismatch --
and DXY.cash/EU50.cash/UK100.cash/US2000.cash/AUS200.cash, none of which are on the needed-symbol
allowlist or were requested).

## Per-series coverage

Every cell below is `bt.load(sym, tf)` with `BT_HISTORY_ROOT` pointed at `data/history/ftmo`, then
`quality.assess()` against the series' own `last_updated`. Bar counts and first/last bar are read from the
loaded series (so the split-gz reader is verified through the SAME path the engine uses, not by inspecting
`index.json` alone). All 56 series are now the split-gz shape (`data/history/ftmo/ohlcv.<SYM>.<TF>/` --
`index.json` + one `<year>.json.gz` part per UTC calendar year).

| Symbol | TF | Bars | First (UTC) | Last (UTC) | §20 state | Year parts |
|---|---|---:|---|---|---|---:|
| XAUUSD | 1W | 1,165 | 2004-06-05 | 2026-09-26 | FRESH | 23 |
| XAUUSD | 1D | 5,737 | 2004-06-10 | 2026-09-27 | FRESH | 23 |
| XAUUSD | 4H | 34,181 | 2004-06-11 | 2026-09-28 | FRESH | 23 |
| XAUUSD | 1H | 132,027 | 2004-06-11 | 2026-09-28 | FRESH | 23 |
| XAUUSD | 30m | 260,313 | 2004-06-11 | 2026-09-28 | FRESH | 23 |
| XAUUSD | 15m | 514,807 | 2004-06-11 | 2026-09-28 | FRESH | 23 |
| XAUUSD | 5m | 1,497,574 | 2004-06-11 | 2026-09-28 | FRESH | 23 |
| XAUUSD | 1m | 5,000,000 | **2012-06-14** | 2026-09-28 | FRESH | 15 |
| XAGUSD | 1W | 935 | 2008-11-01 | 2026-09-26 | FRESH | 19 |
| XAGUSD | 1D | 4,618 | 2008-11-06 | 2026-09-27 | FRESH | 19 |
| XAGUSD | 4H | 27,579 | 2008-11-07 | 2026-09-28 | FRESH | 19 |
| XAGUSD | 1H | 107,072 | 2008-11-07 | 2026-09-28 | FRESH | 19 |
| XAGUSD | 30m | 210,993 | 2008-11-07 | 2026-09-28 | FRESH | 19 |
| XAGUSD | 15m | 418,598 | 2008-11-07 | 2026-09-28 | FRESH | 19 |
| XAGUSD | 5m | 1,234,829 | 2008-11-07 | 2026-09-28 | FRESH | 19 |
| XAGUSD | 1m | 5,000,000 | **2012-05-03** | 2026-09-28 | STALE | 15 |
| US500 | 1W | 458 | 2017-12-23 | 2026-09-26 | FRESH | 10 |
| US500 | 1D | 2,261 | 2017-12-28 | 2026-09-27 | FRESH | 10 |
| US500 | 4H | 9,569 | 2017-12-28 | 2026-09-28 | FRESH | 10 |
| US500 | 1H | 34,369 | 2017-12-28 | 2026-09-28 | FRESH | 10 |
| US500 | 30m | 64,097 | 2017-12-28 | 2026-09-28 | FRESH | 10 |
| US500 | 15m | 123,546 | 2017-12-28 | 2026-09-28 | FRESH | 10 |
| US500 | 5m | 357,496 | 2017-12-28 | 2026-09-28 | FRESH | 10 |
| US500 | 1m | 1,746,192 | 2017-12-28 | 2026-09-28 | STALE | 9 |
| US30 | 1W | 397 | 2019-02-02 | 2026-09-26 | FRESH | 8 |
| US30 | 1D | 1,954 | 2019-02-07 | 2026-09-27 | FRESH | 8 |
| US30 | 4H | 11,659 | 2019-02-08 | 2026-09-28 | FRESH | 8 |
| US30 | 1H | 44,369 | 2019-02-08 | 2026-09-28 | FRESH | 8 |
| US30 | 30m | 88,646 | 2019-02-08 | 2026-09-28 | FRESH | 8 |
| US30 | 15m | 177,171 | 2019-02-08 | 2026-09-28 | FRESH | 8 |
| US30 | 5m | 526,995 | 2019-02-08 | 2026-09-28 | FRESH | 8 |
| US30 | 1m | 2,630,587 | 2019-02-08 | 2026-09-28 | STALE | 8 |
| USTEC | 1W | 458 | 2017-12-23 | 2026-09-26 | FRESH | 10 |
| USTEC | 1D | 2,261 | 2017-12-28 | 2026-09-27 | FRESH | 10 |
| USTEC | 4H | 9,570 | 2017-12-28 | 2026-09-28 | FRESH | 10 |
| USTEC | 1H | 34,369 | 2017-12-28 | 2026-09-28 | FRESH | 10 |
| USTEC | 30m | 64,094 | 2017-12-28 | 2026-09-28 | FRESH | 10 |
| USTEC | 15m | 123,537 | 2017-12-28 | 2026-09-28 | FRESH | 10 |
| USTEC | 5m | 357,538 | 2017-12-28 | 2026-09-28 | FRESH | 10 |
| USTEC | 1m | 1,768,715 | 2017-12-28 | 2026-09-28 | STALE | 9 |
| DE40 | 1W | 427 | 2017-12-23 | 2026-09-26 | FRESH | 10 |
| DE40 | 1D | 2,093 | 2017-12-27 | 2026-09-27 | FRESH | 10 |
| DE40 | 4H | 8,942 | 2017-12-27 | 2026-09-28 | FRESH | 10 |
| DE40 | 1H | 31,955 | 2017-12-27 | 2026-09-28 | FRESH | 10 |
| DE40 | 30m | 59,517 | 2017-12-27 | 2026-09-28 | FRESH | 10 |
| DE40 | 15m | 114,616 | 2017-12-27 | 2026-09-28 | FRESH | 10 |
| DE40 | 5m | 331,451 | 2017-12-27 | 2026-09-28 | FRESH | 10 |
| DE40 | 1m | 1,620,474 | 2017-12-27 | 2026-09-28 | STALE | 9 |
| FRA40 | 1W | 458 | 2017-12-23 | 2026-09-26 | FRESH | 10 |
| FRA40 | 1D | 2,238 | 2017-12-28 | 2026-09-27 | FRESH | 10 |
| FRA40 | 4H | 8,569 | 2017-12-28 | 2026-09-28 | FRESH | 10 |
| FRA40 | 1H | 29,988 | 2017-12-28 | 2026-09-28 | FRESH | 10 |
| FRA40 | 30m | 55,358 | 2017-12-28 | 2026-09-28 | FRESH | 10 |
| FRA40 | 15m | 106,041 | 2017-12-28 | 2026-09-28 | FRESH | 10 |
| FRA40 | 5m | 304,331 | 2017-12-28 | 2026-09-28 | FRESH | 10 |
| FRA40 | 1m | 1,438,246 | 2017-12-28 | 2026-09-28 | STALE | 9 |

56 of 56 (7 symbols x 8 timeframes) requested series are present. No `_structural_fault` (OHLC validity,
ordering, duplicates) or PARTIAL flag on any series -- CFD symbols are not `instruments.is_continuous()`, so
§20's continuity check does not apply (a weekend gap is not a fault); every remaining §20 question
(structural validity) was already enforced bar-by-bar during import (`_convert_bar`), so no series could
reach this table in anything but a structurally valid state. Bar counts, first/last timestamps and §20
structural validity are UNCHANGED from the first import -- this re-import is the same data, split
differently.

**Every STALE reading above (each symbol's own 1m series, XAGUSD's most recently) is expected, not a
fault.** `bt.load()`'s own comment: *"Freshness is meaningless for an archive -- nothing is late in 2023."*
The 1m §20 staleness threshold is a few minutes; by the time a later series in a ~35-minute import run was
assessed, an earlier one had already aged past its own threshold. None of this reflects a hole or a stale
FEED; it is the same "minutes-old is not fresh for a 1-minute bar" rule that applies to any research archive
read after the moment it was written.

## Data completeness caveats

* **XAUUSD and XAGUSD M1 do not reach as far back as their own higher timeframes.** `ExportHistory.mq5`'s
  `InpBars = 5000000` cap was hit exactly (`_bars: 5000000` in the raw export header) for both symbols' M1
  series: XAUUSD 1m starts 2012-06-14 even though XAUUSD 1W/1D/4H/1H/30m/15m/5m all start 2004-06;
  XAGUSD 1m starts 2012-05-03 even though XAGUSD's higher timeframes start 2008-11. The other 5 symbols'
  M1 series (1.4M-2.6M bars each) are well under the 5,000,000 cap and were NOT truncated -- their M1 history
  reaches back exactly as far as their higher timeframes (2017-12/2019-02, matching this account's own
  younger history for those instruments). A re-export with a higher `InpBars` (or accepting the current
  ceiling as this account's practical M1 depth for gold/silver) is an owner decision, not something this
  import can fix -- it converts what the export produced and no more.
* **US30's history (all timeframes) starts 2019-02-08**, roughly a year after the other 6 symbols'
  2017-12/2018 start -- a fact read from the export, not assumed.

## Test evidence

`python -m unittest scripts.tests.test_ftmo_history` -- 27 tests, including
`SplitRoundTrip.test_split_threshold_zero_small_series_reads_back_identical_via_bt_load` (the exact claim
fix round 1 asked for: a SMALL series, written split+gz because `split_threshold=0` forced it, reads back
through `backtest-methods.load()` byte-identical to what the in-memory `convert()` path would have produced
for the same input) and `test_a_stale_plain_single_file_is_removed_once_superseded_by_a_split_write`
(a pre-existing plain-file copy is deleted once a split write for the same series commits).
