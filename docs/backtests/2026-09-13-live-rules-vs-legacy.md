# Live rules vs the legacy backtest engine — 2026-09-13

**What changed.** `scripts/backtest-methods.py` used to carry its own simplified ICT implementation. It has now
been rewired to call the code the live analysis actually runs — `scripts/ict-scan.py` for the structures and
`scripts/htf_context.py` for the higher-timeframe bias — through the point-in-time adapter
`scripts/live_rules.py`. Plan: `docs/plans/2026-09-13-unify-backtest-with-live-rules.md`.

**How this was produced.**

```bash
SYMS=$(python3 -c "import json;print(','.join(json.load(open('docs/architecture/automation-config.json'))['markets']['crypto']['instruments']))")
python3 scripts/backtest-methods.py --rules legacy --tf 5m,15m,1H,4H,1D --symbols "$SYMS" --json /tmp/bt-legacy.json
python3 scripts/backtest-methods.py --rules live   --tf 5m,15m,1H,4H,1D --symbols "$SYMS" --json /tmp/bt-live.json
```

All nine configured crypto instruments, not `backtest-methods.py`'s three-symbol default. Legacy ran in 1m41s;
live in 36m07s. Account $10,000, 1 % risk per trade, compounding, fees 0.05 % per side.

---

## The change is surgical: only ICT moved

Every method other than ICT is **byte-identical** between the two runs, at every timeframe — same trade count,
same win rate, same ΣR, same profit factor, same final equity.

```
methods differing between legacy and live: NONE — only ICT moved
```

That is the correct outcome and worth stating first. `scan()`'s Wyckoff / COMBINED / PARTIAL block calls
`find_ict` unconditionally, so the live/legacy fork exists only for the pure ICT branch. The unification did not
silently perturb anything it was not supposed to touch.

## ICT: legacy vs live

| tf | legacy n | PF | ΣR | final $ | ruin | live n | PF | ΣR | final $ | ruin |
|---|---|---|---|---|---|---|---|---|---|---|
| 5m | 699 | 0.62 | −222.1 | 993 | **blew up** | 1,579 | 0.84 | −151.0 | 1,887 | survived |
| 15m | 1,157 | 0.74 | −218.0 | 999 | **blew up** | 426 | **1.43** | **+100.0** | **25,442** | survived |
| 1H | 1,261 | 1.02 | +11.6 | 9,789 | — | 99 | 1.09 | +4.3 | 10,347 | — |
| 4H | 176 | 1.23 | +19.0 | 11,915 | — | 25 | **1.55** | +5.7 | 10,567 | — |
| 1D | 9 | 1.32 | +0.7 | 10,064 | — | **0** | — | — | 10,000 | — |

**Live is better on profit factor at every single timeframe**, and it never destroyed the account. Legacy
destroyed it twice — 5m on 2025-10-04 and 15m on 2024-07-04. For a system whose first rule is capital
preservation, that difference matters more than the return figures.

The 15m row is the headline: the same rules the pages and verdicts use turned $10,000 into $25,442 over three
years, where the proxy the backtest used to run lost the account entirely.

## What this table does NOT say — read before acting on it

**Live trades far less at the slower rungs.** 99 trades at 1H and 25 at 4H, against 1,261 and 176. A profit
factor computed on 25 trades is not a measurement, it is an anecdote. The 4H row is the clearest example of the
trap: live has the better PF (1.55 vs 1.23) and the *worse* final equity ($10,567 vs $11,915), because better
rules applied far less often make less money. Do not read "higher PF" as "more profit".

**1D produced zero trades, which is not a good result — it is no result.** On BTCUSDT 1D over 1,261 scanned
bars the live scanner found 21 candidates, 6 of them complete, and `pd_ok` rejected all 6: every complete setup
was a long sitting in the premium half of the dealing range, which `knowledge/04 §3.4 R13` forbids. That is the
rule working as written, but it means the 1D column carries no evidence either way.

**5m still loses.** PF 0.84 is an improvement on 0.62 and it no longer ends in ruin, but it is still below 1.0.
Live rules did not make 5m tradeable; they made it survivable.

**Thin samples.** After the full-window requirement (a backtest may only read where the live scanner could
actually have scanned), usable bars per instrument are:

| symbol | 5m | 15m | 1H | 4H | 1D |
|---|---|---|---|---|---|
| BTC / ETH / SOL | 104,425 | 104,425 | 34,521 | 8,441 | 1,261 |
| ASTERUSDT | 97,588 | 32,234 | 7,724 | 1,687 | **103** |
| VIRTUALUSDT | 104,425 | 49,315 | 11,994 | 2,755 | **281** |
| SUIUSDT | 104,425 | 104,425 | 29,012 | 7,009 | 990 |
| TAOUSDT | 104,425 | 84,363 | 20,756 | 4,945 | 646 |
| RENDERUSDT | 104,425 | 74,203 | 18,216 | 4,310 | 540 |
| ONDOUSDT | 104,425 | 49,315 | 11,994 | 2,755 | **281** |

The six newer listings have far less history than BTC/ETH/SOL, and three of them have almost no usable 1D bars
at all. The per-timeframe rows above pool all nine instruments, so the 1D and 4H rows lean on BTC/ETH/SOL by
construction. Do not read a pooled row as if each instrument contributed equally.

## Parameters

Every parameter that forked between the two engines was resolved to **live's** value (user decision
2026-09-13), including `setup_candidate`'s lookback (`max(12, recent * 6)`, `ict-scan.py:466`) and the scan
window per timeframe (`automation.SCAN_WINDOW`).

One parameter is deliberately NOT taken from live, because live has no counterpart: `P[tf]["K"]`, the number of
bars a resting LIMIT order is given to fill. Live places the order and `strategy-runner.py` manages it per tick;
`ict-scan.py` has no such parameter. This is not a fork where live disagrees — it is a parameter only a backtest
needs.

## Superseded

Every report in `docs/backtests/` dated before 2026-09-13 was produced by the legacy engine. Their ICT figures
describe rules nothing runs any more. Their Wyckoff / COMBINED / PARTIAL figures are unaffected, per the
"surgical" section above.

## Open: the pilot still builds ICT setups the old way

`scripts/strategy-runner.py` calls `bt.all_pivots` / `bt.find_ict` directly and never reads `bt.OPTS["rules"]`,
so it constructs ICT setups with the legacy algorithm even though the backtest that is supposed to validate it
now runs the live one. Measured on the same 3,000-bar BTCUSDT 15m window: ICT live 2 trades, legacy 30.
`docs/architecture/pilot-top5.json` selects six ICT setups.

The pilot layer is off behind three locks (`/automation` master switch, `layers.pilot`, and the STOP files) and
must stay off for those six setups until `strategy-runner.py` is migrated. This is Task 8 of the plan, and
`scripts/tests/test_strategy_runner.py::IctParityIsKnownBroken` pins the gap so it cannot be forgotten.
