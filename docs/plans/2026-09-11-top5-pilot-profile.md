# Plan — pilot profile `top5` (2026-09-11)

Goal: run the three most stable backtested rules (ICT 30m, COMBINED 30m, ICT 1H; each with/without the 2H boundary filter) as a
mechanical pilot on Binance Futures TESTNET, operated only through `/automation`. No LLM decides an order. Environment stays `demo`.

Trust boundary: money + external API → full workflow (Security review before the runner goes live; TDD; QA = parity + one testnet round-trip).

## Files (one writer per file kept)
| File | Change |
|---|---|
| `scripts/fetch-binance-klines.sh` | intervals 30m, 2H |
| `scripts/scan-loop.sh` | fetch 30m/2H × 300 for enabled crypto at :01/:31 (pilot data only; no analysis style, no artifact) |
| `scripts/binance-futures-testnet-order.sh` | `open-long-limit` / `open-short-limit` = LIMIT + timeInForce GTX (post-only, maker) |
| `scripts/automation.py` + schema | `execution.pilot_profile` ∈ {legacy, top5} (default legacy); `pilot profile <name>`; shown in `status` |
| `scripts/pilot-loop.sh` | profile → `strategy-runner.py --live` (futures only) with 30-minute ticks; legacy unchanged |
| `scripts/strategy-runner.py` | NEW: signals from `backtest-methods.py` functions on live candles; limit GTX entry; STOP_MARKET + TAKE_PROFIT_MARKET closePosition; cancel unfilled after K bars; breakeven at +1R; time stop H bars; halts; log.jsonl kinds entry/exit compatible with journal |
| `scripts/journal.py` + `trade-file.schema.json` | pilot records carry `strategy`, `config`, `htf_pass` (tags + fields) |
| `scripts/tests/test_strategy_runner.py` | parity with backtest on history, sizing clamp, BE logic, profile switch |
| docs | SYSTEM-DESIGN §9, data-sources, trades/README, .claude/commands/automation.md, parity report |

## Rules (exact = backtest, causal only)
- ICT: last 3-bar pivot sweep → MSS body close within K → FVG in leg → LIMIT at FVG near edge, valid K bars after MSS; stop = excursion extreme ∓ 0.05 %; target = R-bar extreme before the sweep. No fill → no trade.
- COMBINED: Spring/Upthrust proxy (R-bar border pierce, reclaim ≤ 2 bars, volume type gate) + the ICT confirmation → LIMIT at FVG edge only (`--combined-entry limit`; the old fallback to the MSS close used hindsight and is retired).
- Management: BE at +1R (replace stop), time stop after H bars, one position per symbol, max 2 open, 1 % risk (env PILOT_RISK_PCT clamped), notional cap 25 % × leverage 3.
- Halts: equity −15 % from start, 5 consecutive losses, 3 consecutive connector errors, event blackout ±30 min, kill switch STOP, `/automation allows pilot`.
- HTF (config C): `htf_allows` on the 2H series; signals are logged with `htf_pass` either way, orders only when the profile's filter passes (default: filter OFF, i.e. config B; `--htf` flag on the runner selects C).

## Acceptance
1. `python3 -m unittest scripts/tests/test_strategy_runner.py` green.
2. Replay parity: runner `--replay` over the last 600 bars of `data/history` 30m/1H reproduces the backtest signal list (time, side, entry, stop, target) — report in `docs/backtests/2026-09-11-runner-parity.md`.
3. `binance-futures-testnet-order.sh check` ok; one far-from-market GTX limit placed and cancelled on testnet.
4. The user (not this session) runs `/automation pilot profile top5` then `/automation demo`.
