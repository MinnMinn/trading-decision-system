# Sàn R:R kế hoạch + trần rủi ro mỗi lệnh — 2026-09-13

_Bằng chứng cho quyết định của người dùng ngày 2026-09-13: mọi lệnh phải có R:R kế hoạch ≥ 3, và trần rủi ro mỗi
lệnh nâng từ 1 % lên 3 %. Hai thay đổi này là **một** quyết định — không cái nào an toàn nếu thiếu cái kia._

Nguồn số: `scripts/backtest-methods.py` (`simulate`, phí 0,05 %/chiều = `fee_R = 2 × 0,0005 / khoảng_stop`), luật
ICT đọc từ live (`scripts/live_rules.py`), 9 công cụ crypto, khung 15m, cửa sổ 2025-09-09 → 2026-09-09, 215 setup
thô, tài khoản $10.000.

## 1. Vấn đề được phát hiện

`docs/architecture/analysis-params.json` đã có `ict.min_rr = 2.0` với nguồn (knowledge/06 §3.1 luật 23, Model11
p92: *"2R is the minimum requirement before taking profit"*). Nhưng giá trị đó **chỉ được đọc để in một dòng chữ
cảnh báo** (`scripts/ict-scan.py:359`). Mọi đường ra quyết định đều chạy `min_rr=0.0`:

| nơi | trước 2026-09-13 |
|---|---|
| `backtest-methods.py:60` `OPTS` | `min_rr=0.0` |
| `backtest-methods.py` cờ `--min-rr` | `default=0.0` |
| `stability-report.py:39` | `min_rr=0.0` (nơi sinh bảng xếp hạng cho pilot) |
| `strategy-runner.py` đường đặt lệnh | không có cổng nào trên `r_planned` |

Hệ quả trên 215 setup của một năm:

| R:R kế hoạch | số lệnh | tỉ lệ |
|---|---|---|
| < 2 | 82 | **38 %** |
| 2–3 | 37 | 17 % |
| 3–4 | 33 | 15 % |
| ≥ 4 | 63 | 29 % |

`R_planned` thấp nhất = **0,00**. Hệ thống vào những lệnh mà TP gần như trùng giá vào.

## 2. Sàn R:R — đo trên 1 năm

| lọc | rủi ro | lệnh | thắng | vốn cuối | lợi nhuận | sụt giảm |
|---|---|---|---|---|---|---|
| không lọc | 1 % | 215 | 46,5 % | $14.276 | +42,8 % | 16,5 % |
| không lọc | 3 % | 215 | 46,5 % | $24.897 | +149,0 % | 43,6 % |
| không lọc | 5 % | 215 | 46,5 % | $35.760 | +257,6 % | 63,3 % |
| **R:R ≥ 2** | 1 % | 133 | 42,1 % | $15.213 | +52,1 % | 14,7 % |
| **R:R ≥ 2** | 3 % | 133 | 42,1 % | $30.751 | **+207,5 %** | 39,4 % |
| **R:R ≥ 2** | 5 % | 133 | 42,1 % | $52.619 | +426,2 % | 58,3 % |
| **R:R ≥ 3** | 1 % | 96 | 41,7 % | $14.643 | +46,4 % | 10,3 % |
| **R:R ≥ 3** | **3 %** | **96** | **41,7 %** | **$28.009** | **+180,1 %** | **29,1 %** |
| **R:R ≥ 3** | 5 % | 96 | 41,7 % | $46.604 | +366,0 % | 45,3 % |
| R:R ≥ 4 | 1 % | 63 | — | — | — | — |

Lọc nào cũng hơn không lọc. Theo quý (1 % rủi ro): R:R ≥ 2 cho **4/5 quý dương**, R:R ≥ 3 cho **3/5**
(Q3/2025 −0,1 %), R:R ≥ 4 thoái hoá ở mọi chỉ tiêu.

## 3. Vì sao **5 % bị loại**, không phải chỉ bị chê

`strategy-runner.py:963` halt **vĩnh viễn** (ghi file STOP) khi equity ≤ `EQUITY_HALT_FRAC` = 85 % vốn đầu kỳ.
`simulate()` không mô phỏng cái halt đó. Chiếu luật −15 % lên chính đường vốn backtest:

| lọc | rủi ro | chạm halt −15 %? | rủi ro đồng thời tối đa | vốn cuối nếu **không** halt |
|---|---|---|---|---|
| R:R ≥ 2 | 1 % | không | 4,0 % | $15.215 |
| R:R ≥ 2 | 3 % | không | 12,0 % | $30.811 |
| R:R ≥ 2 | 5 % | **2025-10-12** | 20,0 % | ~~$52.926~~ |
| R:R ≥ 3 | 1 % | không | 2,0 % | $14.637 |
| R:R ≥ 3 | **3 %** | **không** | **6,1 %** | $27.920 |
| R:R ≥ 3 | 5 % | **2025-10-12** | 10,3 % | ~~$46.226~~ |

Ở 5 %, tài khoản dừng hẳn sau **một tháng**. Các con số +426 %/+366 % là không thể đạt trong hệ thống này. Muốn
dùng 5 % thì phải quyết định lại `EQUITY_HALT_FRAC` — **đó là một quyết định riêng và chưa được đưa ra.**

Chọn **3R thay vì 2R** ở mức 3 %: đổi 27 điểm % lợi nhuận (+180 vs +208) lấy 10 điểm % sụt giảm (29,1 vs 39,4) và
một nửa rủi ro đồng thời (6,1 vs 12,0). Đúng thứ tự ưu tiên "bảo toàn vốn trước" của hệ thống.

## 4. Đã thay đổi những gì

| file | thay đổi |
|---|---|
| `docs/architecture/analysis-params.json` | `ict.min_rr.value` 2.0 → **3.0**; `_basis` ghi rõ đây là override **chặt hơn** nguồn, kèm số đo |
| `scripts/backtest-methods.py` | thêm `MIN_RR` đọc từ file trên; `OPTS["min_rr"]` mặc định = `MIN_RR` (không còn 0.0); `--min-rr` mặc định = `MIN_RR`; `RISK` 0.01 → **0.03** |
| `scripts/strategy-runner.py` | `RISK_CEILING = 0.03` (clamp giữ nguyên, chỉ nâng trần); `MIN_RR = bt.MIN_RR`; hàm mới `rr_reason(sig)` nối vào khối `reasons[]` duy nhất mà mọi phương pháp đi qua |
| `scripts/stability-report.py` | bỏ `min_rr=0.0` — kế thừa mặc định của `bt.OPTS` |
| `scripts/tests/test_min_rr_and_risk.py` | mới, 13 test |
| `scripts/tests/test_strategy_runner.py` | fixture `ONE_SIG` đổi `r_planned` 2.0 → 3.0 (test về cổng HTF, phải qua được cổng R:R mới tới được bước đặt lệnh) |

**Không đụng tới:** `EQUITY_HALT_FRAC` (0.85), `CONSEC_LOSS_HALT` (5), `MAX_OPEN`, `MAX_TRADES_PER_DAY`, danh sách
công cụ, khoá pilot. `rr_reason()` **fail closed**: `r_planned` thiếu / không phải số / NaN đều bị từ chối — `nan
< 3.0` là `False` nên so sánh trần trụi sẽ *mở* cổng, đúng chiều không được phép xảy ra.

### 4b. Hai chỗ phát hiện thêm trong lúc thi hành

**Trần rủi ro nằm ở HAI nơi.** `trading_env.py` cắt giá trị đọc từ file *trước khi* `strategy-runner` nhìn thấy.
Lượt sửa đầu chỉ nâng bản sao trong runner, nên `config/env` ghi `0.03` vẫn bị cắt về 1 % trong khi runner báo trần
3 % mà không bao giờ chạm tới. Nay `trading_env.MAX_RISK_PCT` là **định nghĩa duy nhất** và
`strategy-runner.RISK_CEILING` đọc từ đó — hai lớp clamp (tốt), một con số (bắt buộc).

**`ict-flags-1y.py` cũng là đường ra quyết định.** `--apply` ghi thẳng `ict_disp`/`ict_pd`/`std_origin` vào
`pilot-top5.json`, và `rank-setups.py` giữ lại các khoá đó khi ghi lại. Nó vẫn ghim `min_rr=0.0`, tức là chọn biến
thể ICT bằng cách đo trên tập lệnh mà cổng live sẽ từ chối. Đã bỏ ghim, cùng với `strategy-runner.replay()`.

## 5. Sàn "không chọn luật thua" trong `rank-setups.py`

Quyết định người dùng 2026-09-13, **thay thế** quy tắc 2026-09-11 ("chạy đủ 3 khung cho mỗi luật, kể cả khi lợi thế
backtest yếu hoặc âm"): một ô `(khung, luật)` chỉ được lấp bởi ứng viên có **≥ 3 tháng dữ liệu, không cháy, và có
lãi**; không ai qua thì **bỏ trống ô**.

Nguyên nhân: lần xếp hạng đầu tiên dưới sàn 3R đã chọn `cfd-day-wyckoff-1h-border-a`, một luật kết thúc cửa sổ xếp
hạng ở **$988 trên vốn $10.000** (cháy 2026-01-29, sụt giảm 92,3 %). Nó được chọn vì là *đỡ tệ nhất* trong ba ứng
viên đều cháy — chế độ `--horizons` lấp mọi ô, không có sàn nào bên dưới. Lỗi này **có sẵn từ trước**: trong dữ liệu
cũ dòng tương ứng không chạm ngưỡng cháy nhưng vẫn lỗ 82 % ($10.000 → $1.832) và vẫn được chọn. Nâng rủi ro lên 3 %
chỉ làm nó lộ ra.

Cài đặt: `rank-setups.solvent(r, window)` + `MIN_WINDOW_DAYS = 90`, lọc trong `rank()` nên **cả** chế độ top-N lẫn
`--horizons` cùng tuân theo. Đo lãi bằng `ann > 0` (đơn điệu với `final > START`, và tránh cho module này phải phụ
thuộc vào `backtest-methods` chỉ để biết vốn khởi điểm).

Kết quả: `pilot-top5.json` **19 → 6 setup**, không setup nào lỗ. Bốn ô `(preset, khung)` bỏ trống —
`(wyckoff, day)`, `(ict, day)`, `(ict, swing)`, `(wyckoff+footprint, day)` — được ghim trong
`test_rank_setups_horizons.py` để không âm thầm lan rộng.

## 6. Hai cải chính về CFD

Trong phiên, hai nhận định sai đã được đưa ra rồi sửa — ghi lại để không tái phát:

1. **"Dữ liệu CFD chỉ có ~10 tuần"** — chỉ đúng với **15m** (`2026-07-02 → 2026-09-11`, 71 ngày). Các khung
   1H/4H/1D có lịch sử `2024-04-19 → 2026-09-11`. `MIN_WINDOW_DAYS` vì thế loại toàn bộ CFD 15m và chỉ CFD 15m.
2. **"ICT lỗ trên CFD"** — con số $9.042/$8.828 là **toàn kỳ**. Trong cửa sổ 1 năm, CFD 1H ICT cfg A là
   **+1,5 %/năm**, tức có lãi. Nó bị loại vì **5 lệnh** (cần ≥ 15), không phải vì thua lỗ.

## 7. Hệ quả vận hành cần biết

Preset phương pháp đang đặt `ict` cho **cả hai** thị trường. Sau lần chọn này CFD **không còn setup ICT nào**, nên
với preset hiện tại pilot sẽ không có gì để đánh phía CFD. Đây là hệ quả của dữ liệu, không phải lỗi cấu hình.

## Cảnh báo

- Một năm, 96 lệnh sau lọc. Mẫu nhỏ; 29,1 % sụt giảm là số của **quá khứ**, không phải trần.
- Rủi ro đồng thời tối đa đo được 6,1 %, nhưng trần lý thuyết là 9 cặp × 3 % = **27 %**. Crypto tương quan gần như
  hoàn hảo khi sập — xem RISK NOTE trong `strategy-runner.py`.
- Backtest vào lệnh bằng LIMIT tại biên FVG và giả định khớp đầy đủ, không có trượt giá.
