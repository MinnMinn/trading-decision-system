# Wyckoff 1m backtest scan: why it is >100x slower than the live read (2026-10-01)

Status: investigation (timings and counts only; no R / expectancy read). Branch `b8-wyckoff-1m-profile`, base
`windows-migration` 85bbc08. Machine: 12 cores, serial runs (1 process each, <= 3 concurrent), Python 3.14.

## 1. Answer in five lines

1. OBSERVED. The slowdown is **not** the per-window Wyckoff detection. Without one key the fund-search Wyckoff scan costs
   ~0.15 ms/bar marginal (0.18 ms/bar at 160k bars), linear, i.e. the same order as the live read's ~0.3 ms.
2. OBSERVED. The key is `fx_w7_htf_target`, which `fund-search.fixed_opts()` turns on for every cell
   (`scripts/fund-search.py:79-81`, `:106-112`). Per Phase-D fire it calls `_htf_wyckoff_target()`
   (`scripts/backtest-methods.py:814`, call site `:1215`), which re-runs the Wyckoff detector over the **whole 5m history
   before the decision time** (1m's higher rung, `HTF_OF`, `:679`). The live path never sets this key.
3. OBSERVED. The 5m series starts 2004-06-11, eight years before the 1m series (2012-05), so the prefix is already
   ~492k bars at the first 1m bar and ~1.31M at the end of the dev span. Detector cost on that prefix is **super-linear**
   (measured exponent ~1.9 in prefix length): 23.6 s at 492k bars, 155 s at 1.31M bars, per call, per side.
4. OBSERVED/INFERRED. The super-linearity is one loop in `wyckoff_rules.detect_accumulations` that re-scans all swings
   from bar 0 for every candidate SC (`prior = []` loop). Walking back from the SC instead (byte-identical, prototyped on
   this branch) cuts a detection on the 1.31M-bar prefix from 168 s to 5.2 s (long+short, all four detection keys on).
5. The prototype brings the w7 scan from ~45 ms/bar to ~4.5-5.6 ms/bar (measured on 5k-40k slices); it is still ~25x the
   no-w7 cost, so a second change (section 6) is needed to reach linear cost. Extrapolation, full 4.1M bars:
   ~178 CPU-h before, ~6 CPU-h with the prototype, ~11 CPU-min without w7.

## 2. Method

- Harness: `scripts/research/profile_wyckoff_1m.py` (scan_many with `workers=1` and ONE overlay = the path
  `BtEngine.prefetch` runs per worker chunk; `--fixed` = the overlay is `fund-search.fixed_opts()`; `--no-w7` drops
  `fx_w7_htf_target`; `--time-htf` records every `_htf_wyckoff_target` call; `--cprofile`).
  Data: `BT_HISTORY_ROOT=data/history/ftmo`, `bt.pit_cutoff("2024-03-01T00:00:00Z")`, XAUUSD 1m, first N bars of the
  PIT-truncated series (`bt.load` wrapped to return `c[:N]`; the higher-timeframe series is NOT truncated, as in the real
  run). Timings exclude the load (8.5-9.8 s, reported by the script as `load_secs`).
- "First value set" = the baseline overlay (no grid key set) plus the fixed keys; the grid's own keys
  (`docs/architecture/v-grid-wyckoff.json`) only add gating/window variants and are not needed to show the cause.
- Prefix-cost probe: `scripts/research/htf_target_cost.py` (one `_htf_wyckoff_target` body at chosen decision times, split
  into `series_as_of` and detection). Byte-identity probe: `scripts/research/ab_wyckoff_detect.py` (original
  `wyckoff_rules.py` from 85bbc08 vs working tree, same inputs, sha256 of `json.dumps(records, sort_keys=True)`).
- Raw logs: `/tmp/b8-*.log` (list in section 8).

## 3. Scaling (OBSERVED)

Seconds for the scan only; s/bar = seconds / N. `n/a` = not run / killed at the 10 min limit.

| N bars | Wyckoff v1 overlay (no fixed keys) | Wyckoff fixed keys **without** w7 | Wyckoff fixed keys **with** w7, original code | Wyckoff fixed keys with w7, prototype | ICT fixed keys |
|---:|---:|---:|---:|---:|---:|
| 5 000 | 4.96 s (0.99 ms) | n/a | **223.1 s (44.6 ms)** | 34.2 s (6.8 ms) | 7.13 s (1.43 ms) |
| 10 000 | n/a | n/a | n/a | 55.8 s (5.6 ms) | 10.11 s (1.01 ms) |
| 20 000 | 6.99 s (0.35 ms) | 7.35 s (0.37 ms) | **> 590 s (> 29 ms), killed** | 99.8 s (5.0 ms) | 15.98 s (0.80 ms) |
| 40 000 | n/a | 10.17 s (0.25 ms) | n/a | 179.7 s (4.5 ms) | 28.14 s (0.70 ms) |
| 80 000 | n/a | 16.2 s (0.20 ms) | n/a | n/a | 51.4 s (0.64 ms) |
| 160 000 | 24.49 s (0.15 ms) | 28.17 s (0.18 ms) | n/a | n/a | 98.5 s (0.62 ms) |

Reading:

- Without w7 and for ICT, cost is **linear with a fixed offset** (~4-5 s of set-up for Wyckoff): log-log exponent
  0.65 (Wyckoff) and 0.87 (ICT) over 20k-160k is the offset, the marginal cost is constant (Wyckoff 0.14-0.15 ms/bar
  between every pair of slices; ICT 0.58-0.61 ms/bar). No forward-walk, list-rebuild or per-fire O(n) term shows up:
  `walk()` is bounded by the horizon `HZ = 144` (`backtest-methods.py:513-`, called with `HZ` at `:1300/:1305`), and
  the `horizon` value `n` ("none" time stop, `:931`) exists only in the ICT path.
- With w7 (original code) the scan is ~45 ms/bar on 5k bars (13 `_htf_wyckoff_target` calls, 201.8 s in them, 15.5 s
  mean) and did not finish 20k bars in 590 s. That is ~250x the no-w7 cost on the same bars and is the only
  non-linear term found.
- With the prototype the w7 scan is ~linear in N (exponent 0.80 incl. fixed offset; marginal 4.0 ms/bar between 20k
  and 40k) because the number of HTF calls is linear in N (measured 13 / 22 / 43 / 80 calls for 5k / 10k / 20k / 40k
  bars = ~2.0-2.6 per 1000 bars) and the prefix barely grows inside a 40k-bar (~1 month) slice.
- The cost of one HTF call grows with the decision date, not with N: section 4.

## 4. One `_htf_wyckoff_target` call vs HTF prefix length (OBSERVED, XAUUSD 5m, `htf_target_cost.py`)

`series_as_of` = `pit.series_as_of(c, "5m", decision_time)` over the whole 1.32M-bar 5m series (O(total), ~0.6 s, the
same on every call). Detection = `wyckoff_records(side="long")` on the prefix (short side adds about the same).

| Decision time | 5m prefix bars | `series_as_of` | detect long, original | detect long, prototype |
|---|---:|---:|---:|---:|
| 2005-06-01 | 51 414 | 0.59 s | 0.49 s | 0.13 s |
| 2008-06-01 | 228 619 | 0.58 s | 5.08 s | 0.49 s |
| 2012-06-01 | 492 242 | 0.59 s | 23.6 s | 0.58 s (after 2nd edit; 1.97 s after 1st) |
| 2016-06-01 | 772 096 | 0.59 s | 52.7 s | 3.73 s (1st edit) |
| 2020-06-01 | 1 052 871 | 0.61 s | 95.1 s | 6.32 s (1st edit) |
| 2024-02-01 | 1 311 083 | 0.59 s | 155.3 s | 2.39 s |

Original exponent over 492k-1.31M bars: **1.91** (quadratic). Prototype exponent (492k -> 1.31M): 1.45.
The 1m series begins 2012-05-03, so every 1m decision in the dev span sees a prefix of at least ~492k bars.

## 5. Hotspots (cProfile, file:line)

Both profiles are inflated ~1.3-2x by cProfile. Paths are relative to `scripts/`.

**(a) Fixed keys incl. w7, original code, first 1 500 bars** (139 s; the 80k slice cannot be profiled with w7 on the
original code). Top 15 by self time, plus cumulative where it matters:

| # | function (file:line) | calls | self s | cum s |
|---:|---|---:|---:|---:|
| 1 | `wyckoff_rules.py:304 detect_accumulations` | 2 407 | 77.3 | 111.7 |
| 2 | `{builtins.sum}` (the `prior` loop's `sum(V[...])`) | 181 242 618 | 18.2 | 18.2 |
| 3 | `normalized.py:118 available_time` (from `pit.py:139 series_as_of`, run on the 4.1M 1m series at load and on the 1.3M 5m series per HTF call) | 24 071 790 | 10.6 | 20.8 |
| 4 | `{list.append}` (the `prior` loop) | 184 261 176 | 10.0 | 10.0 |
| 5 | `normalized.py:70 _parse` | 24 071 790 | 4.8 | 8.6 |
| 6 | `wyckoff_rules.py:376 <genexpr>` | 16 642 | 3.8 | 3.8 |
| 7 | `pit.py:139 series_as_of` | 12 | 2.2 | 23.0 |
| 8 | `{str.replace}` | 26 886 313 | 2.2 | 2.2 |
| 9 | `{datetime.fromisoformat}` | 26 886 278 | 2.0 | 2.0 |
| 10 | `normalized.py:75 tf_seconds` | 24 071 791 | 1.6 | 1.6 |
| 11 | `json decoder raw_decode` (history load) | 26 | 1.3 | 1.3 |
| 12 | `wyckoff_rules.py:16` | 6 | 0.8 | 0.9 |
| 13 | `wyckoff_rules.py:14` | 2 407 | 0.7 | 1.6 |
| 14 | `quality.py:155 _str...` (load-time quality) | 1 | 0.6 | 1.2 |
| 15 | `wyckoff_rules.py:23` | 4 348 | 0.4 | 0.5 |

Cumulative: `scan_many.py:154 _chunk_wy` 129.5 s -> `backtest-methods.py:1120 _fires_from` 129.0 s ->
`backtest-methods.py:814 _htf_wyckoff_target` 128.9 s (5 calls) -> `structures.py:259 wyckoff_records` 111.9 s ->
`wyckoff_rules.py:304 detect_accumulations`. In that run 99 % of the scan is inside `_htf_wyckoff_target`.
(Call graph for the w7-only 1 500-bar run: `wyckoff_records` has 3 calls from `_htf_wyckoff_target` totalling 134.5 s
and 2 402 calls from `_wyckoff_candidates` totalling 0.39 s.)

**(b) Fixed keys without w7, prototype code, first 80 000 bars** (38.4 s profiled, 29.4 s in `_chunk_wy`). This is what
the per-window live-equivalent work looks like once w7 is out. Top 15 by self time:

| # | function (file:line) | calls | self s | cum s |
|---:|---|---:|---:|---:|
| 1 | `wyckoff_rules.py:304 detect_accumulations` | 159 402 | 12.2 | 25.4 |
| 2 | `normalized.py:118 available_time` (load-time PIT cut of the 1m series, not scan) | 10 000 000 | 4.3 | 8.6 |
| 3 | `{builtins.len}` | 60 434 263 | 2.8 | 2.8 |
| 4 | `wyckoff_rules.py:236 volume_profile` | 62 801 | 2.3 | 3.0 |
| 5 | `normalized.py:70 _parse` | 10 000 000 | 2.0 | 3.6 |
| 6 | `{list.append}` | 27 591 759 | 1.8 | 1.8 |
| 7 | `wyckoff_rules.py:146 swings` | 159 402 | 1.8 | 2.3 |
| 8 | `wyckoff_rules.py:549 <lambda>` (distribution price inversion) | 318 804 | 1.2 | 1.2 |
| 9 | `pit.py:139 series_as_of` | 2 | 0.9 | 9.5 |
| 10 | `{str.replace}` | 10 010 514 | 0.8 | 0.8 |
| 11 | `{datetime.fromisoformat}` | 10 010 512 | 0.7 | 0.7 |
| 12 | `{builtins.min}` | 11 555 807 | 0.7 | 0.7 |
| 13 | `normalized.py:75 tf_seconds` | 10 000 000 | 0.7 | 0.7 |
| 14 | `wyckoff_rules.py:544 detect_distributions` | 79 701 | 0.6 | 14.5 |
| 15 | `scan_many.py:154 _chunk_wy` | 1 | 0.6 | 29.4 |

Per window the backtest does the same work as live: one `detect_accumulations` and one `detect_distributions` over a
300-bar window (`WYCKOFF_WINDOW = 300`, `backtest-methods.py` near `_WY_CANDIDATES`; `fx_w6_window` 300 -> `_wy_window`
`:1251`), 159 402 detector calls for 79 701 windows = 0.17 ms per call. So windows, pivots (pre-computed once per
series in `scan_many._chunk_wy`, `window_pivots` 0.58 s total) and the per-fire `walk` are not the problem.

## 6. Causes (labelled) and proposal

**Cause 1 (OBSERVED, dominant): `fx_w7_htf_target` is on in every fund-search Wyckoff cell and does per-fire full-history
HTF detection.** Evidence: single-key ablation at 1 500 bars (`--keys`): w1 4.66 s, w2 4.54 s, w3 4.61 s, w5 4.57 s,
**w7 85.8 s**; all fixed keys minus w7 at 20k-160k bars stay at 0.18 ms/bar (section 3). Mechanism:
`_htf_wyckoff_target` (`backtest-methods.py:814`) truncates the HTF series with `pit.series_as_of` (full pass over 1.3M
bars every call) and runs `wyckoff_records` on the entire prefix since 2004; the memo key includes `decision_time`
(`:852-854`), so nearly every fire misses it. ~2.0-2.6 calls per 1000 1m bars (OBSERVED on 5k-40k slices).
W7 was ADOPTED by the owner 2026-09-30 (`docs/plans/2026-09-30-owner-decisions.md`; `ADOPTED_F_KEYS`). The live/pilot path does not set the key (OPTS default False, `backtest-methods.py:139`), which is why the live read costs ~0.3 ms and the backtest
does not (live-vs-backtest behavioural difference, noted not judged).

**Cause 2 (OBSERVED + INFERRED): the per-call detection is O(S^2) in the number of swings S, from the `prior` loop.**
OBSERVED: measured exponent 1.91 (section 4); 181M `sum()` and 184M `append()` calls in the 1 500-bar profile; the loop
is `85bbc08:scripts/wyckoff_rules.py:339-344`: for every downtrend-SC candidate it walks `sw` from index 0 to the SC, although only
`prior[-nd - 1:]` (the last nd+1 pairs) is used. INFERRED: the residual superlinearity after the fix (exponent 1.45) comes
from the two other per-candidate O(S) scans (`st = next(... for s in sw ...)`, `after = [s for s in sw ...]`,
`85bbc08:scripts/wyckoff_rules.py:380/395`), which the second half of the prototype also replaced by bisect on the sorted swing bars.

**Cause 3 (OBSERVED, minor): `pit.series_as_of` is O(whole HTF series) per call** (0.6 s on the 1.32M-bar 5m series,
`pit.py:139`, 24M `available_time` calls in the profile). After Cause 2 is fixed it is ~25-30 % of a call.

### Prototype on this branch (engine code touched: `scripts/wyckoff_rules.py`, +12/-7 lines)

1. `prior` loop walks back from `si - 1` and stops after `nd + 1` pairs (then `reverse()`), same tuples, same order,
   same float sums.
2. `sw_bars = [s[0] for s in sw]` once per call; `st` and `after` start from `bisect.bisect_right(sw_bars, ...)` instead
   of scanning `sw` from 0. Swing bars are non-decreasing (`swings()` appends in pivot order).

Byte-identity evidence (OBSERVED):

- `ab_wyckoff_detect.py` (original `wyckoff_rules.py` from 85bbc08 vs working tree, `detect_accumulations` +
  `detect_distributions` on the whole 5m PIT prefix, all four W1/W2/W3/W5 detection keys on), sha256 of the record lists:
  2016-06-01 (772 096 bars) `ffe221c1...`, 65.8 s -> 2.3 s; 2020-06-01 (1 052 871) `ca52bd15...`, 114.7 s -> 3.7 s;
  2024-02-01 (1 311 083) `8b893727...`, 168.1 s -> 5.2 s; all **IDENTICAL**. Records of 2005/2008/2012 prefixes
  (`htf_target_cost.py`, long+short) equal before vs after as well (`/tmp/b8-htf-cost-before.log` vs
  `/tmp/b8-htf-cost-after3.log`).
- Trade-list sha256 (`json.dumps(trades, sort_keys=True)`), original vs prototype, scan_many 1 overlay:
  v1 overlay 20k `71aae65b...` and 160k `c0924b48...` (same); fixed-no-w7 20k `ba82d19f...`, 40k `2e0be9cc...`,
  80k `a610313c...`, 160k `126996b0...` (full hashes in the section 8 logs `/tmp/b8-wy-now7-scaling.log` = original code
  vs `/tmp/b8-new-now7.log` = prototype; same before and after); fixed-with-w7 5 000 bars `855fccf3...` (same; 223 s ->
  34 s). The w7 slices of 10k/20k/40k have **no original-code baseline** (too slow to
  run), only the detector-level A/B above covers them.
- Unit tests: `scripts/tests/test_wyckoff_fidelity`, `test_v_items_wyckoff`, `test_audit_round3_wyckoff`: 111 tests OK.
  `test_speed_equivalence`: see section 9.

### Proposal for the remaining gap (NOT implemented; needs a decision)

Prototype leaves ~2.6 s per HTF call (model, section 7) x ~8 200 calls ~ 6 CPU-h for 4.1M bars, vs ~11 CPU-min for
everything else. The smallest byte-identical follow-ups, in order of safety:

1. Memoize `_htf_wyckoff_target` on `(len(prefix), side, ...)` instead of `decision_time`: all 1m decisions inside one
   5m bar share the same PIT prefix (only fires in the same 5m bar benefit; expect a small gain).
2. Build the HTF O/H/L/C/V arrays and the available-time list **once per HTF series** and cut the prefix by `bisect`
   instead of `series_as_of` + 5 list comprehensions per call (removes the ~0.6 s + list-build term, ~35-45 % of a call
   at 2012 prefixes). Must reproduce `series_as_of`'s exact selection (it is the PIT primitive, CLAUDE.md section 8);
   verify by sha256 of the selected prefix vs `series_as_of` for many decision times.
3. Only the last HTF structure (`recs[-1]`) is read. An incremental/suffix detector would remove the per-call O(prefix)
   pass but is NOT provably byte-identical (record pairing and `used_until` depend on earlier swings) and is out of
   scope without an A/B harness of the `ab_wyckoff_detect.py` kind over many decision times.

W7 is already adopted by the owner (2026-09-30, `docs/plans/2026-09-30-owner-decisions.md`), so removing
`fx_w7_htf_target` from `ADOPTED_F_KEYS` would REVERSE an owner decision; it is listed only as an option the owner could
weigh against the cost (scan back to ~0.15 ms/bar without it), not as a recommendation. The live/pilot path does not set
the key (OPTS default False, `backtest-methods.py:139`).

## 7. Revised extrapolation for the full 4.1M-bar XAUUSD 1m dev scan (EXTRAPOLATION, serial CPU time)

Inputs: measured marginal costs (section 3), measured call rate 2.0-2.6 HTF calls per 1000 bars (first 40k bars only, so
the call rate later in the span is an assumption), per-call cost interpolated log-log between the measured prefix sizes
(section 4) over the prefix growing linearly 492k -> 1.31M across the span; mean detect cost per call 76.9 s
(original; + ~1 s `series_as_of`/list build) and ~2.6 s (prototype: detection + 0.6 s `series_as_of` + ~0.6 s lists).

| Scenario | per-bar cost | 4.1M bars, 1 process | with 5 workers |
|---|---:|---:|---:|
| Live-path rate, both sides (0.3 ms) | 0.3 ms | ~20 min | - |
| "If linear" (measured no-w7 marginal 0.15 ms/bar; 0.176 ms/bar incl. offset at 160k) | 0.15-0.18 ms | **10-12 min** | ~2-3 min |
| As measured, original code with w7 (8 200 calls x ~78 s) | ~156 ms | **~178 CPU-h** | ~36 h |
| Prototype with w7 (8 200 calls x ~2.6 s) | ~5.2 ms | **~6 CPU-h** | ~1.2 h |

The original-code figure is consistent with the observed non-completion after 5 h 6 min at 145-300 CPU-min per worker.
The 4.1M-bar numbers are extrapolations, not measurements; the ICT row in section 3 (0.62 ms/bar -> ~42 min serial) is
linear and is not part of the problem.

## 8. Evidence

- Code: `scripts/research/profile_wyckoff_1m.py`, `scripts/research/htf_target_cost.py`,
  `scripts/research/ab_wyckoff_detect.py`, prototype `scripts/wyckoff_rules.py` (git diff on this branch).
- Logs: `/tmp/b8-smoke.log` (5k, w7 fixed, original: 223 s), `/tmp/b8-nofixed-5000.log`, `/tmp/b8-wy-w7-5000.log`
  (13 HTF calls, 201.8 s), `/tmp/b8-wy-now7-scaling.log`, `/tmp/b8-wy-nofixed.log`, `/tmp/b8-ict-scaling.log`,
  `/tmp/b8-prof-fixed-1500.log` (cProfile a), `/tmp/b8-prof-w7-1500.log`, `/tmp/b8-prof-now7-80000.log` (cProfile b),
  `/tmp/b8-htf-cost.log`, `/tmp/b8-htf-cost-before.log`, `/tmp/b8-htf-cost-after{1,2,3}.log`,
  `/tmp/b8-ab-{2016,2020,2024}.log`, prototype slices `/tmp/b8-new-*.log`, `/tmp/b8-wy-tests.log`,
  `/tmp/b8-speed-equiv.log`.
- Single-key ablation at 1 500 bars was run in the shell (output quoted in section 6), not logged to a file.

## 9. Test status

Engine code (`scripts/wyckoff_rules.py`) was touched, so `cd scripts/tests && PYTHONPATH=.. python3 -W ignore -m unittest
test_speed_equivalence` was run on the prototype: **42 tests, OK, 1107 s** (`/tmp/b8-speed-equiv.log`). The three Wyckoff
test modules (111 tests) also pass (`/tmp/b8-wy-tests.log`). The prototype is NOT requested for merge by this document;
it is a proof that the byte-identical change exists and what it buys.
