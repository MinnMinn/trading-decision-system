# Execution plan for the methodology improvement plan (2026-09-29)

Parent: docs/plans/2026-09-28-methodology-improvement-plan.md (approved, with the owner decisions in its §6).
Owner instruction 2026-09-29: continue until the whole system is complete.

Done so far: A0 (real costs + no-overnight rule), A0b (record honesty), A1 (structures module), the FTMO
history source, 1m/30m parameters.

## Shared contract: the fidelity / variant keys (the "v1 key")

Every F or V item from plan §3 is one engine option. All items follow the same four rules, so that parallel
workstreams never redefine the contract:

1. **One OPTS key per item**, named `fx_<item>`: for example `fx_b2a_fvg_in_leg`, `fx_b1_pivot1`, `fx_w1_tr_low_st`.
   - An F item's key is a bool.
   - A V item's key holds the declared value set of plan §3, with the baseline first.
2. **Default = v1 behaviour.** Every default lives in `backtest-methods._OPTS_BASE`, so no key changes any output
   unless it is set. The live runner never sets a key. A key reaches live only when the owner approves v2 (plan §1.6).
3. **Every key is scan-relevant.** It is listed in `stability-report._SCAN_RELEVANT_KEYS` and stated with its v1
   default in `config_opts`, so the scan cache can never mix two computations. The key is also recorded by
   the config snapshot.
4. **Every item ships with four things:**
   - a unit test citing its knowledge/ source;
   - its funnel delta from `scripts/diagnose-methods.py`, run on development data (< 2024-03-01) with
     `BT_HISTORY_ROOT=data/history/ftmo` on XAUUSD/US500/DE40 15m;
   - a before/after chart image, for items that change structure;
   - proof that v1 is unchanged: stability rows byte-identical with every key at its default.

## Batches

- **Batch 1 (parallel):**
  - (a) the ICT F items in ict-scan.py: B2a, B2b, B1, B-RAID;
  - (b) the Wyckoff F items: W-BU check, W1, W2, W3, W5. W7 is built behind its key but not adopted: it waits
    for owner sign-off, which it needs in advance;
  - (c) A1b + A2 + A2b: the new structure objects, the chart rendered from the engine, and staleness as a quality state.
- **Batch 2:**
  - (a) the V-item keys and value sets, which the grid in plan §3 fixes;
  - (b) the evaluation harness `scripts/fund-search.py`. It runs a nested walk-forward over the development span
    and applies the N-adjusted lower bound, the stability and frequency rules, and the §45 checks (plan §1.4).
    The runs are cell-sharded for GitHub Actions and use real costs with no overnight holding;
  - (c) A3t: point-in-time chart pages for the image gate.
- **Batch 3:**
  - the single evaluation run;
  - an honest report;
  - owner review;
  - a new pre-registration.
- **Stop point:** turning on forward demo on the FTMO demo account requires the owner's explicit go-ahead. The
  pilot stays off until then.
