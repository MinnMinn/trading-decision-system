"""CLAUDE.md §40 -- THE recorder and summariser for docs/architecture/latency-model.json.

§40 names ten timestamps the live path must record and four statistics it must report. Before this module the
repo had **four wall-clock stamps at one-second resolution and differenced none of them**, no p50/p95/p99/max
anywhere, and no `perf_counter` in the order path's entire import closure. The isolation half of §40 was
partly true by accident (the live path imports nothing that calls a model) and partly false: `pilot-loop.sh`
ran the journal's index rebuild and HTML render SYNCHRONOUSLY between the tick and the sleep.

    import latency as L

    with L.tick("live") as t:              # one tick = one trace
        with t.span("provider_receive"):
            candles = fetch(...)
        with t.span("normalization"):
            ...
        t.mark("market_event", bar_close_epoch)   # a transport-bound fact, not a code latency

    L.summary()          -> {"provider_receive": {"n": 412, "p50": 61.2, "p95": 180.4, ...}, ...}

Four decisions worth stating, because each closes a way a latency number lies:

1. **`perf_counter_ns`, not wall clock.** Wall clock is not monotonic (NTP steps, DST on a naive stamp) and
   the repo's existing stamps are one-second resolution, which cannot see a hot path at all.
2. **A span closes in `finally`.** `tick()` has five early returns. A span that only closes on the happy path
   would report the fast cases and silently drop the slow ones -- the exact inversion of what it is for.
3. **Transport-bound stamps are recorded but summarised SEPARATELY.** This repo polls REST and reads MT5
   files, so `market_event -> provider_receive` and `order_submission -> fill` are dominated by the poll
   interval and by how patient a limit order is. Mixing them into the hot-stage percentiles would make a slow
   tick indistinguishable from a resting order that waited an hour for its price.
4. **Sample size travels** (§39's rule, and the same reason): a p99 over 7 observations is not a p99.

Recording is append-only JSONL under `data/live/latency/`, and it is BEST EFFORT: a failure to record must
never fail a tick. §1's priority order puts execution safety above measurement, so every write is wrapped and
a broken recorder degrades to silence rather than to a refused trade.
"""
import contextlib
import json
import math
import os
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "docs", "architecture", "latency-model.json")
DIR = os.path.join(ROOT, "data", "live", "latency")

HOT, TRANSPORT = "hot", "transport_bound"


class RegistryError(ValueError):
    """The §40 registry itself is wrong -- raised at import."""


class NotDeclared(KeyError):
    """Something timed a stage CLAUDE.md §40 does not name."""


def _load(path=None):
    path = path or PATH
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    stamps = data.get("stamps")
    if not isinstance(stamps, list) or not stamps:
        raise RegistryError(f"{path}: `stamps` must be a non-empty list")
    seen = set()
    for s in stamps:
        for field in ("id", "spec_name", "kind", "captured"):
            if not str(s.get(field) or "").strip():
                raise RegistryError(f"{path}: stamp {s.get('id')!r} has no {field!r}")
        if s["id"] in seen:
            raise RegistryError(f"{path}: duplicate stamp id {s['id']!r}")
        seen.add(s["id"])
        if s["kind"] not in (HOT, TRANSPORT):
            raise RegistryError(f"{path}: stamp {s['id']!r} has kind {s['kind']!r}; §40's stages are either "
                                f"{HOT!r} (code we can make faster) or {TRANSPORT!r} (a poll interval or a "
                                f"market fact)")
        if s["kind"] == TRANSPORT and not str(s.get("_bound_why") or "").strip():
            raise RegistryError(
                f"{path}: stamp {s['id']!r} is declared transport-bound and does not say why. Calling a stage "
                f"unmeasurable is how a slow stage stops being measured, so the reason is mandatory.")
    if not isinstance(data.get("percentiles"), list) or not data["percentiles"]:
        raise RegistryError(f"{path}: `percentiles` must list the percentiles §40 asks for")
    return data, {s["id"]: s for s in stamps}, tuple(s["id"] for s in stamps)


_DATA, STAMPS, ORDER = _load()
PERCENTILES = tuple(_DATA["percentiles"])
HOT_STAGES = tuple(s for s in ORDER if STAMPS[s]["kind"] == HOT)
TRANSPORT_STAGES = tuple(s for s in ORDER if STAMPS[s]["kind"] == TRANSPORT)
REGRESSION_STAGES = tuple(_DATA.get("regression_stages") or ())
WORKLOADS = _DATA.get("workloads") or {}


def stamp(sid):
    s = STAMPS.get(sid)
    if s is None:
        raise NotDeclared(f"no §40 stage {sid!r}; the ten are {list(ORDER)}")
    return s


def spec_name(sid):
    return stamp(sid)["spec_name"]


def research_workloads():
    """The workloads §40 says must not block the live path, with how each is kept off it."""
    return tuple(w["id"] for w in WORKLOADS.get("research") or ())


class Trace:
    """One tick's latency record.

    `span(id)` is a context manager that times a declared stage and closes in `finally`. `mark(id, value)`
    records a transport-bound fact that was measured elsewhere (a bar close, a venue fill time).
    """

    def __init__(self, label=None, *, sink=None):
        self.label = label
        self.rows = {}
        self.marks = {}
        self._sink = sink
        self.started = time.time()

    @contextlib.contextmanager
    def span(self, sid):
        stamp(sid)                                   # refuse an undeclared stage loudly, at the call site
        t0 = time.perf_counter_ns()
        try:
            yield
        finally:
            # `finally`, not the happy path: tick() has five early returns and an exception is exactly the
            # case whose duration a reader wants.
            self.rows[sid] = self.rows.get(sid, 0.0) + (time.perf_counter_ns() - t0) / 1e6

    def record(self, sid, t0_ns):
        """Record a stage measured with explicit start/stop rather than a `with` block.

        Needed where a span cannot wrap the region without re-indenting a live order path: the per-signal
        decision walk has two exits (a blocked signal `continue`s, an eligible one falls through to
        execution) and both call this. Additive like `span()`, so a stage entered twice in one tick reports
        the total of the two, which is what a per-tick latency means.
        """
        stamp(sid)
        self.rows[sid] = self.rows.get(sid, 0.0) + (time.perf_counter_ns() - t0_ns) / 1e6
        return self

    def mark(self, sid, ms):
        if stamp(sid)["kind"] != TRANSPORT:
            raise NotDeclared(f"{sid!r} is a hot stage; time it with span() rather than asserting a number")
        self.marks[sid] = float(ms)
        return self

    def as_row(self):
        return {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.started)), "label": self.label,
                "hot_ms": {k: round(v, 3) for k, v in self.rows.items()},
                "transport_ms": {k: round(v, 3) for k, v in self.marks.items()},
                "total_hot_ms": round(sum(self.rows.values()), 3)}

    def write(self):
        """Append this trace. BEST EFFORT: §1 puts execution safety above measurement, so a recorder that
        cannot write degrades to silence and never to a refused trade."""
        row = self.as_row()
        try:
            os.makedirs(DIR, exist_ok=True)
            day = row["at"][:10]
            with open(os.path.join(DIR, f"{day}.jsonl"), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError:
            pass
        if self._sink is not None:
            self._sink.append(row)
        return row


@contextlib.contextmanager
def tick(label=None, *, sink=None):
    """One tick's trace, written on the way out whatever happened inside it."""
    tr = Trace(label, sink=sink)
    try:
        yield tr
    finally:
        tr.write()


def percentile(values, p):
    """Nearest-rank percentile. Deliberately not interpolated: with the sample sizes a poll loop produces,
    an interpolated p99 invents a value between two observations and reports it as one."""
    if not values:
        return None
    vs = sorted(values)
    # Nearest rank: ceil(p/100 * n), 1-based. `round()` here would be banker's rounding, which
    # silently returns the NEXT observation for every even half -- p95 over 100 samples came back
    # as the 96th.
    k = max(0, min(len(vs) - 1, math.ceil(p / 100.0 * len(vs)) - 1))
    return vs[k]


def summarize(rows):
    """p50/p95/p99/max per stage, with `n`, hot stages and transport-bound facts kept APART.

    Keeping them apart is the point: a resting limit order that waited an hour for its price is not a slow
    code path, and one table containing both cannot tell a reader which it is looking at.
    """
    hot, transport = {}, {}
    for sid in HOT_STAGES:
        vals = [r["hot_ms"][sid] for r in rows if sid in (r.get("hot_ms") or {})]
        if vals:
            hot[sid] = _stats(vals)
    for sid in TRANSPORT_STAGES:
        vals = [r["transport_ms"][sid] for r in rows if sid in (r.get("transport_ms") or {})]
        if vals:
            transport[sid] = _stats(vals)
    totals = [r["total_hot_ms"] for r in rows if isinstance(r.get("total_hot_ms"), (int, float))]
    return {"n_traces": len(rows), "hot": hot, "transport_bound": transport,
            "total_hot_ms": _stats(totals) if totals else None,
            "_note": "hot stages are code; transport-bound stages are a poll interval or a market fact and "
                     "are reported apart from them (docs/architecture/latency-model.json)",
            "_source": "docs/architecture/latency-model.json (CLAUDE.md §40)"}


def _stats(vals):
    out = {"n": len(vals), "max": max(vals)}
    for p in PERCENTILES:
        out[f"p{p}"] = percentile(vals, p)
    return out


def read(days=None):
    """Every recorded trace, newest file last. `days` limits to the last N daily files."""
    if not os.path.isdir(DIR):
        return []
    files = sorted(f for f in os.listdir(DIR) if f.endswith(".jsonl"))
    if days:
        files = files[-days:]
    rows = []
    for f in files:
        with open(os.path.join(DIR, f), encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        continue          # a half-written line from a killed tick is not a reason to fail
    return rows


def summary(days=None):
    return summarize(read(days))


def describe(summ):
    """One line per hot stage, sample size first (§39)."""
    if not summ["hot"]:
        return f"§40 latency: no hot-stage observations yet (traces: {summ['n_traces']})"
    out = [f"§40 latency over {summ['n_traces']} traces"]
    for sid, st in summ["hot"].items():
        out.append(f"  {spec_name(sid):<28} n={st['n']:<6} p50={st['p50']:.1f}ms  p95={st['p95']:.1f}ms  "
                   f"p99={st['p99']:.1f}ms  max={st['max']:.1f}ms")
    for sid, st in summ["transport_bound"].items():
        out.append(f"  {spec_name(sid):<28} n={st['n']:<6} p50={st['p50']:.1f}ms  (transport-bound: "
                   f"{stamp(sid)['_bound_why'].split('.')[0]})")
    return "\n".join(out)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="CLAUDE.md §40 latency (docs/architecture/latency-model.json).")
    ap.add_argument("--days", type=int, default=None, help="summarise only the last N daily files")
    ap.add_argument("--stages", action="store_true", help="list the ten declared stages and exit")
    a = ap.parse_args()
    if a.stages:
        for sid in ORDER:
            s = STAMPS[sid]
            print(f"{sid:<26} {s['kind']:<16} {s['captured']}")
        print(f"\nresearch workloads that must not block the live path: {', '.join(research_workloads())}")
    else:
        print(describe(summary(a.days)))
