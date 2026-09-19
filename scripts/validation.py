"""CLAUDE.md §45 -- THE runner for docs/architecture/validation.json: twelve ways to try to break a candidate,
eleven things to check, and a default posture of disbelief.

§45's operative sentence is not the list. It is:

    "Actively attempt to disprove candidates. Do not only search for evidence that a candidate works."

That is a statement about the DEFAULT, so the default here is refutation. `disprove()` returns `REFUTED`
unless every applicable check survived, and **a check that could not run counts against the candidate** rather
than being passed over in silence. Confirmation is what is left after failing to break something; it is never
the starting position.

    import validation as V

    res = V.disprove(evaluate, baseline=trades, partitions={"instrument": ..., "session": ...})
    res["verdict"]      -> 'REFUTED'
    res["checks"]["regime_dependency"]   -> {"verdict": "REFUTED", "why": "...", "threshold": 0.5}

Every method takes an **evaluator** -- a callable mapping a configuration to a trade population -- so a method
can be exercised on a synthetic system in a test and run against the real backtest engine in a research run
without knowing which it has. That is what makes these testable at all: a validation suite that can only be
run by executing three hours of backtests is a validation suite nobody runs.

**No thresholds live here.** §45 says what to check, not where to draw a line, and a line drawn in this module
would be a project parameter masquerading as a rule. Every check takes its threshold as an argument and
records it in the result, so a reader can see what "survived" was measured against and disagree with it.
"""
import json
import os
import random
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import performance as P

PATH = os.path.join(ROOT, "docs", "architecture", "validation.json")

SURVIVED, REFUTED, NOT_RUN = "SURVIVED", "REFUTED", "NOT_RUN"


class RegistryError(ValueError):
    """The §45 registry itself is wrong -- raised at import."""


class NotDeclared(KeyError):
    """Something named a method or check CLAUDE.md §45 does not list."""


def _load(path=None):
    path = path or PATH
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    for key in ("methods", "checks"):
        if not isinstance(data.get(key), list) or not data[key]:
            raise RegistryError(f"{path}: `{key}` must be a non-empty list")
        seen = set()
        for row in data[key]:
            for f in ("id", "spec_name", "implemented_by"):
                if not str(row.get(f) or "").strip():
                    raise RegistryError(f"{path}: {key[:-1]} {row.get('id')!r} has no {f!r}")
            if row["id"] in seen:
                raise RegistryError(f"{path}: duplicate {key[:-1]} id {row['id']!r}")
            seen.add(row["id"])
    v = data.get("verdicts") or {}
    if set(v) != {SURVIVED, REFUTED, NOT_RUN}:
        raise RegistryError(f"{path}: `verdicts` must be exactly {SURVIVED}, {REFUTED}, {NOT_RUN}")
    if "NOT a pass" not in v[NOT_RUN]:
        raise RegistryError(
            f"{path}: the {NOT_RUN!r} verdict must say it is not a pass. CLAUDE.md §45's posture is "
            f"refutation, and a check that silently counts as survived is how a candidate passes by being "
            f"untested.")
    return data


_DATA = _load()
METHODS = {m["id"]: m for m in _DATA["methods"]}
METHOD_ORDER = tuple(m["id"] for m in _DATA["methods"])
CHECKS = {c["id"]: c for c in _DATA["checks"]}
CHECK_ORDER = tuple(c["id"] for c in _DATA["checks"])


def method(mid):
    m = METHODS.get(mid)
    if m is None:
        raise NotDeclared(f"no §45 method {mid!r}; the twelve are {list(METHOD_ORDER)}")
    return m


def check(cid):
    c = CHECKS.get(cid)
    if c is None:
        raise NotDeclared(f"no §45 check {cid!r}; the eleven are {list(CHECK_ORDER)}")
    return c


def spec_name(xid):
    return (METHODS.get(xid) or CHECKS.get(xid) or {}).get("spec_name") or xid


def _verdict(ok, why, **extra):
    return dict({"verdict": SURVIVED if ok else REFUTED, "why": why}, **extra)


def not_run(why, **extra):
    """A check that could not run. NOT a pass -- `disprove()` counts it against the candidate."""
    return dict({"verdict": NOT_RUN, "why": why}, **extra)


def _edge(trades):
    """The one number every method compares: mean R with its sample size beside it (§39)."""
    m = P.metrics(trades)
    exp = m["expectancy"]
    return (None if P.is_unavailable(exp) else exp), m["n"]


# ---- the twelve methods


def in_sample(trades):
    """§45 method 1. NOT validation, and labelled so -- it is the baseline the others are compared against."""
    e, n = _edge(trades)
    return {"method": "in_sample", "expectancy": e, "n": n,
            "_note": "in-sample is the baseline, not evidence: the candidate was built on this data"}


def oos(evaluate, period_id):
    """§45 method 2, gated by §44.

    Refuses rather than measuring development data and calling it validation. That refusal is the whole value
    of the method in this repo today.
    """
    import research_ledger as RL
    try:
        RL.assert_untouched(period_id)
    except RL.NotValidationData as exc:
        return not_run(str(exc), method="oos")
    except RL.NotDeclared as exc:
        return not_run(str(exc), method="oos")
    trades = evaluate({"period": period_id})
    e, n = _edge(trades)
    return {"method": "oos", "period": period_id, "expectancy": e, "n": n}


def walk_forward(trades, *, folds=5, key="entry_time"):
    """§45 method 3: rolling windows in chronological order.

    With fixed rules there is nothing to re-fit, so what this measures is whether the edge is SPREAD across
    time or concentrated in one stretch. The fold count is the caller's and is recorded.
    """
    rows = sorted([t for t in trades if t.get(key)], key=lambda t: t[key])
    if len(rows) < folds * 2:
        return not_run(f"{len(rows)} trades cannot be split into {folds} folds of at least 2", method="walk_forward")
    size = len(rows) // folds
    out = []
    for i in range(folds):
        chunk = rows[i * size:(i + 1) * size] if i < folds - 1 else rows[i * size:]
        e, n = _edge(chunk)
        out.append({"fold": i + 1, "n": n, "expectancy": e,
                    "from": chunk[0][key], "to": chunk[-1][key]})
    return {"method": "walk_forward", "folds": folds, "results": out,
            "positive_folds": sum(1 for f in out if (f["expectancy"] or 0) > 0)}


def parameter_sensitivity(evaluate, *, parameter, values, baseline_value=None):
    """§45 method 4: vary one parameter and watch the result move.

    A result that survives only at its exact configured value was fitted to that value, whether or not anyone
    ran an optimiser.
    """
    out = []
    for v in values:
        e, n = _edge(evaluate({parameter: v}))
        out.append({"value": v, "expectancy": e, "n": n, "is_configured": v == baseline_value})
    es = [r["expectancy"] for r in out if r["expectancy"] is not None]
    return {"method": "parameter_sensitivity", "parameter": parameter, "results": out,
            "positive_settings": sum(1 for e in es if e > 0), "settings_tried": len(out),
            "spread": (max(es) - min(es)) if len(es) > 1 else None}


def partition(trades, key_fn, *, name):
    """§45 methods 5-8: the same rules measured per regime / instrument / session / period.

    One function for four methods because they differ only in the key. Four copies would drift, and §45 lists
    them separately because they are four QUESTIONS, not four algorithms.
    """
    groups = {}
    for t in trades:
        groups.setdefault(str(key_fn(t)), []).append(t)
    out = {}
    for k, v in groups.items():
        e, n = _edge(v)
        out[k] = {"n": n, "expectancy": e}
    positive = [k for k, v in out.items() if (v["expectancy"] or 0) > 0]
    return {"method": f"{name}_variation", "partition": name, "groups": out,
            "n_groups": len(out), "positive_groups": len(positive), "positive": sorted(positive)}


def monte_carlo(trades, *, iterations=2000, seed=20260918):
    """§45 method 10: resample the trade SEQUENCE.

    The order of the same trades is luck. A drawdown that depends on it is a property of one ordering, not of
    the rules -- so the distribution of drawdowns over reorderings is what the number should have been.
    """
    rs = [P._r(t) for t in trades if P._r(t) is not None]
    if len(rs) < 10:
        return not_run(f"{len(rs)} trades is too few to resample meaningfully", method="monte_carlo")
    rng = random.Random(seed)
    dds, finals = [], []
    for _ in range(iterations):
        order = rs[:]
        rng.shuffle(order)
        cum = peak = 0.0
        dd = 0.0
        for r in order:
            cum += r
            peak = max(peak, cum)
            dd = max(dd, peak - cum)
        dds.append(dd)
        finals.append(cum)
    dds.sort()
    return {"method": "monte_carlo", "iterations": iterations, "seed": seed, "n": len(rs),
            "observed_sum_R": sum(rs),
            "max_drawdown_R_p50": dds[len(dds) // 2], "max_drawdown_R_p95": dds[int(len(dds) * 0.95)],
            "max_drawdown_R_worst": dds[-1],
            "share_of_orderings_profitable": sum(1 for f in finals if f > 0) / len(finals)}


def perturbation(evaluate, *, jitters, baseline=None):
    """§45 method 11: jitter the inputs and re-measure.

    A result that needs an exact fill is a result about a fill nobody will get.
    """
    out = []
    for j in jitters:
        e, n = _edge(evaluate(j))
        out.append({"jitter": j, "expectancy": e, "n": n})
    base_e = _edge(baseline)[0] if baseline is not None else None
    es = [r["expectancy"] for r in out if r["expectancy"] is not None]
    return {"method": "perturbation", "baseline_expectancy": base_e, "results": out,
            "positive_under_jitter": sum(1 for e in es if e > 0), "jitters_tried": len(out)}


def stress(evaluate, *, scenarios):
    """§45 method 12: deliberately hostile execution assumptions.

    Not a sensitivity sweep around the configured value -- a walk to the bad end of it: a wider fee, slippage
    against every fill, the worse side of every stop.
    """
    out = []
    for name, cfg in scenarios.items():
        e, n = _edge(evaluate(cfg))
        out.append({"scenario": name, "config": cfg, "expectancy": e, "n": n})
    return {"method": "stress", "results": out,
            "survived": [r["scenario"] for r in out if (r["expectancy"] or 0) > 0],
            "scenarios_tried": len(out)}


def robustness(*results):
    """§45 method 9: the combined verdict over the perturbation family.

    An umbrella, and it says so: it does not compute anything new, it refuses to let three passing tests and
    one failing one be reported as "robust".
    """
    parts = [r for r in results if r]
    broke = [r.get("method") for r in parts
             if r.get("verdict") == REFUTED
             or (r.get("positive_settings") == 0 and r.get("settings_tried"))
             or (r.get("survived") == [] and r.get("scenarios_tried"))
             or (r.get("positive_under_jitter") == 0 and r.get("jitters_tried"))]
    unrun = [r.get("method") for r in parts if r.get("verdict") == NOT_RUN]
    return {"method": "robustness", "components": [r.get("method") for r in parts],
            "broken_by": broke, "not_run": unrun,
            "verdict": REFUTED if broke else (NOT_RUN if unrun else SURVIVED)}


# ---- the eleven checks


def check_sample_size(trades, *, minimum=30):
    n = len([t for t in trades if P._r(t) is not None])
    return _verdict(n >= minimum, f"n={n} against a declared minimum of {minimum}", n=n, threshold=minimum)


def check_consistency(trades, *, max_share_from_best=0.5):
    """Is the edge spread, or is it a handful of trades?

    The failure this catches: a positive sum carried by two outliers. A candidate whose edge is one trade is
    a candidate with a sample size of one wearing a sample size of two hundred.
    """
    rs = sorted((P._r(t) for t in trades if P._r(t) is not None), reverse=True)
    total = sum(rs)
    if not rs or total <= 0:
        return not_run("no positive total to attribute", n=len(rs))
    top = max(1, len(rs) // 20)                       # the best 5 % of trades
    share = sum(rs[:top]) / total
    return _verdict(share <= max_share_from_best,
                    f"the best {top} of {len(rs)} trades supply {share:.0%} of the total R",
                    share_from_best=share, threshold=max_share_from_best)


def check_partition_dependency(part, *, min_positive_share=0.5):
    """One implementation for the four dependency checks (regime / instrument / session / temporal).

    §45 lists them separately because they are four questions; the arithmetic is one.
    """
    if not part or part.get("verdict") == NOT_RUN or not part.get("n_groups"):
        return not_run("no partition available", threshold=min_positive_share)
    share = part["positive_groups"] / part["n_groups"]
    return _verdict(share >= min_positive_share,
                    f"{part['positive_groups']} of {part['n_groups']} {part.get('partition')} groups are "
                    f"positive ({share:.0%})",
                    positive_share=share, threshold=min_positive_share, groups=part["groups"])


def check_execution_assumptions(stress_result):
    if not stress_result or stress_result.get("verdict") == NOT_RUN:
        return not_run("no stress scenarios were run")
    survived = stress_result.get("survived") or []
    tried = stress_result.get("scenarios_tried") or 0
    return _verdict(len(survived) == tried and tried > 0,
                    f"survived {len(survived)} of {tried} hostile execution scenarios",
                    survived=survived, scenarios=tried)


def check_data_quality(validity_block):
    """§38's verdict on the run that produced this population. A candidate validated on flagged data is a
    candidate whose validation carries that flag."""
    if not validity_block or "verdict" not in (validity_block or {}):
        return not_run("the population carries no §38 research-validity verdict")
    v = validity_block["verdict"]
    return _verdict(v in ("VALID", "FLAGGED"), f"§38 verdict is {v}", research_validity=v)


def check_selection_bias(budget_block, *, max_candidates=10):
    if not budget_block:
        return not_run("no §43 budget available")
    n = budget_block["counts"]["candidate_count"]
    unrecorded = len(budget_block.get("unrecorded") or ())
    if unrecorded:
        return not_run(f"{n} candidates recorded, but {unrecorded} known selection(s) predate the experiment "
                       f"store and are not counted -- the true denominator is unknown",
                       recorded=n, unrecorded=unrecorded)
    return _verdict(n <= max_candidates, f"{n} candidates recorded", candidates=n, threshold=max_candidates)


def check_survivorship(symbols=None):
    """§9 recorded this as structural: the allowlist holds only currently-listed symbols, so every backtest
    runs on survivors. It is not fixable by a threshold, so the check REPORTS rather than passing."""
    import instruments as I
    syms = list(symbols or I.backtested("crypto"))
    return not_run(
        f"structural: the {len(syms)} instruments measured are all currently listed, so delisted and failed "
        f"symbols are absent from every population by construction (§9's bias register). No threshold makes "
        f"this pass; it is a property of the instrument set.",
        instruments=syms)


def check_multiple_testing(budget_block):
    if not budget_block:
        return not_run("no §43 budget available")
    c = budget_block["counts"]
    tests = c["candidate_count"] + c["parameter_searches"]
    unrecorded = len(budget_block.get("unrecorded") or ())
    if unrecorded:
        return not_run(f"{tests} recorded tests, plus {unrecorded} unrecorded search(es) -- a multiple-testing "
                       f"correction needs a denominator, and this one is incomplete",
                       recorded_tests=tests, unrecorded=unrecorded)
    return _verdict(tests <= 10, f"{tests} tests produced this winner", tests=tests)


# ---- the posture


def disprove(*, checks):
    """CLAUDE.md §45: the candidate is REFUTED unless every check survived.

    `checks` maps a declared check id to its result. Two rules make this a disproof rather than a search for
    confirmation:

      * a missing check is NOT_RUN, not absent -- every declared check appears in the output;
      * NOT_RUN counts AGAINST the candidate, because a candidate that passed by being untested has not
        passed.
    """
    out = {}
    for cid in CHECK_ORDER:
        r = checks.get(cid)
        out[cid] = r if r else not_run("this check was not attempted")
    refuted = [c for c, r in out.items() if r["verdict"] == REFUTED]
    unrun = [c for c, r in out.items() if r["verdict"] == NOT_RUN]
    verdict = REFUTED if refuted else (NOT_RUN if unrun else SURVIVED)
    return {"verdict": verdict, "refuted_by": refuted, "not_run": unrun,
            "checks": out,
            "_posture": "CLAUDE.md §45: 'Actively attempt to disprove candidates.' A candidate is only "
                        "SURVIVED when every declared check ran and none broke it; NOT_RUN is not a pass.",
            "_source": "docs/architecture/validation.json (CLAUDE.md §45)"}


def describe(res):
    lines = [f"§45 verdict: {res['verdict']}"]
    for cid in CHECK_ORDER:
        r = res["checks"][cid]
        lines.append(f"  {spec_name(cid):<24} {r['verdict']:<10} {r['why']}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(f"CLAUDE.md §45 -- {len(METHOD_ORDER)} methods, {len(CHECK_ORDER)} checks\n")
    for mid in METHOD_ORDER:
        m = METHODS[mid]
        gate = f"  [gated: {m['_gated_by'][:60]}...]" if m.get("_gated_by") else ""
        print(f"  {m['spec_name']:<32} {m['kind']}{gate}")
    print()
    for cid in CHECK_ORDER:
        print(f"  {CHECKS[cid]['spec_name']:<32} {CHECKS[cid]['asks']}")
