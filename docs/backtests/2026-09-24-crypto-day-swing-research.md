# Crypto day (1H) / swing (4H) — /improve research proposal — 2026-09-24

_Controlled-improvement procedure (`.claude/commands/improve.md`, CLAUDE.md §41–§46). Evidence only: nothing here
changes `pilot-top20.json`, `methods.json`, `trading-systems.json` or `improve-candidates.json`. Every
recommendation below is a proposal for a human decision (§41 stage 11)._

**Question.** Crypto day (1H) and swing (4H) have no eligible pilot setup. Selection bar (user decision
2026-09-13, `scripts/rank-setups.py` `solvent()` + `main_horizons()`): on the last-365-day window a rule must be
not ruined, profitable (`ann > 0`), and have ≥ 15 trades (day) / ≥ 6 trades (swing) across the 9 crypto symbols.
The user chose "research new rules" over lowering the bar.

**Answer in one paragraph.** No declared candidate produces a *robust* day or swing setup. On 1H nothing passes
the bar at all. On 4H, WYCKOFF-BOOK config B (maker fee + breakeven at +1R, no HTF filter) — the *baseline*, not a
candidate — technically passes on current code (1y n=10, +1.3 %/yr, DD 5.1 %), as does the declared `via=fvg`
candidate (min R:R 3, n=6, +2.4 %/yr). Both rest on **one** winning trade (VIRTUALUSDT long 2025-10-24, +6.7R);
the nine trades since then are 0 wins / 4 breakeven / 5 losses, calendar 2026 YTD is −5.1 %, and only 29 % of
quarters are positive over four years. That is a pass by the letter of the bar and a failure of §45's robustness
check. ICT is starved of trades on both timeframes (1H n=3, 4H n=1 over 4 years); a gate-by-gate funnel shows why
and motivates three new, knowledge-grounded candidates (§5), which are proposed but **not** run.

---

## 1. Runs performed

| Run | Command (all `--market crypto --symbols BTCUSDT,ETHUSDT,SOLUSDT,ASTERUSDT,VIRTUALUSDT,SUIUSDT,TAOUSDT,RENDERUSDT,ONDOUSDT`) | Wall time | Report |
|---|---|---|---|
| 1H ICT | `improve-loop.py --tf 1H --method ICT` | 656 s | [2026-09-24-improve-crypto-1H-ict.md](2026-09-24-improve-crypto-1H-ict.md) |
| 1H WYCKOFF-BOOK | `improve-loop.py --tf 1H --method WYCKOFF-BOOK` | 258 s | [2026-09-24-improve-crypto-1H-wyckoff-book.md](2026-09-24-improve-crypto-1H-wyckoff-book.md) |
| 4H ICT | `improve-loop.py --tf 4H --method ICT` | 111 s | [2026-09-24-improve-crypto-4H-ict.md](2026-09-24-improve-crypto-4H-ict.md) |
| 4H WYCKOFF-BOOK | `improve-loop.py --tf 4H --method WYCKOFF-BOOK` | 64 s | [2026-09-24-improve-crypto-4H-wyckoff-book.md](2026-09-24-improve-crypto-4H-wyckoff-book.md) |

Full history, no `--bars` (one `--bars 300` smoke test went to a scratch store, not `docs/experiments/`). All four
exited 0. Sealed experiment records (`decision: PENDING`):

- `docs/experiments/2026-09-24-improve-crypto-1H-wyckoff-book-session-asia.json`
- `docs/experiments/2026-09-24-improve-crypto-1H-wyckoff-book-session-london.json`
- `docs/experiments/2026-09-24-improve-crypto-1H-wyckoff-book-session-ny_pm.json`
- `docs/experiments/2026-09-24-improve-crypto-1H-wyckoff-book-method-WYCKOFF-BOOK.json`
- `docs/experiments/2026-09-24-improve-crypto-4H-wyckoff-book-session-london.json`
- `docs/experiments/2026-09-24-improve-crypto-4H-wyckoff-book-method-WYCKOFF-BOOK.json`

ICT produced no loss cluster ≥ `min_size=3` on either timeframe, so no ICT candidate ran and no ICT record exists.

## 2. What improve-loop measured (full history, its own default config)

improve-loop's baseline is fee 0.05 %/side, no management, no HTF filter (≈ stability config A), over the **full**
history (2022-09 → 2026-09). It does not compute the 1y window the selection bar uses — see §3 for that.

| TF / method | Baseline n | Expectancy (R) | PF | Max DD | Loss clusters | Candidates run → result |
|---|---|---|---|---|---|---|
| 1H ICT | 3 | −1.04 | 0.0 | 3.1 % | none | none |
| 1H WYCKOFF-BOOK | 154 | −0.24 | 0.74 | 35.1 % | off 87, asia 12, london 10, ny_am 9, ny_pm 3 | `session=asia` n=30 exp −0.11 (only "outperformer", still negative); `session=ny_pm` n=23 −0.47; `session=london` n=12 −0.37; `method=WYCKOFF-BOOK` n=1 |
| 4H ICT | 1 | −1.02 | 0.0 | 1.0 % | none | none |
| 4H WYCKOFF-BOOK | 41 | +0.15 | 1.19 | 12.8 % | off 24, london 5 | `method=WYCKOFF-BOOK` n=0; `session=london` n=0 |

Validation state of every record: `in-sample only: no OOS period carved out (§44)` —
`scripts/research_ledger.py periods()` reports `validation_available: false` (both crypto and CFD history are
`development`). `robustness_results` is `unavailable` on every record (no walk-forward / perturbation run).

## 3. The selection bar on the 1y window (current code)

The stability files the brief quoted (`data/history/stability/crypto-*.json`, generated 2026-09-19/20) no longer
match the current engine + data: e.g. 1H WYCKOFF-BOOK config A 1y n is 18 there and **61** now; 4H WYCKOFF-BOOK
config B 1y n is 2–4 there and **10** now. I did not establish the cause (the files are dated around commit
`05859c4` "causal Wyckoff backtest"; not verified). So baseline and every declared candidate were re-measured with
a scratch evaluator that reuses `scripts/stability-report.py`'s own `CONFIGS`, `config_fee()` and `metrics()`
(identical `w1y` construction: entries ≥ last bar − 365 days) and applies each declared override the way
improve-loop does (`sessions` → `simulate(sessions=)`, other keys → `bt.OPTS`). "Qualifies" = no ruin, ann > 0,
n ≥ 15 (1H) / ≥ 6 (4H); the ≥ 90-day window condition holds for every row.

Rows that change anything (the full 54-row table is summarised: `vol_type=*` rows equal baseline ±2 trades because
every 1H/4H WYCKOFF-BOOK trade is a Phase-D / LPS[C] entry with `vol_type=None` — the typed-Spring leg never fires):

| TF | Cfg | Variant | Full n | Full %/yr | 1y n | 1y %/yr | 1y DD | Ruin | Qualifies |
|---|---|---|---|---|---|---|---|---|---|
| 1H | A | baseline | 154 | −9.4 % | 61 | −13.5 % | 23.3 % | — | no |
| 1H | B | baseline | 155 | −1.6 % | 61 | −5.5 % | 16.2 % | — | no |
| 1H | C | baseline | 26 | −2.1 % | 13 | −1.9 % | 4.2 % | — | no |
| 1H | B | session=asia (keep london/ny_am/ny_pm) | 31 | +1.8 % | 13 | +1.0 % | 3.1 % | — | no (n<15) |
| 1H | B | session=london (ny_am only, R:R≥3) | 9 | −0.1 % | 6 | +0.8 % | 2.1 % | — | no (n<15) |
| 1H | B | via=fvg (R:R≥3) | 128 | −1.4 % | 52 | −6.4 % | 14.4 % | — | no |
| 1H | any | method=WYCKOFF-BOOK (HTF on, no Phase D) | 1 | −0.3 % | 0 | — | — | — | no |
| 4H | A | baseline | 41 | +1.2 % | 10 | −3.0 % | 9.1 % | — | no |
| **4H** | **B** | **baseline** | 41 | +2.2 % | **10** | **+1.3 %** | 5.1 % | — | **YES** |
| 4H | C | baseline | 4 | −0.8 % | 1 | −0.0 % | 0.0 % | — | no |
| 4H | A | via=fvg (R:R≥3) | 34 | +2.1 % | 6 | +1.1 % | 5.2 % | — | YES (n = bar) |
| **4H** | **B** | **via=fvg (R:R≥3)** | 35 | +1.9 % | **6** | **+2.4 %** | 4.1 % | — | **YES (n = bar)** |
| 4H | any | session=london (ny_am only) | 0 | — | 0 | — | — | — | no — structurally inert (see §4) |
| 4H | any | method=WYCKOFF-BOOK | 0 | — | 0 | — | — | — | no |

### Overfit / robustness check on the 4H passes

- **Trade list, 4H WYCKOFF-BOOK config B, 1y window** (entry time, symbol, side, outcome, net R): 2025-10-24 VIRTUAL
  long **win +6.70**; 2026-01-08 ASTER long BE; 2026-03-04 VIRTUAL long loss −1.01; 2026-03-31 BTC short BE;
  2026-04-07 ONDO short loss; 2026-04-30 SOL short loss; 2026-05-21 ASTER long BE; 2026-06-20 TAO long BE;
  2026-07-05 ONDO long loss; 2026-08-09 SUI short loss. **1 win in 10.** Leave-that-one-out: −5.1R. The `via=fvg`
  row is the R:R ≥ 3 subset of the same list (VIRTUAL win + BTC BE + 4 losses).
- **Calendar years** (full history, config B): 2023 −2.1 %, 2024 −8.3 %, 2025 +28.3 %, 2026 YTD −5.1 %. Positive
  quarters 29 %. The 1y window is positive only because it still contains 2025-Q4; moving it ~6 weeks forward
  (dropping 2025-10-24) makes it negative.
- **Sample size**: 10 (resp. 6) trades cannot distinguish +0.15R expectancy from zero; the full-history 41 trades
  have win rate 22 % and PF 1.19 (improve-loop baseline).
- **OOS / walk-forward**: none available (§44 ledger has no untouched period; improve-loop records no robustness run).
- **Multiple testing (§43)**: improve-loop sealed 6 candidate records; in addition this research ran **54 unrecorded
  scratch evaluations** (9 variants × 3 configs × 2 TFs, WYCKOFF-BOOK) plus two ICT gate-count diagnostics (counts
  only, no outcomes). The best-of-54 on a single dataset passing a 6-trade bar is exactly the pattern §43 warns
  about. The ledger's pre-existing unrecorded searches (7 ICT target variants, 120→6 ranking rows) also apply.

**Consequence to flag:** if `stability-report.py` is re-run on current code and `rank-setups.py --horizons
--window 1y` is re-run after it, the mechanical rule would very likely put 4H WYCKOFF-BOOK config B into the swing
slot. That selection would rest on the single VIRTUAL trade above. Decide on that before regenerating the pilot.

## 4. Defects / caveats found in the tooling (not fixed — scripts are out of scope)

1. **improve-loop baseline line prints the wrong `refused` / `failed_by`.** `_report()` reads `bt.SIM_LAST` after
   the candidates have run, so the baseline line shows the *last candidate's* counters — e.g. 4H WYCKOFF-BOOK
   "Baseline … n=41 … refused={'session': 41}" although the baseline had no session gate
   (`scripts/improve-loop.py` `_report`, the `**Baseline**` f-string).
2. **Session candidates are inert on 4H.** 4H bars open at 00/04/08/12/16/20 UTC, i.e. 20/00/04/08/12/16 New York
   (EDT) or 19/23/03/07/11/15 (EST); none falls inside `ny_am` 08:30–11:00 NY (`docs/architecture/sessions.json`),
   so `session=london` (ny_am only) can never admit a 4H trade. Session labels on 4H describe the bar-open instant,
   not the session a 4-hour bar spans.
3. **`vol_type=*` candidates are inert on 1H/4H**: no trade carries a volume type (all are Phase-D / LPS[C] entries).
4. **`method=WYCKOFF-BOOK` candidate removes almost everything on 1H/4H** (n=1 / 0): its `why` was measured on 1H
   config B→C in an earlier engine; with Phase D dropped there is no entry leg left on these timeframes.
5. **Stale stability files** (§3) — the numbers in `data/history/stability/crypto-*.json` do not reproduce on current
   code; any ranking decision should be preceded by regenerating them.

## 5. Why ICT has no trades — gate-by-gate funnel (counts only, no outcomes)

Scratch diagnostic mirroring `ict_setups_live()` gate by gate, counting each distinct (side, sweep, MSS) setup once
at the first bar it is visible (live window, live bias, `fvg_fill` "already triggered" rule, net-of-fee R:R floor 2.0):

| Gate (first failure) | 1H all | 1H 1y | 4H all | 4H 1y |
|---|---|---|---|---|
| Sweep → MSS visible | 2568 | 1018 | 636 | 272 |
| no displacement on the break (R10/R11 — mandatory, not a candidate) | 1262 | 511 | 310 | 149 |
| displaced, but **no same-direction FVG** after the sweep | 1105 | 432 | 276 | 107 |
| complete, but **PD gate fails** (close not in discount/premium) | 173 | 63 | 41 | 12 |
| HTF bias neutral / disagrees | 5 | 2 | 3 | 3 |
| limit already triggered at detection | 3 | 2 | 0 | 0 |
| limit never filled | 14 | 7 | 5 | 1 |
| R:R below floor (net) | 3 | 0 | 0 | 0 |
| **admissible today** | **3** | **1** | **1** | **0** |
| PD-fail setups whose **entry (FVG near edge)** is in the correct half, bias agrees, and would be admissible | +26 | +5 | +7 | +2 |

Reading: 93 % of 1H setups die on displacement or on the missing FVG; of the setups that do complete, 84 % (1H 1y:
63/75) die on the PD gate, which `scripts/ict-scan.py` evaluates on the **current close** (`pct = (last − lo)/(hi − lo)`)
rather than on the entry price. The declared ICT-relevant candidates (sessions, R:R 3) can only remove trades.

## 6. Proposed new candidates (≤ 3, not implemented)

Each needs (a) a human decision to declare it (and, for P1/P2, an engine knob), (b) a pre-registered test design,
and (c) Trading System version consideration (§47/§59) before any live use. None lowers the R:R floor, the risk
ceiling or the selection bar.

### P1 — ICT: judge premium/discount on the entry array, not on the current close
- **Grounding.** `knowledge/ict/core-a.md` §3.4 **R13** (line 207): "IF you intend to long, THEN require **entry** in
  the discount"; **R14** (line 208): "IF a **PD array** (OB, FVG, …) lies in the discount, THEN it frames a long".
  Both rules locate the *entry / PD array*, not the price at the moment of detection. The current gate
  (`scripts/ict-scan.py` `setup_candidate`, `pd_ok = a["pct"] < 0.5`, with `pct` from the last close) is stricter
  than the source whenever displacement has already carried price out of the discount — which is what displacement
  does.
- **Why more trades, no look-ahead.** The FVG near edge and the dealing range are both known at the detection bar;
  the limit is still placed at bar `i` and filled from `i+1`. Funnel: +26 admissible setups on 1H over 4 years
  (3 → 29) and +7 on 4H (1 → 8); on the 1y window 1H 1 → 6 and 4H 0 → 2. **Not enough on its own for either slot**
  (15 / 6) — but it is the largest fidelity-preserving lever after P2.
- **Semantics impact.** This changes the LIVE ICT path for every timeframe including the 15m scalping systems
  (the backtest calls the live scanner) — version-significant (§59); must be decided for all ICT systems, not only
  1H/4H.
- **Experiment.** Add an explicit OPTS/scanner switch `pd_basis ∈ {close, entry}` (default `close`), declare it in
  `improve-candidates.json`, run improve-loop + the 1y evaluator on 1H/4H/15m; pre-register the success criterion
  (bar met AND ≥ 2 of 3 calendar years positive AND leave-best-trade-out still > 0) before looking at outcomes.

### P2 — ICT: Order Block as the entry array when a displaced MSS leaves no FVG
- **Grounding.** `knowledge/ict/core-a.md` **R12** (line 204): after displacement "expect an FVG … ('generally')" —
  not always; **R14** (line 208) names the OB as a PD array alongside the FVG; `knowledge/ict/core-b.md` §2.5
  (17. Orderblocks p3–p8): OB = last opposing-close candle before the displacement, entry reference the OB open,
  mean threshold at the body midpoint (p7), stop at the OB body or the raid swing (p8). `setup_candidate()`
  already computes `ob` for every complete setup.
- **Why more trades, no look-ahead.** "Displaced but no FVG" is the second-largest kill (1H 1y: 432 of 1018;
  4H 1y: 107 of 272). These setups already passed the mandatory displacement test; the OB is formed before the MSS
  bar, so a limit at its open/mean threshold is placeable at the detection bar exactly like the FVG limit. PD (P1 or
  current), bias, already-triggered, fill and R:R gates stay unchanged.
- **Experiment.** Entry-model switch `ict_array ∈ {fvg, fvg_or_ob}`; OB entry at the open (p3) with mean threshold
  (p7) as a second pre-declared variant only — two variants, counted as two candidates. Same pre-registered
  criteria as P1; report P1, P2 and P1+P2 separately (three candidates, one family).

### P3 — WYCKOFF-BOOK 1H: turn on the book's own đối nhãn gates (existing knobs, no engine code)
- **Grounding.** `knowledge/wyckoff/advance.md` **WA2-34** (line 1105, WA p150/p166): ST[A] in the lower third /
  breaking SC is an early sign of *distribution*, not accumulation; **WA2-35** (line 1106, WA p154/p157): Phase B
  that keeps testing the bottom signals weakness. `scripts/backtest-methods.py` already records both signs on every
  structure and exposes them as `st_gate` (D1) and `phase_b_gate` (D2), both off by default.
- **Why it fits the 1H slot.** 1H WYCKOFF-BOOK does not lack trades (1y n=61 vs the bar of 15) — it lacks edge
  (−5.5 to −13.5 %/yr). Refusing structures whose own đối nhãn signs contradict the label is a knowledge-grounded
  quality cut with ~4× headroom above the trade bar; it removes trades, uses only signs known by the entry bar, and
  needs no new code. (It does not help 4H, which has no headroom.)
- **Experiment.** Declare it (improve-candidates.json keys candidates by cluster field; the natural key is
  `method=WYCKOFF-BOOK`, which today holds the inert HTF/no-Phase-D candidate — replacing or adding a key is a human
  edit). Run D1, D2, D1+D2 as three candidates under configs A/B, same pre-registered criteria.

### Considered and not proposed
- Lowering the R:R floor or dropping displacement: excluded (risk rule / R10–R11 mandatory).
- TTrades Fractal / CISD trigger with Daily→1H and Weekly→4H pairing (`knowledge/ict/models.md` §2.3, §3.6): grounded
  and likely count-raising, but it is a new setup family needing a lower-timeframe CISD engine; deferred behind P1/P2.
- Wyckoff re-accumulation / re-distribution structures (`knowledge/wyckoff/advance.md` §2.9–§2.10, WA2-28…30): would
  raise 4H count, but `scripts/wyckoff_rules.py` only detects structures after a downtrend (`downtrend_swings`) — a new
  detector, larger than the three above.

## 7. Recommendation per candidate

| Candidate | TF / method | Recommendation | Reason |
|---|---|---|---|
| `session=asia` | 1H WB | **REJECT** | full-history exp −0.11R (A); 1y n=13 < 15 even in config B |
| `session=ny_pm` | 1H WB | **REJECT** | n=23, exp −0.47R |
| `session=london` | 1H WB | **REJECT** | n=12, exp −0.37R |
| `session=london` | 4H WB | **REJECT** | structurally zero trades on 4H (§4.2) |
| `method=WYCKOFF-BOOK` (HTF on, no Phase D) | 1H / 4H WB | **REJECT** | n=1 / 0 |
| `vol_type=1/2/3` | 1H / 4H WB | **REJECT (not applicable)** | inert: no typed-Spring trades on these TFs |
| `via=fvg` (R:R ≥ 3) | 4H WB | **TEST** (forward only) | passes bar at n=6 exactly; same single-win dependence as baseline |
| 4H WB config B baseline (not a candidate) | 4H WB | **KEEP out of the slot / TEST forward** | passes by the letter (n=10, +1.3 %/yr) but 1 win in 10, 2026 YTD −5.1 %, 29 % positive quarters, no OOS — do not ADOPT |
| ICT baseline | 1H / 4H | **KEEP** | no cluster, no candidate; n=3 / 1 |
| P1 PD on entry array | ICT (all TFs) | **TEST** | grounded fidelity fix, largest non-FVG lever; live-semantics change → human + versioning decision |
| P2 OB when no FVG | ICT 1H / 4H | **TEST** | targets the 42 % "displaced but no FVG" pool; needs an engine switch |
| P3 đối nhãn D1/D2 gates | 1H WB | **TEST** | existing knobs; needs only a declaration |

No candidate is recommended for **ADOPT**. Nothing currently fills the day slot; the swing slot can only be filled
by a result that would not survive a leave-one-out check.

**Next action (human):** (1) decide whether a 1-win-in-10 pass should be allowed to fill the swing slot before
regenerating stability files; (2) if P1/P2/P3 are wanted, carve a forward OOS period now (research ledger
`oos_untouched`, e.g. from 2026-09-24), declare the candidates, then run them — every historical span is already
`development`.
