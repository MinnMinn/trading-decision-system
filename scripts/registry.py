"""THE reader of the account registry (docs/architecture/accounts.json) and the book setups
(docs/architecture/setups.json), and the cross-registry validator that joins them to the rest (ADR 0010).

    import registry as R

    R.account("ftmo-demo-01")                       -> the account row (+ "id")
    R.accounts(market="cfd", state="ACTIVE")        -> [rows]
    R.active_assignment("ftmo-demo-01", at)         -> the assignment live at `at`, or None
    R.resolve("ftmo-demo-01", at)                   -> {"account", "assignment", "system"}  (system = the version)
    R.setup("E5")                                   -> the setup row

Model (the owner's decision 2026-10-03, ADR 0010): an account trades ONE market through ONE broker under ONE
account profile, and runs at most ONE Trading System version at a time -- the one its live assignment names.
The registries this joins keep their own single sources: markets and the allowlist (instruments.json), brokers
and their capabilities (providers.json), fund rules (account-profiles.json), Trading Systems and their versions
(trading-systems.json via scripts/trading_system.py), the risk ceiling (risk-config.json via trading_env).

Everything is validated at import. A broken registry stops the process that imports it -- the executor never
starts on a configuration that does not hold together (CLAUDE.md §6, §15: no silent fallback, no silent switch).
"""
import datetime
import importlib.util
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import account_profile as AP  # noqa: E402
import instruments as I  # noqa: E402
import providers as P  # noqa: E402
import trading_system as TS  # noqa: E402

ACCOUNTS_PATH = os.path.join(ROOT, "docs", "architecture", "accounts.json")
SETUPS_PATH = os.path.join(ROOT, "docs", "architecture", "setups.json")

_ENV_VAR = re.compile(r"^[A-Z][A-Z0-9_]*$")
# A literal that looks like an API key or secret. accounts.json carries the NAMES of environment variables,
# never their values; this is the tripwire for the day someone pastes a key into it (CLAUDE.md §51).
_SECRET_LIKE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9+/=_-]{40,}(?![A-Za-z0-9])")


class RegistryError(ValueError):
    """The registry is inconsistent -- raised at import or by validate(), never mid-decision."""


def _parse(ts):
    if ts is None:
        return None
    return datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _public(d):
    return {k: v for k, v in d.items() if not k.startswith("_")}


# --------------------------------------------------------------------------- setups
def _rule_exists(ref):
    """`rule_ref` names one or more `<path> <function>` pairs separated by ';'. Each must exist, so a setup
    cannot name a definition that was renamed or deleted."""
    for part in ref.split(";"):
        bits = part.split()
        if len(bits) != 2:
            return False, f"{part.strip()!r} is not '<path> <function>'"
        path, fn = bits
        full = os.path.join(ROOT, path)
        if not os.path.isfile(full):
            return False, f"{path} does not exist"
        with open(full, encoding="utf-8") as fh:
            src = fh.read()
        if not re.search(rf"^def {re.escape(fn)}\(", src, re.M):
            return False, f"{path} defines no {fn}()"
    return True, ""


def validate_setups(data, path=SETUPS_PATH):
    statuses = tuple(data.get("evidence_statuses") or ())
    meths = _public(data.get("methodologies") or {})
    setups = _public(data.get("setups") or {})
    if not setups:
        raise RegistryError(f"{path}: no setups")
    for sid, s in setups.items():
        where = f"{path}: setup {sid!r}"
        if s.get("methodology") not in meths:
            raise RegistryError(f"{where}: methodology {s.get('methodology')!r} is not declared in {sorted(meths)}")
        if not str(s.get("version") or "").strip():
            raise RegistryError(f"{where}: no version")
        ok, why = _rule_exists(str(s.get("rule_ref") or ""))
        if not ok:
            raise RegistryError(f"{where}: rule_ref -- {why}")
        ev = s.get("evidence") or {}
        if not ev:
            raise RegistryError(f"{where}: no per-instrument evidence")
        for sym, st in ev.items():
            if st not in statuses:
                raise RegistryError(f"{where}: evidence {sym}={st!r} is not one of {list(statuses)}")
            if sym not in I.ALL_ANALYSIS:
                raise RegistryError(f"{where}: evidence names {sym!r}, which is not on the analysis allowlist "
                                    f"(docs/architecture/instruments.json)")
        if not isinstance(s.get("params"), list):
            raise RegistryError(f"{where}: params must be a list of parameter names")
    return setups


# --------------------------------------------------------------------------- accounts
def _execution_brokers():
    return {pid: p for pid, p in P.PROVIDERS.items() if "execution" in (p.get("roles") or [])}


def _components_ok(acc_id, acc, version, setups, where):
    """An assignment's components must be tradeable BY THIS ACCOUNT: a declared setup whose evidence on the
    instrument is VALIDATED (for an APPROVED version), the instrument on the market's execution allowlist, and
    a broker spelling for it when the account declares a symbol map."""
    to_broker = None
    if acc.get("symbol_map"):
        sm = _read(os.path.join(ROOT, acc["symbol_map"]))
        to_broker = {canon: broker for broker, canon in sm["map"].items()}
    for c in version["components"]:
        s = setups.get(c["setup"])
        if s is None:
            raise RegistryError(f"{where}: component setup {c['setup']!r} is not in {SETUPS_PATH}")
        unknown = sorted(set(c["params"]) - set(s["params"]))
        if unknown:
            raise RegistryError(f"{where}: component {c['setup']}/{c['instrument']} has params {unknown} the "
                                f"setup does not declare ({s['params']})")
        if version["status"] == "APPROVED" and s["evidence"].get(c["instrument"]) != "VALIDATED":
            raise RegistryError(f"{where}: {c['setup']} on {c['instrument']} is "
                                f"{s['evidence'].get(c['instrument'], 'not evidenced')!r}, and an APPROVED version "
                                f"may only hold VALIDATED components ({SETUPS_PATH})")
        if c["instrument"] not in I.EXECUTION[acc["market"]]:
            raise RegistryError(f"{where}: {c['instrument']} is not on the {acc['market']} EXECUTION allowlist "
                                f"(docs/architecture/instruments.json)")
        if to_broker is not None and c["instrument"] not in to_broker:
            raise RegistryError(f"{where}: account {acc_id!r} symbol map {acc['symbol_map']} has no broker "
                                f"symbol for {c['instrument']}")


def validate_accounts(data, setups, path=ACCOUNTS_PATH):
    states = tuple(data.get("states") or ())
    policies = tuple(data.get("open_position_policies") or ())
    if data.get("default_open_position_policy") not in policies:
        raise RegistryError(f"{path}: default_open_position_policy must be one of {list(policies)}")
    owners = _public(data.get("owners") or {})
    accounts = _public(data.get("accounts") or {})
    brokers = _execution_brokers()
    raw = json.dumps(data, ensure_ascii=False)
    if _SECRET_LIKE.search(raw):
        raise RegistryError(f"{path}: contains a literal that looks like a key or secret. Store the NAME of an "
                            f"environment variable in credential_ref, never its value (CLAUDE.md §51).")
    channels = {}
    for aid, a in accounts.items():
        where = f"{path}: account {aid!r}"
        for f in ("owner", "market", "broker", "account_profile", "environment", "state", "created_at"):
            if a.get(f) in (None, ""):
                raise RegistryError(f"{where}: no {f!r}")
        if a["owner"] not in owners:
            raise RegistryError(f"{where}: owner {a['owner']!r} is not in owners {sorted(owners)}")
        if a["market"] not in I.MARKETS:
            raise RegistryError(f"{where}: market {a['market']!r} is not one of {I.MARKETS}")
        if a["state"] not in states:
            raise RegistryError(f"{where}: state {a['state']!r} is not one of {list(states)}")
        b = brokers.get(a["broker"])
        if b is None:
            raise RegistryError(f"{where}: broker {a['broker']!r} is not an execution provider in "
                                f"{P.PATH} ({sorted(brokers)})")
        if a["market"] not in (b.get("markets") or []):
            raise RegistryError(f"{where}: broker {a['broker']!r} does not serve market {a['market']!r} "
                                f"(its markets: {b.get('markets')}) -- capabilities are declared, never assumed (§6)")
        try:
            prof = AP.for_account(a["account_profile"], venue=b.get("execution_alias"), environment=a["environment"])
        except (KeyError, ValueError) as e:
            raise RegistryError(f"{where}: account_profile -- {e}") from None
        if a.get("real_money") is not False:
            raise RegistryError(
                f"{where}: real_money must be false. No real-money account is enabled on this platform; enabling "
                f"one is an explicit owner decision recorded in an ADR, never a registry edit (CLAUDE.md §51).")
        if a["environment"] != "demo":
            raise RegistryError(f"{where}: environment {a['environment']!r} -- only demo accounts are declared "
                                f"while real_money is false")
        ref = a.get("credential_ref")
        if ref is not None and not _ENV_VAR.match(str(ref)):
            raise RegistryError(f"{where}: credential_ref {ref!r} must be an environment-variable NAME")
        if a.get("symbol_map") and not os.path.isfile(os.path.join(ROOT, a["symbol_map"])):
            raise RegistryError(f"{where}: symbol_map {a['symbol_map']} does not exist")
        ib = a.get("initial_balance")
        if ib is not None and not (isinstance(ib, (int, float)) and ib > 0):
            raise RegistryError(f"{where}: initial_balance must be a positive number or null")
        if b.get("execution_alias") == "mt5":
            ch = a.get("bridge_channel")
            if not ch:
                raise RegistryError(f"{where}: an MT5 account needs a bridge_channel (the EA's InpBridgeDir)")
            if a["state"] != "ENDED":
                if ch in channels:
                    raise RegistryError(f"{where}: bridge_channel {ch!r} is already used by {channels[ch]!r}; one "
                                        f"terminal serves one account, so two accounts on one channel would see "
                                        f"each other's fills")
                channels[ch] = aid
        lref = a.get("login_ref")
        if lref is not None and not _ENV_VAR.match(str(lref)):
            raise RegistryError(f"{where}: login_ref {lref!r} must be an environment-variable NAME")
        a["id"], a["profile"] = aid, prof
    if len(channels) > 1:
        unchecked = sorted(aid for aid in channels.values() if not accounts[aid].get("login_ref"))
        if unchecked:
            raise RegistryError(f"{path}: {len(channels)} live MT5 accounts share this machine's terminals, and "
                                f"{unchecked} declare no login_ref -- each must name the environment variable holding "
                                f"its login, so a terminal on the wrong account refuses instead of trading")

    seen, by_account = set(), {}
    for row in data.get("assignments") or []:
        rid = row.get("id")
        where = f"{path}: assignment {rid!r}"
        if not rid or rid in seen:
            raise RegistryError(f"{where}: missing or duplicate id")
        seen.add(rid)
        acc = accounts.get(row.get("account"))
        if acc is None:
            raise RegistryError(f"{where}: account {row.get('account')!r} is not declared")
        if row.get("open_position_policy") not in policies:
            raise RegistryError(f"{where}: open_position_policy must be one of {list(policies)}")
        try:
            market = TS.market_of(row.get("trading_system"), row.get("version"))
        except KeyError as e:
            raise RegistryError(f"{where}: {e}") from None
        if market != acc["market"]:
            raise RegistryError(f"{where}: {row['trading_system']}@{row['version']} trades {market!r} but account "
                                f"{acc['id']!r} trades {acc['market']!r} -- one account, one market")
        start, end = _parse(row.get("effective_from")), _parse(row.get("ended_at"))
        if start is None:
            raise RegistryError(f"{where}: no effective_from")
        if end is not None and end <= start:
            raise RegistryError(f"{where}: ended_at must be after effective_from")
        if row["trading_system"] in TS.BOOKS:
            v = TS.book(row["trading_system"], row["version"])
            if v["status"] == "DRAFT":
                raise RegistryError(f"{where}: {v['id']} is a DRAFT; only an APPROVED version may be assigned")
            if v["status"] == "RETIRED" and end is None:
                raise RegistryError(f"{where}: {v['id']} is RETIRED and cannot be the live assignment")
            _components_ok(acc["id"], acc, v, setups, where)
        by_account.setdefault(acc["id"], []).append((start, end, rid))
    for aid, spans in by_account.items():
        spans.sort(key=lambda x: x[0])
        for (s0, e0, r0), (s1, _e1, r1) in zip(spans, spans[1:]):
            if e0 is None or e0 > s1:
                raise RegistryError(f"{path}: assignments {r0!r} and {r1!r} of account {aid!r} overlap -- at most "
                                    f"one Trading System version is live per account (ADR 0010)")
    return owners, accounts


def _load(accounts_path=ACCOUNTS_PATH, setups_path=SETUPS_PATH):
    setups = validate_setups(_read(setups_path), setups_path)
    data = _read(accounts_path)
    owners, accounts = validate_accounts(data, setups, accounts_path)
    return data, owners, accounts, setups


_DATA, OWNERS, ACCOUNTS, SETUPS = _load()
ASSIGNMENTS = list(_DATA.get("assignments") or [])
STATES = tuple(_DATA["states"])
POLICIES = tuple(_DATA["open_position_policies"])
DEFAULT_POLICY = _DATA["default_open_position_policy"]


# --------------------------------------------------------------------------- lookup
def account(account_id):
    if account_id not in ACCOUNTS:
        raise KeyError(f"no account {account_id!r} in {ACCOUNTS_PATH}; declared: {sorted(ACCOUNTS)}")
    return ACCOUNTS[account_id]


def accounts(market=None, state=None, broker=None):
    return [a for a in ACCOUNTS.values()
            if (market is None or a["market"] == market) and (state is None or a["state"] == state)
            and (broker is None or a["broker"] == broker)]


def setup(setup_id):
    if setup_id not in SETUPS:
        raise KeyError(f"no setup {setup_id!r} in {SETUPS_PATH}; declared: {sorted(SETUPS)}")
    return SETUPS[setup_id]


def assignments(account_id, rows=None):
    """Every assignment of the account, oldest first."""
    rows = ASSIGNMENTS if rows is None else rows
    return sorted((r for r in rows if r["account"] == account_id), key=lambda r: _parse(r["effective_from"]))


def active_assignment(account_id, at=None, rows=None):
    """The assignment live at `at` (effective_from <= at < ended_at), or None. Point-in-time: a switch recorded
    later never changes what was live earlier (CLAUDE.md §8)."""
    at = at or _now()
    for r in assignments(account_id, rows):
        end = _parse(r.get("ended_at"))
        if _parse(r["effective_from"]) <= at and (end is None or at < end):
            return r
    return None


def assignment(assignment_id, rows=None):
    for r in (ASSIGNMENTS if rows is None else rows):
        if r["id"] == assignment_id:
            return r
    raise KeyError(f"no assignment {assignment_id!r} in {ACCOUNTS_PATH}")


def system_of(row):
    """The Trading System version an assignment names: a book version dict, or a style system dict."""
    if row["trading_system"] in TS.BOOKS:
        return TS.book(row["trading_system"], row["version"])
    return TS.get(row["trading_system"])


def resolve(account_id, at=None):
    """{"account", "assignment", "system"} for the account at `at`; assignment/system None when nothing is live."""
    a = account(account_id)
    row = active_assignment(account_id, at)
    return {"account": a, "assignment": row, "system": system_of(row) if row else None}


def validate(accounts_path=ACCOUNTS_PATH, setups_path=SETUPS_PATH):
    """Re-run every check against the files on disk (the CLI's `validate`, and the tests)."""
    _load(accounts_path, setups_path)
    return True
