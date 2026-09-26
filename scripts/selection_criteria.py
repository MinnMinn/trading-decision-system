"""The pilot's selection gate (ADR 0008): does one backtest window meet its horizon's absolute criteria?

    import selection_criteria as SC
    crit = SC.load()                                   # docs/architecture/selection-criteria.json
    v = SC.evaluate(window_block, "scalping", crit)    # {"passed": bool, "checks": [...], "reported": [...]}

`docs/architecture/selection-criteria.json` is the ONE source of the thresholds; this module is its one reader.
It owns only the mapping from a criterion name to the window field it reads and the direction of the test --
never a number.

Rules (ADR 0008, CLAUDE.md §20):
  * every criterion of the horizon must pass; there is no score, no weighting and no ranking;
  * a threshold is met AT the boundary: a `_min` criterion passes on `value >= threshold`, a `_max` criterion
    passes on `value <= threshold`;
  * a missing, null, non-numeric or non-finite input FAILS with reason "missing" -- an unmeasured value is
    never read as a pass (MISSING is not EMPTY, UNKNOWN is not LOW);
  * a key in the file this module does not know REFUSES the whole file (a threshold it cannot evaluate would
    otherwise be silently skipped, i.e. loosened);
  * `monthly_return_pct_target` is REPORTED and never gates (the file's own `_notes`).

The window fields are the ones `scripts/stability-report.py` `window_block()` / `monthly_block()` write for
each side of the in-sample / OOS split: `m_mean_geo`, `m_losing`, `m_worst`, `dd`, `q_worst`.
"""
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "docs", "architecture", "selection-criteria.json")

GE, LE = ">=", "<="
# criterion key -> (window field, comparison that PASSES, label). Order is the order they are reported in.
GATES = {
    "mean_monthly_return_pct_min": ("m_mean_geo", GE, "mean monthly return % (geometric)"),
    "losing_months_max": ("m_losing", LE, "losing calendar months"),
    "worst_month_pct_min": ("m_worst", GE, "worst calendar month %"),
    "max_drawdown_pct_max": ("dd", LE, "max drawdown %"),
    "worst_quarter_pct_min": ("q_worst", GE, "worst quarter %"),
}
REPORTED_ONLY = {
    "monthly_return_pct_target": ("m_mean_geo", GE, "mean monthly return % vs the owner's target (reported, not a gate)"),
}
MISSING = "missing"


class CriteriaError(ValueError):
    """The criteria file cannot be evaluated as written; nothing may be selected from it."""


def load(path=None):
    """The parsed criteria file, validated. Raises CriteriaError on anything this module cannot evaluate."""
    p = path or PATH
    with open(p, encoding="utf-8") as fh:
        doc = json.load(fh)
    horizons = doc.get("horizons")
    if not isinstance(horizons, dict) or not horizons:
        raise CriteriaError(f"{p}: no `horizons` block")
    for hz, spec in horizons.items():
        gates = 0
        for k, v in spec.items():
            if k.startswith("_"):
                continue
            if k not in GATES and k not in REPORTED_ONLY:
                raise CriteriaError(f"{p}: horizon {hz!r} declares {k!r}, which scripts/selection_criteria.py "
                                    f"cannot evaluate -- refusing the file rather than skipping a threshold")
            if not _is_number(v):
                raise CriteriaError(f"{p}: horizon {hz!r} {k!r} = {v!r} is not a number")
            gates += k in GATES
        if not gates:
            raise CriteriaError(f"{p}: horizon {hz!r} has no gating criterion -- it would pass everything")
    return doc


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _check(key, spec_value, block, table):
    field, op, label = table[key]
    raw = block.get(field) if isinstance(block, dict) else None
    out = dict(criterion=key, field=field, op=op, threshold=spec_value, label=label)
    if not _is_number(raw):
        return dict(out, value=None, passed=False, reason=MISSING)
    ok = raw >= spec_value if op == GE else raw <= spec_value
    return dict(out, value=raw, passed=ok,
                reason=f"{label} {raw:.4g} {'meets' if ok else 'fails'} {op} {spec_value:g}")


def evaluate(block, horizon, criteria):
    """One window block against one horizon. Pure.

    Returns {"horizon", "passed", "checks": [one per gating criterion], "reported": [target lines], "failed":
    [reasons]}. An unknown horizon or a missing block fails closed with an explicit reason."""
    spec = (criteria.get("horizons") or {}).get(horizon)
    if spec is None:
        return dict(horizon=horizon, passed=False, checks=[], reported=[],
                    failed=[f"no criteria for horizon {horizon!r} in selection-criteria.json"])
    if not isinstance(block, dict):
        checks = [dict(criterion=k, field=GATES[k][0], op=GATES[k][1], threshold=v, label=GATES[k][2],
                       value=None, passed=False, reason=MISSING)
                  for k, v in spec.items() if k in GATES]
        return dict(horizon=horizon, passed=False, checks=checks, reported=[],
                    failed=[f"{c['criterion']}: missing (no window block)" for c in checks])
    checks = [_check(k, spec[k], block, GATES) for k in GATES if k in spec]
    reported = [_check(k, spec[k], block, REPORTED_ONLY) for k in REPORTED_ONLY if k in spec]
    failed = [f"{c['criterion']}: {c['reason']}" for c in checks if not c["passed"]]
    return dict(horizon=horizon, passed=bool(checks) and not failed, checks=checks, reported=reported, failed=failed)
