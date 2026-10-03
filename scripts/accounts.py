#!/usr/bin/env python3
"""Accounts and their Trading System assignments (ADR 0010). The registry is docs/architecture/accounts.json; the reader
and validator is scripts/registry.py.

    python3 scripts/accounts.py list
    python3 scripts/accounts.py status   [--account ID]
    python3 scripts/accounts.py validate
    python3 scripts/accounts.py switch   --account ID --to fvg-book@v3 --reason "..." [--policy DRAIN|CLOSE|BLOCK] [--at ISO]

`switch` ENDS the account's live assignment and appends a new one, effective at the next 5-minute decision slot unless
--at says otherwise; nothing already in the file is rewritten except that one `ended_at`. The new file is validated in
full before it replaces the old one, so a switch to a DRAFT or unknown version, to another market, or to a component the
account cannot trade is refused and nothing changes. Policies (what happens to positions the old assignment opened):
DRAIN (default) keeps them to their own exits, CLOSE closes them at the next tick, BLOCK refuses the switch while any is
open. Demo accounts only: the registry holds no real-money account, and one would be switched by a reviewed PR (§41, §51).
After a switch, commit docs/architecture/accounts.json -- the file in git is the record of what each account ran."""
import argparse
import datetime
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import registry as R  # noqa: E402

ACCOUNTS_DIR = os.path.join(ROOT, "data", "live", "accounts")
SLOT = datetime.timedelta(minutes=5)


class SwitchRefused(ValueError):
    pass


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def next_slot(now):
    """The next 5-minute decision slot strictly after `now` -- a switch never takes effect inside a running tick."""
    base = now.replace(minute=now.minute - now.minute % 5, second=0, microsecond=0)
    return base + SLOT


def open_book(account_id, accounts_dir=ACCOUNTS_DIR):
    """(pending, open) records in the account's executor state; ([], []) when it has none."""
    p = os.path.join(accounts_dir, account_id, "state.json")
    if not os.path.exists(p):
        return [], []
    with open(p, encoding="utf-8") as fh:
        st = json.load(fh)
    return st.get("pending", []), st.get("open", [])


def plan_switch(data, account_id, target, reason, policy=None, at=None, now=None, accounts_dir=ACCOUNTS_DIR):
    """The registry document after the switch (a new dict; `data` is untouched). Raises SwitchRefused."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    policy = policy or data["default_open_position_policy"]
    if policy not in data["open_position_policies"]:
        raise SwitchRefused(f"policy {policy!r} is not one of {data['open_position_policies']}")
    if not reason or not reason.strip():
        raise SwitchRefused("a switch needs a --reason: the assignment history is the record of why an account changed")
    if "@" not in target:
        raise SwitchRefused(f"--to {target!r} must be <trading_system>@<version>, e.g. fvg-book@v2")
    system, version = target.split("@", 1)
    acc = (data.get("accounts") or {}).get(account_id)
    if acc is None:
        raise SwitchRefused(f"no account {account_id!r}")
    if acc.get("real_money") is not False:
        raise SwitchRefused(f"{account_id} is not a demo account; a real-money account is switched by a reviewed PR")
    effective = R._parse(at) if at else next_slot(now)
    if effective < now:
        raise SwitchRefused(f"--at {at} is in the past; a switch never rewrites what an account already ran (§8)")
    rows = [dict(r) for r in data.get("assignments") or []]
    mine = [r for r in rows if r["account"] == account_id]
    if any(R._parse(r["effective_from"]) > now for r in mine):
        raise SwitchRefused(f"{account_id} already has a pending assignment; one switch at a time")
    live = R.active_assignment(account_id, effective, rows)
    if live and (live["trading_system"], live["version"]) == (system, version):
        raise SwitchRefused(f"{account_id} already runs {target} ({live['id']})")
    if policy == "BLOCK":
        pending, opened = open_book(account_id, accounts_dir)
        if pending or opened:
            raise SwitchRefused(f"policy BLOCK: {account_id} has {len(pending)} pending order(s) and {len(opened)} open "
                                f"position(s); switch again when they are closed, or use DRAIN / CLOSE")
    if live:
        live["ended_at"] = _iso(effective)
    nums = [int(r["id"].split("-")[-1]) for r in rows if r["id"].split("-")[-1].isdigit()]
    rows.append({"id": f"asg-{max(nums, default=0) + 1:04d}", "account": account_id, "trading_system": system,
                 "version": version, "effective_from": _iso(effective), "ended_at": None, "open_position_policy": policy,
                 "requested_by": "accounts.py switch", "reason": reason.strip()})
    out = dict(data, assignments=rows)
    return out


def write_validated(doc, path=R.ACCOUNTS_PATH):
    """Validate the whole new document, then replace the file atomically. Nothing is written when validation fails."""
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        try:
            R.validate(accounts_path=tmp)
        except R.RegistryError as e:
            raise SwitchRefused(str(e).replace(tmp, path)) from None
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def cmd_list():
    for a in R.ACCOUNTS.values():
        live = R.active_assignment(a["id"])
        ts = f"{live['trading_system']}@{live['version']}" if live else "-"
        print(f"{a['id']:<22} {a['market']:<7} {a['broker']:<16} {a['state']:<7} {ts}")


def cmd_status(account_id=None):
    for aid in [account_id] if account_id else list(R.ACCOUNTS):
        a = R.account(aid)
        live = R.active_assignment(aid)
        pending, opened = open_book(aid)
        stop = os.path.exists(os.path.join(ACCOUNTS_DIR, aid, "STOP"))
        print(f"{aid}: {a['market']} via {a['broker']} ({a.get('broker_server', '-')}), state {a['state']}"
              f"{', STOP' if stop else ''}")
        print(f"  live: {live['trading_system']}@{live['version']} since {live['effective_from']} ({live['id']})"
              if live else "  live: none -- no new entries")
        by = {}
        for rec in pending + opened:
            by[rec.get("assignment")] = by.get(rec.get("assignment"), 0) + 1
        print(f"  pending {len(pending)}, open {len(opened)}" + (f"  by assignment {by}" if by else ""))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    s = sub.add_parser("status")
    s.add_argument("--account")
    sub.add_parser("validate")
    w = sub.add_parser("switch")
    w.add_argument("--account", required=True)
    w.add_argument("--to", required=True, help="<trading_system>@<version>")
    w.add_argument("--reason", required=True)
    w.add_argument("--policy", choices=R.POLICIES)
    w.add_argument("--at", help="ISO time the switch takes effect (default: the next 5-minute slot)")
    a = ap.parse_args(argv)
    if a.cmd == "list":
        cmd_list()
    elif a.cmd == "status":
        cmd_status(a.account)
    elif a.cmd == "validate":
        R.validate()
        print("registry OK")
    else:
        with open(R.ACCOUNTS_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        try:
            doc = plan_switch(data, a.account, a.to, a.reason, a.policy, a.at)
            write_validated(doc)
        except SwitchRefused as e:
            print(f"REFUSED: {e}")
            return 2
        new = doc["assignments"][-1]
        print(f"{a.account}: {new['trading_system']}@{new['version']} from {new['effective_from']} ({new['id']}, "
              f"{new['open_position_policy']}). Commit docs/architecture/accounts.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
