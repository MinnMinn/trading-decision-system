# Audit: knowledge/05-ttrades-core-B.md vs 13 TTrades PDF decks (diagram pages)

> **Knowledge-path note (added 2026-09-17).** The `knowledge/` citations below use the FLAT numbered
> layout (`knowledge/07-wyckoff-advance.md`, or the `kNN` short codes) that was retired on 2026-09-17 in
> favour of one folder per methodology. They are left exactly as written: this document is a dated record,
> and re-pointing its citations would change what it says it checked. `knowledge/INDEX.md` carries the
> old→new map.

Scope: verify every page image of the 13 decks against the corresponding claims in `knowledge/05-ttrades-core-B.md`. Text-layer claims were already verified per the task brief; this audit focuses on the diagram pages. All 126 physical pages across the 13 decks were viewed (13 parallel sub-audits, one per deck).

## Findings

| Deck | Page (physical) | Finding type | What the page shows | What knowledge/05 says (quote + section) | Severity |
|---|---|---|---|---|---|
| 16. CISD | p3 vs p4 | AMBIGUOUS | At 70 dpi both pages render as visually near-identical candle sequences (bearish diagram top, bullish diagram bottom): a small consolidation under/over the "Important Level" dashed bracket, then a single opposite-colour candle immediately preceding the "CISD" line, then the reversal candles. No visual distinction between a "single last candle" (p3) construction and a "consecutive same-colour run of 2+ candles" (p4) construction — both pages appear to show only ONE opposing-colour candle immediately before the CISD line, not a run. | §2.3 bullet 4: "Variant (p4): when the final leg into the level is a **series of consecutive same-colour candles**, the CISD line is drawn at the open of the **first candle in that series**... — `16. CISD p4`." Also §6 item 1 and `change_in_state_of_delivery.detection_criteria` "variant B (p4): run length >1" in the YAML block. | High |
| 17. Orderblocks | p6 (printed 4) | AMBIGUOUS | Same visual grammar as p3 (dashed stop-raid line + OB line at open of down-close candle), but no "Important Level" text label appears anywhere on this page. | §2.5: "It forms at an 'Important Level' after a stop raid of a prior swing (dashed line). — `p3 (1)`, `p6 (4)`." The p6 citation implies the label is shown there too; only the stop-raid dashed line and OB line actually recur. | Low |
| 18. Market_Structure_Shift | p4 (printed 2) | MISSING | Below the MSS bracket/confirmation, the diagram also marks a second liquidity sweep with a yellow ▲ triangle at the bottom of the subsequent down-leg (a low swept during continuation). | §2.2 / `market_structure_shift` describe only the ▼ raid-high marker and the MSS bracket on the swing low; the continuation ▲ sweep marker is not mentioned. | Low |
| 18. Market_Structure_Shift | p5 (printed 3) | MISSING | Mirror bullish diagram also shows a ▼ triangle marking a raid of an old high during the up-move continuation, after the confirming green displacement candle. | §2.2 diagram description only covers "price runs below the HTF Level, then a green displacement candle closes above the swing high preceding the drop" — the extra ▼ continuation marker is not mentioned. | Low |
| 19. BreakerBlocks | p2 (TOC) | AMBIGUOUS | TOC lists only 3 numbered entries: "1 Fair Value Gaps", "2 Breaker Blocks", "4 Unicorn" — no "3", no "5"; "Stop Losses" and "OB vs BB" (printed page 16, used twice) are not listed in the TOC at all. | §1 source-table row 4 phrasing "Sections (from TOC): Fair Value Gaps, Breaker Blocks, Unicorn, Stop Losses, OB vs BB" implies all 5 are TOC entries; the TOC image itself shows only 3 partial entries. The underlying content-page citations (p18, p19) are still correct — only the "(from TOC)" framing overstates the TOC page. | Low |
| 20. Mitigation_Blocks | p6 (printed 4) | AMBIGUOUS | Two thin horizontal lines near the small consolidation candles; at 70 dpi neither is confidently orange — both read as grey/black. | §2.9: "a small bounce high (orange line); a green displacement candle closes above that high leaving an FVG (two lines)" implies 3 distinct lines (1 orange + 2 FVG); only 2 lines are visually distinguishable, neither confidently orange. | Low |
| 20. Mitigation_Blocks | p10 (printed 8) | AMBIGUOUS | A second line segment at the top of the grey box is visually much fainter than the clearly-blue line at the box bottom (present since p9) — its colour cannot be confidently confirmed as blue vs. the box border itself. | §2.9: "second blue line at the top as price passes through — p10 (8)." (File's own §6 conflict item #4 already flags this whole two-blue-line sequence as inference.) | Low |
| 21. SMT | — | none | All 9 content pages verified; asset-A/asset-B divergence direction correct on every page; the p4+p5, p7+p8, p10+p11 page-pairs are genuine before/after-SMT-line build-ups, not duplicates or errors. | §2.10, R9, `smt_divergence` — accurate throughout. | — |
| 22. Power_Of_Three | p4 (printed 2) | (non-finding, noted) | The "beyond the open" manipulation detail is not literally visible on p4's abstract box-only diagram; it is directly evidenced on p5 instead. | §2.11 cites p4 for AMD box "Manipulation... beyond the open" — concept correct, citation slightly imprecise (not flagged as WRONG). | Low |
| 23. Standard_Deviation_Projections | p5 (printed 3) | WRONG | The swept high is marked by a plain black dashed line; no orange-coloured line appears anywhere on the page. | §2.12: "the orange line marks the low of the manipulation leg (where the sweep started) — `23. STD p5 (3)`." | Low |
| 23. Standard_Deviation_Projections | p9 (printed 7) | WRONG | The -4 level line is drawn in the same plain grey/black style as the other fib levels; no orange colouring visible. | §2.12: "Max Expansion: -4 (orange line) is the maximum expected expansion. — `23. STD p9 (7)`." | Low |
| 24. AMD_STD | p4 (printed 2) | WRONG | AMD boxes (green/pink/blue) over a real candle sequence — same content type as p3 and p5. No O-L-H-C lettering, no single-candle expansion, no dashed open-line anywhere on this page. | §2.11: "OHLC / OLHC: ... Dashed line drawn at the candle's open. — `22. PO3 p3 (1)`; `24. AMD_STD p4 (2)`." The OHLC/OLHC concept does not appear anywhere in the AMD_STD deck — it belongs only to the PO3 deck. | Low (but a genuine mis-citation; see summary) |
| IRL-ERL | p5 (printed 3) | AMBIGUOUS | The drop after the top stops visibly short of the ERL dotted line (candle lows sit above it) — the sketch does not clearly show price returning all the way to the ERL. | §2.13 / `irl_erl_alternation`: "drops leaving a bearish FVG (IRL) and **reaches the ERL** (dashed line at the range low) — p5 (3)." | Low |
| IRL-ERL | p9 (printed 7) | AMBIGUOUS | Arrow's tail sits near the most recent swing high, not inside/at the IRL zone; it points down-right to the new ERL. More precisely "from the recent high to the new ERL." | §2.13 / R20: "arrow from the IRL to the new ERL — p9 (7)." | Low |
| MSS_vs_CISD | p3 (printed 1) | AMBIGUOUS | Page shows only ONE diagram (bearish MSS case); no bullish/mirror diagram on this page. | §2.2 cites `MSS_vs_CISD p3 (1)` at the end of a sentence covering both "Bearish MSS: ... Bullish MSS: ...", readable as implying p3 shows both. | Low |
| Relative_Strength_ES.NQ | — | none | All 4 content pages' quotes verified word-for-word (including the "My Theory" sentence); ratio-direction table and SMT diagram both match. | §2.14, R24 — accurate throughout. | — |
| Silver_Bullet_AM | p3 (printed 1) | UNSOURCED | The 9:30 tick has no text annotation beyond the number "9:30" — nothing labels it as "NY equities open". | §2.15: "with **9:30** marked as the reference start (NY equities open)" — the "(NY equities open)" gloss is the author's own inference, not printed on the slide. | Low |

No findings for: SMT (21), Power_Of_Three (22, aside from the noted citation imprecision), Relative_Strength_ES.NQ.

## Pages verified

| Deck | Pages verified |
|---|---|
| 16. CISD | 5/5 |
| 17. Orderblocks | 9/9 |
| 18. Market_Structure_Shift | 6/6 |
| 19. BreakerBlocks | 20/20 |
| 20. Mitigation_Blocks | 15/15 |
| 21. SMT | 12/12 |
| 22. Power_Of_Three | 7/7 |
| 23. Standard_Deviation_Projections | 11/11 |
| 24. AMD_STD | 10/10 |
| IRL-ERL | 11/11 |
| MSS_vs_CISD | 7/7 |
| Relative_Strength_ES.NQ | 7/7 |
| Silver_Bullet_AM | 6/6 |
| **Total** | **126/126** |

## Findings tally

- Total findings: 14 (across 126 pages / 13 decks)
- By type: AMBIGUOUS 8, WRONG 3, MISSING 2, UNSOURCED 1
- By severity: High 1, Low 13
- Zero-finding decks: SMT, Relative_Strength_ES.NQ (Power_Of_Three has only a non-flagged citation-precision note)
