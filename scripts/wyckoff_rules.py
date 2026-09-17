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
  R3  ST[A] position (WA p75, p77; p150 đối nhãn 1): recorded as st_pct = (ST low − SC low)/TR; ST above 50% = supply thinned,
      ST below SC = supply abundant. Exposed as a filter, not hardcoded.
  R4  Phase B must exist before a Phase C call (WA p79, WA3-08 p189–190): a border break before PARAMS.min_phase_b_swings
      swings after ST is mSOW[B]/UA[B], never Spring/UT.
  R5  Sloped structure → do not trade (WA p167, p170): skip when Phase-B swing lows drift by more than PARAMS.slope_max_tr of the TR.
  R6  Spring vs Shakeout (WA p80, p83): price must close back inside within PARAMS.spring_max_bars_outside bars and fewer than
      half the excursion bars may close below the border; otherwise it is a Shakeout (supply remains) → no direct entry (WA2-12).
  R7  Spring/Upthrust volume type 1/2/3 (WMT p049, knowledge/wyckoff/modern-tools.md §2.6–2.7) with the volume thresholds of analysis-params.json.
  R8  Test after the Spring (WA p80): a pullback holding above the Spring low, inside the lower third of the TR, on volume lower
      than the Spring bar, closing in its upper half. Type 2 needs it (WMT p049); type 1 may enter at the reclaim (WA p80, partial).
  R9  SOT into the border (WA p278–284): successive pushes into the low with shortening distance; ≥3 pushes = valid SOT; more than 4
      pushes = trend too strong to oppose. Recorded (sot_pushes, sot) and exposed as a filter.
  R10 Volume Profile of the TR (WA p259–265, WMT p243–249): VPOC, VAH/VAL at 68.2 % of volume, LVN just beyond VAL; the abandon
      rule: if the Spring excursion closes beyond the LVN and does not close back above VAL within 2 bars, the plan is abandoned.
  R11 Phase D entry (WA p83–85): SOS = close above the TR high with widening spread and volume ≥ average, held for
      PARAMS.commitment_bars closes; BU/LPS = the first pullback to the TR top on lower volume; entry at the first up-close of the
      pullback, stop under the pullback low, target = TR top + 1 TR (PROJECT PARAMETER — the book gives no numeric projection).
  R12 Stop under the Spring low (WMT p271); first target = opposite border (WMT p273, WA p83–84); breakeven at +1R (WMT p272) is
      handled by the caller's walk().
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
    vp_bins=30,                 # Volume Profile resolution (project)
    phase_d_window=40,          # bars to wait for SOS + BU after the Spring/Test (project)
    d_target_tr=1.0,            # Phase D target = TR top + this × TR (project)
    lookback=20,                # average window for volume/spread ratios (analysis-params lookback_bars)
)


def swings(H, L, k):
    """Alternating swing list [(bar, 'H'|'L', price)] from k-bar pivots; consecutive same-kind pivots keep the more extreme one."""
    out = []
    for i in range(k, len(H) - k):
        isH = all(H[j] <= H[i] for j in range(i - k, i + k + 1) if j != i)
        isL = all(L[j] >= L[i] for j in range(i - k, i + k + 1) if j != i)
        for kind, px in ((("H", H[i]),) if isH else ()) + ((("L", L[i]),) if isL else ()):
            if out and out[-1][1] == kind:
                if (kind == "H" and px >= out[-1][2]) or (kind == "L" and px <= out[-1][2]):
                    out[-1] = (i, kind, px)
            else:
                out.append((i, kind, px))
    return out


def avg(xs, i, n):
    w = xs[max(0, i - n):i]
    return sum(w) / len(w) if w else 0.0


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


def detect_accumulations(O, H, L, C, V, P=PARAMS):
    """Walk the series and return every accumulation structure that reaches a Spring candidate, with all rule outputs.
    Each record: dict(sc, ar, st, tr_lo, tr_hi, st_pct, chobev_bars, phase_b_swings, sloped, spring=dict(...), ...)."""
    n = len(C); k = P["pivot"]; sw = swings(H, L, k); out = []
    lb = P["lookback"]
    spread = [h - l for h, l in zip(H, L)]
    used_until = -1
    for si in range(4, len(sw)):
        i, kind, px = sw[si]
        if kind != "L" or i <= used_until:
            continue
        # --- downtrend before the candidate SC: lower lows and lower highs (R1 precondition) ---
        lows = [s for s in sw[:si + 1] if s[1] == "L"]; highs = [s for s in sw[:si] if s[1] == "H"]
        nd = P["downtrend_swings"]
        if len(lows) < nd + 1 or len(highs) < nd + 1:
            continue
        if not all(lows[-j][2] < lows[-j - 1][2] for j in range(1, nd + 1)) or not all(highs[-j][2] < highs[-j - 1][2] for j in range(1, nd + 1)):
            continue
        sc_i = i; sc_low = px; bump("1_downtrend_low")
        # prior counter-trend reactions of the downtrend: (spread, volume) of each up-swing before SC
        prior = []
        for a in range(len(sw) - 1):
            if sw[a][0] >= sc_i:
                break
            if sw[a][1] == "L" and sw[a + 1][1] == "H" and sw[a + 1][0] <= sc_i:
                prior.append((sw[a + 1][2] - sw[a][2], sum(V[sw[a][0]:sw[a + 1][0] + 1])))
        prior = prior[-nd - 1:]
        if not prior:
            continue
        ref_spread = sum(p[0] for p in prior) / len(prior); ref_vol = sum(p[1] for p in prior) / len(prior)  # "spread and effort larger than the trend's reactions" (WA p68); mean of the last reactions = project reading
        # --- CHoBEV counting on the up-swings after SC (R1) ---
        chobev = []; ar = None; broke = False; j = si
        while j + 2 < len(sw) and len(chobev) < P["chobev_needed"]:
            lo_s, hi_s = sw[j], sw[j + 1]
            if lo_s[1] != "L" or hi_s[1] != "H":
                j += 1; continue
            if lo_s[2] < sc_low - 1e-12 and lo_s[0] != sc_i:
                broke = True; break            # downtrend continues: the CHoCH never completed
            sp = hi_s[2] - lo_s[2]; vol = sum(V[lo_s[0]:hi_s[0] + 1])
            if sp > ref_spread and vol > ref_vol:
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
        st = next((s for s in sw if s[0] > ar[0] and s[1] == "L"), None)
        if st is None:
            bump("3_no_st"); continue
        st_pct = (st[2] - tr_lo) / tr
        # --- Phase B: swings after ST; sloped check (R4, R5) ---
        after = [s for s in sw if s[0] > st[0]]
        if not after:
            continue
        # walk bars from the CHoCH for the first break below the TR low
        start = max(choch_bar, st[0]) + 1; b_lows = [st[2]]
        b_swings = 0; spring = None; sloped = False; sot_lows = [lows[-2][2], sc_low, st[2]]; lpsc_sos = None
        for b in range(start, n - COMMIT):
            # count swings completed so far in Phase B
            while b_swings < len(after) and after[b_swings][0] + k <= b:
                s = after[b_swings]
                if s[1] == "L":
                    b_lows.append(s[2]); sot_lows.append(s[2])
                b_swings += 1
            if L[b] < tr_lo:
                if b_swings < P["min_phase_b_swings"]:
                    bump("4_break_before_phase_b"); break  # mSOW[B]: too early to be Phase C (R4) → discard this structure
                if max(b_lows) - min(b_lows) > P["slope_max_tr"] * tr:
                    sloped = True
                spring = b; break
            # Phase C without Spring = LPS[C] (WA p81–83): the structure breaks out directly with an SOS
            if b_swings >= P["min_phase_b_swings"] and C[b] > tr_hi and spread[b] >= avg(spread, b, lb) and V[b] >= avg(V, b, lb) and all(C[b + m] > tr_hi for m in range(1, COMMIT)):
                lpsc_sos = b + COMMIT - 1; break
            if H[b] > tr_hi + tr:              # ran away without a Phase C test: not our setup
                bump("4_ran_away"); break
        if spring is None and lpsc_sos is None:
            bump("4_no_phase_c"); continue
        bump("5_spring" if spring is not None else "5_lps_c")
        if spring is None:                     # LPS[C] path: only the Phase D entry exists
            used_until = lpsc_sos
            bu = None; pull = None
            for q in range(lpsc_sos + 1, min(lpsc_sos + 1 + P["phase_d_window"], n)):
                if L[q] <= tr_hi + 0.1 * tr and L[q] >= tr_lo + 0.5 * tr and V[q] < V[lpsc_sos]:
                    pull = q
                if pull is not None and q > pull and C[q] > O[q] and C[q] > tr_hi:
                    bu = dict(low=min(L[pull:q + 1]), bar=q); break
            out.append(dict(sc=sc_i, ar=ar[0], st=st[0], choch=choch_bar, tr_lo=tr_lo, tr_hi=tr_hi, st_pct=round(st_pct, 2), phase_b_swings=b_swings,
                            sloped=(max(b_lows) - min(b_lows) > P["slope_max_tr"] * tr), spring=None, reclaim=None, shakeout=False, spring_low=None, vol_ratio=None,
                            vol_type=None, rec_ratio=None, sot_pushes=0, sot=False, sot_too_strong=False, vpoc=None, vah=None, val=None, lvn=None, abandon=False,
                            test=None, sos=lpsc_sos, bu=bu, path="lps_c"))
            continue
        used_until = spring
        # --- Spring vs Shakeout (R6) ---
        outside = [q for q in range(spring, min(spring + P["spring_max_bars_outside"] + 1, n)) if C[q] < tr_lo]
        rec = next((q for q in range(spring, min(spring + P["spring_max_bars_outside"] + 1, n)) if C[q] > tr_lo), None)
        shakeout = rec is None or len(outside) > (rec - spring + 1) / 2
        spring_low = min(L[spring:(rec if rec is not None else spring) + 1])
        # --- volume type (R7) ---
        av = avg(V, spring, lb); ratio = V[spring] / av if av else None
        vt = None if ratio is None else (1 if ratio < VOL["low_max_ratio"] else (3 if ratio > VOL["high_min_ratio"] else 2))
        rec_ratio = (V[rec] / av) if (rec is not None and av) else None
        # --- SOT into the low (R9) ---
        pushes = sot_pushes(sot_lows + [spring_low])
        # --- Volume Profile of the TR and the abandon rule (R10) ---
        lo_, step, hist = volume_profile(H, L, V, sc_i, spring - 1, P["vp_bins"])
        vpoc, vah, val, lvn = value_area(lo_, step, hist)
        abandon = False
        if lvn is not None and rec is not None:
            crossed = any(C[q] < lvn for q in range(spring, rec + 1))
            back = any(C[q] > val for q in range(rec, min(rec + 3, n)))
            abandon = crossed and not back
        # --- Test after the Spring (R8) ---
        test = None
        if rec is not None:
            for q in range(rec + 1, min(rec + 1 + P["test_window"], n)):
                if L[q] < spring_low:
                    break
                if L[q] <= tr_lo + P["test_zone_tr"] * tr and V[q] < V[spring] and C[q] >= L[q] + 0.5 * (H[q] - L[q]):
                    test = q; break
        # --- Phase D: SOS then BU/LPS (R11) ---
        sos = bu = None
        if rec is not None:
            anchor = test if test is not None else rec
            for q in range(anchor + 1, min(anchor + 1 + P["phase_d_window"], n - COMMIT)):
                if L[q] < spring_low:
                    break
                if C[q] > tr_hi and spread[q] >= avg(spread, q, lb) and V[q] >= avg(V, q, lb) and all(C[q + m] > tr_hi for m in range(1, COMMIT)):
                    sos = q + COMMIT - 1; break
            if sos is not None:
                pull = None
                for q in range(sos + 1, min(sos + 1 + P["phase_d_window"], n)):
                    if L[q] <= tr_hi + 0.1 * tr and L[q] >= tr_lo + 0.5 * tr and V[q] < V[sos]:
                        pull = q
                    if pull is not None and q > pull and C[q] > O[q] and C[q] > tr_hi:
                        bu = dict(low=min(L[pull:q + 1]), bar=q); break
        out.append(dict(sc=sc_i, ar=ar[0], st=st[0], choch=choch_bar, tr_lo=tr_lo, tr_hi=tr_hi, st_pct=round(st_pct, 2), phase_b_swings=b_swings,
                        sloped=sloped, spring=spring, reclaim=rec, shakeout=shakeout, spring_low=spring_low, vol_ratio=(round(ratio, 2) if ratio else None),
                        vol_type=vt, rec_ratio=rec_ratio, sot_pushes=pushes, sot=(SOT_MIN <= pushes <= SOT_MAX), sot_too_strong=pushes > SOT_MAX,
                        vpoc=vpoc, vah=vah, val=val, lvn=lvn, abandon=abandon, test=test, sos=sos, bu=bu, path="spring"))
    return out


def detect_distributions(O, H, L, C, V, P=PARAMS):
    """Mirror: run the accumulation detector on inverted prices (WA p101 schematics are mirror images) and map prices back."""
    inv = lambda xs: [-x for x in xs]
    recs = detect_accumulations(inv(O), inv(L), inv(H), inv(C), V, P)
    for r in recs:
        for key in ("tr_lo", "tr_hi", "spring_low", "vpoc", "vah", "val", "lvn"):
            if r.get(key) is not None:
                r[key] = -r[key]
        r["tr_lo"], r["tr_hi"] = r["tr_hi"], r["tr_lo"]
        r["vah"], r["val"] = r["val"], r["vah"]
        if r["bu"]:
            r["bu"]["low"] = -r["bu"]["low"]
        # st_pct keeps its meaning: fraction of the TR travelled from the SC/BC border toward the AR
    return recs
