# Edge families F6 / F7 (overnight reversal after a US-session sell-off) -- discovery read (2026-10-03)

Pre-registrations: docs/plans/2026-10-03-edge-f6-overnight-reversal-preregistration.md and
docs/plans/2026-10-03-edge-f7-gold-overnight-reversal-preregistration.md (commit 4e551b6, before this read). Code
`scripts/research/edge_f6.py run --read discovery` at that commit; raw `docs/audits/2026-10-03-edge-f6-discovery.json`.
Only the DISCOVERY period was read (US500 / USTEC 2021-09 -> 2023-03, US30 2019-02 -> 2022-03, XAUUSD 2004-06 -> 2016-11).

## Verdict: 0 of 12 (F6) and 0 of 4 (F7) candidates -- both families end here

No test is BH-rejected; **every excess z is NEGATIVE**: in this data the night after a US-session sell-off is WORSE than the
other nights, i.e. continuation, not the reversal the source documents for E-mini futures. Per the pre-registration a family
with no candidate is not read further: the confirmation and exposed periods of F6 / F7 stay unread.

| family | symbol | theta | window | n | gross bp | net bp | excess z | p (1-sided) | MDE bp (80 %, alpha 0.10) | corr. with H7 + G9 |
|---|---|---|---|---|---|---|---|---|---|---|
| F6 | US500 | -0.5 | to 09:00 Berlin | 98 | -3.7 | -4.6 | -0.059 | 0.82 | 10.8 | -0.03 |
| F6 | US500 | -0.5 | to 09:30 NY | 98 | -8.9 | -9.7 | -0.092 | 0.89 | 17.2 | 0.13 |
| F6 | US500 | -1.0 | to 09:00 Berlin | 51 | -2.8 | -3.7 | -0.026 | 0.61 | 15.1 | 0.03 |
| F6 | US500 | -1.0 | to 09:30 NY | 51 | -8.0 | -8.8 | -0.079 | 0.78 | 21.4 | 0.08 |
| F6 | US30 | -0.5 | to 09:00 Berlin | 167 | -3.4 | -3.9 | -0.203 | 0.998 | 12.6 | 0.05 |
| F6 | US30 | -0.5 | to 09:30 NY | 166 | -6.4 | -6.9 | -0.281 | 1.000 | 17.3 | 0.10 |
| F6 | US30 | -1.0 | to 09:00 Berlin | 94 | +3.1 | +2.6 | -0.065 | 0.76 | 19.1 | 0.02 |
| F6 | US30 | -1.0 | to 09:30 NY | 93 | +5.1 | +4.6 | -0.117 | 0.85 | 25.2 | 0.05 |
| F6 | USTEC | -0.5 | to 09:00 Berlin | 101 | -6.7 | -7.5 | -0.099 | 0.95 | 13.4 | -0.02 |
| F6 | USTEC | -0.5 | to 09:30 NY | 101 | -14.6 | -15.3 | -0.110 | 0.94 | 21.1 | 0.12 |
| F6 | USTEC | -1.0 | to 09:00 Berlin | 56 | -5.0 | -5.8 | -0.045 | 0.70 | 17.7 | 0.03 |
| F6 | USTEC | -1.0 | to 09:30 NY | 56 | -16.7 | -17.4 | -0.117 | 0.89 | 25.6 | 0.03 |
| F7 | XAUUSD | -0.5 | to 09:00 Berlin | 621 | +1.4 | +0.7 | -0.030 | 0.86 | 4.8 | -0.06 |
| F7 | XAUUSD | -0.5 | to 09:30 NY | 621 | -4.0 | -4.7 | -0.054 | 0.94 | 7.9 | -0.14 |
| F7 | XAUUSD | -1.0 | to 09:00 Berlin | 321 | -0.4 | -1.1 | -0.061 | 0.94 | 7.4 | -0.05 |
| F7 | XAUUSD | -1.0 | to 09:30 NY | 321 | -7.4 | -8.1 | -0.097 | 0.98 | 11.0 | -0.14 |

(US30 at theta -1.0 nets +2.6 / +4.6 bp, but the non-trigger nights do better still: negative excess, not a reversal.)

## Reading

- **F6 (US indices): not found at this power.** The minimum detectable effect is 11-26 bp per night on 51-167 events; the
  published reversal could be smaller than that. But the point estimates have the WRONG sign in 12 of 12 tests, so a larger
  sample is unlikely to turn this into an edge on these CFDs. Possible reasons, none tested: the CFD night price is the
  broker's derivation from futures; 2019-2023 is short and contains 2022's trending sell-off; the paper's trigger is signed
  order flow, here only price.
- **F7 (gold): an informative null.** With 321-621 events and an MDE of 5-11 bp, US-session gold sell-offs CONTINUE into the
  next night (negative excess in all four tests) -- the same trend-continuation character as H7 / G9 / AMD3. The transfer of
  the inventory mechanism to gold is not supported.
- Report-only, NOT a finding (post hoc, decides nothing): the unconditional window nets on US30 (+2.9 / +5.1 bp, t 1.2 / 1.5)
  and on gold to 09:00 Berlin (+1.8 bp, t 1.7) are not significant; picking them now would be selection after the fact.
- Correlations with the base were measured as agreed: F7's are negative (-0.05 to -0.14), F6's about 0 to +0.13 -- moot
  without an edge.

Experiment budget: 16 tests, discovery period only; nothing else read. The reframes' B1 / B2 are closed as null.
