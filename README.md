# Trading

Hệ thống ra quyết định giao dịch chạy trong Claude Code: phân tích theo Wyckoff + ICT + Footprint + Heatmap, tự động hoá nền bằng launchd, và nhật ký để đo xem hệ thống có edge hay không.

**Người mới bắt đầu ở đây:** [`docs/GETTING-STARTED.md`](docs/GETTING-STARTED.md) — cài đặt, bật tắt, chuyển demo sang real, sự cố thường gặp.

| Cần gì | Đọc |
|---|---|
| Kiến trúc và mọi quyết định thiết kế | `docs/architecture/SYSTEM-DESIGN.md` |
| Bật tắt tự động hoá | `.claude/commands/automation.md` |
| Quy trình đọc thị trường hợp nhất | `knowledge/integrated/method.md` |
| Nguồn dữ liệu và trạng thái AVAILABLE / MOCK / STALE | `docs/architecture/data-sources.md` |
| Nhật ký lệnh | `trades/` |

Luật cứng ở mọi môi trường: chỉ những mã trong allowlist, tối đa 1% vốn mỗi lệnh.
