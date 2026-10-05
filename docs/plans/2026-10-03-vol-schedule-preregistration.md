# A1 -- phase-aware volatility through the stop width -- pre-registration (2026-10-03)

**Status: FINAL (2026-10-03), committed before the run.** The owner's decisions (docs/plans/2026-09-30-owner-decisions.md,
2026-10-03 evening) fixed the base -- v3 = H7 + G9 XAUUSD -- and the meaning of the risk rule: 1 % = the maximum loss AT THE
STOP, so a tighter stop at the same 1 % is inside the rule. The owner does not know an exchange rate between a month of delay
and a fee; the value objective below prices time endogenously (a faster pass earns more funded months inside a fixed horizon). **DESCRIPTIVE / EXPOSED** by construction: every trade sequence used here was
already read. Agreed with the session "Khám phá hệ thống FTMO" (reframes §9): a stop-width change is a NEW setup version that
needs its own evidence; this study is design evidence, judged by the value objective, labelled "variance, not edge" wherever
that is where the gain comes from.

## 1. Question

At the base's own (point-in-time) edge, does running the book closer to its speed-optimal volatility -- through a tighter
protective stop at the SAME 1 % worst case per trade, separately in Phase 1 and Phase 2 -- raise the expected net value of a
challenge (E[payouts over 12 months] - E[fees]) at the measured edge AND at a 50 % haircut, without breaking FTMO's limits?

## 2. Policies (6, fixed now)

- Base book: v3 = H7 + G9 XAUUSD (point-in-time detectors, unchanged). Span: every stored XAUUSD bar (2004 ->), because v3 no
  longer needs the 2021+ US500 span. Trade
  mechanics as `book_sim.trades`, except the protective stop distance = k x sigma_5m x sqrt(hold) x price; sizing 1 % of the
  initial balance AT the stop (never above `risk-config.json` max_risk_pct); dd3 throttle unchanged; flat before the rollover.
- Grid: k_P1 in {2.0 (today), 1.4} x k_P2 in {2.0, 1.4, 1.0}. Reference = (2.0, 2.0).

## 3. Measurement

1. `pass_policy` protocol unchanged: selection starts < 2024, confirmation starts >= 2024, stationary block bootstrap (mean
   block 20 weekdays, 3000 paths, seed 20261002) at the edge as measured and with a 50 % haircut; FLOATING P&L as FTMO counts
   it (`mae`) and realised.
2. Value objective on the same bootstrap paths, inside a fixed HORIZON of 252 weekdays from the challenge start: challenge
   attempts (retry the weekday after a fail, a new fee each) until funded or the horizon ends; then the FUNDED stage until the
   horizon ends, always at the reference stop k = 2.0 with dd3 (only the challenge lever varies); a funded breach ends the
   account (no new challenge after it inside the horizon). Funded-stage replay (monthly payout of `split`
   x profit above the initial balance, balance reset; the account ends at the first -5 % day or -10 % total, floating
   included); E[net] = E[payouts] - E[fees] with a new fee for every retry within the horizon. Owner inputs are NAMED
   parameters with stated defaults, not facts: fee = 0.6 % of the balance (EUR 540 on 100k), split = 0.80, payout monthly,
   fee refunded with the first payout. The study reports the result for every edge multiple in {1, 0.5, 0}.
3. Tails: share of trades whose realised loss exceeds 1R (gap through the stop, `mae_R < -1`) and the worst single-trade loss
   in % of the initial balance, per k.

## 4. Decision rule (fixed now)

Bootstrap for phase-specific k: weekdays are resampled ONCE per path (stationary blocks, mean 20, 3000 paths, seed 20261002)
and every k's trade list is replayed on the SAME sampled days, so policies differ only by the stop. Selection / confirmation
starts: Mondays before / from 2024-01-01 on the historical sequence.

A policy is PROPOSED to the owner iff, against the reference: Delta E[net] > 0 at the 50 % haircut in the bootstrap, AND
first-attempt fail <= 10 % in the confirmation starts and in the haircut bootstrap (floating), AND the worst single-trade loss
<= 1.2 % of the initial balance (gap tolerance). If its Delta E[net] at edge x 0 is also > 0, the proposal must say that the
gain is variance, not edge. Zero proposals is a valid result. Experiment budget: 6 policies on exposed data.
