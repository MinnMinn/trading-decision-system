# Setup theo khung — scalping / day / swing — mỗi thị trường — xếp trên 12 tháng gần nhất — 2026-09-13

_`scripts/rank-setups.py --horizons`. Quyết định người dùng 2026-09-11 (mở rộng 2026-09-13): mỗi thị trường chạy đủ 3 khung cho MỖI luật chạy được (RUNNABLE — WYCKOFF, WYCKOFF-BOOK, ICT, COMBINED). Sửa 2026-09-13 (quyết định người dùng): một ô CHỈ được lấp bởi luật có ≥ 3 tháng dữ liệu, không cháy, VÀ có lãi — không ai qua thì **bỏ trống ô**, không lấp bằng đứa đỡ tệ nhất. Trước đó ô được lấp kể cả khi mọi ứng viên đều lỗ, và lần xếp hạng 2026-09-13 đã chọn một luật CFD kết thúc ở $988 trên vốn $10.000. Lý do: `strategy-runner.py`'s `allowed_methods()` chỉ cho phép các luật mà method-switch preset đang bật; chọn theo (khung, luật) thay vì chỉ theo khung đảm bảo mọi preset (dù chỉ bật một luật, ví dụ ICT-only) vẫn có đủ 3 khung, thay vì chỉ có khung mà luật đó tình cờ thắng khi so giữa các luật. Trong mỗi (khung, luật), cấu hình/target tốt nhất theo cùng tiêu chí (không cháy → quý dương → năm dương → quý tệ nhất) — dòng âm được in nghiêng; scalping 5m/15m bị phí và trượt giá ăn nhiều nhất. Một khung có thể không đủ lệnh cho MỘT luật cụ thể dù các luật khác ở cùng khung có đủ — dòng đó vẫn được in để việc thiếu setup luôn hiện rõ, không âm thầm giảm số lượng._

## CRYPTO

| Khung | TF | Luật | Target | Cấu hình | Lệnh | Vốn cuối ($10k) | %/năm | Sụt giảm | Quý dương | Quý tệ nhất | Ổn định | Năm dương (từng năm %) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| scalping | 15m | COMBINED | border | B | 104 | $15,251 | +52.5% | −33.6% | 80% | -25.7% | 348 · +17.8%/năm · 54% quý dương · 2/4 năm |
| scalping | 15m | ICT | live | A | 32 | $19,259 | +92.6% | −22.9% | 60% | -18.0% | 85 · +36.9%/năm · 54% quý dương · 4/4 năm |
| scalping | — | WYCKOFF | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| scalping | 15m | WYCKOFF-BOOK | border | C | 21 | $10,072 | +0.7% | −22.0% | 20% | -10.2% | 49 · +2.4%/năm · 31% quý dương · 3/4 năm |
| day | 1H | COMBINED | border | A | 18 | $12,103 | +21.0% | −13.3% | 60% | -10.5% | 66 · -3.4%/năm · 29% quý dương · 1/5 năm |
| day | — | ICT | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| day | — | WYCKOFF | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| day | — | WYCKOFF-BOOK | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| swing | — | COMBINED | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| swing | — | ICT | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| swing | 4H | WYCKOFF | border | C | 122 | $13,367 | +33.7% | −33.4% | 60% | -28.6% | 463 · -12.1%/năm · 41% quý dương · 1/5 năm |
| swing | — | WYCKOFF-BOOK | — | — | — | không đủ dữ liệu / lệnh | | | | | | |

## CFD

| Khung | TF | Luật | Target | Cấu hình | Lệnh | Vốn cuối ($10k) | %/năm | Sụt giảm | Quý dương | Quý tệ nhất | Ổn định | Năm dương (từng năm %) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| scalping | — | COMBINED | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| scalping | — | ICT | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| scalping | — | WYCKOFF | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| scalping | — | WYCKOFF-BOOK | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| day | — | COMBINED | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| day | — | ICT | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| day | — | WYCKOFF | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| day | — | WYCKOFF-BOOK | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| swing | — | COMBINED | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| swing | — | ICT | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| swing | 4H | WYCKOFF | border | A | 200 | $13,266 | +32.7% | −49.7% | 60% | -22.5% | 459 · -22.2%/năm · 50% quý dương · 2/3 năm |
| swing | — | WYCKOFF-BOOK | — | — | — | không đủ dữ liệu / lệnh | | | | | | |

