> **Superseded 2026-09-13.** The ICT figures here were produced by the legacy in-file rules, replaced by the live scanner (`docs/plans/2026-09-13-unify-backtest-with-live-rules.md`); see `docs/backtests/2026-09-13-live-rules-vs-legacy.md`. Wyckoff / COMBINED / PARTIAL figures are unaffected.

# Top 5 setup mỗi thị trường — hiệu quả 12 tháng gần nhất — 2026-09-11

_`scripts/rank-setups.py --window 1y` (được `/automation on setup top N` gọi). Xếp theo cửa sổ 365 ngày cuối của mỗi dòng: không cháy → tỉ lệ quý dương trong năm → lợi nhuận năm → quý tệ nhất; mỗi (khung, luật) giữ một target và cấu hình. Cột cuối là toàn bộ lịch sử để đối chiếu. Cả long lẫn short; số là proxy code trên lịch sử nghiên cứu (CFD = futures Yahoo)._

## CRYPTO — top 5 (≥ 30 lệnh trong 12 tháng; 420 dòng xét)

| Khung | Luật | Target | Cấu hình | Lệnh 1 năm | Vốn cuối 1 năm ($10k) | % 1 năm | Sụt giảm 1 năm | Quý dương | Quý tệ nhất | Toàn lịch sử |
|---|---|---|---|---|---|---|---|---|---|---|
| 30m | ICT | std4 | B | 437 | $15,136 | +51.4% | −29.5% | 80% | -5.5% | 1602 · +32.3%/năm · 53% quý dương · 3/5 năm |
| 2H | ICT | range | A | 49 | $11,821 | +18.2% | −11.9% | 80% | -7.1% | 220 · +5.5%/năm · 71% quý dương · 3/5 năm |
| 1H | ICT | std4 | B | 167 | $11,050 | +10.5% | −22.8% | 80% | -2.2% | 606 · +5.4%/năm · 41% quý dương · 4/5 năm |
| 4H | WYCKOFF | border | B | 262 | $12,395 | +23.9% | −20.2% | 60% | -6.2% | 1004 · +11.5%/năm · 53% quý dương · 4/5 năm |
| 5m | WYCKOFF-BOOK | border | B | 386 | $12,132 | +21.3% | −23.2% | 60% | -13.5% | 386 · +21.3%/năm · 60% quý dương · 1/2 năm |

## CFD — top 5 (≥ 15 lệnh trong 12 tháng; 420 dòng xét)

| Khung | Luật | Target | Cấu hình | Lệnh 1 năm | Vốn cuối 1 năm ($10k) | % 1 năm | Sụt giảm 1 năm | Quý dương | Quý tệ nhất | Toàn lịch sử |
|---|---|---|---|---|---|---|---|---|---|---|
| 15m | ICT | std4 | C | 15 | $11,817 | +135.9% | −4.9% | 100% | +18.2% | 15 · +135.9%/năm · 100% quý dương · 1/1 năm |
| 30m | ICT | std2 | B | 18 | $9,951 | -2.5% | −6.3% | 100% | +0.7% | 18 · -2.5%/năm · 100% quý dương · 1/1 năm |
| 4H | WYCKOFF | border | C | 46 | $9,855 | -1.5% | −11.4% | 40% | -3.5% | 106 · +5.7%/năm · 60% quý dương · 2/3 năm |
| 1H | ICT | std25 | B | 19 | $10,957 | +9.6% | −6.5% | 20% | -4.3% | 61 · +7.9%/năm · 50% quý dương · 2/3 năm |
| 2H | WYCKOFF | border | B | 111 | $8,319 | -16.8% | −18.8% | 20% | -10.6% | 264 · -14.7%/năm · 40% quý dương · 0/3 năm |