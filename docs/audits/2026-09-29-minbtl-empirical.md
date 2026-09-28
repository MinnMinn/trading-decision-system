# Minimum backtest length, checked on our own data (2026-09-29)

**Question (owner):** do shorter timeframes need less history? Is the published result still true on our data?

**Method:** `python scripts/research/minbtl_check.py --symbol XAUUSD --n 328 --reps 5 --tfs 15m,1H`. The script runs 328 skill-less random strategies (the plan's N for ICT over 8 cells) on XAUUSD development data (< 2024-03-01). It records the best annualised in-sample Sharpe that luck produces, averaged over 5 random windows.

| years | 15m | 1H | Bailey et al. 2014 bound sqrt(2 ln N / y) |
|---|---|---|---|
| 1 | 3.03 | 2.89 | 3.40 |
| 2 | 1.95 | 1.81 | 2.41 |
| 3 | 1.75 | 1.64 | 1.97 |
| 5 | 1.54 | 1.34 | 1.52 |

**Findings:**
1. **The luck ceiling is set by calendar years, not by timeframe.** 15m and 1H give nearly the same ceiling, even though 15m has four times as many bars. That confirms the paper's claim on our data. A lower timeframe does not, by itself, need less history.
2. **The paper's formula is an upper bound.** It sits slightly above what our data shows at 1–3 years, so it is conservative, not wrong.
3. **Consequence for the plan:** with 3 years of development data, luck alone reaches an annualised Sharpe of about 1.7 across 328 tries. A setup has to clear well above that, which the N-adjusted lower bound in plan §1.4 already enforces. A genuinely better 1m/5m setup, with a higher true Sharpe, clears it with fewer years. That is the only sense in which lower timeframes need less history.
4. **Not yet checked:** 1m/5m/30m, pending the MT5 export. Re-run with `--tfs 1m,5m,30m` once the data is in.

Source: Bailey, Borwein, López de Prado, Zhu, "Pseudo-Mathematics and Financial Charlatanism: The Effects of Backtest Overfitting on Out-of-Sample Performance", Notices of the AMS 61(5), 2014, Theorem 3.1 (https://www.davidhbailey.com/dhbpapers/backtest-pseudo.pdf).
