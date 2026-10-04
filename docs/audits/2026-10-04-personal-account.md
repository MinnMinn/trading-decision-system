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

**BLOWN never happened** in any `skip` cell: under "never above 1 %" an account cannot lose all its money. Risk shows up
as drawdowns and STALLED. (Corrected: `floor` had one, v4 + silver at edge x 0, 1 path in 1,000 at each r; see §5.1.)

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
     run in this first read (the owner chose it: §5), and it is the owner's call;
   - **(c)** a broker with smaller contract units (micro / cent).
2. **A research lead, not evidence:** the H7 / G9 edge is concentrated on high-volatility days. A pre-registered test of a
   volatility condition (trade only above the median stop width) on the FTMO book is the natural next step. It was found
   post hoc, on exposed data.

## 5. Minimum lot up to 2 % (owner 2026-10-04)

Owner 2026-10-04: "Cho phép vào lot nhỏ nhất dù vượt 1%, có giới hạn trên (ví dụ: 2% với tài khoản có số vốn 5000$)".
Design §7.4, A3 mode `floor_cap`.

**DESCRIPTIVE re-read of already-read days.** The rule was chosen AFTER §2.3 showed mode `floor` recovering the edge. These
numbers describe a sizing choice on exposed data (CLAUDE.md §44). They do not validate an edge.

Rule (`lots_for`, scripts/research/personal_account.py:110-122):
- Size at r = 1 % of the current balance, as before.
- If that is below the minimum lot (0.01), trade 0.01 only if its risk at the stop is <= the cap x the CURRENT balance.
- Otherwise skip (`min_lot_over_cap`). Such skips also count toward STALLED.
- "Risk at the stop" is the stop distance only, as for r. The spread comes on top (`cost_R`, scripts/research/book_sim.py:76,
  :80). Commission is 0 in this run, as in the first read.
- The owner's words also allowed a FIXED cap: 2 % of the starting 5,000 USD = 100 USD. That cap does not shrink as the
  balance falls, so it is looser after a drawdown. It was not run here. The owner chose it afterwards ("Trần 2% tính
  theo cố định 100 USD", 2026-10-04): §5.5. This section (§5.1-§5.3) is the current-balance reading.

Run: same rows, specs, seed, days and paths as §1-§3; r = 1 % only; B0 5,000 and 100,000; caps 2 % (the owner's
example) and 1.5 % (sensitivity); 108 cells. Raw data: docs/audits/2026-10-04-personal-account-cap.json.

    python3 scripts/research/personal_account.py run --out <json> --cache <rows.pkl> --paths 1000 --jobs 10 \
        --r 0.01 --b0 5000 100000 --mode skip floor_cap --cap 0.02 0.015

Code version (CLAUDE.md §46): the run used the uncommitted working copy on top of commit 9dfb31e, i.e. the code of the
commit that adds this section. The JSON meta has no commit field; later runs record one (`meta.code`,
personal_account.py `code_version`). The committed code reproduces the run:

    python3 scripts/research/personal_account.py check --cache <rows.pkl> \
        --against docs/audits/2026-10-04-personal-account.json --new docs/audits/2026-10-04-personal-account-cap.json
    python3 scripts/research/personal_account.py check --cache <rows.pkl> \
        --against docs/audits/2026-10-04-personal-account-cap.json

- All 96 first-read historical entries (`skip` and `floor`) and all 72 of this run replay exactly.
- The 60 entries both files share (the `skip` cells: 36 bootstrap, 24 historical) are equal.
- A reviewer re-ran 4 bootstrap cells over all 1,000 seeds (v4 cap 2 % at x0.5 and x0, silver cap 1.5 % at x0.5, v4
  `skip` at x0.5). All were equal.

Experiment budget on these days (CLAUDE.md §43):
- Read so far: 5 sizing rules (`skip`, `floor`, cap 2 %, cap 1.5 %, and the fixed 100 USD cap of §5.5) x 6 setups x 3
  edge levels. `skip` and `floor` at r 0.5 % and 1 % and B0 5,000 and 100,000; the two current-balance caps at r 1 % and
  both balances; the fixed cap at r 1 % and 5,000 only. That is 234 distinct bootstrap cells and 156 historical ones
  (216 / 144 before §5.5).
- The fixed cap is one more rule read on the same days. The owner chose its base (2026-10-04) before any fixed-cap number
  existed; the current-balance numbers above were known. It was not picked from results.
- Before them, two full runs were superseded: B0 10,000 / 100,000 (before the owner gave 5,000), and 5,000 / 100,000 with
  the haircut mean on the full history (fixed in b4961c9). There were also 20-path smoke runs of the same cells.
- 2 % is the owner's number, not a backtest optimum. No further cap values or bases should be read on these days.

### 5.1 Bootstrap, 5,000 USD at 1 % (5 years, 1,000 paths)

"above 1 %" = share of the trades taken whose risk at the stop was above 1 % of the balance. "mean risk" = the average
risk actually taken, in % of the balance. Both at edge x 0.5, pooled over all paths. `floor` rows are from the first read
(no cap; these two columns were not recorded then).

| setup | sizing | median multiple x1 / x0.5 / x0 | P(DD >= 25 %) x0.5 | p95 DD x0.5 | P(BLOWN) | STALLED x0.5 | above 1 % | mean risk |
|---|---|---|---|---|---|---|---|---|
| v4 | skip | 1.65 / 0.90 / 0.65 | 48 % | 42 % | 0 | 3.6 % | 0 % | 0.77 % |
| v4 | cap 1.5 % | 2.75 / 1.68 / 0.89 | 18 % | 36 % | 0 | 0 | 16 % | 0.84 % |
| v4 | **cap 2 %** | **3.05 / 1.87 / 1.25** | **9 %** | **27 %** | **0** | **0** | **15 %** | **0.85 %** |
| v4 | floor | 3.19 / 2.02 / 1.35 | 6 % | 26 % | 0 | 0 | n/r | n/r |
| v3 | skip | 0.98 / 0.89 / 0.82 | 5 % | 26 % | 0 | 12.9 % | 0 % | 0.80 % |
| v3 | cap 1.5 % | 1.82 / 0.99 / 0.65 | 43 % | 43 % | 0 | 2.7 % | 47 % | 1.00 % |
| v3 | cap 2 % | 2.43 / 1.68 / 0.83 | 18 % | 41 % | 0 | 0.2 % | 43 % | 1.03 % |
| v3 | floor | 2.83 / 2.09 / 1.49 | 3 % | 23 % | 0 | 0 | n/r | n/r |
| H7 gold | skip | 1.02 / 0.99 / 0.96 | 0 % | 12 % | 0 | 5.2 % | 0 % | 0.80 % |
| H7 gold | cap 1.5 % | 1.23 / 1.06 / 0.93 | 1 % | 20 % | 0 | 0.7 % | 56 % | 1.04 % |
| H7 gold | cap 2 % | 1.34 / 1.12 / 0.96 | 2 % | 22 % | 0 | 0 | 62 % | 1.15 % |
| H7 gold | floor | 1.51 / 1.27 / 1.04 | 2 % | 22 % | 0 | 0 | n/r | n/r |
| G9 gold | skip | 0.96 / 0.88 / 0.82 | 3 % | 24 % | 0 | 7.7 % | 0 % | 0.80 % |
| G9 gold | cap 1.5 % | 1.35 / 0.95 / 0.72 | 27 % | 35 % | 0 | 1.0 % | 47 % | 1.00 % |
| G9 gold | cap 2 % | 1.93 / 1.44 / 0.89 | 8 % | 28 % | 0 | 0.1 % | 45 % | 1.04 % |
| G9 gold | floor | 2.30 / 1.85 / 1.46 | 0 % | 17 % | 0 | 0 | n/r | n/r |
| G9 silver | skip | 0.95 / 0.94 / 0.92 | 0 % | 13 % | 0 | 33 % | 0 % | 0.85 % |
| G9 silver | cap 1.5 % | 0.80 / 0.75 / 0.71 | 69 % | 36 % | 0 | 13.1 % | 80 % | 1.18 % |
| G9 silver | cap 2 % | 1.24 / 0.92 / 0.71 | 44 % | 47 % | 0 | 3.7 % | 82 % | 1.36 % |
| G9 silver | floor | 2.53 / 2.15 / 1.77 | 10 % | 29 % | 0 | 0 | n/r | n/r |
| v4 + silver | skip | 1.36 / 0.82 / 0.63 | 66 % | 43 % | 0 | 9.5 % | 0 % | 0.78 % |
| v4 + silver | cap 1.5 % | 3.27 / 1.44 / 0.52 | 54 % | 54 % | 0 | 1.4 % | 30 % | 0.91 % |
| v4 + silver | cap 2 % | 4.20 / 2.14 / 0.86 | 41 % | 44 % | 0 | 0.2 % | 28 % | 0.94 % |
| v4 + silver | floor | 5.48 / 2.96 / 1.76 | 32 % | 36 % | 0.1 % | 0 | n/r | n/r |

P(BLOWN) is the highest over the three edge levels. The one non-zero value is `floor` for v4 + silver at edge x 0: one
path in 1,000, at r 0.5 % and at 1 % (first-read JSON; the intro is corrected). No `skip` or current-balance cap cell has
a BLOWN path (the fixed cap has, at edge x 0: §5.5).
Survival (design §4: P(BLOWN) <= 1 % and P(DD >= 50 %) <= 5 % at x0.5):
- every setup survives at cap 2 % (highest P(DD >= 50 %): v4 + silver, 2.6 %);
- at cap 1.5 %, v4 + silver fails (7.1 %).

Ranking at cap 2 % (paired CAGR, x0.5):
- v4 beats v3 on 79 % of paths: just under the 80 % bar, so v4 leads on the lower p95 drawdown;
- G9 gold beats silver on 89 % of paths and H7 on 78 %, so G9 gold leads its label.

### 5.2 Historical, 5,000 USD at 1 % (2018-02-26 -> 2026-10-02, full edge)

| setup | sizing | multiple | CAGR | max DD | taken / skipped | above 1 % | mean risk | STALLED |
|---|---|---|---|---|---|---|---|---|
| v4 | skip | 4.02 | 17.5 % | 12.5 % | 2,481 / 166 | 0 % | 0.8 % | - |
| v4 | cap 1.5 % | 5.44 | 21.8 % | 13.4 % | 2,636 / 11 | 2 % | 0.8 % | - |
| v4 | cap 2 % | 5.89 | 22.9 % | 13.1 % | 2,647 / 0 | 2 % | 0.9 % | - |
| v3 | skip | 1.13 | 1.5 % | 21.2 % | 749 / 1,898 | 0 % | 0.8 % | - |
| v3 | cap 2 % | 4.43 | 18.9 % | 11.3 % | 2,633 / 14 | 10 % | 0.9 % | - |
| H7 gold | skip | 1.06 | 0.7 % | 10.2 % | 284 / 812 | 0 % | 0.8 % | - |
| H7 gold | cap 2 % | 1.85 | 7.4 % | 7.1 % | 1,061 / 35 | 38 % | 1.0 % | - |
| G9 gold | skip | 0.91 | -1.1 % | 17.2 % | 445 / 1,106 | 0 % | 0.8 % | 2026-07-31 |
| G9 gold | cap 2 % | 3.17 | 14.4 % | 12.6 % | 1,540 / 11 | 14 % | 0.9 % | - |
| G9 silver | skip | 0.90 | -1.2 % | 12.3 % | 99 / 1,418 | 0 % | 0.8 % | 2026-07-31 |
| G9 silver | cap 1.5 % | 0.72 | -3.8 % | 34.2 % | 265 / 1,252 | 80 % | 1.2 % | 2026-08-12 |
| G9 silver | cap 2 % | 2.74 | 12.4 % | 21.0 % | 1,457 / 60 | 28 % | 0.9 % | - |
| v4 + silver | skip | 2.00 | 8.4 % | 24.0 % | 2,742 / 1,422 | 0 % | 0.8 % | - |
| v4 + silver | cap 2 % | 11.37 | 32.7 % | 18.9 % | 4,154 / 10 | 4 % | 0.9 % | - |

No BLOWN in any historical cell. v4 at cap 2 % equals mode `floor` exactly (x5.89): it never needed more than 2 %.
The other cap-1.5 % rows are in the JSON.

**At 100,000 USD** the caps change almost nothing. Every cell equals `skip` exactly, except v4 + silver at edge x 0: there a
few deep paths reach the minimum lot (about 120 more trades out of 2.4 million; same medians and drawdown probabilities).

### 5.3 What the numbers say

1. **Cap 2 % recovers most of what `floor` showed, with no BLOWN.** v4: median x1.87 at half edge (skip x0.90, floor
   x2.02), P(DD >= 25 %) 9 % (skip 48 %). Only 15 % of v4's trades go above 1 %; the mean risk is 0.85 %.
2. **The cap costs little for v4, more for the stop-2.0 setups.** v4's minimum lot at the median stop is $41-45 (0.8-0.9 %
   of 5,000), so 2 % almost never binds (no skip in the historical path). For v3 and the single components the cap
   still drops the widest stops, which carry the edge (§2.2). v3 at cap 2 % has a heavier tail (p95 DD 41 %) than both
   `skip` (26 %) and `floor` (23 %).
3. **Cap 1.5 % is a poor middle on these days.** At half edge every setup grows less at 1.5 % than at 2 %, and all but H7
   gold have a higher P(DD >= 25 %). For silver it is worse than `skip`: it takes the 1-1.5 % trades but still skips the
   wide ones. This does not make 2 % an optimum: 2 % is the owner's number, and 1.5 % is the only other value read. The
   response to the cap is not smooth:
   - silver's history goes from x0.72 at 1.5 % to x2.74 at 2 %;
   - the COMPONENT-VALIDATED leader flips. Under `skip` at r 1 %, H7 beats G9 gold on 93 % of paths. At cap 2 %, G9 gold
     beats H7 on 78 %.
4. **Silver does not fit 5,000 USD.** At cap 2 %, 82 % of its trades are above 1 %, the mean risk is 1.36 %, and the
   half-edge median is x0.92 with P(DD >= 25 %) 44 %.
5. **The edge levels do not mean the same thing under `skip` and under a cap.** The haircut subtracts one flat mean R per
   component (personal_account.py:301-309). It is paid in proportion to the money at risk (:168, :214). Mean R rises with
   stop width (§2.2). So:
   - `skip` drops the wide stops but pays the full haircut on the narrow ones it keeps. Its x0.5 and x0 are below half
     and zero edge on the trades it takes.
   - The caps put more than r on the wide stops. Their x0.5 and x0 are above it: v4 still shows x1.25 at "x0".
   - At every edge level, part of the gap between `skip` and the caps (v4 at x0.5: x0.90 against x1.87) is the post-hoc
     stop-width pattern of §4.2, not the sizing rule alone. No row here is a clean planning row.

### 5.4 Recommendation for 5,000 USD

- **If the owner trades a personal 5,000 USD account: v4 (H7 + G9 gold, stop 1.4), r = 1 %, minimum lot up to a fixed
  100 USD (the owner's rule, §5.5).** Half-edge median x1.79, P(DD >= 25 %) 8 %, p95 drawdown 27 %, no BLOWN or STALLED
  path at any edge level. It beats v3 on 98 % of paths (paired CAGR, half edge). H7 gold alone grows little (x1.09) at
  about the same p95 drawdown (26 %). Historically v4 took all but 33 signals, all skipped above 10,000 USD, where the
  fixed cap equals `skip`.
- **The current-balance cap of §5.1 grows v4 a little more** (x1.87 at half edge, x5.89 historically). The gap is the
  fixed cap's tighter side above 5,000 USD (§5.5 item 1). Picking the base again from these numbers would be a choice on
  exposed data (CLAUDE.md §43-44); the owner fixed it before they existed.
- **How much of that gain is real depends on the volatility-condition test** (family VC,
  docs/plans/2026-10-04-vc-volatility-condition-preregistration-DRAFT.md, not sealed). VC asks, on data where the split
  was never computed, whether mean R rises on volatile days: the pattern behind §5.3 item 5. If VC fails, read the cap
  rows here as optimistic and the `skip` rows as pessimistic: a cap takes wide-stop days that `skip` cuts. The fixed
  cap takes one only while its minimum lot risks <= 100 USD, and from 10,000 USD up it cuts them like `skip`
  (historical skips: v4 33, v3 313; §5.5).
- **Not:** silver alone (under the fixed cap it fails survival: P(DD >= 50 %) 7.2 % at half edge), or v4 + silver
  (UNTESTED, P(DD >= 25 %) 45 %, BLOWN paths at edge x 0). Silver's minimum lot is too large for 5,000 USD (§5.3 item 4).
- **Labels still apply.** v4 is POLICY-EXPOSED, and the cap rule was chosen after seeing `floor`. It is a CANDIDATE: a
  forward record on demo (or a small live size) should come first.
- **Before live use:** a personal-account risk config (the min lot above `risk-config.json` max_risk_pct = 1 %, up to a
  fixed 100 USD) and a book version with current-balance sizing and the fixed cap in the executor (CLAUDE.md §47).
  Neither is done here.
- **Owner decisions:**
  - the cap's base: **closed** 2026-10-04, "Trần 2% tính theo cố định 100 USD": a fixed 100 USD (§5.5). The
    current-balance rows stay as the earlier reading;
  - the cap value: the same words name 2 % (100 USD on 5,000), the value as run. No other value is read on these days;
  - A5 for a lone trade. Design A5 as written is (b); the code is (a) (personal_account.py:189 checks A5 only
    next to an open trade). They differ only in `floor` and the fixed cap, where one minimum lot can exceed 5 %.
    Options: "(a) as run: a lone minimum lot may risk the full 100 USD, even above 5 % of the balance (below 2,000
    USD)" / "(b) a lone trade also stays within 5 % of the current balance (`risk-config.json`
    max_portfolio_risk_pct)". (b) changes no v4 trade at edge x 1 or x 0.5 (largest risk 2.3 % / 2.6 %); it bounds
    the edge-x-0 tails of §5.5 item 3. **Lead decision 2026-10-04 (owner may override): (b) for any real use**, since
    it is the house portfolio limit as written and only binds after a 60 % drawdown. **Not read on these days**: it
    changes no v4 row above, and a read would add a rule to the §5 budget for tails only. The replay gets its own
    switch (default (a), so rows already read stay reproducible: silver's common-span path, §5.5, took a lone trade at
    9.8 % of the balance) when the personal-account book version is built.

### 5.5 Fixed 100 USD cap (owner's choice 2026-10-04)

Owner 2026-10-04, answering §5.4: "Trần 2% tính theo cố định 100 USD". Design §7.4; A3 `min_lot_cap_base = "initial"`,
label `floor_cap@0.02/initial`.

**DESCRIPTIVE, on the same exposed days** (CLAUDE.md §44). The owner fixed the base before any fixed-cap number existed;
the current-balance rows of §5.1-§5.2 were known. Read once; no other cap value or base.

Rule (personal_account.py:110-122):
- Size at r = 1 % of the current balance, as before.
- Below the minimum lot, trade 0.01 only if its risk at the stop is <= 2 % x 5,000 = 100 USD, whatever the balance
  (:118-120). Otherwise skip (`min_lot_over_cap`, counts toward STALLED).
- Below 5,000 USD that allows more than 2 % of the balance (4 % at 2,500, 10 % at 1,000). Above 5,000 it allows less.
  From 10,000 USD (cap / r x B0) it sizes exactly as `skip`.
- Nothing scales the 100 USD down after a drawdown. A5 (5 % of the current balance) binds only a second open trade
  (:189). A lone minimum lot meets only the margin check (:195), stop-out (:208) and BLOWN (:217: balance below the
  smallest minimum-lot margin of the book's symbols, 138.55 USD for gold and 101.11 USD for silver at the assumed 1:30).

Run: same rows, specs, seed, days and paths as §5.1; B0 5,000 only; r = 1 %; edge x 1 / 0.5 / 0; 18 bootstrap and 12
historical cells. Raw data: docs/audits/2026-10-04-personal-account-cap-fixed.json.

    python3 scripts/research/personal_account.py run --out <json> --cache <rows.pkl> --paths 1000 --jobs 10 \
        --r 0.01 --b0 5000 --mode floor_cap --cap 0.02 --cap-base initial --edge 1 0.5 0

Code version (`meta.code`, CLAUDE.md §46): commit 4f803bf plus the uncommitted personal_account.py (and its tests);
script sha256 ea31d0ba76b09e3d07e78b42c79a5fbd2e1f0563ba7c1b16b7c57306ffbb09b6, the personal_account.py of the commit
that adds this section. With that code:
- `check --against` the first-read JSON (`--new` the cap JSON) and `check --against` the cap JSON: all 96 and all 72
  historical entries replay exactly; the 60 shared entries are equal. The default base reproduces §1-§5.2.
- `check --against` the fixed-cap JSON: its 12 historical entries replay exactly.
- 12 already-read bootstrap cells (`skip` and cap 2 % of the balance, edge x 0.5, all setups) recomputed over all 1,000
  seeds: equal to the cap JSON.

**Bootstrap, 5,000 USD at 1 % (5 years, 1,000 paths).** Columns as §5.1, plus:
- P(DD >= 50 %) (the survival line, design §4);
- "above 2 % of balance": the share of trades whose risk at the stop was above 2 % of the balance at entry / the share
  of paths with at least one such trade;
- "max risk": the largest risk taken, in % of the balance at entry: the p95 of the per-path maxima / the maximum.

All at edge x 0.5 except the multiples and P(BLOWN). Under the current-balance cap the last two columns are 0 and
<= 2 % by construction.

| setup | cap | median multiple x1 / x0.5 / x0 | P(DD >= 25 %) x0.5 | p95 DD x0.5 | P(DD >= 50 %) x0.5 | P(BLOWN) x1 / x0.5 / x0 | STALLED x0.5 | above 1 % | above 2 % of balance: trades / paths | mean risk | max risk: p95 path / max |
|---|---|---|---|---|---|---|---|---|---|---|---|
| v4 | 2 % of balance | 3.05 / 1.87 / 1.25 | 9 % | 27 % | 0 | 0 / 0 / 0 | 0 | 15 % | 0 / 0 | 0.85 % | <= 2 % |
| v4 | **fixed 100 USD** | 2.79 / 1.79 / 1.25 | 8 % | 27 % | 0 | 0 / 0 / 0 | 0 | 13 % | 0.04 % / 20 % | 0.83 % | 2.2 % / 2.6 % |
| v3 | 2 % of balance | 2.43 / 1.68 / 0.83 | 18 % | 41 % | 1.2 % | 0 / 0 / 0 | 0.2 % | 43 % | 0 / 0 | 1.03 % | <= 2 % |
| v3 | **fixed 100 USD** | 1.75 / 1.28 / 0.82 | 29 % | 42 % | 2.1 % | 0 / 0 / 0.2 % | 0.2 % | 48 % | 1.9 % / 64 % | 1.06 % | 2.9 % / 7.4 % |
| H7 gold | 2 % of balance | 1.34 / 1.12 / 0.96 | 2 % | 22 % | 0 | 0 / 0 / 0 | 0 | 62 % | 0 / 0 | 1.15 % | <= 2 % |
| H7 gold | **fixed 100 USD** | 1.25 / 1.09 / 0.93 | 6 % | 26 % | 0 | 0 / 0 / 0 | 0.2 % | 63 % | 1.3 % / 60 % | 1.15 % | 2.5 % / 3.1 % |
| G9 gold | 2 % of balance | 1.93 / 1.44 / 0.89 | 8 % | 28 % | 0.3 % | 0 / 0 / 0 | 0.1 % | 45 % | 0 / 0 | 1.04 % | <= 2 % |
| G9 gold | **fixed 100 USD** | 1.48 / 1.20 / 0.89 | 9 % | 29 % | 0.3 % | 0 / 0 / 0 | 0 | 48 % | 1.1 % / 60 % | 1.05 % | 2.5 % / 4.7 % |
| G9 silver | 2 % of balance | 1.24 / 0.92 / 0.71 | 44 % | 47 % | 1.9 % | 0 / 0 / 0 | 3.7 % | 82 % | 0 / 0 | 1.36 % | <= 2 % |
| G9 silver | **fixed 100 USD** | 1.12 / 0.92 / 0.72 | 50 % | 54 % | 7.2 % | 0 / 0 / 0 | 1.8 % | 86 % | 12.5 % / 89 % | 1.49 % | 3.8 % / 7.1 % |
| v4 + silver | 2 % of balance | 4.20 / 2.14 / 0.86 | 41 % | 44 % | 2.6 % | 0 / 0 / 0 | 0.2 % | 28 % | 0 / 0 | 0.94 % | <= 2 % |
| v4 + silver | **fixed 100 USD** | 2.96 / 1.71 / 1.00 | 45 % | 43 % | 2.4 % | 0 / 0 / 0.2 % | 0.1 % | 27 % | 0.8 % / 59 % | 0.92 % | 2.8 % / 4.3 % |

**Historical, 5,000 USD at 1 % (2018-02-26 -> 2026-10-02, full edge).** Columns as §5.2, plus the two above.

| setup | cap | multiple | CAGR | max DD | taken / skipped | above 1 % | above 2 % of balance | mean risk | max risk | BLOWN | STALLED |
|---|---|---|---|---|---|---|---|---|---|---|---|
| v4 | 2 % of balance | 5.89 | 22.9 % | 13.1 % | 2,647 / 0 | 2 % | 0 | 0.9 % | <= 2 % | - | - |
| v4 | **fixed 100 USD** | 5.10 | 20.8 % | 12.7 % | 2,614 / 33 | 1 % | 0 | 0.8 % | 1.2 % | - | - |
| v3 | 2 % of balance | 4.43 | 18.9 % | 11.3 % | 2,633 / 14 | 10 % | 0 | 0.9 % | <= 2 % | - | - |
| v3 | **fixed 100 USD** | 2.61 | 11.8 % | 13.9 % | 2,334 / 313 | 7 % | 0 | 0.8 % | 1.7 % | - | - |
| H7 gold | 2 % of balance | 1.85 | 7.4 % | 7.1 % | 1,061 / 35 | 38 % | 0 | 1.0 % | <= 2 % | - | - |
| H7 gold | **fixed 100 USD** | 1.48 | 4.7 % | 8.0 % | 915 / 181 | 42 % | 0 | 1.0 % | 1.7 % | - | - |
| G9 gold | 2 % of balance | 3.17 | 14.4 % | 12.6 % | 1,540 / 11 | 14 % | 0 | 0.9 % | <= 2 % | - | - |
| G9 gold | **fixed 100 USD** | 1.89 | 7.7 % | 12.6 % | 1,328 / 223 | 13 % | 0 | 0.8 % | 1.7 % | - | - |
| G9 silver | 2 % of balance | 2.74 | 12.4 % | 21.0 % | 1,457 / 60 | 28 % | 0 | 0.9 % | <= 2 % | - | - |
| G9 silver | **fixed 100 USD** | 1.17 | 1.8 % | 31.8 % | 1,079 / 438 | 56 % | 0 | 1.1 % | 1.8 % | - | - |
| v4 + silver | 2 % of balance | 11.37 | 32.7 % | 18.9 % | 4,154 / 10 | 4 % | 0 | 0.9 % | <= 2 % | - | - |
| v4 + silver | **fixed 100 USD** | 8.05 | 27.4 % | 19.3 % | 4,041 / 123 | 3 % | 0 | 0.9 % | 1.8 % | - | - |

In this span: no BLOWN, no STALLED, and no trade above 2 % of the balance. Every fixed-cap skip came at a balance at or
above 5,000 USD (silver 3 and v4 + silver 1 at exactly the starting 5,000). v4's 33 all came above 10,000 USD (lowest
11,382); H7's, G9 gold's and silver's all below it. Method: these paths replayed with `lots_for` wrapped to record the
balance at each skip. This is a scratch check, not committed; it used the same code, rows and specs, and its trades,
skips and multiples equal the JSON.

Over the longer common span (2008-12-10 -> 2026-10-02, in the JSON) the fixed cap did go above 2 % of the balance: v3
17 trades, H7 2, G9 gold 7, silver 453 (largest 9.8 % of the balance). Silver fell 82 % from its peak there (current
cap: 62 %, then STALLED from 2026-07-31). No setup blew.

**What the fixed base changes:**
1. **On these days it is mostly the tighter cap.** Most paths grow, and above 5,000 USD the 100 USD is less than 2 % of
   the balance. The median falls against the current-balance cap for every setup at edge x 1, and for all but silver
   (equal) at x 0.5: v4 x1.87 -> x1.79, v3 x1.68 -> x1.28, G9 gold x1.44 -> x1.20, v4 + silver x2.14 -> x1.71. At x 0
   they are about equal, except v4 + silver (x0.86 -> x1.00). Historically every setup ends lower (v4 x5.89 -> x5.10).
2. **Its looser side is used on paths that fall below 5,000 USD.** At x 0.5 few trades go above 2 % of the balance
   (v4: 665 of 1.48 million; v3 1.9 %; silver 12.5 %), but many paths have one (v4 20 %, the others 59-89 %). The
   largest risk at x 0.5 is 2.6 % (v4), 7.4 % (v3), 7.1 % (silver).
3. **BLOWN appears, only at edge x 0:** v3 and v4 + silver, 2 paths in 1,000 each. None at x 1 or x 0.5, none for v4.
   At x 0 the largest single risk was 52 % (v3) and 75 % (v4 + silver) of the balance: a lone minimum lot (<= 100 USD)
   on a balance of at most 192 / 133 USD, which A5 does not stop (open item in §5.4).
4. **Survival** (design §4, edge x 0.5): every setup but silver. Silver fails on P(DD >= 50 %) 7.2 % (current cap
   1.9 %). Ranking: v4 beats v3 on 98 % of paths (79 % under the current cap). In COMPONENT-VALIDATED the leader
   changes because silver drops out: under the current cap G9 gold led only through its win over silver (89 %). G9
   gold beats H7 on 67 % of paths (78 % under the current cap; both below the 80 % bar), so the lower p95 drawdown
   decides: H7 26 % against G9 gold 29 %.
5. **v4 (the §5.4 candidate):** x2.79 / x1.79 / x1.25 against x3.05 / x1.87 / x1.25; P(DD >= 25 %) 8 %; p95 drawdown 27 %;
   P(DD >= 50 %) 0 at x 0.5 and 3.5 % at x 0 (current cap 8.4 %); no BLOWN, no STALLED. Historically x5.10 (20.8 %/yr),
   max drawdown 12.7 %.
6. **§5.3 item 5 applies unchanged:** the edge levels mean different things under `skip` and under a cap, and part of
   any cap's gain is the post-hoc stop-width pattern. No row here is a clean planning row.
