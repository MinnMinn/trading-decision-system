# Setup theo khung — scalping / day / swing — mỗi thị trường — xếp trên 12 tháng gần nhất — 2026-09-12

_`scripts/rank-setups.py --horizons`. Quyết định người dùng 2026-09-11: mỗi thị trường chạy đủ 3 khung, kể cả khi lợi thế backtest yếu hoặc âm. Trong mỗi khung, luật tốt nhất theo cùng tiêu chí (không cháy → quý dương → năm dương → quý tệ nhất). Dòng âm được in nghiêng; scalping 5m/15m bị phí và trượt giá ăn nhiều nhất._

## CRYPTO

| Khung | TF | Luật | Target | Cấu hình | Lệnh | Vốn cuối ($10k) | %/năm | Sụt giảm | Quý dương | Quý tệ nhất | Ổn định | Năm dương (từng năm %) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| scalping | 5m | WYCKOFF-BOOK | border | B | 386 | $12,132 | +21.3% | −23.2% | 60% | -13.5% | 386 · +21.3%/năm · 60% quý dương · 1/2 năm |
| day | 30m | ICT | std4 | B | 437 | $15,136 | +51.4% | −29.5% | 80% | -5.5% | 1602 · +32.3%/năm · 53% quý dương · 3/5 năm |
| swing | 4H | WYCKOFF | border | B | 262 | $12,395 | +23.9% | −20.2% | 60% | -6.2% | 1004 · +11.5%/năm · 53% quý dương · 4/5 năm |

## CFD

| Khung | TF | Luật | Target | Cấu hình | Lệnh | Vốn cuối ($10k) | %/năm | Sụt giảm | Quý dương | Quý tệ nhất | Ổn định | Năm dương (từng năm %) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| scalping | 15m | ICT | std4 | B | 32 | $10,729 | +43.6% | −11.2% | 100% | +7.3% | 32 · +43.6%/năm · 100% quý dương · 1/1 năm |
| *day* | 30m | ICT | std2 | B | 18 | $9,951 | -2.5% | −6.3% | 100% | +0.7% | 18 · -2.5%/năm · 100% quý dương · 1/1 năm |
| *swing* | 4H | WYCKOFF | border | C | 46 | $9,855 | -1.5% | −11.4% | 40% | -3.5% | 106 · +5.7%/năm · 60% quý dương · 2/3 năm |

