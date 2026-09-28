# Pre-registration — search for setups that pass the FTMO / The5ers challenge rule sets

Date: 2026-09-27. Owner decisions recorded here verbatim in substance. This file is committed BEFORE any
candidate is evaluated (CLAUDE.md §42–§45); changing it after the first evaluation is itself an experiment
event and must be recorded in the ledger with the reason.

## 1. Question

Which setups, run by the existing engine, would pass the prop-challenge rule sets of **FTMO Challenge
Phase 1** and **The5ers High Stakes Step 1** as declared in `docs/architecture/account-profiles.json`
(`ftmo-challenge-phase1`, `the5ers-high-stakes-step1`)? The target is at least **5** such setups — a goal,
not a stopping rule (§3).

## 2. Pass definition (owner, 2026-09-27)

A candidate PASSES only if, on the VALIDATION window (§4) alone:

1. `prop_pass_probability` ≥ **0.70** under the FTMO Phase 1 rules **and** ≥ **0.70** under the The5ers Step 1
   rules — each fund on its own, both required. Computed by `scripts/performance.py` (day-block bootstrap,
   2000 iterations, fixed seed, risk 1 % per trade = `risk-config.json max_risk_pct`), horizon = the number
   of trading days in the validation window.
2. It trades on at least the fund's own `min_trading_days` (FTMO 4, The5ers 3) within the window, and the
   bootstrap has the sample it needs to run at all (the engine's own floor).
3. Expectancy per trade is credibly positive: the one-sided 90 % bootstrap lower bound of mean net R on the
   validation trades is > 0. There is NO fixed minimum trade count — this bound is what penalises a small
   sample (owner, 2026-09-27: "the 30-trade floor is not a fund rule; lower it to the lowest appropriate").

A 70 % threshold is judged per fund, so "≥ 70 % on both funds" and "≥ 70 % on each fund" are the same rule.

## 3. Budget and stopping rule (owner: fixed budget)

- At most **200** candidates evaluated on the validation window, counted in the ledger from the first one.
- The search stops at whichever comes first: 5 passes, or the budget is spent.
- If fewer than 5 pass, the result is reported as found — no criterion is relaxed to reach 5.
- Every candidate, passed or not, is recorded (§42 immutable experiment record via `scripts/experiment.py`),
  with the running count, so the number of tries behind any pass is visible (§43).

## 4. Data (owner: development before 2024-03, validation 2024-03 → 2025-03)

| Window | Period (entry_time, UTC) | Use |
|---|---|---|
| Development | everything before **2024-03-01** | free exploration, parameter choice, candidate generation |
| Validation | **2024-03-01 → 2025-03-01** | evaluated ONCE per candidate, only for the pass decision |
| Exposed — reporting only | after 2025-03-01 | used by ADR 0008's selection (IS 2025-03 → 2026-03, OOS 2026-03 → 2026-09); never used to choose or tune anything here |
| Forward confirmation | live demo from the day a candidate passes | required before any funded attempt |

Point-in-time: a run is fed history truncated at **2025-03-01**, so nothing after the validation window can
reach a decision, an indicator warm-up, or a data-quality verdict (§8, §37). The validation window becomes
EXPOSED the first time a candidate is judged on it, and is recorded as such.

## 5. Candidate space

- Instruments: the CFD analysis list — XAUUSD, XAGUSD, US500, US30, USTEC, DE40, FRA40, AUS200 (added
  2026-09-27; deep history via `integrations/mt5/ExportHistory.mq5` → `scripts/import-mt5-history.py`).
  USOIL/UKOIL only if MT5 history exists for them. An instrument without history before 2024-03 cannot be
  developed on and is skipped, stated as such.
- Methods: the runnable set (`docs/architecture/methods.json`: ICT, WYCKOFF-BOOK) × configurations A/B/C ×
  timeframes 15m/1H/4H, per instrument and pooled per asset class.
- Methodology changes are EXTENSIONS only (ADR 0007), each cited to `knowledge/`, each counted as new
  candidates. Project parameters (R, K, T, H, targets) may be varied on development data only; every variant
  evaluated on validation spends budget.

## 6. What is known before starting (and why it does not count)

`data/history/stability/cfd-ftmo-challenge-phase1.json` shows full-period bootstrap pass probabilities of 0.88
(CFD 1H ICT config A, n = 63) and 0.65 (config B). Those numbers include the exposed 2025-03 → 2026-09 data and
are therefore leads, not evidence. They are listed here so they cannot later be presented as a discovery.

## 7. Not in scope

Real-money or funded execution; changing risk above 1 % per trade; changing ADR 0008's pilot criteria.

## 8. Addendum 2026-09-28 — owner decisions after the pre-run review (still before any evaluation)

Recorded before the first candidate is evaluated (`docs/experiments/prop-search-2026-09-27/` holds only
`plan.json`), so none of these was chosen after seeing a result.

1. **Challenge horizon = 120 trading days.** `prop_pass_probability` is computed over a 120-trading-day horizon
   (≈ 6 months), trading days = Mon–Fri, for BOTH funds. Why: neither fund imposes a time limit today (FTMO removed
   its 30-day limit in late 2024; The5ers High Stakes has none — third-party 2026 summaries, to be checked
   against the funds' own pages), so the horizon is the owner's maximum acceptable wait. 30, 60 and 261 days are
   REPORTED for information and never gate. The earlier implementer reading (horizon = every weekday in the
   validation window, ~261) is superseded.
2. **Trades not finished at the cutoff are excluded.** A validation trade whose exit (stop, target or the
   H-bar time stop) would need a bar after 2025-03-01 is excluded from the pass decision, and the number
   excluded is recorded per candidate. It is not marked to market at the truncated last bar.
3. **The5ers rules modelled as the fund states them.** Step 1 requires at least 3 *profitable* days (closed
   profit ≥ 0.5 % of the initial balance on the day), not 3 trading days, and an evaluation account expires
   after 30 consecutive calendar days without a trade — both enter the The5ers pass event.
   (`docs/architecture/account-profiles.json` `the5ers-high-stakes-step1` is updated accordingly; that is an
   account-rule change, §33, approved by the owner 2026-09-28.)
4. **The implementer's other readings are confirmed:** pooled asset class = one shared simulated account over
   the class's symbols; expectancy bound = 10th percentile of 2000 bootstrap means of validation net R, seed
   20260927, minimum 5 trades; `parent_trading_system_version` unavailable for a from-scratch search.
