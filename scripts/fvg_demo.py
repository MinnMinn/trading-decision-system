#!/usr/bin/env python3
"""Forward DEMO executor for book Trading Systems, one ACCOUNT per call (ADR 0010). What an account trades is the book
version its live assignment names (docs/architecture/accounts.json -> docs/architecture/trading-systems.json `books`):
today fvg-book v2 = E5 FVG retrace (XAUUSD 24 bars, US500 48 bars), H7 and G9 on XAUUSD (to the rollover), 1 % per trade
under the dd3 drawdown throttle. DEMO ONLY.

    python3 scripts/fvg_demo.py tick   [--account ID]   # one pass per account: place / cancel / close (every 1-5 minutes)
    python3 scripts/fvg_demo.py status [--account ID]   # open orders, positions and the paired comparison so far

Without --account, every non-ENDED account on the MT5 broker is ticked, each in isolation. Each account has its own state,
event log and kill switch under data/live/accounts/<id>/ and its own bridge channel (the EA's InpBridgeDir).

What it trades is exactly what the research measured (scripts/research/edge_census.py `fvg_gap_at`, the ONE definition):
a displacement FVG known at the close of its third bar -> a LIMIT at the gap's near edge, protective stop 2 x sigma_5m x
sqrt(h), the time exit after h bars, flat before the broker rollover; one trade per (symbol, server day, side), the first
filled. Every fill and exit is logged next to the intended price, so implementation shortfall (fill vs edge, exit vs bar
close) is measured per trade -- the paired comparison of docs/plans/2026-10-02-edge-followup-preregistration.md §4.

Safety (CLAUDE.md §51, all fail closed): new entries only for an ACTIVE account with a live assignment to an APPROVED
version and no STOP file (data/live/STOP or the account's own); the registry refuses real_money accounts; the bridge must report
trade_mode "demo" (the EA also refuses non-demo, InpDemoOnly); symbols must be on the cfd EXECUTION allowlist
(docs/architecture/instruments.json, re-checked by scripts/mt5-order-bridge.py and the EA); risk per trade <= max_risk_pct;
every order carries its stop at placement; no new entry inside an event-risk window or when the calendar is unavailable
(scripts/event_risk.py, §24-§32); no new entry on stale bars (§20/§52). Open positions are only ever CLOSED by this script,
never added to or widened. Positions opened under an earlier assignment keep the exits they were opened with (DRAIN), or
are closed at the next tick when the assignment that replaced theirs says CLOSE.

Every pending order, position and log line carries the account, the assignment and the Trading System version, so a trade
is always attributable to the version that opened it (CLAUDE.md §47)."""
import argparse
import datetime
import importlib.util
import json
import math
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
_spec = importlib.util.spec_from_file_location("fvg_forward", os.path.join(ROOT, "scripts", "research", "fvg_forward.py"))
FF = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(FF)
EC = FF.EC

ACCOUNTS_DIR = os.path.join(ROOT, "data", "live", "accounts")
GLOBAL_STOP = os.path.join(ROOT, "data", "live", "STOP")
# Where the single-account executor kept its files until 2026-10-03; moved once into the account that owns the legacy
# bridge channel (migrate_legacy), then never read again.
LEGACY_STATE = os.path.join(ROOT, "data", "live", "forward", "fvg-demo-state.json")
LEGACY_LOG = os.path.join(ROOT, "data", "live", "forward", "fvg-demo.jsonl")
LEGACY_CHANNEL = "bridge"
BAR = datetime.timedelta(minutes=5)
import providers as P  # noqa: E402  (connector paths come from docs/architecture/providers.json, never hard-coded)
import registry as R  # noqa: E402
import trading_env  # noqa: E402
BRIDGE_ADAPTER = P.adapter("mt5_bridge")
BROKER = "mt5_bridge"


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


class Bridge:
    """scripts/mt5-order-bridge.py as a function (the tests pass a fake with the same `__call__`)."""

    def __init__(self, subdir):
        self.env = dict(os.environ, MT5_BRIDGE_SUBDIR=subdir)

    def __call__(self, *args):
        r = subprocess.run([sys.executable, BRIDGE_ADAPTER, *map(str, args)],
                           capture_output=True, text=True, env=self.env)
        out = r.stdout.strip() or r.stderr.strip()
        try:
            d = json.loads(out) if out else {}
        except json.JSONDecodeError:
            d = {"ok": False, "comment": out[:300]}
        if r.returncode != 0:
            d.setdefault("ok", False)
        return d


def account_paths(account_id):
    d = os.path.join(ACCOUNTS_DIR, account_id)
    return {"state_path": os.path.join(d, "state.json"), "log_path": os.path.join(d, "events.jsonl"),
            "stop_path": os.path.join(d, "STOP")}


def config_for(system, account, assignment=None):
    """The executor's configuration for one book version on one account. Everything that decides a trade comes from
    the version (immutable, §47); the account contributes only where it trades (bridge channel) and the balance its
    throttle keys off. Risk is clamped to the platform ceiling (risk-config.json max_risk_pct via trading_env)."""
    comps = system["components"]
    risk = system["risk"]
    return {
        "enabled": True,
        "trading_system": system["id"],
        "assignment": assignment["id"] if assignment else None,
        "account": account["id"],
        "risk_pct": min(float(risk["risk_pct"]), float(trading_env.MAX_RISK_PCT)),
        "components": {c["instrument"]: int(c["params"]["hold_bars"]) for c in comps if c["setup"] == "E5"},
        "h7_symbols": [c["instrument"] for c in comps if c["setup"] == "H7"],
        "g9_symbols": [c["instrument"] for c in comps if c["setup"] == "G9"],
        "throttle": {"kind": risk["throttle"], "initial_balance": account.get("initial_balance")},
        "bridge_subdir": account["bridge_channel"],
        "login_ref": account.get("login_ref"),
        **{k: system["execution"][k] for k in ("max_bar_age_minutes", "close_before_rollover_minutes", "tp_stop_multiple")},
    }


def _closing_assignments(account_id, now):
    """Assignments whose positions must be closed now: each one replaced by an assignment (effective by `now`) whose
    open_position_policy is CLOSE. Derived from the registry, so a switch never has to write into the runtime state."""
    rows = R.assignments(account_id)
    out = set()
    for prev, nxt in zip(rows, rows[1:]):
        if nxt.get("open_position_policy") == "CLOSE" and R._parse(nxt["effective_from"]) <= now:
            out.add(prev["id"])
    return out


def resolve(account_id, now):
    """(cfg, why_no_entries) for the account at `now`. cfg is None when the account has never had an assignment; it is
    the last assignment's config with enabled=False when new entries are not allowed, so open positions are still
    managed to their exits."""
    acc = R.account(account_id)
    if acc["broker"] != BROKER:
        raise ValueError(f"account {account_id!r} is on broker {acc['broker']!r}; this executor drives {BROKER!r} only")
    row = R.active_assignment(account_id, now)
    why = None
    if row is None:
        past = [r for r in R.assignments(account_id) if R._parse(r["effective_from"]) <= now]
        if not past:
            return None, "no assignment"
        row, why = past[-1], "no live assignment"
    system = R.system_of(row)
    if "components" not in system:
        raise ValueError(f"assignment {row['id']} names {row['trading_system']!r}, which is not a book; this executor "
                         f"runs book Trading Systems only")
    cfg = config_for(system, acc, row)
    paths = account_paths(account_id)
    if why is None and acc["state"] != "ACTIVE":
        why = f"account state {acc['state']}"
    if why is None and (os.path.exists(GLOBAL_STOP) or os.path.exists(paths["stop_path"])):
        why = "STOP file present"
    cfg["enabled"] = why is None
    cfg["close_assignments"] = sorted(_closing_assignments(account_id, now))
    return cfg, why


def migrate_legacy(account_id, state_path, log_path):
    """Once: move the single-account executor's state and log into the account that serves the legacy bridge channel,
    stamping each carried-over order/position with the assignment that was live when it was placed."""
    acc = R.account(account_id)
    if acc.get("bridge_channel") != LEGACY_CHANNEL or os.path.exists(state_path) or not os.path.exists(LEGACY_STATE):
        return False
    with open(LEGACY_STATE, encoding="utf-8") as fh:
        st = json.load(fh)
    for rec in st.get("pending", []) + st.get("open", []):
        at = rec.get("placed_at") or rec.get("filled_seen_at")
        row = R.active_assignment(account_id, _parse(at)) if at else None
        rec.setdefault("assignment", row["id"] if row else None)
        rec.setdefault("trading_system", f"{row['trading_system']}@{row['version']}" if row else None)
    _write_state(st, state_path)
    if os.path.exists(LEGACY_LOG) and not os.path.exists(log_path):
        os.replace(LEGACY_LOG, log_path)
    os.replace(LEGACY_STATE, LEGACY_STATE + ".migrated")
    log("migrated", log_path, account=account_id, source=LEGACY_STATE)
    return True


def _read_state(path):
    if not os.path.exists(path):
        return {"pending": [], "open": [], "done_keys": [], "placed_gaps": []}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _write_state(st, path):
    """Atomic: the temp file is closed (flushed) before it replaces the state."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(st, fh, indent=1)
    os.replace(tmp, path)


def log(kind, log_path, **kw):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a") as fh:
        fh.write(json.dumps(dict(kind=kind, at=_iso(datetime.datetime.now(datetime.timezone.utc)), **kw)) + "\n")


def closed_series(sym, now, live_dir=FF.LIVE_DIR):
    """The merged bars with every bar whose CLOSE is after `now` dropped (MT5 exports the forming bar)."""
    bars = [b for b in FF.merged_candles(sym, live_dir) if _parse(b["time"]) + BAR <= now]
    return EC.Series(sym, bars, FF._zone(), end="9999-12-31T00:00:00Z", sigma_every_day=True)


def server_day_end(t):
    """UTC instant of the next server midnight after `t` (the broker rollover)."""
    z = FF._zone()
    lt = t.astimezone(z)
    nxt = datetime.datetime.combine(lt.date() + datetime.timedelta(days=1), datetime.time(0), tzinfo=z)
    return nxt.astimezone(datetime.timezone.utc)


LOOKBACK_BARS = 6        # a late tick still sees a gap formed up to 30 min ago, if price has not touched it since


def new_gaps(s, sym, h):
    """Untouched gaps whose third bar is among the last LOOKBACK_BARS closed bars, inside their touch window and server day:
    ("gap", sym, third_bar_time, side, edge, stop_dist, server_day) or ("refused", sym, third_bar_time, side, reason)."""
    n, out = len(s.C), []
    for m in range(max(1, n - 1 - LOOKBACK_BARS), n - 1):
        g = EC.fvg_gap_at(s, m)
        if g is None or n - 1 > m + 1 + EC.FVG_TOUCH_BARS or s.sday[n - 1] != s.sday[m]:
            continue
        side, edge, _far = g
        touched = any((s.L[j] <= edge) if side > 0 else (s.H[j] >= edge) for j in range(m + 2, n))
        if touched:
            continue
        sig = s.sigma(m + 1)
        if not sig or not FF._vol_fresh(s, m + 1):
            out.append(("refused", sym, s.T[m + 1], side, "volatility history stale or missing"))
            continue
        out.append(("gap", sym, s.T[m + 1], side, edge, 2.0 * sig * math.sqrt(h) * edge, s.sday[m + 1].isoformat()))
    return out


def lots_for(info, balance, risk_pct, entry, stop):
    per_lot = abs(entry - stop) * float(info["tick_value"]) / float(info["tick_size"])
    if per_lot <= 0:
        return 0.0
    step = float(info["volume_step"])
    lots = int((balance * risk_pct / per_lot) / step) * step
    return round(min(lots, float(info["volume_max"])), 8)


def throttle_mult(cfg, balance, initial):
    """dd3 drawdown throttle (docs/audits/2026-10-02-pass-policy.md, v2): x1 above 97 % of the initial balance, x0.5 down to
    94 %, x0.25 below. It only ever LOWERS the configured risk; 'none' = x1."""
    kind = (cfg.get("throttle") or {}).get("kind", "none")
    if kind == "none":
        return 1.0
    if kind != "dd3":
        raise ValueError(f"unknown throttle {kind!r}")
    if not initial or initial <= 0:
        return 0.25                          # unknown reference: the most conservative step, never the full risk
    f = balance / initial
    return 1.0 if f > 0.97 else 0.5 if f > 0.94 else 0.25


def sizing(cfg, st, balance):
    """(risk_pct, sizing_balance): risk on the INITIAL balance (as the replay), throttled; the initial balance is the config's
    `throttle.initial_balance`, else the first balance this executor saw (kept in the state)."""
    initial = (cfg.get("throttle") or {}).get("initial_balance") or st.setdefault("initial_balance", balance or None)
    risk = min(float(cfg["risk_pct"]), float(cfg["risk_pct"]) * throttle_mult(cfg, balance, initial))
    return risk, (initial or balance)


def tick(now=None, bridge=None, cfg=None, state_path=None, log_path=None, live_dir=FF.LIVE_DIR, event_blocked=None,
         account_id=None):
    """One pass for one account. Production passes `account_id` and the configuration comes from the registry; the tests
    pass `cfg` and explicit paths."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if cfg is None:
        if account_id is None:
            raise ValueError("tick needs an account_id (or an explicit cfg)")
        paths = account_paths(account_id)
        state_path, log_path = state_path or paths["state_path"], log_path or paths["log_path"]
        migrate_legacy(account_id, state_path, log_path)
        cfg, why = resolve(account_id, now)
        if cfg is None:
            print(f"{account_id}: {why}: nothing done")
            return "disabled"
        if why:
            cfg = dict(cfg, disabled_reason=why)
    st = _read_state(state_path)
    if not cfg.get("enabled") and not (st["pending"] or st["open"]):
        print(f"{cfg.get('account') or 'fvg-demo'}: no new entries ({cfg.get('disabled_reason', 'disabled')}), nothing open")
        return "disabled"
    bridge = bridge or Bridge(cfg.get("bridge_subdir", "bridge"))
    if event_blocked is None:
        import event_risk as ER
        event_blocked = lambda sym, at: ER.blocked(sym, at=_iso(at))
    ping = bridge("check")
    if not ping.get("demo"):
        log("refused", log_path, account=cfg.get("account"), reason=f"bridge does not report a DEMO account: {ping}")
        print("REFUSED: not a demo account (or bridge unreachable)")
        return "refused"
    wrong = _wrong_terminal(cfg, bridge)
    if wrong:
        log("refused", log_path, account=cfg.get("account"), reason=wrong)
        print(f"REFUSED: {wrong}")
        return "refused"
    _manage(st, now, cfg, bridge, log_path)
    if not cfg.get("enabled"):
        _write_state(st, state_path)
        log("no_entries", log_path, account=cfg.get("account"), reason=cfg.get("disabled_reason", "disabled"))
        return "manage-only"
    balance = float(bridge("account").get("balance") or 0)
    risk, base = sizing(cfg, st, balance)
    if risk < float(cfg["risk_pct"]):
        log("throttled", log_path, balance=balance, initial_balance=base, risk_pct=risk, configured=cfg["risk_pct"])
    cfg = dict(cfg, risk_pct=risk)
    for sym, h in cfg["components"].items():
        _isolated(log_path, sym, "E5", _fvg_component, st, sym, h, now, cfg, bridge, base, log_path, live_dir, event_blocked)
    for kind, key in (("H7", "h7_symbols"), ("G9", "g9_symbols")):
        for sym in cfg.get(key, []):
            _isolated(log_path, sym, kind, _eod_breakout, st, kind, sym, now, cfg, bridge, base, log_path, live_dir,
                      event_blocked)
    _write_state(st, state_path)
    return "ok"


def _symbol_info(bridge, sym, log_path, component):
    """The bridge's contract data for `sym`, or None (logged) when it lacks what sizing needs -- e.g. the EA does not know the
    symbol under that name. Never sizes an order from a partial answer."""
    info = bridge("symbol", sym)
    need = ("tick_value", "tick_size", "volume_step", "volume_max")
    if not isinstance(info, dict) or any(info.get(k) in (None, "") for k in need):
        log("skip", log_path, symbol=sym, component=component, reason=f"no usable contract data from the bridge: {info}")
        return None
    return info


def _isolated(log_path, sym, component, fn, *args):
    """Run one symbol's component; an exception is logged and contained so one symbol never blocks the others or the
    state write (the open positions' exits were already managed before any entry logic runs)."""
    try:
        fn(*args)
    except Exception as e:      # noqa: BLE001 -- logged with its type; fails closed (no order on this symbol this tick)
        log("error", log_path, symbol=sym, component=component, error=f"{type(e).__name__}: {e}")


def data_ok(s, sym, now, cfg, log_path, component):
    """§20/§52 gate for a NEW entry: the latest closed bar is fresh AND the bars the decision reads (the last
    FF.HOLE_LOOKBACK) have no hole. A hole means the previous day's range, the momentum and sigma would be computed on the wrong
    days -- WAIT, never trade through it."""
    if not s.T or now - (_parse(s.T[-1]) + BAR) > datetime.timedelta(minutes=cfg["max_bar_age_minutes"]):
        log("wait", log_path, symbol=sym, component=component, reason="bars stale: no NEW entry (§20/§52)",
            last_bar=s.T[-1] if s.T else None)
        return False
    hs = FF.holes(s.T, since=now - FF.HOLE_LOOKBACK)
    if hs:
        log("wait", log_path, symbol=sym, component=component, reason="data hole in the decision window: no NEW entry (§20/§52)",
            holes=hs[:3])
        return False
    return True


def _fvg_component(st, sym, h, now, cfg, bridge, base, log_path, live_dir, event_blocked):
    """E5 FVG retrace on one symbol: a LIMIT at the untouched gap's near edge (see new_gaps)."""
    s = closed_series(sym, now, live_dir)
    if not data_ok(s, sym, now, cfg, log_path, "E5"):
        return
    for g in new_gaps(s, sym, h):
        if g[0] == "refused":
            log("refused", log_path, symbol=sym, gap_time=g[2], reason=g[4])
            continue
        _, _, gap_time, side, edge, dist, sday = g
        key = f"{sym}|{sday}|{side}"
        gap_id = f"{sym}|{gap_time}|{side}"
        st.setdefault("placed_gaps", [])
        if key in st["done_keys"] or gap_id in st["placed_gaps"]:
            continue        # one FILLED trade per (symbol, server day, side), as the research; siblings cancel on fill
        blocked, why = event_blocked(sym, now)
        if blocked:
            log("blocked", log_path, symbol=sym, gap_time=gap_time, reason=why)
            continue
        info = _symbol_info(bridge, sym, log_path, "E5")
        if info is None:
            continue
        stop = edge - side * dist
        tp = edge + side * cfg["tp_stop_multiple"] * dist
        lots = lots_for(info, base, cfg["risk_pct"], edge, stop)
        if lots < float(info.get("volume_min", 0) or 0) or lots <= 0:
            log("skip", log_path, symbol=sym, gap_time=gap_time, reason=f"lots {lots} below volume_min")
            continue
        d = int(info.get("digits", 2))
        r = bridge("limit", sym, "buy" if side > 0 else "sell", f"{lots:g}", f"{edge:.{d}f}", f"{stop:.{d}f}",
                   f"{tp:.{d}f}", f"fvg-{sym}-{gap_time[11:16]}")
        if not r.get("ok"):
            log("rejected", log_path, symbol=sym, gap_time=gap_time, response=r)
            continue
        expires = min(_parse(gap_time) + BAR * (1 + EC.FVG_TOUCH_BARS), server_day_end(_parse(gap_time)))
        p = {"key": key, "symbol": sym, "h": h, "side": side, "ticket": r["ticket"], "edge": edge, "stop": stop,
             "lots": lots, "gap_time": gap_time, "placed_at": _iso(now), "expires_at": _iso(expires),
             "close_before_rollover_minutes": cfg["close_before_rollover_minutes"], **_attribution(cfg)}
        st["pending"].append(p)
        st["placed_gaps"].append(gap_id)
        log("limit_placed", log_path, **p)


def _eod_breakout(st, kind, sym, now, cfg, bridge, balance, log_path, live_dir, event_blocked):
    """H7 (F3: previous-day breakout with the 20-day momentum) or G9 (F4: open +/- 0.5 x previous range): a MARKET entry when
    the signal bar is the LAST closed bar (a later tick does not chase it), stop 2 sigma x sqrt(bars to the rollover), closed
    before the rollover. One trade per (component, symbol, server day, side)."""
    s = closed_series(sym, now, live_dir)
    if not data_ok(s, sym, now, cfg, log_path, kind):
        return
    det = {"H7": lambda: FF._f3().ev_breakout_trend(s), "G9": lambda: FF._f4().ev_vol_breakout(s)}[kind]
    for ev in det():
        if ev["i"] != len(s.T) - 1:
            continue
        side = ev["side"]
        key = f"{kind}|{sym}|{s.sday[ev['i']].isoformat()}|{side}"
        if key in st["done_keys"]:
            continue
        sig = s.sigma(ev["i"])
        if not sig or not FF._vol_fresh(s, ev["i"]):
            log("refused", log_path, symbol=sym, component=kind, reason="volatility history stale or missing")
            continue
        blocked, why = event_blocked(sym, now)
        if blocked:
            log("blocked", log_path, symbol=sym, component=kind, reason=why)
            continue
        day_end = server_day_end(now)
        exit_due = day_end - datetime.timedelta(minutes=cfg["close_before_rollover_minutes"])
        if now >= exit_due or s.sday[ev["i"]] != now.astimezone(FF._zone()).date():
            st["done_keys"].append(key)
            log("skip", log_path, symbol=sym, component=kind, reason="signal too close to the rollover: no same-day trade")
            continue
        nb = max(1, int((day_end - now).total_seconds() // 300))
        ref = s.C[ev["i"]]
        dist = 2.0 * sig * math.sqrt(nb) * ref
        info = _symbol_info(bridge, sym, log_path, kind)
        if info is None:
            continue
        d = int(info.get("digits", 2))
        stop, tp = ref - side * dist, ref + side * cfg["tp_stop_multiple"] * dist
        lots = lots_for(info, balance, cfg["risk_pct"], ref, stop)
        if lots <= 0 or lots < float(info.get("volume_min", 0) or 0):
            log("skip", log_path, symbol=sym, component=kind, reason=f"lots {lots} below volume_min")
            continue
        r = bridge("market", sym, "buy" if side > 0 else "sell", f"{lots:g}", f"{stop:.{d}f}", f"{tp:.{d}f}", f"{kind.lower()}-{sym}")
        st["done_keys"].append(key)
        if not r.get("ok"):
            log("rejected", log_path, symbol=sym, component=kind, response=r)
            continue
        pos = {"key": key, "component": kind, "symbol": sym, "side": side, "position_ticket": r.get("ticket"),
               "signal_close": ref, "fill_price": r.get("price"), "fill_slippage": (r.get("price", ref) - ref) * side,
               "stop": stop, "lots": lots, "filled_seen_at": _iso(now),
               "exit_due": _iso(exit_due), "risk_pct": cfg["risk_pct"], **_attribution(cfg)}
        st["open"].append(pos)
        log("filled", log_path, **pos)


def _wrong_terminal(cfg, bridge):
    """Defence in depth for several MT5 accounts on one machine: when the account declares `login_ref` (the NAME of an
    environment variable holding its login), the terminal behind its bridge channel must be logged into that login.
    A channel typed wrongly or a terminal restarted on another login becomes a refusal, not another account's orders."""
    ref = cfg.get("login_ref")
    if not ref:
        return None
    want = os.environ.get(ref)
    if not want:
        return f"login_ref {ref} is not set in the environment; refusing rather than trusting whoever is logged in"
    got = (bridge("account") or {}).get("login")
    if str(got) != str(want):
        return f"bridge channel {cfg.get('bridge_subdir')!r} reaches login {got}, but account {cfg.get('account')} is {want}"
    return None


def _attribution(cfg):
    return {"account": cfg.get("account"), "assignment": cfg.get("assignment"), "trading_system": cfg.get("trading_system")}


def _manage(st, now, cfg, bridge, log_path):
    """Exits and order housekeeping for everything already placed, whatever assignment placed it (DRAIN): each record
    carries the exit rule it was placed with. Records of an assignment listed in cfg["close_assignments"] (replaced by an
    assignment whose policy is CLOSE) are cancelled / closed now."""
    closing = set(cfg.get("close_assignments") or ())
    keep = []
    for p in st["pending"]:
        if p.get("assignment") in closing:
            bridge("cancel", p["ticket"])
            log("cancel_on_switch", log_path, **p)
            continue
        o = bridge("order-status", p["ticket"])
        if o.get("state") == "filled":
            before = p.get("close_before_rollover_minutes", cfg["close_before_rollover_minutes"])
            exit_due = min(now + BAR * p["h"], server_day_end(now) - datetime.timedelta(minutes=before))
            pos = dict(p, position_ticket=o.get("position_ticket"), fill_price=o.get("price"), filled_seen_at=_iso(now),
                       exit_due=_iso(exit_due), fill_slippage=(o.get("price", p["edge"]) - p["edge"]) * p["side"])   # + = paid worse than the edge
            st["open"].append(pos)
            st["done_keys"].append(p["key"])
            log("filled", log_path, **pos)
            for q in st["pending"]:          # the first fill of a (symbol, day, side) cancels its siblings
                if q is not p and q["key"] == p["key"]:
                    bridge("cancel", q["ticket"])
            continue
        if o.get("state") == "pending" and now >= _parse(p["expires_at"]):
            bridge("cancel", p["ticket"])
            log("expired", log_path, **p)
            continue
        if o.get("state") in ("canceled", "expired", "rejected"):
            log(o["state"], log_path, **p)
            continue
        keep.append(p)
    st["pending"] = [p for p in keep if p["key"] not in st["done_keys"]]
    still = []
    for pos in st["open"]:
        ps = bridge("position-status", pos["position_ticket"])
        if ps.get("state") == "closed":
            log("closed", log_path, **pos, exit_price=ps.get("price_close"), profit=ps.get("profit"), reason=ps.get("reason"))
            continue
        if ps.get("state") == "open" and pos.get("assignment") in closing:
            r = bridge("close", pos["position_ticket"])
            log("close_on_switch", log_path, **pos, response=r)
            if r.get("ok"):
                continue
        elif ps.get("state") == "open" and now >= _parse(pos["exit_due"]):
            r = bridge("close", pos["position_ticket"])
            log("time_exit", log_path, **pos, response=r)
            if r.get("ok"):
                continue
        still.append(pos)
    st["open"] = still


def status(account_id):
    paths = account_paths(account_id)
    st = _read_state(paths["state_path"])
    rows = []
    if os.path.exists(paths["log_path"]):
        with open(paths["log_path"], encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh]
    fills = [r for r in rows if r["kind"] == "filled"]
    closed = [r for r in rows if r["kind"] in ("closed", "time_exit", "close_on_switch")]
    live = R.active_assignment(account_id)
    print(f"{account_id}: {live['trading_system']}@{live['version']} ({live['id']})" if live else f"{account_id}: no live assignment")
    print(f"  pending {len(st['pending'])}, open {len(st['open'])}, fills {len(fills)}, exits {len(closed)}")
    if fills:
        print(f"  mean fill slippage vs the intended price (price units, + = worse): "
              f"{sum(r['fill_slippage'] for r in fills) / len(fills):.5f}")


def executor_accounts():
    """Accounts this executor drives: every non-ENDED account on the MT5 broker, in registry order."""
    return [a["id"] for a in R.accounts(broker=BROKER) if a["state"] != "ENDED"]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("tick", "status"))
    ap.add_argument("--account", default=None, help="one account id (default: every account this executor drives)")
    a = ap.parse_args()
    ids = [a.account] if a.account else executor_accounts()
    for aid in ids:
        if a.cmd == "tick":
            tick(account_id=aid)
        else:
            status(aid)


if __name__ == "__main__":
    main()
