# Chọn khung thời gian: bối cảnh → cấu trúc → vào lệnh

Last updated: 2026-09-13 (§5 rewritten for the three-horizon ladder; §4 frozen as the 2026-09-12 audit record).
Câu hỏi gốc của người dùng: *"cửa sổ chính M15 nhưng bối cảnh H4 có hợp lý không?"* — và yêu cầu
rà soát mọi lựa chọn khung thời gian trong repo hiện chỉ là phỏng đoán, đối chiếu nguồn, thay nếu cần.

Tài liệu này là **nguồn duy nhất** cho quy tắc ghép khung. `scripts/automation.py` `CONTEXT_STYLE` và
`scripts/strategy-runner.py` `HTF_OF` phải trỏ về đây; không chép lại bảng ở nơi khác.

## 1. Trả lời ngắn

**M15 (cửa sổ làm việc) ↔ H4 (bối cảnh) là cặp chuẩn của chính TTrades, không sai.** Bảng ghép khung in trong hai deck
(`Timeframe Alignement TTrades.pdf` p5 và `Model11` p44/p95 — `knowledge/ict/models.md` §2.3, §2.8): **W→H4, D→H1, H4→M15, H1→M5,
M30→M3, M15→M1.** Trong đó khung trái là nơi đọc *cấu trúc* (swing point / key level), khung phải là nơi xác nhận
CISD và vào lệnh.

Điều người dùng cảm thấy "không hợp lý" là có thật, nhưng nằm ở chỗ khác: **hệ thống hiện gộp hai tầng thành một.** Mọi
nguồn ba tầng (Elder, ICT top-down, chính trang TTrades) đều đặt **một tầng trung gian** giữa M15 và H4:

| Nguồn | Bias / Tide | Structure / Wave | Entry |
|---|---|---|---|
| Elder Triple Screen, ví dụ intraday (mql5 blog, forexop) | H4 | H1 | M15 |
| ICT top-down (innercircletrader.net) | D → H4 | H1 | M15 |
| TTrades TFA (ttrades.com): "5M entry ↔ 1H structure ↔ daily bias" | D | H1 | M5 |
| Wyckoff Advance (WA p93–96, `knowledge/wyckoff/advance.md` §2.7) | — | M30 (Shakeout[C]) | M5 (Spring[C]/LPS[C]) |

Kết luận: **M15/H4 đúng nếu hiểu H4 là *cấu trúc* và M15 là *vào lệnh* (cặp TTrades, 2 tầng). Nếu muốn nhìn chart
đúng theo mô hình 3 tầng thì thiếu H1 ở giữa, và H4 là tầng bias chứ không phải tầng ngay trên M15.** Người dùng không
sai về cảm giác, chỉ sai về nguyên nhân: vấn đề không phải "H4 quá xa M15", mà là (tại 2026-09-12) repo đang có hai
bảng ghép khung mâu thuẫn nhau (mục 4, dòng A). **Đã xử lý 2026-09-13** — một hàm sinh ra cả hai; thang đang chạy ở
mục 5, và M15 → H1 (cấu trúc) → H4 (bias) đúng là thang ba tầng mà mục này nói còn thiếu.

## 2. Nguồn đã đối chiếu

| # | Nguồn | Loại | Nội dung dùng | Đường dẫn / trích |
|---|---|---|---|---|
| S1 | TTrades *Timeframe Alignment* deck + *Model11* | sơ cấp (deck đã ingest) | Bảng ghép W→H4, D→H1, H4→M15, H1→M5, M30→M3, M15→M1; "Structure (CISD) / Entry (OB)" | `knowledge/ict/models.md` §2.3, §2.8 (`TFA p5`, `Model11 p44, p95`) |
| S2 | TTrades *Daily Bias* / *Intraday Bias* decks | sơ cấp | Daily bias đọc trên nến D, thực thi trên chart H4; intraday bias đơn vị H4/H1/M30/M15 | `knowledge/ict/core-a.md` §2.11–2.12, R9, bảng "Bias timeframes" |
| S3 | TTrades *TTRS* deck | sơ cấp | Khung vào lệnh theo tính cách: M15 (kiên nhẫn) / M1 (nóng vội) | `knowledge/ict/models.md` §2.9 (`TTRS p4`) |
| S4 | ttrades.com "Time Frame Alignment" | sơ cấp (web, tác giả deck) | Ba tầng: "Higher Time Frame (Bias) / Intermediate Time Frame (Structure) / Entry Time Frame (Entry)"; ví dụ "5M entry, 1H structure, daily bias" | https://ttrades.com/timeframe-alignment-how-to-align-higher-and-lower-time-frames-for-precision-entries/ |
| S5 | Wyckoff Advance (WA) p93–100 | sơ cấp (sách đã ingest) | "Giảm khung": Shakeout[C] M30 → Spring[C]/LPS[C] m5; "Tăng khung": M30 → H1 để giữ lệnh lâu hơn | `knowledge/wyckoff/advance.md` §2.7 |
| S6 | Wyckoff & Modern Tools (WMT) p233–236 | sơ cấp | Bước 1: xu hướng lớn trên khung cao hơn, rồi tìm TR cục bộ trên khung giao dịch | `knowledge/wyckoff/modern-tools.md` §5 Step 1 |
| S7 | Elder, *Trading for a Living* — Triple Screen | thứ cấp (bản tóm tắt web; sách chưa ingest) | "Factor of five": khung dài = 5× khung trung gian, khung ngắn = khung trung gian / 5; ví dụ W/D/H1 (swing), H1/M10/M2 (day). Bản forexop: "reduces by a factor of 3, 4 or 5"; ví dụ W/D/H4, D/H4/H1, H4/H1/M15 | https://forexop.com/strategy/simple-triple-screen/ ; https://www.mql5.com/en/blogs/post/731016 ; https://medium.com/@86adrian.popa/swing-trading-with-elders-triple-screen-a-simple-guide-e6a1236547d7 |
| S8 | ICT top-down | thứ cấp (trang tổng hợp) | D = bias, H4 = hướng trung hạn, H1 = hướng ngắn hạn, M15 = vào lệnh; "always start from the highest timeframe" | https://innercircletrader.net/tutorials/ict-top-down-analysis/ |
| S9 | DailyFX/IG "Multiple Time Frame Analysis" | thứ cấp | "Rule of four": khung ngắn ≥ ¼ khung trung gian, khung dài ≥ 4× khung trung gian; "ratio of 4, 5, or 6" | https://www.dailyfx.com/education/time-frame-analysis/multiple-time-frame-analysis.html |

Chưa lấy được nguyên văn: Elder sách gốc và Investopedia (fetch bị chặn trong phiên này). S7/S9 vì thế là nguồn thứ
cấp; ba bản tóm tắt độc lập trùng nhau về hệ số 4–6 nên đủ để dùng làm quy tắc, nhưng ghi rõ là thứ cấp.

## 3. Công thức

Gọi `E` là khung vào lệnh (phút). Ba tầng, hệ số liền kề `r ∈ [4, 6]` (S7, S9):

```
Structure  S = r · E          (4E … 6E, làm tròn về khung chuẩn gần nhất)
Bias       B = r · S          (16E … 36E)
```

Cặp TTrades (S1) là **bỏ đúng một tầng**: `HTF_cặp = B`, nghĩa là 12–42× khung vào lệnh (D→H1 = 24×, H4→M15 = 16×,
H1→M5 = 12×, W→H4 = 42×). Vì vậy cặp TTrades và thang ba tầng không mâu thuẫn — cặp TTrades là thang ba tầng đã lược
tầng giữa.

Thang chuẩn suy ra (khung chuẩn có trên Binance và MT5):

| Entry `E` | Structure `S` (4–6E) | Bias `B` (4–6S) | Cặp TTrades tương ứng | Ghi chú |
|---|---|---|---|---|
| M1 | M5 | M15–M30 | M15→M1 | scalping (S3: "impatient") |
| M5 | M30 | H1–H4 | H1→M5 | WA p93–96 dùng M30→m5 (S5) |
| M15 | H1 | H4 | H4→M15 | ví dụ intraday của Elder, ICT (S7, S8) |
| M30 | H2–H4 | D | — (TTrades: M30→M3 khi M30 là structure) | ICT 30m là luật tốt nhất trong backtest của repo |
| H1 | H4 | D | D→H1 | |
| H4 | D | W | W→H4 | Elder long-range W/D/H4 (S7) |
| D | W | M | — | swing/position |

Quy tắc đọc chart đi kèm (S4, S6, S8, S5): đọc từ `B` xuống, không bao giờ từ `E` lên; `S` chỉ để xác nhận `E` cùng
hướng với `B` và tìm vùng; `E` chỉ để canh điểm vào, **không tạo bias ở `E`**.

## 4. Rà soát: cái gì trong repo là phỏng đoán

> **Bản ghi của ngày 2026-09-12 — giữ nguyên câu chữ, không cập nhật theo code.** Cột "Hiện trạng" mô tả repo
> *tại ngày đó*. Ngày **2026-09-13** hệ thống gom về một engine (`scripts/strategy-runner.py`) và ba horizon
> (`scalping` 15m / `day` 1h / `swing` 4h, `automation.HORIZON_TF`); mọi tên style cũ (`daytrade`, `gold`,
> `gold-scalp`, `gold-1h`, `gold-4h`, `gold-swing`) và **engine pilot cũ** (script thứ hai, đã xoá) **không còn tồn tại**. Bảng ba tầng
> đang chạy là §5, không phải bảng này. Các ô bị ảnh hưởng có ghi chú ngày ngay trong ô.

| # | Mục | Hiện trạng | Nguồn nói gì | Kết luận | Hành động |
|---|---|---|---|---|---|
| A | **Hai bảng ghép khung khác nhau** *(bản ghi 2026-09-12; đã xử lý — xem cuối ô)* | Hai bảng gõ tay, không trùng nhau. `CONTEXT_STYLE` (tại 2026-09-12): 1m→15m, 15m→**4h**, 1h→1D, 4h→1D, gold 5m→**15m**, 15m→4h. `HTF_OF` (tại 2026-09-12): 5m→30m, 15m→**1H**, 30m→2H, 1H→4H, 2H→1D, 4H→1D | S1 ghép 15m với H4 (cặp, bỏ tầng); S7/S8/S9 đặt H1 ngay trên M15 (liền kề). Cả hai đều có nguồn, nhưng là **hai tầng khác nhau**: `HTF_OF` là tầng Structure, `CONTEXT_STYLE` là tầng Bias | Không phải sai, mà là **không đặt tên tầng**. SYSTEM-DESIGN §15.2 nói "one mapping, never restate it elsewhere" — đã bị vi phạm | **Đã xử lý, không còn hai bảng.** Cả hai giờ là dẫn xuất của cùng một hàm `next_rung`: `CONTEXT_STYLE` = `gate_style` trên `TIERS` (`automation.py:207` (`CONTEXT_STYLE = {st: gate_style(st)[0]`)) và `HTF_OF` = `next_rung` trên rung của runner (`strategy-runner.py:157` (`HTF_OF = {tf: _auto.next_rung(`)). Tên tầng đã đặt: `HTF_OF` = structure (S), `CONTEXT_STYLE` = tầng gate (bias nếu rung đó có style được quét, nếu không thì structure). Engine pilot cũ nhắc trong ô này đã bị xoá 2026-09-13; các tên style cũ được liệt kê một lần duy nhất ở `scripts/tests/test_one_system.py`. |
| B | gold-scalp **5m → 15m** làm bối cảnh (`CONTEXT_STYLE`, §15.1) *(bản ghi 2026-09-12)* | tỉ lệ 3× | S9: ≥4×; S7: ×5; S1: H1→M5; S5: M30→m5 | **Phỏng đoán, trái mọi nguồn.** Crypto 1m→15m (15×) thì đúng S1, nhưng gold 5m→15m thì không | **Hết hiệu lực 2026-09-13:** `5m` rời tập khung được quét, style `gold-scalp` không còn tồn tại; CFD scalping là `cfd-scalping` 15m → 1h → 4h (§5), mọi bước đều ≥ ×4. |
| C | **4h → 1D** làm bối cảnh (cả hai bảng) | 6× | S1: W→H4 (cặp bỏ tầng); S7 long-range: W/D/H4 → D là structure, W là bias của H4 | Đúng ở tầng Structure, **sai tên** ở tầng Bias (bias của H4 là W, và repo đã fetch 1W cho swing) | Nếu giữ tên "bối cảnh = bias" thì 4h→1W; nếu gọi là structure thì giữ 1D. Theo dòng A. |
| D | §15.1: "**M30 adds nothing between M15 and H1**" | M30 bị loại khỏi thang CFD; crypto cũng không có style 30m | S1: M30→M3 là một cặp chuẩn; S2: M30 là đơn vị intraday bias; S5: mọi ví dụ giảm/tăng khung của WA đều lấy M30 làm trục; backtest của chính repo (`docs/backtests/2026-09-11-stability-by-timeframe.md` dòng 9): ICT 30m +10.2%/năm, 5/5 năm dương, tốt nhất bảng; mọi dòng 15m ≤ +0.2% | **Phỏng đoán, bị chính dữ liệu repo bác bỏ** | Bỏ câu này khỏi §15.1. **Kết cục 2026-09-13:** người dùng chọn một khung duy nhất cho mỗi horizon — `day` là **1h**, không phải 30m; `rank-setups.HORIZONS` giờ đơn trị và khớp `automation.HORIZON_TF` (`rank-setups.py:74` (`HORIZONS = {"scalping": "15m"`)), nên pilot và chart không còn lệch nhau. Style 30m không được thêm. |
| E | §15.1: "**M1 is rejected for gold: the spread swallows a 1-minute bar**" | không có dữ liệu 1m XAUUSD trong repo để kiểm | Không nguồn nào trong repo bàn spread/khung; S3 cho phép M1 entry (impatient) | **Chưa kiểm chứng.** Có thể đúng nhưng chưa đo | Giữ như quyết định người dùng, nhưng ghi "chưa đo". Cách đo: export 1m XAUUSD 1 tuần, so `median(high-low)` với spread của tài khoản demo. |
| F | Cửa sổ nến 288 / 240 / 180 / 120 / 104 (`scan-loop.sh`) | 288×5m = 24h; 288×15m = 3 ngày; 240×1H = 10 ngày; 180×4H = 30 ngày; 120×1D = 4 tháng; 104×1W = 2 năm | Không nguồn nào cho số nến. S2 chỉ cần PDH/PDL, PWH/PWL, PMH/PML → cửa sổ tối thiểu phải chứa **ngày/tuần/tháng trước** | Tham số dự án, **không phải luật**; đủ điều kiện S2 (15m×288 = 3 ngày chứa PDH/PDL; 4H×180 chứa PWH/PWL và PMH/PML) | Ghi nhãn "project parameter" như `analysis-params.json` `project_defined`. Không cần đổi. |
| G | `min_timeframe_minutes = 15` cho điểm killzone (`analysis-params.json`) | "1m chart carries no timing information" | `knowledge/ict/core-b.md` §6 item 10: deck Silver Bullet vẽ **chart NASDAQ 1 phút** trong cửa sổ 1 giờ; S3 chấp nhận M1 entry | **Phỏng đoán, ngược deck.** Killzone là cửa sổ giờ, áp lên nến 1m vẫn có nghĩa | Đã được ghi là project-defined nên không sai quy trình; nhưng cơ sở ("no timing information") nên đổi thành lý do thật (nếu có: nhiễu/phí) hoặc hạ xuống 5m. Qua `/improve`. |
| H | `HTF_FILTER` của engine pilot cũ: mọi setup 15m dùng bias Wyckoff của **4H** (`load_context("daytrade")`) *(bản ghi 2026-09-12)* | 15m→4H | S1 H4→M15; S5 WA p95–96 | Có nguồn (cặp TTrades / giảm khung WA). Engine cũ chỉ chạy 15m nên cố định "daytrade" là ổn; `strategy-runner` chạy 5m…1D và dùng `HTF_OF` ⅓-biên | **Hết hiệu lực 2026-09-13:** engine cũ đã bị xoá và style `daytrade` không còn tồn tại. Còn một engine, `scripts/strategy-runner.py`, lọc bằng `HTF_OF` (tầng Structure) trên rung của chính nó. |
| I | `BOUNDARY_FRACTION = ⅓` (htf_context.py, backtest-methods.py) | "ở biên" = ⅓ ngoài của TR khung cao | WA p150/p166 dùng ⅓ cho phép thử ST, không cho vùng vào lệnh — file đã tự ghi "project adaptation" | Đã gắn nhãn đúng | Không đổi. |
| J | Horizon của pilot: scalping {5m,15m}, day {30m,1H,2H}, swing {4H,1D} *(bản ghi 2026-09-12, nhiều khung mỗi horizon)* | nhãn | S7: day-trader trung gian M10 (H1 dài / M2 ngắn), swing trung gian D (W/H1); S3: M15 vs M1 theo tính cách | Nhãn dự án, không có nguồn quy định ranh giới; không mâu thuẫn nguồn nào | **Đổi 2026-09-13:** mỗi horizon còn **một** khung — scalping 15m, day 1H, swing 4H (`rank-setups.py:74` (`HORIZONS = {"scalping": "15m"`)), khớp `automation.HORIZON_TF` (khác nhau chỉ ở cách viết hoa `1h`/`1H`). Vẫn là nhãn dự án. |

Chú ý dòng D và G: đây là hai chỗ mà câu chữ trong SYSTEM-DESIGN/analysis-params **phủ định dữ liệu hoặc deck của
chính repo**, nên là ưu tiên sửa trước dòng B.

## 5. Bảng ba tầng đang chạy (cập nhật 2026-09-13, code sinh ra — `scripts/automation.py` TIERS)

Quy tắc trong code: tầng liền kề = **rung có sẵn gần nhất chậm hơn ≥ ×4** (`next_rung`, `MIN_TIER_RATIO = 4`). Cùng một hàm
sinh ra bảng cho trang (rung = khung được quét + 1D/1W) và cho pilot/backtest (rung của runner: 5m…1D) — hàm này tái tạo
đúng `HTF_OF` cũ (5m→30m, 15m→1H, 30m→2H, 1H→4H, 2H→1D, 4H→1D), kiểm bằng `scripts/tests/test_timeframe_ladder.py`.

**Ba horizon, một khung vào lệnh mỗi horizon** (quyết định người dùng 2026-09-13, `automation.HORIZON_TF` ở
`automation.py:142` (`HORIZON_TF = {"scalping": "15m"`)): `scalping` 15m · `day` 1h · `swing` 4h. Tên style phẳng
(crypto giữ nguyên chữ horizon, cfd thêm tiền tố `cfd-`) được **suy ra** từ bảng đó ở `automation.py:149`
(`STYLE = {(m, HORIZON_TF[h])`) — đừng chép lại danh sách sáu tên ở đâu nữa, đọc `automation.HORIZON_TF`.

Bảng dưới đây được **in ra từ code**, không gõ tay:

```bash
python3 -c "import importlib.util as u; s=u.spec_from_file_location('a','scripts/automation.py'); a=u.module_from_spec(s); s.loader.exec_module(a); [print(st, a.STYLE_MARKET_TF[st][1], t) for st,t in a.TIERS.items()]"
```

| Style (Vào lệnh E) | Cấu trúc S | Bias B | Tầng quyết định verdict (`gate_style`) | Nguồn |
|---|---|---|---|---|
| `scalping` 15m | 1h (`day`) ×4 | 4h (`swing`) ×4 | Bias (`swing`) | Elder intraday, ICT top-down, TTrades H4→M15 (S1, S7, S8) |
| `day` 1h | 4h (`swing`) ×4 | 1D ×6 — **chỉ chart, không quét** | Cấu trúc (`swing`) | TTrades D→H1; Elder mid-range D/H4/H1 |
| `swing` 4h | 1D ×6 — **chỉ chart, không quét** | 1W ×7 — **chỉ chart, không quét** | — (không rung nào ở trên có style được quét) | TTrades W→H4; Elder long-range W/D/H4 |
| `cfd-scalping` 15m | 1h (`cfd-day`) ×4 | 4h (`cfd-swing`) ×4 | Bias (`cfd-swing`) | như `scalping` |
| `cfd-day` 1h | 4h (`cfd-swing`) ×4 | 1D ×6 — **chỉ chart, không quét** | Cấu trúc (`cfd-swing`) | như `day` |
| `cfd-swing` 4h | 1D ×6 — **chỉ chart, không quét** | 1W ×7 — **chỉ chart, không quét** | — | như `swing` |

**`1D` và `1W` là rung bối cảnh: được lấy về nhưng không bao giờ được quét.** Tập khung được quét là
`["15m", "1h", "4h"]` cho **mọi** market (một danh sách được viết ra, map qua `MARKETS`) (`automation.py:115` (`MARKET_TIMEFRAMES = {m: list(_SCANNED_TF)`)); `1m`, `5m` và
`1D` đã rời tập đó ngày 2026-09-13. Hai rung `1D`/`1W` vẫn nằm trong `PAGE_RUNGS` (`automation.py:188`
(`PAGE_RUNGS = {m: _SCANNED_TF`)) và được `scan-loop.sh:110` (`1D + 1W = CONTEXT charts only`) fetch ở lần quét 4h — đó
chính là điều giữ cho `swing` (4h) còn đủ một thang cấu trúc + bias. `automation.py timeframe 1D on` giờ là lỗi
cú pháp, nên nếu lần fetch bối cảnh đó mất thì không gì làm tươi lại được hai chart ấy.

Trang: mỗi mã có khối **Thang khung** ba dòng (Bias → Cấu trúc → Vào lệnh), mỗi dòng một ô Wyckoff (cấu trúc · pha · TR),
một ô ICT (vị trí dealing range · MSS gần nhất), một ô kết luận; tầng quyết định được tô. Dưới đó là ba chart cùng thứ tự,
vùng tô trên hai chart trên = cửa sổ vào lệnh. Rung thiếu được in "—" / "chỉ chart", không bị bỏ qua. Brief của lớp 2
(`local-eval-brief.py`) in mục THANG KHUNG với cả hai tầng; `m-synth` mở đầu bằng "<Tầng> <khung>: …".
