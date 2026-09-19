"""THE Evidence record type (CLAUDE.md §12): an observation that carries where it came from and when.

    import evidence as E
    ev = E.observation("market_structure", "ict", "MSS up, body closed past 76,863",
                       series=("BTCUSDT", "15m"), event_time="2026-09-17T18:00:00Z")
    ev["available_time"]   -> when it became knowable (from the bar, via §7/§8)
    ev["quality"]          -> inherited from the source series, never asserted
    E.admissible([ev], decision_time=now)   -> the §8 gate, over evidence

Why a record type at all. The scanner already computes every value §12 calls evidence -- `last_mss`,
`nearest_fvg`, `unswept_pools`, `events_recent`, `eq`, `stance` in `data/live/prelim/<style>.facts.json`.
They are flat fields on a symbol: a number or a string, with no source, no event time, no availability, no
quality and no methodology scope of their own. The file header says when the scan RAN; an individual
observation cannot say what it was derived from or whether it was knowable at a given decision time.

The practical consequence, and the reason this is not bookkeeping: **nothing in this system can answer "what
evidence did this decision use?"** A trade file records a `confluence_score` and a `setup_type`; the facts
file is overwritten on the next scan. So a post-trade review (§41) cannot reconstruct the inputs, and the §8
gate has nothing per-observation to gate.

**Evidence is not a signal, and that is enforced.** §12 says so twice over, and the failure it guards against
is the easy one: an "evidence" record that also carries `direction: long` has quietly become a decision, and
every consumer downstream will treat it as one. `observation()` REFUSES a direction, verdict, side or score
field. Interpretation is a separate level of the ladder below.

**The six-level ladder** §12 requires the system to distinguish is real here already -- by FILE LAYOUT, which
SYSTEM-DESIGN.md §13 rule 1 enforces ("numbers from code, words from the model"). `LADDER` names each level
and the artifact that holds it, so the distinction is inspectable rather than a convention someone has to
know. This module adds the missing rung: evidence as a record rather than a display row.
"""
import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import normalized as N
import pit

# §12's own example list, snake_cased. Not a closed set of everything evidence could be -- the spec says
# "Examples" -- but a declared vocabulary, so a new kind is named once here rather than spelled three ways at
# three call sites. scripts/tests/test_evidence.py checks it against the spec's bullets.
EVIDENCE_KINDS = (
    "market_structure",
    "liquidity",
    "order_flow",
    "volume",
    "imbalance",
    "footprint",
    "heatmap",
    "volatility",
    "session_context",
    "news_event_state",
)

# The fields §12 requires every evidence record to preserve.
REQUIRED_FIELDS = ("source", "event_time", "available_time", "quality", "methodology_scope", "provenance")

# Fields that would turn an observation into a decision. Refused by observation().
FORBIDDEN_FIELDS = ("direction", "side", "verdict", "signal", "score", "confluence", "stance", "recommendation")

# CLAUDE.md §12's six levels, each with the artifact that holds it in THIS system. The distinction is the
# requirement; naming the holder is what makes it checkable rather than asserted.
LADDER = (
    ("raw_data", "data/live/<feed>/ohlcv.<SYM>.<TF>.json -- the normalized series as written by a provider's "
                 "connector; read through scripts/normalized.py"),
    ("derived_analytics", "data/live/prelim/<style>.facts.json -- computed by scripts/ict-scan.py, "
                          "scripts/wyckoff_rules.py, scripts/htf_context.py. Numbers only, no judgement "
                          "(SYSTEM-DESIGN.md §13 rule 1)"),
    ("evidence", "this module: an observation plus source, times, quality, methodology scope and provenance"),
    ("interpretation", "<style>.<SYM>.model.html -- a model's per-method reading, vocabulary-gated by "
                       "scripts/method_purity.py so one methodology cannot borrow another's terms"),
    ("setup", "docs/architecture/pilot-top5.json rule families; live detection in scripts/live_rules.py"),
    ("decision", "the /analyze verdict and the pilot's order path (scripts/strategy-runner.py tick)"),
)


def ladder_level(name):
    for level, holder in LADDER:
        if level == name:
            return holder
    raise KeyError(name)


def observation(kind, methodology, statement, *, series=None, event_time=None, available_time=None,
                derived_from=None, quality=None, cite=None, **extra):
    """One evidence record.

    `series` is a (symbol, timeframe) pair when the observation came off a price series; passing it makes
    `available_time`, `quality` and `provenance` derive from §7's normalized layer instead of being asserted
    here. `available_time` is otherwise required -- an observation with no knowable-at time cannot be gated
    by §8, and defaulting it to "now" would make every record trivially admissible, which is worse than
    refusing.
    """
    if kind not in EVIDENCE_KINDS:
        raise ValueError(f"unknown evidence kind {kind!r}; CLAUDE.md §12 lists {list(EVIDENCE_KINDS)}")
    bad = sorted(set(extra) & set(FORBIDDEN_FIELDS))
    if bad:
        raise ValueError(
            f"evidence may not carry {bad}: CLAUDE.md §12 -- 'Evidence is not automatically a signal'. A "
            f"record that states a direction or a score has become an interpretation or a decision, and every "
            f"consumer downstream will read it as one. Put it at the right rung of the ladder instead "
            f"({ladder_level('interpretation')}).")

    provenance, derived_quality = None, quality
    if series is not None:
        symbol, timeframe = series
        loaded = N.load(symbol, timeframe)
        provenance = loaded["provenance"]
        derived_quality = quality or provenance["quality"]
        if available_time is None and event_time is not None:
            available_time = N.available_time({"time": event_time}, timeframe)
    if available_time is None:
        raise ValueError(
            f"evidence {kind!r} has no available_time and no series to derive one from. An observation that "
            f"cannot say when it became knowable cannot be gated by CLAUDE.md §8, and defaulting to now would "
            f"make every record trivially admissible.")

    rec = {
        "kind": kind,
        "methodology_scope": methodology,
        "statement": statement,
        "source": (provenance or {}).get("source_identifier") if provenance else (derived_from or "unstated"),
        "event_time": pit._aware(event_time).isoformat().replace("+00:00", "Z") if event_time else None,
        "available_time": pit._aware(available_time).isoformat().replace("+00:00", "Z"),
        "quality": derived_quality or "UNKNOWN",
        "provenance": provenance,
        "derived_from": derived_from,
        "cite": cite,
        "ladder_level": "evidence",
    }
    rec.update(extra)
    missing = [f for f in REQUIRED_FIELDS if f not in rec]
    if missing:
        raise ValueError(f"evidence record is missing required field(s) {missing} (CLAUDE.md §12)")
    return rec


def as_pit_inputs(records):
    """Evidence as §8 gate inputs, so one gate covers candles and evidence alike."""
    kind_for = {"news_event_state": "news", "footprint": "footprint", "heatmap": "heatmap",
                "order_flow": "trades", "volume": "candles", "imbalance": "footprint"}
    return [pit.input_(kind_for.get(r["kind"], "derived_analytics"),
                       f"{r['methodology_scope']}:{r['kind']}:{r['statement'][:40]}",
                       available_time=r["available_time"], event_time=r["event_time"],
                       source=r["source"])
            for r in records]


def admissible(records, decision_time):
    """Which evidence a decision at `decision_time` may use, and why the rest is refused (§8 over §12)."""
    return pit.admit(as_pit_inputs(records), decision_time)


def from_facts(facts, symbol, timeframe, methodology="ict"):
    """Adapt the scanner's flat facts into evidence records, so the type is exercised on real output.

    This is a READER over `data/live/prelim/<style>.facts.json` as it exists, not a rewrite of it. The
    scanner's format feeds the published pages and the model-prose checker; changing it is a larger,
    separately-verified change and belongs with the §35/§36 decision-engine work. What this gives today is an
    honest answer to "what evidence underlies this read?", which nothing could produce before.

    Every record's `event_time` is the anchoring candle's OPEN, so `available_time` comes out one period
    later through §7's rule -- the scanner's own facts do not distinguish the two, and an evidence record must.
    """
    sym = (facts.get("symbols") or {}).get(symbol) or {}
    # Anchor on the last COMPLETED candle, not on `last_time`.
    #
    # `last_time` / `last` / `pct` in the facts file are the FORMING candle, reported separately on purpose --
    # ict-scan.py:232 states that verdicts use the last completed candle `c[-2]` and that the forming one may
    # never confirm a break. The first version of this adapter anchored on `last_time`, and the §8 gate then
    # correctly refused every record it produced: an observation anchored on a bar that has not closed is not
    # knowable yet. Anchoring on the completed candle matches the scanner's own verdict basis.
    forming = sym.get("last_time") or facts.get("window_last")
    anchor = None
    if forming:
        anchor = (pit._aware(forming) - datetime.timedelta(seconds=N.tf_seconds(timeframe))) \
            .isoformat().replace("+00:00", "Z")
    out = []

    def add(kind, statement, **kw):
        if statement:
            out.append(observation(kind, methodology, statement, series=(symbol, timeframe),
                                   event_time=anchor, derived_from=f"prelim facts scanned_at "
                                                                   f"{facts.get('scanned_at')}", **kw))

    # Field names read from a real facts file, not inferred: `last_mss` is
    # {type: bull|bear, level, disp, ext, ext_time, origin}, `nearest_fvg` is {type, lo, hi, ce, mitigated},
    # `unswept_pools` rows are {kind: BSL|SSL, level, from, swept}. The first version of this adapter guessed
    # `dir`/`price`/`side` and emitted "latest MSS ? past 76862.85" -- which is why it is worth saying that
    # the shapes here were checked against data/live/prelim/scalping.facts.json rather than assumed.
    mss = sym.get("last_mss") or {}
    if mss.get("level") is not None:
        add("market_structure",
            f"latest MSS {mss.get('type', 'unknown')} past {mss['level']}"
            + ("" if mss.get("disp") else " (no displacement on the breaking candle)"))
    pools = [p for p in (sym.get("unswept_pools") or []) if p.get("level") is not None]
    if pools:
        add("liquidity", f"{len(pools)} unswept pool(s): "
                         + ", ".join(f"{p.get('kind', '?')} {p['level']}" for p in pools[:6]))
    fvg = sym.get("nearest_fvg") or {}
    if fvg.get("lo") is not None:
        add("imbalance", f"nearest {'un' if not fvg.get('mitigated') else ''}mitigated FVG "
                         f"{fvg.get('type', 'unknown')} {fvg['lo']}-{fvg['hi']}")
    if sym.get("eq") is not None and sym.get("pct") is not None:
        # `pct` is a FRACTION in the facts file (0.2678), not a percentage. The first version printed
        # "0.2678%" for what is 26.8% of the window range.
        add("volatility", f"position in window range {sym['pct'] * 100:.1f}% (EQ {sym['eq']:.2f})")
    # The scanner emits FOUR event shapes (scripts/ict-scan.py): a level one (`sweep`, `erl_*`, `mss_*`), a
    # ZONE one (`fvg_*`, which carries lo/hi and no level at all), a MULTIPLE one (`volume`), and whatever a
    # later rule adds. The first version read `ev.get("level", "?")` for all of them and called every one
    # "swept", so an FVG came out as `recent: swept fvg_bull ?` -- a placeholder where a number belongs, and a
    # verb that is wrong twice over: an FVG is formed, not swept, and a volume spike is neither.
    #
    # It went unnoticed because the live scan simply had no FVG in its recent window for days. It appeared the
    # moment one did. An unknown shape is now SKIPPED rather than printed with a `?`: a record that says
    # nothing is honest, and one that says `?` is a fabricated observation §12 would carry into a decision.
    for ev in (sym.get("events_recent") or []):
        if not (isinstance(ev, dict) and ev.get("kind")):
            continue
        kind = ev["kind"]
        if kind.startswith("fvg_"):
            add("imbalance", f"recent: {kind} formed {ev['lo']}-{ev['hi']}"
                if ev.get("lo") is not None and ev.get("hi") is not None else None)
        elif kind == "volume":
            add("volume", f"recent: volume {ev['mult']}x average, candle {ev.get('dir', 'unknown')}"
                if ev.get("mult") is not None else None)
        elif ev.get("level") is not None:
            verb = "swept" if kind == "sweep" else "printed"
            what = f"{kind}" + (f" ({ev['pool']})" if kind == "sweep" and ev.get("pool") else "")
            add("liquidity", f"recent: {what} {verb} at {ev['level']}")
    return out


if __name__ == "__main__":
    import argparse
    import json
    ap = argparse.ArgumentParser(description="Evidence records from the scanner's facts (CLAUDE.md §12).")
    ap.add_argument("--style", default="scalping")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--tf", default="15m")
    a = ap.parse_args()
    path = os.path.join(ROOT, "data", "live", "prelim", f"{a.style}.facts.json")
    if not os.path.exists(path):
        print(f"no facts on disk: {os.path.relpath(path, ROOT)}", file=sys.stderr)
        sys.exit(2)
    with open(path, encoding="utf-8") as fh:
        facts = json.load(fh)
    recs = from_facts(facts, a.symbol, a.tf)
    print(f"{len(recs)} evidence record(s) for {a.symbol} {a.tf}\n")
    for r in recs:
        print(f"  [{r['kind']:17}] {r['statement'][:78]}")
        print(f"   {'':19} event {r['event_time']}  available {r['available_time']}  "
              f"quality {r['quality']}  source {r['source']}")
    gate = admissible(recs, datetime.datetime.now(datetime.timezone.utc))
    print(f"\nadmissible now: {len(gate['admitted'])} of {len(recs)}; refused {len(gate['refused'])}")
