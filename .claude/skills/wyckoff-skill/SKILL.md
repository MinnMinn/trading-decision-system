---
name: wyckoff-skill
description: Use when analyzing market context/narrative under the institutional trading system — Wyckoff phase identification via the full Phase A–E event vocabulary, the mislabelling (đối nhãn) tests, the CO plan, Spring/Upthrust typing, Effort-vs-Result, tape reading and SOT. Invoked by StructureAgent as part of /analyze, /bias, and /entry.
---

# WyckoffSkill

Answers: **what is the market doing, and why?** Owns the Wyckoff dimension of the Confluence Score (`docs/architecture/SYSTEM-DESIGN.md` §6, 0–25 points).

**Theory lives in `knowledge/`, not here.** Primary source is `knowledge/07-wyckoff-advance.md` — the full 294-page classical Wyckoff book. `knowledge/08-wyckoff-and-modern-tools.md` is the same author's other book and is secondary for Wyckoff proper: it says so itself (`08` §2.5), deferring the event vocabulary to `07`. `knowledge/01` carries a second author's version of the same material. The operating procedure and source precedence are in `knowledge/10-integrated-method.md` §1–§2.

Cite the exact `knowledge/` section for every claim (per this project's reduce-hallucinations discipline). Never assert a phase, event or Spring/Upthrust type from memory.

## Procedure

Run `knowledge/10` §2 steps A1–A8 in order. Condensed, with what each step must output:

1. **CHoBEV/CHoCH gate** (`knowledge/07` §2.6). Three CHoBEV make a CHoCH. This gates everything: `07` §5.2 rule WA2-03 states a misidentified CHoCH makes the entire phase labelling wrong. **If you cannot evidence the CHoCH, report "no Wyckoff structure established" and stop** — do not emit a low-confidence phase instead.
2. **Draw the Trading Range from events, not by eye** (`07` §2.7.1, rule WA2-02): AR high and SC/ST low. **Output both boundary prices numerically** — the de-duplication check below needs them.
3. **Market Regime**: TRENDING / RANGING / TRANSITIONAL / UNCLEAR. If UNCLEAR and the candidate setup depends on the range being real, say so; never force a Trading Range read onto a genuinely trending chart.
4. **Phase A→E event walk** for the right structure type — accumulation `07` §2.7, distribution `07` §2.8, re-accumulation `07` §2.9, re-distribution `07` §2.10. State which events are present, which absent, and whether the phase's own boxed summary is satisfied.
5. **Run the đối nhãn (mislabelling) tests** (`07` §2.11). A phase call that has not been tested is a hypothesis and must be labelled one. Includes the ST-within-1/3-of-TR rule, Phase-B test types, sloped-structure variants (the author discourages trading them, `07` §5.2), and failure-to-maintain-structure.
6. **State the CO plan expectation** (`07` §3.4) — what the operator should do next in this phase — *before* looking for confirmation. This makes the read falsifiable.
7. **Type the reversal event in two separate fields** — never collapsed into one string (user decision 2026-09-10):
   - `event_class` — the classic label from `07` §2.7–2.8 (Spring, Shakeout, Test, UA, UT, UTAD, SOS, LPS, BU, LPSY …).
   - `volume_type` — the `08` §2.6–2.7 volume type 1/2/3, or null when the event is not a Spring/Upthrust.
   Both go into the `wyckoff_event` object in `docs/architecture/schemas/trade-file.schema.json`, along with `phase`, `structure` and `doi_nhan_tested`. `08` §8 warns these are different vocabularies; if they disagree, record both in `naming_conflict` rather than resolving it.
   - **UT vs UA is phase-conditional and mandatory** (WA p8, `07` §1.3): **UT** only in phân phối / tái phân phối, **UA** only in tích lũy / tái tích lũy. Never write "Upthrust" unqualified where the phase determines the label.
8. **Effort-vs-Result evidence.** Tape reading by spread and volume (`07` §4.1 — five cases per context, **no order-flow data required**) and SOT (`07` §4.6, minimum 3 pushes, 3–4 useful, **more than 4 means the trend is too strong to oppose**). Where the phase warrants, add the advanced volume reads: distribution volume forms (`07` §3.1), horizontal vs vertical absorption (`07` §3.2), Urgent Demand (`07` §3.3).
9. **Volume Profile — this dimension owns it** (user decision 2026-09-10). Mark VAH/VAL and the LVN just beyond them (`knowledge/08` §3.1, §5 Step 4). Near VAL look for a Spring, near VAH look for an Upthrust; the LVN is the stop zone. Cross-check against `knowledge/07` §4.5, which covers Volume Profile from the same author with a different attribution (`07` §8).
   - **The abandon rule is a veto, not a score input.** If price crossed cleanly through VAH/VAL into the LVN **without a reversal reaction, the Spring/Upthrust thesis is dead** (`08` §5 Step 4, WMT p243–p249). Report it as a thesis invalidation that overrides the score, the way Regime and Event Risk gate before scoring (`SYSTEM-DESIGN.md` §6.3). Do not convert it into lost points.
10. **Score (0–25):** phase clarity *after* the đối nhãn tests (0–8) + event identification and typing quality (0–10) + Effort-vs-Result / tape-reading / SOT evidence (0–7).
11. **Cite every claim** — `knowledge/07 §X` or `WA pNNN` — so DecisionAgent and any later review can verify it.

## Data-source rules

- Mark this dimension `eligible: true` only if the exchange market-data source was `AVAILABLE` (not `MOCK`, `STALE` or `UNAVAILABLE`) per `docs/architecture/data-sources.md`.
- **This skill does not need footprint data.** Steps 1–9 all run on candles plus volume (`knowledge/10` §5). A `MOCK` or missing CoinGlass feed disables the Footprint dimension, not this one.
- **Tick volume is not traded volume.** On `mt5_bridge_live` (XAUUSD/XAGUSD/USOIL/UKOIL), "volume" is tick count (`docs/architecture/mt5-bridge.md`). Say so explicitly and **reduce the step-8 effort/volume credit** — do not treat it as equivalent to Binance-sourced volume. This also weakens Wyckoff/ICT independence; see the next section.

## Independence discipline (mandatory, `knowledge/09`)

The ICT corpus (`knowledge/04`–`06`) contains **no volume of any kind**. Volume is therefore the only genuinely orthogonal axis between the Wyckoff and ICT dimensions — everything else the two appear to confirm in each other is price geometry read twice (`knowledge/09` §3 item 3, `knowledge/10` §4.1).

Before this dimension claims credit for a location or a structural break, apply `knowledge/10` §4.3:

- **Print both prices.** If the Wyckoff TR boundary and the ICT liquidity level are within `analysis-params.json` → `project_defined.same_level_tolerance_atr` of each other, they are **one** observation, not two. Raise it as a `wyckoff_ict_same_level` contradiction if both dimensions were about to score it.
- **Spring ≡ liquidity grab.** One wick. This dimension owns the excursion and its volume typing; the ICT dimension owns the structure the excursion leaves behind.
- **SOS ⊂ MSS.** The break scores once, in ICT. This dimension may add credit only for acceptance-over-time and volume, and only with an actual volume series to cite. "SOS confirmed" with no volume evidence is the MSS restated — score it 0 here and say why.
- **Spread-widening is not separate evidence from displacement.** Only the attached volume is this dimension's to add.
- **A Shakeout coinciding with body closes beyond the boundary is a Contradiction, not a confirmation** (`knowledge/10` §4.5). Raise it; never award both dimensions. **Log it** as category `shakeout_vs_displacement` in the trade record's `contradictions` array (`docs/architecture/schemas/trade-file.schema.json`). This case is unresolved in every source, and the standing decision (2026-09-10) is to keep raising it while collecting outcomes, so `/review` can fill `outcome_side` and `/improve` can eventually settle it from results rather than argument.

## Hard rules (inherited — see master spec §25 and §10)

- Never claim an event confirmation from a timeframe or data source marked `UNAVAILABLE` or `STALE`.
- Never re-classify the phase after seeing the Confluence Score to make a trade pass (mode-lock discipline, `SYSTEM-DESIGN.md` §6.2).
- If regime is UNCLEAR, reduce this dimension's score rather than assuming RANGING.
- **Numeric thresholds come from `docs/architecture/analysis-params.json`, never from memory.** That file has two blocks. `sourced` holds numbers the books actually print, each with its page citation (the ST-above-50%-of-TR reading, the ST-within-one-third test, the SOT push bounds, the imbalance ratios, the Value Area share). `project_defined` holds numbers **no source gives** — what counts as low volume, a narrow spread, a low-volume Spring, a "period of commitment". When you use a `project_defined` value, say so in the output: it is a project parameter tunable via `/improve`, not a rule from the book.
- On `mt5_bridge_live`, apply `project_defined.tick_volume_credit_multiplier` to the effort/volume sub-score rather than inventing a discount.
