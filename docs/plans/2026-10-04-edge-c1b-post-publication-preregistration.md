# C1b -- one post-publication read of the frozen C1 crypto trend book -- pre-registration (2026-10-04) [C1b-P1]

**Committed BEFORE the read.** Code: `scripts/research/edge_c1b.py` (reuses `scripts/research/edge_c1.py` unchanged);
tests: `scripts/tests/test_edge_c1b.py`. **This is a SECOND STAGE chosen AFTER seeing C1's discovery read**
(docs/audits/2026-10-04-edge-c1-discovery.json: sleeve alpha +9.5 %/yr, Newey-West one-sided p 0.0385, placebo p 0.001, BH
m = 4 rejected nothing, regime-driven). The design record had considered collapsing C1's reads into one replication read and
rejected it as "a protocol change that would have to be decided before any read"
(docs/plans/2026-10-03-crypto-cfd-design.md, section 6 item 1). It is done anyway, after the read, for the reason and under
the constraints below; an adversarial review (2026-10-04) recommended running C1b only, with every change listed here, and
NOT running a second stage for M1.

## 1. Why, and the selection rule

C1's spec is entirely the source's (Zarattini-Pagani-Barbon, sample ending 2025-03-19); 2025-03-20 -> 2026-09-30 is the only
data after its publication, and nothing in this repo has measured this hypothesis on it. A failed family qualifies for one
post-publication read only if (a) every parameter is the source's, (b) a post-publication window exists that no family here
has read for that hypothesis or for a near-identical signal, and (c) its discovery point estimate is > 0 with a placebo
p <= 0.01. **C1 qualifies. M1 does not** (b fails: its later windows overlap F3's H1 20-day-momentum reads and G7's
turn-of-month reads of nearly the same signal on the same days) -- M1 is CLOSED, "not a candidate; inconclusive at this
power". **H7x does not** (a fails: its parameters were chosen by this repo on gold).

Decided now for every other window, and C1b's result cannot change it: C1's CONFIRMATION window is never read for promotion;
H7x's EXPOSED window is RETIRED (never read for H7x); M1's confirmation / exposed windows are never read for M1.

## 2. The read

- Window 2025-03-20 -> 2026-09-30 (C1's EXPOSED window). Every rule, cost, fill, funding, eligibility and placebo detail is
  C1's (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §2-§5 and amendment [C1-A1]); signals are built from
  spot closes over all history up to the window's END; no P&L is computed before the window (positions open at its start are
  placed at an equal split of capital without a fee, [C1-A1] item 5).
- **One test, no BH:** T1 sleeve alpha against the equal-capital benchmark, Newey-West (10 lags) one-sided p.
  **PASS iff** p < 0.05 AND mean net daily return > 0 AND mean net at 2x slippage > 0 AND placebo p_P <= 0.10 (1,000 draws, seed
  20261003, C1's circular-shift offsets inside the window). Per-coin T2-T4 are reported, decide nothing.
- Reported with the decision: alpha with a 90 % CI (Newey-West); a SHRUNK alpha with a normal prior N(0, (10 %/yr)^2)
  (discovery is subject to the winner's curse); alpha by calendar month and the regime flag (> 50 % of alpha from <= 3 months);
  C1's diagnostics N2 (owner sizing, 1 % at the stop), N3 (gross / net / funding), N4, N5 (correlation with fvg-book v3), N6.

## 3. Actions fixed in advance

- **PASS** -> label "single post-publication read passed; never read for this hypothesis; bars are development-state; price
  path public" (+ "regime-driven" when flagged). Action: build a forward PAPER monitor of C1 on Binance perps with an always-
  valid sequential test, as a cost / execution check (not as proof: at these effect sizes it takes years); any testnet or real
  order is an owner decision. Never called "validated".
- **FAIL** -> C1 is CLOSED; no forward monitor; recorded as "single post-publication read failed".

## 4. Power (stated before the read; adversarial review's arithmetic on committed numbers)

560 days; alpha SE about 8.6 %/yr, so a pass needs a realized alpha of at least about 14 %/yr. Power about 0.52 at the full
published effect, 0.29 at the discovery estimate (9.5 %/yr), 0.23 at half the published effect, 0.12 at a shrunk ~4 %/yr. A
pass is moderately informative (likelihood ratio about 2-10); a fail is nearly uninformative -- which is why a fail closes C1
rather than inviting a third read.

## 5. Prior reads (disclosed)

Everything in C1 §9; C1's discovery result itself (it chose this stage); H7x's discovery and confirmation reads (another
trend mechanism on the same coins, 2017-2024); the crypto bars of this window are development-state for the ICT / Wyckoff
spot selections (research-ledger `crypto-history-2023-2026`); the 2025-26 BTC / ETH / SOL price path is public knowledge.
Experiment budget: +1 test (a second stage after a failed discovery gate).
