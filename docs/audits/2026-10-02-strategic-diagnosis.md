# Strategic diagnosis: why almost no setup passes FTMO (2026-10-02)

**Type:** read-only diagnosis plus owner decisions. No code, config, grid, cell or engine behaviour was changed by
this document. **Audience:** any later session that continues the work. Read §0 and §6 first.

**Tóm tắt (VI):** Hệ thống vừa có lỗi đo lường cụ thể (làm kết quả 0/180 là chắc chắn), vừa sai hướng từ đầu:
coi "trung thành với sách ICT/Wyckoff" là nguồn edge, đánh giá từng setup thay vì cả book + chính sách risk, và xây
governance trước khi có alpha. Sửa lỗi không tạo ra edge: Wyckoff gross ≈ 0, ICT gross +0.21R mỏng và quá ít lệnh.
Owner đã chọn: mục tiêu là **pass FTMO bằng bất kỳ phương pháp đã kiểm chứng**; sửa lỗi #3–#5 rồi declare lại
fund-search; chấp nhận demo forward làm bằng chứng chính.

## 0. Owner decisions (2026-10-02, in chat, binding)

1. **Goal:** pass FTMO with ANY validated method. ICT/Wyckoff are no longer the required edge source; they are one
   hypothesis family among others.
2. **Fix defects #3, #4, #5 (§2) and re-declare the fund-search** before any fund-search record is run. At the time
   of this decision the declaration (commit `c4ea722`, plan_hash `275763cb81b0518a`) existed and
   `docs/experiments/fund-search/` held only `plan.json`: no candidate outcome had been read.
3. **Forward demo is the primary evidence**, and the nomination gate to demo may be looser than the gate for real
   money (accepted "if this is the best way"; §5 states why it is).

## 1. How the system works (one paragraph)

Analysis layer: Claude agents/skills (Wyckoff, ICT, Footprint, Heatmap) -> Confluence -> Risk -> journal; not
backtestable. For CFDs Footprint/Heatmap have no real data (CoinGlass mock) and Wyckoff has tick volume only, so the
original 4-dimension confluence design has never been tested. Mechanical layer (what is backtested and what the
pilot runs): `scripts/ict-scan.py` (sweep -> displaced MSS -> FVG -> IOFED limit, -2 sigma target) and
`scripts/wyckoff_rules.py` (Spring/Test, Phase-D LPS/BU), shared by `scripts/backtest-methods.py` (scan -> walk ->
simulate) and `scripts/strategy-runner.py` (live). Research layer: `scripts/prop-search.py` (180 candidates, 0
passed) -> diagnosis -> F/V items -> `scripts/fund-search.py` + `scripts/fund_stats.py` (sealed 2026-10-02, 3 cells
1m-metals / 1m-indices / 5m-metals x ICT / Wyckoff).

## 2. Defects (verified in code)

| # | Defect | Where | Bias | Effect |
|---|---|---|---|---|
| 1 | The5ers 30-day inactivity rule evaluated over the WHOLE validation year (incl. window start -> first trade), not over a challenge horizon. **180/180 records breach it.** | `scripts/prop-search.py:398-447`, gate `:475`, `:482` | too harsh | 0/180 was certain regardless of edge |
| 2 | CFD cost = flat 0.05 %/side, copied from the Binance taker schedule. FTMO's recorded spread is 2-19x lower (incl. swap 3-10x, `docs/audits/2026-09-29-real-costs-reprice.md`). The 180 records carry `fee_pct_per_side 0.0005`. | `docs/architecture/risk-config.json` `costs.mt5`; `scripts/risk_model.py:115` | pessimistic | Same dev trades re-priced with `ftmo_demo_2026_09_relspread`: ICT net -0.02 -> +0.10 R (after floor +0.06 -> +0.20 R, 127 trades); Wyckoff -0.35 -> -0.14 R. (fund-search already uses the real profile) |
| 3 | **FVG self-touch in the "already triggered" gate.** Bull FVG at middle candle `i`: IOFED edge = `L[i+1]` (`scripts/ict-scan.py:255`, `:687`). When the MSS candle is the FVG's middle candle (the canonical displacement FVG), candle `i+1` = `mss_i+1` is the first bar `fvg_fill` scans, and `L[j] <= edge` is trivially true, so the setup is refused. The order cannot exist before candle 3 closes, so the scan must start at `max(mss_i, fvg_i+1) + 1`. | `scripts/backtest-methods.py:1224` + `fvg_fill` (`:744`); live identical at `scripts/strategy-runner.py:916-918` | pessimistic (frequency) | 261 of 351 "already triggered" refusals, 37 % of all 699 config-A setups (dev, XAU/US500/DE40, 15m/1H/4H). The live pilot can never place this order. Fixed, +157 fills at about -0.05 R gross: raises frequency, reveals no hidden edge on those TFs. |
| 4 | Prop-pass "horizon 120 days" counts **days that had a trade**, not weekdays: `_bootstrap_days` resamples trade-day blocks only. | `scripts/performance.py:320-375`, `:590` | too lenient | All 8 prop-search candidates with >= 0.70 were artefacts (5-9 trades/yr); on 120 weekdays three re-checked cases fall to 0.01-0.05. In 5m-metals e* is understated. |
| 5 | Prop simulation risk per trade is always the 1 % ceiling (`_risk_fraction` -> `account_profile.effective_risk_pct`), regardless of trade frequency. | `scripts/performance.py` `_risk_fraction` | pessimistic at high frequency | In 1m cells the 5 % daily limit binds and inflates e*. Simulation: 1785 trades/yr, +0.1 R: P(pass) 0.44 at 1 %, 0.79 at 0.5 %, 0.89 at 0.25 %. |
| 6 | Sizing: P&L = equity x 1 % x (R - fee_R), so a stop-out costs (1 + fee_R) %; live `size()` keeps it at 1 %. | `scripts/backtest-methods.py:1873`, `:2148` | slightly pessimistic | 7-37 % larger dollar swings than live |
| 7 | Minor: daily loss checked at close on closed-trade equity (FTMO: continuous equity vs midnight CE(S)T balance minus 5 % of initial); UTC day boundary; days resampled iid; `low_confidence` ignored by prop-search's pass. | `scripts/performance.py:270, 374-386`; `scripts/prop-search.py:469-471` | mostly lenient | small at 1 % risk |

Power of the prop-search criteria (synthetic, +2.5/-1 R, fee 0.07 R): at <= 36 trades/yr (the search's max was 39,
median 2) a true +0.5 R/trade strategy passes all criteria with probability <= 0.08, and 0 at <= 20 trades/yr. Even
without defect 1 no candidate had a positive expectancy bound (best -0.19 R, n = 6).

## 3. The part no bug fix changes: the measured edge

| Dev data (< 2024-03-01), config A | n | gross | net, flat fee | net, real FTMO cost |
|---|---|---|---|---|
| ICT, XAU/US500/DE40 x 15m/1H/4H | 158 | +0.21 R (~1.6 SE) | -0.02 R | ~ +0.10 R |
| WYCKOFF-BOOK, same | 686 | -0.04 R | -0.35 R | -0.14 R |

ICT is negative on US500 and on 4H, and yields ~1.5-1.9 trades per symbol-year on 1H. Wyckoff loses before costs;
its trades clearing the 2R floor win 21 %. No F-item variant was stably net-positive across symbols (flat-fee funnels,
`docs/audits/2026-09-29-ict-fidelity-funnel.md`, `docs/audits/2026-09-29-wyckoff-fidelity-funnel.md`). Crypto shows
the same (ICT 1H n = 3, 4H n = 1 over 4 years on 9 symbols, `docs/backtests/2026-09-24-crypto-day-swing-research.md`).
Prop-search records pooled at instrument level: validation -0.42 R (n = 359), development -0.29 R (n = 2039), flat fee.

## 4. Why the direction was wrong

1. **Book fidelity was treated as edge.** ADR 0007 makes the sources ground truth, so research asked "is the code
   faithful?" instead of "does this predict returns net of cost?". Codifying discretionary methods needs dozens of
   project-defined thresholds (pivot width, displacement ratios, K, H, lookback, sob, test window), each a degree of
   freedom (`docs/audits/2026-09-28-method-fidelity.md` I-1..I-18, W-1..W-27).
2. **A conjunctive 8-9 gate funnel destroys frequency without demonstrated marginal value:** 4,550 sweep->MSS
   candidates -> 158 trades (3.5 %). No gate's conditional predictive value was measured. The 2.5R floor is a
   management rule in the source ("minimum 2R before any profit is taken", fidelity I-14) used as an admission filter.
3. **Wrong unit of evaluation.** FTMO pass is a barrier problem (+10 % before -10 % and -5 %/day); it is a property of
   a BOOK (edge x frequency x correlation) plus a risk policy, not of one setup. Simulation (120 trading days,
   +2.5/-1 R, independent trades; script below):

   | net edge | trades/day | risk 0.25 % | 0.5 % | 1 % |
   |---|---|---|---|---|
   | +0.10 R | 0.05 (~12/yr) | 0.00 | 0.00 | 0.02 |
   | +0.20 R | 0.25 | 0.00 | 0.10 | 0.43 |
   | +0.10 R | 1 | 0.09 | 0.47 | 0.65 |
   | +0.10 R | 3 | 0.57 | 0.79 | 0.53 |
   | +0.20 R | 3 | 0.90 | 0.95 | 0.67 |
   | 0 | 3 | 0.19 | 0.45 | 0.37 |

   At current setup frequencies pass probability is ~0 for ANY edge; at high frequency 0.5 % beats 1 %; zero edge
   still passes up to 45 %, so pass probability alone does not discriminate edge.
4. **Evidence standard mismatched to the stakes.** The sealed fund-search certifies (80 % power) only 0.20-0.30 R per
   trade at 450-1,800 trades/yr, i.e. an annual Sharpe of roughly 2-7.5 if trades were independent
   (`docs/audits/2026-10-02-e2e-power.md` F1); at 0.10-0.15 R P(PASS) is 0-7 %; type I 0/3000. The red team expected
   zero nominations with ~80-90 % probability. A false nomination to a demo costs only demo time.
5. **Governance before alpha.** ~48K LOC code, ~47K LOC tests (~3,600 tests), ~3 MB of docs, 62 compliance sections,
   Playwright and i18n in ~3.5 weeks, for two hypothesis families; plan inputs changed repeatedly (symbol list three
   times in one day; `min_rr` 3.0 -> 2.0 -> 2.5). CLAUDE.md §57 (YAGNI) applies.
6. **Going to 1m to buy power** enters the regime where OHLC bid-bar backtests are least reliable (ask-side triggers
   not modelled, spread variation), the route to a spurious nomination named in the fund-search disclosures 9 and 12.

**Keep:** PIT engine, real MT5 cost model, FTMO data, research ledger / OOS exposure, pre-registration discipline,
and the rule not to move a window to rescue a method.

## 5. Plan (in order)

1. **Freeze** expansion of governance / UI / compliance work until an edge exists.
2. **Fix #3, #4, #5, then re-declare** (owner decision 2). Each change is §59 version-significant:
   - #3: start the "already triggered" scan after the FVG's third candle closes, in the ONE shared function so backtest
     and live agree (`fvg_fill` call sites `scripts/backtest-methods.py:1224` and `scripts/strategy-runner.py:916`).
     Backtest behind an `fx_` key adopted in the fund-search baseline as an F item (correctness, not performance);
     live stays v1 until the owner approves v2 (plan §1.6). Regression test: a setup whose MSS candle is the FVG middle
     candle must NOT be refused by its own third candle.
   - #4: horizon in weekdays (inactive weekdays are empty days in the bootstrap path); FTMO day boundary as in the
     profile; prop-search's inactivity rule (#1) judged within the challenge horizon. The 180 prop-search records are
     immutable: issue an erratum successor, never a re-run on the exposed window.
   - #5: risk per trade becomes a declared parameter of the prop simulation (grid e.g. 0.25 / 0.5 / 1 %, never above
     `risk-config.json max_risk_pct`), reported per cell; choice made on training folds only.
   - Then re-run `scripts/research/e2e_power.py`, update the pre-registration (prior-reads table §0.1 MUST add the reads
     listed in §7 below), commit `plan.json`, and `declare` again. All files above are in `FINGERPRINT_FILES`.
3. **Edge census on development data (< 2024-03-01)**, cheap and fast: event studies of single primitives (sweep-and-
   reclaim of PDH/PDL and session highs/lows, FVG fill, MSS) — forward net return at 15/30/60/120 min vs a same-hour
   placebo, real costs — plus documented baselines for indices/metals (opening-range breakout, intraday momentum,
   trend following). If a primitive has no signal, no stack of gates on top creates one.
4. **Build a book** from net-positive, weakly correlated components (target ≥ +0.05-0.10 R net, ≥ ~1 trade/day for
   the whole book).
5. **Optimise the prop policy by Monte Carlo on FTMO rules** (risk 0.25-1 %, daily stop, stop at target).
6. **Tiered evidence (owner decision 3):** pre-registered, looser nomination gate to demo (e.g. FDR q ≈ 0.2 or
   shrinkage instead of FWER on min-of-five bounds); parallel forward demos with pre-registered kill rules are the
   primary evidence; the strict gate applies to real money only. This needs its own pre-registration.

## 6. Status for the next session

- Done: this diagnosis; owner decisions §0.
- Done (same day): §5 step 2. D3 `fx_fvg_formed_start` (F item, fund cells only; live still v1), D4 weekday horizon,
  D5 frequency-based prop risk, `declare --supersede`; power re-run (docs/audits/2026-10-02-e2e-power.md §10); plan_hash
  275763cb81b0518a -> 0ec4e27e15fa7df9 re-declared, the old declaration kept in `research-ledger.json`
  `fund_search_superseded`. The fund-search MAY now be run on this declaration.
- Power result to read before running: the prop pass no longer binds; the statistical standard (stress, perturbation, floor
  bound) does. Detectable edge with 80 % power stays 0.20-0.30 R/trade; at 0.10 R P(PASS) is 0.01-0.03. A zero-nomination
  result therefore remains likely and says little about edges near 0.10 R (diagnosis §4.4).
- Next: run the fund-search (Actions sharding), then §5 steps 3-6 (edge census, book, prop policy, tiered evidence with a
  separately pre-registered demo-nomination gate). Live v2 (D3 in strategy-runner) needs the owner's approval.
- FTMO rules in `account-profiles.json` are still unverified at the source (ftmo.com blocked in the cloud sandbox);
  2026 third-party summaries agree: 10 % target, 10 % static max loss, 5 % daily (equity vs midnight CE(S)T balance
  minus 5 % of initial), min 4 trading days, no time limit.

## 7. Integrity disclosure (add to the fund-search prior-reads table on re-declare)

During this audit, subagents ran the unmodified engine on the development window (`bt.pit_cutoff("2024-03-01")`),
config A, XAUUSD / US500 / DE40 on 15m / 1H / 4H, and READ gross/net R of: the baseline; the self-touch fix (#3);
K x2 / x3 expiry; B6 (cancel after target); time stop walked to 10 x H; real-cost re-pricing
(`ftmo_demo_2026_09_relspread`); same-bar and gap-fill cases; Wyckoff next-open entry. The 180 prop-search records
were aggregated (already-exposed reads). Synthetic simulations read no data. The sealed 1m/5m cells were not run.

Reproduce the simulation of §4.3: a stdlib-only Monte Carlo (binary +2.5/-1 R net, Poisson trades per weekday, FTMO
+10 % / -10 % static / -5 % daily from day start, min 4 trading days, 120 weekdays, fixed risk on initial balance,
6000 paths per cell, seed 20261002). It was a scratch script and is not committed.
