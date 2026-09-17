# Audit of `knowledge/09-wyckoff-ict-mapping.md` (216 lines)

> **Knowledge-path note (added 2026-09-17).** The `knowledge/` citations below use the FLAT numbered
> layout (`knowledge/07-wyckoff-advance.md`, or the `kNN` short codes) that was retired on 2026-09-17 in
> favour of one folder per methodology. They are left exactly as written: this document is a dated record,
> and re-pointing its citations would change what it says it checked. `knowledge/INDEX.md` carries the
> old→new map.

Verification date: 2026-09-11. Every evidence line below comes from an actual `grep`/`sed` read of the cited file in this repo. Nothing is cited from memory.

Legend: **CORRECT** = citation resolves and says what 09 claims. **STALE** = true when written, superseded by the k07 rebuild (2026-09-10) or by the downstream decisions recorded in `knowledge/10 §7`. **WRONG** = does not match the source as written. **UNVERIFIABLE** = no source reachable.

---

## A. Header / scope claims (lines 1–12)

| Claim | Line | Verdict | Evidence | Suggested correction |
|---|---|---|---|---|
| Grep-verified absent from k04–k06: "BOS", "Break of Structure", "CHOCH", "ChoCh", "Change of Character", "BMS" | 12 | **CORRECT** | `grep -ioc` over `knowledge/04-ttrades-core-A.md`, `05-ttrades-core-B.md`, `06-ttrades-models.md` → **0 lines for all six tokens in all three files** (18/18 zero) | none |
| k07 rebuilt to pp. 4–56 and 59–293 of 294 | 10, 195 | **CORRECT** | `knowledge/07-wyckoff-advance.md:17` — "Photographed and extracted pages: **4–56 and 59–293** (288 of 294 pages)" | none |
| PHẦN 3 map: absorption `k07 §3.2`, urgent demand `§3.3`, CO plan `§3.4` | 195 | **CORRECT** | `07:555`, `07:578`, `07:591` — headers match verbatim | none |
| PHẦN 4 map: Bar-by-Bar `§4.1`, Analog `§4.2`, Swing `§4.3–§4.4`, VP `§4.5`, SOT `§4.6` | 195 | **CORRECT** | `07:682`, `07:780`, `07:813`, `07:833`, `07:856`, `07:936` | none |
| Vietnamese event names taken verbatim from `WA p8` glossary via `k07 §1.3` | 11 | **CORRECT** | `07:66–92` glossary table; every VN name used in rows 1–20, 28, 35 matches character-for-character (PS *Nguồn cầu sơ bộ*, SC *Cao trào bán*, AR *Điểm phục hồi tự nhiên*, LPS *Điểm kiểm tra nguồn cầu*, LPSY *Điểm kiểm tra nguồn cung*, TR *Vùng giao dịch*, CO *Người tạo lập thị trường*, UA *Bẫy tăng giá trong tích lũy và tái tích lũy*) | none |
| Row count "58 (35 in 1A, 23 in 1B)" | 86 | **CORRECT** | `grep -c "^\| [0-9]\+ \|" 09 → 58`; 1A = rows 1–35, 1B = rows 36–58 | none |

---

## B. Section 1A — Wyckoff → ICT (rows 1–35, lines 22–56)

### B1. Rows verified CORRECT on both sides

| Row | Line | What was checked | Evidence |
|---|---|---|---|
| 1 PS | 22 | `k05 §3.1 R1` (`18. MSS p5`), `k04 §2.13` | `05:145` R1 "require a **higher-timeframe level to be engaged first**. `18. MSS p5 (3)`"; `04:111` §2.13 "Swing points … used as a draw on liquidity or … frame a reversal" |
| 3 SC | 24 | `k04 §2.6 (3. Liquidity p4)`, `k05 §2.13 (IRL-ERL p4)`, `k05 §2.11 (22. PO3 p4)` | `04:68`, `05:123` ("ERL = swing highs … swing lows", p4), `05:107` (AMD boxes, `22. PO3 p4 (2)`) |
| 5 AR | 26 | displacement "generally has FVG present"; `k01 §3.4 R13`, `R24` | `04:124` §2.16 verbatim; `01:169` R13 "lows of SC/ST = support, high of AR = resistance"; `01:187` R24 |
| 6 ST | 27 | `k05 §2.5 (17. OB p3)`, `k04 §2.23 (12. FVG p6)`, `k04 §2.26` CE hold/fail, `k01 §3.4 R14` | `05:58`, `04:166`, `04:178`, `01:170` R14 "narrowing spread and lower volume" |
| 7 ST[B] as UT | 28 | `k04 §2.14 (6. IB p6)`, `§2.17 (11. MSS_vs_LG p5)`, `k01 §3.5 R25`, `k05 §3.1 R3` | `04:115`, `04:130`, `01:189` R25 "ST pushes above BCLX and closes back below → UT (ST[B]) → expect a test of the TR lower boundary", `05:147` R3 |
| 8 Test | 29 | `k01 §3.4 R17` low-volume test; `k05 §3.3 R10` | `01:173` R17; `05:158` R10 |
| 9 Spring | 30 | Spring types 1/2/3 in `k08 §2.6` Bảng 2.1 `WMT p049`; `k04 §2.17`; `k06 §2.9 (TTRS p13)` | `08:50–59` — table with Type 1 low / Type 2 moderate / Type 3 "Shake Out" high, "(Table per Bảng 2.1, WMT p049)"; `06:240` TTRS p13 "turtle soup" |
| 10 Shakeout, mapping to bearish MSS | 31 | `k01 §4.3`; `k04 §2.17`; `k04 §3.6 R25` | `01:232` §4.3 "Spring vs Shakeout `[P1 p24]`"; `01:171` R15 "IF most candles close below the TR low … Shakeout"; `04:225` R25 verbatim "invalidated if a later candle **body-closes** beyond the same level (that would convert the grab into an MSS)" |
| 11 UA, 15 MSOS, 17 MSOW | 32, 36, 38 | `k01 §6 item 9` "never defined in text" | `01:311` item 9 — "MSOS / MSOW / UA / JAC / BUEC / BMS never defined in text" |
| 14 SOS | 35 | `k01 §3.4 R18`; `k05 §2.2 (18. MSS p4)` | `01:174` R18 "commit for a period above the TR high with spread and volume rising steadily"; `05:36–39` |
| 16 SOW | 37 | `k01 §3.5 R29`; MSS reference swing per `k04 §6 item 12`, `k05 §6 item 5` | `01:191` R29; `04:317` item 12; `05:233` item 5 — both "swing low **immediately preceding** the raid leg" |
| 18 LPS | 39 | two LPS types; `k01 §3.4 R19` declining supply volume; OB 0.5 / CE 0.5 / OTE 0.62–0.79 | `01:304` item 4 confirms two types; `01:175` R19; `05:64` mean threshold; `04:178`; `04:150` |
| 19 BU/JAC | 40 | `k04 §2.25 (12. FVG p8; 13. Inversion p4–p8)`; breaker requires prior sweep; `k01 §3.4 R23`; `k05 §3.4 R20` | `04:173–175` matches page list exactly; `05:73–81` breaker construction Low→High→Lower Low→HH; `01:179` R23 "SOS high acts as AR … of the following re-accumulation range"; `05:170` R20 |
| 20 LPSY | 41 | `k01 §3.5 R28` "feeble narrow-spread rally"; `k01 §3.5 R27` "safer to wait for Phase D and an LPSY confirmation" | `01:190` R28, `01:189` R27 — both verbatim |
| 23 Phase A / PO3 false friend | 44 | PO3 "Accumulation" = ranging around the open | `05:108` — "**Accumulation** (green) = ranging around the open" |
| 24 Phase B | 45 | economic-calendar anticipation `k06 §2.5.1, Model11 p61–p62` | `06:133` — "'The economic calendar is the foundation to anticipating market conditions…' — `Model11 p61–p62`" |
| 26 Phase D / "distribution" collision | 47 | PO3 "Distribution" = "the expansion in the true direction" | `05:108` verbatim |
| 28 Trading Range | 49 | `k08 §2.4 (WMT p023–p026)` fractal + 70–80% citing Dalton; `k04 §2.18 (8. D&P p3)` quote; swing = 3-candle wick | `08:42–43`; `04:136` "look for where sell side and buyside liquidity is resting"; `04:64` §2.5 |
| 29, 30 TR boundaries | 50–51 | `k01 §6 item 7` SSL printing error | `01:309` item 7 — "`[P2 p29]` lists 'OLD High (Swing Low)'; the diagram says 'OLD LOW'" |
| 35 CO | 56 | `k05 §2.10 (21. SMT)` is the only "SM" trace | `05:96–104` — SMT deck has no actor definition |

### B2. Rows with defects

| Claim | Line | Verdict | Evidence | Suggested correction |
|---|---|---|---|---|
| Row 13 — "UTAD … = Upthrust **type 2** in `k08 §2.7`" stated as an equality | 34 | **STALE** | `08:63–69` does label Type 2 = UTAD, BUT `07:1707` (k07 §8, "Upthrust naming" row) marks the two taxonomies **CONFLICTING/different**: "WA splits by structure type (UA vs UT) and phase bracket; 08 splits by volume/reaction strength. **Not resolved**" | Replace "=" with "≈, unresolved": "`k08 §2.7` labels its Upthrust type 2 'UTAD'; `k07 §8` records this as an unresolved taxonomy conflict with the classic UTAD[C] of `k07 §2.8.3` (WA p106) — do not merge." |
| Rows 12 & 13 cite `k06 §3.4 **step 1**` for the sweep; row 25 cites `k06 §3.4 **step 2**` for the same object | 33, 34, 46 | **WRONG** (internally inconsistent) | `06:328–336` — §3.4's numbered list: item 1 = "Context: trade inside a killzone…", item **2** = "Step 1 turtle soup: a prior low (longs) is swept". So "step 1" resolves to the killzone item, not the sweep | Use one convention. Recommend citing the deck page: "`k06 §3.4` item 2 (TTRS p13, 'Step 1 turtle soup')" in rows 12, 13 and 25. |
| Row 21 CHoBEV — Wyckoff side cited as "`PHẦN 2 §1` at `WA p67–71` per `k07 §1.2`" (the table-of-contents section) | 42 | **STALE** | Body now exists: `07:267` "### 2.6 PHẦN 2 §1 — Thay đổi hành vi (CHoBEV) / Thay đổi đặc tính (CHoCH) (WA p67–71)"; `07:275` gives the three criteria verbatim — "phản ứng chống lại xu hướng hiện tại. Mức chênh lệch tăng, nỗ lực tăng trên phản ứng đảo chiều" (WA p68), which **confirms 09's substantive description** | Change citation to `k07 §2.6 (WA p67–71)`; keep `k01 §2.5` as the secondary. |
| Row 22 CHoCH — cites `k07 §1.2`; describes Wyckoff ChoCh only as "a series of behaviour changes" | 43 | **STALE** | `07:279` (WA p68) quantifies it: "**Thay đổi đặc tính (CHoCH): bao gồm ba lần thay đổi hành vi (CHoBEV)**"; restated `07:281` as "3CHoBEV=ChoCH" (WA p125). Enforced downstream at `.claude/skills/wyckoff-skill/SKILL.md:18` ("Three CHoBEV make a CHoCH") | Cite `k07 §2.6 (WA p68)` and state the count: "exactly three CHoBEV". This is the sharpest available contrast with the SMC single-event CHoCH and strengthens the row's argument. |
| Row 31 Reaccumulation — cites `k07 §1.2 (PHẦN 2 §4, WA pp.124–141)` | 52 | **STALE** | Body: `07:422` "### 2.9 PHẦN 2 §4 — Tái tích lũy [re-accumulation] (WA p124–141)"; `07:1737` (k07 §8) adds 4 sub-types NEW in k07 | Cite `k07 §2.9`; note the four re-accumulation sub-types (WA p126–141) which have no ICT analogue at all. |
| Row 32 Redistribution — cites `k07 §1.2 (PHẦN 2 §5)` | 53 | **STALE** | `07:443` "### 2.10 PHẦN 2 §5 — Tái phân phối (WA p142–149)" | Cite `k07 §2.10`. |
| Row 33 "Volume as effort" — Wyckoff side cites only `k01 §2.1/§4.1` and `k08 §2.1` | 54 | **STALE** (incomplete) | `07:171` "#### 2.2.3 Quy luật nỗ lực – kết quả [Law of Effort vs. Result] (WA p33–39)" | Add `k07 §2.2.3 (WA p33–39)`. The NO-EQUIVALENT verdict is unaffected and becomes better sourced. |
| Row 34 SOT — "the deeper SOT material sits in WA PHẦN 4 §6 (p277), which `k07 §1.1` marks **not covered**" | 55 | **WRONG** | `07:936` "### 4.6 PHẦN 4 §6 — SOT (WA p277–292)" — fully extracted (def. WA p278, push count WA p280/p284, two momentum-loss forms WA p292, location rules WA p284–286). `07:1718` states explicitly: "**Superseded within this file:** SOT *is* fully covered at §4.6 (WA p277–292)" | Delete the "not covered" note. Replace with: "`k07 §4.6` (WA p277–292) develops SOT fully: minimum 3 pushes, 3–4 the useful window, >4 means the trend is too strong to oppose (WA p280, p284); two forms — phân kỳ (volume up) and kiệt sức (volume down) (WA p292); and an explicit location rule (SOT at a TR boundary > SOT mid-range, WA p285). None of this has an ICT analogue, which strengthens the RELATED-BUT-DISTINCT verdict." |
| Row 28 — "markets range 70–80% of the time (citing Dalton); `k01 §2.3` gives 70%" | 49 | **STALE** (incomplete) | `07:203` (WA p40–41) "**củng cố ≈ 70%** of market time, **trending ≈ 30%**"; `07:1671` flags "70% flat vs 70–80% band. Not resolved" | Add `k07 §2.3 (WA p41)` and the unresolved-conflict note from `k07 §8`. |
| Row 20 — LPSY preference rule attributed only to `k01 §3.5 R27` | 41 | **STALE** (incomplete) | `07:1727` (k07 §8) — "WA p106: 'thường an toàn hơn nếu đợi đến Phase D và xác nhận LPSY'; but WA p176/p179 endorse shorts at UTAD[C]" | Add `k07 §2.8.3 (WA p106)` and note k07 itself is internally split (WA p176/p179). |

---

## C. Section 1B — ICT → Wyckoff (rows 36–58, lines 62–84)

### C1. Rows verified CORRECT

| Row | Line | What was checked | Evidence |
|---|---|---|---|
| 36 sweep/grab | 62 | `k01 §6 item 11` decks never reconciled | `01:313` item 11 verbatim |
| 37 BSL/SSL | 63 | `k04 §6 item 8` "relatively equal" has no tolerance | `04:313` item 8 — "**'Relatively equal' has no tolerance**" |
| 38 MSS | 64 | MSS reference swing `k04 §6 item 12`, `k05 §6 item 5` | `04:317`, `05:233` |
| 41 CISD | 67 | `k05 §2.3`, `§3.2 R5`, `k06 §2.3 (Model11 p44)`; caveat `k05 §6 item 1` two line placements | `05:46–49`; `05:150` R5; `06:104` "confirmed by a lower timeframe change in state of delivery (CISD) within candle 2 … `Model11 p44`"; `05:231` item 1 verbatim |
| 42 Displacement | 68 | `k01 §4.1` "widening up bars + declining volume ⇒ divergence" | `01:161` R4 — "IF up-thrust widens with declining volume THEN divergence" |
| 43 OB | 69 | `k05 §6 item 2` OB is line in CISD decks, body zone on mean-threshold slide | `05:232` item 2 verbatim |
| 44 Breaker | 70 | `k05 §2.7` sweep precondition; `k05 §6 item 3` box bounds unspecified | `05:73–81`; `05:235` item 3 |
| 45 Mitigation | 71 | "`19. Breaker p6` vs `20. Mitigation p3`" | `05:92` — the exact same page pair is printed in k05 as the differentiator |
| 46 FVG/IFVG/CE — ICT side | 72 | `k04 §6 item 13` wick-based vs body-based; `item 14` CE two roles | `04:319`, `04:320` verbatim |
| 47 IRL/ERL | 73 | `k05 §2.13`, `§3.1 R3`; Wyckoff P&F 3 counts | `05:123–126`; `05:147`; `01:159` R2 "conservative / probable / aggressive" |
| 49 OTE | 75 | `k04 §6 item 17` OTE band is an inference; `item 18` stop not given; `k06 §2.9 (TTRS p9)` | `04:325`, `04:326`; `06:238` "OTE — `p9 (7)`… 0.62–0.79 is the OTE zone" |
| 50 Killzones | 76 | `k04 §6 items 1–3`; `k04 §2.9` session boundaries undefined | `04:307–309`; `04:95` "Session boundaries are **not defined** on the session slides" |
| 51 PO3 | 77 | `k05 §6 item 9` PO3 entry slide arrows only | `05:241` item 9 verbatim |
| 52 SMT | 78 | `k05 §3.5 R24` ratio-chart variant is "My Theory" | `05:177` R24 verbatim |
| 53 OSOK vs k08 §5 | 79 | `k06 §2.5, §3.1 (Model11 p60–p94)`; `k08 §5 (WMT p233–p279)` | `06:269` header prints `Model11 p60–p94`; `08:162–184` |
| 54 Fractal Model | 80 | pairing table W→H4, D→H1, H4→M15, H1→M5, M30→M3, M15→M1 | `06:106–113` — table matches exactly; `01:178` R22 confirms the Wyckoff side |
| 55 Sons | 81 | `k06 §6 item 7` entry element not labelled | `06:426` item 7 verbatim |
| 56 TTRS | 82 | "a progressively later confirmation/entry point on the same reversal"; `k06 §6 item 6` no stops/targets | `06:247` verbatim; `06:425` item 6 |
| 57 Unicorn | 83 | `k05 §2.8 (19. Breaker p17)`; `k06 §2.11` | `05:86` cites `19. Breaker p17 (15)` |
| 58 TFA | 84 | `k06 §2.8 TFA p5` pairing table identical to `Model11 p44`; `k06 §6 item 8` "Bias" ambiguity | `06:218`; `06:427` item 8 |
| 48 premium/discount RR argument | 74 | `k04 §2.19` longs in premium give RR<1 | `04:143` — "Long positions in **discount** … Discount → RR>1; Equilibrium → RR=1; Premium → RR<1" |

### C2. Rows with defects

| Claim | Line | Verdict | Evidence | Suggested correction |
|---|---|---|---|---|
| Row 39 BOS — "The only break-of-structure token in the ingested knowledge base is **BMS**, in `k01 §2.6, §4.7`, which `k01 §6 item 9` records is *never expanded in text*" | 65 | **STALE** | `07:205` — "**BMS [Break of Market Structure] (WA p42, p44).** Bullish structure: successively higher highs and higher lows, each swing high marked **BMS**…"; rule `07:1024` WA1-19; diagram `07:1261`. So BMS **is** expanded, in k07, with worked examples (USD/JPY, S&P 500, WTI, XAU/USD, WA p43–49, per `07:1664`) | Rewrite: "BMS is defined in `k07 §2.3` (WA p42, p44) as a continuation marker inside an HH/HL (or LH/LL) structure — `k07 §5.1 WA1-19`. `k01 §6 item 9`'s 'never expanded' applies to the `k01` decks only." Then the mapping option becomes BOS→BMS citing **`k07 §2.3`**, a far stronger source than `k01 §4.7`. |
| Row 39 — "`.claude/skills/ict-skill/SKILL.md` step 1 currently asks for 'the last confirmed structural break (MSS/BOS)'" | 65 | **STALE** | `.claude/skills/ict-skill/SKILL.md:18` now reads "Is the last confirmed structural break (**MSS**) …" — no BOS. Lines 41–48 add an "Unsourced tokens — do not use" section: ":48 — Do not use bare 'BOS'" | Delete the step-1 claim; replace with: "`ict-skill` already rejects both tokens (its 'Unsourced tokens' section, interim per `knowledge/10 §7` decision 7)." |
| Row 41 CISD — absence checked against "`k01`, `k07 §1.3` or `k08`" (glossary only) | 67 | **STALE** (basis), conclusion holds | Re-run against the whole rebuilt k07: `grep -ic "giá mở cửa" 07 → 0`. The nearest k07 per-candle reference is the **prior session close**, not an open: `07:673` (WA p218) "khoảng cách giá đóng cửa phiên trước đến giá cao nhất hoặc thấp nhất của phiên sau … **phạm vi thực**" | Keep NO EQUIVALENT; change the basis to "grep-verified across the full `k07` (0 occurrences of *giá mở cửa*); `k07 §3.6` (WA p218) references the prior session **close**, never a candle open." |
| Row 46 FVG — "Wyckoff (in `k01`, `k07 §1.3`, `k08`) has **no inefficiency/gap concept whatsoever**" | 72 | **WRONG** | `07:673` (`k07 §3.6`, WA p218–219) defines gaps explicitly: "**Khoảng trống được che phủ**" vs "**Khoảng trống không được che phủ**" (covered vs uncovered gap), alongside **phạm vi thực** (true range) and **mức chênh lệch** (spread), under headings BIẾN ĐỘNG GIÁ TRONG NGÀY (WA p219) / THANH NẾN (WA p220). Separately `07:223` (WA p51–52) defines *thời điểm giao dịch kém hiệu quả* (inefficient trading time) | Soften to RELATED BUT DISTINCT on the gap half: "`k07 §3.6` (WA p218–219) does define covered/uncovered **gaps** and true range at the session level. The ICT FVG is still distinct — a 3-candle wick-overlap failure used as an entry array — and the *inefficiency-as-tradeable-object* framing has no Wyckoff analogue. The 'no gap concept whatsoever' claim is retired." |
| Row 48 — VAH/VAL attributed to `k08` only | 74 | **STALE** | `07:873` (`k07 §4.5.3`, WA p259) defines the Value Area verbatim: "Vùng giá trị được xác định giữa … **VAH – Value Area High** và **VAL – Value Area Low** … thể hiện chính xác **68,2%** tổng khối lượng"; VPOC `07:890` (WA p262); HVN/LVN `07:895` (WA p264–265) | Add `k07 §4.5.3–§4.5.5 (WA p259–p265)` alongside `k08 §5 Step 4`. |

---

## D. Section 2 — Risk register (lines 94–147)

| Claim | Line | Verdict | Evidence | Suggested correction |
|---|---|---|---|---|
| Risk 1 (Spring ↔ SSL grab is one wick) | 94–97 | **CORRECT** | `01:170`–`01:171` (R15) and `04:130` (§2.17) describe the same excursion on the same candle; de-dup lever (volume typing) sourced at `08:50–59` | none |
| Risk 2 (SOS ⊂ MSS) | 99–102 | **CORRECT** | `01:174` R18 (time + rising volume) vs `04:222` R10 / `05:150` R4 (single body close, no time/volume) | none |
| Risk 3 (retest pile-up; Unicorn = breaker ∩ FVG at one price; OB+FVG confluence) | 104–107 | **CORRECT** | `05:86` (`19. Breaker p17`); `06:262` (`Unicorn p6`); `05:63` OB+FVG confluence item 4 | none |
| Risks 4, 5, 6, 7, 10, 11, 12 | 109–147 | **CORRECT** | Risk 6/7 rest on `05:108` (PO3 scoped to one period's open, "Distribution = expansion in the true direction"); Risk 10 rests on the 0-hit grep in §A; Risk 11 on `05:123` (ERL = swing low) vs `01:169` R13; Risk 12 on `01:178` R22 + `06:104` (both are the same zoom) | none |
| Risk 8 — "step 4 of the current `wyckoff-skill/SKILL.md`" (tick-volume caveat) | 131 | **WRONG** | `.claude/skills/wyckoff-skill/SKILL.md:39` — the tick-volume rule is in **"## Data-source rules"**, not step 4. Step 4 (`:21`) is the "Phase A→E event walk". The credit multiplier is at `:59` (`project_defined.tick_volume_credit_multiplier`) | Cite "`wyckoff-skill/SKILL.md` 'Data-source rules' (`:39`) and `analysis-params.json` → `project_defined.tick_volume_credit_multiplier`". |
| Risk 8 — `SYSTEM-DESIGN.md §3` MT5 tick volume | 131 | **CORRECT** | `docs/architecture/SYSTEM-DESIGN.md:53` "## 3. Data Source Layer"; `:114` confirms "The volume component is **reduced on tick-volume feeds** (MT5 bridge)" | none |
| Risk 9 — the contradiction, and "No source file resolves this" | 133–135 | **STALE** | The ICT half is exact (`04:225` R25). But the Wyckoff half now has a source rule: `07:1083` **WA2-12** — "IF most candles of the break close BELOW the lower border and price lingers there forming its own value area, THEN label **Shakeout** (supply remains), not Spring; expect a longer test and prefer **dropping timeframe** to find a local Spring[C]/LPS[C] (WA p80, p83, p93–94)". `07:336` (WA p83) gives the discriminator; `07:1712` records WA p83 vs WMT p049 as CONFLICTING. And the project decision exists: `knowledge/10:206` decision 3 — "Keep raising it as a Contradiction and log every occurrence" | Rewrite the handling rule: "`k07 §2.7.3` (WA p83) discriminates Spring from Shakeout by *time spent outside the range + whether a separate value area forms*, not by close count — and k07's Shakeout means **supply remains**, which narrows (not eliminates) the gap to ICT's bearish read. `k07 §5.2 WA2-12` prescribes dropping a timeframe to find a local Spring[C]/LPS[C] rather than trading the Shakeout directly. Project decision (`knowledge/10 §7` #3): raise as Contradiction and log `shakeout_vs_displacement`." |
| Risk 9 — `SYSTEM-DESIGN.md §6.2` "opposing HTF structure penalty" | 135 | **CORRECT** | `SYSTEM-DESIGN.md:107` — "major opposing HTF structure (−15)" | none |
| Header claim — `SYSTEM-DESIGN.md §6.1` "Independent-Confluence Check" | 5 | **CORRECT** | `SYSTEM-DESIGN.md:92` — "### 6.1 Independent-Confluence Check" | none |

---

## E. Section 3 — Independent-confirmation list (lines 153–161)

| Claim | Line | Verdict | Evidence | Suggested correction |
|---|---|---|---|---|
| item 1 SMT | 153 | **CORRECT** | `05:96–104`; `05:177` R24 "My Theory" | none |
| item 2 time-axis | 154 | **CORRECT** | `04:33–40`; `06:130–147`; no time-of-day token found in `k01`/`k08`, and `grep -i "killzone\|phiên London\|phiên New York\|time of day" 07 → 0 hits` | optional: add "and none in `k07` (grep-verified)" — strengthens the claim |
| item 3 effort vs geometry | 155 | **STALE** (incomplete) | `07:171` `k07 §2.2.3` (WA p33–39) also measures volume | add `k07 §2.2.3` |
| item 4 calendar-derived levels | 156 | **CORRECT** | `04:80–86` §2.8; `01:171–172` R10/R11 | none |
| item 5 two targeting methods | 157 | **CORRECT** | `01:159` R2 (3 P&F counts); `08:182` (WMT p273, Market-Profile 80% rule, explicitly citing Dalton); `05:166–169` R16–R19; `05:169` R19 endorses PD-array pairing verbatim | none |
| item 6 VAH/VAL vs EQ | 158 | **STALE** ×2 | (a) VAH/VAL also in `07:873` (`k07 §4.5.3`, WA p259, 68.2%); (b) "see §5 for the unresolved question of which dimension should own VAH/VAL" — resolved: `knowledge/10:204` decision 1, "**Wyckoff owns it**", enforced at `wyckoff-skill/SKILL.md:30` and removed from `ict-skill` (`ict-skill/SKILL.md:22`) | cite `k07 §4.5.3` too; replace the "unresolved" pointer with the decision |
| item 7 CISD as trigger | 159 | **CORRECT** | `05:46`; `06:104` pairing table | none |
| items 8, 9 | 160–161 | **CORRECT** | `01:189` R25; `05:147` R3 | none |

---

## F. Section 4 — Sequencing / precedence (lines 169–189)

| Claim | Line | Verdict | Evidence | Suggested correction |
|---|---|---|---|---|
| item 1 — `k08 §5 Step 1 (WMT p233–p236)` prescribes zoom-out then local range; `k08 §2.5 (WMT p236)` hardest-call caveat | 169 | **CORRECT** | `08:166`; `08:47` — "(WMT p236)" verbatim | none |
| item 2 — `k08 §5 Step 2 (WMT p236–p238)` | 170 | **CORRECT** | `08:169` verbatim | none |
| item 3 — `k05 §3.1 R1` quote | 171 | **CORRECT** | `05:39` — "It is important that a higher time frame level is engaged prior to the lower time frame market structure shift." verbatim | none |
| item 4 — ICT sub-levels | 172 | **CORRECT** | `05:64` mean threshold; `04:166`/`04:178`; `05:73`; `04:150`; `01:204` R37 | none |
| item 5 — `k08 §5 Step 4` abandon rule; "the strongest thesis-invalidation statement **in either tradition**" | 173 | **STALE** (2nd half) | The rule itself is exact (`08:175` — "**abandon the Spring/Upthrust plan**"). But k07 now supplies a competing Wyckoff invalidation: `07:513` "#### 2.11.7 Sự thất bại về mặt duy trì cấu trúc [failure to maintain structure] (WA p181–183)", and `07:1745` (k07 §8) records: "08 §5 Step 4 gives a **different invalidation** … **Different invalidation logic; both may be used, not merged**" | Soften: "…the strongest *volume-derived* invalidation. `k07 §2.11.7` (WA p181–183) gives an independent structural one (failure to maintain structure); `k07 §8` says the two must not be merged." |
| item 6 — quote "wait for an intraday CISD to be established before attempting to get onside" attributed to `k06 §2.5.7` | 174 | **WRONG** (section) | The quote is real but lives in the worked example: `06:199` — "…wait for an intraday CISD to be established before attempting to get onside with the expansion." — `p102–p103`; repeated `06:202` (`p107–p110`). `k06 §2.5.7` (`06:172–180`, Model11 p89–p94) says instead "The daily profile will be aligned after an intraday CISD is established." The rule form is `k06 §3.1` item 19 (`06:305`) | Change the citation to "`k06 §2.7.1 (Model11 p102–p103)`, ruleised at `k06 §3.1` item 19". |
| item 6 — `k08 §5 Step 5` timing trigger is Footprint/Delta | 174 | **CORRECT** | `08:178` — exhaustion → absorption → development | none |
| Invalidation table, Wyckoff row (`k08 §5 Step 6 WMT p271`; `k08 §5 Step 4`; `k01 §3.7 R37`) | ~180 | **CORRECT but STALE (incomplete)** | `08:183` verbatim "below the lowest low of the Spring, or above the highest high of the Upthrust — placed so the stop only triggers on genuine pattern failure (WMT p271)". Missing: `07:1747` (k07 §8, "Stop placement") — "WA p96: stop 220.0 below the Shakeout/Spring low (one worked case); **no general rule**"; and `k07 §2.11.7` | Add a k07 column note: "k07 states no general stop rule (single worked case, WA p96) and adds a structural thesis-invalidation at `§2.11.7`." |
| Invalidation table, ICT row (`k04 §3.6 R22, R23`; `k05 §3.5 R21, R22`; `k06 §2.5.7 Model11 p90–p92`) | ~181 | **CORRECT** | `04:222` R22 (FVG far edge / OB low / originating swing low), `04:223` R23 (CE body close); `05:174–175` R21/R22; `06:176–177` (stop at candle-2 swing point, p90–p91) | none |
| "Only ICT's *wide* option ('below the raid swing low', `k05 §3.3 R10`) coincides with Wyckoff's" | 184 | **CORRECT** | `05:158` R10 — "Stop below the OB low (tight) or below the raid swing low (wide)" | none |
| Premium/discount vs Phase-D LPS conflict (`k04 §2.19`, `k01 §3.4 R19`) | 189 | **CORRECT** | `04:143`; `01:175` R19 | none |

---

## G. Section 5 — Open questions (lines 195–208)

**Structural finding:** `knowledge/09` was last written 2026-09-10 16:17; `knowledge/10-integrated-method.md` (16:59) records at `:196` that "**All nine open questions were put to the user and decided on 2026-09-10**". Nine of 09's fourteen §5 items are therefore superseded.

| Item | Line | Verdict | Evidence | Suggested correction |
|---|---|---|---|---|
| 1 — k07 incomplete, RESOLVED | 195 | **CORRECT** | `07:17`, `07:19` | none |
| 2 — "WA pp.57–58 are missing and WA p31's prose is illegible, **inside the auction-theory section**" | 196 | **WRONG** (partly) | pp. 57–58: correct — `07:214` "(WA p50–62; **pp. 57–58 missing**)". p31: **not** auction theory — `07:159` places p31 in "#### 2.2.2 Quy luật nguyên nhân – kết quả [Law of Cause and Effect] (WA p30–32)"; `07:25` lists p31 separately as partially legible | "WA pp.57–58 are missing inside PHẦN 1 §4 (auction theory); separately, WA p31's prose is illegible inside PHẦN 1 §2.2.2 (Law of Cause and Effect)." |
| 3 — UT vs UA, "**Human call**" | 197 | **STALE** | Decided: `knowledge/10:209` decision 6 — "**Adopt the book's phase-conditional rule** (WA p8)"; enforced `wyckoff-skill/SKILL.md:28` — "UT vs UA is phase-conditional and mandatory" | Mark RESOLVED 2026-09-10; point to `knowledge/10 §7` #6. |
| 4 — BOS/CHOCH, "**Human call**"; ict-skill "step 1 currently asks for (MSS/BOS)"; map BOS→BMS via `k01 §4.7` | 198 | **STALE** ×3 | (a) Decided: `knowledge/10:210` decision 7 — "Ingest a source that defines them. BLOCKED … Interim: keep rejecting both tokens"; (b) `ict-skill/SKILL.md:18` no longer says BOS, and `:41–48` is an explicit rejection section; (c) the better BMS source is now `07:205` (`k07 §2.3`, WA p42/p44), not `k01 §4.7` | Mark RESOLVED-but-BLOCKED-on-source; correct the skill claim; retarget the BOS→BMS option at `k07 §2.3`. |
| 5 — "`k01 §6 item 11` leaves ChoCh vs BMS unreconciled … **Nothing downstream can reconcile them either**" | 199 | **STALE** | `k07` defines **both** in one book by one author: BMS at `07:205` (WA p42, p44 — continuation marker in an HH/HL structure) and CHoCH at `07:279` (WA p68 — three CHoBEV, a character change). That is an authorial separation: they are different objects, not competing names | "`k07 §2.3` and `k07 §2.6` define BMS and CHoCH side by side in one book: BMS = continuation break inside a trending structure; CHoCH = 3 CHoBEV marking a character change. The `k01 §6 item 11` non-reconciliation applies to the `k01` decks only." |
| 6 — "Two incompatible Spring taxonomies … **Human call on which is canonical**"; "`wyckoff-skill/SKILL.md` **step 3** uses `k08`'s types" | 200 | **WRONG** ×2 + STALE | (a) `wyckoff-skill/SKILL.md:20` step 3 is "**Market Regime**: TRENDING / RANGING / TRANSITIONAL / UNCLEAR". The typing is **step 7** (`:24`), which deliberately keeps two fields: `event_class` (k07 §2.7–2.8) and `volume_type` (k08 §2.6–2.7), with a `naming_conflict` field; (b) decided at `knowledge/10:208` decision 5. Also note it is now a **three**-way question: `07:1712` records WA p83 vs WMT p049 as an unresolved criterion conflict | Correct to "step 7"; mark RESOLVED (two structured fields, never collapsed); add the `k07 §8` WA p83 criterion as the third taxonomy. |
| 7 — Shakeout/bearish-MSS "has **no resolution in any ingested file**" | 201 | **STALE** | `07:1083` WA2-12 gives a handling rule (label Shakeout, drop timeframe, find local Spring[C]/LPS[C], WA p80/p83/p93–94); `07:336` (WA p83) gives the discriminator; `knowledge/10:206` decision 3 records the project handling | See Risk 9 correction above. |
| 8 — "Which dimension owns Volume Profile?" | 202 | **STALE** | `knowledge/10:204` decision 1 — "**Wyckoff owns it** … a **veto evaluated before scoring**"; `wyckoff-skill/SKILL.md:30` "this dimension owns it"; `ict-skill/SKILL.md:22` "This dimension does not own Volume Profile". The literal observation about `SYSTEM-DESIGN.md §6.2`'s bucket list is still true (`SYSTEM-DESIGN.md:113–114` does not name VP), but the question is answered. Also `k07 §4.5` covers VP from the same author | Mark RESOLVED; add `k07 §4.5` as a second source. |
| 9 — killzone applicability unresolved | 203 | **STALE** | `knowledge/10:207` decision 4 — project session model; `ict-skill/SKILL.md:20` — "use `docs/architecture/session-model.md`, not the raw killzone slides" | Mark RESOLVED at project level (sources still silent). |
| 10 — "**No numeric thresholds exist for the Wyckoff side**" | 204 | **WRONG** | `k07` supplies several, page-cited: CHoCH = **3** CHoBEV (`07:279`, WA p68); SOT minimum **3** pushes, **>4** too strong (`07:944`, WA p280/p284/p292); Value Area = **68.2%** (`07:873`, WA p259); ST[A] within **1/3** of the TR (`07:461`, WA p150–153). These are already operationalised: `docs/architecture/analysis-params.json` has a **`sourced`** block — `st_above_half_tr` 0.5 (WA p75, p88), `st_within_third_of_tr` 0.3333 (WA p150, p166), `sot_min_pushes` 3, `sot_useful_max_pushes` 4 (WA p280/p284/p292), `value_area_pct` 0.682 — beside a `project_defined` block | Rewrite: "`k01 §5` gives no thresholds, and the *qualitative* terms (large volume, narrow spread, period of commitment) remain unquantified in every source — those live in `analysis-params.json` → `project_defined`. But `k07` **does** print several sourced numbers (3 CHoBEV = CHoCH, SOT 3–4 pushes, VA 68.2%, ST within 1/3 of the TR), carried in `analysis-params.json` → `sourced`. Do not label those as project parameters." |
| 11 — range-boundary reconciliation, flagged `[not in knowledge/ — my inference]` | 205 | **CORRECT** | Honest self-flag; `04:64`/`04:68` confirm the ICT swing-derived construction, `01:169` R13 the event-derived one. Partially operationalised since: `wyckoff-skill/SKILL.md:19` now requires both boundary prices numerically | optional: note the skill already prints both numbers |
| 12 — k04–k06 contain no volume | 206 | **CORRECT** | consistent with the grep evidence in §A and with `SYSTEM-DESIGN.md:114` | none |
| 13 — OSOK vs six-step coexistence | 207 | **STALE** | `knowledge/10:211` decision 8 — "**The six-step method is the pipeline.**"; `ict-skill/SKILL.md:57–61` "Pipeline precedence (user decision 2026-09-10)" | Mark RESOLVED. |
| 14 — `k06 §6 item 6` no stops/targets | 208 | **CORRECT** | `06:425` item 6 verbatim | none |

---

## H. Downstream citation consistency (task item 5)

| Citing file | Line | Cites | Verdict | Evidence |
|---|---|---|---|---|
| `knowledge/10-integrated-method.md` | 40 | `k09` authoritative for correspondence + de-dup | **CORRECT** | matches 09's stated purpose (09:3–5) |
| `knowledge/10` | 85 | "`k09 §2` risk 9" for Shakeout | **CORRECT** | 09:133 Risk 9 exists and is the Shakeout/bearish-MSS item |
| `knowledge/10` | 119 | "the **twelve** double-counting risks" | **CORRECT** | 09:94–145 — Risks 1–12 |
| `knowledge/10` | 123 | "`k09` §1B and §3 item 3" for the no-volume finding | **CORRECT** | 09:58 (§1B) and 09:155 (§3 item 3 = "Effort … vs price geometry") |
| `knowledge/10` | 139 | "§4.3 De-duplication rules (condensed from `k09 §2`)" | **CORRECT** | 09 §2 is the risk register |
| `.claude/skills/ict-skill/SKILL.md` | 30 | "`knowledge/09` §3 item 3" | **CORRECT** | 09:155 |
| `ict-skill` | 45 | "Grep-verified absent … (`knowledge/09`, header)" + the six tokens | **CORRECT** | 09:12 lists exactly those six; independently re-verified 0 hits |
| `ict-skill` | 61 | "`knowledge/09` §5 item 13" for OSOK-vs-six-step | **CORRECT** | 09:207 is item 13 and is that question |
| `.claude/skills/wyckoff-skill/SKILL.md` | 43 | "`knowledge/09` §3 item 3, `knowledge/10` §4.1" | **CORRECT** | 09:155; `knowledge/10:121` §4.1 exists |

**No downstream file cites a non-existent section of 09.** The inconsistency runs the other way: 09 makes two stale claims *about* the skills — `ict-skill` "step 1 … (MSS/BOS)" (09:65, 09:198) and `wyckoff-skill` "step 3 uses k08's types" / "step 4" tick volume (09:200, 09:131) — none of which match the current skill files.

---

## Tally

| Verdict | Count |
|---|---|
| CORRECT | 74 |
| STALE | 21 |
| WRONG | 9 |
| UNVERIFIABLE | 0 |

**WRONG (9):** row 34 SOT "not covered"; row 46 FVG "no gap concept whatsoever"; `k06 §3.4 step N` numbering inconsistency (rows 12/13 vs 25); Risk 8 "wyckoff-skill step 4"; §4 item 6 "onside" quote attributed to `k06 §2.5.7`; §5 item 2 p31 located in auction theory; §5 item 6 "wyckoff-skill step 3"; §5 item 6 "Human call" (already decided); §5 item 10 "no numeric thresholds exist".

**No fabricated citations found.** Every `WA pNNN`, `WMT pNNN`, deck-page tag (`17. OB p3`, `Model11 p44`, `TTRS p13`, `19. Breaker p17`, `9. OTE p3–p9`, …), R-number and `§6 item N` reference in 09 that I checked resolves to real content that says what 09 claims. The document's citation hygiene is high; every defect above is either a citation that now points at a weaker source than the rebuilt `k07` offers, or a claim about downstream files that has aged out.
