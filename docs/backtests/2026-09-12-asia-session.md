> **Superseded 2026-09-13.** The ICT figures here were produced by the legacy in-file rules, replaced by the live scanner (`docs/plans/2026-09-13-unify-backtest-with-live-rules.md`); see `docs/backtests/2026-09-13-live-rules-vs-legacy.md`. Wyckoff / COMBINED / PARTIAL figures are unaffected.

# Ranh giới phiên Á — đo hành vi thanh khoản của đỉnh/đáy phiên — 2026-09-12

_`scripts/asia-session-eval.py` trên nến 15m tại `data/history/`, 365 ngày cuối, chỉ ngày thường. Định nghĩa các chỉ số ở docstring của script. Điểm = trung bình(một phía, đảo chiều|quét) − 0.5 × tỉ lệ range phiên / range cả ngày._

## BTCUSDT — 2025-09-11 → 2026-09-11 (35041 nến)

| Cửa sổ | Phiên | Bị quét | Một phía | Cả hai | Đảo chiều \| quét | Range phiên / ngày (trung vị) | Điểm |
|---|---|---|---|---|---|---|---|
| tokyo_00_06 (Asia/Tokyo 00:00–06:00) | 261 | 94% | 70% | 24% | 25% | 54% | 0.205 |
| ny_20_00 (America/New_York 20:00–00:00) | 261 | 100% | 52% | 47% | 47% | 35% | 0.326 |
| utc_00_08 (UTC 00:00–08:00) | 261 | 98% | 65% | 33% | 33% | 49% | 0.249 |
| tokyo_09_15 (Asia/Tokyo 09:00–15:00) | 261 | 98% | 59% | 40% | 40% | 43% | 0.282 |
| sg_08_16 (Asia/Singapore 08:00–16:00) | 261 | 98% | 65% | 33% | 33% | 49% | 0.249 |

## ETHUSDT — 2025-09-11 → 2026-09-11 (35041 nến)

| Cửa sổ | Phiên | Bị quét | Một phía | Cả hai | Đảo chiều \| quét | Range phiên / ngày (trung vị) | Điểm |
|---|---|---|---|---|---|---|---|
| tokyo_00_06 (Asia/Tokyo 00:00–06:00) | 261 | 92% | 62% | 30% | 32% | 56% | 0.192 |
| ny_20_00 (America/New_York 20:00–00:00) | 261 | 100% | 54% | 45% | 45% | 36% | 0.315 |
| utc_00_08 (UTC 00:00–08:00) | 261 | 96% | 65% | 31% | 32% | 46% | 0.258 |
| tokyo_09_15 (Asia/Tokyo 09:00–15:00) | 261 | 98% | 60% | 38% | 39% | 42% | 0.284 |
| sg_08_16 (Asia/Singapore 08:00–16:00) | 261 | 96% | 65% | 31% | 32% | 46% | 0.258 |

## SOLUSDT — 2025-09-11 → 2026-09-11 (35041 nến)

| Cửa sổ | Phiên | Bị quét | Một phía | Cả hai | Đảo chiều \| quét | Range phiên / ngày (trung vị) | Điểm |
|---|---|---|---|---|---|---|---|
| tokyo_00_06 (Asia/Tokyo 00:00–06:00) | 261 | 95% | 66% | 28% | 30% | 57% | 0.196 |
| ny_20_00 (America/New_York 20:00–00:00) | 261 | 99% | 44% | 55% | 55% | 34% | 0.327 |
| utc_00_08 (UTC 00:00–08:00) | 261 | 96% | 56% | 40% | 41% | 47% | 0.253 |
| tokyo_09_15 (Asia/Tokyo 09:00–15:00) | 261 | 98% | 51% | 47% | 47% | 41% | 0.287 |
| sg_08_16 (Asia/Singapore 08:00–16:00) | 261 | 96% | 56% | 40% | 41% | 47% | 0.253 |

## XAUUSD — 2026-07-02 → 2026-09-11 (4526 nến)

| Cửa sổ | Phiên | Bị quét | Một phía | Cả hai | Đảo chiều \| quét | Range phiên / ngày (trung vị) | Điểm |
|---|---|---|---|---|---|---|---|
| tokyo_00_06 (Asia/Tokyo 00:00–06:00) | 49 | 100% | 55% | 45% | 45% | 45% | 0.276 |
| ny_20_00 (America/New_York 20:00–00:00) | 49 | 98% | 76% | 22% | 23% | 45% | 0.268 |
| utc_00_08 (UTC 00:00–08:00) | 50 | 96% | 84% | 12% | 12% | 52% | 0.220 |
| tokyo_09_15 (Asia/Tokyo 09:00–15:00) | 51 | 98% | 80% | 18% | 18% | 48% | 0.252 |
| sg_08_16 (Asia/Singapore 08:00–16:00) | 50 | 96% | 84% | 12% | 12% | 52% | 0.220 |

## Gộp mọi mã

| Cửa sổ | Phiên | Bị quét | Một phía | Cả hai | Đảo chiều \| quét | Range phiên / ngày | Điểm |
|---|---|---|---|---|---|---|---|
| tokyo_00_06 | 832 | 94% | 66% | 28% | 30% | 55% | 0.204 |
| ny_20_00 | 832 | 99% | 52% | 47% | 48% | 36% | 0.319 |
| utc_00_08 | 833 | 97% | 64% | 33% | 34% | 48% | 0.250 |
| tokyo_09_15 | 834 | 98% | 58% | 40% | 41% | 42% | 0.283 |
| sg_08_16 | 833 | 97% | 64% | 33% | 34% | 48% | 0.250 |

**Cửa sổ điểm cao nhất:** `ny_20_00` (0.319); hiện tại `tokyo_00_06` = 0.204.