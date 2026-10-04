# Personal account -- first read (2026-10-04)

**DESCRIPTIVE.** Design: docs/plans/2026-10-04-personal-account-backtest-design.md (v2, A1-A11, owner decisions §7). Script:
`scripts/research/personal_account.py` at commit b4961c9. Raw data: docs/audits/2026-10-04-personal-account.json.

Setup:
- B0 = 5,000 USD (the owner's) and 100,000 USD (reference), r in {0.5 %, 1 %}.
- Mode `skip` (the owner's rule: never above r) and `floor` (minimum lot whatever its risk; sensitivity only).
- Lots at the 2026-09-30 prices; FTMO-Demo specs and costs as proxy.
- Historical paths, plus 1,000 bootstrap paths of 5 years (1,305 weekdays), sampled from the post-discovery days
  2018-02-26 -> 2026-10-02, the same days for every setup.
- Edge x {1, 0.5, 0}, with the haircut mean taken on the sampled span.

Labels:
- H7 / G9 gold and G9 silver are COMPONENT-VALIDATED.
- v3 / v4 are POLICY-EXPOSED.
- v4 + silver is UNTESTED.

**BLOWN never happened** in any cell: under "never above 1 %" an account cannot lose all its money. Risk shows up as
drawdowns and as STALLED instead.

## 1. The answer for 5,000 USD at 1 % (mode `skip`, the owner's rule)

5-year bootstrap at edge x 1 / x 0.5 / x 0:

| setup | median multiple (x1 / x0.5 / x0) | P(DD >= 25 %) at x0.5 | p95 max DD at x0.5 | STALLED at x0.5 |
|---|---|---|---|---|
| v4 (H7 + G9 gold, stop 1.4) | 1.65 / 0.90 / 0.65 | 48 % | 42 % | 3.6 % |
| v3 (stop 2.0) | 0.98 / 0.89 / 0.82 | 5 % | 26 % | 12.9 % |
| H7 gold alone | 1.02 / 0.99 / 0.96 | 0 % | 12 % | 5.2 % |
| G9 gold alone | 0.96 / 0.88 / 0.82 | 3 % | 24 % | 7.7 % |
| G9 silver alone | 0.95 / 0.94 / 0.92 | 0 % | 13 % | 33 % |
| v4 + silver | 1.36 / 0.82 / 0.63 | 66 % | 43 % | 9.5 % |

Historical, 2018-02 -> 2026-10:
- v4 on 5,000 USD: x4.0 (17.5 %/yr), max drawdown 12.5 %, 6 % of signals skipped.
- v3: x1.13, with 72 % of signals skipped.
- H7 / G9 separately: about flat, with 71-74 % of signals skipped.

At 100,000 USD (same rule) the same edge gives v4 x3.52 / x1.80 / x0.93, and v3 x2.38 / x1.50 / x0.95.

## 2. Why 5,000 USD loses most of the edge: the minimum lot meets the volatility of the edge

1. **The minimum lot is large for 5,000 USD.** It is 0.01 lot (1 oz gold, 50 oz silver), and its loss at the median stop
   since 2024 is $64 / $59 (H7 / G9 at stop 2.0), $45 / $41 (at 1.4) and $88 (silver). At 1 % of 5,000 USD = $50, every
   trade whose minimum lot risks more than $50 is skipped.
2. **The skipped trades are the wide-stop, high-volatility days.** The edge lives on exactly those days. Mean R by
   stop-width quartile since 2018, narrowest to widest:

   | component | Q1 | Q2 | Q3 | Q4 |
   |---|---|---|---|---|
   | G9 gold (stop 1.4) | -0.02 | +0.01 | +0.12 | +0.29 |
   | G9 gold (stop 2.0) | -0.02 | +0.02 | +0.08 | +0.20 |
   | G9 silver | -0.08 | +0.05 | +0.05 | +0.17 |
   | H7 gold | +0.04 to +0.05 | | | +0.07 to +0.10 |

   The rule therefore keeps the near-zero-edge trades and drops the profitable ones. That is why v3 and the single
   components are flat at 5,000 USD and positive at 100,000 USD.
3. **Mode `floor` shows the cost of the rule.** It trades the minimum lot even above 1 %, so on 5,000 USD it risks about
   0.8-1.8 % on wide-stop days. Its 5-year medians are v4 x3.19 / x2.02 / x1.35 and v3 x2.83 / x2.09 / x1.49, with P(DD >=
   25 %) 6 % (v4, x0.5) and still no BLOWN. That mode breaks the owner's 1 % rule. It is shown, not proposed.

## 3. Ranking (design §4; survival at edge x 0.5, then median CAGR)

- **5,000 USD, `skip`:** every setup survives. Its best r is 0.5 %, because at 1 % the medians are negative at half edge. But
  at 0.5 % most signals are too small to place (STALLED 30-70 %), so the "best" is close to not trading. **At this size,
  with the 1 % rule, no setup gives a robust positive result.**
- **100,000 USD, `skip`:** v4 ranks first (POLICY-EXPOSED); within COMPONENT-VALIDATED the order is H7, G9 gold, G9 silver
  (no paired win >= 80 %, so the p95 drawdown decides). This is in line with the FTMO work.

## 4. What this means (owner decisions, not taken here)

1. **At 5,000 USD the 1 % rule and the gold minimum lot conflict.** The options:
   - **(a)** a larger personal account: from about 10-15k the minimum lot binds rarely at 1 %;
   - **(b)** a risk ceiling above 1 % only for the minimum lot (e.g. <= 2 %). This is mode `floor` with a cap; it was not
     run, and it is the owner's call;
   - **(c)** a broker with smaller contract units (micro / cent).
2. **A research lead, not evidence:** the H7 / G9 edge is concentrated on high-volatility days. A pre-registered test of a
   volatility condition (trade only above the median stop width) on the FTMO book is the natural next step. It was found
   post hoc, on exposed data.
