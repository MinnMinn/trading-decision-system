# Handoff — Windows to MacBook (2026-09-29)

Branch base: `windows-migration` at the commit that adds this file. Remote: `minn`.
Governing plans: `docs/plans/2026-09-28-methodology-improvement-plan.md` (owner decisions §6) and `docs/plans/2026-09-29-execution-plan.md` (shared `fx_` key contract, batches).

## Where the work stands

Batch 1 (fidelity items, all behind `fx_<item>` keys, default v1) is code-complete on three branches pushed to `minn`. None is merged, and none has passed code-review yet (the reviewer agents were killed by session restarts twice).

| Branch | Content | State |
|---|---|---|
| `b1-chart-structures` | A1b, A2, A2b page side: chart draws only engine structure objects, `invalidated_at`, Wyckoff `phases`, STALE HTF tier | 2 commits (c8772fa, d699ac3). Review round 1 done and fixed. Round 2 (last allowed) NOT done. |
| `b1-ict-fidelity` | B2a `fx_b2a_fvg_in_leg`, B2b `fx_b2b_ce_fail`, B1 `fx_b1_pivot1`, B-RAID `fx_braid_optional` | 1 WIP commit. Own-run tests: test_ict_fidelity 19, test_audit_round2_ict 29, test_audit_round4_integrity 49, all OK. AUS200 4H rows identical to base. Not reviewed. Funnel doc missing. |
| `b1-wyckoff-fidelity` | W1 `fx_w1_tr_low_st`, W2 `fx_w2_st_below_sc`, W3 `fx_w3_mSOW_spring`, W5 `fx_w5_vp_abandon`, W7 `fx_w7_htf_target` (W7 NOT adopted, needs owner sign-off) | 1 WIP commit. Own-run: test_wyckoff_fidelity 33 OK. AUS200 4H rows identical. Not reviewed. Funnel doc missing. |

`fx_a2b_stale_htf_block` (decision side of A2b) is NOT wired anywhere yet. Wire it after the three branches are merged (default v1, in `_OPTS_BASE`, `_SCAN_RELEVANT_KEYS`, `config_opts`).

## Partial funnel deltas (dev data before 2024-03-01, 15m, config A) — not evidence of edge

Method: `BT_HISTORY_ROOT=data/history/ftmo python scripts/diagnose-methods.py run --symbol <S> --tf 15m --method <ICT|WYCKOFF-BOOK> --config A --out <file.json> [--set fx_key ...]`. One XAUUSD run takes 10-20 min. Each variant tried counts toward N (ICT 41, Wyckoff 16 per candidate cell).

ICT (trades / sum R): US500 v1 34 / 4.04, b2a 23 / 2.01, b2b 33 / 2.90, b1p 48 / -4.31. DE40 v1 15 / 0.07, b2a 12 / -2.75, b2b 15 / 0.07 (identical to v1), b1p 31 / 11.89, braid 137 / -1.85.
Wyckoff (trades / sum R): v1 XAUUSD 416 / -16.79, US500 73 / 13.85, DE40 61 / 22.62. w1 identical to v1 on all three. w3 and w5 identical to v1 on US500 and DE40. w2 US500 107 / 16.40, DE40 80 / -8.32. all-four DE40 103 / 8.38. w7 DE40 40 / 21.28.
Still missing: every ICT XAUUSD variant, ICT braid US500, ICT `all` on all symbols; Wyckoff XAUUSD w2/w3/w5/all/w7, US500 all/w7. The raw JSONs were in a Windows scratch folder and are not in git.

## Remaining steps (in order)

1. Finish the missing funnel runs; write `docs/audits/2026-09-29-ict-fidelity-funnel.md` and `docs/audits/2026-09-29-wyckoff-fidelity-funnel.md` (label OBSERVED / INFERRED; W7 reported but not adopted).
2. Chart images for structure-changing items if the chart-image gate requires them.
3. code-reviewer on each branch (chart: last allowed round; ICT and Wyckoff: up to 2 fix rounds). Review checklist: v1 default unchanged, PIT, live never sets `fx_` keys, key present in `_OPTS_BASE` + `_SCAN_RELEVANT_KEYS` + `config_opts`, tests non-vacuous. For Wyckoff also check that `wyckoff_rules.PARAMS` is not left mutated between runs.
4. Merge into `windows-migration`. The ICT and Wyckoff branches collide textually in `backtest-methods._OPTS_BASE`, `stability-report._SCAN_RELEVANT_KEYS`, `config_opts`, `snapshot.py`, `diagnose-methods.py` (the `--set` hunks are identical). Resolve, then wire `fx_a2b_stale_htf_block`.
5. Re-verify v1 unchanged: AUS200 4H stability rows byte-identical vs base commit 3d52fae. Run the per-module tests in the main checkout, including `test_i18n` (needs CFD data).
6. Push to `minn`.
7. Batch 2: V-item keys; `scripts/fund-search.py` (nested walk-forward, N-adjusted one-sided lower bound at 1 - 0.10/N, stability across at least ceil(2m/3) symbols with no trade over 25% of net R, frequency rule, §45 checks, cell-sharded on GitHub Actions, real costs plus no overnight); A3t point-in-time chart pages; re-run the MinBTL luck-ceiling check on FTMO 1m/5m/30m.
8. Batch 3: one evaluation run, honest report, owner review, new pre-registration.

## Stop points (ask the owner)

W7 sign-off; forward-demo go-ahead (pilot stays OFF); any change of the evaluation window (only allowed to confirm a method that already works). Report results honestly, including zero passes.

## Running tests (quirk)

Run from `scripts/tests` with `PYTHONPATH=..`, one module per invocation: `python -W ignore -m unittest <module>`, then grep `^(Ran|OK|FAILED|ERROR:|FAIL:)`. Running from the repo root breaks sibling-helper imports. Worktrees have no mt5-bridge data, so `test_i18n` exits 1 there; run it in the main checkout.
Known pre-existing failures on the base: `test_improve_loop` (180 s timeout), `test_config_snapshot`, 4 in `test_strategy_runner`, 1 in `test_coverage`.

## Other open items

FTMO real commission is unknown (open and close a 0.01 lot trade, re-export); never guess it. The owner must change the FTMO trial password (it was pasted in chat once and was not used or stored). XAGUSD live feed stops at 09-25 (EA chart must be reopened). Windows-only runtime files under `data/live/` were not committed.
