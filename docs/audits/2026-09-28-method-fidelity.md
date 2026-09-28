# Method-fidelity audit: ICT + Wyckoff detection, parameters, staleness (2026-09-28)

**Type:** read-only audit. No code, config or data changed. No backtest, stability report, prop-search or automation run.
**Trigger:** the pre-registered prop-challenge search found 0 of 180 setups passing (very few signals, negative expectancy), and the owner reported that "the ICT and Wyckoff charts drawn earlier had many wrong places — drawn only from old data, not re-evaluated on the newest data".
**Reference:** ADR 0007. The source books in `knowledge/` are the reference. Code may extend them but may not alter them.
**Prior audits read first:** `docs/audits/2026-09-11-ict-entry-checklist-audit.md`, `docs/audits/2026-09-11-wyckoff-entry-checklist-audit.md`, `docs/audits/2026-09-19-knowledge-fidelity.md`, `docs/audits/2026-09-24-wyckoff-label-review.md`. Findings they recorded as fixed were re-checked in the current code (§0). They are not re-reported unless the fix is incomplete.
**Data rule honoured:** no market data on or after 2024-03-01 was read for performance. The recent live files under `data/live/` were read only to check staleness and update behaviour.

Deviation scale: **none** · **stricter** (fewer signals than the source) · **looser** (more) · **different** (another rule) · **missing** (the source has it, the code does not).
Every hypothesis in §4 uses only rules that exist in `knowledge/`. A threshold the source does not give stays a project parameter, and the report says so.

---

## 0. Status of earlier findings (re-verified in the current code)

| Earlier finding | Status now | Evidence |
|---|---|---|
| 09-19 #1 Upthrust typed with the Spring table | **Fixed** | `scripts/wyckoff_rules.py:109-135` has two tables. The side is passed through `detect_distributions` → `side="short"` (`:395`). |
| 09-19 #4 window edge used as "ERL" target | **Fixed** | Target order is −2σ, then the dealing-range edge, then refuse (`scripts/ict-scan.py:416-421, 430-435`). |
| 09-19 #6/#7 proxy Wyckoff engine | **Fixed (removed)** | `scripts/backtest-methods.py:735-740`. Only WYCKOFF-BOOK is left. |
| 09-19 #8 tick volume | **Declared, not refused** (as decided) | `volume_kind`, `scripts/wyckoff_rules.py:49-59`, `scripts/backtest-methods.py:777`. |
| 09-19 #9 đối nhãn thirds | **Fixed (recorded, not gating)** | `scripts/wyckoff_rules.py:254-255, 263, 283-287`. |
| 09-19 #10 Old Highs/Lows | **Fixed in the scanner, NOT in the chart** | Scanner: `scripts/ict-scan.py:182-183`. The chart is still different, see §3.2 C1. |
| 09-19 #11 dead flags `--ict-pd`/`--std-origin` | **Fixed** | The same defect class has come back with `range_touches` and `ict_target`, see §2.3. |
| 09-19 #12 HTF ICT bias without displacement | **Fixed** | `last_displaced_mss`, `scripts/ict-scan.py:313`, read at `scripts/htf_context.py:213`. |
| 09-19 #13 FVG-before-MSS rule / engine drift | **Fixed** | The ICT backtest now calls the live scanner (`scripts/backtest-methods.py:630-731`). The old `find_ict` is used only by COMBINED-BOOK (`:434-466`). |
| 09-19 §7 limit resting from the MSS bar | **Fixed** | `scripts/backtest-methods.py:703-708`. |
| 09-19 §10 Wyckoff look-ahead | **Fixed** by the per-window read | `scripts/backtest-methods.py:905-912`. |
| 09-24 P1.1–P6.2 narrative checker | **Implemented** in `scripts/check-narrative.py` | volume_type `:276-307`, doi_nhan `:321-343`, '?' grammar `:89, :204-210, :353-377`. |
| 09-24 P7.1/P7.2 invalidated-label rendering | **Implemented, but ineffective for crypto scalping** | `scripts/build-artifact.py:1050-1071`, `scripts/chart.js:236-320`. See §3.2 S5–S7. |
| 09-24 P7.4 bias ignores broken HTF TR | **Implemented for Phase C/D/E only** | `scripts/htf_context.py:250-260`. |
| 09-11 ICT B1–B3 PDH/PCH draw | **Implemented, on the wrong timeframe** | See §1.1 row I-10. |
| 09-11 ICT B6 "HTF level engaged before LTF MSS" | **Still missing** | See §1.1 row I-12. |
| 09-11 ICT L1 swing width | **Still 3 bars each side** (deck: 1) | `docs/architecture/analysis-params.json` `project_defined.ict.pivot_bars = 3`. |
| 09-11 ICT M5 CISD, P3 CE/Fill, P6 OB | **Computed, never used for a decision** | `scripts/ict-scan.py:229-230, 388-398`. Entry is always IOFED. |
| 09-11 ICT P10 Inversion, P7 Breaker, S1 candle-2 swing | **Still missing** | grep finds no detector. |
| 09-11 Wyckoff #10 partial Spring position, #15 unused sourced params | **Still missing** | `spring_low_volume_max_ratio`, `market_profile_80_rule`, `st_above_half_tr` and `same_level_tolerance_atr` have no reader in `scripts/*.py`. |

---

## 1. Detection fidelity

### 1.1 ICT (scanner `scripts/ict-scan.py`, shared by the backtest and the live runner through `scripts/live_rules.py`)

| # | Structure | Source says | Code does | Deviation | Likely effect |
|---|---|---|---|---|---|
| I-1 | Swing high/low | "a high with a lower high to the left and right". **One candle each side** (`knowledge/ict/core-a.md §2.5`, §4 table, §5 "Swing definition width 1 candle each side"). | `PIV` bars each side, default **3** (`ict-scan.py:62, 118-121`). The same in `chart.js:73` and `wyckoff_rules.py:73, 89-101`. | **stricter** (7-bar pivot) | Fewer swings, so fewer pools, fewer sweeps and fewer MSS levels. The MSS reference swing sits further from the raid (I-5). Every pivot is confirmed only 3 bars late, so a setup becomes visible later, which feeds the "limit already pierced" refusals (§4 H2). |
| I-2 | Liquidity pools (BSL/SSL) | Two types: Old Highs/Lows and Relatively Equal Highs/Lows (`core-a.md §2.7`). PDH/PDL, PWH/PWL, PMH/PML and session highs/lows are liquidity levels too (`§2.8-2.9`). | Equal pairs, plus every single pivot as "old" (`ict-scan.py:176-183`). PDH/PDL and PCH/PCL are computed (`:258-278`) but **never added to `pools`**, so they can never be swept, targeted or used as a dealing-range edge. Session highs/lows exist only in the chart (`chart.js`, `sess`). | **missing** (HTF and session levels as pools) | A sweep of PDH/PDL, a session high/low or an HTF swing is not a setup trigger unless it happens to coincide with a 7-bar pivot on the entry timeframe. |
| I-3 | Sweep vs close-through | Wick beyond with the body closing back = grab. A body close beyond = draw reached, continuation (`core-a.md §4`, `§3.2 R6-R7`). | A bar-by-bar walk stops at the first body close beyond, which is `closed_through` (`ict-scan.py:152-161`). | **none** (scanner) · **different** (chart, §3.2 C2) | — |
| I-4 | Displacement | "aggressive move with full-bodied candles … single or multiple candles … generally FVG present" (`core-a.md §2.16`). No numeric threshold (`§5`). | A single candle with body ≥ 0.6 × range and range ≥ 1.2 × window median, **or** a contiguous same-colour run ending at the break that holds such a candle or a same-direction FVG (`ict-scan.py:189-208`). | **faithful simplification**. The thresholds are project parameters. | The prior funnel shows 786/1119 BTC candidates dropped at "not complete" (displacement or FVG) (`2026-09-19-knowledge-fidelity.md §8`). The thresholds are the largest single numeric filter in the funnel. |
| I-5 | MSS | Displacement body close beyond the swing **immediately preceding the raid leg**. A stop raid before it is "preferred" (`core-a.md §2.17, §6 item 12`, `core-b.md §2.2, §6 item 5`). "It is important that a higher time frame level is engaged prior to the lower time frame MSS" (`core-b.md §2.2, §3.1 R1`). | A state machine over the 7-bar pivots. After a lower-low pivot (`bias=-1`), the first close above `lastH`. A non-displaced close is logged as a grab and the scan goes on (`ict-scan.py:215-246`). The stop raid is made **mandatory** (`setup_candidate`, `:366-372`). | **stricter** (raid mandatory; the swing is "last 7-bar pivot", not "the swing before the raid leg") | Because of I-1, `lastH` is often an older, higher swing than the deck's pre-raid swing. The MSS needs a larger move and fires later or never. |
| I-6 | FVG | A 3-candle wick-to-wick gap (`core-a.md §2.21`). "Generally displacement candle(s) have FVG present … use it as the entry array" (`§3.3 R12`). No minimum size. | Wick gaps, kept only if ≥ 0.6 × median range (`ict-scan.py:123-133`). `setup_candidate` takes the **latest** same-direction FVG after the sweep, `fv[-1]` (`:384-387`). That is not necessarily the FVG inside the displacement leg. | **different** (the FVG is chosen by recency, not by R12's displacement FVG) · **stricter** (size filter) | Entry can move to a later, shallower continuation FVG. That gives a smaller distance to target, a higher entry-in-range % (more R13 failures) and a lower planned R. |
| I-7 | Dealing range / premium-discount | "based off the range high to the range low … where sell side and buyside liquidity is resting" (`core-a.md §2.18`). Nearest swing high/low pair (`§3.4 R15`). The R13 diagram draws the stop at the range extreme behind the entry and the target at the opposite extreme (`§2.19` diagram reading, `§6 item 19`). | The nearest unswept, not-closed-through BSL above and SSL below the **last close of the detection bar**. Window extremes are the fallback (`ict-scan.py:252-257`). `pd_ok` is judged on the **entry** price inside that range (`:442-445`). | **faithful to R15's text**. **different** from the R13 diagram geometry, because the swept SSL (the stop-side extreme) is excluded from the range. | The prior funnel shows 270/1119 BTC and 167/836 XAU candidates dropped by R13 (`2026-09-19-knowledge-fidelity.md §8`). The range is re-framed around the post-displacement close, not around the setup's own sweep→draw leg. |
| I-8 | Entry | Three FVG entries: IOFED, CE and Fill (`core-a.md §2.23, R19`). Model11: opposing-candle / CISD entry, or candle-2 / candle-3 closure entries (`models.md §3.1 rules 19-21`). | Always IOFED, the near edge, as a LIMIT (`ict-scan.py:395, 424`). CE, Fill and OB are computed as `entry_models` / `ob` but unused. | **faithful subset** (R19 lets you pick one) | Neutral for count. IOFED fills most often and suffers the most adverse selection. |
| I-9 | Stop | FVG end / OB low / originating swing (`core-a.md R22`). Model11: the candle-2 swing point (`models.md §3.1 rule 22`). | The sweep extreme, `min(L[sweep..mss])`, with **no buffer** (`ict-scan.py:395, 424`). Wyckoff gets `STOP_BUFFER_PCT` (`backtest-methods.py:74, 841`). ICT does not. | **faithful** (the "Swing" option). The missing buffer is a project inconsistency. | A stop placed exactly at the wick extreme is touched by an equal-low retest. |
| I-10 | Bias (draw + structure) | "Is price more likely to reach for previous candle high or low?" The PCH/PCL of **H4/H1/M30/M15**, used to frame lower-timeframe price. The daily candle frames the daily bias, executed on H4 (`core-a.md §2.11-2.12, §3.2 R5-R9, §5 "Bias timeframes"`). | `ict_bias(facts)` reads `prev_candle`: the entry-TF **last bar vs the bar before it** (`ict-scan.py:274-278`), plus the last displaced MSS on the **same** timeframe (`htf_context.py:178-225`). The backtest **always** requires this same-TF bias to agree (`backtest-methods.py:649-651`), and so does the live runner (`scripts/strategy-runner.py` `ict_live_setups`, `bias_at … bias_allows`). | **different** (the deck's unit is the previous **higher-timeframe** candle; the code uses the previous **entry-timeframe** bar). The project's own brief also says "Không bao giờ tạo bias từ khung vào lệnh" (`scripts/local-eval-brief.py:138`). | A 1-bar-lookback gate on the 15m chart is close to a coin flip at the detection bar, and it defers the setup. A deferred setup is then more often refused as "already triggered" (H1, H2). Prior funnel: 7/23 (BTC) and 7/20 (XAU) complete setups were refused by this bias. |
| I-11 | HTF gate | See I-10 and R1 ("HTF level engaged"). | `OPTS["htf"]` defaults to **False** (`backtest-methods.py:88`). When on, it is the same `ict_bias` computed on the HTF window (`:577-616`). That is agreement of direction, not "an HTF level was engaged". | **missing** (R1 "engaged level"). The gate itself is optional. | Setups can be taken on 15m pivots with no HTF level involved. This is a candidate cause of negative expectancy (N1). |
| I-12 | "HTF level engaged prior to the LTF MSS" | `core-b.md §2.2, §3.1 R1`. | No code checks that the swept pool is an HTF level (HTF swing, PDH/PDL, PWH/PWL). | **missing** | See N1. |
| I-13 | Target | "main focus for identifying targets is standard deviation projections". Manipulation leg from 1 = extreme to 0 = "the previous high which made the highest high". Zones −2…−2.5 and −4…−4.5 (`models.md §2.1.5`, `core-b.md §2.12`, R16-R19). Liquidity and PD arrays **pair with** the σ level (R19). Take profit also at liquidity, opposing candles and swings (`models.md §3.1 rule 23`). | −2σ = `origin + 2·|origin−ext|` (`ict-scan.py:398, 417`). The unswept pool is kept only as `objective`. Nothing checks R19 pairing. Exit is target or stop only. **Timeout at H bars**, marked to market (`backtest-methods.py:71, 411-413`). | **faithful anchor**. **missing** R19 pairing and partial / trailing management (`models.md rules 24-25`). | The −2σ target can be far. With H = 96 × 15m it becomes a timeout, and the result drifts toward the mean (N2). |
| I-14 | Minimum R | "Minimum 2R **before any profit is taken**" (`models.md §3.1 rule 23`). This is a profit-taking rule. | Used as a **pre-entry filter** on planned R net of fees: `R_planned − fee_R < min_rr → skip` (`backtest-methods.py:1359`; `analysis-params.json` `ict.min_rr = 2.0`). | **different** (a management rule reused as an admission filter; the number is sourced) | This removes setups before they exist. The prior funnel showed 0 of 6 BTC trades survived the older 3R floor. |
| I-15 | Setup lookback | None in the deck. | The sweep must lie within `max(12, recent×6)` bars. That is 12 bars on 15m, 1H and 4H alike (`live_rules.py:73-78`; `automation.py` `SCAN_WINDOW`). | project parameter | Caps how slowly a sweep→MSS→FVG may form (3 h on 15m). |
| I-16 | Limit validity | None in the deck. | The fill window is K bars from the MSS (`backtest-methods.py:71, 703-715`). The order is **not cancelled** when price reaches the target, or when an opposite MSS prints, before the fill (`fvg_fill`, `:469-495`, which checks edge and stop only). The live runner is the same (`strategy-runner.py` `ict_live_setups`, `bars_left`). | **looser** (a spent or invalidated setup can still fill) | This adds losing fills on setups whose draw was already delivered (N3). |
| I-17 | Killzones | Forex and **indices** killzones are sourced (`core-a.md §2.1, R1`). | No killzone gate anywhere on the decision path (`ict-scan.py` only prints a gold note, `:471-472`). Index CFDs (US500, US30, USTEC, DE40, FRA40, AUS200) are now in `analysis.cfd`/`execution.cfd` (`docs/architecture/instruments.json` history 2026-09-27). | **missing** for index CFDs. The 09-19 audit's "no killzone on CFD is right" predates indices. | Index setups are taken at any hour (N4). |
| I-18 | CISD / Model11 swing formation / OTE / Inversion / Breaker / Unicorn / Silver Bullet / weekly & daily profiles | `core-b.md §2.3-2.8, R5-R12`; `models.md §2.2-2.5, §3.1`; `core-a.md §2.20, §2.25`. | CISD and OB are computed for display. OTE and σ appear in the chart only. The rest are absent. | **missing** | The implemented "ICT" is one model (sweep → MSS → IOFED) with the Model11 target attached. The OSOK/Fractal models, which give the stop/target/2R rules used here, are not what is detected (see H6). |

### 1.2 Wyckoff (`scripts/wyckoff_rules.py`, read per 300-bar window by `scripts/backtest-methods.py:748-853`)

| # | Structure | Source says | Code does | Deviation | Likely effect |
|---|---|---|---|---|---|
| W-1 | Swings | The book gives no pivot width. | 3 bars each side, with consecutive same-kind pivots merged (`wyckoff_rules.py:73, 89-101`). | project parameter | Every swing is known 3 bars late, and every stage below is counted in these coarse swings. |
| W-2 | Downtrend before SC | "sau một giai đoạn downtrend mạnh … thường là vài tháng" (WA p98, `advance.md §2.7`). | 2 lower lows **and** 2 lower highs just before the candidate SC (`:207-213`). | project threshold (a faithful reading) | Requires a clean LL/LH staircase inside the window. |
| W-3 | SC | A climax. **SC need not have high volume** (WA p76, `advance.md §2.7.1`). | Any qualifying swing low. No volume or spread test (`:214`). | **none** (consistent with WA p76) | — |
| W-4 | PS | Phase A event, a hint of demand (WA p72-73). | Not detected. | **missing** (no decision role, WA2-05) | None on count. |
| W-5 | CHoBEV / CHoCH | A reaction against the trend with increased spread and increased effort. Three CHoBEV = CHoCH, and only then may the TR be drawn (WA p67-69, WA2-01). | Up-swings from the SC onward, each needing `spread > mean` **and** `summed volume > mean` of the last 3 downtrend reactions (`:216-239`). Any low below SC before the 3rd CHoBEV discards the structure (`:232-233`). | **faithful core**. The reference (mean of the last 3 reactions) is a project reading. **stricter**: the book's three CHoBEV are not required to follow the SC, and the WA p69 chart counts them in the turn. | The code needs SC→AR plus two more qualifying rallies before Phase C can even begin (`start = max(choch_bar, st)+1`, `:261`). On 15m that is a lot of structure inside 300 bars. |
| W-6 | TR borders | "Mức thấp của SC **và ST** và mức cao của AR thiết lập ranh giới của TR" (WA p72). The lower border is the start of the first up-wave, the upper is the top of that wave (WA p69; WA2-02). | `tr_lo = SC low`, `tr_hi = AR high` (`:245`). An ST[A] below SC never lowers the border. `ceiling` is raised by confirmed Phase-B swing highs (WY-3, `:270, 288`). | **different** (an ST-set low border is ignored) | When ST[A] < SC, a later dip between ST and SC counts as a "Spring" although it is still inside the book's TR. |
| W-7 | AR | The first rally high after SC, and it sets the upper border (WA p73). | The first swing high after SC (`:237-238`). | **none** | — |
| W-8 | ST[A] | Usually above SC. **ST below SC is allowed**: "expect new lows or a prolonged consolidation" (WA p72, p74-75, WA2-06). | ST is the first swing low after AR (`:249`). The docstring says "holding above SC", but the only check is the CHoBEV loop's `broke` (`:232`). An ST below SC before the 3rd CHoBEV discards the whole structure. An ST below SC after it is kept, with `st_sign = contradicts`. | **stricter** (discards some ST-below-SC structures the book keeps) | Fewer structures (H5). |
| W-9 | Phase B | "thời gian hình thành … thường sẽ dài nhất" (WA p79). UA[B], ST[B], ST[B]-as-mSOW (WA p78, p88, p91). | ≥ `min_phase_b_swings = 2` confirmed swings after ST (`:76, 279-292`). A break earlier than that is `mSOW[B]` and the structure is **discarded** (`:291-292`). A later break below SC is always taken as the Spring. There is no ST[B]-as-mSOW state after 2 swings. | **different** (the book allows Phase-B SC breaks as a bear trap, WA p91, and says MSOW[B] "cũng là Spring tiềm năng", WA p166). The count of 2 is a project parameter. | A true Phase-B mSOW is either discarded (early) or mislabelled as the Phase C Spring (late). |
| W-10 | Sloped structure | Taught and discouraged for first-time operators only. There is "không có một quy chuẩn nào về độ dốc" (WA p167-181, WA2-41/42). | Recorded. Gated only with `--sloped-gate` (`backtest-methods.py:820-821`). | **none** (not gated by default) | — |
| W-11 | Spring | Price below the TR low, which then reverses to **close inside** the TR (WA p80). | The first bar with `L < tr_lo`, then a reclaim close `> tr_lo` within `sob` bars (`:290, 335-338`). `sob` per TF is 8/6/5/4/3/3/2 (`backtest-methods.py:71-72, 776`). | **faithful**. `sob` is a project parameter (WA p83 says only "khá ngắn ngủi"). | — |
| W-12 | Shakeout | "hầu hết các cây nến … đóng cửa dưới biên dưới" (WA p80). A bullish Phase-C test in its own right. WA2-12: expect a longer test and prefer dropping timeframe for a local Spring. | `shakeout` if there is no reclaim within `sob` or more than half the excursion closes are below (`:337`). Shakeouts **never** get an entry (`backtest-methods.py:826`). | **faithful to WA2-12**. **stricter** than WA p80's "Spring (hoặc Shakeout) mang lại cơ hội giao dịch có xác suất cao". The drop-timeframe path of WA2-18 is not implemented. | Removes every type-3-style shake that lingers (H5). |
| W-13 | Spring volume type | Bảng 2.1: type 1 low, type 2 moderate, type 3 high (WMT p049, `modern-tools.md §2.6`). Upthrust Bảng 2.2 (`§2.7`). | Spring: `<0.7` → 1, `>1.5` → 3, else 2. Upthrust: `>1.5` → 2 (UTAD), `≥1.0` → 1, else refused (`:109-135`). Ratio = bar volume / 20-bar mean. | **faithful tables**. The cut-offs are project parameters. Upthrust type 3 is never produced (a declared limit). | A short UT under 1.0× average has no entry at all. |
| W-14 | Spring entry leg | Type 1: recovery close = confirmation. Type 2: retest around the broken support. Type 3: reversal on high volume (Bảng 2.1). WA2-11: partial long on a low-volume Spring, with the Test as confirmation. | Long enters at the reclaim if type 1 **or** (type 3 and reclaim volume ≥ 1.5×). Otherwise it waits for the Test. Short enters at the reclaim for type 1/2 (`backtest-methods.py:834-837`). Entry is at the close of **that exact bar** (`:840`). There is no partial position (`spring_low_volume_max_ratio` has no reader). | **faithful legs**. **missing** the partial-size rule (WA p80). | — |
| W-15 | Test | "kiểm tra nguồn cung trong toàn bộ TR. Thường thì xuất hiện ngay sau Spring" (WA p80). | The first bar within `test_window = 12` that holds above the Spring low, sits inside the lower third, has volume < the Spring bar and closes in its upper half (`:355-361`). | project thresholds (12, 1/3, upper-half close) on a faithful concept | If the Test comes after 12 bars, or its close falls just under mid-bar, the type-2 leg never fires. |
| W-16 | VP abandon rule | Price crosses VAL into the LVN "without a reversal reaction" → abandon the plan (WMT p243-249, `modern-tools.md §5 Step 4`). | Abandon if a close is beyond the LVN and there is **no close back above VAL within 2 bars** of the reclaim (`:349-353`). Under the causal per-window read, when the entry bar is the reclaim itself, only that one bar can be checked. | **stricter** ("2 bars" is not in the book; see §2.2), and stricter again at the fire bar | Type-1 reclaim entries after a deep excursion are abandoned more often than the rule intends. |
| W-17 | SOT | ≥3 pushes valid, 3-4 useful, >4 too strong to oppose (WA p278-292). | Counted. `sot_too_strong` blocks entries (`:171-182, 384`; `backtest-methods.py:826`). | **none** | — |
| W-18 | SOS | Commitment above the TR highs with widening spread and steadily rising volume. The close is judged against the **TR** (WA p84-85). | Close > `ceiling`, spread ≥ 20-bar mean, volume ≥ 20-bar mean, and `commitment_bars = 2` consecutive closes above (`:299-301, 367-371`). | **faithful**. The "2 closes" is a project parameter, and "tăng đều" is read as ≥ mean. | — |
| W-19 | LPS / BU | Two LPS types: after SOS and inside the TR (WA p84). BU = absorption on the TR wall (WA p84-85). | Only the post-SOS pullback. The zone is `[tr_lo + 0.5·TR, ceiling + 0.1·TR]` with volume < SOS bar, and entry is the first up-close above `ceiling` (`:319-326, 374-380`). | **missing** (the in-range LPS type). The zone bounds are project numbers. | — |
| W-20 | Targets | Spring: the opposite side of the TR, reinforced by VAH and the 80 % rule (WMT p273). Phase D: "ít nhất đến biên trên" (WA p83-84). HTF AR/SOS as the target (WA2-19). | Spring target = **AR (`tr_hi`)**, not `ceiling` and not VAH (`backtest-methods.py:842`). Phase D target = `ceiling + 1.0 × TR` (`:850`; `d_target_tr` is project). `vah` is computed and unused. | **faithful** (Spring → AR). **different** within the code itself (the Spring target ignores the Phase-B ceiling that SOS uses). The Phase-D number is invented. | The Spring leg's R is limited by the AR. The Phase-D R depends on an invented multiplier (N6). |
| W-21 | Stop | Below the lowest low of the Spring (WMT p271). | `spring_low × (1 − 0.0005)` (`:841`). BU low for Phase D (`:847`). | **faithful**. The buffer is a project parameter. | — |
| W-22 | Breakeven | "consider moving stop to entry once price has moved favorably or consolidated" — no number (WMT p272). | +1R trigger when `mgmt=be` (`backtest-methods.py:384`). | project parameter (labelled) | — |
| W-23 | đối nhãn Dấu hiệu 3 and 4, failure to maintain structure | WA p160-165, p181-183. | Not implemented. Dấu hiệu 3's "minimum objective = opposite side" is used only as the target. | **missing** | None on count. It would change quality if it were ever measured. |
| W-24 | Distribution | The mirror of accumulation (WA p101). WA2-24: waiting for LPSY is safer than shorting the UT. | The detector runs on inverted prices (`:389-405`). Short entries at the UT reclaim or Test (`backtest-methods.py:834-837`). No LPSY[C]/LPSY[D] entry exists except the mirrored Phase-D BU. | **faithful mirror**. **missing** the WA2-24 preference. | — |
| W-25 | Phase labels A–E | Phases are read off the event sequence. Phase B is usually the longest. | The engine emits events (SC, AR, ST, Spring, Test, SOS, BU), not phase labels. Phase labels on the **live chart** come from the LLM narrative, not from this engine (§3.2 S3). | **different by construction** (live chart ≠ backtested engine) | The owner sees one Wyckoff reading on the chart. The backtest measures another. |
| W-26 | Structure lifetime | Accumulation length has no time standard (WA p76: "Không có một chuẩn mực về thời gian"). | Detection sees only the trailing `WYCKOFF_WINDOW = 300` bars on every timeframe (`backtest-methods.py:743, 905-912`). | project parameter, **stricter** | The whole of downtrend + SC + 3 CHoBEV + ST + ≥ 2 Phase-B swings + Spring + Test/SOS/BU must fit in 300 bars of 7-bar swings (75 h on 15m, 50 days on 4H) (H5). |
| W-27 | Volume feed | Real traded volume is a requirement (WMT p131-133). | CFD tick count is used unchanged in R1, R7, R8, R10 and R11 (`wyckoff_rules.py:49-59`). | **declared, not corrected** (as decided 09-19) | Every volume gate on CFD compares tick counts (N7). |

---

## 2. Numeric parameters on the detection path

### 2.1 `docs/architecture/analysis-params.json`

| Key | Value | Sourced? | Note |
|---|---|---|---|
| `sourced.st_within_third_of_tr` | 1/3 | **sourced** (WA p150) | Read by `wyckoff_rules.py` through `doi_nhan_third`, and by `htf_context.BOUNDARY_FRACTION` (a project adaptation of it). |
| `sourced.st_above_half_tr` | 0.5 | **sourced** (WA p75) | **No reader.** |
| `sourced.sot_min_pushes` / `sot_useful_max_pushes` | 3 / 4 | **sourced** (WA p278-292) | Read by `wyckoff_rules.py:70`. |
| `sourced.value_area_pct` | 0.682 | **sourced** (WA p259, p262) | Read by `wyckoff_rules.py:69`. |
| `sourced.market_profile_80_rule` | 0.8 | **sourced** (WMT p273) | **No reader.** The VAH target is not implemented. |
| `sourced.imbalance_ratio_*` | 3-4 / 3 | **sourced** | Footprint only. Not on this path. |
| `project_defined.lookback_bars` | 20 | project | Volume/spread averages (`wyckoff_rules.py:85`). |
| `project_defined.volume.low_max_ratio / high_min_ratio / spike_min_ratio / upthrust_min_ratio` | 0.7 / 1.5 / 2.5 / 1.0 | project (the tables are sourced qualitatively) | `wyckoff_rules.py:129-135`. The spike value is display only (`build-artifact.py`). |
| `project_defined.spread.narrow_max_ratio / wide_min_ratio` | 0.7 / 1.5 | project | **No reader** (loaded into `SPREAD`, `wyckoff_rules.py:68`, never used). |
| `project_defined.spring_low_volume_max_ratio` | 0.7 | project | **No reader.** WA p80's partial position is missing. |
| `project_defined.commitment_bars` | 2 | project | SOS/SOW commitment (`wyckoff_rules.py:69, 300, 370`). |
| `project_defined.same_level_tolerance_atr` | 0.25 | project | **No reader.** The method.md §4.3 de-duplication is not coded. |
| `project_defined.tick_volume_credit_multiplier` | 0.5 | project | Read by the LLM skill only. |
| `project_defined.ict.pivot_bars` | 3 | project. **The deck says 1** (`core-a.md §2.5`, §5). | `ict-scan.py:62`, `chart.js:63`. |
| `project_defined.ict.equal_level_tolerance_pct` | 0.08 % | project (the deck gives no tolerance, `core-a.md §6 item 8`) | `ict-scan.py:63`. |
| `project_defined.ict.fvg_min_size_median_ratio` | 0.6 | project (`core-a.md §5`: no minimum) | `ict-scan.py:64, 133`. |
| `project_defined.ict.displacement.body_min_ratio / range_min_median_ratio` | 0.6 / 1.2 | project | `ict-scan.py:65, 189-191`. |
| `project_defined.ict.dealing_range` | nearest_pools | a reading of R15. The reference price (last close) is project. | `ict-scan.py:252-257`. |
| `project_defined.ict.std_projection_origin` | highest_pivot_before_sweep | sourced anchor (Model11 p20). The implementation is project. | `ict-scan.py:228, 238`. |
| `project_defined.ict.min_rr` | 2.0 | **sourced number, used differently** (a profit-taking minimum used as an entry floor, `models.md §3.1 rule 23`) | `backtest-methods.py:1359`. |
| `timing.*` | 7/3/0, 15 min | project | Confluence display. Not on the backtest decision path. |

### 2.2 Code literals

| Where | Value | Sourced? |
|---|---|---|
| `backtest-methods.py:71-72` `P[tf]` **R** | 60/48/48/48/36/30/20 | project. **No reader on the ICT or WYCKOFF-BOOK path** (only the legacy `htf_position` and COMBINED's `is_displacement` default). |
| `P[tf]` **K** (fill / MSS window) | 18/16/14/12/10/8/6 | project. ICT limit expiry (`:703`), COMBINED MSS window. |
| `P[tf]` **T** | 20/16/14/12/10/8/6 | project. **No reader.** |
| `P[tf]` **H** (horizon) | 120/96/84/72/48/30/20 | project. The timeout is marked to market (`:411-413`). |
| `P[tf]` **sob** | 8/6/5/4/3/3/2 | project. Spring bars outside (WA p83 gives none). |
| `backtest-methods.py:74` `STOP_BUFFER_PCT` | 0.05 % | project. Wyckoff only. |
| `backtest-methods.py:384` breakeven | +1R | project (WMT p272 gives no number). |
| `backtest-methods.py:743` `WYCKOFF_WINDOW` | 300 bars | project. |
| `backtest-methods.py:1187` `NOTIONAL_CAP_PCT` | 25 % | project (sizing). |
| `automation.py:184-191` `SCAN_WINDOW` | 15m 576/2 · 1H 480/2 · 4H 360/2 · 1D 240/1 | project. Fixes the ICT window, and so the pools, median range and MSS state-machine start. |
| `live_rules.py:73-78` setup lookback | `max(12, recent×6)` = 12 | project. |
| `automation.py:199` `MIN_TIER_RATIO` | 4 | project ("rule of four", an external source). The deck's pairing table is `models.md §2.3`. |
| `ict-scan.py:178, 181` equal-pair minimum separation | ≥ 4 bars | project. |
| `ict-scan.py:291` volume outlier | 1.5 × | project. |
| `wyckoff_rules.py:73-86` `PARAMS` | pivot 3, downtrend_swings 2, min_phase_b_swings 2, slope_max_tr 0.35, spring_max_bars_outside (overridden by sob), test_window 12, test_zone_tr 1/3, vp_bins 30, phase_d_window 40, d_target_tr 1.0, lookback 20 | All project except `chobev_needed = 3` and `doi_nhan_third = 1/3` (sourced). |
| `wyckoff_rules.py:225` CHoBEV reference | mean of the last 3 downtrend reactions | project reading of WA p68. |
| `wyckoff_rules.py:310` "ran away" | `H > ceiling + 1·TR` | project. |
| `wyckoff_rules.py:321, 376` BU zone | `ceiling + 0.1·TR` … `tr_lo + 0.5·TR` | project. |
| `wyckoff_rules.py:352` VP abandon "within 2 bars" | 2 | project. **Not in the book** (grep `knowledge/wyckoff/` finds no such number). |
| `wyckoff_rules.py:360` Test close | upper half of the bar | project. |
| `htf_context.py:165` `BOUNDARY_FRACTION` | 1/3 | project adaptation of WA p150 (the code says so). |

### 2.3 Dead configuration recorded as if it were live (research integrity)

- `range_touches` has no detection reader. `range_established()` (`backtest-methods.py:497-507`) has no caller. The value is still printed in the report header (`:1576`) and stored in the run snapshot (`scripts/snapshot.py:333`). This is the same defect class as the 09-19 finding 11.
- `ict_target` has no reader in `backtest-methods.py` or `ict-scan.py`. `prop-search.py:604, 919` pass `ict_target="range"`, and `snapshot.py:277` records it. The scanner always targets −2σ first (`ict-scan.py:417, 431`). **The 180 prop-search records therefore carry a target label ("range") that does not describe the target actually used.** `stability-report.py:52-57` admits the key is "never read".

---

## 3. Staleness / no-update (the owner's observation)

### 3.1 Verdict

- **Live chart, narrative and HTF context: YES, stale by construction, and also stale now by environment failure.** Wyckoff structure, phase bands, events and all named anchor levels on the live page come from files the **LLM daily full read** writes (`data/live/narrative/<style>.json`, `data/live/anchors.<style>.json`). Nothing in code recomputes them between reads. Evidence shows they were **carried forward for 17 days** from a structure the model could no longer see.
- **Backtest: NO frozen-structure problem.** Every bar re-runs the scanner on the trailing window (ICT: `live_rules.read_at` → `ict_scan.analyze`, `live_rules.py:57-70`, called at `backtest-methods.py:642-646`). Every bar re-runs the Wyckoff detector on a fresh 300-bar window (`backtest-methods.py:905-912`). The backtest never reads `anchors.*`, `narrative/*` or `prelim/*`. The backtest has three different problems instead (§3.3).

### 3.2 Live path: what is frozen, where, with evidence

**S1 — The scanner loop has been dead since 2026-09-27 05:46Z.** `data/live/scan-loop.log` holds 274 lines `"<style>: no scan window for tf=… (SCANWIN_BARS_… unset) -- style skipped"`. The first is at 2026-09-27T05:46:01Z, and the last successful `rc=` line is at 2026-09-27T05:31:06Z. Cause: the embedded Python config block in `scripts/scan-loop.sh:15-35` swallows every exception (`except Exception: pass`, `:31`), so `SCANWIN_*` stays unset and `run_style` fails closed (`:59-71`). This is most likely a Windows-migration environment fault (`python3` / path). It was not confirmed beyond the log. Consequences:
- `data/live/market-data/ohlcv.BTCUSDT.15m.json`: last candle **2026-09-27T05:30Z** (today is 2026-09-28).
- `data/live/prelim/scalping.facts.json`: `scanned_at 2026-09-28T07:42:39Z` but `window_last 2026-09-27T05:30:00Z`. A run triggered by the model re-scanned a frozen file.
- The HTF context used by the scalping page and brief comes from `prelim/swing.facts.json`, `scanned_at 2026-09-27T04:03:05Z`. `load_tier` (`htf_context.py:371-400`) shows `scanned_at` but never refuses stale facts.

**S2 — Full analysis is once a day, on a 24-hour slice.** `scripts/model-read.sh:24` sets `MODEL_READ_INTERVAL=72000` for `full`. The prompt `integrations/headless/scalping-daily-full.md:1` starts with `local-eval-brief.py scalping --bars 96`, so the model sees **96 × 15m = 24 h**. The same prompt demands "EVERY Wyckoff event … from its origin … even when that is earlier than the chart window". The model cannot derive those events from candles it does not have, so it copies them.

**S3 — Wyckoff structure carried forward, not re-derived (direct evidence).**
- `git show 3070e2e:data/live/anchors.scalping.json` (updated 2026-09-11T11:00Z): BTC `sc_low 76,676.07 @ 2026-09-10T12:45Z`, `ar_high 77,424.98 @ 2026-09-10T14:45Z`, `spring_low 76,464 @ 2026-09-10T23:15Z`.
- `git show 15f78bf:data/live/narrative/scalping.json` (updated 2026-09-20T02:30Z): BTC "tích lũy **E**", TR 76,676–77,425 `from 2026-09-10T12:45Z`, Phase A 09-10 → Phase E 09-20. The 15m file in that same commit **starts 2026-09-14T03:15Z** (range 74,968–81,951), so the TR origin and Phase A/B lay outside the data the read was built from.
- `data/live/model-reads/scalping/run-20260926T073002Z-full/result.json` (model's own caveat): "**BTC/ETH/SOL TR, phases and events were carried over from the previous read, with only text and the last phase's end time refreshed. The 15m×96 window cannot re-derive Sep 10–15 events.**" In that read BTC was back at "Phase C (Shakeout 76,423)". The phase went **backwards from E to C** on the same TR. ETH carried TR 2,405.85–2,444.45 and SOL 98.50–100.37. On 09-27 ETH's anchors list SSL 2,659 / 2,639 / 2,600 and SOL's SSL 119 / 120 / 112, so price stood far above those TRs.
- `data/live/model-reads/scalping/run-20260928T073002Z-full/result.json`: "`data/live/anchors.scalping.json` (**anchor set unchanged from prior read, timestamp bumped**)".
- Working tree `data/live/anchors.scalping.json` (updated 2026-09-27T05:30Z): BTC still carries Wyckoff `SC 76,676`, `AR 77,425`, `UA 77,534`, `Shakeout 76,423`, now **without `time` or `role`, and with no `rule`**. The same file's ICT levels sit at 82,875–87,396. The 576-bar 15m window runs 81,400–87,395.67, last close 84,419.6. All four Wyckoff anchors lie **below the entire window**. Meanwhile `data/live/narrative/scalping.json` (same `updated`) says BTC Wyckoff "**chưa xác lập**", with no TR, events or phases. The anchor file contradicts the narrative it is supposed to mirror. `check-narrative.py:587-592` only checks narrative ⊂ anchors, never anchors ⊂ narrative, so nothing catches this.

**S4 — Stale anchors are drawn across the whole chart.** `build-artifact.py:1547-1549` passes every anchor to the chart. `chart.js:304-318` `levelShapes` draws each anchor from `spanOf(rows, lv.time)` to the right edge (`i2:null`). With `time` missing, `spanOf` returns −1 (`chart.js:179`), so the line starts at bar 0. The Wyckoff lane is drawn because Wyckoff is "analysed" (the narrative has `wyckoff.text_html`; `build-artifact.py` `analysed`; `chart.js:653`). The result: SC/AR/UA/Shakeout from 09-10 drawn full width on the 09-21 → 09-27 chart.

**S5 — The anchor-comparison machinery is inert for crypto scalping.** `ict-scan.py:317-358` `anchor_facts` needs each level's `role` (support/resistance) and the file's `rule`. `anchors.scalping.json` has neither. So every level gets `first_close_beyond: null` and the verdict is `null`. `prelim/scalping.facts.json` confirms this: `anchors.verdict_short None`, `SC … fcb None`, `anchor_in_window False`. `cfd-scalping` anchors do carry `role/time/rule`, and a verdict is computed there ("PHÁ DƯỚI SSL 4,244.03").

**S6 — Invalidation uses the wrong owner and does not fire for crypto.** `build-artifact.py:1050-1071` `invalidated_at` matches the narrative's single `invalidation.level` by exact price against a scanner anchor, and it needs that anchor's `first_close_beyond`, which S5 makes impossible for crypto. `chart.js:305` then applies this invalidation to the **Wyckoff** lane's anchors, although every current narrative's invalidation is owned by `ict` (`narrative/scalping.json` BTC `{'owner': 'ict', 'level': 85114}`). A Wyckoff TR/anchor set is therefore never invalidated by its own border break on the entry tier. An ICT invalidation, if it could fire, would fade Wyckoff lines. `htf_context.py:250-260` (P7.4) protects only the HTF **bias**, only for Phase C/D/E, and only when the stored `trading_range` exists. It does not affect drawing or the entry tier.

**S7 — The page measures model staleness against its own newest candle, not the clock.** `build-artifact.py:236-253` says so: "computed against the newest candle ON THIS PAGE, not against the wall clock". With the feed frozen (S1), the model-read chips cannot flag the page as old. The series quality chip (`quality.assess`, `scripts/quality.py:130-140`, STALE after `3 × tf`) is wall-clock based and is the only staleness signal. It does not gate the overlays. The layer-1 header prints only `HH:MM` for "data through" (`ict-scan.py:568-570`), with no date.

**S8 — The live model knowingly publishes stale reads.** `data/live/model-reads/cfd-scalping/run-20260928T073002Z-full/result.json`: "XAGUSD … (**STALE ~49h**)". And: "XAUUSD has since moved live to 4,158.13 and broken below SSL 4,244.03 … this is newer than the frozen snapshot and **was not fed back into the narrative**, per the read-only/frozen-snapshot instruction … the published CHỜ read is already stale relative to current price."

**S9 — The live ICT drawing is not the ICT the system trades.** `chart.js:65-150` `ictAnalyze` re-derives ICT in the browser. That is recomputed on every build, so it is fresh when the feed is fresh. It differs from `ict-scan.analyze`, which feeds the backtest and the runner:
- **C1 pools.** The chart adds only equal pairs, plus the single **most recent** swing high above and swing low below the last close (`chart.js:93`, `.reverse().find`). The scanner adds every pivot as an "old" pool (`ict-scan.py:182-183`). So the dealing range, EQ and premium/discount on the chart can differ from `facts.lo/hi/pct`, which gate `pd_ok`.
- **C2 sweep state.** The chart's `sweptAt` (`chart.js:81`) finds a wick-and-close-back **any time later**, even after a body close through. The scanner stops at the first body close, `closed_through` (`ict-scan.py:152-161`, the ICT-1 fix). The chart can therefore draw "swept" pools and keep dealing-range edges on levels the scanner treats as consumed.
- **C3 MSS.** The chart resets on the first close beyond the swing, displaced or not (`chart.js:115, 120`), and tests displacement on one candle only (`:103`). The scanner keeps scanning past a grab for a later displaced close and accepts multi-candle displacement (`ict-scan.py:199-208, 234-236, 244-246`). The OTE and σ lines on the chart therefore come from a possibly different "last MSS".

**S10 — HTF Wyckoff read on the page and in the brief.** The bias and structure tiers read `narrative/<tier style>.json`, falling back to this style's `context.wyckoff` (`htf_context.py:385-392`; `build-artifact.py:1565-1567`). Only `scalping` and `cfd-scalping` narratives exist (`data/live/narrative/`), so the 4H/1D context comes from a 60-bar 4H slice written once a day inside the 15m full read. It is frozen in the same way as S3. The 09-24 review already found the 09-11 XAUUSD context read still being served on 09-24 (`2026-09-24-wyckoff-label-review.md §0, §4(b)`).

### 3.3 Backtest: recomputed, but three different defects

- **B1 — Window-limited memory (not frozen, forgotten).** ICT re-frames pools, MSS state and the dealing range inside the trailing 576 bars on 15m (`automation.py:184-191`). Wyckoff sees 300 bars (`backtest-methods.py:743`). A structure is recomputed every bar, but anything older than the window does not exist. This is the reverse of the live problem, and it caps Wyckoff structure length (W-26).
- **B2 — A spent or invalidated setup can still fill.** The ICT limit lives K bars from the MSS and is cancelled only by expiry or a same-bar stop (`fvg_fill`, `backtest-methods.py:469-495`; expiry `:703-715`). Reaching the −2σ target first, or an opposite displaced MSS, does not cancel it. The live runner behaves the same (`strategy-runner.py` `ict_live_setups`: `fill is not None or bars_left < 0`). That keeps the engines at parity, but it is a structure used after its draw was delivered.
- **B3 — The Wyckoff HTF bias differs between live and backtest.** In the backtest, `lr.bias_at` → `htf.bias_of(None, facts)` gets no narrative and no anchors. So `wyckoff_bias` always returns `unknown`, which is silent (`htf_context.py:281-287, 342-346`). Live pages and brief use the LLM narrative's (stale) phase. This has **no effect today**, because Wyckoff is disengaged in both markets (`docs/architecture/automation-config.json` `markets.crypto/cfd.dimensions.wyckoff = false`). It becomes a §37 divergence the day Wyckoff is engaged.

Computational caches on the backtest path are sound. `_WY_CANDIDATES` is keyed by history identity (`backtest-methods.py:907-910`). The prop-search disk cache key includes the data digest, the code digest over `scripts/*.py` and `docs/architecture/**/*.json`, and the PIT cutoff (`scripts/scan_cache.py:54-66`). `_ASSESSED` is keyed by (sym, tf) regardless of cutoff, which is documented as safe for current callers (`backtest-methods.py:124-135`).

---

## 4. Ranked, checkable hypotheses

Every hypothesis is built from a source rule or from a project parameter named as such. None adds a rule that is absent from `knowledge/`. The measuring agent can test each one on development data (< 2024-03-01).

### Few signals

| Rank | Hypothesis | How to check | Source basis |
|---|---|---|---|
| **H1** | The same-timeframe 1-bar PCH/PCL bias gate (`backtest-methods.py:649-651`, `htf_context.py:178-225`, `ict-scan.py:274-278`) removes or defers a large share of complete, `pd_ok` ICT setups. The deck frames this bias on the previous **higher-timeframe** candle. | Count complete+pd_ok setups refused by `bias_allows` at first visibility. Count those whose first bias-agreeing bar arrives after the limit was already pierced. Compare with the bias read on the structure tier (`HTF_OF[tf]`) instead of the entry tier. | `core-a.md §2.11-2.12, §3.2 R5-R9, §5` |
| **H2** | Pivot width 3 (the deck says 1) delays pivot confirmation by 3 bars. Together with the bias deferral (H1) and the FVG-third-candle wait, the setup becomes visible after price has already touched the FVG edge, so it is refused as "already triggered" (`backtest-methods.py:706`). | With `pivot_bars = 1` (the deck's own value), measure `i − mss_i` at first visibility and the share refused at `:706`. | `core-a.md §2.5, §5` |
| **H3** | The displacement and FVG-size thresholds (0.6/1.2, 0.6 × median; project) are the largest filter. The prior funnel shows 786 of 1,119 BTC candidates dropped as "not complete". | Report the funnel split: no displacement vs no same-direction FVG after the sweep. Sensitivity-test each threshold. Do not select on it, since the thresholds are unsourced. | `core-a.md §2.16, §5` (no number given) |
| **H4** | R13 is judged on a dealing range built around the detection bar's last close, and the range excludes the swept SSL (`ict-scan.py:252-257, 442-445`). The deck's R13 geometry puts the stop at the range extreme behind the entry. Re-framed this way, the range fails more setups than the R13 diagram would (270/1,119 BTC). | Recompute `pd_ok` with the range framed from the swept extreme to the nearest opposing BSL/SSL (both are deck liquidity definitions). Compare the counts. | `core-a.md §2.18-2.19, §3.4 R13, R15, §6 item 19` |
| **H5** | WYCKOFF-BOOK structure count is bounded by six things together: the 300-bar window, 7-bar swings, 3 CHoBEV counted only after SC, discarding ST-below-SC-before-CHoCH, discarding every Shakeout, and the causal VP abandon test at the fire bar. | Per-stage counts are already in `wyckoff_rules.STATS` (`bump`). Report them per timeframe. Re-run with the window at 600/900 (project parameter) and see whether structures appear that 300 cuts. | WA p68-69, p72, p76, p80, p83; WMT p243-249 |
| **H6** | The index-CFD universe has no killzone gate (I-17). This does not change the signal count, but it mixes setups from all hours. | Split index-CFD setups by the deck's indices killzones (`core-a.md §2.1`, the NY clock via `sessions.py`) and count the trades inside and outside them. | `core-a.md §2.1, R1` |

### Negative expectancy

| Rank | Hypothesis | How to check | Source basis |
|---|---|---|---|
| **N1** | ICT setups taken with no HTF level engaged (the swept pool is only an entry-TF 7-bar pivot) have worse expectancy than setups whose sweep is of an HTF swing or PDH/PDL. | Tag each trade by whether the swept level matches an HTF pivot or `prev_day.pdh/pdl` (both are computed today) within `equal_level_tolerance_pct`. Compare the expectancy of the two groups. | `core-b.md §2.2, §3.1 R1, R23` |
| **N2** | The −2σ target together with the fixed horizon H (96 × 15m) produces many `timeout` exits, and those have near-zero or negative mean R. Planned R looks high, but realised R does not. | Break the ICT outcome down by win/loss/timeout. Measure MFE against the −2σ distance. Measure the share of trades that touched the −2…−2.5 zone (the deck's first zone) but not −2 exactly. | `models.md §2.1.5`, `core-b.md §2.12 R17` (the zone, not the point) |
| **N3** | Some fills happen after the setup's draw was already delivered (price hit −2σ, or an opposite displaced MSS printed, before the retrace to the FVG). These are losing trades on spent setups (B2). | For each filled ICT trade, check whether `H ≥ target` (long) or an opposite `last_displaced_mss` occurred between the detection bar and the fill bar. Compare the expectancy of that group with the rest. | `core-b.md §3.1 R3` (ERL → IRL → ERL), `core-a.md R25` |
| **N4** | Using the **latest** same-direction FVG after the sweep (`fv[-1]`), rather than the FVG inside the displacement leg, moves entries to shallower continuation gaps and lowers realised R. | Tag trades by whether the chosen FVG lies inside the contiguous displacement run (the `leg_disp` span) or after it. Compare the two groups. | `core-a.md §2.16, §3.3 R12` |
| **N5** | The ICT stop sits exactly at the sweep wick with no buffer. Equal-low retests stop out trades that would otherwise have survived. | Count stop-outs whose low equals the sweep extreme within one tick. Compare with Wyckoff's 0.05 % buffer (project parameter). | `core-a.md R22` ("stop **below** the originating swing low") |
| **N6** | The Wyckoff Phase-D target, `ceiling + 1 TR` (project, `d_target_tr`), and the Spring target at AR rather than at the Phase-B ceiling or VAH decide R more than the method does. | Report the Phase-D and Spring legs separately, with timeout share and MFE/target ratio. Compare the Spring target at AR, at the ceiling and at VAH (the last two are book-sourced: WA p85, WMT p273). | WA p83-85, WMT p273 |
| **N7** | On CFD, tick-count volume drives CHoBEV, Spring typing, the Test and SOS. Those gates then select on noise. | Split the CFD WYCKOFF-BOOK trades by `volume_kind` and compare them with crypto on the same timeframe. Count how many CFD structures pass CHoBEV purely on summed tick volume. | WMT p131-133 |

### The owner's observation, stated as checks

| # | Check | Expected if the observation is right |
|---|---|---|
| O1 | For every `data/live/anchors.*.json` level with `method: wyckoff`, compare the price against the current window range. Check whether the matching narrative has `wyckoff.structure == "chưa xác lập"`. | BTC/ETH/SOL Wyckoff anchors lie outside the window and contradict the narrative (true on 2026-09-27, §3.2 S3). |
| O2 | Diff `narrative/scalping.json` `wyckoff.trading_range/events/phases` across consecutive full reads. | The TR and events are identical across reads while `phases[-1].to` moves forward, and the phase letter changes without any new event (seen 09-20 E → 09-26 C). |
| O3 | Compare `ict-scan.analyze(window)` `lo/hi/pct/last_mss` with `chart.js ictAnalyze` on the same rows. | They disagree on pools, sweeps and the last MSS whenever old pools, closed-through levels or multi-candle displacement are involved (§3.2 S9). |

---

## 5. Minor deviations and hygiene (recorded, low impact)

- The `backtest-methods.py:17-24` docstring still describes the pre-2026-09-13 ICT proxy ("last 3-bar pivot … Target = the highest high of the previous R bars"). The code uses the live scanner with a −2σ target.
- `live_rules.py:34-35` comments say "will be called by backtest-methods.py (Task 4), not yet". It already is.
- `wyckoff_rules.py:249` comment says "ST[A]: first swing low after AR holding above SC". Holding above SC is not checked.
- `_wyckoff_candidates` mutates the module global `W.PARAMS["spring_max_bars_outside"]` per timeframe (`backtest-methods.py:776`). That is shared state with `check-narrative.py`, which imports the same module.
- `chart.js:78` keeps only the 10 largest FVGs, then the last 8. The scanner keeps all FVGs above the size floor. This is display only, but the overlay can omit the FVG a setup uses.
- `ict-scan.py:568-570` prelim header "dữ liệu tới HH:MM UTC" has no date (see S7).
- `SPREAD` is loaded and never used (`wyckoff_rules.py:68`).

---

## 6. What was not verified

- Why `scripts/scan-loop.sh`'s embedded Python fails on this machine. Only the effect is shown, in the log.
- The rendered page was not opened. What is drawn is derived from `chart.js` / `build-artifact.py` logic and the current data files.
- No count in §4 was measured in this audit, by instruction. The funnel numbers quoted (786/1,119, 270/1,119, 7/23, 9/23) are from `docs/audits/2026-09-19-knowledge-fidelity.md §8`, measured before later code changes (ICT-1 closed-through, ICT-4 multi-candle displacement, 2R floor). They may have shifted.
- Whether `strategy-runner.htf_pass` reads fresh HTF candles in every live path. The backtest docstring says it does (`backtest-methods.py:578-583`). It was not traced end to end.
