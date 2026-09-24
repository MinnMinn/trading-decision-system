# Wyckoff label review: CFD Scalping XAUUSD 15m (response to an external critique)

**Date:** 2026-09-24 · **Type:** read-only advisory. No code, narrative or config was changed.
**Subject:** the six-point critique (from another AI, Grok) of the Wyckoff labels on the published CFD Scalping XAUUSD 15m chart.
**Labels under review:** `data/live/narrative/cfd-scalping.json`, `symbols.XAUUSD`, full analysis `updated 2026-09-11T15:00:00Z`.
**Sources used for verdicts:** `knowledge/wyckoff/advance.md` (WA, the primary source for the event vocabulary per `knowledge/integrated/method.md` §1 line 21), `knowledge/wyckoff/modern-tools.md` (WMT), `knowledge/integrated/method.md`. A claim the books do not make is marked **NOT IN THE BOOK** and gets no rule proposal (CLAUDE.md §13).

Verdict scale: **SUPPORTED** (the book states it) · **PARTLY SUPPORTED** (part stated, part not, or the book states it in a weaker form) · **NOT IN THE BOOK** · **CONTRADICTED** (the book states the opposite).

---

## 0. What was actually drawn, and what is true now

Facts from the repo, checked in this session:

| Item | Value | Where |
|---|---|---|
| Structure / phase | `tích lũy`, Phase **D**, regime TRANSITIONAL | `cfd-scalping.json` `symbols.XAUUSD.wyckoff` |
| Phase bands | A 09-10 19:00 → 09-11 04:00 · B → 12:15 · C 12:15 → 12:35 · D 12:35 → 15:00 | same, `phases[0..3]` |
| Events | SC 4,313.68 · AR 4,340.42 · ST 4,300.64 · UA[B] 4,361.01 · ST[B] 4,324.66 · Spring[C] 4,289.57 (12:30) · SOS[D] 4,390.13 (12:45) · LPS[D] 4,370.76 (14:45) | same, `events[0..7]` |
| Trading range | AR 4,340.42 / "ST 4,300.64 (dưới SC 4,313.68)" | same, `trading_range` |
| Invalidation | owner `wyckoff`, level 4,289.57, rule "đóng cửa dưới đáy Spring 4,289.57" | same, `invalidation` |
| Spring bar | low 4,289.57, **close 4,353.82**, volume **2.78×** (tick) | `wyckoff.text_html` paragraph 3 |
| SOS bar | close 4,388.38, volume 2.49× (tick); validated in prose "vì khối lượng vượt trung bình" | `wyckoff.text_html` paragraph 4 |
| 4H context | "Spring[C] 4,289.57" at the 4H 09:00 bar; 4H TR low = **4,285.91** | `context.wyckoff` |
| 4H ICT context | last 4H MSS **bearish** (4,340.63); price "vùng premium nhẹ" | `context.ict.text_html` |
| First close below the Spring low | **2026-09-15T23:45Z, close 4,283.38** | `data/live/prelim/cfd-scalping.facts.json` → `symbols.XAUUSD.anchors.levels[spring_low].first_close_beyond` |
| Scanner verdict now | "PHÁ DƯỚI Spring[C] 4,289.57 … cấu trúc mất hiệu lực, cần phân tích lại"; ref close 4,263.69 @ 09-24 11:15 | same file, `anchors.verdict` |
| Engaged / analysed methods | engaged `('ict',)`, analysed `('wyckoff','ict')`, the same for all six styles | `htf_context.engaged_methods` / `analysed_methods`, run this session |

**How the stale read reaches the page today.** The entry chart window is 576 × 15m starting about 09-18. So `chart.js` `idxOf` (`scripts/chart.js:173`) returns -1 for the 09-10/11 event flags, and `spanOf` (`:174`) makes all four phase bands zero-width (`:220`, `b<=0 → return`). The **flags and bands are therefore no longer drawn on the entry chart.** Two kinds of line are still drawn across the full width:
- the TR lines, from `max(0, spanOf(tr.from))` to the right edge with axis labels (`scripts/chart.js:221-222`);
- every Wyckoff anchor from `anchors.cfd-scalping.json`: SC, AR, ST, **Spring 4289.57**, **SOS 4390.13** (`levelShapes`, `scripts/chart.js:233`).

The invalidation line is also drawn full width (`planShapes`, `scripts/chart.js:251`). In the matrix, the synthesis cell still shows the 09-11 verdict chip THEO DÕI LONG and the badges `tích lũy / Phase D` (`scripts/build-artifact.py:707-735`). Only the free text of the scanner verdict says the structure is dead. The critique was probably made against an earlier build, when the window still contained 09-11 and the flags and bands were visible. That point matters for §7, not for the verdicts.

---

## 1. Point 1: "Spring[C] 4,289.57: the close is below the low, so it is invalid. 4H bias is SHORT + premium, so this is a shakeout in the range, not an accumulation Spring. Only call it a Spring when (a) HTF is clearly Accumulation, (b) the close is back inside the range, (c) a lower-volume Secondary Test follows."

### (a) Verdict by sub-claim

| Sub-claim | Verdict | Book basis |
|---|---|---|
| "Close below the Spring low → invalid" | **SUPPORTED as a post-write invalidation. It does not show that the label was wrong when written** | Stop/invalidation is "below the lowest low of the Spring" (WMT p271; `knowledge/wyckoff/modern-tools.md` §5 Step 6, and `knowledge/integrated/method.md:155`). The narrative set that same rule as its own invalidation. A Spring means "nguồn cung cạn kiệt nên việc giá tồn tại ở ngoài Trading Range là khá ngắn ngủi". When price stays out there and builds value, the book reads it as "nguồn cung vẫn còn" (WA p83, `advance.md:336`). Price has closed below 4,289.57 since 09-15 23:45. |
| "4H SHORT + premium ⇒ shakeout, not Spring" | **CONTRADICTED** (the terms), **PARTLY SUPPORTED** (the intuition) | In the book a **Shakeout** is itself a bullish Phase C *accumulation* test, where "hầu hết các cây nến của Shakeout đóng cửa dưới biên dưới của TR" (WA p80, `advance.md:334`; WA2-12 `advance.md:1083`). So it is not an alternative to "accumulation". "Premium" is ICT vocabulary with no place in a Wyckoff event definition (method.md §4.3 `method.md:146`). The intuition that the HTF must be consulted *is* in the book, but for trade quality, not for naming: see (c-a). |
| (a) Label a Spring only if HTF is clearly Accumulation | **NOT IN THE BOOK** as a naming precondition | The Spring definition is local to the TR being read: "Một 'Spring' có giá dưới mức thấp nhất của Trading Range và sau đó đảo chiều để đóng trong Trading Range" (WA p80, `advance.md:333`). HTF agreement shows up as a **trade-quality / confirmation** factor: an m5 Spring[C] "sẽ đồng thuận với bối cảnh hoàn thành Shakeout[C] M30, khả năng nâng cao (R:R) tốt hơn" (WA p94, `advance.md:361`); WA2-18/19/20 (`advance.md:1089-1091`), where WA2-20 says to *re-examine holding* when the HTF shows prior supply. |
| (b) Close back inside the range | **SUPPORTED** | WA p80 (above); WA2-11 (`advance.md:1082`). Already R6 in `scripts/wyckoff_rules.py:33-34, 271-275`. |
| (c) A lower-volume "Secondary Test" must follow | **PARTLY SUPPORTED** | The book's post-Spring event is **Test**, not "Secondary Test" (ST is a Phase A/B event, WA p73). "Test … Thường thì xuất hiện ngay sau Spring, Shakeout" (WA p80, `advance.md:335`). WA2-11 makes Test (and reaching the upper border) a *confirmation* (`advance.md:1082`). But the book also allows no Test at all: "sau khi tạo ra Spring thì giá không quay trở lại để test … có thể mở vị thế mua sớm" (WA p89, WA2-14 `advance.md:1085`), and "Một Spring khối lượng thấp … thời điểm tốt để bắt đầu mở một phần vị thế" before any Test (WA p80). The Test is confirmation, not part of the name. |

### What the book says *against* the 09-11 label, which the critique missed

These are stronger than the critique's arguments and rest on the book's own tests:

1. **Đối nhãn Dấu hiệu 1 contradicted accumulation at write time.** ST[A] 4,300.64 sat *below* SC 4,313.68, and the narrative says so itself ("thấp hơn SC, cung còn nhiều"). The book reads that case like this: "Nếu ST ở 1/3 phần dưới Trading Range hoặc thậm chí … [phá] hỗ trợ cục bộ SC … dấu hiệu để nhận dạng sớm tái phân phối hoặc phân phối" (WA p150, `advance.md:461-465`; WA2-34 `advance.md:1105`). ST below SC also means "expect new lows or a prolonged consolidation with many further STs" (WA2-06, `advance.md:1077`). The narrative never ran method.md step A4, "A phase call that has not been tested is a hypothesis, and must be reported as one" (`method.md:55`). `wyckoff_rules.py` R3 would have returned `st_sign = "contradicts"` (`scripts/wyckoff_rules.py:219-222`).
2. **Volume type was never recorded.** A 2.78× bar is Spring **type 3** under the project's thresholds (`analysis-params.json` `volume.high_min_ratio` 1.5, `spike_min_ratio` 2.5; WMT Bảng 2.1). The book's high-probability case is the opposite: "**Một Spring khối lượng thấp** chỉ ra rằng sản phẩm có khả năng sẵn sàng tăng" (WA p80, `advance.md:331`). method.md A6 requires *both* the WA event class and the WMT volume type (`method.md:59`). The narrative gives only the first.
3. **The prose contradicts its own numbers.** It says the Spring bar "đóng cửa ngay trong Trading Range tại 4,353.82". But the narrative's TR is 4,300.64–4,340.42, so that close is *above AR*: the bar swept below the range and closed beyond the opposite border. Spring and breakout happened in one bar, with Phase C lasting one bar (12:15–12:35 band) and no Test. The book has no single-bar Spring-plus-breakout case. This is a factual error in the prose, and `check-narrative.py` did not catch it because it checks that numbers exist, not how they relate.
4. **The 4H "Spring" was not a Spring by definition.** The context read calls the 4H 09:00 bar "Spring[C] 4,289.57", but the context's own 4H TR low is 4,285.91. The bar never traded below the range low that WA p80 requires, so on 4H the label fails the book's definition.
5. **HTF disagreement was not declared.** The 4H ICT read (last MSS bearish, premium) and the 4H Wyckoff read (accumulation Phase C) disagree. The synthesis turned that into "bias khung lớn nghiêng LONG" and cited only the Wyckoff side. method.md §4.2 item 3 says an HTF structural break that contradicts the phase call "is a Contradiction to be raised, not resolved by preferring one tradition" (`method.md:134`), and CLAUDE.md §19 says the same.

**Conclusion.** Under the book, the 09-11 label was at best "Spring[C] candidate: volume type 3 (tick), Dấu hiệu 1 contradicts, no Test". It was not a Phase D accumulation. The label did pass WA2-36: price reached the opposite border at once (`advance.md:1107`). Since 09-15 23:45 its invalidation has fired.

### (b) What code and narrative do today
- `scripts/wyckoff_rules.py` (the backtest engine, not the live narrative) already encodes R3 Dấu hiệu 1 (`:219-222`), R6 Spring vs Shakeout (`:271-275`), R7 volume type (`:276-279`) and R8 Test (`:290-297`). **None of these is applied to the LLM-written narrative.**
- `scripts/check-narrative.py` `phase_grammar` (`:47-118`) checks phase order, event-to-phase membership, and "Phase C has a test event" (`:102-103`). It does not check the Spring bar against the TR, the ST position, the volume type, or HTF agreement.
- The narrative schema's `events` items allow only `time/label/up` (`docs/architecture/schemas/narrative.schema.json:31`). There is nowhere to record `event_class`, `volume_type` or `st_sign`.

### (c) Proposal
- **P1.1 (narrative contract + checker).** Add optional structured fields to Wyckoff `events[]`: `event_class`, `volume_type` (1/2/3), `volume_kind` (`traded|tick`), and to `wyckoff`: `doi_nhan` `{st_sign, phase_b_sign}` (the names used by R3/R3b). `check-narrative.py` then **requires**:
  - for every `Spring`/`Shakeout` event, `volume_type`, recording both vocabularies (method.md A6, decision 5 `method.md:207`);
  - `doi_nhan.st_sign`, and when it is `contradicts`, the phase must not be past C unless `alternative` (P6.1) is present and the synthesis names the contradiction (WA2-34, method.md A4);
  - the Spring event bar's close above `trading_range.low` (WA p80). A close above `trading_range.high` in the same bar is a **warning** ("Spring và phá biên trên cùng một nến — Phase C không có Test"), not a failure. The book has no rule for that case, so it cannot be a hard gate.
  Values are computed deterministically from the snapshot candles by reusing the `wyckoff_rules.py` functions. They are not trusted from the model.
- **P1.2 (context read).** In `phase_grammar` for `context.wyckoff`: a `Spring`/`UTAD` event in the context read must lie beyond the context `trading_range` border (WA p80). That rule would have refused the 4H "Spring 4,289.57 > TR low 4,285.91".
- **Rejected:** the "HTF must be clearly Accumulation before the word Spring" precondition (NOT IN THE BOOK). HTF disagreement is instead raised as a Contradiction (P4.1).
- **Version significance:** P1.1/P1.2 change what Wyckoff analysis may *claim*. Wyckoff is engaged in no style today, so there is no live decision change. But the narrative phase feeds `htf_context.wyckoff_bias` (`scripts/htf_context.py:224-272`) for any preset that engages Wyckoff, so under CLAUDE.md §59 this is **methodology-interpretation significant**. Record it in an ADR and version the Wyckoff analysis contract. No Trading System bump is needed while no TS has Wyckoff as REQUIRED_FOR_DECISION.

---

## 2. Point 2: "SOS[D] 4,390.13 labelled early: weak close, weak follow-through, deep pullback. Only label SOS on a strong breakout + rising volume + close near the high + 1–2 follow-through bars holding above AR."

### (a) Verdict: **PARTLY SUPPORTED**
| Element | Verdict | Book basis |
|---|---|---|
| Strong breakout, widening spread, rising volume | **SUPPORTED** | "SOS … khi giá có khoảng thời gian cam kết ở trên mức cao nhất của Trading Range biểu hiện mức chênh lệch và khối lượng tăng đều" (WA p84); Phase D is shown by an SOS "về việc mở rộng chênh lệch giá và tăng khối lượng" (WA p83–84) (`advance.md:344-346`). |
| Follow-through holding above AR | **SUPPORTED (qualitatively)** | "khoảng thời gian cam kết" (WA p84). The book gives no bar count. The project fixed it at **2 consecutive completed closes**, labelled `project_defined` (`docs/architecture/analysis-params.json` `commitment_bars`). WA2-38: breakout candles with volume and spread that are **not sustained**, with demand then fading, are a rejection back into the structure (`advance.md:1109`). |
| Close near the *bar's* high | **NOT IN THE BOOK** | The book's close criterion is relative to the **TR**: "đóng cửa trên phạm vi giá của Trading Range … đóng cửa ở mức cao nhất Trading Range với khối lượng rất lớn" (WA p85, `advance.md:346`). The extraction records no close-position criterion in the Bar-by-Bar cases either (`advance.md:1877`). |
| "Deep pullback" disqualifies | **PARTLY SUPPORTED** | Phase D requires "giá sẽ di chuyển ít nhất đến biên trên Trading Range" (WA p84). WA2-47 (`advance.md` WA p182): turning down before reaching resistance shows supply taking over. At write time the pullback low 4,370.76 was still *above* AR 4,340.42. The deep pullback happened after the read. |

### (b) Current behaviour
- The narrative justified SOS on volume alone: "một dấu hiệu sức mạnh (SOS[D]) hợp lệ vì khối lượng vượt trung bình" (`wyckoff.text_html` ¶4). It never states commitment.
- `check-narrative.py:98-101` enforces only `KL ≥ 1.0×` for SOS/SOW. The label here has no `KL` token (`"SOS[D] 4,390.13"`), so even that check was skipped.
- The deterministic engine is stricter. `wyckoff_rules.py` R11 requires close > TR high, spread ≥ average, volume ≥ average, **and** `COMMIT` consecutive closes above (`scripts/wyckoff_rules.py:46-48, 305`). **The live narrative applies a weaker SOS test than the backtest engine.** This is the concrete defect behind the critique.
- The label price 4,390.13 is the bar high; the prose uses the close 4,388.38. Not wrong, but label and anchor are not the close.
- **Unverified:** whether the 13:00 bar closed above AR. The 09-11 snapshot candles are not in the working tree: `data/live/mt5-bridge/ohlcv.XAUUSD.15m.json` starts 2026-09-15T15:45Z, and the snapshot directory `local-eval-gold-20260911T150202Z` was not found. The narrative's own numbers (peak 4,402.45, pullback low 4,370.76 > AR) suggest commitment held. That is an inference, not a check.

### (c) Proposal
- **P2.1 (checker).** An `SOS`/`SOW` event in the narrative must pass the same deterministic test as R11: close beyond the TR border, spread and volume ≥ `lookback` average, and `commitment_bars` consecutive **completed** closes beyond, all available at `updated` (point-in-time). If the commitment bars do not exist yet at write time, the label must be written as a candidate, `SOS[D]?` (see P3.1). Remove the "KL token optional" hole: the checker computes the ratio from candles rather than parsing the label.
- **Rejected:** "close near the bar high" (NOT IN THE BOOK). Keep the book's "close above the TR".
- **Version significance:** same as P1. The checker only aligns the narrative with R11, which the backtest engine already uses, so it causes **no backtest-semantics change**.

---

## 3. Point 3: "LPS 'đang test' is not a confirmed LPS; only tag [D] once a bar closes above that level on lower volume than the SOS."

### (a) Verdict: **SUPPORTED**
- LPS[D] is "sự thoái lui của giá sau khi tạo SOS" (WA p84, `advance.md:347`). The Phase D description pairs it with "khối lượng nguồn cung giảm dần" (WA p83–84, `advance.md:344`), which supports the lower-volume part.
- The book describes the LPS as *completed* once demand pushes price back up: the last supply "được hấp thụ mạnh và đẩy giá lên lại tạo nên BU/LPS" (WA p85, `advance.md:348`). A pullback still in progress is not yet that event.
- The book uses a "?" notation for unconfirmed events on its own schematics: "BUEC?" / "JAC?" (WA p161, `advance.md:480` ff.) and "Local accumulation as Spring?" (WA p93, `advance.md:361`). Marking a candidate is therefore book practice, not an invention.
- The **exact** trigger (the first up-close back above the level) is not printed in the book. `wyckoff_rules.py` R11 already uses it as the project reading: "entry at the first up-close of the pullback" (`scripts/wyckoff_rules.py:46-48, 308-313`, pullback volume `< V[sos]`).

### (b) Current behaviour
- The event flag reads `LPS[D] 4,370.76` with no candidate marker. The unconfirmed status survives only in the timeline ("LPS[D] đang test") and the prose ("chưa xác nhận giữ"). The chart flag, which is what a reader sees, drops it.
- Pullback volume 1.92× vs SOS 2.49× is lower than the SOS, as R11 requires, but it is still well above average. The book's "giảm dần" is relative, so this passes R11's test while being weak evidence.

### (c) Proposal
- **P3.1 (label grammar, checker).** Add the book's "?" convention to the grammar in `check-narrative.py`. A `LPS`, `BU`, `LPSY`, `Test`, `SOS` or `SOW` event whose confirming bar (per P2.1 / R11) is not in the candles up to `updated` **must** end with `?`, and a label with `?` must not open a later phase band. So Phase D may not start on `SOS?`.
- The chart draws `?` labels with a dashed flag (see §7 styling).
- **Version significance:** display plus analysis contract only. Methodology-interpretation significant in the §59 sense for any preset that engages Wyckoff, because a candidate no longer advances the phase letter used by `wyckoff_bias`.

---

## 4. Point 4: "Phase A–D on 6 days of 15m is forced. The schematic belongs on 4H/Daily, with 15m only to refine entry. Rule: if the 4H bias opposes the 15m phase, cut confidence 50% or switch to observe."

### (a) Verdict: **CONTRADICTED** (15m schematics are illegitimate) · **SUPPORTED** (HTF context first, HTF disagreement must be handled) · **NOT IN THE BOOK** (the 50% number)
- **The book runs full Phase A–E schematics on intraday charts.** The first worked accumulation in the book is **XAUUSD m15** (Sơ đồ tích lũy #1, WA p87–89, `advance.md:359`). Others are MATIC m5, BNB M30/M5, XRP/NEAR/SOL M5 (`advance.md:360-362`, §2.11). Fractality is explicit: "Quy trình … sẽ liên tục diễn ra trên thị trường ở mọi khung thời gian khác nhau … một quy trình 4 giai đoạn của khung thời gian nhỏ sẽ trong một giai đoạn của một khung thời gian lớn" (WA p60, `advance.md:253`). A 15m schematic is not wrong in itself.
- **HTF first is book procedure.** WMT Step 1 says to determine the broader trend on a higher timeframe first, then the local TR on the trading timeframe (WMT p233–236). WA2-18 drops a timeframe to *refine entry* (`advance.md:1089`), WA2-19 moves up a timeframe to *hold/target* (`:1090`), and WA2-20 says HTF prior supply against an LTF bullish read means re-examine (`:1091`). The critique's "15m refines entry" matches WA2-18, but the book does not forbid the 15m schematic.
- **What makes this particular read weak is proportion, not timeframe.** The structure lasted about 20 hours (09-10 19:00 → 09-11 15:00), with Phase B (≈8 h) shorter than Phase A (≈9 h) and Phase C one bar. The book says Phase B "thời gian hình thành … thường sẽ dài nhất" (WA p79, `advance.md:325`). "Thường" means usually, so this is a warning sign, not a rule. By cause–effect, "một nguyên nhân lớn sẽ tạo ra mục tiêu lớn hơn và một nguyên nhân nhỏ sẽ dẫn đến mục tiêu thấp hơn" (WA p30, `advance.md:165`). A 20-hour cause supports only a local objective, which is the book's reason to nest it in the HTF read.
- **"Cut confidence 50%" is NOT IN THE BOOK.** It would also bring back a Confidence-% style number, which CLAUDE.md §18 forbids ("Confluence Score", no fake probability).

### (b) Current behaviour
- `check-narrative.py:208-236` already requires a cited HTF Wyckoff and ICT context read. `htf.check_verdict` (`scripts/htf_context.py:396-415`) refuses a SETUP TIỀM NĂNG against the HTF bias and requires "ngược bối cảnh" to be written for a THEO DÕI against it.
- **Gap:** the bias it checks against is `bias_of(..., methods=engaged_methods(style))` (`check-narrative.py:232-233`), which is ICT-only today. The synthesis wrote "bias khung lớn nghiêng LONG" from the 4H *Wyckoff* read while the 4H ICT read had a bearish MSS. Nothing forces a disagreement *between the two HTF reads* to be declared.
- **Gap:** `wyckoff_bias` returns `long` for "tích lũy + Phase C/D/E" (`scripts/htf_context.py:242-245`) with no check that the structure is still intact. `load_context('cfd-scalping','XAUUSD')`, run this session, still carries the 09-11 context read (`tích lũy`, Phase C, TR low 4,285.91) against a 4H last close of 4,261.60, *below that TR low*. Its bias comes out `neutral` only because ICT is the sole engaged method.

### (c) Proposal
- **P4.1 (narrative contract).** When the `context.wyckoff` direction and the `context.ict` direction disagree, the synthesis must contain an explicit Contradiction sentence naming both (CLAUDE.md §19; method.md §4.2 item 3, `method.md:134`). Enforce it in `check_verdict` by computing both methods' bias with `METHOD_BIAS` (`htf_context.py:275`), not only the engaged set. The *tolerance* (WAIT / NO TRADE / allowed) stays with the active Trading System's contradiction configuration, not a fixed haircut.
- **P4.2 (nesting field).** Add `wyckoff.nesting`: where the working-TF TR sits inside the HTF TR (price position plus the HTF event it coincides with, if any), per WA2-19/20. The field is descriptive, and the checker requires it when a context read exists.
- **P4.3 (bias integrity).** See P7.4. `wyckoff_bias` must not return a direction from a structure whose TR border has since been closed beyond.
- **Rejected:** the 50% confidence rule (NOT IN THE BOOK, and it conflicts with §18). Also rejected: "schematics only on 4H/Daily", which the book contradicts at WA p87–89 and p60.
- **Version significance:** P4.1 changes when a verdict is refused, and P4.3 changes the bias gate. **Trading-System-version significant** for any TS/preset that engages Wyckoff or uses `bias_of` with Wyckoff (including `backtest-methods.py:494-498` via `live_rules.bias_at`). No effect on the current ICT-only presets beyond stricter narrative validation.

---

## 5. Point 5: "MT5 tick volume is not reliable enough for Effort vs Result; state a clearer disclaimer and lower the weight of volume."

### (a) Verdict: **PARTLY SUPPORTED**
- The book's own caveat is narrower than the critique. WMT flags **tick-based Delta** as not real volume and unreliable for order-flow analysis, and states real-volume availability as a requirement of *its footprint method* (WMT p131–133, `modern-tools.md:108, 233-234`).
- Extending this to classic Effort-vs-Result on plain volume is the **project's** inference: method.md §4.1 (`method.md:128`), §5 row "Candles + tick volume: every effort/volume claim reduced" (`:177`), §6.3 "reduce credit" (`:191`), and `docs/architecture/mt5-bridge.md` ("Hard caveat: volume here is NOT real traded volume"). It is a reasonable data-quality position (CLAUDE.md §20), but it is not a book rule.
- The book itself runs full volume-based walkthroughs on **XAUUSD m15** and FX pairs with no tick-volume caveat: EUR/USD M5, AUDUSD M15, USD/CAD M15, USDJPY M30 (WA p87–89, p112–119, p97–98). Whether those charts carried tick volume is not stated in the extraction.
- "Lower the weight of volume" is SUPPORTED as project policy (method.md §6.3). The book gives no number, so any number would be `project_defined` in `analysis-params.json`, and it applies only to the Confluence Score rubric (`SYSTEM-DESIGN.md` §6.2), where Wyckoff scores nothing for CFD today.

### (b) Current behaviour
- The disclaimer exists **three times** in the narrative (`wyckoff.text_html` ¶5, `synthesis_html` ¶5, `context.wyckoff.text_html` ¶2). The chart legend adds a tick-volume marker (`scripts/chart.js:526`, `d.tick` from `build-artifact.py:1528` `I.is_tick_volume`). `wyckoff_rules.py` carries `volume_kind` (R0, `:49-59`).
- **The real problem is prose that contradicts the disclaimer.** The same text validates events *by* tick volume: "SOS[D] hợp lệ vì khối lượng vượt trung bình", "SOS khối lượng 2.49× hợp lệ (≥ trung bình)". A disclaimer followed by volume-as-proof is the pattern the critique reacts to. The checker's own SOS floor (`check-narrative.py:99`) also treats a tick ratio as validation.

### (c) Proposal
- **P5.1 (narrative contract).** When `volume_kind == "tick"` for the symbol, the checker refuses prose that uses volume as the **sole** validator of an event ("hợp lệ vì khối lượng…"). Every volume ratio printed must carry the tick marker, e.g. `KL 2.49× (tick)`. Volume may be *reported* but not be the deciding criterion. The deciding criteria then fall back to price-structure tests: close beyond the border, commitment bars, Dấu hiệu 1–2 position tests, WA2-36 objective reached. The disclaimer is written once, in the Wyckoff cell, not repeated.
- **No new weight number.** Keep method.md §6.3's qualitative "reduce credit" until a Trading System actually scores Wyckoff on a tick feed. At that point the reduction goes in `analysis-params.json` `project_defined`, labelled as an assumption.
- **Version significance:** narrative-contract only, **not** TS-version significant while Wyckoff is unscored on CFD. It becomes significant if a TS later scores Wyckoff on MT5 data.

---

## 6. Point 6: "Draw only the TR borders (AR/SC) and clear events; don't shade Phases A–E without enough evidence; always write an alternative scenario."

### (a) Verdict: **PARTLY SUPPORTED**
- **Alternative scenario: SUPPORTED.** At a border break, "prepare BOTH scenarios — Spring … and MSOW … and let the reaction decide" (WA2-27, `advance.md:1098`, WA p115). The two-branch scenario after the largest counter-reaction (WA p70). "chúng ta cần phải liên tục cập nhật thông tin mới" (WA p161). "chúng ta không thể thực sự biết đó là tích lũy hay phân phối" until cause and effect are complete (WA p167, `advance.md:502`).
- **Phase shading needs tested evidence: SUPPORTED.** method.md A4: an untested phase call "is a hypothesis, and must be reported as one" (`method.md:55`). WA p166 warns against labelling mechanically (`advance.md:488-500`, WA2-39 `:1110`). WA p77 says textbook-clean structures are rare (`advance.md:313`).
- **"Only TR borders + clear events": CONTRADICTED as an absolute.** Every worked example in the book labels the event sequence *and* the phases on the chart (WA p87–100, §2.11), and the book says labelling Phase C is the point of the method ("với phương pháp Wyckoff việc gắn nhãn và hiểu những giai đoạn rất quan trọng và đặc biệt là Phase C", WA p77). The right fix is to mark labels as hypotheses, not to hide them.

### (b) Current behaviour
- The schema has no `alternative` field and no per-band evidence status (`narrative.schema.json:31`). `phase_grammar` checks order, membership and presence (`check-narrative.py:47-118`) but not whether the đối nhãn tests passed.
- `chart.js` draws every band at the same weight (`alpha:0.07`, `scripts/chart.js:220-221`) and every flag the same way (`:224`). A hypothesis band and a tested band look identical.

### (c) Proposal
- **P6.1 (narrative contract).** `wyckoff.alternative` is **required**: a short cited paragraph naming the competing reading and the price/volume behaviour that would decide between them (WA2-27). For this read it would have been: "ST dưới SC → có thể là phân phối / tái phân phối (WA p150); phá đáy 4,289.57 và giữ dưới = Shakeout hoặc MSOW, không phải Spring".
- **P6.2 (per-band status).** Each `phases[]` item gets `status: "tested" | "hypothesis"`. `tested` requires the band's own event checks to pass (P1.1, P2.1, P3.1 and the Dấu hiệu fields). Anything else is `hypothesis`. `chart.js` draws hypothesis bands with a dashed outline, lower fill, and a `?` suffix on the band letter (`C?`, `D?`), following the book's own "?" usage (WA p93, p161).
- **Version significance:** display plus narrative contract, not TS-version significant. P6.2 feeds `wyckoff_bias` only if the bias rule is changed to ignore hypothesis bands, which is a separate, TS-significant decision to be taken explicitly.

---

## 7. How to render a label whose invalidation has already fired

**Constraint (CLAUDE.md §8, §17, §37):** the label was valid at `updated = 2026-09-11T15:00Z` and must not be rewritten. "Original expectations are immutable … The actual path must never rewrite the original expectation" (§17). But a label drawn today must not claim to be current.

**P7.1: Derive the invalidation time and never store it in the narrative.** The scanner already computes, per anchor, the first **completed** close beyond the level after the anchor time. It never counts the forming candle (`scripts/ict-scan.py:249-270`, `ref_i = n-2`, "never let the forming candle 'confirm' a break"). For the narrative's `invalidation.level` and its rule direction, take `invalidated_at` = the first completed close beyond that level with time > `updated`. For XAUUSD that gives `2026-09-15T23:45Z`, close 4,283.38 (`prelim/cfd-scalping.facts.json`). The narrative file stays untouched. The status is derived at build time from the facts, so it is point-in-time and reproducible.

**P7.2: Rendering rules once `invalidated_at` exists:**
1. **Truncate, don't extend.** TR lines, phase bands and Wyckoff anchor lines currently run to the right edge (`i2:null`, `chart.js:222, 233`). That drawing itself says "still in force". Set their right end to `idxOf(rows, invalidated_at)` so the structure is drawn only over the period it was valid.
2. **Fade and mark historical.** Draw every overlay from that narrative's Wyckoff read (events, bands, TR, Wyckoff-method anchors) at reduced alpha in the muted colour, with the label suffix `· hết hiệu lực <dd/mm HH:MM>` / `· invalidated <date>`. Keep the original text unchanged before the suffix, so the original label survives.
3. **Mark the break.** Put an `x` mark on the invalidating candle at the level, labelled `Vô hiệu: đóng 4,283.38 < Spring 4,289.57`, reusing the anchor `swept` glyph style (`chart.js:207`). Relabel the invalidation line from "Vô hiệu · wyckoff 4289.57" to "đã kích hoạt 15/09 23:45" and truncate it at the break.
4. **Out-of-window case, which applies today.** The events and bands are already off-window, but the anchor and TR lines still run across the chart. After (1) they stop at `invalidated_at`. If that is also before the window, nothing from the dead read is drawn on the entry chart. A single muted note in the Wyckoff lane replaces it: "Phân tích 11/09 hết hiệu lực 15/09 — chờ phân tích lại".
5. **Replay stays point-in-time.** `chart.js:469` already filters events and bands by the replay cursor. With the cursor before `invalidated_at`, draw normally. At or after it, apply (1)–(3). A reader replaying 09-11 therefore sees what the system saw then.
6. **Matrix cell.** In `build-artifact.py:730-736`, render the layer-3 verdict chip of an invalidated narrative as the historical verdict: struck-through chip plus "đã vô hiệu 15/09 23:45". Show the phase/structure badges (`:708-712`) as "(11/09, hết hiệu lực)". The current state comes from the scanner (`verdict_of(l1, l2)`, `:1537`), which already says PHÁ DƯỚI.

**P7.3: Checker/automation.** No change to `check-narrative.py` for old narratives: they are historical records. The scanner's "cần phân tích lại" should queue a new full analysis. That is an automation decision and out of scope for this review.

**P7.4: Bias integrity (the only decision-affecting part).** `wyckoff_bias` (`scripts/htf_context.py:224-272`) should return `unknown` with a basis such as `bias.wy.invalidated` when the context read's `trading_range` border has been closed beyond (for accumulation, a completed close below `trading_range.low`) after the read's `updated`. Today it would return `long` from a structure whose 4H TR low 4,285.91 is already below price (4,261.60), and only ICT-only engagement hides this.

**Version significance of §7:** P7.1–P7.3 are display only and **not** TS-version significant; record them in an ADR as the rendering rule for invalidated analyses. P7.4 changes the bias gate and is **TS-version significant** for any preset or backtest that engages Wyckoff (`live_rules.bias_at`, `backtest-methods.py:494-498`).

---

## 8. Summary table

| # | Critique | Verdict | Proposed change | TS-version significant? |
|---|---|---|---|---|
| 1 | Spring invalid; needs HTF accumulation + close inside + Test | Invalidation SUPPORTED (post-write); HTF precondition NOT IN THE BOOK; close-inside SUPPORTED; Test PARTLY (confirmation, not naming); "shakeout" usage CONTRADICTED | P1.1 dual typing + Dấu hiệu 1 + Spring-bar/TR check; P1.2 context Spring must breach context TR | Methodology-interpretation (§59); no live effect (Wyckoff engaged nowhere) |
| 2 | SOS too early | PARTLY: spread/volume/commitment SUPPORTED; "close near bar high" NOT IN THE BOOK | P2.1 narrative SOS = R11 test incl. `commitment_bars`; candidate `SOS?` otherwise | As P1; aligns narrative with existing backtest rule |
| 3 | LPS "đang test" is not LPS | SUPPORTED (WA p84–85; book's own "?" notation WA p93/p161) | P3.1 `?` grammar for unconfirmed LPS/BU/Test/SOS; a `?` event cannot open a phase | As P1 |
| 4 | 15m A–D forced; 4H vs 15m → −50% | 15m illegitimate CONTRADICTED (WA p87–89, p60); HTF-first SUPPORTED; −50% NOT IN THE BOOK | P4.1 declare HTF Wyckoff-vs-ICT Contradiction; P4.2 `nesting` field; P4.3 = P7.4 | Yes for Wyckoff-engaging TS (bias gate) |
| 5 | Tick volume unreliable | PARTLY: book flags tick *Delta* (WMT p131–133); plain-volume extension is project policy | P5.1 no volume-as-sole-validator on tick feeds, tick marker on every ratio; no new weight number | No (Wyckoff unscored on CFD) |
| 6 | Only TR + clear events; no unsupported shading; always alternative | PARTLY: alternative + hypothesis marking SUPPORTED; "only TR" CONTRADICTED | P6.1 required `alternative`; P6.2 `tested`/`hypothesis` band status, drawn dashed with `?` | No (display/contract) |
| — | Rendering an invalidated label | — | P7.1 derive `invalidated_at` from facts; P7.2 truncate + fade + mark, replay-aware; P7.4 bias ignores invalidated structures | P7.1–7.3 no; P7.4 yes |

## 9. Not verified in this review
- The 09-11 candles (Spring/SOS/commitment bars) could not be re-read. The snapshot `local-eval-gold-20260911T150202Z` is not in the working tree, the MT5 15m file starts 2026-09-15T15:45Z, and git history was out of scope. Spring bar values, SOS commitment and LPS volumes are taken from the narrative's own text.
- The rendered page was not opened. The "what is drawn today" in §0 is derived from `chart.js`/`build-artifact.py` logic plus the current data window, not from a screenshot.
- Whether the book's XAUUSD/FX worked examples used tick volume is not stated in `knowledge/wyckoff/advance.md`.
