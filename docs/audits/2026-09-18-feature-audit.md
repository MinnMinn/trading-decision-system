# Audit 11 yêu cầu chức năng ↔ working tree — 2026-09-18

Đối chiếu 11 yêu cầu người dùng nêu (tài khoản CFD cá nhân/thi quỹ, setup tối ưu, backtest PIT, ràng buộc custom,
xếp hạng system, phiên, tin ±10', học từ lệnh thua, tốc độ scalping, tách hai artifact, điểm kì vọng trên chart) với
mã nguồn tại thời điểm audit (HEAD `b894e7e` + working tree chưa commit, `pytest scripts/tests` → 1763 pass, 2 fail).

Phương pháp: 4 agent đọc-only, mỗi agent một nhóm yêu cầu, bắt buộc trích `path:line`; phiên chính mở lại từng
dòng được trích để xác nhận trước khi ghi. `docs/architecture/SPEC-COMPLIANCE.md` (ledger theo §CLAUDE.md) chỉ
dùng làm bản đồ, không dùng làm bằng chứng. Không sửa file nào ngoài `docs/audits/`.

Verdict: **PRESENT** = có và có test giữ; **PARTIAL** = một phần, cột "Còn thiếu" nói đúng phần nào;
**MISSING** = không có artifact thực thi.

---

## 1. Bảng tổng hợp

| # | Yêu cầu | Verdict | Đã có (dẫn chứng) | Còn thiếu (dẫn chứng) |
|---|---|---|---|---|
| 1 | CFD phân biệt cá nhân / thi quỹ; backtest theo điều kiện fail riêng; thi quỹ dùng FTMO hoặc The5ers | PARTIAL | 5 context type + 16 rule key (`docs/architecture/account-profiles.json:7-34`). Engine dừng run khi vi phạm rule prop, cá nhân chỉ thua khi cháy (`scripts/backtest-methods.py:648-751`; `scripts/tests/test_account_aware_backtest.py:67`). `prop_pass_probability`, `account_failure_probability` (`scripts/performance.py:449-456`) | Không có profile FTMO / The5ers / PERSONAL / PROP_*; chỉ 2 profile DEMO (`account-profiles.json:38,71`, lý do tại `:105`). `backtest-methods.py` `main()` không có cờ `--account`, gọi `simulate(tr, fee)` không account (`:836-837`); chỉ `scripts/stability-report.py:79-80` có. Xác suất fail chỉ mô hình `max_total_drawdown` + `trailing_drawdown`, bỏ `max_daily_loss`, `min_trading_days`, `consistency_rules` (`performance.py:218-228`) |
| 2 | Nhiều setup / phương pháp, tỉ lệ khác nhau; kết hợp điều kiện tài khoản để tìm setup tối ưu | PARTIAL | Setup = dòng `(market, tf, method, target, cfg)` trong `docs/architecture/pilot-top5.json`; xếp hạng per setup (`scripts/rank-setups.py:162-208`). 7 objective gồm `prop_pass_rate`, `survival` (`scripts/ranking.py:87`, `docs/architecture/ranking.json:9-30`) | `ranking.py` không có caller ngoài `scripts/tests/test_ranking.py`. Ranker không nhận account (`grep account rank-setups.py` chỉ prose). Data stability ship ra không có `account` → `prop_pass_probability` trả `unavailable` (`data/history/stability/crypto-live.json` rows[0].perf). `methods.json` không khai báo quan hệ methodology → setups |
| 3 | Backtest PIT nghiêm ngặt: vào lệnh chỉ dùng data đến thời điểm đó | PARTIAL | `scripts/pit.py:96,113,135`; mutation probe `scripts/leakage.py:40,72` chạy trên engine thật với 4 method (`scripts/tests/test_backtesting.py:162-172`, anti-vacuity `:158`); FVG `[i+1]` là causal (`backtest-methods.py:320-324`) | **Leak thật ở bộ lọc HTF**: `htf_position` key theo `c[i]["time"]` (giờ MỞ nến HTF) nhưng dùng `c[i]["close"]` (`backtest-methods.py:376-390`); `htf_allows` lấy `bisect_left(htf,(t,))-1` = nến HTF có giờ mở trước t, tức nến CHƯA ĐÓNG (`:392-404`, docstring nói ngược lại). Probe không bắt được vì `OPTS["htf"]` mặc định False (`:77`), nhưng `stability-report.py:39` config "C" chạy `htf=True`. `research_validity.checked("look_ahead", note)` nhận ghi chú tự do (`scripts/research_validity.py:169`) |
| 4 | Ràng buộc bổ sung theo kinh nghiệm từng trader, per phương pháp | MISSING | Chỉ có key `custom_constraints` trỏ tới file config chung (`scripts/trading_system.py:403-405`); test chỉ assert key tồn tại (`scripts/tests/test_trading_system.py:377`) | Không có trader identity (grep `trader_id|per_trader|custom_rules` = 0 ngoài prose). `trading-systems.json:200-208` mỗi system chỉ `{version, dependency_profile, account_profile}`. `policy.json` là policy phát triển (§56-62), không phải policy trader. Không được backtest lẫn live đọc |
| 5 | Artifact thống kê xếp hạng độ hiệu quả các system | MISSING | `ranking.exposure_report()` đủ 7 mục §48 (`scripts/ranking.py:178`) | Không có caller. `docs/architecture/ui-fields.json:41-44`: `"System Performance & Ranking"`, `served_by: []`, `"No page"`. 9 Trading System (`trading-systems.json:200-208`) chưa được so sánh với nhau; chỉ có markdown per-setup ở `docs/backtests/` thiếu validation state / assumptions / robustness |
| 6 | Thời gian trade trong các phiên (backtest) | PARTIAL | Registry phiên + DST đúng: `docs/architecture/sessions.json:9-44`; `scripts/sessions.py:34` (zoneinfo), `:85-91` từ chối alias cố định, `:127` union overlap; test DST `scripts/tests/test_event_risk.py:339` | Không có gate phiên ở cả hai đường: backtest `grep -i session backtest-methods.py` = 1 dòng docstring (`:27`); live `strategy-runner.py:1587` `tr.skip("session", …)`; `docs/architecture/decision-order.json` step 4 `live: null`, `backtest: null`. Gate duy nhất là `session_restrictions` trong `account_profile.entry_gate` (`scripts/account_profile.py:349-357`) và cả 2 profile để `null` (`account-profiles.json:64,98`) |
| 7 | Tránh ±10' quanh tin quan trọng | PARTIAL | Live đầy đủ: buffer 10/10 configurable (`docs/architecture/event-calendar.json` policy; `scripts/event_risk.py:209,224`), entry-only `:262`, union cửa sổ `:227-234`, PIT `visible()` `:180`, fail-closed `:66`; wired `scripts/strategy-runner.py:1492-1496,1582-1586,1641-1644`; 65 test | Backtest không đọc calendar (`backtest-methods.py:236-237`, snapshot `news_rules` `:298-299`; decision-order step 3/14 `backtest: null`). UNKNOWN chỉ block khi `mode == "STRICT"` (`event_risk.py:221`) mà không caller nào truyền mode. Calendar có 1 event mẫu (cancelled), không có snapshot lịch sử |
| 8 | Học từ lệnh thua cùng nguyên nhân → AI đề xuất → backtest → report vượt trội | PARTIAL | Trường `root_cause`/`is_mistake`/`lessons` (`docs/architecture/schemas/trade-file.schema.json:169-188`); `scripts/outcomes.py:327 cluster()`, `:414 Proposal.compare`; `scripts/experiment.py` Record/seal/decide; OOS bị chặn đúng thiết kế (`outcomes.py:403-408,446-451`) | `docs/experiments/` chưa tồn tại (`experiment.py:48`). `/improve` chỉ prose LLM (`.claude/skills/learning-skill/SKILL.md` không có bước backtest). Không có orchestrator cluster → candidate → `backtest-methods` → so baseline → report; gần nhất là grid cố định `scripts/ict-flags-1y.py`. **Sample = 0 lệnh đóng**: `trades/index.jsonl` 1 dòng, PLANNED, rehearsal; `outcomes.ingest()` = 165 NO_TRADE + 120 DATA_FAILURE + 1 EXECUTION_FAILURE |
| 9 | Đủ tốc độ phân tích + vào lệnh cho scalping | PARTIAL | 10 stamp (`docs/architecture/latency-model.json:12-70`); recorder `scripts/latency.py:175,197`; wired vào `strategy-runner.py` fetch/normalize/analytics/decision/risk/submit; số đo thật `data/live/latency/2026-09-18.jsonl` (1079 trace); LLM không trên đường đặt lệnh (`scripts/tests/test_latency.py:261-272`) | `order_submission` và `provider_acknowledgement` **chưa có quan sát nào** (`python3 scripts/latency.py` chỉ in 6/8 stage hot). `provider receive` p95 ≈ 9 s. Vòng live tick **900 s** (`scripts/pilot-loop.sh:52`, `strategy-runner.py --tick-seconds`); `scan-loop.sh` gate phút 01/16/31/46. Không có latency budget (`latency-model.json:6`), không trang nào hiển thị p50/p95 |
| 10 | Tách "Công tắc phương pháp" (chọn để trade) khỏi "Scalping" (phân tích mọi phương pháp có data) | PARTIAL | Prose/matrix đã tách: `analysed` gate theo provider liveness không theo preset (`scripts/build-artifact.py:1354-1360`; `scripts/methods.py:241-280`); capability registry + `dimensions.*.data_sources` (`docs/architecture/providers.json`; `methods.json`; validate `methods.py:92-108`); REQUIRED/OPTIONAL enforced (`scripts/trading_system.py:309`), runner không đọc dimension nào (`strategy-runner.py:1651`) | **Chart overlay vẫn khoá theo preset**: `build-artifact.py:1416 engaged=[…]` → `scripts/chart.js:485 drawnFor`. Overlay hard-code 2 lane (`build-artifact.py:151 OVERLAY_LANES`, `:1377`, `:945`, `:1397`). Pane footprint/heatmap `kind: "unavailable"` (`methods.json:93,126`), `chart.js:415-431` không có nhánh vẽ → Coinglass bật lên chỉ tự sáng phần prose. **OKX không tồn tại**: crypto là Binance REST (`providers.json:37`, `build-artifact.py:1513`); Bookmap chưa có provider. Song song chỉ per style (`scripts/model-read.sh:3`), không per phương pháp, không "xong cái nào hiện cái đó" |
| 11 | Điểm kì vọng trước / trong / sau vào lệnh theo từng phương pháp trên chart | PARTIAL | Model đầy đủ: 7 state, 3 phase `before_entry/entry_area/after_entry`, immutable `original`, per-methodology không merge (`scripts/expectation.py:50-254`; schema `trade-file.schema.json:498`); `expectation_kinds` per wyckoff/ict (`methods.json:32-37,66-72`); 38 test | **Không có producer**: ngoài test không file nào `create()` (chỉ comment `strategy-runner.py:1623-1626`, ghi 1 target scalar). **Không có renderer**: grep `expectation|expected_path` trong `chart.js`, `build-artifact.py`, `journal_render.py` = 0. `trading-systems.json:142` ghi "drawn by scripts/chart.js" — sai so với code. Footprint/heatmap không có `expectation_kinds` |

## 2. Phát hiện cần xử lý trước

1. **Leak HTF (mục 3)** là lỗi research-integrity thật; mọi run `stability-report` config C (htf=True) đến nay không tin được cho tới khi sửa và probe lại với `htf=True`.
2. **OKX** chưa có trong hệ thống. Yêu cầu "chart từ OKX" hiện tương đương "chart từ Binance"; thêm OKX là thêm provider + adapter mới, không phải bật cờ.
3. **Tách artifact không ảnh hưởng tốc độ đặt lệnh**: runner cơ học không đọc lane phân tích nào; điểm chậm là tick 900 s + fetch REST, không phải phân tích.
4. **Hai test fail có sẵn** (không do audit): `test_rank_setups_horizons.py` ô trống preset thêm `wyckoff/scalping`; `test_risk_model.py` 2 setup CFD giả định phí 0.0002 trong khi venue MT5 khai 0.0005.

## 3. Thứ tự đóng gap (dependency-aware)

1. Sửa leak HTF + probe với htf=True; `--account` cho backtest chính; profile FTMO / The5ers; mở rộng fail model (daily loss, min days, consistency).
2. Calendar + session gate vào backtest, và session gate live step 4.
3. Producer + renderer Expectation; gỡ khoá overlay theo preset; lane list theo registry.
4. Trang xếp hạng Trading System qua `ranking.py` có account.
5. Trader constraints registry; vòng lặp cluster → candidate → backtest → experiment record → report.

Kế hoạch triển khai: `docs/plans/2026-09-18-close-feature-gaps.md`.

## 4. Trạng thái đóng gap (cập nhật cuối ngày 2026-09-18, plan `docs/plans/2026-09-18-close-feature-gaps.md`)

| # | Đã làm | Còn mở |
|---|---|---|
| 1 | Profile FTMO / The5ers (research), `--account` trên backtest chính, fail model thêm daily loss + min days, cột `Fail theo luật`, nhãn `DỪNG (luật)` ≠ `CHÁY` | Số liệu prop firm lấy từ tóm tắt web search, cần xác minh trên trang vendor (`_source.verify`) |
| 2 | Trang xếp hạng (`system-ranking.py`) chạy `ranking.py` với 6 objective; `--account` có thể chạy per setup | Chưa sinh lại stability với account nên objective theo tài khoản còn `unavailable`; `methods.json` vẫn chưa khai báo methodology → setups |
| 3 | Leak HTF đã sửa, probe chạy với `htf=True` | Kết quả stability config C trước 18/09 không so sánh được với sau |
| 4 | `trader-constraints.json` + overlay chỉ-siết ở backtest (`--trader`) và live (`execution.trader`) | Kind `types` chưa áp dụng live (detector Wyckoff không nhận tham số) |
| 5 | Trang System Ranking, `ui-fields.json` đã có `served_by`; đã publish: https://claude.ai/code/artifact/e13dc189-7d35-4cec-83c7-3b6221e34beb | Objective theo tài khoản còn `unavailable` cho tới khi stability chạy xong với account (đang chạy) |
| 6 | `--sessions` + `session_restrictions` ở backtest; step 4 live phát ok/block từ account | Profile pilot chưa khai báo phiên nào |
| 7 | `--calendar` ở backtest, PIT theo `entry_time` | §29: chưa có kho snapshot lịch sử; calendar có 1 event mẫu |
| 8 | `improve-loop.py` + `docs/experiments/` + `/improve` gọi script | Chưa có OOS; 0 lệnh thật đã đóng |
| 9 | Không đổi | Stamp `order_submission`/`provider_ack` chỉ ghi khi có lệnh — drill sẽ tạo mẫu đầu tiên |
| 10 | Overlay chart theo `analysed`, lane theo registry, nhãn "không tính vào Confluence" | Chưa có pane footprint/heatmap; không có OKX/Bookmap; chưa song song per phương pháp |
| 11 | Producer + renderer expectation, lưu vào trade/index | Chỉ xuất hiện khi có plan PLANNED/OPEN |
| E2E | Drill thật đã chạy cả hai venue (`docs/audits/2026-09-18-e2e-drill.md`): 17/17 bước, lệnh khớp, SL khớp tại venue, trang vẽ plan + kì vọng, flatten sạch | 2 lỗi thật phát hiện và đã sửa (giá khớp, pnl MT5) + jitter giờ nến MT5 đã chuẩn hoá |
