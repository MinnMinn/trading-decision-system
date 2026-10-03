# A1 -- phase-aware volatility through the stop width -- pre-registration (DRAFT, 2026-10-03)

**Status: DRAFT, not run.** Runs only after the owner's decision on E5 (docs/audits/2026-10-03-e5-lookahead-erratum.md §5),
because that decision fixes the base book. **DESCRIPTIVE / EXPOSED** by construction: every trade sequence used here was
already read. Agreed with the session "Khám phá hệ thống FTMO" (reframes §9): a stop-width change is a NEW setup version that
needs its own evidence; this study is design evidence, judged by the value objective, labelled "variance, not edge" wherever
that is where the gain comes from.

## 1. Question

At the base's own (point-in-time) edge, does running the book closer to its speed-optimal volatility -- through a tighter
protective stop at the SAME 1 % worst case per trade, separately in Phase 1 and Phase 2 -- raise the expected net value of a
challenge (E[payouts over 12 months] - E[fees]) at the measured edge AND at a 50 % haircut, without breaking FTMO's limits?

## 2. Policies (6, fixed now)

- Base book: the point-in-time base the owner chooses (v3 = H7 + G9 gold, or v2 with E5 under the demo's selection). Trade
  mechanics as `book_sim.trades`, except the protective stop distance = k x sigma_5m x sqrt(hold) x price; sizing 1 % of the
  initial balance AT the stop (never above `risk-config.json` max_risk_pct); dd3 throttle unchanged; flat before the rollover.
- Grid: k_P1 in {2.0 (today), 1.4} x k_P2 in {2.0, 1.4, 1.0}. Reference = (2.0, 2.0).

## 3. Measurement

1. `pass_policy` protocol unchanged: selection starts < 2024, confirmation starts >= 2024, stationary block bootstrap (mean
   block 20 weekdays, 3000 paths, seed 20261002) at the edge as measured and with a 50 % haircut; FLOATING P&L as FTMO counts
   it (`mae`) and realised.
2. Value objective on the same bootstrap paths: a challenge -> funded-stage replay of 12 months (monthly payout of `split`
   x profit above the initial balance, balance reset; the account ends at the first -5 % day or -10 % total, floating
   included); E[net] = E[payouts] - E[fees] with a new fee for every retry within the horizon. Owner inputs are NAMED
   parameters with stated defaults, not facts: fee = 0.6 % of the balance (EUR 540 on 100k), split = 0.80, payout monthly,
   fee refunded with the first payout. The study reports the result for every edge multiple in {1, 0.5, 0}.
3. Tails: share of trades whose realised loss exceeds 1R (gap through the stop, `mae_R < -1`) and the worst single-trade loss
   in % of the initial balance, per k.

## 4. Decision rule (fixed now)

A policy is PROPOSED to the owner iff, against the reference: Delta E[net] > 0 at the 50 % haircut in the bootstrap, AND
first-attempt fail <= 10 % in the confirmation starts and in the haircut bootstrap (floating), AND the worst single-trade loss
<= 1.2 % of the initial balance (gap tolerance). If its Delta E[net] at edge x 0 is also > 0, the proposal must say that the
gain is variance, not edge. Zero proposals is a valid result. Experiment budget: 6 policies on exposed data.
