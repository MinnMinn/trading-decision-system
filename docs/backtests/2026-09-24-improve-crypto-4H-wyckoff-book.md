# Vòng lặp cải tiến có kiểm soát — WYCKOFF-BOOK crypto 4H — 2026-09-24-improve-crypto-4H-wyckoff-book

_`scripts/improve-loop.py` -- CLAUDE.md §41 stages 1-4 (Trading Outcomes -> Failure Pattern -> Hypothesis -> Candidate) + §42 (mỗi ứng viên là một experiment.Record niêm phong dưới `docs/experiments/`). Không tự ý sửa pilot-selection.json / methods.json / trading-systems.json — stage 11 (§41) là quyết định của con người, không phải của script này._

**Baseline** (BTCUSDT, ETHUSDT, SOLUSDT, ASTERUSDT, VIRTUALUSDT, SUIUSDT, TAOUSDT, RENDERUSDT, ONDOUSDT, 2022-09-05 → 2026-09-12): n=41, expectancy=0.1527317073170732, PF=1.1925761909155208, max DD=12.8%, failed_by=—, refused={'news': 0, 'session': 41}

## Cụm lỗi lặp lại (loss clusters)
_min_size=3 · nhóm theo ['method', 'session', 'vol_type', 'via'] · 1 nhóm dưới ngưỡng (không tính là cụm)._

- `{'method': 'WYCKOFF-BOOK', 'session': 'off', 'vol_type': 'None', 'via': 'None'}` — n=24, states=['LOSS']
- `{'method': 'WYCKOFF-BOOK', 'session': 'london', 'vol_type': 'None', 'via': 'None'}` — n=5, states=['LOSS']

## Ứng viên đã chạy (xếp hạng theo `--objective`)

1. `method=WYCKOFF-BOOK` — n=0, expectancy=None, PF=None, DD=0.0%, failed_by=—, refused={'news': 0, 'session': 0} — record: `docs\experiments\2026-09-24-improve-crypto-4H-wyckoff-book-method-WYCKOFF-BOOK.json`
   - lý do: 1H WYCKOFF-BOOK B->C (HTF on) is exp -0.12R/dd 19.69% -> +0.62R/dd 7.17%, a PASS. Phase-D BU/LPS entries are the late, low-cause leg of the book engine (advance.md 2.7.4) and are dropped so the cause/effect target has room to pay for the trade.
2. `session=london` — n=0, expectancy=None, PF=None, DD=0.0%, failed_by=—, refused={'news': 0, 'session': 41} — record: `docs\experiments\2026-09-24-improve-crypto-4H-wyckoff-book-session-london.json`
   - lý do: if the cluster keys on london rather than asia the thin-liquidity explanation does not apply, so this is not a pure session cut but a session cut plus a higher planned-R floor: each loss costs 1.2-1.9R net of fee (backtest-methods.py fee_R = 2*fee_pct/dist), so the ~8-loss budget a 10% cap allows must buy bigger winners.

### Vượt trội hơn baseline (outperformers)
Không có ứng viên nào vượt baseline trên `expectancy` với n ≥ 20.

### Không có ứng viên khai báo
Mọi cụm đều khớp ít nhất một ứng viên đã khai báo.

---
**Con người quyết định (§41 stage 11).** Báo cáo này chỉ là bằng chứng: mọi bản ghi experiment ở trên đều `decision: PENDING`. Không ứng viên nào được tự động áp dụng; việc đưa một ứng viên vào `pilot-selection.json` / `methods.json` / `trading-systems.json` là một sửa đổi registry do một người thực hiện sau khi đọc báo cáo này, không phải hành động của `scripts/improve-loop.py`.
