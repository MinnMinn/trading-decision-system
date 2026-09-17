# Footprint Chart, Delta, and Footprint + Wyckoff (Stockmap.vn series, docs 6–8)

> Previously `03-footprint-chart-delta-wyckoff.md`. See `knowledge/INDEX.md` for the old→new map.

Synthesis of three Vietnamese-language slide decks from www.stockmap.vn ("cho thị trường chứng khoán Việt Nam" — for the Vietnamese stock market). All quotations below are translated from Vietnamese by the reader; page numbers refer to the PDF page index (1-based). Chart examples in the decks are VN30 index futures (VN30F2307 / VN30F2309, 1m and 5m) and HOSE/HNX stocks (MWG, FPT, HUT, STB, 1h). Nothing below is invented; where the source is silent or ambiguous this is stated explicitly in Section 6.

---

## 1. Source list

| # | File | Pages | Language | Content |
|---|------|-------|----------|---------|
| 6 | `docs/Footprint/6. Footprint chart.pdf` | 28 | Vietnamese (chart labels partly English) | Order types, DOM, matching mechanism, why price moves, how a footprint is built from Time & Sales, POC, imbalances, stacked imbalances, traps |
| 7 | `docs/Footprint/7. Delta.pdf` | 16 | Vietnamese | Delta, Delta %, Cumulative Delta, importance of delta, delta divergence (with/without structure), CVD divergence types, absorption, common mistakes, annotated FPT chart |
| 8 | `docs/Footprint/8. Footprint + Wyckoff.pdf` | 14 | Vietnamese (pages 11–14 are image-only text; read from renders) | Wyckoff structure/context templates (accumulation, re-accumulation, distribution, re-distribution, SOS/mSOS, MSOW/mSOW), five entry "signals", six Spring patterns, six UTAD patterns |

Reading method: `pdftotext -layout` for text, plus page renders for every page (charts, arrows, tables, and the image-only pages).

---

## 2. Core concepts (as the source defines them)

### 2.1 Order flow foundations (doc 6)

- **Order flow / "footprints in the sand"** (6:p2) — Order flow is a specialised tool to track exceptionally large volumes. The volumes *actually executed* by large institutions that affect price are treated as "footprints on sand"; following them helps a trader find or manage a position. Large institutions and market makers are the forces that usually move price.
- **Order types by location** (6:p3) — Above current price: Buy Stop / Sell Limit, and Buy Stop Limit. At current price: Buy Market / Sell Market. Below current price: Sell Stop Limit, and Sell Stop / Buy Limit.
- **DOM (Depth of Market), traditional** (6:p4) — displays current market information: BID/ASK, Best BID/Best ASK, current price, most recent trade, spread. Example: HOSE order-entry screen for VIC with "Dư mua" (resting buy) / "Dư bán" (resting sell) and a Binance-style BTC ladder.
- **Matching mechanism — which column a fill prints in** (6:p5). This table is the definitional basis for reading a footprint cell:

  | Order type | Matches with | Appears in |
  |---|---|---|
  | Buy Market | Sell Limit | **ASK** |
  | Buy Limit | Sell Market | **BID** |
  | Buy Stop | Sell Limit | ASK |
  | Buy Stop Limit | Sell Market | BID |
  | Sell Market | Buy Limit | BID |
  | Sell Limit | Buy Market | ASK |
  | Sell Stop | Buy Limit | BID |
  | Sell Stop Limit | Buy Market | ASK |

  The first two rows are boxed in red in the source as the key pair.
- **Two camps of participants** (6:p6) — "Phe dừng giá" (the price-stopping side): BID and ASK (resting limit liquidity). "Phe di chuyển giá" (the price-moving side): BUY MARKET and SELL MARKET.
- **Why price moves** (6:p7) — two causes: (1) the volume of aggressive trades ("Aggressor volume"); (2) "Imbalance in the Intent of Trade".
  - (1) Aggressive trades (6:p8): a market sell of 1 lot "hits the bid" and prints at best bid; a market buy of 1 lot "lifts the offer" and prints at best ask. Diagram: best ask 12 contracts, best bid 15 contracts, spread between.
  - (2) Imbalance in intent (6:p9–10): resting liquidity levels affect best bid, best offer and spread through *pulling* or *adding* liquidity. When market orders hit the bid or lift the offer, trades occur at new price levels. p10 sequence shows a large ask stack (120/85/72 contracts) appearing above, bids being pulled (15→gone, 18→gone), and the last trade printing inside the widened spread, annotated "NEWS ALERT — Potential spoofing".
- **Thesis** (6:p11) — "Order flow visually shows market & limit orders — the elements that show *real* supply and demand and are the reason price moves."
- **Order-flow tool family** (6:p12) — Footprint chart ("follow the money flow"), Heatmap ("liquidity map"), Volume Dot ("follow the big boys"), DOM.
- **Footprint chart origin** (6:p13) — developed by Trevor Harnett, CEO of MarketDelta, in 2000, brought to market in 2003; "a breakthrough in trading showing the traces of the Bigboy".

### 2.2 The footprint cell and candle (doc 6)

- **Footprint vs. Japanese candle** (6:p14) — a footprint replaces the candle body with one row per price level. Each row is `BID × ASK` (left = bid volume, right = ask volume). Stockmap's rendering also carries a per-candle header/footer, visible on p14/p16/p23/p27/p28 renders: header `V:` (total volume), `D:` (delta), `R/H:` (a ratio, undefined in text — see §6), and a pair of small counts (e.g. `4 16`, `5 2`, `0 0`, `6 5`, `3 0`, `0 1`, orange left / blue right); footer `R/L:` (another undefined ratio) and a pair of totals (e.g. `6.8k 10k`, `430k 340k`) that reconcile to the bid total and ask total — e.g. p27: 340k − 430k = −90k ≈ D −92.4k; p14: 10k − 6.8k = 3.2k ≈ D 3.29k. The highest-volume row is highlighted yellow (POC).
- **Aggression vs. passivity** (6:p15) — "Aggression is expressed when you execute an order that fills immediately. Passivity is expressed when you place a waiting (resting) order."
- **Who is in each column** (6:p16) —
  - BID column: "market sell orders (or orders that can convert into market sell) matched with Buy Limit orders." Labelled *Aggressive Sellers* meeting *Passive Buyers*.
  - ASK/OFFER column: "market buy orders (or orders that can convert into market buy) matched with Sell Limit orders." Labelled *Aggressive Buyers* meeting *Passive Sellers*.
- **Subjectivity of a cell** (6:p17) — pointing at a `0 × 1.91k` cell: "Buy market or Sell limit???" — the same ask-side print is simultaneously an aggressive buy and a passive sell; which side *matters* is a matter of interpretation (illustrated with the 6-vs-9 cartoon).
- **How a footprint is formed** (6:p18–21) — "The FOOTPRINT chart is created from the Time & Sales tape, recorded in the order shown, according to the matching mechanism on the order book." Worked example (book: asks 5@102, 10@101, 20@100; bids 15@99, 12@98, 7@97):
  1. t1: 1 lot trades at 99 on the BID → footprint row 99 = `1 × 0` (6:p18).
  2. t2: 14 lots at 99 on BID, 12 lots at 98 on BID → rows 99 = `15 × 0`, 98 = `12 × 0`; bid at 99 is consumed (6:p19).
  3. t3 (variant A): 5 lots at 100 on the OFFER → row 100 = `0 × 5`; ask at 100 falls to 15 (6:p20).
  4. t3 (variant B): a sell limit is placed at 98 and 5 lots lift it → row 98 = `12 × 5` (6:p21).
  Rule implied: every print is attributed to BID if it executed against resting bids, to ASK if it executed against resting offers.
- **Point of Control (POC)** (6:p22) — "The most important position in any footprint is probably the high-liquidity zone. It represents where the largest traded volume is, where institutions are most actively operating, usually marked by the most prominent yellow background." (Per-candle POC; the chart on p22 marks a POC on each 5m candle.)
- **Imbalance** (6:p23) — "Helps track market psychology. A *buy imbalance* is when total aggressive buy volume equals 250%, 300%, 400%, … of aggressive sell volume or more, depending on the market; and vice-versa for a *sell imbalance*. Read along the diagonal, from the bottom up." The example candle (V 1.9k, D −250, R/H 3.70) highlights bid cells 100, 120, 120, 56, 96 in orange (sell imbalances) with red diagonal arrows, and ask cell 340 (row `160 × 340`, also the POC) with a green diagonal arrow (buy imbalance). Checking the numbers confirms the standard diagonal: **buy imbalance = ASK at price P vs BID at price P−1** (340 vs 67 ≈ 5.1×, highlighted; 150 vs 67 ≈ 2.2×, not highlighted); **sell imbalance = BID at price P vs ASK at price P+1** (56 vs 16 ≈ 3.5× highlighted, whereas 56 vs the 30 below is only 1.9×; 87 vs 49 above ≈ 1.8×, not highlighted). See §6 for the caveat that the mapping is inferred from the chart, not written out.
- **Stacked imbalance ("Mất cân bằng xếp chồng")** (6:p24) — "The start or end of a trend is often marked by imbalance caused by aggressive participants. A stacked imbalance is when there are 3 or more consecutive imbalances." Stockmap draws each stacked-imbalance zone as a horizontal band (teal = buy-stack, brown = sell-stack) extended to the right until price trades through it.
- **What makes a strong stacked imbalance** (6:p25) — three factors: (1) **Context** — it appears at a zone ("xuất hiện tại vùng"); (2) **Position** — at the head/extreme of the candle ("đầu cây nến"); (3) **Volume** — increasing, or high volume.
- **Stacked imbalances as S/R** (6:p26) — "Price frequently respects these strong stacked-imbalance zones." (MWG 1h chart with two boxed examples of price returning to and reacting at old stacked-imbalance bands.)
- **Trap** (6:p27–28) — "Trap is the word used for traders who get stuck at highs or lows when the market reverses. When a trap occurs there is usually a short-term trading opportunity; this is usually a nice signal." Both examples are *sell traps*: a candle with a stacked *sell* imbalance at its low (p27 MWG 1h: bids 14.7k/11.3k/22.7k/13.4k vs asks 1.10k/200/1.50k/0, D −92.4k; p28 VN30 5m: bids 594/178/378/132 vs asks 0/0/0/0, D −1.34k) after which price reversed up, leaving the aggressive sellers trapped.

### 2.3 Delta (doc 7)

- **Delta (origin)** (7:p2) — "a term originally coined by MarketDelta in 2002 to measure the difference between volume traded at the bid and at the offer over a given period."
- **Three kinds of delta** (7:p3): Delta, Delta %, Cumulative Delta.
- **DELTA = ASK − BID** (7:p4) — "the difference between contracts bought and sold in a given period." Displayed as a histogram under the chart (green positive / red negative).
- **DELTA % = (DELTA / VOL) × 100%** (7:p5) — "the relationship between delta and volume, often used to track abnormal fluctuation at the start of a new trend." Example histogram values: −15.32, −18.49, −13.26, 0, 20.72, −40.5, 33.33, 4.35, 6.05, 5.57, 2.96, 16, 8.51, −16.09, −15.61, −60.
- **Cumulative Delta (CVD)** (7:p6) — "equals the sum of delta over the day / week / month." Drawn as a red line in a sub-pane ("Cumulative delta: 690").
- **Why delta matters** (7:p7–8) —
  - One of the most important tools in order-flow analysis.
  - Helps determine the strength of a trend based on volume.
  - Its essence is to show the strength of *aggressive* buyers and sellers.
  - Shows the *effort* of market participants.
  - Can show **absorption** in the market.
  - Shows the aggression of buyers and sellers.
  - "If you want to hold your position, you want to see price and delta rise together."
  - Shows people's willingness to accept higher or lower prices — can be a sign of an "invasion" (aggressive campaign) in the market, or of readiness to believe what is currently unfolding.
- **Delta divergence** (7:p9) — "Positive delta while price falls, forming a red candle. Negative delta while price rises, forming a green candle. This can be a reversal signal if it appears at the zones we are preparing to trade. But not every delta divergence means price falls — we must look at context and think about what the market is trying to say."
  - **With structure** (7:p10, MWG 1h): at the top of a multi-week range (~54.5 resistance) a red candle prints D +308k (V 1.49M) with a stacked sell imbalance at its top (43.6k/51.0k/53.5k bids vs 3.50k/7.80k/32.3k asks) — positive delta, red candle, at resistance → price then fell to ~48.
  - **Without structure** (7:p11, STB 1h): at a swing low (~27.7) a green candle prints D −1.26M (V 6.38M) with large bid volumes (1.26M, 1.05M, 1.37M) — negative delta, green candle, no range structure → price then rallied to ~30.8.
- **Cumulative-delta divergence types** (7:p12) — table (price vs CVD):

  | | Strong | Medium | Weak | Hidden |
  |---|---|---|---|---|
  | **Bullish** | Price Lower Low / CVD Higher Low | Price Equal Low / CVD Higher Low | Price Lower Low / CVD Equal Low | Price Higher Low / CVD Lower Low |
  | **Bearish** | Price Higher High / CVD Lower High | Price Equal High / CVD Lower High | Price Higher High / CVD Equal High | Price Lower High / CVD Higher High |

- **Absorption and hidden divergence** (7:p13) — "Absorption and divergence in cumulative delta (hidden divergence)." VN30F2309 1m: price makes a higher low while CVD makes a lower low (bullish hidden divergence in the table), i.e. aggressive selling is being absorbed; price then rallied ~1,238 → ~1,258.
- **CVD lag and bias** (7:p14) — "Although cumulative delta lags price, it gives us a fairly important bias. This is a very clear example of divergence from cumulative delta signalling the Range of a Distribution process (strong divergence)." VN30F2309 1m: price higher high while CVD lower high → price dropped ~1,265 → ~1,254.
- **Mistakes when using delta** (7:p15) — listed as errors to avoid: (1) "Large positive cumulative delta means buyers are strong and the market will go up; large negative cumulative delta means many sellers." (The chart shows VN30 rising for two days while CVD falls from 0 to −16k.) (2) "Negative delta and positive delta are *not* positions to enter; they only mean someone is buying or selling aggressively." (3) "Positive delta means more aggressive buy orders" — i.e. that is *all* it means.
- **Reading a trend with per-bar delta** (7:p16, FPT 1h annotated) — see §3.3 for the rules extracted from the annotations.

### 2.4 Footprint + Wyckoff (doc 8)

- **Structure vs. Signal** (8:p2) — the method is split into *Cấu trúc* (structure/context: the Wyckoff accumulation schematic with PS, SC, AR, ST, ST in Phase B, Spring, Test, LPS, SOS, BU/LPS across Phases A–E, with a resistance zone and support zone) and *Tín hiệu* (signal: footprint + heatmap, labelled "Ask/Offer/sell limit/large sell wall", "best offer", "best bid", "market order", "Bid/buy limit/large buy wall").
- **Context templates — accumulation side** (8:p3): *Tích luỹ* (Accumulation): a trading range after a decline; the entry box (yellow) sits at the range low after tests 1 and 2. *Tái tích luỹ* (Re-accumulation): a range after an advance; entry box at the range low after 1 test, or after tests 1 and 2. Right panel: same, with a green support band under the entry box.
- **Context templates — SOS / mSOS** (8:p4). Letters: C = range low, B = range top (breakout point), A = high of the breakout leg, D = pullback.
  - Case 1: `AB = BC`, `AD ≈ 50%–100% of AB` → "SOS (100%)"; entry box at D near B (above the range top / on the green band), or at the range top itself.
  - Case 2: `AB = BC` → "SOS (100%)"; entry box inside the *upper 50%* of the range (a 50% line is drawn through the range).
  - Case 3: `AB = 50% BC`, `AD ≈ 50%–100% of AB` → "mSOS (50%)" (minor SOS); entry box at D near B, or inside the top of the range.
- **Context templates — distribution side** (8:p5): *Phân phối* (Distribution): range after an advance; entry box at the range high after tests 1 and 2. *Tái phân phối* (Re-distribution): range after a decline; entry box at the high after tests 1,2 or after 1 test. Right panel: same with a pink resistance band.
- **Context templates — MSOW / mSOW** (8:p6): mirror of p4 with C = range high, B = range low (breakdown), A = low of the breakdown leg, D = pullback. `AB = BC` → "MSOW (100%)"; `AB = 50% BC` → "mSOW (50%)"; entry box at D near B (under the pink band) or inside the lower 50% of the range.
- **MBC / "nến mẹ" (mother candle)** — used throughout 8:p7–14 but never expanded. It is the large reversal/impulse candle that carries the stacked imbalance ("MBC có Stack.Imb"); every entry in doc 8 is "close of the mother candle". See §6.
- **Stack.Imb** — Stockmap shorthand for stacked imbalance (≥3 consecutive imbalances, 6:p24). "Stack.Imb Buy" = stacked buy imbalance.
- **Value Area (VA)** — used in doc 8 as "the Value Area created by the preceding stopping candles" (8:p7) and "a small Value Area" (8:p10), i.e. the price cluster formed by the 3–7 small stopping candles; the stop-loss is placed at its lower/upper boundary. Not formally defined in these three decks (see §6).
- **Trading Range (TR)** — the Wyckoff range; "large TR" in Spring/UTAD patterns 4–6.
- **Trap sell / Trap buy** — a pinbar wick that "hunts" stops and traps aggressive sellers (Spring) or buyers (UTAD), ideally with a Stack.Imb inside the wick (8:p11, p13).
- **Pinbar** — candle with a long rejection wick; "Pinbar hunt" (8:p11, p13).
- **Spread** — candle range (high–low); "spread decreasing" (spread giảm dần) is used repeatedly as the contraction signature before a reversal (8:p7–14).
- **Effort that fails** — purple annotations: "Effort to push up but failed or had no result" (8:p8, at top 2) and "Effort to push down but failed or had no result" (8:p9, at bottom 2).

### 2.5 Concepts requested but NOT covered in these three decks
- **Unfinished auction** — not mentioned anywhere in docs 6–8.
- **Exhaustion** — not named; the nearest equivalents are "spread decreasing", "buying effort no longer present" (7:p16) and "effort … failed or no result" (8:p8–9).
- **Value Area** — used, not defined (see above).
- **Session/composite POC, VAH/VAL** — not covered; POC is per-candle only (6:p22).

---

## 3. Actionable rules / checklists (IF / THEN, with citations)

### 3.1 Reading rules (doc 6)
- R6-1 IF a print executes against resting bids THEN attribute it to the BID column (aggressive sell); IF against resting offers THEN to the ASK column (aggressive buy) (6:p5, p16, p18–21).
- R6-2 IF you see a large ask-side cell THEN do not assume it is only "buying" — it is equally a passive seller absorbing; interpret with context (6:p17).
- R6-3 IF resting liquidity is added/pulled around best bid/ask THEN expect best bid/ask and spread to shift and trades to occur at new levels; large stacks that appear and vanish around news are potential spoofing (6:p9–10).
- R6-4 IF a row has the highest volume in the candle THEN it is that candle's POC — the location where institutions were most active (6:p22).
- R6-5 IF ASK(P) ≥ k × BID(P−1) with k ≈ 250–400% (market-dependent) THEN mark a buy imbalance at P; IF BID(P) ≥ k × ASK(P+1) THEN mark a sell imbalance at P (6:p23; diagonal mapping inferred from the chart, §6).
- R6-6 IF ≥3 consecutive imbalances of the same side THEN mark a stacked imbalance (6:p24).
- R6-7 IF a stacked imbalance (a) appears at a zone, (b) sits at the head/extreme of the candle, (c) has high or increasing volume THEN treat it as *strong* (6:p25).
- R6-8 IF price returns to a strong stacked-imbalance zone THEN expect it to be respected (react/support/resist) (6:p26).
- R6-9 IF a candle prints a stacked imbalance at an extreme AND price reverses against it THEN the aggressors are trapped → short-term opportunity in the direction of the reversal ("usually a nice signal") (6:p27–28).

### 3.2 Delta rules (doc 7)
- R7-1 IF holding a position THEN want to see price and delta rising together (for a long); if delta stops confirming, reassess (7:p8).
- R7-2 IF delta > 0 but the candle closes red (or delta < 0 but candle closes green) THEN flag a delta divergence; IF it occurs at a zone you were already preparing to trade THEN treat it as a possible reversal signal; ELSE do not act on it alone — read context (7:p9).
- R7-3 IF delta divergence occurs at range structure (e.g. resistance of a distribution range with a stacked sell imbalance at the candle top) THEN it is the higher-quality case ("with structure") (7:p10). A divergence at a swing low with no structure can still resolve as a reversal (7:p11) but is the weaker case.
- R7-4 Classify CVD divergence by the table (7:p12): Strong / Medium / Weak / Hidden for bullish and bearish, using swing lows (bullish) or swing highs (bearish) of price vs CVD.
- R7-5 IF price makes a higher low while CVD makes a lower low THEN sellers are being absorbed (bullish hidden divergence) — bullish bias (7:p13).
- R7-6 IF price makes a higher high while CVD makes a lower high THEN strong bearish divergence — signals the range of a distribution process; bearish bias (7:p14).
- R7-7 Use CVD for *bias*, not timing — it lags price (7:p14).
- R7-8 DO NOT infer "market will go up" from large positive CVD or "many sellers" from large negative CVD (7:p15 #1).
- R7-9 DO NOT use the sign of delta as an entry location; it only says someone is aggressively buying/selling (7:p15 #2, #3).
- R7-10 Per-bar delta reading in a trend (7:p16 FPT annotations), as management rules:
  - IF decline has stopped and price is sideways (small mixed delta) AND then a large positive delta bar appears THEN "there is a large aggressive buyer".
  - IF successive positive delta bars persist during the advance THEN "buying effort is maintained → price still rising" (hold).
  - IF a large negative delta bar appears AND buying effort disappears THEN "take partial profit" (chốt bớt).
  - IF aggressive selling stops (negative bars fade) AND a large positive delta bar appears THEN "look for a buy point".
  - IF buying effort is maintained steadily THEN "price still rising, should not sell".
  - IF a large aggressive seller appears (large negative bar) near the highs THEN "consider taking partial profit".

### 3.3 Wyckoff context rules (doc 8)
- R8-C1 IF a range forms after a decline (accumulation) THEN the entry location is at the range low after the 2nd test (tests 1, 2) — with support band under it (8:p3).
- R8-C2 IF a range forms after an advance (re-accumulation) THEN entry at the range low after the 1st or 2nd test (8:p3).
- R8-C3 IF price breaks out of the range with leg AB = BC (leg equals range height) THEN label it SOS (100%); IF AB = 50% BC THEN mSOS (50%) (8:p4).
- R8-C4 IF after an SOS price pulls back D with AD ≈ 50–100% of AB THEN the entry zone is at D around B (the old range top), or inside the upper 50% of the range (8:p4).
- R8-C5 Mirror for distribution/re-distribution (entry at range high after tests) (8:p5) and for MSOW (100%) / mSOW (50%) with pullback AD ≈ 50–100% AB to B (old range low) or the lower 50% of the range (8:p6).

### 3.4 Signal rules (doc 8, p7–10)
- R8-S1 **Stopping decline → reversal up** (8:p7): IF price stops declining for 3–7 M5 candles, AND an MBC with Stack.Imb prints whose body is ≥ 80%–120% of the largest candle in the Value Area formed by the stopping candles, THEN entry = close of the mother candle (IF the mother candle is very large THEN may wait for a 20% pullback); stop-loss = lower boundary of the Value Area. Confirmations: candles in the down-move had decreasing spread before stopping; the stopping candles have lower wicks (contest and rejection of value). Invalidation: IF the stopping candles have many long *upper* wicks, OR the VA contains too many large candles THEN do not trade.
- R8-S2 **Stopping rise → reversal down** (8:p7): mirror — 3–7 M5 stopping candles, MBC with Stack.Imb ≥ 80–120% of the largest VA candle, entry at close (or 20% pullback), SL = upper boundary of VA; stopping candles should have upper wicks; IF many long lower wicks OR too many large candles in VA THEN do not trade.
- R8-S3 **Double top with MBC + Stack.Imb** (8:p8): IF two tops AND an MBC with Stack.Imb whose body is ≥ 120% of the rising candles near top 2 THEN entry = close of mother candle; SL = above the highest top. Confirmations: rising candles into top 2 have decreasing spread, preferably upper wicks; the failed push ("effort to push up but failed / no result"). Invalidation: IF the child candles have long lower wicks THEN do not trade. Location: the MBC must appear within the top 30% band below the highest peak.
- R8-S4 **Double bottom with MBC + Stack.Imb** (8:p9): IF two bottoms AND an MBC with Stack.Imb whose body is ≥ 120% of the candles near bottom 2 THEN entry = close of mother candle; SL = below the lowest bottom (source text literally says "below the highest bottom" — see §6). Confirmations: candles of the decline from the neckline to bottom 2 have decreasing spread, preferably lower wicks. Invalidation: IF child candles have long upper wicks THEN do not trade. Location: MBC must appear within the bottom 30% band above the lowest bottom.
- R8-S5 **Double bottom after neckline break, pullback to the upper 50%** (8:p10): IF a double bottom has broken its neckline AND price pulls back into the upper 50% of the two-bottom range, AND (price stops declining OR an MBC prints OR a Stack.Imb Buy prints) THEN entry = close of the mother candle / close of the candle carrying the Stack.Imb / close of the candle breaking out of the small Value Area. SL: IF the pullback contains MBC + Stack.Imb THEN SL below that MBC; ELSE SL below the lowest bottom. Confirmation: pullback candles have decreasing spread. Note: "entry here is paying up after a reversal signal, so entry is flexible."

### 3.5 Spring patterns (doc 8, p11–12) — long entries at the bottom of a Trading Range
- R8-SP1 **Spring 1 — stop decline and return to TR** (8:p11): IF a strong down-move is stopped, contracts, then returns strongly into the TR, AND an MBC with Stack.Imb closes back inside the TR THEN entry = close of mother candle (20% pullback if very large); SL = lower boundary of the VA. Quality: Move [1] (the decline) — the larger its spread and volume the better; Move [2] — price stops falling, candles get progressively smaller or show many lower wicks (struggle and contraction).
- R8-SP2 **Spring 2 — two bottoms, bottom 2 has MBC + Stack.Imb** (8:p11): IF two bottoms with a large-spread, large-volume decline, AND MBC with Stack.Imb at bottom 2 THEN entry = close of mother candle; SL = below the lowest bottom. Quality: Move [1] large spread/volume; Move [2] (decline to bottom 2) has decreasing spread and many lower wicks (contraction, rejection); the best mother candle has a lower wick ≥ the child candles' wicks.
- R8-SP3 **Spring 3 — Pinbar + MBC with Stack.Imb** (8:p11): IF a pinbar hunts stops with a Trap sell (candle [1]) and then market buying appears (candle [2]) THEN entry = close of the mother candle; SL = below the mother candle. Rules: candle [1] green pinbar is best; IF candle [1] is a red pinbar THEN the following contraction must be seen (subsequent small candles with lower wicks). A Trap sell *with* Stack.Imb is best; without is acceptable if the trapped quantity is large enough. Candle [2]: MBC + Stack.Imb is best. IF candle [1] has NO trap THEN candle [2] MUST be MBC + Stack.Imb. IF candle [1] has Trap + Stack.Imb THEN candle [2] only needs to be a prominent candle with a strong close.
- R8-SP4 **Spring 4 — block and reject value** (8:p12): IF one strong down candle exits the large TR, is stopped and contracts, then returns strongly THEN signal = MBC with Stack.Imb closing back inside the TR, negating down-candle [1]; entry = close of mother candle (20% pullback if large); SL = lower boundary of the VA. Quality: candle [1] must have large volume and a lower wick; Move [2] price recovers right after and contracts at one Value Area; a mother candle with a long lower wick is best.
- R8-SP5 **Spring 5 — stop decline and negate** (8:p12): IF a strong down candle *with Stack.Imb* breaks out of the large TR, then stops and is negated back into the TR THEN signal = MBC with Stack.Imb closing successfully through candle [1]'s Stack.Imb zone; entry = close of mother candle beyond candle [1]'s Stack.Imb zone; SL = below the wick of the MBC.
- R8-SP6 **Spring 6 — stop decline and negate the whole candle** (8:p12): IF a strong down candle exits the TR, then stops and is negated THEN signal = MBC with Stack.Imb closing beyond down-candle [1]; entry = close of mother candle beyond the *open* of candle [1]; SL = below the wick of the MBC.

### 3.6 UTAD patterns (doc 8, p13–14) — short entries at the top of a Trading Range (mirror of Springs)
- R8-U1 **UTAD 1 — stop rise and return to TR** (8:p13): strong up-move stopped, contracts, returns into TR; MBC with Stack.Imb closes back inside the TR; entry = close (20% pullback if large); SL = upper boundary of VA. Quality: Move [1] large spread/volume; Move [2] price stops rising, candles smaller or many upper wicks.
- R8-U2 **UTAD 2 — two tops, top 2 has MBC + Stack.Imb** (8:p13): entry = close of mother candle; SL = above the highest top (source literally "below the lowest top" — see §6). Quality: Move [2] rising candles have decreasing spread, many upper wicks (contraction, rejection, "stretching up"); best mother candle has an upper wick ≥ child candles'.
- R8-U3 **UTAD 3 — Pinbar + MBC with Stack.Imb** (8:p13): pinbar hunt with Trap buy then market selling; entry = close of mother candle; SL = above the mother candle (source literally "below" — see §6). Red pinbar best; IF green pinbar THEN subsequent contraction (small candles with upper wicks) required. Trap buy with Stack.Imb best; without OK if trapped quantity is large. IF candle [1] has no trap THEN candle [2] MUST be MBC + Stack.Imb; IF candle [1] has Trap + Stack.Imb THEN candle [2] only needs to be prominent with a strong close.
- R8-U4 **UTAD 4 — block and reject value** (8:p14): one strong up candle exits the TR, stopped, contracts, returns; MBC with Stack.Imb closes back inside negating up-candle [1]; entry = close (20% pullback if large); SL = upper boundary of VA. Candle [1] must have large volume, upper wick is best; Move [2] price gets pulled back right after and contracts at a VA; mother candle with long upper wick is best.
- R8-U5 **UTAD 5 — stop rise and negate** (8:p14): strong up candle with Stack.Imb exits TR, then negated; signal = MBC with Stack.Imb closing through candle [1]'s Stack.Imb zone; entry = close beyond that zone; SL = above the mother candle's upper wick.
- R8-U6 **UTAD 6 — negate the whole candle** (8:p14): strong up candle exits TR, stops, and an MBC + Stack.Imb negates it; entry = close of mother candle beyond the *open* of candle [1]; SL = above the mother candle's upper wick.

---

## 4. Patterns with identification criteria

| Pattern | Must be true | Must NOT be true | Entry / SL | Source |
|---|---|---|---|---|
| Buy imbalance cell | ASK(P) ≥ ~250–400% × BID(P−1) | — | n/a (building block) | 6:p23 |
| Sell imbalance cell | BID(P) ≥ ~250–400% × ASK(P+1) | — | n/a | 6:p23 |
| Stacked imbalance | ≥3 consecutive same-side imbalances | — | zone drawn as S/R band | 6:p24 |
| Strong stacked imbalance | at a zone; at the head of the candle; high/increasing volume | — | expect respect on retest | 6:p25–26 |
| Trap (sell trap shown) | stacked sell imbalance at candle low; price then reverses up | — | short-term trade with the reversal | 6:p27–28 |
| Delta divergence (bar) | delta>0 & red close, or delta<0 & green close; at a zone being prepared | acting without context | reversal candidate | 7:p9–11 |
| CVD divergence (strong bullish) | price LL, CVD HL | — | bias long | 7:p12 |
| CVD divergence (strong bearish) | price HH, CVD LH | — | bias short / distribution range | 7:p12, p14 |
| CVD hidden bullish (absorption) | price HL, CVD LL | — | bias long | 7:p12–13 |
| Accumulation context | range after decline; entry at low after tests 1,2 | — | yellow box at low | 8:p3 |
| Re-accumulation context | range after advance; entry at low after 1 or 2 tests | — | yellow box at low | 8:p3 |
| SOS / mSOS pullback | AB=BC (100%) or AB=50%BC (mSOS); AD ≈ 50–100% AB | — | box at D≈B or upper 50% of range | 8:p4 |
| Distribution / re-distribution / MSOW | mirrors of the above | — | box at high / D≈B / lower 50% | 8:p5–6 |
| Stop-decline reversal | 3–7 M5 stopping candles; decreasing spread into stop; lower wicks; MBC+Stack.Imb ≥ 80–120% of largest VA candle | many long upper wicks on stopping candles; too many large candles in VA | close of MBC (or 20% pullback) / SL below VA | 8:p7 |
| Stop-rise reversal | mirror (upper wicks) | many long lower wicks; too many large VA candles | close / SL above VA | 8:p7 |
| Double top + MBC | MBC+Stack.Imb ≥120% of rising candles near top 2; decreasing spread into top 2, upper wicks; MBC within top 30% of the peak | child candles with long lower wicks | close of MBC / SL above highest top | 8:p8 |
| Double bottom + MBC | MBC+Stack.Imb ≥120% of candles near bottom 2; decreasing spread from neckline to bottom 2, lower wicks; MBC within bottom 30% | child candles with long upper wicks | close of MBC / SL below lowest bottom | 8:p9 |
| Neckline-break pullback (50%) | double bottom broke neckline; pullback into upper 50%; stop-decline or MBC or Stack.Imb Buy; pullback spread decreasing | — | close of MBC / Stack.Imb candle / VA-break candle; SL below MBC if present else below lowest bottom | 8:p10 |
| Spring 1 | strong decline (large spread+vol) stopped, contracts (small candles/lower wicks), MBC+Stack.Imb closes back in TR | — | close (20% pullback) / SL below VA | 8:p11 |
| Spring 2 | two bottoms; move[1] large spread+vol; move[2] decreasing spread + lower wicks; MBC+Stack.Imb at bottom 2; MBC lower wick ≥ child wicks (best) | — | close / SL below lowest bottom | 8:p11 |
| Spring 3 | pinbar trap-sell (green best; if red, needs contraction) then MBC; conditional rule on candle [2] | red pinbar without follow-through contraction | close / SL below mother candle | 8:p11 |
| Spring 4 | one big down candle (large vol, lower wick) out of TR; recovers & contracts at a VA; MBC+Stack.Imb closes back in TR | — | close (20%) / SL below VA | 8:p12 |
| Spring 5 | down candle [1] carries Stack.Imb; MBC+Stack.Imb closes through [1]'s Stack.Imb zone | — | close beyond that zone / SL below MBC wick | 8:p12 |
| Spring 6 | MBC+Stack.Imb closes beyond the open of down candle [1] | — | close beyond [1] open / SL below MBC wick | 8:p12 |
| UTAD 1–6 | exact mirrors (upper wicks, trap buy, red pinbar best) | — | SL above VA / highest top / mother candle / MBC upper wick | 8:p13–14 |

---

## 5. Quantitative details

| Quantity | Value | Source |
|---|---|---|
| Imbalance ratio | 250%, 300%, 400% "or more, depending on the market" | 6:p23 |
| Stacked imbalance | ≥ 3 consecutive imbalances | 6:p24 |
| Delta | ASK − BID | 7:p4 |
| Delta % | (Delta / Volume) × 100% | 7:p5 |
| Cumulative delta | Σ delta over day / week / month | 7:p6 |
| Stopping-candle count | 3–7 candles on M5 | 8:p7 |
| MBC size (stop-decline/stop-rise) | ≥ 80%–120% of the largest candle in the VA of the stopping candles | 8:p7 |
| MBC size (double top / bottom) | ≥ 120% of the candles near top/bottom 2 | 8:p8–9 |
| Pullback entry when MBC is very large | wait for a 20% pullback | 8:p7, p11, p12, p13, p14 |
| MBC location (double top/bottom) | within 30% of the extreme (top 30% below the peak / bottom 30% above the low) | 8:p8–9 |
| Neckline-break pullback depth | to the upper 50% of the two-bottom range | 8:p10 |
| SOS breakout leg | AB = BC → SOS (100%); AB = 50% × BC → mSOS (50%) | 8:p4 |
| SOS pullback | AD ≈ 50%–100% of AB | 8:p4 |
| Range re-entry after SOS | upper 50% of the range | 8:p4 |
| MSOW / mSOW | same ratios mirrored (100% / 50%) | 8:p6 |
| Timeframes used in examples | 1m, 5m (VN30F), 1h (stocks); M5 for signal counting | 6:p12, 7:p6–16, 8:p7 |
| Chart-example candle stats | e.g. V 1.9k / D −250; V 798k / D −92.4k; V 5.49k / D −1.34k; V 1.90M / D −410k; V 1.49M / D +308k; V 6.38M / D −1.26M | 6:p23,27,28; 7:p9–11 |
| Dates | Footprint invented 2000, released 2003 (Trevor Harnett); "Delta" coined 2002 (MarketDelta) | 6:p13; 7:p2 |

---

## 6. Conflicts, typos, and ambiguities inside the sources

1. **Imbalance diagonal is not written out.** 6:p23 says only "read along the diagonal from the bottom up". The standard mapping (buy: ASK(P) vs BID(P−1); sell: BID(P) vs ASK(P+1)) is *inferred* by checking which cells are highlighted in the example (340/67 ≈ 5.1× highlighted, 150/67 ≈ 2.2× not; 56/16 ≈ 3.5× highlighted whereas 56/30 ≈ 1.9×). The exact threshold used in the screenshot is not stated (somewhere ≥ 2.2× and ≤ 3.5×, consistent with 250–300%).
2. **Imbalance threshold is deliberately loose** — "250%, 300%, 400% … or more depending on the market" (6:p23). A FootprintSkill must treat the ratio as a parameter.
3. **`R/H` and `R/L` on the candle header/footer are never defined** (6:p14, p16, p23, p27, p28; 7:p9–11). The footer pair of totals reconciles to bid-total / ask-total; the header pair of small counts is consistent with (#sell imbalances, #buy imbalances) but this is not stated.
4. **"Position — head of the candle" (đầu cây nến)** for a strong stacked imbalance (6:p25) is ambiguous between "at the start (open) of the candle" and "at the extreme end of the candle". The trap examples (6:p27–28) place the stack at the candle's *low* extreme, which supports "extreme".
5. **MBC is never expanded.** It is used interchangeably with "nến mẹ" (mother candle) — the large reversal candle carrying the Stack.Imb (8:p7–14). Treat as "mother/momentum breakout candle"; do not rely on the acronym.
6. **Value Area is used but not defined** in docs 6–8 (8:p7, p10, p11, p12). Context implies the price cluster of the 3–7 small stopping candles, not a volume-profile 70% VA.
7. **Copy-paste typos in the mirrored (short-side) text of doc 8:**
   - 8:p7 right column: "Candles in the up-move have decreasing spread before *stopping the decline*" — should read "stopping the rise".
   - 8:p9 (double bottom): signal says "≥120% of the *rising* candles near *top* 2" (copied from p8) — should be the declining candles near bottom 2; stop-loss says "below the *highest* bottom" — the note on the same page ("within 30% of the *lowest* bottom") and the diagram (SL at the lowest low) indicate "below the lowest bottom".
   - 8:p13 UTAD 1 title says "DỪNG GIẢM" (stop *decline*) while the body describes a stopped *rise*; UTAD 2 stop-loss says "below the *lowest* top" (should be above the highest top); UTAD 3 stop-loss says "below the mother candle" (should be above); UTAD 5/6 titles say "DỪNG GIẢM" (should be stop-rise). Rules in §3.6 use the corrected mirror.
8. **Double-top/bottom "30%" reference** (8:p8–9): the diagram brackets 30% from the extreme toward the neckline; the text says "within 30% of the highest peak". Interpreted as 30% of the extreme-to-neckline height; the base of the percentage is not stated.
9. **Delta divergence sign convention.** 7:p9 defines divergence on the *bar* (delta sign vs candle colour), while 7:p12–14 define it on *swings* of CVD vs price. Both are called "phân kỳ" — keep the two detectors separate.
10. **"Not every delta divergence means price falls"** (7:p9) vs the p10/p11 examples where both cases resolved as reversals — the deck itself warns the examples are context-dependent.
11. **Mistake #1 vs importance bullets.** 7:p7 says delta "helps determine the strength of the trend", while 7:p15 warns that large CVD does *not* imply direction (chart: price rose two days on falling CVD). Reconcile as: delta = *effort*, price = *result*; use divergence between the two, not the level of CVD.
12. **Trap examples are one-sided** — only sell traps (bid-side stacks at lows) are shown (6:p27–28); the buy-trap mirror is asserted by symmetry in doc 8 (UTAD 3) but not illustrated in doc 6.
13. **Doc 8 context templates have no text** (8:p3–6) — all criteria (AB=BC, AD ≈ 50–100% AB, 50% line, test counts) are read from diagram labels only.

---

## 7. Machine-readable summary

```yaml
# FootprintSkill — concepts extracted from Stockmap docs 6–8.
# Data assumptions: per-candle footprint rows {price, bid_vol, ask_vol}; per-candle OHLCV;
# per-candle delta = sum(ask_vol) - sum(bid_vol); cvd = running sum of delta.
# Parameters marked `param:` are left open by the source and must be tuned per market.

concepts:
  - name: bid_ask_attribution
    definition: "A print executed against resting bids (market sell / sell stop hitting buy limits) is BID volume; a print executed against resting offers (market buy / buy stop lifting sell limits) is ASK volume."
    detection_criteria: "row.bid_vol = volume of trades at price that hit the bid; row.ask_vol = volume that lifted the offer (from Time & Sales)."
    page: "6:p5, p16, p18-21"

  - name: aggressive_vs_passive
    definition: "Aggressor = immediate-fill order (market); passive = resting order (limit). BID column = aggressive sellers vs passive buyers; ASK column = aggressive buyers vs passive sellers."
    detection_criteria: "n/a (interpretation); a large ask cell may be read either as aggressive buying or passive selling — context decides."
    page: "6:p15-17"

  - name: point_of_control
    definition: "The price row with the largest traded volume in a footprint candle; where institutions are most active."
    detection_criteria: "poc = argmax over rows of (bid_vol + ask_vol) within the candle."
    page: "6:p22"

  - name: buy_imbalance
    definition: "Aggressive buy volume at a price equals >= k x aggressive sell volume one tick below (k = 250%, 300%, 400% ... depending on market)."
    detection_criteria: "ask_vol[P] >= k * bid_vol[P - tick], with bid_vol[P - tick] > 0 (or ask_vol[P] > 0 when bid below is 0). param: k default 3.0, range 2.5-4.0. Diagonal mapping inferred from 6:p23 chart."
    page: "6:p23"

  - name: sell_imbalance
    definition: "Aggressive sell volume at a price >= k x aggressive buy volume one tick above."
    detection_criteria: "bid_vol[P] >= k * ask_vol[P + tick]. param: k as above."
    page: "6:p23"

  - name: stacked_imbalance
    definition: "3 or more consecutive imbalances of the same side at adjacent price levels; marks the start or end of a trend by aggressive participants."
    detection_criteria: "run_length(consecutive same-side imbalance rows) >= 3. Emit zone = [min_price, max_price] of the run; side = buy|sell."
    page: "6:p24"

  - name: strong_stacked_imbalance
    definition: "A stacked imbalance that (1) appears at a zone/level of interest, (2) sits at the head/extreme of the candle, (3) has high or increasing volume."
    detection_criteria: "stacked_imbalance AND zone overlaps a predefined S/R or range boundary AND (zone touches candle high for sell-stack at top / candle low for buy-stack at bottom, or lies at the candle extreme) AND (sum volume of run >= volume percentile param OR volumes increase monotonically along the run). param: volume percentile."
    page: "6:p25"

  - name: stacked_imbalance_zone_respect
    definition: "Price frequently respects strong stacked-imbalance zones on retest."
    detection_criteria: "Persist zone until price closes through it; on first retest emit support (buy-stack) or resistance (sell-stack) event."
    page: "6:p26"

  - name: trap
    definition: "Traders stuck at highs or lows when the market reverses; usually a short-term opportunity."
    detection_criteria: "sell_trap: candle c has stacked sell imbalance touching its low AND subsequent close(s) > high of the stacked zone (price reverses up) -> trapped sellers, bias long. buy_trap: mirror (stacked buy imbalance at the high, price reverses down)."
    page: "6:p27-28 (sell trap illustrated; buy trap by symmetry)"

  - name: delta
    definition: "DELTA = ASK - BID over the candle."
    detection_criteria: "delta = sum(ask_vol) - sum(bid_vol)."
    page: "7:p4"

  - name: delta_percent
    definition: "DELTA% = (DELTA / VOL) * 100; used to track abnormal fluctuation at the start of a new trend."
    detection_criteria: "delta_pct = delta / total_volume * 100; flag |delta_pct| above param threshold (source gives examples like -40.5, -60, 33.33 but no threshold)."
    page: "7:p5"

  - name: cumulative_delta
    definition: "Sum of delta over the day / week / month."
    detection_criteria: "cvd[t] = cvd[t-1] + delta[t], reset per chosen period."
    page: "7:p6"

  - name: delta_price_confirmation
    definition: "To hold a position you want price and delta rising together (for longs)."
    detection_criteria: "long_ok = close[t] > close[t-1] AND delta[t] > 0 (or cvd rising); flag when price rises while delta/cvd falls."
    page: "7:p8"

  - name: bar_delta_divergence
    definition: "Positive delta on a red candle, or negative delta on a green candle; a possible reversal signal only at zones being prepared to trade; context required."
    detection_criteria: "(delta > 0 AND close < open) OR (delta < 0 AND close > open); qualify with at_zone = candle overlaps predefined level/range boundary; with_structure = at_zone AND (stacked_imbalance at the extreme facing the level)."
    page: "7:p9-11"

  - name: cvd_divergence
    definition: "Swing-based divergence between price and cumulative delta, classified Strong / Medium / Weak / Hidden for bullish and bearish."
    detection_criteria: |
      Using matched swing lows (bullish) or swing highs (bearish) of price and cvd:
        bullish_strong: price LL and cvd HL
        bullish_medium: price EL and cvd HL
        bullish_weak:   price LL and cvd EL
        bullish_hidden: price HL and cvd LL   (absorption)
        bearish_strong: price HH and cvd LH   (distribution range)
        bearish_medium: price EH and cvd LH
        bearish_weak:   price HH and cvd EH
        bearish_hidden: price LH and cvd HH
      param: swing lookback; equality tolerance.
    page: "7:p12-14"

  - name: absorption
    definition: "Aggressive selling (or buying) that fails to move price; visible as CVD falling while price holds a higher low (hidden bullish divergence)."
    detection_criteria: "bullish_hidden cvd_divergence (price HL, cvd LL); mirror for bearish."
    page: "7:p8, p13"

  - name: delta_misuse_guards
    definition: "Large CVD level is not a directional forecast; delta sign is not an entry location; positive delta only means more aggressive buys."
    detection_criteria: "Skill must not emit entry on delta sign alone; CVD level used only to compute divergence, never as a standalone bias."
    page: "7:p15"

  - name: trend_delta_management
    definition: "Per-bar delta reading in a trend: large positive bar after sideways = large aggressive buyer; sustained positive bars = effort maintained (hold); large negative bar with buying effort gone = take partial profit; selling stops + large positive bar = look for buy."
    detection_criteria: "large_bar = |delta| >= percentile param over lookback; effort_maintained = majority of last N deltas > 0; partial_profit_signal = large negative bar AND NOT effort_maintained."
    page: "7:p16"

  - name: wyckoff_context_templates
    definition: "Accumulation / re-accumulation entries at the range low after 1-2 tests; distribution / re-distribution entries at the range high after 1-2 tests; SOS(100%) when breakout leg AB = range height BC, mSOS(50%) when AB = 0.5*BC; pullback AD = 50-100% of AB to B or into the upper (lower) 50% of the range."
    detection_criteria: "Requires a range detector: range = [low C, high B]; test_count at boundary >= 1 (re-acc) or >= 2 (acc); breakout leg length AB vs BC; pullback depth AD/AB in [0.5, 1.0]; entry zone near B or within top/bottom 50% of range."
    page: "8:p3-6"

  - name: mbc_mother_candle
    definition: "Large reversal/impulse candle carrying a stacked imbalance (MBC + Stack.Imb); all doc-8 entries are at its close; if very large, wait for a 20% pullback."
    detection_criteria: "candle contains stacked_imbalance in the direction of the reversal AND body/range >= size_ref (80-120% of largest VA candle for stop patterns; 120% of nearby candles for double top/bottom). entry = close; alt_entry = close - 0.2*range (long) when range >> reference."
    page: "8:p7-14"

  - name: stopping_action_value_area
    definition: "3-7 M5 candles where price stops falling (or rising) with decreasing spread and rejection wicks; their high-low cluster is the Value Area used for the stop-loss."
    detection_criteria: "3 <= N <= 7 consecutive candles with range decreasing vs the prior impulse; lower wicks (for stop-decline) present; VA = [min low, max high] of those candles. Invalidate if many long opposite wicks or too many large candles inside VA. param: wick ratio, 'large candle' threshold."
    page: "8:p7"

  - name: signal_stop_decline_reversal_up
    definition: "Stop-decline pattern + MBC with Stack.Imb >= 80-120% of largest VA candle; entry at close; SL below VA."
    detection_criteria: "stopping_action_value_area(side=down) AND mbc_mother_candle(dir=up, size_ref=largest VA candle, factor in [0.8,1.2]) -> entry=close, sl=VA.low."
    page: "8:p7"

  - name: signal_stop_rise_reversal_down
    definition: "Mirror of the above; SL above VA."
    detection_criteria: "stopping_action_value_area(side=up) AND mbc_mother_candle(dir=down) -> entry=close, sl=VA.high."
    page: "8:p7"

  - name: signal_double_top_mbc
    definition: "Two tops; MBC with Stack.Imb >= 120% of rising candles near top 2; MBC within top 30% of the peak; SL above highest top."
    detection_criteria: "two swing highs within tolerance; candles into top 2 have decreasing range and upper wicks; mbc(dir=down) with range >= 1.2 * mean(range of rising candles near top 2); mbc.high >= peak - 0.3*(peak - neckline); NOT child candles with long lower wicks. entry=close, sl=highest top."
    page: "8:p8"

  - name: signal_double_bottom_mbc
    definition: "Mirror: MBC with Stack.Imb >= 120% of candles near bottom 2, within bottom 30%; SL below lowest bottom."
    detection_criteria: "mirror of signal_double_top_mbc."
    page: "8:p9"

  - name: signal_neckline_break_pullback
    definition: "Double bottom broke neckline; pullback into upper 50% of the pattern; stop-decline or MBC or Stack.Imb Buy triggers; SL below MBC if present else below lowest bottom."
    detection_criteria: "neckline_broken AND pullback_low >= bottom + 0.5*(neckline - bottom) AND (stopping_action OR mbc(dir=up) OR stacked_imbalance(side=buy)) -> entry=close of trigger candle; sl = mbc.low if mbc else lowest bottom."
    page: "8:p10"

  - name: spring_patterns
    definition: "Six long setups at the bottom of a Trading Range: (1) stop-decline & return to TR, (2) two bottoms with MBC at bottom 2, (3) pinbar trap-sell + MBC, (4) block & reject value, (5) stop-decline & negate the Stack.Imb zone of candle [1], (6) negate the whole candle [1]."
    detection_criteria: |
      common: mbc(dir=up) with stacked buy imbalance; entry = close (20% pullback if large).
      sp1: prior decline large range+volume; contraction; mbc.close inside TR; sl = VA.low
      sp2: two bottoms; move2 decreasing range + lower wicks; mbc at bottom 2; sl = lowest bottom
      sp3: candle1 = pinbar with lower wick (green best; red requires following contraction); trap_sell quantity large (Stack.Imb preferred); candle2 = mbc (mandatory if candle1 has no trap; strong-close prominent candle suffices if candle1 has trap+Stack.Imb); sl = mother candle low
      sp4: candle1 = single large-volume down candle out of TR with lower wick; recovery + contraction at a VA; mbc.close inside TR; sl = VA.low
      sp5: candle1 carries stacked sell imbalance out of TR; mbc.close > top of candle1's Stack.Imb zone; sl = mbc wick low
      sp6: mbc.close > candle1.open; sl = mbc wick low
    page: "8:p11-12"

  - name: utad_patterns
    definition: "Six short setups at the top of a Trading Range, exact mirrors of the spring patterns (upper wicks, trap buy, red pinbar best)."
    detection_criteria: "mirror of spring_patterns with dir=down; sl = VA.high / highest top / mother candle high / mbc wick high; u5 entry = close below bottom of candle1's Stack.Imb zone; u6 entry = close < candle1.open."
    page: "8:p13-14"

parameters_left_open_by_source:
  - imbalance_ratio_k: "250-400%+, market dependent (6:p23)"
  - strong_stack_volume_threshold: "'high or increasing' only (6:p25)"
  - delta_percent_threshold: "not given (7:p5)"
  - swing_detection_for_cvd_divergence: "not given (7:p12)"
  - large_candle_threshold_in_va: "'too many large candles' only (8:p7)"
  - trap_quantity_threshold: "'large enough' only (8:p11)"
  - candle_size_reference_for_mbc: "80-120% / 120% given; 'nearby candles' unquantified (8:p7-9)"
  - R_H_and_R_L_ratios: "undefined platform fields (6:p14)"
not_covered_by_these_sources:
  - unfinished_auction
  - exhaustion (only described as 'effort failed' / 'spread decreasing')
  - session value area / VAH / VAL / composite POC
```
