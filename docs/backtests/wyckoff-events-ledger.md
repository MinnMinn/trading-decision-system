> **Superseded 2026-09-13.** The ICT figures here were produced by the legacy in-file rules, replaced by the live scanner (`docs/plans/2026-09-13-unify-backtest-with-live-rules.md`); see `docs/backtests/2026-09-13-live-rules-vs-legacy.md`. Wyckoff / COMBINED / PARTIAL figures are unaffected.

# Sổ sự kiện Wyckoff của phân tích đầy đủ — đo 2026-09-11

_`scripts/event-ledger.py measure`. Sự kiện được ghi lần đầu khi xuất hiện trong `data/live/narrative/*.json` (không nhìn trước), kết quả đo từ nến lưu. Entry = nến đóng lại trong TR sau sự kiện, stop dưới/trên cực trị sự kiện, target = biên đối diện TR mà phân tích vẽ, hoà vốn +1R, hạn H nến._

Tổng sự kiện ghi: 34 · sự kiện đảo chiều (Spring/Shakeout/UT/UTAD): 2 · đã có kết quả: 0 · đang chờ: 1


| Style | Mã | Khung | Thời điểm | Sự kiện | Pha | Cấu trúc | Chiều | Entry | Stop | Target | R kế hoạch | ICT xác nhận | Kết quả | R |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| daytrade | BTCUSDT | 15m | 2026-09-10T23:15:00Z | Spring 76,464 · KL 1.47x | C | tái tích lũy | long | 76734.29 | 76425.768 | 77424.98 | 2.24 | không | pending | 1.45 |
| gold | XAUUSD | 15m | 2026-09-10T06:00:00Z | UT 4,434.62 · KL 1.00× | None | chưa xác lập | — | — | — | — | — | — | no_entry (no timeframe / not a reversal event / no trading range) | — |