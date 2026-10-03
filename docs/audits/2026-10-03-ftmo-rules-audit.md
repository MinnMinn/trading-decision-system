# FTMO rules audit (2026-10-03)

Owner request 2026-10-03: "Nguyên nhân không để lệnh qua đêm là do ... để qua đêm sẽ bị tính phí cao. ... Thẩm định lại toàn bộ
rules để chắc chắn rằng mày không nhầm lẫn gì." Sources: the broker's own MT5 symbol specification exported from FTMO-Demo
(`data/history/costs/ftmo/symbolspec.*.json`, the cost profile `ftmo_demo_2026_09_relspread` every edge family uses) and
third-party summaries of FTMO's rules found by web search (ftmo.com itself is blocked by this environment's network proxy;
verify on ftmo.com/en/trading-objectives before a paid challenge).

## 1. Rules: what the simulations assume vs what FTMO states (2-Step CFD challenge)

| rule | FTMO (sources below) | simulations (fvg_book_sim / book_sim / pass_policy) | verdict |
|---|---|---|---|
| Phase 1 target | +10 % | +10 % | correct |
| Phase 2 target | +5 % | +5 %, starts the day after Phase 1 | correct |
| max loss | 10 % of the initial balance, static, incl. floating | 10 %, static; realised only (v1 run) | **floating was missing** -> fixed (A1) |
| max daily loss | 5 % of the INITIAL balance, closed + FLOATING, resets midnight CE(S)T | 5 %, realised only, bucketed by broker server day | **floating missing** -> fixed (A1); day boundary off by 1 h (server = CE(S)T + 1) -- immaterial for flat-before-rollover trades |
| minimum trading days | 4 per phase | 4 per phase (UTC entry date) | correct |
| time limit | none | none | correct |
| best-day / consistency rule | 1-Step only (50 %); none on 2-Step | none | correct for 2-Step (1-Step NOT modelled -- different product) |
| overnight / weekend holding | ALLOWED in Challenge + Verification (Standard and Swing). Funded Standard: close before the weekend and before rollover breaks > 2 h; Swing: no restriction | not a rule in the code -- every component is flat before the rollover BY DESIGN | **the intraday-only choice was a research design, not an FTMO rule** |
| news | Challenge: no restriction; funded Standard: selected high-impact news restricted; Swing: none | platform policy blocks new entries 10 min either side of HIGH news (CLAUDE.md §24, stricter) | conservative, keep |
| commission (metals, indices) | none | none | correct |
| risk per trade | no FTMO cap | 1 % platform ceiling | platform rule, keep |

## 2. Swap (the overnight charge) -- real FTMO-Demo numbers

| symbol | price_ref | swap_long (points) | long, bp per night | swap_short (points) | short, bp per night | triple-swap night | long held a whole year |
|---|---|---|---|---|---|---|---|
| XAUUSD | 2,471.98 | -83.0 | -3.36 | -8.3 | -0.34 | Wed | -12.3 % |
| XAGUSD | 29.73 | -19.25 | -6.47 | 0.7 | +0.24 | Wed | -23.6 % |
| US500 | 5,488.65 | -172.84 | -3.15 | 7.33 | +0.13 | Fri | -11.5 % |
| US30 | 40,115.30 | -1160.42 | -2.89 | 56.93 | +0.14 | Fri | -10.6 % |
| USTEC | 19,391.85 | -675.12 | -3.48 | 20.47 | +0.11 | Fri | -12.7 % |
| DE40 | 18,528.03 | -453.26 | -2.45 | -4.58 | -0.02 | Fri | -8.9 % |
| FRA40 | 7,355.27 | -145.15 | -1.97 | -1.47 | -0.02 | Fri | -7.2 % |
| AUS200 | 7,773.00 | -220.55 | -2.84 | 14.8 | +0.19 | Fri | -10.4 % |

Points x point size / price_ref. Long swaps are a real carry cost (~2-6.5 bp per night, three nights on the triple day); short
swaps are near zero or a small credit. Per TRADE at 1 % risk with the book's stops (gold ~125-175 bp), one long night costs
~0.02-0.03 R and the triple night ~0.07-0.08 R.

## 3. Was "holding overnight is expensive" right?

- Partly. For the INTRADAY edges found (+0.03-0.05 R per trade), one long night would eat roughly half the edge, so flat
  before the rollover is the right design for THOSE rules.
- But it is not an FTMO restriction, and for a multi-day trade (targets of several R) 0.03 R per night is small. Multi-day
  holding was tested only once (F4 G1 time-series momentum): its GROSS edge was ~0-8 bp per night before any cost, so swap was
  not what killed it.
- Consequence: multi-day holding of the rules that DO work (H7 / G9 gold trend) has never been measured. That is a gap, now a
  pre-registered next test (extend the hold by 1-3 server days, swap charged).

## 4. Impact on v1 / v2 (floating P&L re-run, docs/audits/2026-10-03-pass-policy-floating.json)

| | funded <= 122 d (confirmation starts) | first-attempt fail (confirmation) | bootstrap funded <= 122 d / fail | bootstrap -50 % edge |
|---|---|---|---|---|
| v1 base3 @1 %, realised -> floating | 0.226 -> 0.226 | 0.000 -> 0.009 | 0.097 / 0.059 -> 0.097 / 0.075 | 0.050 / 0.176 -> 0.050 / 0.207 |
| v2 base3+G9 gold @1 % dd3, realised -> floating | 0.357 -> 0.357 | 0.000 -> 0.000 | 0.217 / 0.010 -> 0.217 / 0.011 | 0.127 / 0.060 -> 0.127 / 0.067 |

Same chosen policy under both. The v2 decision stands; fails move by at most a few points (the floating bound is an upper
bound: every open position assumed at its own worst point simultaneously).

## Sources

- FTMO rules summaries (search 2026-10-03): propfirmatlas.io/guides/ftmo-challenge-rules-guide, jptradingcapital.com/blog/en/ftmo-rules,
  edgeflo.com/blog/ftmo-rules, tradetanto.com/learn/ftmo-rules-evaluation-process, propfirmbriefing.com/prop-firm-rules/ftmo,
  ftmo.com/en/faq/do-i-have-to-close-my-positions-overnight-or-before-the-weekend (title only), propvator.com/blog/ftmo-trading-conditions.
- Swap: FTMO-Demo MT5 symbol specifications (repo), swap_mode 1 (points).
