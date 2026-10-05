#!/usr/bin/env python3
"""Codeable Wyckoff rules from the books, as pure functions over OHLCV arrays. Used by scripts/backtest-methods.py
(method WYCKOFF-BOOK / COMBINED-BOOK); written so scripts/ict-scan.py or check-narrative.py can reuse them later.

Every rule cites its page. Numbers the books do not print are PROJECT PARAMETERS (named in PARAMS) — say so when reporting.

Accumulation is detected on the raw series; distribution is the same detector run on the price-inverted series
(WA p101: the distribution schematic is the mirror image), with the event names mapped back (SC→BC, AR→AR, ST→ST,
Spring→UT/UTAD, SOS→SOW, BU/LPS→LPSY).

Rules implemented (knowledge/wyckoff/advance.md = WA, knowledge/wyckoff/modern-tools.md = WMT):
  R1  CHoBEV / CHoCH gate (WA p67–68): a counter-trend reaction counts as a CHoBEV when its spread and its effort (volume)
      exceed those of the prior counter-trend reactions of the trend; three CHoBEV = CHoCH; only then may a TR be drawn.
  R2  Trading range from events (WA p69, p73): lower border = SC low (start of the first up-wave), upper border = AR high.
  R3  ST[A] position -- đối nhãn Dấu hiệu 1 (WA p150-153): the book divides the TR into THREE parts, not two.
      "Nếu ST ở 1/3 phần trên Trading Range ... nền hỗ trợ cực kỳ mạnh ... dấu hiệu để nhận dạng sớm tích lũy";
      "Nếu ST ở 1/3 phần dưới Trading Range hoặc thậm chí [phá] hỗ trợ cục bộ SC ... dấu hiệu để nhận dạng sớm
      tái phân phối hoặc phân phối" (WA p150). Recorded as st_pct = (ST low − SC low)/TR and as st_sign:
      "supports" (upper third) / "neutral" (middle) / "contradicts" (lower third, or below the SC border).
      Until 2026-09-19 the docstring said "ST above 50%" and the filter's only threshold was a half -- a number
      the book never gives (docs/audits/2026-09-19-knowledge-fidelity.md finding 9).
  R3b Phase-B test location -- đối nhãn Dấu hiệu 2 (WA p154-159): "Kiểm tra trên đỉnh của cấu trúc nhiều lần gợi ý
      dấu hiệu sức mạnh. Kiểm tra ... phần dưới của cấu trúc nhiều lần gợi ý dấu hiệu suy yếu" (WA p154).
      Counted over the Phase-B swings between ST[A] and the border break: phase_b_tests = {upper, lower} using
      the same thirds as R3, and phase_b_sign = supports / neutral / contradicts. Recorded, and exposed as an
      optional filter -- the book presents the four dấu hiệu as judgement inputs, not as one hard gate.
      NOTE ON FRAME: detect_distributions() runs this same detector on INVERTED prices, so "upper third" always
      means the third that supports the label being detected. That is why the signs are named supports/contradicts
      and not upper/lower: the words survive the mirror, the directions do not.
  R4  Phase B must exist before a Phase C call (WA p79, WA3-08 p189–190): a border break before PARAMS.min_phase_b_swings
      swings after ST is mSOW[B]/UA[B], never Spring/UT.
  R5  Sloped structure → do not trade (WA p167, p170): skip when Phase-B swing lows drift by more than PARAMS.slope_max_tr of the TR.
  R6  Spring vs Shakeout (WA p80, p83): price must close back inside within PARAMS.spring_max_bars_outside bars and fewer than
      half the excursion bars may close below the border; otherwise it is a Shakeout (supply remains) → no direct entry (WA2-12).
  R7  Spring volume type 1/2/3 (Bảng 2.1, WMT p049) and Upthrust volume type 1/2/3 (Bảng 2.2, WMT p064) --
      TWO DIFFERENT TABLES, not a mirror: Spring runs low->1/moderate->2/high->3, Upthrust runs
      increases->1 / very high (UTAD)->2 / strong-but-lower->3, and the book has no low-volume Upthrust.
      knowledge/wyckoff/modern-tools.md:55-72, thresholds from analysis-params.json. (The single-table
      reading, and the p049 cite standing for both, were corrected 2026-09-19 after a knowledge audit.)
  R8  Test after the Spring (WA p80): a pullback holding above the Spring low, inside the lower third of the TR, on volume lower
      than the Spring bar, closing in its upper half. Type 2 needs it (WMT p049); type 1 may enter at the reclaim (WA p80, partial).
  R9  SOT into the border (WA p278–284): successive pushes into the low with shortening distance; ≥3 pushes = valid SOT; more than 4
      pushes = trend too strong to oppose. Recorded (sot_pushes, sot) and exposed as a filter.
  R10 Volume Profile of the TR (WA p259–265, WMT p243–249): VPOC, VAH/VAL at 68.2 % of volume, LVN just beyond VAL; the abandon
      rule: if the Spring excursion closes beyond the LVN and does not close back above VAL within 2 bars, the plan is abandoned.
  R11 Phase D entry (WA p83–85): SOS = close above the TR high with widening spread and volume ≥ average, held for
      PARAMS.commitment_bars closes; BU/LPS = the first pullback to the TR top on lower volume; entry at the first up-close of the
      pullback, stop under the pullback low, target = TR top + 1 TR (PROJECT PARAMETER — the book gives no numeric projection).
  R0  VOLUME PROVENANCE (WMT p131-133, knowledge/wyckoff/modern-tools.md §7). Every volume rule below -- R1's
      CHoBEV effort, R7's Spring/Upthrust typing, R8's "Test on lower volume than the Spring", R10's Volume
      Profile, R11's "SOS on volume >= average" -- assumes TRADED volume. The MT5 CFD feed reports TICK COUNT:
      the broker counts price changes, not size (docs/architecture/mt5-bridge.md, providers.json). The book
      flags exactly this ("Forex's tick-based Delta is not real volume and therefore unreliable", WMT p131-132)
      and states real-volume availability as a hard requirement of its method (WMT p131-133).
      This engine does NOT refuse a tick feed -- that is a methodology decision, not a reading of the book --
      but every record it returns now carries `volume_kind` ("traded" | "tick") so no downstream surface can
      print a volume type as if the book's table had been fed what the book requires. Callers pass it from
      scripts/instruments.py is_tick_volume(symbol); the default is "traded" only because the crypto feeds are.
      Before 2026-09-19 nothing carried the distinction at all (knowledge audit finding 8).
  R12 Stop under the Spring low (WMT p271); first target = opposite border (WMT p273, WA p83–84); breakeven
      handled by the caller's walk(). NOTE: the book (WMT p272) says "move to entry once price has moved
      favorably or consolidated" and gives NO number -- the +1R trigger is a PROJECT parameter.

FIDELITY CORRECTIONS (docs/plans/2026-09-28-methodology-improvement-plan.md §3 batch 1(b); the shared `fx_`
key contract, docs/plans/2026-09-29-execution-plan.md). Each is a bool in PARAMS, default False = v1 (the
funnel/trade-count delta between False and True is recorded in docs/audits/2026-09-29-wyckoff-fidelity-funnel.md
per item, and the live/pilot path never sets any of them -- backtest-methods.py's OPTS carries the caller-facing
copy and bridges it into this module's PARAMS before every detection call, exactly like `spring_max_bars_outside`
already is):
  fx_w1_tr_low_st   W1 (WA p72): "Mức thấp của SC và ST và mức cao của AR thiết lập ranh giới của TR" -- the TR
                     low is min(SC low, ST low), not SC low alone (the code drew tr_lo from SC only, before ST
                     is even known). Widens tr_lo/tr for every downstream Phase B/C/D read once ST is found;
                     st_pct/st_sign (WA p150's đối nhãn thirds, framed over the Phase-A SC-AR range) are computed
                     BEFORE the widening and are unaffected by this key.
  fx_w2_st_below_sc W2 (WA2-06, WA p72, p74-75, p77): "Nếu ST[A] holds above SC (most common), supply is drying
                     up; IF ST[A] breaks below SC, THEN expect new lows or a prolonged consolidation with many
                     further STs" -- the book does not say discard the structure. The R1 CHoBEV loop's `broke`
                     early-exit currently discards ANY structure where a low-swing dips below SC before the 3rd
                     CHoBEV (docs/audits/2026-09-28-method-fidelity.md finding W-8); this key removes only that
                     discard, the CHoBEV search itself is unchanged.
  fx_w3_mSOW_spring W3 (WA p166 boxed method summary): "Hoặc ở vị trí MSOW[B] cũng là Spring tiềm năng trong
                     tích lũy để xem hành động ở biên dưới có cạn kiệt/hấp thụ phán đoán sự từ chối để mở vị
                     thế Long tại đây" -- an early Phase-B border break (R4's mSOW[B]) is ALSO a potential
                     Spring, not "never Spring/UT" (WA3-08, WA p189-190, read together: at the time you cannot
                     assert MSOW vs Spring, which is exactly "also potential", not "discard"). When set, an
                     early break feeds the SAME Spring/Shakeout/vol-type/reclaim/test/Phase-D pipeline below
                     instead of being discarded at R4.
  fx_w5_vp_abandon  W5 (WMT p243-249, Step 4): "If price crosses cleanly through VAH/VAL into LVN WITHOUT a
                     reversal reaction, ... abandon the Spring/Upthrust plan" -- the book states no bar count
                     for "reversal reaction". The code's "back above VAL within 2 bars of the reclaim" window
                     is UNSOURCED and is removed: the reclaim bar itself (`rec`, the same close-back-inside-the-
                     TR event R6 already defines) is tested against VAL instead of a separate fixed window.
  (W7 -- Phase-D target from the higher-timeframe TR's AR/SOS, WA2-19 -- is a SEPARATE key,
  `fx_w7_htf_target`, read by backtest-methods.py `_fires_from`/`_htf_wyckoff_target`, not by this module: it
  needs a second, higher-timeframe candle series this module has no access to. See that module's docstring.)

V ITEMS READ BY THIS MODULE (Batch 2(a); docs/plans/2026-09-28-methodology-improvement-plan.md section 3, the V grid;
docs/architecture/v-grid-wyckoff.json). Each is a PER-CALL override of the caller's PARAMS copy -- this module never
writes PARAMS -- and each default reproduces v1 exactly:
  fx_w4a_linger_closes  W4a (WA2-12, WA p80, p83): "most candles of the break close BELOW the lower border and price
                     lingers there" = Shakeout. None (default) = v1's typing (no reclaim within
                     `spring_max_bars_outside` bars, or more than half of the excursion window closing below the
                     border). An int N in the declared set {2, 3, 4} types a break a Shakeout when it has NO
                     reclaim, or when N or more closes below the border precede the reclaim bar. The count is
                     the V threshold; the book prints none.
  test_window, min_phase_b_swings (W-TW, project parameters, PARAMS above): the V item `fx_w_tw` of
                     backtest-methods.py overrides both in the per-call copy: test window {12, 8, 20} x
                     Phase-B swings {2, 3}.

PRICE-ONLY READ (docs/plans/2026-10-04-wyckoff-retest-preregistration-DRAFT.md §3.1 and §10 item 1, the re-test's
detector DET-PO). `price_only` is a PER-CALL key like the ones above, default False = v1, byte-identical (the live path,
check-narrative.py and backtest-methods.py never set it). When True, the six volume clauses that decide WHETHER a
structure or event is detected count as satisfied, so every structural field of a record is a function of O/H/L/C only:
  R1   CHoBEV effort         the up-swing's summed volume > the mean of the prior reactions' (the spread leg stays)
  R11  LPS[C] SOS effort     V >= the `lookback`-bar average on the breakout bar
  R11  LPS[C] BU pullback    V < the breakout bar's volume
  R8   Test after the Spring V < the Spring bar's volume
  R11  SOS effort            V >= the `lookback`-bar average on the breakout bar
  R11  BU pullback           V < the breakout bar's volume
  Volume is still read for the record fields in VOLUME_FIELDS (R7 type and ratios, R10 profile and abandon). Nothing
  in this module gates on them, and the pre-registration's price-only family reads none of them ("still computed,
  but nothing in this family reads them", §3.1). So with the key on, a record is unchanged under any permutation or
  rescaling of V outside VOLUME_FIELDS (scripts/tests/test_wyckoff_price_only.py). Dropping the effort legs departs
  from the book (WA p68, knowledge/wyckoff/advance.md:274 "nỗ lực tăng"; WMT p131-133 asks for real volume): every
  price-only result must say so. On a tick-volume feed (R0) this is the only reading that does not lean on tick counts.
"""
import bisect, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AP = json.load(open(f"{ROOT}/docs/architecture/analysis-params.json"))
VOL = _AP["project_defined"]["volume"]; SPREAD = _AP["project_defined"]["spread"]
COMMIT = _AP["project_defined"]["commitment_bars"]["value"]; VA_PCT = _AP["sourced"]["value_area_pct"]["value"]
SOT_MIN = _AP["sourced"]["sot_min_pushes"]["value"]; SOT_MAX = _AP["sourced"]["sot_useful_max_pushes"]["value"]

PARAMS = dict(
    pivot=3,                    # bars each side for a swing point (project; the ICT scanner uses the same)
    downtrend_swings=2,         # lower lows + lower highs needed before an SC (project)
    chobev_needed=3,            # WA p68: three CHoBEV = CHoCH (sourced)
    min_phase_b_swings=2,       # swings after ST[A] before a border break may be Phase C (project; WA p79 "Phase B is the longest")
    slope_max_tr=0.35,          # Phase-B lows drifting more than this × TR = sloped structure (project; WA p167)
    spring_max_bars_outside=3,  # bars allowed outside the TR before it is a Shakeout (project; WA p83 "khá ngắn ngủi")
    test_window=12,             # bars to wait for the Test after the reclaim (project)
    test_zone_tr=1 / 3,         # the Test must hold inside the lower third of the TR (project; WA p80 "kiểm tra nguồn cung")
    doi_nhan_third=1 / 3,       # WA p150 "chia biên độ của cấu trúc thành 3 phần" -- the đối nhãn thirds (sourced, R3/R3b)
    vp_bins=30,                 # Volume Profile resolution (project)
    phase_d_window=40,          # bars to wait for SOS + BU after the Spring/Test (project)
    d_target_tr=1.0,            # Phase D target = TR top + this × TR (project)
    lookback=20,                # average window for volume/spread ratios (analysis-params lookback_bars)
    # F items (module docstring, "FIDELITY CORRECTIONS"): v1 default False everywhere. A caller that never sets
    # these (every test, check-narrative.py, the live runner via backtest-methods.OPTS left at its defaults)
    # reads exactly v1 behaviour -- backtest-methods._wyckoff_candidates'/wyckoff_fires' callers bridge
    # bt.OPTS["fx_w*"] into this dict before every detection call, the same way they already do for
    # spring_max_bars_outside.
    fx_w1_tr_low_st=False,
    fx_w2_st_below_sc=False,
    fx_w3_mSOW_spring=False,
    fx_w5_vp_abandon=False,
    # V item W4a (module docstring "V ITEMS"): None = v1 Shakeout typing; an int = the lingering-closes threshold.
    fx_w4a_linger_closes=None,
    # Module docstring "PRICE-ONLY READ": True = the six volume gates count as satisfied (DET-PO). False = v1.
    price_only=False,
)

# Record keys that still read V when `price_only` is on (R7, R10). Recorded only; nothing in this module gates on them.
VOLUME_FIELDS = ("vol_ratio", "vol_type", "rec_ratio", "vpoc", "vah", "val", "lvn", "abandon")


def swings(H, L, k, pivots=None):
    """Alternating swing list [(bar, 'H'|'L', price)] from k-bar pivots; consecutive same-kind pivots keep the more extreme one.

    `pivots` (speed, byte-identical): the window's pivot bars already known, as `[(bar, mask)]` ascending, mask bit 1 =
    a high pivot, bit 2 = a low pivot -- what `window_pivots()` slices out of ONE series-wide `pivot_index()`. A k-bar
    pivot at bar i reads only bars i-k..i+k, all inside the window for every bar this loop visits, so the flag of a
    bar is the same whichever window it is read from; the caller (scripts/backtest-methods.py via scan_many.py) proves
    that by running both paths on real windows. None (every existing caller) = the original per-window scan."""
    out = []
    if pivots is None:
        pivots = list(zip(*pivot_index(H, L, k)))
    for i, mask in pivots:
        for kind, px in ((("H", H[i]),) if mask & 1 else ()) + ((("L", L[i]),) if mask & 2 else ()):
            if out and out[-1][1] == kind:
                if (kind == "H" and px >= out[-1][2]) or (kind == "L" and px <= out[-1][2]):
                    out[-1] = (i, kind, px)
            else:
                out.append((i, kind, px))
    return out


def pivot_index(H, L, k):
    """Every k-bar pivot of a whole series, once: (bars, masks) ascending, mask bit 1 = high pivot (`all(H[j] <= H[i])`
    over the k bars each side), bit 2 = low pivot -- the exact predicates `swings()` evaluates per window."""
    bars, masks = [], []
    for i in range(k, len(H) - k):
        h, l = H[i], L[i]
        isH = True
        for j in range(i - k, i + k + 1):
            if j != i and not H[j] <= h:
                isH = False
                break
        isL = True
        for j in range(i - k, i + k + 1):
            if j != i and not L[j] >= l:
                isL = False
                break
        if isH or isL:
            bars.append(i)
            masks.append((1 if isH else 0) | (2 if isL else 0))
    return bars, masks


def window_pivots(index, a, m, k, swap=False):
    """`swings(..., pivots=)` input for the window of history bars [a, a+m): the series-wide `pivot_index` entries
    whose bar the window's own loop would visit (a+k .. a+m-k-1), re-based to window-local bars. `swap` exchanges the
    high and low flags -- the input of `detect_distributions`, which runs the accumulation detector on -L / -H."""
    import bisect
    bars, masks = index
    lo = bisect.bisect_left(bars, a + k)
    hi = bisect.bisect_left(bars, a + m - k)
    if not swap:
        return [(bars[q] - a, masks[q]) for q in range(lo, hi)]
    return [(bars[q] - a, ((masks[q] & 1) << 1) | ((masks[q] & 2) >> 1)) for q in range(lo, hi)]


def swing_prefix_index(H, L, k, nd):
    """Speed (byte-identical; W7's HTF read, docs/audits/2026-10-01-w7-speed.md): everything `prefix_swings()` needs to
    hand `detect_accumulations(pre=)` the swing data of ANY prefix of one series, computed once for the whole series.
    `H`/`L` are the arrays the detector sees (the INVERTED ones for `detect_distributions`), `k` = P["pivot"], `nd` =
    P["downtrend_swings"].

    `swings()` is a left-to-right fold over the pivots: each step appends a swing or replaces the LAST one (same kind,
    more extreme). So after the pivots with bar < m - k (exactly the pivots of the prefix H[:m], because a k-bar pivot at
    bar i reads only bars i-k..i+k) the swing list is `final[:len-1] + [last]`, where only that last element can later
    change: any element followed by another is never touched again. `lens[e]`/`lasts[e]` record the list's length and last
    element after the first e+1 pivot entries.

    `cands` = the swing indices of the FULL swing list that pass detect_accumulations' downtrend test (a low swing with
    `nd` lower lows and `nd` lower highs before it: the code below is that test, verbatim). The test reads only
    sw[:si+1], so for a prefix whose swing list agrees with the full one up to index Lm-2 the verdict at every si <= Lm-2
    is the same; only the prefix's own last swing (index Lm-1) needs a fresh look, and `prefix_swings` always lists it."""
    bars, masks = pivot_index(H, L, k)
    out, lens, lasts = [], [], []
    for i, mask in zip(bars, masks):
        for kind, px in ((("H", H[i]),) if mask & 1 else ()) + ((("L", L[i]),) if mask & 2 else ()):
            if out and out[-1][1] == kind:
                if (kind == "H" and px >= out[-1][2]) or (kind == "L" and px <= out[-1][2]):
                    out[-1] = (i, kind, px)
            else:
                out.append((i, kind, px))
        lens.append(len(out)); lasts.append(out[-1])
    need = max(nd + 1, 2)
    cands = []
    for si in range(4, len(out)):
        if out[si][1] != "L":
            continue
        lows, highs, q = [], [], si
        while q >= 0 and (len(lows) < need or len(highs) < need):
            sq = out[q]
            if sq[1] == "L":
                if len(lows) < need: lows.append(sq)
            elif len(highs) < need:
                highs.append(sq)
            q -= 1
        lows.reverse(); highs.reverse()
        if len(lows) < nd + 1 or len(highs) < nd + 1:
            continue
        if not all(lows[-j][2] < lows[-j - 1][2] for j in range(1, nd + 1)) or not all(highs[-j][2] < highs[-j - 1][2] for j in range(1, nd + 1)):
            continue
        cands.append(si)
    return dict(k=k, nd=nd, bars=bars, sw=out, lens=lens, lasts=lasts, cands=cands)


def prefix_swings(index, m):
    """`(sw, cands)` for `detect_accumulations(H[:m], ..., pre=)` from a `swing_prefix_index()`: `sw` == swings(H[:m],
    L[:m], k) and `cands` ascending, a superset of the prefix's downtrend-test passes (see `swing_prefix_index`)."""
    e = bisect.bisect_left(index["bars"], m - index["k"])
    if e == 0:
        return [], []
    Lm = index["lens"][e - 1]
    sw = index["sw"][:Lm - 1]
    sw.append(index["lasts"][e - 1])
    cands = index["cands"][:bisect.bisect_right(index["cands"], Lm - 2)]
    if Lm - 1 >= 4:
        cands.append(Lm - 1)
    return sw, cands


def avg(xs, i, n):
    w = xs[max(0, i - n):i]
    return sum(w) / len(w) if w else 0.0


def vol_type(ratio, side="long"):
    """R7 volume TYPE for a break bar. Spring (long, Bang 2.1, WMT p049) and Upthrust (short, Bang 2.2, WMT
    p064) are typed from TWO DIFFERENT tables -- not a mirror. Moved here from backtest-methods.vtype()
    2026-09-25 (docs/audits/2026-09-24-system-audit.md WY-1) so there is exactly ONE owner of this logic;
    detect_accumulations/detect_distributions below are the only callers, so both the live runner
    (via wyckoff_fires) and the backtest ask the same question the same way (CLAUDE.md Sec37).

    Spring (long) -- Bang 2.1, WMT p049 (knowledge/wyckoff/modern-tools.md:55-61): type 1 = LOW ("no fresh
    selling pressure"), type 2 = MODERATE, type 3 = HIGH ("Shake Out"). Ascending in volume: 1 < 2 < 3.

    Upthrust (short) -- Bang 2.2, WMT p064 (knowledge/wyckoff/modern-tools.md:66-72): type 1 = volume
    INCREASES at the touch, type 2 (UTAD) = VERY HIGH at the extreme, type 3 (Minor UTAD) = "strong but not
    as high as type 2". There is NO low-volume Upthrust in the book: a ratio below `upthrust_min_ratio` is
    refused (returns None) rather than relabelled as a low-volume type, per
    analysis-params.json project_defined.volume._upthrust_basis. The book also separates Upthrust type 1
    from type 3 by PRICE reaction, not volume -- on volume alone both bands look the same, so this never
    returns 3 for a short; that is a declared limit of a volume-only proxy, not a reading of the book.
    """
    if ratio is None:
        return None
    if side == "long":
        return 1 if ratio < VOL["low_max_ratio"] else (3 if ratio > VOL["high_min_ratio"] else 2)
    if ratio > VOL["high_min_ratio"]:
        return 2
    if ratio >= VOL["upthrust_min_ratio"]:
        return 1
    return None


def volume_profile(H, L, V, a, b, bins):
    """Volume profile of bars a..b (inclusive): each bar's volume spread evenly over the bins it covers. Returns (lo, step, hist)."""
    lo = min(L[a:b + 1]); hi = max(H[a:b + 1])
    if hi <= lo:
        return lo, 0.0, [0.0]
    step = (hi - lo) / bins; hist = [0.0] * bins
    for j in range(a, b + 1):
        b0 = min(bins - 1, int((L[j] - lo) / step)); b1 = min(bins - 1, int((H[j] - lo) / step))
        share = V[j] / (b1 - b0 + 1)
        for q in range(b0, b1 + 1):
            hist[q] += share
    return lo, step, hist


def value_area(lo, step, hist, pct=VA_PCT):
    """VPOC and VAH/VAL holding `pct` of volume, expanding from the VPOC toward the heavier neighbour (WA p259, p262)."""
    if step == 0:
        return lo, lo, lo, None
    poc = max(range(len(hist)), key=lambda q: hist[q]); total = sum(hist); acc = hist[poc]; a = b = poc
    while acc < pct * total and (a > 0 or b < len(hist) - 1):
        up = hist[b + 1] if b < len(hist) - 1 else -1; dn = hist[a - 1] if a > 0 else -1
        if up >= dn:
            b += 1; acc += hist[b]
        else:
            a -= 1; acc += hist[a]
    val = lo + a * step; vah = lo + (b + 1) * step; vpoc = lo + (poc + 0.5) * step
    # LVN just beyond VAL: lowest bin between the profile low and VAL (WA p264–265; WMT p243–249 "LVN just beyond VAH/VAL")
    lvn = None
    if a > 0:
        q = min(range(0, a), key=lambda q: hist[q]); lvn = lo + (q + 0.5) * step
    return vpoc, vah, val, lvn


def sot_pushes(lows):
    """Number of successive pushes with shortening distance, counted backwards from the last low (WA p278–280)."""
    if len(lows) < 3:
        return 0
    d = [lows[i - 1] - lows[i] for i in range(1, len(lows))]  # distance travelled by each new push down (positive = lower low)
    n = 1
    for i in range(len(d) - 1, 0, -1):
        if 0 < d[i] < d[i - 1]:
            n += 1
        else:
            break
    return n + 1 if n > 1 else 0  # pushes = shortening intervals + 1


STATS = {}


def bump(k):
    STATS[k] = STATS.get(k, 0) + 1


class _LazySpread:
    """`[h - l for h, l in zip(H, L)]`, built the first time it is indexed or sliced. Speed only (byte-identical): the
    list feeds two gates deep inside detect_accumulations' loops, which the great majority of windows never reach."""
    __slots__ = ("_H", "_L", "_v")

    def __init__(self, H, L):
        self._H, self._L, self._v = H, L, None

    def __getitem__(self, k):
        if self._v is None:
            self._v = [h - l for h, l in zip(self._H, self._L)]
        return self._v[k]


def detect_accumulations(O, H, L, C, V, P=PARAMS, volume_kind="traded", side="long", pivots=None, pre=None):
    """Walk the series and return every accumulation structure that reaches a Spring candidate, with all rule outputs.
    Each record: dict(sc, ar, st, tr_lo, tr_hi, st_pct, chobev_bars, phase_b_swings, sloped, spring=dict(...), ...).

    `side`: "long" for a genuine accumulation/Spring read (Bang 2.1), "short" when called from
    detect_distributions on inverted prices, so the break bar is typed against the Upthrust table
    (Bang 2.2) instead of the Spring table (WY-1, docs/audits/2026-09-24-system-audit.md).

    `pre` (speed, byte-identical; W7's HTF read, docs/audits/2026-10-01-w7-speed.md): `(sw, cands)` as
    `prefix_swings()` returns them -- this series' swing list and the swing indices the loop below visits, instead of
    computing `swings()` and visiting every swing from 4. `cands` must be ascending and a SUPERSET of the swings that
    pass the downtrend test below (`prefix_swings` documents why it is); every index it lists still runs that test, and
    an index it omits would have hit one of the `continue`s before `used_until` or `out` is touched, so the records are
    the same. None (every other caller) = the original."""
    n = len(C); k = P["pivot"]; out = []
    if pre is None:
        sw = swings(H, L, k, pivots=pivots)
        cands = range(4, len(sw))
    else:
        sw, cands = pre
    sw_bars = [s[0] for s in sw]    # swing bars are non-decreasing: bisect targets for the "first swing after bar X" reads below
    lb = P["lookback"]
    po = P.get("price_only")        # module docstring "PRICE-ONLY READ": `po or <volume clause>` at the six gates below
    spread = _LazySpread(H, L)      # bar ranges: built on first use (most windows never reach a use)
    used_until = -1
    for si in cands:
        i, kind, px = sw[si]
        if kind != "L" or i <= used_until:
            continue
        # --- downtrend before the candidate SC: lower lows and lower highs (R1 precondition) ---
        # Speed (byte-identical): only the LAST `need` low swings (sw[:si+1]) and high swings (sw[:si]) are ever read below
        # -- the R1 test looks at the last nd+1 of each, and `lows[-2]` feeds the SOT pushes -- so they are collected by
        # walking back from `si` and stopping once both have `need` (the full lists this replaces are O(swings) per candidate).
        nd = P["downtrend_swings"]; need = max(nd + 1, 2)
        lows, highs, q = [], [], si
        while q >= 0 and (len(lows) < need or len(highs) < need):
            sq = sw[q]
            if sq[1] == "L":
                if len(lows) < need: lows.append(sq)
            elif len(highs) < need:
                highs.append(sq)
            q -= 1
        lows.reverse(); highs.reverse()
        if len(lows) < nd + 1 or len(highs) < nd + 1:
            continue
        if not all(lows[-j][2] < lows[-j - 1][2] for j in range(1, nd + 1)) or not all(highs[-j][2] < highs[-j - 1][2] for j in range(1, nd + 1)):
            continue
        sc_i = i; sc_low = px; bump("1_downtrend_low")
        # prior counter-trend reactions of the downtrend: (spread, volume) of each up-swing before SC
        # Speed (byte-identical): only the LAST nd+1 reactions are ever read (`prior[-nd - 1:]`), so walk back from the
        # SC swing and stop once they are collected; the forward scan this replaces was O(swings before SC) per
        # candidate (O(swings^2) over a long series). Swing bars are non-decreasing and kinds alternate, so the
        # forward loop's `sw[a][0] >= sc_i` break and `sw[a + 1][0] <= sc_i` test only ever cut at a <= si - 2.
        assert nd >= 0, "downtrend_swings < 0: the backward prior loop would diverge from the original forward loop"
        prior = []
        a = si - 1
        while a >= 0 and len(prior) < nd + 1:
            if sw[a][1] == "L" and sw[a + 1][1] == "H" and sw[a][0] < sc_i and sw[a + 1][0] <= sc_i:
                prior.append((sw[a + 1][2] - sw[a][2], sum(V[sw[a][0]:sw[a + 1][0] + 1])))
            a -= 1
        prior.reverse()
        if not prior:
            continue
        ref_spread = sum(p[0] for p in prior) / len(prior); ref_vol = sum(p[1] for p in prior) / len(prior)  # "spread and effort larger than the trend's reactions" (WA p68); mean of the last reactions = project reading
        # --- CHoBEV counting on the up-swings after SC (R1) ---
        chobev = []; ar = None; broke = False; j = si
        while j + 2 < len(sw) and len(chobev) < P["chobev_needed"]:
            lo_s, hi_s = sw[j], sw[j + 1]
            if lo_s[1] != "L" or hi_s[1] != "H":
                j += 1; continue
            if lo_s[2] < sc_low - 1e-12 and lo_s[0] != sc_i and not P.get("fx_w2_st_below_sc"):
                broke = True; break            # downtrend continues: the CHoCH never completed
            # W2 (WA2-06, module docstring): fx_w2_st_below_sc on -- a low-swing below SC before the 3rd CHoBEV
            # (which may become ST[A] itself, found below) does not discard the structure; the book's own
            # reading of that case is "expect new lows or a prolonged consolidation with many further STs", not
            # "this was never an accumulation". The CHoBEV search below is otherwise unchanged.
            sp = hi_s[2] - lo_s[2]; vol = sum(V[lo_s[0]:hi_s[0] + 1])
            if sp > ref_spread and (po or vol > ref_vol):     # price_only: the spread leg alone
                chobev.append(hi_s[0])
            if ar is None:
                ar = hi_s                      # AR = first swing high after SC (WA p73)
            j += 2
        if broke:
            bump("2a_new_low_before_choch"); continue
        if len(chobev) < P["chobev_needed"] or ar is None:
            bump("2b_fewer_than_3_chobev"); continue
        bump("2_choch"); choch_bar = chobev[-1]
        tr_lo, tr_hi = sc_low, ar[2]; tr = tr_hi - tr_lo
        if tr <= 0:
            continue
        # --- ST[A]: first swing low after AR holding above SC (R3) ---
        # Speed (byte-identical): the same "first L swing after AR" as `next(s for s in sw[j0:] if s[1] == "L")`, without
        # copying the tail of `sw` (O(swings) per candidate).
        st = next((sw[j] for j in range(bisect.bisect_right(sw_bars, ar[0]), len(sw)) if sw[j][1] == "L"), None)
        if st is None:
            bump("3_no_st"); continue
        st_pct = (st[2] - tr_lo) / tr
        # --- đối nhãn Dấu hiệu 1 (R3, WA p150): which third of the TR is ST[A] sitting in? ---
        third = P["doi_nhan_third"]
        st_sign = "supports" if st_pct >= 2 * third else ("contradicts" if st_pct <= third else "neutral")
        # W1 (WA p72, module docstring): "Mức thấp của SC và ST và mức cao của AR thiết lập ranh giới của TR" --
        # the TR low is min(SC low, ST low), not SC low alone. st_pct/st_sign above are framed over the
        # Phase-A SC-AR range (WA p150's đối nhãn thirds) and are computed BEFORE this widening, so they are
        # unaffected; only the boundary every DOWNSTREAM Phase B/C/D read below uses (the break test, the
        # đối nhãn Dấu hiệu 2 thirds, the Test-after-Spring zone, the Phase-D target multiplier) is widened.
        if P.get("fx_w1_tr_low_st") and st[2] < tr_lo:
            tr_lo = st[2]; tr = tr_hi - tr_lo
        # --- Phase B: swings after ST; sloped check (R4, R5) ---
        # Speed (byte-identical): `after` = sw[after_lo:] read in place (`sw[after_lo + x]`, `n_after`), not copied per candidate.
        after_lo = bisect.bisect_right(sw_bars, st[0]); n_after = len(sw) - after_lo
        if not n_after:
            continue
        # walk bars from the CHoCH for the first break below the TR low
        start = max(choch_bar, st[0]) + 1; b_lows = [st[2]]
        b_swings = 0; spring = None; sloped = False; sot_lows = [lows[-2][2], sc_low, st[2]]; lpsc_sos = None; lpsc_sos_bar = None
        b_tests = {"upper": 0, "lower": 0}     # đối nhãn Dấu hiệu 2 (R3b, WA p154)
        # WY-3 (docs/audits/2026-09-24-system-audit.md; WA p85, p88-89): `tr_hi` stays the AR/Phase-A border
        # (used for the đối nhãn thirds and st_pct only, per the fix critique). `ceiling` tracks the highest
        # CONFIRMED Phase-B swing high seen so far -- the running UA resistance -- and is what SOS, the BU
        # zone and the Phase-D target are actually measured against, so a close above AR but still below a
        # Phase-B UA high stays inside the range instead of reading as strength (WA p85: SOS = "vượt qua khỏi
        # những điểm cao nhất trong Trading Range"; the XAUUSD/MATIC worked examples break the UA, not the AR).
        ceiling = tr_hi
        # WY-2 (docs/audits/2026-09-24-system-audit.md): this used to stop at `n - COMMIT`, a bound meant only
        # for the LPS[C] commitment look-ahead below. That silently made every Spring/reclaim within the last
        # COMMIT bars of the window invisible -- including same-bar reclaims exactly on the last bar, so the
        # book's type-1 "enter at the reclaim" leg (WA p80, Bảng 2.1) could never fire in `wyckoff_fires`'s
        # per-window read. The break search itself only ever looks at bar `b`; COMMIT is a LPS[C]-only
        # look-ahead and is now guarded locally (`b + COMMIT - 1 < n`) instead of truncating this whole loop.
        for b in range(start, n):
            # count swings completed so far in Phase B
            while b_swings < n_after and sw[after_lo + b_swings][0] + k <= b:
                s = sw[after_lo + b_swings]
                if s[1] == "L":
                    b_lows.append(s[2]); sot_lows.append(s[2])
                    if s[2] <= tr_lo + third * tr:
                        b_tests["lower"] += 1
                else:
                    if s[2] >= tr_lo + 2 * third * tr:
                        b_tests["upper"] += 1
                    ceiling = max(ceiling, s[2])   # WY-3: a confirmed Phase-B swing high raises the ceiling
                b_swings += 1
            if L[b] < tr_lo:
                if b_swings < P["min_phase_b_swings"]:
                    if not P.get("fx_w3_mSOW_spring"):
                        bump("4_break_before_phase_b"); break  # mSOW[B]: too early to be Phase C (R4) → discard this structure
                    # W3 (WA p166, module docstring): "MSOW[B] cũng là Spring tiềm năng" -- an early break is
                    # ALSO a potential Spring, not "never Spring/UT" (R4). Feed it through the SAME
                    # Spring/Shakeout/vol-type/reclaim/test/Phase-D pipeline below instead of discarding here.
                    bump("4b_mSOW_as_spring")
                if max(b_lows) - min(b_lows) > P["slope_max_tr"] * tr:
                    sloped = True
                spring = b; break
            # Phase C without Spring = LPS[C] (WA p81–83): the structure breaks out directly with an SOS.
            # WY-3: gated on `ceiling`, not the AR-only `tr_hi`. WY-2: guard the COMMIT look-ahead locally so
            # the outer loop can run to n-1.
            if (b_swings >= P["min_phase_b_swings"] and C[b] > ceiling and spread[b] >= avg(spread, b, lb)
                    and (po or V[b] >= avg(V, b, lb)) and b + COMMIT - 1 < n and all(C[b + m] > ceiling for m in range(1, COMMIT))):
                lpsc_sos_bar = b; lpsc_sos = b + COMMIT - 1; break
            # WY-3 follow-up (docs/audits/2026-09-24-system-audit.md, fix critique: "Check whether [the ran-away
            # guard] should use the Phase-B ceiling too, or UA-heavy structures will be discarded differently"):
            # gated on `ceiling` (the running Phase-B UA high), not the AR-only `tr_hi`. WA p88-89's own worked
            # examples run a UA well past the AR before the eventual SOS breaks the UA itself, not the AR
            # (advance.md: XAUUSD UA 1744->1750 makes "new resistance 1744-1750", SOS at 1754 "breaking the UA
            # resistance"; MATIC "SOS breaking UA 0.820000") -- a structure whose Phase-B excursion is itself a
            # legitimate (if large) UA must not be discarded here for the same reason SOS is no longer measured
            # against the AR alone above.
            if H[b] > ceiling + tr:            # ran away past the running UA ceiling without a Phase C test
                bump("4_ran_away"); break
        if spring is None and lpsc_sos is None:
            bump("4_no_phase_c"); continue
        bump("5_spring" if spring is not None else "5_lps_c")
        if spring is None:                     # LPS[C] path: only the Phase D entry exists
            used_until = lpsc_sos
            # WY-5: compare the pullback's volume to the BREAKOUT bar (lpsc_sos_bar, the bar that actually
            # passed the V>=avg effort test), not the follow-through/confirmation bar (lpsc_sos).
            bu = None; pull = None
            for q in range(lpsc_sos + 1, min(lpsc_sos + 1 + P["phase_d_window"], n)):
                if L[q] <= ceiling + 0.1 * tr and L[q] >= tr_lo + 0.5 * tr and (po or V[q] < V[lpsc_sos_bar]):
                    pull = q
                if pull is not None and q > pull and C[q] > O[q] and C[q] > ceiling:
                    # WY-4: stop under the WHOLE pullback (from the breakout, not just the last qualifying
                    # bar) -- min(L[sos+1:entry+1]), per the fix critique's timing-neutral formula.
                    bu = dict(low=min(L[lpsc_sos + 1:q + 1]), bar=q); break
            out.append(dict(sc=sc_i, ar=ar[0], st=st[0], choch=choch_bar, tr_lo=tr_lo, tr_hi=tr_hi, ceiling=ceiling, st_pct=round(st_pct, 2), st_sign=st_sign, volume_kind=volume_kind, phase_b_swings=b_swings,
                        phase_b_tests=dict(b_tests), phase_b_sign=("supports" if b_tests["upper"] > b_tests["lower"] else ("contradicts" if b_tests["lower"] > b_tests["upper"] else "neutral")),
                            sloped=(max(b_lows) - min(b_lows) > P["slope_max_tr"] * tr), spring=None, reclaim=None, shakeout=False, spring_low=None, vol_ratio=None,
                            vol_type=None, rec_ratio=None, sot_pushes=0, sot=False, sot_too_strong=False, vpoc=None, vah=None, val=None, lvn=None, abandon=False,
                            test=None, sos=lpsc_sos, sos_bar=lpsc_sos_bar, bu=bu, path="lps_c"))
            continue
        used_until = spring
        # --- Spring vs Shakeout (R6) ---
        outside = [q for q in range(spring, min(spring + P["spring_max_bars_outside"] + 1, n)) if C[q] < tr_lo]
        rec = next((q for q in range(spring, min(spring + P["spring_max_bars_outside"] + 1, n)) if C[q] > tr_lo), None)
        shakeout = rec is None or len(outside) > (rec - spring + 1) / 2
        if P.get("fx_w4a_linger_closes") is not None:
            # W4a (WA2-12, module docstring "V ITEMS"): lingering = closes below the border BEFORE the reclaim bar
            # (every bar in [spring, rec) failed to close back inside). No reclaim at all is always a Shakeout.
            shakeout = rec is None or sum(1 for q in range(spring, rec) if C[q] < tr_lo) >= P["fx_w4a_linger_closes"]
        spring_low = min(L[spring:(rec if rec is not None else spring) + 1])
        # --- volume type (R7 / WY-1): Spring table on the long side, Upthrust table on the short side --
        # see vol_type() above. `side` comes from the caller (detect_distributions passes "short"). ---
        av = avg(V, spring, lb); ratio = V[spring] / av if av else None
        vt = vol_type(ratio, side)
        rec_ratio = (V[rec] / av) if (rec is not None and av) else None
        # --- SOT into the low (R9) ---
        pushes = sot_pushes(sot_lows + [spring_low])
        # --- Volume Profile of the TR and the abandon rule (R10) ---
        lo_, step, hist = volume_profile(H, L, V, sc_i, spring - 1, P["vp_bins"])
        vpoc, vah, val, lvn = value_area(lo_, step, hist)
        abandon = False
        if lvn is not None and rec is not None:
            crossed = any(C[q] < lvn for q in range(spring, rec + 1))
            if P.get("fx_w5_vp_abandon"):
                # W5 (WMT p243-249, module docstring): the book gives no bar count for "without a reversal
                # reaction" -- the unsourced fixed "within 2 bars" window below is removed; the reclaim bar
                # itself (`rec`, the same close-back-inside-the-TR event R6 already defines) is tested against
                # VAL instead of a separate window.
                back = C[rec] > val
            else:
                back = any(C[q] > val for q in range(rec, min(rec + 3, n)))
            abandon = crossed and not back
        # --- Test after the Spring (R8) ---
        test = None
        if rec is not None:
            for q in range(rec + 1, min(rec + 1 + P["test_window"], n)):
                if L[q] < spring_low:
                    break
                if L[q] <= tr_lo + P["test_zone_tr"] * tr and (po or V[q] < V[spring]) and C[q] >= L[q] + 0.5 * (H[q] - L[q]):
                    test = q; break
        # --- Phase D: SOS then BU/LPS (R11) --- WY-3: gated on `ceiling` (the Phase-B extreme), not the
        # AR-only `tr_hi`, so a close between AR and the running Phase-B UA high stays inside the range.
        sos = sos_bar = bu = None
        if rec is not None:
            anchor = test if test is not None else rec
            for q in range(anchor + 1, min(anchor + 1 + P["phase_d_window"], n - COMMIT)):
                if L[q] < spring_low:
                    break
                if C[q] > ceiling and spread[q] >= avg(spread, q, lb) and (po or V[q] >= avg(V, q, lb)) and all(C[q + m] > ceiling for m in range(1, COMMIT)):
                    sos_bar = q; sos = q + COMMIT - 1; break
            if sos is not None:
                # WY-5: compare against the breakout bar's volume (sos_bar), not the follow-through bar's (sos).
                pull = None
                for q in range(sos + 1, min(sos + 1 + P["phase_d_window"], n)):
                    if L[q] <= ceiling + 0.1 * tr and L[q] >= tr_lo + 0.5 * tr and (po or V[q] < V[sos_bar]):
                        pull = q
                    if pull is not None and q > pull and C[q] > O[q] and C[q] > ceiling:
                        # WY-4: stop under the whole pullback since the breakout, not just the last qualifying bar.
                        bu = dict(low=min(L[sos + 1:q + 1]), bar=q); break
        out.append(dict(sc=sc_i, ar=ar[0], st=st[0], choch=choch_bar, tr_lo=tr_lo, tr_hi=tr_hi, ceiling=ceiling, st_pct=round(st_pct, 2), st_sign=st_sign, volume_kind=volume_kind, phase_b_swings=b_swings,
                        phase_b_tests=dict(b_tests), phase_b_sign=("supports" if b_tests["upper"] > b_tests["lower"] else ("contradicts" if b_tests["lower"] > b_tests["upper"] else "neutral")),
                        sloped=sloped, spring=spring, reclaim=rec, shakeout=shakeout, spring_low=spring_low, vol_ratio=(round(ratio, 2) if ratio else None),
                        vol_type=vt, rec_ratio=rec_ratio, sot_pushes=pushes, sot=(SOT_MIN <= pushes <= SOT_MAX), sot_too_strong=pushes > SOT_MAX,
                        vpoc=vpoc, vah=vah, val=val, lvn=lvn, abandon=abandon, test=test, sos=sos, sos_bar=sos_bar, bu=bu, path="spring"))
    return out


def detect_distributions(O, H, L, C, V, P=PARAMS, volume_kind="traded", pivots=None, pre=None):
    """Mirror: run the accumulation detector on inverted prices (WA p101 schematics are mirror images) and map
    prices back. side="short" (WY-1, docs/audits/2026-09-24-system-audit.md) so the break bar is typed with the
    Upthrust table (Bang 2.2), not the Spring table -- detect_accumulations no longer assumes it is always
    reading a Spring."""
    inv = lambda xs: [-x for x in xs]
    # `pivots` (if any) was built for the ORIGINAL prices: on -L / -H a high pivot is a low pivot and vice versa,
    # so the flags arrive already swapped (window_pivots(..., swap=True)).
    recs = detect_accumulations(inv(O), inv(L), inv(H), inv(C), V, P, volume_kind, side="short", pivots=pivots, pre=pre)
    for r in recs:
        for key in ("tr_lo", "tr_hi", "spring_low", "vpoc", "vah", "val", "lvn", "ceiling"):
            if r.get(key) is not None:
                r[key] = -r[key]
        r["tr_lo"], r["tr_hi"] = r["tr_hi"], r["tr_lo"]
        r["vah"], r["val"] = r["val"], r["vah"]
        if r["bu"]:
            r["bu"]["low"] = -r["bu"]["low"]
        # st_pct keeps its meaning: fraction of the TR travelled from the SC/BC border toward the AR
    return recs
