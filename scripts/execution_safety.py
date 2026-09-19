"""CLAUDE.md §51 -- THE reader for docs/architecture/execution-safety.json, and the one guard §51 was missing.

§51 has eight requirements. Seven of them were already held somewhere in this repository and had simply never
been written down in one place -- the pilot's refusal of environment `real`, the `__FILL_ME__` placeholders,
the `unattended` provider flag, the §36 decision ordering, the two demo-only account profiles, the venue
resolution that raises instead of defaulting. The registry names where each one lives and the tests resolve
every citation, so a requirement cannot be satisfied by describing it.

The eighth had no home at all:

    "Never require withdrawal permission."

That sentence was TRUE here -- no code in this repository has ever called a withdrawal endpoint -- and it was
**unasserted**, which is a different thing. A key minted with withdrawal rights would have worked exactly as
well as one without, and nothing would have said so. "We don't use it" is not the same claim as "it isn't
there", and only the second one survives a leaked key.

    import execution_safety as ES

    ES.assess("binance_spot", "demo")          # -> ("UNKNOWN", "...no apiRestrictions on testnet...")
    ES.assert_safe("binance_spot", "real")     # -> raises UnsafeKey: the scope was never read

Three states, and the middle one is the point:

* ``NO_WITHDRAWAL``      the provider reported the restrictions and withdrawals are off;
* ``WITHDRAWAL_ENABLED`` the provider reported that this key may withdraw -- refused in EVERY environment,
  including demo, because the fact worth refusing is what the key can do, not what this run intends;
* ``UNKNOWN``            unread, or unreadable. It refuses in `real` and is recorded-but-allowed in demo,
  because Binance publishes `apiRestrictions` only on the mainnet SPOT host -- a testnet key genuinely cannot
  be probed, and a testnet key genuinely cannot move real funds.

``UNKNOWN`` never reads as ``NO_WITHDRAWAL``. That is the same three-valued rule §20 applies to data and §38
applies to research, arriving at the last place it was missing.

Reading the scope is a deliberate, separate act: ``scripts/binance-testnet-order.sh api-restrictions`` signs
one request and writes ``data/live/key-scope.json``. Nothing here reaches the network.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "docs", "architecture", "execution-safety.json")

NO_WITHDRAWAL = "NO_WITHDRAWAL"
WITHDRAWAL_ENABLED = "WITHDRAWAL_ENABLED"
UNKNOWN = "UNKNOWN"
STATES = (NO_WITHDRAWAL, WITHDRAWAL_ENABLED, UNKNOWN)


class RegistryError(ValueError):
    """docs/architecture/execution-safety.json says something §51 does not allow."""


class UnsafeKey(RuntimeError):
    """A credential this platform refuses to trade with."""


def _load(path=None):
    data = json.load(open(path or PATH, encoding="utf-8"))
    ids = [r["id"] for r in data["requirements"]]
    if len(set(ids)) != len(ids):
        raise RegistryError("duplicate requirement id")
    for r in data["requirements"]:
        if "::" not in str(r.get("enforced_by") or ""):
            raise RegistryError(
                f"{r['id']!r} names no enforcer -- CLAUDE.md §51 is a list of things that must be true at run "
                f"time, and a requirement whose `enforced_by` is prose is a requirement nothing holds.")
        if not str(r.get("how") or "").strip():
            raise RegistryError(f"{r['id']!r} does not say how")
    ks = data["key_scope"]
    if set(ks["states"]) != set(STATES):
        raise RegistryError(f"key_scope states must be exactly {list(STATES)}")
    if "NOT safe" not in ks["states"][UNKNOWN] and "NOT healthy" not in ks["states"][UNKNOWN]:
        raise RegistryError(
            "UNKNOWN must be declared NOT safe. An unread key scope that reads as 'no withdrawal permission' "
            "is the exact silent downgrade CLAUDE.md §20 forbids for data and §51 forbids for credentials.")
    if not ks["refusal_environments"]:
        raise RegistryError(
            "no environment refuses an unread scope -- §51: 'Never assume mainnet API credentials are safe.' "
            "An empty refusal list makes UNKNOWN indistinguishable from NO_WITHDRAWAL wherever it matters.")
    return data


_DATA = _load()

REQUIREMENTS = tuple(r["id"] for r in _DATA["requirements"])
REFUSAL_ENVIRONMENTS = tuple(_DATA["key_scope"]["refusal_environments"])
SCOPE_PATH = os.path.join(ROOT, _DATA["key_scope"]["probe"]["record"])
PROBE = dict(_DATA["key_scope"]["probe"])


def requirement(rid):
    for r in _DATA["requirements"]:
        if r["id"] == rid:
            return r
    raise KeyError(rid)


def spec_lines():
    return [r["spec"] for r in _DATA["requirements"]]


def read_scope(path=None):
    """The recorded key-scope readings, or {} when none was ever taken. Never raises: an unreadable record is
    the same fact as no record, and both are UNKNOWN."""
    p = path or SCOPE_PATH
    try:
        d = json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d.get("keys") or {}


def assess(provider, environment, *, scope=None, path=None):
    """(state, why) for this provider's credential in this environment.

    `scope` lets a caller pass a reading directly (a test, or a probe's own output) instead of the record.
    """
    rec = scope if scope is not None else read_scope(path).get(provider)
    if rec is None:
        return UNKNOWN, (f"no key-scope reading for {provider!r}; run `{PROBE['command']}` to take one "
                         f"({PROBE['endpoint']} exists only on the mainnet host, so a testnet key cannot be "
                         f"probed at all)")
    if rec.get("unavailable"):
        return UNKNOWN, f"{provider!r} could not report its key restrictions: {rec.get('why') or 'no reason given'}"
    val = rec.get(PROBE["field"])
    if val is True:
        return WITHDRAWAL_ENABLED, (f"{provider!r}'s API key has {PROBE['field']}=true (read "
                                    f"{rec.get('checked_at') or 'at an unrecorded time'})")
    if val is False:
        return NO_WITHDRAWAL, (f"{provider!r}'s API key has {PROBE['field']}=false (read "
                               f"{rec.get('checked_at') or 'at an unrecorded time'})")
    return UNKNOWN, f"{provider!r}'s reading carries no {PROBE['field']!r} field"


def assert_safe(provider, environment, *, scope=None, path=None):
    """Raise unless this credential may be traded with. Returns (state, why) when it may.

    WITHDRAWAL_ENABLED refuses everywhere -- including demo. The thing being refused is what the KEY can do,
    and a key that can move funds is not made safe by the intentions of the run that holds it.
    """
    state, why = assess(provider, environment, scope=scope, path=path)
    if state == WITHDRAWAL_ENABLED:
        raise UnsafeKey(
            f"refusing to trade with {provider!r}: {why}. CLAUDE.md §51: never require withdrawal permission "
            f"-- mint a key with withdrawals disabled. This refusal applies in every environment, because the "
            f"risk is what the key can do, not what this run intends to do with it.")
    if state == UNKNOWN and environment in REFUSAL_ENVIRONMENTS:
        raise UnsafeKey(
            f"refusing to trade with {provider!r} in environment {environment!r}: {why}. CLAUDE.md §51: never "
            f"assume mainnet API credentials are safe -- an unread scope is unread, it is not 'no withdrawal "
            f"permission'.")
    return state, why


def gate_reason(provider, environment, *, scope=None, path=None):
    """The refusal sentence for a stop-only gate, or None. Same rule as `assert_safe`, without the exception --
    the pilot's tick gate can only stop a tick, so it takes a reason rather than an raise."""
    try:
        assert_safe(provider, environment, scope=scope, path=path)
    except UnsafeKey as e:
        return str(e)
    return None


def record(provider, *, enable_withdrawals=None, checked_at=None, unavailable=None, why=None, path=None):
    """Write one reading into the record. The probe's writer; nothing on a decision path calls this."""
    p = path or SCOPE_PATH
    try:
        doc = json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        doc = {}
    keys = doc.setdefault("keys", {})
    rec = {"checked_at": checked_at}
    if unavailable:
        rec.update(unavailable=True, why=why)
    else:
        rec[PROBE["field"]] = enable_withdrawals
    keys[provider] = rec
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    json.dump(doc, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return rec


def describe(environment=None):
    env = environment or "demo"
    lines = [f"§51 execution safety: {len(REQUIREMENTS)} requirement(s); "
             f"unread key scope refuses in {list(REFUSAL_ENVIRONMENTS)}"]
    for r in _DATA["requirements"]:
        lines.append(f"  {r['id']:<26} {r['enforced_by']}")
    for pid in ("binance_spot", "binance_futures", "mt5_bridge"):
        st, why = assess(pid, env)
        lines.append(f"  key scope {pid:<17} {st}  -- {why}")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="CLAUDE.md §51 execution safety.")
    ap.add_argument("--env", default="demo")
    a = ap.parse_args()
    print(describe(a.env))
