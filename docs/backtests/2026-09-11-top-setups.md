> **Superseded 2026-09-13.** The ICT figures here were produced by the legacy in-file rules, replaced by the live scanner (`docs/plans/2026-09-13-unify-backtest-with-live-rules.md`). Wyckoff / COMBINED / PARTIAL figures are unaffected.

# Setup theo khung — scalping / day / swing — mỗi thị trường — 2026-09-11

_`scripts/rank-setups.py --horizons`. Quyết định người dùng 2026-09-11: mỗi thị trường chạy đủ 3 khung, kể cả khi lợi thế backtest yếu hoặc âm. Trong mỗi khung, luật tốt nhất theo cùng tiêu chí (không cháy → quý dương → năm dương → quý tệ nhất). Dòng âm được in nghiêng; scalping 5m/15m bị phí và trượt giá ăn nhiều nhất._

## CRYPTO

| Khung | TF | Luật | Target | Cấu hình | Lệnh | Vốn cuối ($10k) | %/năm | Sụt giảm | Quý dương | Quý tệ nhất | Ổn định | Năm dương (từng năm %) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| scalping | 15m | ICT | std2 | B | 3081 | $15,608 | +16.0% | −66.3% | 62% | -50.0% | +0.91 | 2/4 (+3 / -40 / +228 / -24) |
| day | 30m | ICT | std25 | C | 620 | $19,087 | +17.6% | −19.8% | 82% | -17.2% | +1.91 | 4/5 (+12 / -0 / +10 / +15 / +34) |
| swing | 4H | ICT | std4 | A | 87 | $15,053 | +10.7% | −8.2% | 76% | -5.1% | +2.40 | 4/5 (+3 / +1 / +29 / -0 / +11) |

## CFD

| Khung | TF | Luật | Target | Cấu hình | Lệnh | Vốn cuối ($10k) | %/năm | Sụt giảm | Quý dương | Quý tệ nhất | Ổn định | Năm dương (từng năm %) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| *scalping* | 5m | ICT | range | C | 63 | $7,394 | -78.8% | −27.1% | 0% | -26.1% | +0.00 | 0/1 (-26) |
| day | 1H | ICT | std2 | C | 129 | $12,724 | +10.6% | −17.3% | 70% | -8.4% | +1.11 | 3/3 (+0 / +14 / +11) |
| *swing* | 4H | COMBINED | border | A | 26 | $9,807 | -0.8% | −9.8% | 60% | -4.9% | -0.20 | 1/3 (+7 / -4 / -4) |