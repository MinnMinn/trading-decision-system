# Tape Reading (Wyckoff Effort vs Result) — Synthesis of StockMap "Dải Băng Giá" #1 and #2

> Scope note (important for FlowAgent design): despite the folder name "Footprint", these two decks do **not** cover footprint charts, order-book/DOM reading, time & sales, iceberg orders, delta, or absorption/exhaustion in the order-flow sense. "Tape reading" here means the Wyckoff/VSA discipline of reading **price spread + close + volume, bar by bar and swing by swing**, in the context of Wyckoff structure. Chart screenshots do show a "Delta" panel toggle next to "Volume" (Tape #1 pp.15–24, 35–38), but delta is never discussed. Anything about DOM / T&S / icebergs must come from other sources; nothing below should be attributed to these PDFs.

---

## 1. Source list

| File | Pages | Language | Content |
|---|---|---|---|
| `docs/Footprint/4. TAPE READING #1.pdf` (title: "TAPE READING #1", StockMap.vn, "Dải băng giá cho thị trường chứng khoán Việt Nam") | 39 | Vietnamese (with one English bar-by-bar annotation page, p.39) | Wyckoff 3 laws; harmony vs divergence of effort/result; notation table; spread / true range definitions; 5 uptrend cases + 5 downtrend cases with VN stock examples (5m–1h charts); 40-bar bar-by-bar worked example |
| `docs/Footprint/5. TAPE READING #2.pdf` (title: "TAPE READING #2", "Phần 2") | 26 | Vietnamese (with English annotations on p.21) | Two bar-by-bar worked examples; analog bars; importance of context; swing-by-swing comparison of down waves and up waves (extension / volume / structure); Wyckoff phase mapping; 4-step analysis sequence |

All translations below are mine from Vietnamese. Page numbers are PDF page indices (cover = p.1).

---

## 2. Core concepts (as defined by the source)

### 2.1 Tape reading (Dải băng giá / Đọc băng)
- Not explicitly defined in a single sentence; operationally it is the study of the relationship between supply and demand "using price and volume over time on the candlestick chart" (T1 p.2), applied **bar by bar**, **swing by swing**, and via **analog bars** (T2 p.26).
- "Reading tape reading according to context is the most important thing and is the key to applying the technique well" (T2 p.6).

### 2.2 Wyckoff's three laws (T1 pp.2–4)
1. **Supply (S) – Demand (D)** (T1 p.2): when demand exceeds supply price rises; when supply exceeds demand price falls. The analyst studies the S/D relationship via price and volume over time on candlestick charts.
2. **Cause and Effect (Nhân – Quả)** (T1 p.3): a price change does not happen "naturally"; the root CAUSE must be built first. Seen when price accumulates or distributes inside a trading range before leaving it. Point-and-Figure charts are used to measure cause and effect. Chart example: VN-Index 15m PnF (Traditional 0.5, 1) with box counts [122], [76], [34], labelled "Xây dựng nguyên nhân" (building the cause), "Thuyết đấu giá" (auction theory), LPSY(D), MSOW(D), and three completed targets 1226, 1205, 1182 points; annotation "rướn mua, ko còn muốn mua nữa" (stretched buying, nobody wants to buy any more).
3. **Effort vs Result (Nỗ lực – Kết quả)** (T1 p.4): **effort = volume, result = price**. Price behaviour must be reflected by volume, because without effort a move cannot be sustained. "Price is not the most important factor in the market; volume is" — but both are foundational to the Wyckoff method. **Participation of market makers ("nhà tạo lập") is identified by an increase in volume.**

### 2.3 Harmony vs Divergence (Hài hòa vs Phân kỳ) — the core reading lens (T1 pp.4–7)
- **Harmony**: "moderate price range with appropriate volume" (p.4); "large-volume effort on an up bar **with** continuation of the move" (p.5); "upward thrust with expanding range accompanied by rising volume; downside reversal accompanied by falling volume" (p.6); "thrust with rising range and rising volume that **breaks** resistance" (p.7).
- **Divergence**: "small price range with large volume" (p.4); "large-volume effort on an up bar **without** continuation" (p.5); "upward thrust with expanding range on **declining** volume; downside reversal on **rising** volume" (p.6); "thrust with rising range and rising volume that **fails** to break resistance" (p.7).
- Purpose statement (p.9): "when price crosses important support/resistance levels, you must be able to see the harmony or the anomaly of effort and result."

### 2.4 Notation (T1 p.8)
| Symbol | Meaning |
|---|---|
| E | Effort (volume) |
| R | Result (price) |
| E> / E< | Effort increasing / decreasing (volume) |
| E>> | Abnormal increase in effort |
| R> / R< | Result increasing / decreasing |
| uE / uR | Upward effort / upward result (up bar) |
| dE / dR | Downward effort / downward result (down bar) — see conflict §6.1: the table literally labels both uE and dE as "hướng lên" (upward); usage throughout T2 makes clear d = down |
| `>>>` / `<<<` | Extreme (climactic) increase / decrease (used in the case formulas, T1 pp.9, 14–36) |
| `=` , `>=`, `<=`, `=>` | Approximately equal / at least / at most (used in worked examples, T1 p.39, T2 pp.15, 22–25) |
| dER / dRR | Down-wave Effort of the Reaction / down-wave Result of the Reaction (used T2 p.15; never formally defined) |

### 2.5 What effort/result is measured by (T1 p.9)
- **Spread (Mức chênh lệch): (>, <)** — high-minus-low of the bar.
- **Close (Giá đóng cửa)** — relative to a single session (daily) or to the true range; and closes of previous sessions relative to each other.
- **Volume spike** formulas: `.VOL>>> = D>>> + S>` (spike up); `.VOL>>> = S>>> + D>` (spike down). "What matters and must be considered is whether price is closing above or below (i.e. where within) the spread."

### 2.6 Spread vs True Range (T1 pp.10–12)
- Two definitions: (a) intra-session price movement = low to high (**spread, "Chênh lệch (Cao–Thấp)"**); (b) if there is a gap between the previous and the next session, the distance from the **previous close** to the high or low of the next session is the **true range ("Phạm vi thực")**.
- Diagrams (pp.11–12) distinguish "Khoảng trống được che phủ" (gap covered/filled by the next bar's range) from "Khoảng trống không được che phủ" (gap not covered) and show the same logic for candlesticks and for intraday price paths.

### 2.7 Bars and volume — supply-first principle (T1 p.13)
- Rising volume is a sign of some change in the supply–demand relationship.
- **Think about SUPPLY first, then analyse DEMAND**, because supply is what market makers always watch or distribute; observing supply tells you whether they are buying and holding it during the trend or distributing the available supply to us.
- **The appearance of LARGE VOLUME can be a sign that the opposing side has appeared.**

### 2.8 Ten context cases (T1 pp.14–36) — see §4 for identification tables.
Named outcomes: **TĂNG GIÁ** (price rises), **DỪNG TĂNG** (rise stops), **GIẢM GIÁ** (price falls), **DỪNG GIẢM** (decline stops). Special labels: **EOM** (Ease of Movement: large spread on lower volume — T1 pp.21, 34, 35), **Climax / cao trào** (T1 pp.23, 36, 35 chart), **phe đối lập** (opposing side appears — pp.23, 36).

### 2.9 Climactic volume (T1 pp.23, 36)
"Usually when volume spikes abnormally it expresses a climax, and in many cases it is the **stopping action** for the actions about to happen (accumulation or distribution)." The opposing side has appeared; this may create a noticeable change of behaviour and entry into a different trend.

### 2.10 Analog bars (Những thanh tương tự) (T2 p.5)
- "Candles that appear similar at **equivalent positions** in a structure." By judging effort and result of analog bars, the reader can assess the strength or weakness of the bars being observed.
- Categories (colour-coded on the chart): **Climactic run analog bars** (red), **Change of Character analog bars** ("xanh lam"), **Selling climax analog bars** ("xanh dương"), **Test of climactic action analog bars** (yellow), **Up Effort off the test analog bars** (purple).

### 2.11 Context (Bối cảnh) (T2 pp.6–7, 10)
- First determine whether you are in a **trend** or a **trading range** (T2 p.10).
- Illustrated sequence (T2 p.7): bullish context (uptrend) → sign of supply appearing that could reverse the trend → a **change-of-behaviour bar** ("thanh thay đổi hành vi") that may push the prior uptrend into a trading range → a **climactic bar** ("nến cực đại") that stops the previous action and establishes the range → a bar that **tests the low of the climactic bar** and officially creates the two boundaries (high/low) of the trading range. Chart annotation: "Nên kiểm tra và xác nhận sự dừng lại" (one should test and confirm the stop).

### 2.12 Swing by swing comparison (T2 pp.8–9, 16)
Compare reactions/waves with each other on three dimensions, within a Wyckoff context (trend or trading range; phase or part of the trend):
1. **Price extension** ("Phần mở rộng giá"): points, %, whether it crosses support/resistance.
2. **Volume**: consistently increasing / decreasing. Standard practice: **compare the average volume of each wave** (T2 p.11).
3. **Structure / texture** ("Kết cấu"): the variation of spread and volume within the wave (e.g. whether individual bars show spread expansion) (T2 p.12).

### 2.13 Supply tests (T2 p.10)
Smaller down waves that follow the main down waves are "down waves (supply tests) of the main down wave".

### 2.14 Demand tail (nến đuôi cầu) (T2 pp.2, 11; T1 p.39 "demand tail")
A candle with a lower tail that shows demand has been present. Not further defined.

### 2.15 Wyckoff phase vocabulary used (not defined in these decks)
Phase A/B/C/D/E, LPS, LPSY, MSOW/mSOW, BC (Buying Climax), AR, ST, CHoCH / Change of Character, BO (breakout), SC (selling climax), accumulation / re-accumulation / distribution. Phase-specific remarks:
- Phase C: volume decreasing; "volume decreases from A to B, then increases again from B to C" (T2 p.13).
- Phase D: a successful push above the high with less effort than the prior waves ("Thường thấy trong giai đoạn D") (T2 p.22).
- Phase B: successful push above the high while both supply and demand are exhausted → expect more tests (T2 p.23).
- Phase C & D: failed push above earlier high but HH/HL → shortening of momentum (T2 p.24).
- Phase E: successful push above prior high with lower volatility / smaller spread (T2 p.25).

### 2.16 Analysis sequence (T2 p.26)
1. Identify the current environment: **Trend** or **Consolidation**.
2. Identify the Wyckoff price structure: **Wyckoff events**, **Wyckoff phases**.
3. Apply tape-reading techniques: **Bar by bar**, **Swing by swing**, **Analog bars**.
4. Finally: **Bias**, **Timing**, **Character ("Tính cách")**.

---

## 3. Actionable rules / checklists (IF / THEN, with page citations)

### 3.1 Global procedure
- R-SEQ-1: IF analysing any chart THEN follow the order: environment (trend/consolidation) → Wyckoff structure (events, phases) → tape techniques (bar-by-bar, swing-by-swing, analog bars) → output bias, timing, character (T2 p.26).
- R-CTX-1: IF you have not established whether price is in a trend or a trading range THEN do not interpret bars; context is "the key" (T2 pp.6, 10).
- R-SUP-1: IF reading any bar or wave THEN evaluate supply first, then demand (T1 p.13).
- R-SR-1: IF price crosses an important support/resistance THEN check for harmony vs anomaly of effort and result at that crossing (T1 p.9).
- R-CLOSE-1: IF a volume spike occurs THEN the deciding question is where the close sits within the bar's spread (above or below) (T1 p.9).

### 3.2 Bar-level effort/result rules (uptrend context, T1 pp.14–23)
- R-UP-1: IF spread rising AND volume rising steadily (no abnormality; `Vol> = D>> + S<`; Effort >, Result >) THEN scenario = **price rises** (harmony; demand up, supply down) (p.14; examples DPM 30m p.15, VND 1h p.16).
- R-UP-2: IF spread **falling** AND volume still rising steadily (`Vol>> = D>> + S>`; Effort >>, Result <) THEN scenario = **rise stops** — supply is present to halt the rise or reverse the trend (p.17; GEX 5m p.18).
- R-UP-3: IF spread falling AND volume falling (`Vol< = D< + S<=>`; Effort <, Result <) THEN scenario = **rise stops** — demand decreasing, supply flat or slightly rising (p.19; SSI 15m p.20).
- R-UP-4: IF spread rising AND volume falling (`Vol< = D< + S<`; Effort <, Result >) THEN scenario = **price rises** — EOM: both demand and supply decreasing (p.21; VNM 15m p.22).
- R-UP-5: IF spread rising AND volume spikes abnormally (`Vol>>> = D>>> + S>>`; Effort >>>, Result >>) THEN scenario = **rise stops** — opposing side appeared; climax; likely stopping action before accumulation/distribution (p.23; DPM 15m p.24).

### 3.3 Bar-level effort/result rules (downtrend context, T1 pp.25–36)
- R-DN-1: IF spread rising AND volume rising steadily (`Vol> = S>> + D<`; Effort >, Result >) THEN scenario = **price falls** (harmony) (p.25; KDH 15m p.26).
- R-DN-2: IF spread falling AND volume rising steadily (`Vol>> = S>> + D>`; Effort >>, Result <) THEN scenario = **decline stops** — demand present to halt the decline or reverse (p.27; DIG 15m p.28, HSG 30m p.29).
- R-DN-3: IF spread falling AND volume falling (`Vol< = S< + D<=>`; Effort <, Result <) THEN scenario = **decline stops** — supply decreasing, demand flat or slightly rising (p.30; CRE 30m p.31, VPB 30m p.32, DBC 30m p.33).
- R-DN-4: IF spread rising AND volume gradually falling (`Vol< = S< + D<`; Effort <, Result >) THEN scenario = **price falls** — EOM: supply and demand both decreasing (p.34; POW 15m p.35 shows "Climax" spike earlier in the range, then "EOM" breakdown on falling volume).
- R-DN-5: IF spread rising AND volume spikes abnormally (`Vol>>> = S>>> + D>>`; Effort >>>, Result >>) THEN scenario = **decline stops** — opposing side appeared; climax; stopping action (p.36; IDC 30m p.37, DPM 1h p.38).

### 3.4 Bar-to-bar comparison rules (derived from worked examples, T1 p.39; T2 pp.2–3)
Compare each bar with the **most recent bar of the same direction** (and with analog bars), on effort (volume) and result (spread/close):
- R-BB-1 (harmony continuation): IF dE_n > dE_prev AND dR_n > dR_prev THEN bearish continuation (T2 p.2 bars 1, 8, 9; p.3 bars 4, 9). Symmetric: uE_n > uE_prev AND uR_n > uR_prev → bullish continuation (T2 p.2 bar 11; p.3 bars 5, 7).
- R-BB-2 (effort up, result down = stopping): IF dE_n > dE_prev AND dR_n < dR_prev THEN "the down action may stop" (T2 p.2 bar 2). IF uE_n > uE_prev AND uR_n < uR_prev THEN supply / vulnerable (T1 p.39 bars 11, 37, 39).
- R-BB-3 (EOM): IF uE_n < uE_prev AND uR_n ≥ uR_prev THEN Ease of Movement → bullish (T1 p.39 bars 6, 7, 8, 26, 36; T2 p.2 bar 3 "effort not high, result large → up").
- R-BB-4 (less selling): IF dE_n < dE_prev AND dR_n < dR_prev in a decline THEN less selling / demand → bullish lean (T1 p.39 bars 3, 4, 10, 34); but in a **bearish background** the same reading is "still bearish" until a demand tail / reversal bar appears (T1 p.39 bars 20–21; T2 p.2 bars 5, 7 "vẫn Giảm").
- R-BB-5 (no demand): IF uE_n < uE_prev AND uR_n < uR_prev on a rally within a decline THEN no demand → bearish (T1 p.39 bar 17; T2 p.2 bars 4, 10; p.3 bar 3 "not yet able to rise").
- R-BB-6 (demand tail / reversal): IF a down bar shows dE_n >> dE_prev AND dR_n >> dR_prev with a demand tail, followed by an up bar with uE >> AND uR >> versus the last comparable up bar THEN reversal → bullish (T1 p.39 bars 22–23; T2 p.2 bar 12 "confirms completion of double bottom").
- R-BB-7 (supply after breakout): IF after a high-volume breakout bar (uE>, uR>) the next down bar has small effort and small result (dE<, dR<) THEN "hard to fall" (T2 p.3 bar 2); IF subsequently a down bar shows the **largest** down effort and result in the range, negating all bars of the range THEN large supply has appeared → bearish scenario (T2 p.3 bar 10; chart p.4 shows the wide-range breakdown below the range).
- R-BB-8 (absorption label): IF uE_n < uE_prev AND uR_n < uR_prev but the background is bullish and price holds THEN annotated "absorption, Bullish" (T1 p.39 bar 35) — no further criteria given.
- R-BB-9 (CHoCH bar): IF a down bar shows dE> AND dR> at the top of an uptrend THEN Change-of-Character bar → bearish (T1 p.39 bar 1).
- R-BB-10 (bias precedence): the background bias ("Bias Background = Bullish", T1 p.39) is stated first and individual bars are read as confirming or "still" contrary to it; a single contrary bar does not flip the bias.

### 3.5 Swing-by-swing rules (T2 pp.8–25)
- R-SW-1: IF comparing two analog down waves from the same boundary (e.g. range resistance) THEN compare (a) % / point extension and whether S/R was crossed, (b) average volume, (c) texture (spread expansion within bars) (T2 pp.9, 11–12).
- R-SW-2: IF the second down wave has **smaller extension** (e.g. -15.20% vs -16.60%) THEN selling force may be decreasing and a higher low is forming (T2 p.11).
- R-SW-3: IF average volume of down wave 2 < average volume of down wave 1 THEN supply is decreasing — but this does **not** by itself prove accumulation/re-accumulation; the remaining task is to locate demand and what it is doing (T2 p.11).
- R-SW-4: IF down wave 1 shows spread expansion within its bars and down wave 2 does not THEN the texture of wave 2 leans bullish; texture only adds inference about the potential trend once the trading range completes (T2 p.12).
- R-SW-5: IF a secondary (test) down wave has **greater** down effort than the previous one but its formation/spread shows a **quick return into the range** THEN potential Wyckoff Phase C; selling has stopped there and a temporary commitment to the range low is made (T2 p.12).
- R-SW-6: IF a later down wave fails to reach range support and its first leg is shallow with quick recovery THEN conclude a **bullish range** (T2 p.10, zone 3).
- R-SW-7 (down-reaction matrix, T2 p.15):
  - IF dER_n < dER_prev AND dRR_n < dRR_prev (less extension, less volume) THEN weaker reaction (R2 vs R1).
  - IF dER_n ≥ dER_prev AND dRR_n >> dRR_prev THEN determined, climactic downside (R3 vs R2).
  - IF reaction is modest above the prior reaction's top with less volume and dRR_n << dRR_prev THEN bullish (R4 vs R3).
  - IF dER_n > dER_prev but dRR_n << dRR_prev THEN bullish (effort without result on the downside) (R5 vs R4).
  - IF volume decreasing and sporadic, dER_n < dER_prev, dRR_n < dRR_prev THEN bullish (R6 vs R5).
- R-SW-8 (up waves, T2 pp.17, 20): demand is concentrated at the **start** of an up wave; late in an up wave, demand/volume declining is normal ("the value area is left behind; at high prices they are less willing to buy") — therefore **the first momentum signal is very important; watch and compare it**. An up wave "does not necessarily need large demand volume — what matters is that supply is absorbed by demand; price will still rise; nobody wants to buy any more so falling volume is normal."
- R-SW-9 (up-wave matrix, T2 pp.22–25):
  - IF uE_n > uE_prev AND uR_n > uR_prev THEN up (#2 vs #1). IF uE_n < uE_prev AND uR_n > uR_prev THEN up (#3 vs #2). IF the intention "to go above resistance" **fails** AND LL/LH THEN bearish: demand decreasing, waiting for lower prices before a rise (#2,#3).
  - IF push above the high **succeeds** with uE_n < uE_prev while uR ≫ prior AND HH/HL THEN bullish, typical Phase D; conclusion: less demand can lift price → supply exhausted; expect resistance at High #1 and then a sharp decline (#4).
  - IF push above the high succeeds with uE_n < uE_prev AND uR_n < uR_prev (vs the immediately prior wave) but uR > the earlier reference wave THEN bullish, typical Phase B; both supply and demand exhausted → expect further tests before a new trend (#5).
  - IF push above the earlier high **fails** (uE_n < ref, uR_n < ref) but the next wave prints uE_n < uE_prev with uR_n > uR_prev and HH/HL THEN shortening of momentum → bullish; typical Phases C and D (#6,#7).
  - IF uE_n ≥ uE_ref AND uR_n < uR_ref THEN down (#8 vs #5); IF uE_n << uE_prev AND uR_n ≥ uR_prev THEN up (#9); IF uE_n >> uE_prev AND uR_n exceeds all prior moves with lower volatility / smaller spread THEN bullish but **vulnerable**; typical Phase E; conclusion: demand and supply both increasing → expect a stronger rise but fragile (#10). (See §6.5 for the conflicting English annotation.)

### 3.6 Structure-level rules
- R-ST-1: IF a climactic volume bar appears in a trend THEN treat it as a **stopping action**; expect a trading range (accumulation or distribution) rather than immediate continuation (T1 pp.23, 36; T2 p.7).
- R-ST-2: IF a climactic bar has formed THEN require a **test of its low** (for a selling climax) to confirm the stop and define the range boundaries (T2 p.7).
- R-ST-3: IF Phase C is suspected THEN expect volume to have declined from A→B and to rise again B→C (T2 p.13).
- R-ST-4: IF a range breakout occurs on rising spread and rising volume THEN harmony (valid breakout); IF rising spread and rising volume but resistance is not broken THEN divergence → expect failure (T1 p.7).

---

## 4. Patterns with identification criteria

### 4.1 Ten single-bar/short-sequence context cases (T1 pp.14–36)

| Context | Case | Must be true (spread, volume) | Formula (as printed) | Reads as | Must NOT be true | Outcome |
|---|---|---|---|---|---|---|
| Uptrend | 1 | spread ↑, volume ↑ steadily | `Vol> = D>> + S<`; E>, R> | harmony, D up S down | no volume abnormality | TĂNG GIÁ (p.14) |
| Uptrend | 2 | spread ↓, volume ↑ steadily | `Vol>> = D>> + S>`; E>>, R< | effort ↑ result ↓ → supply present | spread must not be expanding | DỪNG TĂNG (p.17) |
| Uptrend | 3 | spread ↓, volume ↓ | `Vol< = D< + S<=>`; E<, R< | demand fading | — | DỪNG TĂNG (p.19) |
| Uptrend | 4 | spread ↑, volume ↓ | `Vol< = D< + S<`; E<, R> | EOM (ease of movement) | no supply spike | TĂNG GIÁ (p.21) |
| Uptrend | 5 | spread ↑, volume spikes abnormally | `Vol>>> = D>>> + S>>`; E>>>, R>> | climax, opposing side | — | DỪNG TĂNG (p.23) |
| Downtrend | 1 | spread ↑, volume ↑ steadily | `Vol> = S>> + D<`; E>, R> | harmony | no abnormality | GIẢM GIÁ (p.25) |
| Downtrend | 2 | spread ↓, volume ↑ steadily | `Vol>> = S>> + D>`; E>>, R< | demand present | — | DỪNG GIẢM (p.27) |
| Downtrend | 3 | spread ↓, volume ↓ | `Vol< = S< + D<=>`; E<, R< | supply fading | — | DỪNG GIẢM (p.30) |
| Downtrend | 4 | spread ↑, volume gradually ↓ | `Vol< = S< + D<`; E<, R> | EOM | — | GIẢM GIÁ (p.34) |
| Downtrend | 5 | spread ↑, volume spikes abnormally | `Vol>>> = S>>> + D>>`; E>>>, R>> | climax, opposing side | — | DỪNG GIẢM (p.36) |

Chart-example annotations (what the author points at): "Mức chênh lệch tăng/giảm" (spread rising/falling), "Khối lượng tăng đều / tăng / giảm / tăng đột biến" (volume rising steadily / rising / falling / spiking), "Climax", "EOM".

### 4.2 Harmony / Divergence templates (T1 pp.4–7)
- **Harmony-continuation**: series of up bars with progressively larger ranges and progressively larger volume; big volume bar followed by further advance.
- **Divergence-top**: small-range bar on the largest volume at the top of a run (p.4); or big-volume up bar with no follow-through (p.5); or expanding ranges on shrinking volume followed by down bars on rising volume (p.6).
- **Breakout validity**: rising range + rising volume that closes through resistance = harmony; same effort but price fails to hold above resistance = divergence (p.7).

### 4.3 Bar-by-bar double bottom (T2 p.2, 12 bars)
1. dE>, dR> → down. 2. dE2>dE1, dR2<dR1 → down action may stop. 3. uE3<, uR3> → up. 4. uE4<uE3, uR4<uR3 → down. 5. dE5<dE2 with demand tail, dR5<dR2 → still down. 6. dE6<dE5, dR6 much < dR5 → up. 7. uE7<uE4, uR7<uR4 → still down. 8. dE8>dE6, dR8>dR6 → down. 9. dE9>dE8, dR9>dR8 → down. 10. uE10<uE7, uR10<uR7 → down. 11. uE11>uE10, uR11>uR10 → up. 12. uE12 largest vs 4,7,10,11 and uR12 largest vs 3,4,7,10,11 → **confirms completion of the double bottom → up**.
Identification: the confirming bar must have both the largest up-effort and largest up-result of the whole formation.

### 4.4 Bar-by-bar failed breakout / upthrust-type sequence (T2 pp.3–4, 10 bars)
1. Up bar breaks important resistance on large volume (uE1>, uR1>) → bullish scenario. 2. Down bar, low effort, low result (dE2<, dR2<) → hard to fall. 3. uE3<uE1, uR3<uR1 → not yet able to rise. 4. dE4>dE2, dR4>dR2 → bearish scenario. 5. uE5>uE3, uR5>uR3 → bullish. 6. (see §6.3) → bullish. 7. uE7 > uE6,5,3 and uR7 > uR6,5,3 → bullish. 8. Down bar with narrowing spread = sign of supply (dE8<, dR8<) → observe supply. 9. dE9>dE8, dR9>dR8 → bearish. 10. Largest down effort and largest down result in the range, negating all bars in the range → large supply appeared → bearish. Chart p.4: the range (two horizontal lines) is broken above (dashed line), then a wide red bar with the largest volume of the chart drives price back to the range low.

### 4.5 Analog-bar map (T2 p.5)
At each swing top in the chart the same five bar types recur in the same order: climactic run bar (red box) → change-of-character bar → selling-climax bar → test-of-climax bar → up-effort-off-the-test bar, each pointing down to its volume bar. Identification = same position in structure + comparable effort/result.

### 4.6 Trend-to-range transition (T2 pp.6–7)
Uptrend → supply sign → change-of-behaviour bar (red bar at the top on high volume) → climactic bar (largest volume on the chart) stops the move and sets the range low → test bar (lower volume) confirms → range boundaries established (upper = top before the CoC bar, lower = climax low; dashed line below = test low).

### 4.7 Trading-range down-wave comparison (T2 pp.8–13)
Three main declines from resistance: -16.60% (Volatility >>), -15.20% (Volatility <), -6.84% (Volatility <<<), each followed by a smaller Phase-C supply test (-9.03%, -10.37%, -8.31%). Volume peak declines from decline 1 to decline 2; volume rises into the last test (arrow up on volume). Identification of bullish range: successive declines shrink in extension, average volume, and spread expansion; final test fails to reach support and recovers quickly.

### 4.8 Reaction series R1–R6 in an uptrend (T2 pp.14–15)
R1 -14.86% (20 bars, 28d) → R2 -10.81% (8 bars) → R3 -18.47% (16 bars, 23d, climactic) → minor -3.56% / -3.41% → R4 -11.91% (26 bars, 39d; labelled BC, AR, ST, mSOW) → R5 -10.27% (9 bars, 13d) → R6 -6.37% (15 bars, 21d). Blue lines on the volume pane mark average volume per reaction. Pattern: after the climactic R3, each subsequent reaction has smaller result relative to effort → bullish.

### 4.9 Up-wave series in Phase C→E (T2 pp.16–25)
Waves: 13.65% (Phase C), 17.05%, 6.39%, 5.07%, 8.18%, 18.69% (Phase C, 46 bars 68d), 6.43%, 16.08% (50 bars 72d), 6.36%, 7.44% (Phase C), 25.65% (128 bars 186d), 7.83%. Second series (#1–#10): 4.54% (16 bars 24d), ~9–10% (8 bars 10d), 10.69% (8 bars 13d), 35.37% (82 bars 120d), 16.00% (36 bars 51d), 7.82%, 8.56%, 13.17% (39 bars 55d), 13.70% (35 bars 52d), 9.38% (17 bars 24d). Reading rule: judge each wave by (intention: exceed prior high? success/failure), (HH/HL vs LL/LH), (effort vs result vs the previous comparable wave), and map to a Wyckoff phase.

---

## 5. Quantitative details (everything numeric in the sources)

- Timeframes used in examples: 5m (GEX), 15m (SSI, VNM, DPM, KDH, DIG, POW), 30m (DPM, HSG, CRE, VPB, DBC, IDC), 1h (VND, DPM), daily/weekly index charts in T2; PnF 15m VN-Index with box size 0.5, reversal 1 (T1 p.3).
- PnF cause counts: [122] box, [76] box, [34] box; targets 1226, 1205, 1182 points, all completed (T1 p.3).
- Down-wave extensions (T2 pp.8–13): -777.75 (-16.60%) with -3111 [bar count/volume figure as printed], -401.00 (-9.03%) -1604, -274.75 (-5.81%) -1099, -714.25 (-15.20%) -2857, -446.75 (-10.37%) -1787, -313.50 (-6.84%) -1254, -377.75 (-8.31%) -1511.
- Reactions R1–R6 (T2 p.14): -1148.25 (-14.86%) -4593 (20 bars, 28d); -781.50 (-10.81%) -3126; -1318.50 (-18.47%) -5274 (16 bars, 23d); -268.75 (-3.56%) -1075; -245.75 (-3.41%) -983; -938.25 (-11.91%) -3753 (26 bars, 39d); -827.25 (-10.27%) -3309 (9 bars, 13d); -508.50 (-6.37%) -2034 (15 bars, 21d).
- Up waves (T2 pp.16–20): 533.50 (13.65%) 2134; 689.00 (17.05%) 2750; 284.50 (6.39%) 1138; 226.50 (5.07%) 906; 325.75 (8.18%) 1303; 722.00 (18.69%) 2888 (46 bars, 68d); 274.50 (6.43%) 1098; 670.25 (16.08%) 2681 (50 bars, 72d); 294.25 (6.36%) 1177; 339.25 (7.44%) 1357; 1206.00 (25.65%) 4824 (128 bars, 186d); 435.50 (7.83%) 1742.
- Up waves #1–#10 (T2 p.21): 335.75 (4.54%) 1343 (16 bars, 24d); 650.50 (~9%) (8 bars, 10d); 689.50 (10.69%) 2758 (8 bars, 13d); 2059.00 (35.37%) 8236 (82 bars, 120d); 1110.50 (16.00%) 4442 (36 bars, 51d); (7.82%) 2260; 629.50 (8.56%) 2518; 984.50 (13.17%) 3938 (39 bars, 55d); 1119.00 (13.70%) 4476 (35 bars, 52d); 837.50 (9.38%) (17 bars, 24d).
- Text comparisons: "17%" vs "18.69%" (T2 p.17), "16%" (p.18), "17%" vs "18%" (p.20) — see §6.6.
- Bar-by-bar example lengths: 40 bars (T1 p.39), 12 bars (T2 p.2), 10 bars (T2 p.3).
- No numeric thresholds are given for "abnormal" volume (`>>>`), "steady" increase, or spread ratios. No stop-loss, target, or position-sizing numbers anywhere.

---

## 6. Conflicts and ambiguities inside these sources

1. **Notation table typo (T1 p.8)**: rows read "Nỗ lực hướng lên (uE)" and "Nỗ lực hướng lên (dE)"; likewise "Kết quả hướng lên (uR)" and "Kết quả hướng lên (dR)". Both are labelled "upward". Usage in T2 (e.g., "Nỗ lực giảm giá … (dE>, dR>)") confirms d = downward. Treat dE/dR as down-bar effort/result.
2. **Downtrend case 5 formula label (T1 p.36)**: scenario text says DỪNG GIẢM (decline stops) and the arrow is up, but the printed formula line reads "Nỗ Lực >>>, Kết quả >>= **Giảm giá**". By symmetry with uptrend case 5 (p.23, "Giảm giá" for DỪNG TĂNG) this should read "Tăng giá". Treat the scenario text as authoritative.
3. **Bar 6 in T2 p.3**: prose says "up effort of bar 6 is **smaller** than bar 5, result of bar 6 better than bar 5", but the formula prints "(uE6>uE5, uR6>uR5)". Prose (uE6<uE5, uR6>uR5 = EOM) is consistent with the rest of the example; the formula is likely a typo.
4. **Wave #4 formulas (T2 p.22)**: "uE #4 < uE #3, uR #2 >> uR #1 → Tăng. uE #4 = uE #1, uR #3 >> uR #2 → Tăng." The uR indices (#2/#1, #3/#2) do not match the uE indices (#4/#3, #4/#1); most likely intended uR#4 >> uR#3 and uR#4 >> uR#1. Ambiguous as printed.
5. **Wave #10 (T2 pp.21 vs 25)**: the English annotation on the chart (p.21) says "uR#10 **<** All Earlier moves", "Higher high, Higher Low => **Bearish**; Phase E", "Conclusion – Increasing Supply and so expect further sharp Drop and then go up". The Vietnamese text (p.25) says "uR #10 **>** all prior moves", HH/HL → bullish, "demand and supply both increasing → expect a stronger rise but vulnerable". Direction of uR#10 and the HH/HL verdict are contradictory. Both agree on "bullish but vulnerable / lower volatility, smaller spread".
6. **"Volume" percentages (T2 pp.17, 20)**: the text compares "khối lượng" (volume) of wave 1 "(17%)" vs wave 2 "(18.69%)", but 17.05% and 18.69% on the chart are **price extensions**, not volume. Likely the author means the waves' size; the sentence conflates volume and extension.
7. **KDH chart annotation (T1 p.26)** for downtrend case 1 (spread rising) is labelled "Mức chênh lệch giảm" (spread falling) — probably meaning "spread in the down direction" / downward spread; inconsistent with the case definition wording.
8. **Analog-bar colours (T2 p.5)**: "xanh lam" and "xanh dương" both mean blue in Vietnamese; on the chart the Change-of-Character bars are olive/green boxes and Selling-climax bars are light blue. Colour mapping is ambiguous; rely on the category names.
9. **R2 vs R1 wording (T2 p.15)**: "less volume, **demand** decreases" for a down wave with lower volume; by the deck's own supply-first logic this should read as supply decreasing. Read literally it is ambiguous.
10. **dER / dRR** (T2 p.15) are never defined; inferred as down-reaction effort / result.
11. **"Absorption"** (T1 p.39 bar 35) and **"demand tail"** are used as labels without criteria.
12. **Scope mismatch** (see header): no DOM / T&S / iceberg / delta content, despite the folder name and despite "Delta" toggles visible on the charts.

---

## 7. Machine-readable summary

```yaml
source_set: stockmap_tape_reading
files:
  - path: "docs/Footprint/4. TAPE READING #1.pdf"
    pages: 39
    language: vi (p.39 en)
  - path: "docs/Footprint/5. TAPE READING #2.pdf"
    pages: 26
    language: vi (p.21 en)
not_covered:
  - dom_orderbook_reading
  - time_and_sales
  - iceberg_orders
  - footprint_delta
  - order_flow_absorption_exhaustion
notation:
  E: volume (effort)
  R: price spread/close (result)
  uE_uR: up-bar effort/result
  dE_dR: down-bar effort/result
  ">": increasing
  "<": decreasing
  ">>": abnormal increase
  ">>>": extreme/climactic increase
  "=": approximately equal
  dER_dRR: down-reaction effort/result (undefined in source, inferred)

concepts:
  - name: law_supply_demand
    definition: "Demand > supply -> price rises; supply > demand -> price falls; studied via price and volume over time on candlesticks."
    detection_criteria: "n/a (axiom)"
    page: "T1 p.2"
  - name: law_cause_effect
    definition: "A price move requires a cause built first, seen as accumulation/distribution in a trading range; measured with PnF box counts."
    detection_criteria: "Trading range present before breakout; PnF horizontal count gives targets."
    page: "T1 p.3"
  - name: law_effort_result
    definition: "Effort = volume, result = price; a sustainable move needs matching effort. Market-maker participation is identified by rising volume."
    detection_criteria: "Compare volume change vs spread/close change bar to bar."
    page: "T1 p.4"
  - name: harmony
    definition: "Effort and result agree: moderate range with fitting volume; large-volume up bar followed by continuation; expanding range with rising volume; breakout of resistance on rising range and volume."
    detection_criteria: "sign(dVolume) == sign(dSpread) and follow-through in the same direction"
    page: "T1 pp.4-7"
  - name: divergence
    definition: "Effort and result disagree: small range on large volume; large-volume up bar without continuation; expanding range on falling volume; rising range+volume that fails to break resistance."
    detection_criteria: "large volume with small spread, or expanding spread with falling volume, or no follow-through / failed S-R break"
    page: "T1 pp.4-7"
  - name: spread
    definition: "High minus low of the bar/session."
    detection_criteria: "high - low"
    page: "T1 pp.9-12"
  - name: true_range
    definition: "When a gap exists between sessions, distance from previous close to the high or low of the next session."
    detection_criteria: "max(high, prev_close) - min(low, prev_close) when gap not covered"
    page: "T1 pp.10-12"
  - name: close_position_in_spread
    definition: "Whether price closes above or below within the spread; the decisive question on volume-spike bars."
    detection_criteria: "(close - low) / (high - low) relative to midpoint"
    page: "T1 p.9"
  - name: volume_spike_composition
    definition: "VOL>>> = D>>> + S> (spike on up move) or VOL>>> = S>>> + D> (spike on down move); the big side dominates but the opposing side is also present."
    detection_criteria: "volume >> recent bars; direction from bar close"
    page: "T1 p.9"
  - name: supply_first_principle
    definition: "Analyse supply before demand because market makers watch/distribute supply; large volume can signal the opposing side."
    detection_criteria: "procedural"
    page: "T1 p.13"
  - name: uptrend_case_1_harmony_rise
    definition: "Spread rising, volume rising steadily, no abnormality -> price rises."
    detection_criteria: "spread_n > spread_prev AND vol_n > vol_prev AND vol_n not spike; formula Vol> = D>> + S<"
    page: "T1 p.14"
  - name: uptrend_case_2_supply_stops_rise
    definition: "Spread falling while volume rises steadily -> effort up, result down -> supply present -> rise stops (possible reversal)."
    detection_criteria: "spread_n < spread_prev AND vol_n > vol_prev; formula Vol>> = D>> + S>"
    page: "T1 p.17"
  - name: uptrend_case_3_demand_fades
    definition: "Spread falling and volume falling -> demand decreasing -> rise stops."
    detection_criteria: "spread_n < spread_prev AND vol_n < vol_prev; formula Vol< = D< + S<=>"
    page: "T1 p.19"
  - name: uptrend_case_4_eom_rise
    definition: "Spread rising on falling volume (Ease of Movement) -> both supply and demand decreasing -> price rises."
    detection_criteria: "spread_n > spread_prev AND vol_n < vol_prev; formula Vol< = D< + S<"
    page: "T1 p.21"
  - name: uptrend_case_5_climax_stops_rise
    definition: "Spread rising with abnormal volume spike -> opposing side appears -> climax, stopping action -> rise stops."
    detection_criteria: "spread_n > spread_prev AND vol_n >>> recent; formula Vol>>> = D>>> + S>>"
    page: "T1 p.23"
  - name: downtrend_case_1_harmony_fall
    definition: "Spread rising, volume rising steadily -> price falls."
    detection_criteria: "spread_n > spread_prev AND vol_n > vol_prev on down bars; formula Vol> = S>> + D<"
    page: "T1 p.25"
  - name: downtrend_case_2_demand_stops_fall
    definition: "Spread falling while volume rises steadily -> demand present -> decline stops (possible reversal)."
    detection_criteria: "spread_n < spread_prev AND vol_n > vol_prev on down bars; formula Vol>> = S>> + D>"
    page: "T1 p.27"
  - name: downtrend_case_3_supply_fades
    definition: "Spread falling and volume falling -> supply decreasing -> decline stops."
    detection_criteria: "spread_n < spread_prev AND vol_n < vol_prev on down bars; formula Vol< = S< + D<=>"
    page: "T1 p.30"
  - name: downtrend_case_4_eom_fall
    definition: "Spread rising on gradually falling volume (EOM) -> supply and demand decreasing -> price falls."
    detection_criteria: "spread_n > spread_prev AND vol_n < vol_prev on down bars; formula Vol< = S< + D<"
    page: "T1 p.34"
  - name: downtrend_case_5_climax_stops_fall
    definition: "Spread rising with abnormal volume spike -> opposing side appears -> climax, stopping action -> decline stops."
    detection_criteria: "spread_n > spread_prev AND vol_n >>> recent on down bar; formula Vol>>> = S>>> + D>>"
    page: "T1 p.36"
  - name: ease_of_movement
    definition: "Price moves with larger spread on less volume; both sides have withdrawn."
    detection_criteria: "spread_n > spread_prev AND vol_n < vol_prev"
    page: "T1 pp.21,34,35,39"
  - name: climactic_bar
    definition: "Abnormal volume spike bar; expresses a climax and usually is the stopping action before accumulation/distribution; establishes a range boundary."
    detection_criteria: "vol_n >>> recent AND wide spread; then expect test of its extreme"
    page: "T1 pp.23,36; T2 p.7"
  - name: change_of_character_bar
    definition: "Bar whose effort/result differs from the trend's character; may push a trend into a trading range."
    detection_criteria: "in uptrend: down bar with dE> and dR> (T1 p.39 bar1)"
    page: "T1 p.39; T2 pp.5,7"
  - name: test_of_climax
    definition: "Bar that revisits the climactic bar's extreme on lower volume, confirming the stop and defining the range."
    detection_criteria: "price near climax low/high, vol < climax vol"
    page: "T2 pp.5,7"
  - name: demand_tail
    definition: "Down bar with a lower tail showing demand was present."
    detection_criteria: "long lower wick on a down bar (source gives no ratio)"
    page: "T2 pp.2,11; T1 p.39"
  - name: analog_bars
    definition: "Bars appearing similar at equivalent positions in a structure; comparing their effort/result grades strength/weakness. Types: climactic run, change of character, selling climax, test of climactic action, up effort off the test."
    detection_criteria: "same structural position + comparable spread/volume"
    page: "T2 p.5"
  - name: bar_by_bar_analysis
    definition: "Compare each bar's effort and result with the previous bar of the same direction (and analogs); classify as continuation, EOM, no demand, less selling, supply, absorption, reversal; read against background bias."
    detection_criteria: "pairwise uE/uR or dE/dR comparisons per rules R-BB-1..R-BB-10"
    page: "T1 p.39; T2 pp.2-3"
  - name: double_bottom_confirmation
    definition: "Confirming bar has the largest up-effort and largest up-result versus all prior up bars of the formation."
    detection_criteria: "uE_n > max(prior uE) AND uR_n > max(prior uR)"
    page: "T2 p.2"
  - name: failed_breakout_supply_bar
    definition: "After a range breakout, a down bar with the largest down effort and result of the range negates the range -> large supply."
    detection_criteria: "dE_n > max(range dE) AND dR_n > max(range dR) AND close back inside/below range"
    page: "T2 pp.3-4"
  - name: context_trend_vs_range
    definition: "First step of any read: determine trend vs trading range; then Wyckoff and Modern Tools events/phases."
    detection_criteria: "procedural"
    page: "T2 pp.6,10,26"
  - name: swing_by_swing
    definition: "Compare analog waves on price extension (points, %, S/R crossed), volume (average per wave, consistency), and texture (spread/volume variation within the wave), within Wyckoff and Modern Tools phase context."
    detection_criteria: "wave_n vs wave_prev on extension_pct, mean_volume, spread_expansion_flag"
    page: "T2 pp.8-9,11-12,16"
  - name: supply_test_wave
    definition: "Smaller down wave following a main down wave; tests supply."
    detection_criteria: "secondary decline after main decline, smaller extension"
    page: "T2 p.10"
  - name: bullish_trading_range
    definition: "Successive declines shrink in extension and average volume, lack spread expansion, and the final test fails to reach support with quick recovery."
    detection_criteria: "ext_n < ext_prev AND meanvol_n < meanvol_prev AND no bar spread expansion AND low_n > range_support"
    page: "T2 pp.10-12"
  - name: phase_c_volume_profile
    definition: "Phase C shows decreasing volume; volume falls A->B then rises B->C."
    detection_criteria: "declining wave volume through B, rising into C test"
    page: "T2 p.13"
  - name: reaction_comparison_matrix
    definition: "R_n vs R_prev: lower effort+lower result = weaker reaction; higher effort+much higher result = climactic; lower effort+much lower result = bullish; higher effort+much lower result = bullish; falling sporadic volume+smaller spread = bullish."
    detection_criteria: "see R-SW-7"
    page: "T2 p.15"
  - name: up_wave_intention_test
    definition: "Each up wave judged by intention to exceed the prior high (success/failure), HH/HL vs LL/LH, and effort vs result relative to the prior wave; mapped to Wyckoff and Modern Tools phase B/C/D/E."
    detection_criteria: "see R-SW-9"
    page: "T2 pp.21-25"
  - name: early_momentum_importance
    definition: "Demand concentrates at the start of an up wave; falling volume late in an up wave is normal (value left behind); the first momentum signal is the key comparison."
    detection_criteria: "compare initial thrust volume/extension across waves"
    page: "T2 pp.17,20"
  - name: shortening_of_momentum
    definition: "Failed attempt to exceed the earlier high followed by HH/HL with lower effort and higher result -> bullish (Phases C-D)."
    detection_criteria: "uE_n < uE_prev AND uR_n > uR_prev after a failed break, with HH/HL"
    page: "T2 p.24"
  - name: analysis_sequence
    definition: "1 environment (trend/consolidation) -> 2 Wyckoff and Modern Tools structure (events, phases) -> 3 tape techniques (bar-by-bar, swing-by-swing, analog bars) -> 4 bias, timing, character."
    detection_criteria: "pipeline order"
    page: "T2 p.26"

rules_index:
  procedure: [R-SEQ-1, R-CTX-1, R-SUP-1, R-SR-1, R-CLOSE-1]
  bar_context_uptrend: [R-UP-1, R-UP-2, R-UP-3, R-UP-4, R-UP-5]
  bar_context_downtrend: [R-DN-1, R-DN-2, R-DN-3, R-DN-4, R-DN-5]
  bar_by_bar: [R-BB-1, R-BB-2, R-BB-3, R-BB-4, R-BB-5, R-BB-6, R-BB-7, R-BB-8, R-BB-9, R-BB-10]
  swing_by_swing: [R-SW-1, R-SW-2, R-SW-3, R-SW-4, R-SW-5, R-SW-6, R-SW-7, R-SW-8, R-SW-9]
  structure: [R-ST-1, R-ST-2, R-ST-3, R-ST-4]

quantitative_thresholds_given: none   # source never quantifies "abnormal", "steady", or spread ratios
conflicts: see section 6 (items 1-12)
```
