# Target ICT theo deck — chiếu std-dev, ERL kế tiếp, IRL — 2026-09-11 (lựa chọn 3 của người dùng)

Luật vào ICT giữ nguyên (sweep pivot → MSS đóng thân → FVG hoàn thành trước MSS → limit tại mép FVG, nhân quả). Chỉ đổi cách đặt target
(`backtest-methods.py --ict-target`, hàm `ict_target`):

| Target | Nguồn | Định nghĩa trong code |
|---|---|---|
| `range` | proxy dự án (bản trước) | cực trị R nến trước cú sweep |
| `std2` / `std25` / `std4` | knowledge/05 §2.12, R16–R18 (23. STD p4–p9) | fib 1 tại cực trị sweep, 0 tại swing nơi nhịp thao túng bắt đầu (pivot cuối trước sweep); −2 / −2,5 = vùng hồi/đảo (chốt lời), −4 = mở rộng tối đa |
| `erl_next` | knowledge/05 §2.13, R3/R20 | thanh khoản ngoài kế tiếp: pivot đầu tiên vượt mức MSS phá trong R nến trước sweep |
| `irl` | knowledge/05 §2.13 | FVG đối diện gần nhất phía trên (long) trong R nến trước sweep, mép gần; không có → `erl_next` |

Đầy đủ: `2026-09-11-ict-target-<target>.md` (mỗi file một bảng xếp hạng + theo năm cho 30m/1H/2H/4H, cấu hình A/B/C). Cả long lẫn short.

## Kết quả ICT theo target (%/năm · sụt giảm · quý dương), tài khoản $10.000, 2022-09 → 2026-09

| Khung · cấu hình | range | std2 | std25 | std4 | erl_next | irl |
|---|---|---|---|---|---|---|
| 30m · B (maker, BE) | +8,8 · −31 · 53 % | +20,5 · −33 · 59 % | +22,6 · −37 · 53 % | +32,3 · −39 · 53 % | −9,6 · −59 · 53 % | −4,9 · −48 · 53 % |
| 30m · C (B + lọc 2H) | +10,2 · −19 · 53 % | +12,7 · −20 · 71 % | **+17,6 · −20 · 82 %** | +13,4 · −27 · 71 % | −4,1 · −32 · 41 % | +1,4 · −16 · 41 % |
| 1H · B | +2,7 · −19 · 41 % | +4,9 · −25 · 41 % | +9,4 · −27 · 47 % | +5,4 · −37 · 41 % | −5,0 · −26 · 47 % | −5,0 · −27 · 41 % |
| 2H · A (taker) | +5,5 · −16 · 71 % | −3,3 · −24 · 47 % | −3,0 · −26 · 47 % | −1,0 · −27 · 41 % | +2,3 · −11 · 65 % | −0,2 · −17 · 47 % |
| 4H · A (taker) | +4,7 · −7 · 59 % | +9,2 · −7 · 71 % | **+9,8 · −7 · 76 %** | +10,7 · −8 · 76 % | +3,2 · −8 · 59 % | +2,5 · −7 · 59 % |

Theo năm của hai dòng nổi bật (2022 → 2026): 30m std25 C: +12,4 / −0,2 / +10,0 / +15,1 / +34,4 %; 4H std25 A: +1,7 / −1,3 / +27,2 / +10,4 / +3,4 % (chỉ 87 lệnh).
Theo chiều (30m std25 C, R ròng TB): BTC long +0,06 (n=118) · BTC short +0,10 (115) · ETH long +0,01 (84) · ETH short −0,02 (84) · SOL long +0,33 (102) · SOL short +0,20 (117).

## Cách đọc

- **Chiếu std-dev là cách đặt target duy nhất làm ICT tốt lên rõ rệt**, đúng như deck nói (−2…−2,5 là vùng chốt): tỉ lệ thắng giảm (19–33 %) nhưng R mỗi lệnh thắng lớn hơn. `erl_next` và `irl` cho tỉ lệ thắng cao hơn nhưng R ≈ 0 hoặc âm — target quá gần so với phí và stop.
- **Dòng ổn định nhất hiện có: ICT 30m, target −2,5, cấu hình C** (limit maker, hoà vốn +1R, lọc khung lớn 2H): +17,6 %/năm, sụt giảm −20 %, 82 % quý dương, 4/5 năm dương, long và short đều dương trên BTC/SOL. Vẫn nhạy với phí: cùng luật với phí taker (A) cháy hoặc âm ở 30m.
- 4H với std-dev có 76 % quý dương và sụt giảm nhỏ nhưng chỉ 87 lệnh trong 4 năm — chưa đủ mẫu.
- 2H là khung duy nhất std-dev làm xấu đi; không có lời giải thích từ sách, coi là nhiễu mẫu.
- Lưới thử: 6 target × 4 khung × 3 cấu hình; kết quả tốt nhất vẫn có rủi ro khớp quá mức. Tiêu chí ưu tiên là tỉ lệ quý dương và độ nhất quán theo năm, không phải tổng %.

## Việc tiếp theo nếu muốn dùng
`scripts/strategy-runner.py` lấy target từ `bt.P`/`setups()`; để pilot dùng std25 cần thêm `ict_target` vào `setups()` (hiện là `range`) và chạy lại parity. Chưa làm — chờ quyết định.
