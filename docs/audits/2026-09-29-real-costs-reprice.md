# A0 real-cost re-pricing of the development baseline (2026-09-29)

**Status: informational only.** This is the ONE disclosed re-pricing run named in
`docs/plans/2026-09-28-methodology-improvement-plan.md` §2 "A0 Costs" item 4. It changes no methodology,
selects no candidate, and proposes no rule. It measures what the same trades from
`docs/audits/2026-09-28-method-diagnosis.md` look like once spread and swap are the broker's own recorded
figures instead of the flat 0.05 %/side assumption `docs/architecture/risk-config.json` itself labels "an
assumption". A0 explicitly never re-evaluates `[2024-03, 2025-03)` (`oos_exposed`) as evidence (plan §2); this
run reads nothing at or after that boundary (see "Point-in-time" below).

**Caveat added in code review, fix round 1 (2026-09-29):** this run was measured BEFORE
`scripts/mt5_time.py UsDatesFixedOffsetZone.fromutc()` was fixed (a wrong-by-up-to-two-hours UTC->local
conversion right at a US DST edge, which `real_costs.nights_held()`/`crosses_rollover()` inherited via
`.astimezone(zone)`). The bug can only have affected `swap_R`/`cost_R_total`/`net_R` in the two "real" columns
below, and only for a trade whose `entry_time` or `exit_time` fell inside the roughly one-hour mis-zoned
window around a 2nd-Sunday-March or 1st-Sunday-November transition instant -- it never affected which trades
were scanned, their entry/stop/target/gross R, or point-in-time correctness (§8; the scan/admission path does
not call `real_costs` at all). This table was not re-measured after the fix (a full re-scan of this dataset
takes on the order of an hour -- see "What produced these numbers"); a future re-run is warranted before this
table is used for anything beyond the disclosure it already is. `scripts/tests/test_real_costs.py
FromUtcIsExactAcrossDstTransitions` is the regression test for the underlying bug.

## What produced these numbers

- Engine: `scripts/backtest-methods.py` `scan()`/`simulate()`, unmodified detection logic -- only the cost
  model changed (`cost_profile="ftmo_demo_2026_09"` on `simulate()`, and `flat_before_rollover` on `scan()`
  for the fund-cell variant). Code: `scripts/real_costs.py` (new), `scripts/backtest-methods.py` (`walk()`
  `Tm`/`flat_before_rollover`, `simulate()` `cost_profile`/`spread_stat`), `scripts/snapshot.py`
  (`execution_assumptions.cost_profile`/`flat_before_rollover`).
- Data: `BT_HISTORY_ROOT=data/history/ftmo` (FTMO-Demo, the fund's own feed -- plan §6 items 3, 7), 15m,
  symbols XAUUSD, US500, DE40 -- the three development symbols (§0 evidence table), config A (`side=taker,
  mgmt=none, htf=False`, `scripts/stability-report.py` CONFIGS), methods ICT and WYCKOFF-BOOK.
- Cost profile: `ftmo_demo_2026_09` (`scripts/real_costs.py PROFILES`), built from
  `data/history/costs/ftmo/symbolspec.*.json` (exported 2026-09-28 by `integrations/mt5/ExportSymbolSpec.mq5`)
  and `data/history/costs/ftmo/symbol-map.json`. Source file sha256 (via `real_costs.profile_snapshot`):

  | file | sha256 |
  |---|---|
  | `data/history/costs/ftmo/symbol-map.json` | `44d469ee280109c56158931ab20bc70375d97775b8ee543fcb32497d53a83bd1` |
  | `data/history/costs/ftmo/symbolspec.XAUUSD.json` | `85517bc67b5a2133c85c1e0793b18e1c4717bfe1a3af80d14902aa90b3456060` |
  | `data/history/costs/ftmo/symbolspec.US500.cash.json` | `94229383baa1d30337c3e0a345498a19849eb66244f1b8a143fa7282d0ee30df` |
  | `data/history/costs/ftmo/symbolspec.GER40.cash.json` (DE40) | `caf6f696a60b2d59b4a31c8ff4941abdd1607f0b7a369ee3beea8bf2258addc0` |

  Spread: `recorded_spread_m15.by_utc_hour` median at the entry bar's and the exit bar's own UTC hour, half
  each (round trip pays the spread once). Swap: `swap_long`/`swap_short` (points/lot/day, swap_mode 1 =
  POINTS), one charge per server-local night held, tripled on the spec's own `swap_rollover3days` day.
  Commission: every symbol here declares `commission.status: "no_deals"` -- priced at 0.0 and flagged
  `UNKNOWN`, never guessed (`real_costs.commission_r`). Server clock: FTMO-Demo
  (`docs/architecture/providers.json mt5_bridge_ftmo`, `docs/audits/2026-09-29-ftmo-server-timezone.md`).
- Code version: `3343294f952c414fbfc41effbea05ca480ff1271` (branch `a0-real-costs`), plus the four A0 files
  above, uncommitted at measurement time.

## Point-in-time

`bt.pit_cutoff("2024-03-01T00:00:00Z")` was set before any `scan()` call, so no candle at or after that
instant was loaded (`scripts/backtest-methods.py load()` -> `pit.series_as_of()`). Latest trade exit time seen
across all eighteen cells below: **2024-02-20T12:30:00Z** (DE40 WYCKOFF-BOOK) -- before the cutoff, as
required. Raw run output: `a0_reprice_result.json` (evidence path below).

## Results

Three variants per (symbol, method) cell:
- **baseline** -- today's v1 flat fee (0.05 %/side, `docs/architecture/risk-config.json` `costs.mt5`), no
  cost profile, no flatten rule. This is `docs/audits/2026-09-28-method-diagnosis.md`'s own cost convention,
  just re-measured on the FTMO feed instead of MetaQuotes-Demo's.
- **real (no flatten)** -- `ftmo_demo_2026_09` cost profile, `flat_before_rollover=False`.
- **real + flatten** -- `ftmo_demo_2026_09` cost profile, `flat_before_rollover=True` (the fund-cell
  "no overnight holding" rule, §2 A0 / §6 items 3, 5, 7): a position still open at the last bar closing
  before FTMO-Demo's own server midnight is closed there, `exit_reason="rollover_flat"`.

Trade counts differ slightly between variants: `simulate()`'s planned-R:R admission gate
(`R_planned - fee_R < min_rr`) compares against the SAME trades' fee, and the real cost model charges a
different fee than the flat one -- a trade the flat fee rejected can clear the floor under the (usually
cheaper, wide-stop CFD) real cost, or vice versa. The flatten variant additionally changes some trades' own
exit (and therefore `entry_time`/`exit_time`-derived swap), which can itself tip an admission. Every count
below is the actual admitted population for that variant, not the same 96/129/... trades re-priced three ways.

| Symbol | Method | Variant | Trades | Gross R | Spread R | Swap R | Net R |
|---|---|---|---:|---:|---:|---:|---:|
| XAUUSD | ICT | baseline (flat fee) | 96 | +3.75 | -- | -- | -32.05 |
| XAUUSD | ICT | real, no flatten | 100 | +5.96 | 6.77 | 4.94 | -5.76 |
| XAUUSD | ICT | real, flatten | 103 | +10.38 | 7.14 | 0.00 | +3.24 |
| XAUUSD | WYCKOFF-BOOK | baseline (flat fee) | 129 | -22.49 | -- | -- | -86.17 |
| XAUUSD | WYCKOFF-BOOK | real, no flatten | 145 | -24.99 | 11.02 | 9.60 | -45.61 |
| XAUUSD | WYCKOFF-BOOK | real, flatten | 148 | +0.80 | 11.09 | 0.00 | -10.28 |
| US500 | ICT | baseline (flat fee) | 25 | -1.25 | -- | -- | -8.05 |
| US500 | ICT | real, no flatten | 28 | +2.84 | 0.91 | 0.40 | +1.53 |
| US500 | ICT | real, flatten | 29 | -0.85 | 0.91 | 0.00 | -1.76 |
| US500 | WYCKOFF-BOOK | baseline (flat fee) | 27 | +6.95 | -- | -- | -7.55 |
| US500 | WYCKOFF-BOOK | real, no flatten | 31 | +7.40 | 1.72 | 0.41 | +5.28 |
| US500 | WYCKOFF-BOOK | real, flatten | 33 | +7.32 | 1.78 | -0.00 | +5.54 |
| DE40 | ICT | baseline (flat fee) | 11 | +1.72 | -- | -- | -1.82 |
| DE40 | ICT | real, no flatten | 11 | +1.72 | 0.29 | 0.07 | +1.36 |
| DE40 | ICT | real, flatten | 11 | -1.64 | 0.32 | 0.00 | -1.96 |
| DE40 | WYCKOFF-BOOK | baseline (flat fee) | 27 | +22.79 | -- | -- | +9.79 |
| DE40 | WYCKOFF-BOOK | real, no flatten | 31 | +22.61 | 1.68 | 1.48 | +19.46 |
| DE40 | WYCKOFF-BOOK | real, flatten | 32 | +26.74 | 1.75 | 0.00 | +24.99 |

Commission R is 0.00 in every cell (every symbol's spec declares `commission.status: "no_deals"` -- see
"What produced these numbers" above); omitted as a column since it never varies here.

Raw per-cell JSON (spread/swap/commission decomposition, refused-trade counts, last exit time): evidence path
below.

## What this shows, and what it does not

- The flat 0.05 %/side assumption (`net_R` "baseline" column) is dramatically more pessimistic than the
  broker's own recorded spread/swap on every cell measured here -- `cost_R_total` (gross minus net) under the
  flat assumption is 3.1x-9.9x the real (no-flatten) figure across the six cells (XAUUSD 3.1x both methods,
  US500 5.2x/6.8x, DE40 9.9x/4.1x). `risk-config.json`'s
  own `_spread_note` already flagged this direction ("Treating it as a flat per-side percentage ... UNDERSTATES
  cost when the spread widens"); this run is the first measurement of the size of that gap on FTMO-Demo data.
- `flat_before_rollover` removes ALL swap cost (by construction -- no position survives to a rollover) at the
  price of a different, usually smaller, spread-only cost and a changed trade population/exit set. It is NOT
  shown here as "better": four of the six flatten cells have a HIGHER net R than the matching no-flatten cell
  (XAUUSD both methods, US500 WYCKOFF-BOOK, DE40 WYCKOFF-BOOK); two (US500 ICT, DE40 ICT) are LOWER --
  consistent with "no overnight holding" being a fund CONSTRAINT (§6 item 5), not a method chosen for
  performance.
- This is six (symbol, method) cells x three cost variants on development data already read by
  `docs/audits/2026-09-28-method-diagnosis.md` (and by the 180 prop-search records, §0). It is a re-pricing of
  ALREADY-EXPOSED development evidence, not a new read of held-out data, and it does not by itself pass or
  fail anything against §3/§4's pre-declared statistics (no walk-forward, no lower bound, no stability check
  was computed here). **No candidate is selected or rejected by this document.**
- `[2024-03-01, 2025-03-01)` was not read (point-in-time section above). If the 180 prop-search records are
  ever re-priced under this profile, plan §2 requires that to be its own disclosed erratum, not folded into
  this file.

## Evidence

- `scripts/real_costs.py` -- the cost model (spread/swap/commission, `crosses_rollover`, `profile_snapshot`).
- `scripts/backtest-methods.py` -- `walk()` (`Tm`, `flat_before_rollover`), `simulate()` (`cost_profile`,
  `spread_stat`), `main()` (`--cost-profile`, `--spread-stat`, `--flat-before-rollover`).
- `scripts/snapshot.py` -- `backtest_config_snapshot(cost_profile=...)`, `execution_assumptions.cost_profile`
  / `.flat_before_rollover`.
- `scripts/tests/test_real_costs.py` -- 24 tests (spread-by-hour incl. daily-break fallback, swap nights incl.
  triple day and the FTMO US-dates DST edge, non-POINTS swap_mode refusal, flatten-at-the-right-bar /
  never-a-later-bar, default-profile-byte-identical). All pass:
  `$TMP/a0-tests.log` (`python -m unittest scripts.tests.test_real_costs scripts.tests.test_backtesting
  scripts.tests.test_prop_search scripts.tests.test_scan_cache scripts.tests.test_snapshot
  scripts.tests.test_risk_model` -- 212 tests, OK).
- `$TMP/a0-rows.log`, `$TMP/a0-rows-before.json`, `$TMP/a0-rows-after.json` -- `stability-report.py --tf 4H
  --symbols AUS200 --workers 1` with no `--cost-profile`, run against the pre-A0 code (`git stash`) and the
  post-A0 code: `rows`/`research_validity`/`run_params`/`oos_holdout` byte-identical; the only
  `config_snapshot` differences are the two new, additive, `not_applicable`/`false` execution_assumptions
  fields and the expected uncommitted-file dirty-tree bookkeeping.
- `docs/audits/2026-09-29-real-costs-reprice.json` -- the raw per-cell output this document's table is built
  from (spread/swap/commission decomposition, refused-trade counts, last exit time per cell), committed
  alongside this file (code review 2026-09-29, fix round 1, item 2) so the table is reproducible without a
  scratch/session path.
- `scripts/research/reprice_real_costs.py` -- the measurement script that produced the JSON above (`ROOT`
  derived from `__file__`, not hardcoded -- same fix round). Re-running it regenerates
  `docs/audits/2026-09-29-real-costs-reprice.json` in place; see the fromutc-fix caveat at the top of this
  document for why a re-run is warranted before this table is relied on for anything beyond disclosure.
