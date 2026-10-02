#!/usr/bin/env python3
"""Forward DEMO executor for the FVG-retrace book (XAUUSD hold 24 bars, US500 hold 48 bars). DEMO ONLY.

    python3 scripts/fvg_demo.py tick       # one pass: place / cancel / close as needed (run every 1-5 minutes)
    python3 scripts/fvg_demo.py status     # open orders, positions and the paired comparison so far

What it trades is exactly what the research measured (scripts/research/edge_census.py `fvg_gap_at`, the ONE definition):
a displacement FVG known at the close of its third bar -> a LIMIT at the gap's near edge, protective stop 2 x sigma_5m x
sqrt(h), the time exit after h bars, flat before the broker rollover; one trade per (symbol, server day, side), the first
filled. Every fill and exit is logged next to the intended price, so implementation shortfall (fill vs edge, exit vs bar
close) is measured per trade -- the paired comparison of docs/plans/2026-10-02-edge-followup-preregistration.md §4.

Safety (CLAUDE.md §51, all fail closed): `docs/architecture/fvg-demo.json` enabled=false by default; the bridge must report
trade_mode "demo" (the EA also refuses non-demo, InpDemoOnly); symbols must be on the cfd EXECUTION allowlist
(docs/architecture/instruments.json, re-checked by scripts/mt5-order-bridge.py and the EA); risk per trade <= max_risk_pct;
every order carries its stop at placement; no new entry inside an event-risk window or when the calendar is unavailable
(scripts/event_risk.py, §24-§32); no new entry on stale bars (§20/§52). Open positions are only ever CLOSED by this script,
never added to or widened."""
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

CONFIG = os.path.join(ROOT, "docs", "architecture", "fvg-demo.json")
STATE = os.path.join(ROOT, "data", "live", "forward", "fvg-demo-state.json")
LOG = os.path.join(ROOT, "data", "live", "forward", "fvg-demo.jsonl")
BAR = datetime.timedelta(minutes=5)


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


class Bridge:
    """scripts/mt5-order-bridge.py as a function (the tests pass a fake with the same `__call__`)."""

    def __init__(self, subdir):
        self.env = dict(os.environ, MT5_BRIDGE_SUBDIR=subdir)

    def __call__(self, *args):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "mt5-order-bridge.py"), *map(str, args)],
                           capture_output=True, text=True, env=self.env)
        out = r.stdout.strip() or r.stderr.strip()
        try:
            d = json.loads(out) if out else {}
        except json.JSONDecodeError:
            d = {"ok": False, "comment": out[:300]}
        if r.returncode != 0:
            d.setdefault("ok", False)
        return d


def load_config(path=CONFIG):
    import trading_env
    c = json.load(open(path, encoding="utf-8"))
    c["risk_pct"] = min(float(c["risk_pct"]), float(trading_env.MAX_RISK_PCT))
    return c


def _read_state(path=STATE):
    return json.load(open(path)) if os.path.exists(path) else {"pending": [], "open": [], "done_keys": [], "placed_gaps": []}


def _write_state(st, path=STATE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    json.dump(st, open(tmp, "w"), indent=1)
    os.replace(tmp, path)


def log(kind, log_path=LOG, **kw):
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


def tick(now=None, bridge=None, cfg=None, state_path=STATE, log_path=LOG, live_dir=FF.LIVE_DIR, event_blocked=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    cfg = cfg or load_config()
    if not cfg.get("enabled"):
        print("fvg-demo disabled (docs/architecture/fvg-demo.json enabled=false): nothing done")
        return "disabled"
    bridge = bridge or Bridge(cfg.get("bridge_subdir", "bridge"))
    if event_blocked is None:
        import event_risk as ER
        event_blocked = lambda sym, at: ER.blocked(sym, at=_iso(at))
    ping = bridge("check")
    if not ping.get("demo"):
        log("refused", log_path, reason=f"bridge does not report a DEMO account: {ping}")
        print("REFUSED: not a demo account (or bridge unreachable)")
        return "refused"
    st = _read_state(state_path)
    _manage(st, now, cfg, bridge, log_path)
    balance = float(bridge("account").get("balance") or 0)
    for sym, h in cfg["components"].items():
        s = closed_series(sym, now, live_dir)
        if not s.T or now - (_parse(s.T[-1]) + BAR) > datetime.timedelta(minutes=cfg["max_bar_age_minutes"]):
            log("wait", log_path, symbol=sym, reason="bars stale: no NEW entry (§20/§52)", last_bar=s.T[-1] if s.T else None)
            continue
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
            info = bridge("symbol", sym)
            stop = edge - side * dist
            tp = edge + side * cfg["tp_stop_multiple"] * dist
            lots = lots_for(info, balance, cfg["risk_pct"], edge, stop)
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
                 "lots": lots, "gap_time": gap_time, "placed_at": _iso(now), "expires_at": _iso(expires)}
            st["pending"].append(p)
            st["placed_gaps"].append(gap_id)
            log("limit_placed", log_path, **p)
    _write_state(st, state_path)
    return "ok"


def _manage(st, now, cfg, bridge, log_path):
    keep = []
    for p in st["pending"]:
        o = bridge("order-status", p["ticket"])
        if o.get("state") == "filled":
            exit_due = min(now + BAR * p["h"], server_day_end(now) - datetime.timedelta(minutes=cfg["close_before_rollover_minutes"]))
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
        if ps.get("state") == "open" and now >= _parse(pos["exit_due"]):
            r = bridge("close", pos["position_ticket"])
            log("time_exit", log_path, **pos, response=r)
            if r.get("ok"):
                continue
        still.append(pos)
    st["open"] = still


def status(state_path=STATE, log_path=LOG):
    st = _read_state(state_path)
    rows = [json.loads(l) for l in open(log_path)] if os.path.exists(log_path) else []
    fills = [r for r in rows if r["kind"] == "filled"]
    closed = [r for r in rows if r["kind"] in ("closed", "time_exit")]
    print(f"pending {len(st['pending'])}, open {len(st['open'])}, fills {len(fills)}, exits {len(closed)}")
    if fills:
        print(f"mean fill slippage vs the FVG edge (price units, + = worse): "
              f"{sum(r['fill_slippage'] for r in fills) / len(fills):.5f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("tick", "status"))
    a = ap.parse_args()
    if a.cmd == "tick":
        tick()
    else:
        status()


if __name__ == "__main__":
    main()
