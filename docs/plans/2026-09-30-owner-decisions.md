# Owner decisions recorded during Batch 1-2 (2026-09-29 / 2026-09-30)

Source: chat with the owner; recorded here so they survive a context reset. Supplements plan §6
(docs/plans/2026-09-28-methodology-improvement-plan.md). Nothing here loosens any §1.4 rule.

## Adopted F set for the evaluation baseline (owner: "Cho phép adopt", 2026-09-30)
Adopted on the default proposal (F items whose funnel trade-count delta is within x1.5, plan §1.2):
- ICT: `fx_b2a_fvg_in_leg` (B2a), `fx_b2b_ce_fail` (B2b).
- Wyckoff: `fx_w1_tr_low_st` (W1), `fx_w3_mSOW_spring` (W3), `fx_w5_vp_abandon` (W5).
Evidence: docs/audits/2026-09-29-ict-fidelity-funnel.md, docs/audits/2026-09-29-wyckoff-fidelity-funnel.md.
ALSO ADOPTED by explicit owner instruction 2026-09-30 ("Đồng ý adopt B-RAID, W2, B1 và W7"), despite trade-count deltas beyond
x1.5 (B-RAID ~x9, B1 x2.07 on DE40, W2 x1.63 on XAUUSD) and W7 acting on ~80 % of Wyckoff trades: `fx_braid_optional`,
`fx_b1_pivot1`, `fx_w2_st_below_sc`, `fx_w7_htf_target`. The reviewer's B-RAID recency suspicion was tested and rejected
(docs/audits/2026-09-29-ict-fidelity-funnel.md); a lookback bound was added on the no-raid path, effect ~0.
So all nine F items are in the evaluation baseline. `fx_a2b_stale_htf_block` (A2b) is a live-safety key, default OFF; its
adoption is a separate live-safety decision.
"Adopted" means: ON in the evaluation baseline of the fund search only. The live/pilot path keeps v1 until the owner
approves v2 (plan §1.6). The evaluation harness must set the nine F keys in its fixed overlay before any run.

## V-item readings (defaults accepted 2026-09-29)
- W4a: baseline = key unset (v1's own typing, not a count); the cells 3 and 4 are the variants. An explicit `2` is a different rule.
- W-TOUCH: at least 2 recorded Phase-B tests at each TR border (`W_TOUCH_MIN = 2`).
- W6: only the Wyckoff-side key; decided together with the ICT SCAN_WINDOW; a 600-bar window needs >= 600 bars.
- B-POOL: most recent completed UTC day (PDH/PDL) plus the most recent completed asia/london run.
B4 (ICT) and W4b (Wyckoff) are declared but not implemented (the sources define no engine-usable rule); they stay counted in N.

## Execution / MT5 MCP
- Order placement through the MT5 MCP is permitted (owner, 2026-09-29). The system is built to trade real accounts, so there
  is NO hard-coded demo-only block. Real money is selected only by the explicit environment switch, never by default, and
  every order still passes the risk check (1 %), event-risk, account rules and human confirmation (CLAUDE.md §51).
- The forward-demo go-ahead and the pilot remain a separate explicit owner decision; the pilot stays OFF.
- The MT5 MCP key lives only in config/env.demo (gitignored). The key that appeared in chat is compromised and must be rotated.
  MCP research: docs/architecture/mt5-mcp-evaluation.md (official docs do not describe auth; key sharing "not documented").

## Compute plan (owner: "(b) rồi (a)")
(b) first: make the scan engine fast enough to run cells locally (multi-value-set reuse, parallelism), byte-identical results.
(a) then: shard the fund search on GitHub Actions by value set/symbol. Pushing/triggering workflows needs the owner's go-ahead
at that time.

## Standing rules restated
- The evaluation window is never moved to rescue a method. Results are reported honestly, including zero passes.
- The engine smoke test (docs/audits/2026-09-30-fund-search-engine-smoke.md) is structural only and does not count as an evaluation.

## 2026-09-30 (later): planned R:R floor 2.5, `no_floor` removed, minimum edge `e`
1. **Planned R:R floor at entry = 2.5** (owner: "R:R target when entering a trade must be at least 2.5R"), for BOTH methods
   (ICT and WYCKOFF-BOOK) and BOTH backtest (`simulate()`) and live (`strategy-runner` `rr_reason`), applied NET of fees
   exactly as before. Source of truth: `docs/architecture/analysis-params.json` `project_defined.ict.min_rr` (was 2.0 since
   2026-09-19, 3.0 from 2026-09-13; the history stays in its `_basis`). One reader: `trading_env.min_rr()`.
2. **`no_floor` removed from the ICT V grid** (`docs/architecture/v-grid-ict.json`, item B-EXIT): it skipped the planned-R:R
   floor for ICT trades, which contradicts decision 1. B-EXIT is now 3 x 4 x 1 = 12 value sets (11 non-baseline). The engine
   code path for a `no_floor` token is kept (live never sets `fx_` keys), but no grid cell can reach it (`build_overlay`
   refuses a value the grid does not declare).
3. **New N.** ICT: 1 + 27 + 1 = **29 per cell** (was 41), x 8 cells = **232** (was 328), one-sided confidence
   1 - 0.10/232 = **0.999569** (was 0.999695). Wyckoff unchanged: 16 per cell, 128, 0.999219.
   (`python3 -W ignore scripts/fund-search.py plan --dry-run`.)
4. **The declaration pins the floor.** `evaluation_config.min_rr` (scripts/fund-search.py) is written by `declare`; `run`
   refuses on drift if the effective floor differs. `scripts/fund-search.py` is a pinned file, so `declare` must run after this change.
5. **`e` (minimum edge of interest).** Delegated by the owner and set by the coordinator to **0.20R** as a
   pre-declaration default. It is to be fixed before `declare` and is not adjustable after results are seen.
