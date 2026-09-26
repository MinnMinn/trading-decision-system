"""Which customer account runs which setup -- the account<->setup table (CLAUDE.md §33/§14).

    import mandates as MD
    MD.for_account("acc-001")        -> [mandate, ...]   the setups this account may trade right now
    MD.for_setup("cfd-scalping-...") -> [mandate, ...]   the accounts running that setup right now
    MD.drift()                       -> [ {...}, ... ]   mandates whose pinned version no longer matches

Why this is a table and not a field
-----------------------------------
The business is customers renting a methodology and handing over their own account (user, 2026-09-19). One
account runs several setups across several markets; one setup serves many accounts. That is many-to-many, and
it carries facts belonging to the RELATION rather than to either side: which version of the setup the customer
agreed to, when it started, when it ended, what risk fraction was agreed. An array field on the account (or on
the setup) has nowhere to put any of those, and picks an arbitrary owner for a symmetric relation.

It is a separate file for the same reason every other list here is: one list, one JSON, one reader. The
account registry stays `docs/architecture/account-profiles.json` (scripts/account_profile.py) and the setup
selection stays `docs/architecture/pilot-selection.json`; this file only joins them, and validates that both ends
of every row actually exist.

The version pin is the point
----------------------------
`setup_version` is the setup's `rule_version` as it stood when the mandate was attached. scripts/rank-setups.py
rewrites pilot-selection.json in place, so the same setup id can mean different rules after any re-ranking -- which
happened four times in one day on 2026-09-19. A customer must keep running the rules they agreed to until they
accept new ones, so the pin is recorded and `drift()` reports divergence rather than resolving it. Resolving it
silently would change what somebody's money is doing without telling them.

The sharing cap
---------------
`max_accounts_per_method_market` in the registry: at most that many DISTINCT accounts may hold live mandates
for one methodology on one market (user decision 2026-09-19). It counts across every setup of that method on
that market, so attaching a customer to a second ICT setup on crypto does not buy a second allowance -- what
is being bounded is how many customers are exposed to the SAME way of reading the SAME market, which is the
thing that makes them win and lose together.

It is a cap on ATTACHMENT, checked when the table is read, and it is deliberately not the same as the two
gates in scripts/exposure.py. Those ask what is on the book right now (how many of one owner's accounts hold
this symbol and side; how much notional the estate has in this instrument). This one asks who is signed up,
and it answers before any of them has a position -- which is when a limit on concentration is actually
actionable, because the alternative is telling the eleventh customer their signal was refused.

Validation refuses rather than warns
------------------------------------
Every check below raises at import. This file decides whose money trades on which rules; a row that names a
missing account, a missing setup, an unknown state, or a risk fraction above the platform ceiling is not a
degraded row, it is a row nobody can act on safely (CLAUDE.md §51).
"""
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "docs", "architecture", "mandates.json")
SELECTION = os.path.join(ROOT, "docs", "architecture", "pilot-selection.json")

sys.path.insert(0, os.path.join(ROOT, "scripts"))
import account_profile as AP
import trading_env as _TE

# The states a mandate may be in, read from the registry itself so the vocabulary has one source.
# ACTIVE is the ONLY state a signal may be taken under; PAUSED deliberately is not, and is deliberately not
# the same as ENDED, because a paused mandate may still have open positions to manage.
TRADEABLE = ("ACTIVE",)


class RegistryError(Exception):
    """Raised at import. A mandate table that cannot be trusted must stop the process, not degrade."""


def _setups():
    """The setup ids and their CURRENT rule_version, from the one selection file."""
    return {sid: row["rule_version"] for sid, row in _setup_rows().items()}


def _setup_rows():
    """id -> {rule_version, method, market}. The method and market are what the sharing cap counts over."""
    try:
        sel = json.load(open(SELECTION, encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise RegistryError(f"{SELECTION} could not be read: {e}") from e
    return {s["id"]: {"rule_version": s.get("rule_version"), "method": s.get("method"),
                      "market": s.get("market")} for s in sel.get("setups", [])}


def _date(value, field, mid):
    if value is None:
        return None
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except ValueError as e:
        raise RegistryError(f"{PATH}: mandate {mid!r} has {field}={value!r}, which is not an ISO date") from e


def _validate(data, path=PATH, setups=None):
    if data.get("version") != 1:
        raise RegistryError(f"{path}: version must be the integer 1, got {data.get('version')!r}")
    states = tuple(data.get("states") or ())
    if not states:
        raise RegistryError(f"{path}: `states` must list the mandate states; the vocabulary has one source")
    for t in TRADEABLE:
        if t not in states:
            raise RegistryError(f"{path}: `states` does not contain {t!r}, which is the state a signal may be "
                                f"taken under (mandates.TRADEABLE)")
    rows = data.get("mandates")
    if not isinstance(rows, list):
        raise RegistryError(f"{path}: `mandates` must be a list (an EMPTY list is valid -- no customers yet)")

    rows_meta = _setup_rows() if setups is None else {k: {"rule_version": v, "method": None, "market": None}
                                                     for k, v in dict(setups).items()}
    known = {k: v["rule_version"] for k, v in rows_meta.items()}
    cap = data.get("max_accounts_per_method_market")
    if not isinstance(cap, int) or cap < 1:
        raise RegistryError(f"{path}: max_accounts_per_method_market is {cap!r}; it must be a whole number "
                            f"of accounts, at least 1. It is the cap on how many accounts may share ONE "
                            f"methodology on ONE market (user decision 2026-09-19).")
    shared = {}          # (method, market) -> {account ids}
    seen_ids, seen_pairs = set(), {}
    for row in rows:
        mid = row.get("id")
        if not mid:
            raise RegistryError(f"{path}: a mandate has no `id`")
        if mid in seen_ids:
            raise RegistryError(f"{path}: duplicate mandate id {mid!r}")
        seen_ids.add(mid)
        for field in ("account", "setup", "setup_version", "state", "started_at"):
            if field not in row:
                raise RegistryError(f"{path}: mandate {mid!r} is missing {field!r}")
        if row["state"] not in states:
            raise RegistryError(f"{path}: mandate {mid!r} has state {row['state']!r}, not one of {list(states)}")
        if row["account"] not in AP.PROFILES:
            raise RegistryError(f"{path}: mandate {mid!r} names account {row['account']!r}, which is not in "
                                f"{AP.PATH}. A mandate that points at no account trades nobody's money on "
                                f"rules nobody agreed to.")
        if row["setup"] not in known:
            raise RegistryError(f"{path}: mandate {mid!r} names setup {row['setup']!r}, which is not in "
                                f"{SELECTION} (have {sorted(known)})")
        started = _date(row["started_at"], "started_at", mid)
        ended = _date(row.get("ended_at"), "ended_at", mid)
        if ended and started and ended < started:
            raise RegistryError(f"{path}: mandate {mid!r} ended {ended} before it started {started}")
        if row["state"] == "ENDED" and not ended:
            raise RegistryError(f"{path}: mandate {mid!r} is ENDED with no `ended_at`; when it stopped is the "
                                f"whole content of that state")
        if row["state"] in TRADEABLE and ended:
            raise RegistryError(f"{path}: mandate {mid!r} is {row['state']} but carries ended_at={ended}. A "
                                f"mandate that has ended may not be tradeable; set state to ENDED.")
        rp = row.get("risk_pct")
        if rp is not None:
            try:
                rp = float(rp)
            except (TypeError, ValueError) as e:
                raise RegistryError(f"{path}: mandate {mid!r} has risk_pct={row['risk_pct']!r}, not a number") from e
            if not 0 < rp <= _TE.MAX_RISK_PCT:
                raise RegistryError(
                    f"{path}: mandate {mid!r} has risk_pct {rp}, outside (0, {_TE.MAX_RISK_PCT}]. The "
                    f"platform ceiling is authored once in docs/architecture/risk-config.json and read through "
                    f"trading_env.MAX_RISK_PCT; a mandate may agree to LESS risk, never to more.")
        # Two live mandates for the same (account, setup) would make "which rules is this account running for
        # this setup" a question with two answers, and the version pin is exactly what would differ.
        if row["state"] in TRADEABLE or row["state"] == "PAUSED":
            pair = (row["account"], row["setup"])
            if pair in seen_pairs:
                raise RegistryError(f"{path}: mandates {seen_pairs[pair]!r} and {mid!r} are both live for "
                                    f"account {pair[0]!r} on setup {pair[1]!r}. End one -- a returning "
                                    f"customer gets a NEW mandate so the history stays readable.")
            seen_pairs[pair] = mid
            meta = rows_meta.get(row["setup"]) or {}
            key = (meta.get("method"), meta.get("market"))
            if key != (None, None):
                accts = shared.setdefault(key, set())
                accts.add(row["account"])
                if len(accts) > cap:
                    raise RegistryError(
                        f"{path}: mandate {mid!r} would make {len(accts)} accounts share method "
                        f"{key[0]!r} on market {key[1]!r}, over the max_accounts_per_method_market cap of "
                        f"{cap}. Accounts already on it: {sorted(accts - {row['account']})}. The cap counts "
                        f"DISTINCT accounts across every setup of that method on that market, so two setups "
                        f"of the same method do not buy a second allowance.")
    return rows


_DATA = json.load(open(PATH, encoding="utf-8"))
STATES = tuple(_DATA.get("states") or ())
MANDATES = _validate(_DATA)


# --------------------------------------------------------------------------------------------------
# Lookup

def _live(row, at=None):
    if row["state"] not in TRADEABLE:
        return False
    at = at or datetime.date.today()
    started = _date(row["started_at"], "started_at", row["id"])
    return not (started and at < started)


def all_mandates():
    return [dict(m) for m in MANDATES]


def for_account(account_id, at=None):
    """The setups this account may trade, right now. ACTIVE only -- PAUSED is not permission."""
    return [dict(m) for m in MANDATES if m["account"] == account_id and _live(m, at)]


def for_setup(setup_id, at=None):
    """The accounts running this setup right now. This is the count that says how many customers a rule
    change is about to affect."""
    return [dict(m) for m in MANDATES if m["setup"] == setup_id and _live(m, at)]


def accounts(at=None):
    """Every account with at least one tradeable mandate -- the list a supervisor spawns runners for."""
    return sorted({m["account"] for m in MANDATES if _live(m, at)})


def risk_pct(mandate):
    """The risk fraction agreed for THIS mandate, never above the platform ceiling and never above the
    account's own. Falls back to the account's effective ceiling when the mandate did not name one."""
    prof = AP.get(mandate["account"])
    account_ceiling = AP.effective_risk_pct(prof)
    rp = mandate.get("risk_pct")
    return min(float(rp), account_ceiling) if rp is not None else account_ceiling


def drift(at=None):
    """Live mandates whose pinned `setup_version` no longer matches the setup's current `rule_version`.

    Reported, never resolved. A customer agreed to a version; moving them onto a new one is a decision
    somebody makes, and this is the list that decision starts from. Empty is the normal state.
    """
    current = _setups()
    out = []
    for m in MANDATES:
        if not _live(m, at):
            continue
        now = current.get(m["setup"])
        if now is not None and now != m["setup_version"]:
            out.append({"mandate": m["id"], "account": m["account"], "setup": m["setup"],
                        "agreed": m["setup_version"], "current": now})
    return out
