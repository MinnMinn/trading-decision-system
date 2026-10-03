# Crypto + CFD phase -- summary (2026-10-04)

Owner direction 2026-10-03: crypto and CFD first, forex parked; 1 % = the maximum loss at the stop; demo runs fvg-book v3
(H7 + G9 gold). Design: docs/plans/2026-10-03-crypto-cfd-design.md (13-agent workflow). Every family was pre-registered and
committed before its read, implemented under two adversarial reviewers, and read once per window, one commit per read.

## Tóm tắt (VI)

Ba hướng tốt nhất mà thiết kế tìm được cho crypto và CFD đều đã được test đúng quy trình, và **không hướng nào sống sót**:
xu hướng trong ngày trên crypto (luật H7/G9 của vàng) có tín hiệu thật nhưng lãi ròng ≈ 0 sau phí taker + funding giai
đoạn 2021-24; hệ xu hướng ngày đã công bố (Donchian ensemble) không có alpha so với giữ coin trên dữ liệu sau công bố
2025-26; hiệu ứng tái cân bằng cuối tháng trên chỉ số Mỹ đúng dấu nhưng thiếu power. Book thật duy nhất vẫn là xu hướng
vàng (v3), chậm. Thứ cản lớn nhất trên crypto là CHI PHÍ (taker 10-12 bp/vòng), không phải tín hiệu.

## 1. Results

| family | hypothesis | reads run | verdict |
|---|---|---|---|
| H7x | gold's H7 / G9 intraday trend on BTC / ETH / SOL perps (UTC day, realized funding) | discovery: both CANDIDATES (H7x excess z +0.101, p 0.016, net +39 bp; G9x z +0.107, p 0.0015, net +13 bp); confirmation 2021-07 -> 2024-02: neither confirms (z +0.053 / +0.062, net +0.2 / +0.05 bp) | closed; EXPOSED retired unread |
| C1 | Zarattini-Pagani-Barbon daily Donchian ensemble, perps, funded | discovery (source in-sample): alpha +9.5 %/yr, NW p 0.0385, placebo p 0.001, BH m=4 rejects nothing, regime-driven | not a candidate |
| C1b | one post-publication read of the frozen C1 book (second stage, disclosed, adversarially reviewed) | 2025-03-20 -> 2026-09-30: alpha +0.7 %/yr (90 % CI -7.3 .. +8.7), p 0.445, placebo p 0.245 | FAILED -> C1 closed |
| M1 | month-end pension-rebalancing pressure on US index CFDs (NBER w33554) | discovery 2018-01 -> 2021-08: every gamma has the source's sign (+7.5 .. +11.4 bp/day), T1 p 0.110, net +3.7 bp | not a candidate; closed (its later windows overlap F3 H1 / G7 reads) |

Audits: docs/audits/2026-10-03-edge-h7x-{discovery,confirmation}.json, 2026-10-04-edge-c1-discovery.json,
2026-10-04-edge-c1b.json, 2026-10-04-edge-m1-discovery.json.

## 2. What it means

- **Crypto intraday trend exists in excess terms, not in net terms.** The H7x signal has the same per-trade size as on gold
  (excess z ~0.10 in 2017-21, ~0.05 in 2021-24); a 12 bp taker round trip plus funding takes all of it after 2021. Execution
  cost is the binding constraint on crypto, as spread was on the FTMO CFDs.
- **A published crypto trend book showed no post-publication alpha** against simply holding the coins (2025-26), and its
  in-sample alpha came from a few months. Its 1 %-at-the-stop version cannot keep the 1 % cap on a crash day (worst day
  -1.63 %, 2025-10-10).
- **Month-end rebalancing** is a real, documented flow with the right sign here, too small to see at 44 episodes.
- The only robust edge in this repository remains intraday trend continuation on GOLD (fvg-book v3).

## 3. Open defects found along the way (not fixed here)

- `edge_census.Costs` looks the FTMO spread table up at the TRUE UTC hour, but the table buckets are server hour minus the
  export-time offset (UTC+3): in US standard time every cost leg in census / F2-F7 used the neighbouring hour's spread (M1
  [M1-A1] item 7). Small except near the daily break; a fix changes historical semantics, so it needs its own erratum.
- 1H FTMO files for US500 / USTEC / FRA40 carry a one-hour label shift on 2021-01-20 .. 2021-03-26 ([M1-A1] item 15).
- This machine's MT5 terminal exports a `DXY.cash` live series that is on no allowlist: `test_quality` fails here (environment).

## 4. Next (owner decisions, not run)

1. **FTMO (CFD):** A2 -- the vol-schedule lever on v3 made safe for the 1 % rule: size for gaps, or be flat across HIGH-impact
   releases. The second needs a point-in-time historical release calendar (payrolls, CPI, FOMC schedules), not in the repo.
2. **Crypto:** the only remaining lever is execution cost (maker fills at 0.02 % instead of taker 0.05 %). Kline data cannot
   model maker fills honestly (the E5 lesson): it would need trade-through rules on 1m data and a forward paper check of real
   fill rates before any claim.
3. **Forex** stays parked per the owner; if reopened, the first test is its daily correlation with the gold book.

## 5. Experiment budget of this phase

H7x 2 tests x 2 reads; C1 4 tests x 1 read; C1b 1 test x 1 read (a second stage after a failed gate); M1 5 tests x 1 read;
design workflow: unconditional statistics only. Windows never read: H7x exposed (retired), C1 confirmation, M1 confirmation /
exposed.
