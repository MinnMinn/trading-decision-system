# Wyckoff W-C-long-15m: historical replication (discovery grade) on FTMO symbols never scored for it -- pre-registration DRAFT (2026-10-04) [WY-X1]

Status: DRAFT. Not sealed. Sealing = the coordinator commits this text as
`docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration.md` with "Status: SEALED" in place of this line, the code
manifest and the X0 pin (§11), after the owner's decisions in §13. Until then `scripts/research/wyckoff_wcx.py read`
refuses before it loads any data (WX `cmd_read`; test `test_the_read_refuses_before_the_seal_and_before_any_data`).
**The recommendation (§13 item 1) is NOT to run WY-X1 now.** The design stays on file for the owner's decision.

**No outcome was computed to write this.** Sources: committed records (cited); the outcome-blind counts X0 (§2, §3, §7),
run from the uncommitted draft code into the coordinator's scratchpad as a preview (`wcx_X0_fix.json`) and re-run from
committed code at sealing (§11); code (cited `file:line`); metadata (the FTMO symbol list, the cost specs).

Abbreviations. RT = the sealed re-test `docs/plans/2026-10-04-wyckoff-retest-preregistration.md` [WY-P1]; AU = its results
`docs/audits/2026-10-04-wyckoff-retest.md`; R0 / R1 = `docs/experiments/wyckoff-retest-r0/edge-wyckoff-R0.json` /
`docs/experiments/wyckoff-retest-2026-10-04/edge-wyckoff-R1.json`; WF1 = the forward draft
`docs/plans/2026-10-04-wyckoff-forward-wc15-preregistration-DRAFT.md` [WY-F1] (line cites at commit f76d6fa; another session
is editing it, so sections are cited by number); EW = `scripts/research/edge_wyckoff.py`; WX =
`scripts/research/wyckoff_wcx.py`; RD = `docs/plans/2026-10-04-research-directions.md` (at f76d6fa); L =
`docs/architecture/research-ledger.json`; IJ = `docs/architecture/instruments.json`; SL = the FTMO symbol list
`data/live/mt5-bridge/symbollist.FTMO-Demo.json` (bridge export 2026-10-01; the bridge folder is outside git).

---

## Tóm tắt (VI)

1. Ô W-C-long-15m (Spring/Shakeout long) của RT: +0.25R net, n 63, p 0.18, chưa kết luận (AU:20). WY-F1 forward chỉ
   ~11 lệnh một năm.
2. Ý tưởng WY-X1 (đọc lại đúng ô đó, không đổi gì, trên 5 mã FTMO chưa từng bị chấm cho ô này: XPTUSD, XPDUSD, US2000,
   UK100, JP225) **không đạt như kỳ vọng**: đếm (không đọc kết quả) chỉ được **58 lệnh** (44 trước 2024-03, 14 sau),
   không phải ~100.
3. Spread của bạch kim / palladium ăn ~0.9R mỗi lệnh của ô này. Các mã giao dịch được và 3 chỉ số của pool: trung vị
   0.02-0.09R, trung bình tới 0.23R (UK100); R1 thực tế 0.09R. Nếu chạy, WY-X1 phải chấm excess GỘP (trước chi phí).
   Chấm net như RT thì xác suất qua chỉ ≤ 6 %, kể cả khi edge gộp +0.5R.
4. Sức mạnh thấp hơn bản trước đã ghi. Pool này có R:R kế hoạch trung bình 4.23, nên SD mỗi lệnh ~2.1-2.8R (không phải
   1.4R). Nếu edge gộp thật bằng R1 (+0.35R): xác suất qua 0.34-0.47 (α một phía 0.10). Trượt thì gần như không nói lên
   điều gì (§7).
5. Biến thể để tăng số lệnh / tỉ lệ thắng: **hồ sơ đã commit không ủng hộ biến thể nào** (§4). Chỉ có thể ghi forward.
6. **Khuyến nghị: CHƯA chạy WY-X1** (§13 mục 1 B). Như bản nháp, không nhãn nào thay đổi gì: WF1, sổ lệnh và hai tài
   khoản đều như cũ. RD §0 đòi bằng chứng mới mới được mở lại một lớp đã bị giới hạn ở forward (RT:323); yêu cầu của anh
   là mục tiêu, không phải bằng chứng. Đọc xong thì 5 mã R2 mất vĩnh viễn vai trò bộ kiểm tra lặp lại cho Wyckoff. Nếu
   anh vẫn muốn chạy: A (chỉ để biết) hoặc A' (có hệ quả: 3 chỉ số rẻ chỉ vào WF1 khi REPLICATED).
7. Con đường thật để có nhiều lệnh hơn:
   - WF1 thêm US2000, UK100, JP225 (~11 → ~14 lệnh/năm), đọc 2 lần (12 và 36 tháng, O'Brien-Fleming, tổng α 0.10).
   - FX: server FTMO giữ lịch sử FX từ 2000 cho 20 cặp (SL). Đây là dữ liệu FRESH thật. Nếu nến 15m dày từ 2021-09 như các
     chỉ số thì có ~180 lệnh; nếu dày từ 2012 như vàng thì ~500 (nếu FX ra tín hiệu như CFD). Chưa biết cho tới khi
     export và đếm (WY-X2, đếm trước).
     Forward với FX + CFD rẻ chỉ ~50 lệnh/năm (không phải ~100). Cần anh mở lại forex cho nghiên cứu (§13 mục 7).

---

## 1. Origin, question, and how this departs from RT

- Owner, 2026-10-04, after "WY-F1 forward on 7 symbols gives ~11 events a year; 100 events take ~9 years": *"Tìm giải
  pháp phù hợp để tăng số lệnh và tỉ lệ win cao lên đi. Nếu thật sự không được thì mở rộng sang nhiều mã FTMO hơn."*
- **The cell.** W-C-long-15m read INCONCLUSIVE: n 63, net excess +0.25R, one-sided p 0.18, 95 % upper bound +0.72R
  (AU:20). Gross excess (before cost) +0.35R; realised cost 0.09R a trade (R1 `tests["W-C-long-15m"]`, `rows`). Metals
  carry it: net +0.39R (n 39) against indices +0.04R (n 24) (R1 `groups`).
- **A correction to carry.** AU:39 reports "Shakeouts +0.64 (n 14) and Springs +0.26 (n 49)". Those are mean GROSS excess
  (R1 `descriptive["desc:W-C-long-15m|SHAKEOUT"].mean_excess` 0.638, `...|SPRING` 0.263), while the pooled +0.25 beside
  them is NET. On the net line they are +0.54 (n 14, SE 0.52) and +0.17 (n 49, SE 0.33). WF1 §1 (f76d6fa :23) repeats the
  gross pair. AU and WF1 are not edited here.
- **Question.** On FTMO symbols that no committed read has scored for this cell, does the UNCHANGED W-C-long-15m trade beat
  a same-geometry random entry (RT §5's placebo excess) in the book's direction?
- **Grade: discovery, not confirmation.** The pool is UNREAD-FOR-H, "valid as discovery, with a dependence note"
  (RD:55-56). Confirmation needs forward bars (RT:245, RT:323); RD §0 puts FRESH bars, never in the repo, in the same
  grade as forward data (RD:54).
- **Not a variant.** Same detector, event, trade, placebo, cost model and statistics as RT §3.1-§3.2 and §5 (§4, §5 here).
  WX imports EW and changes nothing in it. One choice differs from RT and is disclosed in §6: the DECISION line is the
  placebo excess before cost, because these symbols' spreads would otherwise decide the test (§7).
- **A departure from RT's read plan, disclosed; the owner signs it or WY-X1 does not run (§13 item 1):**
  - RT:221 and RT:243 made exactly these symbols RT's replication set (R2), "read only for R1 survivors, so these symbols
    stay unread for Wyckoff otherwise". W-C-long-15m is inconclusive, not a survivor (AU:66-67), so RT never reads them.
  - RT:323: INCONCLUSIVE "never licenses new variants on history. Only forward bars can settle it."
  - RD:62-63: a direction whose class an earlier verdict limited to forward data "must cite that verdict and name the new
    evidence that justifies reopening it". **This draft names none.** The owner's request is a goal, not evidence about the
    effect; the X0 counts are feasibility, not evidence. Under RD §0, WY-X1 is a reopening, not a ranked direction.
  - What WY-X1 could do: test, on symbols that played no part in choosing the cell, whether R1's result was a winner's
    curse (WF1 §1, f76d6fa :27-29). It cannot settle the cell (RT:323).
  - **Consequence.** Under §13 item 1 (A) no label changes anything that is traded or collected: WF1's rule and symbols are
    sealed before the read (§11 step 7), and nothing is built or traded from WY-X1 (RT:447). Only AGAINST THE BOOK has an
    effect (it is logged for the edge families). Option (A') registers one consequence before sealing (§12.2 a).
  - A PASS reads **"REPLICATED (gross, history)"** (WX `replicated_label`): a before-cost result on history, never RT's net
    H-WC replicating.
- **Selection, disclosed (CLAUDE.md §43).** The cell is replicated BECAUSE it was the best of four confirmatory cells.
  The replication data took no part in that choice (§2).

## 2. Inventory and exposure grade for W-C-long (strict)

Grades are RD §0's (RD:47-63): FRESH (no bar in the repo, or forward data), UNREAD-FOR-H (bars read by other families,
this statistic never computed), PARTLY EXPOSED (a related cut of the same trades was read), EXPOSED (the statistic, or a
superset that determines it, was read). Checked: every Wyckoff run (RT's R0 / R1 / V / L1 / ABL records; the method
diagnosis and funnels; the prop search `docs/experiments/prop-search-2026-09-27/plan.json`; the stability snapshots
`git show 05859c4|0daadd2|2469b3c|ae9b2b7:data/history/stability/cfd-*.json` and the `3070e2e` legacy archive; the fund
search's compute calibration), the ICT and trend families (census E1-E7, F2-F6, H7x, C1, M1, AMD) and every audit that
names a symbol (grep of `docs/`). No pool symbol appears in the stability files that name their symbols: 0daadd2 /
2469b3c hold XAUUSD, XAGUSD and the oils, ae9b2b7 the eight tradeable symbols. 05859c4's rows name none; its dataset
snapshot failed on USOIL, one of the 0daadd2 symbols.

| symbol | 15m in the repo (`data/history/ftmo`) | RT §4 15m dense start (R0 = X0) | cost under `ftmo_demo_2026_09_relspread` | registry (IJ) | W-C-long-15m scored by | seen by (other statistics) | grade for W-C-long |
|---|---|---|---|---|---|---|---|
| XAUUSD, XAGUSD | 2004-06 / 2008-11 -> 2026-10-01 | 2012-04-01 | spec; recorded spreads 2022-07 -> 2026-09 | execution | R1 (AU:20) | engine WYCKOFF-BOOK (method diagnosis, funnels, prop search 2024-03 -> 2025-03, stability files incl. MetaQuotes-Demo bars at 05859c4 / 0daadd2 / 2469b3c), ABL, census, F2-F4, the H7 / G9 book | **EXPOSED** before 2024-03-01; **PARTLY EXPOSED** after (engine spring legs read; RT:244 made it veto-only) |
| US500, US30, USTEC, DE40, AUS200 | 2017-12 / 2019-02 -> 2026-09-28 (AUS200 10-01) | 2021-09 / 2019-10 / 2021-09 / 2022-01 / 2019-10 | as above | execution | R1 | as above, plus L1 (engine config A, 15m, 2024-03 -> end; RT:400-411, AU:26) | **EXPOSED** / **PARTLY EXPOSED** |
| FRA40 | 2017-12-28 -> 2026-09-28 | none (session cut 2025-01: 92 -> 56 bars a day, R0 `dense["FRA40\|15m"].months`) | as above | execution | never (no dense start) | engine Wyckoff and L1 as above | **PARTLY EXPOSED** |
| XPTUSD, XPDUSD | 2015-01-06 -> 2026-10-01 | 2017-04-01 | spec; 2022-07 -> 2026-10 | research_only | never | F5 H7 / G9 / E5 in discovery, confirmation and holdout (`docs/plans/2026-10-02-edge-f5-preregistration.md:23-26`; `docs/audits/2026-10-02-edge-f5.md:8-9`); outcome-blind counts (R0 `reads.R2`; `docs/audits/2026-10-01-cell-selection.md:3-5`). The fund search's `wyckoff-5m-metals` cell was declared (L:192-208) and never run as a search (`docs/audits/2026-10-02-strategic-diagnosis.md:154`). **But its compute calibration ran the engine's WYCKOFF-BOOK wave-1 scan and the nested wave-2 selection on XAUUSD + XPTUSD 5m, 7 folds from 2015-01-07, before 2024-03-01** (`docs/audits/2026-10-01-shard-calibration.md:42` PIT cutoff, `:647-650`, `:656`; `docs/audits/2026-10-02-shard-recalibration-data/res-wave2.jsonl:2`): outcomes were computed inside the selection, only counts and timings were kept. The dev-start decision counted the engine's admitted Wyckoff trades per year on XPT / XPD 5m (`docs/audits/2026-10-02-dev-start-decision.md:68-69`, counts only) | **UNREAD-FOR-H** (another detector and timeframe; no outcome reported) |
| US2000, UK100, JP225 | 2018-01-23 / 2017-12-28 / 2017-12-28 -> 2026-10-01 | 2018-01-01 / 2021-09-01 / 2021-09-01 | spec; 2022-05/07 -> 2026-10 | research_only | never | F5 (all three reads); counts | **UNREAD-FOR-H** |
| EU50, HK50 | 2017-12-28 / 2018-12-16 -> 2026-09-30 | none (2025-01 session cut: 92 -> 56 / 64 bars a day) | spec; 2021-09 -> 2026-09 | research_only | never | F5; counts | **UNREAD-FOR-H** |
| N25, SPN35 | 2020-11 -> 2026-09-30 | 2024-08-01 / 2021-09-01 (RT:222 excluded both on data quality) | spec; 2020-11 -> 2026-09 | research_only | never | F5; counts | **UNREAD-FOR-H** |
| XCUUSD, DXY.cash | none (only the MT5 bridge export, e.g. `data/live/mt5-bridge/history.XCUUSD.15m.json`: 41,316 bars from 2024-12-02; DXY from 2024-11-26) | none: no 2023 bars, so no reference year (EW:369-371) | none under `data/history/costs/ftmo` (the bridge holds specs with recorded spreads) | not registered; the importer refuses (`scripts/import-mt5-history.py:135-137`) | never | never read | **FRESH**, but no usable history (dropped for that reason: `docs/plans/2026-09-30-owner-decisions.md:124`) |
| FX, 28 pairs | none anywhere (repo or bridge history exports). The FTMO server holds history from 2000-03 for 20 pairs and from 2004-06 to 2010-05 for the other 8 (SL `server_first_date`); the terminal held 15m only from 2024-01-02 or later at the export (SL `first_bar_server`) | unknown until exported | 7 pairs have recorded spreads in the bridge spec exports (2022-09 ->), 21 have none | forex market removed 2026-09-27 (IJ :279); parked (`docs/audits/2026-10-04-crypto-cfd-phase.md:3, :53`) | never | never read | **FRESH**; needs an export (§12.1) |

**Partial information overlap with exposed symbols** (X0; market statistics, not trade outcomes):
- Daily close-to-close log-return correlation, FTMO 1D, 2021-09-01 -> 2026-09-26, about 1,300 days (X0 `daily_corr`).
  **Pool against exposed symbols: 0.48 (XPDUSD vs XAUUSD) to 0.85 (US2000 vs US500).** In full: XPTUSD vs XAUUSD 0.62,
  XAGUSD 0.72; XPDUSD vs XAUUSD 0.48, XAGUSD 0.53; US2000 vs US500 0.85, US30 0.83, USTEC 0.77; UK100 vs DE40 0.76, FRA40
  0.78; JP225 vs AUS200 0.60, US500 0.70. Not against exposed symbols: XPTUSD vs XPDUSD 0.67, UK100 vs EU50 0.77, HK50 vs
  JP225 0.36. Optional symbols against exposed ones: EU50 vs DE40 0.94, FRA40 0.96; HK50 vs AUS200 0.44; N25 vs DE40 0.81;
  SPN35 vs DE40 0.75.
- Event overlap (X0 `overlap`): 12 of the 58 pool events (21 %) fall in an ISO week that holds a W-C-long-15m event on an
  exposed symbol (R1's 63, plus the 29 the tradeable symbols fired after 2024-03-01); 5 (9 %) share a server day.
- So the pool is partly the same market path as R1, US2000 above all. It is not independent the way forward bars are. The
  read reports the subset outside those weeks (§6).

## 3. Pool, windows and data rules (fixed now, by grade and counts only)

- **Pool** (WX `POOL`): XPTUSD, XPDUSD, US2000, UK100, JP225 = RT's R2 symbols (EW:137-138) that have a 15m dense start
  under RT §4. All UNREAD-FOR-H. No symbol was added or dropped on anything but its grade and its dense start.
- **Not in the pool:** the eight tradeable symbols (EXPOSED or PARTLY EXPOSED); EU50, HK50 (no RT §4 dense start; §13
  item 4 offers a rule that adds them); N25, SPN35 (RT:222's exclusion stands; they add 1 and 3 events); XCUUSD,
  DXY.cash, FX (no history in the repo; §12.1).
- **Breadth groups** (WX `GROUP_OF`): metals = XPTUSD, XPDUSD; indices = US2000, UK100, JP225. RT's R2 clusters (metals,
  US, EU, Asia; EW:137-138) are reported (§6).
- **Window** (WX `WINDOW_END`): every 15m bar from the symbol's RT §4 dense start to 2026-09-26T00:00Z (a Saturday, after
  every Friday close). The series is cut there, as RT cut R1 and R2 at their end (EW:2049 `until = hi`). An event belongs
  to the read iff its ENTRY bar closes in the window (EW `in_window`, EW:521). Both periods are in, because neither was
  ever scored for this cell; the split at 2024-03-01 is reported.
- **Dense rule:** RT §4 unchanged (RT:226-235; EW `dense_start` EW:355, `dense_days` EW:396, `kept` EW:898).
- **Data pin:** X0 records, per pool symbol, the sha256 of every bar inside the window (WX `window_digest`). The read
  recomputes it and refuses on any difference (a revised bar). An export that only appends bars changes nothing (test
  `test_the_data_pin_refuses_a_revised_bar_and_ignores_an_appended_one`).
- **No overlap with WF1:** WF1's forward window starts at its own seal instant (WF1 §3), after 2026-10-04.

## 4. The cell, unchanged, and every variant the owner asked about

**The cell** = RT §3.1-§3.2 (RT:60-124): DET-PO with RT's parameters (EW `BASE_CFG` EW:186; `det_params` EW:559); the
Spring / Shakeout long event; entry at the next open; stop at the spring low -0.05 %; target `tr_hi`; cap 96 bars; the
engine walk with gap fill (EW `walk_from` EW:933). WX calls `EW.detect_series` (EW:759) with no higher timeframe:
W-C-long's event, stop and target read none (RT §3.2).

**Variants, judged on committed records only** (no new outcome on any symbol). Base (R1): net +0.25R (SE 0.28); win
rate 46 % (29 wins, 30 losses, 4 timeouts); median winning R +0.50; planned R:R median 1.68 (R1 `rows["W-C-long-15m"]`).

| idea (more trades / higher win rate) | committed record | mean net excess | trades | enters WY-X1? |
|---|---|---|---|---|
| more symbols, same rule | -- | -- | +58 history; +5.4 a year forward, of which 2.3 on the three cheap indices | **this study** (not a variant) |
| nearer target, partial target, break-even | **none.** R1 rows carry R, outcome and planned R:R, not the price path (their `path` field is the engine label "spring"; no MFE / MAE). Scoring one = a new outcome on R1's window (RT:323) | unknown | same | **no**: forward log only (§12.2 c) |
| Phase-B ceiling target (farther) | R1 `desc:W-C-long-15m\|ceiling-target` | +0.06 | same | no: worse |
| flatten before the rollover | R1 `desc:W-C-long-15m\|flatten` | +0.13 (SE 0.24 vs 0.28) | same | no: the mean falls (see §8, personal account) |
| Shakeout only | R1 `\|SHAKEOUT` vs `\|SPRING` | +0.54 (n 14) vs +0.17 (n 49); not significant | -78 % | no: cuts trades, unsupported |
| Wyckoff HTF context | W-CTX (AU:35) | -0.34 (n 18, all timeframes) | -70 % | no: against |
| ICT HTF gate | ablation A3 (`docs/experiments/wyckoff-retest-2026-10-04/ablation-report.md`, A3 spring 15m) | engine springs +0.18 vs -0.13 (n 162 of 1,069) | -85 % | no: another detector, one of 78 post-hoc cells (AU:57-58) |
| 1H / 4H | AU:32-33 | -0.42 (n 26) / -0.70 (n 5) | | no: against |
| short side (UT / UTAD) | AU:36 | -0.22 / -0.50 / -0.56 | | no: against |

**Result: the committed records support no variant.** WY-X1 has one hypothesis (WX `HYPOTHESES`); Holm with m = 1 is
the plain one-sided test. A higher win rate only helps if the mean R does not fall; for an FTMO challenge a smoother
equity at EQUAL mean raises the pass probability, but no recorded variant keeps the mean. Unsupported variants can only be
logged forward and tested on later forward bars (§12.2).

## 5. Measurement: RT §5, unchanged

- **Score:** EW `score` (EW:999): gross R from the walk; the ATR-multiple placebo (up to 200 bars of the same series,
  window, server slot and side, previous day dense; seed sha256("WY-P0|sym|tf|signal_time"); EW:952, `Series.pool`
  EW:527); excess = R - mean placebo R, both gross; net = excess - cost. EW `walk_opts` (EW:920): gap fill on, no
  management, no flatten.
- **Cost:** EW `Pricer` (EW:961) with `ftmo_demo_2026_09_relspread` (`scripts/real_costs.py:107-115`), server-table hour
  frame, asserted by both `counts` and `read` (WX `counts`, `cmd_read`). Four lines: {median, p90 spread} x {today's swap,
  zero swap}. Commission 0 / UNKNOWN (RT:265).
- **Cost profile per new symbol: none is missing.** All five have a spec under `data/history/costs/ftmo` mapped by
  `symbol-map.json` (XPTUSD, XPDUSD, US2000.cash, UK100.cash, JP225.cash; recorded M15 spreads 2022-05/07 -> 2026-10-01,
  24 hourly buckets, swap in points) and a `price_ref` from their committed 15m history.
- **Statistics:** EW `summarise` (EW:1179): CR1 by ISO week of the signal bar, Student-t with G - 1 df, one-sided. The
  gross line is the same call with a zero-cost line (WX `with_gross`), so all five lines come from one function.
- **Pins (the read refuses on any, before it loads market data unless noted):**
  - the sealed text, its code manifest (prereg_guard) and its `x0-sha256` line for X0 (WX `_require_x0`);
  - the ledger entry (WX `_require_ledger`) and clean `scripts`, `docs/architecture`, `data/history/costs` trees,
    untracked files included (WX `_require_clean_trees`, as EW `_require_clean_trees` EW:1443);
  - an R0-pinned file (EW CODE without its tests, WX `R0_PINNED`) that differs from R0 `meta.code_sha256` (WX `r0_drift`);
  - a cost table, or an EXTRA_CODE file, that differs from its blob at R0's commit (WX `cost_drift`, `blob_drift`).
    EXTRA_CODE is `scripts/method_purity.py`: `scripts/htf_context.py:48` loads it by file location at import, outside
    `sys.modules`, so EW's `_loaded_code` never saw it (found by test `test_a_traced_read_path_executes_only_code_files`).
    It equals R0's blob today;
  - after loading: a window digest that differs from X0's (data pin), and a real_costs price reference (median close over
    each spec's spread recording window, `real_costs.price_ref_info`) that differs from X0's (price pin);
  - at the end: a repository .py file executed outside the manifest (prereg_guard `require_covered`).
  EW's tests are left out of the R0 pin: one of them was edited after every re-test read (the test-file note another
  session added to AU), and no test runs in a read.

## 6. The read (once) and the pass rule

- **Once.** `python3 scripts/research/wyckoff_wcx.py read --counts docs/experiments/wyckoff-wcx/wyckoff-wcx-X0.json --out
  docs/experiments/wyckoff-wcx/wyckoff-wcx-X1.json`. It refuses any other output path, an existing file, or a path with
  git history (WX `cmd_read`).
- **The decision line** (WX `DECISION`; §13 item 2): **the placebo excess before cost ("gross")**. Why: the outcome-blind
  entry-hour spread proxy (§7) is about 0.9R a trade on XPTUSD / XPDUSD, ten times R1's realised 0.09R. On RT's net line a
  real effect as large as +0.5R gross would still pass with probability of about 6 % at most (§7). A net test here would
  measure the platinum-group spread, not the Spring. Tradeability is a per-symbol question for the forward stage (§8,
  §12.2). This choice was made after seeing that cost proxy, which reads no outcome.
- **REPLICATED (gross, history)** iff both:
  1. Holm (m = 1): one-sided p ≤ **alpha = 0.10** on the decision line (WX `ALPHA`, `holm`; Holm's "≤", as EC `bh`;
     §13 item 3);
  2. breadth = RT §6.2 item 3 (RT:301; EW:1282-1284) on the decision line: metals and indices each hold >= 20 events and
     each has a mean > 0. X0 gives metals 30, indices 28 (WX `breadth_groups`).
  Under the "net" option (RT's H-WC statistic) the label is "REPLICATED (net, history)" and a third gate applies: net > 0
  on all four cost lines (RT §6.2 item 2).
- **AGAINST THE BOOK** iff two-sided p < 0.05 with a negative mean: price continued through the shake. Logged for the
  edge families, as E1 / E3 on metals.
- **NOT REPLICATED** otherwise. It reads "not shown", never "no edge".
- **Reported, never decisive:** RT's four net lines (pooled, per group, per symbol: the tradeability view); the 95 %
  upper bound and "below delta 0.20R"; RT's R2 cluster rule (EW:1294, WX `breadth`); the split before / after
  2024-03-01; per symbol, group and type; the subset outside exposed-symbol event weeks (§2); the trend-matched placebo;
  RT §3.7's flatten and ceiling variants; win rate and outcome mix; truncated walks.
- **Why alpha 0.10:** it is the cell's own forward bar (RT:245 R4; WF1 §7). Under (A) a PASS moves nothing (§1); under
  (A') it widens WF1's pool, which only adds forward data that WF1 itself must still pass. 0.05, the house confirmation
  bar (F5's), is the alternative.

## 7. Counts and power (counts only, X0)

**Counts** (placeable events = previous server day dense, entry open strictly between stop and target):

| symbol | dense start | symbol-years to 2026-09-26 | events before 2024-03-01 | after | per year (after) | Spring / Shakeout | entry-hour spread proxy, R (median / mean) |
|---|---|---|---|---|---|---|---|
| XPTUSD | 2017-04-01 | 9.5 | 12 | 5 | 1.9 | 13 / 4 | 0.66 / 0.95 |
| XPDUSD | 2017-04-01 | 9.5 | 10 | 3 | 1.2 | 10 / 3 | 0.54 / 0.91 |
| US2000 | 2018-01-01 | 8.7 | 8 | 2 | 0.8 | 7 / 3 | 0.06 / 0.12 |
| UK100 | 2021-09-01 | 5.1 | 9 | 2 | 0.8 | 9 / 2 | 0.09 / 0.23 |
| JP225 | 2021-09-01 | 5.1 | 5 | 2 | 0.8 | 4 / 3 | 0.06 / 0.07 |
| **pool** | | 37.8 | **44** | **14** | **5.4** | 43 / 15 | 0.26 / 0.56 |

- The pre-2024 counts equal R0's R2 counts exactly (R0 `reads.R2["W-C-long-15m"].by_symbol`: 12, 10, 8, 9, 5). X0 also
  reproduces R0's R1 and R3 counts on the tradeable symbols and R0's dense starts (X0 `r0_crosscheck` = []); no R0-pinned
  file drifted (`r0_code_drift` = []).
- 58 events in 54 ISO weeks; the week-clustering bound gives n_eff 51.
- Planned R:R at the entry open: median 2.77, mean 4.23 (R1: 1.68 / 2.39).
- Truncation probe: 64 events (pool and optional symbols) re-detected on the series cut at the signal bar, 0 violations.
- **The spread proxy** (X0 `spread_r_entry`): the round-trip spread priced at the ENTRY hour (median spread, no night), in R
  of the planned stop, a cost known at the entry (`real_costs.mean_spread_r`'s convention: "a COST figure, not a result").
  For comparison (medians / means): XAUUSD 0.02 / 0.03, XAGUSD 0.04 / 0.06, US500 0.04 / 0.04, US30 0.02 / 0.03, USTEC
  0.03 / 0.03, DE40 0.02 / 0.05, AUS200 0.06 / 0.07. On the tradeable symbols and the pool's indices, medians run
  0.02-0.09R and means up to 0.23R (UK100). R1's realised mean cost was 0.09R.

**Planning SD of the excess per event** (WX `SD_PLAN`). RT §8's rule is SD ≈ √(mean planned R:R) (RT:423). At this pool's
4.23 that is 2.06R. R1 measured 2.09R at a mean planned R:R of 2.39, i.e. 1.35 times its rule (R1 `rows`); the same ratio
here gives 2.8R. So the table uses **2.2R** (WF1 §9's upper value, about RT §8's rule) **and 2.8R**. RT §8's 1.4R belongs
to a planned R:R near 1.9 and does not apply to this pool.

**Power** (WX `power_t`, `pass_power`; X0 `power`; one-sided; df = G - 1 = 53). P(REPLICATED) includes the breadth gate:

| alpha | SD | MDE at 80 % | P(REPLICATED), true gross mean +0.25R / +0.35R (R1's) / +0.50R | at 0 (false pass) |
|---|---|---|---|---|
| 0.10 | 2.2 | 0.62 | 0.31 / 0.44 / 0.64 | 0.09 |
| 0.10 | 2.8 | 0.79 | 0.25 / 0.34 / 0.50 | 0.09 |
| 0.05 | 2.2 | 0.73 | 0.20 / 0.31 / 0.51 | 0.05 |
| 0.05 | 2.8 | 0.93 | 0.16 / 0.23 / 0.37 | 0.05 |

At RT §8's own 2.06R and alpha 0.10 (WX `pass_power` on the same 30 / 28 events): 0.33 / 0.47 / 0.68.

- **Under RT's net line** (the §13 item 2 alternative), with each group's mean spread proxy subtracted (metals 0.93R,
  indices 0.15R; swap and the p90 lines would lower it further): P(REPLICATED) at a gross +0.25 / +0.35 / +0.50R is
  0.006-0.012 / 0.015-0.024 / 0.046-0.056 at alpha 0.10 (SD 2.2-2.8; X0 `power.pass_with_breadth.net_at_cost_proxy`).
  The net design cannot pass on this pool.
- **What it means.** WY-X1 detects a gross effect of about +0.6 to +0.8R with 80 % power. If the effect is R1's +0.35R gross
  it replicates with probability 0.34-0.47 at alpha 0.10 (SD 2.8 to 2.06). A smaller true effect (a winner's curse) most
  likely reads NOT REPLICATED, which reads "not shown", never "no edge". A miss therefore says little.
- **Not comparable with WF1 §9.** WF1's powers are for the NET line, on tradeable symbols, on forward bars. WY-X1 answers
  another question (does the Spring predict, before cost, on other symbols, on history).

## 8. What a result means on the two account layers

**Nothing is traded from WY-X1.** Both layers below are descriptive replays on already-read history, never validation
(the convention of `scripts/research/book_sim.py:2-3`).

**FTMO challenge layer.**
- The existing replay: `scripts/research/fvg_book_sim.py` `replay` (:74-102): a challenge starts every Monday; fixed risk r
  of the initial balance per trade; fail at equity <= 90 % or a server-day loss >= 5 %; pass at +10 % (Phase 1) / +5 %
  (Phase 2) with >= 4 trading days (:15-18). `scripts/research/book_sim.py compare` adds a component to the baseline book
  on the common span and reports its daily-R correlation (:7-12). `scripts/research/pass_policy.py` gives P(funded) on
  historical starts and a block bootstrap with a 50 % haircut (:1-13).
- **How a PASS is carried there:** it is not, by itself. The account sees net R = gross R - cost, not the placebo excess.
  The rows that matter are the TRADEABLE ones: R1's rows (tradeable symbols, exposed history) now, and WF1's forward rows
  later. Under (A') the three cheap pool indices join WF1's forward pool on a PASS; their X1 history rows could enter the
  replay only if the owner allowlists them after a WF1 pass. Each row carries entry and exit times and the server day: the
  input `replay`, `book_sim compare` and `pass_policy` take.
- **PGMs are not tradeable for this cell on FTMO**, whatever WY-X1 says: about 0.9R of spread a trade (§7).
- **What to expect, plainly:** W-C-long-15m fires about 11 times a year on the tradeable symbols, about 14 with the three
  cheap pool indices. At +0.25R net and 1 % risk that is about +3.5 % a year: the cell alone cannot reach a +10 % Phase-1
  target inside the replay's 120-weekday horizon. Its only FTMO role is a low-frequency component that may lower the
  book's correlation.
- **Registry:** the pool symbols are `research_only` (IJ:98; "never on execution or backtested",
  `docs/plans/2026-09-30-owner-decisions.md:132`). Trading one needs an owner registry decision after a forward pass
  (RT:447), never after WY-X1 alone.
- **NOT REPLICATED / AGAINST:** no change to the book. WF1 continues exactly as sealed (§12.2 d).

**Personal 5,000 USD layer** (`scripts/research/personal_account.py`).
- Its scope is INTRADAY rows from `book_sim.trades`, flat before the server rollover: no swap, no weekend gap
  (`scripts/research/personal_account.py:11-13` at b818e99). A W-C-long-15m trade holds up to 96 bars with swap paid
  (RT:118-122). Its rows cross the rollover, so they are outside the replay's v2 conditions.
- **How a PASS would be carried:** either (a) the flatten variant's rows, which fit v2 now but are a weaker trade
  (R1 +0.13 vs +0.25 net); or (b) an extension of the replay's conditions to multi-day rows (swap in money per night,
  weekend gap risk) in `docs/plans/2026-10-04-personal-account-backtest-design.md`, owned by the personal-account session.
  Per trade it needs: symbol, side, entry and exit times, entry, stop (the stop width in bp sizes the lot at today's
  price), net R. The minimum lot then decides skips: 1 % of 5,000 USD is 50 USD at the stop, under the owner's fixed
  100 USD minimum-lot cap (commit b818e99). Only tradeable, cheap symbols belong there. Not run here.

## 9. Threats to validity

1. **Shared market path.** Daily-return correlation 0.48-0.85 with exposed symbols; 21 % of events share a week with an
   exposed event (§2). The exposed-week-free subset is reported.
2. **Not pristine.** F5 read these bars for trend and FVG statistics, and the fund search's calibration ran the engine's
   Wyckoff selection on XPTUSD 5m (UNREAD-FOR-H, §2). This design was written knowing R1's group pattern (metals strong);
   the pool is every R2 symbol with a dense start, so no per-symbol choice was made.
3. **Winner's curse** in R1 (best of four cells): what WY-X1 tests.
4. **Power** (§7): a miss says little.
5. **The decision line** is gross, chosen after an outcome-blind cost proxy. It answers "does the Spring predict?", not
   "would it have paid on these symbols?". The net lines are reported beside it.
6. **Costs.** The 2022-2026 spread tables are rescaled to 2017-2021 by price (relspread); today's swap stands in for
   history (the zero-swap lines guard it); commission unknown. The proxy prices both halves at the entry hour.
7. **The departure from RT and RD §0** (§1). The owner signs it before sealing, or WY-X1 does not run.
8. **Data:** XPT / XPD's 124-day hole of 2016 lies before their dense start (2017-04); UK100 / JP225 are dense only from
   2021-09. Walks of events entering in the window's last 96 bars are cut at its end (reported, as in R1).
9. **No interim look can be ruled out technically:** the bars are on disk. Only procedure protects the read.
10. **The read must run soon after the seal.** WX runs the working tree, not a sealed extract as WF1 does (WF1 §5). Any
    later edit to an R0-pinned file (IJ, `scripts/real_costs.py`, ...) or to a cost table blocks the read until reverted.

## 10. Budget (CLAUDE.md §43) and OOS exposure (§44)

- **This study:** +1 candidate of the re-test's H-WC: "two experiments testing the same hypothesis on different data are
  one hypothesis and two candidates" (L:11). The hypothesis count is counted by text (L:11): the gross decision line makes
  it +1 hypothesis ("W-C-long-15m beats the placebo BEFORE cost"); under the net option (§13 item 2 B) it is +0. 0
  parameter searches, 1 read, 0 variants. The rejected ideas are §4.
- **Dataset reuse:** the pool's 15m bars were read by F5 (3 rules x 3 reads) and counted outcome-blind by R0, the cell
  selection and X0; XPTUSD's 5m bars by the fund search's calibration (§2). WY-X1 is their first W-C-long outcome read.
- **Cumulative, disclosed:** RD §4 lists F2-F5's 153 tests on 17 CFDs, AMD 24, hold 9, F6 / F7 16, M1 5, H7x 4, C1 4,
  C1b 1, and the re-test's 7 confirmatory cells; WF1 adds 1 and WY-X1 adds 1.
- **Exposure after the read:** the pool's 15m bars from each dense start to 2026-09-26 become EXPOSED for W-C-long (and for
  any Wyckoff Phase-C statistic). They can never confirm this cell again, and RT's replication set is gone.
- **Ledger entries** (the coordinator, in the commit after the seal; L is outside the code manifest; the read refuses
  without it, WX `_require_ledger`):
  ```json
  "wyckoff_wcx_replication": {
    "preregistration": "docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration.md",
    "x0_counts": "docs/experiments/wyckoff-wcx/wyckoff-wcx-X0.json",
    "parent": "wyckoff_retest: W-C-long-15m INCONCLUSIVE (docs/audits/2026-10-04-wyckoff-retest.md:20)",
    "grade": "discovery (pool UNREAD-FOR-H, RD §0)",
    "hypotheses": ["W-C-long-15m placebo excess before cost"], "candidates": 1, "holm_m": 1,
    "alpha_one_sided": 0.10, "decision_line": "gross placebo excess",
    "pool": ["XPTUSD", "XPDUSD", "US2000", "UK100", "JP225"], "window": [null, "2026-09-26T00:00:00Z"],
    "consequence": "<§13 item 1: A = none; A' = US2000, UK100, JP225 join WY-F1's pool on REPLICATED (gross, history)>",
    "departure": "RT:243 reads R2 symbols only for R1 survivors; RT:323 forward only; RD:62-63 no new evidence. Owner override <date, quote>.",
    "owner_signoff": "<§13 answers>"
  }
  ```
  At the read, in the commit that adds X1: an `exposures` entry (trigger `candidate_selection`) for the pool's window.
- **A ledger gap found while grading (not fixed here):** `cfd-development-pre-2024-03` (L:148) names XPTUSD / XPDUSD for
  the fund search, but not the seven research-only indices F5 read in the same period (F5 pre-registration :23-25).

## 11. Sealing steps (coordinator; only if §13 item 1 is A or A')

1. The owner answers §13.
2. Commit WX, its tests and this draft. From `scripts/tests`: `PYTHONPATH=.. python3 -W ignore -m unittest test_wyckoff_wcx`
   (47 tests, synthetic bars only; they pass before the seal, after it and after the read).
3. From the committed code: `python3 scripts/research/wyckoff_wcx.py counts --out docs/experiments/wyckoff-wcx/wyckoff-wcx-X0.json`
   (about 10 minutes). Check `r0_crosscheck` = [], `r0_code_drift` = [], the probe (0 violations) and `price_ref` for the
   five pool symbols. Commit X0.
4. `python3 scripts/research/wyckoff_wcx.py manifest` (it refuses if an R0-pinned or EXTRA_CODE file drifted). It prints
   the `code-sha256 ...` lines and, once X0 exists, the `x0-sha256 <sha> docs/experiments/wyckoff-wcx/wyckoff-wcx-X0.json`
   line. Paste them all here.
5. Copy this file to the sealed name with "Status: SEALED", the manifest lines, the x0-sha256 line and the §13 answers.
   Commit.
6. Ledger entry (§10), in the next commit. The read refuses without it.
7. **Order with WF1:** seal WF1 BEFORE the WY-X1 read. WF1's symbols and read rule must not be chosen after seeing
   WY-X1's result (§12.2 d). Under (A') WF1's sealed text carries the conditional rule of §12.2 (a).
8. Read once (§6), soon (§9 item 10), from clean trees. Commit X1 and write `docs/audits/<date>-wyckoff-wcx.md`.

## 12. Proposals (not done here)

### 12.1 Missing pieces, symbol by symbol

- **Pool:** nothing missing (canonical ids IJ `canonical`; specs, symbol map and 15m history committed at bf69cc0).
- **EU50, HK50:** a dense-rule decision (§13 item 4). The code supports it (WX `ALT_POOL`, `alt_dense_entry`).
- **N25, SPN35:** nothing technical; RT:222's exclusion and 4 events make them not worth a rule change.
- **XCUUSD, DXY.cash** (each step an owner or coordinator change; none done):
  1. canonical ids and `research_only` entries in IJ (the importer refuses anything not on the allowlist);
  2. `python3 scripts/import-mt5-history.py --write --provider mt5_bridge_ftmo --symbol-map data/history/costs/ftmo/symbol-map.json --dest-root data/history/ftmo XCUUSD`
     (and DXY);
  3. copy the bridge's `symbolspec.XCUUSD.json` / `symbolspec.DXY.cash.json` into `data/history/costs/ftmo` and add the
     `symbol-map.json` entries;
  4. a dense reference year (no 2023 bars).
  Under three years of history: forward only.
- **FX, 28 pairs:** the owner un-parks forex for research only (no trading); ExportHistory 15m for the 28 pairs, as deep
  as the server serves (SL `server_first_date`: 2000-03 for 20 pairs); IJ forex market and canonical ids; import; specs
  (7 pairs have recorded spreads in the bridge exports, 21 need a spread export); then **WY-X2 counts first**: RT §4's
  dense rule and X0-style outcome-blind counts, before any pre-registration. These bars would be FRESH (RD:54), and FX
  majors are FTMO's cheapest class (`docs/audits/2026-10-02-edge-f5.md:21`).
- **Sequencing (all of the above).** IJ and `symbol-map.json` edits (XCU steps 1 and 3; the FX registry, import and specs)
  come **after WF1's seal** (WF1 §5 pins both to R0 at its sealing; after the seal WF1 runs from its extract) **and after
  the WY-X1 read if it runs** (WX `r0_drift` pins IJ to R0, `cost_drift` pins `symbol-map.json` to R0's blob; both are
  checked at read time). Under §13 item 1 (B) only WF1's seal constrains them. The FX bridge export itself edits nothing
  in the repository and can run now.

### 12.2 WY-F1 (proposal only; WF1 is a draft another session is editing; nothing edited here)

- **(a) More symbols, same rule, cheap ones only.** WF1 decides on RT's NET line, so a symbol whose spread eats the edge
  lowers its power. Add US2000, UK100 and JP225 (spread proxy 0.06-0.09R median, 0.07-0.23R mean); leave out XPTUSD and
  XPDUSD (about 0.9R). X0 gives those three 2.3 events a year after 2024-03-01: WF1 goes from about 11 to about 14 a year.
  Under §13 item 1 (B) or (A): add them unconditionally (**recommended**). Under (A'): WF1 logs them from its seal, and they
  enter its decision pool only on REPLICATED (gross, history); that costs WF1 power, because WY-X1 misses a real +0.35R
  effect 53-66 % of the time and WF1 then runs on 7 symbols instead of 10.
  UK100 and US2000 already have live 15m bridge files (`data/live/mt5-bridge/ohlcv.UK100.cash.15m.json`,
  `ohlcv.US2000.cash.15m.json`); JP225 needs ExportOHLCV attached to a 15m chart (as AUS200, WF1 §12 step 4). If §13
  item 4 adopts the reference-2025 dense rule, HK50 (proxy 0.08R) and FRA40 (0.03R median) add about 1.6 a year (X0
  `alt_dense`); EU50 (0.41R mean) is borderline.
- **(b) The read rule: two looks, O'Brien-Fleming.** Look 1 at seal + 12 months, look 2 at seal + 36 months; Lan-DeMets
  O'Brien-Fleming-type spending, one-sided alpha 0.10 in total (WX `obf_spend`, `two_look`): look 1 passes at nominal
  one-sided p < 0.0044 (z 2.62), look 2 at p < 0.0986 (z 1.29). Information fraction 1/3 assumes a steady event rate.
  Power on the net line (normal approximation, WX `two_look_power`; single looks with the t, WX `power_t`), at WF1 §9's
  planning SDs. R1's measured net SD was 2.03R (R1 `rows`), so the 2.2 rows are the realistic ones:

  | events a year | SD | +0.25R: 12 m only / 36 m only / two looks (P stop at look 1) | +0.50R: same |
  |---|---|---|---|
  | 11 (7 symbols, today) | 1.4 | 0.23 / 0.40 / 0.40 (0.02) | 0.43 / 0.78 / 0.79 (0.08) |
  | 11 | 2.2 | 0.17 / 0.26 / 0.27 (0.01) | 0.28 / 0.51 / 0.52 (0.03) |
  | 14 (+ US2000, UK100, JP225) | 1.4 | 0.25 / 0.44 / 0.44 (0.02) | 0.49 / 0.83 / 0.84 (0.10) |
  | 14 | 2.2 | 0.19 / 0.28 / 0.29 (0.01) | 0.31 / 0.56 / 0.57 (0.04) |
  | 15 (+ HK50, FRA40 under §13 item 4 B) | 1.4 | 0.26 / 0.46 / 0.47 (0.03) | 0.51 / 0.87 / 0.87 (0.11) |

  The two-look rule keeps the 36-month power and adds an early exit for a large edge; WF1's registered rule (A) has the
  12-month power. Spending 0.0044 at 12 months costs almost nothing.
- **(c) Log, never test, the unsupported variants.** At each resolve, also log MFE and MAE in R, bars to MFE, the ICT HTF
  gate flag at the signal (`scripts/backtest-methods.py:894` `htf_bias_gate`, applied at :1641 when `OPTS["htf"]` is on:
  the ablation's A3 arm, `scripts/research/wyckoff_ablation.py:152`), the planned R:R and the entry-hour spread. A later target
  or gate variant can then be pre-registered on these fields and read on LATER forward bars only.
- **(d) Sequencing.** Seal WF1 before WY-X1's read. After WY-X1, WF1's rule never changes; the owner may still stop
  collecting (that only loses power).

### 12.3 What "more trades" can honestly mean for this cell

- **Rate.** After 2024-03-01 the cell fires about 1.2-1.4 times per cheap symbol-year (X0: the 7 tradeable symbols with a
  dense start plus US2000, UK100, JP225 gave 35 events in 2.57 years, 1.36 a symbol-year; 1.24 with SPN35's 0).
- **Forward, CFDs only.** The tradeable symbols give 11.3 a year. All 17 FTMO CFDs give about 17 a year under RT §4's dense
  rule (19.5 with the reference-2025 rule), of which the PGMs' 3.1 cannot be traded at their spread.
- **Forward, with FX.** 28 pairs plus about 13 cheap CFDs is about 41 symbols: about **50 a year** if FX fires like the
  CFDs, i.e. 100 events in about 2 years. Unknown until counted. 100 a year would need about 75-80 cheap symbols.
- **History, with FX: the only large sample.** FX bars are FRESH (none in the repo). The server holds FX history from
  2000-03 for 20 of the 28 pairs (SL). Its dense 15m span is unknown: the metals' 15m exports reached their server first
  date (XAUUSD 2004-06-11), but the indices' 15m bars are sparse until 2021-09 although their server history starts in
  2017-12. At 1.3 events per symbol-year, a dense start in 2021-09 (like the indices) would give about 180 events on 28
  pairs; one in 2012 (like XAUUSD's 15m) about 500. Either beats WY-X1's 58, on FRESH data. FX majors are FTMO's cheapest
  class, so the net line might decide; the counts' entry-hour spread proxy will say (21 pairs first need a spread export).
  Caveat: FX is another asset class than the one the cell was found on; a miss there would not refute it on metals. Hence
  WY-X2 counts first (§12.1), then a pre-registration the owner signs (it too departs from RT:323's "forward bars").
- No variant changes this within the records (§4).

## 13. Open decisions (owner, before sealing)

1. **Run WY-X1?**
   - (A) "Yes, informational (discovery grade): one historical read of the UNCHANGED cell on the five unread symbols,
     departing from RT:243 (R2 only for survivors), RT:323 (only forward bars settle it) and RD:62-63 (no new evidence).
     No label changes WF1, the book or either account; AGAINST THE BOOK is logged for the edge families."
   - (A') "Yes, with a registered consequence: US2000, UK100 and JP225 enter WF1's decision pool only on REPLICATED (gross,
     history); WF1 logs them from its seal either way and its sealed text carries this rule." Costs WF1 power (§12.2 a).
   - (B) "No, not now. RT:243 and RT:323 stand; R2's 15m bars stay unread for W-C-long; WF1 adds the three indices
     unconditionally (item 6); the large historical sample comes from FRESH FX (item 7)." **Recommended.** Why:
     (i) under (A) the read changes nothing, and (A') trades WF1 power for a weak gate;
     (ii) RD:62-63 asks for new evidence before reopening a class limited to forward data, and there is none;
     (iii) power 0.34-0.47 at R1's gross +0.35R (SD 2.06-2.8), so a miss says little and a pass is discovery grade;
     (iv) the read spends RT's replication set for good (§10);
     (v) the gross line is needed only because of the PGM spreads.
2. **The decision line** (only under A or A'):
   - (A) the placebo excess before cost ("does the Spring predict?"), with RT's four net lines reported. **Recommended**:
     on this pool a net test measures the PGM spread (§7).
   - (B) RT's net line (H-WC), with net > 0 on all four cost lines: P(REPLICATED) at most about 6 % even at a gross +0.5R
     effect.
   - (C) (A) plus a disclosed net veto on RT's own R3 window, as RT:244 does for survivors: the tradeable symbols,
     2024-03-01 -> 2026-09, 29 events (FRA40 none: no 15m dense start), PARTLY EXPOSED, entry-hour spread 0.02-0.06R
     median. A gross PASS is vetoed if R3's mean net excess is <= 0. It guards against a PASS driven by the PGMs, but at
     29 events a real +0.25R net effect is vetoed about a quarter of the time, and it reads RT's R3 window for a
     non-survivor. **Not coded:** it needs a WX change and new tests before sealing.
3. **alpha** (one-sided; only under A or A'):
   - (A) 0.10, the cell's forward bar (RT:245, WF1 §7). **Recommended.**
   - (B) 0.05, the house confirmation bar. At R1's gross +0.35R, P(REPLICATED) falls from 0.34-0.44 to 0.23-0.31
     (SD 2.8-2.2).
4. **EU50 and HK50** (only under A or A'):
   - (A) "Keep RT §4's dense rule": they stay out; 58 events. **Recommended** for WY-X1: the replication keeps R1's
     eligibility rule, and EU50 is 0.94-0.96 correlated with DE40 / FRA40.
   - (B) "Reference year 2025 for series whose session FTMO cut in 2025-01": EU50 (6) and HK50 (9) join: 73 events; HK50 is
     the least correlated symbol, with no event in an exposed week. Code: `ALT_POOL = ("EU50", "HK50")` in WX, re-run X0.
     The same rule would give FRA40 a 15m start in WF1 (WF1 §14 item 2).
5. **N25, SPN35:** (A) keep RT's exclusion (**recommended**; 4 events) or (B) add them.
6. **WY-F1** (§12.2): add US2000, UK100, JP225 (not the PGMs), unconditionally unless item 1 is (A'); the two-look
   O'Brien-Fleming rule; the extra resolve fields; seal WF1 before any WY-X1 read. **Recommended.**
7. **FX:**
   - (A) un-park forex for research only (no trading): export FX 15m history for the 28 pairs as deep as the server serves,
     register and import it after WF1's seal and after any WY-X1 read (both pin IJ and `symbol-map.json`; §12.1), and
     count WY-X2 outcome-blind before any pre-registration. The bridge export itself can run now.
     **Recommended**: it is the only route to a large FRESH sample of this cell now, and to about 50 forward events a year.
   - (B) keep it parked.

## 14. Code and tests

- `scripts/research/wyckoff_wcx.py` (WX):
  - `counts` (X0, outcome-blind): dense table, events by period / type / year, symbol-years, R0 cross-check and code
    drift, exposed-event overlap, daily correlations, the reference-2025 rule's counts, the entry-hour spread proxy (it
    asserts the server-table hour frame first), the truncation probe, power and pass probability (gross, and net at the
    cost proxy), and each pool symbol's price reference;
  - `read` (X1, once, guarded by `scripts/research/prereg_guard.py`: sealed text, committed code and counts, the code
    manifest, the x0-sha256 pin, the ledger entry, clean trees, the R0 code pin, the R0-commit blobs of the cost tables and
    of EXTRA_CODE, the data and price pins, executed-code coverage); `report` (markdown); `manifest` (the code-sha256
    lines and the x0-sha256 line; refuses on R0 or blob drift).
  - EW is imported, never modified.
- `scripts/tests/test_wyckoff_wcx.py`, synthetic and hand-built bars only (47 tests), lifecycle-proof (no test depends on
  the seal state, so the pinned file never needs an edit after sealing): registration (cell, measurement, decision line and
  labels, SD_PLAN, pool, clusters, code list incl. EXTRA_CODE, window, the draft is not sealed); a fresh interpreter traces
  the read path from before the imports and finds only CODE files; counts (events equal `EW.detect_series`, no outcome key
  anywhere, no walk and no exit-dependent cost, the price reference, the hour-frame refusal, window and split, the data
  pin, overlap, correlation, the R0 cross-check, the ALT pool); the truncation probe (passes; a next-bar look-ahead is
  caught; an empty probe is not a pass); the pins (cost and EXTRA_CODE blobs byte for byte; the x0 line); the read guard in
  a temporary root (refuses before the seal; every pre-data check refuses before any bar is loaded; the ledger; a revised
  bar and a revised price reference refuse, an appended bar does not; the counts-record checks); the read core on
  synthetic bars (RT §5 rows, the gross and net lines, cut at the window end); verdicts under both decision lines, Holm
  (incl. its boundary), breadth (RT gate 3 and RT's R2 rule); power (reproduces WF1 §9), the O'Brien-Fleming spending and
  boundaries, the bivariate normal, the pass probability.
