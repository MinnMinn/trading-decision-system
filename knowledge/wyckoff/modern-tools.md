# Wyckoff and Modern Tools — Nguyễn Vũ Tuấn Hải (full-book synthesis)

> Previous filenames: `08-wyckoff-and-modern-tools.md` (2026-09-10 to 2026-09-17), and `07-…` before that. The numeric prefixes are gone — see `knowledge/INDEX.md` for the full old→new map, which is what older audit documents under `docs/audits/` still refer to.

Synthesis of the Vietnamese-language book **"Wyckoff and Modern Tools: Advanced Trading Techniques with FRD, Volume Profiles, Footprint, and Delta"** by **Nguyễn Vũ Tuấn Hải** (Nhà Xuất Bản Thế Giới), from all **374** photographed pages (`docs/Wyckoff and Modern Tools/`, staged as `.cache/wyckoff-pages/001.jpg`–`374.jpg`). Ingestion is complete — pages `126.jpg`, `130.jpg`, `365.jpg`, initially missing from the first extraction pass, were later recovered from the original iOS photo library and folded in. This file was assembled by 10 parallel extraction passes (each reading its page range visually and citing page-by-page) plus one gap-fill pass, recorded in `knowledge/.wyckoff-parts/part-01..10-*.md`, then merged and reorganized thematically here. Every claim below traces to a physical page citation `(WMT pNNN)` = `.cache/wyckoff-pages/NNN.jpg`. Nothing below is added from outside the photographed pages; where the extraction passes flagged an ambiguous digit, an unresolved acronym (e.g. "EOM", "SOT" is never expanded in-book beyond its behavioral description), or a small-print table cell as uncertain, that flag is preserved here rather than silently resolved.

**Language note:** the entire book is in Vietnamese. All prose below is translated/paraphrased for this knowledge base; Vietnamese terms are kept in parentheses on first use where the book coins or specially defines them. English trading terms (Spring, Upthrust, Footprint, Delta, Trading Range, POC, VAH/VAL/LVN, etc.) appear untranslated in the original and are reproduced as-is.

**Pagination artifact:** the printed folio badge inside each photo runs ahead of the filename number — by +1 through roughly file 353, and irregularly (+2, and some unnumbered divider pages) from file 354 onward. Citations here always use the **filename number**, never the printed badge.

**Relationship to sibling files:** `01-03` (Footprint course PDFs) and `04-06` (TTrades PDFs) are separate source documents by different authors/platforms; do not merge terminology across them without checking for conflicts (see §8 below for the main cross-source note). This book is a single continuous 12-chapter work, not a slide deck — treat it as the deepest single source on classical-Wyckoff-to-order-flow bridging in this knowledge base.

---

## 1. Book structure (as printed in its own Table of Contents, WMT p002–p006)

- **Part I — General Introduction to the Wyckoff Method** (Chs. 1–2): three laws, price cycle, market phases, Trading Range, Spring/Upthrust scenario taxonomy.
- **Part II — Modern Volume-Analysis Tools** (Chs. 3–5): Volume Profile (auction theory, VAH/VAL/LVN/VPOC), Footprint Chart (order book, Time & Sales, POC, R/H, R/L, Imbalance, Stacked Imbalance, exhaustion/absorption/initiative), Delta & Cumulative Delta.
- **Part III — Tape Reading** (Chs. 6–7): history, Effort-vs-Result rule, three reading methods (Bar by Bar, Analog Bar, Swing by Swing), each with a numbered-case framework and worked examples.
- **Part IV — Combining Wyckoff with Modern Tools** (Chs. 8–12): a 5-step operating method (context → Spring/Upthrust ID → bias → zone analysis via Volume Profile → entry-signal analysis via Footprint/Delta), order entry & position management, and 10 full case studies.
- Conclusion, Appendix 1 (Trading Signal Checklist), List of Figures/Tables/Appendices, Index.

The author explicitly states the book's scope is narrower than "all of Wyckoff": he focuses on **one method** — identifying and trading the important positions within a Trading Range (Spring/Upthrust) — not trend-following, mean-reversion, or seasonal strategies (WMT p010). He also states markets he intends this for: stocks, forex, and crypto (WMT p008), though **the routing rules for this project forbid trading Forex** — treat that part of the book's stated scope as inapplicable here.

---

## 2. Part I — Wyckoff Foundations (Chapters 1–2)

### 2.1 Three Laws (WMT p015–p016)
- **Law of Supply and Demand:** price is set by the balance/imbalance of supply and demand; Wyckoff paid special attention to zones where supply or demand becomes exhausted, producing a major trend change.
- **Law of Cause and Effect:** cause = accumulation or distribution over a period; effect = the subsequent large price move (a long accumulation → strong uptrend; a long distribution → deep decline).
- **Law of Effort vs. Result:** the correlation between volume (effort) and price movement (result). A large price move backed by high volume confirms a genuine supply/demand shift; a price move *not* backed by proportional volume signals weakness/unsustainability. This law is the operative engine behind nearly every later chapter's Footprint/Delta/Tape-Reading signal read.

### 2.2 Wyckoff Price Cycle and strong-hand/weak-hand behavior (WMT p016–p019)
Four phases in sequence: **Accumulation → Markup (uptrend) → Distribution → Markdown (downtrend)**, driven by "strong hands" (Composite Man / institutions) preparing and executing campaigns against "weak hands" (uninformed retail, prone to FOMO — buying tops, selling bottoms). Stage-by-stage behavior (WMT p018):
1. Sharp decline: weak hands panic-sell; strong hands accumulate cheap.
2. Price starts rising: strong hands keep buying; weak hands hesitate/sell remainder; late in the up-leg, good news appears and weak hands FOMO-buy regardless of price while strong hands prepare distribution.
3. Price high: strong hands distribute without disturbing price much, using weak-hand buying demand to offload.
4. Price falls: strong hands exit at the first sign of a downtrend; weak hands still believe and buy the "dip."

### 2.3 Shortening of the Thrust — SOT (WMT p019–p022)
SOT = progressively shorter/shallower price swings on successive attempts in the same direction, especially failure of a third push — an early reversal warning. Combines with volume: SOT **with increasing volume** in a downtrend shows emerging buying demand (effort/result mismatch, bullish tell); SOT **with decreasing volume** shows the pushing side running out of participants (also often a reversal tell). Symmetric logic applies to uptrend SOT (bearish tell). SOT recurs throughout the book as **the** effort/result mismatch pattern applied at the swing level, referenced explicitly in the Chapter-9/10/11 case-study checklists and in essentially every Chapter-12 case study's exit logic (e.g. WMT p252, p262, p273, p276, p287, p304).

### 2.4 Trading Range (WMT p023–p026)
Defined as price oscillating between a support and resistance level without a clear trend — "the box" / "sideways price zone," used interchangeably by the author. Key property: **fractality** — Trading Ranges nest inside larger ones across timeframes; the same behavioral rules apply at every scale. Citing James F. Dalton's *Mind Over Markets* (explicitly named, WMT p232): markets spend **70–80% of their time ranging**, which the author gives as the reason his entire Part IV method targets Trading-Range trading, not trend-following.

### 2.5 Five-step market-phase structure (WMT p026)
Every phase (accumulation/distribution/reaccumulation/redistribution) unfolds through: (1) stop the prior trend, (2) accumulate the cause, (3) test the opposing side (Spring/Upthrust), (4) initiate the new trend, (5) confirm the trend. The book deliberately omits classic Wyckoff-Advance event labels (PS/SC/AR/ST/SOS/LPS/UT/UTAD) from its own prose description of this structure (while still printing them on the reproduced schematic diagrams, explicitly credited to the author's separate prior book *Wyckoff Advance*, WMT p027/p029) — it treats Spring/Upthrust as the load-bearing concepts for the rest of the book, not the full classic schematic vocabulary.

Four phase types (WMT p025–p032): **Accumulation** (after a decline; large investors buy without pushing price up), **Distribution** (after a rise; large investors sell without pushing price down), **Reaccumulation** and **Redistribution** (smaller versions occurring as a pause *within* an already-established trend, rather than after a full reversal). The book states distinguishing reaccumulation-vs-distribution (and redistribution-vs-accumulation) correctly is one of the hardest parts of this method, but says misclassification is not fatal — later steps (Spring/Upthrust ID, Volume Profile zone, Footprint entry-signal read) reduce the risk (WMT p236).

### 2.6 Spring — three types (Ch. 2 §2, WMT p036–p049)
Spring = a rapid recovery after price suddenly breaks below Trading-Range support; signals seller exhaustion and buyer control emerging; often a deliberate "trap" for premature sellers.

| Type | Volume at the break | Price reaction | Confirmation |
|---|---|---|---|
| **Type 1** | Low — no fresh selling pressure | Quick return into the range | Recovery/close back above support |
| **Type 2** | Moderate — sellers present but not overwhelming | Returns to range fairly quickly | One or more retests around the broken support |
| **Type 3 ("Shake Out")** | High — panic-selling, but high volume also shows market-maker absorption | May keep falling briefly, but long-wick "fish-tail" candles then a sharp reversal | Reversal on high volume after the break; e.g. a wickless marubozu candle negating prior supply |

(Table per Bảng 2.1, WMT p049; worked real-market examples across the three types include CTG stock, RNDR/USDT, FPT stock, RDNT/USDT, ACB stock (weekly), CHZ/USDT — WMT p038–p048.)

### 2.7 Upthrust — three types (Ch. 2 §3, WMT p050–p064)
Upthrust = an unsuccessful challenge of Trading-Range resistance; signals the market can't sustain the up-move; usually the start of a new downtrend.

| Type | Volume at the break | Price reaction | Confirmation |
|---|---|---|---|
| **Type 1** | Increases at the touch — false-breakout traders piling in | Sharp reversal back inside/below the range | Close below resistance, unable to hold the new high |
| **Type 2 (UTAD — Upthrust After Distribution)** | Very high at the extreme — heavy distribution participation | Fast, deep reversal | Not just a turn but a deep decline after the new high; may be followed by a separate "UTAD Test" retest (not always present) |
| **Type 3 (Minor UTAD)** | Strong but not as high as Type 2 | Moderate pullback, sellers controlling but not overwhelming | Price fails to exceed the prior (higher) structural high and starts declining |

(Table per Bảng 2.2, WMT p064; worked examples: ETH/USDT 15m, BAF stock daily, ETH/USDT 3m, NLG stock 60m, BTC/USDT 5m, ACB stock daily — WMT p051–p063.)

### 2.8 Stated limitations of Spring/Upthrust scenarios alone (WMT p064–p066)
The author lists why pattern-recognition alone is insufficient: (1) volume-change detail is hard to pin from traditional volume indicators; (2) candlestick charts don't show buy/sell distribution at specific prices; (3) Spring/Upthrust can be confused with a genuine continued breakdown/breakout without order-flow confirmation; (4) candles/traditional volume give no insight into market psychology at specific levels; (5) without price/volume detail, stop-loss placement is imprecise, hurting realized R:R. This is the book's own stated motivation for Parts II–III (Volume Profile, Footprint, Delta, Tape Reading).

---

## 3. Part II — Modern Volume-Analysis Tools (Chapters 3–5)

### 3.1 Auction Theory and Volume Profile (Ch. 3, WMT p069–p079)
Citing **James Dalton, Robert Bevan Dalton, Eric Jones, *Markets in Profile*** (WMT p070, book's own citation): an auction is composed of price, time, and volume. When both sides agree on a price band (**Value Area**), moves away from it meet unwillingness from the other side and volume drops until price reverts ("reversion to the mean," basis of mean-reversion strategies); but when a move away from Value Area *attracts* more volume, that is "trend-following" territory, and reversion-based trades fail. A Trading Range breakout marks the start of a new auction seeking a new equilibrium.

**Volume Profile terms used throughout the rest of the book:**
- **Value Area (VA), VAH / VAL** — the price band holding a given percentage (default 68.2%) of traded volume; VAH/VAL often coincide with (or sit close to) the Trading Range's own extremes.
- **VPOC** — Volume Point of Control (highest-volume price within the profile).
- **LVN (Low Volume Node)** — the low-volume zone just outside VAH/VAL; the book treats LVN as (a) a magnet/continuation-test zone and (b) the preferred stop-loss placement zone, because price rejection there is high-probability.
- **HVN (High Volume Node)** — referenced in the figure index (Hình 3.4-area) as the counterpart to LVN, not separately elaborated in the extracted prose.

**Operative rule used throughout Ch. 8–12:** near VAL → look for a **Spring** (a level the market previously found attractive to buy); near VAH → look for an **Upthrust** (a level that previously met strong resistance). When a Wyckoff Spring/Upthrust coincides with VAH/VAL, that is treated as independent confluence, not double-counting, in the book's own framing (WMT p244–p249).

### 3.2 Footprint Chart mechanics (Ch. 4, WMT p080–p134)
- **Order types:** passive/resting orders (Buy/Sell Limit; VN-stock LO/ATO/ATC) vs. active/aggressor orders (Market; VN-stock MP/MOK/MAK/MTL); Stop and Stop-Limit orders are classed as active once triggered (WMT p081–p083).
- **Order Book vs. Time and Sales:** Order Book shows *pending* liquidity (Best Bid/Best Offer/Spread); Time and Sales ("the tape") shows *executed* trades and, per the book, cannot be manipulated the way resting orders can (WMT p084–p088).
- **Footprint formation:** built directly from Time and Sales; an active buy hitting a resting sell posts to the Footprint's ASK (right) column at that price; an active sell hitting a resting buy posts to the BID (left) column (WMT p089–p097, with a fully worked step-by-step example across 4 order-book snapshots).
- **POC (Point of Control):** the highest-volume price level within one Footprint bar; **Multiple POC** (several stacked/level POCs) flagged as likely institutional accumulation/distribution and likely S/R + stop-loss/take-profit clustering (WMT p100).
- **R/H and R/L (Ratio High / Ratio Low):** ratio between the two highest ASK-column values (R/H) or two lowest BID-column values (R/L) in a bar; small-volume cells at the bar's price extremes (especially right after a large-volume cell) suggest the last aggressive buyer/seller has capitulated — a reversal tell, strongest when paired with an Imbalance signal (WMT p102–p104).
- **Unfinished vs. Finished Auction:** a bar is a "finished auction" (blue) when BID or ASK volume at the extreme price is zero; "unfinished" (green) when both sides still show volume at the extreme — unfinished levels act as a "price magnet" the market tends to retest (WMT p104–p106).
- **Imbalance:** a significant BID-vs-ASK volume skew, compared **diagonally** (not horizontally) across adjacent price levels. Imbalance-ratio thresholds vary by product: gold/oil CFDs ~3–4×; crypto potentially higher (adjust per token liquidity); stocks ~3× (300%) as a near-complete, high-liquidity market (WMT p107–p109). **This is the book's own explicit, product-specific threshold guidance — directly relevant to this project's XAUUSD/XAGUSD/USOIL/UKOIL and crypto instruments.**
- **Stacked Imbalance:** ≥2 adjacent imbalanced cells (user-configurable "Zone Count"); treated as a likely support/resistance threshold. A stacked imbalance is judged **valuable** only when three factors converge (WMT p111–p112):
  1. **Context** — it must occur at a real trading-zone location, e.g. explicitly **at a Wyckoff Spring or UTAD, or at a double-top/double-bottom neckline break** (the book's own words — this is the single explicit bridge between classic Wyckoff schematic vocabulary and the order-flow toolset in Chapter 4).
  2. **Position** — ideally near the start of the candle (where large/informed players tend to transact), not the close.
  3. **Volume** — the higher and more sustained, the stronger; especially strong when it coincides with the POC (a rationale the book gives for placing stops there).
- **Why price moves (WMT p112–p117):** (1) active/aggressor trades matching resting liquidity; (2) imbalance in trading *intent* — large resting-order changes (adding/pulling liquidity) shifting Best Bid/Offer even without a large executed trade. A worked example shows a single 1-contract active sell moving price sharply once resting buy-side liquidity had already been pulled.
- **Why price stops — Absorption (WMT p117–p120, p125–p127):** a large passive order size matches repeated active orders at one price without the price moving — a temporary equilibrium; recognizing absorption in real time helps avoid buying tops/selling bottoms and flags durable S/R.
- **Why price stops — Exhaustion (WMT p120–p125):** a marked drop in active-order volume without a compensating rise in passive liquidity; recognized on Footprint via decreasing volume near a high/low and short-bodied indecision candles.
- **Initiative / Development (Phát triển) (WMT p127–p130):** active traders pushing price directionally with large orders — checklist: (1) large volume on one side (ASK for buying-initiative, BID for selling-initiative), (2) an imbalance skew matching that direction, (3) the imbalance sitting near/above the close (confirming the push held), (4) price actually moving further in that direction right after — full confirmation only when all four align.
- **Caveats — subjectivity of column placement (Ch. 4 §5.1, WMT p130):** "Analyzing order flow via Footprint carries inherent subjectivity, because order matching always has different intentions behind it" — the book's own explicit warning. Worked illustration: **closing a Short** via an active Buy-Market or a Buy-Stop both post to the **ASK** column, but closing the same Short via a Buy-Limit/Buy-Stop-Limit take-profit posts to the **BID** column; the mirror holds for closing a **Long** (Sell-Market/Sell-Stop → BID; Sell-Limit/Sell-Stop-Limit take-profit → ASK). The same real-world action (position-closing) can therefore print into either column depending purely on order type used — not every ASK-column fill is fresh bullish conviction, and not every BID-column fill is fresh bearish conviction. This directly continues into: quoting **Trevor Harnett** ("Footprint's founder," per the book) — "Footprint is not a system, it's a foundation for understanding what's happening in the market" (WMT p092) — and citing **Rubén Villahermosa Chaves, *Wyckoff 2.0: Structures, Volume Profile and Order Flow*** (named explicitly, WMT p009 and again p131) for the same caution that raw ASK/BID prints do not reveal true intent. Real-volume data is required (crypto/futures/stocks are fine; Forex uses tick-count as a Delta proxy, which the book flags as unreliable). The author names the platforms he personally built/uses: **Stockmap.vn** (Vietnamese stocks) and **Coinmap.tech** (crypto) (WMT p098, p133).
- **Absorption — 3-point Footprint checklist (WMT p125–p126):** absorption forms a price "wall" ("tường thành") where active orders on one side fully match resting liquidity on the other without moving price. Recognize it via: (1) a sudden large-volume print concentrated at one specific price (ASK-side spike → buy absorption; BID-side spike → sell absorption); (2) **price fails to continue moving** in the prevailing direction immediately after that large print — the tell that large resting limit orders are blocking the move; (3) the **imbalance itself stalls** — large ASK-column buying that doesn't lift price, or large BID-column selling that doesn't push price down.

### 3.3 Delta and Cumulative Delta (Ch. 5, WMT p135–p145)
- **Formula:** `Delta = ASK-column volume − BID-column volume` per bar; negative (red) = BID > ASK; positive (green) = ASK > BID.
- **Cumulative Delta:** running sum of Delta over a session/period; rising = more active buying pressure accumulating, falling = more active selling. Used to gauge whether a breakout candidate has real committed buying/selling behind it — "if price is ranging with a downward bias but Cumulative Delta points up, someone is buying the dip; for a real breakout, Cumulative Delta needs to keep rising, especially near the range's upper edge" (WMT p139).
- **Fixed Range Delta (FRD):** a user-selected price/time-range variant of Cumulative Delta for zoomed analysis of one specific range — named in the book's own subtitle as one of its four core tools.
- **Price/Cumulative-Delta Divergence — four strengths (Hình 5.5, WMT p141–p143):**
  - **Strong (Mạnh):** the cleanest signal, called out by the book as especially strong precisely **at Wyckoff Spring/UTAD locations** — a second explicit classic-Wyckoff bridge point.
  - **Medium (Vừa):** price makes equal double-bottoms/tops while Cumulative Delta shows a higher-low/lower-high.
  - **Weak (Yếu):** the mirror — Delta makes an equal double-bottom/top while price shows the higher-low/lower-high.
  - **Hidden (Ẩn):** price and Delta both move the "wrong" way relative to standard divergence — reads as a *trend-continuation-difficulty* warning, not a reliable reversal signal on its own.
- **Common misconceptions the book explicitly warns against (WMT p143–p145):** (1) not every ASK-column active buy is genuinely trying to push price up (e.g. a short-cover); (2) high Delta does not guarantee a price move — it can be entirely absorbed by resting orders; (3) positive/negative Cumulative Delta alone does not mean the market will rise/fall — it only measures relative active buy/sell volume over a window, and price can rise on net-negative Cumulative Delta.

---

## 4. Part III — Tape Reading (Chapters 6–7)

### 4.1 History and the Effort-vs-Result rule (Ch. 6, WMT p149–p154)
Tape Reading traces to 19th-century ticker tape; the book explicitly credits **Richard Wyckoff** as the pioneer who "developed and refined" it into a discipline in the 20th century (WMT p150). The **Effort-vs-Result rule** = Wyckoff's Law of Effort vs. Result applied bar-by-bar: Effort (E) = volume/participation; Result (R) = the resulting price differential/range. Symbol notation (WMT p152–p153): `E>` effort increasing, `E<` decreasing, `E>>`/`E>>>` sharply/abnormally increasing (mirrored for `R`/Result, and later for Delta as `Del`).

### 4.2 Tape Reading Bar by Bar — the 10-case framework (Ch. 7 §1, WMT p159–p201)
Applied specifically at Trading-Range Spring/Upthrust locations, or when price nears key S/R, to time entries/exits — not meant to be read across an entire range (WMT p203). Each case combines Volume(E) / Delta(Del) / Price-differential(R):

| Case | Effort (Volume) | Delta | Result (price diff.) | Harmony? | Scenario |
|---|---|---|---|---|---|
| 1 | steady ↑ | positive, ↑ | expanding (up) | harmonious | Bullish, sustainable |
| 2 | strong ↑ | positive, holding/↑ | shrinking | **divergent (absorption)** | Bearish |
| 3 | ↓ | positive→falling/negative | shrinking | harmonious (buyer exhaustion) | Bearish |
| 4 | ↓ | positive→falling/negative | expanding (up) | divergent (fragile rally) | Bullish but vulnerable |
| 5 | sudden spike | positive, spike | expanding sharply (up) | surface-harmonious but flagged **climax** | Short-term bullish / bearish scenario ("distribution/redistribution") |
| 6 | ↑ | negative, steadily ↓ | shrinking (down) | harmonious | Bearish, stable continuation |
| 7 | strong ↑ | flips negative→positive | shrinking (down) | divergent | Bullish reversal signalled |
| 8 | ↓ | negative, magnitude ↓ | shrinking (down) | harmonious (seller exhaustion) | Bullish |
| 9 | ↓ | negative, magnitude ↓ | expanding (down) | divergent (fragile decline) | Bearish but vulnerable |
| 10 | sudden spike | negative, spike | expanding sharply (down) | surface **climax** | Short-term bearish / bullish scenario ("accumulation/reaccumulation") |

(Table synthesized from Bảng 7.1 and the 10 case statements, WMT p161–p201; Cases 5 and 10 are the book's explicit statements of a **buying climax → distribution/redistribution** and a **selling climax → accumulation/reaccumulation**, using the English loanwords "climax," "overbought," "oversold" directly — a third explicit bridge to classic Wyckoff vocabulary.) Worked examples span 19 HOSE-listed stocks (DXG, STB, PDR, VND, NVL, DCM, SSI, HAG, MSN, NLG, NKG, VNM, VIC, VHM, plus DIG, HDG per the List of Figures) at 15–60 min timeframes. Recurring chart-annotation terms: **"Phe đối lập"** (the opposing side, i.e. absorption), **"Kiệt sức"** (exhaustion), **"Hài hòa"** (harmony), and an unglossed **"EOM"** abbreviation paired with "even small aggressive volume still moves price" (book never spells out the acronym).

### 4.3 Tape Reading Analog Bar (Ch. 7 §2, WMT p203–p211)
Compares structurally-similar candle *pairs* within a Trading Range across five defined bar types: **Climactic Run** (red), **Change of Character** (green), **Selling-Climax Analog** (blue), **Test-of-Climactic-Action Analog** (yellow), **Up-Effort-off-the-Test Analog** (purple) — comparing effort (volume+Delta) vs. result (price reaction) between the two bars of each pair. Recommended only for experienced traders, as a *refinement* layered on top of Wyckoff/Volume-Profile analysis, not a standalone method (WMT p211). Full worked example: PVS stock (HNX, 1h) across 5 bar-pairs, concluding PVS was in **reaccumulation** with a buy opportunity at the range's lower boundary.

### 4.4 Tape Reading Swing by Swing (Ch. 7 §3, WMT p211–p229)
Compares two consecutive up-waves (from range support) or two consecutive down-waves (from range resistance) on Volume(E) / Cumulative-Delta(DEL) / price-change(R):

| Case | Wave comparison | Volume | Cumulative Delta | Price | Conclusion |
|---|---|---|---|---|---|
| 1 | two up-waves | wave 2 ≥ wave 1 | wave 2 ≥ wave 1, both positive | wave 2 rise ≥ wave 1 | Harmony — continuation, breakout likely |
| 2 | two up-waves | wave 1 ≥ wave 2 | wave 2 markedly < wave 1 (still +) | wave 2 rise < wave 1 | Divergence — weakening, **potential Upthrust** |
| 3 | two down-waves | wave 2 ≥ wave 1 | wave 2 more negative than wave 1 | wave 2 decline < wave 1 (despite more selling effort) | Divergence — buyers absorbing, **potential Spring** |
| 4 | two down-waves | wave 1 ≥ wave 2 | magnitude shrinks toward zero from wave 1→2 | wave 1 decline >> wave 2 | Divergence — buyers accumulating, **potential Spring** |

(Bảng 7.2, WMT p212–p213.) This table is the book's most direct operational statement tying **price/Cumulative-Delta divergence at swing level directly to Spring (Cases 3–4) and Upthrust (Case 2) identification.** Worked example: PNJ stock 30-min (HOSE), a full multi-wave divergence read concluding accumulation with a likely reversal at a specific down-wave, flagged against an "LPS[C]" buy zone. Optional, flexible within a range; not recommended for beginners (WMT p228).

---

## 5. Part IV — Combining Wyckoff with Modern Tools: the operating method (Chapters 8–12)

This is the book's synthesis chapter sequence and is the closest thing it has to a decision pipeline. It maps closely onto (and can inform) this project's own 12-step Decision Pipeline in the master system prompt.

### Step 1 — Identify market phase (Ch. 8 §1, WMT p233–p236)
Determine the broader trend (up/down/sideways) on a higher timeframe or by zooming out; then find **local** non-trending zones (Trading Ranges) on the actual trading timeframe; then classify the phase as accumulation / distribution / reaccumulation / redistribution based on what preceded the range (decline → likely accumulation/reaccumulation-of-uptrend; rise → likely distribution/redistribution). Misclassification here is tolerated — later steps compensate.

### Step 2 — Identify Spring or Upthrust (Ch. 8 §2, WMT p236–p238)
If Step 1 → accumulation/reaccumulation, look for the best-fitting **Spring type** (1/2/3) at the range low; if distribution/redistribution, look for the best-fitting **Upthrust type** (1/2/3-Minor-UTAD) at the range high. Buying range lows / selling range highs *without* phase context is explicitly discouraged for new traders (poor R:R). Experienced traders may optionally layer in Ch. 7's Analog-Bar/Swing-by-Swing reads here for extra confidence.

### Step 3 — Identify trading Bias (Ch. 8 §3, WMT p238–p241)
**Buy bias** for Spring-type setups; **Sell bias** for Upthrust-type setups. (Worked examples: BTC/USDT 5m and VCI stock 30m, both concluding reaccumulation → Spring → buy bias.)

### Step 4 — Zone analysis via Volume Profile (Ch. 9, WMT p243–p249)
Mark **VAH/VAL** (often near/at the Trading Range extremes) as the primary "waiting" levels — VAL → look for Spring, VAH → look for Upthrust — and mark **LVN** just beyond VAH/VAL as the stop-loss zone (high-probability rejection area). If price crosses cleanly through VAH/VAL into LVN *without* a reversal reaction, the book explicitly says: **abandon the Spring/Upthrust plan** — the market is trending, not ranging, and the original thesis is invalidated (this is the book's own Data/Thesis-Invalidation logic, directly reusable for this project's §21 Invalidation framework).

### Step 5 — Entry-signal analysis via Footprint/Delta: Exhaustion → Absorption → Development (Ch. 10, WMT p250–p267)
Not a rigid fixed sequence — steps may be absent or interleaved (WMT p267). At a **Spring** location: look for (a) volume decline / Delta turning positive-or-less-negative / cumulative Delta rising = **exhaustion**; (b) a volume spike on the BID column with stacked BID imbalances, Delta flipping from negative to positive, price failing to move lower despite the spike = **absorption**; (c) sustained elevated volume concentrated on the **ASK** column, Delta and cumulative Delta continuing positive, one or more **SOS** (Sign of Strength) candles = **development**. Mirror-image logic applies at an **Upthrust** location (BID/ASK reversed, **SOW** — Sign of Weakness — candles instead of SOS). The chapter's own worked checklist (Hình 10.1, "Trading Signal Checklist," reproduced in full at Appendix 1, WMT p356–p357) is the book's single canonical decision artifact — B1 phase, B2 Spring/Upthrust, B3 bias, B4 VAL/VAH+LVN, B5 volume/Delta/cumulative-Delta/price-reaction/Stacked-Imbalance-column/signal-summary. Two fully worked examples (BTC/USDT 5m, VCI stock 30m) each conclude "**Spring Type 3**" via a numbered candle-by-candle Exhaustion→Development read.

### Step 6 — Order entry and position management (Ch. 11, WMT p268–p279)
- **Entry:** the book explicitly recommends a **Market order** once the full checklist is satisfied, over Limit/Stop-Limit, arguing immediate execution beats fill-price precision in volatile markets (explicitly names crypto as the prime example) (WMT p269–p271).
- **Stop Loss:** below the lowest low of the Spring, or above the highest high of the Upthrust — placed so the stop only triggers on genuine pattern failure (WMT p271). Calculate R:R before entry. Consider **moving stop to entry (Breakeven)** or a **Trailing Stop** once price has moved favorably or consolidated into a new zone (WMT p272).
- **Take Profit:** first target = the **opposite side of the Trading Range**, reinforced by the **"Market Profile 80% rule"** — if an attempted breakout of the Value Area fails, price has an ~80% chance of reaching the *other* end of the Value Area — applied here as VAH (from a Spring entry) or VAL (from an Upthrust entry) (WMT p273, explicitly citing Dalton's Market-Profile literature). At the opposite range edge: watch for **SOT** or a clear reversal signal to decide exit-vs-ride; if trend continuation looks intact, move stop to breakeven and keep riding, since a fresh, smaller Trading Range typically forms after any breakout (needing time to confirm real vs. fakeout) — Tape Reading and a lower timeframe are the recommended tools for managing this next stage (WMT p273–p274).

### Chapter 12 case studies (10 total; template = identical 5-step method each time)
| Instrument | Timeframe | Setup | Realized RR (as stated) |
|---|---|---|---|
| GMX/USDT | 5m | Spring type 2 | 4.10 |
| CHZ/USDT | 30m | Spring type 2 | 2.59 |
| NFP/USDT | 60m | Spring type 2 | 1.88 |
| ETHW/USDT | 30m | Spring type 2 | 4.06 |
| RDNT/USDT | 60m | Spring type 2 | 1.74 |
| INJ/USDT | 60m | **Upthrust type 1** (short) | 2.43 |
| VNM (stock) | 30m | Spring type 2 | 5.11 |
| FPT (stock) | 60m | Spring type 2 | 5.8 |
| VND (stock) | 60m | **Upthrust type 2** (short) | not stated as a clean RR figure in the extracted text |
| EIB (stock) | 240m/H4 | **Upthrust type 2** (short) | not stated as a clean RR figure in the extracted text |

Every case follows: Step1 phase call → Step2 Spring/Upthrust location → Step3 bias → Step4 VAH/VAL/LVN → Step5 numbered candle-by-candle Volume/Delta/price/Stacked-Imbalance read ending in a Type classification → Entry (market, on the confirming candle's close) → Stop (beyond the pattern's extreme) → Take Profit (range opposite edge, then trail on SOT/reversal signal). All five crypto Spring examples and both VN-equity Spring examples were independently classified "**Type 2**" by the book — the extraction agents flag that a formal enumerated Type-1/2/3 *definition* table doesn't reappear in this chapter (it's back in §2.6 above); Chapter 12 only *applies* the taxonomy.

---

## 6. Terminology quick-reference (as defined/used in this book)

| Term | Meaning per this book |
|---|---|
| Tích lũy / Tái tích lũy | Accumulation / Re-accumulation |
| Phân phối / Tái phân phối | Distribution / Re-distribution |
| Spring (loại 1/2/3) | Bullish Trading-Range-low reversal, 3 types by volume/reaction/confirmation strength |
| Upthrust (loại 1 / 2=UTAD / 3=Minor UTAD) | Bearish Trading-Range-high reversal, 3 types |
| SOT | Shortening of the Thrust — progressively shorter swings signaling exhausted momentum (acronym never expanded beyond this behavioral definition anywhere in the book) |
| VAH / VAL / LVN / VPOC | Volume Profile: Value Area High/Low, Low Volume Node, Volume Point of Control |
| POC / R/H / R/L | Footprint: Point of Control; Ratio-High / Ratio-Low (extreme-cell exhaustion ratios) |
| Imbalance / Stacked Imbalance | BID-vs-ASK diagonal volume skew; ≥2 adjacent such skews |
| Hấp thụ / Kiệt sức / Phát triển | Absorption / Exhaustion / Development (Initiative) |
| Delta / Delta tích lũy / FRD | Delta (ASK−BID per bar) / Cumulative Delta / Fixed Range Delta |
| Phe đối lập | "The opposing side" — the book's own chart-annotation term for absorption in action |
| SOS / SOW | Sign of Strength / Sign of Weakness (large, directionally-decisive candles) |
| RR | Risk/Reward ratio |
| Bias | Trading bias — Mua (buy) or Bán (sell) |

---

## 7. Adaptation notes for this project's instruments (BTC, ETH, SOL, XAUUSD, XAGUSD, Oil)

*(This section is the extractor/synthesizer's own addition — clearly separated from the book's content above per the "nothing added from outside the source" discipline. It does not introduce new Wyckoff/order-flow theory; it only notes fit/gaps against this project's stated instrument universe.)*

- **BTC/ETH:** the book uses these directly as worked examples throughout (Springs on RNDR, RDNT, CHZ, GMX, ETHW/USDT; Upthrust on INJ/USDT; BTC/USDT appears in Ch. 8–10's running example) — high direct applicability. Its own Imbalance-ratio guidance explicitly calls for **adjusting the threshold per token liquidity** in crypto (WMT p109) — do not reuse a single fixed ratio across BTC/ETH/SOL without checking each pair's own typical order-book depth.
- **SOL:** not used as a named example anywhere in the extracted pages; apply the same crypto Imbalance-ratio caveat above.
- **XAUUSD / XAGUSD / Oil:** the book gives an explicit CFD imbalance-ratio figure (~3–4×, WMT p109) for "gold and oil CFDs" specifically — directly usable — but has **no worked chart examples** on these instruments anywhere in the extracted pages; the Volume-Profile/Footprint mechanics are instrument-agnostic in the book's own framing, but real-volume-data availability (a hard requirement the book itself states, WMT p131–p133) needs separate verification for whichever CFD/futures feed this project ultimately uses for XAUUSD/XAGUSD/oil, since the book only validated its method on crypto/futures/VN-equities data.
- **Forex / tick-volume limit:** the book flags Forex's tick-based Delta as not real volume and therefore unreliable for exactly this kind of analysis (WMT p131–p132). This is the SOURCE's own data-quality limit and it stands on its own. It was written here as reinforcing "this project's own hard 'never trade Forex' rule"; that rule was lifted 2026-09-17 (user decision), so the editorial half is gone and the book's half is not. The consequence is unchanged: Footprint/Delta must not be scored on a tick-volume feed.

---

## 8. Cross-source notes and explicit statement of scope

- This book's Spring/Upthrust type-1/2/3 taxonomy is **specific to this author** and is not the same vocabulary as the classic Wyckoff-Advance PS/SC/AR/ST/SOS/SOW/UT/UTAD schematic labels reproduced (but not re-explained) on its own Chapter-1 diagrams, nor identical to any ICT/TTrades concept in sibling files `04-06`. When a dispatch or analysis prompt needs "Spring type 2" specifically, cite this file; when it needs classic Wyckoff-Advance phase-letter labels, note that this book explicitly declines to redefine them in its own prose (WMT p026) — those labels are illustrative-diagram-only in this source.
- The book's explicit points of contact with classic Wyckoff vocabulary (the three "bridge" statements captured above) are: (1) stacked imbalance being most meaningful at a Spring/UTAD or double-top/bottom neckline (WMT p111); (2) "strong" price/Cumulative-Delta divergence being cleanest at Spring/UTAD (WMT p141); (3) Tape-Reading-Bar-by-Bar Cases 5 and 10 being explicit buying/selling **climax** → distribution/redistribution or accumulation/reaccumulation calls (WMT p180, p200).
- Everything in this file traces to `.cache/wyckoff-pages/001.jpg`–`374.jpg` (all 374 pages, including the three initially-missing pages 126/130/365, now recovered and folded in) except the explicitly-marked §7 adaptation notes. Ingestion of this source is complete with no remaining known gaps.
- Per-range extraction detail (candle-by-candle numeric readings, every individual worked example's full Vietnamese quotes) lives in `knowledge/.wyckoff-parts/part-01..10-*.md` if deeper verification against a specific page is ever needed; this file is the curated synthesis for day-to-day use.
