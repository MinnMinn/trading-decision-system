# Pre-registration brief for the owner (2026-09-30) — decisions needed BEFORE `fund-search declare`

Sources: docs/plans/2026-09-29-fund-search-preregistration-DRAFT.md (12 choices + O1..O9),
docs/plans/2026-09-29-v-ict-constants-DRAFT.md, docs/plans/2026-09-30-owner-decisions.md. Nothing is sealed.
`declare` pins code SHAs, grid hashes and the settings below; after it, any code or setting change is reported as drift.

## What is already fixed (no decision needed)
- All nine F items ON in every cell; live/pilot stay v1. N = 29 per ICT cell (was 41 before the owner removed B-EXIT `no_floor`, 2026-09-30), 16 per Wyckoff cell, 3 cells (1m-metals, 1m-indices, 5m-metals: the owner applied the pre-stated inclusion rule e_min <= 2 x e_star, 2026-10-01, `docs/audits/2026-10-01-cell-selection.md`; 5m-indices, 15m-metals, 15m-indices and both 30m cells were removed, `docs/architecture/fund-search-cells.json`)
  => N_ICT 87, N_Wyckoff 48 (confidence 0.998851 / 0.997917). Planned R:R floor = 2.5 net of fees, both methods, pinned in the declaration (`evaluation_config.min_rr`). B4 and W4b are declared, not runnable, counted in N.
- Statistic: min of five one-sided bounds (iid t, cluster by UTC day, 30 days, quarter, half-year) at 1 - 0.10/N,
  computed on pooled TEST-fold trades only; fold geometry 365/730 days; verdict precedence; costs real; no overnight.
- O8 (ICT fill on the last bar of a server day held past midnight) is RESOLVED by the walk() fix (2869c35): the
  fill-bar boundary is now asked. The harness still records entries on the last bar of a server day.

## Decisions needed (my recommended default first)
| # | Question | Recommended | Why |
|---|---|---|---|
| O1 | min_rr admission depends on the EXIT-hour spread (look-ahead vs plan §37) | Add an `fx_` key so admission uses the ENTRY-hour cost only, adopt it, then declare | It removes a known look-ahead from a result you will rely on; ~1 day of work; default v1 unchanged |
| O2 | Embargo of one time-stop horizon after each test fold | Yes (stricter) | Cheap; covers serial dependence between last training and first test trades |
| O3 | Keep 365/730 fold sizes | Keep | Set from dates, not results; fold counts differ by cell (4-17) and that is disclosed |
| O4 | Deployment rule for a PASS | "Values chosen in the final fold" | A PASS certifies a selection procedure, so a rule is needed to name one configuration |
| O6 | FTMO commission unknown | Accept the disclosure for this run; measure it with one 0.01-lot round trip and re-export | Net R is NOT net of commission today; a PASS would be optimistic by that amount |
| O7 | Regime split threshold | Median of pooled TEST trades (as written) | Descriptive only; never feeds selection |
| V-ICT | Constants not in the plan grid: ATR_PERIOD=14; B-POOL = most recent completed UTC day + latest asia/london run; B-LB scaling on 1m/5m; B7 killzone = registry windows at fill-bar open, indices only; B3 pairing table (30m has no pair -> no trades under tfa_p5) | Accept as listed in the V-ICT DRAFT | Each is disclosed and fixed before any run |

## Expectations to set honestly
- Baseline trade frequency (structural counts, adopted-F baseline): XAUUSD 15m ICT 523 trades / 20 yrs, Wyckoff 346;
  US500 5m ICT 239 / ~3 yrs, Wyckoff 157. Many 15m cells may still read "insufficient" (needs >= 30 trades per
  365-day test fold and gaps <= 30 days); 1m/5m index cells are the most likely to be testable.
- The bound is deliberately strict: a genuine ~+0.30R edge survives at n≈600 over several years; edges <= 0.15R mostly do not.
- The honest outcome may be zero passes. The only pristine evidence afterwards is a forward demo (needs your explicit go-ahead; pilot stays OFF).

## Compute (measured / projected)
- Engine speed: ~40x with 10 workers at equal results (docs/audits/2026-09-30-engine-speed-profile.md). Heaviest cell
  (metals 1m) projected ~3.7 h wall for both methods; a wave-1 measurement on ICT XAUUSD 1m is running now.
- Local run is feasible; GitHub Actions sharding (plan (a)) is optional and needs your go-ahead to push/trigger.
