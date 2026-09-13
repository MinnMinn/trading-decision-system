> **Superseded 2026-09-13.** The ICT figures here were produced by the legacy in-file rules, replaced by the live scanner (`docs/plans/2026-09-13-unify-backtest-with-live-rules.md`); see `docs/backtests/2026-09-13-live-rules-vs-legacy.md`. Wyckoff / COMBINED / PARTIAL figures are unaffected.

# Setup theo khung — scalping / day / swing — mỗi thị trường — xếp trên 12 tháng gần nhất — 2026-09-13

_`scripts/rank-setups.py --horizons`. Quyết định người dùng 2026-09-11 (mở rộng 2026-09-13): mỗi thị trường chạy đủ 3 khung cho MỖI luật chạy được (RUNNABLE — WYCKOFF, WYCKOFF-BOOK, ICT, COMBINED), kể cả khi lợi thế backtest yếu hoặc âm. Lý do: `strategy-runner.py`'s `allowed_methods()` chỉ cho phép các luật mà method-switch preset đang bật; chọn theo (khung, luật) thay vì chỉ theo khung đảm bảo mọi preset (dù chỉ bật một luật, ví dụ ICT-only) vẫn có đủ 3 khung, thay vì chỉ có khung mà luật đó tình cờ thắng khi so giữa các luật. Trong mỗi (khung, luật), cấu hình/target tốt nhất theo cùng tiêu chí (không cháy → quý dương → năm dương → quý tệ nhất) — dòng âm được in nghiêng; scalping 5m/15m bị phí và trượt giá ăn nhiều nhất. Một khung có thể không đủ lệnh cho MỘT luật cụ thể dù các luật khác ở cùng khung có đủ — dòng đó vẫn được in để việc thiếu setup luôn hiện rõ, không âm thầm giảm số lượng._

## CRYPTO

| Khung | TF | Luật | Target | Cấu hình | Lệnh | Vốn cuối ($10k) | %/năm | Sụt giảm | Quý dương | Quý tệ nhất | Ổn định | Năm dương (từng năm %) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| *scalping* | 15m | COMBINED | border | C | 186 | $9,646 | -3.5% | −22.7% | 40% | -8.9% | 509 · -0.9%/năm · 46% quý dương · 2/4 năm |
| scalping | 15m | ICT | std4 | B | 1064 | $16,693 | +66.9% | −44.4% | 40% | -13.8% | 3081 · +11.5%/năm · 46% quý dương · 3/4 năm |
| *scalping* | 5m | WYCKOFF | border | C | 981 | CHÁY 2025-10-04 | -90.0% | −91.2% | 0% | -80.0% | 981 · -89.9%/năm · 0% quý dương · 0/2 năm |
| scalping | 15m | WYCKOFF-BOOK | border | C | 44 | $10,856 | +8.6% | −10.8% | 60% | -7.9% | 114 · +2.2%/năm · 38% quý dương · 2/4 năm |
| day | 2H | COMBINED | border | A | 68 | $11,780 | +17.8% | −7.2% | 60% | -2.5% | 177 · +0.9%/năm · 47% quý dương · 2/5 năm |
| day | 2H | ICT | range | A | 179 | $13,267 | +32.7% | −19.4% | 80% | -12.1% | 464 · +7.2%/năm · 71% quý dương · 3/5 năm |
| *day* | 1H | WYCKOFF | border | C | 622 | $4,594 | -54.1% | −58.0% | 20% | -38.1% | 2416 · -30.4%/năm · 47% quý dương · 1/5 năm |
| day | 2H | WYCKOFF-BOOK | border | B | 56 | $12,284 | +22.8% | −5.1% | 80% | -1.8% | 164 · +5.7%/năm · 53% quý dương · 3/5 năm |
| swing | 4H | COMBINED | border | C | 20 | $10,156 | +1.6% | −2.2% | 40% | -1.0% | 49 · +2.2%/năm · 53% quý dương · 4/5 năm |
| swing | 4H | ICT | std25 | C | 27 | $11,119 | +11.2% | −3.6% | 80% | -1.0% | 72 · +3.9%/năm · 53% quý dương · 2/5 năm |
| swing | 1D | WYCKOFF | border | A | 155 | $11,938 | +19.4% | −22.8% | 80% | -21.1% | 398 · -6.0%/năm · 41% quý dương · 1/5 năm |
| swing | 4H | WYCKOFF-BOOK | border | B | 17 | $10,030 | +0.3% | −6.0% | 20% | -2.4% | 67 · +4.0%/năm · 44% quý dương · 3/5 năm |

## CFD

| Khung | TF | Luật | Target | Cấu hình | Lệnh | Vốn cuối ($10k) | %/năm | Sụt giảm | Quý dương | Quý tệ nhất | Ổn định | Năm dương (từng năm %) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| *scalping* | 5m | COMBINED | border | C | 24 | $8,706 | -50.9% | −14.2% | 0% | -12.9% | 24 · -50.9%/năm · 0% quý dương · 0/1 năm |
| scalping | 15m | ICT | std4 | B | 32 | $10,729 | +43.6% | −11.2% | 100% | +7.3% | 32 · +43.6%/năm · 100% quý dương · 1/1 năm |
| *scalping* | 15m | WYCKOFF | border | C | 93 | $8,494 | -56.8% | −24.4% | 0% | -15.1% | 93 · -56.8%/năm · 0% quý dương · 0/1 năm |
| scalping | — | WYCKOFF-BOOK | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| day | 2H | COMBINED | border | B | 24 | $10,607 | +6.1% | −3.7% | 40% | -1.4% | 60 · +0.6%/năm · 40% quý dương · 2/3 năm |
| *day* | 30m | ICT | std2 | B | 18 | $9,951 | -2.5% | −6.3% | 100% | +0.7% | 18 · -2.5%/năm · 100% quý dương · 1/1 năm |
| *day* | 2H | WYCKOFF | border | B | 496 | $8,130 | -18.7% | −44.8% | 40% | -19.8% | 1155 · -13.0%/năm · 40% quý dương · 1/3 năm |
| day | 1H | WYCKOFF-BOOK | border | B | 24 | $10,744 | +7.4% | −4.3% | 60% | -2.1% | 58 · +1.0%/năm · 50% quý dương · 2/3 năm |
| *swing* | 4H | COMBINED | border | B | 12 | $9,536 | -4.6% | −5.8% | 60% | -4.8% | 26 · -1.7%/năm · 50% quý dương · 1/3 năm |
| swing | 4H | ICT | std4 | B | 20 | $11,065 | +10.6% | −3.5% | 60% | -1.5% | 45 · +1.7%/năm · 44% quý dương · 1/3 năm |
| *swing* | 4H | WYCKOFF | border | C | 196 | $8,753 | -12.5% | −25.8% | 40% | -15.5% | 456 · +17.9%/năm · 80% quý dương · 2/3 năm |
| swing | 4H | WYCKOFF-BOOK | border | A | 9 | $10,733 | +7.3% | −2.3% | 40% | -1.1% | 21 · +3.6%/năm · 50% quý dương · 3/3 năm |