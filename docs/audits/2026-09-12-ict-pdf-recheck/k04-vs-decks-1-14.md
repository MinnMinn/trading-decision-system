# Audit of knowledge/04-ttrades-core-A.md against source deck page images

> **Knowledge-path note (added 2026-09-17).** The `knowledge/` citations below use the FLAT numbered
> layout (`knowledge/07-wyckoff-advance.md`, or the `kNN` short codes) that was retired on 2026-09-17 in
> favour of one folder per methodology. They are left exactly as written: this document is a dated record,
> and re-pointing its citations would change what it says it checked. `knowledge/INDEX.md` carries the
> old→new map.

Method: read knowledge/04-ttrades-core-A.md in full (809 lines), then viewed every one of the 100
physical page PNGs (70 dpi) across the 11 decks and compared each page's diagram/text content
against the corresponding claims in the knowledge file. Citations below use the knowledge file's
own `File p<physical> (printed <n>)` format.

## Findings

| Deck | Page (physical) | Finding type | What the page shows | What knowledge/04 says (quote + section) | Severity |
|---|---|---|---|---|---|
| 4. Important_Liquidity_Levels | p5 (printed 3, "Weekly") | WRONG (citation) | The Weekly-page PWH/PWL diagram (same candle shape as `3. Liquidity p6` and `14. Daily_Bias p5`) carries **no day-letter labels** at all — the candles are unlabeled grey/light-green boxes. | §2.8: "`[diagram]` PWH/PWL shown on the Daily timeframe: five grey candles labelled M, T, W, TH, F are the previous week... `3. Liquidity p6 (4)`; `4. Important_Liquidity_Levels p5 (3)`; `14. Daily_Bias p5 (3)`." The M/T/W/TH/F label claim is true for 2 of the 3 cited pages (Liquidity p6 and Daily_Bias p5 do show the letters) but **not** for ILL p5, which is unlabeled. | Low (descriptive/citation only, no rule affected) |
| 3. Liquidity / 4. Important_Liquidity_Levels / 14. Daily_Bias | p6 (Liquidity, printed 4), p5 (Weekly, ILL/DB) | AMBIGUOUS | On the labelled PWH/PWL diagrams (`3. Liquidity p6`, `14. Daily_Bias p5`), the "Previous Weeks Low" line visually appears to touch the wick of an **unlabeled** candle immediately after the "F" (Friday) candle, not clearly the F or TH candle itself. | §2.8: "PWL the lowest wick (Thursday/Friday)." At 70 dpi the exact candle-to-line correspondence at the low end is hard to pin down with certainty; the claim may be slightly imprecise about which candle sets PWL. | Low |
| 3. Liquidity / 4. Important_Liquidity_Levels | p6 (Liquidity, printed 4); p6 (ILL, printed 4, "Daily"/PDH-PDL) | AMBIGUOUS (possible undercount) | The PDH/PDL 4H diagrams show roughly 8–9 visible candles before the reaction leg, of which only about 4 are the uniform grey "reference" color. | §2.8: "`[diagram]` PDH/PDL shown on the 4 Hour timeframe: **six** grey H4 candles = previous day." Visual count does not cleanly match "six." | Low (descriptive count, no rule affected) |
| 4. Important_Liquidity_Levels | p4 (printed 2, "Monthly") | AMBIGUOUS | Both stacked panels (top and bottom) show price tapping the Previous Month Low and then rallying up to/through the Previous Month High; the visual distinction between a wick-sweep-then-reversal (top) and a body-close-through continuation (bottom) that the general "two outcomes" framework claims is not crisply legible at this resolution — both panels look similar in overall shape. | §2.8: "`[diagram]` Each level slide shows two outcomes stacked: (top) the level is swept by a wick and price reverses away from it; (bottom) the level is traded through with body closes and price continues... `p4 (2)`, `p5 (3)`, `p6 (4)`." Confirmed clearly legible on p5 (Weekly) and p6 (Daily); harder to confirm on p4 (Monthly) specifically. | Low |
| 6. Intraday_Bias / 14. Daily_Bias | p5 (Intraday, printed 3, "Swing Points"); p6 (Daily Bias, printed 4, identical slide) | AMBIGUOUS | The bottom "Reversal Framed Off Swing Point" sequence ends with a green (bullish) candle at the point the label sits over; no clearly-drawn subsequent bearish candle follows within the frame. | §2.13 narrative (and the general reversal-then-opposite-direction pattern used elsewhere in the file) implies a bearish follow-through after a wick-above/close-below event at a swing high, but this specific page's final candle in the "Reversal" sequence reads as bullish/green, not clearly showing the bearish follow-through. | Low |
| 13. Inversion | p4 (printed 2) | WRONG | Page 4 shows **only a plain downtrend candle sequence with no horizontal gap lines at all** — no SIBI is marked on this page. | §2.25: "Step-by-step (Inversion deck, no text): **p4 — downtrend, SIBI marked** between candle 1 low and candle 3 high; p5 — a green candle closes through and above the SIBI..." The "SIBI marked" step does not occur on p4; the two horizontal gap lines (the SIBI) first appear together with the closing green candle on **p5**, i.e., "marked" and "closed through" happen on the same slide (p5), not on two separate slides (p4 then p5) as the file's step-by-step description implies. | Medium (a genuine step-mis-sequencing in the one page-by-page walkthrough the user asked to be checked closely; does not change any numeric rule, since §2.25's summary elsewhere and §3.6/R20 are still directionally correct) |
| 13. Inversion | p6 (printed 4) | AMBIGUOUS | p5 (printed 3) and p6 (printed 4) appear visually identical at 70 dpi — same candles, same two horizontal gap lines in the same positions. No visible rightward extension of the gap lines between the two pages. | §2.25: "p6 — the gap lines are extended right." Could not visually confirm this distinguishing feature between p5 and p6 at the rendered resolution. | Low |

## Pages specifically checked per the task's "special attention" list

- **`12. Fair_Value_Gaps` p7 (Stop Losses)** — confirmed accurate. Three stop placements verified in increasing distance from entry: FVG End (stop just below the FVG's lower/far edge), Order Block (stop below the low of the down-close candle(s) preceding the displacement leg), Swing (stop below the originating swing low, the widest of the three, drawn in red). Matches §2.24 and R22 exactly. No discrepancy found.
- **`9. OTE` p7–p9 ("Extra")** — confirmed accurate. p7 = same chart with anchor arcs removed; p8 = new red arcs placed on the retracement high (~0.705 touch) and the small swing low that followed; p9 = fib grid re-anchored on that smaller swing (1 at the retracement high, 0 at the new low), price bounces into ~0.5–0.62 of the child fib before a final sell-off. Matches §2.20 and R18 exactly.
- **13. Inversion 14 diagram pages (p4–p16)** — walked step by step; see the two findings above (p4 mis-sequencing; p6 extension unconfirmed). p9–p14 (Consequent Encroachment "respected" vs "failed" sequences) and p15–p16 (Old SIBI/BISI three-level stack) were verified accurate against §2.26 and §2.27.
- **"Candles: Consolidation / One Side / Both Sides" slide (`4. ILL p3`)** — confirmed accurate; matches §2.10 and the pattern table in §4 exactly, including both "One Side" sub-examples (high-only vs low-only).
- **`9. OTE` p6 alignment with PD arrays** — reasonably confirmed; the two black lines forming the bearish-FVG band sit in the region between the 0.62 and 0.705 levels as claimed, though exact pixel-level edge placement could not be verified with certainty at 70 dpi.
- **Two-outcome slides in `4. Important_Liquidity_Levels`** — Weekly (p5) and Daily (p6) confirmed clearly; Monthly (p4) flagged as AMBIGUOUS above.
- **Next Candle / Next Day Model slides** — confirmed identical between `6. Intraday_Bias p7` and `14. Daily_Bias p8` and accurately described (hollow/light-green anticipated-bullish candle, grey anticipated-bearish candle, blue PD-array staircase sequence).

## Overall assessment

No numeric rule, level, formula, or stop-placement claim in the knowledge file was found to be
factually wrong against the source images. All discrepancies found are either (a) citation-page
imprecision for a repeated diagram (M/T/W/TH/F labels present on 2 of 3 cited pages, not 3), (b) a
step-sequencing error in the one purely-diagrammatic, no-text 17-page Inversion deck (SIBI marked
on p5, not p4, contra the file's own step-by-step claim), or (c) resolution-limited ambiguity where
the 70 dpi renders do not permit a fully confident visual call. Text-quoted content (`[text]` tags)
was independently spot-checked against every page carrying prose and found to be verbatim-accurate
throughout.

## Pages verified

| Deck | Physical pages | Pages viewed |
|---|---|---|
| 1. Killzones.pdf | 5 | 5/5 (p1–p5) |
| 2. Position_Sizing.pdf | 9 | 9/9 (p1–p9) |
| 3. Liquidity.pdf | 8 | 8/8 (p1–p8) |
| 4. Important_Liquidity_Levels.pdf | 10 | 10/10 (p1–p10) |
| 6. Intraday_Bias.pdf | 8 | 8/8 (p1–p8) |
| 8. Discount__Premium.pdf | 8 | 8/8 (p1–p8) |
| 9. OTE.pdf | 10 | 10/10 (p1–p10) |
| 11. MSS_vs_Liquidity_Grab.pdf | 7 | 7/7 (p1–p7) |
| 12. Fair_Value_Gaps.pdf | 9 | 9/9 (p1–p9) |
| 13. Inversion.pdf | 17 | 17/17 (p1–p17) |
| 14. Daily_Bias.pdf | 9 | 9/9 (p1–p9) |
| **Total** | **100** | **100/100** |

All 100 physical pages across all 11 decks were viewed directly (image Read), not inferred.
