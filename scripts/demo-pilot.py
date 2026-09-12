#!/usr/bin/env python3
"""Rules-only pilot -- mechanical rules, hard caps. Trades the ACTIVE environment:
  docs/architecture/automation-config.json -> execution.environment ("demo" = Binance TESTNET, fake funds;
  "real" = Binance MAINNET, real money), credentials from config/env.<environment> via scripts/trading_env.py.
  --market spot    (default) SPOT, LONG only, OCO exits                    (scripts/binance-testnet-order.sh, env-driven)
  --market futures USDT-M FUTURES, LONG and SHORT, ISOLATED, leverage LEVERAGE (<=3),
                   STOP_MARKET + TAKE_PROFIT_MARKET closePosition exits     (scripts/binance-futures-testnet-order.sh, env-driven)
State/log/kill-switch live in data/live/pilot (spot) or data/live/pilot-futures (futures). SHORT rules mirror the
LONG rules: premium instead of discount, BSL/ERL-high sweep, bearish MSS, bearish FVG, stop above the swept high.

Authorised by the user on 2026-09-09 as a time-boxed testnet pilot (fake funds). Everything here is
deterministic: no LLM decides an order. Rules (all must hold for an entry, evaluated on 15m closes):
  1. Discount: last close below the 288-bar window equilibrium (docs/TTrades PDFs/8. Discount__Premium.pdf).
  2. ICT: a sweep of SSL / ERL-low within the last SWEEP_LOOKBACK bars, then a bullish MSS within the last
     MSS_LOOKBACK bars, and a bullish FVG formed since the sweep (docs/TTrades PDFs/11, 12, 18).
  3. Wyckoff Effort-vs-Result: the sweep bar or the MSS bar carries >= VOL_MULT x average volume and the
     MSS bar closes in its upper half (knowledge/08 §2.3, §4.1).
  4. Not inside an event blackout (docs/architecture/event-calendar.md, +/- 30 min), no open position in the
     symbol, < MAX_TRADES_PER_DAY for the symbol, < MAX_OPEN positions overall, pilot not halted.
Risk: RISK_PCT of USDT equity per trade (halved after 2 consecutive losses), notional capped at
NOTIONAL_CAP_PCT of equity, stop below the swept low, TP = window EQ if >= MIN_RR R else 2R, exits via OCO,
time-stop after TIME_STOP_BARS. Halt for the UTC day after 3 consecutive losses or daily loss <= -2% equity.
Kill switch: create data/live/pilot/STOP. `--flatten` closes everything. `--report` prints P&L.
Permission gate: docs/architecture/automation-config.json (the /automation command) can forbid a tick --
master switch off, layers.pilot off, markets.crypto off -- and an INCOMPLETE environment file (placeholder keys)
refuses a tick too (correctness, exit 2). The gate can only stop this tick, never start anything, and
`--report`/`--flatten` stay available so a disabled pilot can still be inspected/closed. Tradable symbols come
from markets.crypto.instruments. Risk per trade = PILOT_RISK_PCT from the env file, clamped to <= 1% (hard rule).
"""
import argparse, json, os, subprocess, sys, datetime, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from importlib import import_module
scan = import_module("ict-scan".replace("-", "_")) if False else None  # placeholder (module name has a dash)
import importlib.util
_spec = importlib.util.spec_from_file_location("ictscan", os.path.join(ROOT, "scripts", "ict-scan.py"))
ictscan = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(ictscan)

MARKET = os.environ.get("PILOT_MARKET", "spot")
if "--market" in sys.argv:
    MARKET = sys.argv[sys.argv.index("--market") + 1]
assert MARKET in ("spot", "futures"), "PILOT_MARKET must be spot or futures"
ORDER = os.path.join(ROOT, "scripts", "binance-testnet-order.sh" if MARKET == "spot" else "binance-futures-testnet-order.sh")
FETCH = os.path.join(ROOT, "scripts", "fetch-binance-klines.sh")
PILOT_DIR = os.path.join(ROOT, "data", "live", "pilot" if MARKET == "spot" else "pilot-futures")
STATE = os.path.join(PILOT_DIR, "state.json")
LOG = os.path.join(PILOT_DIR, "log.jsonl")
STOP = os.path.join(PILOT_DIR, "STOP")
LEVERAGE = 3                # futures only; ISOLATED margin; connector refuses > 3
SIDES = ["LONG"] if MARKET == "spot" else ["LONG", "SHORT"]

_ispec = importlib.util.spec_from_file_location("instruments", os.path.join(ROOT, "scripts", "instruments.py"))
instruments = importlib.util.module_from_spec(_ispec); _ispec.loader.exec_module(instruments)
SYMBOLS = instruments.execution("crypto")   # EXECUTION list (docs/architecture/instruments.json), not the allowlist
TF, N = "15m", 288

# ---- environment (demo testnet | real mainnet) -- scripts/trading_env.py; secrets never printed ----
_tspec = importlib.util.spec_from_file_location("trading_env", os.path.join(ROOT, "scripts", "trading_env.py"))
trading_env = importlib.util.module_from_spec(_tspec); _tspec.loader.exec_module(trading_env)
ENV_NAME = trading_env.active_env_name()
_ENV_KEYS = ("BINANCE_SPOT_API_KEY", "BINANCE_SPOT_SECRET_KEY") if MARKET == "spot" \
    else ("BINANCE_FUTURES_API_KEY", "BINANCE_FUTURES_SECRET_KEY")
try:
    _env = trading_env.load_env(resolve_secrets=False)      # limits + URLs only; the connectors resolve the secrets
    ENV_ERROR = None
except trading_env.EnvIncomplete as e:
    _env, ENV_ERROR = {}, str(e)
def _envf(key, default, lo=None, hi=None):
    try:
        v = float(_env.get(key, default))
    except (TypeError, ValueError):
        v = float(default)
    if lo is not None: v = max(lo, v)
    if hi is not None: v = min(hi, v)
    return v
MARKET_LABEL = f"{MARKET}_{'mainnet' if ENV_NAME == 'real' else 'testnet'}"   # trade-file.schema.json `market` enum
RISK_PCT = _envf("PILOT_RISK_PCT", 0.005, 0.0, 0.01)      # of USDT equity per trade; HARD CEILING 1% (max 1% rule)
NOTIONAL_CAP_PCT = 0.25     # never more than 25% of equity in one position
MAX_OPEN = int(_envf("PILOT_MAX_OPEN", 2, 1, 4))
MAX_TRADES_PER_DAY = int(_envf("PILOT_MAX_TRADES_PER_DAY", 3, 1, 6))
SWEEP_LOOKBACK, MSS_LOOKBACK = 8, 3
HTF_FILTER = True   # giảm khung: only trade in the direction the 4H structure allows (knowledge/07 §2.7, WA p93–96); user decision 2026-09-11
VOL_MULT = 1.5
MIN_RR = 2.0   # knowledge/06 §3.1 rule 23 (Model11 p92): 2R is the minimum before taking profit; was 1.5 until 2026-09-12
TIME_STOP_BARS = 24
DAILY_LOSS_HALT = -0.02
STOP_BUFFER_PCT = 0.0015


AUTOMATION_CONFIG = os.path.join(ROOT, "docs", "architecture", "automation-config.json")


def _automation():
    """docs/architecture/automation-config.json -- written only by scripts/automation.py (the /automation command).
    A missing file means UNCONFIGURED (no policy): the pilot behaves exactly as it did before the switch existed.
    A present file is authoritative."""
    if not os.path.exists(AUTOMATION_CONFIG):
        return None
    try:
        return json.load(open(AUTOMATION_CONFIG, encoding="utf-8"))
    except Exception:
        return {"_unreadable": True}


def automation_gate():
    """Reason to refuse this tick, or None. Never grants anything -- it can only stop the pilot."""
    c = _automation()
    if c is None:
        return None
    if c.get("_unreadable"):
        return "automation config unreadable -- refusing to tick"
    if not c.get("enabled", True):
        return "automation master switch is OFF (scripts/automation.py off)"
    if not c.get("layers", {}).get("pilot", True):
        return "pilot layer disabled (scripts/automation.py layer pilot off)"
    # v2 (schema_version 2): the pilot trades crypto only, so markets.crypto is its market gate.
    if not c.get("markets", {}).get("crypto", {}).get("enabled", True):
        return "markets.crypto disabled (scripts/automation.py market crypto off) -- the pilot trades crypto only"
    if MARKET == "futures" and c.get("execution", {}).get("pilot_profile", "legacy") == "top5":
        return "pilot profile is top5 -- the futures loop runs scripts/strategy-runner.py, not these rules (one profile per account, docs/security/2026-09-11-top5-pilot.md PILOT-04)"
    if ENV_ERROR:
        return f"environment '{ENV_NAME}' unusable -- {ENV_ERROR}"
    ok, missing, note = trading_env.completeness(ENV_NAME, _ENV_KEYS)
    if not ok:
        return f"environment '{ENV_NAME}' incomplete -- fill {', '.join(missing)} in config/env.{ENV_NAME} (refusing to tick)"
    return None


def enabled_symbols():
    """v2: markets.crypto.instruments. Unconfigured/unreadable = no policy = the built-in list."""
    c = _automation()
    if not c or c.get("_unreadable"):
        return SYMBOLS
    allow = set(c.get("markets", {}).get("crypto", {}).get("instruments", SYMBOLS))
    return [s for s in SYMBOLS if s in allow]


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def log(kind, **kw):
    os.makedirs(PILOT_DIR, exist_ok=True)
    rec = {"t": now().strftime("%Y-%m-%dT%H:%M:%SZ"), "kind": kind, **kw}
    with open(LOG, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps(rec, ensure_ascii=False))


def sh(*args, check=True):
    r = subprocess.run(args, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:3])} failed: {r.stderr.strip()[:300]}")
    return r.stdout


def order(*args):
    return sh(ORDER, *args)


def order_json(*args):
    out = order(*args)
    return json.loads(out) if out.strip() else {}


def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE))
    return {"started": now().strftime("%Y-%m-%dT%H:%M:%SZ"), "equity_start": None, "positions": {},
            "closed": [], "day": None, "trades_today": {}, "consec_losses": 0, "daily_pnl": 0.0, "halted_day": None}


def save_state(s):
    os.makedirs(PILOT_DIR, exist_ok=True)
    json.dump(s, open(STATE, "w"), indent=1)


def usdt_free():
    if MARKET == "futures":
        for b in order_json("balance"):
            if b["asset"] == "USDT":
                return float(b["availableBalance"])
        return 0.0
    acct = order_json("account")
    for b in acct["balances"]:
        if b["asset"] == "USDT":
            return float(b["free"])
    return 0.0


def event_blackout():
    p = os.path.join(ROOT, "docs", "architecture", "event-calendar.md")
    if not os.path.exists(p):
        return None
    t = now()
    for m in re.finditer(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})", open(p).read()):
        try:
            ev = datetime.datetime.strptime(m.group(1) + " " + m.group(2), "%Y-%m-%d %H:%M").replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
        if abs((ev - t).total_seconds()) <= 1800:
            return ev.strftime("%Y-%m-%dT%H:%MZ")
    return None


def evaluate(sym, side="LONG"):
    """Decision dict for one symbol/side on the freshest 288x15m window. SHORT mirrors LONG."""
    c = ictscan.load(sym, TF)[-N:]
    a = ictscan.analyze(c, SWEEP_LOOKBACK)
    n = len(c); V = [x["volume"] for x in c]; avgv = sum(V) / n
    O = [x["open"] for x in c]; H = [x["high"] for x in c]; L = [x["low"] for x in c]; C = [x["close"] for x in c]
    reasons = []
    long = side == "LONG"
    # 1. location: discount for longs, premium for shorts
    if long and a["pct"] >= 0.5:
        reasons.append(f"không ở discount ({a['pct']*100:.0f}% biên độ)")
    if not long and a["pct"] <= 0.5:
        reasons.append(f"không ở premium ({a['pct']*100:.0f}% biên độ)")
    # 2. sweep then MSS then FVG (same direction)
    pool, erl, mtype = ("SSL", "erl_low", "bull") if long else ("BSL", "erl_high", "bear")
    sweeps = [e for e in a["events"] if e["i"] >= n - SWEEP_LOOKBACK and (e["kind"] == erl or (e["kind"] == "sweep" and e.get("pool") == pool))]
    mss = [m for m in a["mss"] if m["type"] == mtype and m["i"] >= n - MSS_LOOKBACK]
    if not sweeps:
        reasons.append(f"chưa quét {pool}/{'ERL-low' if long else 'ERL-high'} trong {SWEEP_LOOKBACK} nến")
    if not mss:
        reasons.append(f"chưa có MSS {'tăng' if long else 'giảm'} trong {MSS_LOOKBACK} nến")
    sweep_i = max(e["i"] for e in sweeps) if sweeps else None
    mss_i = mss[-1]["i"] if mss else None
    fvg_ok = False
    if sweep_i is not None:
        for i in range(max(sweep_i, 1), n - 1):
            if (long and H[i - 1] < L[i + 1]) or ((not long) and L[i - 1] > H[i + 1]):
                fvg_ok = True; break
    if sweep_i is not None and not fvg_ok:
        reasons.append(f"chưa có FVG {'tăng' if long else 'giảm'} sau cú quét (chưa displacement)")
    # 3. effort vs result
    if sweep_i is not None and mss_i is not None:
        vol_ok = V[sweep_i] >= VOL_MULT * avgv or V[mss_i] >= VOL_MULT * avgv
        mid = (H[mss_i] + L[mss_i]) / 2
        strong_close = C[mss_i] >= mid if long else C[mss_i] <= mid
        if not vol_ok:
            reasons.append(f"volume nến quét/MSS < {VOL_MULT}x trung bình")
        if not strong_close:
            reasons.append(f"nến MSS đóng ở nửa {'dưới' if long else 'trên'} (kết quả yếu)")
    # 4. higher-timeframe filter (giảm khung): the 4H context must be in Phase C/D/E of a structure pointing our way
    htf_note = None
    if HTF_FILTER:
        import importlib.util as _iu
        _hs = _iu.spec_from_file_location("htf_context", os.path.join(ROOT, "scripts", "htf_context.py")); _htf = _iu.module_from_spec(_hs); _hs.loader.exec_module(_htf)
        ctx = _htf.load_context("daytrade", sym)
        want = "long" if long else "short"
        htf_note = f"{ctx['tf']}: bias {ctx['bias']}" if ctx else "không có bối cảnh"
        if not ctx or ctx["bias"] != want:
            reasons.append(f"bối cảnh {ctx['tf'] if ctx else '?'} không ủng hộ {side} (bias {ctx['bias'] if ctx else 'unknown'}: {(ctx or {}).get('basis', 'không có dữ liệu')})")
    entry = C[-1]
    stop = tp = None
    if sweep_i is not None:
        eq = a["eq"]
        if long:
            swept = min(L[sweep_i:]); stop = swept - max(STOP_BUFFER_PCT * entry, (entry - swept) * 0.1); r = entry - stop
            tp = eq if (eq - entry) >= MIN_RR * r else entry + 2 * r
        else:
            swept = max(H[sweep_i:]); stop = swept + max(STOP_BUFFER_PCT * entry, (swept - entry) * 0.1); r = stop - entry
            tp = eq if (entry - eq) >= MIN_RR * r else entry - 2 * r
        if r <= 0:
            reasons.append("stop không hợp lệ")
    return {"symbol": sym, "side": side, "ok": not reasons, "reasons": reasons, "entry": entry, "stop": stop, "tp": tp,
            "pct": a["pct"], "eq": a["eq"], "last_time": a["last_time"], "sweep_i": sweep_i, "mss_i": mss_i, "htf": htf_note}


def place_long(sym, d, equity, risk_mult, live):
    r = d["entry"] - d["stop"]
    risk_usd = equity * RISK_PCT * risk_mult
    qty = risk_usd / r
    notional_cap = equity * NOTIONAL_CAP_PCT
    if qty * d["entry"] > notional_cap:
        qty = notional_cap / d["entry"]
    qty_r = order("round-qty", sym, f"{qty:.8f}").strip()
    tp_r = order("round-price", sym, f"{d['tp']:.8f}").strip()
    stop_r = order("round-price", sym, f"{d['stop']:.8f}").strip()
    stop_limit = order("round-price", sym, f"{d['stop']*0.998:.8f}").strip()
    plan = {"symbol": sym, "qty": qty_r, "entry_ref": d["entry"], "stop": stop_r, "tp": tp_r, "stop_limit": stop_limit,
            "risk_usd": round(min(risk_usd, float(qty_r) * r), 2), "notional": round(float(qty_r) * d["entry"], 2)}
    if float(qty_r) * d["entry"] < 6:
        log("skip", symbol=sym, why="notional below exchange minimum", plan=plan); return None
    if not live:
        log("dry_run_entry", **plan); return None
    buy = order_json("market-buy-qty", sym, qty_r)
    fills = buy.get("fills", [])
    filled_qty = float(buy.get("executedQty", qty_r))
    avg_px = (sum(float(f["price"]) * float(f["qty"]) for f in fills) / filled_qty) if fills and filled_qty else d["entry"]
    fee_base = sum(float(f["commission"]) for f in fills if f.get("commissionAsset") == sym.replace("USDT", ""))
    sell_qty = order("round-qty", sym, f"{filled_qty - fee_base:.8f}").strip()
    oco = order_json("oco-sell", sym, sell_qty, tp_r, stop_r, stop_limit)
    reports = oco.get("orderReports", [])
    ids = {rep.get("type"): rep.get("orderId") for rep in reports}
    pos = {"qty": sell_qty, "entry": avg_px, "entry_order": buy.get("orderId"), "stop": float(stop_r), "tp": float(tp_r),
           "oco_list": oco.get("orderListId"), "tp_order": ids.get("LIMIT_MAKER"), "stop_order": ids.get("STOP_LOSS_LIMIT"),
           "opened_at": now().strftime("%Y-%m-%dT%H:%M:%SZ"), "bars": 0, "risk_usd": plan["risk_usd"]}
    log("entry", symbol=sym, market=MARKET_LABEL, env=ENV_NAME, **pos)
    return pos


def place_futures(sym, d, equity, risk_mult, live):
    """MARKET entry on USDT-M futures testnet (ISOLATED, LEVERAGE), then STOP_MARKET + TAKE_PROFIT_MARKET closePosition."""
    long = d["side"] == "LONG"
    r = abs(d["entry"] - d["stop"])
    risk_usd = equity * RISK_PCT * risk_mult
    qty = risk_usd / r
    notional_cap = equity * NOTIONAL_CAP_PCT * LEVERAGE      # margin used stays <= NOTIONAL_CAP_PCT of equity
    if qty * d["entry"] > notional_cap:
        qty = notional_cap / d["entry"]
    qty_r = order("round-qty", sym, f"{qty:.8f}").strip()
    tp_r = order("round-price", sym, f"{d['tp']:.8f}").strip()
    stop_r = order("round-price", sym, f"{d['stop']:.8f}").strip()
    plan = {"symbol": sym, "side": d["side"], "qty": qty_r, "entry_ref": d["entry"], "stop": stop_r, "tp": tp_r, "leverage": LEVERAGE,
            "risk_usd": round(min(risk_usd, float(qty_r) * r), 2), "notional": round(float(qty_r) * d["entry"], 2)}
    if float(qty_r) * d["entry"] < 5.5:
        log("skip", symbol=sym, why="notional below exchange minimum", plan=plan); return None
    if not live:
        log("dry_run_entry", **plan); return None
    sh(ORDER, "set-margin-type", sym, "ISOLATED", check=False)   # "No need to change margin type" is not an error
    order("set-leverage", sym, str(LEVERAGE))
    o = order_json("open-long" if long else "open-short", sym, qty_r)
    avg_px = float(o.get("avgPrice") or 0) or d["entry"]
    filled = float(o.get("executedQty") or qty_r)
    prot_side = "SELL" if long else "BUY"
    sl = order_json("stop-market", sym, prot_side, stop_r)
    tp = order_json("take-profit-market", sym, prot_side, tp_r)
    pos = {"side": d["side"], "qty": f"{filled:.8f}".rstrip("0").rstrip("."), "entry": avg_px, "entry_order": o.get("orderId"),
           "stop": float(stop_r), "tp": float(tp_r), "stop_order": sl.get("orderId"), "tp_order": tp.get("orderId"), "leverage": LEVERAGE,
           "opened_at": now().strftime("%Y-%m-%dT%H:%M:%SZ"), "bars": 0, "risk_usd": plan["risk_usd"]}
    log("entry", symbol=sym, market=MARKET_LABEL, env=ENV_NAME, **pos)
    return pos


def _futures_close_record(sym, pos, px, via, qty):
    sign = 1 if pos["side"] == "LONG" else -1
    pnl = (px - pos["entry"]) * float(qty) * sign
    return {"symbol": sym, "side": pos["side"], "exit": px, "via": via, "pnl": round(pnl, 2),
            "r": round(pnl / pos["risk_usd"], 2) if pos["risk_usd"] else None, "entry": pos["entry"], "qty": qty,
            "opened_at": pos["opened_at"], "closed_at": now().strftime("%Y-%m-%dT%H:%M:%SZ")}


def check_exit_futures(sym, pos, live):
    for leg in ("tp_order", "stop_order"):
        oid = pos.get(leg)
        if not oid:
            continue
        st = order_json("order-status", sym, str(oid))
        if st.get("status") == "FILLED":
            px = float(st.get("avgPrice") or 0) or float(st.get("stopPrice") or pos["tp" if leg == "tp_order" else "stop"])
            sh(ORDER, "cancel-all", sym, check=False)          # the other closePosition order is now orphaned
            return _futures_close_record(sym, pos, px, "TP" if leg == "tp_order" else "SL", st.get("executedQty") or pos["qty"])
    pos["bars"] += 1
    if pos["bars"] >= TIME_STOP_BARS:
        if not live:
            return None
        sh(ORDER, "cancel-all", sym, check=False)
        o = order_json("close-position", sym)
        px = float(o.get("avgPrice") or 0) or float(order_json("price", sym)["price"])
        return _futures_close_record(sym, pos, px, "TIME", o.get("executedQty") or pos["qty"])
    return None


def check_exit(sym, pos, live):
    if MARKET == "futures":
        return check_exit_futures(sym, pos, live)
    """Return closed-trade dict if the OCO resolved (or time-stop hit), else None."""
    for leg in ("tp_order", "stop_order"):
        oid = pos.get(leg)
        if not oid:
            continue
        st = order_json("order-status", sym, str(oid))
        if st.get("status") == "FILLED":
            px = float(st["cummulativeQuoteQty"]) / float(st["executedQty"])
            pnl = (px - pos["entry"]) * float(st["executedQty"])
            return {"symbol": sym, "exit": px, "via": "TP" if leg == "tp_order" else "SL", "pnl": round(pnl, 2),
                    "r": round(pnl / pos["risk_usd"], 2) if pos["risk_usd"] else None, "entry": pos["entry"], "qty": st["executedQty"],
                    "opened_at": pos["opened_at"], "closed_at": now().strftime("%Y-%m-%dT%H:%M:%SZ")}
    pos["bars"] += 1
    if pos["bars"] >= TIME_STOP_BARS:
        if not live:
            return None
        order("cancel-oco", sym, str(pos["oco_list"]))
        sell = order_json("market-sell-qty", sym, pos["qty"])
        px = float(sell["cummulativeQuoteQty"]) / float(sell["executedQty"])
        pnl = (px - pos["entry"]) * float(sell["executedQty"])
        return {"symbol": sym, "exit": px, "via": "TIME", "pnl": round(pnl, 2), "r": round(pnl / pos["risk_usd"], 2) if pos["risk_usd"] else None,
                "entry": pos["entry"], "qty": sell["executedQty"], "opened_at": pos["opened_at"], "closed_at": now().strftime("%Y-%m-%dT%H:%M:%SZ")}
    return None


def report(s):
    eq_now = usdt_free()
    closed = s["closed"]
    wins = [c for c in closed if c["pnl"] > 0]; losses = [c for c in closed if c["pnl"] <= 0]
    realised = round(sum(c["pnl"] for c in closed), 2)
    lines = [f"PILOT REPORT [{MARKET_LABEL} / env {ENV_NAME}] {now().strftime('%Y-%m-%d %H:%M UTC')} (started {s['started']})",
             f"USDT equity: start {s['equity_start']:.2f} -> now {eq_now:.2f} (free; open positions hold base assets)",
             f"Closed trades: {len(closed)} | wins {len(wins)} | losses {len(losses)} | realised P&L {realised:+.2f} USDT"
             + (f" | avg R {sum(c['r'] for c in closed if c['r'] is not None)/max(1,len([c for c in closed if c['r'] is not None])):+.2f}" if closed else "")]
    for c in closed:
        lines.append(f"  {c['symbol']} {c['opened_at'][11:16]}->{c['closed_at'][11:16]} via {c['via']}: entry {c['entry']:.2f} exit {c['exit']:.2f} pnl {c['pnl']:+.2f} ({c['r']:+.2f}R)")
    for sym, p in s["positions"].items():
        px = float(order_json("price", sym)["price"])
        sign = -1 if p.get("side") == "SHORT" else 1
        lines.append(f"  OPEN {sym} {p.get('side','LONG')}: qty {p['qty']} entry {p['entry']:.2f} stop {p['stop']:.2f} tp {p['tp']:.2f} mark {px:.2f} unrealised {(px-p['entry'])*float(p['qty'])*sign:+.2f}")
    lines.append(f"Consecutive losses: {s['consec_losses']} | halted today: {s['halted_day'] == now().strftime('%Y-%m-%d')} | daily pnl {s['daily_pnl']:+.2f}")
    print("\n".join(lines)); return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", action="store_true"); ap.add_argument("--flatten", action="store_true")
    ap.add_argument("--market", choices=["spot", "futures"], default=MARKET)
    a = ap.parse_args()
    s = load_state()
    if a.report:
        report(s); return
    if a.flatten and MARKET == "futures":
        for sym, p in list(s["positions"].items()):
            sh(ORDER, "cancel-all", sym, check=False); o = order_json("close-position", sym)
            px = float(o.get("avgPrice") or 0) or float(order_json("price", sym)["price"])
            rec = _futures_close_record(sym, p, px, "FLATTEN", o.get("executedQty") or p["qty"])
            s["closed"].append(rec); log("flatten", symbol=sym, pnl=rec["pnl"]); del s["positions"][sym]
        save_state(s); report(s); return
    if a.flatten:
        for sym, p in list(s["positions"].items()):
            order("cancel-oco", sym, str(p["oco_list"])); sell = order_json("market-sell-qty", sym, p["qty"])
            px = float(sell["cummulativeQuoteQty"]) / float(sell["executedQty"]); pnl = (px - p["entry"]) * float(sell["executedQty"])
            s["closed"].append({"symbol": sym, "exit": px, "via": "FLATTEN", "pnl": round(pnl, 2), "r": round(pnl / p["risk_usd"], 2), "entry": p["entry"], "qty": sell["executedQty"], "opened_at": p["opened_at"], "closed_at": now().strftime("%Y-%m-%dT%H:%M:%SZ")})
            log("flatten", symbol=sym, pnl=round(pnl, 2)); del s["positions"][sym]
        save_state(s); report(s); return
    live = a.live and not a.dry_run
    if os.path.exists(STOP):
        log("halt", why="STOP file present"); return
    gate = automation_gate()
    if gate:
        log("halt", why=gate); return
    if live and ENV_NAME == "real":
        log("env", note="REAL MAINNET tick -- real money", market=MARKET_LABEL, risk_pct=RISK_PCT)
    today = now().strftime("%Y-%m-%d")
    if s["day"] != today:
        s["day"] = today; s["trades_today"] = {}; s["daily_pnl"] = 0.0
    equity = usdt_free()
    if s["equity_start"] is None:
        s["equity_start"] = equity
    # 1. manage open positions
    for sym in list(s["positions"].keys()):
        closed = check_exit(sym, s["positions"][sym], live)
        if closed:
            s["closed"].append(closed); del s["positions"][sym]
            s["daily_pnl"] += closed["pnl"]
            s["consec_losses"] = 0 if closed["pnl"] > 0 else s["consec_losses"] + 1
            log("exit", **closed)
    halted = s["halted_day"] == today or s["consec_losses"] >= 3 or s["daily_pnl"] <= DAILY_LOSS_HALT * (s["equity_start"] or equity)
    if halted and s["halted_day"] != today:
        s["halted_day"] = today; log("halt", why=f"consec_losses={s['consec_losses']} daily_pnl={s['daily_pnl']:.2f}")
    blackout = event_blackout()
    # 2. look for entries (instrument allowlist honoured: scripts/automation.py instrument <SYM> on|off)
    for sym in enabled_symbols():
      sh(FETCH, sym, TF, str(N))
      for side in SIDES:
        d = evaluate(sym, side)
        if sym in s["positions"]:
            d["reasons"].append("đã có vị thế"); d["ok"] = False
        if s["trades_today"].get(sym, 0) >= MAX_TRADES_PER_DAY:
            d["reasons"].append("đủ 3 lệnh/ngày"); d["ok"] = False
        if len(s["positions"]) >= MAX_OPEN:
            d["reasons"].append("đã đủ 2 vị thế mở"); d["ok"] = False
        if halted:
            d["reasons"].append("đã dừng trong ngày"); d["ok"] = False
        if blackout:
            d["reasons"].append(f"blackout sự kiện {blackout}"); d["ok"] = False
        log("eval", symbol=sym, side=side, ok=d["ok"], pct=round(d["pct"], 3), reasons=d["reasons"], last_time=d["last_time"])
        if d["ok"]:
            risk_mult = 0.5 if s["consec_losses"] >= 2 else 1.0
            pos = (place_futures if MARKET == "futures" else place_long)(sym, d, equity, risk_mult, live)
            if pos:
                s["positions"][sym] = pos; s["trades_today"][sym] = s["trades_today"].get(sym, 0) + 1
                break
    save_state(s)


if __name__ == "__main__":
    main()
