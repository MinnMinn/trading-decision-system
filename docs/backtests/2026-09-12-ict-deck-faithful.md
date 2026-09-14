> **Superseded 2026-09-13.** The ICT figures here were produced by the legacy in-file rules, replaced by the live scanner (`docs/plans/2026-09-13-unify-backtest-with-live-rules.md`). Wyckoff / COMBINED / PARTIAL figures are unaffected.

# ICT theo đúng deck — ba công tắc mới của `backtest-methods.py`, đo 2026-09-12

_Cùng cấu hình với setup pilot đang chọn (`docs/architecture/pilot-top5.json`): target `std4`, quản lý `be`, phí 0.02%/chiều, không lọc khung lớn, long + short. Nến ở `data/history/`. Số là của proxy bằng code, không phải phân tích đầy đủ. Bản gốc từng biến thể: `docs/backtests/2026-09-12-ict-deck-faithful/`._

Ba công tắc, đều **tắt mặc định** (luật pilot không đổi cho tới khi setup bật chúng bằng khoá cùng tên trong `pilot-top5.json`):

| Cờ | Luật deck | Nguồn |
|---|---|---|
| `--ict-disp` / `ict_disp` | nến phá swing phải là nến displacement: thân ≥ 0.6 biên độ nến và biên độ ≥ 1.2× trung vị 48 nến trước (ngưỡng = tham số dự án `analysis-params.json → project_defined.ict.displacement`) | `knowledge/04 §2.16` |
| `--ict-pd` / `ict_pd` | long chỉ khi nến quét đóng ở nửa discount của range R nến, short ở nửa premium | `knowledge/04 §3.4 R13` |
| `--std-origin highest` / `std_origin` | mốc 0 của phép chiếu STD = đỉnh cao nhất (long) / đáy thấp nhất (short) giữa pivot trước cú quét và cú quét — "the previous high which made the highest high" — thay vì pivot 3 nến gần nhất | `Model11 p20`, `knowledge/06 §2.1.5` |

## Crypto (BTCUSDT, ETHUSDT, SOLUSDT; 2022-09 → 2026-09-11)

| Khung | Biến thể | Lệnh | Thắng | R TB | ΣR | PF | %/năm | Sụt giảm tối đa |
|---|---|---|---|---|---|---|---|---|
| 30m | gốc | 1602 | 15% | +0.09 | +142.1 | 1.17 | +32.3% | −38.7% |
| 30m | chỉ displacement | 969 | 17% | +0.12 | +114.4 | 1.23 | +27.1% | −26.8% |
| 30m | chỉ P/D | 1157 | 16% | +0.13 | +155.6 | 1.27 | +39.4% | −34.3% |
| 30m | chỉ gốc STD highest | 1602 | 15% | +0.09 | +148.0 | 1.18 | +34.0% | −38.7% |
| 30m | cả ba | 683 | 18% | +0.15 | +100.8 | 1.29 | +24.4% | −28.3% |
| 1H | gốc | 606 | 16% | +0.05 | +32.2 | 1.10 | +5.4% | −36.5% |
| 1H | chỉ displacement | 332 | 15% | +0.01 | +4.4 | 1.03 | −0.2% | −26.0% |
| 1H | chỉ P/D | 447 | 17% | +0.05 | +22.9 | 1.10 | +3.7% | −30.9% |
| 1H | chỉ gốc STD highest | 606 | 16% | +0.06 | +34.3 | 1.11 | +6.0% | −36.2% |
| 1H | cả ba | 237 | 17% | +0.05 | +11.5 | 1.10 | +2.0% | −25.9% |
| 4H | gốc | 87 | 33% | +0.43 | +37.3 | 2.10 | +9.3% | −11.1% |
| 4H | chỉ displacement | 49 | 37% | +0.57 | +28.0 | 2.36 | +6.9% | −5.5% |
| 4H | chỉ P/D | 71 | 35% | +0.44 | +31.4 | 2.22 | +7.8% | −8.7% |
| 4H | chỉ gốc STD highest | 87 | 33% | +0.43 | +37.3 | 2.10 | +9.3% | −11.1% |
| 4H | cả ba | 39 | 36% | +0.41 | +15.9 | 1.96 | +3.9% | −8.5% |

## CFD (XAUUSD; mẫu rất nhỏ)

| Khung | Biến thể | Lệnh | Thắng | R TB | ΣR | PF | %/năm | Sụt giảm tối đa |
|---|---|---|---|---|---|---|---|---|
| 15m | gốc | 32 | 19% | +0.24 | +7.8 | 1.42 | +43.6% | −11.2% |
| 15m | cả ba | 9 | 11% | −0.25 | −2.3 | 0.50 | −11.3% | −3.2% |
| 30m | gốc | 18 | 17% | −0.08 | −1.4 | 0.87 | −7.9% | −7.3% |
| 30m | cả ba | 5 | 20% | +0.08 | +0.4 | 1.17 | +1.9% | −2.3% |
| 1H | gốc | 61 | 20% | +0.36 | +21.9 | 1.71 | +8.8% | −12.6% |
| 1H | cả ba | 30 | 27% | +0.50 | +15.1 | 2.10 | +6.1% | −5.5% |

## Đọc số

- **Gốc STD `highest`** không giảm gì và tăng nhẹ ΣR ở 30m/1H → đây là định nghĩa của deck, có thể bật không mất gì.
- **P/D gate** bỏ ~30% lệnh, tăng PF ở cả 3 khung, giảm drawdown; %/năm 30m tăng, 1H và 4H giảm nhẹ.
- **Displacement** bỏ ~40% lệnh, giảm drawdown mạnh nhất (30m −38.7% → −26.8%, 4H −11.1% → −5.5%) nhưng kéo 1H về ~0 %/năm. Ngưỡng 0.6 / 1.2 là tham số dự án, chưa dò.
- **Cả ba** cho đường vốn êm hơn nhưng lợi nhuận tuyệt đối thấp hơn ở mọi khung crypto. Với 1% rủi ro/lệnh, so sánh đúng là **lợi nhuận trên drawdown**: 30m gốc 0.83, cả ba 0.86; 4H gốc 0.84, cả ba 0.46.
- CFD: 9–30 lệnh, không kết luận được.

## Chưa quyết định

Bật cờ nào cho pilot là quyết định của người dùng (`/improve`): đổi luật đang chạy trên demo/testnet. Đề xuất: bật `std_origin: "highest"` và `ict_pd: true` cho setup 30m crypto; giữ `ict_disp` tắt cho tới khi dò ngưỡng bằng `/improve`.