#!/usr/bin/env python3
"""Python side of the MT5 file order bridge (integrations/mt5/OrderBridge.mq5). Same role as
scripts/binance-futures-testnet-order.sh for crypto: this script does NOT decide to trade; the caller does.

Files live in the terminal's Common\\Files folder, reachable as data/live/mt5-bridge (symlink, docs/architecture/mt5-bridge.md):
  bridge/cmd-<id>.json  -> written here (temp file + rename, so the EA never reads a half-written command)
  bridge/res-<id>.json  <- written by the EA; read here, then deleted
  bridge/state.json, bridge/symbols.json  <- snapshots the EA refreshes
Every response is printed as JSON on stdout. Exit 2 = refused (allowlist / not demo / bridge folder missing), 3 = timeout (the EA
is not attached or the terminal is closed), 1 = usage. Secrets: none -- the terminal is already logged in.

Usage:
  mt5-order-bridge.py check                                   ping + account mode + symbols file
  mt5-order-bridge.py account | state | symbol <SYM>
  mt5-order-bridge.py limit <SYM> <buy|sell> <LOTS> <PRICE> <SL> <TP> [COMMENT]   pending limit with SL/TP attached (GTC)
  mt5-order-bridge.py market <SYM> <buy|sell> <LOTS> <SL> <TP> [COMMENT]          market order with SL/TP (Wyckoff entries at the bar close)
  mt5-order-bridge.py cancel <TICKET> | modify <TICKET> <SL> <TP> | close <TICKET>
  mt5-order-bridge.py order-status <TICKET> | position-status <TICKET>
"""
import json, os, re, sys, time, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The command/response folder inside the terminal's Common\Files. ONE PER ACCOUNT when several MT5 terminals
# run on one machine: they share that Common folder, and this connector CONSUMES res-<id>.json (reads then
# deletes it), so two accounts on the same folder would race to eat each other's replies and one customer's
# fill could be reported to another. MT5_BRIDGE_SUBDIR must match the EA's InpBridgeDir input on that
# terminal. Default "bridge" keeps the single-account setup exactly as it was.
BRIDGE = os.path.join(ROOT, "data", "live", "mt5-bridge",
                      os.environ.get("MT5_BRIDGE_SUBDIR", "bridge"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from repo_paths import repo_rel
import instruments as I  # noqa: E402

# The EXECUTION allowlist for every market this bridge serves -- i.e. every market whose feed IS MetaTrader
# (I.DATA_DIR == "mt5-bridge"). Derived, not listed: this was a hard-coded four-symbol set, which meant the
# order path's allowlist and docs/architecture/instruments.json could disagree with nothing failing -- the
# precise shape SYSTEM-DESIGN.md §1 forbids ("never hard-code a symbol list").
# execution(), never analysis(): a watch-only symbol must not be orderable.
# The EA has its own copy (integrations/mt5/OrderBridge.mq5 InpAllowedSymbols) because it is compiled and
# cannot read this file; that one is a genuine second gate, and it must be kept in step by hand.
ALLOWED = {s for m, d in I.DATA_DIR.items() if d == "mt5-bridge" for s in I.execution(m)}
TIMEOUT = float(os.environ.get("MT5_BRIDGE_TIMEOUT", "10"))
# Canonical -> broker spelling (FTMO: US500 -> US500.cash) at THIS boundary only (scripts/broker_symbols.py). Callers pass the
# canonical symbol; the allowlist is checked on it; the EA receives the broker's name. MT5_SYMBOL_MAP=<path> points at another
# terminal's map; MT5_SYMBOL_MAP=none means the terminal spells every symbol canonically.
SYMBOL_MAP = os.environ.get("MT5_SYMBOL_MAP", "")


def refuse(msg, code=2):
    print(json.dumps({"ok": False, "comment": msg}), file=sys.stderr); sys.exit(code)


def resolve(sym, symbol_map=None):
    """(canonical, broker) for a symbol given in either spelling; refuses (exit 2) off the allowlist or off the map."""
    import broker_symbols as BSYM
    m = SYMBOL_MAP if symbol_map is None else symbol_map
    if m.lower() == "none":
        canon, broker = sym, sym
    else:
        path = m or BSYM.MAP_PATH
        try:
            canon = sym if sym in ALLOWED else BSYM.to_canonical(sym, path)
            broker = BSYM.to_broker(canon, path)
        except BSYM.UnknownSymbol as e:
            refuse(f"symbol {sym}: {e}")
    if canon not in ALLOWED:
        refuse(f"symbol {sym} not in allowlist")
    return canon, broker


def call(action, **fields):
    if not os.path.isdir(os.path.dirname(BRIDGE)):
        refuse(f"MT5 bridge folder missing: {repo_rel(os.path.dirname(BRIDGE), ROOT)} (symlink to Common/Files, docs/architecture/mt5-bridge.md)")
    os.makedirs(BRIDGE, exist_ok=True)
    cid = uuid.uuid4().hex[:12]
    body = {"id": cid, "action": action, **{k: str(v) for k, v in fields.items()}}
    tmp = os.path.join(BRIDGE, f".cmd-{cid}.tmp"); dst = os.path.join(BRIDGE, f"cmd-{cid}.json")
    with open(tmp, "w", encoding="ascii") as f:
        json.dump(body, f)
    os.replace(tmp, dst)
    res = os.path.join(BRIDGE, f"res-{cid}.json"); t0 = time.time()
    while time.time() - t0 < TIMEOUT:
        if os.path.exists(res):
            time.sleep(0.05)
            raw = open(res, encoding="utf-8", errors="replace").read()
            try:
                d = json.loads(raw)
            except json.JSONDecodeError:
                try:
                    d = json.loads(raw.replace("\\", "\\\\"))   # tolerate unescaped Windows paths from an older EA build (it never emits real escapes)
                except json.JSONDecodeError:
                    time.sleep(0.1); continue
            os.remove(res)
            return d
        time.sleep(0.2)
    try:
        os.remove(dst)              # never leave a command behind for a later EA start to execute
    except OSError:
        pass
    refuse(f"timeout after {TIMEOUT:.0f}s -- is OrderBridge attached to a chart and the terminal open?", 3)


def snapshot(name):
    p = os.path.join(BRIDGE, name)
    if not os.path.exists(p):
        refuse(f"{name} not written yet by the EA")
    return json.load(open(p, encoding="utf-8", errors="replace"))


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(1)
    cmd = a[0]
    if cmd == "check":
        r = call("ping"); call("symbol"); syms = snapshot("symbols.json")
        print(json.dumps({"ping": r, "symbols": sorted(syms), "demo": r.get("trade_mode") == "demo"})); return
    if cmd == "account":
        call("state"); print(json.dumps(snapshot("state.json")["account"])); return
    if cmd == "state":
        call("state"); print(json.dumps(snapshot("state.json"))); return
    if cmd == "symbol":
        _canon, broker = resolve(a[1])
        call("symbol")
        syms = snapshot("symbols.json")
        if broker not in syms:
            refuse(f"symbol {broker} not in the EA's symbols.json (its InpAllowedSymbols must name the broker spelling)")
        print(json.dumps(syms[broker])); return
    if cmd == "limit":
        sym, side, lots, price, sl, tp = a[1:7]; comment = a[7] if len(a) > 7 else ""
        _canon, broker = resolve(sym)
        if side not in ("buy", "sell"):
            refuse("side must be buy|sell")
        print(json.dumps(call("limit", symbol=broker, side=side, volume=lots, price=price, sl=sl, tp=tp, comment=comment))); return
    if cmd == "market":
        sym, side, lots, sl, tp = a[1:6]; comment = a[6] if len(a) > 6 else ""
        _canon, broker = resolve(sym)
        if side not in ("buy", "sell"):
            refuse("side must be buy|sell")
        print(json.dumps(call("market", symbol=broker, side=side, volume=lots, sl=sl, tp=tp, comment=comment))); return
    if cmd == "cancel":
        print(json.dumps(call("cancel", ticket=a[1]))); return
    if cmd == "modify":
        print(json.dumps(call("modify", ticket=a[1], sl=a[2], tp=a[3]))); return
    if cmd == "close":
        print(json.dumps(call("close", ticket=a[1]))); return
    if cmd == "order-status":
        print(json.dumps(call("order_status", ticket=a[1]))); return
    if cmd == "position-status":
        print(json.dumps(call("position_status", ticket=a[1]))); return
    print(__doc__); sys.exit(1)


if __name__ == "__main__":
    main()
