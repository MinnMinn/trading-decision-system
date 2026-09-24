# Vòng lặp cải tiến có kiểm soát — ICT crypto 4H — 2026-09-24-improve-crypto-4H-ict

_`scripts/improve-loop.py` -- CLAUDE.md §41 stages 1-4 (Trading Outcomes -> Failure Pattern -> Hypothesis -> Candidate) + §42 (mỗi ứng viên là một experiment.Record niêm phong dưới `docs/experiments/`). Không tự ý sửa pilot-top20.json / methods.json / trading-systems.json — stage 11 (§41) là quyết định của con người, không phải của script này._

**Baseline** (BTCUSDT, ETHUSDT, SOLUSDT, ASTERUSDT, VIRTUALUSDT, SUIUSDT, TAOUSDT, RENDERUSDT, ONDOUSDT, 2022-09-05 → 2026-09-12): n=1, expectancy=-1.024, PF=0.0, max DD=1.0%, failed_by=—, refused={'news': 0, 'session': 0}

## Cụm lỗi lặp lại (loss clusters)
_min_size=3 · nhóm theo ['method', 'session', 'vol_type', 'via'] · 1 nhóm dưới ngưỡng (không tính là cụm)._

Không có cụm lỗi lặp lại nào đạt `min_size` trong baseline.

## Ứng viên đã chạy (xếp hạng theo `--objective`)

Không có cụm nào khớp một ứng viên đã khai báo trong `docs/architecture/improve-candidates.json`.

### Vượt trội hơn baseline (outperformers)
Không có ứng viên nào vượt baseline trên `expectancy` với n ≥ 20.

### Không có ứng viên khai báo
Mọi cụm đều khớp ít nhất một ứng viên đã khai báo.

---
**Con người quyết định (§41 stage 11).** Báo cáo này chỉ là bằng chứng: mọi bản ghi experiment ở trên đều `decision: PENDING`. Không ứng viên nào được tự động áp dụng; việc đưa một ứng viên vào `pilot-top20.json` / `methods.json` / `trading-systems.json` là một sửa đổi registry do một người thực hiện sau khi đọc báo cáo này, không phải hành động của `scripts/improve-loop.py`.
