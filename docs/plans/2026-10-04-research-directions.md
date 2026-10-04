# New research directions for the FTMO CFDs and the personal account (2026-10-04)

**Type:** research-direction document. Owner, 2026-10-04: "càng có nhiều hướng nghiên cứu mới càng tốt". It changes no code
path, config, account, assignment or demo behaviour. **Market data read for this document: none.** New facts come from
committed audits (cited), from code (cited by file:line), from calendar arithmetic (NYSE holidays, no prices), and from the
FTMO-Demo symbol-list export of 2026-10-01 (metadata only: names, sessions, swap fields, first dates; sha256 `be3f9a2e…`, not
yet committed; [CX-P1] §2 commits it). Literature I cite from memory and did not re-check here is marked *(not verified
here)*.

**Revised once after a review (2026-10-04).** The first version: graded the VC gold holdout as never split (it was partly
cut by stop width in the personal-account replays); called oil "all fresh" (Yahoo oil futures were in the repo and read by
the ICT / Wyckoff stability runs); and listed five directions whose class an earlier verdict had closed or limited to
forward data, without citing the verdict (CLAUDE.md §53). This version fixes the grades, cites every earlier verdict, moves
the re-openings out of the ranked list, and re-ranks.

Drafted for sealing (code and synthetic tests exist for each):
- VC: docs/plans/2026-10-04-vc-volatility-condition-preregistration-DRAFT.md (rank 1)
- OIL: docs/plans/2026-10-04-oil-trend-transfer-preregistration-DRAFT.md (rank 2)
- CAL: docs/plans/2026-10-04-cal-us-index-calendar-preregistration-DRAFT.md (rank 6 now: forward-only by B6)

Rank 3 (NEWS-FLAT) has no draft yet: it moved up when CAL became forward-only (open decision 7, §5).

## Tóm tắt (VI)

1. Gần như toàn bộ lịch sử FTMO đã bị đọc cho họ xu hướng (research-ledger.json:190: không còn giai đoạn OOS nào chưa
   chạm). Dữ liệu "sạch" thật sự chỉ còn: (a) mã chưa từng export (crypto CFD của FTMO; dầu trước 2024), (b) một thống kê
   chưa từng tính trên dữ liệu đã đọc (yếu hơn, phải ghi rõ), (c) dữ liệu forward.
2. **Hướng 1 (VC):** kiểm tra công bằng phát hiện "edge của H7/G9 nằm ở ngày stop rộng". Phát hiện này trộn hai thứ: biến
   động của ngày và GIỜ vào lệnh (stop = k·σ·√(số nến còn lại trong ngày)). Bảng phát hiện ghi "từ 2018" nhưng không có code,
   nên vùng holdout kết thúc 2018-01-01. Từ 2008-12-10 các lần chạy tài khoản cá nhân (skip/floor) đã cắt lệnh theo độ rộng
   stop tuyệt đối, nên vùng đó chỉ "đọc một phần". **Anh chọn:** (A) vàng 2004-06 → 2017-12 (đề xuất, ghi rõ phần đã lộ)
   hoặc (B) chỉ vàng 2004-06 → 2008-12-09 (sạch hơn, ít lệnh hơn, MDE ~0.14R thay vì ~0.08R).
3. **Hướng 2 (OIL):** H7/G9 trên UKOIL/USOIL của FTMO. Dầu chưa có nến FTMO nào, nhưng giá futures Yahoo của dầu đã có
   trong repo và đã được các lần chạy ICT/Wyckoff đọc ở khung 1H/4H từ 2024-04-19. Vì vậy vùng EXPOSED (từ 2024-03) chỉ là
   "chưa đọc cho giả thuyết này", còn vùng discovery/confirmation vẫn sạch. Thêm `UKOIL.cash`, `USOIL.cash` vào cùng file
   export với 30 mã crypto nếu anh đồng ý.
4. **Hướng 3 (NEWS-FLAT):** đóng lệnh H7/G9 trước tin lớn (NFP/CPI/FOMC) để giữ đúng quy tắc 1 %; đây chính là bước A2 còn
   treo. Cần lịch tin lịch sử có nguồn. Chưa viết bản pre-registration.
5. **CAL (FOMC, trước ngày lễ):** các đánh giá trước đã kết luận "chỉ forward" (B6, candidates.md:44; crypto-cfd-design.md:248,
   :263). Bản nháp giờ mặc định chỉ forward; đọc lịch sử chỉ khi anh ghi rõ quyết định ghi đè B6, và kể cả khi đó cũng bỏ
   các ngày G7/M1 đã đọc. Đi chậm (~4-5 năm để đủ 40 sự kiện mỗi test).
6. Bốn ý tưởng ở bản đầu thực ra mở lại các lớp đã bị loại: funding cực đoan (DF-3), giá vàng quanh LBMA, phần bù qua đêm
   của chỉ số, BTC cuối tuần → thứ Hai (SEAS-4). Đã chuyển xuống mục riêng, kèm điều kiện để mở lại.
7. Phí qua đêm crypto CFD của FTMO là -30 cả hai chiều (swap_mode 5). Nếu đó là -30 %/năm thì giữ qua đêm tốn ~8 bp/đêm.
   Cần kiểm bằng một lệnh demo.

## 0. What "unread" means here (strict)

- docs/architecture/research-ledger.json:190: no period is `oos_untouched`; every span of FTMO history the repo holds was
  read by the runs that produced the live selection.
- A window is **unread for a hypothesis** only if no committed read computed that hypothesis' statistic (or one that
  implies it) on it. Data read for OTHER hypotheses counts as "seen, not read for this one" and is disclosed as such.
- Four grades, used in every entry below:
  - **FRESH**: no bar of it exists in the repo (FTMO crypto CFDs; oil before 2024), or it is forward data.
  - **UNREAD-FOR-H**: bars (or the same market path) read by other families; this statistic never computed. Valid as
    discovery, with a dependence note.
  - **PARTLY EXPOSED**: a related cut of the same trades was computed and reported in another form (e.g. account metrics
    after a stop-width cut). Usable only with the cut named and a cleaner sub-window reported beside it.
  - **EXPOSED**: the statistic, or a superset that determines it, was read. Descriptive only.
- A subgroup of a family that FAILED on some data (e.g. H7 / G9 on the indices, F3 / F4 / F5) is not tested there under a new
  condition: that is a rescue by subgroup, i.e. fishing.
- **A direction whose class an earlier verdict rejected or limited to forward data must cite that verdict** and name the new
  evidence that justifies reopening it (CLAUDE.md §53). Without new evidence it is listed under "Reopenings", not ranked.

## 1. Ranked list

Ranking rule: (value to the owner if real) x (probability it is real AND detectable on fair data) / (cost), with the
second driver for the FTMO book valued above levers on the existing driver (docs/plans/2026-10-03-candidates.md:10-14).

### 1. VC -- the gold trend edge concentrates on high-volatility days, or on early entries [DRAFTED]

- **Hypothesis.** Among H7 / G9 trades, (a) those on days whose sigma_5m is above its trailing-250-day median, and/or
  (b) those entering early (an entry slot before the component's median, i.e. more bars left in the server day), have a
  higher mean R than the others.
- **Origin, disclosed.** Post hoc, on exposed data: G9 gold (stop 1.4) mean R by stop-width quartile -0.02 / +0.01 / +0.12
  / +0.29 "since 2018" (docs/audits/2026-10-04-personal-account.md:47-55). That table has no committed code and no JSON
  (commit e6a77ae adds only the .md and the .json; the JSON has no quartile key), so its exact start is unknown. The stop
  is k x sigma_5m x sqrt(bars to the server day's end) (scripts/research/book_sim.py:59): a wide stop means a volatile day
  OR an early entry, and in absolute bp also the 2020 / 2024-26 gold regimes. Cost dilution cannot explain the gradient:
  gold's round trip is ~0.65 bp (docs/plans/2026-10-03-reframes.md:88) against a median stop of ~100-110 bp at k = 1.4
  (personal-account.json `min_lot`), ~0.006 R.
- **Mechanism / literature.** Gao, Han, Li, Zhou (2018, JFE, "Market intraday momentum", the source of census E7,
  scripts/research/edge_census.py:77-78) report that intraday momentum is stronger on high-volatility days *(not verified
  here)*. Early entries: a trend that breaks out early has more time to run; no source in hand.
- **Data.** Exists for gold / silver. FTMO crypto CFDs: pending the B2 export. Forward: the paper log already records
  H7 / G9 gold (scripts/research/fvg_forward.py:36-38).
- **Unread windows for VC.**
  - Gold before 2008-12-10 (from 2004-06): UNREAD-FOR-H (H7 / G9 were selected and replayed there; no stop-width or VR
    split was computed).
  - Gold and silver 2008-12-10 -> 2017-12-31: PARTLY EXPOSED. The personal-account replays ran mode `skip` against `floor`
    on the common span 2008-12-10 -> 2026-10-02 (docs/audits/2026-10-04-personal-account.json `meta.common_span`,
    `historical` keys); docs/audits/2026-10-04-personal-account-cap.json (commit 4f803bf) adds `floor_cap`. `skip` drops
    trades whose minimum lot risks more than r x balance (`personal_account.py` `lots_for`): an absolute stop-width cut,
    reported as compounded account metrics.
  - 2018-01-01 onwards: EXPOSED for VC.
  - FTMO crypto CFDs: UNREAD-FOR-H at VC-X's read time (VC-X runs after the CX reads; group B only from 2024-03-01, as CX).
    Forward from the seal: FRESH. Indices, PGMs, research-only symbols: excluded (H7 / G9 failed there).
- **Effect vs cost.** Cost: no new data, one read of minutes. If half of the 2018+ gradient holds (high-half mean R ~+0.10,
  low-half ~0), a filter keeps the edge with half the trades; on the 5,000 USD account it points the owner's new
  "minimum lot up to ~2 %" rule at the trades that pay.
- **Multiple testing.** 4 historical tests (T1a, T1b gold, Holm m = 2; T2 silver, T3 crypto, Holm m = 2) + 1-2 forward.
  Power on gold: window A ~3,400 trades, MDE ~0.08 R; window B ~1,100 trades, MDE ~0.14 R (draft §7, side-balanced test).
- **Honest prior.** Moderate that some gradient exists (~40 %); low that a filter beats the unfiltered book at equal
  risk after forward data (~15 %).

### 2. OIL -- H7 / G9 transferred to FTMO crude oil (UKOIL.cash, USOIL.cash) [DRAFTED]

- **Hypothesis.** Gold's intraday trend rules, unchanged, earn net of FTMO's oil spread and commission.
- **Mechanism / literature.** Time-series momentum is documented across commodity futures (Moskowitz, Ooi, Pedersen 2012,
  JFE *(not verified here)*); oil is a macro-driven, trending commodity with a different driver from gold. No intraday
  source in hand.
- **Data.** No FTMO oil bar in the repo: the owner universe of 2026-10-01 excluded energies
  (docs/plans/2026-10-01-symbol-universe-design.md:3). Symbol list: UKOIL.cash server history from 2016-04-22, USOIL.cash
  from 2020-12-31; weekday sessions 03:05-23:50 and 01:05-23:50 server; swap points mode. The 5m depth is unknown until
  the export.
- **Unread windows.** DISCOVERY and CONFIRMATION (before 2024-03-01): FRESH. EXPOSED (2024-03-01 onwards): UNREAD-FOR-H.
  Yahoo CL=F / BZ=F futures files were in the repo from 3070e2e to 345e586 (docs/architecture/data-sources.md:33), and the
  ICT / Wyckoff stability runs read their 1H / 4H bars 2024-04-19 -> 2026-09-11 (data/history/stability/cfd-*.json at
  0daadd2, 2469b3c, b690648). Same market path, other methods; H7 / G9 never computed on oil.
- **Effect vs cost.** A second driver with near-daily events is worth more than any lever (candidates.md:10-14). Cost:
  two more names in the B2 export run, one spec export, a commission figure, the drafted code.
- **Multiple testing.** 2 pooled tests x 3 reads ([CX-P1] gates).
- **Honest prior.** Weak (~5-10 % to survive all reads). Every transfer of H7 / G9 outside gold and silver failed: F5
  0 / 27 (docs/audits/2026-10-02-edge-f5.md:6), H7x 0 / 2 (docs/audits/2026-10-04-crypto-cfd-phase.md:19).

### 3. NEWS-FLAT -- be flat across HIGH US releases (policy lever on fvg-book v4) [NOT DRAFTED]

- **Hypothesis.** Closing H7 / G9 before NFP / CPI / FOMC (and not re-entering until after) removes the gap-through tail
  that broke the 1 % rule (the worst trades were news gaps: docs/audits/2026-10-03-vol-schedule.md:37-43) at a small cost
  in R.
- **Status.** This is the pending owner step A2 (docs/audits/2026-10-04-crypto-cfd-phase.md:48-49; vol-schedule.md §4,
  option 2). v4 now trades k = 1.4, whose worst historical trade lost 1.39 % of the balance (vol-schedule.md:12).
- **Tension, stated up front.** If VC is right, news days are among the best days; flattening may cut the edge. That is
  exactly what the measurement must show.
- **Data.** Needs a sourced historical release calendar (NFP, CPI, FOMC; event-calendar.json is a 2026 snapshot,
  vol-schedule.md:43). The FOMC part is CAL's file.
- **Unread windows.** EXPOSED (all H7 / G9 gold trades read). Descriptive policy comparison (POLICY-EXPOSED); the fair
  test is forward.
- **Effect vs cost.** Removes the 1.39-1.94 % worst trades if they are all news; costs the R of those windows.
- **Multiple testing.** Policy comparison, 2-3 variants, labelled POLICY-EXPOSED.
- **Honest prior.** High that the tail shrinks; unknown sign on value.

### 4. XAU-FX -- is the gold edge a USD effect? H7 / G9 on XAUEUR and XAUAUD

- **Hypothesis.** H7 / G9 keep their edge when gold is priced in EUR or AUD. If they weaken sharply, part of the edge is a
  USD trend, and FX majors (parked) would correlate with the book (reframes.md:177-180).
- **Data.** Not in the repo; symbol list: XAUEUR from 2016-10-19, XAUAUD from 2016-10-21. Two more names in the export.
  The OIL code (a 5-day-market transfer) would serve with a symbol map.
- **Unread windows.** FRESH bars, but the XAUUSD path of 2016+ (read) drives most of their moves: a pass is NOT new
  evidence for H7; a fail is informative about the mechanism.
- **Effect vs cost.** Informs the FX decision and diversification; not a new driver. Cheap.
- **Multiple testing.** 2 tests, one read, mechanism-labelled.
- **Honest prior.** High that they work about as well (gold moves dominate EURUSD intraday); the informative case is rare.

### 5. CX-WE -- weekend vs weekday trend on FTMO crypto CFDs

- **Hypothesis.** H7 / G9 behave differently on weekend server days (thinner liquidity).
- **Unread windows.** FRESH now, but [CX-P1] §4 reports weekend trades separately in EVERY CX read: after the CX discovery
  read the discovery window is EXPOSED for this split. **Seal before that read or drop it** (open decision 3).
- **Multiple testing.** 1-2 tests riding CX's windows.
- **Honest prior.** Low.

### 6. CAL -- pre-FOMC drift and the pre-holiday effect on US index CFDs, FORWARD-ONLY [DRAFTED]

- **Earlier verdicts.** Pre-holiday is part of B6: "history CONTAMINATED (G7 / H2 read): forward only"
  (docs/plans/2026-10-03-candidates.md:44); "no source, and MDE about 32 bp" (docs/plans/2026-10-03-crypto-cfd-design.md:263).
  Pre-FOMC is B5 (candidates.md:43): "decayed after 2015. Forward-only at most" (crypto-cfd-design.md:248).
- **Hypothesis.** US500 / US30 / USTEC rise more than on ordinary days (a) from the server-day open to 5 minutes before a
  scheduled FOMC statement, (b) on the last NYSE day before a holiday (to 12:55 New York), against a same-year calendar null.
- **Contamination, counted (calendar only).** 24 of the 72 pre-holiday days from 2019-02-11 to 2026-09-25 are turn-of-month
  days whose full-day return G7 read (scripts/research/edge_f4.py:157-176; nets positive in all three reads,
  docs/audits/2026-10-02-edge-f4.md:81-83). M1's discovery read computed the return of 855 of the 923 NYSE days of
  2018-01 -> 2021-08 (week 4, falsification placebo, reversal; scripts/research/edge_m1.py:654-701) and reported their
  intercepts. 44 of 83 pre-holiday days since 2017-12-28 are on one or the other.
- **Design now.** Forward only (default). A single history read only under a recorded owner override of B6, and even then
  without the G7 and M1 read days (draft §0).
- **Data.** Index 5m exists; NYSE calendar exists and is tested (scripts/research/edge_m1.py:219). The FOMC calendar is NOT
  in the repo: one sourced JSON from federalreserve.gov is needed.
- **Effect vs cost.** ~17 events a year: 40 per test take ~4-5 years; MDE ~40 bp. Cheap to seal and leave running; its
  value is a zero-correlation component, years away.
- **Multiple testing.** 2 tests, 1 read, BH m = 2.
- **Honest prior.** Low (~10 %).

### 7. XS -- cross-sectional momentum among FTMO's 30 crypto CFDs

- **Hypothesis.** Coins that outperformed the basket over the past week outperform over the next week (long-short).
- **Mechanism / literature.** Liu, Tsyvinski, Wu (2022, JF, "Common risk factors in cryptocurrency") report a momentum
  factor *(not verified here)*. Not one of the rejected crypto classes: CRY-TSMOM-2 / -3 were time-series momentum
  (docs/plans/2026-10-03-crypto-cfd-design.md:229-230).
- **Data.** FRESH: the B2 export. Binance in the repo has three coins only (no cross-section).
- **Effect vs cost.** Market neutral, so near zero correlation with gold. **But** the symbol list shows swap -30 / -30 in
  swap_mode 5 for every crypto CFD. If that is -30 % a year, a weekly long-short pays ~1.1 % per week in swap alone. Verify
  with one demo position before spending more on this (open decision 5).
- **Multiple testing.** 1-2 tests (one lookback, one hold, fixed now).
- **Honest prior.** Low on FTMO (cost); low-moderate on a perp venue with many coins (needs data the repo lacks).

### 8. RV-METALS -- intraday gold / silver ratio reversion

- **Hypothesis.** After a 2-sigma intraday divergence of XAG / XAU, the ratio reverts within hours.
- **Data / windows.** Exists; UNREAD-FOR-H (both legs read for trend, the ratio never). B3 (index relative value,
  candidates.md:41) is the same idea on indices, not rejected, weak prior.
- **Effect vs cost.** Two spreads per trade; silver's p90 spread is large (edge-f4.md:14).
- **Honest prior.** Low.

### 9. MAKER -- maker entries for the crypto trend rule (execution lever)

- **Hypothesis.** Posting the H7x entry as a limit order cuts the 12 bp taker round trip enough to make it net positive.
- **Status.** The pending crypto lever (docs/audits/2026-10-04-crypto-cfd-phase.md:50-52).
- **Data.** Needs Binance 1m trade-through rules and a forward fill-rate check. The E5 lesson: limit fills select a
  different population (docs/audits/2026-10-03-e5-lookahead-erratum.md).
- **Honest prior.** Low.

### 10. FUNDED -- funded-stage risk policy and the two-account split (levers, no new edge)

- **Hypothesis.** A different risk per trade in the funded stage (a lost funded account costs the payout stream) and a
  second account for a second driver raise E[net payouts - fees] (reframes.md R1, R5; candidates.md:31-33).
- **Data.** Synthetic + the pass_policy / vol_schedule bootstrap on v4's trades. POLICY-EXPOSED.
- **Needs.** Owner parameters (fee, split, payout count, discount) as named inputs.
- **Honest prior.** Not a probability question: it is arithmetic on assumptions, worth doing once a second driver exists.

### 11. SHORT-HISTORY commodities -- H7 / G9 on agriculture, natural gas, heating oil, copper

- **Data.** Symbol list: agriculture from 2023, NATGAS 2024-10-23, HEATOIL 2024-12-11, XCUUSD 2024-12-02. Under three years,
  wide spreads, short sessions.
- **Only fair form.** Forward, or one exposed-style read labelled as such. Not worth a family now.
- **Honest prior.** Low.

## 2. Reopenings: listed in the first version, but their class was already rejected (not ranked, not counted as new)

| idea | earlier verdict | what would justify reopening |
|---|---|---|
| FUND: extreme perp funding -> crypto reversal | DF-3 "crowded-positioning contrarian: extreme funding ... -> next-7-day perp return", rejected: "MDE of 4-5% per week against a plausible effect under 1%; the OI archive was re-uploaded retroactively" (docs/plans/2026-10-03-crypto-cfd-design.md:236; definition in docs/audits/2026-10-03-crypto-cfd-design-workflow.json, id DF-3) | a shorter horizon with a cited source and an MDE below 1 %, or many more coins (FTMO's 30 CFDs give the cross-section, not the funding) |
| LBMA: gold around the London auctions | "decayed after the 2015 reform" (crypto-cfd-design.md:255); B8 "only with one window fixed from a cited source; none in hand" (candidates.md:46) | a post-2015 source with a fixed window |
| ON-PREM: unconditional overnight premium on US index CFDs | "negative after spread, and F6 already read it" (crypto-cfd-design.md:261) | none in hand; the FTMO long swap (US500 -157.55 points a lot a night on the symbol list) makes it worse |
| BTC-MON: weekend bitcoin -> Monday US index | B4 / SEAS-4 / XA3: "42 events since 2022, MDE 0.8-0.9%; practitioner evidence flips sign ... Forward-only" (crypto-cfd-design.md:33, :245) | forward only, as already decided; no new evidence |
| CAL history read | B6 / B5 above | an explicit owner override (CAL draft §0); the forward design stays ranked (#6) |

**Count, honestly:** 11 ranked directions that no earlier verdict closed (7 never listed before: VC, OIL, XAU-FX, CX-WE,
XS, RV-METALS, SHORT-HISTORY; 4 pending from earlier rounds: NEWS-FLAT, CAL forward, MAKER, FUNDED). The first version's
"15" counted the four reopenings above. I did not find a twelfth that is new, testable on fair data, and not already
rejected; listing a rejected class again would not be a new direction.

### Parked or out of scope (not ranked)

- **Forex**: parked by the owner (crypto-cfd-phase.md:53). First test if reopened: daily correlation with the gold book.
- **Stock CFDs** (59 on the symbol list), e.g. post-earnings drift: outside the owner's universe; needs a point-in-time
  earnings calendar.
- **Adding G9 silver to the book**: rejected (docs/audits/2026-10-02-pass-policy.md:29).
- **Other broker's gold history** (data/history/ohlcv.*.json, MetaQuotes-Demo): same market path, same years. Not
  independent evidence.
- **0DTE / options-gamma conditioning**: no options data (crypto-cfd-design.md:251).
- Handled by other sessions this round: the personal account's capped minimum-lot rule, Wyckoff W-C-long-15m forward
  collection, the B2 export and the crypto commission check.

## 3. Recommended order

1. **VC.** Owner picks window A or B (open decision 1). Seal VC; run the gold holdout. No new data; highest value per hour.
2. **Before the owner runs the B2 export (today):** decide OIL (and XAU-FX). If yes, add the names to
   `Common\Files\export-list.txt` line 2 and to the ExportSymbolSpec list, and seal OIL before the import.
   Decide CX-WE now too: it must be sealed before the CX discovery read.
3. **NEWS-FLAT:** write its pre-registration next (open decision 7); build NFP / CPI / FOMC dates in one sourced pass.
4. **CAL:** seal forward-only once the FOMC file exists (cheap), and leave it to accumulate.
5. **VC-X** after the CX family's reads are done (VC draft §5).
6. Then XS (after the swap check), RV-METALS, MAKER, FUNDED, SHORT-HISTORY.

## 4. Experiment budget implications

| family | tests | reads | grade |
|---|---|---|---|
| VC | T1a, T1b (Holm m = 2), T2, T3 (Holm m = 2) + forward (1-2) | gold holdout 1, crypto 1, forward 1 | gold: UNREAD-FOR-H before 2008-12-10, PARTLY EXPOSED 2008-12-10 -> 2017 (window A); crypto UNREAD-FOR-H; forward FRESH |
| OIL | 2 pooled | 3 | FRESH / FRESH / UNREAD-FOR-H |
| CAL | 2 | 1 (forward) | FRESH (forward); history only under the owner override, read days excluded |
| NEWS-FLAT | 2-3 policies | 1 | POLICY-EXPOSED |

Cumulative before this round, disclosed: F2-F5 153 pre-registered tests on 17 CFDs (edge-f5.md:15), AMD 24, hold 9,
F6 / F7 16, M1 5, H7x 4, C1 4, C1b 1, Wyckoff 7 confirmatory cells (docs/audits/2026-10-04-wyckoff-retest.md:18-26).

## 5. Open owner decisions (quoted options)

1. VC holdout window: "(A) gold 2004-06 -> 2017-12-31 and silver 2008-11 -> 2017-12-31, partly exposed from 2008-12-10,
   with window B reported beside it" (recommended) or "(B) gold 2004-06 -> 2008-12-09 only; T2 silver not run".
2. Oil in the B2 export: "add UKOIL.cash, USOIL.cash" or "no".
3. CX-WE: "seal the weekend split before the CX discovery read" or "drop it".
4. If VC gold passes: "demo only after the forward test and approval" (default) or "personal account now, labelled
   HOLDOUT-FOR-THE-CONDITION".
5. Crypto swap: "hold one demo crypto position overnight to measure swap" or "treat multi-day crypto on FTMO as infeasible".
6. CAL: "forward only" (default, B6) or "override B6 for one history read without the G7 / M1 days".
7. NEWS-FLAT: "write its pre-registration next" or "wait".
8. XAUEUR, XAUAUD in the same export: "yes" or "no".

## 6. Where I may be wrong

- The swap reading for crypto (mode 5, -30) is my interpretation of an MQL5 enum I could not confirm here; one demo
  position settles it.
- The OIL 5m depth is unknown; if FTMO keeps only recent 5m bars, OIL has no discovery window and becomes forward-only.
- VC's holdout is not pristine: H7 / G9 were selected on those years, and window A was cut by stop width in the
  personal-account replays. A pass says the gradient is not a 2018+ accident; it does not re-validate H7 / G9.
- The M1 read days counted for CAL are a conservative reading: M1's falsification rows were signed returns with an OLS
  intercept, not a pre-holiday mean. Under the strict §0 rule they are "seen", not "read for CAL"; I excluded them anyway.
- VC-X's check of the CX files assumes field names that `scripts/research/edge_cx.py` (not written yet) must match.
- Priors are judgement, stated so they can be argued with.
