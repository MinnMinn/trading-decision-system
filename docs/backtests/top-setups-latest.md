# Setup theo khung — scalping / day / swing — mỗi thị trường — xếp trên 12 tháng gần nhất — 2026-09-20

_`scripts/rank-setups.py --horizons`. Quyết định người dùng 2026-09-11 (mở rộng 2026-09-13): mỗi thị trường chạy đủ 3 khung cho MỖI luật chạy được (RUNNABLE — WYCKOFF-BOOK, ICT; WYCKOFF và COMBINED đã bị xoá 2026-09-19, xem docs/audits/2026-09-19-knowledge-fidelity.md finding 6). Sửa 2026-09-13 (quyết định người dùng): một ô CHỈ được lấp bởi luật có ≥ 3 tháng dữ liệu, không cháy, VÀ có lãi — không ai qua thì **bỏ trống ô**, không lấp bằng đứa đỡ tệ nhất. Trước đó ô được lấp kể cả khi mọi ứng viên đều lỗ, và lần xếp hạng 2026-09-13 đã chọn một luật CFD kết thúc ở $988 trên vốn $10.000. Lý do: `strategy-runner.py`'s `allowed_methods()` chỉ cho phép các luật mà method-switch preset đang bật; chọn theo (khung, luật) thay vì chỉ theo khung đảm bảo mọi preset (dù chỉ bật một luật, ví dụ ICT-only) vẫn có đủ 3 khung, thay vì chỉ có khung mà luật đó tình cờ thắng khi so giữa các luật. Trong mỗi (khung, luật), cấu hình/target tốt nhất theo cùng tiêu chí (không cháy → quý dương → năm dương → quý tệ nhất) — dòng âm được in nghiêng. Sửa tiếp 2026-09-13: mỗi khung chỉ ứng với MỘT timeframe — scalping 15m, day 1H, swing 4H — đúng như `automation.HORIZON_TF`; trước đó mỗi khung là một TẬP timeframe (kể cả 5m/30m/2H/1D) mà scanner không còn quét, nên có thể chọn ra setup không gì chạy được. Trong đó scalping 15m bị phí và trượt giá ăn nhiều nhất. Một khung có thể không đủ lệnh cho MỘT luật cụ thể dù các luật khác ở cùng khung có đủ — dòng đó vẫn được in để việc thiếu setup luôn hiện rõ, không âm thầm giảm số lượng._

## CRYPTO

| Khung | TF | Luật | Target | Cấu hình | Lệnh | Vốn cuối ($10k) | %/năm | Sụt giảm | Quý dương | Quý tệ nhất | Ổn định | Năm dương (từng năm %) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| scalping | 15m | ICT | v1 | B | 23 | $11,973 | +19.7% | −3.7% | 60% | -3.7% | 64 · +4.9%/năm · 38% quý dương · 3/4 năm |
| scalping | — | WYCKOFF-BOOK | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| day | — | ICT | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| day | — | WYCKOFF-BOOK | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| swing | — | ICT | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| swing | — | WYCKOFF-BOOK | — | — | — | không đủ dữ liệu / lệnh | | | | | | |

## CFD

| Khung | TF | Luật | Target | Cấu hình | Lệnh | Vốn cuối ($10k) | %/năm | Sụt giảm | Quý dương | Quý tệ nhất | Ổn định | Năm dương (từng năm %) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| scalping | — | ICT | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| scalping | 15m | WYCKOFF-BOOK | border | A | 27 | $10,002 | +0.0% | −6.7% | 40% | -4.3% | 184 · -1.2%/năm · 0% quý dương · 0/2 năm |
| day | — | ICT | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| day | 1H | WYCKOFF-BOOK | border | A | 15 | $10,379 | +3.8% | −7.4% | 40% | -3.3% | 162 · -0.5%/năm · 19% quý dương · 2/8 năm |
| swing | — | ICT | — | — | — | không đủ dữ liệu / lệnh | | | | | | |
| swing | — | WYCKOFF-BOOK | — | — | — | không đủ dữ liệu / lệnh | | | | | | |


_CLAUDE.md §38 — tính hợp lệ của nghiên cứu nguồn: **FLAGGED**._ Nguồn không HỢP LỆ hoàn toàn: `data/history/stability/cfd-ftmo-challenge-phase1.json` (FLAGGED), `data/history/stability/cfd-live.json` (FLAGGED), `data/history/stability/crypto-crypto-personal-v1.json` (FLAGGED), `data/history/stability/crypto-crypto-prop-discipline.json` (FLAGGED), `data/history/stability/crypto-live.json` (FLAGGED), `data/history/stability/crypto-pilot-binance-futures-testnet.json` (FLAGGED).
