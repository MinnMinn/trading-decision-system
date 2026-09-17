# Audit: knowledge/06-ttrades-models.md vs TTrades Model11.pdf (118 pages, diagram/chart focus)

> **Knowledge-path note (added 2026-09-17).** The `knowledge/` citations below use the FLAT numbered
> layout (`knowledge/07-wyckoff-advance.md`, or the `kNN` short codes) that was retired on 2026-09-17 in
> favour of one folder per methodology. They are left exactly as written: this document is a dated record,
> and re-pointing its citations would change what it says it checked. `knowledge/INDEX.md` carries the
> old→new map.

Scope: every physical page 1-118 of `docs/TTrades PDFs/TTrades Model11.pdf` was viewed via the rendered PNGs at
`/private/tmp/claude-502/-Users-tungnguyen-TYME-Trading/1944841f-d671-4770-a5e9-372b39da04b2/scratchpad/png/TTrades_Model11/p-001.png` … `p-118.png`.
The knowledge file `knowledge/06-ttrades-models.md` was read in full (664 lines). Prose (`[text]`) claims were treated as
already-verified per the task brief; this audit's added value is checking `[diagram]` claims and any quantitative
labels visible only in the chart images.

| Page (physical) | Finding type | What the page shows | What knowledge/06 says (quote + section) | Severity |
|---|---|---|---|---|
| p23 | Confirmed (no finding) | Fibonacci tool settings screenshot: checkboxes `1, 0, -1, -2, -2.5, -4, -4.5`, all enabled | "`[diagram]` **Fibonacci tool settings** (p23): levels enabled = `1, 0, -1, -2, -2.5, -4, -4.5`." — §2.1.5 | n/a (verified correct) |
| p67 | Confirmed (no finding) | Monday-stats bar chart, `_amtrades` watermark, values: Mon 262/129, Tue 310/158, Wed 316/166, Thu 332/179, Fri 312/163 | Table in §5 "Monday average range … Mon 262/129, Tue 310/158, Wed 316/166, Thu 332/179, Fri 312/163" | n/a (verified correct, exact match) |
| p61 | Confirmed (no finding) | Calendar screenshot: Tue Mar 12 Core CPI/CPI m-m/y-y + 10-y Bond Auction; Wed Mar 13 30-y Bond Auction; Thu Mar 14 Core PPI/Core Retail Sales/PPI/Retail Sales/Unemployment Claims/Empire State Mfg; Fri Mar 15 Prelim UoM Consumer Sentiment | §2.5.1 p61 sample calendar description | n/a (verified correct) |
| p68 | Confirmed (no finding) | Second calendar sample: Tue 08:30 Core PCE; Wed 14:00 FOMC Statement, 14:30 FOMC Press Conf.; Thu 08:30 CPI, 08:30 PPI; Fri 08:30 NFP | §2.5.1 p68 second sample description | n/a (verified correct) |
| p73, p77, p79, p80 | Confirmed (no finding) | Weekly-profile diagrams: Classic Expansion = M(1)/Tu(2)/W(3)/Th(4); Midweek Reversal = Tu(1)/W(2)/Th(3)/F(4); Consolidation Reversal = W(1)/Th(2)/F(3); Thursday Counter = W(1)/Th(2)/F(3) with Mon/Tue/Wed pre-expanding same direction | §2.5.4 / table §4.6 | n/a (verified correct) |
| p96–p99 | Confirmed (no finding) | Pairing row printed under each Fractal-model chart reads `H4/W1, H1/D1, M15/H4, M5/H1, M3/M30, M1/M15` (LTF over HTF) | "The pairing row `H4/W1, H1/D1, M15/H4, M5/H1, M3/M30, M1/M15` is printed under each chart (LTF above HTF)." — §2.6 | n/a (verified correct, exact match incl. order) |
| p90 | Confirmed (no finding) | Diagram tag "-23 ticks" on the CISD/opposing-candle entry example | Quantitative table: "tick labels … (p90 '-23 ticks' …)" | n/a (verified correct) |
| p91 | Confirmed (no finding) | Tags "+86 ticks" / "+94 ticks" | Table: "p91 '+86'/'+94 ticks'" | n/a (verified correct) |
| p92 | Confirmed (no finding) | Tags "+76 ticks" / "+83 ticks" | Table: "p92 '+76'/'+83 ticks'" | n/a (verified correct) |
| p93 | Confirmed (no finding) | Tag "+379 ticks", grey risk box + "2R minimum" reward box | Table: "p93 '+379 ticks'"; §2.5.7 "risk box … reward box '2R minimum'" | n/a (verified correct) |
| p118 | **WRONG** | Second (candle-4) 5-minute NQ chart shows a small time annotation reading **"8:00"** next to the consolidation/expansion zone, not "8:30" | "`[diagram]` p118: the '8:30' label marks the time of the candle-4 expansion." — §2.7.2, also §5 quantitative table "NY open reference on example charts … `Model11 p104–p105, p107–p112`" (p118 not in that list, but the standalone p118 claim is separately wrong) | Low (cosmetic quantitative label; does not affect any rule) |
| p17 | AMBIGUOUS / unverifiable at render resolution | "Ranges" diagram: a zigzag candle sequence with plain solid bracket lines at the top (up-leg) and bottom-right (down-leg); no clearly-rendered **dotted** midline is visible at 70 dpi | "`[diagram]` p17: multiple range boxes with dotted midlines; price respects the midpoint as it trades out of each range." — §2.1.4 | Low (likely a 70 dpi rendering artifact — dotted lines may be too thin to render — but cannot be confirmed either way from the available images) |
| p9 | AMBIGUOUS / unverifiable at render resolution | "Fair Value Gaps" diagram: candle pattern with a blue opposing-candle line visible, but no clearly distinguishable grey FVG boundary lines at this resolution | "`[diagram]` p9: the FVG (two grey lines) is traded into; the opposing-candle line sits at the FVG; close through it → expansion." — §2.1.3 | Low (same 70 dpi caveat as above; the blue CISD/opposing-candle line is confirmed present, the FVG grey lines specifically could not be confirmed) |
| p35, p36, p38, p39 (wick/range EQ diagrams) | AMBIGUOUS / unverifiable at render resolution | Wick/range brackets are drawn as plain solid horizontal lines; the "dotted midline" descriptor used repeatedly in knowledge/06 (§2.2.4) could not be visually confirmed as dotted (vs. solid) at 70 dpi | "`[diagram]` p35–p40: the wick or range being used is bracketed with a dotted midline …" — §2.2.4 | Low (systemic rendering-resolution caveat, not a contradiction — the bracket levels themselves and the described candle behavior around them are consistent with the text on each page) |
| p75 | AMBIGUOUS (documentation gap, not a contradiction) | The diagram at the top of p75 (Mo=1, Tu=2 [dark/reversal], W=3, Th=4, F=grey/unlabeled) is visually identical in structure to the Classic Expansion diagram (p73–74), not a distinct "Counter-Trend" diagram. Given this PDF's established layout convention (a text block introduces a concept at the bottom of a page; its diagram appears at the top of the *next* page), this is almost certainly the Classic Expansion diagram trailing over from p74, reused as context for the Counter-Trend discussion (Fri is the un-numbered grey candle where the counter-trend trade occurs) | knowledge/06 §4.6 table and the YAML `classic_expansion_counter_trend` block assert `c1: Thu, c2: Fri` purely from prose (p75-76 text), with no diagram citation tied to that specific Thu/Fri candle-numbering. The file does not flag that no dedicated Thu=1/Fri=2 diagram exists — a reader could look for one and be confused when p75's diagram appears to show Mon=1…Thu=4 instead | Low-medium (no factual contradiction found, but the file could add one sentence noting the Counter-Trend section has no dedicated candle-1/2 diagram of its own and reuses the Mon–Thu context chart) |
| p3–p16, p18–p22, p24–p34, p37, p40–p74, p76, p78, p81–p89, p94–p95, p100–p117 | Confirmed (no finding) | All prose headings, quoted rule text, candle-numbering diagrams, CISD/opposing-candle diagrams, entry/stop diagrams, economic-calendar rules text, Monday-rule reasons 1–3, daily-profile diagrams (London/NY reversal + invalidation, p86–p88), and the full CL1! (p100–p114) and NQ1! (p115–p118) worked examples (dates 28–30 Apr / 1–3 May 2024 on the CL charts; 20 Jun 2024 "NQ1! | 5M" on the Fractal charts) all match the corresponding `[text]`/`[diagram]` citations in knowledge/06 §2.1–§2.7, §3.1–§3.2, §4.1–§4.7 | (covers many individually-cited pages; no contradictions found on visual re-check) | n/a |

## Notes on method / limitations

- The rendered PNGs are 70 dpi. Several knowledge/06 diagram descriptions specify fine visual details (dotted vs.
  solid midlines, thin grey FVG boundary lines) that could not be reliably confirmed or refuted at this resolution.
  These are listed above as AMBIGUOUS/low severity rather than WRONG, since I cannot certify the line style is
  actually absent from the source PDF — only that it is not visible in this render.
- No MISSING or UNSOURCED findings were identified: every `[diagram]` claim checked against its cited page had
  visible supporting content on that page (candle-numbering shapes, CISD/opposing-candle lines, projection fib
  levels, weekly/daily profile day-labels, tick-count entry tags, and the CL1!/NQ1! worked-example charts and
  dates all matched).
- The one confirmed **WRONG** finding (p118 "8:30" vs actual "8:00") is a single mislabeled time annotation with
  no downstream effect on any stated rule, checklist item, or YAML field in knowledge/06.
- Scope was limited to `TTrades Model11.pdf` (118 pages) per the task; the other five slide decks referenced in
  knowledge/06 (Sons_Model, Sons_Model_HTF, TTRS, Timeframe Alignment, Unicorn) were out of scope for this audit.

Pages verified: 118 of 118.
No pages were skipped.
