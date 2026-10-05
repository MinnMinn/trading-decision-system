# Family NF -- be flat across HIGH-impact US releases on fvg-book v4 (H7 + G9 XAUUSD, stop_k 1.4) -- pre-registration DRAFT (2026-10-04) [NF-P1]

Status: DRAFT. Not sealed.

Sealing: the coordinator commits this text, after review, as
`docs/plans/2026-10-04-news-flat-preregistration.md`, with the status line above replaced by a line that reads exactly
"Status: SEALED", and with §12's manifest filled in (the code-sha256 lines, the one calendar-history line and the one dataset
line), and in the same commit the ledger entry of §7. Until then `scripts/research/news_flat.py` refuses both reads
(scripts/research/prereg_guard.py `require_sealed`, `require_fingerprint`; `news_flat.require_calendar_history`,
`news_flat.require_ledger`; the exposed read also `news_flat.require_dataset` and `require_vc_first`), and it runs each read once (`require_read_once`: one output name per read, refused if that
read's output exists or was ever committed). This draft file stays in the repository beside the sealed text: the tests read
it.

**No outcome of this family has been read.** The code was tested on synthetic calendars, rows and bars only
(`scripts/tests/test_news_flat.py`). The calendar build read no market data. The one market-data run is the outcome-blind
dry run of §6 (entry times, planned exits and calendar overlaps; no exit walk, no R). Rank 3 in
docs/plans/2026-10-04-research-directions.md §1 (entry 3); the pending owner step A2
(docs/audits/2026-10-04-crypto-cfd-phase.md:48-49; docs/audits/2026-10-03-vol-schedule.md §4, option 2).

## Tóm tắt (VI)

1. **Câu hỏi.** Đóng lệnh v4 (H7 + G9 vàng, stop 1,4) trước tin lớn của Mỹ (NFP, CPI, FOMC và họp báo FOMC) thì bỏ được
   phần đuôi gap (lệnh lỗ quá 1 %) với giá bao nhiêu R? Đây là bước A2 còn treo.
2. **Lịch tin có nguồn.** `data/calendar/us-high-impact-releases.json`: 866 dòng 2004 -> 2027, mỗi dòng trích nguyên văn
   tài liệu gốc (bls.gov, federalreserve.gov, hoặc bản lưu archive.org của chính trang đó), kèm sha256 và giờ tải. Giờ
   FOMC 2004-01 -> 2006-06 (20 phiên) và giờ họp báo 2012 (5 buổi) KHÔNG có nguồn: ghi UNKNOWN, các lệnh quanh đó bị loại
   khỏi cả ba chính sách (không bao giờ coi là "không có tin").
3. **Ba chính sách (chốt bây giờ):** P0 như hiện tại; P1 không vào lệnh mới trong [T-10, T+10] phút (đúng luật live
   đang chạy); P2 = P1 + đóng mọi lệnh đang mở lúc T-10 (giá đóng nến kết thúc đúng T-10; phí thoát tính ở mức p90, thận
   trọng), tín hiệu sau cửa sổ vẫn vào. Thiếu nến tại T-10 -> lệnh UNKNOWN, bị loại khỏi cả ba.
4. **Đo trên lịch sử (POLICY-EXPOSED, mô tả):** mean R, lệnh tệ nhất (% tài khoản ở 1 %), số lệnh gap qua stop, số lệnh
   mất, FTMO (replay thi quỹ, số ngày vượt 5 %). Chạy SAU lần đọc vùng B của VC (để không làm lộ vùng B). Dry run chỉ
   đếm (không kết quả): 5.979 lệnh v4 (khớp kiểm toán A1); P1 chặn 88 lệnh vào; 562 lệnh đang mở lúc T-10 (trần của số
   lệnh P2 đóng), khoảng 26 lệnh/năm trên 401 ngày tin.
5. **Test công bằng = forward (paper log), luật chốt bây giờ:** đo chi phí của P2 so với P1 trên các lệnh bị đóng sớm,
   cả hai vế tính cùng một bảng phí, lịch tin lấy đúng phiên bản đã commit tại thời điểm quyết định. Đủ 50 lệnh hoặc 36
   tháng. CHEAP nếu cận dưới 90 % một phía của chi phí > -0,20R/lệnh -> P2 thành ứng viên v5, anh quyết. Biên 0,10R như
   bản nháp đầu chỉ chứng nhận "miễn phí" được khoảng 34-42 % số lần dù P2 thật sự miễn phí (§6); khuyến nghị 0,20R,
   anh chọn (§11). Tài khoản cá nhân 5.000 USD: chỉ mô tả cách replay, không chạy.
6. **Mâu thuẫn với VC:** nếu VC đúng (ngày biến động mạnh là ngày tốt), P2 có thể cắt edge. Kết quả nào cũng đọc được
   (§9).
7. **Ngân sách (§43):** 1 giả thuyết, 3 chính sách (P0 là mốc, P1 là luật live, P2 là ứng viên), 0 quét tham số, 2 lần
   đọc (lịch sử mô tả + forward), 1 test quyết định (forward). Sổ nghiên cứu phải có mục `news_flat` trước lần đọc đầu (§7).

## 0. Origin (disclosed) and question

- **The tail.** v4 trades k = 1.4. Its worst historical trade lost 1.39 % of the balance at 1 % risk
  (docs/audits/2026-10-03-vol-schedule.md:12). The worst trades were news gaps found post hoc: 2012-06-01, entry 25 minutes
  before the payrolls release, and 2021-03-17, entry 45 minutes before the FOMC statement (vol-schedule.md:37-43). A bar that
  opens beyond the stop fills at its open (scripts/research/book_sim.py:66), so a stop cannot cap a release jump. NF cannot
  remove the whole tail. Of the four trades above 1.05 % at k = 1.4 (docs/audits/2026-10-04-gap-tail-counts.json, case "A1
  k=1.4", `worst5`), three entered on a release day of this calendar (2012-06-01 at 01:10 and 12:05 UTC, 2021-03-17 at 17:15
  UTC); the fourth (2010-03-10, 03:05 UTC) and the fifth (2015-09-15, 20:45 UTC, 1.048 %) entered on no release day. I did not
  read these trades' exits; whether P2 would have closed the first three before their loss is for the exposed read.
- **The owner's tolerance** (set after those results): "Khoảng 1,5%, 2 lần trong 1 năm"
  (docs/audits/2026-10-04-a1-under-owner-tolerance.md:8-9). On history v4 meets it: losses above 1.05 % happened 4 times in
  22.2 years, above 1.5 % never (a1-under-owner-tolerance.md:32-33). So NF is insurance for a stricter cap, and its price
  is the question.
- **What runs live today.** The demo executor blocks NEW entries inside an event-risk window (scripts/fvg_demo.py:24,
  :435-438, through scripts/event_risk.py) and never closes an open position for news: `existing_positions.action` is HOLD
  (docs/architecture/event-calendar.json:44-46; scripts/event_risk.py:273). The research replay (book_sim) has no calendar at
  all, and the live calendar is a 2026 snapshot (vol-schedule.md:43). So P1 below replays the live entry rule for the three
  release types; P2 is the A2 question proper.
- **Question.** On v4's trades, what does being flat across scheduled HIGH-impact US releases buy (the gap tail) and cost
  (R)? The history answers descriptively; a forward read with a rule fixed now decides.

## 1. The calendar (data, sourced, point in time)

File: `data/calendar/us-high-impact-releases.json` (schema `nf-calendar/1`, snapshot `us-hi-2026-10-04-a`). Loader:
`news_flat.load_calendar`; `python3 scripts/research/news_flat.py check-calendar` prints its counts.

- **Release types (HIGH by type, fixed before any outcome):** Employment Situation (NFP), Consumer Price Index (CPI), FOMC
  statement, FOMC Chair press conference. These are HIGH in the live policy's scope (docs/architecture/event-calendar.json:12).
  The class never depends on the market's reaction. Not covered: PCE and the GDP advance estimate, which the live calendar
  also restricts (same line). NF's P1 is therefore the live rule for these three release families only (§10).
- **Rows:** 866. NFP 273 released, 2 scheduled, 5 postponed, 1 cancelled. CPI 272 / 3 / 5 / 1. FOMC statements 181
  released (161 with a time, 20 time UNKNOWN), 10 scheduled, 1 cancelled, 8 unscheduled (report only). Press conferences 93
  released (88 with a time, 5 UNKNOWN), 10 scheduled, 1 cancelled.
- **Coverage:** from 2004-01-01 (the XAUUSD 5m history starts 2004-06-11) through 2026-12-04 (NFP), 2026-12-10 (CPI) and
  2027-12-08 (FOMC). BLS has not published its 2027 dates; the forward read refuses while the calendar does not cover its
  window (§4).
- **Sources (every row; 1,059 cited source documents, each with sha256 and retrieval time).** NFP and CPI: each release's own
  document in the bls.gov archive, quoted at its embargo line, e.g. "Transmission of material in this release is
  embargoed USDL-12-1070 until 8:30 a.m. (EDT) Friday, June 1, 2012". FOMC statement dates: the federalreserve.gov FOMC
  calendar pages and each statement page. FOMC statement times: the minutes of each meeting from August 2006 (e.g. March
  2008: "The vote encompassed approval of the statement below to be released at 2:15 p.m."), and the Fed's standing
  announcements (2011-03-24: 12:30 p.m. on briefing days; 2013-03-13: 2 p.m. and news conferences at about 2:30 p.m.;
  2024-08-09 and 2025-09-05: "The Committee releases a policy statement at 2 p.m. Eastern Time ... and the Chair holds a
  news conference at 2:30 p.m."). All 2,181 quotes were checked verbatim against the stored bodies before the file was
  written.
- **UNKNOWN (never guessed):** the release time of the 20 FOMC statements from 2004-01-28 to 2006-06-29 (the pages say only
  "For immediate release"; the minutes record the time only from August 2006), and the start time of the 5 press
  conferences of 2012. Trades near these rows leave all three policies (§2).
- **Point in time.** `available_time` = the earliest evidence that a row's date and time were public, an upper bound
  (later than the truth is conservative). NFP and CPI: the previous release's own sentence ("The Employment Situation for May
  is scheduled to be released on Friday, June 1, 2012, at 8:30 a.m. (EDT)."), public at that release's embargo time. FOMC:
  the tentative-schedule release (publication time from the Fed's press-release feed, else the end of its date in New York),
  or an archive.org capture of the FOMC calendar page for the five meetings extended to two days after their schedule (four
  in 2009, one in 2011). The shortest lead from availability to release is 4.4 days (2013-10-22 NFP).
- **Deviations (sourced):** the 2013 lapse in appropriations (NFP 2013-10-04 -> 10-22, CPI 10-16 -> 10-30, NFP 11-01 ->
  11-08, CPI 11-15 -> 11-20); the 2025 lapse (NFP 2025-10-03 -> 11-20, CPI 10-15 -> 10-24, October 2025 NFP and CPI
  cancelled, NFP 12-05 -> 12-16, CPI 12-10 -> 12-18); the 2026 lapse (NFP 2026-02-06 -> 02-11, CPI 02-11 -> 02-13); the
  FOMC meeting of 2020-03-17/18 cancelled (replaced by the unscheduled meeting of 2020-03-15). An announced date that did not
  happen stays as a `postponed` or `cancelled` row with `withdrawn_available_time`, the first evidence that it would not
  happen. Where no explicit BLS statement before the release time was found (NFP 2025-10-03), that time is null and a
  point-in-time reader keeps the release expected (conservative). 2018-19: no NFP or CPI release moved.
- **Discrepancies recorded, not used:** the 2012-12-07 NFP document prints "(EDT)" on a December date (8:30 a.m. New York
  is used); the press-conference pages and the press-release feed show 12:20 or 12:35 p.m. for four 2012 statements whose
  minutes record the approved 12:30 p.m. (the minutes are used). Windows use the scheduled time; `actual_release_time` is
  never used to move a window (CLAUDE.md §27).
- **Build and what is kept.** A scratch builder fetched bls.gov and federalreserve.gov directly and archive.org raw captures
  (`id_`) of the same publishers' pages. The builder, its fetch log and the fetched bodies (about 430 MB) lived in a session
  scratch folder that no longer exists; they are NOT in the repository. What is kept is in the calendar file: for every row its
  source URLs, each body's sha256 and retrieval time, and the verbatim quote. A row is re-checkable against the publisher
  (an archive.org capture is permanent; a live page may have changed since). The 2,181-quote check above ran while the
  bodies existed and cannot be repeated now. The calendar's `snapshot` names the builder only as a session script.

## 2. The three policies (fixed now; nothing else is run)

Defaults of CLAUDE.md §24: pre = post = 10 minutes. A restricted window of a release at T is [T - 10 min, T + 10 min],
closed (as scripts/event_risk.py:258); overlapping and touching windows join (scripts/event_risk.py:233; CLAUDE.md §30).

| policy | rule | code |
|---|---|---|
| P0 | v4 rows as `book_sim.trades(..., stop_k=1.4)` gives them for H7_XAUUSD_eod and G9_XAUUSD_eod | `apply_policies` |
| P1 | drop a row whose entry time lies in a window known at the entry (the live entry rule) | `classify` |
| P2 | P1, and close every position still open at a window start s (known at s) at the CLOSE of the 5m bar that ends exactly at s (no such bar: the trade is UNKNOWN); the flatten leg is priced at the p90 spread; a flattened trade is not resumed; signals entering after the window are taken | `classify`, `flatten_row`, `series_cutter` |

- **Why "re-enter after the window" and not "no re-entry that day".** The hypothesis is about a position open THROUGH the
  release instant. Keeping later signals isolates that one effect. Dropping the rest of the day would add a second effect
  (the post-release trend, which VC suggests may be the best part; §9).
- **Why no wider window.** ±10 minutes is the live default, and the jump happens at T. A wider window is one more variant on
  exposed data without a mechanism.
- **Flattened trade arithmetic** = book_sim's: R = (side x (exit - entry) - cost) / stop distance
  (scripts/research/book_sim.py:59, :74-76); the adverse path is cut at the cut bar, so the floating-loss inputs stay exact.
  **Cost, conservative:** the entry leg at the median spread, as for the held trade; the flatten leg at the **p90** spread of its
  hour bucket (`edge_census.Costs.leg_at(t, "p90")`), because the minutes before a release are not the median hour. book_sim
  prices a held trade's exit at the rollover-hour median; pricing P2's exit at the p90 of a liquid hour keeps a model artefact
  from crediting P2. Two sensitivities are reported and never decide: the flatten leg at book_sim's median pricing
  (`R_med`), and the flatten priced with the held trade's own cost (`R_neutral`). The credit the median pricing could give P2 is
  small against the margin: gold's round trip is about 0.65 bp (docs/plans/2026-10-03-reframes.md:88) against a median stop of
  about 100 bp, so five times the median at the rollover leg is worth under 0.015 R.
- **A missing bar is UNKNOWN, not a stale price.** The cut bar must end exactly at the window start. A data gap there (the
  dry run counts none in the stored history) makes the trade UNKNOWN in all three policies (CLAUDE.md §20, §32); the read
  never uses an earlier bar's close.
- **Point in time.** A row restricts a decision at time t only if `available_time` <= t and it is not withdrawn by t
  (`news_flat.expected`). Decision times: the entry for P1 and for UNKNOWN, the window start for P2. In the exposed read the
  calendar is one state and each row's `available_time` carries what was public when. In the forward read the calendar is the
  version COMMITTED at each decision time (`news_flat.AsOf`, from `git log` / `git show` of the calendar file), so a row added,
  edited or backdated after a decision cannot steer it, and a day the committed calendar did not yet cover is UNKNOWN, never
  "no news". Commit dates are as trustworthy as git's; the seal instant rests on the same assumption. Unscheduled FOMC actions
  never restrict (nobody could know them in advance; 8 rows, report only).
- **UNKNOWN is never "no news" (CLAUDE.md §25, §32).** A row without an impact loads as UNKNOWN and restricts like HIGH; LOW
  and MEDIUM do not restrict (none exist in this file). A trade is UNKNOWN when it is outside coverage, overlaps the New
  York date of a row whose time is UNKNOWN (widened by the buffers), or overlaps the window of a row whose availability is
  UNKNOWN at the decision. UNKNOWN is judged on the PLANNED span, the entry to the end of its server day, which is known at
  the entry; never on the realised exit, so that a stop hit cannot decide which trades the news filter removes (CLAUDE.md
  §37; `classify`, `server_day_end`, tested). UNKNOWN trades leave P0, P1 and P2 alike (identical rows, CLAUDE.md §49) and
  are counted with their reason. From the XAU start, 22 calendar rows are UNKNOWN in time (17 statements 2004-06-30 ->
  2006-06-29, 5 press conferences of 2012); the dry run puts 20 of the 5,979 trades there (0.3 %).
- **A dropped or flattened entry is not replaced.** H7 filters `edge_census.ev_prev_day` events by momentum
  (scripts/research/edge_f3.py:134-138) and `ev_prev_day` returns the first event per (server day, side)
  (scripts/research/edge_census.py:215, `_first_per_day`); G9 emits at most one event per server day, the first close beyond a
  band (scripts/research/edge_f4.py:193-195). The executor acts only on the latest bar's event (scripts/fvg_demo.py:415-418,
  :425), so a blocked first signal is not followed by a second one. The replay and the live rule agree on this.

## 3. Measurement on the exposed history (POLICY-EXPOSED, descriptive; one read)

- **Data, fixed end, pinned.** FTMO-Demo XAUUSD 5m bars from 2004-06-11 to the export end, and no later: the read sees the
  stored bars BEFORE `EXPOSED_END = 2026-10-03T00:00:00Z` only (the stored history ends 2026-10-02T20:45:00Z), through a
  capped loader (`news_flat.capped`), so a re-export after the seal cannot feed this descriptive read with forward days
  (CLAUDE.md §44) or move the dense-day median (scripts/research/edge_census.py:104-107). The sha256 of exactly those bars
  (`prereg_guard.candles_digest`) is pinned in the sealed text as one `dataset-sha256` line and checked before the read
  (`dataset_line`, `require_dataset`); an edit of an old bar refuses the read. Every v4 trade on these years was read before
  (vol-schedule.md:3); the label is POLICY-EXPOSED (docs/plans/2026-10-04-personal-account-backtest-design.md:64). No pass or
  fail: the numbers inform; the forward read decides.
- **Research-mode rows, disclosed.** The rows are book_sim's (the A1 population, 5,979 trades). In research mode a day has a
  sigma only if the whole day proves dense (scripts/research/edge_census.py:121-124), so signals on days that later prove sparse
  are dropped; a point-in-time replay adds 55 H7 and 78 G9 trades over the full history (+2.2 %) with identical R on the
  common ones (docs/audits/2026-10-04-density-selection-check.md:16, :18), and the VC draft measures about 11 % in window B
  (before 2008-12-10; VC-P1 §2). The exposed read describes the research-mode population; the forward read runs on the paper
  log, which is point in time.
- **Per policy** (`news_flat.summary`): trades, mean R, sd R, sum R and by year; worst trade in % of the balance at 1 %
  risk; gap-through stops (stop exits below -1.05 R, the honest count of vol-schedule.md:39-45); stop share; trades
  flattened.
- **Trades lost and changed:** P1 vs P0, the dropped rows and their R; P2 vs P1, the paired dR on flattened trades (mean,
  CR1 standard error by release day, one-sided 90 % bounds: `news_flat.paired_delta`), also by release type and year in the
  bookkeeping, with the two cost sensitivities of §2 (`R_med`, `R_neutral`). The read records its cost profile
  (`cost_profile`: the profile name, the sha256 of the symbol's spec file, the `price_ref` provenance; as edge_vc.cost_profile).
- **FTMO (challenge layer).** For each policy's rows: `pass_policy.prepare` and `pass_policy.evaluate_hist` on the
  selection starts (before 2024) and the confirmation starts (2024 on), Phase 1 +10 %, Phase 2 +5 %, 5 % daily and 10 %
  total loss limits, floating `mae` bound, risk 1 % with the dd3 throttle (scripts/research/pass_policy.py:27, :74, :161,
  :205): first-attempt fail, funded within 91 / 122 days, median days. Plus the FTMO daily-loss breach days at a fixed 1 %
  (realised, and every trade at its worst excursion at once): `news_flat.daily_breach_days`.
- **Personal 5,000 USD account: described, not run** (§8).
- **Ordering.** This read runs only after VC's window-B read (`edge-vc-xau-holdout`) is committed (`news_flat.AFTER_VC`,
  `require_vc_first`), because it reports R on release days of the years VC decides on (VC-P1 §3). If VC is withdrawn,
  the coordinator sets `AFTER_VC = False` before sealing and records it here.

## 4. The FAIR test: forward, rule fixed now (one read)

- **Rows.** The forward paper log (`data/live/forward/fvg-paper.jsonl`, scripts/research/fvg_forward.py): components
  H7_XAUUSD_eod and G9_XAUUSD_eod, status closed, `stop_k` 1.4, server day on or after the first forward day after the seal
  commit (`prereg_guard.first_forward_day`; no date is typed). The paper log takes every signal (no event gate), so P0, P1
  and P2 are all defined on it. The paper log is untracked and rewritten by `resolve` (scripts/research/fvg_forward.py:300-310;
  .gitignore): the read records its sha256 and row count, and the merged bars' digest, count, first and last bar, and the
  forward store and live bridge files' sha256 (`forward_snapshot`).
- **One cost basis for both legs.** The log's own R was priced when each row resolved, with the cost table current then (none
  recorded). The read re-prices every row from its logged entry and exit prices with the read-time cost table
  (`reprice_paper_row`; the log's figure is kept as `R_logged`), and prices the flatten with the same table (the p90 flatten
  leg of §2), so dR never carries a cost-table change between the two dates.
- **Calendar, point in time: the version committed at each decision.** `news_flat.AsOf` loads every committed version of the
  calendar file (`git log`, `git show`) and each decision reads the latest version committed at or before its own time (the
  entry for P1 and UNKNOWN, the window start for P2). So a release row appended or edited after a decision does not count, a
  withdrawal backdated in a later commit does not count, and a day that the committed calendar did not cover yet is UNKNOWN
  (excluded from all three policies and counted), never silently "no news" (CLAUDE.md §29, §32). The read refuses to start
  unless the latest calendar covers the whole forward window (BLS's 2027 dates must be appended when BLS publishes them); a
  version that does not load is a refusal, not a skipped version.
- **Statistic.** dR = R_P2 - R_P1 on the forward trades P2 flattens; mean over them; CR1 standard error clustered by the
  release day; one-sided 90 % bounds (normal quantile 1.2816).
- **Due.** At least 50 flattened trades, or 36 months after the seal, whichever comes first (`forward_due`). The clock is
  the last full server day the merged bars hold (`last_full_day`), never the wall clock, so a re-run gives the same answer.
  Not due: refused.
- **Decision** (`forward_verdict`):
  - **CHEAP** if the lower bound > -0.20 R (the margin, `MARGIN_R`): P2's cost per flattened trade is credibly below the
    margin. This is a gate to CANDIDACY, not adoption: P2 becomes a CANDIDATE for v5 (= v4 + flat across HIGH US releases) for
    owner review, who sees the estimate, its interval and the two sensitivities (CLAUDE.md §47).
  - else **COSTLY** if the upper bound < 0: flattening credibly costs R. v4 stays; NEWS-FLAT is closed; the tail is governed
    by the owner's 1.5 % tolerance.
  - else **INCONCLUSIVE**, and always when the trades come from fewer than 20 release days. v4 stays.
- **The margin, 0.20 R per flattened trade,** is the largest cost the gate tolerates. It is fixed now, before any forward
  row; the owner may set another value before the seal (§11). The first draft had 0.10 R; at 50 flattened trades that
  certifies a truly free P2 only 34-42 % of the time (§6), so INCONCLUSIVE would be the likely verdict whatever the truth.
  0.20 R certifies it 67-81 % of the time and errs in about 10 % of reads when the true cost equals the margin. In money:
  at the history's rate (at most about 26 flattened trades a year, §6) 0.20 R is at most about 5.2 R a year, 18 % of the
  roughly 29 R a year that v4 earned at its measured edge (269 trades a year x 0.109 R; a1-under-owner-tolerance.md:63;
  vol-schedule.md:6) and about 35 % of it at the 50 % haircut the repo applies to edges
  (docs/plans/2026-10-04-personal-account-backtest-design.md:66). Per flattened trade, 0.20 R is about twice v4's mean R per
  trade (0.109): that is why it is a gate to candidacy and not a price the owner is asked to accept.

## 5. Windows: what has been read (strict, CLAUDE.md §44)

- History 2004-06 -> 2026-10-02: EXPOSED. Every v4 trade was read for H7 / G9 and A1. I found no release-window split of v4's
  R in docs/audits (a grep for payrolls and release: only the post-hoc tail diagnostic of vol-schedule.md:37-43 and the
  per-year gap counts of gap-tail-counts.json), but the idea came from those post-hoc tail trades, so the history cannot
  validate it.
- XAU window B (before 2008-12-10) is VC's decisive window, UNREAD for its split: hence the ordering in §3. The exposed read
  sees bars before `EXPOSED_END` only; the forward window (from the server day after the seal) stays FRESH because no read
  before the forward read sees a bar after the stored history's end.
- Forward from the server day after the seal: FRESH.

## 6. Dry-run counts, power and prior (arithmetic and counts before any read)

- **Outcome-blind dry run, done 2026-10-05** (`python3 scripts/research/news_flat.py dry-run --out <scratch json>`, through the
  capped loader of §3): planned entries from the same detectors and skips as `book_sim.trades`
  (scripts/research/book_sim.py:48-57), the planned exit (the server day's last bar), bar existence at each window start, and
  the calendar. No exit walk, no price, no R. Pinned bars: `dataset-sha256
  54f081ad628b313396f648f15e5e5bdc5f676f0dd77ac171287ccde21b11cbd6 XAUUSD|5m before 2026-10-03T00:00:00Z`
  (`dataset_line`; the stored files' `history_store` digest is `aab48876...b55180`); calendar sha256
  `7ac2f56777b91b9c55d02340836888620fe3b22f46158912b90fdfe5bc1b25a2`; `counts` sha256
  `0b2e49c1860ba8a7d4f18d12c14493200e1950a8e4881c39b35fbaa947ec4187` (a re-run from the final code must give identical
  `counts`; the sealing step re-checks it). The dry-run JSON is in the session scratch folder, not in the repository (the
  table below carries its numbers).
- **The total is the audit's:** 5,979 planned trades (H7 2,430, G9 3,549), the count of the A1 study
  (docs/audits/2026-10-03-vol-schedule.md:6; docs/audits/2026-10-04-density-selection-check.md:16, :18). So the dry run
  reproduces book_sim's entry set exactly.
- **Counts, 2004-06 -> 2026-10-02, both components:**

| item | all | H7 | G9 | note |
|---|---|---|---|---|
| planned trades | 5,979 | 2,430 | 3,549 | |
| P1: entry inside a known window | 88 (1.5 %) | 34 | 54 | NFP 36, CPI 33, FOMC statement 16, press conference 3 |
| P2: open at a window start (planned) | 562 (9.4 %) | 232 | 330 | NFP 192, CPI 209, FOMC statement 161; on 401 release days |
| no bar ending at the window start | 0 | 0 | 0 | none: the exact-bar rule of §2 costs nothing in the stored history |
| UNKNOWN (left out of all policies) | 20 (0.3 %) | 10 | 10 | 8 by an UNKNOWN statement time (2005-06), 12 by an UNKNOWN press-conference availability (2012) |

  "Open at a window start" is an upper bound on the trades P2 flattens: a stop may close a trade before the window.

| year | planned | P1 blocks | open at a window start | release days | UNKNOWN |
|---|---|---|---|---|---|
| 2004 | 24 | 0 | 3 | 2 | 0 |
| 2005 | 73 | 0 | 2 | 2 | 3 |
| 2006 | 176 | 0 | 15 | 12 | 5 |
| 2007 | 249 | 1 | 29 | 19 | 0 |
| 2008 | 291 | 2 | 29 | 20 | 0 |
| 2009 | 281 | 0 | 30 | 21 | 0 |
| 2010 | 277 | 1 | 34 | 23 | 0 |
| 2011 | 288 | 1 | 26 | 20 | 0 |
| 2012 | 261 | 2 | 18 | 12 | 12 |
| 2013 | 265 | 2 | 35 | 23 | 0 |
| 2014 | 268 | 3 | 33 | 24 | 0 |
| 2015 | 269 | 4 | 36 | 24 | 0 |
| 2016 | 276 | 2 | 38 | 23 | 0 |
| 2017 | 294 | 2 | 29 | 21 | 0 |
| 2018 | 295 | 5 | 27 | 21 | 0 |
| 2019 | 298 | 1 | 38 | 25 | 0 |
| 2020 | 301 | 0 | 24 | 18 | 0 |
| 2021 | 288 | 7 | 22 | 19 | 0 |
| 2022 | 318 | 16 | 14 | 12 | 0 |
| 2023 | 309 | 15 | 15 | 11 | 0 |
| 2024 | 310 | 10 | 26 | 19 | 0 |
| 2025 | 328 | 8 | 21 | 17 | 0 |
| 2026 (to Oct 2) | 240 | 6 | 18 | 13 | 0 |

- **Rate.** Open at a window start per year, 2005-2025: mean 25.8, median 27, range 2-38; 2021-2025: 22, 14, 15, 26, 21
  (mean 19.6). Release days carrying such a trade: mean 18.4 a year, 2021-2025: 19, 12, 11, 19, 17. P1 blocks 2021-2025: 7, 16,
  15, 10, 8 (more than before 2021). With about 20 flattened trades a year, 50 take about 2.5 years and the 36-month cap
  (about 60 trades) is about as likely to bind; the 20-release-day floor of §4 is met after about 1.3 years and does not bind.
- **Power (assumptions stated; arithmetic, no market data).** dR = R_P2 - R_P1 on the flattened trades. P(verdict) =
  Phi((true dR + margin) / SE - 1.2816) for CHEAP; Phi(-true dR / SE - 1.2816) for COSTLY; SE = sd(dR) / sqrt(n) x 1.10 (the
  1.10 allows for 1.4 trades per release day, 562 / 401; an assumption). sd(dR) is not known before a read: 0.75 is v4's
  per-trade sd (a1-under-owner-tolerance.md:64), a conservative stand-in because a paired difference is probably tighter; 0.60
  is my estimate for the part of the hold after the window (an assumption). n = 50:

| sd(dR) | margin | P(CHEAP) if the true dR is 0 | -0.05 | -0.10 | -0.20 |
|---|---|---|---|---|---|
| 0.75 (SE 0.117) | 0.10 | 0.34 | 0.20 | 0.10 | 0.02 |
| 0.75 | **0.20** | **0.67** | 0.50 | 0.34 | 0.10 |
| 0.75 | 0.25 | 0.81 | 0.67 | 0.50 | 0.20 |
| 0.60 (SE 0.093) | 0.10 | 0.42 | 0.23 | 0.10 | 0.01 |
| 0.60 | **0.20** | **0.81** | 0.63 | 0.42 | 0.10 |
| 0.60 | 0.25 | 0.92 | 0.81 | 0.63 | 0.23 |

  P(COSTLY) if the true dR is -0.20 / -0.30: 0.67 / 0.90 at sd 0.75; 0.81 / 0.97 at sd 0.60. At n = 60 the CHEAP columns
  rise by 0.03-0.05. Reading: at the first draft's 0.10 R margin a truly free P2 is certified 34-42 % of the time and the
  likely verdict is INCONCLUSIVE whatever the truth; at 0.20 R it is 67-81 %. The test catches a cost of 0.20 R or more
  about two times in three, and a cost of 0.30 R about nine times in ten.
- **Two things the mean contains.** (1) If the edge accrues evenly in time, flattening gives up the part of the hold after the
  window: about 0.04-0.07 R per flattened trade (v4's mean R of 0.109 times the share left, roughly 25-60 %; an assumption), so
  a true dR near -0.05 is the mechanical expectation when release windows carry no extra edge. VC's tension (§9) is about the
  excess beyond that. (2) One avoided gap-through-stop (dR about +1.4) among 50 trades adds +0.03 R to the mean; the verdict
  reads the mean, so a lucky draw can lift it.
- Prior: high that P2 removes the scheduled-release part of the tail (by construction), but not all of it (§0: two of the
  five worst trades are on no release day); unknown sign on value (docs/plans/2026-10-04-research-directions.md §1, entry 3).

## 7. Budget (CLAUDE.md §43) and the ledger entry

| counter | NF-P1 |
|---|---|
| hypotheses | 1: being flat across scheduled HIGH US releases removes the release-gap tail of v4 at an acceptable cost in R |
| candidates | 1: v5 = v4 + P2, only if the forward verdict is CHEAP. P0 is the reference, P1 the live rule replayed |
| policies run | 3 (P0, P1, P2); nothing else |
| parameter searches | 0. Buffers are the §24 defaults; the margin (0.20 R), the due rule (50 / 36 months) and the cluster floor (20) are fixed in this text. A wider window and "no re-entry that day" were weighed in §2 and not run |
| reads | 2: exposed history (descriptive, no test), forward (one decisive test: P2 against P1, non-inferiority) |
| dry runs | 1, counts only (§6) |
| dataset reuse | XAUUSD 5m 2004-06 -> 2026-10: read before by F3 / F4 (origin of H7 / G9), A1 and the personal-account replays (research-directions §4 table); this read adds 1. The forward paper log: 1 read |
| OOS reuse and exposed OOS periods | none newly exposed: the history is already EXPOSED. XAU window B stays unread for VC's split until VC reads it; NF reads it after (§3) |
| rejected before any outcome | the wider window; "no re-entry that day"; sizing for the gap (A2 option 1, vol-schedule.md:50-51: a separate study) |
| multiple testing | one decisive forward test, no selection among candidates: no correction needed. The history is a description, not a test |

research-directions §4 lists NEWS-FLAT as "2-3 policies, 1 read, POLICY-EXPOSED"; this draft has 3 policies and 2 reads (the
descriptive history read and the forward read).

**Ledger entry** (the seal commit adds it to `docs/architecture/research-ledger.json`; `news_flat.require_ledger` refuses a read
without it, and without the right counts):

```
"news_flat": {"preregistration": "docs/plans/2026-10-04-news-flat-preregistration.md", "tag": "[NF-P1]", "policies": 3,
              "reads": 2, "hypotheses": 1, "candidates": 1, "parameter_searches": 0,
              "grade": {"history": "POLICY-EXPOSED", "forward": "FRESH"},
              "calendar": "data/calendar/us-high-impact-releases.json"}
```

## 8. What a result changes (both account layers; described, not run)

- **FTMO challenge layer.** The exposed read already replays each policy through the challenge machinery (§3). After a
  CHEAP forward verdict and an owner yes: v5 = v4 + P2 is a NEW Trading System version (CLAUDE.md §47). The demo executor
  needs a flatten-before-release action (today HOLD) and the calendar rows in its live calendar: live code and config, out
  of this study's scope, done under the owner's change process. No funded-stage claim follows from the demo
  (a1-under-owner-tolerance.md:56-59).
- **Personal 5,000 USD account.** `scripts/research/personal_account.py` replays whole book_sim components (`BOOKS`,
  scripts/research/personal_account.py:241-243) and has no row transform. P2 changes rows (R, exit time, a cut adverse path),
  so the personal-account workflow, which owns that file, would add a row-transform hook and replay v4 vs v4 + P2
  descriptively (5,000 USD, the minimum lot, the owner's 100 USD capped minimum-lot mode, compounding, ruin). NF's flattened
  rows keep a truncated `adv_path_R`, so the exact floating floor (personal-account design A6) stays computable. Nothing is
  run for the personal account in this family.
- **COSTLY or INCONCLUSIVE:** v4 unchanged on both layers. The owner may still choose P2 as a pure risk preference; that
  would be recorded as an owner decision on POLICY-EXPOSED data, not as a validated result.

## 9. The VC tension (stated before any read) and how each result is read

VC-P1 asks whether the edge concentrates on volatile days and on early entries. Release days are volatile days, so
flattening could cut the edge.

| VC (gold window B) | NF forward | reading |
|---|---|---|
| passes | COSTLY | the edge on volatile days includes the release move; keep v4 and the 1.5 % tolerance |
| passes | CHEAP | the edge is in the trend after the release, which P2 keeps; P2 is a candidate |
| fails | COSTLY | release windows pay for a reason other than volatility; a new observation, not a pass |
| fails | CHEAP | P2 is a candidate |
| any | INCONCLUSIVE | v4 stays; the cost is not known to be small |

The exposed history (§3) is read after VC's window B, and neither family's numbers change the other's decision rule.

## 10. Limits (where this may be wrong)

- P1 covers NFP, CPI and FOMC only. The live calendar also restricts PCE and GDP-advance releases. A P1 that matched the
  live rule exactly would need those calendars too.
- 22 UNKNOWN-time rows remove the trades around them in 2004-2006 and 2012 (20 trades of 5,979). If those trades differ from
  the rest, the history comparison is biased by the omission (counted in the output).
- **The cost of P2 is modelled, not measured.** The flatten fills at the 5m close that ends at T - 10 minutes; the p90 leg
  of §2 is a conservative stand-in for the minutes before a release, and a real close there may still cost more (spreads
  widen). The cost of P2 is therefore likely understated; the two sensitivities of §2 show how much the pricing moves dR.
- **P1 differs from the live rule by one bar at T + 10.** The replay decides at the entry bar's open, the live executor a
  moment after it (scripts/fvg_demo.py:435): an entry opening exactly at T + 10 is dropped in the replay and allowed live
  (about one of the five grid slots inside a window). It affects P1 against P0 only, in the conservative direction.
- **Research-mode rows** in the exposed read (§3): a point-in-time replay has about 2.2 % more trades, about 11 % more in
  window B.
- **Calendar evidence.** An archive.org capture time is an upper bound on when a page was public; rows whose only evidence
  is a capture are treated as known later than they were, which only removes windows, never adds them. NFP 2025-10-03 has no
  withdrawal time (no explicit BLS statement before 08:30 ET on that day was found), so a release that never happened is
  still treated as expected on that day. Commit dates in git can be rewritten; the as-of calendar of §4 and the seal
  instant rest on the same assumption.
- **Reproducibility of the calendar build:** the builder, the fetch log and the fetched bodies are not in the repository (§1);
  the per-row sources, sha256 values and quotes are.
- Release times are scheduled times. A release that came out early (none documented here) would hit a position before the
  flatten.
- Other scheduled events with a gap risk are not in the calendar: FOMC minutes, ISM, retail sales, PPI, ECB and other central
  banks, Fed speakers. P2 does not make v4 flat across all of them.
- Unscheduled FOMC actions (8 rows, 4 with a known time) stay inside v4's baseline risk; no policy here touches them.
- The paired difference dR is the cost of P2 on trades that were open; it does not measure the tail benefit directly (a
  gap-through stop that P2 avoided shows up as a large positive dR on that trade, and the exposed read counts the
  gap-through stops per policy).
- **The forward verdict is weakly powered** (§6): whatever the margin, a small true cost reads INCONCLUSIVE, and one avoided
  gap among 50 trades moves the mean by +0.03 R.

## 11. Owner decisions (before the seal)

1. **Margin:** "0.20 R per flattened trade" (recommended: 67-81 % power if P2 is free, a gate to candidacy only; §4, §6) or
   "0.10 R" (a tight gate that a free P2 passes 34-42 % of the time; INCONCLUSIVE is then the likely verdict) or another
   value. The constant `MARGIN_R` is pinned by the code fingerprint.
2. **Due rule:** "50 flattened trades or 36 months" (recommended; at about 20-26 flattened trades a year the count binds at
   about 2-2.5 years) or longer.
3. **Event set:** "NFP, CPI, FOMC as drafted" (recommended: sourced now) or "add PCE and GDP-advance first" (needs a
   sourced BEA calendar; delays the seal).
4. **P2 as a risk rule regardless of the test:** "no, wait for the forward verdict" (recommended) or "adopt now as a
   preference" (recorded as POLICY-EXPOSED, not validated).
5. **Ordering with VC:** "NF's exposed read after VC's window-B read" (recommended; `AFTER_VC = True`) or "independent"
   (`AFTER_VC = False`, recorded in §3).
6. **One FOMC source:** CAL's FOMC file (docs/plans/2026-10-04-cal-us-index-calendar-preregistration-DRAFT.md §8) can be
   derived from this calendar by a pure transform at the seal (recommended: one source of truth) instead of a second
   hand-built file.

## 12. Sealing steps (coordinator), code and fingerprint

1. Review this draft, the calendar and the code (`scripts/research/news_flat.py`, `scripts/tests/test_news_flat.py`).
2. Commit `data/calendar/us-high-impact-releases.json` with the code. Optionally also archive the dry-run JSON and, if the
   builder can be recovered, the builder, so §6 and §1 are reproducible from the repository.
3. Outcome-blind dry run: **done 2026-10-05** (§6: counts and the sha256 values). Re-run
   `python3 scripts/research/news_flat.py dry-run --out <scratch json>` from the final code (refused at a read's output
   name): its `meta.counts_sha256` must equal the value in §6 and its `meta.dataset_line` the pinned line. No trade is
   simulated.
4. `python3 scripts/research/news_flat.py manifest` and paste its lines (the code-sha256 lines, the one
   `calendar-history-sha256 ... before 2026-10-05 data/calendar/us-high-impact-releases.json` line and the one
   `dataset-sha256 ... XAUUSD|5m before 2026-10-03T00:00:00Z` line) into the block below.
5. Commit this text under the sealed name with the exact "Status: SEALED" line and, in the same commit, the ledger entry of
   §7. A read refuses without it (`news_flat.require_ledger`).
6. Exposed read, after VC's xau-holdout read is committed (`require_vc_first` checks VC's output, tag and read name):
   `python3 scripts/research/news_flat.py run --read exposed --out docs/audits/<date>-edge-nf-exposed.json`, committed alone.
7. Forward read, when due: `python3 scripts/research/news_flat.py run --read forward --out
   docs/audits/<date>-edge-nf-forward.json`. Before it, append BLS's 2027 dates (and later years) to the calendar, each
   committed, with `coverage.through` extended in the same commit, before the days it covers: the read takes the calendar as
   committed at each decision.
8. Owner (MT5): nothing for the exposed read. The forward read needs the paper log kept running (fvg_forward.py
   `accumulate`, `scan`, `resolve`) and the 5m bars it merges.
9. After the seal this file's tests must stay green WITHOUT edits (the test file is pinned by the manifest): the tests do not
   depend on the seal state of this repository; the refusal before a sealed text is tested in a temporary git repository.

Code: `scripts/research/news_flat.py` (`load_calendar`, `Calendar.at`, `AsOf`, `calendar_versions`, `expected`,
`state_unknown`, `windows_at`, `merge`, `in_windows`, `unknown_reasons`, `server_day_end`, `classify`, `flatten_row`,
`flatten_paper_row`, `apply_policies`, `summary`, `daily_breach_days`, `paired_delta`, `forward_verdict`, `forward_due`,
`last_full_day`, `calendar_history_digest`, `require_calendar_history`, `require_ledger`, `require_vc_first`,
`require_no_pycache_prefix`, `capped`, `exposed_dataset_digest`, `dataset_line`, `require_dataset`, `series_cutter`,
`cut_bar`, `exact_cut`, `reprice_paper_row`, `planned_entries`, `dry_counts`, `exposed_result`, `forward_result`,
`forward_snapshot`, `cost_profile`, `_exposed`, `_forward`, CLI with the registration guard). Tests:
`scripts/tests/test_news_flat.py` (exact start and end boundaries, overlapping, adjacent and separate windows, statement and
press conference, DST under the 2006 and 2007 rules, wrong offsets refused, impact UNKNOWN restricts and LOW does not, UNKNOWN
time and availability, coverage gaps, a late row, postponed rows before and after withdrawal, unscheduled rows, a truncation
probe, UNKNOWN judged on the planned span, the cut bar with gaps and later bars, an exact cut bar or UNKNOWN, `exposed_result`
and `forward_result` end to end on synthetic bars through the real book_sim, pass_policy and cut code, `_exposed` and
`_forward` themselves on synthetic bars, re-pricing on one cost basis, the as-of calendar (a late row, a backdated edit, a day
not yet covered, the commit versions from git), the forward rule, the VC ordering with its tag check, the calendar pin, the
dataset pin, the capped loader, the pycache refusal, the repo calendar, a seal rehearsal in a temporary git repository (every
refusal in the CLI's order including the missing sealed text, one read, read-once, a code change after the seal), the module
list for both reads, and the dry run's entries equal to book_sim's).

Manifest (filled at sealing by `python3 scripts/research/news_flat.py manifest`; empty in this draft):

```
(paste here)
```
