> **Superseded 2026-09-13.** The ICT figures here were produced by the legacy in-file rules, replaced by the live scanner (`docs/plans/2026-09-13-unify-backtest-with-live-rules.md`); see `docs/backtests/2026-09-13-live-rules-vs-legacy.md`. Wyckoff / COMBINED / PARTIAL figures are unaffected.

# Vì sao Wyckoff hoặc ICT dùng riêng thua nhiều — chẩn đoán và thử khắc phục (2026-09-11)

> **Cảnh báo (cùng ngày, muộn hơn):** các số ICT/Kết hợp trong file này được đo TRƯỚC khi vá lỗi nhìn-trước của FVG và luật vào Kết hợp (xem `2026-09-11-stability-by-timeframe.md`, mục Cách đọc). Phần chẩn đoán Wyckoff (phí, vùng proxy, Test, target) vẫn đúng; các cột ICT/Kết hợp và lưới khắc phục thì lạc quan quá mức.

_Chạy bằng `scripts/backtest-methods.py` với các cờ mới `--min-rr`, `--range-touches`, `--htf`, `--entry test`, `--mgmt be`, `--fee-pct`, `--sides`. Mỗi ô: số lệnh · R ròng trung bình · %/năm quy đổi. Khung 1D bỏ khỏi bảng vì quá ít lệnh. Đây là lưới thử ~14 cấu hình trên cùng một mẫu, nên có rủi ro khớp quá mức; chỉ tin những hiệu ứng lặp lại ở nhiều khung._

## 1. Lọc R/R kế hoạch ≥ 3 không giúp

| Khung · phương pháp | R/R ≥ 0 | R/R ≥ 2 | R/R ≥ 3 |
|---|---|---|---|
_(bảng chi tiết theo bucket R/R kế hoạch ở mục 2; số %/năm khi lọc R/R trên cấu hình cơ sở: xem phần trả lời)_

## 2. Lưới khắc phục (%/năm, có phí)

| Cấu hình | 15m WYCKOFF | 15m ICT | 15m COMBINED | 1H WYCKOFF | 1H ICT | 1H COMBINED | 4H WYCKOFF | 4H ICT | 4H COMBINED |
|---|---|---|---|---|---|---|---|---|---|
| `(cơ sở: phí 0.05%, mọi loại KL, không lọc)` | n=1518 · -0.29R · -100.0% | n=903 · -0.17R · -94.1% | n=440 · +0.01R · -2.5% | n=1555 · -0.20R · -81.4% | n=551 · +0.10R · +28.4% | n=315 · +0.16R · +27.9% | n=486 · +0.07R · +11.5% | n=94 · +0.06R · +2.7% | n=76 · +0.04R · +1.3% |
| `--entry test` | n=1211 · -0.26R · -99.7% | n=903 · -0.17R · -94.1% | n=440 · +0.01R · -2.5% | n=1185 · -0.12R · -54.6% | n=551 · +0.10R · +28.4% | n=315 · +0.16R · +27.9% | n=377 · +0.09R · +15.9% | n=94 · +0.06R · +2.7% | n=76 · +0.04R · +1.3% |
| `--mgmt be` | n=1704 · -0.29R · -100.0% | n=903 · -0.15R · -91.7% | n=454 · -0.01R · -8.8% | n=1666 · -0.16R · -75.6% | n=551 · +0.07R · +18.2% | n=323 · +0.12R · +21.4% | n=501 · +0.08R · +16.0% | n=94 · +0.04R · +1.5% | n=77 · +0.06R · +2.2% |
| `--entry test --mgmt be` | n=1338 · -0.25R · -99.8% | n=903 · -0.15R · -91.7% | n=454 · -0.01R · -8.8% | n=1241 · -0.09R · -47.5% | n=551 · +0.07R · +18.2% | n=323 · +0.12R · +21.4% | n=383 · +0.06R · +9.4% | n=94 · +0.04R · +1.5% | n=77 · +0.06R · +2.2% |
| `--range-touches 2` | n=1001 · -0.32R · -99.7% | n=903 · -0.17R · -94.1% | n=302 · -0.06R · -28.9% | n=975 · -0.13R · -51.5% | n=551 · +0.10R · +28.4% | n=214 · +0.30R · +37.0% | n=228 · +0.21R · +21.3% | n=94 · +0.06R · +2.7% | n=36 · +0.24R · +4.3% |
| `--entry test --mgmt be --range-touches 2` | n=858 · -0.22R · -96.8% | n=903 · -0.15R · -91.7% | n=308 · -0.04R · -22.1% | n=751 · -0.06R · -23.1% | n=551 · +0.07R · +18.2% | n=215 · +0.25R · +30.8% | n=175 · -0.01R · -2.1% | n=94 · +0.04R · +1.5% | n=36 · +0.09R · +1.6% |
| `--entry test --mgmt be --range-touches 2 --min-rr 2` | n=665 · -0.28R · -96.6% | n=356 · -0.23R · -77.4% | n=77 · -0.17R · -21.9% | n=608 · -0.07R · -23.0% | n=191 · +0.16R · +15.0% | n=60 · +0.33R · +10.0% | n=133 · -0.02R · -2.1% | n=20 · +0.31R · +3.0% | n=9 · -0.15R · -0.7% |
| `--entry test --mgmt be --range-touches 2 --min-rr 3` | n=489 · -0.34R · -95.2% | n=194 · -0.20R · -52.4% | n=49 · -0.06R · -6.7% | n=480 · -0.09R · -22.7% | n=96 · +0.05R · +1.7% | n=39 · +0.03R · +0.3% | n=92 · -0.24R · -10.8% | n=5 · +0.86R · +2.1% | n=4 · -0.55R · -1.1% |
| `--entry test --mgmt be --range-touches 2 --htf` | n=587 · -0.25R · -93.1% | n=390 · -0.19R · -74.5% | n=190 · -0.05R · -17.6% | n=560 · -0.03R · -12.1% | n=212 · +0.12R · +12.6% | n=154 · +0.24R · +19.8% | n=99 · -0.05R · -2.8% | n=34 · -0.10R · -1.7% | n=17 · -0.22R · -1.9% |
| `--entry test --mgmt be --range-touches 2 --fee-pct 0.02` | n=858 · -0.09R · -78.5% | n=903 · -0.04R · -48.7% | n=308 · +0.03R · +15.7% | n=751 · -0.00R · -5.5% | n=551 · +0.12R · +34.9% | n=215 · +0.28R · +34.8% | n=175 · +0.02R · +0.5% | n=94 · +0.06R · +2.6% | n=36 · +0.11R · +1.8% |
| `--entry test --mgmt be --range-touches 2 --fee-pct 0.02 --min-rr 2` | n=665 · -0.14R · -82.0% | n=356 · -0.08R · -43.1% | n=77 · -0.03R · -6.3% | n=608 · -0.01R · -7.7% | n=191 · +0.22R · +22.1% | n=60 · +0.37R · +11.4% | n=133 · +0.01R · +0.2% | n=20 · +0.34R · +3.3% | n=9 · -0.13R · -0.6% |
| `--entry test --mgmt be --range-touches 2 --fee-pct 0.02 --htf` | n=587 · -0.13R · -75.5% | n=390 · -0.09R · -48.0% | n=190 · +0.03R · +6.2% | n=560 · +0.02R · +2.5% | n=212 · +0.16R · +17.9% | n=154 · +0.27R · +22.3% | n=99 · -0.02R · -1.4% | n=34 · -0.08R · -1.4% | n=17 · -0.21R · -1.8% |
| `--entry test --mgmt be --range-touches 2 --fee-pct 0.02 --htf --min-rr 2` | n=458 · -0.17R · -75.8% | n=175 · -0.17R · -43.3% | n=54 · +0.07R · +4.2% | n=469 · -0.00R · -3.4% | n=99 · +0.19R · +9.3% | n=47 · +0.31R · +7.4% | n=76 · -0.00R · -0.6% | n=11 · +0.04R · +0.2% | n=7 · -0.58R · -2.0% |
| `--entry test --mgmt be --range-touches 2 --fee-pct 0.02 --sides long` | n=452 · -0.09R · -53.9% | n=459 · +0.02R · +12.3% | n=142 · +0.06R · +14.0% | n=395 · +0.01R · -1.0% | n=268 · +0.24R · +37.1% | n=105 · +0.27R · +14.7% | n=94 · +0.01R · +0.2% | n=48 · +0.12R · +2.9% | n=23 · +0.09R · +1.0% |

## 3. Chẩn đoán (từ `data/history/backtest-methods-2026-09-11.json`, cấu hình cơ sở)

**Wyckoff đơn lẻ**

1. **Phí so với khoảng stop.** 15m: stop trung vị 0,48% giá → phí 0,1%/vòng = 0,21R mỗi lệnh; tổng ΣR gộp −53R nhưng ròng −442R, tức 389R là phí. 1H: 202R trong 305R lỗ là phí.
2. **'Trading range' của proxy không phải TR Wyckoff.** Đáy 48 nến trong một xu hướng giảm bị đếm là 'Spring'. Nhóm R/R kế hoạch ≥ 6 (30–38% số lệnh) chỉ thắng 11–12%: stop sát đáy Spring, target là đỉnh cửa sổ xa tít — đúng hình dạng của một nhịp xu hướng chứ không phải vùng tích lũy. Lọc 'biên đã được test ≥ 2 lần mỗi phía' (WA p71–72) cải thiện ở cả 1H, 4H, 1D.
3. **Vào ngay tại nến đóng lại, bỏ qua Test.** Lệnh loại 1 vào ngay trên 1H: thắng 14%, −0,51R. Bắt buộc chờ Test (WA p80: Test là xác nhận) kéo 1H từ −81% lên −55%/năm; nhưng trên 4H lại làm giảm (vào ngay ở 4H vốn +0,08R) → hiệu ứng phụ thuộc khung.
4. **Target biên đối diện quá xa cho vùng proxy.** Các lệnh hết hạn H nến (timeout) thắng 86–91%, +1,7–2,0R trung bình: giá đi đúng hướng nhưng không tới target. Dời stop hoà vốn tại +1R (WMT p272) giúp nhẹ.
5. **Short ngược thị trường tăng 2024–2026.** 1H: short −0,25R vs long −0,13R. Chỉ long: Wyckoff 1H về ≈ −1%/năm.
6. **Thiếu cổng CHoCH, đối nhãn, Volume Profile** — không proxy hoá được bằng code; đây là phần audit ghi MISSING và chỉ phân tích đầy đủ mới làm được.

**ICT đơn lẻ**

1. **Phí.** 15m gộp +21R, ròng −153R. Với phí maker 0,02% (lệnh limit tại FVG) 15m vẫn −49%/năm; chỉ long +12%.
2. **Target quá gần.** Target = đỉnh cũ gần nhất; R/R kế hoạch trung vị 1,4–1,6. 47% lệnh có R/R < 1,5: thắng 58–65% nhưng R trung bình ≈ 0. Deck dùng ERL kế tiếp / phép chiếu std-dev −2/−2,5/−4 (audit ICT lỗ hổng 7, chưa có trong code).
3. **Sweep của bất kỳ pivot 3 nến nào** trong xu hướng bị đếm; không có bối cảnh 'draw on liquidity' khung lớn, không PD array (audit ICT lỗ hổng 1–3, 9).
4. **Short ngược xu hướng**: 1H short −0,03R vs long +0,24R.
5. 1H là khung ICT đơn lẻ hoạt động tốt nhất: +28%/năm cơ sở, +35% với phí maker, +37% chỉ long.

## 4. Kết luận khắc phục

- **Không scalping 15m** với stop 0,5% và phí taker: phí nuốt 0,2R mỗi lệnh, không cấu hình nào dương trừ kết hợp + phí maker + chỉ long.
- **Khung 1H là khung khả thi nhất** cho cả ICT và kết hợp; 4H chỉ Wyckoff có vùng đã xác lập là dương (+21%/năm với `--range-touches 2`).
- **Bắt buộc vùng đã xác lập** (≥ 2 lần test mỗi biên) trước khi gọi Spring — hiệu ứng dương ở mọi khung ≥ 1H, cho cả Wyckoff và kết hợp (1H kết hợp +37%/năm).
- **Vào bằng lệnh limit** (tại Test hoặc mép FVG) để trả phí maker: chuyển 1H Wyckoff từ −23% lên −5%, ICT từ +18% lên +35%.
- **Lọc R/R kế hoạch ≥ 2 chỉ hợp lý cho ICT** (R trung bình 1H tăng 0,10 → 0,28 nhưng tổng lợi nhuận không tăng); ≥ 3 làm cạn số lệnh và giảm lợi nhuận ở mọi khung. Với Wyckoff proxy, R/R kế hoạch cao là dấu hiệu Spring giả, không phải lệnh tốt.
- **Theo chiều khung lớn** (chỉ long khi khung lớn ở phần ba dưới vùng hoặc đã phá lên, đúng luật biên trong `htf_context.py`): giảm sụt giảm tối đa (ICT 1H −17% → −8%) với lợi nhuận tương đương.
- **Với Wyckoff đơn lẻ, tốt nhất bằng code chỉ tới ≈ hoà vốn**; phần còn lại (CHoCH, đối nhãn, VP veto, đọc SOT) phải đến từ phân tích đầy đủ. Cần đo lại trên các Spring do phân tích đầy đủ gọi ra khi tích luỹ đủ mẫu.