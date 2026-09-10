---
name: ict-skill
description: Use when analyzing location/setup/structure/timing under the institutional trading system — ICT/TTrades market structure, liquidity, OTE, killzones, PO3/AMD, TTrades models. Invoked by StructureAgent as part of /analyze, /bias, and /entry.
---

# ICTSkill

Answers: **where and when is the setup likely to occur?** Owns the ICT dimension of the Confluence Score (`docs/architecture/SYSTEM-DESIGN.md` §6, 0–25 points).

Theory lives in `knowledge/04-ttrades-core-A.md`, `knowledge/05-ttrades-core-B.md` and `knowledge/06-ttrades-models.md`. This skill does not restate it — cite the exact file and section for every claim. The Wyckoff↔ICT correspondence and the de-duplication rules are in `knowledge/09-wyckoff-ict-mapping.md`, summarised operationally in `knowledge/10-integrated-method.md` §4.

## Read Wyckoff first

`knowledge/04`–`06` contain **no phase, campaign or cause vocabulary**; the longest horizon they offer is a weekly profile or a previous-day bias. The HTF narrative therefore comes from WyckoffSkill, and this skill's job starts at falsification and location (`knowledge/10` §4.2). Do not construct an independent HTF story here and present it as a second opinion — that is the double-count this skill exists to avoid.

## Procedure

1. **HTF structural falsification** (`knowledge/05` §2.2, §3.1). Is the last confirmed structural break (MSS) bullish or bearish, by body close? If it contradicts WyckoffSkill's phase call, that is a **Contradiction to raise**, not something to resolve by quietly preferring one tradition.
2. **Structure/location quality** (`knowledge/04`–`05`): the nearest relevant Order Block (open and mean threshold), FVG (edges and consequent encroachment), Breaker, Mitigation Block, IRL/ERL liquidity, and premium/discount positioning relative to the current dealing range. **State the specific price levels**, never "near support".
3. **Timing — use `docs/architecture/session-model.md`, not the raw killzone slides.** The ICT sources give two competing killzone sets, no rule at all for crypto or commodity CFDs, and an unresolved daylight-saving question (`knowledge/04` §6). The project's answer to all three is the session model: windows defined in the exchange's local zone and converted to UTC per date, an instrument-by-instrument weight table, and a timeframe gate. Points come from `docs/architecture/analysis-params.json` → `timing.weight_by_class`.
   - **State the assumption every time you award timing points**: the window, the instrument's weight class, the local-to-UTC conversion for that date, and the fact that the weighting is a project assumption rather than a sourced rule.
   - No timing credit below `timing.min_timeframe_minutes`, and none on Saturday or Sunday UTC for any instrument including crypto.
   - PO3/AMD and the TTrades models (`knowledge/06` — OSOK, Fractal, Sons Model, TTRS, Unicorn, Timeframe Alignment) still supply setup timing; see the pipeline note below.
4. **Check the Volume Profile veto result before scoring location.** **This dimension does not own Volume Profile** — WyckoffSkill does (user decision 2026-09-10), matching where `knowledge/08` §5 Step 4 places it in the author's own method. Do not compute VAH/VAL/LVN here and do not score them. Read WyckoffSkill's verdict: if the abandon rule fired (price crossed cleanly through VAH/VAL into the LVN without a reversal reaction), **the thesis is dead and a good-looking location does not revive it**. Say so and stop scoring location.
5. **Score (0–25):** HTF falsification check (0–8) + structure/location quality (0–10) + timing alignment (0–7), **after** applying the de-duplication rules below.
6. **Cite every claim** — `knowledge/04-06`, section heading or concept name.

## De-duplication discipline (mandatory)

The ICT corpus has no volume of any kind. Volume is the only genuinely orthogonal axis between this dimension and Wyckoff; everything else the two traditions appear to confirm in each other is **price geometry read twice** (`knowledge/09` §3 item 3). Apply `knowledge/10` §4.3 before claiming points:

- **Print both prices.** If the ICT liquidity level and the Wyckoff TR boundary are within `docs/architecture/analysis-params.json` → `project_defined.same_level_tolerance_atr` of each other, "price is at SSL" and "price is at the TR low" are one observation. Score it once and raise a `wyckoff_ict_same_level` contradiction.
- **Spring ≡ liquidity grab of SSL** (mirror: UT/UTAD ≡ BSL grab). One wick. Wyckoff owns the excursion and its volume typing; **this dimension may score only the incremental structure the excursion left behind** — the CISD line, displacement, the gap, premium/discount position.
- **SOS ⊂ MSS.** The structural break scores **once, here** (MSS is the more precisely defined test: body close). Wyckoff may then add credit only for acceptance-over-time and volume.
- **LPS ≡ the retest pile.** One pullback is at most one location observation. An Order Block plus an FVG plus a Breaker at one price is a **quality grade** of a single location — score it higher inside the 0–10 location bucket, never as three confluences. A Unicorn is *by definition* breaker ∩ FVG (`knowledge/05` §2.8), so it is one thing, not two.
- **Premium/discount scores only when its anchors are stated and differ from the Wyckoff TR anchors.** Otherwise it adds nothing beyond "price is in the lower half of the range", which the phase read already implies. If the anchors are the same, score that sub-item 0 and say so.
- **Displacement and Wyckoff's "widening spread" are the same measurement** on the same candle. If this dimension scored displacement, Wyckoff may cite only the attached volume.
- **PO3 manipulation ≡ Phase C**, and **PO3 distribution leg ≡ Phase D expansion** — name the PO3 period unit before claiming either as separate evidence.
- **On tick-volume instruments** (XAUUSD/XAGUSD/USOIL/UKOIL via the MT5 bridge), Wyckoff and ICT are close to **not independent at all**. Flag this to DecisionAgent rather than letting both dimensions score at face value.

## Unsourced tokens — do not use

The rejection of BOS and CHOCH below is **interim**. The standing decision (2026-09-10) is to ingest an ICT source that defines them; all 30 PDFs in `docs/TTrades PDFs/` are already extracted and none does, so this is blocked until a new source document is supplied. Until then, keep rejecting them.

Grep-verified absent from `knowledge/04`, `05` and `06` (`knowledge/09`, header): **"BOS", "Break of Structure", "CHOCH", "ChoCh", "Change of Character", "BMS"**.

- Reject "CHOCH" as an ICT-dimension observation outright. If the observation is real, it is the Wyckoff Change of Character — cite `knowledge/07` §2.6 and score it in the Wyckoff dimension.
- Do not use bare "BOS" unless you can cite a source for it. Use MSS, with its `knowledge/05` §2.2 citation.
- **Ban the bare word "distribution" in cross-dimension reasoning.** PO3's "distribution" is the markup leg; Wyckoff distribution is topping — opposite signs. Always write the qualified form.

## Invalidation

This dimension's stop choices (gap far edge, order-block low, originating swing low, TTrades candle-2 swing point) sit **inside** the Wyckoff stop except for the widest option. The same setup can carry stops differing by the entire depth of the sweep (`knowledge/10` §4.4).

**Name one invalidation owner per trade plan and state it explicitly.** Sizing and management must use the same level. Also surface ICT's own thesis invalidation, which has no Wyckoff analogue: a later body close beyond the swept level converts the grab into an MSS, killing the reversal read even if the stop has not been hit (`knowledge/04` §3.6).

## Pipeline precedence (user decision 2026-09-10)

`knowledge/08` §5's six-step method is **the** pipeline. The TTrades models supply **location and timing inputs to it** — they are not a second pipeline run in parallel.

This matters because OSOK and the six-step method are each complete and self-sufficient, with their own bias, location, trigger, stop and target rules, and neither author sanctions running both and summing the results (`knowledge/09` §5 item 13). If a TTrades model's own stop or target disagrees with the six-step method's, the six-step method wins and the disagreement is reported.

Note also `knowledge/06` §6 item 6: Sons, TTRS and Unicorn state **no stops and no targets** in their own decks. Do not credit "TTRS setup complete" as if it carried an invalidation — it does not.
