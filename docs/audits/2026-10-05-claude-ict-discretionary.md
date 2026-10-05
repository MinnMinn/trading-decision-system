# Can Claude trade ICT discretionarily with an edge? Result: FAIL (2026-10-05)

Pre-registration `docs/plans/2026-10-04-claude-ict-discretionary-preregistration.md` (7f2b142, written by the session
"Khám phá hệ thống FTMO" before any decision), amendments 1 and 2 (`docs/plans/2026-10-05-claude-ict-amendment-1.md`,
`-2.md`), implementation `docs/plans/2026-10-04-claude-ict-implementation.md`. Raw: `docs/experiments/claude-ict/`
(`decisions.jsonl`, `evaluation.json`, `post-evaluation.json`). Ledger: `research-ledger.json` `claude_ict`.

**Plain answer.** On 338 killzone decisions in July-October 2026 (after the model's training cutoff, so it could not
remember the prices), Claude Opus 5.5 reading the repo's ICT knowledge base did not show an edge. Its 158 filled trades
lost a little after cost (mean -0.05 R). It did no better than the same trades with the direction shuffled at random.
This is one window of three months: it rules out a large edge, not a small one.

## 1. What ran

- **Arm C:** 338 decision points (XAUUSD London / NY AM, US500 London / NY AM / NY PM; 68 weekdays, 2 US500 days without
  data). Each decision was one isolated process: `claude -p --safe-mode --tools "" ... --model claude-opus-5-5 --effort
  high`, no tool, no repository, no web, no earlier outcome. Input: closed 4H / 1H / 15m / 5m bars before the killzone
  open, the day / week / Asia levels and the spread. Output: strict JSON.
- **Run integrity:** 338 of 338 answered by the pinned model in one turn; 0 technical failures, 0 retries; one usage-limit
  pause (the interrupted call was asked again; no stored decision was regenerated); the log was committed before the
  evaluator's first and only run (`60f7561`, then `88f34aa`). The evaluator is the blob frozen at the start commit
  `873672c`. Reported cost 55.11 USD.
- **Fills:** the live rule (a buy limit fills when ASK <= entry), stop first when one bar touches both, flat at 16:00 ET.

## 2. The verdict

| condition (all needed for PASS) | result |
|---|---|
| at least 60 filled trades | 158: met |
| primary test (pre-registration §6): C vs within-instrument shuffles of its directions, p < 0.05 | **p = 0.418: failed** |
| mirror-order test (amendment 1), p < 0.05 | **p = 0.104: failed** |
| C's mean net R > 0 | **-0.052 R (bootstrap 95 %: -0.276 .. +0.184): failed** |
| C beats arm M | M had 1 filled trade (+0.057 R): not met (and M is too thin to mean much) |

**FAIL.** Two independent tests fail and the mean is negative.

**Amendment 2 §1 check (the primary test is biased by order kind).** C's book is almost all LIMIT orders (153 of 158
filled; 5 stop). The primary test is biased IN FAVOUR of a limit book (it over-rejects under random directions,
amendment 1), and it still found nothing (p = 0.42). The "stop book failed unfairly" caveat does not apply.

| filled trades | n | mean R of C | mean R of the opposite trade at C's fill | C minus opposite |
|---|---|---|---|---|
| XAUUSD limit | 67 | +0.057 | -0.187 | +0.244 |
| XAUUSD stop | 3 | -0.986 | +0.994 | -1.980 |
| US500 limit | 86 | -0.110 | -0.035 | -0.074 |
| US500 stop | 2 | +0.151 | +0.308 | -0.157 |
| all | 158 | -0.052 | -0.076 | +0.023 |

## 3. What the numbers look like

- 70 NO_TRADE answers (21 % of valid answers), 4 invalid answers (2 reasoning over 120 words, 2 extra keys), 264 orders,
  158 filled (fill rate 60 %).
- Filled trades: win rate 31 %, profit factor 0.92, median -0.95 R (most trades lose about 1 R; a third reach the target),
  total -8.3 R, max drawdown 17.6 R. Exits: 106 stop, 33 target, 19 time.
- By instrument: XAUUSD +0.012 R (n 70, PF 1.02); US500 -0.104 R (n 88, PF 0.83).
- By killzone (descriptive, five subgroups, not tested):

| killzone | filled | mean R | win rate | PF |
|---|---|---|---|---|
| XAUUSD London | 35 | -0.383 | 0.17 | 0.53 |
| XAUUSD New York AM | 35 | +0.408 | 0.40 | 1.69 |
| US500 London | 25 | +0.175 | 0.32 | 1.27 |
| US500 New York AM | 32 | -0.138 | 0.25 | 0.80 |
| US500 New York PM | 31 | -0.294 | 0.42 | 0.46 |

  XAUUSD New York AM looks good (+0.41 R on 35 trades), but it is the best of five cells found after the fact, with a
  standard error near 0.25 R. It is a hypothesis for a forward test at most, not a finding.
- Cost (amendment 2 §3): with the spread doubled, C's mean falls to -0.085 R (XAUUSD +0.012, US500 -0.163). The cost
  model (median spread, no measured commission) does not hide an edge; a worse cost only deepens the loss.
- Arm M (the repo's mechanical ICT rules, 15m pilot settings): 1 filled trade in the window; its 15m series ends
  2026-09-28 17:00Z for US500 (13 decision points not scannable) and 2026-10-01 02:00Z for XAUUSD (4) (amendment 2 §2).
  "C beats M" is formally not met; with one M trade it says nothing either way.
- Arm T (report-only, the demo book's H7 + G9 on XAUUSD): v3 +0.009 R on 85 trades; v4 -0.009 R on 85. Neither the
  model nor the trend book made money in this quiet window; C was 0.04-0.06 R per trade worse than T.

## 4. Threats and what the result does and does not say

- **One window, three months, one regime.** A FAIL here says "no large edge in this window". The 95 % interval still
  includes +0.18 R per trade. It does not prove that no prompt, model or process could trade ICT.
- **One prompt, one model, one effort level, run once.** That was the design (§7): a different prompt is a different
  hypothesis and would need its own pre-registration on new data.
- **The training cutoff is the platform's statement,** not verified here. If the model had remembered the path, the result
  would be biased toward a PASS, and it failed anyway.
- **Arm M and T are in-sample** for this window (their rules were built on overlapping data); C is not.

## 5. Consequence for the project

- ADR 0009 (no model reading on the live decision path) stands. This experiment produced no evidence to reopen it.
- No forward demo test of discretionary Claude-ICT is proposed. If the owner wants one anyway, the only candidate cell
  is XAUUSD New York AM, labelled post hoc, forward-only, under its own pre-registration.
