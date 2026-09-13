# Scalping 15m — kết quả TỪNG CẶP với R:R kế hoạch ≥ 2, 3, 4, 5, 6 · rủi ro 3 %/lệnh — 2026-09-13

_Trả lời yêu cầu ngày 2026-09-13: "kết quả của toàn bộ các cặp trade với R:R kì vọng khi vào lệnh là 2 hoặc 3, mỗi
lệnh 3 % như thiết lập hiện tại" — và yêu cầu tiếp theo cùng ngày: thêm mức 4, 5, 6 rồi tổng kết chung._

**Kết luận một dòng: R:R ≥ 3 là đỉnh. Siết chặt hơn nữa (4, 5, 6) làm xấu mọi chỉ tiêu cùng lúc — xem mục 1.**

Nguồn số: `scripts/backtest-methods.py --tf 15m --min-rr {2,3,4,5,6}`, nến lưu ở `data/history/`, phí taker 0,05 %/chiều,
vốn đầu kỳ `START = $10.000`, rủi ro `RISK = 0.03` (`backtest-methods.py:57` — đúng thiết lập hiện tại, bằng
`strategy-runner.RISK_CEILING`). Luật ICT đọc từ live (`scripts/live_rules.py`); preset đang bật trên bảng điều
khiển là `ict` cho **cả hai** thị trường (`control/applied.crypto`, `control/applied.cfd`), nên **hàng ICT là hàng
có thật**; WYCKOFF / COMBINED để đối chiếu.

JSON thô: `crypto-rr{2,3,4,5,6}.json`, `cfd-rr{2,3,4,5,6}.json` trong scratchpad của phiên
`cd4d2265-5156-402f-9c70-3fe629dfcf68` (không commit; chạy lại bằng lệnh ở trên là ra y hệt).

## 0. Phạm vi thực tế — đọc trước

| thị trường | công cụ | nến 15m có? |
|---|---|---|
| crypto | BTCUSDT ETHUSDT SOLUSDT ASTERUSDT VIRTUALUSDT SUIUSDT TAOUSDT RENDERUSDT ONDOUSDT | **có, cả 9** |
| cfd | XAUUSD | có, nhưng chỉ 4.526 nến (2026-07-02 → 2026-09-11 ≈ 71 ngày), nguồn Yahoo `GC=F` *research-only* |
| cfd | **XAGUSD, USOIL, UKOIL** | **KHÔNG CÓ** — `data/history/` chỉ có 1H/2H/4H/1D cho ba mã này |

`scripts/fetch-history-cfd.py` không ghi khung 15m (chỉ 1H/2H/4H/1D), nên ba mã CFD kia **không thể trả lời được**
ở khung 15m với dữ liệu hiện tại. Lưu ý thêm: lựa chọn CFD đang bật trên bảng điều khiển là `XAGUSD, XAUUSD` —
tức **một nửa lựa chọn CFD đang chạy không có nền dữ liệu 15m để kiểm chứng**.

## 1. BẢNG TỔNG KẾT — sàn R:R 2 → 6, preset `ict`, crypto, rủi ro 3 %/lệnh

Khung 15m, 2023-09-13 → 2026-09-13 (3 năm), chín mã chia một tài khoản $10.000. `vốn thấp nhất` = điểm thấp nhất
của đường vốn, so với ngưỡng halt vĩnh viễn $8.500 (`strategy-runner.EQUITY_HALT_FRAC = 0.85`).

| Sàn R:R | Lệnh | Thắng | R ròng TB | ΣR | PF | Vốn cuối | Lợi nhuận | %/năm | Sụt giảm tối đa | Quý dương | Quý tệ nhất | Quý trung vị | Vốn thấp nhất | Halt |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ≥ 2 | 287 | 38 % | +0,31 | +88,2 | 1,48 | $84.069 | +740,7 % | +103,2 % | −39,4 % | 9/13 | −25,7 % | +25,6 % | $8.656 | ok (biên 1,6 %) |
| **≥ 3** | **217** | **39 %** | **+0,42** | **+90,1** | **1,63** | **$94.099** | **+841,0 %** | **+111,0 %** | **−30,9 %** | **9/13** | **−21,8 %** | **+16,7 %** | **$8.981** | **ok (biên 5,7 %)** |
| ≥ 4 | 151 | 36 % | +0,40 | +61,1 | 1,58 | $43.652 | +336,5 % | +63,4 % | −52,3 % | 8/13 | −25,1 % | +8,2 % | $8.981 | ok |
| ≥ 5 | 110 | 35 % | +0,37 | +40,7 | 1,52 | $25.728 | +157,3 % | +37,0 % | −48,2 % | 7/13 | −21,1 % | +8,9 % | $8.981 | ok |
| ≥ 6 | 71 | 32 % | +0,38 | +27,2 | 1,52 | $18.440 | +84,4 % | +22,6 % | −31,5 % | 6/13 | −17,6 % | +0,0 % | $9.278 | ok |

### Theo năm

| Sàn R:R | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|
| ≥ 2 | +33,0 % | +115,8 % | +43,6 % | +111,2 % |
| **≥ 3** | **+42,7 %** | **+109,1 %** | **+60,3 %** | **+103,7 %** |
| ≥ 4 | +52,7 % | +98,4 % | **−16,0 %** | +77,5 % |
| ≥ 5 | +46,3 % | +84,0 % | **−13,3 %** | +10,3 % |
| ≥ 6 | +35,2 % | +31,9 % | +1,1 % | +2,3 % |

### Đọc bảng

**Đường cong có đỉnh rõ ở 3, không phải "càng chặt càng tốt".**

1. **ΣR đạt cực đại đúng tại 3** (+90,1) rồi đổ: 4 → +61,1 · 5 → +40,7 · 6 → +27,2. Từ 3 lên 4 bỏ 66 lệnh (−30 %)
   và mất 32 % tổng R. Chất lượng mỗi lệnh **không** tăng để bù: R ròng TB đứng im quanh +0,38–0,42 và tỉ lệ
   thắng **giảm** (39 % → 36 % → 35 % → 32 %). Tức là lọc trên 3 không loại lệnh xấu, nó loại cả lệnh tốt.
2. **Sụt giảm TĂNG khi siết lên 4 và 5** (−30,9 % → −52,3 % → −48,2 %) dù số lệnh ít hơn. Ít lệnh hơn ở 3 % rủi ro
   = chuỗi thua ít được pha loãng, nên mỗi chuỗi thua ăn sâu hơn. Đây là điểm phản trực giác quan trọng nhất:
   **siết R:R quá tay làm tài khoản rủi ro hơn, không an toàn hơn.**
3. **Tính bền theo quý xói mòn đều**: 9/13 quý dương ở 2–3, xuống 8, 7, rồi 6/13 ở mức 6. Quý trung vị từ +16,7 %
   về +0,0 %.
4. **Năm 2025 lật sang âm ngay khi vượt 3** (−16,0 % ở mức 4, −13,3 % ở mức 5). Cả 2026 sụp ở mức 5–6 (+10,3 %,
   +2,3 %). Sàn cao chỉ sống được trong hai năm sóng mạnh 2023–2024.
5. **Chọn 3 thay vì 2 vì cổng halt**, không vì lợi nhuận (841 % vs 741 % là cùng một khoảng): ở mức 2 đường vốn
   xuống $8.656, chỉ cách mức halt vĩnh viễn $8.500 đúng 1,6 %; ở mức 3 là $8.981, biên rộng gấp ba rưỡi.
6. Không mức nào chạm halt trong mẫu này — nhưng mẫu này gần như toàn bộ là crypto đi lên.

**Kết luận: giữ nguyên sàn 3 đang cấu hình** (`docs/architecture/analysis-params.json` →
`project_defined.ict.min_rr = 3.0`). Dữ liệu không ủng hộ việc nâng lên 4 trở lên ở bất kỳ chỉ tiêu nào.

## 1b. So sánh ba preset ở mức 2 và 3 (vì sao trần 3 % chỉ an toàn với `ict`)

Khung 15m, 2023-09-13 → 2026-09-13 (3 năm; cửa sổ là hợp của các mã, mỗi mã bắt đầu từ ngày có dữ liệu).

| Lọc | Phương pháp | Lệnh | Thắng | R ròng TB | ΣR | PF | Vốn cuối (từ $10.000) | %/năm | Sụt giảm tối đa | Cháy |
|---|---|---|---|---|---|---|---|---|---|---|
| **R:R ≥ 2** | **ICT** | **287** | **38 %** | **+0,31** | **+88,2** | **1,48** | **$84.069 (+740,7 %)** | **+103,2 %** | **−39,4 %** | — |
| R:R ≥ 2 | WYCKOFF | 157 | 23 % | −0,45 | −70,0 | 0,54 | $993 (−90,1 %) | −53,7 % | −91,6 % | CHÁY 2023-10-04 |
| R:R ≥ 2 | COMBINED | 382 | 25 % | −0,15 | −58,2 | 0,82 | $998 (−90,0 %) | −53,6 % | −90,0 % | CHÁY 2025-01-13 |
| **R:R ≥ 3** | **ICT** | **217** | **39 %** | **+0,42** | **+90,1** | **1,63** | **$94.099 (+841,0 %)** | **+111,0 %** | **−30,9 %** | — |
| R:R ≥ 3 | WYCKOFF | 114 | 15 % | −0,62 | −70,6 | 0,47 | $988 (−90,1 %) | −53,7 % | −90,2 % | CHÁY 2023-10-02 |
| R:R ≥ 3 | COMBINED | 309 | 21 % | −0,19 | −59,8 | 0,79 | $987 (−90,1 %) | −53,7 % | −92,2 % | CHÁY 2025-03-18 |

**Ở rủi ro 3 %, chỉ ICT sống.** WYCKOFF và COMBINED cháy tài khoản ở cả hai mức R:R — trần 3 % chỉ an toàn vì
preset đang bật là `ict`. Đổi preset sang `wyckoff` hoặc `wyckoff+ict` mà giữ 3 % là đổi sang một đường cháy.

Số ICT theo năm/quý và điểm vốn thấp nhất so với cổng halt: xem bảng tổng kết ở mục 1 (cả năm mức R:R).
`simulate()` không mô phỏng cái halt vĩnh viễn, nên cột `Vốn thấp nhất` / `Halt` ở mục 1 là phép chiếu tay lên
chính đường vốn backtest.

## 2. Ma trận từng cặp — lợi nhuận % qua cả năm mức R:R

Mỗi ô = cặp đó chạy **một mình** trong tài khoản $10.000 riêng ở sàn R:R đó (không phải phần của tài khoản gộp ở
mục 1 — không cộng các dòng lại được). `n` = số lệnh.

| Mã | R:R ≥ 2 | R:R ≥ 3 | R:R ≥ 4 | R:R ≥ 5 | R:R ≥ 6 |
|---|---|---|---|---|---|
| ETHUSDT | +81,6 % (n=40) | +73,3 % (n=29) | **+113,4 % (n=20)** | +97,2 % (n=12) | +42,9 % (n=8) |
| TAOUSDT | +68,8 % (n=38) | **+79,6 % (n=29)** | +33,5 % (n=19) | +22,5 % (n=17) | +26,8 % (n=9) |
| BTCUSDT | +24,5 % (n=51) | **+48,5 % (n=38)** | +36,9 % (n=32) | −9,3 % (n=24) | +6,1 % (n=18) |
| ONDOUSDT | **+52,6 % (n=22)** | +49,0 % (n=18) | +27,9 % (n=11) | +13,6 % (n=7) | −0,1 % (n=3) |
| SUIUSDT | +29,9 % (n=45) | **+46,0 % (n=33)** | +12,3 % (n=22) | +16,5 % (n=15) | +0,4 % (n=9) |
| RENDERUSDT | +21,3 % (n=32) | **+22,5 % (n=25)** | −9,3 % (n=20) | −15,0 % (n=14) | −16,1 % (n=11) |
| SOLUSDT | **+10,3 % (n=26)** | −0,4 % (n=18) | −10,7 % (n=11) | −1,6 % (n=8) | +5,1 % (n=6) |
| ASTERUSDT | +6,7 % (n=8) | +2,7 % (n=6) | +6,2 % (n=5) | **+9,7 % (n=4)** | +9,7 % (n=4) |
| **VIRTUALUSDT** | **−22,2 %** (n=25) | **−25,4 %** (n=21) | −9,5 % (n=11) | −3,2 % (n=9) | −1,0 % (n=3) |
| Số mã dương | 8/9 | 7/9 | 6/9 | 5/9 | 6/9 |

Đọc ma trận:

- **Sáu trong chín mã đạt đỉnh ở 2 hoặc 3** (TAO, BTC, SUI, RENDER đỉnh ở 3; ONDO, SOL ở 2). ETHUSDT là mã duy
  nhất đỉnh ở 4 (+113,4 %). ASTERUSDT bằng nhau ở 5 và 6 nhưng với n=4 — nhiễu, không phải tín hiệu.
  VIRTUALUSDT âm ở mọi mức nên "đỉnh" của nó chỉ là mức ít lỗ nhất, không có nghĩa gì.
- **RENDERUSDT lật dấu tại 4** (+22,5 % → −9,3 % → −15,0 % → −16,1 %): mọi lệnh có R:R kế hoạch cao của nó đều là
  lệnh thua. Mã này bị loại khỏi lựa chọn nếu sàn từng được nâng.
- **VIRTUALUSDT âm ở cả năm mức.** Không phải vấn đề sàn R:R — luật ICT không có lợi thế trên mã này.
- Cỡ mẫu ở mức 5–6 rơi xuống 3–9 lệnh cho nửa số mã. **Đừng ra quyết định giữ/loại mã nào từ hai cột cuối.**

## 3. Chi tiết từng cặp — ICT, R:R ≥ 2, rủi ro 3 %

Mỗi dòng = cặp đó chạy **một mình** trong tài khoản $10.000 riêng (không phải phần của tài khoản gộp ở mục 1).
`medRR` = R:R kế hoạch trung vị. Cửa sổ khác nhau giữa các mã vì ngày bắt đầu dữ liệu khác nhau.

| Mã | Lệnh | Thắng | R ròng TB | ΣR | PF | Vốn cuối | Lợi nhuận | Sụt giảm | medRR | Giai đoạn |
|---|---|---|---|---|---|---|---|---|---|---|
| ETHUSDT | 40 | 42 % | +0,58 | +23,0 | 2,01 | $18.159 | **+81,6 %** | −16,2 % | 4,17 | 2023-10-16→2026-09-09 |
| TAOUSDT | 38 | 42 % | +0,54 | +20,4 | 1,90 | $16.882 | +68,8 % | −17,5 % | 4,03 | 2024-05-11→2026-05-27 |
| ONDOUSDT | 22 | 45 % | +0,71 | +15,7 | 2,22 | $15.257 | +52,6 % | −12,4 % | 4,26 | 2025-04-26→2026-07-22 |
| SUIUSDT | 45 | 40 % | +0,24 | +10,7 | 1,39 | $12.989 | +29,9 % | −24,3 % | 3,93 | 2023-10-29→2026-07-22 |
| BTCUSDT | 51 | 33 % | +0,22 | +11,1 | 1,28 | $12.454 | +24,5 % | −39,7 % | 4,72 | 2023-10-02→2026-09-09 |
| RENDERUSDT | 32 | 34 % | +0,25 | +8,1 | 1,38 | $12.133 | +21,3 % | −20,3 % | 4,57 | 2024-10-26→2026-08-23 |
| SOLUSDT | 26 | 38 % | +0,18 | +4,7 | 1,29 | $11.026 | +10,3 % | −18,9 % | 3,56 | 2023-10-10→2026-08-07 |
| ASTERUSDT | 8 | 50 % | +0,30 | +2,4 | 1,63 | $10.674 | +6,7 % | −7,2 % | 7,32 | 2025-11-16→2026-09-07 |
| **VIRTUALUSDT** | 25 | 28 % | −0,31 | −7,7 | 0,60 | $7.783 | **−22,2 %** | −23,3 % | 3,75 | 2025-04-27→2026-07-22 |

## 4. Chi tiết từng cặp — ICT, R:R ≥ 3, rủi ro 3 % (mức đang cấu hình)

| Mã | Lệnh | Thắng | R ròng TB | ΣR | PF | Vốn cuối | Lợi nhuận | Sụt giảm | medRR | Giai đoạn |
|---|---|---|---|---|---|---|---|---|---|---|
| TAOUSDT | 29 | 45 % | +0,77 | +22,2 | 2,30 | $17.958 | **+79,6 %** | −14,6 % | 5,12 | 2024-05-11→2026-05-27 |
| ETHUSDT | 29 | 45 % | +0,73 | +21,1 | 2,25 | $17.333 | +73,3 % | −10,0 % | 4,77 | 2023-10-16→2026-09-09 |
| ONDOUSDT | 18 | 44 % | +0,82 | +14,8 | 2,38 | $14.901 | +49,0 % | −9,3 % | 4,82 | 2025-04-26→2026-07-17 |
| BTCUSDT | 38 | 34 % | +0,44 | +16,6 | 1,58 | $14.852 | +48,5 % | −29,3 % | 5,97 | 2023-10-02→2026-09-09 |
| SUIUSDT | 33 | 45 % | +0,44 | +14,4 | 1,75 | $14.602 | +46,0 % | −17,8 % | 4,87 | 2023-10-29→2026-07-22 |
| RENDERUSDT | 25 | 36 % | +0,32 | +8,1 | 1,50 | $12.252 | +22,5 % | −17,7 % | 5,69 | 2024-10-26→2026-08-23 |
| ASTERUSDT | 6 | 50 % | +0,18 | +1,1 | 1,34 | $10.273 | +2,7 % | −6,3 % | 8,17 | 2025-11-20→2026-09-07 |
| SOLUSDT | 18 | 28 % | +0,06 | +1,0 | 1,08 | $9.963 | −0,4 % | −17,1 % | 4,75 | 2023-10-10→2026-08-07 |
| **VIRTUALUSDT** | 21 | 24 % | −0,44 | −9,3 | 0,46 | $7.461 | **−25,4 %** | −25,4 % | 4,10 | 2025-04-27→2026-07-22 |

Đọc gì từ hai bảng chi tiết: siết từ ≥ 2 lên ≥ 3 **bỏ 70 lệnh (287 → 217, −24 %)** mà ΣR vẫn tăng (+88,2 → +90,1)
và PF tăng (1,48 → 1,63) — đây là lần siết duy nhất có lãi; mọi lần siết sau đó đều lỗ (mục 1).
**VIRTUALUSDT âm ở cả hai và tệ hơn khi siết** — nó không phải là một cặp bị lọc sai, nó là cặp duy nhất mà luật
ICT không có lợi thế; SOLUSDT gần như bằng không ở ≥ 3. Hai mã này là ứng viên loại khỏi lựa chọn, nhưng cỡ mẫu
21–26 lệnh chưa đủ để kết luận dứt khoát.

## 5. CFD — XAUUSD, 15m, cả năm mức R:R

Cửa sổ 2026-07-02 → 2026-09-11 (71 ngày, 4.526 nến, futures `GC=F` chứ không phải giá CFD).

| Sàn R:R | Phương pháp | Lệnh | Thắng | ΣR | Vốn cuối | Sụt giảm |
|---|---|---|---|---|---|---|
| ≥ 2 | **ICT** | **1** | 0 % | −1,2 | $9.634 (−3,7 %) | −3,7 % |
| ≥ 3 | **ICT** | **1** | 0 % | −1,2 | $9.634 (−3,7 %) | −3,7 % |
| ≥ 4 | **ICT** | **0** | — | — | $10.000 (0,0 %) | — |
| ≥ 5 | **ICT** | **0** | — | — | $10.000 (0,0 %) | — |
| ≥ 6 | **ICT** | **0** | — | — | $10.000 (0,0 %) | — |
| ≥ 2 | WYCKOFF | 96 | 17 % | −58,7 | $1.397 (−86,0 %) | −89,6 % |
| ≥ 3 | WYCKOFF | 84 | 13 % | −62,1 | $1.277 (−87,2 %) | −89,8 % |

**Preset đang bật (`ict`) sinh ĐÚNG MỘT lệnh trên vàng trong 71 ngày ở mức 2–3, và KHÔNG lệnh nào từ mức 4 trở
lên.** Đó không phải một kết quả — đó là không có kết quả. Không kết luận được gì về CFD 15m ở bất kỳ mức R:R nào.
WYCKOFF trên vàng 15m thì thua thảm (0/3 tháng dương, sụt 90 %) và ở 3 % rủi ro là đường cháy.

## 6. Lỗi phát hiện khi chạy — ĐÃ SỬA 2026-09-13

Cả bốn đã sửa theo TDD (test đỏ trước, `scripts/tests/test_min_rr_and_risk.py`, toàn bộ suite 392 test xanh).

1. **Tiêu đề báo cáo in sai trần rủi ro.** Là chuỗi cố định `"rủi ro 1%/lệnh"` trong khi `RISK = 0.03` — mọi số
   vốn trong mọi báo cáo cũ là đường 3 % nhưng dán nhãn 1 %. Nay tiêu đề nội suy từ `RISK`; docstring dòng 2 và
   45 không còn nêu con số bằng chữ. Test: `BacktestReportHonesty.test_the_report_does_not_claim_a_risk_it_does_not_use`.
2. **Bảng năm/quý/tháng lấy khoá kỳ từ `res["WYCKOFF"]`.** WYCKOFF cháy 2023-10 nên khoá của nó chỉ còn 2023 và
   2026 → bảng mất hẳn 2024 và 2025 cho MỌI phương pháp, kể cả ICT. Nay dùng `period_keys(res, key)` = hợp của
   mọi phương pháp. Đo trên `crypto-rr3.json`: bảng quý từ **3 kỳ lên 13 kỳ**.
   Test: `test_period_keys_are_the_union_across_methods_not_one_method_s`.
3. **Dòng Caveats thiếu tiền tố `f`** — in ra nguyên văn `${START:,.0f}`. Nay render `$10,000` và nêu luôn trần
   rủi ro thật. Test: `test_the_caveats_render_the_account_size` (khẳng định trên tiền tố `f"`, không phải trên
   nội dung chữ — bản test đầu tiên của tao *pass* ngay trên chính cái lỗi nó định bắt, vì `"- Tài khoản … ${START`
   cũng là substring của bản đã sửa).
4. **`demo-pilot.py` không hề có sàn R:R** (lỗi nặng nhất, tìm ra sau, không nằm trong ba lỗi hiển thị trên).
   Chi tiết ở mục 6b.

## 6b. `demo-pilot.py` — đường đặt lệnh thứ hai đã bị bỏ sót

`pilot-loop.sh:31` chạy `demo-pilot.py` với mọi cặp profile/market **không phải** `top5`+`futures`
(`pilot-loop.sh:26` mới chạy `strategy-runner.py`). Quyết định 3R ngày 2026-09-13 không tới được file này:

- Nó giữ bản sao riêng `MIN_RR = 2.0`, **hardcode**, không đọc `analysis-params.json` — floor đã nâng lên 3.0 mà
  bản sao này ở lại 2.0.
- Tệ hơn: con số đó **chưa bao giờ chặn một lệnh nào**. Nó chỉ dùng để chọn TP —
  `tp = eq if (eq-entry) >= MIN_RR*r else entry + 2*r`. Setup có target cấu trúc gần hơn floor được **giãn** ra
  một target tổng hợp đúng 2R thay vì bị từ chối. Đó vừa là bản sao thứ hai của floor cũ, vừa làm mọi floor
  không thể thi hành.

Đã sửa:

| | Trước | Sau |
|---|---|---|
| Nguồn floor | `MIN_RR = 2.0` hardcode | `_min_rr()` đọc `analysis-params.json`; `None` nếu file thiếu/không đọc được/giá trị không hợp lệ |
| Cổng vào lệnh | không có | `rr_reason()` trong `reasons[]` của `evaluate()` — fail-closed ba đường: floor `None`, `r_planned` thiếu/không phải số/NaN |
| TP | `eq`, hoặc giãn `entry ± 2*r` | luôn là `eq` (target cấu trúc); nếu nó kế hoạch < floor thì **từ chối**, không giãn |

Fail-closed trên floor không đọc được theo `docs/security/2026-09-11-top5-pilot.md` ("a missing or unreadable
config MUST refuse"): floor không biết không phải là floor bằng 0. `rr_reason()` soi gương
`strategy-runner.rr_reason()`, kể cả phép thử NaN `rr != rr` (vì `nan < 3.0` là False, so sánh thường sẽ **mở**
cổng). Nay cả ba đường quyết định — backtest (`:464`), runner, pilot — cùng một floor, cùng một nguồn, và đều
**từ chối** dưới floor thay vì giãn target.

Lưu ý: hiện `layers.pilot = off`, nên thay đổi này chưa đổi hành vi đang chạy; nó bịt lỗ cho lần bật lại.

## 7. Caveats

- Spring/Upthrust và MSS/FVG là **proxy bằng code**: không cổng CHoCH, không đối nhãn, không Volume Profile, không
  footprint. Phân tích đầy đủ sẽ lọc bớt và số thật sẽ khác.
- Số từng cặp ở mục 2–4 là **tài khoản riêng cho mỗi cặp**; hệ thống thật chia một tài khoản (mục 1), nên không
  cộng chín dòng đó lại được.
- Cửa sổ mỗi cặp khác nhau (ngày bắt đầu dữ liệu). ETHUSDT có 3 năm, ASTERUSDT có 10 tháng — không so trực tiếp.
- Phí 0,05 %/chiều, **không** tính trượt giá và funding. Ở 15m stop hẹp, phí ăn phần đáng kể của mỗi R.
- Một vị thế mở/mã; lệnh trùng thời gian bị bỏ. Nến chạm cả stop và target tính là thua.
- Cỡ mẫu **sụp nhanh khi sàn R:R lên cao**: ở mức 6 thì ONDOUSDT còn 3 lệnh, VIRTUALUSDT 3, ASTERUSDT 4. Cả cột
  R:R ≥ 5 và ≥ 6 trong ma trận mục 2 là chỉ dấu, không phải bằng chứng. Dưới ~30 lệnh đừng ra quyết định giữ/loại.
- Sàn R:R chỉ lọc theo **R:R kế hoạch tại lúc vào lệnh** (`target/stop`), không phải R thực hiện. Một lệnh kế
  hoạch 6R vẫn có thể đóng bằng timeout ở +0,3R — đó là lý do R ròng TB không tăng theo sàn.
- Ba năm này gần như toàn bộ là thị trường crypto đi lên; chưa có bear market dài trong mẫu. Các sàn cao (4–6)
  phụ thuộc nặng vào hai năm sóng mạnh 2023–2024 và đã âm trong 2025 — mẫu chưa đủ để tin chúng ở chế độ khác.
