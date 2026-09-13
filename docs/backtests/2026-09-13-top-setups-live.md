# Setup theo khung — scalping / day / swing — mỗi thị trường — xếp trên 12 tháng gần nhất — 2026-09-13

_`scripts/rank-setups.py --horizons`. Quyết định người dùng 2026-09-11 (mở rộng 2026-09-13): mỗi thị trường chạy đủ 3 khung cho MỖI luật chạy được (RUNNABLE — WYCKOFF, WYCKOFF-BOOK, ICT, COMBINED), kể cả khi lợi thế backtest yếu hoặc âm. Lý do: `strategy-runner.py`'s `allowed_methods()` chỉ cho phép các luật mà method-switch preset đang bật; chọn theo (khung, luật) thay vì chỉ theo khung đảm bảo mọi preset (dù chỉ bật một luật, ví dụ ICT-only) vẫn có đủ 3 khung, thay vì chỉ có khung mà luật đó tình cờ thắng khi so giữa các luật. Trong mỗi (khung, luật), cấu hình/target tốt nhất theo cùng tiêu chí (không cháy → quý dương → năm dương → quý tệ nhất) — dòng âm được in nghiêng; scalping 5m/15m bị phí và trượt giá ăn nhiều nhất. Một khung có thể không đủ lệnh cho MỘT luật cụ thể dù các luật khác ở cùng khung có đủ — dòng đó vẫn được in để việc thiếu setup luôn hiện rõ, không âm thầm giảm số lượng._

## CRYPTO

| Khung | TF | Luật | Target | Cấu hình | Lệnh | Vốn cuối ($10k) | %/năm | Sụt giảm | Quý dương | Quý tệ nhất | Ổn định | Năm dương (từng năm %) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| *scalping* | 15m | COMBINED | border | C | 186 | $9,646 | -3.5% | −22.7% | 40% | -8.9% | 509 · -0.9%/năm · 46% quý dương · 2/4 năm |
| scalping | 15m | ICT | live | A | 73 | $13,526 | +35.3% | −10.3% | 60% | -3.2% | 175 · +15.5%/năm · 46% quý dương · 4/4 năm |
| *scalping* | 15m | WYCKOFF | border | A | 896 | CHÁY 2026-01-12 | -90.0% | −90.0% | 0% | -77.7% | 771 · -53.7%/năm · 0% quý dương · 0/2 năm |
| scalping | 15m | WYCKOFF-BOOK | border | C | 44 | $10,856 | +8.6% | −10.8% | 60% | -7.9% | 114 · +2.2%/năm · 38% quý dương · 2/4 năm |
| *day* | 1H | COMBINED | border | A | 40 | $9,980 | -0.2% | −10.5% | 60% | -8.0% | 162 · -0.7%/năm · 47% quý dương · 2/5 năm |
| *day* | 1H | ICT | live | B | 16 | $9,728 | -2.7% | −4.8% | 20% | -2.9% | 59 · -0.2%/năm · 31% quý dương · 1/5 năm |
| *day* | 1H | WYCKOFF | border | C | 622 | $4,594 | -54.1% | −58.0% | 20% | -38.1% | 2416 · -30.4%/năm · 47% quý dương · 1/5 năm |
| *day* | 1H | WYCKOFF-BOOK | border | B | 30 | $9,121 | -8.8% | −9.5% | 0% | -4.2% | 124 · -3.7%/năm · 24% quý dương · 1/5 năm |
| *swing* | 4H | COMBINED | border | C | 7 | $9,684 | -3.2% | −4.0% | 25% | -2.9% | 23 · +0.7%/năm · 42% quý dương · 3/5 năm |
| swing | — | ICT | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| swing | 4H | WYCKOFF | border | B | 262 | $12,395 | +23.9% | −20.2% | 60% | -6.2% | 1004 · +11.5%/năm · 53% quý dương · 4/5 năm |
| swing | — | WYCKOFF-BOOK | — | — | — | không đủ dữ liệu / lệnh | | | | | | |

## CFD

| Khung | TF | Luật | Target | Cấu hình | Lệnh | Vốn cuối ($10k) | %/năm | Sụt giảm | Quý dương | Quý tệ nhất | Ổn định | Năm dương (từng năm %) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| scalping | — | COMBINED | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| scalping | — | ICT | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| *scalping* | 15m | WYCKOFF | border | C | 93 | $8,494 | -56.8% | −24.4% | 0% | -15.1% | 93 · -56.8%/năm · 0% quý dương · 0/1 năm |
| scalping | — | WYCKOFF-BOOK | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| *day* | 1H | COMBINED | border | C | 37 | $9,605 | -3.9% | −13.9% | 20% | -4.0% | 76 · +0.2%/năm · 50% quý dương · 2/3 năm |
| *day* | 1H | ICT | live | A | 15 | $9,804 | -2.0% | −5.3% | 40% | -5.0% | 36 · -2.2%/năm · 40% quý dương · 1/3 năm |
| *day* | 1H | WYCKOFF | border | B | 808 | $2,088 | -79.1% | −81.0% | 0% | -46.3% | 1032 · -61.9%/năm · 0% quý dương · 0/3 năm |
| day | 1H | WYCKOFF-BOOK | border | B | 24 | $10,744 | +7.4% | −4.3% | 60% | -2.1% | 58 · +1.0%/năm · 50% quý dương · 2/3 năm |
| *swing* | 4H | COMBINED | border | B | 12 | $9,536 | -4.6% | −5.8% | 60% | -4.8% | 26 · -1.7%/năm · 50% quý dương · 1/3 năm |
| swing | 4H | ICT | live | B | 6 | $10,022 | +0.2% | −1.0% | 60% | -1.0% | 14 · -1.3%/năm · 38% quý dương · 0/3 năm |
| *swing* | 4H | WYCKOFF | border | C | 196 | $8,753 | -12.5% | −25.8% | 40% | -15.5% | 456 · +17.9%/năm · 80% quý dương · 2/3 năm |
| swing | 4H | WYCKOFF-BOOK | border | A | 9 | $10,733 | +7.3% | −2.3% | 40% | -1.1% | 21 · +3.6%/năm · 50% quý dương · 3/3 năm |

