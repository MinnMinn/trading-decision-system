# ICT / TTrades entry-checklist audit — does the implementation follow the decks?

Date: 2026-09-11. Read-only audit. Every citation below comes from a file read in this session; deck page
numbers are quoted **as the knowledge files record them** (the audit did not open the PDFs themselves).

Legend for status:
- **CODE** — a deterministic script enforces or computes it. File:line given.
- **INSTR** — only an instruction to the model (`.claude/skills/ict-skill/SKILL.md`, `scripts/local-eval-brief.py`
  brief text). Nothing verifies it; `scripts/check-model-prose.py` checks vocabulary purity and number provenance,
  not rule compliance.
- **PARTIAL** — implemented in a weaker or different form than the deck states.
- **MISSING** — no code, no instruction.
- **CONTRADICTS** — implemented in a way that conflicts with the deck or with the project's own
  `docs/architecture/session-model.md`.

Implementation surfaces audited:
- `scripts/ict-scan.py` — the only layer-1 ICT fact producer (`analyze()`, `setup_candidate()`, `anchor_facts()`).
- `scripts/build-artifact.py` — in-page JS `ictAnalyze()` (lines 501–536); drawing layer only.
- `scripts/demo-pilot.py` — `evaluate()` (lines 203–265); the only thing that actually places orders.
- `scripts/local-eval-brief.py` — the layer-2 model brief.
- `scripts/check-model-prose.py`, `scripts/method_purity.py` — output guards (vocabulary + number provenance).
- `scripts/measure-spring-ict.py` — backtest proxy only, not a live path.
- `.claude/skills/ict-skill/SKILL.md` — the procedure the model follows.

---

## 1. Rule-by-rule coverage

### 1.1 Bias / HTF context

| # | Deck rule | Source | Status | Covering line |
|---|---|---|---|---|
| B1 | "Is price more likely to reach for previous [day/candle] high or low?" — pick the draw (PDH/PDL, PCH/PCL, PWH/PWL, PMH/PML) | `k04 §3.2 R5`, `14. Daily_Bias p3 (1)`; `6. Intraday_Bias p3 (1)` | **MISSING** | grep for `PDH`/`PDL`/`opposing` across `scripts/*.py` returns nothing. No previous-day/-week/-month level is computed anywhere. |
| B2 | Body closes **through** PDH/PDL ⇒ level was a draw, expect continuation | `k04 §3.2 R6`, `4. ILL p4–p6` | **MISSING** | same |
| B3 | Wick through, body fails to close beyond ⇒ **failure to displace**, frame reversal, opposite level becomes the new draw | `k04 §3.2 R7`, `14. Daily_Bias p3 (1), p7 (5)` | **PARTIAL** | The sweep detector is exactly this test but only on *equal-high/low pools*: `ict-scan.py:98-99` `if kind == "BSL" and H[j] > level and C[j] < level: swept = j`. It is never applied to PDH/PDL/session levels, and the "opposite level becomes the new draw" half is absent. |
| B4 | Next Candle / Next Day Model — anticipate the next candle after a failure to displace or while a PD array caps pullbacks | `k04 §3.2 R8`, `6. IB p7 (5)` | **MISSING** | — |
| B5 | HTF structural falsification: last confirmed MSS by **body close**, contradictions with the Wyckoff phase call to be raised, not resolved | `k05 §2.2`, `k10 §4.2 step 3`; SKILL.md:18 | **INSTR** | `SKILL.md:18` "Is the last confirmed structural break (MSS) bullish or bearish, by body close?" No code computes an HTF MSS bias. The only coded HTF filter is **Wyckoff**-derived: `htf_context.py` docstring "Book basis (the only source of the rule): knowledge/07 … §2.7 'Giảm khung của tích lũy'", consumed at `demo-pilot.py:250-251`. |
| B6 | HTF level must be engaged **before** the LTF MSS/CISD | `k05 §3.1 R1`, `18. MSS p5 (3)` | **PARTIAL** | `demo-pilot.py:244-251` requires the 4H/1D Wyckoff bias to match the side, which is a different (and weaker) test than "an HTF price level was engaged". |
| B7 | Weekly profiles (Classic Expansion / Midweek / Consolidation Reversal / Thursday Counter) gate which day may be the reversal | `k06 §3.1 rules 9–13`, `Model11 p74–p81` | **MISSING** | no day-of-week logic in any script. |
| B8 | Daily profiles: London Reversal → seek NY continuation; London consolidation/opposing run → seek NY reversal | `k06 §3.1 rules 16–17`, `Model11 p85–p87` | **MISSING** | — |

### 1.2 Liquidity

| # | Deck rule | Source | Status | Covering line |
|---|---|---|---|---|
| L1 | Swing high/low = one candle each side | `k04 §4` table, `3. Liquidity p3 (1)` | **CONTRADICTS (declared)** | `ict-scan.py:78` `if all(H[j] <= H[i] for j in range(i - 3, i + 4) if j != i)` — **3 bars each side**. Mirrored in `build-artifact.py:506`. Declared as a project parameter in `ict-scan.py:26` ("3-bar pivot … are this system's own parameters"). |
| L2 | BSL = swing high, SSL = swing low, line projected from the wick | `k04 §2.6`, `3. Liquidity p4 (2)` | **PARTIAL** | Only **relatively-equal pairs** become pools: `ict-scan.py:104` requires `abs(H[sh[a]] - H[sh[b]]) <= tol and sh[b] - sh[a] >= 4`. A single unpaired swing high is never a pool. |
| L3 | Old highs & lows are liquidity in their own right | `k04 §2.7`, `3. Liquidity p5 (3)` | **MISSING** | consequence of L2. |
| L4 | PDH/PDL, PWH/PWL, PMH/PML, session highs/lows are liquidity levels | `k04 §2.8–2.9`, `3. Liquidity p6–p7`, `4. ILL p4–p9` | **MISSING** | no code computes any of them. `ict-scan.py:233` only prints a prose note that killzones matter for gold. |
| L5 | ERL = swing highs/lows; IRL = FVGs; after ERL is taken target IRL, after IRL target the next ERL | `k05 §2.13, §3.1 R3, §3.4 R20`, `IRL-ERL p6 (4), p9 (7)` | **PARTIAL** | ERL exists as window extremes (`ict-scan.py:133-134` `erl_high`/`erl_low`; `build-artifact.py:519`). The **alternation rule** is not implemented: `setup_candidate()` targets the nearest unswept opposite pool, else the window extreme (`ict-scan.py:214-215`), never "the FVG next". |
| L6 | "Relatively equal" has no sourced tolerance | `k04 §6 item 8` | **CODE (project param, declared)** | `ict-scan.py:93` `tol = eq * 0.0008`; declared in the docstring line 26. |

### 1.3 Displacement / MSS / CISD

| # | Deck rule | Source | Status | Covering line |
|---|---|---|---|---|
| M1 | Displacement = aggressive **full-bodied** candle(s), generally leaving an FVG | `k04 §2.16`, `k05 §2.1`, `11. MSS_vs_LG p3 (1)` / `18. MSS p3 (1)` | **MISSING as a test** | No body-ratio or range-ratio test exists anywhere. `demo-pilot.py:237` `strong_close = C[mss_i] >= mid` (close in the upper half of the MSS bar) is the closest thing, and it is labelled Wyckoff Effort-vs-Result in the module docstring (line 17), not displacement. |
| M2 | MSS = displacement **body close** over/below the swing; prefer a stop raid immediately before | `k04 §3.3 R10`, `11. MSS_vs_LG p4 (2)`; `k05 §3.2 R4` | **PARTIAL/CODE** | Close test: `ict-scan.py:122` `if bias == -1 and lastH is not None and C[j] > H[lastH]`. Stop-raid-first is *enforced* (stronger than the deck's "preferred") in `ict-scan.py:201` `if m["i"] <= s["swept"]: return None` and in `demo-pilot.py:218-223`. Missing: the displacement requirement (M1) and the FVG-in-the-displacement requirement (`k04 §3.3 R12`). |
| M3 | The MSS reference swing is the one **immediately preceding the raid leg** | `k04 §6 item 12`, `11. MSS_vs_LG p4 (2)` | **PARTIAL** | `ict-scan.py:113-125` tracks `lastH`/`lastL` and a HH/LL `bias` flag; the swing used is the last pivot of the opposite kind, which usually but not always equals the pre-raid swing. No explicit link between the pool that was swept and the swing that must be broken. |
| M4 | Liquidity grab = wick beyond, body fails to close beyond ⇒ failure to continue (not a trend change) | `k04 §3.3 R11`, `11. MSS_vs_LG p5 (3)` | **CODE** | `ict-scan.py:98-99` (the sweep test), and the prose is emitted at `ict-scan.py:269-271` "đây là liquidity grab, chưa phải MSS cho tới khi có nến đóng phá swing ngược chiều". |
| M5 | **CISD** — close through the open of the first candle of the final opposing-colour run into the level; earlier and tighter than MSS | `k05 §2.3, §3.2 R5, R7`, `16. CISD p3–p4`; `k06 §4.5`, `Model11 p44–p48` | **MISSING** | `grep -niI "CISD" scripts/*.py` → no hits. CISD is the trigger of OSOK, the Fractal model, Timeframe Alignment and TTRS; none of it is implemented, and `SKILL.md` never mentions CISD either. |
| M6 | Opposing (close) candle level = open of the first candle of the run; must be paired with a POI (swept high/low, FVG, or prior opposing series); inner series ignored | `k06 §2.1.1, §4.4`, `Model11 p5–p10` | **MISSING** | `grep -niI "opposing" scripts/*.py` → no hits. |

### 1.4 PD arrays — FVG / OB / Breaker / Mitigation / Unicorn / Inversion

| # | Deck rule | Source | Status | Covering line |
|---|---|---|---|---|
| P1 | FVG = 3 candles, wick-based: bull `high[1] < low[3]`, bear `low[1] > high[3]` | `k04 §2.21, §4`, `12. FVG p3–p4` | **CODE (faithful)** | `ict-scan.py:84-85` `if H[i - 1] < L[i + 1]: f = {"type": "bull", …}` / `elif L[i - 1] > H[i + 1]`. Same in `build-artifact.py:508`. |
| P2 | No minimum FVG size is given by the source | `k04 §5` ("No numeric thresholds are given for: … FVG minimum size") | **CODE (project param, declared)** | `ict-scan.py:91` `if f["size"] >= 0.6 * med`. Declared at line 26 and in the emitted prose `ict-scan.py:314`. |
| P3 | Three FVG entry models: IOFED (near edge), **Consequent Encroachment (0.5)**, FVG Fill (far edge) | `k04 §2.23, §3.5 R19`, `12. FVG p6 (4)` | **PARTIAL** | Only IOFED is computed: `ict-scan.py:213` `entry = f["hi"]` for longs (the bull FVG's upper edge = `L[i+1]`), `:218` `entry = f["lo"]` for shorts. CE and FVG-Fill are never offered. `grep -niI "consequent" scripts/*.py` → no hits. |
| P4 | CE (0.5 of the gap) is also the hold/fail decision line — a body close through CE means the FVG is failing | `k04 §2.26, §3.6 R23`, `13. Inversion p9–p14` | **MISSING** | no CE anywhere in code. `SKILL.md:19` names "FVG (edges and consequent encroachment)" as something to state — **INSTR only**. |
| P5 | FVG stop models: gap far edge (tight) / OB candle low (medium) / originating swing low (wide) | `k04 §2.24, §3.6 R22`, `12. FVG p7 (5)` | **PARTIAL** | Only the widest-ish option: `ict-scan.py:213` `stop = min(L[s["swept"]:m["i"] + 1])` = the sweep extreme; `demo-pilot.py:257` `swept = min(L[sweep_i:]); stop = swept - max(STOP_BUFFER_PCT * entry, …)`. Gap far edge and OB low are not offered. `SKILL.md:53` acknowledges all four options exist and demands one owner be named — **INSTR**. |
| P6 | **Order Block** = last opposing-close candle before displacement; the **open** is the OB line; **mean threshold** = 0.5 of the OB body | `k05 §2.5, §3.3 R10`, `17. Orderblocks p3 (1), p7 (5)` | **PARTIAL / CONTRADICTS** | Only the drawing layer has an OB: `build-artifact.py:526` `for(let q=j-1;q>=…;q--){ if(C(q)<O(q)){obs.push({type:'bull',i:q,lo:L(q),hi:Math.max(O(q),C(q)),until:j});break;} }` — a **zone from the candle low to the body top**, not the deck's **open line**, and with **no mean threshold**. The scanner (`ict-scan.py`) computes no OB at all, so no OB ever reaches `setup_candidate()`, the brief, or the pilot. |
| P7 | **Breaker Block** (Low→High→Lower Low sweep→Higher High; box on the up-close bodies at the High) and its two stops | `k05 §2.7, §3.3 R11, §3.5 R22`, `19. Breaker p4–p9, p18 (16)` | **MISSING** | `grep -niI "breaker" scripts/*.py` → no hits. `SKILL.md:19` names "Breaker" — **INSTR**. |
| P8 | **Mitigation Block** (prior extreme **not** swept; higher low / lower high; SMT often present) | `k05 §2.9, §3.3 R13`, `20. Mitigation p3–p14` | **MISSING** | `SKILL.md:19` names "Mitigation Block" — **INSTR**. |
| P9 | **Unicorn** = breaker box ∩ FVG; entry = the overlap | `k05 §2.8, §3.3 R12`, `19. Breaker p17 (15)`; `k06 §3.5, §4.10`, `Unicorn p6 (4)` | **MISSING** | `grep -niI "unicorn" scripts/*.py` → no hits. `SKILL.md:35` mentions Unicorn only as a de-duplication caveat. |
| P10 | **Inversion / IFVG** — an FVG closed through by displacement, retested from the other side, becomes the entry | `k04 §2.25, §3.5 R20`, `12. FVG p8 (6)`, `13. Inversion p4–p8`; `k05 §3.2 R8` | **MISSING** | `grep -niI "inversion" scripts/*.py` → no hits. The FVG record has a `mitigated` flag (`ict-scan.py:87-90`) but a mitigated FVG is simply dropped from `fvgs_open`, never re-used as inverted support/resistance. |
| P11 | Old SIBI/BISI chain — successive prior-trend FVGs as sequential draws | `k04 §3.5 R21`, `13. Inversion p16 (14)` | **MISSING** | — |
| P12 | Volume Imbalance (bodies don't overlap, wicks do) and Opening Gap (no overlap at all) | `k04 §2.22, §4`, `12. FVG p5 (3)` | **MISSING** | only referenced as a vocabulary exception in `method_purity.py:51` `"ict": [r"volume[ -]imbalance", r"\bVI\b"]`. |

### 1.5 Premium / discount / OTE

| # | Deck rule | Source | Status | Covering line |
|---|---|---|---|---|
| D1 | Range = where BSL and SSL rest (the nearest swing-high/swing-low pair); EQ = 0.5 | `k04 §2.18, §3.4 R15`, `8. D&P p3 (1), p4 (2)` | **CONTRADICTS** | `ict-scan.py:72` `lo, hi = min(L), max(H); eq = (lo + hi) / 2` — the range is the **window's extreme wicks over N bars**, not a BSL↔SSL pair. Same in `build-artifact.py:503`. This makes the dealing range a function of the chosen lookback (`N` = 180 bars on 1m, 288 on 15m, …) rather than of structure. |
| D2 | Shorts only in premium, longs only in discount | `k04 §3.4 R13`, `8. D&P p5 (3)` | **CODE** | `demo-pilot.py:212-215` `if long and a["pct"] >= 0.5: reasons.append("không ở discount …")`. Enforced as a hard gate. |
| D3 | A PD array in the premium frames a short; in the discount frames a long; ignore opposite-half arrays | `k04 §3.4 R14`, `8. D&P p6–p7` | **NOT ENFORCED** | `ict-scan.py:207` records `"in_discount": a["pct"] < 0.5` but `setup_candidate()` never uses it to reject a setup — the flag is only printed (`local-eval-brief.py:151`). |
| D4 | Premium/discount scores only when its anchors differ from the Wyckoff TR anchors | `k10 §4.3`; `SKILL.md:36` | **INSTR** | `SKILL.md:36` "Premium/discount scores only when its anchors are stated and differ from the Wyckoff TR anchors … score that sub-item 0 and say so." No code checks it. |
| D5 | **OTE** — fib 1 at impulse origin / 0 at terminus; entry band 0.62–0.79, 0.705 emphasised; prefer overlap with a PD array; nested re-anchor on the internal swing | `k04 §2.20, §3.5 R16–R18`, `9. OTE p3–p9` | **MISSING** | `grep -niI "OTE" scripts/*.py` → only false positives (`footer`, `notes`). OTE appears in the `ict-skill` **frontmatter description** (`SKILL.md:3`) and in the brief's citation map (`local-eval-brief.py:33`), but is absent from the SKILL's own Procedure (lines 16–26) and from all code. |

### 1.6 Timing

| # | Deck rule | Source | Status | Covering line |
|---|---|---|---|---|
| T1 | Killzone windows (two competing sets: forex vs indices) | `k04 §2.1, §3.1 R1`, `1. Killzones p3 (1)` | **CONTRADICTS the project's own model** | `build-artifact.py:531` `[{name:'LDN',a:6,b:9},{name:'NY AM',a:11,b:14}]` — fixed UTC hours. `docs/architecture/session-model.md:21` says exactly this: "the fixed UTC windows previously used in `scripts/local-eval-brief.py` ('London 06–09Z, NY AM 11–14Z') are correct in summer only. Any code computing a session must convert from the local zone for the date in question, not hardcode a UTC hour." `local-eval-brief.py:30` still prints those same windows to the model. Worse: session-model's `london` is 08:00–11:00 Europe/London (= 07:00–10:00Z in BST, 08:00–11:00Z in GMT) — never 06–09Z; and its `ny_am` is 08:30–11:00 New York (= 12:30–15:00Z EDT), whereas 11–14Z corresponds to the **forex** 07:00–10:00 NY set that session-model.md:37 explicitly rejected. |
| T2 | Silver Bullet windows 03:00–04:00 / 10:00–11:00 / 14:00–15:00 EST; AM SB framed on the 9:00 hourly candle | `k04 §2.2, §3.1 R2`, `1. Killzones p4 (2)`; `k05 §2.15, §3.3 R15`, `Silver_Bullet_AM p3–p5` | **MISSING** | `grep -niI "silver bullet" scripts/*.py` → no hits. |
| T3 | No timing credit below 15m; none on Sat/Sun; asia = journalling only | `session-model.md:34, 59-60`; `analysis-params.json` `timing.min_timeframe_minutes` | **INSTR / CONFIG** | Values exist in `analysis-params.json:88-91`; the gate is stated in `SKILL.md:22` "No timing credit below `timing.min_timeframe_minutes`, and none on Saturday or Sunday UTC". No script evaluates it — `build-artifact.py` draws killzones on a per-style `kz=True/False` flag (`build-artifact.py:38-47`) rather than from the 15m rule, and `demo-pilot.py` has **no session gate at all**. |
| T4 | PO3 / AMD — manipulation beyond the period open, enter at/after the end of manipulation | `k05 §2.11, §3.3 R14`, `22. PO3 p3–p6` | **MISSING** | `grep -niI "PO3" scripts/*.py` → no hits. `SKILL.md:23, 38` mention PO3 only as a timing input and a de-duplication caveat — **INSTR**. |
| T5 | Timeframe pairing table W→4H, D→1H, 4H→15m, 1H→5m, 30m→3m, 15m→1m | `k06 §2.3, §3.6 rule 4`, `Model11 p44, p95`; `TFA p5 (3)` | **PARTIAL** | `automation.py:95` `CONTEXT_STYLE = {"scalping": "daytrade", "daytrade": "4h", "1h": "swing", "4h": "swing", …}` → 1m↔15m ✓, 15m↔4H ✓, 1H↔1D ✓, but **4H↔1D** where the deck pairs 4H with Weekly. Also the project's pairing is used for a *Wyckoff* context read, not for the deck's purpose (HTF swing → LTF CISD). |

### 1.7 Stops, targets, management

| # | Deck rule | Source | Status | Covering line |
|---|---|---|---|---|
| S1 | Stop = the TTrades candle-2 swing point | `k06 §3.1 rule 22`, `Model11 p90–p91` | **MISSING** (candle-2 formation itself is not detected) | — |
| S2 | Stop options: OB low / raid swing low; breaker low / Lower Low | `k05 §3.5 R21–R22`, `17. OB p8 (6)`, `19. Breaker p18 (16)` | **PARTIAL** | Only the raid/sweep extreme: `ict-scan.py:213`, `demo-pilot.py:257`. |
| S3 | **Minimum 2R before any profit is taken** | `k06 §3.1 rule 23`, `Model11 p92` | **CONTRADICTS (softened)** | `demo-pilot.py:84` `MIN_RR = 1.5`, used at `:258` `tp = eq if (eq - entry) >= MIN_RR * r else entry + 2 * r`. The deck's number is 2R; the pilot accepts 1.5R and, in the fallback branch, takes a flat 2R. `ict-scan.py` computes R but applies no minimum. |
| S4 | Targets = std-dev projections −1/−2/−2.5/−4(/−4.5) anchored on the manipulation leg; −2..−2.5 = retrace/reverse zone; −4 = max expansion; prefer a level that coincides with a PD array | `k05 §2.12, §3.4 R16–R19`, `23. STD p3–p10`; `k06 §2.1.5, §3.1 rule 15`, `Model11 p20–p23` | **MISSING** | no projection code anywhere. Targets are "nearest unswept opposite pool, else window extreme" (`ict-scan.py:214-215, 219-220`) or "window EQ, else 2R" (`demo-pilot.py:258, 261`). |
| S5 | Take profit at liquidity levels, opposing candles, opposing swing formations | `k06 §3.1 rule 23` | **PARTIAL** | Liquidity-pool targets only (`ict-scan.py:214`). |
| S6 | Trail the stop to opposing candles / validated swing points | `k06 §3.1 rule 24`, `Model11 p93–p94` | **MISSING** | the pilot exits via a static OCO (`demo-pilot.py:291`) plus `TIME_STOP_BARS = 24` (line 85). |
| S7 | Position size = $risk / $ per point / stop size | `k04 §3.1 R3`, `2. Position_Sizing p7 (5)` | **CODE** | `demo-pilot.py:270-271` `r = d["entry"] - d["stop"]; risk_usd = equity * RISK_PCT * risk_mult; qty = risk_usd / r`. Faithful. |
| S8 | Win-rate × RR profitability table | `k04 §2.3, §3.1 R4` | **MISSING** | not evaluated anywhere (no expectancy gate). |

### 1.8 Invalidation

| # | Deck rule | Source | Status | Covering line |
|---|---|---|---|---|
| I1 | A later **body close beyond the same swept level** converts the grab into an MSS and kills the reversal read, even if the stop has not been hit | `k04 §3.6 R25`; `SKILL.md:55` | **PARTIAL** | The machinery exists but is aimed elsewhere: `ict-scan.py:165` `if (role == "support" and C[i] < price) or (role == "resistance" and C[i] > price): first = i; break` — this is a first-close-beyond test, applied to the **named anchors of the last full analysis** (`data/live/anchors.<style>.json`), not to the swept level of the current setup. `demo-pilot.py` never re-checks the thesis; it only holds the OCO stop. |
| I2 | Body close through the FVG's CE ⇒ FVG failing; close through the far edge ⇒ inverted | `k04 §3.6 R23`, `13. Inversion p13–p14` | **MISSING** | see P4. |
| I3 | One invalidation owner per plan; sizing and management use the same level | `k10 §4.4`; `SKILL.md:55` | **INSTR** | `local-eval-brief.py:105` requires the `m-synth` block to state "điều kiện vô hiệu và chủ sở hữu vô hiệu (Wyckoff hay ICT …)"; `check-model-prose.py` does **not** verify it (it checks head timestamp, verdict set, cite spans, number provenance, HTF consistency, vocabulary purity). |
| I4 | Sons / TTRS / Unicorn state no stops and no targets — do not treat "setup complete" as carrying an invalidation | `k06 §6 item 6`; `SKILL.md:63` | **INSTR** | `SKILL.md:63` "Do not credit 'TTRS setup complete' as if it carried an invalidation — it does not." |

### 1.9 Model step-sequences

| Model | Steps the deck requires | Status |
|---|---|---|
| **OSOK** (`k06 §3.1`, `Model11 p60–p94`) | news filter → Monday rule → daily candle-2/3 closure at POI → weekly profile → 1H CISD → std-dev projection → daily profile (London/NY) → intraday CISD → entry (opposing candle / candle-3 open / candle-4 open) → stop at candle-2 extreme → 2R min → trail | **MISSING** end-to-end. The only fragment present is the event blackout (`demo-pilot.py:188-193, 458, 472-473`), which covers OSOK rule 4 ("never hold through") partially and rule 3 ("no entries in the session before") not at all. |
| **Fractal** (`k06 §3.2`, `Model11 p95–p99`) | HTF candle-2 closure → LTF CISD in HTF candle 2 → HTF candle-2 wick EQ respected → entries in candle 3/4 off opposing candles → candle-3 range EQ → −2/−2.5 then −4 | **MISSING**. No candle-1/2/3/4 numbering, no wick/range equilibrium framework, no CISD. |
| **Sons** (`k06 §3.3`) | DOL on HTF → stop raid on mid TF (wick below prior low, close back above) → displacement + FVG on entry TF → enter the gap retrace; target = the DOL | **PARTIAL**. The coded chain sweep→MSS→FVG (`ict-scan.py:setup_candidate`, `demo-pilot.py:evaluate`) is structurally the closest match: it has the stop raid (`:98-99`), the displacement-leg gap (`:208-211`) and an entry on the gap edge (`:213`). Missing: the three-timeframe separation and the DOL-as-target. |
| **TTRS** (`k06 §3.4`, `TTRS p13–p17`) | killzone → turtle soup sweep → inversion → CISD/OB → FVG → breaker, in order; optional SMT/OTE/premium-discount | **MISSING** (steps 2, 3, 5 absent; killzone gate absent). |
| **Unicorn** (`k06 §3.5`) | breaker + overlapping FVG; entry in the overlap | **MISSING**. |
| **Timeframe Alignment** (`k06 §3.6`) | Bias TF → Structure TF (sweep + CISD) → Entry TF (OB/CISD retest) | **MISSING** as stated; the project substitutes a Wyckoff-bias HTF filter (`htf_context.py`, `demo-pilot.py:244-251`). |

---

## 2. Gap table — sorted by importance for an entry decision

| Rank | Gap | Why it matters at the entry | Status | Cite |
|---|---|---|---|---|
| 1 | **CISD is entirely absent** | It is the trigger in four of the six models (OSOK, Fractal, TFA, TTRS) and the *earliest* confirmation the corpus offers; the system waits for the later, looser MSS instead | MISSING (code **and** SKILL.md) | `k05 §2.3, §3.2 R5/R7`; `k06 §4.5`, `Model11 p44–p48` |
| 2 | **No displacement test on the MSS candle** | Without it, any close through a pivot counts as a structural break; the deck's MSS *requires* an aggressive full-bodied move, generally with an FVG | MISSING | `k04 §2.16, §3.3 R10/R12`, `11. MSS_vs_LG p3–p4` |
| 3 | **Only one of three FVG entry models (IOFED); no CE, no fill; no OTE band; no OB open / mean threshold; no breaker; no unicorn overlap** | The entry price is the single most leverage-sensitive number in the plan, and the corpus gives six named ways to set it. The system offers one. | MISSING / PARTIAL | `k04 §2.23, §3.5 R16–R19`; `k05 §2.5, §3.3 R10–R12` |
| 4 | **The pilot enters at market on the last close, not at any PD array** | `demo-pilot.py:252` `entry = C[-1]` — the discount/premium and sweep tests gate *whether* to trade, nothing sets *where* | CONTRADICTS the entry models | `k04 §3.5`; `k05 §3.3` |
| 5 | **Dealing range = lookback-window extremes, not the BSL↔SSL pair** | Premium/discount, EQ and the fallback target all hinge on it; changing `--n` changes the verdict | CONTRADICTS | `k04 §2.18, §3.4 R15` vs `ict-scan.py:72` |
| 6 | **No "do not trade" filters from OSOK** (Monday, day-prior to high-impact news, session-prior to medium-impact, unclear daily bias, no confirmed CISD, London expansion) | These are hard NO-TRADE rules; only the ±30-min event blackout exists | MISSING | `k06 §3.1 rules 1–4, 7, 18, 19` |
| 7 | **No std-dev projection targets (−2/−2.5/−4/−4.5) and 2R minimum is softened to 1.5R** | Determines exit and therefore expectancy | MISSING / CONTRADICTS | `k05 §3.4 R16–R18`; `k06 §3.1 rule 23` vs `demo-pilot.py:84` |
| 8 | **Killzone windows hardcoded in UTC and inconsistent with `session-model.md`** | The project's own doc names this file as the thing to fix; the drawn window is also the rejected forex set | CONTRADICTS | `session-model.md:21, 37` vs `build-artifact.py:531`, `local-eval-brief.py:30` |
| 9 | **Liquidity universe limited to relatively-equal pivot pairs** | Single old highs/lows, PDH/PDL, PWH/PWL, session highs/lows — the deck's main draws — are invisible to the scanner, so both the sweep detector and the target picker are blind to them | MISSING | `k04 §2.7–2.9, §4` vs `ict-scan.py:104-107` |
| 10 | **Thesis invalidation (body close back beyond the swept level) is not monitored on live setups** | The deck kills the reversal read before the stop is hit; the pilot only holds an OCO | PARTIAL | `k04 §3.6 R25`; `SKILL.md:55` vs `ict-scan.py:165` (anchors only) |
| 11 | **No inversion/IFVG, no CE hold/fail line** | Both a second entry model and an early warning | MISSING | `k04 §2.25–2.26, §3.5 R20, §3.6 R23` |
| 12 | **No IRL↔ERL alternation for target selection** | The deck's stated target logic after a sweep | PARTIAL | `k05 §3.1 R3, §3.4 R20` |
| 13 | **No SMT / relative strength** | Confluence at the sweep and the mitigation-block differentiator | MISSING | `k05 §2.10, §3.2 R9`; `k06 §2.1.1 (p8)` |
| 14 | **No PO3/AMD, no Silver Bullet, no weekly/daily profiles** | Timing and narrative layers | MISSING | `k05 §2.11, §2.15`; `k06 §2.5.4, §2.5.6` |
| 15 | **Swing definition 3 bars/side vs the deck's 1 bar/side** | Changes which pivots exist and therefore every downstream level | CONTRADICTS (declared as a project param) | `k04 §4` vs `ict-scan.py:78` |
| 16 | **No expectancy / win-rate × RR gate** | The deck's own profitability test | MISSING | `k04 §2.3, §3.1 R4` |

---

## 3. Contradictions between implementation and the decks

1. **Swing pivot width.** Deck: "a high with a lower high to the left and right" — one candle each side (`k04 §4`, `3. Liquidity p3 (1)`). Code: `ict-scan.py:78` and `build-artifact.py:506` use three candles each side. Declared as a project parameter (`ict-scan.py:26`), so it is a *documented* deviation, but every level in the system inherits it.

2. **Dealing range anchors.** Deck: "An easy way to view a range is to look for where sell side and buyside liquidity is resting" (`k04 §2.18`, `8. D&P p3 (1)`); R15 makes the nearest swing-high/swing-low pair the range. Code: `ict-scan.py:72` `lo, hi = min(L), max(H)` over the lookback window. Not declared as a deviation anywhere.

3. **Order Block geometry.** Deck: the OB is the **open price line** of the last opposing-close candle, with the body midpoint as the "mean threshold" deeper-entry line (`k05 §2.5`, `17. Orderblocks p3 (1), p7 (5)`). Code: `build-artifact.py:526-527` builds a zone from the candle's **low to its body top** (bull) with no mean threshold, and nothing outside the drawing layer consumes it.

4. **MSS without displacement.** Deck: MSS = *displacement* closing beyond structure (`k04 §3.3 R10`; `k05 §3.2 R4`). Code: a bare close beyond the last pivot (`ict-scan.py:122-125`). Consequence: the system can print "MSS" on a doji that ticks one cent through a pivot.

5. **Killzone windows.** `build-artifact.py:531` draws LDN 06–09Z and NY AM 11–14Z; `local-eval-brief.py:30` tells the model the same. `docs/architecture/session-model.md:21` states that hardcoded UTC hours are wrong and names `local-eval-brief.py` explicitly; §2 defines `london` as 08:00–11:00 Europe/London and `ny_am` as 08:30–11:00 America/New_York (the indices set), and §37 records that the forex NY AM set was deliberately rejected. 11–14Z is the forex set's summer conversion. So the drawing contradicts both the project's decision and (for London) any conversion of it.

6. **Minimum R:R.** Deck: "2R is the minimum requirement before taking profit" (`k06 §3.1 rule 23`, `Model11 p92`). Code: `demo-pilot.py:84` `MIN_RR = 1.5`.

7. **Timeframe pairing.** Deck table pairs 4H with Weekly (`k06 §2.3`, `Model11 p44`). `automation.py:95` pairs `4h` with `swing` (1D).

8. **"m-ict must not mention volume" vs the coded MSS fact.** `local-eval-brief.py:104` forbids the ICT block from mentioning volume (correct per `k10 §4.1`), yet the scanner attaches `vol_mult` to every MSS (`ict-scan.py:123`) and the brief prints it on the MSS line (`local-eval-brief.py:135`). Not a deck contradiction, but a self-consistency trap for the model: the number is served inside the ICT fact it may not discuss.

---

## 4. "Do NOT trade" rules in the decks, and whether the system honours them

| Deck prohibition | Source | Honoured? |
|---|---|---|
| **Monday: no trading, in all scenarios** | `k06 §3.1 rule 1`, `Model11 p66` | **NO.** No day-of-week check in any script. |
| **No trades the day prior to a high-impact event (CPI, NFP, FOMC Press Conf.)** | `k06 §3.1 rule 2`, `Model11 p64` | **NO.** `demo-pilot.py:188` `event_blackout()` reads `docs/architecture/event-calendar.md` with a ±30-minute window only (module docstring line 18). |
| **No trades in any session prior to a medium-impact event; only after the release** | `k06 §3.1 rule 3`, `Model11 p64` | **NO.** Same ±30-minute window. |
| **Never hold a position through a high/medium-impact release** | `k06 §3.1 rule 4`, `Model11 p64` | **PARTIAL.** The blackout blocks new entries (`demo-pilot.py:472-473`) but nothing closes an open position ahead of a release. |
| **If the next daily candle cannot be anticipated with a clear one-sided expectation → no entries that day** | `k06 §3.1 rule 7`, `Model11 p70` | **PARTIAL / different mechanism.** `demo-pilot.py:250-251` refuses when the HTF Wyckoff bias does not match the side, and `htf_context.py` returns neutral mid-range in Phase B — a Wyckoff-sourced analogue, not the deck's rule. |
| **If candle 2 failed to close back inside candle 1 → do not participate in candle 3** | `k06 §3.1 rule 6`, `Model11 p30` | **NO.** Candle numbering is not implemented. |
| **No confirmed CISD → no entry** ("As there is yet to be a confirmed CISD, no entry is to be taken") | `k06 §3.1 rule 19`, `Model11 p108` | **NO.** CISD is absent; the analogue gate is "sweep + MSS + FVG" (`demo-pilot.py:218-232`), which is a different and later condition. |
| **If London expands in either direction → avoid New York participation** | `k06 §3.1 rule 18`, `Model11 p87` | **NO.** No session logic in the pilot at all. |
| **If the weekly profile is unclear → wait for another daily candle** | `k06 §3.1 rule 13`, `Model11 p72` | **NO.** |
| **Ignore opposing-close candles not paired with a POI** | `k06 §2.1.1`, `Model11 p6` | **N/A** — opposing candles are not detected. |
| **Ignore PD arrays in the wrong half of the range** | `k04 §3.4 R14`, `8. D&P p6–p7` | **PARTIAL.** The *price* must be in the right half (`demo-pilot.py:212-215`), but the FVG that defines the entry is not required to be (`ict-scan.py:207` computes `in_discount` and never uses it). |
| **Wick-only break is a liquidity grab, not a trend change — do not treat it as MSS** | `k04 §3.3 R11` | **YES.** `ict-scan.py:98-99` + the emitted prose at `:269-271`; the pilot requires a separate MSS close (`demo-pilot.py:222-223`). |
| **Do not project beyond −4 (max expansion)** | `k05 §3.4 R18` | **N/A** — projections not implemented. |
| **RS/RW ratio reversal is "My Theory" — not a standalone trigger** | `k05 §3.5 R24` | **N/A** — not implemented. |
| **Sons / TTRS / Unicorn carry no stop or target — do not treat "setup complete" as carrying an invalidation** | `k06 §6 item 6` | **YES (instruction).** `SKILL.md:63`. |
| **Volume Profile abandon rule overrides a good location** | `k08 §5 Step 4` via `SKILL.md:24` | **INSTR.** `SKILL.md:24` "the thesis is dead and a good-looking location does not revive it". No code enforces it. |
| **Reject "CHOCH" / bare "BOS" as ICT observations** | `SKILL.md:45-48`; `k10 §4.3` | **PARTIAL/CODE.** `method_purity.py:28` lists `\bBOS\b` among ICT terms — which *forbids it in Wyckoff blocks* rather than forbidding it in ICT blocks. `CHoCH` is in `WYCKOFF_ACRONYMS` (`method_purity.py:35`), so it is correctly blocked inside `m-ict`. Bare "BOS" inside an `m-ict` block is **not** blocked. |

---

## 5. What the system does implement faithfully

For balance, these are correct against the source:

- FVG detection, wick-based, 3-candle, both polarities — `ict-scan.py:84-85` ≡ `k04 §2.21`, `12. FVG p3–p4`.
- Liquidity grab / failure-to-displace test (wick beyond, close back inside) — `ict-scan.py:98-99` ≡ `k04 §3.3 R11`.
- MSS by **close** (not wick) beyond the swing — `ict-scan.py:122-125` ≡ `k04 §3.3 R10` (body-close half of the rule).
- Stop raid **before** the break, enforced rather than merely preferred — `ict-scan.py:201`, `demo-pilot.py:218-223` ≡ `k05 §3.1 R2`.
- Longs only in discount, shorts only in premium — `demo-pilot.py:212-215` ≡ `k04 §3.4 R13`.
- Position sizing `risk / stop distance` — `demo-pilot.py:270-271` ≡ `k04 §3.1 R3`.
- The "no volume in the ICT dimension" rule from `k10 §4.1` — enforced by `method_purity.py:36-46, 58`.
- Every project-defined threshold (0.08% equal-level tolerance, 0.6× median FVG size, 3-bar pivot, 1.5× volume,
  `same_level_tolerance_atr`, timing weights) is labelled as a project parameter rather than passed off as sourced
  — `ict-scan.py:26`, `ict-scan.py:314`, `analysis-params.json:2, 49, 81`.

---

## 6. Caveats on this audit

- Deck page numbers are reproduced from `knowledge/04`–`06`; the PDFs in `docs/TTrades PDFs/` were not opened.
- `scripts/build-artifact.py` was read only around `ictAnalyze` (lines 498–536) and the legend/glossary
  (lines 290–320, 640–660); a rule implemented elsewhere in that 829-line file would have been missed.
- `scripts/demo-pilot.py` was read at lines 1–110 and 203–323; the order-management tail (lines 323–485) was
  skimmed via grep for `blackout`/`event` only.
- No runtime verification was performed (no scanner run, no backtest execution). All statements are static reads.
