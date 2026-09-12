# Integrated Wyckoff method — file 10

**What this is.** The operating procedure that merges the two Nguyễn Vũ Tuấn Hải books and the ICT/TTrades material into one method, in three layers:

- **Layer A — Wyckoff core** (§2): what the market is doing and why.
- **Layer B — Wyckoff + Footprint/Delta** (§3): what is happening inside the price movement at the Wyckoff location.
- **Layer C — Wyckoff + ICT** (§4): where and when the setup can be traded, and how to stop the two traditions double-counting one phenomenon.

**This file states procedure and precedence only.** It does not restate theory — every step cites the `knowledge/` section that owns it (per `rules/single-source-of-truth.md`). If a step here and its cited source ever disagree, the source wins and this file is the bug.

**What it replaces.** Before 2026-09-10 the Skills treated `knowledge/08` as the primary Wyckoff source. That was inverted: `08` §2.5 (WMT p026–p029) explicitly declines to define the classic event vocabulary in its own prose and credits the author's other book — which is now fully ingested as `knowledge/07`. §8 below lists what was retired.

---

## 1. Source precedence — which file is authoritative for what

Read this table before citing anything. "Primary" means: when two files cover the same concept, cite the primary and note the other only if it conflicts (conflicts are catalogued in `knowledge/07` §8).

| Question | Primary source | Secondary / cross-check | Note |
|---|---|---|---|
| Phase A–E structure and the full event vocabulary (PS, SC, AR, ST, ST[B], UA, Spring, Shakeout, Test, SOS, LPS, BU/BUEC, JAC, PSY, BCLX, UT, UTAD, SOW, LPSY, MSOS/MSOW) | `k07 §2.6–2.11` | `k01 §2.8–2.11` (different author) | `k08` defers here by its own statement (`k08 §2.5`) |
| CHoBEV / CHoCH and the three-CHoBEV rule | `k07 §2.6` | `k01 §2.5` | Absent from `k08` |
| Phase mislabelling tests (*đối nhãn*) | `k07 §2.11` | — | No counterpart anywhere else |
| Tái tích lũy / tái phân phối sub-types | `k07 §2.9–2.10` | `k08 §2.5` | `k07` enumerates sub-types; `k08` gives only the four phase names |
| Spring vs Shakeout (binary, by where candles **close**) | `k07 §2.7.3`, glossary `k07 §1.3` | `k01 §4.3` | |
| Spring / Upthrust **type 1/2/3** (by volume) | `k08 §2.6–2.7` | — | `k08 §8` states this taxonomy is author-specific and *not* the classic vocabulary. It is a refinement layered on the event, not a substitute for it |
| Volume forms of a distribution range (hình thái 1/2) | `k07 §3.1` | — | New; no `k08` counterpart |
| Hấp thụ chiều ngang / dọc (horizontal vs vertical absorption) | `k07 §3.2` | `k01 §2.14` | Prefer `k07` — same author as `k08`, so the vocabulary is consistent |
| Nguồn cầu khẩn cấp (Urgent Demand) | `k07 §3.3` | `k01 §2.15` | |
| Kế hoạch CO per phase (what the operator is doing in A/B/C/D/E) | `k07 §3.4` | — | New; the strongest "what should happen next" tool in the corpus |
| Tape Reading on **candles + volume only** (no Delta) | `k07 §4.1–4.4` | — | 5 cases per context; runs on plain OHLCV |
| Tape Reading **with Delta** | `k08 §4.2–4.4` | — | 10 cases; requires order-flow data |
| Volume Profile (VAH/VAL/LVN/POC) | `k08 §3.1` + `k08 §5 Step 4` | `k07 §4.5` | Attribution conflicts between the two books — see `k07 §8` |
| SOT (Shortening of the Thrust) | `k07 §4.6` | `k08 §2.3` | `k07` is fuller: push-count bounds and event-priority rules |
| Footprint mechanics (POC, R/H, R/L, Imbalance, Stacked Imbalance, unfinished auction) and per-instrument imbalance ratios | `k08 §3.2` | `k01–k03` | `k07` contains no Footprint material at all |
| Delta / Cumulative Delta and the four divergence strengths | `k08 §3.3` | `k03` | |
| Absorption / Exhaustion / Development as an entry-signal read | `k08 §5 Step 5` | `k01 §2.14` | Distinct from `k07 §3.2`'s structural absorption — see §3.4 |
| Entry, stop, take-profit mechanics | `k08 §5 Step 6` | `k07 §5` rules, `k01 §3.7` | |
| ICT/TTrades structure, location, timing, models | `k04–k06` | — | |
| Wyckoff ↔ ICT correspondence and de-duplication | `k09` | — | |

---

## 2. Layer A — Wyckoff core procedure

Run in order. Each step names its gate; a step that cannot be evidenced is reported as such, never assumed.

**A1. CHoBEV / CHoCH gate.** Establish that the prior trend has actually changed character before labelling anything (`k07 §2.6`). Three CHoBEV make a CHoCH. This is a hard gate: `k07 §5.2` rule WA2-03 states that a misidentified CHoBEV/CHoCH makes the entire phase labelling — and every decision derived from it — wrong. If you cannot evidence the CHoCH, stop here and report "no Wyckoff structure established", not a low-confidence phase.

**A2. Draw the Trading Range from events, not by eye.** The upper boundary is the AR high, the lower boundary is the SC/ST low (`k07 §2.7.1`; `k07 §5.2` WA2-02). Record both prices numerically — §4.3 needs them.

**A3. Walk Phase A → E with the event checklist.** Accumulation `k07 §2.7`, distribution `k07 §2.8`, re-accumulation `k07 §2.9`, re-distribution `k07 §2.10`. For each phase state which events are present, which are absent, and what the phase's own boxed summary requires. Two frequently-decisive sub-rules: the ST-above-50%-of-TR reading (`k07 §5.2` WA2-07) and the low-volume-SC ambiguity (WA2-08).

**A4. Run the đối nhãn (mislabelling) tests.** `k07 §2.11`. This is the step with no equivalent in the previous system. The phase call must survive the book's own tests — including the ST-within-1/3-of-TR rule, the Phase-B test types, the sloped-structure variants (which the author explicitly discourages trading, `k07 §5.2`), and the failure-to-maintain-structure case. A phase call that has not been tested is a hypothesis, and must be reported as one.

**A5. Apply the CO plan.** `k07 §3.4` states what the operator should be doing in each phase of tích lũy and tái tích lũy, including the Phase A&B / C&D / E breakdown. Use it to state the expected next behaviour *before* looking for confirmation — this is what makes the read falsifiable rather than descriptive.

**A6. Type the reversal event.** Record two things, not one: the `k07` event and close-behaviour classification (Spring vs Shakeout, UA vs UT vs UTAD per the phase-conditional naming rule in `k07 §1.3`), and the `k08 §2.6–2.7` volume type 1/2/3. Do not collapse them — they answer different questions, and `k08 §8` warns they are different vocabularies. If the two disagree, record both readings in the `naming_conflict` field rather than resolving them (§7 decision 5).

**A7. SOT check.** `k07 §4.6`. Mind the push-count bounds: a minimum of three pushes, three to four useful, and **more than four means the trend is too strong to oppose**. `k07` also ranks SOT against Wyckoff events (a UTAD outranks an SOT) — a distinction `k08 §2.3` does not make.

**A8. Advanced volume reads, where the phase warrants.** Distribution volume forms (`k07 §3.1`), horizontal vs vertical absorption (`k07 §3.2`), and Urgent Demand (`k07 §3.3`). Urgent Demand in particular is a distinct bullish signature — a demand spike that negates prior supply — and is not the same thing as an SOS.

---

## 3. Layer B — Wyckoff + Footprint / Delta

### 3.1 The three bridges the books state themselves

These are the author's own statements, not inferences, and they are the backbone of this layer:

1. A **Stacked Imbalance is only meaningful in context**, and the context the book names first is "at a Wyckoff Spring or UTAD, or at a double-top/bottom neckline break" (`k08 §3.2`, WMT p111–p112).
2. A **"Strong" price / Cumulative-Delta divergence is cleanest at Spring/UTAD locations** (`k08 §3.3`, WMT p141).
3. **Bar-by-Bar cases 5 and 10 are explicit climax calls** — buying climax into distribution/redistribution, selling climax into accumulation/reaccumulation (`k08 §4.2`, WMT p180, p200).

### 3.2 Event → expected order-flow signature

Use this to decide what would *confirm* the Layer-A read, and equally what would falsify it. Anchor the footprint read on the specific candle Layer A identified.

| Wyckoff event (`k07`) | Expected order-flow signature | Source |
|---|---|---|
| SC / BCLX (climax) | Volume spike at the extreme; exhaustion tells at the bar's extreme cells (R/L at a low, R/H at a high) | `k08 §3.2`; `k07 §4.1` case 5 |
| ST (any) | Reduced volume and narrower spread versus the event being tested; no fresh imbalance | `k07 §2.7.1`; `k08 §4.2` |
| Spring[C] | Exhaustion → absorption → development: falling volume with Delta turning less negative, then a BID-side spike with stacked BID imbalance while price refuses to fall, then sustained ASK-side volume | `k08 §5 Step 5` |
| Shakeout | Same as Spring but expect the closes below the boundary; treat as the contradiction case in §4.5 | `k07 §2.7.3`; `k09 §2` risk 9 |
| SOS / MSOS[D] | Development: sustained elevated ASK-column volume, Cumulative Delta continuing positive, SOS candles | `k08 §5 Step 5` |
| LPS[C] / BU | Absorption at the level: a large print with price failing to continue, imbalance stalling. Cross-check against horizontal absorption | `k08 §3.2`; `k07 §3.2` |
| Urgent Demand | Vertical absorption plus a demand spike that negates prior supply; stacked ASK imbalance with rapid price gain | `k07 §3.3` |
| UT / UTAD | Mirror of Spring, with SOW candles instead of SOS | `k08 §5 Step 5` |
| LPSY | Feeble rally on narrow spread; weak ASK volume, Cumulative Delta not confirming | `k07 §2.8`; `k08 §5 Step 5` |

### 3.3 Two tape-reading frameworks — pick by data, never merge

`k07 §4.1` and `k08 §4.2` are **different frameworks by the same author**, and `k07 §8` records the conflict explicitly:

| | `k07 §4.1` Bar-by-Bar | `k08 §4.2` Bar-by-Bar |
|---|---|---|
| Cases | 5 in an up context + 5 in a down context | 10 in one table |
| Axes | spread direction × volume direction | Volume × Delta × Result |
| Needs order-flow data | **No** — plain candles and volume | **Yes** — Delta |

**Rule: the case numbers do not correspond.** Never cite "case 3" without naming which framework. Use `k07 §4.1` when the footprint feed is `MOCK`, `STALE` or `UNAVAILABLE`; use `k08 §4.2` when it is `AVAILABLE`. This is the single most practical gain from ingesting `k07` — see §5.

### 3.4 Two different things both called "absorption"

- **Structural absorption** (`k07 §3.2`): horizontal, meaning absorption through consolidation with supply gradually decreasing; or vertical, meaning absorption on the way up with demand spiking. This is a *range-and-swing-level* read from candles and volume.
- **Order-flow absorption** (`k08 §5 Step 5`, `k08 §3.2`): a large passive order matching repeated active orders at one price without price moving. This is a *single-bar* read from footprint data.

They are compatible but are not the same observation, and they must not be counted as two confirmations of each other when the second is simply the first zoomed in.

### 3.5 Caveats that stay in force

The subjectivity warning at `k08 §3.2` still applies in full: a BID/ASK print can be position-closing flow rather than fresh conviction. And the imbalance ratio is instrument-specific — roughly 3–4× for gold and oil CFDs, about 3× for stocks, adjusted per token for crypto (`k08 §3.2`, WMT p107–p109).

---

## 4. Layer C — Wyckoff + ICT

The full correspondence table, the twelve double-counting risks and the sequencing argument live in `knowledge/09`. This section is the operating summary.

### 4.1 The finding that drives everything else

`k04`–`k06` contain **no volume of any kind** (grep-verified, `k09` §1B and §3 item 3). "Volume Imbalance" in the ICT corpus is a body gap, not volume. Therefore:

> Volume is the only genuinely orthogonal axis between the Wyckoff and ICT dimensions. Everything else the two traditions appear to confirm in each other is price geometry read twice.

The corollary matters for this project's instruments: on a feed where volume is tick-count rather than real traded size (the MT5 bridge, per `docs/architecture/mt5-bridge.md`), the two dimensions are close to **not independent at all**, and the correct response is to reduce Wyckoff credit rather than to score both dimensions normally.

### 4.2 Reading order

1. **Regime, Trading Range, phase — Wyckoff first.** `k04`–`k06` have no phase, campaign or cause vocabulary; their longest horizon is a weekly profile. `k08 §5 Step 1` prescribes this order.
2. **Which event to expect next — Wyckoff.** `k08 §5 Step 2`. This produces the hypothesis the rest of the pipeline tests.
3. **HTF structural falsification — ICT, as a check and not a tiebreak.** If the last HTF body-close break contradicts the phase call, that is a Contradiction to be raised, not resolved by preferring one tradition.
4. **Entry location — ICT leads, Wyckoff filters.** ICT's location vocabulary is far more resolved (order-block open and mean threshold, fair-value-gap edges and consequent encroachment, breaker box, optimal-trade-entry band). Wyckoff's is "at the Spring low / at the LPS" with no sub-level.
5. **Location veto — Volume Profile.** `k08 §5 Step 4`: if price crosses cleanly through VAH/VAL into the LVN **without a reversal reaction, abandon the Spring/Upthrust plan**. This is the strongest thesis-invalidation statement in either tradition and has no ICT counterpart.
6. **Timing — ICT, essentially uncontested**, with the caveat in §7 that killzone applicability to crypto and commodities is unresolved by the sources.
7. **Invalidation — choose an owner explicitly** (§4.4).

### 4.3 De-duplication rules (condensed from `k09 §2`)

- **Print both prices before scoring.** The Wyckoff event-derived boundary and the ICT swing-derived liquidity level must both be stated numerically. If they round to the same level, "price is at the TR low" and "price is at SSL" are **one** observation.
- **Spring ≡ liquidity grab.** One wick. Wyckoff owns the excursion and its volume typing; ICT may score only the incremental structure the excursion leaves behind (the change-in-state-of-delivery line, displacement, the gap left behind, premium/discount position).
- **SOS ⊂ MSS.** The structural break scores once, in ICT (the more precisely defined test). Wyckoff may add points only for acceptance-over-time and volume — and only with an actual volume series to cite. "SOS confirmed" with no volume evidence is the MSS restated.
- **LPS ≡ the retest pile.** One pullback is at most one location observation. An order block plus a gap plus a breaker at one price is a *quality grade* of a single location, never three confluences.
- **Premium/discount scores only when its anchors are stated and differ from the TR anchors.** Otherwise it contains nothing beyond "price is in the lower half of the range", which the phase read already implies.
- **Spread-widening is not separate evidence from displacement** — same measurement on the same candle. Only the attached volume is Wyckoff's to add.
- **Reject "CHOCH" and bare "BOS" as ICT-dimension observations.** Neither string exists in `k04`–`k06`. A real change-of-character observation belongs to Wyckoff (`k07 §2.6`).
- **Ban the bare word "distribution" from cross-dimension reasoning.** The ICT power-of-three "distribution" leg is the markup leg; Wyckoff distribution is topping. They are opposite signs. Always qualify.

### 4.4 Invalidation ownership — the traditions genuinely disagree

| | Stop / invalidation | Source |
|---|---|---|
| Wyckoff | Below the lowest low of the Spring (above the highest high of the Upthrust), plus the VAL/VAH→LVN abandon rule | `k08 §5 Step 4`, `§5 Step 6` |
| ICT | Nested choices: gap far edge (tight), order-block body low / close (medium; `k05 §2.5` re-verified 2026-09-12), displacement-candle low under a breaker, originating swing low (wide), plus the TTrades candle-2 swing point | `k04 §3.6`, `k05 §3.5`, `k06 §2.5.7` |

ICT's tight and medium stops sit **inside** the swept extreme, i.e. inside the Wyckoff stop. Only the wide option coincides. The same setup can therefore carry stops differing by the entire depth of the sweep, which changes position size by a multiple.

**Rule: name one invalidation owner per trade plan and record it. Sizing and management must both use that one level.** Sizing off the tight stop while managing to the wide one is silent risk inflation.

A second, quieter disagreement: ICT says buy in discount, while Wyckoff's best long add is the Phase-D LPS, which forms after the SOS and is frequently in premium by ICT's own measure. They are describing different trades at that point, not contradicting each other.

### 4.5 The one hard contradiction

A high-volume Spring type 3 / Shakeout, where candles **close** below the boundary, is bullish under `k08 §2.6` and `k07 §2.7.3`, and bearish displacement under `k04 §2.17`. Same candles, opposite bias. **No ingested source resolves this.** When it occurs, raise a Contradiction under `SYSTEM-DESIGN.md` §6.2 — never award both dimensions.

---

## 5. What can be read with which feed

This is why full ingestion of `k07` matters operationally. Previously, a `MOCK` or missing footprint feed left the order-flow layer unscoreable and the Wyckoff layer thin. It no longer does.

| Feed state | Layer A (Wyckoff core) | Layer B (order flow) | Layer C (ICT) |
|---|---|---|---|
| Candles + real traded volume (Binance) | Full — including `k07 §4.1` tape reading, SOT, absorption, CO plan | Only if footprint data is separately available | Full |
| Candles + tick volume (MT5 bridge) | Structure and events yes; every effort/volume claim reduced, per §4.1 | Not available | Full |
| Footprint / Delta available | Full | Full — `k08 §4.2`, `§5 Step 5`, Delta divergence tiers | Full |
| Footprint `MOCK` / `STALE` / `UNAVAILABLE` | **Full, unchanged** | Not scoreable; say so | Full |

**Consequence for scoring:** the Wyckoff dimension no longer needs order-flow data to be scored deeply. Tape reading by spread and volume (`k07 §4.1`), SOT (`k07 §4.6`), the CO plan (`k07 §3.4`) and the đối nhãn tests (`k07 §2.11`) all run on plain candles. What order-flow data adds is *confirmation at the anchor bar*, which is Layer B's own dimension.

---

## 6. Consequences for the Confluence Score

These change how the existing rubric in `docs/architecture/SYSTEM-DESIGN.md` §6.2 should be applied. They tighten it; they do not replace the formula.

1. **The Wyckoff dimension's evidence buckets change** to reward the discipline the old system had no source for: phase clarity *after* the đối nhãn tests, event typing recorded in both vocabularies, and effort/volume evidence (tape reading or SOT) — with the volume component reduced on tick-volume feeds.
2. **Wyckoff and ICT are not automatically independent.** Before both dimensions score a location, the analysis must print both derived price levels and state that they differ. If they are the same level, the phenomenon scores once, per §4.3.
3. **On tick-volume instruments, treat the Wyckoff/ICT pair as weakly independent** and reduce credit rather than scoring both at face value.
4. **A Shakeout coinciding with body closes beyond the boundary raises a Contradiction**, never a double confirmation.
5. **Volume Profile's abandon rule is a thesis invalidation, not a score penalty.** If it triggers, the plan is abandoned regardless of the score.

---

## 7. Decisions taken (2026-09-10)

All nine open questions were put to the user and decided on 2026-09-10. Recorded here so a later session does not silently re-open them. Only one remains blocked, and it is blocked on a missing document, not on judgment.

| # | Question | Decision | Where it lives now |
|---|---|---|---|
| 1 | Which dimension owns Volume Profile | **Wyckoff owns it.** Rationale given: ICT does not treat volume as meaningful, and this is where `k08 §5 Step 4` puts it in the author's own method. The VAH/VAL to LVN abandon rule is a **veto evaluated before scoring**, not a point deduction | `wyckoff-skill` step 9; `SYSTEM-DESIGN.md` §6.3 gates; removed from `ict-skill` |
| 2 | Numeric thresholds on the Wyckoff side | **Project parameters in a config file**, split into a page-cited `sourced` block and a `project_defined` block that outputs must label as assumptions | `docs/architecture/analysis-params.json` |
| 3 | Shakeout vs bearish displacement | **Keep raising it as a Contradiction and log every occurrence**, so the case is settled later from outcomes rather than argument | category `shakeout_vs_displacement` in both schemas; `/review` fills `outcome_side` |
| 4 | Killzones for crypto and commodities | **Define a project session model and document it.** Windows anchored in exchange-local time and converted to UTC per date, so they follow daylight saving; instrument-by-instrument weight table; timeframe and weekend gates | `docs/architecture/session-model.md` |
| 5 | Two Spring taxonomies | **Two structured fields, never collapsed**: `event_class` (classic) and `volume_type` (1/2/3), with a `naming_conflict` field when they disagree | `wyckoff_event` object in `trade-file.schema.json` |
| 6 | UT vs UA naming | **Adopt the book's phase-conditional rule** (WA p8): UT only in phan phoi / tai phan phoi, UA only in tich luy / tai tich luy | enforced in `wyckoff-skill` step 7, `structure-agent`, and the schema enum description |
| 7 | "BOS" and "CHOCH" are unsourced | **Ingest a source that defines them.** BLOCKED — all 30 PDFs in `docs/TTrades PDFs/` are already extracted and none contains the strings. Needs a new source document from the user. **Interim: keep rejecting both tokens** | `ict-skill`, "Unsourced tokens" section, marked interim |
| 8 | OSOK vs the six-step method | **The six-step method is the pipeline.** TTrades models supply location and timing inputs to it, never a parallel pipeline whose results get summed | `ict-skill`, "Pipeline precedence" |
| 9 | Volume Profile attribution conflict | **Record both** (Steidlmayer/CBOT 1985 in `k07`, Dalton in `k08`) without resolving | `knowledge/07` §8 |

### Still genuinely open

- **Decision 7 needs a source document.** Supply an ICT source that actually defines Break of Structure and Change of Character, the way the Wyckoff book photographs were supplied, and it can be ingested. Until then the tokens stay rejected, because no file in this repo defines them.
- **Decision 3 is deliberately deferred, not settled.** It resolves itself once enough closed trades carry the `shakeout_vs_displacement` contradiction with `outcome_side` filled in.
- **Decision 4's weights are a first draft.** `session-model.md` §6 lists the triggers for revisiting them; the intended path is to compare outcomes by session once the journal has enough trades, and to drop a window's weight rather than defend it.
- **What no source gives, and no decision can invent.** The `project_defined` block of `analysis-params.json` exists because the books genuinely never quantify "large volume", "narrow spread" or "a period of commitment". Those numbers are this project's, and every output that uses one says so.

## 8. Retired from the previous system

Removed because the sources contradict them or a better-sourced procedure now exists. Listed so the change is auditable.

| Retired | Why |
|---|---|
| `knowledge/08` as the primary Wyckoff theory source | `k08 §2.5` defers the event vocabulary to `k07`, which is now fully ingested |
| Phase classification as a bare four-way label with a confidence caveat | Superseded by the Phase A–E event walk (`k07 §2.7–2.10`) plus the đối nhãn tests (`k07 §2.11`) |
| Spring/Upthrust typing as the *only* event classification | Now paired with `k07`'s event and close-behaviour vocabulary; the type taxonomy is author-specific per `k08 §8` |
| Treating Tape Reading as a single framework citing `k08 §4` | Two distinct frameworks with non-corresponding case numbers — see §3.3 |
| The claim, in the scanner and local-read briefs, that classic Wyckoff terms (SC/AR/ST/LPS) have no source document | False since `k07` was ingested; they are defined in `k07 §2.7–2.8` |
| Scoring the Wyckoff and ICT dimensions as independent by default | `k09` shows they largely read the same price geometry; independence must now be demonstrated, not assumed |
| Leaving order-flow-unavailable runs with a thin Wyckoff read | `k07 §4.1` tape reading and `k07 §4.6` SOT run on plain candles — see §5 |
| Fixed UTC killzone windows ("London 06-09Z, NY AM 11-14Z") | Correct in summer only. Windows are now exchange-local and DST-aware — `docs/architecture/session-model.md` §1 |
| Volume Profile computed inside the ICT dimension | Wyckoff owns it by user decision 2026-09-10 (§7 decision 1) |
| Ad-hoc numeric thresholds invented per analysis | Now centralised and labelled in `docs/architecture/analysis-params.json` (§7 decision 2) |
