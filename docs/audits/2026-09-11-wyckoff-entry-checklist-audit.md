# Wyckoff entry-checklist audit — books vs. implementation

> **Knowledge-path note (added 2026-09-17).** The `knowledge/` citations below use the FLAT numbered
> layout (`knowledge/07-wyckoff-advance.md`, or the `kNN` short codes) that was retired on 2026-09-17 in
> favour of one folder per methodology. They are left exactly as written: this document is a dated record,
> and re-pointing its citations would change what it says it checked. `knowledge/INDEX.md` carries the
> old→new map.

Read-only audit, 2026-09-11. Scope: every entry-related checklist / precondition / threshold stated in
`knowledge/07-wyckoff-advance.md` (WA) and `knowledge/08-wyckoff-and-modern-tools.md` (WMT), checked against
what the system actually enforces.

Coverage codes used throughout:
- **CODE** — enforced deterministically by a named file:function.
- **MODEL** — required only in model instructions (`.claude/skills/wyckoff-skill/SKILL.md`,
  `scripts/local-eval-brief.py` brief text, `knowledge/10` §2). No machine check.
- **PARTIAL** — some part enforced, a load-bearing part not.
- **MISSING** — nothing in code or model instructions asks for it on the path that produces a trade.

Two execution paths exist and they differ a lot. Keep them apart:
- **Path A — full analysis** (`/analyze`, `/bias`, `/entry` → `structure-agent` → `wyckoff-skill`), output validated
  by `scripts/check-narrative.py`.
- **Path B — live automation** (`scripts/ict-scan.py` facts → `scripts/local-eval-brief.py` → Sonnet →
  `scripts/check-model-prose.py`) and **Path C — the paper pilot** (`scripts/demo-pilot.py` `evaluate()`), which
  is the only path that actually sends an order.

The headline finding is that **Path C contains no Wyckoff entry test at all beyond one volume multiple**, while
journalling its trades as `dimensions_used: ["wyckoff", "ict"]` (`scripts/journal.py:144`).

---

## 1. WMT Appendix 1 — "Trading Signal Checklist" B1–B5 (WMT p356–p357, `knowledge/08` §5 Step 5, line 179)

The book calls this "the book's single canonical decision artifact".

| # | Book requirement | Status | Where |
|---|---|---|---|
| **B1** | Identify market phase (accumulation / distribution / re-acc / re-dist) — WMT p233–236, `k08` §5 Step 1 | **PARTIAL** | Path A: `check-narrative.py:phase_grammar` enforces phase letters A–E contiguity, event→phase membership, Phase A needs SC/BC, Phase C needs a test event, Phase D needs SOS/LPS/BU (`check-narrative.py:86–91`). Path B/C: no phase is computed at all; `htf_context.bias_of` only *reads* a phase word written earlier by Path A (`htf_context.py:63–82`). |
| **B2** | Identify Spring or Upthrust and its **type 1/2/3** — WMT p236–238, `k08` §2.6–2.7 | **PARTIAL** | MODEL only for live trading: `wyckoff-skill/SKILL.md:36–39` requires `event_class` + `volume_type` as two separate fields. CODE exists only in the **backtest** `measure-spring-ict.py` ("Spring volume type = ratio to the mean volume of the previous 20 bars: <0.7 type 1, 0.7–1.5 type 2, >1.5 type 3"). `check-narrative.py` never requires `volume_type`; `demo-pilot.py` never computes it. |
| **B3** | Trading bias: buy bias on Spring, sell bias on Upthrust — WMT p238–241 | **CODE** | `htf_context.py:bias_of` + `htf_context.py:check_verdict` — the only book rule in this system that is fully mechanised. Blocks `SETUP TIỀM NĂNG` against HTF bias (`htf_context.py:131–135`) and blocks it entirely when bias is neutral (`:136–137`). `demo-pilot.py:evaluate()` step 4 applies the same gate when `HTF_FILTER` is on. |
| **B4** | **VAH/VAL as the waiting levels, LVN just beyond as the stop zone; abandon the Spring/Upthrust plan if price crosses cleanly through VAH/VAL into the LVN without a reversal reaction** — WMT p243–249, `k08` §5 Step 4 | **MISSING in code; MODEL-only on Path A** | `wyckoff-skill/SKILL.md:30–31` states it and calls it "a veto, not a score input". **No code anywhere computes VAH, VAL, LVN or VPOC** (`grep -rn "VAH\|LVN\|value_area\|VPOC" scripts/*.py` → only `fetch-history.py` false positives). `analysis-params.json` `sourced.value_area_pct` (0.682) is referenced by **no script**. `local-eval-brief.py`'s citation map (lines 22–37) contains **no Volume Profile entry at all**, so the live Sonnet read is never asked for it. `demo-pilot.py` has no VAH/VAL/LVN concept. |
| **B5** | Volume / Delta / cumulative Delta / price reaction / stacked-imbalance column / signal summary at the entry candle — WMT p250–267 | **PARTIAL / data-gated** | Footprint dimension is skipped when CoinGlass is MOCK (`build-artifact.py:707`). The only part enforced for a real order is `demo-pilot.py:evaluate()` step 3: `V[sweep_i] >= VOL_MULT*avgv or V[mss_i] >= VOL_MULT*avgv` plus an MSS close in the upper/lower half. Delta and cumulative Delta are never computed. |

**Sequence gate.** The book runs B1→B5 and only then enters (WMT p268–271: market order "once the full checklist is
satisfied"). `demo-pilot.py:evaluate()` enters on B3 (bias) + an ICT sweep→MSS→FVG chain + one volume test. B1, B2
and B4 are absent from the order path.

---

## 2. WMT Step 6 — order entry, stop, target, management (WMT p268–279, `k08` §5 Step 6, line 181–184)

| Book rule | Status | Evidence |
|---|---|---|
| Market order once the checklist is satisfied (WMT p269–271) | **CODE** | `demo-pilot.py:place_long` → `order_json("market-buy-qty", ...)`. |
| Stop **below the lowest low of the Spring** / above the highest high of the Upthrust (WMT p271) | **PARTIAL / different level** | `demo-pilot.py:evaluate()` uses `swept = min(L[sweep_i:])` — the low of the **ICT sweep**, not of a Wyckoff Spring; there is no Spring in that code path. `measure-spring-ict.py` does use "Spring low − 0.05%" and cites `k08` §5 Step 4. `knowledge/10` §4.4 requires naming one invalidation owner per plan; `demo-pilot.py` records none. |
| Calculate R:R **before** entry (WMT p271) | **CODE** | `demo-pilot.py:evaluate()` `MIN_RR`; `journal.py:134` `planned_rr`. |
| Move stop to **breakeven** or use a **trailing stop** after favourable movement (WMT p272) | **MISSING** | `demo-pilot.py:check_exit` and `check_exit_futures` only resolve the OCO legs or a bar-count time stop. No breakeven move, no trail. |
| First target = **the opposite side of the Trading Range**, reinforced by the Market-Profile 80% rule → VAH from a Spring (WMT p273); WA agrees: "Trong Phase D, giá sẽ di chuyển ít nhất đến biên trên Trading Range" (WA p83–84, `k07` §2.7.4) | **CONTRADICTED** | `demo-pilot.py:evaluate()`: `tp = eq if (eq - entry) >= MIN_RR*r else entry + 2*r`, where `eq` is the **equilibrium (midpoint) of the 288-bar window** (`ict-scan.analyze` → `a["eq"]`). The midpoint is roughly half the book's target. `analysis-params.json sourced.market_profile_80_rule` (0.8, cited WMT p273) is **used by no script**. |
| At the opposite range edge, watch for **SOT** or a clear reversal to decide exit-vs-ride (WMT p273–274) | **MISSING** | No SOT computation anywhere in `scripts/`. |

---

## 3. WA Phase C / Phase D entry conditions (accumulation) — `knowledge/07` §2.7.3–2.7.4, §5.2

| Rule | Book text | Status |
|---|---|---|
| **WA2-11** Spring: break below TR support, quick reverse to close back **inside** the TR on **low volume** → "thời điểm tốt để bắt đầu mở một phần vị thế" (WA p80) | partial position, not full | **MODEL** (`SKILL.md:36–39`, `k10` §2 A6). `analysis-params.json project_defined.spring_low_volume_max_ratio` (0.7) is **used by no script**. `demo-pilot.py` has no Spring concept and always enters full size. |
| **Spring vs Shakeout discriminator** — boxed, WA p83: Spring = supply exhausted so price stays outside the TR only briefly; **Shakeout = most candles close below the lower border and price builds its own value area there** (WA p80 Shakeout definition, WA2-12) | must be distinguished | **PARTIAL/CONTRADICTED.** `check-narrative.py` accepts both tokens in Phase C but does not test the close-location rule. `measure-spring-ict.py` explicitly collapses them: "Spring candidate at bar i = low pierces support and price closes back above it **within 0–2 bars** (Spring: same bar; Shakeout: close back inside within 2 bars)" — the proxy labels both "Spring", then types it 1/2/3 by volume alone. |
| **Test after Spring** — "Test … thường thì xuất hiện ngay sau Spring, Shakeout" (WA p80); WA2-11 makes the Test the confirmation | **PARTIAL** | `check-narrative.py:86` accepts TEST as one of several Phase-C events but never requires a Test *after* a Spring. Not in `demo-pilot.py`. |
| **WA2-36 / Dấu hiệu 3** — a genuine Phase C shake must **at least reach the opposite side of the structure**, ideally break it; otherwise the shake is rejected (WA p153, p156, p160, p164; §2.11.3) | hard rejection test | **MISSING** everywhere. Nothing measures the post-Spring excursion against the opposite TR boundary. This is the book's own "Dấu hiệu thứ ba là quan trọng nhất" (WA p160). |
| **WA2-14** After a Spring that does not retest SC, red candles with long lower wicks = CO absorbing; **LPS on the way up are the buy locations with excellent R:R** (WA p89, p92) | entry location | **MODEL** only. |
| **WA2-15 / §2.7.4** Phase D: SOS = "mở rộng chênh lệch giá và tăng khối lượng"; add at **LPS[D]**; **BU** completes the last supply test (WA p83–85) | entry location + volume floor | **PARTIAL-CODE.** `check-narrative.py:83–85` enforces the SOS/SOW volume floor: an event labelled `SOS`/`SOW` carrying `KL <1.0×` is rejected and told to relabel as UA. Good. But nothing requires an LPS[D] before an add, and `demo-pilot.py` has no SOS/LPS concept. |
| **WA2-17** Labelling at the SOS stage means **you are late** — Wyckoff's value is in Phase C (WA p77) | warning | **MISSING**. |
| **WA2-18 / giảm khung** — at an HTF Shakeout[C]/UTAD, drop a timeframe and take Spring[C]/LPS[C] there (WA p93–96) | entry technique | **CODE** — the best-implemented WA rule: `htf_context.py` module docstring + `bias_of` + `check_verdict`, wired into `local-eval-brief.py:107` (rule 8), `check-narrative.py:158–174` and `check-model-prose.py:70–72`. |
| **WA2-48** the only numeric stop example: BNB/USDT M5 long 226.0, stop 220.0 just below the Shakeout/Spring low, target the M30 SOS extreme 248.0 → R:R 1:4 (WA p96) | stop + target shape | **PARTIAL** — the shape (stop under the shake, target at the HTF extreme) is honoured in `measure-spring-ict.py` but not in `demo-pilot.py`, whose target is the window midpoint. |

### Distribution mirror (`k07` §2.8, §5.2)

| Rule | Status |
|---|---|
| **WA2-22** UT at ST[B] above BCLX then close back below → expect a test of the TR lower border (WA p103) | **PARTIAL** — `check-narrative.py` EVENT_VOCAB puts `UT` in Phase B, which matches; no reaction test. |
| **WA2-24** A UT/UTAD short has very large R:R **but it is usually SAFER to wait for Phase D and the LPSY confirmation** (WA p106) | **MISSING** — no code or skill text encodes the "prefer LPSY" preference. |
| **WA2-25 / WA3-07** Short at LPSY[C]/LPSY[D] when the rally is weak and narrow-spread (WA p107, p110, p147, p149, p177, p179; WA p189) | **MODEL** only. |
| **WA2-26** MSOW[D]: TR floor broken fast on a volume spike, negligible rally → further shorts at LPSY[D] retests (WA p109, p113, p179) | **CONTRADICTED by the checker** — see §7 item 1. |
| **WA2-27** On a lower-border break in a distribution candidate, prepare **both** scenarios (Spring vs MSOW) and let the reaction decide (WA p115); **WA3-08**: during Phase B do **NOT** label a deep dip MSOW or Spring — the call is only possible after Phase C completes (WA p189–190) | **CODE (partially, by accident)** — `check-narrative.py` `EVENT_VOCAB["SPRING"]="C"` rejects a Spring labelled inside Phase B, which enforces WA3-08 for Spring. It does **not** enforce it for MSOW (MSOW is pinned to B, the opposite error). |

---

## 4. The đối nhãn (mislabelling) tests — `knowledge/07` §2.11 (WA p150–184)

`knowledge/10` §2 A4 calls this "the step with no equivalent in the previous system"; `wyckoff-skill/SKILL.md:28`
says an untested phase call "is a hypothesis and must be labelled one".

| Test | Book | Status |
|---|---|---|
| **Dấu hiệu 1** — ST[A] in the upper 1/3 of the TR = strong support / early accumulation; lower 1/3 or below SC = early distribution (WA p150, p166; WA2-34) | quantitative, 1/3 | **MISSING as a test.** `analysis-params.json sourced.st_within_third_of_tr` (0.3333) appears in code only inside a **comment** in `htf_context.py:46–48`; the constant `BOUNDARY_FRACTION = 1.0/3.0` (`htf_context.py:49`) is hardcoded and used for a *different* purpose (where price sits in the HTF TR), which that file itself flags as "this project's adaptation, not a printed rule". No code ever locates ST[A] or measures its position. |
| **WA2-07 / ST above 50% of TR** → supply thinned, TR works in its upper half (WA p75, p88, p91) | quantitative, 0.5 | **MISSING.** `analysis-params.json sourced.st_above_half_tr` is referenced by **no script**. |
| **Dấu hiệu 2** — Phase B test type: repeated tests of the **top** (UA) → expect an upward break from a mid-structure LPS; repeated tests of the **bottom** → weakness, expect LPSY as the Phase C test (WA p154, p157; WA2-35) | **MISSING.** |
| **Dấu hiệu 3** — the Phase C shake; minimum expectation = reach the opposite side of the structure (WA p160, p164) | **MISSING** (see §3). |
| **Dấu hiệu 4** — Phase D effort-vs-result: big volume + spread on the breakout candle but **price not sustained** and demand effort fading = rejection back into the structure; **open a short only when aggressive selling negates the earlier weak demand** (WA p163–164; WA2-38) | **MISSING.** |
| **Boxed summary WA p166** — UT[B] may equally be a potential SOS, and MSOW[B] may equally be a potential Spring; read effort+result before labelling (WA2-39) | **MISSING** — and `check-narrative.py` actively pushes the other way by hard-coding UT→B, MSOW→B. |
| **Epistemic rule WA p167 / WA2-40** — you cannot know accumulation vs distribution in real time; you must enter **before** the cause-result is fully developed | **MODEL** (`SKILL.md:28`). |
| **Failure to maintain structure** (WA p181–183; WA2-47) — price bouncing **before** reaching support = demand overpowering; turning down before reaching resistance = supply entering | **MISSING.** |
| `doi_nhan_tested` recorded on the trade file | required field in `docs/architecture/schemas/trade-file.schema.json:395, 409` | **NOT VALIDATED.** `scripts/journal.py:28–29` loads the schema **only for field ordering** (`FIELD_ORDER = list(SCHEMA["properties"].keys())`); no script validates `required`. Pilot trades (`journal.py:141–150`) are written with no `wyckoff_event` object at all, yet with `dimensions_used: ["wyckoff", "ict"]`. |

---

## 5. CO plan expectations — `knowledge/07` §3.4 (WA p199–208)

| Rule | Status |
|---|---|
| **WA3-15 / Phase B** — "CO sẽ tiếp tục tích lũy khi giá tiệm cận vùng hỗ trợ" (WA p201); from ST to UT CO buys only enough to keep price out of a downtrend (WA p203) | **CODE** — this is exactly the rule `htf_context.bias_of` implements for HTF Phase B, citing WA p201 and WA p93 (`htf_context.py:53–82`). |
| **WA3-16 / Phase C** — at the Spring ("điểm sợ hãi thứ 2") CO is the most active buyer and keeps buying up to SOS (WA p200–201, p203) | **MODEL** (`SKILL.md:33`, `k10` §2 A5). |
| **WA3-17 / WA3-18 — post-SOS "khác biệt lớn"**: after SOS CO sells nothing, so a decline back to support is contrary to the plan unless CO intends it (WA p202–204) — the book's stated discriminator between accumulation and distribution | **MISSING.** Nothing tests a post-SOS decline against this. |
| **WA3-21 / WA3-22 — post-MSOW**: CO no longer supports price; a subsequent rally must fail to make a new high / makes a lower LPSY; a strong CO-backed rally after MSOW is **against the plan** (WA p207–208) | **MISSING.** |
| State the CO expectation **before** looking for confirmation (makes the read falsifiable) | **MODEL** (`SKILL.md:33` step 6). No machine check. |

---

## 6. SOT, tape reading, Volume Profile

| Rule | Book | Status |
|---|---|---|
| **WA4-51** new stopping point travels a shorter distance than the previous → SOT (WA p278) | **MISSING in code.** |
| **WA4-52** minimum **3 pushes**; 3–4 is the useful window; **more than 4 = the trend is too strong to oppose** (WA p280, p284, p292) | `analysis-params.json sourced.sot_min_pushes`, `sot_useful_max_pushes` — **referenced by no script**. MODEL only (`SKILL.md:41`, `k10` §2 A7). |
| **WA4-53 / WA4-54** the two forms: phân kỳ (momentum down, volume large) vs kiệt sức (momentum down, volume down) (WA p281–283, p292) | **MISSING in code**; MODEL. |
| **WA4-57** SOT after a potential UTAD → be cautious with longs; SOT after a potential Spring → be cautious with shorts (WA p284) | **MISSING.** |
| **WA4-58** an SOT at the TR boundary outranks a mid-range SOT; **a prior UTAD signal outranks a mid-range SOT** (WA p285–286) | **MISSING.** |
| **WA4-01..WA4-10** the ten bar-by-bar spread×volume cases (WA p221–238) | **MISSING in code** — `analysis-params.json project_defined.spread` thresholds (narrow ≤0.7×, wide ≥1.5×) are defined but referenced by no script; `local-eval-brief.py:29` cites the tape-reading section to the model as prose only. |
| **WA4-11** read only the **last** bar, and only to confirm a system signal or at important S/R (WA p243) | **MODEL.** |
| **WA4-12** Trường hợp 4 (wide spread + falling volume) = low-confidence, *dễ bị tổn thương* (WA p226, p234, p243) | **MISSING.** |
| **WA4-36..WA4-38** completed vs uncompleted auction; **require a completed auction at the balance's lower part before planning an upside exit**; if unsure, treat as completed (WA p260–262) | **MISSING.** |
| **WA4-39** above VPOC prefer long, below prefer short, **avoid operating in the VPOC's immediate vicinity** (WA p263) | **MISSING.** |
| **WA4-40** targets at HVN, entries at LVN (WA p264–265); **WA4-49** the limits of Wyckoff structures are always LVNs (WA p275) | **MISSING.** |
| **WA4-50** always prefer the direction of the last HVN; inside an HVN zone do not commit to a direction until the break is confirmed (WA p275–276) | **MISSING.** |
| **WA4-62** pullback grows larger than the prior one → supply entering: take partial profit (50% or 30%); on UTAD/LPSY close and short (WA p291) | **MISSING** — `demo-pilot.py` has no partial-exit logic. |

---

## 7. Items where the implementation CONTRADICTS the book

Ordered by how much they can change an entry or exit decision.

### C1 — `mSOW` / `MSOW` and `mSOS` are pinned to Phase B; the book puts MSOW in Phase D
`scripts/check-narrative.py:36` — `"MSOW": "B", "MSOS": "B"`. The token regex (`:40`) is case-insensitive and
upper-cases, so `mSOW[B]` and `MSOW[D]` collapse to the same token. The book distinguishes them:
- minor `mSOW` in Phase B: "IF price commits below the AR support in Phase B … (mSOW)" (WA2-23, WA p104);
- major `MSOW` in **Phase D**: "IF price breaks the TR floor quickly with a volume spike (**MSOW[D]**)"
  (WA2-26, WA p109, p113, p179); the distribution ledger orders `UTAD → MSOW → LPSY` (`k07` §3.4.3, WA p204–206);
  the SAND/USDT worked example places MSOW at 0.5800 **in Phase D** (`k07` §2.11.6, WA p179); the falling-slope
  distribution schematic labels "Phase D (MSOW, CHoCH)" (WA p173).
  `mSOS[D]` is likewise printed on the BNB/USDT M5 chart (WA p94) and the LTC/USDT M5 chart (WA p173).
**Effect:** a correctly-labelled MSOW[D] or mSOS[D] is rejected by the validator, pushing the model to mislabel it.
**Fix direction:** make the token case-sensitive (`mSOW`→"B", `MSOW`→"CD"/"D"; `mSOS`→"BD").

### C2 — Take-profit is the window midpoint, not the opposite TR boundary
`scripts/demo-pilot.py:evaluate()`: `tp = eq if (eq - entry) >= MIN_RR * r else entry + 2*r`, `eq` = the
288-bar window equilibrium from `ict-scan.analyze`. Both books give the opposite range edge:
WMT p273 ("first target = the opposite side of the Trading Range", plus the 80% rule → VAH from a Spring,
`k08` §5 Step 6) and WA p83–84 ("Trong Phase D, giá sẽ di chuyển ít nhất đến biên trên Trading Range",
`k07` §2.7.4). The `market_profile_80_rule` parameter exists in `analysis-params.json` and is used nowhere.
**Effect:** systematically truncates every winner to roughly half the book's target, which also distorts the
MIN_RR gate and therefore which setups qualify at all.

### C3 — The pilot's stop is an ICT swept low, not the Spring low, and no invalidation owner is recorded
`demo-pilot.py:evaluate()` uses `swept = min(L[sweep_i:])` where `sweep_i` is an ICT SSL/ERL sweep index.
WMT p271 / `k08` §5 Step 6 require the stop below the **Spring's** lowest low; `k10` §4.4 explicitly warns that
the ICT and Wyckoff stops differ "by the entire depth of the sweep, which changes position size by a multiple"
and rules: "name one invalidation owner per trade plan and record it". `journal.py:141–150` records none.

### C4 — Spring and Shakeout are conflated in the backtest proxy
`scripts/measure-spring-ict.py` header: "Spring candidate at bar i = low pierces support and price closes back
above it **within 0–2 bars** (Spring: same bar; Shakeout: close back inside within 2 bars)". WA p83 (boxed) makes
this the discriminating rule and WA p80 defines Shakeout as "**hầu hết các cây nến của Shakeout đóng cửa dưới biên
dưới của TR**" with its own value area. Typing the result 1/2/3 by volume alone (`k08` §2.6) also drops the book's
price-reaction and confirmation columns (Type 2 needs retests; Type 3 needs the long-wick reversal).
**Effect:** any measured "Spring" hit-rate mixes two events the book says behave differently.

### C5 — `demo-pilot.py` rule 3 cites Wyckoff for a rule the books do not state
Header line 16–17: "Wyckoff Effort-vs-Result: the sweep bar or the MSS bar carries >= VOL_MULT x average volume and
the MSS bar closes in its upper half (`knowledge/08` §2.3, §4.1)". `k08` §2.3 is SOT (shortening of the thrust);
§4.1 is the Effort-vs-Result rule. Neither states a 1.5× volume multiple nor a "close in the upper half of the bar"
test. The nearest book text, WA p84, says "**quan sát khi giá ở nửa trên Trading Range**" — upper half of the
*Trading Range*, not of the candle. Per `analysis-params.json`'s own preamble these are `project_defined` numbers
that must be reported as project parameters, "never cited as rules from the book".

### C6 — `st_within_third_of_tr` is reused for a different measurement
`htf_context.py:46–49` takes the book's ST-position yardstick (WA p150, p166) and uses it as the width of the
HTF entry zone. The file is honest about it ("this project's adaptation, not a printed rule"), but the constant is
**hardcoded** (`BOUNDARY_FRACTION = 1.0/3.0`) rather than read from `analysis-params.json`, so tuning the JSON via
`/improve` silently does nothing.

### C7 — Phase bands are forced to start at A inside the working window
`check-narrative.py:55–58` requires `"".join(letters) == PHASE_ORDER[:len(letters)]`, and `:150` requires every
event to sit inside `window_first..window_last`. A structure whose Phase A predates the window cannot be described
truthfully; the model must either invent a Phase A or drop the structure. The book's own procedure (WA p93–96
giảm khung, WA p98 tăng khung) assumes you routinely look at a structure mid-flight. Lower severity than C1–C3 but
it biases what gets labelled.

---

## 8. Gap table, sorted by importance for the entry decision

| Rank | Gap | Book source | Status | Why it matters |
|---|---|---|---|---|
| 1 | **The order path enforces no Wyckoff entry test.** `demo-pilot.py:evaluate()` = discount/premium + sweep + MSS + FVG + one volume multiple + HTF bias. No phase, no TR, no Spring, no type, no VAH/VAL, no đối nhãn | WMT p356–357 B1–B5; WA §2.7.3–2.7.4 | MISSING | The only path that sends money is the one with the least Wyckoff in it, while journalling `dimensions_used: ["wyckoff","ict"]` |
| 2 | **Volume Profile / VAH-VAL-LVN abandon rule** — the book's own thesis-invalidation | WMT p243–249, `k08` §5 Step 4; WA p275–277 | MISSING in code; absent from the Path-B brief entirely | It is a *veto*. Without it a Spring thesis that the book says is dead stays alive |
| 3 | **TP = opposite TR boundary** replaced by the window midpoint | WMT p273; WA p83–84 | CONTRADICTED (C2) | Halves every target and changes which setups pass MIN_RR |
| 4 | **Phase-C shake must reach the opposite side of the structure** ("Dấu hiệu thứ ba là quan trọng nhất") | WA p153, p156, p160, p164 | MISSING | The book's own primary rejection test for a false Spring |
| 5 | **đối nhãn tests 1, 2, 4 + failure-to-maintain-structure** | WA p150–183, §2.11 | MISSING in code; MODEL-only, unvalidated | `trade-file.schema.json` requires `doi_nhan_tested` but nothing validates the schema |
| 6 | **MSOW/mSOS phase membership wrong in the validator** | WA p109, p113, p173, p179, p204–206 | CONTRADICTED (C1) | Actively forces mislabelling of the key distribution Phase-D event |
| 7 | **Stop level + single invalidation owner** | WMT p271; `k10` §4.4 | PARTIAL/CONTRADICTED (C3) | Silent position-size inflation |
| 8 | **SOT entirely absent from code** (3/3–4/>4 push bounds; phân kỳ vs kiệt sức; SOT at boundary > mid-range; UTAD outranks SOT) | WA p278–292; `k08` §2.3 | MISSING; params unused | Used by both books for exits and for rejecting late entries |
| 9 | **Breakeven / trailing stop / partial take-profit** | WMT p272; WA p291 | MISSING | `check_exit` only resolves OCO or a time stop |
| 10 | **Spring low-volume partial-position rule** ("mở một phần vị thế", WA p80) | WA p80; param `spring_low_volume_max_ratio` | MISSING (param unused) | The book sizes the Spring entry as partial, the pilot always enters full |
| 11 | **Test-after-Spring as the confirmation** | WA p80, p153, p156 | PARTIAL | Confirmation step skipped |
| 12 | **CO post-SOS / post-MSOW discriminator** | WA p202–204, p207–208 | MISSING | The book's stated accumulation-vs-distribution discriminator |
| 13 | **Prefer LPSY over UT/UTAD for shorts** | WA p106 (WA2-24) | MISSING | The book calls the UTAD short the less safe of the two |
| 14 | **Bar-by-bar 10 cases + "Trường hợp 4 = low confidence"** | WA p221–243 | MISSING in code | Spread thresholds exist in params, unused |
| 15 | **Six unused `sourced` parameters** (`st_above_half_tr`, `sot_min_pushes`, `sot_useful_max_pushes`, `value_area_pct`, `market_profile_80_rule`, and `st_within_third_of_tr` in comment only) | analysis-params.json | Dead config | Every one of these is a number the book prints; none reaches a decision |

---

## 9. Author's "do NOT trade" warnings, and whether the system honors them

| Warning | Book | Honored? |
|---|---|---|
| **Phase B with balanced tests at both borders, no unusual volume, no sign of CO → do not trade, wait for Phase C**: "nguồn cung/cầu đang khá cân bằng … chưa cho thấy sự xuất hiện của CO" | WA p95 (WA2-10); WA p95–96 | **YES, in code.** `htf_context.bias_of` returns neutral mid-range Phase B and `check_verdict` (`:136–137`) blocks `SETUP TIỀM NĂNG` on neutral bias. `demo-pilot.py:evaluate()` step 4 inherits it via `HTF_FILTER`. Best-honored warning in the system. |
| **Do not buy an early Phase-B break above AR — it is a UA bull trap where CO clears stops** | WA p78, p88 (WA2-09) | **PARTIAL, in code.** `check-narrative.py:83–85` forces a below-average-volume "SOS" to be relabelled UA, citing WA p78/p88. But nothing stops a verdict from being long at that location. |
| **A deep Phase-B dip must NOT be labelled MSOW or Spring before Phase C completes** | WA p189–190 (WA3-08) | **PARTIAL.** Enforced for Spring by `EVENT_VOCAB["SPRING"]="C"`; the mirror for MSOW is inverted (C1). |
| **"Tôi không khuyến khích mọi người giao dịch với những mẫu hình dốc như thế này"** — sloped structures have no slope standard and the TR becomes subjective; first-time operators should use horizontal schematics only | WA p167, p170 (WA2-42) | **NO.** Mentioned in `wyckoff-skill/SKILL.md:28` ("the author discourages trading them") but nothing detects slope or downgrades the read. |
| **PS is only the first hint of demand, NOT a reversal signal — do not act** | WA p73 (WA2-05) | **NO.** `EVENT_VOCAB["PS"]="A"` accepts the label; no "do not act" consequence. |
| **Labelling at the SOS stage means you are late** | WA p77 (WA2-17) | **NO.** |
| **More than four pushes: the trend may be too strong to oppose** | WA p284, p292 (WA4-52) | **NO in code** (param unused); MODEL only (`SKILL.md:41`). |
| **Falling-slope distribution moves too fast to enter — "ít ra chúng ta sẽ không chọn sai phe … không dại gì lại mua vào thời điểm này"** | WA p174–175 (WA2-45) | **NO.** |
| **In a rising-slope distribution, Phase B is only an assumption — wait for the Phase C action (UTAD)** | WA p177, p179 (WA2-46) | **PARTIAL** — the generic neutral-Phase-B gate covers the practical effect. |
| **If price crosses cleanly through VAH/VAL into the LVN with no reversal reaction: abandon the Spring/Upthrust plan** | WMT p243–249 | **NO in code** (see gap 2). |
| **WMT §2.8 (p064–066): Spring/Upthrust pattern recognition alone is insufficient** — volume detail is imprecise, candles hide the buy/sell distribution, Spring/Upthrust can be confused with a genuine breakdown without order-flow confirmation, and **stop placement is imprecise without price/volume detail** | WMT p064–066 | **DELIBERATELY DIVERGED.** `wyckoff-skill/SKILL.md:45` states "This skill does not need footprint data. Steps 1–9 all run on candles plus volume". That is defensible under WA §4.1 (tape reading needs only spread + volume) but it is WMT's own stated reason for Parts II–III, and the system currently runs live with CoinGlass MOCK, i.e. exactly the configuration WMT warns about. Worth recording as an accepted risk rather than a silent gap. |
| **"Chúng ta không thể thực sự biết đó là tích lũy hay phân phối"** — you must enter before the cause-result is fully developed | WA p167 | **MODEL** (`SKILL.md:28`). |
| **Buying range lows / selling range highs without phase context is explicitly discouraged (poor R:R)** | WMT p236–238, `k08` §5 Step 2 | **NO.** `demo-pilot.py` buys discount sweeps with no phase context at all — this is precisely the discouraged trade, mitigated only by the HTF bias filter when `HTF_FILTER` is on. |

---

## 10. What IS well covered (so it is not re-done)

- **Giảm khung / top-down direction rule** (WA p93–96): fully mechanised in `htf_context.py`, wired into the
  brief (`local-eval-brief.py:107`), the narrative checker (`check-narrative.py:158–174`) and the prose checker
  (`check-model-prose.py:70–72`), and gating the pilot (`demo-pilot.py:evaluate()` step 4).
- **Phase grammar** (`check-narrative.py:phase_grammar`): contiguity A→E, chronological order, phase/event
  membership, Phase A needs SC/BC, Phase C needs a test event, Phase D needs SOS/LPS/BU, SOS/SOW volume floor.
- **UT vs UA phase-conditional naming** (WA p8, `k07` §1.3): stated in `SKILL.md:40` and encoded in
  `EVENT_VOCAB` (`UA`→B accumulation, `UT`→B distribution, `UTAD`→C).
- **Wyckoff/ICT de-duplication and the shakeout-vs-displacement contradiction** (`k10` §4.3, §4.5):
  `SKILL.md:52–60`, `same_level_tolerance_atr` referenced by the skills and the confluence schema.
- **Method purity** (`scripts/method_purity.py`): keeps the Wyckoff vocabulary out of the ICT block and vice versa.

---

## 11. Suggested order of remediation (not performed — audit is read-only)

1. Fix `EVENT_VOCAB` case-sensitivity for `mSOW`/`MSOW`/`mSOS` (C1) — smallest change, removes an active
   mislabelling pressure.
2. Change `demo-pilot.py` TP to the range boundary the books name (C2), or state explicitly in the header that
   the midpoint is a deliberate project deviation.
3. Add a Volume Profile computation (VAH/VAL/LVN from `value_area_pct`) and wire the abandon rule as a veto,
   plus put it into `local-eval-brief.py`'s citation map so Path B is even asked for it.
4. Implement the Phase-C "shake must reach the opposite boundary" test and the ST-position tests (they only need
   the TR boundaries, which `check-narrative.py` already has in `wyckoff.trading_range`).
5. Add SOT push-counting and wire the four unused `sourced` parameters.
6. Validate `trade-file.schema.json` `required` in `journal.py` so `doi_nhan_tested` cannot be omitted.
