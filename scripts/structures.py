#!/usr/bin/env python3
"""THE structure source (ADR 0009; docs/plans/2026-09-28-methodology-improvement-plan.md §2 item A1).

Before this module, structure was computed once per method (scripts/ict-scan.py `analyze()` /
`setup_candidate()`, scripts/wyckoff_rules.py `detect_accumulations()` / `detect_distributions()`) and the
decision path (scripts/live_rules.py, scripts/backtest-methods.py, scripts/strategy-runner.py) read those raw
dicts directly. ADR 0009 requires ONE structure source that both the decision path and (later, A2) the chart
consume. This module does NOT recompute detection -- it calls the existing functions and wraps their output
into a schema of plain, timestamped objects. A1 is a REFACTOR: every existing reader of `analyze()` /
`detect_accumulations()` / `detect_distributions()` keeps reading those functions' unchanged return values;
this module adds a normalized VIEW over the same data, and the two seams that decide entries (live_rules.py's
read_at, backtest-methods.py's _wyckoff_candidates) are re-plumbed to obtain their raw data by calling INTO
this module rather than calling ict_scan.analyze() / wyckoff_rules.detect_*() directly -- so this module really
is in the decision path, not merely available beside it, while returning byte-identical underlying objects.

Hot-path / cold-path split (A1 code review round 1, item 4). `read_at()` and `_wyckoff_candidates()` run once
per bar/window in a backtest (tens of thousands of calls); the enriched structure objects (pivots, pools, MSS,
FVGs, dealing range, bias / trading-range events) are not read on that path at all -- only the raw `analyze()` /
`detect_*()` result is. Building the enriched objects on every call regardless was pure waste. `ict_analysis()`
and `wyckoff_records()` below are the raw pass-throughs the hot path uses (literally the wrapped call, zero
extra allocation); `ict_structures()` and `wyckoff_structures()` build the full enriched envelope ON TOP of
those raw calls, for callers that actually want the typed objects (A2, tests, research tooling). Both are still
"in structures.py" -- ADR 0009's one-source requirement is about where detection is called from and how its
output is shaped when structure is wanted, not that every hot-path call must materialize every field.

Schema. Every structure object is a plain dict with at least:
    kind          -- one of: pivot_high, pivot_low, pool, sweep, closed_through, mss, fvg, dealing_range, bias
                     (ICT); trading_range, sc, ar, st, choch, spring, reclaim, test, sos, bu (Wyckoff events)
    formed_at     -- ISO-8601 "...Z" open time of the bar where the structure formed (never the forming bar --
                     ict-scan.causal_window()/live_rules.window() already keep the still-forming bar out of the
                     window this module is handed)
    available_at  -- ISO-8601 "...Z" from scripts/normalized.py available_time(): when this structure actually
                     became knowable (CLAUDE.md §8 availableTime <= decisionTime). This is NOT always
                     available_time(formed_at)'s own bar -- see "Confirmation delay" below. Computed here, never
                     re-invented -- every timestamp in this module goes through `_avail()`, the one call site.

Confirmation delay (A1 code review round 1, item 1). Several ICT structures are not knowable as soon as their
own bar closes -- the detection rule itself needs LATER bars' data:
    pivot_high/pivot_low -- a `PIV`-bar pivot at bar `i` (ict-scan.py's `PIV = pivot_bars` half-width) compares
        H[i]/L[i] against `PIV` bars on EACH side (`range(i - PIV, i + PIV + 1)`); it is not confirmable until
        bar `i + PIV` closes. formed_at is bar `i` (where the extremum sits); available_at is bar `i + PIV`.
    fvg -- a 3-candle gap at `i` compares H[i-1] against L[i+1] (bull) or L[i-1] against H[i+1] (bear); it needs
        bar `i + 1`'s high/low, so available_at is bar `i + 1`, not bar `i`.
    pool -- an "old" pool is a single pivot (`to == from`); an "equal" pool needs its SECOND matching pivot to
        exist as a pool at all, and ict-scan.py's `add()` additively returns the LAST constituent pivot's bar
        index as `to` for exactly this reason (A1 code review round 1). available_at is therefore
        `to + PIV` -- the confirmation delay of the LATER of the pool's constituent pivots -- never `from`'s.
`mss` and `sweep`/`closed_through` are single-bar body-close tests (`C[j] > level`); they need no look-ahead
beyond their own bar, so their available_at is their own bar's, unchanged.

Pool objects carry FORMATION fields only (A1 code review round 1, item 3): `pool_kind` (ict-scan.py's own
"kind", BSL/SSL -- renamed to avoid colliding with this schema's `kind`), `level`, `from`, `to`, `type`. They do
NOT carry `state`/`swept`/`closed_at`: those are determined by a FORWARD scan over bars strictly after the pool
formed (ict-scan.py's `add()`, "for j in range(last + 1, n)"), so stamping them onto an object timestamped at
the pool's OWN formation bar would silently attach future information to a past timestamp -- exactly the kind
of look-ahead-shaped defect CLAUDE.md §8 exists to prevent. That forward-scanned state is instead exposed as
its own, separately and correctly timestamped `sweep` / `closed_through` object (already the case before this
fix; this fix only removes the duplicate, mistimed copy that used to also live on the `pool` object).

Kind-specific fields are otherwise copied VERBATIM from the wrapped function's record (same keys, same values)
so a caller that already knows the old shape (e.g. an mss event's `type`/`level`) finds it unchanged inside the
wrapped object.

ICT (`ict_structures`): pivots, pools (formation only; state via `sweep`/`closed_through`), sweeps, MSS, FVGs,
dealing range, bias -- the ADR 0009 list. Wyckoff (`wyckoff_structures`): trading range and events -- the ADR
0009 list.

A1b (plan §2 item A1b; declared NEW, not byte-identical): Wyckoff phase LABELS and `invalidated_at` for
pools/FVGs. Both are ADDITIVE fields computed from data the wrapped functions already returned -- neither
changes `analysis`/`records` (still byte-identical, A1's own invariant) and neither is read by any hot-path
decision call (`ict_analysis`/`wyckoff_records`), only by the enriched envelope A2 (the chart) consumes.
  * A pool's/FVG's `invalidated_at` is set only when the wrapped function's OWN forward scan already found the
    level consumed: a pool whose `state` is "closed_through" (ict-scan.py `add()`, a completed body close
    beyond the level -- never "swept", which is a level that held), or an FVG whose `mitigated` is true (a
    later bar's wick traded back into the gap). The timestamp is that confirming bar's own `available_time()`,
    clamped to >= the object's own `available_at` (S5: never invalidated before it is available)
    -- no PIV/i+1 confirmation delay applies here (both tests are single-bar wick/close tests against an
    already-known level, the same "no look-ahead beyond its own bar" case `mss`/`sweep`/`closed_through`
    already are, module docstring above). A2 (chart.js) draws an invalidated pool/FVG ending at this bar, not
    edge to edge.
  * Wyckoff phase labels (A/B/C/D/E) are boundaries read off the SAME event bars `wyckoff_records()` already
    named on its return record (sc/ar/st = Phase A stopping action; st..spring/test = Phase B building the
    cause; spring/test = Phase C testing supply/demand; sos/sos_bar..bu = Phase D; after bu = Phase E markup)
    -- knowledge/wyckoff/advance.md's own event vocabulary (WA p68-96), which is exactly why wyckoff_rules.py
    already names its record fields sc/ar/st/spring/sos/bu. No new detection: a phase's boundary is one of
    those already-detected bars, and a phase's `available_at` is the `available_time()` of the bar that CONFIRMS its
    boundaries (the SOS boundary is confirmed at `sos = sos_bar + COMMIT - 1`, not at `sos_bar`), clamped to
    >= the parent trading range's own `available_at` -- never earlier. A phase whose closing event has not happened yet in this record (Phase E always; Phase D
    when `bu` is None; Phase C/B when the next event is None) is `status: "hypothesis"` -- open, not yet
    confirmed closed -- matching chart.js's existing hypothesis/tested rendering (P6.2, docs/audits/
    2026-09-24-wyckoff-label-review.md; WA p166 warns against labelling mechanically). This is a NEW,
    project-level labelling convention, not itself a sourced page citation for the A/B/C/D/E cut points beyond
    the event vocabulary already cited above -- disclosed as such in docs/audits/2026-09-29-a2-chart-from-
    engine.md.

The higher-timeframe Wyckoff trading-range detector A1b also names (WA2-19, needed by plan item W7) is NOT
added here -- that is new DETECTION (a second trading range on a different timeframe), out of this module's
"wrap, do not detect" contract, and belongs with the Wyckoff F-item workstream that owns wyckoff_rules.py.
"""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import normalized as N   # noqa: E402 -- the one available_time() (CLAUDE.md §8), never re-derived here
import wyckoff_rules as W  # noqa: E402 -- detect_accumulations/detect_distributions, unchanged


def _load(name, mod):
    """ict-scan.py has a dash in its filename and cannot be `import`ed directly -- the same loader
    scripts/live_rules.py and scripts/htf_context.py already use for it."""
    spec = importlib.util.spec_from_file_location(mod, os.path.join(ROOT, "scripts", name))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


ict_scan = _load("ict-scan.py", "ict_scan")
htf_context = _load("htf_context.py", "htf_context")
PIV = ict_scan.PIV   # the one pivot half-width (ict-scan.py, from analysis-params.json) -- never restated


def _formed(window, i):
    return window[i]["time"]


def _avail(window, i, tf):
    """available_time() of bar `i` of `window`, on timeframe `tf`. The one call site for
    normalized.available_time() in this module -- see the module docstring."""
    return N.available_time(window[i], tf).isoformat().replace("+00:00", "Z")


def _ts(window, i, tf):
    """(formed_at, available_at) when a structure's confirmation needs no bar beyond its own -- the common
    case (mss, sweep, closed_through, an fvg's/pool's formed_at). See the module docstring for the structures
    whose available_at is a LATER bar than formed_at (pivots, fvgs, pools)."""
    return _formed(window, i), _avail(window, i, tf)


# ---------------------------------------------------------------------------------------------------- ICT


def ict_analysis(window, recent, tf, methods=("ict",), opts=None):
    """The RAW scripts/ict-scan.py `analyze()` call -- for hot-path callers (scripts/live_rules.py `read_at()`)
    that need only `a`, never the enriched structure objects. This IS that call: zero extra allocation over
    calling `ict_scan.analyze()` directly (see the module docstring, "Hot-path / cold-path split").

    `opts` -- passthrough only (docs/plans/2026-09-29-execution-plan.md "Shared contract" fx_ keys); this
    module does not read or default any fx_ key itself, so `opts=None` reproduces v1 exactly, same as
    `ict_scan.analyze()`'s own default."""
    return ict_scan.analyze(window, recent, tf=tf, methods=methods, opts=opts)


def ict_structures(window, recent, tf, methods=("ict",), analysis=None):
    """The ICT structures `window` already implies, wrapped from scripts/ict-scan.py `analyze()`.

    `analysis`: a caller that already ran `analyze()` for this window (scripts/live_rules.py's `bias_at` reuses
    `read_at`'s facts the same way) passes the result through instead of paying for a second scan -- this is
    NOT caching, the same non-caching convention scripts/live_rules.py's `bias_at` docstring already states.

    Returns {"analysis": a, "structures": [...], "dealing_range": {...}, "bias": {...} | None} where `a` is
    EXACTLY what `analyze()` returned (same object, not copied) -- a caller that only wants the raw dict (every
    existing reader of `analyze()`'s output) can keep using `env["analysis"]` unchanged, or call `ict_analysis()`
    directly and skip building this envelope entirely."""
    a = analysis if analysis is not None else ict_analysis(window, recent, tf, methods=methods)
    structs = []
    n = len(window)

    for i in a.get("pivots_high", []):
        # Confirmation delay: a PIV-bar pivot is not confirmable until bar i+PIV closes (module docstring).
        structs.append({"kind": "pivot_high", "i": i, "price": window[i]["high"],
                         "formed_at": _formed(window, i), "available_at": _avail(window, min(i + PIV, n - 1), tf)})
    for i in a.get("pivots_low", []):
        structs.append({"kind": "pivot_low", "i": i, "price": window[i]["low"],
                         "formed_at": _formed(window, i), "available_at": _avail(window, min(i + PIV, n - 1), tf)})

    for p in a["pools"]:
        # Formation fields only (module docstring, "Pool objects carry FORMATION fields only") -- state/swept/
        # closed_at are forward-scanned past the pool's own formation bar and belong on the separately
        # timestamped sweep/closed_through objects below, never on this one. `invalidated_at` (A1b) is the ONE
        # exception: it is not restoring the removed state/swept/closed_at fields, it is a single derived
        # timestamp -- set only when the wrapped function's own scan found the level CLOSED THROUGH (a real
        # break, never a "swept" wick-and-hold), timestamped at that confirming bar, same as the separate
        # closed_through structure object below carries.
        to = p.get("to", p["from"])
        pool_available_at = _avail(window, min(to + PIV, n - 1), tf)
        # S5: an object can never be invalidated before it is available (CLAUDE.md §8) -- clamp to available_at.
        pool_invalidated_at = (max(_avail(window, p["closed_at"], tf), pool_available_at)
                                if p.get("state") == "closed_through" and p.get("closed_at") is not None else None)
        structs.append({"kind": "pool", "pool_kind": p["kind"], "level": p["level"], "from": p["from"], "to": to,
                         "type": p["type"], "formed_at": _formed(window, p["from"]),
                         "available_at": pool_available_at,
                         "invalidated_at": pool_invalidated_at})
        if p["swept"] >= 0:
            sf, sa = _ts(window, p["swept"], tf)
            structs.append({"kind": "sweep", "pool_kind": p["kind"], "level": p["level"], "i": p["swept"],
                             "formed_at": sf, "available_at": sa})
        elif p["state"] == "closed_through" and p.get("closed_at") is not None:
            cf, ca = _ts(window, p["closed_at"], tf)
            structs.append({"kind": "closed_through", "pool_kind": p["kind"], "level": p["level"], "i": p["closed_at"],
                             "formed_at": cf, "available_at": ca})

    for m in a.get("mss_all", a["mss"]):
        formed_at, available_at = _ts(window, m["i"], tf)
        structs.append(dict(m, kind="mss", formed_at=formed_at, available_at=available_at))

    for f in a["fvgs_all"]:
        # Confirmation delay: the gap at i needs bar i+1's high/low (H[i-1] vs L[i+1], or L[i-1] vs H[i+1]).
        # `invalidated_at` (A1b): set only when ict-scan.py's own mitigation scan already found a later bar
        # trading back into the gap (`f["mitigated"]`) -- `f["end"]` IS that bar (ict-scan.py analyze(), the
        # first j with L[j]<=f["hi"] (bull) / H[j]>=f["lo"] (bear)), a single-bar wick test against an
        # already-known range, so no further confirmation delay applies (same reasoning as the pool's
        # closed_through above).
        fvg_available_at = _avail(window, min(f["i"] + 1, n - 1), tf)
        fvg_invalidated_at = (max(_avail(window, f["end"], tf), fvg_available_at) if f.get("mitigated") else None)
        structs.append(dict(f, kind="fvg", formed_at=_formed(window, f["i"]),
                             available_at=fvg_available_at,
                             invalidated_at=fvg_invalidated_at))

    dr_formed_at, dr_available_at = _ts(window, n - 1, tf)
    dealing_range = {"kind": "dealing_range", "lo": a["lo"], "hi": a["hi"], "eq": a["eq"], "pct": a["pct"],
                      "source": a["dr_source"], "formed_at": dr_formed_at, "available_at": dr_available_at}

    bias = None
    m = a.get("last_displaced_mss")
    pc = a.get("prev_candle")
    if m or pc:
        # htf_context.ict_bias() is the ONE bias computation (CLAUDE.md §13 methodology != setup); called here
        # unchanged on a minimal facts-shaped dict carrying exactly the two fields it reads
        # (scripts/htf_context.py:187,213), so this is the same read facts_entry()/prelim_html() already do,
        # not a second bias rule.
        direction, basis = htf_context.ict_bias({"prev_candle": pc, "last_displaced_mss": m})
        # A1 code review round 1, item 2: available_at is the LATER of every bar the read actually consulted.
        # pc's pch_state/pcl_state (ict-scan.py analyze()) are computed from C[n-1]/H[n-1]/L[n-1] -- window[-1]
        # -- REGARDLESS of which state ends up firing, so pc's presence alone pins a candidate at window[-1]
        # (a safe over-approximation: never claims availability before the bar whose data was read, even on
        # the branch where that bar's data did not end up changing the verdict). m's candidate is its own MSS
        # bar. Previously this used `m["i"] if m else ...` -- which silently ignored pc's window[-1] read
        # whenever an MSS was ALSO present, understating available_at whenever the two combined.
        candidates = []
        if pc:
            candidates.append(n - 1)
        if m:
            candidates.append(m["i"])
        bar_i = max(candidates)
        bias = {"kind": "bias", "direction": direction, "basis": basis,
                "formed_at": _formed(window, bar_i), "available_at": _avail(window, bar_i, tf)}

    return {"analysis": a, "structures": structs, "dealing_range": dealing_range, "bias": bias}


# ------------------------------------------------------------------------------------------------- Wyckoff


_WY_EVENT_BARS = ("sc", "ar", "st", "choch", "spring", "reclaim", "test", "sos", "sos_bar")


def wyckoff_records(O, H, L, C, V, P=None, volume_kind="traded", side="long", pivots=None):
    """The RAW scripts/wyckoff_rules.py `detect_accumulations()` (side="long") / `detect_distributions()`
    (side="short") call -- for hot-path callers (scripts/backtest-methods.py `_wyckoff_candidates()`) that need
    only the records, never the enriched trading_range objects and never a per-window `candles` list built
    solely to timestamp them. This IS that call: zero extra allocation over calling `W.detect_accumulations()`/
    `W.detect_distributions()` directly (see the module docstring, "Hot-path / cold-path split")."""
    kwargs = {} if P is None else {"P": P}
    if pivots is not None:      # speed: the window's pivots, pre-computed once per series (wyckoff_rules.swings)
        kwargs["pivots"] = pivots
    return (W.detect_accumulations(O, H, L, C, V, volume_kind=volume_kind, **kwargs) if side == "long"
            else W.detect_distributions(O, H, L, C, V, volume_kind=volume_kind, **kwargs))


def _wy_bar(v):
    """A record field that is sometimes a plain bar index, sometimes a {"bar":...} dict (`bu`) -- one accessor,
    so the phase-bounds table below reads every field the same way."""
    if v is None:
        return None
    return v.get("bar") if isinstance(v, dict) else v


def _wy_phase_bounds(r):
    """Phase boundaries (A1b), as (letter, start_bar, end_bar_or_None, start_conf_bar, end_conf_bar_or_None) -- the
    last two are the bars that CONFIRM each boundary (equal to the boundary bar itself except the SOS, I3) -- book basis: knowledge/wyckoff/
    advance.md's own WA event vocabulary, the SAME vocabulary wyckoff_rules.py already names its record fields
    after (module docstring above): SC/AR/ST = Phase A stopping action (WA p68-72); ST..Spring/Test = Phase B
    building the cause (WA p79-83, R4 "Phase B must exist before a Phase C call"); Spring/Test = Phase C (WA
    p80-85); SOS/SOS_bar..BU = Phase D (WA p85-91); after BU = Phase E markup (WA p91). `end_bar=None` means
    "open -- runs to the last bar this record confirms so far", which is what makes that phase `status:
    "hypothesis"` below (WA p166: do not label a phase mechanically past what the record has actually shown).

    The "lps_c" path (wyckoff_rules.py's W-BU majority path, spring=test=None, straight ST -> SOS/BU) has no
    Phase C boundary at all -- correctly: no Spring/Test event to hang a C band from, so only A/B/D/(E) appear.
    """
    sc, ar, st, c_bar = r.get("sc"), r.get("ar"), r.get("st"), _wy_bar(r.get("spring"))
    if c_bar is None:
        c_bar = _wy_bar(r.get("test"))
    # `sos_bar` (the breakout candle itself) STARTS Phase D, but the SOS is not KNOWABLE at that bar:
    # wyckoff_rules.py requires `C[q+m] > ceiling for m in 1..COMMIT-1` after it (~L300, ~L370), so the SOS is
    # confirmed only at `sos = sos_bar + COMMIT - 1`. Every boundary below therefore carries its own CONFIRMING
    # bar (`conf`), which for the SOS boundary is `sos`, never `sos_bar` (I3, code-review fix round 1).
    sos_bar, sos = r.get("sos_bar"), r.get("sos")
    d_start = sos_bar if sos_bar is not None else sos
    d_conf = sos if sos is not None else d_start
    bu_bar = _wy_bar(r.get("bu"))

    # (letter, start_bar, end_bar_or_None, start_conf_bar, end_conf_bar_or_None)
    bounds = []
    if sc is not None and st is not None:
        bounds.append(("A", sc, st, sc, st))
    if st is not None:
        if c_bar is not None:
            bounds.append(("B", st, c_bar, st, c_bar))
        else:
            bounds.append(("B", st, d_start, st, d_conf))
    if c_bar is not None:
        bounds.append(("C", c_bar, d_start, c_bar, d_conf))
    if d_start is not None:
        bounds.append(("D", d_start, bu_bar, d_conf, bu_bar))
    if bu_bar is not None:
        bounds.append(("E", bu_bar, None, bu_bar, None))
    return bounds


def _wy_phases(r, candles, tf, tr_available_at):
    """Phase structure objects (A1b) for one trading_range record -- see `_wy_phase_bounds` for the boundary
    rule. `available_at` is the bar that actually CONFIRMS the phase exists: the later of its start's and (when
    closed by a later event) its end's CONFIRMING bar -- for the SOS boundary that is `sos`, not `sos_bar` (I3)
    -- and never earlier than the parent trading range's own `available_at` (a phase of a range that is not yet
    knowable cannot be knowable; CLAUDE.md §8). `to` stays the end event's own bar (where the phase is DRAWN to);
    a phase can never be SHOWN as ending later than it is CONFIRMED because `available_at` >= that bar. Still-
    open phases are `status: "hypothesis"` (chart.js P6.2 convention; WA p166 warns against labelling a phase
    mechanically past what the record has actually shown)."""
    out = []
    for letter, start, end, s_conf, e_conf in _wy_phase_bounds(r):
        from_at = _formed(candles, start)
        conf_bar = max(s_conf, e_conf) if e_conf is not None else s_conf
        available_at = max(_avail(candles, conf_bar, tf), tr_available_at)
        if end is not None:
            to_at, status = _formed(candles, end), "tested"
        else:
            to_at, status = None, "hypothesis"
        out.append({"kind": "phase", "label": letter, "from": from_at, "to": to_at,
                     "formed_at": from_at, "available_at": available_at, "status": status})
    return out


def wyckoff_structures(O, H, L, C, V, candles, tf, P=None, volume_kind="traded", side="long"):
    """The Wyckoff trading ranges and events `candles` implies, wrapped from `wyckoff_records()`.

    `candles` is the same OHLCV list O/H/L/C/V were built from (bar `i`'s time is `candles[i]["time"]`).

    Returns {"records": recs, "structures": [...]} where `recs` is EXACTLY what `wyckoff_records()` returned
    (same objects, not copied) -- a caller that only wants the raw records (every existing reader of
    `detect_accumulations()`/`detect_distributions()`) can keep using `env["records"]` unchanged, or call
    `wyckoff_records()` directly and skip building this envelope (and the `candles` list) entirely. Each
    trading_range structure also carries `phases` (A1b, see `_wy_phases`)."""
    recs = wyckoff_records(O, H, L, C, V, P=P, volume_kind=volume_kind, side=side)
    structs = []
    for r in recs:
        events = []
        for key in _WY_EVENT_BARS:
            i = r.get(key)
            if i is None:
                continue
            formed_at, available_at = _ts(candles, i, tf)
            if key == "sos_bar" and r.get("sos") is not None:
                # I3: the breakout candle is only KNOWABLE as an SOS at `sos = sos_bar + COMMIT - 1` (the follow-
                # through closes wyckoff_rules.py requires); formed_at stays the breakout candle's own time.
                available_at = _avail(candles, r["sos"], tf)
            events.append({"kind": key, "i": i, "formed_at": formed_at, "available_at": available_at})
        bu = r.get("bu")
        if bu and bu.get("bar") is not None:
            formed_at, available_at = _ts(candles, bu["bar"], tf)
            events.append({"kind": "bu", "i": bu["bar"], "low": bu["low"], "formed_at": formed_at, "available_at": available_at})
        # The range is drawable only once the CHoCH confirms it (WA p68: three CHoBEV = CHoCH; wyckoff_rules.py
        # R1 docstring: "only then may a TR be drawn") -- available_at is the CHoCH bar's, not the SC bar's,
        # even though the lower border (formed_at) was set earlier at SC.
        tr_formed_at, _ = _ts(candles, r["sc"], tf)
        _, tr_available_at = _ts(candles, r["choch"], tf)
        phases = _wy_phases(r, candles, tf, tr_available_at)
        structs.append(dict(r, kind="trading_range", events=events, phases=phases,
                             formed_at=tr_formed_at, available_at=tr_available_at))
    return {"records": recs, "structures": structs}
