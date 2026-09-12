---
name: ict-skill
description: Use when analyzing location/setup/structure/timing under the institutional trading system — ICT/TTrades market structure, liquidity, OTE, killzones, PO3/AMD, TTrades models. Invoked by StructureAgent as part of /analyze, /bias, and /entry.
---

# ICTSkill

Answers: **where and when is the setup likely to occur?** Owns the ICT dimension of the Confluence Score (`docs/architecture/SYSTEM-DESIGN.md` §6, 0–25 points).

Theory lives in `knowledge/04-ttrades-core-A.md`, `knowledge/05-ttrades-core-B.md` and `knowledge/06-ttrades-models.md`. This skill does not restate it — cite the exact file and section for every claim. The Wyckoff↔ICT correspondence and the de-duplication rules are in `knowledge/09-wyckoff-ict-mapping.md`, summarised operationally in `knowledge/10-integrated-method.md` §4. Box and stop geometry in `knowledge/05` §2.5, §2.7, §2.9 was re-verified against the PDFs on 2026-09-12 (`docs/audits/2026-09-12-ict-pdf-recheck.md`) — use the corrected wording (OB stop = body low / close; breaker box = full candle range incl. wicks; breaker tight stop = displacement-candle low).

## Read Wyckoff first

`knowledge/04`–`06` contain **no phase, campaign or cause vocabulary**; the longest horizon they offer is a weekly profile or a previous-day bias. The HTF narrative therefore comes from WyckoffSkill, and this skill's job starts at falsification and location (`knowledge/10` §4.2). Do not construct an independent HTF story here and present it as a second opinion — that is the double-count this skill exists to avoid.

## Procedure — seven steps, in this order

Every step names **specific prices and candle times**, never "near support". A step that cannot be filled from the candle data is reported as "not present", not skipped silently.

1. **HTF bias (Daily / H4) and premium–discount.**
   - ICT's own bias unit is the previous candle: "Is price more likely to reach for the previous day high or low?" (`knowledge/04` §2.12 PDH/PDL on the daily, §2.11 PCH/PCL on H4/H1/M30/M15). State **PDH, PDL, PWH, PWL** (and PMH/PML on the daily chart) as numbers. A body close **through** a level = it was the draw, expect continuation; a wick through with the body failing to close beyond = **failure to displace**, frame a reversal and name the opposite level as the new draw (`knowledge/04` §2.14, §3.2 R5–R8).
   - TTrades adds the candle-2 / candle-3 closure test on the bias timeframe (`knowledge/06` §2.2, §3.1 rules 5–8): a candle 2 that takes the candle-1 extreme and closes back inside frames candle 3 expansion; mark candle-2 wick EQ (or range EQ) as the framework the next candle must respect.
   - Structural falsification: the last confirmed MSS on the bias timeframe, by body close (`knowledge/05` §2.2). If it contradicts WyckoffSkill's phase call, that is a **Contradiction to raise**, not something to resolve quietly.
   - Premium/discount: the dealing range is the nearest **BSL↔SSL pair** ("where sellside and buyside liquidity is resting"), EQ = 0.5; longs only in discount, shorts only in premium; a PD array in the wrong half is ignored (`knowledge/04` §2.18–2.19, §3.4 R13–R15). State both anchors. If they coincide with the Wyckoff TR anchors, this sub-item scores 0 (de-duplication below).

2. **Draw on Liquidity (BSL / SSL).**
   - Name the pools above and below: swing highs/lows (**one candle each side**, `knowledge/04` §2.5), old highs/lows, relatively-equal highs/lows, PDH/PDL/PWH/PWL, **Asian and London session highs/lows** (`knowledge/04` §2.6–2.9). Session boundaries are not in the source (`knowledge/04` §6 item 9) — take them from `docs/architecture/session-model.md` §2 (`asia` 20:00–00:00 America/New_York — the decks' Asia killzone, chosen by measurement 2026-09-12; `london` 08:00–11:00 Europe/London) and say they are project-defined.
   - State the intended draw and the IRL↔ERL alternation: after an external level is taken, target the internal (FVG); after the internal, the next external (`knowledge/05` §2.13, §3.1 R3, §3.4 R20).

3. **Mark the PD arrays — OB / FVG / breaker / mitigation — with the deck's geometry.**
   - **Order Block** = last opposing-close candle before displacement; the **open** is the OB line, 0.5 of the body is the mean threshold (`knowledge/05` §2.5). Stops: body low / close (tight) or the raid swing low (wide).
   - **FVG** = wick-based three-candle gap; state both edges and the **consequent encroachment** (0.5), which is both an entry price and the hold/fail line (`knowledge/04` §2.21, §2.23, §2.26).
   - **Breaker** = full range, wicks included, of the up-close (bull) / down-close (bear) candle at the swept swing; tight stop = the displacement-candle low, wide = the swept extreme; **Unicorn** = breaker ∩ FVG, one location (`knowledge/05` §2.7–2.8). **Mitigation block** = same construction when the prior extreme was **not** swept (`knowledge/05` §2.9).
   - **Inversion**: an FVG closed through by displacement and retested from the other side (`knowledge/04` §2.25). Old SIBI/BISI chains are sequential draws (`knowledge/04` §2.27).
   - OB + FVG + breaker at one price is **one location at a higher quality grade**, never three confluences (`knowledge/10` §4.3; `knowledge/06` §6 item 16 for the TTRS nested zones).

4. **Timing — is this a killzone?** Use `docs/architecture/session-model.md`, not the raw killzone slides. The sources give two competing sets, no rule for crypto or commodity CFDs, and an unresolved daylight-saving question (`knowledge/04` §6 items 1–3). Points come from `docs/architecture/analysis-params.json` → `timing.weight_by_class`.
   - **State the assumption every time you award timing points**: the window, the instrument's weight class, the local-to-UTC conversion for that date, and that the weighting is a project assumption.
   - No timing credit below `timing.min_timeframe_minutes`, and none on Saturday or Sunday UTC for any instrument including crypto.
   - PO3/AMD (`knowledge/05` §2.11), the Silver Bullet windows (`knowledge/04` §2.2, `knowledge/05` §2.15) and the TTrades weekly/daily profiles (`knowledge/06` §2.5.4, §2.5.6) supply setup timing inside the pipeline — see "Pipeline precedence".

5. **Liquidity sweep — has a pool been taken?** A wick beyond the level with the body failing to close beyond it is a **liquidity grab / failure to displace**, not a trend change (`knowledge/04` §2.14, §2.17, §3.3 R11). Name the pool, the sweep candle time and the extreme. A stop raid immediately before the structural break is preferred (`knowledge/05` §3.1 R2).

6. **Confirmation — CISD, then MSS, each with displacement.**
   - **CISD** is the earliest trigger: a body close through the open of the first candle of the final opposing-colour run into the level (`knowledge/05` §2.3; `knowledge/06` §2.3, §4.5). It is the trigger of OSOK, the Fractal model, Timeframe Alignment and TTRS.
   - **MSS** = displacement closing beyond the swing that immediately precedes the raid leg (`knowledge/04` §2.17, §6 item 12; `knowledge/05` §2.2). **Displacement** = aggressive full-bodied candle(s), generally leaving an FVG (`knowledge/04` §2.16). A bare close through a pivot on a small-bodied candle is **not** an MSS — say "close beyond swing without displacement".
   - CISD and MSS are ordered by **level**, not necessarily by time; the same candle may trigger both (`knowledge/05` §6 item 12).
   - **"CHoCH" is not an ICT term in any ingested source** — see "Unsourced tokens". A real change of character is Wyckoff's (`knowledge/07` §2.6) and scores there.

7. **Return to the PD array (OTE) → entry, stop, target.**
   - **OTE**: fib 1 at the impulse origin, 0 at its terminus; entry band 0.62–0.79 with 0.705 emphasised; prefer overlap with a PD array; re-anchor on the internal swing for a second entry (`knowledge/04` §2.20, §3.5 R16–R18). The deck never prints "0.62–0.79" as a phrase (`knowledge/04` §6 item 17) — say so.
   - Entry models: IOFED (near edge), consequent encroachment (0.5), FVG fill (far edge) (`knowledge/04` §2.23); OB open or mean threshold; breaker/Unicorn overlap (`knowledge/05` §3.3 R10–R12); TTrades candle-3/candle-4 open after a valid closure (`knowledge/06` §3.1 rule 21).
   - Stops: gap far edge (tight), OB body low (medium), originating swing low (wide), TTrades candle-2 swing point (`knowledge/04` §2.24; `knowledge/05` §3.5; `knowledge/06` §3.1 rule 22). **Name one invalidation owner** — see "Invalidation".
   - Targets: standard-deviation projections of the manipulation leg — 1 at the manipulation extreme, 0 at the origin ("the previous high which made the highest high"), −2/−2.5 retrace-or-reverse zone, −4 max expansion, −4.5 in Model11 — paired with a PD array or liquidity level; **2R minimum** before any profit is taken (`knowledge/05` §2.12, §3.4 R16–R19; `knowledge/06` §2.1.5, §3.1 rule 23).

Then:

8. **Check the Volume Profile veto result before scoring location.** **This dimension does not own Volume Profile** — WyckoffSkill does (user decision 2026-09-10), matching where `knowledge/08` §5 Step 4 places it in the author's own method. Do not compute VAH/VAL/LVN here and do not score them. If WyckoffSkill's abandon rule fired (price crossed cleanly through VAH/VAL into the LVN without a reversal reaction), **the thesis is dead and a good-looking location does not revive it**. Say so and stop scoring location.
9. **Score (0–25):** HTF falsification check (0–8, steps 1 and 6) + structure/location quality (0–10, steps 2, 3, 5, 7) + timing alignment (0–7, step 4), **after** applying the de-duplication rules below.
10. **Cite every claim** — `knowledge/04-06`, section heading or concept name.

## De-duplication discipline (mandatory)

The ICT corpus has no volume of any kind. Volume is the only genuinely orthogonal axis between this dimension and Wyckoff; everything else the two traditions appear to confirm in each other is **price geometry read twice** (`knowledge/09` §3 item 3). Apply `knowledge/10` §4.3 before claiming points:

- **Print both prices.** If the ICT liquidity level and the Wyckoff TR boundary are within `docs/architecture/analysis-params.json` → `project_defined.same_level_tolerance_atr` of each other, "price is at SSL" and "price is at the TR low" are one observation. Score it once and raise a `wyckoff_ict_same_level` contradiction.
- **Spring ≡ liquidity grab of SSL** (mirror: UT/UTAD ≡ BSL grab). One wick. Wyckoff owns the excursion and its volume typing; **this dimension may score only the incremental structure the excursion left behind** — the CISD line, displacement, the gap, premium/discount position.
- **SOS ⊂ MSS.** The structural break scores **once, here** (MSS is the more precisely defined test: body close). Wyckoff may then add credit only for acceptance-over-time and volume.
- **LPS ≡ the retest pile.** One pullback is at most one location observation. An Order Block plus an FVG plus a Breaker at one price is a **quality grade** of a single location — score it higher inside the 0–10 location bucket, never as three confluences. A Unicorn is *by definition* breaker ∩ FVG (`knowledge/05` §2.8), so it is one thing, not two; the TTRS "order of reversal" draws one pullback through OB line, FVG and breaker (`knowledge/06` §6 item 16).
- **Premium/discount scores only when its anchors are stated and differ from the Wyckoff TR anchors.** Otherwise it adds nothing beyond "price is in the lower half of the range", which the phase read already implies. If the anchors are the same, score that sub-item 0 and say so.
- **Displacement and Wyckoff's "widening spread" are the same measurement** on the same candle. If this dimension scored displacement, Wyckoff may cite only the attached volume.
- **PO3 manipulation ≡ Phase C**, and **PO3 distribution leg ≡ Phase D expansion** — name the PO3 period unit before claiming either as separate evidence.
- **On tick-volume instruments** (XAUUSD/XAGUSD/USOIL/UKOIL via the MT5 bridge), Wyckoff and ICT are close to **not independent at all**. Flag this to DecisionAgent rather than letting both dimensions score at face value.

## Unsourced tokens — do not use

The rejection of BOS and CHOCH below is **interim**. The standing decision (2026-09-10) is to ingest an ICT source that defines them; all 30 PDFs in `docs/TTrades PDFs/` are extracted and were re-checked page by page on 2026-09-12 — none contains the strings — so this is blocked until a new source document is supplied. Until then, keep rejecting them.

Grep-verified absent from `knowledge/04`, `05` and `06` and from the 30 PDF text layers: **"BOS", "Break of Structure", "CHOCH", "ChoCh", "Change of Character", "BMS"**.

- Reject "CHOCH" as an ICT-dimension observation outright. If the observation is real, it is the Wyckoff Change of Character — cite `knowledge/07` §2.6 and score it in the Wyckoff dimension.
- Do not use bare "BOS" unless you can cite a source for it. Use MSS, with its `knowledge/05` §2.2 citation.
- **Ban the bare word "distribution" in cross-dimension reasoning.** PO3's "distribution" is the markup leg; Wyckoff distribution is topping — opposite signs. Always write the qualified form.

## Invalidation

This dimension's stop choices (gap far edge, OB body low, displacement-candle low under a breaker, originating swing low, TTrades candle-2 swing point) sit **inside** the Wyckoff stop except for the widest option. The same setup can carry stops differing by the entire depth of the sweep (`knowledge/10` §4.4).

**Name one invalidation owner per trade plan and state it explicitly.** Sizing and management must use the same level. Also surface ICT's own thesis invalidation, which has no Wyckoff analogue: a later body close beyond the swept level converts the grab into an MSS, killing the reversal read even if the stop has not been hit (`knowledge/04` §3.6 R25); and a body close through an FVG's consequent encroachment means the gap is failing (`knowledge/04` §2.26, §3.6 R23).

## Pipeline precedence (user decision 2026-09-10)

`knowledge/08` §5's six-step method is **the** pipeline. The TTrades models supply **location and timing inputs to it** — they are not a second pipeline run in parallel.

This matters because OSOK and the six-step method are each complete and self-sufficient, with their own bias, location, trigger, stop and target rules, and neither author sanctions running both and summing the results (`knowledge/09` §5 item 13). If a TTrades model's own stop or target disagrees with the six-step method's, the six-step method wins and the disagreement is reported.

Note also `knowledge/06` §6 item 6: Sons, TTRS and Unicorn state **no stops and no targets** in their own decks. Do not credit "TTRS setup complete" as if it carried an invalidation — it does not.
