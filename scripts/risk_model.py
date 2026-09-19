"""THE risk model (CLAUDE.md §34): what a trade costs, what it risks, and whether it may be placed.

    import risk_model as RM
    RM.net_r(entry=100.0, stop=99.0, target=110.0, venue="futures", order_type="maker")
        -> {"gross_r": 10.0, "cost_r": 0.04, "net_r": 9.96, "slippage": "UNKNOWN", ...}
    RM.size(equity=10000, entry=100.0, stop=99.0, risk_pct=0.01, leverage=3, notional_cap_pct=0.25)
    RM.open_risk(positions, equity)     -> the exposure already on, as a FRACTION of equity, not a count
    RM.validate(plan, ...)              -> [checks], each named, each pass/fail/UNKNOWN

§34 names eleven inputs a risk calculation must consider: entry, stop loss, position size, leverage, account
balance, account limits, fees, slippage, existing exposure, instrument specifications. Before 2026-09-18 the
live path considered six of them. Fees and slippage reached no live sizing path at all, and existing exposure
was counted (`n positions`) rather than summed (`n x risk`).

THE DEFECT THIS MODULE EXISTS TO CLOSE
---------------------------------------
`r_planned` is `|target - entry| / |entry - stop|` (strategy-runner.py) -- a GROSS R:R. The 3R floor it is
compared against was measured NET of fees: `docs/architecture/analysis-params.json` records the basis as
"Measured on the last year of ICT 15m setups ... (fee 0.05 %/side)", and the backtest that produced it
subtracts `2 * fee_pct / dist` from every R before counting it (backtest-methods.py:517).

So the live gate was strictly looser than the evidence behind it, and by a margin that grows as the stop
tightens: round-turn cost in R is `2 * fee / (|entry - stop| / entry)`, so at 0.05 %/side a 1 % stop costs
0.1R and a 0.2 % stop costs 0.5R. A setup planning 3.1R gross on a tight stop was being taken as though it
cleared a floor it did not clear. Tightening this REFUSES trades that used to pass; that is the direction a
risk model is supposed to fail in.

WHAT IT REFUSES RATHER THAN GUESSES
------------------------------------
An unknown venue, an unknown order type, a non-positive stop distance, a missing instrument specification.
Every one raises `RiskRefused` carrying the reason. The old `min_notional()` swallowed every exception and
returned a literal 50.0 -- a number no venue published, used to decide whether a real order was big enough.

SLIPPAGE IS UNKNOWN, NOT ZERO
------------------------------
`risk-config.json costs.slippage_pct` is null on purpose. Every result this module returns carries
`slippage: "UNKNOWN"` and every net figure is therefore an UPPER BOUND on what the trade actually keeps.
Callers may not treat the absence of a slippage number as the presence of a zero.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "docs", "architecture", "risk-config.json")

ORDER_TYPES = ("maker", "taker")
UNKNOWN = "UNKNOWN"

# What `validate` can say about one check. A check that could not be evaluated is UNKNOWN and is NOT a pass --
# same three-valued discipline as §20's data quality and §33's account rules.
PASS, FAIL = "PASS", "FAIL"


class RiskRefused(Exception):
    """A risk calculation that must not produce a number, carrying why."""


def _config(path=None):
    with open(path or CONFIG, encoding="utf-8") as fh:
        return json.load(fh)


def costs(venue, order_type="taker", cfg=None):
    """The declared per-side cost for this venue and order type, plus the slippage state.

    Raises rather than defaulting: a fee this module invented would silently change every position size and
    every R:R verdict downstream of it.
    """
    cfg = cfg if cfg is not None else _config()
    block = (cfg.get("costs") or {})
    if not block:
        raise RiskRefused(f"{CONFIG} declares no `costs`. CLAUDE.md §34 requires fees in the risk "
                          f"calculation, and there is no default fee that is safe to assume.")
    if order_type not in ORDER_TYPES:
        raise RiskRefused(f"order_type {order_type!r} is not one of {list(ORDER_TYPES)}. A post-only GTX limit "
                          f"pays maker; a market order pays taker; guessing between them mis-prices the trade.")
    venue_costs = block.get(venue)
    if not isinstance(venue_costs, dict):
        raise RiskRefused(f"no execution costs declared for venue {venue!r} in {CONFIG} "
                          f"(have {sorted(k for k in block if not k.startswith('_'))}).")
    key = f"{order_type}_pct_per_side"
    fee = venue_costs.get(key)
    if not isinstance(fee, (int, float)) or isinstance(fee, bool) or fee < 0:
        raise RiskRefused(f"{venue}.{key} is {fee!r}; expected a non-negative fraction (0.0005 = 0.05 %).")
    slip = block.get("slippage_pct")
    return {"fee_pct_per_side": float(fee), "venue": venue, "order_type": order_type,
            "slippage_pct": slip,
            "slippage": UNKNOWN if slip is None else "MODELLED"}


def cost_r(entry, stop, venue, order_type="taker", cfg=None):
    """Round-turn cost expressed in R -- the same formula the backtest charges (backtest-methods.py:517).

    `dist` is the stop distance as a fraction of entry, so the cost in R is `2 * fee / dist`: two sides, and
    the tighter the stop the more of the trade's R the fee eats. This is why it cannot be ignored on a
    scalping timeframe, where stops are tight by construction.
    """
    c = costs(venue, order_type, cfg=cfg)
    entry, stop = float(entry), float(stop)
    if entry <= 0:
        raise RiskRefused(f"entry {entry} is not a positive price.")
    dist = abs(entry - stop) / entry
    if dist <= 0:
        raise RiskRefused("stop distance is zero: entry and stop are the same price, so risk per unit is zero "
                          "and position size would be unbounded.")
    return 2.0 * c["fee_pct_per_side"] / dist, c


def net_r(entry, stop, target, venue, order_type="taker", cfg=None):
    """Planned R:R after execution costs -- an UPPER BOUND, because slippage is unmodelled.

    Returns gross and net side by side on purpose: the gross number is what the chart shows and what every
    pre-2026-09-18 log line recorded, so a reader comparing the two can see exactly what the cost took.
    """
    cr, c = cost_r(entry, stop, venue, order_type, cfg=cfg)
    entry, stop, target = float(entry), float(stop), float(target)
    gross = abs(target - entry) / abs(entry - stop)
    return {"gross_r": gross, "cost_r": cr, "net_r": gross - cr,
            "fee_pct_per_side": c["fee_pct_per_side"], "venue": venue, "order_type": order_type,
            "slippage": c["slippage"],
            "net_is_upper_bound": c["slippage"] == UNKNOWN}


def size(equity, entry, stop, risk_pct, leverage=1.0, notional_cap_pct=None, risk_mult=1.0):
    """Position size from the account, the stop distance and the leverage cap.

    Unchanged in arithmetic from the runner's own `size()` -- deliberately, so this migration moves the
    calculation without moving the number. What it adds is refusal: a zero stop distance, a non-positive
    equity or a nonsensical risk fraction used to produce a quantity; now each one raises.
    """
    equity, entry, stop = float(equity), float(entry), float(stop)
    if equity <= 0:
        raise RiskRefused(f"equity {equity} is not positive; there is nothing to risk a fraction of.")
    if not 0 < risk_pct <= 1:
        raise RiskRefused(f"risk_pct {risk_pct!r} is not a fraction in (0, 1]. A `1` typed for '1 %' would "
                          f"risk the whole account on one trade.")
    r = abs(entry - stop)
    if r <= 0:
        raise RiskRefused("stop distance is zero: position size would be unbounded.")
    risk_usd = equity * risk_pct * risk_mult
    qty = risk_usd / r
    capped = False
    if notional_cap_pct is not None:
        cap = equity * float(notional_cap_pct) * float(leverage)
        if qty * entry > cap:
            qty, capped = cap / entry, True
    return {"qty": qty, "risk_usd": risk_usd, "stop_distance": r,
            "notional": qty * entry, "notional_capped": capped, "leverage": leverage}


def open_risk(positions, equity):
    """Exposure already on the book, as a FRACTION of equity -- §34's "existing exposure".

    The pre-2026-09-18 gate counted positions and compared the count to a cap. Two positions with a 2 % stop
    and twenty with a 0.1 % stop are the same exposure and the count cannot tell them apart; this sums what is
    actually at risk. A position whose risk cannot be computed is returned in `unknown`, never as zero -- an
    unmeasurable position is the one most likely to be the large one.
    """
    equity = float(equity)
    if equity <= 0:
        raise RiskRefused(f"equity {equity} is not positive.")
    total, unknown = 0.0, []
    for sym, p in (positions or {}).items():
        try:
            qty = abs(float(p["qty"])); entry = float(p["entry"]); stop = float(p["stop"])
        except (KeyError, TypeError, ValueError):
            unknown.append(sym); continue
        if not (qty > 0 and entry > 0 and abs(entry - stop) > 0):
            unknown.append(sym); continue
        total += qty * abs(entry - stop)
    return {"risk_fraction": total / equity, "risk_usd": total,
            "positions": len(positions or {}), "unknown": unknown,
            "complete": not unknown}


def validate(*, entry, stop, target, venue, order_type, equity, risk_pct, min_rr,
             positions=None, max_open_risk_fraction=None, min_notional=None, notional=None, cfg=None):
    """Every §34 check, by name, before execution. Returns a list of findings; `ok` is the summary.

    §34's last line is "Risk must be validated before execution", and the point of returning the checks rather
    than a bare boolean is that a refusal has to be able to say WHICH rule refused -- a caller that only knows
    "no" cannot explain itself in a decision record (§19, §50).

    A check that cannot be evaluated is UNKNOWN and counts as not-passed.
    """
    out = []

    def add(name, state, why, blocking=True):
        """`blocking` is what separates a GATE from a DISCLOSURE.

        Every UNKNOWN blocks by default -- a check that could not be evaluated is not permission. The one
        exception is the slippage note, and the reason is worth stating rather than assuming: slippage is not
        merely unmeasured, it is unmeasurABLE here until the pilot has recorded fill-vs-intent data (§41), so
        blocking on it would not be a risk control but a permanent refusal to operate. What it does instead is
        travel with the verdict, so nobody reads the net R:R as a floor rather than a ceiling.
        """
        out.append({"check": name, "state": state, "why": why, "blocking": blocking})

    try:
        r = net_r(entry, stop, target, venue, order_type, cfg=cfg)
    except RiskRefused as exc:
        add("planned_rr", UNKNOWN, str(exc))
        return {"ok": False, "checks": out, "rr": None}

    if min_rr is None:
        add("planned_rr", UNKNOWN, "the R:R floor is unreadable (docs/architecture/analysis-params.json)")
    elif r["net_r"] < min_rr:
        add("planned_rr", FAIL,
            f"net R:R {r['net_r']:.2f} < {min_rr} floor (gross {r['gross_r']:.2f} minus "
            f"{r['cost_r']:.2f}R of fees at {r['fee_pct_per_side']:.4%}/side, {order_type})")
    else:
        add("planned_rr", PASS,
            f"net R:R {r['net_r']:.2f} >= {min_rr} (gross {r['gross_r']:.2f} - {r['cost_r']:.2f}R fees)")

    if r["net_is_upper_bound"]:
        add("slippage", UNKNOWN,
            "slippage is not modelled (risk-config.json costs.slippage_pct is null), so the net R:R above is "
            "an upper bound on what this trade keeps", blocking=False)

    try:
        s = size(equity, entry, stop, risk_pct)
        add("position_size", PASS, f"{s['qty']:.8f} units risking {s['risk_usd']:.2f} "
                                   f"({risk_pct:.2%} of {equity:.2f})")
    except RiskRefused as exc:
        add("position_size", UNKNOWN, str(exc)); s = None

    if max_open_risk_fraction is not None:
        try:
            ex = open_risk(positions or {}, equity)
        except RiskRefused as exc:
            add("existing_exposure", UNKNOWN, str(exc))
        else:
            would_be = ex["risk_fraction"] + (risk_pct if s else 0.0)
            if not ex["complete"]:
                add("existing_exposure", UNKNOWN,
                    f"risk could not be computed for {ex['unknown']}; the book's total exposure is unknown, "
                    f"and an unmeasurable position is not a zero-risk one")
            elif would_be > max_open_risk_fraction:
                add("existing_exposure", FAIL,
                    f"open risk {ex['risk_fraction']:.2%} + this trade {risk_pct:.2%} = {would_be:.2%} "
                    f"> {max_open_risk_fraction:.2%} allowed")
            else:
                add("existing_exposure", PASS,
                    f"open risk {ex['risk_fraction']:.2%} over {ex['positions']} position(s); with this trade "
                    f"{would_be:.2%}")

    if min_notional is not None:
        if notional is None:
            add("min_notional", UNKNOWN, "order notional not supplied")
        elif float(notional) < float(min_notional):
            add("min_notional", FAIL, f"notional {float(notional):.2f} below the venue minimum {min_notional}")
        else:
            add("min_notional", PASS, f"notional {float(notional):.2f} >= {min_notional}")

    return {"ok": all(f["state"] == PASS for f in out if f["blocking"]), "checks": out, "rr": r,
            "disclosures": [f for f in out if not f["blocking"]]}


def describe(result):
    """One line per check, for a log or a decision record."""
    return "\n".join(f"  {f['state']:7} {'' if f['blocking'] else '(note) '}{f['check']}: {f['why']}"
                     for f in result["checks"])


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Risk model (CLAUDE.md §34).")
    ap.add_argument("--entry", type=float, required=True); ap.add_argument("--stop", type=float, required=True)
    ap.add_argument("--target", type=float, required=True)
    ap.add_argument("--venue", default="futures"); ap.add_argument("--order-type", default="taker")
    ap.add_argument("--equity", type=float, default=10000.0); ap.add_argument("--risk-pct", type=float, default=0.01)
    ap.add_argument("--min-rr", type=float, default=3.0)
    a = ap.parse_args()
    try:
        res = validate(entry=a.entry, stop=a.stop, target=a.target, venue=a.venue, order_type=a.order_type,
                       equity=a.equity, risk_pct=a.risk_pct, min_rr=a.min_rr)
    except RiskRefused as exc:
        print(f"REFUSED: {exc}"); raise SystemExit(2)
    print(("OK" if res["ok"] else "REFUSED") + ":")
    print(describe(res))
