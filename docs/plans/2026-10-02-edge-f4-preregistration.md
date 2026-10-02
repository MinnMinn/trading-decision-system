# Edge family F4 -- pre-registration (2026-10-02, committed BEFORE any run on real data)

Parent: owner request 2026-10-02 ("lưu lại 'Mô phỏng book 3 thành phần' như một base và thử nghiệm thêm nhiều biến thể với những
'thành phần độc lập'"; "tìm kiếm thêm phương pháp mới ... Pass FTMO bằng bất kỳ phương pháp nào đã kiểm chứng"). Purpose: find
components that are INDEPENDENT of the current book (H7 gold, E5 FVG gold / US500) so the FTMO time-to-pass shortens without
raising per-trade risk. Code: `scripts/research/edge_f4.py` (machinery from `edge_census.py` / `edge_f3.py`, unchanged); tests:
`scripts/tests/test_edge_f4.py` (synthetic bars only).

## 1. Hypotheses (published, method-agnostic effects; none measured in this repository before)

| id | rule | hold |
|---|---|---|
| G1 | time-series momentum (Moskowitz-Ooi-Pedersen): sign of the 60-dense-day return at the close of day d's second-to-last bar | open of d's last bar -> close of the next server day's last bar (overnight, swap paid) |
| G3 | F3's H7 unchanged, on the allowlisted CFDs F3 did not test (XAGUSD, FRA40, AUS200) | server day |
| G4 | first close beyond the previous ISO week's high (low) when the 20-day momentum has the same sign | server day |
| G5 | NR7 (Crabel): yesterday's range is the narrowest of the last 7 dense days -> first close beyond yesterday's range, either side | server day |
| G7 | turn of the month (Lakonishok-Smidt): long on the last weekday of a month and the first three of the next (indices only) | first -> last bar of the day |
| G9 | volatility breakout (Williams/Crabel): first close beyond day open +/- 0.5 x the previous dense day's range | server day |

Point-in-time: every signal uses previous days' density only (`prev_dense`), previous dense days' prices, and bars up to the
signal bar's close; entry at the next bar's open. A signal on a day's LAST bar is not an event (its next bar is the next day).
G1's exit-day density is an outcome-side data filter (disclosed). G7 uses the published trading calendar (tomorrow's month).
G1 cost = relative spread round trip + the broker's CURRENT swap points scaled by entry / price_ref (history's swap rates are not
recorded -- disclosed; a long-run swap regime change is a known limitation).

## 2. Universe and family

All eight allowlisted CFDs: XAUUSD, XAGUSD, US500, US30, USTEC, DE40, FRA40, AUS200. FAMILY = 41 tests
(G1 x 8, G3 x 3, G4 x 8, G5 x 8, G7 x 6 indices, G9 x 8).

## 3. Three reads, each once -- identical to F3 (docs/plans/2026-10-02-edge-f3-preregistration.md §3)

DISCOVERY (first 60 % of dense development days; BH q = 0.10 over the 41 two-sided p-values, net > 0 bp; direction = sign of the
mean excess z, except G7 which is long-only and never flipped) -> CONFIRMATION (last 40 %; one-sided p < 0.05, net > 0, net at p90
spread > 0) -> EXPOSED (2024-03-01 -> end of data; one-sided p < 0.10, net > 0). Placebo: intraday = same period, same time of
day, to the end of the day; overnight (G1) = the same open-of-last-bar -> next-day-close construction on every eligible day of the
period. Zero survivors is a valid result.

## 4. After the reads (design, not selection)

Survivors become candidate book components. The baseline is the 3-component book `all_three|0.01`
(docs/architecture/book-baseline.json). A variant book is compared with the baseline on the common span by P1 pass rate, fail
rate, median days to pass, and the daily-P&L correlation of each new component with the baseline book. Survivors go to the
forward stage (docs/plans/2026-10-02-edge-followup-preregistration.md §4) before any real-money consideration.
