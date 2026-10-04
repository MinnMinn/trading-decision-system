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
                     (ICT); trading_range, sc, ar, st, choch, spring, test, lps_c, sos_bar, bu (Wyckoff events)
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
    mss -- the body close is a single-bar test, but the state that makes it an MSS rests on pivots (the reference
        swing, the leg anchor, the pivot that set the bias) that are confirmed only PIV bars later, and `disp` may
        rest on an FVG that needs its third candle; ict-scan.py records them (`dep_pivots`, `disp_conf_i`) and
        available_at is the latest of the MSS bar, each dep pivot + PIV and disp_conf_i (ICT chart-fidelity audit
        2026-10-04, item 2; before that fix it was the MSS bar alone -- too early).
`sweep`/`closed_through` are single-bar wick/body-close tests against an already-available level; they need no
look-ahead beyond their own bar, so their available_at is their own bar's, unchanged.

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
    already-known level, the same "no look-ahead beyond its own bar" case `sweep`/`closed_through`
    already are, module docstring above). A2 (chart.js) draws an invalidated pool/FVG ending at this bar, not
    edge to edge.
    CORRECTED 2026-10-04 (ICT chart-fidelity audit, items 3-4): the first touch is NOT the end of an FVG --
    touching the near edge is the IOFED entry (knowledge/ict/core-a.md §2.23, R19). An FVG's `invalidated_at`
    is now its `inversion_at` (body close through the CE, then through the far edge: §2.26, R23), with
    `touched_at`/`ce_fail_at` as state markers. A SWEPT pool (a level that held) is no longer open forever: its
    `invalidated_at`/`broken_at` is the first later body close beyond the level (R6, R25; mentorship-2024.md §15
    "remain valid after being run" until then). Both come from ict-scan.py display_lifecycle(), cold path only.
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

Chart fidelity (2026-10-04, docs/audits/2026-10-04-wyckoff-chart-fidelity.md) SUPERSEDES the Wyckoff timing and
phase rules of the A1b paragraph above: every Wyckoff object's `available_at` is now the bar at which a PREFIX
re-run of the detector first emits it in its shipped state (`_wy_availability`) -- the hand-written "CHoCH bar /
SOS conf bar" stamps were each too early (the record only exists once its Spring/LPS[C] fires; the SOS search
needs one bar past `sos`; a Spring's type needs its reclaim). Phase bounds, Phase E, expiry, status reasons and the
invalidation are in `_wy_view`; the extra reads they need (LPS[C] bar, SOS-leg high, Phase E start, invalidation)
come from wyckoff_rules.record_extras(), so detection still lives in wyckoff_rules.py (ADR 0009).

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
    # Display-only lifecycle (ICT chart-fidelity audit 2026-10-04, items 3-4): ict-scan.py's own forward scans past
    # the first sweep / first touch, computed here on the cold path only -- never by ict_analysis() (hot path).
    life = ict_scan.display_lifecycle(window, a)

    def _state_at(i, floor):
        """available_time of state bar `i`, clamped to >= the object's own available_at (S5); None if no bar."""
        return None if i is None else max(_avail(window, i, tf), floor)

    for i in a.get("pivots_high", []):
        # Confirmation delay: a PIV-bar pivot is not confirmable until bar i+PIV closes (module docstring).
        structs.append({"kind": "pivot_high", "i": i, "price": window[i]["high"],
                         "formed_at": _formed(window, i), "available_at": _avail(window, min(i + PIV, n - 1), tf)})
    for i in a.get("pivots_low", []):
        structs.append({"kind": "pivot_low", "i": i, "price": window[i]["low"],
                         "formed_at": _formed(window, i), "available_at": _avail(window, min(i + PIV, n - 1), tf)})

    for k, p in enumerate(a["pools"]):
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
        # A SWEPT pool stays a level (mentorship-2024.md §15) until a later BODY close beyond it (core-a.md R6,
        # R25): `broken_at` is that bar's availability (ict-scan.py display_lifecycle()), and it is the swept
        # pool's `invalidated_at` -- the chart ends the line there instead of drawing it to the right edge.
        broken_i = (life["pools"].get(k) or {}).get("broken_i")
        broken_at = _state_at(broken_i, pool_available_at)
        if pool_invalidated_at is None and broken_at is not None:
            pool_invalidated_at = broken_at
        structs.append({"kind": "pool", "pool_kind": p["kind"], "level": p["level"], "from": p["from"], "to": to,
                         "type": p["type"], "formed_at": _formed(window, p["from"]),
                         "available_at": pool_available_at,
                         "invalidated_at": pool_invalidated_at,
                         "broken_i": broken_i, "broken_at": broken_at})
        if p["swept"] >= 0:
            sf, sa = _ts(window, p["swept"], tf)
            structs.append({"kind": "sweep", "pool_kind": p["kind"], "level": p["level"], "i": p["swept"],
                             "formed_at": sf, "available_at": sa})
        elif p["state"] == "closed_through" and p.get("closed_at") is not None:
            cf, ca = _ts(window, p["closed_at"], tf)
            structs.append({"kind": "closed_through", "pool_kind": p["kind"], "level": p["level"], "i": p["closed_at"],
                             "formed_at": cf, "available_at": ca})

    for m in a.get("mss_all", a["mss"]):
        # Confirmation delay (ICT chart-fidelity audit 2026-10-04, item 2): the body close is judged on bar m["i"],
        # but the STATE that makes it an MSS (ict-scan.py's state machine: the reference swing `lastH`/`lastL`
        # and the pivot that set `bias`) rests on pivots that are only confirmed PIV bars after their own bar
        # (`dep_pivots`), and `disp` may rest on an FVG that needs its third candle (`disp_conf_i`). available_at
        # is therefore the LATEST of those bars -- never the MSS bar alone. A record from an analysis that
        # predates the dependency fields falls back to its own bar (unchanged behaviour).
        conf = max([m["i"], m.get("disp_conf_i", m["i"])] + [q + PIV for q in m.get("dep_pivots", ())])
        structs.append(dict(m, kind="mss", formed_at=_formed(window, m["i"]),
                             available_at=_avail(window, min(conf, n - 1), tf), confirm_i=conf))

    for k, f in enumerate(a["fvgs_all"]):
        # Confirmation delay: the gap at i needs bar i+1's high/low (H[i-1] vs L[i+1], or L[i-1] vs H[i+1]).
        # Lifecycle (ICT chart-fidelity audit 2026-10-04, item 4; ict-scan.py display_lifecycle()), each state
        # timestamped at the availability of the bar that confirms it (single-bar wick/close tests against an
        # already-known range, so no further delay), clamped to >= available_at (S5):
        #   touched_at   -- first wick back into the gap (`f["end"]` when `f["mitigated"]`). A STATE, not the end:
        #                   touching the near edge is the IOFED entry (core-a.md §2.23, R19).
        #   ce_fail_at   -- first body close through the 0.5 CE: "treat the FVG as failing" (§2.26, R23).
        #   inversion_at -- the next body close through the far edge: the failure is complete and the gap inverts
        #                   (R23; §2.25/§2.27). This is the FVG's `invalidated_at` -- the box ends here.
        # `mitigated`/`end` are still copied verbatim from analyze() (the decision path's own fields).
        lf = life["fvgs"].get(k) or {}
        fvg_available_at = _avail(window, min(f["i"] + 1, n - 1), tf)
        inversion_at = _state_at(lf.get("inversion_i"), fvg_available_at)
        structs.append(dict(f, kind="fvg", formed_at=_formed(window, f["i"]),
                             available_at=fvg_available_at,
                             touch_i=lf.get("touch_i"), touched_at=_state_at(lf.get("touch_i"), fvg_available_at),
                             ce_fail_i=lf.get("ce_fail_i"), ce_fail_at=_state_at(lf.get("ce_fail_i"), fvg_available_at),
                             inversion_i=lf.get("inversion_i"), inversion_at=inversion_at,
                             invalidated_at=inversion_at))

    dr_formed_at, dr_available_at = _ts(window, n - 1, tf)

    def _edge_i(level, pool_kind):
        """The bar from which this dealing-range edge existed: the availability bar (to + PIV) of the resting
        pool analyze() chose for it (same filter as analyze()'s own `above`/`below`), else -- the window-extreme
        fallback (dr_source mixed/window) -- the extreme's own bar. Regrouping engine output, not detection."""
        for p in a["pools"]:
            if (p["kind"] == pool_kind and p["level"] == level and p["swept"] < 0
                    and p.get("state") != "closed_through"):
                return min(p.get("to", p["from"]) + PIV, n - 1)
        ext = [r["high"] for r in window] if pool_kind == "BSL" else [r["low"] for r in window]
        return ext.index(level) if level in ext else 0

    # ICT chart-fidelity audit 2026-10-04, items 5-6: the range is judged on the last bar (available_at above), but
    # BOTH of its edges existed only from `from_i` on -- the later edge's availability bar. The chart starts the
    # premium/discount shading, EQ and the range-% pane there; before it the range did not exist (CLAUDE.md §8).
    dr_from_i = max(_edge_i(a["hi"], "BSL"), _edge_i(a["lo"], "SSL")) if n else 0
    dealing_range = {"kind": "dealing_range", "lo": a["lo"], "hi": a["hi"], "eq": a["eq"], "pct": a["pct"],
                      "source": a["dr_source"], "formed_at": dr_formed_at, "available_at": dr_available_at,
                      "from_i": dr_from_i, "edges_available_at": _avail(window, dr_from_i, tf) if n else None}

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


# The chart's detection parameters (VISUALIZATION_ONLY): W.PARAMS plus the W8 fidelity correction (CHoCH inside the
# SC->AR box, WA p68-69; wyckoff_rules.py module docstring). The decision path never reads this dict -- it calls
# wyckoff_records() with backtest-methods.py's own bridged copy, where fx_w8 stays False (v1) until the owner flips
# it. The page builders (build-artifact.py wy_json_engine, build-pit-page.py through it) pass it explicitly, so the
# chart does not draw a trend leg as Phase B (docs/audits/2026-10-04-wyckoff-chart-fidelity.md finding 1).
ENVELOPE_PARAMS = dict(W.PARAMS, fx_w8_choch_in_box=True)

# Drawable Wyckoff events (built in `_wy_view`): sc, ar, st, choch, spring, test, lps_c, sos_bar, bu. "reclaim"
# (R6's close-back-inside bar) is a typing input, not a Wyckoff event name, and "sos" (the SOS confirmation bar)
# duplicated the "sos_bar" flag -- both stay on the raw record, neither is shipped as an event (chart fidelity
# findings 15/16); sos_bar carries `conf_bar` = sos instead. LPS[C] (lps_c) is the Phase C event of the no-Spring
# path (WA p81-83, finding 9).


def wyckoff_records(O, H, L, C, V, P=None, volume_kind="traded", side="long", pivots=None, pre=None):
    """The RAW scripts/wyckoff_rules.py `detect_accumulations()` (side="long") / `detect_distributions()`
    (side="short") call -- for hot-path callers (scripts/backtest-methods.py `_wyckoff_candidates()`) that need
    only the records, never the enriched trading_range objects and never a per-window `candles` list built
    solely to timestamp them. This IS that call: zero extra allocation over calling `W.detect_accumulations()`/
    `W.detect_distributions()` directly (see the module docstring, "Hot-path / cold-path split")."""
    kwargs = {} if P is None else {"P": P}
    if pivots is not None:      # speed: the window's pivots, pre-computed once per series (wyckoff_rules.swings)
        kwargs["pivots"] = pivots
    if pre is not None:         # speed: the prefix's swings + candidate swing indices (wyckoff_rules.prefix_swings)
        kwargs["pre"] = pre
    return (W.detect_accumulations(O, H, L, C, V, volume_kind=volume_kind, **kwargs) if side == "long"
            else W.detect_distributions(O, H, L, C, V, volume_kind=volume_kind, **kwargs))


def _wy_bar(v):
    """A record field that is sometimes a plain bar index, sometimes a {"bar":...} dict (`bu`) -- one accessor."""
    if v is None:
        return None
    return v.get("bar") if isinstance(v, dict) else v


def _wy_view(r, O, H, L, C, P, side):
    """Everything the envelope ships for ONE record, in BAR indices, computed only from `O/H/L/C` (which may be any
    prefix containing the record): events, phases, the trading range's end and the invalidation. Pure -- the
    point-in-time scan in `_wy_availability()` re-runs it on every prefix and compares states, so nothing here may
    read past len(C) - 1.

    Phase boundaries (book basis WA p68-96, the record's own event vocabulary): A = SC..ST (stopping action);
    B = ST..Phase-C event (building the cause); C = Spring/Shakeout/UT (spring path) or LPS[C] (no-Spring path,
    WA p81-83 -- finding 9; it used to draw A->B->D with no C) .. SOS bar; D = SOS bar .. Phase E start; E starts at
    the first close above the SOS leg's high AFTER the BU (WA p85; wyckoff_rules.record_extras) -- not at the BU
    bar, which is a Phase-D event (finding 10).

    Expiry (finding 10; PROJECT RULE, the book prints no duration): an open last phase is stale once the engine's
    own search window for its closing event has passed with no event -- C: anchor (Test, else reclaim, else the end
    of the Shakeout window) + phase_d_window + COMMIT - 1 (the last bar an SOS could still be confirmed); D:
    SOS + phase_d_window without a BU, BU + phase_d_window without a Phase E start; E: start + phase_d_window. An
    expired phase ends at that bar with reason "expired" and the trading range ends with it.

    Status (finding 7; method.md §2 A4, WA p150-159 đối nhãn, WA p166-167 sloped): "tested" only when the phase is
    closed by its next event AND the record's đối nhãn reads do not contradict (st_sign, phase_b_sign) AND the
    structure is not sloped AND the phase's opening event is confirmed. Otherwise "hypothesis" with `reasons`
    (sloped / st_lower_third / b_tests_lower / unconfirmed / expired / invalidated / open). An open last phase that
    the engine invalidates before it expires ends at the invalidation bar (reason "invalidated")."""
    n = len(C)
    x = W.record_extras(r, O, H, L, C, P=P, side=side)
    win = P["phase_d_window"]
    conf = x["confirm"]
    events = []

    def ev(kind, i, **state):
        if i is not None:
            events.append(dict(kind=kind, i=i, **state))

    for key in ("sc", "ar", "st", "choch"):
        ev(key, r.get(key))
    if r.get("path") == "spring":
        ev("spring", r.get("spring"), shakeout=bool(r.get("shakeout")), vol_type=r.get("vol_type"))
        ev("test", r.get("test"), confirmed=conf.get("test") is True)
        c_bar = r.get("spring")
    else:
        ev("lps_c", x["lps_c"], confirmed=conf.get("lps_c") is True)
        c_bar = x["lps_c"]
    # The SOS breakout candle is only an SOS once its follow-through closes print (I3): conf_bar carries that bar.
    ev("sos_bar", r.get("sos_bar"), conf_bar=r.get("sos"))
    bu_bar = _wy_bar(r.get("bu"))
    ev("bu", bu_bar, confirmed=conf.get("bu") is True)

    sc, st, d_start, e_start = r.get("sc"), r.get("st"), r.get("sos_bar"), x["e_start"]
    bounds = [("A", sc, st)]
    if c_bar is not None:
        bounds += [("B", st, c_bar), ("C", c_bar, d_start)]
    else:
        bounds += [("B", st, d_start)]
    if d_start is not None:
        bounds.append(("D", d_start, e_start))
    if e_start is not None:
        bounds.append(("E", e_start, None))

    expired = None
    last = bounds[-1]
    if last[2] is None:
        if last[0] == "C":
            anchor = r.get("test") if r.get("test") is not None else r.get("reclaim")
            if anchor is None:
                anchor = r["spring"] + P["spring_max_bars_outside"]
            exp = anchor + win + W.COMMIT - 1
        elif last[0] == "D":
            exp = (bu_bar if bu_bar is not None else r["sos"]) + win
        elif last[0] == "E":
            exp = e_start + win
        else:
            exp = None
        if exp is not None and exp <= n - 1:
            expired = exp
            bounds[-1] = (last[0], last[1], exp)
    # An invalidated read stops where it was invalidated (ADR 0004): the phase running at the invalidation bar ends
    # there (reason "invalidated", instead of running on to its next event or the stale-read expiry), and no phase
    # or event AFTER it belongs to this read any more -- the plan was abandoned (WMT p243-249) / the Spring failed
    # (WMT p271), so a later "Test"/"SOS" the detector still finds is not drawn as part of it.
    invalidated_end = None
    ib = x["inval_bar"]
    if ib is not None:
        kept = []
        for letter, start, end in bounds:
            if kept and start >= ib:
                break
            if end is None or end > ib:
                kept.append((letter, start, ib))
                invalidated_end, expired = ib, None
                break
            kept.append((letter, start, end))
        if kept[-1][0] != last[0]:
            expired = None      # the phase that expired is not part of the read any more
        bounds = kept
        events = [e for e in events if e["i"] < ib]   # a phase's `to` is exclusive: the breaking bar is not in it

    contra = []
    if r.get("sloped"):
        contra.append("sloped")
    if r.get("st_sign") == "contradicts":
        contra.append("st_lower_third")
    if r.get("phase_b_sign") == "contradicts":
        contra.append("b_tests_lower")
    phases = []
    for idx, (letter, start, end) in enumerate(bounds):
        reasons = list(contra)
        if letter == "C" and r.get("path") == "lps_c" and conf.get("lps_c") is not True:
            reasons.append("unconfirmed")
        is_last = idx == len(bounds) - 1
        if is_last and expired is not None:
            reasons.append("expired")
        elif is_last and invalidated_end is not None:
            reasons.append("invalidated")
        elif end is None:
            reasons.append("open")
        open_reasons = [q for q in reasons if q not in ("expired", "invalidated", "open")] + ["open"]
        phases.append(dict(label=letter, start=start, end=end, status="hypothesis" if reasons else "tested",
                           reasons=reasons, open_reasons=open_reasons))

    inval = (x["inval_bar"], x["inval_reason"]) if x["inval_bar"] is not None else None
    ends = []
    if e_start is not None:
        ends.append((e_start, "phase_e"))
    if inval is not None:
        ends.append((inval[0], "invalidated"))
    if expired is not None:
        ends.append((expired, "expired"))
    tr_end = min(ends) if ends else None
    return dict(events=events, phases=phases, tr=(r["tr_lo"], r["tr_hi"]), tr_end=tr_end, inval=inval)


def _wy_state(d, drop=()):
    return tuple(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in d.items() if k not in drop))


def _wy_objects(view):
    """{object id: state} -- the unit of point-in-time comparison. A phase is two objects: its identity (label,
    start) and its full state (end, status, reasons), so replay can show a phase as open before its end is known."""
    objs = {("tr",): view["tr"]}
    if view["tr_end"] is not None:
        objs[("tr_end",)] = view["tr_end"]
    if view["inval"] is not None:
        objs[("inval",)] = view["inval"]
    for e in view["events"]:
        objs[("ev", e["kind"], e["i"])] = _wy_state(e)
    for p in view["phases"]:
        objs[("ph", p["label"])] = (p["start"],)
        objs[("ph_full", p["label"])] = _wy_state(p, drop=("open_reasons",))
    return objs


def _wy_key(r):
    return (r["sc"], r["ar"], r["st"], r["choch"])


def _wy_availability(recs, views, O, H, L, C, V, P, volume_kind, side):
    """Point-in-time availability (findings 3/4; CLAUDE.md §8 availableTime <= decisionTime). For every object a
    record ships, the earliest bar `k` such that re-running the SAME detector on candles[:k+1] -- and on every longer
    prefix -- emits that object in the SAME state. Bar-exact by construction, so it covers every confirmation delay
    the detector has, including the ones no hand-written formula caught: a record exists only once its Spring/LPS[C]
    path fires (so its trading range and Phases A/B are NOT knowable at the CHoCH), a CHoCH pivot needs `pivot` more
    bars, a Spring is a Spring (not a Shakeout) only once the reclaim / typing window decides it, an SOS only after
    its follow-through closes, a '?' label only drops after its confirming close.

    Scans prefixes downward from the full window and stops per record as soon as every one of its objects has
    changed state (or the record itself disappears) -- cost is (n - earliest emission) detector calls per side."""
    n = len(C)
    PP = W.PARAMS if P is None else P
    avail = []
    pending = {}
    for idx, (r, view) in enumerate(zip(recs, views)):
        objs = _wy_objects(view)
        avail.append({oid: n - 1 for oid in objs})
        pending[_wy_key(r)] = (idx, objs, set(objs))
    k = n - 2
    while pending and k >= 0:
        m = k + 1
        Ok, Hk, Lk, Ck = O[:m], H[:m], L[:m], C[:m]
        recs_k = {_wy_key(rr): rr for rr in wyckoff_records(Ok, Hk, Lk, Ck, V[:m], P=P, volume_kind=volume_kind, side=side)}
        for key in list(pending):
            idx, objs, live = pending[key]
            rk = recs_k.get(key)
            if rk is not None:
                objs_k = _wy_objects(_wy_view(rk, Ok, Hk, Lk, Ck, PP, side))
                for oid in list(live):
                    if objs_k.get(oid) == objs[oid]:
                        avail[idx][oid] = k
                    else:
                        live.discard(oid)
            else:
                live.clear()
            if not live:
                del pending[key]
        k -= 1
    return avail


def wyckoff_structures(O, H, L, C, V, candles, tf, P=None, volume_kind="traded", side="long", pit=True):
    """The Wyckoff trading ranges and events `candles` implies, wrapped from `wyckoff_records()`.

    `candles` is the same OHLCV list O/H/L/C/V were built from (bar `i`'s time is `candles[i]["time"]`).
    `P`: detection parameters (None = wyckoff_rules.PARAMS, the decision path's v1 defaults); the chart passes
    ENVELOPE_PARAMS.

    Returns {"records": recs, "structures": [...]} where `recs` is EXACTLY what `wyckoff_records()` returned
    (same objects, not copied). Each trading_range structure carries `events`, `phases`, its end (`to`,
    `to_available_at`, `end_reason`) and `invalidated` (`_wy_view`). Every object's `available_at` is the
    point-in-time availability from `_wy_availability()`; a phase also carries `state_available_at` (when its end /
    status became known -- before that, replay shows it open, with `open_reasons`). `pit=False` skips that scan and
    stamps no availability (the prefix re-detection test uses it to read what a prefix run emits, cheaply)."""
    PP = W.PARAMS if P is None else P
    recs = wyckoff_records(O, H, L, C, V, P=P, volume_kind=volume_kind, side=side)
    views = [_wy_view(r, O, H, L, C, PP, side) for r in recs]
    avail = (_wy_availability(recs, views, O, H, L, C, V, P, volume_kind, side) if pit
             else [None] * len(recs))
    structs = []
    for r, view, av in zip(recs, views, avail):
        def at(oid, av=av):
            return _avail(candles, av[oid], tf) if av is not None else None
        events = []
        for e in view["events"]:
            d = dict(e, formed_at=_formed(candles, e["i"]), available_at=at(("ev", e["kind"], e["i"])))
            if e["kind"] == "bu":
                d["low"] = r["bu"]["low"]
            events.append(d)
        phases = []
        for p in view["phases"]:
            from_at = _formed(candles, p["start"])
            phases.append({"kind": "phase", "label": p["label"], "from": from_at,
                           "to": _formed(candles, p["end"]) if p["end"] is not None else None,
                           "formed_at": from_at, "available_at": at(("ph", p["label"])),
                           "state_available_at": at(("ph_full", p["label"])),
                           "status": p["status"], "reasons": p["reasons"], "open_reasons": p["open_reasons"]})
        end = view["tr_end"]
        inval = view["inval"]
        invalidated = (None if inval is None else
                       {"i": inval[0], "reason": inval[1], "formed_at": _formed(candles, inval[0]),
                        "available_at": at(("inval",))})
        structs.append(dict(r, kind="trading_range", events=events, phases=phases,
                            formed_at=_formed(candles, r["sc"]), available_at=at(("tr",)),
                            to=_formed(candles, end[0]) if end else None,
                            to_available_at=at(("tr_end",)) if end else None,
                            end_reason=end[1] if end else None,
                            invalidated=invalidated,
                            invalidated_at=invalidated["available_at"] if invalidated else None))
    return {"records": recs, "structures": structs}
