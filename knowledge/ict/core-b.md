# TTrades Core B — CISD, Order/Breaker/Mitigation Blocks, MSS, SMT, PO3/AMD, Std-Dev Projections, IRL/ERL, Relative Strength, Silver Bullet AM

Synthesis of 13 TTrades_edu slide-deck PDFs (folder `docs/TTrades PDFs/`). These decks are almost entirely annotated chart diagrams with very little prose. Where a statement below is **quoted prose** from a slide it is marked `[text]`; where it is **read from the diagram** it is marked `[diagram]`. Nothing below is added from outside the PDFs except the clearly labelled **Adaptation notes** for crypto (BTC/ETH/SOL, 24/7) and commodity CFDs (Gold/Silver/Oil).

Citation format: `File p<physical PDF page> (printed <n>)`. Physical page 1 is the cover, page 2 is the table of contents, and the last page is always "Resources" (links only, no content).

---

## 1. Source list

| # | File | Physical pages | Content pages (printed) | Sections (from TOC) |
|---|------|----------------|-------------------------|---------------------|
| 1 | `16. CISD.pdf` | 5 | p3–p4 (both printed "1") | CISD |
| 2 | `17. Orderblocks.pdf` | 9 | p3–p8 (1–6) | Orderblocks (1), Mean Threshold (5), Stop Losses (6) |
| 3 | `18. Market_Structure_Shift.pdf` | 6 | p3–p5 (1–3) | Displacement (1), Market Structure Shift (2), Higher Time Frame Level (3) |
| 4 | `19. BreakerBlocks.pdf` | 20 | p3–p19 (1–16; "16" used twice) | Fair Value Gaps, Breaker Blocks, Unicorn, Stop Losses, OB vs BB |
| 5 | `20. Mitigation_Blocks.pdf` | 15 | p3–p14 (1–12) | Mitigation Blocks |
| 6 | `21. SMT.pdf` | 12 | p3–p11 (1–9) | Correlated Pairs Bullish/Bearish (+SMT), Inversely Correlated Pairs (+SMT) |
| 7 | `22. Power_Of_Three.pdf` | 7 | p3–p6 (1–4) | OHLC/OLHC (1), AMD (2), Power Of Three (3), Entries (4) |
| 8 | `23. Standard_Deviation_Projections.pdf` | 11 | p3–p10 (1–8) | Settings (1), Anchoring (2–5), Retracement or Reversal (6), Max Expansion (7), Pairing with PD Arrays (8) |
| 9 | `24. AMD_STD.pdf` | 10 | p3–p9 (1–7) | AMD (1–5), Standard Deviation Projection (6), Combination (7) |
| 10 | `IRL-ERL.pdf` | 11 | p3–p10 (1–8) | Internal Liquidity (1), External Liquidity (2), Relationship (3–8) |
| 11 | `MSS_vs_CISD.pdf` | 7 | p3–p6 (1–4) | Market Structure Shift (1), CISD (2), Comparison (3), Inversion (4) |
| 12 | `Relative_Strength_ES.NQ.pdf` | 7 | p3–p6 (1–4) | What is RS/RW (1), Using SMT (2), Using ES/NQ Chart (3), Reversals (4) |
| 13 | `Silver_Bullet_AM.pdf` | 6 | p3–p5 (1–3) | Time (1), Framework (2–3) |

Total: 126 physical pages, all read (text layer via `pdftotext -layout` plus full visual read of every page).

---

## 2. Core concepts

### 2.1 Displacement
- `[text]` "Displacement is an aggressive move with full-bodied candles. This can form in a single candle or in multiple candles. Generally, displacement candle(s) have FVG present." — `18. MSS p3 (1)`.
- `[diagram]` Shown as one large full-bodied candle closing beyond a marked swing level, with prior candles drawn hollow/neutral to contrast the displacement candle. — `18. MSS p3 (1)`.

### 2.2 Market Structure Shift (MSS)
- `[text]` "When displacement occurs over or below a swing high or low, a market structure shift happens." — `18. MSS p4 (2)`.
- `[text]` "Having bodies close over/below previous structure is preferred. A stop raid before the MSS is preferred." (italic footnote) — `18. MSS p4 (2)`.
- `[text]` "A market structure shift (MSS) indicates a change in trend from bullish to bearish or bearish to bullish." — `18. MSS p4 (2)`.
- `[text]` "It is important that a higher time frame level is engaged prior to the lower time frame market structure shift." — `18. MSS p5 (3)`.
- `[diagram]` Bearish MSS: price sweeps a prior swing high (dashed line, yellow ▼ marks the raid high), then a large black candle closes **below the swing low that preceded the run-up** (bracket labelled "Market Structure Shift" is on that swing low). Bullish MSS: price runs below the "Higher Time Frame Level", then a green displacement candle closes above the swing high preceding the drop. — `18. MSS p4 (2), p5 (3)`; `MSS_vs_CISD p3 (1)`.

### 2.3 Change In State of Delivery (CISD)
- No prose in the CISD deck; definition is entirely `[diagram]` — `16. CISD p3–p4 (both printed 1)`; identical diagram in `MSS_vs_CISD p4 (2)`.
- `[diagram]` Bearish CISD: price rallies into an "Important Level" (drawn above), sweeps a prior swing high (dashed line), and the last **up-close (green) candle(s)** of that rally define the level. A horizontal "CISD" line is drawn at the **opening price of that up-close candle**. The CISD is confirmed when a subsequent candle **closes below that open**. — `16. CISD p3`.
- `[diagram]` Bullish CISD: price drops into an "Important Level" (drawn below), sweeps a prior swing low, the last **down-close (black) candle(s)** define the level; CISD line at the **open of the down-close candle**; confirmed when a candle **closes above** it. — `16. CISD p3`.
- `[diagram]` Variant (p4): when the final leg into the level is a **series of consecutive same-colour candles**, the CISD line is drawn at the open of the **first candle in that series** (i.e. the lowest open of the consecutive up-closes for bearish; the highest open of the consecutive down-closes for bullish). The close through that open is the CISD. — `16. CISD p4`.
- Relationship to OB: the Orderblocks deck reuses the exact same two diagrams with the line relabelled "OB" (blue) instead of "CISD". So in TTrades' framing the **order block is the candle(s) whose open forms the CISD line**; a CISD = a close through the OB open. — `17. Orderblocks p3 (1)` vs `16. CISD p3`.

### 2.4 MSS vs CISD (distinction)
- `[diagram]` On the "Comparison" slide both are marked on the same price sequence. Bearish case: the **CISD** line is the open of the last up-close candle (higher); the **MSS** level is the swing low that preceded the run-up (lower). Bullish case: the CISD is the open of the last down-close candle (lower); the MSS level is the swing high that preceded the drop (higher). The same displacement leg triggers the CISD **first** (closer to the extreme), then the MSS (further away). — `MSS_vs_CISD p5 (3)`.
- Implication (faithful to diagram): CISD is the earlier, tighter confirmation; MSS is the later, stronger confirmation requiring a break of actual swing structure.
- `[diagram]` "Inversion" slide (no text): a V-reversal where a **bearish FVG** left on the way down is closed through by the bullish displacement; the FVG is then retested **from above** as support (inverted FVG) and price continues up. Placed under MSS-vs-CISD as the third confirmation/entry element after the shift. — `MSS_vs_CISD p6 (4)`.

### 2.5 Order Block (OB)
- No prose definition; all `[diagram]` — `17. Orderblocks p3–p8`.
- Definition by diagram: in a bullish reversal the OB is the **last down-close candle** before the displacement up; its **open** is marked as the OB line. In a bearish reversal the OB is the **last up-close candle** before the displacement down; its open is the OB line. — `p3 (1)`.
- Validity/confirmation elements shown:
  1. It forms **at an "Important Level"** after a **stop raid** of a prior swing (dashed line). — `p3 (1)` (the Important Level label; `p6 (4)` shows the raid dashed line and OB line only).
  2. The candle after the OB **closes through the OB open** (this is the CISD). — `p3 (1)`, `p4 (2)`.
  3. In a trend, successive OBs stack: each down-close candle in an uptrend whose open is closed above becomes the next OB. — `p4 (2)`.
  4. OB + FVG confluence: the OB (down-close candle) sits inside/adjacent to a bullish FVG (orange box) formed by the preceding candles; the confirming green candle closes above the OB open. — `p5 (3)`.
- **Mean Threshold**: a fib drawn over the OB candle body with 0 at the OB **open**, 0.5 at the **body midpoint** ("mean threshold"), 1 at the OB **close**. Price is shown retracing to the 0.5 level after the CISD and then continuing. — `p7 (5)`.
- **Stop losses**: two options drawn side by side — (a) at the **OB candle's body low (its close)** — the red risk zone of the "OB" column ends exactly on the body bottom while the candle's lower wick extends below it, so the tight stop is the close, not the wick low; or (b) below the **swing low** created by the stop raid (the raid candle's wick low, wider). Green shading above = reward, red below = risk; the green/red boundary (entry reference) is the blue OB line. — `p8 (6)` (re-verified against the PDF at 110–150 dpi, 2026-09-12 — `docs/audits/2026-09-12-ict-pdf-recheck.md`).

### 2.6 Fair Value Gap (FVG) — as used in these decks
- `[diagram]` Bearish FVG: three consecutive down candles; the gap between candle 1's low and candle 3's high. Bullish FVG: gap between candle 1's high and candle 3's low. — `19. Breaker p16 (14)`; identical drawing labelled "Internal Range Liquidity" in `IRL-ERL p3 (1)`.
- `[text]` Displacement "generally" has an FVG present. — `18. MSS p3 (1)`.

### 2.7 Breaker Block (BB)
- No prose; the deck is a step-by-step construction `[diagram]` — `19. Breaker p3–p15`.
- **Bullish breaker construction** (`p4–p9`, printed 2–7):
  1. Downtrend makes a **Low** (▲). — p4 (2)
  2. Bounce makes a **High** (▼). — p5 (3)
  3. Price takes out the Low → **Lower Low** (▲) (liquidity swept). — p6 (4)
  4. Displacement up closes above the High → **Higher High** (▼). — p7 (5)
  5. The grey box (breaker) is drawn over the **full range, wicks included, of the up-close candle that formed the High** — box top = that candle's wick high, box bottom = its wick low; the adjacent down-close candle's wicks fall outside the box. Not a body-only zone. — p8 (6); same box on p3, p9, p17–p19 (re-verified against the PDF at 110–150 dpi, 2026-09-12 — `docs/audits/2026-09-12-ict-pdf-recheck.md`). Variant in the TTRS and Unicorn decks: the box spans the whole pre-sweep swing (both up-close and down-close candles) from the swing high down to the swept low — see `06-ttrades-models` §2.9 step 5, §6 item 16.
  6. Price retraces into the box and continues higher. — p9 (7)
- **Bearish breaker** is the mirror: High → Low → **Higher High** (sweep) → **Lower Low** (displacement) → box over the **full range (wicks) of the down-close candle that formed the Low** → retrace into box → continuation down. — `p10–p15` (8–13); box verified on p14–p15.
- Overview slide shows the completed bullish setup with the sweep dashed line, breaker box and continuation. — `p3 (1)`.
- **OB vs BB** `[diagram]`: same bullish breaker; a blue "OB" line is drawn at the **open of the down-close candle inside the breaker box**. I.e. the breaker range contains the order block; the OB is the finer level within the breaker. — `p19 (printed 16, second use)`.
- **Stop losses** `[diagram]`: two shaded columns, no labels. The green→red boundary (entry reference) in both columns sits at the **top of the breaker box**. (a) Tight: the red zone ends **below the box bottom**, on the **low of the displacement candle** (the candle that made the Higher High) — not on the box's own low; (b) wide: below the **Lower Low** (the swept extreme). — `p18 (16)` (re-verified against the PDF at 110–150 dpi, 2026-09-12 — `docs/audits/2026-09-12-ict-pdf-recheck.md`).

### 2.8 Unicorn Model
- `[diagram]` A breaker block that **overlaps with an FVG**. Bearish: sweep of a high (▼), displacement makes a lower low, grey breaker box at the prior swing-low candles, an FVG (two horizontal lines) sits inside/overlapping the box; price retraces into the overlap and continues down. Bullish mirror shown below it. — `19. Breaker p17 (15)`.

### 2.9 Mitigation Block (MB)
- No prose; `[diagram]` only — `20. Mitigation p3–p14`.
- Construction (`p3 (1)`): downtrend makes a Low; bounce makes a High; price returns down but **fails to take the Low** (the second low holds above the dashed line from the first low — a higher low / failure swing); displacement up closes above the High; grey box drawn over the **full range (wicks) of the up-close candle** that formed the High (same construction as the breaker box, p3–p4); price retraces into the box and continues.
- **Key differentiator from a breaker** (from the two decks side by side): Breaker = the prior extreme **was** swept (Lower Low / Higher High made). Mitigation = the prior extreme was **not** swept (higher low / lower high made). — `19. Breaker p6 (4)` vs `20. Mitigation p3 (1)`.
- `[diagram]` The second slide adds a blue "SMT" line across the two lows — the higher low that creates a mitigation block is the kind of failure swing that shows up as SMT versus a correlated asset. — `20. Mitigation p4 (2)`.
- **Sequence in context** (`p5–p14`, printed 3–12): downtrend into an "HTF Level"; a small bounce high (line); a green displacement candle closes above that high leaving an FVG (two lines) — p6 (4); pullback into the FVG — p7 (5); grey mitigation box drawn over the up-close candles from the **previous consolidation in the downtrend** — box top at the wick high, box bottom at roughly the body lows (the deck is not consistent about the lower edge between p3–p4 and p8) — p8 (6); blue line slightly above the box bottom as price enters — p9 (7); second blue line slightly above the box top as price passes through — p10 (8) (both sit at the **open of a down-close candle**, i.e. the OB/CISD line convention of `17. Orderblocks p4`, rather than exactly on the box edges); continuation — p11 (9); a **second, higher mitigation box** drawn at the next earlier consolidation of the downtrend — p12 (10); price reaches it and a small dashed FVG inside it is respected — p13 (11); price continues above — p14 (12).
- Reading: after the HTF-level reversal, the up-close candle bodies left behind on the way down (unmitigated) act as successive **targets / continuation levels** ("mitigation") on the way back up.

### 2.10 SMT (Smart Money Technique) divergence
- No prose; `[diagram]` — `21. SMT p3–p11`.
- **Correlated pairs, normal (no SMT)**: both assets make Low → Higher Low (bullish, p3/1) or High → Lower High (bearish, p6/4).
- **Bullish SMT**: asset A makes Low → **Lower Low**; asset B makes Low → **Higher Low**. Line labelled "SMT" connects the two lows on each chart. — p4 (2), p5 (3).
- **Bearish SMT**: asset A makes High → **Higher High**; asset B makes High → **Lower High**. — p7 (5), p8 (6).
- **Inversely correlated pairs, normal**: A High→Higher High while B Low→Lower Low; or A High→Lower High while B Low→Higher Low. — p9 (7).
- **Inverse SMT**: A High→Higher High while B Low→**Higher Low** (B fails to make its lower low); or A High→Lower High while B Low→**Lower Low**. — p10 (8), p11 (9).
- Used elsewhere: SMT marks the failure-swing low of a mitigation block (`20. Mitigation p4 (2)`) and defines relative strength/weakness (`Relative_Strength p4 (2)`).

### 2.11 Power of Three (PO3) / AMD
- `[diagram]` **OHLC / OLHC**: a single bullish candle expanded into its lower-timeframe path: Open → dip **below the open** (Low) → rally (High) → Close = **O-L-H-C**. A bearish candle: Open → rally above open (High) → decline (Low) → Close = **O-H-L-C**. Dashed line drawn at the candle's open. — `22. PO3 p3 (1)` (`24. AMD_STD p4 (2)` shows AMD boxes only, not this anatomy).
- `[diagram]` **AMD** boxes: **Accumulation** (green) = ranging around the open; **Manipulation** (red) = the move **against** the eventual direction, beyond the open (below the open for a bullish candle, above for bearish); **Distribution** (blue) = the expansion in the true direction. Bearish is the mirror. — `22. PO3 p4 (2)`; `24. AMD_STD p3 (1)`.
- `[diagram]` PO3 on candles: accumulation box around the open, manipulation box below the open (bullish) / above (bearish), distribution box after. — `22. PO3 p5 (3)`; `24. AMD_STD p5 (3)`.
- `[diagram]` **Entries**: an arrow from the manipulation box (below the accumulation range) up into the distribution box; a second zig-zag arrow inside the distribution box. I.e. entries are taken **during/at the end of manipulation** (against the open) and on **pullbacks within distribution**. — `22. PO3 p6 (4)`.
- `[diagram]` Manipulation leg isolation: the manipulation box is widened to start at the **high of the last accumulation candle(s) before the drop** and end at the manipulation low. This is the swing that gets anchored for standard deviations. — `24. AMD_STD p6 (4), p7 (5)`.

### 2.12 Standard Deviation Projections (STD)
- `[diagram]` **Settings** (TradingView "Fib Retracement" tool): enabled levels **1, 0, -1, -2, -2.5, -4**; disabled 0.236, 0.5, 0.786, 1.618, 3.618, 1.272; Trend line off; Extend lines left/right off; Background on; Reverse off; Prices off; Levels = Values; Labels Left / Middle; Font 10; "Fib levels based on log scale" off. — `23. STD p3 (1)`.
- `[diagram]` **Anchoring (bullish)**: fib drawn over the **manipulation leg** with **1 at the manipulation low** and **0 at the manipulation swing high** (where the manipulation began). Negative levels project **above**: -1, -2, -2.5, -4. Price expands to -4. — `23. STD p4 (2)`; `24. AMD_STD p8 (6)`.
- `[diagram]` **Anchoring (bearish)**: uptrend sweeps a high (dashed), a dashed line marks the **low of the manipulation leg** (where the sweep started) — p5 (3); that leg is boxed pink — p6 (4); fib with **1 at the sweep high, 0 at the manipulation low**; -1, -2, -2.5, -4 project **below** — p7 (5).
- `[diagram]` **Retracement or Reversal zone**: the band between **-2 and -2.5** (yellow) — price reaching it is expected to retrace or reverse. — `23. STD p8 (6)`.
- `[diagram]` **Max Expansion**: **-4** is the maximum expected expansion. — `23. STD p9 (7)`.
- `[diagram]` **PD Array Pairing**: the **-2** level coincides with a prior swing low (dashed line from an earlier low). Std-dev levels are confirmed/selected by pairing them with PD arrays / liquidity. — `23. STD p10 (8)`.
- `[diagram]` **Combination**: AMD boxes plus STD — the distribution box runs from 0 up to the -4 level. — `24. AMD_STD p9 (7)`.

### 2.13 Internal Range Liquidity (IRL) vs External Range Liquidity (ERL)
- `[diagram]` **IRL** = Fair Value Gaps (bearish and bullish FVG drawings). — `IRL-ERL p3 (1)`.
- `[diagram]` **ERL** = swing highs (**Buyside Liquidity**, red arc over the high) and swing lows (**Sellside Liquidity**, red arc under the low). — `IRL-ERL p4 (2)`.
- `[diagram]` **Relationship**: price rallies from an ERL (range low), tops, drops leaving a bearish FVG (IRL) and reaches the ERL (dashed line at the range low) — p5 (3); arrow: once ERL is taken, expect a move **to the IRL** (the FVG) — p6 (4); price rallies into the IRL — p7 (5); a **new ERL** is defined at the recent sweep low — p8 (6); arrow from IRL **to the new ERL** — p9 (7); price drops to it — p10 (8).
- Rule shown: price alternates **ERL → IRL → ERL**. After taking external liquidity, target internal (FVG); after reaching internal, target the next external.

### 2.14 Relative Strength / Weakness (ES vs NQ)
- `[text]` "Relative Strength or Weakness is when comparing correlated assets, assessing which one is more bullish (strength) or bearish (weakness)." — `Relative_Strength p3 (1)`.
- `[diagram]` Strength = the asset with the larger up-move / smaller down-move; Weakness = the asset with the smaller up-move / larger down-move over the same candles. — p3 (1).
- `[text]` "SMT can be used to show a divergence between correlated assets. This can be used to show relative strength and weakness." `[diagram]` The asset making the **higher low** = Relative Strength; the one making the **lower low** = Relative Weakness. — p4 (2).
- `[text]` "Relative Strength or Weakness can be determined comparing ES to NQ by charting ES1! / NQ1! on Tradingview." `[diagram]` ES/NQ ↑ ⇒ ES ↑ (stronger), NQ ↓ (weaker); ES/NQ ↓ ⇒ ES ↓, NQ ↑. — p5 (3).
- `[text]` "My Theory is reversals on ES1!/NQ1! can be used to show the change in correlation and used to anticipate a reversal on ES or NQ and/or determine relative strength." `[diagram]` Ratio chart sweeps a low (dashed) then rallies and takes the prior high — flips from ES/NQ↓ (ES↓ NQ↑) to ES/NQ↑ (ES↑ NQ↓). Explicitly labelled a theory. — p6 (4).

### 2.15 Silver Bullet — AM session
- `[diagram]` **Time**: "AM Session Silver Bullet Window (EST)" = **10:00–11:00**, with **9:30** marked as the reference start (NY equities open). — `Silver_Bullet_AM p3 (1)`.
- `[text]` "Intraday bias video uses the previous candles high and low to frame a reversal. The previous hourly candle (9:00am) will be used in this framework." `[diagram]` 9:00am hourly high and 9:00am hourly low drawn for a bearish and a bullish 9:00 candle. — p4 (2).
- `[diagram]` NASDAQ 1-minute: during 10:00–11:00 price **sweeps the 9:00am hourly high** shortly after 10:00, reverses, and declines **through the 9:00am hourly low** before 11:00. — p5 (3).

---

## 3. Actionable rules / checklists (IF/THEN)

### 3.1 Context / pre-conditions
- R1. IF you are looking for a lower-timeframe MSS/CISD entry, THEN require a **higher-timeframe level to be engaged first**. `[text]` `18. MSS p5 (3)`.
- R2. IF a swing high/low is about to be broken, THEN prefer setups where a **stop raid preceded** the break. `[text]` `18. MSS p4 (2)`; `[diagram]` OB at Important Level after sweep `17. OB p3, p6`.
- R3. IF price has just taken **external range liquidity** (swing high/low), THEN the next objective is **internal range liquidity** (nearest opposing FVG); IF price has reached IRL, THEN the next objective is the **next ERL**. `[diagram]` `IRL-ERL p6 (4), p9 (7)`.

### 3.2 Confirmation
- R4. IF displacement (full-bodied candle(s), usually with FVG) closes **beyond a swing high/low** → **MSS**; prefer **body** close beyond structure, not wick. `[text]` `18. MSS p3–p4`.
- R5. IF, after a sweep into an Important Level, a candle **closes through the open of the last opposing-colour candle(s)** of the sweep leg → **CISD**. When the sweep leg is a run of consecutive same-colour candles, use the open of the **first** candle of that run. `[diagram]` `16. CISD p3, p4`.
- R6. IF CISD is confirmed, THEN the candle(s) whose open was closed through is the **OB**; the OB open is the entry line; the OB body mid (0.5) is the **mean threshold** deeper-entry line. `[diagram]` `17. OB p3, p7`.
- R7. CISD triggers before MSS on the same leg. IF you want the earliest confirmation use CISD; IF you want a structural confirmation, wait for MSS (break of the pre-run swing). `[diagram]` `MSS_vs_CISD p5 (3)`.
- R8. IF a bearish FVG on the way down is **closed through** by the bullish displacement and then retested from above and holds → **inversion** confirmation for the long (mirror for shorts). `[diagram]` `MSS_vs_CISD p6 (4)`.
- R9. IF two correlated assets diverge at a swing (one makes a new extreme, the other fails) → **SMT**; the asset that **failed** to make the new low shows **relative strength** (prefer it for longs); the asset that failed to make the new high shows relative weakness (prefer it for shorts). `[diagram]` `21. SMT p4–p8`; `Relative_Strength p4 (2)`.

### 3.3 Entry
- R10. **OB entry**: IF CISD confirmed at an Important Level, THEN entry at the OB open (limit) or at the 0.5 mean threshold of the OB body. Stop at the OB candle's body low / close (tight — p8 draws the risk zone ending on the close, not the wick) or below the raid swing low (wide). `[diagram]` `17. OB p7 (5), p8 (6)`.
- R11. **Breaker entry**: IF Low → High → Lower Low (sweep) → displacement to Higher High, THEN mark the full range (wicks included) of the up-close candle at the High as the breaker; enter on the retrace into the breaker (entry reference = box top); stop below the low of the displacement candle that made the Higher High (tight — drawn below the box bottom on p18) or below the Lower Low (wide). Mirror for bearish. `[diagram]` `19. Breaker p4–p9, p18 (16)`.
- R12. **Unicorn entry**: IF a breaker box overlaps an FVG, THEN entry zone = the overlap. `[diagram]` `19. Breaker p17 (15)`.
- R13. **Mitigation entry/targets**: IF a reversal from an HTF level occurs **without** the prior extreme being swept (higher low / SMT), THEN mark the opposing-colour candle range (wicks included on p3–p4) at the prior swing as a mitigation block; use it for the pullback entry and mark successive earlier consolidation bodies as continuation targets. `[diagram]` `20. Mitigation p3–p14`.
- R14. **PO3 entry**: IF price trades **beyond the period open against the expected direction** (manipulation), THEN look to enter at/after the end of manipulation for the distribution leg; add on pullbacks within distribution. `[diagram]` `22. PO3 p6 (4)`.
- R15. **Silver Bullet AM**: IF time is **10:00–11:00 New York**, THEN frame the trade on the **9:00am hourly candle's high/low**; IF price sweeps the 9:00 high (or low) inside the window and reverses, THEN target the opposite side of the 9:00 candle. `[text+diagram]` `Silver_Bullet_AM p3–p5`.

### 3.4 Targets / management
- R16. IF the manipulation leg is identified, THEN anchor the fib **1 at the manipulation extreme, 0 at the manipulation origin**; expect **-1, -2, -2.5, -4** as projections in the distribution direction. `[diagram]` `23. STD p4–p7`; `24. AMD_STD p8`.
- R17. IF price reaches **-2 to -2.5**, THEN expect **retracement or reversal** — take profit / tighten. `[diagram]` `23. STD p8 (6)`.
- R18. **-4** is the **max expansion** target; do not project beyond it. `[diagram]` `23. STD p9 (7)`.
- R19. IF a std-dev level **coincides with a PD array / liquidity** (e.g. -2 on a prior swing low), THEN prefer that level as the target. `[diagram]` `23. STD p10 (8)`.
- R20. IF after ERL is taken price reaches IRL (FVG), THEN that is the first target; re-define ERL at the new sweep extreme for the next leg. `[diagram]` `IRL-ERL p6–p10`.

### 3.5 Invalidation
- R21. OB long: invalid if price closes below the OB candle's body low / close (tight) or below the raid swing low (wide). `[diagram]` `17. OB p8 (6)`.
- R22. Breaker long: invalid below the displacement-candle low (tight, below the box bottom) or below the Lower Low (wide). `[diagram]` `19. Breaker p18 (16)`.
- R23. MSS without an engaged HTF level, or without body closes beyond structure, is lower quality (stated as "important"/"preferred", not as hard invalidation). `[text]` `18. MSS p4–p5`.
- R24. RS/RW ratio reversal is explicitly "My Theory" — treat as a supplementary read, not a standalone trigger. `[text]` `Relative_Strength p6 (4)`.

---

## 4. Patterns with identification criteria

| Pattern | MUST be true | MUST NOT be true | Source |
|---|---|---|---|
| **Displacement** | Aggressive full-bodied candle(s); single or multiple; FVG generally present | Small-bodied / wick-dominated candles | `18. MSS p3` |
| **MSS (bearish)** | Prior swing high raided (preferred); displacement candle body closes below the swing low preceding the run-up; HTF level engaged first | Wick-only break; no HTF context | `18. MSS p4–p5` |
| **MSS (bullish)** | Mirror: raid of low, body close above swing high preceding the drop | — | `18. MSS p5` |
| **CISD (bearish)** | Rally into Important Level with sweep of prior high; a close **below the open of the last up-close candle(s)** of the rally (first candle of a same-colour run) | Close only below wick; no level/sweep context (diagram always shows both) | `16. CISD p3–p4` |
| **CISD (bullish)** | Mirror: close above open of last down-close candle(s) | — | `16. CISD p3–p4` |
| **Order Block (bullish)** | Last down-close candle before displacement up; forms at Important Level after stop raid; subsequent close above its open (CISD); ideally overlapping an FVG | Candle whose open was never closed through | `17. OB p3–p6` |
| **Breaker (bullish)** | Sequence Low → High → **Lower Low** → **Higher High**; box over the up-close candle's full range (wicks) at the High; retrace into box | Lower Low not made (then it is a mitigation block) | `19. Breaker p4–p9` |
| **Breaker (bearish)** | High → Low → **Higher High** → **Lower Low**; box over the down-close candle's full range (wicks) at the Low | — | `19. Breaker p10–p15` |
| **Unicorn** | Breaker box AND FVG overlap; entry in overlap | Breaker or FVG alone | `19. Breaker p17` |
| **Mitigation block (bullish)** | Low → High → **higher low (Low NOT swept)** → displacement above High; box over the up-close candle range at the High; SMT often present at the higher low | Prior low swept (then breaker) | `20. Mitigation p3–p4` |
| **SMT (bullish)** | Correlated A: Low → Lower Low; B: Low → Higher Low at the same swing | Both make lower lows (no divergence) | `21. SMT p4–p5` |
| **SMT (bearish)** | A: High → Higher High; B: High → Lower High | Both make higher highs | `21. SMT p7–p8` |
| **Inverse SMT** | Inversely-correlated pair: A makes a new extreme, B fails to make its **opposite** new extreme | Both extend as expected | `21. SMT p10–p11` |
| **PO3 bullish candle** | Path O → L (below open) → H → C; manipulation box below open; distribution above | Candle never trades below its open (no manipulation) | `22. PO3 p3–p5` |
| **STD projection** | Fib on manipulation leg, 1 at extreme, 0 at origin; levels -1/-2/-2.5/-4 in distribution direction | Anchoring on the distribution leg | `23. STD p4–p7` |
| **IRL** | An FVG inside the current range | — | `IRL-ERL p3` |
| **ERL** | Swing high (buyside) / swing low (sellside) bounding the range | — | `IRL-ERL p4` |
| **Inversion (IFVG)** | FVG closed through by displacement, then retested from the other side and holds | FVG merely wicked | `MSS_vs_CISD p6` |
| **Silver Bullet AM** | Time 10:00–11:00 NY; sweep of 9:00am hourly high/low inside window; reversal toward the other side of the 9:00 candle | Setup outside window; 9:00 candle range not referenced | `Silver_Bullet_AM p3–p5` |
| **Relative strength via ratio** | ES/NQ ratio rising ⇒ ES strong / NQ weak; falling ⇒ inverse | — | `Relative_Strength p5` |

---

## 5. Quantitative details

| Item | Value | Timezone / units | Source |
|---|---|---|---|
| Silver Bullet AM window | 10:00–11:00 | "EST" per slide (New York local time; slide labels it EST regardless of DST). 10:00 NY = 14:00 UTC during EDT (Mar–Nov), 15:00 UTC during EST (Nov–Mar). | `Silver_Bullet_AM p3 (1)` |
| Reference candle for AM Silver Bullet | 9:00am hourly candle (high & low) | NY time, 1H | `Silver_Bullet_AM p4 (2)` |
| NY equities open marker | 9:30 | NY time | `Silver_Bullet_AM p3 (1)` |
| Std-dev levels enabled | 1, 0, -1, -2, -2.5, -4 | Fib retracement tool | `23. STD p3 (1)` |
| Std-dev levels disabled | 0.236, 0.5, 0.786, 1.618, 3.618, 1.272 | — | `23. STD p3 (1)` |
| Fib anchor convention | 1 = manipulation extreme, 0 = manipulation origin; negatives project in distribution direction | — | `23. STD p4, p7` |
| Retracement-or-reversal zone | -2 to -2.5 | std-dev of manipulation leg | `23. STD p8 (6)` |
| Max expansion | -4 | std-dev | `23. STD p9 (7)` |
| PD-array pairing example | -2 on prior swing low | — | `23. STD p10 (8)` |
| OB mean threshold | 0.5 of OB body (0 = open, 1 = close) | fib on body | `17. OB p7 (5)` |
| OB stop options | OB candle body low (close); raid swing low (wick) | price | `17. OB p8 (6)` |
| Breaker stop options | displacement-candle low (below box bottom); Lower Low. Entry reference = box top | price | `19. Breaker p18 (16)` |
| Ratio symbol for RS/RW | ES1! / NQ1! | TradingView | `Relative_Strength p5 (3)` |
| Fib tool font | 10; labels Left/Middle; log scale off | TradingView | `23. STD p3 (1)` |

No other numeric thresholds (e.g. minimum displacement size, FVG size, ATR multiples, R:R) appear in these decks.

---

## 6. Conflicts, ambiguities, gaps

1. **CISD line placement**: `16. CISD p3` draws the line at the open of the *last* up-close candle; `p4` draws it at the open of the *first* candle of a same-colour run. Both are labelled "1". Reconcile as: use the open of the **first candle of the final consecutive same-colour run** (which equals the last candle when the run is length 1). Detector should treat both as valid and report which variant fired.
2. **OB = CISD candle**: The OB deck reuses the CISD diagrams verbatim with the label swapped. Therefore "OB" in TTrades usage is the *opening price line* of the CISD candle, not necessarily a full-body zone. The Mean Threshold slide, however, treats the OB as a **body zone** (0 → 0.5 → 1). Both readings coexist: line for trigger, body for entry depth.
3. **Breaker box extent** (re-verified against the PDF at 110–150 dpi, 2026-09-12 — `docs/audits/2026-09-12-ict-pdf-recheck.md`): in `19. Breaker` the box is the **wick-to-wick range of the single up-close (bullish) / down-close (bearish) candle** at the swing; the neighbouring candle's wicks are excluded. The earlier "bodies" reading was wrong. `TTRS p8, p17` and `Unicorn p5` draw a wider box covering **both colours** around the intermediate swing. Two sourced variants → box bounds stay a declared parameter, choose one per detector and say which.
4. **Mitigation deck sequence (p5–p14)** does not explain what the two blue lines (p9, p10) are. At 150 dpi they sit slightly off the box edges, at the **opens of down-close candles** inside the mitigation leg — the OB/CISD line convention — rather than exactly on the box bottom/top. Both readings recorded; inference either way.
5. **MSS "swing low" reference**: the MSS bracket in `18. MSS p4` and `MSS_vs_CISD p3` is on the swing low **immediately preceding the run-up into the raid**, not an older structural low. Detector should use the most recent opposing swing before the raid leg.
6. **Silver Bullet "EST"**: slide says EST; in practice the window is NY local time. Ambiguity about DST is not addressed in the deck.
7. **Relative-strength reversal rule** is explicitly labelled "My Theory" — lower confidence than the rest.
8. **Inversion slide** in `MSS_vs_CISD` has no text and is not tied explicitly to MSS or CISD; its position (after Comparison) implies it is the follow-through/entry element, but that is inference.
9. **PO3 "Entries" slide** shows arrows only; whether entry is at the manipulation extreme or on the first CISD after manipulation is not specified. Cross-deck consistency (CISD/OB decks) suggests: manipulation sweep → CISD → OB entry.
10. **No timeframes** are specified anywhere except the 1-minute NASDAQ chart and the 9:00 hourly candle in the Silver Bullet deck, and "higher time frame level" / "lower time frame MSS" in the MSS deck.
11. Std-dev deck shows **1 at the manipulation extreme** (the more recent point) and **0 at the origin** for both directions — do not flip anchors; the negative levels always project through 0 away from 1.
12. **CISD before MSS is a level ordering, not a time ordering** — on `MSS_vs_CISD p5 (3)` the same displacement candle closes through both the CISD line and the MSS level. A detector must not assume a separate earlier CISD bar exists.
13. **OB stop = body low** — `17. Orderblocks p8` ends the tight risk zone on the OB candle's close, with the wick below it (§2.5). **Breaker tight stop = displacement-candle low**, drawn below the box bottom (`19. Breaker p18`, §2.7). Recorded 2026-09-12 after the PDF re-check.
14. **Minor citation fixes (2026-09-12)**: OHLC/OLHC appears only in `22. PO3 p3`, not in `24. AMD_STD`; the "orange" lines in `23. STD p5, p9` are plain dashed/grey lines; `18. MSS p4–p5` also mark a later continuation sweep (▲/▼) not described in §2.2; the "NY equities open" gloss on 9:30 in `Silver_Bullet_AM p3` is inference (the slide prints only the time); `17. Orderblocks p6` has no "Important Level" label (only p3 does).

---

## Adaptation notes (NOT in the PDFs — for crypto 24/7 and commodity CFDs)

- **SMT pairs**: the decks only show generic "correlated pairs" and "inversely correlated pairs" (ES/NQ named only in the RS deck). Candidate pairs for the user's universe: BTC/ETH, BTC/SOL, ETH/SOL (correlated); Gold/Silver (correlated); WTI/Brent (correlated). Inverse-SMT logic (`21. SMT p9–p11`) would apply to e.g. Gold vs DXY if DXY is available — not in the source.
- **Relative-strength ratio**: replace ES1!/NQ1! with BTC/ETH, ETH/SOL, XAU/XAG ratio charts; the ratio-direction table on `Relative_Strength p5` maps 1:1 (numerator strong when ratio rises).
- **Silver Bullet AM**: session-bound (NY 10:00–11:00, 9:00 hourly candle). Crypto trades 24/7 but NY hours still carry US flow; commodity CFDs follow the same NY clock. Convert to UTC (14:00–15:00 UTC in EDT, 15:00–16:00 UTC in EST) and reference the 9:00 NY hourly candle. Applying the "previous hourly candle high/low" framework to other windows is an extrapolation, not sourced.
- **PO3 open reference**: the decks use "the candle's open" abstractly. For crypto, the daily open is exchange-dependent (00:00 UTC is standard); for CFDs use the broker's daily open or NY midnight — the PDF does not specify.
- Everything else (CISD, OB, MSS, breaker, mitigation, STD, IRL/ERL, inversion) is price-action-only and applies unchanged.

---

## 7. Machine-readable summary

```yaml
meta:
  source_folder: "docs/TTrades PDFs/"
  files: 13
  physical_pages: 126
  page_citation: "physical PDF page (printed label)"
  evidence_tags: {text: "quoted prose on slide", diagram: "read from chart drawing"}

concepts:
  - name: displacement
    definition: "Aggressive move with full-bodied candle(s), single or multiple; generally leaves an FVG."
    evidence: text
    detection_criteria:
      - "body_size / range >= high (full-bodied); tunable threshold, not given in source"
      - "one or more consecutive same-direction candles"
      - "FVG present between candle[i-1].high/low and candle[i+1].low/high (usually)"
    source: "18. Market_Structure_Shift.pdf"
    page: "p3 (1)"

  - name: market_structure_shift
    aliases: [MSS]
    definition: "Displacement closing over/below a swing high or low, indicating a change in trend; body close preferred; stop raid before it preferred; HTF level must be engaged first."
    evidence: text+diagram
    detection_criteria:
      - "HTF level engaged (price reached a higher-timeframe level) before the LTF break"
      - "bearish: prior swing high raided (wick above) THEN displacement candle CLOSE < swing_low_preceding_the_raid_leg"
      - "bullish: prior swing low raided THEN displacement candle CLOSE > swing_high_preceding_the_raid_leg"
      - "reference swing = most recent opposing swing before the raid leg"
    source: "18. Market_Structure_Shift.pdf; MSS_vs_CISD.pdf"
    page: "18: p4 (2), p5 (3); MSS_vs_CISD: p3 (1)"

  - name: change_in_state_of_delivery
    aliases: [CISD]
    definition: "After a sweep into an important level, a close through the opening price of the last opposing-colour candle(s) of the sweep leg."
    evidence: diagram
    detection_criteria:
      - "context: price at/through an important level AND prior swing swept"
      - "bearish: identify final run of consecutive up-close candles ending at the raid high; level = OPEN of first candle in that run; trigger = candle CLOSE < level"
      - "bullish: final run of consecutive down-close candles ending at the raid low; level = OPEN of first candle in run; trigger = CLOSE > level"
      - "variant A (p3): run length 1 -> level = open of the single last opposing candle"
      - "variant B (p4): run length >1 -> level = open of first candle of the run"
    source: "16. CISD.pdf; MSS_vs_CISD.pdf"
    page: "16: p3 (1), p4 (1); MSS_vs_CISD: p4 (2)"

  - name: mss_vs_cisd_ordering
    definition: "On the same reversal leg the CISD level sits closer to the extreme than the MSS level, so CISD confirms first, MSS second."
    evidence: diagram
    detection_criteria:
      - "bearish: cisd_level (open of last up-close) > mss_level (pre-raid swing low)"
      - "bullish: cisd_level (open of last down-close) < mss_level (pre-raid swing high)"
      - "emit CISD event before MSS event; MSS requires close beyond swing"
    source: "MSS_vs_CISD.pdf"
    page: "p5 (3)"

  - name: inversion_fvg
    aliases: [IFVG, inversion]
    definition: "An FVG that is closed through by displacement and then retested from the opposite side as support/resistance."
    evidence: diagram
    detection_criteria:
      - "bullish: bearish FVG exists; candle CLOSE > fvg.top; later price returns to [fvg.bottom, fvg.top] and holds (close stays above fvg.bottom); continuation up"
      - "bearish: mirror"
    source: "MSS_vs_CISD.pdf"
    page: "p6 (4)"

  - name: order_block
    aliases: [OB]
    definition: "Last opposing-colour candle before displacement at an important level after a stop raid; its open is the OB line (equal to the CISD level); body midpoint is the mean threshold."
    evidence: diagram
    detection_criteria:
      - "bullish OB = last down-close candle before bullish displacement; ob_line = candle.open; ob_body = [candle.close, candle.open]"
      - "bearish OB = last up-close candle before bearish displacement; ob_line = candle.open"
      - "valid when a subsequent candle closes through ob_line (CISD)"
      - "quality: formed at important level; prior swing swept; overlapping/adjacent FVG"
      - "mean_threshold = ob.open + 0.5*(ob.close - ob.open)  # 0=open, 0.5=mid, 1=close"
      - "stops: ob_candle.body_low = ob_candle.close (tight, 17. OB p8) | raid_swing_low (wide); mirror for bearish"
    source: "17. Orderblocks.pdf"
    page: "p3 (1), p4 (2), p5 (3), p6 (4), p7 (5), p8 (6)"

  - name: fair_value_gap
    aliases: [FVG, internal_range_liquidity]
    definition: "Three-candle gap: bullish = candle1.high < candle3.low; bearish = candle1.low > candle3.high."
    evidence: diagram
    detection_criteria:
      - "bullish: low[i+1] > high[i-1] -> zone [high[i-1], low[i+1]]"
      - "bearish: high[i+1] < low[i-1] -> zone [high[i+1], low[i-1]]"
    source: "19. BreakerBlocks.pdf; IRL-ERL.pdf"
    page: "19: p16 (14); IRL-ERL: p3 (1)"

  - name: breaker_block
    aliases: [BB, breaker]
    definition: "Opposing-colour candle bodies at the intermediate swing of a sequence where the prior extreme is swept and then structure is displaced the other way; price retraces into it for continuation."
    evidence: diagram
    detection_criteria:
      - "bullish: swing Low(L1) -> swing High(H1) -> Lower Low(L2 < L1, sweep) -> displacement CLOSE > H1 (Higher High)"
      - "bullish box = full range of the up-close candle forming H1: [low, high] wicks included (19. Breaker p8); variant (TTRS p17, Unicorn p5): [swept low, swing high] over both colours"
      - "bearish: High(H1) -> Low(L1) -> Higher High(H2 > H1) -> displacement CLOSE < L1 (Lower Low); box = full range (wicks) of the down-close candle forming L1"
      - "entry on first retrace into box (entry reference = box top); stops: displacement_candle.low (tight, below box bottom, 19. Breaker p18) | L2 (wide)"
      - "OB within breaker = open of the opposing candle inside the box (blue line)"
    source: "19. BreakerBlocks.pdf"
    page: "p3 (1), p4–p9 (2–7), p10–p15 (8–13), p18 (16), p19 (16)"

  - name: unicorn_model
    definition: "Breaker block overlapping a fair value gap; the overlap is the entry zone."
    evidence: diagram
    detection_criteria:
      - "breaker_box intersects fvg_zone -> entry_zone = intersection"
      - "direction and sequence as breaker_block"
    source: "19. BreakerBlocks.pdf"
    page: "p17 (15)"

  - name: mitigation_block
    aliases: [MB]
    definition: "Same construction as breaker but the prior extreme is NOT swept (higher low / lower high, often SMT); the opposing-colour bodies at the intermediate swing are used for entry and as continuation targets."
    evidence: diagram
    detection_criteria:
      - "bullish: Low(L1) -> High(H1) -> L2 >= L1 (no sweep; failure swing) -> displacement CLOSE > H1"
      - "box = full range (wicks) of the up-close candle forming H1 on p3-p4; p8 uses ~body lows for the bottom edge (deck inconsistent)"
      - "SMT vs correlated asset at L2 strengthens it"
      - "after HTF-level reversal, mark unmitigated opposing bodies of each prior consolidation as sequential targets"
      - "differentiator from breaker: sweep flag == false"
    source: "20. Mitigation_Blocks.pdf"
    page: "p3 (1), p4 (2), p5–p14 (3–12)"

  - name: smt_divergence
    aliases: [SMT]
    definition: "At the same swing, one correlated asset makes a new extreme while the other fails to."
    evidence: diagram
    detection_criteria:
      - "bullish SMT: A.low2 < A.low1 AND B.low2 > B.low1 (same swing window)"
      - "bearish SMT: A.high2 > A.high1 AND B.high2 < B.high1"
      - "inverse pairs: normal = A HH with B LL, or A LH with B HL; inverse SMT = A HH with B HL, or A LH with B LL"
      - "asset that failed to make the new low = relative strength; failed new high = relative weakness"
    source: "21. SMT.pdf"
    page: "p3–p5 (1–3), p6–p8 (4–6), p9–p11 (7–9)"
    adaptation: "pairs for user: BTC/ETH, BTC/SOL, ETH/SOL, XAU/XAG, WTI/Brent (not in source)"

  - name: power_of_three
    aliases: [PO3, AMD]
    definition: "Any candle decomposes into Accumulation (range around open), Manipulation (move beyond open against final direction), Distribution (expansion to close). Bullish path O-L-H-C, bearish O-H-L-C."
    evidence: diagram
    detection_criteria:
      - "period_open = O; accumulation = LTF range containing O"
      - "bullish manipulation = LTF excursion below O (and below accumulation low); distribution = subsequent expansion above O to H then close"
      - "bearish mirror"
      - "manipulation leg = [high of last accumulation candle(s) before the drop, manipulation low]"
      - "entries: at/after manipulation end (below O for bullish) and on pullbacks inside distribution"
    source: "22. Power_Of_Three.pdf; 24. AMD_STD.pdf"
    page: "22: p3 (1), p4 (2), p5 (3), p6 (4); 24: p3–p7 (1–5)"
    adaptation: "daily open for crypto = 00:00 UTC by convention; for CFDs broker open or NY midnight (not specified in source)"

  - name: standard_deviation_projection
    aliases: [STD, std_dev_projection]
    definition: "Fib drawn on the manipulation leg (1 at manipulation extreme, 0 at origin) with negative levels -1, -2, -2.5, -4 projecting in the distribution direction."
    evidence: diagram
    detection_criteria:
      - "anchor: p1 = manipulation extreme (1), p0 = manipulation origin (0)"
      - "level(k) = p0 + k*(p0 - p1) for k in [-1,-2,-2.5,-4]  # i.e. -1 is one leg-length beyond origin"
      - "retracement_or_reversal_zone = [level(-2), level(-2.5)]"
      - "max_expansion = level(-4)"
      - "prefer a level that coincides with a PD array / prior swing (pairing)"
    settings:
      tool: "TradingView Fib Retracement"
      levels_on: [1, 0, -1, -2, -2.5, -4]
      levels_off: [0.236, 0.5, 0.786, 1.618, 3.618, 1.272]
      trend_line: false
      extend_lines: false
      background: true
      log_scale: false
    source: "23. Standard_Deviation_Projections.pdf; 24. AMD_STD.pdf"
    page: "23: p3 (1), p4 (2), p5–p7 (3–5), p8 (6), p9 (7), p10 (8); 24: p8 (6), p9 (7)"

  - name: external_range_liquidity
    aliases: [ERL, buyside_liquidity, sellside_liquidity]
    definition: "Swing highs (buyside) and swing lows (sellside) that bound the current range."
    evidence: diagram
    detection_criteria:
      - "swing high/low by fractal (exact lookback not given in source)"
      - "after a sweep, redefine ERL at the new extreme"
    source: "IRL-ERL.pdf"
    page: "p4 (2), p8 (6)"

  - name: irl_erl_alternation
    definition: "Price alternates between external range liquidity and internal range liquidity (FVG)."
    evidence: diagram
    detection_criteria:
      - "state ERL_TAKEN -> target nearest opposing FVG (IRL)"
      - "state IRL_REACHED -> target next ERL (swing beyond)"
    source: "IRL-ERL.pdf"
    page: "p5–p10 (3–8)"

  - name: relative_strength_weakness
    definition: "Comparing correlated assets, which is more bullish (strength) or bearish (weakness); via SMT or via ratio chart (ES1!/NQ1!)."
    evidence: text+diagram
    detection_criteria:
      - "same window: larger up-move / smaller down-move = strength"
      - "SMT: asset with higher low = strength; asset with lower low = weakness"
      - "ratio A/B rising => A strong, B weak; falling => A weak, B strong"
      - "theory (lower confidence): sweep+reversal on ratio chart anticipates reversal in A or B"
    source: "Relative_Strength_ES.NQ.pdf"
    page: "p3 (1), p4 (2), p5 (3), p6 (4)"
    adaptation: "ratios: BTC/ETH, ETH/SOL, XAU/XAG (not in source)"

  - name: silver_bullet_am
    definition: "10:00–11:00 New York window; trade framed on the 9:00am hourly candle high/low; sweep of one side inside the window then reversal toward the other side."
    evidence: text+diagram
    detection_criteria:
      - "time in [10:00, 11:00) America/New_York (slide says EST)"
      - "ref_high = 09:00 1H candle high; ref_low = 09:00 1H candle low"
      - "bearish: price > ref_high inside window then reverses (CISD/MSS on LTF) -> target ref_low and below"
      - "bullish: mirror"
      - "example chart timeframe: 1-minute NASDAQ"
    source: "Silver_Bullet_AM.pdf"
    page: "p3 (1), p4 (2), p5 (3)"
    adaptation: "UTC 14:00–15:00 in EDT / 15:00–16:00 in EST; applies to crypto and CFDs on NY clock"

  - name: higher_timeframe_level_precondition
    definition: "A higher-timeframe level must be engaged before a lower-timeframe MSS is acted on."
    evidence: text
    detection_criteria:
      - "HTF PD array / level touched or traded through before LTF shift"
    source: "18. Market_Structure_Shift.pdf; 20. Mitigation_Blocks.pdf"
    page: "18: p5 (3); 20: p5 (3)"

  - name: stop_placement_options
    definition: "Two stop options: tight (below/above the block itself) or wide (below/above the swept swing)."
    evidence: diagram
    detection_criteria:
      - "OB: ob_candle.low | raid_swing_low"
      - "Breaker: displacement_candle.low (below box bottom) | lower_low"
    source: "17. Orderblocks.pdf; 19. BreakerBlocks.pdf"
    page: "17: p8 (6); 19: p18 (16)"
```
