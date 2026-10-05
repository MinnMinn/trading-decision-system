# A1 / A3 re-read under the owner's gap tolerance (2026-10-04)

**DESCRIPTIVE, post hoc.** No new run: every number below is read from the committed results
(docs/audits/2026-10-03-vol-schedule.json, docs/audits/2026-10-04-a3-silver.json, docs/audits/2026-10-04-gap-tail-counts.json),
except the silver prior in §2, which is quoted from the A3 pre-registration (named there).
The decision rules are those of A1 (docs/plans/2026-10-03-vol-schedule-preregistration.md §4) and A3
(docs/plans/2026-10-04-a3-silver-preregistration.md §3, [A3-P1]), with ONE change: the gap tolerance. Both pre-registrations
used 1.2 % of the balance, which was this session's assumption (disclosed then). The owner set it on 2026-10-04 **after**
seeing these results: "Khoảng 1,5%, 2 lần trong 1 năm" -- a single trade may lose about 1.5 % of the balance, up to twice
a year. Because the tolerance was chosen with the results in view, a "PROPOSED" below is an owner choice informed by exposed
data, not a pre-registered pass.

## 1. A1 -- stop width k in Phase 1 / Phase 2 (reference 2.0/2.0 = v3; funded stage always at 2.0)

Delta E[net] in % of the balance over a 252-weekday horizon, against the reference on the same bootstrap days; fail = first
attempt; boot = stationary block bootstrap (3000 paths); conf = historical starts from 2024; sel = starts before 2024.

| policy | dE half edge | dE edge 0 | dE edge 1 | conf fail | boot fail, half edge | boot fail, edge 0 | worst trade % | at 1.2 % | at 1.5 % | sel funded <=122 d | conf funded <=122 d | sel median days |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2.0/2.0 (v3) | -- | -- | -- | 0.000 | 0.003 | 0.058 | 1.18 | -- | -- | 0.111 | 0.009 | 281 |
| 2.0/1.4 | +0.148 | +0.023 | +0.546 | 0.000 | 0.005 | 0.063 | 1.39 | no | yes (variance) | 0.175 | 0.017 | 254 |
| 2.0/1.0 | +0.236 | +0.035 | +0.802 | 0.000 | 0.023 | 0.076 | 1.94 | no | no (gap) | 0.234 | 0.078 | 205 |
| 1.4/2.0 | +0.364 | -0.033 | +1.185 | 0.000 | 0.036 | 0.245 | 1.39 | no | yes | 0.262 | 0.121 | 214 |
| **1.4/1.4** | **+0.592** | +0.005 | +1.782 | 0.000 | 0.041 | 0.260 | 1.39 | no | **yes (variance flag)** | **0.327** | **0.250** | **180.5** |
| 1.4/1.0 | +0.718 | +0.023 | +2.123 | 0.000 | 0.063 | 0.294 | 1.94 | no | no (gap) | 0.382 | 0.379 | 144 |

- Under 1.5 %, the best value that passes is **1.4/1.4**. Its edge-0 delta is +0.005 pp, so the rule marks it
  "variance, not edge". The flag is mechanical: the gain is +0.59 at half edge and +1.78 at full edge, so it scales with the
  edge. But if the edge is gone, the tighter stop fails the first attempt far more often (26 % against 5.8 %). That is the
  price of the speed.
- The k = 1.0 policies stay out. Their worst trade, 1.94 % (2012-06-01), is well above "about 1.5 %".
- Gap frequency at k = 1.4 (H7 + G9 gold, 22.2 years, unthrottled 1 % at the stop): a loss above 1.05 % happened 4 times,
  above 1.2 % twice, above 1.5 % never. The worst was 1.39 %. That is far inside "twice a year".

## 2. A3 -- add G9 XAGUSD to v3 (span from 2008-12-10)

dE half edge +0.911, dE edge 0 -0.023 (edge, not variance), dE edge 1 +3.52; conf fail 0.000; boot fail 0.076 at half edge,
0.352 at edge 0; worst silver trade 1.32 % → it **also passes at 1.5 %**. Two caveats keep it second:

1. In the selection starts (before 2024) v3+ag fails the first attempt **16 %** of the time; v3 fails 0 %. The pre-registered rule
   did not gate on selection starts, but 1.4/1.4 is 0 % there.
2. Silver's recent mean R is about 0. The [A3-P1] §4 prior (book-variants, 2021-10 -> 2026-09) gives -0.17 / 0.00 / -0.08 /
   +0.07 / +0.04 / +0.02 by year for 2021-26. The A3 run's own by-year means (a3-silver.json `components.G9_XAGUSD_eod`,
   other trade mechanics) differ in level, e.g. 2021 -0.016 and 2026 +0.010, and are near 0 too.

The A1 and A3 deltas come from different spans and baselines (2004- and 2008-), so they are not directly comparable.
**Running both (k = 1.4 plus silver) was never tested.** Its value and its fail rate are unknown and would need their own
pre-registered read.

## 3. Decision (owner)

The owner's tolerance selects the recommendation already given: **fvg-book v4 = v3 with stop_k 1.4 on H7 and G9 XAUUSD**,
used in both challenge phases. The A1 value assumed the funded stage back at k = 2.0 (v3). docs/architecture/trading-systems.json
holds v4. The demo account moves to v4 under DRAIN.

What the demo can and cannot show. ftmo-demo-01 runs the pilot demo profile: no profit target, no phases, no funded stage.
It keeps stop_k 1.4 with no switch back to 2.0. So the challenge measures above (funded <= 122 days, E[net] with a funded
stage at k = 2.0) are model expectations the demo record cannot produce. A real challenge would need its own switch to v3
at funding. The demo can check the per-trade expectations (vol-schedule.json `tails`, 5979 trades 2004 ->):

| per trade | k = 1.4 (v4) | k = 2.0 (v3) |
|---|---|---|
| mean R | 0.109 | 0.073 |
| sd R | 0.747 | 0.541 |
| stop-out share | 0.134 | 0.055 |
| worst loss, % of the balance | 1.39 | 1.18 |

## 4. Paper-twin note

The forward paper log (data/live/forward/fvg-paper.jsonl, local, untracked) has one G9 XAUUSD row with signal time
2026-10-03T09:42:40Z, logged by the 18:11:49Z scan with stop_k 1.4. That scan ran before the point-in-time fix: the row's
stop should be 2.0, because v2 was live then. From the fix on, the paper stop is the stop of the version assigned to the demo
account at each row's signal time (scripts/research/fvg_forward.py `stop_k_at`). Read that one row's stop as 2.0.
