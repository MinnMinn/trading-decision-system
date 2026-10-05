# Erratum: look-ahead in the E5 (FVG retrace) event selection (2026-10-03)

**What.** `edge_census._first_per_day` kept the first event per (server day, side) in LIST order. `ev_fvg` lists gaps in
FORMATION order with entry at a LATER touch, and only gaps that were ever touched. On a day with two same-side gaps where the
later-formed gap B is filled first and the earlier gap A later, the research traded A and dropped B: deciding that at B's
fill requires knowing that A will be touched. Look-ahead in the entry decision (CLAUDE.md §8, §37: future movement "may not
influence entry"). Found by docs/audits/2026-10-03-e5-live-fill.md (pre-registered, DESCRIPTIVE / EXPOSED), confirmed
independently by the session "Khám phá hệ thống FTMO" (reframes §9, round B). **§38 makes the flag mandatory**; it is not an
owner choice. Which Trading System the demo runs IS an owner choice (§5 below).

**Size.** The dropped trades average -0.14 R (XAUUSD, 1,135 of 10,337) and -0.09 R (US500, 197 of 2,556). Under the demo's
point-in-time selection E5 has no edge: XAUUSD +0.0042 -> -0.0123 R per trade (2004-26), US500 +0.0084 -> +0.0013 R.

**Fix (this commit).** `_first_per_day` keeps the event with the earliest ENTRY bar per (day, side) (ties keep list order),
which is what the executor does (first fill cancels the siblings). Identical output for every detector that appends in bar
order with entry at the next bar (E1-E4, E9; verified by the full census re-run below). Regression tests in
`scripts/tests/test_edge_census.py` (`test_fvg_keeps_the_first_FILL_not_the_first_formed_gap`,
`test_first_per_day_is_the_earliest_entry_whatever_the_list_order`). Historical records are NOT re-run or edited (§42); they
are flagged here.

## 1. Records flagged (contents unchanged; read every E5 number in them as INVALIDATED)

| record | what is invalid | what stays valid |
|---|---|---|
| docs/audits/2026-10-02-edge-census.md / .json | the 6 E5 rows and the reading "E5 ... significant in both groups and both periods" | every other row (re-run identical, §2) |
| docs/plans/2026-10-02-edge-followup-preregistration.md, docs/audits/2026-10-02-edge-followup-exposed.md / .json, 2026-10-02-edge-followup-history.json | the 15 E5 tests, incl. both stage-(b) "survivors" (E5 XAUUSD 2 h, E5 US500 4 h) | E1 / E2 rows |
| docs/audits/2026-10-02-fvg-book-sim.md / .json | everything (E5-only books) | -- |
| docs/audits/2026-10-02-book-sim.md / .json | every book containing E5 (`gold_both`, `all_three`) | `H7_XAUUSD` rows, the H7 component line |
| docs/audits/2026-10-02-book-variants.json, docs/audits/2026-10-02-edge-f4.md §2 | the baseline and every variant (all contain E5); "G9 gold corr 0.19 with the baseline" | the F4 test table (§1, §4) |
| docs/audits/2026-10-02-pass-policy.md / .json, -pass-policy-descriptive.json, 2026-10-03-pass-policy-floating.json | every policy (all books contain E5), incl. the v2 choice and its 0.36 / 0.22 / 0.13 | -- |
| docs/audits/2026-10-03-ftmo-rules-audit.md §4 | the v1 / v2 replay numbers | §1-§3 (rules, swap) |
| docs/audits/2026-10-02-strategic-diagnosis.md, status updates | every book / pass figure that includes E5 | the diagnosis itself, the F3 / F4 / F5 test verdicts |
| docs/audits/2026-10-02-edge-f3.md | H5 rows (FVG in high-vol regime; null anyway) | the other 25 rows, H7 |
| docs/audits/2026-10-02-edge-f5.md | the 9 E5 rows (null anyway) | H7 / G9 rows |
| docs/architecture/book-baseline.json | the `all_three` baseline is a look-ahead baseline | -- (the file is the owner's; replacing it is an owner decision) |
| docs/plans/2026-10-03-reframes.md (this session) | R2 composition (E5 = 62 % of base3 R), R4 book volatility 0.71 / 0.95 R, R3's E5 power rows | the synthetic study (reads no market data) |

The v1 and v2 approvals of `fvg-book` (trading-systems.json) rest on the invalidated E5 evidence. Nothing in the demo, a
Trading System version or a config is changed here.

## 2. Census re-run with the fix (development window, already read twice; DESCRIPTIVE)

`edge_census.py run` at this commit -> `docs/audits/2026-10-03-edge-census-pit-rerun.json` (same data snapshot, same cost
profile, same splits as the original: the per-symbol meta blocks are equal).

- **The 34 non-E5 tests are unchanged**: every field equal to the original JSON up to a maximum relative difference of
  7.8e-12 (floating-point summation order). The fix touches nothing but E5.
- **E5 under the point-in-time selection** (excess z over the same-minute placebo; net at the median spread):

| E5 | h | discovery excess z, p (2-sided) -- original -> PIT | BH | confirmation excess z, p (1-sided) -- original -> PIT | net bp discovery / confirmation (PIT) |
|---|---|---|---|---|---|
| metals | 6 | 0.044, <1e-4 -> **0.018, 0.012** | yes | 0.048, <1e-4 -> 0.022, 0.011 | -1.96 / -2.09 |
| metals | 12 | 0.040, <1e-4 -> 0.007, 0.30 | no | 0.033, <1e-4 -> 0.003, 0.38 | -2.06 / -2.44 |
| metals | 24 | 0.025, 0.0002 -> 0.004 (sign flips), 0.52 | no | 0.027, 0.0005 -> 0.001, 0.44 | -2.67 / -2.45 |
| indices | 6 | 0.036, 0.006 -> 0.004, 0.75 | no | 0.046, 0.0003 -> 0.012, 0.19 | -2.37 / -2.28 |
| indices | 12 | 0.038, 0.004 -> 0.001, 0.93 | no | 0.051, 0.0001 -> 0.013, 0.17 | -2.36 / -2.08 |
| indices | 24 | 0.042, 0.001 -> 0.003, 0.82 | no | 0.041, 0.0002 -> 0.012, 0.14 | -1.78 / -2.01 |

Reading: most of the "replicating predictability" the census reported for the FVG retrace was the selection. What is left is
a small 30-minute continuation on the metals (excess z ~0.02 in both periods), at a net of about -2 bp -- far below the cost.
On the indices nothing is left. DESCRIPTIVE: the development window had been read before; this re-measures, it does not
discover.

## 3. Forward paper log and stage (a)

`fvg_forward.py` detects E5 with `ev_fvg` on cumulative bars and de-duplicates on (component, entry time, side)
(`fvg_forward.py:226`). Before this fix, a scan between B's fill and A's touch logged B, and a later scan logged A as well:
the E5 paper record depended on WHEN scans ran (not reproducible). With the fix the first fill (B) stays the day's event in
every later scan. E5 rows already in a machine's `fvg-paper.jsonl` (from 2026-09-29) may contain such doubles; the stage-(a)
read of E5 must re-derive events from the bars with the fixed selection, or E5's forward stage is stopped (owner).

## 4. Process gap

The edge-family scripts (census, F2-F5, AMD, hold, book_sim, pass_policy) write their own JSON and never carry a §38
verdict stamp (`scripts/research_validity.py`), and no leakage probe ran on them. A "truncate the future and re-detect"
check -- the census test `test_no_event_uses_a_future_bar` does this for E1 only -- would have caught this for E5.

## 5. For the owner (decisions)

1. Demo: keep v2 (E5 included; as executed: funded <= 122 d ~0.10 confirmation / 0.07 bootstrap / 0.07 half edge, first
   fails 11-15 %, and its pass probability comes from VARIANCE, not edge) or move to v3 = H7 + G9 gold, dd3, 1 % (no E5;
   ~0.01-0.04 within 122 days, fails 0-1 %, funded eventually 0.78 of the 2024+ starts, median ~246 days).
2. Replace `book-baseline.json` with a point-in-time baseline.
3. E5's forward stage (a): re-specify (re-derive from bars) or stop.
