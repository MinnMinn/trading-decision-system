# Family CX -- the gold intraday-trend rules (H7, G9) on FTMO's crypto CFDs -- pre-registration (2026-10-04) [CX-P1]

**Committed BEFORE any FTMO crypto bar exists in this repository.** The owner exports them after this commit, so no outcome,
count or spread of these instruments has been read. Owner 2026-10-04: "B2 mở crypto CFD của FTMO". Code, to be written
against this text: `scripts/research/edge_cx.py`. Tests: `scripts/tests/test_edge_cx.py` (hand-built bars) plus the detector
leakage probe, including a truncation test. Revised once before commit after an adversarial review (12 findings, all
applied).

Question: the only robust edge in this repository is intraday trend continuation on gold (H7, G9; fvg-book v4). On Binance
perps the same rules showed a signal but no net profit after a 12 bp taker round trip (docs/audits/2026-10-04-crypto-cfd-phase.md:
H7x confirmation pooled gross 13.9 / 12.6 bp, net +0.2 / +0.05 bp). Can FTMO's own crypto CFD -- its prices, its server day,
its costs -- turn that signal into net profit, on windows no test has read?

## 1. Rules (FTMO server day, direction FIXED = continuation, one-sided)

- **H7** (F3 `ev_breakout_trend` rule text): the first 5m close beyond the previous qualifying server day's high (low) when
  MOM20 has the same sign. MOM20 = the last close of D-1 / the last close of the 21st previous qualifying day - 1.
  **G9** (F4 `ev_vol_breakout` rule text): the first 5m close beyond open(D) +/- 0.5 x the previous qualifying day's range.
  Parameters come from gold, with no tuning.
- **Point-in-time completeness (the H7x rule; F3 / F4's research mode is NOT used).** A server day QUALIFIES as history iff
  it has >= 230 distinct on-grid 5m bars (a fixed constant, 0.8 x 288, never a data median). Day D is eligible iff D-1
  qualifies and >= 21 qualifying days precede D. D's own bar count is never consulted. sigma_5m = RMS of 5m log returns
  over the previous 20 qualifying days. MOM20 counts 20 qualifying days, whatever calendar span that is.
  Why: edge_census.Series in research mode keys sigma and MOM20 on days that turn out dense, a same-day completeness selection
  (edge_census.py:121-124; edge_f3.py:123-135). On crypto, feed gaps cluster on crash days. Measured on gold for
  comparison, the selection changed nothing material: docs/audits/2026-10-04-density-selection-check.md.
- Entry at the next bar's open. Exit at D's last bar (the `eod` hold), or at D's last available bar when bars are missing
  after the signal (counted and reported). An event whose entry bar is not in the signal's server day is dropped. One event
  per (symbol, D, rule): the earliest entry.
- The leakage probe deletes every bar after the signal bar and requires the event and its inputs (side, MOM20, sigma, range)
  to be unchanged.

## 2. Universe and screens (fixed before any return is read)

- **Universe:** the 30 symbols of the FTMO-Demo paths `Crypto I CFD` / `Crypto II CFD` in the symbol-list export of
  2026-10-01 (file sha256 recorded in the screening amendment; the file is committed with it): BTCUSD ETHUSD SOLUSD ADAUSD
  DOTUSD LTCUSD XRPUSD BCHUSD AVAUSD ETCUSD DASHUSD DOGEUSD NEOUSD XMRUSD BNBUSD SANUSD LNKUSD NERUSD ALGUSD ICPUSD AAVUSD
  BARUSD GALUSD GRTUSD IMXUSD MANUSD VECUSD XLMUSD UNIUSD XTZUSD.
  - Each symbol gets a canonical instrument from its MT5 description (e.g. BARUSD = Hedera, NERUSD = NEAR) before the
    screen (CLAUDE.md §5).
  - Survivorship, disclosed: the list holds only coins listed at FTMO in 2026.
- **Commission (established BEFORE the screening amendment; an owner action that reads no outcome):**
  - c_sym = commission per side as a fraction of notional.
  - Source: FTMO's published per-asset schedule (URL and retrieval date committed). Failing that, |sum of commission in
    account currency| / sum over deals of (volume x contract size x deal price), from that symbol's own demo deals.
  - `real_costs.commission_r` (always 0.0) is NOT used.
  - A symbol without c_sym cannot be screened in.
- **Cost profile:** a new profile `ftmo_demo_2026_10_crypto_relspread` (ExportSymbolSpec export date and file sha256
  committed), passed explicitly by edge_cx and the sizing diagnostics, never through `edge_census.COST_PROFILE`. The table
  covers about the last 100,000 M15 bars (about 2.85 years on a 7-day market). Every development-window net is labelled
  "modelled at the export window's relative spreads".
- **Cost screen (outcome-blind):**
  - K = 0.5 x median over the 24 buckets of the relative spread + 0.5 x the relative spread at the bucket of a server day's
    last bar (every exit is there) + 2 x c_sym.
  - S = the median, over qualifying days before 2024-03-01, of sigma_5m x sqrt(median hold in bars), the hold taken from
    an outcome-blind dry-run count.
  - A symbol is admitted iff K <= 0.5 x 0.05 x S: cost may eat at most half of an H7x-confirmation-sized excess (z = 0.05).
- **Calendar split and membership (group A, below):**
  - D* = the date by which 60 % of the group's pooled qualifying coin-days before 2024-03-01 have elapsed.
  - Membership is fixed ONCE: coins with >= 250 qualifying days in both [start, D*) and [D*, 2024-03-01).
  - Exactly these coins enter every group-A read. The others are listed and never tested.
- **The screening amendment** is committed before the discovery read. It records:
  - per symbol: K, S, c_sym and qualifying-day counts per window;
  - D*, the members and the fixed EXPOSED end date;
  - the dataset snapshot (per symbol and timeframe: file sha256, first / last bar, bar counts, ExportHistory version,
    server; the spec sha256);
  - median bars per weekday and per server hour;
  - power in distinct server days per read.

  It reports counts only, never split by side.

## 3. Groups, windows and reads

- **Group A** = the members minus BTC, ETH and SOL. None of these coins has had prices read by any test here.
  - Three reads, in order, each once, each in its own commit: DISCOVERY = [first bar, D*), CONFIRMATION = [D*, 2024-03-01),
    EXPOSED = [2024-03-01, the fixed end date].
  - Disclosed dependence: the altcoins co-move with BTC / ETH, whose 2017-24 intraday behaviour H7x read. Discovery is
    therefore not independent of that knowledge; confirmation and exposed are what count.
- **Group B** = BTCUSD, ETHUSD, SOLUSD, if screened in.
  - Their development window is NOT used, because H7x read their underlying through 2024-02-29.
  - ONE read: [2024-03-01, the fixed end date]. This is NOT an out-of-sample read:
    - docs/architecture/research-ledger.json declares `crypto-history-2023-2026` (development) for BTC / ETH / SOL;
    - it is a second stage of H7x after H7x failed confirmation;
    - C1b read a daily rule on 2025-03..2026-09.
  - A group-B pass makes a CANDIDATE only. It needs a separately pre-registered forward stage before any book use.
- The research ledger gets group A's periods and group B's relabelled period before the discovery read, with the one-way
  state changes after each read (§44).

## 4. Measurement

- r = side x (C[exit] / O[entry] - 1); scale = sigma_5m x sqrt(bars held).
- **Placebo, matched as in H7x §3:** the mean return from the same entry 5m slot to D's last bar, over eligible days of the
  same symbol, read, weekday and MOM20 sign, signed by side. Excess = r - placebo. The F3 / F4 unconditional placebo would
  credit crypto drift and time-series momentum to the breakout.
- Statistics: `edge_census.summarise` with each row's cluster key = the signal's SERVER date (`s.sday[i]`), set by edge_cx
  (the census default keys the UTC date).
- Cost per leg = half the profile's relative spread at the leg's table bucket (`real_costs.table_hour`, server-hour frame)
  plus c_sym. Stress = the p90 spread plus c_sym. No swap: every trade is flat before the server rollover.
- Report-only extras: long and short legs separately, weekend-day trades separately, net per symbol and per year, and the
  MOM20-alone comparator (H7x §5).

## 5. Tests and decision rule

The primary tests are POOLED within a group: **T1 = H7 group A, T2 = G9 group A, T3 = H7 group B, T4 = G9 group B.** Per-coin
rows are reported only.

| read | gate |
|---|---|
| A, discovery | BH over {T1, T2}, one-sided p, q = 0.10, rejects AND net > 0 -> CANDIDATE |
| A, confirmation | one-sided p < 0.05, net > 0, net at the p90 spread > 0 |
| A, exposed | one-sided p < 0.10, net > 0 |
| B, single read | Holm (m = 2) one-sided p < 0.05, net > 0, net at the p90 spread > 0 -> CANDIDATE (forward stage required) |

- Each test advances independently. A test that fails a gate is closed, and its later windows are retired unread.
- Every scheduled read runs regardless of the other group's results. A group left empty by the screens is "not run (screen)",
  and the other group's correction does not change.
- Read JSONs persist their trade rows.
- A survivor is the pooled basket over its group's members, never a hand-picked subset. Its only tradable form is fixed now:
  - at most 3 concurrent basket positions, first come first served, each at 1 % / 3 risk at the stop;
  - every read reports, in that form: the worst server-day loss, the number of days with loss > 2 % and > 5 %, the most
    concurrent positions, and the most gross notional / equity;
  - a survivor with any server day beyond -5 % in its reads is not proposed.
- A survivor then goes to `book_sim compare` against fvg-book v4, and to the forward stage of
  docs/plans/2026-10-02-edge-followup-preregistration.md §4, before any symbol leaves research-only.
- Zero survivors is a valid result.

## 6. Diagnostics (outside the family)

- Owner sizing at 1 % at the stop, stop_k 2.0 and 1.4 as `book_sim.trades`: R per trade, stop share, gap-through (loss
  > 1.05 %), worst trade.
- Daily P&L correlation with fvg-book v4 per server day.

## 7. Budget and prior

- CX: 4 primary tests; reads: group A 3, group B 1.
- Cumulative transfers of H7 / G9 to date, disclosed:
  - F3 / F4 (gold and silver origin);
  - F5: 27 tests, 0 survivors;
  - H7x: 2 tests x 2 reads, 0 survivors.
- Prior: weak.

## 8. Data (owner action, after this commit)

On FTMO-Demo MT5:
1. Tools > Options > Charts > Max bars in chart = Unlimited.
2. Write `Common\Files\export-list.txt` with line 1 `tf=5m,15m,1H,1D` and line 2 `symbols=` plus the 30 names in §2
   (ExportHistory v1.02 file mode; typing a long InpSymbols proved unreliable).
3. Run `integrations/mt5/ExportHistory.mq5`.
4. Run `integrations/mt5/ExportSymbolSpec.mq5` with InpSymbols = the same 30 names.
5. Provide c_sym as in §2.

The importer, the canonical-instrument entries and the research-only registry entries (never execution) are added when the
files exist.
