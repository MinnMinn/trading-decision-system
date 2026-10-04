# Family OIL -- the gold intraday-trend rules (H7, G9) on FTMO's crude-oil CFDs -- pre-registration DRAFT (2026-10-04) [OIL-P1]

Status: DRAFT. Not sealed.

Sealing: the coordinator commits this text, after review, as
`docs/plans/2026-10-04-oil-trend-transfer-preregistration.md`, with the status line above replaced by a line that reads
exactly "Status: SEALED" and with §10's code manifest filled in. `scripts/research/edge_oil.py` refuses every read until then
(scripts/research/prereg_guard.py `require_sealed`, `require_fingerprint`).

**Written before any FTMO oil bar exists in this repository.** The owner universe of 2026-10-01 excluded energies
(docs/plans/2026-10-01-symbol-universe-design.md:3), so no FTMO oil CFD was ever exported. The underlying was NOT unseen,
though (corrected after review, 2026-10-04):
- Yahoo Finance front-month futures (CL=F -> USOIL, BZ=F -> UKOIL), 1H / 2H / 4H / 1D, were in the repo from commit
  3070e2e (2026-09-19) to 345e586 (2026-09-27) (docs/architecture/data-sources.md:33; docs/architecture/instruments.json
  history, 2026-09-27 entry).
- The ICT / Wyckoff stability runs (scripts/stability-report.py) read their 1H and 4H bars, 2024-04-19 -> 2026-09-11, as
  research inputs for other methods: data/history/stability/cfd-ftmo-challenge-phase1.json and cfd-live.json at 0daadd2,
  cfd-pilot-mt5-demo.json at 2469b3c, and the CI rerun committed at b690648 (`dataset_snapshot.series`). No H7 / G9
  statistic was computed on oil.
- No read of the 1D file was found: `git log --all -S ohlcv.UKOIL` shows only 3070e2e (which added the files), the
  stability commits above, and ae9b2b7 (which regenerated them without oil).

This family follows [CX-P1] (docs/plans/2026-10-04-edge-cx-ftmo-crypto-preregistration.md) wherever it can, so that one
rule text covers both new-data transfers. Ranked second in docs/plans/2026-10-04-research-directions.md §1.

Question: the only robust edge here is intraday trend continuation on gold (H7, G9). Every transfer outside gold and
silver failed (F5 0 / 27, docs/audits/2026-10-02-edge-f5.md:6; H7x 0 / 2, docs/audits/2026-10-04-crypto-cfd-phase.md:19).
Crude oil is a macro commodity with a different driver from gold. Do H7 / G9, unchanged, earn net of FTMO's oil costs,
on windows no test has read?

## 1. Rules (FTMO server day; direction fixed = continuation; one-sided)

- H7 and G9 exactly as [CX-P1] §1, implemented once in `scripts/research/pit_trend.py`. Parameters are gold's
  (MOM_DAYS 20, VB_K 0.5; asserted equal to edge_f3 / edge_f4 in scripts/tests/test_pit_trend.py). No tuning.
- Server day: the FTMO-Demo clock (provider `mt5_bridge_ftmo`, New York + 7 h).
- **Two changes from [CX-P1], both forced by a 5-day market:**
  1. "Previous day" = the latest earlier server day that has bars (Monday's is Friday). [CX-P1] uses the calendar day
     D - 1 because crypto trades every day.
  2. A day QUALIFIES with >= floor(0.8 x the regular weekday session's 5m bars), read from the committed symbol-list
     export's `sessions_trade` (pit_trend `session_bars`). On the 2026-10-01 list: UKOIL.cash 03:05-23:50 -> 249 bars ->
     199; USOIL.cash 01:05-23:50 -> 273 bars -> 218. Fixed constants, never a data median. Older sessions may have been
     different: the dry run reports the median bars per weekday.
- Entry at the next bar's open; an event whose entry bar is not in D is dropped. Exit at the CLOSE of D's last bar. One
  event per (symbol, D, rule). Bars held = exit index - entry index + 1 (the census convention).
- The truncation probe: deleting every bar after the signal leaves the event and its inputs unchanged
  (scripts/tests/test_pit_trend.py `test_truncation_probe_event_and_inputs_unchanged`).

## 2. Universe and screens (fixed before any return is read)

- **Universe:** UKOIL (raw UKOIL.cash, server history from 2016-04-22) and USOIL (raw USOIL.cash, from 2020-12-31), per
  the symbol-list export of 2026-10-01 (sha256 be3f9a2edcdc52664ca05bda7e380b6df9de5ef3b547151008db7c79a2155831; committed
  with the screening amendment). Canonical names UKOIL / USOIL, research-only, never execution.
- Excluded now, with the reason: NATGAS.cash (history from 2024-10-23), HEATOIL.c (2024-12-11): no development window.
- **Commission c_sym** exactly as [CX-P1] §2 (FTMO's published schedule, else the symbol's own demo deals). A symbol
  without c_sym cannot be screened in.
- **Costs.** ExportSymbolSpec files for both symbols (export date and sha256 committed). Relative spread = recorded spread at
  the leg's table bucket ((server hour - export offset) mod 24) / price_ref (median M15 close over the recording window),
  the `real_costs` convention (scripts/real_costs.py:314, :426), computed by pit_trend `SpecCost` because
  scripts/real_costs.py is frozen by the Wyckoff re-test fingerprint. Every development-window net is labelled "modelled
  at the export window's spreads".
- **Cost screen (outcome-blind), [CX-P1] §2:** K = 0.5 x median over the 24 buckets of the relative spread + 0.5 x the
  relative spread at the bucket of the server day's last bar + 2 x c_sym; S = median over qualifying days before
  2024-03-01 of sigma_5m x sqrt(median hold bars of the dry run's events). Admitted iff K <= 0.5 x 0.05 x S.
- **Split and membership ([CX-P1] §2):** D* = the date by which 60 % of the pooled qualifying symbol-days before 2024-03-01
  have elapsed; members = symbols with >= 250 qualifying days in both [start, D*) and [D*, 2024-03-01). Fixed once.
  USOIL may fail membership (its history starts 2020-12-31); then the family is UKOIL alone.
- **Screening amendment**, committed before the discovery read: per symbol K, S, c_sym, min_bars, qualifying days per
  window, D*, members, the fixed EXPOSED end date, the dataset snapshot (history_store digests, spec sha256), median bars
  per weekday, the 20 largest overnight gaps in daily-SD units, power in distinct server days per read. Counts only,
  never split by side.
- **Futures-roll caution (data quality, CLAUDE.md §20).** The .cash oil CFDs follow a futures contract; a roll can shift
  the price between two server days. A trade never crosses a server day, but MOM20 and the previous day's range can
  straddle a roll. No filter is applied; the dry run lists the largest overnight gaps so the coordinator can compare them
  with the contract calendar and disclose.

## 3. Windows and reads

- One group: the members. Three reads, in order, each once, each in its own commit:
  DISCOVERY = [first bar, D*), CONFIRMATION = [D*, 2024-03-01), EXPOSED = [2024-03-01, the fixed end date].
- Grades (research-directions §0): DISCOVERY and CONFIRMATION are FRESH (no intraday oil bar of those years was ever in the
  repo). EXPOSED is UNREAD-FOR-H: the same market path, as futures 1H / 4H bars, was read by the ICT / Wyckoff stability
  runs from 2024-04-19 (§0). A read loads no bar after its window's last server day.
- The research ledger gets the OIL periods before the discovery read, with one-way state changes after each read (§44).

## 4. Measurement ([CX-P1] §4)

- r = side x (C[exit] / O[entry] - 1); scale = sigma_5m x sqrt(bars held).
- Placebo: the mean return from the same entry 5m slot to D's last bar, over eligible days of the same symbol, read, weekday
  and MOM20 sign, signed by side. Excess = r - placebo.
- Statistics: `edge_census.summarise`, cluster key = the signal's SERVER date.
- Cost per leg = half the relative spread at the leg's bucket + c_sym. Stress = the p90 spread + c_sym. No swap.
- Report-only: per symbol and year, long and short legs.

## 5. Tests and decision rule

T1 = H7 pooled over the members, T2 = G9 pooled.

| read | gate |
|---|---|
| discovery | BH over {T1, T2}, one-sided p, q = 0.10, rejects AND net > 0 -> CANDIDATE |
| confirmation | one-sided p < 0.05, net > 0, net at the p90 spread > 0 |
| exposed | one-sided p < 0.10, net > 0 |

- Each test advances independently. A test that fails a gate is closed; its later windows are retired UNREAD (the code
  computes no row for a closed rule: `edge_oil.read_rows(rules=...)`).
- A survivor is the pooled basket of the members. Its tradable form, fixed now: each member at 1 % / (number of members)
  at the stop; the read reports R per trade at stop k 1.4 and 2.0, the stop share, gap-throughs (R_net < -1.05) and the
  worst trade. A survivor with any server day beyond -5 % is not proposed.
- A survivor then goes to `book_sim compare` against fvg-book v4 (daily P&L correlation) and to the forward stage of
  docs/plans/2026-10-02-edge-followup-preregistration.md §4, before any symbol leaves research-only.
- Zero survivors is a valid result.

## 6. Power and prior

- If FTMO keeps 5m UKOIL from 2016: about 1,900-2,000 qualifying days before 2024-03-01, so ~1,150 in discovery. At
  gold-like event rates (roughly 0.35 H7 and 0.5 G9 events a day: F3 / F4 gold discovery counts 1,197 / 1,780 over about
  12 years, edge-f3.md:14, edge-f4.md:13) discovery holds roughly 400 H7 and 600 G9 events (arithmetic, not a count). If 5m starts
  later, the dry run will show it; with no discovery window, OIL becomes forward-only by amendment before any read.
- Prior: weak, ~5-10 % to survive all three reads. Time-series momentum in commodity futures is documented (Moskowitz,
  Ooi, Pedersen 2012, JFE; not verified here), but no intraday evidence is in hand and every non-precious-metal transfer
  failed.

## 7. Budget

- OIL: 2 primary tests; 3 reads. Cumulative transfers of H7 / G9: F3 / F4 origin, F5 27 tests (0 survivors), H7x 2 x 2
  (0), CX 4 (pending).

## 8. Data (owner action)

On FTMO-Demo MT5, ideally in the SAME run as B2 ([CX-P1] §8):
1. Add `UKOIL.cash,USOIL.cash` to line 2 of `Common\Files\export-list.txt` (line 1 `tf=5m,15m,1H,1D` unchanged).
2. Run `integrations/mt5/ExportHistory.mq5`; then `integrations/mt5/ExportSymbolSpec.mq5` with both names added.
3. Commission c_sym as in §2.
The importer, the canonical-instrument entries and the research-only registry entries are added when the files exist.
Sealing should precede the import; it must precede the dry run.

## 9. Sealing steps (coordinator)

1. Review; reconcile pit_trend with `scripts/research/edge_cx.py` if that file exists (one rule text for CX and OIL).
2. Commit the final code; paste `python3 scripts/research/edge_oil.py manifest` into §10; seal under the final name with
   the exact "Status: SEALED" line; ledger periods (EXPOSED window labelled UNREAD-FOR-H with the stability runs named).
3. After the export and import: `edge_oil.py dry-run --symbol-list <committed list> --end <fixed end> --out ...`, then
   `edge_oil.py screen ...`; commit both with the screening amendment.
4. Reads: `edge_oil.py run --read discovery|confirmation|exposed --screen <json> [--after <previous read json>] --out
   docs/audits/<date>-edge-oil-<read>.json`, one commit each.

## 10. Code

- `scripts/research/edge_oil.py` (split, membership, screen, reads, gates, registration guard, dataset snapshot).
- `scripts/research/pit_trend.py` (rules, placebo, SpecCost), `scripts/research/prereg_guard.py`.
- Tests: `scripts/tests/test_edge_oil.py`, `scripts/tests/test_pit_trend.py`, `scripts/tests/test_prereg_guard.py`
  (hand-built bars and temporary repositories only).
- The guard refuses a read unless every file in `edge_oil.CODE` is listed below with its current sha256, and refuses to
  write a result if the read executed a repository module not listed.

Code manifest (filled at sealing by `python3 scripts/research/edge_oil.py manifest`; empty in this draft):

```
(paste here)
```
