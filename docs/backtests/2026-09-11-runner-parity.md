> **Superseded 2026-09-13.** The ICT figures here were produced by the legacy in-file rules, replaced by the live scanner (`docs/plans/2026-09-13-unify-backtest-with-live-rules.md`); see `docs/backtests/2026-09-13-live-rules-vs-legacy.md`. Wyckoff / COMBINED / PARTIAL figures are unaffected.

# Runner ↔ backtest parity — 2026-09-11

`python3 scripts/strategy-runner.py --replay 30m --bars 1500` and `--replay 1H --bars 1500`: the runner walks history bar by bar
as if it ticked at every close (300-bar window each tick, no look-ahead) and records every LIMIT it would have placed; each
`backtest-methods.py` trade in the same span must have a placement with the same sweep time, side, entry, stop and target.

| Khung | Mã | Luật | Lệnh backtest | Khớp | Lệch | Lệnh limit runner đặt | Trong đó không khớp (hết hạn) |
|---|---|---|---|---|---|---|---|
| 30m | BTCUSDT | ICT | 5 | 5 | 0 | 21 | 16 |
| 30m | BTCUSDT | COMBINED | 0 | 0 | 0 | 6 | 6 |
| 30m | ETHUSDT | ICT | 8 | 8 | 0 | 22 | 14 |
| 30m | ETHUSDT | COMBINED | 1 | 1 | 0 | 5 | 4 |
| 30m | SOLUSDT | ICT | 15 | 15 | 0 | 29 | 14 |
| 30m | SOLUSDT | COMBINED | 1 | 1 | 0 | 6 | 5 |
| 1H | BTCUSDT | ICT | 4 | 4 | 0 | 21 | 17 |
| 1H | ETHUSDT | ICT | 11 | 11 | 0 | 20 | 9 |
| 1H | SOLUSDT | ICT | 8 | 8 | 0 | 20 | 12 |

53 / 53 backtest trades reproduced; 0 mismatches. Roughly 60 % of placed limits expire unfilled (the backtest counts only fills).

Two look-ahead defects were found by this test and fixed in the backtest (not in the runner):
1. `find_ict` accepted an FVG whose third candle was the candle after the MSS, and `fvg_fill` "filled" the limit at that candle's
   low — the gap is only known after the candle closed. Fix: the FVG must be complete by the MSS close.
2. COMBINED fell back to a market entry at the MSS close only when the future showed no return to the FVG. Fix: `--combined-entry limit`.

Both fixes changed the backtest numbers materially — see `2026-09-11-stability-by-timeframe.md` ("Cách đọc").

Testnet checks the same day (`scripts/binance-futures-testnet-order.sh`, environment demo): `check` ok; `open-long-limit` GTX at
50 % below market accepted (status NEW, timeInForce GTX) and cancelled; a GTX limit above market rejected with -5022 (would take
liquidity), nothing left open; `newClientOrderId` round-trip via `order-by-client-id`; MIN_NOTIONAL on testnet = 50 USDT;
`round-price` no longer prints scientific notation (3.86E+4 was rejected with -1111). One dry-run tick of the runner
(`--dry-run --ignore-gate`) fetched 30m/1H/2H candles into `data/live/pilot-futures/candles/`, evaluated all three rules and
placed nothing. Unit tests: `python3 -m unittest scripts/tests/test_strategy_runner.py` (9 tests) green.