# New research directions for the FTMO CFDs and the personal account (2026-10-04)

**Type:** research-direction document. Owner, 2026-10-04: "càng có nhiều hướng nghiên cứu mới càng tốt". It changes no code
path, config, account, assignment or demo behaviour. **Market data read for this document: none.** New facts come from
committed audits (cited), from code (cited by file:line), from calendar arithmetic (NYSE holidays, no prices), and from the
FTMO-Demo symbol-list export of 2026-10-01 (metadata only: names, sessions, swap fields, first dates; sha256 `be3f9a2e…`, not
yet committed; [CX-P1] §2 commits it). Literature I cite from memory and did not re-check here is marked *(not verified
here)*.

**Revised three times after reviews (2026-10-04).** Revision 1: graded the VC gold holdout as partly exposed (the
personal-account replays cut it by stop width), disclosed the Yahoo oil files read by the ICT / Wyckoff stability runs,
cited every earlier verdict and moved the reopenings out of the ranked list (CLAUDE.md §53). Revision 2 (review items 9-21):
records the lead decisions below; cites the earlier status of MAKER and FUNDED and parks FUNDED; gives every ranked entry the
same fields (hypothesis, mechanism, data, unread windows, effect against cost, multiple-testing cost, prior); corrects the
median stop (99 / 108 bp at k = 1.4) and CAL's event counts; completes the experiment budget (§4). Revision 3 (the review
of revision 2): VC's window counts are corrected (window B ~950 trades) and a window-B pass is graded discovery, with TF as
its confirmation; VC's T1b is nb-weighted; the budget adds the Wyckoff arms and cells and the ledger's earlier searches;
the H5 prior on the VR rule and the repo's own notes on cross-sectional crypto momentum are cited; the account layers need a
row filter or adapter first.

**Lead decisions 2026-10-04** (the owner authorised independent work; each is also recorded in its draft):
- VC: window B (gold before 2008-12-10) is the DECISIVE test. Window A (to 2017-12-31, partly exposed by all
  personal-account replays) is report-only. `scripts/research/edge_vc.py` sets `HOLDOUT = "B"`. The decision quoted ~1,100
  trades and MDE ~0.14 R; the discovery-window rate gives ~950 trades, MDE ~0.14-0.15 R for T1a (VC §7). Window B is
  UNREAD-FOR-H, so a pass there is discovery grade for the condition (§0); TF on forward data confirms it.
- VC on the personal account: default NO. Any use is an owner decision (VC draft §9; open decision 4).
- CAL: forward-only, the default, stays.
- VC-X group B: from 2024-03-01 only, as CX.
- Every draft states how a pass is carried to both account layers: the FTMO challenge replay of the book, and the personal
  5,000 USD account (`scripts/research/personal_account.py`). Described there, not run. Both tools replay book_sim rows, so
  VC needs a row filter and OIL / CAL a row adapter first (each draft says which).

Drafted for sealing (code and synthetic tests exist for each):
- VC: docs/plans/2026-10-04-vc-volatility-condition-preregistration-DRAFT.md (rank 1)
- OIL: docs/plans/2026-10-04-oil-trend-transfer-preregistration-DRAFT.md (rank 2)
- CAL: docs/plans/2026-10-04-cal-us-index-calendar-preregistration-DRAFT.md (rank 6: forward-only by B6)

Rank 3 (NEWS-FLAT) has no draft yet (open decision 7, §5).

## Tóm tắt (VI)

1. Gần như toàn bộ lịch sử FTMO đã bị đọc cho họ xu hướng (research-ledger.json:190: không còn giai đoạn OOS nào chưa
   chạm). Dữ liệu "sạch" thật sự chỉ còn: (a) mã chưa từng export (crypto CFD của FTMO; dầu trước 2024), (b) một thống kê
   chưa từng tính trên dữ liệu đã đọc (yếu hơn, phải ghi rõ), (c) dữ liệu forward.
2. **Hướng 1 (VC):** kiểm tra công bằng phát hiện "edge của H7/G9 nằm ở ngày stop rộng". Stop rộng trộn hai thứ: biến động
   của ngày và GIỜ vào lệnh (stop = k·σ·√(số nến còn lại trong ngày)). **Quyết định (lead, 2026-10-04):** vùng B (vàng trước
   2008-12-10) là test quyết định; vùng A (đến 2017-12-31, đã lộ một phần qua mọi lần chạy tài khoản cá nhân) chỉ để báo
   cáo. Tính lại theo tốc độ lệnh của giai đoạn discovery: vùng B có ~950 lệnh (không phải ~1.100), MDE ~0,14-0,15R. Vùng
   B chỉ là "chưa đọc cho giả thuyết này", nên đạt ở đây mới là mức discovery; dữ liệu forward (TF) mới là bước xác nhận.
   Test giờ vào lệnh (T1b) đo R trên mỗi √nến, lấy trung bình có trọng số theo số nến: một edge đều theo thời gian tự nó
   đã cho lệnh vào sớm R cao hơn (~+0,03-0,05R, mô phỏng), còn nếu không có trọng số thì các lệnh vào sát cuối ngày sẽ lấn
   át phép đo. Dùng VC cho tài khoản cá nhân: mặc định KHÔNG; muốn dùng thì anh quyết.
3. **Hướng 2 (OIL):** H7/G9 trên UKOIL/USOIL của FTMO. Dầu chưa có nến FTMO nào, nhưng giá futures Yahoo của dầu đã có
   trong repo và đã được các lần chạy ICT/Wyckoff đọc ở khung 1H/4H từ 2024-04-19. Vì vậy vùng EXPOSED (từ 2024-03) chỉ là
   "chưa đọc cho giả thuyết này", còn vùng discovery/confirmation vẫn sạch. Lọc chi phí trước, rồi mới chia mốc D* trên các
   mã qua lọc (giống CX). Thêm `UKOIL.cash`, `USOIL.cash` vào cùng file export với 30 mã crypto nếu anh đồng ý.
4. **Hướng 3 (NEWS-FLAT):** đóng lệnh H7/G9 trước tin lớn (NFP/CPI/FOMC) để giữ đúng quy tắc 1 %; đây chính là bước A2 còn
   treo. Cần lịch tin lịch sử có nguồn. Chưa viết bản pre-registration.
5. **CAL (FOMC, trước ngày lễ):** chỉ forward (B6; lead giữ nguyên). Mẫu so sánh nay là các ngày CÙNG THỨ trong tuần, cùng
   năm, vì hơn nửa số ngày trước lễ là thứ Sáu và FOMC thường vào thứ Tư. Nếu anh ghi đè B6 để đọc lịch sử: dữ liệu dày của
   US500/USTEC chỉ có từ 2021-09, nên chỉ còn khoảng 34 ngày trước lễ và dưới 40 ngày FOMC, MDE ~50 bp.
6. 10 hướng được xếp hạng: 7 hướng mới thật sự, 3 hướng còn treo từ các vòng trước (NEWS-FLAT, CAL forward, MAKER). FUNDED
   (A3/A4) chuyển xuống "tạm gác": A3 chờ có driver thứ hai, A4 là câu hỏi của anh, không phải nghiên cứu. Bốn ý tưởng ở bản
   đầu mở lại các lớp đã bị loại (funding cực đoan DF-3, LBMA, phần bù qua đêm, BTC cuối tuần → thứ Hai) nằm ở mục riêng.
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
  evidence that justifies reopening it (CLAUDE.md §53). Without new evidence it is listed under "Reopenings", not ranked. A
  direction listed in an earlier round and still pending cites where it was listed.

## 1. Ranked list

Ranking rule: (value to the owner if real) x (probability it is real AND detectable on fair data) / (cost), with the
second driver for the FTMO book valued above levers on the existing driver (docs/plans/2026-10-03-candidates.md:10-14).
Every entry carries the same fields; "Earlier" appears where an earlier round listed or judged the class.

### 1. VC -- the gold trend edge concentrates on high-volatility days, or on early entries [DRAFTED, new]

- **Hypothesis.** Among H7 / G9 trades, (a) those on days whose sigma_5m is above its trailing-250-day median, and/or
  (b) those entering early (an entry slot before the component's median, i.e. more bars left in the server day), have a
  higher mean R than the others; for (b), a higher R per sqrt(bar), so that the gap is not the stop's own scaling.
- **Origin, disclosed.** Post hoc, on exposed data: G9 gold (stop 1.4) mean R by stop-width quartile -0.02 / +0.01 / +0.12
  / +0.29 "since 2018" (docs/audits/2026-10-04-personal-account.md:47-55 at f76d6fa). That table has no committed code and
  no JSON (commit e6a77ae adds only the .md and the .json; the JSON has no quartile key), so its exact start is unknown. The
  stop is k x sigma_5m x sqrt(bars to the server day's end) (scripts/research/book_sim.py:59): a wide stop means a volatile
  day OR an early entry, and in absolute bp also the 2020 / 2024-26 gold regimes. Cost dilution cannot explain the
  gradient: gold's round trip is ~0.65 bp (docs/plans/2026-10-03-reframes.md:88) against a median stop since 2024 of 108 bp
  (H7) and 99 bp (G9) at k = 1.4 (docs/audits/2026-10-04-personal-account.json `min_lot`; the 141-155 bp figures are
  k = 2.0): ~0.006 R.
- **Mechanism / literature.** Gao, Han, Li, Zhou (2018, JFE, "Market intraday momentum", the source of census E7,
  scripts/research/edge_census.py:77-78) report that intraday momentum is stronger on high-volatility days *(not verified
  here)*. Early entries: a trend that breaks out early has more time to run; no source in hand. A constant per-bar edge
  already gives early entries more R (R grows with sqrt(bars) when the stop does), so (b) is tested per sqrt(bar) (VC §4).
- **Data.** Exists for gold / silver. FTMO crypto CFDs: pending the B2 export. Forward: the paper log already records
  H7 / G9 gold (scripts/research/fvg_forward.py:36-38).
- **Unread windows for VC.**
  - Gold before 2008-12-10 (from 2004-06): UNREAD-FOR-H (H7 / G9 were selected and replayed there; no stop-width or VR
    split of H7 / G9 was computed). **Window B: the decisive test (lead decision 2026-10-04); a pass there is discovery
    grade, and TF confirms it.** The same VR rule was used on these years for another detector: F3 H5 tested E5's FVG
    retrace on gold's HIGH days only, 2005-2016 (discovery p 0.0107, not BH-rejected; confirmation p 0.115;
    docs/audits/2026-10-02-edge-f3.md:55). That is a prior on the rule, not a read of VC's statistic.
  - Gold and silver 2008-12-10 -> 2017-12-31: PARTLY EXPOSED. All personal-account replays (modes skip, floor, floor_cap,
    and the fixed 100 USD cap of b818e99) drop or size trades by an absolute stop width on the common span 2008-12-10 ->
    2026-10-02 (docs/audits/2026-10-04-personal-account.json `meta.common_span`) and report compounded account metrics.
    Window A (B plus this span) is report-only.
  - 2018-01-01 onwards: EXPOSED for VC.
  - FTMO crypto CFDs: UNREAD-FOR-H at VC-X's read time (VC-X runs after the CX reads; group B only from 2024-03-01, as CX:
    lead decision 2026-10-04). Forward from the seal: FRESH. Indices, PGMs, research-only symbols: excluded (H7 / G9 failed
    there).
- **Effect vs cost.** Cost: no new data, one read of minutes. If half of the 2018+ gradient holds (high-half mean R ~+0.10,
  low-half ~0), a filter keeps the edge with half the trades. On the 5,000 USD account it would point the owner's "minimum
  lot up to ~2 %" rule at the trades that pay, but that use defaults to NO (lead decision; open decision 4).
- **Multiple testing.** Decisive: T1a, T1b on gold (Holm m = 2). Secondary {T2 silver, T3 crypto} (Holm m = 2): no silver
  trade has a VR before 2008-12-10 (silver's 5m history starts 2008-11-07), so T2 is "not run (window)" and enters with
  p = 1. Then 1-2 forward tests. Power: window B ~950 gold trades (an estimate the dry run replaces), MDE ~0.14-0.15 R
  for T1a and ~0.16-0.17 for T1b (nb-weighted per-sqrt-bar statistic; VC §7). Window A (~3,200 trades) is report-only.
- **Honest prior.** Moderate that some gradient exists (~40 %); low that a filter beats the unfiltered book at equal
  risk after forward data (~15 %).

### 2. OIL -- H7 / G9 transferred to FTMO crude oil (UKOIL.cash, USOIL.cash) [DRAFTED, new]

- **Hypothesis.** Gold's intraday trend rules, unchanged, earn net of FTMO's oil spread and commission.
- **Mechanism / literature.** Time-series momentum is documented across commodity futures (Moskowitz, Ooi, Pedersen 2012,
  JFE *(not verified here)*); oil is a macro-driven, trending commodity with a different driver from gold. No intraday
  source in hand.
- **Data.** No FTMO oil bar in the repo: the owner universe of 2026-10-01 excluded energies
  (docs/plans/2026-10-01-symbol-universe-design.md:3). Symbol list: UKOIL.cash server history from 2016-04-22, USOIL.cash
  from 2020-12-31; weekday sessions 03:05-23:50 and 01:05-23:50 server; swap points mode. The 5m depth is unknown until
  the export. The cost screen runs first, then D* and membership on the admitted symbols, as CX (OIL draft §2).
- **Unread windows.** DISCOVERY and CONFIRMATION (before 2024-03-01): FRESH. EXPOSED (2024-03-01 onwards): UNREAD-FOR-H.
  Yahoo CL=F / BZ=F futures files were in the repo from 3070e2e to 345e586 (docs/architecture/data-sources.md:33), and the
  ICT / Wyckoff stability runs read their 1H / 4H bars 2024-04-19 -> 2026-09-11 (data/history/stability/cfd-*.json at
  0daadd2, 2469b3c, b690648). Same market path, other methods; H7 / G9 never computed on oil.
- **Effect vs cost.** A second driver with near-daily events is worth more than any lever (candidates.md:10-14). Cost:
  two more names in the B2 export run, one spec export, a commission figure, the drafted code.
- **Multiple testing.** 2 pooled tests (T1 H7, T2 G9) x 3 reads, BH m = 2 at discovery ([CX-P1] gates).
- **Honest prior.** Weak (~5-10 % to survive all reads). Every transfer of H7 / G9 outside gold and silver failed: F5
  0 / 27 (docs/audits/2026-10-02-edge-f5.md:6), H7x 0 / 2 (docs/audits/2026-10-04-crypto-cfd-phase.md:19).

### 3. NEWS-FLAT -- be flat across HIGH US releases (policy lever on fvg-book v4) [NOT DRAFTED, pending]

- **Earlier.** This is the pending owner step A2 (docs/audits/2026-10-04-crypto-cfd-phase.md:48-49; vol-schedule.md §4,
  option 2). Not killed; no reopening needed.
- **Hypothesis.** Closing H7 / G9 before NFP / CPI / FOMC (and not re-entering until after) removes the gap-through tail
  that broke the 1 % rule (the worst trades were news gaps: docs/audits/2026-10-03-vol-schedule.md:37-43) at a small cost
  in R. v4 trades k = 1.4, whose worst historical trade lost 1.39 % of the balance (vol-schedule.md:12).
- **Mechanism.** A scheduled release moves the price in a jump that a stop cannot cap: a bar that opens beyond the stop
  fills at its open (scripts/research/book_sim.py:66). Being flat removes the jump's tail and also its share of the trend.
- **Tension, stated up front.** If VC is right, news days are among the best days; flattening may cut the edge. That is
  exactly what the measurement must show.
- **Data.** Needs a sourced historical release calendar (NFP, CPI, FOMC; event-calendar.json is a 2026 snapshot,
  vol-schedule.md:43). The FOMC part is CAL's file.
- **Unread windows.** EXPOSED (all H7 / G9 gold trades read). Descriptive policy comparison (POLICY-EXPOSED); the fair
  test is forward.
- **Effect vs cost.** Removes the 1.39-1.94 % worst trades if they are all news; costs the R of those windows.
- **Multiple testing.** Policy comparison, 2-3 variants, labelled POLICY-EXPOSED.
- **Honest prior.** High that the tail shrinks; unknown sign on value.

### 4. XAU-FX -- is the gold edge a USD effect? H7 / G9 on XAUEUR and XAUAUD [new]

- **Hypothesis.** H7 / G9 keep their edge when gold is priced in EUR or AUD. If they weaken sharply, part of the edge is a
  USD trend, and FX majors (parked) would correlate with the book (reframes.md:177-180).
- **Mechanism.** XAUEUR = XAUUSD / EURUSD. A gold-specific trend survives the change of quote currency; a USD trend does
  not.
- **Data.** Not in the repo; symbol list: XAUEUR from 2016-10-19, XAUAUD from 2016-10-21. Two more names in the export.
  The OIL code (a 5-day-market transfer) would serve with a symbol map.
- **Unread windows.** FRESH bars, but the XAUUSD path of 2016+ (read) drives most of their moves: a pass is NOT new
  evidence for H7; a fail is informative about the mechanism.
- **Effect vs cost.** Informs the FX decision and diversification; not a new driver. Cheap.
- **Multiple testing.** 2 tests, one read, mechanism-labelled.
- **Honest prior.** High that they work about as well (gold moves dominate EURUSD intraday); the informative case is rare.

### 5. CX-WE -- weekend vs weekday trend on FTMO crypto CFDs [new]

- **Hypothesis.** H7 / G9 behave differently on weekend server days.
- **Mechanism.** On weekends no equity or futures session anchors crypto prices and liquidity is thinner, so a breakout
  may run further or fail more often. No source in hand.
- **Data.** The B2 export (FTMO crypto CFDs, a 7-day market). The split rides CX's own rows; no new data.
- **Unread windows.** FRESH now, but [CX-P1] §4 reports weekend trades separately in EVERY CX read: after the CX discovery
  read the discovery window is EXPOSED for this split. **Seal before that read or drop it** (open decision 3).
- **Effect vs cost.** A weekend-only (or weekday-only) rule keeps ~2 / 7 (or 5 / 7) of CX's trades at CX's costs; it is
  worth something only if CX itself has an edge in one of the two.
- **Multiple testing.** 1-2 tests riding CX's windows.
- **Honest prior.** Low.

### 6. CAL -- pre-FOMC drift and the pre-holiday effect on US index CFDs, FORWARD-ONLY [DRAFTED, pending]

- **Earlier.** Pre-holiday is part of B6: "history CONTAMINATED (G7 / H2 read): forward only"
  (docs/plans/2026-10-03-candidates.md:44); "no source, and MDE about 32 bp"
  (docs/plans/2026-10-03-crypto-cfd-design.md:263). Pre-FOMC is B5 (candidates.md:43): "decayed after 2015. Forward-only
  at most" (crypto-cfd-design.md:248). Forward-only stays (lead decision 2026-10-04).
- **Hypothesis.** US500 / US30 / USTEC rise more than on ordinary days (a) from the server-day open to 5 minutes before a
  scheduled FOMC statement, (b) on the last NYSE day before a holiday (to 12:55 New York), against a same-year, SAME-WEEKDAY
  calendar null (review item 14: more than half of the pre-holiday days are Fridays, 45 of 83 from 2017-12-28 to 2026-09-25
  by calendar arithmetic; FOMC statements come mid-week).
- **Mechanism / literature.** Pre-FOMC: a pre-announcement risk premium (Lucca and Moench 2015, JF *(not verified here)*).
  Pre-holiday: high pre-holiday returns (Ariel 1990, JF *(not verified here)*), attributed to flows before a closure.
- **Contamination, counted (calendar only).** 24 of the 72 pre-holiday days from 2019-02-11 to 2026-09-25 are turn-of-month
  days whose full-day return G7 read (scripts/research/edge_f4.py:157-176; nets positive in all three reads,
  docs/audits/2026-10-02-edge-f4.md:81-83). M1's discovery read computed the return of 855 of the 923 NYSE days of
  2018-01 -> 2021-08 (week 4, falsification placebo, reversal; scripts/research/edge_m1.py:654-701) and reported their
  intercepts (edge_m1.py:807-824).
- **Design now.** Forward only (default). A single history read only under a recorded owner override of B6, and even then
  without the G7 and M1 read days (draft §0).
- **Event counts (review item 13).** Forward: FOMC 8 a year, pre-holiday 9-10 a year. History (override only): the pooled
  test clusters by NYSE date, and dense 5m data starts 2021-09-14 / 15 for US500 / USTEC but 2019-02-11 for US30
  (docs/audits/2026-10-02-edge-census.json `meta.symbols`). Every event date before 2021-09-14 is US30's alone, and M1's read
  days leave its weekday null too thin there (draft §2). So the history read has about 34 pre-holiday dates (49 since
  2021-09-14, minus 15 on a turn-of-month proxy) and fewer than 40 FOMC dates (8 a year over 5 years, minus those on G7
  days), not ~70.
- **Data.** Index 5m exists; NYSE calendar exists and is tested (scripts/research/edge_m1.py:219). The FOMC calendar is NOT
  in the repo: one sourced JSON from federalreserve.gov is needed.
- **Unread windows.** Forward event days: FRESH. History (override only): UNREAD-FOR-H on the days left after the G7 / M1
  exclusions.
- **Effect vs cost.** ~17 events a year: 40 per test take ~4-5 years; MDE ~40-50 bp. Cheap to seal and leave running; its
  value is a zero-correlation component, years away.
- **Multiple testing.** 2 tests, 1 read, BH m = 2.
- **Honest prior.** Low (~10 %).

### 7. XS -- cross-sectional momentum among FTMO's 30 crypto CFDs [new]

- **Hypothesis.** Coins that outperformed the basket over the past week outperform over the next week (long-short).
- **Mechanism / literature.** Liu, Tsyvinski, Wu (2022, JF, "Common risk factors in cryptocurrency") report a momentum
  factor *(not verified here)*. Not one of the rejected crypto classes: CRY-TSMOM-2 / -3 were time-series momentum
  (docs/plans/2026-10-03-crypto-cfd-design.md:229-230; CRY-TSMOM-3 ranks BTC's own weekly return, not a cross-section).
- **Earlier (the repo's own notes, against it).** The crypto literature sweep recorded that cross-sectional momentum is
  reported WEAK under realistic costs and liquidation risk (Han, Kang, Ryu, SSRN 4675565, seen there only as a search
  snippet; docs/audits/2026-10-03-crypto-cfd-design-workflow.json:1379, :1418, `lit_tsmom`). The derivatives sweep set a
  cross-sectional design (funding deciles) aside because the 9-symbol allowlist was too small and a third party's
  pre-registered Binance test of it (Berachah) was killed by costs (same file :858, `lit_derivatives_flow`). New here:
  FTMO's 30 crypto CFDs give a wider
  cross-section. The cost objection stands, and the swap reading below sharpens it.
- **Data.** The B2 export. Binance in the repo has three coins only (no cross-section).
- **Unread windows.** FRESH before the CX reads. After them, the same bars were read for H7 / G9 (an intraday statistic):
  UNREAD-FOR-H for XS, with a dependence note.
- **Effect vs cost.** Market neutral, so near zero correlation with gold. **But** the symbol list shows swap -30 / -30 in
  swap_mode 5 for every crypto CFD. If that is -30 % a year, a weekly long-short pays ~1.1 % per week in swap alone. Verify
  with one demo position before spending more on this (open decision 5).
- **Multiple testing.** 1-2 tests (one lookback, one hold, fixed now).
- **Honest prior.** Low on FTMO (cost); low-moderate on a perp venue with many coins (needs data the repo lacks).

### 8. RV-METALS -- intraday gold / silver ratio reversion [new]

- **Hypothesis.** After a 2-sigma intraday divergence of XAG / XAU, the ratio reverts within hours.
- **Mechanism.** Gold and silver load on one precious-metals factor; a short-lived divergence may be a liquidity
  dislocation that cross-metal arbitrage closes. No source in hand.
- **Data / windows.** Exists; UNREAD-FOR-H (both legs read for trend, the ratio never). B3 (index relative value,
  candidates.md:41) is the same idea on indices, not rejected, weak prior.
- **Effect vs cost.** Two spreads per trade; silver's confirmation net falls from +34.4 to +23.2 bp at the p90 spread
  (docs/audits/2026-10-02-edge-f4.md:14), so its spread tail is wide.
- **Multiple testing.** 1-2 tests (one threshold, one horizon, fixed before any read).
- **Honest prior.** Low.

### 9. MAKER -- maker entries for the crypto trend rule (execution lever) [pending]

- **Earlier.** Listed, not killed: "the only remaining lever" of the crypto phase
  (docs/audits/2026-10-04-crypto-cfd-phase.md:50-52). The sweep's verdict on SEAS-1 / XA1 sets its limit: "maker fills
  cannot be modelled from klines" (docs/plans/2026-10-03-crypto-cfd-design.md:231). No new evidence since: pending, not new.
- **Hypothesis.** Posting the H7x entry as a limit order cuts the 12 bp taker round trip enough to make it net positive.
- **Mechanism.** A limit order earns the spread instead of paying it (maker 0.02 % against taker 0.05 % a side,
  crypto-cfd-phase.md:50). It fills only when the price comes back, which selects a different population: the E5 lesson
  (docs/audits/2026-10-03-e5-lookahead-erratum.md).
- **Data.** Needs Binance 1m trade-through rules and a forward fill-rate check.
- **Unread windows.** The Binance signal windows 2017-24 are read (H7x, crypto-cfd-phase.md:19). Real maker fills were never
  measured: FRESH only forward.
- **Effect vs cost.** H7x confirmation netted +0.2 / +0.05 bp at taker (crypto-cfd-phase.md:19). Saving ~6 bp a round trip
  helps only if the fills do not select the losers.
- **Multiple testing.** One forward fill-rate check and one net test, pre-registered together.
- **Honest prior.** Low.

### 10. SHORT-HISTORY commodities -- H7 / G9 on agriculture, natural gas, heating oil, copper [new]

- **Hypothesis.** H7 / G9, unchanged, earn net on FTMO's short-history commodity CFDs.
- **Mechanism.** As OIL: time-series momentum in commodity futures *(not verified here)*; no intraday source in hand.
- **Data.** Symbol list: agriculture from 2023, NATGAS 2024-10-23, HEATOIL 2024-12-11, XCUUSD 2024-12-02. Under three years,
  wide spreads, short sessions.
- **Unread windows.** FRESH bars (never exported), but too short for a discovery / confirmation split.
- **Effect vs cost.** Wide spreads and short sessions; each symbol adds a cost screen and few events a year.
- **Multiple testing.** 2 pooled tests (H7, G9), forward or one exposed-style read labelled as such. Not worth a family now.
- **Honest prior.** Low.

## 2. Not ranked

### Reopenings: listed in the first version, but their class was already rejected (not counted as new)

| idea | earlier verdict | what would justify reopening |
|---|---|---|
| FUND: extreme perp funding -> crypto reversal | DF-3 "crowded-positioning contrarian: extreme funding ... -> next-7-day perp return", rejected: "MDE of 4-5% per week against a plausible effect under 1%; the OI archive was re-uploaded retroactively" (docs/plans/2026-10-03-crypto-cfd-design.md:236; definition in docs/audits/2026-10-03-crypto-cfd-design-workflow.json, id DF-3) | a shorter horizon with a cited source and an MDE below 1 %, or many more coins (FTMO's 30 CFDs give the cross-section, not the funding) |
| LBMA: gold around the London auctions | "decayed after the 2015 reform" (crypto-cfd-design.md:255); B8 "only with one window fixed from a cited source; none in hand" (candidates.md:46) | a post-2015 source with a fixed window |
| ON-PREM: unconditional overnight premium on US index CFDs | "negative after spread, and F6 already read it" (crypto-cfd-design.md:261) | none in hand; the FTMO long swap (US500 -157.55 points a lot a night on the symbol list) makes it worse |
| BTC-MON: weekend bitcoin -> Monday US index | B4 / SEAS-4 / XA3: "42 events since 2022, MDE 0.8-0.9%; practitioner evidence flips sign ... Forward-only" (crypto-cfd-design.md:33, :245) | forward only, as already decided; no new evidence |
| CAL history read | B6 / B5 (§1, #6) | an explicit owner override (CAL draft §0); the forward design stays ranked (#6) |

### Parked or out of scope

- **FUNDED** (funded-stage risk policy and the two-account split; listed as #10 in revision 1): these are candidates A3 and
  A4 (docs/plans/2026-10-03-candidates.md:31-32). A3 "waits on B": it needs a second driver that survived its reads; none
  has. A4 is "not research: CLAUDE.md §34 default, owner question". No new evidence: parked until a second driver survives
  (A3) or the owner asks (A4).
- **Forex**: parked by the owner (crypto-cfd-phase.md:53). First test if reopened: daily correlation with the gold book.
- **Stock CFDs** (59 on the symbol list), e.g. post-earnings drift: outside the owner's universe; needs a point-in-time
  earnings calendar.
- **Adding G9 silver to the book**: rejected (docs/audits/2026-10-02-pass-policy.md:29).
- **Other broker's gold history** (data/history/ohlcv.*.json, MetaQuotes-Demo): same market path, same years. Not
  independent evidence.
- **0DTE / options-gamma conditioning**: no options data (crypto-cfd-design.md:251).
- Handled by other sessions this round: the personal account's capped minimum-lot rule, Wyckoff W-C-long-15m forward
  collection, the B2 export and the crypto commission check.

**Count, honestly:** 10 ranked directions. 7 were never listed before: VC, OIL, XAU-FX, CX-WE, XS, RV-METALS,
SHORT-HISTORY. 3 are pending from earlier rounds and cite where: NEWS-FLAT (A2), CAL forward (B5 / B6), MAKER (the crypto
phase's lever). The first version's "15" also counted the four reopenings above and FUNDED. I did not find an eighth new
direction that is testable on fair data and not already rejected.

## 3. Recommended order

1. **VC.** Window B decisive (lead decision 2026-10-04). Seal VC; run the gold holdout. No new data; highest value per hour.
2. **Before the owner runs the B2 export (today):** decide OIL (and XAU-FX). If yes, add the names to
   `Common\Files\export-list.txt` line 2 and to the ExportSymbolSpec list, and seal OIL before the import.
   Decide CX-WE now too: it must be sealed before the CX discovery read.
3. **NEWS-FLAT:** write its pre-registration next (open decision 7); build NFP / CPI / FOMC dates in one sourced pass.
4. **CAL:** seal forward-only once the FOMC file exists (cheap), and leave it to accumulate.
5. **VC-X** after the CX family's reads are done (VC draft §5).
6. Then XS (after the swap check), RV-METALS, MAKER, SHORT-HISTORY.

## 4. Experiment budget (CLAUDE.md §43)

This round's drafts:

| family | tests | reads | grade |
|---|---|---|---|
| VC | decisive T1a, T1b (Holm m = 2); secondary T2 (not run in window B: p = 1), T3 (Holm m = 2); forward 1-2 | gold holdout 1, crypto 1, forward 1 | gold window B UNREAD-FOR-H (decisive); window A PARTLY EXPOSED from 2008-12-10 (report-only); crypto UNREAD-FOR-H; forward FRESH |
| OIL | 2 pooled | 3 | FRESH / FRESH / UNREAD-FOR-H |
| CAL | 2 | 1 (forward) | FRESH (forward); history only under the owner override, read days excluded |
| NEWS-FLAT | 2-3 policies | 1 | POLICY-EXPOSED |

Before this round, disclosed. The table covers the work since the census (2026-10-02) and the earlier searches the ledger
names; `docs/architecture/research-ledger.json` is the full record.

| item | tests or cells | status | source |
|---|---|---|---|
| ICT target models (before the §42 store) | 7 target-model variants on one dataset | recorded as data snooping, not counted as a recorded search | research-ledger.json:66-77 (`budget._known_unrecorded`) |
| setup ranking (before the store) | 120 candidate rows narrowed to the 6 selected setups; nothing recorded about the other 114 | the live selection; candidate-selection bias | same |
| prop search (2026-09-27) | 180 sealed §42 records: every trade of 2024-03-01 -> 2025-03-01 scored against two prop-firm pass rules | selected candidates; that window became exposed the day it was declared | research-ledger.json:169 (period `cfd-prop-search-2024-03-2025-03`) |
| census | 40 tests, development window, plus a point-in-time re-measure of all 40 | 0 confirmed | docs/audits/2026-10-02-edge-census.md:11; candidates.md:56 |
| F2-F5 | 153 pre-registered tests on 17 CFDs | survivors H7 / G9 gold, G9 silver, E5 (later found look-ahead) | edge-f5.md:15 |
| AMD | 24 | 0 survive | docs/audits/2026-10-03-edge-amd.md:6 |
| hold | 9 | 0 | docs/audits/2026-10-03-edge-hold.md:5 |
| F6 / F7 | 16, discovery only | 0 | docs/audits/2026-10-03-edge-f6-discovery.md:50 |
| A1 vol schedule | 6 policies (incl. the reference) + 1 post-hoc tail diagnostic; re-read under the owner's gap tolerance | 0 proposed by its rule | vol-schedule.md:55; docs/audits/2026-10-04-a1-under-owner-tolerance.md |
| A3 silver | 1 comparison (2 books) | exposed data | docs/plans/2026-10-04-a3-silver-preregistration.md:39 |
| personal-account grids | 144 cells (r 2 x balance 2 x skip / floor x edge 3, six books), 108 cells (skip / floor_cap at 2 % and 1.5 % of the current balance) and 18 cells (floor_cap at a fixed 100 USD, 5,000 USD only) | descriptive, exposed | personal-account.json, personal-account-cap.json, personal-account-cap-fixed.json (b818e99): `meta.grid`, `meta.cells` |
| M1, H7x, C1, C1b | 5; 2 x 2 reads; 4; 1 | 0 | crypto-cfd-phase.md:57 |
| Wyckoff re-test | 7 confirmatory cells; 13 engine-ablation arms with 78 descriptive cells | cells: 1 INCONCLUSIVE, 2 NO MECHANICAL EDGE, 3 AGAINST THE BOOK, 1 FAIL; ablation: one positive pocket of the 78, found after the fact | docs/audits/2026-10-04-wyckoff-retest.md:8, :20-26, :58 at 9dfb31e; research-ledger.json `wyckoff_retest` |
| CX (sealed, not run) | 4 primary tests; reads A 3, B 1 | pending | docs/plans/2026-10-04-edge-cx-ftmo-crypto-preregistration.md:135 |
| WY-F1 (draft) | 1 test, 1 forward read | pending | docs/plans/2026-10-04-wyckoff-forward-wc15-preregistration-DRAFT.md §13 |

## 5. Open owner decisions (quoted options)

1. (Decided by the lead, 2026-10-04: VC window B decisive, window A report-only. Kept here so the numbering holds.)
2. Oil in the B2 export: "add UKOIL.cash, USOIL.cash" (recommended) or "no".
3. CX-WE: "seal the weekend split before the CX discovery read" or "drop it" (recommended: drop; low prior).
4. VC on the personal account if VC gold passes: "no" (default, lead decision 2026-10-04) or "yes, after TF passes
   (forward confirmation), replayed first with personal_account.py". A yes needs a row-filter option in that script,
   which the personal-account workflow owns (VC draft §9).
5. Crypto swap: "hold one demo crypto position overnight to measure swap" (recommended) or "treat multi-day crypto on FTMO
   as infeasible".
6. CAL: "forward only" (default, B6; the lead keeps it) or "override B6 for one history read without the G7 / M1 days".
7. NEWS-FLAT: "write its pre-registration next" (recommended) or "wait".
8. XAUEUR, XAUAUD in the same export: "yes" (recommended: cheap) or "no".

## 6. Where I may be wrong

- The swap reading for crypto (mode 5, -30) is my interpretation of an MQL5 enum I could not confirm here; one demo
  position settles it.
- The OIL 5m depth is unknown; if FTMO keeps only recent 5m bars, OIL has no discovery window and becomes forward-only.
- VC's holdout is not pristine: H7 / G9 were selected on those years. Window B is the cleanest piece left, and it is small
  (~950 trades, an estimate from the discovery rate; MDE ~0.14-0.15 R for T1a). A pass is discovery grade: it says the
  gradient is not a 2018+ accident, it does not re-validate H7 / G9, and TF must confirm it.
- VC's T1b statistic (nb-weighted R per sqrt(bar)) removes a constant per-bar edge exactly only without stops; with the
  stop it leans slightly against a pass (about -0.01 R, synthetic, VC §7). The size of the raw-R mechanical gradient
  (+0.03 to +0.05 R) and T1b's MDE depend on the entry-time mix I assumed; the dry run's planned-bar counts replace both.
- The M1 read days counted for CAL are a conservative reading: M1's falsification rows were signed returns with an OLS
  intercept, not a pre-holiday mean. Under the strict §0 rule they are "seen", not "read for CAL"; I excluded them anyway.
- VC-X's check of the CX files assumes field names that `scripts/research/edge_cx.py` (not written yet) must match.
- Priors are judgement, stated so they can be argued with.
