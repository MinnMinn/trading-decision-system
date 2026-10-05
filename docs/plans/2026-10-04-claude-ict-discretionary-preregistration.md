# Pre-registration: can Claude trade ICT discretionarily with an edge? (2026-10-04)

**Owner request (2026-10-04):** "Vậy mày có thể trở thành một trader ICT giỏi không?" → after the answer "unknown, it
must be measured": "Đồng ý, làm đi."

**Status:** pre-registered BEFORE any decision is generated. Research only. Nothing here touches the live order path,
`accounts.json`, `risk-config.json` or `instruments.json`. ADR 0009 rejected deciding from a model's reading on the live
path (non-deterministic, not backtestable, LLM on the hot path, §40); this experiment does not reopen that decision. It
produces the NEW evidence that §53 would require before anyone may propose reopening it.

## 1. Hypothesis

H1: a Claude model applying the ICT knowledge base (knowledge/ict/*.md, knowledge/integrated/method.md, the ict-skill)
to point-in-time price data makes intraday trade decisions whose net expectancy per trade is positive and better than
(a) a random-timing/random-direction control with the same trade structure, and (b) the mechanical ICT rules already in
the repo, on data the model cannot have seen.

H0: no difference from the random control (expectancy ≤ control after costs).

"Unknown" is a valid outcome: too few trades (§6) is reported as INSUFFICIENT, not as a pass or a fail.

## 2. Data -- chosen so the model cannot know the answer

- **Primary window: 2026-07-01 00:00 UTC → 2026-10-02 20:45 UTC**, FTMO-Demo 5m history in `data/history/ftmo/`
  (XAUUSD and US500; both verified to cover the window on 2026-10-04). The model's training cutoff is June 2026, so the
  price path of this window is not in its weights. This is the reason for the window, and the reason it is short.
- **No secondary window** is read for the verdict. A pre-cutoff window would leak through memorised history (the model
  may know what gold did in 2024-25); date anonymisation and price mirroring reduce but do not remove that, so it is
  excluded from the verdict. It may be run afterwards as an explicitly EXPOSED, descriptive check only.
- Higher timeframes (15m, 1H, 4H, 1D) are built from the same 5m bars by the harness, closed bars only.

## 3. Decision protocol (what the model sees and must output)

**Decision points**, from the knowledge base's own killzones (knowledge/ict/core-a.md §2.1, `1. Killzones p3`), ET with
DST via `zoneinfo`:
- XAUUSD (forex set): London 02:00-05:00, New York AM 07:00-10:00.
- US500 (indices set): London 02:00-05:00, New York AM 08:30-11:00, New York PM 13:30-16:00.

One decision per (instrument, killzone, trading day), made at the killzone's OPEN. About 65 trading days × 5
killzones ≈ 325 decisions. Days with no data in the killzone are skipped and counted.

**Input**, point-in-time, closed bars only, all strictly before the killzone open:
- 4H and 1H: last 60 bars; 15m: last 96 bars; 5m: last 48 bars. Given as numeric OHLC tables with UTC timestamps.
- Previous day's high/low, the week-to-date high/low, and the Asia-session high/low (20:00-00:00 ET) computed by code.
- The instrument name and the current spread snapshot (`data/history/costs/ftmo`), so cost is part of the decision.
- No news, no hindsight, no repository access, no indicator the knowledge base does not define, no outcome of earlier
  decisions (each decision is independent, so a lucky streak cannot steer later ones).

**Output** (strict JSON, validated; an invalid answer = NO_TRADE and is counted as an error):
```
{ "decision": "NO_TRADE" | "LONG" | "SHORT",
  "order": "limit" | "stop" | "market",
  "entry": price, "stop": price, "target": price,
  "valid_until": "killzone_end",
  "htf_bias": "bullish" | "bearish" | "neutral",
  "draw_on_liquidity": "<level and what it is>",
  "pd_array": "<the FVG / OB / breaker used, with its bars>",
  "invalidation": "<what would make the idea wrong>",
  "reasoning": "<= 120 words, ICT vocabulary only" }
```
`stop` must be on the losing side of `entry`, and `target` on the winning side, with reward/risk ≥ 1.0. Otherwise the
answer is invalid. No confidence percentage (§18).

**Isolation.** Each decision is a fresh model call (a subagent with no tools other than reading its prompt). The harness
that builds prompts and the evaluator that scores outcomes are separate code paths. Every decision is appended to
`docs/experiments/claude-ict/decisions.jsonl` with a sha256 of its prompt, and that file is COMMITTED before the
evaluator is run for the first time. Model id and date are recorded (§46). The run is done ONCE; a decision that failed
technically (timeout, invalid JSON) may be retried once, and the retry is logged. Re-running to get a better sample is
forbidden.

## 4. Execution simulation (deterministic code, identical for every arm)

- Fills on the bid/ask built from the bid bars plus the snapshot spread: a buy limit fills when ASK ≤ entry; a sell limit
  fills when BID ≥ entry; a stop order fills at the first trade through; a market order fills at the next bar's open.
  This is the live-fill rule, so the E5 look-ahead lesson (docs/audits/2026-10-03-e5-lookahead-erratum.md) does not
  repeat.
- An unfilled order expires at killzone end.
- After a fill: stop and target are resting. If both are touched inside one 5m bar, **the stop is assumed first**
  (conservative).
- Time exit at 16:00 ET, flat before the 17:00 ET FTMO rollover. No overnight holding.
- R = net P&L / (|entry − stop| + spread).

## 5. Comparison arms (on the same window and instruments)

| Arm | What | Why |
|---|---|---|
| C — Claude | §3 decisions | the hypothesis |
| R — random control | same filled-trade times, same stop distance and same reward/risk as C's trades, direction random; 2,000 permutations | isolates whether C's DIRECTION and LOCATION carry information beyond trade structure and timing |
| M — mechanical ICT | the repo's ICT rules (`scripts/backtest-methods.py`, ICT preset, the pilot's 15m settings) | does reading beat the written rules? |
| T — H7/G9 | the current live book v3 on XAUUSD | the bar to clear for being useful to the FTMO goal |

## 6. Verdict rules (fixed now)

- Minimum sample: **≥ 60 filled trades** in arm C. Fewer → **INSUFFICIENT**, reported with the numbers, no verdict.
- **Primary test:** C's mean net R vs the R-control permutation distribution, one-sided, **p < 0.05**.
- **PASS** only if all hold: primary test passes; C's mean net R > 0 with the 95% bootstrap lower bound reported; C beats M
  on mean net R. The comparison with T is reported but does not gate.
- **FAIL** if the primary test does not pass with ≥ 60 trades.
- Reported regardless: trade count, fill rate, win rate, mean R, profit factor, max drawdown in R, per instrument and per
  killzone, the NO_TRADE rate, invalid-answer count, and a sample of 10 decisions with reasoning, chosen by a seeded random
  draw (not hand-picked).
- A PASS is evidence for a forward demo test, not for live use. Any live use would need a new ADR (ADR 0009) and a new
  pre-registration.

## 7. Threats to validity, stated in advance

- **One window, about 3 months, one regime.** Even a PASS is weak evidence. It says "worth a longer forward test", not
  "proven".
- **Model non-determinism:** a re-run would give different decisions. That is why the run is done once and committed.
- **Training-data leakage** is excluded by the window choice (§2), not by trust.
- **Prompt sensitivity:** the prompt template is committed together with this pre-registration's implementation, before
  the run. No prompt change after the first decision is generated.
- **Cost:** about 325 full model calls. Accepted.
- **Experiment budget:** this is one hypothesis, one family. It is recorded in the research ledger.

## 8. Ownership

Implementation and run: session "Challenging the system" (branch `claude/challenging-the-system`), on the owner's
instruction relayed 2026-10-04. Review: session "Khám phá hệ thống FTMO".
