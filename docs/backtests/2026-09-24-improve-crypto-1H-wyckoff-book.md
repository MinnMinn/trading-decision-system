# Vòng lặp cải tiến có kiểm soát — WYCKOFF-BOOK crypto 1H — 2026-09-24-improve-crypto-1H-wyckoff-book

_`scripts/improve-loop.py` -- CLAUDE.md §41 stages 1-4 (Trading Outcomes -> Failure Pattern -> Hypothesis -> Candidate) + §42 (mỗi ứng viên là một experiment.Record niêm phong dưới `docs/experiments/`). Không tự ý sửa pilot-selection.json / methods.json / trading-systems.json — stage 11 (§41) là quyết định của con người, không phải của script này._

**Baseline** (BTCUSDT, ETHUSDT, SOLUSDT, ASTERUSDT, VIRTUALUSDT, SUIUSDT, TAOUSDT, RENDERUSDT, ONDOUSDT, 2022-09-13 → 2026-09-13): n=154, expectancy=-0.23601298701298704, PF=0.74331558355344, max DD=35.1%, failed_by=—, refused={'news': 0, 'session': 131}

## Cụm lỗi lặp lại (loss clusters)
_min_size=3 · nhóm theo ['method', 'session', 'vol_type', 'via'] · 3 nhóm dưới ngưỡng (không tính là cụm)._

- `{'method': 'WYCKOFF-BOOK', 'session': 'off', 'vol_type': 'None', 'via': 'None'}` — n=87, states=['LOSS']
- `{'method': 'WYCKOFF-BOOK', 'session': 'asia', 'vol_type': 'None', 'via': 'None'}` — n=12, states=['LOSS']
- `{'method': 'WYCKOFF-BOOK', 'session': 'london', 'vol_type': 'None', 'via': 'None'}` — n=10, states=['LOSS']
- `{'method': 'WYCKOFF-BOOK', 'session': 'ny_am', 'vol_type': 'None', 'via': 'None'}` — n=9, states=['LOSS']
- `{'method': 'WYCKOFF-BOOK', 'session': 'ny_pm', 'vol_type': 'None', 'via': 'None'}` — n=3, states=['LOSS']

## Ứng viên đã chạy (xếp hạng theo `--objective`)

1. `session=asia` — n=30, expectancy=-0.11243333333333336, PF=0.8572637637002243, DD=10.5%, failed_by=—, refused={'news': 0, 'session': 124} — record: `docs\experiments\2026-09-24-improve-crypto-1H-wyckoff-book-session-asia.json`
   - lý do: if a repeated LOSS cluster keys on the asia session, the declared candidate excludes it -- the thinnest-liquidity window for the crypto/CFD instruments this platform trades -- and keeps the other three.
2. `session=london` — n=12, expectancy=-0.37175, PF=0.5308654958460406, DD=4.5%, failed_by=—, refused={'news': 0, 'session': 142} — record: `docs\experiments\2026-09-24-improve-crypto-1H-wyckoff-book-session-london.json`
   - lý do: if the cluster keys on london rather than asia the thin-liquidity explanation does not apply, so this is not a pure session cut but a session cut plus a higher planned-R floor: each loss costs 1.2-1.9R net of fee (backtest-methods.py fee_R = 2*fee_pct/dist), so the ~8-loss budget a 10% cap allows must buy bigger winners.
3. `session=ny_pm` — n=23, expectancy=-0.47439130434782606, PF=0.4599316933128743, DD=10.6%, failed_by=—, refused={'news': 0, 'session': 131} — record: `docs\experiments\2026-09-24-improve-crypto-1H-wyckoff-book-session-ny_pm.json`
   - lý do: ny_pm is the post-settlement, thinning half of the US day for XAUUSD/XAGUSD; a repeated loss cluster keyed on it is a candidate for keeping only the two windows that carry the CFD session's real participation (docs/architecture/sessions.json).
4. `method=WYCKOFF-BOOK` — n=1, expectancy=-1.05, PF=0.0, DD=1.1%, failed_by=—, refused={'news': 0, 'session': 0} — record: `docs\experiments\2026-09-24-improve-crypto-1H-wyckoff-book-method-WYCKOFF-BOOK.json`
   - lý do: 1H WYCKOFF-BOOK B->C (HTF on) is exp -0.12R/dd 19.69% -> +0.62R/dd 7.17%, a PASS. Phase-D BU/LPS entries are the late, low-cause leg of the book engine (advance.md 2.7.4) and are dropped so the cause/effect target has room to pay for the trade.

### Vượt trội hơn baseline (outperformers)
- `session=asia` — record: `docs\experiments\2026-09-24-improve-crypto-1H-wyckoff-book-session-asia.json`

### Không có ứng viên khai báo
Mọi cụm đều khớp ít nhất một ứng viên đã khai báo.

---
**Con người quyết định (§41 stage 11).** Báo cáo này chỉ là bằng chứng: mọi bản ghi experiment ở trên đều `decision: PENDING`. Không ứng viên nào được tự động áp dụng; việc đưa một ứng viên vào `pilot-selection.json` / `methods.json` / `trading-systems.json` là một sửa đổi registry do một người thực hiện sau khi đọc báo cáo này, không phải hành động của `scripts/improve-loop.py`.
