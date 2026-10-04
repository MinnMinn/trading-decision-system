# Personal-account backtest -- design v2 (2026-10-04)

Owner 2026-10-04: "Ngoài thi quỹ FTMO, tao cũng muốn có kết quả back test cho tài khoản cá nhân ... Tại thời điểm thua hết tiền
thì setup bị đánh giá là cháy tài khoản và không phát sinh thêm giao dịch nào sau đó." (2026-09-18: "cháy tài khoản mới tính
là thua hẳn".) A personal account has no daily-loss limit, no target and no minimum days, and it ends when the money is gone.
v2 applies an adversarial review of v1 (12 findings, all applied). Scope: INTRADAY trade rows (`book_sim.trades`: flat
before the server rollover). Multi-day rows (the method engine) need swap, weekend gaps and another bootstrap first.

## 0. The finding that shapes everything: the minimum lot

FTMO-Demo XAUUSD: 0.01 lot = 1 oz (contract 100); XAGUSD: 0.01 lot = 50 oz (contract 5,000)
(data/history/costs/ftmo/symbolspec.*.json). Prices at the 2026-09-30 close: gold 4,156.44, silver 60.665. Median stops since
2024 (`book_sim.trades`, stop 2.0): H7 gold 155 bp, G9 gold 141 bp, G9 silver 292 bp; at stop 1.4 they are 0.7 of that.

Loss of ONE minimum lot at the median stop:

| setup | stop 2.0 (v3) | stop 1.4 (v4) |
|---|---|---|
| H7 gold | $64 | $45 |
| G9 gold | $59 | $41 |
| G9 silver | $89 | $62 |

The smallest balance that can place a minimum lot within r (B* = min-lot risk / r):

| r | v3 (H7 / G9) | v4 (H7 / G9) | silver (stop 2.0) |
|---|---|---|---|
| 1 % | $6.4k / $5.9k | $4.5k / $4.1k | $8.9k |
| 0.5 % | $12.9k / $11.7k | $9.0k / $8.2k | $17.7k |

Consequences:
- **On 10k at 1 % with "never risk more than r", the account cannot blow.** Once the balance falls below B* (a 35-60 %
  drawdown), every signal is too small to place, so trading stops with money left.
- **Whether that counts as "cháy" is the owner's decision** (§6).
- Rounding down also cuts the risk actually taken; on 10k at 1 % it is about 0.5-0.8 %, not 1 %.

## 1. Account model (conditions A1-A11)

| # | condition | rule |
|---|---|---|
| A1 | Balance | B0 in USD (owner input). No deposits or withdrawals. Primary ranking at a B0 where min-lot rounding loses under 10 % of r for every setup (100k); the owner's B0 is the "what you get" row. |
| A2 | Sizing | sizing_basis = CURRENT balance (compounding); risk r at the stop, r <= `risk-config.json` max_risk_pct (1 %); in mode `floor_cap` only the minimum lot may exceed r, up to the cap (A3, §7.4; under the owner's base the cap is a fixed money amount, not a share of the balance). Optional throttle: none, or halving after N consecutive losses. Live use would need a book version with current-balance sizing in fvg_demo (§47). |
| A3 | Lots at one reference price | P_ref = the last close at the run date (in the config snapshot). Stop in price = stop_bp / 1e4 x P_ref. lots = floor(r x balance / (stop_price x contract) / volume_step) x volume_step, capped at volume_max. Below volume_min: **mode `skip`** (never above r), **mode `floor_cap`** (the owner's rule since §7.4: trade volume_min only if its risk at the stop <= `min_lot_cap` x the cap's base, else skip as `min_lot_over_cap`, which also counts toward STALLED, A9; the base is `min_lot_cap_base`: **"initial"** = `min_lot_cap` x B0, a FIXED amount, the owner's choice of 2026-10-04 (2 % x 5,000 = 100 USD; label `floor_cap@0.02/initial`), or "current" = `min_lot_cap` x the CURRENT balance, the first cap read and the code default (label `floor_cap@0.02`); `r <= min_lot_cap <= 5 %` is checked on the base, so for "initial" it bounds the fixed amount between r x B0 and 5 % x B0 at the start; personal_account.py:90-98, :110-122), or **mode `floor`** (trade volume_min whatever its risk: the account CAN be lost; sensitivity). Report per setup the effective risk taken / r, the share of trades above r, and B*(r). Historical-price sizing is a reported sensitivity only. |
| A4 | Margin | margin_i = lots x contract x P_ref x rate_i / leverage. The trade is skipped if used margin + margin_i > the equity floor. MT5 checks free margin against equity. Rates and leverage are not in the spec export: named ASSUMED constants (leverage 1:30, rate 1) until the owner's broker spec is exported. Reported as a guard (how often it bound). |
| A5 | Portfolio cap | Open risk at the stops <= `risk-config.json` max_portfolio_risk_pct (5 %) of the CURRENT balance; a trade over it is skipped. The code checks it only when another trade is open (personal_account.py:189): a lone trade is never skipped by A5. That matters only when one minimum lot risks more than 5 % of the balance: mode `floor`, or the fixed cap (A3) after a deep drawdown. As written, A5 also skips a lone trade: option (b) of audit §5.4. The code is option (a). Lead decision 2026-10-04 (owner may override): (b) for any real use, not read on these days (audit §5.4); the replay gets its own switch, default (a), since rows already read used (a). |
| A6 | Exact floating floor | `book_sim.trades` emits each trade's per-bar adverse R on the 5m grid (`adv_path`). floor(t) = balance + sum over open trades of money-per-R x adverse R at t. Drawdown = 1 - floor / peak balance. |
| A7 | Stop-out | If floor / used margin <= S (named, 50 %) at a bar, every open trade closes at that bar's adverse price. |
| A8 | Costs | Spread as in the trade row (FTMO-Demo relspread, server-hour frame). Commission per lot per round turn on a grid {0, c_named}; the break-even commission is reported. A ranking that flips across the grid is marked commission-dependent (tight stops pay more commission in R). No swap: the rows are intraday. |
| A9 | Ruin (absorbing) | **BLOWN** = equity <= 0, or free margin < one volume_min position's margin on every symbol of the book. Nothing trades after it, and later signals are counted as `post_ruin`. **STALLED** (reported separately, measured after the fact, NOT absorbing) = the path ENDS with >= 20 consecutive signals all skipped as "below min lot" (or `min_lot_over_cap` in mode `floor_cap`, A3): the account never traded again. (An absorbing version froze accounts during temporary runs of wide stops -- first smoke run: v3 on 10k "stalled" in 2013 at a 9 % drawdown -- so it was dropped.) |
| A10 | No prop rules | No daily loss, no target, no minimum days, no consistency rule. The owner's pain line (default 50 % drawdown, from `crypto-personal-v1`) is a reported probability, not a stop. |
| A11 | Position mode and order | HEDGING (default: H7 and G9 on the same symbol both open, as fvg_demo) or NETTING (a second same-symbol signal is skipped). An exit is realised before an entry only if exit_time < entry_time (strict). Same-time entries are sized on the same balance, in a fixed component order. |

**Stated, not modelled:**
- the executor's take-profit (5 x stop) and its close 10 minutes before the rollover (book_sim exits at the day's last bar);
- event-risk refusals (there is no historical calendar);
- partial fills, requotes, and slippage beyond the trade row;
- margin-rate changes over time, and negative-balance protection;
- currency conversion for a non-USD account.

With those stated, A1-A11 is a necessary set that determines the account path for intraday rows.

## 2. Validation labels (ranked only within a label)

- **COMPONENT-VALIDATED:** passed three reads at stop 2.0. These are H7 XAUUSD, G9 XAUUSD and G9 XAGUSD.
- **POLICY-EXPOSED:** chosen on exposed data. These are v4 (stop 1.4) and v3 as a book.
- **UNTESTED:** v4 + silver.
- **Edge:** the level comes from the post-discovery windows, with a haircut; spread and tail shape come from the full history.
- Any winner is a CANDIDATE until a forward record confirms it.

## 3. Metrics

**Historical path:**
- CAGR, max drawdown on the exact floor, Calmar;
- longest time under water;
- BLOWN / STALLED day;
- trades taken and skipped (by reason), and effective risk.

**Bootstrap:**
- Weekdays are resampled ONCE per path and every setup is replayed on the same days (`vol_schedule.sample_days`).
- The horizon is a parameter: 5 years, about 1,305 weekdays.
- Spans are intersected across the setups compared.
- Edge x {1, 0.5, 0}.
- Outputs: P(BLOWN), P(STALLED), P(drawdown >= 25 % / >= 50 %), terminal multiple p5 / p50 / p95, median CAGR. Time under
  water is taken from the historical path, because 20-day blocks understate it.

## 4. Ranking (objective `custom`, CLAUDE.md §48)

1. **survives** = P(BLOWN) <= 1 % AND P(drawdown >= the pain line) <= 5 %, at edge x 0.5.
2. **Growth:** A beats B only if A's CAGR is higher on >= 80 % of the shared paths; otherwise they tie.
3. **Tie-break:** the lower p95 max drawdown.
4. **Best r for a setup:** the r with the highest median CAGR among the r values that survive.

Each report states the number of cells (setups x r x B0 x mode x edge) and, for the winner, its paired win probability
against each runner-up.

## 5. Implementation

1. `book_sim.trades` gains extra keys only: `entry_px`, `side`, `stop_k` and `adv_path`. No existing key changes.
2. `scripts/research/personal_account.py` holds the replay (A1-A11) and the paired bootstrap. Hand-built tests cover:
   compounding, rounding, the skip, floor and floor_cap modes (the cap inclusive; floor_cap at cap = r trades as skip, at a
   wide cap as floor), the cap base (the fixed amount is cap x B0 for any B0, trades after a drawdown where the
   current-balance cap skips, is tighter above B0 and sizes as skip from cap / r x B0 up, reaches BLOWN on a gap sequence
   where the current cap stalls, labels), the margin skip, the portfolio cap, the exact floor, stop-out, BLOWN /
   STALLED absorbing, `post_ruin` counting, strict tie order, and hedging vs netting. Also the grid guard (a run needs
   edge x 0.5, which the ranking reads) and the entry comparison behind `check` (the reproducibility check, §46).
3. First read (DESCRIPTIVE, labels as in §2):
   - setups: H7 XAU, G9 XAU, G9 XAG; v3, v4, v4 + silver;
   - r: {0.5, 1} %;
   - B0: {owner, 100k};
   - modes: {skip, floor};
   - edge: {1, 0.5, 0};
   - 1,000 paths.

## 6. Owner decisions

1. **B0:** the personal account's size.
2. **Does STALLED count as cháy?** And is mode `floor` acceptable on a personal account (trading the minimum lot even when it
   is more than 1 %, so the account can really be lost)?
3. **Broker:** its spec (leverage, margin rates, commission) if it is not FTMO-like.

## 7. Owner decisions (2026-10-04, chat; binding)

1. **B0 = 5,000 USD.**
2. **"Không vượt 1%, báo 'đứng' riêng".** Mode `skip` is primary: never risk more than r. **Cháy (BLOWN) only when the money
   is really gone.** STALLED (the account can no longer place a minimum lot within r) is reported separately and is not ruin.
   Mode `floor` stays a reported sensitivity only.
3. Broker: not given. FTMO-Demo specs remain the stated proxy.
4. **"Cho phép vào lot nhỏ nhất dù vượt 1%, có giới hạn trên (ví dụ: 2% với tài khoản có số vốn 5000$)"** (2026-10-04,
   after the first read). This replaces "never above 1 %" in item 2 for the minimum lot ONLY: mode `floor_cap` (A3).
   - Sizing stays r = 1 % of the current balance. Only a trade whose 1 % is below volume_min is changed: it trades
     volume_min if that risks <= the cap (2 %, the owner's example) of the cap's base (first read: the current
     balance; owner 2026-10-04: B0, a fixed 100 USD, below); otherwise it is skipped.
   - BLOWN and STALLED keep their meaning (item 2). STALLED now means: the minimum lot no longer fits under the cap.
   - Mode `skip` stays the reference row (the earlier rule); mode `floor` stays a sensitivity.
   - The cap value is a named parameter (`Account.min_lot_cap`). 2 % was given as an example (named as the value
     2026-10-04, below); 1.5 % is reported as a sensitivity. Read: docs/audits/2026-10-04-personal-account.md §5. 2 %
     is the owner's number, not a backtest optimum; no further cap values are read on these days (§5 there counts the
     variants read).
   - The cap's base. The first cap read used the CURRENT balance, like r. The words also allowed a fixed 2 % of the
     starting 5,000 USD (100 USD); that was left open (audit §5.4).
   - **Owner 2026-10-04: "Trần 2% tính theo cố định 100 USD"** (the cap is 2 % of B0, a fixed 100 USD). Decided BEFORE
     any fixed-cap number existed (the current-balance numbers were known); it closes the open item and names 2 % as
     the value. `Account.min_lot_cap_base = "initial"` (A3); the current-balance rows stay in the audit as the earlier
     reading.
     - Sizing above the minimum lot is unchanged: r = 1 % of the current balance.
     - After a drawdown 100 USD is a larger share of the balance (4 % at 2,500, 10 % at 1,000). Nothing scales it down:
       the other entry checks are margin (A4) and A5, which as run binds only a SECOND open trade (the lone-trade case
       is an open decision, A5); then stop-out (A7). So BLOWN (A9) is now possible; no current-balance cap path reached
       it on these days (audit §5.1).
     - After growth it is tighter than 2 % of the balance. From cap / r x B0 = 10,000 USD up, a minimum lot that 1 %
       cannot place risks more than 100 USD, so the rule then sizes exactly as `skip`.
     - Read once, descriptive: audit §5.5.
   - The rule was chosen AFTER the first read showed mode `floor` recovering the edge (CLAUDE.md §44: the same days are exposed).
     Its read is DESCRIPTIVE, a sizing choice on known data, not a validation of an edge.
