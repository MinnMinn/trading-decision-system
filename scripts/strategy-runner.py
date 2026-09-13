#!/usr/bin/env python3
"""Pilot profile `top5` -- mechanical runner for the setups selected in docs/architecture/pilot-top5.json
(written by scripts/rank-setups.py from the stability backtests). Crypto setups trade Binance USDT-M FUTURES TESTNET
(scripts/binance-futures-testnet-order.sh); CFD setups trade the MT5 DEMO account through the file bridge
(scripts/mt5-order-bridge.py + integrations/mt5/OrderBridge.mq5). Real trades, fake money, on both venues.

Selected by `/automation pilot profile top5` (docs/architecture/automation-config.json -> execution.pilot_profile); run by
scripts/pilot-loop.sh every 30 minutes one minute after the half-hour close. No LLM decides an order. This runner REFUSES to
tick when execution.environment is "real" (user decision 2026-09-11: demo/testnet pilot first) and the MT5 bridge EA refuses
non-demo accounts on its side too.

Rules = the backtest, function for function (scripts/backtest-methods.py, imported; parameters bt.P[tf]):
  WYCKOFF   Spring/Upthrust proxy at the R-bar border: type 1 (or type 3 with a high-volume reclaim) enters at the reclaim close, else at the
            retest (WMT p049, WA p80) -- MARKET at that bar's close; stop = Spring extreme; target = opposite border
  WYCKOFF-BOOK  scripts/wyckoff_rules.py structures on the window (CHoCH gate, TR from SC/AR, Phase B, Spring vs Shakeout, VP veto, Test, Phase D
            BU) -- MARKET at the entry bar close; Phase D target = TR top + 1 TR
  ICT       sourced from the LIVE rules (ict_live_setups -> live_rules.ict_scan.setup_candidate), same as bt.scan's ICT branch:
            sweep of the last 3-bar pivot -> MSS body close within K -> FVG complete before the MSS -> LIMIT at the FVG near edge;
            stop = excursion extreme -/+ 0.05 %; target = the live scanner's su["target"] (no configurable target model --
            the six-way range/std2/std25/std4/erl_next/irl switch and bt.ict_target() were deleted 2026-09-13, dead since
            the legacy ICT branch that was their only caller was removed)
  COMBINED  Spring/Upthrust proxy (R-bar border pierce, reclaim <= 2 bars, volume type gate) + the ICT confirmation -> LIMIT at the
            FVG edge; stop = Spring extreme; target = the opposite border
  Entry = LIMIT valid K bars after the MSS (post-only GTX on Binance; a pending order with SL/TP attached on MT5); no fill -> no
  trade. Management = STOP_MARKET + TAKE_PROFIT_MARKET closePosition (futures) or the position's own SL/TP (MT5); breakeven at +1R
  on a CLOSED candle when the setup says mgmt=be (WMT p272); time stop after H bars. The higher-timeframe boundary filter
  (bt.htf_allows on HTF_OF[tf]) is logged as htf_pass for every signal; orders obey it only for setups with htf=true.
Risk: PILOT_RISK_PCT of equity per trade (env file, clamped <= 1 %), halved after 2 consecutive losses; futures notional <= 25 % of
equity x leverage 3, ISOLATED; MT5 lots from the bridge's contract data, capped by the EA's InpMaxLots. One position or resting
order per symbol, MAX_OPEN per venue (= that venue's symbol count, i.e. a full book), MAX_TRADES_PER_DAY per symbol.
Halts (STOP file written with the reason): equity <= 85 % of start (per venue), 5 consecutive losses (per venue), 3 consecutive
connector errors. Refused per tick: kill switch, automation gate (master/pilot layer/market/profile/environment), event blackout.
Reconcile (PILOT-06): venue positions/orders this runner does not own block new entries in that symbol.
Files (this runner is their only writer): data/live/pilot-futures/top5-state.json, top5-log.jsonl (crypto), top5-mt5-log.jsonl (CFD),
candles/ohlcv.<SYM>.<TF>.json (private Binance copies). CFD candles are READ from data/live/mt5-bridge/ (the export EA writes them).
Journal: scripts/journal.py sync-pilot --market futures-top5 | cfd-mt5.
Usage: strategy-runner.py --live | --dry-run [--ignore-gate] [--tick-time ISO] | --replay <setup-id|all> [--bars N] | --report | --flatten | --list | --tick-seconds
"""
import argparse, datetime, hashlib, importlib.util, json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
_spec = importlib.util.spec_from_file_location("bt", os.path.join(ROOT, "scripts", "backtest-methods.py")); bt = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(bt)
import wyckoff_rules as W
_tspec = importlib.util.spec_from_file_location("trading_env", os.path.join(ROOT, "scripts", "trading_env.py")); trading_env = importlib.util.module_from_spec(_tspec); _tspec.loader.exec_module(trading_env)

ORDER = os.path.join(ROOT, "scripts", "binance-futures-testnet-order.sh")
MT5 = os.path.join(ROOT, "scripts", "mt5-order-bridge.py")
FETCH = os.path.join(ROOT, "scripts", "fetch-binance-klines.sh")
PILOT_DIR = os.path.join(ROOT, "data", "live", "pilot-futures")
CANDLES = os.path.join(PILOT_DIR, "candles")
MT5_DIR = os.path.join(ROOT, "data", "live", "mt5-bridge")
STATE = os.path.join(PILOT_DIR, "top5-state.json")
LOG = os.path.join(PILOT_DIR, "top5-log.jsonl")
MT5_LOG = os.path.join(PILOT_DIR, "top5-mt5-log.jsonl")
STOP = os.path.join(PILOT_DIR, "STOP")
AUTOMATION_CONFIG = os.path.join(ROOT, "docs", "architecture", "automation-config.json")
SELECTION = os.path.join(ROOT, "docs", "architecture", "pilot-top5.json")
_ispec = importlib.util.spec_from_file_location("instruments", os.path.join(ROOT, "scripts", "instruments.py"))
instruments = importlib.util.module_from_spec(_ispec); _ispec.loader.exec_module(instruments)
# EXECUTION list (docs/architecture/instruments.json) -- the orderable subset, never the analysis allowlist.
CRYPTO = instruments.execution("crypto"); CFD = instruments.execution("cfd")
_mspec = importlib.util.spec_from_file_location("methods", os.path.join(ROOT, "scripts", "methods.py"))
mreg = importlib.util.module_from_spec(_mspec); _mspec.loader.exec_module(mreg)
DEFAULT_SETUPS = [dict(id="crypto-ict-30m-std25-c", market="crypto", symbols=CRYPTO, tf="30m", method="ICT", htf=True, mgmt="be", execution="futures")]
# STRUCTURE tier = the next runner timeframe >= 4x (scripts/automation.py next_rung -- the one ladder rule, docs/architecture/
# timeframe-mapping.md). Over the runner's rungs this yields 5m->30m, 15m->1H, 30m->2H, 1H->4H, 2H->1D, 4H->1D, 1D->None,
# identical to the table the backtests were run with (scripts/tests/test_timeframe_ladder.py pins it).
RUNNER_TFS = ["5m", "15m", "30m", "1H", "2H", "4H", "1D"]
import importlib.util as _iu
_as = _iu.spec_from_file_location("automation", os.path.join(ROOT, "scripts", "automation.py")); _auto = _iu.module_from_spec(_as); _as.loader.exec_module(_auto)
HTF_OF = {tf: _auto.next_rung(tf, RUNNER_TFS) for tf in RUNNER_TFS}
WINDOW = 300
LEVERAGE = 3
NOTIONAL_CAP_PCT = 0.25
# Full book (user decision 2026-09-12): one concurrent position per tradeable symbol, so the per-symbol rule
# ("one position or resting order per symbol") becomes the only binding cap. Derived from the EXECUTION list
# (docs/architecture/instruments.json) so adding a symbol raises the book by exactly one slot -- no second edit.
# RISK NOTE: max simultaneous risk = len(symbols) x PILOT_RISK_PCT. Crypto is near-perfectly correlated in a dump,
# so a full book is closer to ONE leveraged beta bet than to nine independent ones; EQUITY_HALT_FRAC is what bounds
# the damage. Dial it back by lowering PILOT_RISK_PCT in config/env.<env>, not by editing this line.
MAX_OPEN = {"futures": len(CRYPTO), "mt5": len(CFD)}   # per venue
MAX_TRADES_PER_DAY = 3
EQUITY_HALT_FRAC = 0.85
CONSEC_LOSS_HALT = 5
ERROR_HALT = 3
STOP_BUFFER_PCT = bt.STOP_BUFFER_PCT
TF_SEC = {"5m": 300, "15m": 900, "30m": 1800, "1H": 3600, "2H": 7200, "4H": 14400, "1D": 86400}
VENUES = ("futures", "mt5")
METHODS = tuple(sorted(mreg.runnable()))   # ICT/COMBINED = limit at the FVG edge; WYCKOFF* = market at the bar close

ENV_NAME = trading_env.active_env_name()
try:
    _env = trading_env.load_env(resolve_secrets=False); ENV_ERROR = None
except trading_env.EnvIncomplete as e:
    _env, ENV_ERROR = {}, str(e)
try:
    RISK_PCT = min(0.01, max(0.0, float(_env.get("PILOT_RISK_PCT", 0.005))))
except (TypeError, ValueError):
    RISK_PCT = 0.005
MARKET_LABEL = f"futures_{'mainnet' if ENV_NAME == 'real' else 'testnet'}"


# ---------------------------------------------------------------- infrastructure
def now():
    return datetime.datetime.now(datetime.timezone.utc)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_t(s):
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)


def log(kind, venue="futures", **kw):
    os.makedirs(PILOT_DIR, exist_ok=True)
    rec = {"t": iso(now()), "kind": kind, **kw}
    with open(MT5_LOG if venue == "mt5" else LOG, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps(rec, ensure_ascii=False))


def sh(*args, check=True):
    r = subprocess.run(args, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{os.path.basename(args[0])} {' '.join(args[1:3])} failed: {r.stderr.strip()[:300]}")
    return r.stdout


def order(*args):
    return sh(ORDER, *args)


def order_json(*args):
    out = order(*args)
    return json.loads(out) if out.strip() else {}


def mt5_json(*args):
    out = sh("python3", MT5, *args)
    return json.loads(out) if out.strip() else {}


def load_setups():
    if os.path.exists(SELECTION):
        try:
            return [s for s in json.load(open(SELECTION, encoding="utf-8"))["setups"] if s.get("method") in METHODS and s.get("execution") in VENUES]
        except Exception:
            return []
    return DEFAULT_SETUPS


def automation_gate():
    """Reason to refuse this tick, or None. Can only stop, never start. Missing/unreadable config = refuse (PILOT-03)."""
    if not os.path.exists(AUTOMATION_CONFIG):
        return "no automation config -- profile top5 runs only under /automation"
    try:
        c = json.load(open(AUTOMATION_CONFIG, encoding="utf-8"))
    except Exception:
        return "automation config unreadable"
    if not c.get("enabled", True):
        return "automation master switch is OFF"
    if not c.get("layers", {}).get("pilot", True):
        return "pilot layer disabled"
    if c.get("execution", {}).get("pilot_profile", "legacy") != "top5":
        return "pilot profile is not top5 (scripts/automation.py pilot profile top5)"
    if c.get("execution", {}).get("environment", "demo") == "real":
        return "environment is REAL -- the top5 profile is a demo/testnet pilot (user decision 2026-09-11); refusing"
    if ENV_ERROR:
        return f"environment '{ENV_NAME}' unusable -- {ENV_ERROR}"
    ok, missing, note = trading_env.completeness(ENV_NAME, ("BINANCE_FUTURES_API_KEY", "BINANCE_FUTURES_SECRET_KEY"))
    if not ok:
        return f"environment '{ENV_NAME}' incomplete -- fill {', '.join(missing)}"
    return None


def enabled_symbols(market):
    try:
        c = json.load(open(AUTOMATION_CONFIG, encoding="utf-8"))
        mk = c.get("markets", {}).get(market, {})
        if not mk.get("enabled", True):
            return []
        return [s for s in (CRYPTO if market == "crypto" else CFD) if s in set(mk.get("instruments", []))]
    except Exception:
        return []


def allowed_methods(market, dims=None):
    """Runner methods the current method preset permits for this market. Empty set = no NEW entries; open
    positions and pending orders are still managed (spec §4.3, grandfather). Pass `dims` (an already-parsed
    market "dimensions" dict) to avoid re-reading/re-parsing AUTOMATION_CONFIG once per setup inside a tick;
    omit it for a one-off caller (e.g. --list) that reads fresh.
    automation_gate() already refuses a tick when AUTOMATION_CONFIG is missing or unreadable (PILOT-03), so in
    the live tick path the except-Exception fallback below is unreachable; it is reachable for a caller that
    invokes allowed_methods() directly without going through tick() (e.g. --list run against a moved/corrupt
    config), where it deliberately behaves as if no method preset switch existed."""
    if dims is None:
        try:
            c = json.load(open(AUTOMATION_CONFIG, encoding="utf-8"))
            dims = c.get("markets", {}).get(market, {}).get("dimensions", {})
        except Exception:
            return set(METHODS)                    # unconfigured = behave exactly as before this switch existed
    return mreg.runner_methods(dims) & set(METHODS)


def event_blackout(t=None):
    p = os.path.join(ROOT, "docs", "architecture", "event-calendar.md")
    if not os.path.exists(p):
        return None
    t = t or now()
    for m in re.finditer(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})", open(p).read()):
        try:
            ev = datetime.datetime.strptime(m.group(1) + " " + m.group(2), "%Y-%m-%d %H:%M").replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
        if abs((ev - t).total_seconds()) <= 1800:
            return ev.strftime("%Y-%m-%dT%H:%MZ")
    return None


EQUITY_BASIS = "equity"  # value of state["equity_basis"] once equity_start is captured from usdt_equity()/mt5_equity()


def load_state():
    base = {"started": iso(now()), "pending": {}, "positions": {}, "seen": [], "day": None, "trades_today": {}, "errors": 0, "halted": None, "last_tick": None,
            "equity_basis": EQUITY_BASIS, "venues": {v: {"equity_start": None, "closed": [], "consec_losses": 0} for v in VENUES}}
    if os.path.exists(STATE):
        s = json.load(open(STATE))
        # PILOT-EQUITY-FIX (2026-09-13): equity_start used to be captured from usdt_free() (Binance
        # availableBalance, i.e. free margin) for the futures venue. That is a different quantity from the
        # equity reading the halt now compares it to (usdt_equity() = balance + crossUnPnl), and the two are
        # not comparable -- continuing to check a corrected equity reading against a free-margin baseline
        # could either falsely re-halt (baseline captured while margin was already reserved) or silently
        # widen the drawdown guard (baseline captured before any order, so free margin == equity that once).
        # A state file with no "equity_basis" marker predates this fix; re-baseline every venue by clearing
        # equity_start so the next LIVE tick recaptures it from the corrected reading (same mechanism that
        # already seeds a fresh equity_start today, load_state()/tick() -- no new code path). This is a
        # one-time reset the first time a fixed runner picks up an old state file, not a repeating reset:
        # once equity_basis == EQUITY_BASIS below, this branch does not fire again.
        if s.get("equity_basis") != EQUITY_BASIS:
            for v in VENUES:
                s.setdefault("venues", {}).setdefault(v, dict(base["venues"][v]))
                s["venues"][v]["equity_start"] = None
            s["equity_basis"] = EQUITY_BASIS
        for k, v in base.items():
            s.setdefault(k, v)
        for v in VENUES:
            s["venues"].setdefault(v, base["venues"][v])
        return s
    return base


def save_state(s):
    os.makedirs(PILOT_DIR, exist_ok=True)
    json.dump(s, open(STATE, "w"), indent=1)


def usdt_balance():
    """Single Binance USDT-M futures balance fetch (GET /fapi/v2/balance via order_json("balance")).
    Returns both readings this runner needs from the one snapshot, so they can never disagree within a
    tick:
      free   -- availableBalance: wallet balance minus margin reserved by open positions/resting orders.
                This is FREE MARGIN, not equity -- it drops the instant a pending order reserves margin,
                with nothing lost. Use for position sizing / order placement only (money actually spendable
                on a NEW order); never for the capital-preservation halt.
      equity -- balance + crossUnPnl: true account equity. This is what EQUITY_HALT_FRAC must compare to
                equity_start (2026-09-13 incident: the halt was reading availableBalance instead and fired
                on the pilot's first resting limit order at a 25 %-looking "drawdown" that was really just
                margin held for an open order -- real equity was down ~1 USDT on a 5000 account).
    """
    for b in order_json("balance"):
        if b["asset"] == "USDT":
            return {"free": float(b["availableBalance"]), "equity": float(b["balance"]) + float(b.get("crossUnPnl", 0.0))}
    return {"free": 0.0, "equity": 0.0}


def usdt_free():
    """Free margin only -- see usdt_balance(). Sizing/order-placement callers want this one."""
    return usdt_balance()["free"]


def usdt_equity():
    """Account equity only -- see usdt_balance(). The EQUITY_HALT_FRAC guard wants this one, not usdt_free()."""
    return usdt_balance()["equity"]


def mt5_equity():
    """MT5's own ACCOUNT_EQUITY (balance + floating P/L of open positions, integrations/mt5/OrderBridge.mq5
    JN("equity", AccountInfoDouble(ACCOUNT_EQUITY))) -- this already IS true equity, not free margin (that
    field is separately exported as margin_free and this runner does not read it). No Binance-style
    free-margin confusion on this venue; used unchanged for both the halt guard and MT5 lot sizing."""
    a = mt5_json("account")
    if a.get("trade_mode") not in ("demo", None) and a.get("trade_mode") != "demo":
        raise RuntimeError(f"MT5 account is not DEMO ({a.get('trade_mode')}) -- refusing")
    return float(a["equity"])


def aggregate(c, hours):
    out = {}
    for x in c:
        h = int(x["time"][11:13]); key = f"{x['time'][:11]}{(h // hours) * hours:02d}:00:00Z"
        b = out.get(key)
        if b is None:
            out[key] = dict(time=key, open=x["open"], high=x["high"], low=x["low"], close=x["close"], volume=x.get("volume", 0))
        else:
            b["high"] = max(b["high"], x["high"]); b["low"] = min(b["low"], x["low"]); b["close"] = x["close"]; b["volume"] += x.get("volume", 0)
    return [out[k] for k in sorted(out)]


def drop_forming(c, tf, t):
    if c and parse_t(c[-1]["time"]) + datetime.timedelta(seconds=TF_SEC[tf]) > t:
        c = c[:-1]
    return c


def fetch_candles(sym, tf, market, t, at=None, window=None):
    """Closed candles only. Crypto: private Binance copy. CFD: the MT5 export file (2H aggregated from 1H). --replay: history cut at `at`.
    `window`: candle count to return, default WINDOW (300) -- enough for WYCKOFF/COMBINED. ICT setups need
    live_rules' own (larger, per-tf) trailing window, see ict_scan_bars() in tick() below (2026-09-13, Task 8)."""
    window = window or WINDOW
    if at is not None:
        c = json.load(open(f"{ROOT}/data/history/ohlcv.{sym}.{tf}.json"))["candles"]
        return [x for x in c if x["time"] <= at][-window:]
    if market == "crypto":
        env = dict(os.environ, KLINES_OUT_DIR=CANDLES)
        r = subprocess.run(["bash", FETCH, sym, tf, str(window)], capture_output=True, text=True, env=env)
        if r.returncode != 0:
            raise RuntimeError(f"fetch {sym} {tf}: {r.stderr.strip()[:200]}")
        c = json.load(open(f"{CANDLES}/ohlcv.{sym}.{tf}.json"))["candles"]
    else:
        src_tf = {"2H": "1H", "30m": "15m"}.get(tf, tf)          # the export EA writes 5m/15m/1H/4H/1D/1W; 30m and 2H are aggregated
        p = f"{MT5_DIR}/ohlcv.{sym}.{src_tf}.json"
        if not os.path.exists(p):
            raise RuntimeError(f"no MT5 export for {sym} {src_tf}")
        d = json.load(open(p)); c = d["candles"]
        if d.get("last_updated") and (t - parse_t(d["last_updated"])).total_seconds() > 2 * TF_SEC[src_tf] + 900:
            raise RuntimeError(f"MT5 export for {sym} {src_tf} is stale ({d['last_updated']})")
        if tf == "2H":
            c = aggregate(c, 2)
        elif tf == "30m":
            c = aggregate_minutes(c, 30)
    return drop_forming(c, tf, t)[-window:]


def aggregate_minutes(c, minutes):
    out = {}
    for x in c:
        m = int(x["time"][14:16]); key = f"{x['time'][:14]}{(m // minutes) * minutes:02d}:00Z"
        b = out.get(key)
        if b is None:
            out[key] = dict(time=key, open=x["open"], high=x["high"], low=x["low"], close=x["close"], volume=x.get("volume", 0))
        else:
            b["high"] = max(b["high"], x["high"]); b["low"] = min(b["low"], x["low"]); b["close"] = x["close"]; b["volume"] += x.get("volume", 0)
    return [out[k] for k in sorted(out)]


def due(tf, t, market="crypto"):
    """A setup on `tf` is evaluated on the tick right after its candle closed (ticks run at :01 / :31). MT5 bars close on the
    broker's clock (XAUUSD 4H bars close at 01:00/05:00/... UTC on this broker), so CFD 2H/4H/1D setups are evaluated on every
    hour tick -- the signal cache (`seen`) makes repeated evaluation harmless and drop_forming() keeps only closed bars."""
    if tf in ("5m", "15m", "30m"):
        return True                      # the loop ticks at the fastest selected timeframe; the signal cache makes extra ticks harmless
    if t.minute >= 30:
        return False
    if market == "cfd":
        return True
    return {"1H": True, "2H": t.hour % 2 == 0, "4H": t.hour % 4 == 0, "1D": t.hour == 0}[tf]


# ---------------------------------------------------------------- signals (mirror of backtest-methods.scan, causal cut)
def ict_scan_bars(tf):
    """The live scanner's required trailing window for `tf` (live_rules.scan_spec), or None if live never scans
    this tf at all -- automation.SCAN_WINDOW has no "2H"/"30m" entry today, a pre-existing gap from the Task
    4/6 wiring, not introduced here: `bt.scan(sym, "2H", only=("ICT",))` already raises this same KeyError on
    the current commit (verified empirically 2026-09-13). Callers must treat None as "cannot run the live ICT
    rules on this tf" and degrade to no-signal, not crash the whole tick over one setup."""
    try:
        bars, _ = bt.lr.scan_spec(tf)
        return bars
    except KeyError:
        return None


def ict_live_setups(side, candles, tf, sym):
    """ICT setups from the LIVE rules, mirroring bt.ict_setups_live (2026-09-13, Task 8). Before this, the
    runner built ICT setups with bt.all_pivots/bt.last_pivot/bt.find_ict/bt.ict_target -- the LEGACY algorithm --
    while bt.scan() validates ICT with the live scanner (scripts/ict-scan.py via scripts/live_rules.py), so the
    two disagreed by roughly an order of magnitude (docs/backtests/2026-09-13-live-rules-vs-legacy.md). This
    function asks the SAME live scanner the SAME question bt.ict_setups_live asks, at every bar of the window:
    live_rules.read_at() for the facts, live_rules.ict_scan.setup_candidate() for the setup, require
    complete + pd_ok, gate on bt.bias_allows(live_rules.bias_at(...)[0], side). The one difference from
    bt.ict_setups_live: that function decides whether the LIMIT eventually filled (a completed BACKTEST trade,
    via bt.fvg_fill); this one decides whether the LIMIT is STILL working as of the last closed bar (a NEW
    order for the runner to place) -- same fvg_fill call, opposite reading of its result: fvg_fill returning a
    bar index means the limit ALREADY triggered on an earlier bar (an earlier tick should already have placed
    and filled it -- not a new signal); still within its K-bar expiry with no fill and no stop-hit means it is
    still a working, placeable order.

    `sym` resolves which bias-reading dimensions are engaged for this symbol's market (bt.resolve_methods --
    htf_context.engaged_methods_for_market via /automation), exactly as the backtest does -- never a hardcoded
    default (see live_rules.read_at's own docstring for why). Returns [] rather than raising when `sym` is not
    given, when live never scans `tf` at all (ict_scan_bars() above), or once the window runs out -- one setup
    must not crash the tick for every other symbol."""
    if sym is None:
        return []
    if ict_scan_bars(tf) is None:
        return []
    methods = bt.resolve_methods(sym)
    H = [x["high"] for x in candles]; L = [x["low"] for x in candles]; Tm = [x["time"] for x in candles]
    n = len(candles)
    if n == 0:
        return []
    K = bt.P[tf]["K"]
    idx_of_time = {tt: j for j, tt in enumerate(Tm)}
    out = []; seen = set()
    for i in range(n):
        a = bt.lr.read_at(candles, i, tf, methods)
        if a is None:            # window not yet the full live window -- live would not have scanned here at all
            continue
        su = bt.lr.ict_scan.setup_candidate(a, bt.lr.window(candles, i, tf), bt.lr.setup_lookback(tf))
        if not su or not su.get("complete") or not su.get("pd_ok") or su["side"] != side:
            continue
        bias, _ = bt.lr.bias_at(candles, i, tf, methods, facts=a)
        if not bt.bias_allows(bias, su["side"]):
            continue
        key = (su["side"], su["sweep"]["time"], su["mss"]["time"])
        if key in seen:           # the same setup stays visible for many bars; take it once, at its first bar
            continue
        seen.add(key)
        mss_i = idx_of_time.get(su["mss"]["time"])
        if mss_i is None:
            continue
        entry = su["entry"]; stop = su["stop"]; target = su["target"]
        if (side == "long" and not target > entry) or (side == "short" and not target < entry):
            continue
        far = su["entry_models"]["fill"]   # ict-scan.py setup_candidate: the key is "entry_models", not "entries"
        fill = bt.fvg_fill(su["side"], mss_i, entry, far, stop, H, L, K, n)
        bars_left = (mss_i + K) - (n - 1)
        if fill is not None or bars_left < 0:
            continue          # already triggered on an earlier bar, or expired unfilled -- not a NEW order to place
        out.append(dict(time=Tm[i], vol_type=None, side=su["side"], sweep_bar=idx_of_time.get(su["sweep"]["time"]),
                        mss_bar=mss_i, mss_time=su["mss"]["time"], entry=entry, stop=stop, target=target,
                        expires_bar=mss_i + K, bars_left=bars_left, r_planned=abs(target - entry) / abs(entry - stop)))
    return out


def setups(method, side, candles, tf, ict_disp=False, ict_pd=False, std_origin="pivot", sym=None):
    """Every setup of `method`/`side` in the window whose LIMIT would still be working at the last closed bar.
    ICT (2026-09-13, Task 8): sourced from the LIVE rules -- see ict_live_setups() above -- migrated off the
    legacy bt.all_pivots/bt.find_ict/bt.ict_target proxies so the runner and bt.scan() agree on what an ICT
    setup is. `sym` is required for this path (method resolution, see ict_live_setups); it is otherwise unused.
    COMBINED/PARTIAL (unchanged, Task 8 dependency map): Spring/Upthrust proxy (R-bar border pierce, reclaim <=
    2 bars, volume type gate) + bt.find_ict confirmation -> LIMIT at the FVG edge; mirrors bt.scan's
    COMBINED/PARTIAL block. ict_disp / ict_pd / std_origin are the deck-faithful switches of
    backtest-methods.py (2026-09-12); ict_pd/std_origin no longer affect anything here (only the now-removed
    legacy ICT branch read them) but ict_disp still gates this branch's call into bt.find_ict via bt.OPTS,
    unchanged from before this migration. No ict_target parameter (2026-09-13 audit): its only reader,
    backtest-methods.py's ict_target(), was deleted -- its only caller was the legacy ICT branch removed
    alongside it, and this COMBINED/PARTIAL branch's target has always been the range border (see `target =`
    below), never bt.ict_target()'s output."""
    if method == "ICT":
        return ict_live_setups(side, candles, tf, sym)
    p = bt.P[tf]; R, K = p["R"], p["K"]
    H = [x["high"] for x in candles]; L = [x["low"] for x in candles]; C = [x["close"] for x in candles]; V = [x.get("volume", 0) for x in candles]
    O = [x["open"] for x in candles]; T = [x["time"] for x in candles]; n = len(candles)
    PH = bt.all_pivots(H, "high"); PL = bt.all_pivots(L, "low")
    out = []; last_i = -99; prev = {k: bt.OPTS[k] for k in ("ict_disp", "ict_pd", "std_origin")}
    bt.OPTS.update(ict_disp=bool(ict_disp), ict_pd=bool(ict_pd), std_origin=std_origin or "pivot")
    try:
        for i in range(R + 6, n):
            support = min(L[i - R:i - 5]); resistance = max(H[i - R:i - 5])
            if resistance <= support or i - last_i <= 5:
                continue
            if side == "long":
                if not L[i] < support:
                    continue
                rec = next((j for j in range(i, min(i + 3, n)) if C[j] > support), None)
            else:
                if not H[i] > resistance:
                    continue
                rec = next((j for j in range(i, min(i + 3, n)) if C[j] < resistance), None)
            if rec is None:
                continue
            last_i = i
            ext = min(L[i:rec + 1]) if side == "long" else max(H[i:rec + 1])
            avg20 = sum(V[i - 20:i]) / 20 if i >= 20 else 0
            ratio = V[i] / avg20 if avg20 else None
            vt = bt.vtype(ratio); rec_ratio = (V[rec] / avg20) if avg20 else None
            if not (vt in (1, 2) or (vt == 3 and rec_ratio is not None and rec_ratio >= bt.VOL["high_min_ratio"])):
                continue
            ict = bt.find_ict(side, i, rec, H, L, C, K, n, PH, PL, O=O)
            if not ict:
                continue
            mss, edge, far = ict
            stop = ext * (1 - STOP_BUFFER_PCT) if side == "long" else ext * (1 + STOP_BUFFER_PCT)
            target = resistance if side == "long" else support
            base = dict(time=T[i], vol_type=vt)
            if (side == "long" and not target > edge) or (side == "short" and not target < edge):
                continue
            if mss < n - 1 - K:
                continue
            touched = any((L[j] <= edge) if side == "long" else (H[j] >= edge) for j in range(mss + 1, n))
            stopped = any((L[j] <= stop) if side == "long" else (H[j] >= stop) for j in range(mss + 1, n))
            if touched or stopped:
                continue
            out.append(dict(base, side=side, sweep_bar=i, mss_bar=mss, mss_time=T[mss], entry=edge, stop=stop, target=target,
                            expires_bar=mss + K, bars_left=(mss + K) - (n - 1), r_planned=abs(target - edge) / abs(edge - stop)))
    finally:
        bt.OPTS.update(prev)
    return out


def setups_wyckoff(method, side, candles, tf):
    """WYCKOFF (proxy) and WYCKOFF-BOOK entries that fire on the LAST CLOSED bar (market at its close), mirroring bt.scan.
    Returns dicts with entry_now=True; no limit, no expiry. Only the last bar can be an entry -- earlier bars were our earlier ticks."""
    p = bt.P[tf]; R, T = p["R"], p["T"]
    H = [x["high"] for x in candles]; L = [x["low"] for x in candles]; C = [x["close"] for x in candles]; V = [x.get("volume", 0) for x in candles]
    O = [x["open"] for x in candles]; Tm = [x["time"] for x in candles]; n = len(candles); last = n - 1; out = []
    if method == "WYCKOFF":
        last_i = -99
        for i in range(R + 6, n):
            support = min(L[i - R:i - 5]); resistance = max(H[i - R:i - 5])
            if resistance <= support or i - last_i <= 5:
                continue
            if side == "long":
                if not L[i] < support:
                    continue
                rec = next((j for j in range(i, min(i + 3, n)) if C[j] > support), None)
            else:
                if not H[i] > resistance:
                    continue
                rec = next((j for j in range(i, min(i + 3, n)) if C[j] < resistance), None)
            if rec is None:
                continue
            last_i = i
            ext = min(L[i:rec + 1]) if side == "long" else max(H[i:rec + 1])
            avg20 = sum(V[i - 20:i]) / 20 if i >= 20 else 0
            ratio = V[i] / avg20 if avg20 else None
            vt = bt.vtype(ratio); rec_ratio = (V[rec] / avg20) if avg20 else None
            stop = ext * (1 - STOP_BUFFER_PCT) if side == "long" else ext * (1 + STOP_BUFFER_PCT)
            target = resistance if side == "long" else support; tr = resistance - support
            w_bar = None
            if vt == 1 or (vt == 3 and rec_ratio is not None and rec_ratio >= bt.VOL["high_min_ratio"]):
                w_bar = rec
            else:
                for j in range(rec + 1, min(rec + 1 + T, n)):
                    if (side == "long" and L[j] <= stop) or (side == "short" and H[j] >= stop):
                        break
                    ok = (ext <= L[j] <= support + tr / 3 and V[j] < V[i] and C[j] >= L[j] + 0.5 * (H[j] - L[j])) if side == "long" else \
                         (resistance - tr / 3 <= H[j] <= ext and V[j] < V[i] and C[j] <= H[j] - 0.5 * (H[j] - L[j]))
                    if ok:
                        w_bar = j; break
            if w_bar == last:
                out.append(dict(time=Tm[i], vol_type=vt, side=side, entry_now=True, entry=C[last], stop=stop, target=target, mss_time=None, bars_left=0,
                                r_planned=abs(target - C[last]) / abs(C[last] - stop)))
        return [o for o in out if (o["side"] == "long" and o["target"] > o["entry"] > o["stop"]) or (o["side"] == "short" and o["target"] < o["entry"] < o["stop"])]
    # WYCKOFF-BOOK: structures detected on the window (CHoCH gate, TR from SC/AR, Phase B, Spring vs Shakeout, VP veto, Test, Phase D)
    W.PARAMS["spring_max_bars_outside"] = p["sob"]
    recs = W.detect_accumulations(O, H, L, C, V) if side == "long" else W.detect_distributions(O, H, L, C, V)
    for r in recs:
        tr = r["tr_hi"] - r["tr_lo"]; t0 = Tm[r["spring"] if r["spring"] is not None else r["sos"]]
        if r["path"] == "spring" and not r["shakeout"] and not r["abandon"] and not r["sot_too_strong"] and r["vol_type"] in (1, 2, 3):
            rec = r["reclaim"]; vt = r["vol_type"]; rr = r["rec_ratio"]
            w_bar = rec if (vt == 1 or (vt == 3 and rr is not None and rr >= bt.VOL["high_min_ratio"])) else r["test"]
            if w_bar == last:
                stop = r["spring_low"] * (1 - STOP_BUFFER_PCT) if side == "long" else r["spring_low"] * (1 + STOP_BUFFER_PCT)
                target = r["tr_hi"] if side == "long" else r["tr_lo"]
                if (side == "long" and target > C[last] > stop) or (side == "short" and target < C[last] < stop):
                    out.append(dict(time=t0, vol_type=vt, side=side, entry_now=True, entry=C[last], stop=stop, target=target, mss_time=None, bars_left=0, leg="spring",
                                    r_planned=abs(target - C[last]) / abs(C[last] - stop)))
        if r["bu"] and r["bu"]["bar"] == last:
            stop = r["bu"]["low"] * (1 - STOP_BUFFER_PCT) if side == "long" else r["bu"]["low"] * (1 + STOP_BUFFER_PCT)
            target = r["tr_hi"] + W.PARAMS["d_target_tr"] * tr if side == "long" else r["tr_lo"] - W.PARAMS["d_target_tr"] * tr
            if (side == "long" and target > C[last] > stop) or (side == "short" and target < C[last] < stop):
                out.append(dict(time=t0 + "-D", vol_type=r["vol_type"], side=side, entry_now=True, entry=C[last], stop=stop, target=target, mss_time=None, bars_left=0, leg="phase_d",
                                r_planned=abs(target - C[last]) / abs(C[last] - stop)))
    return out


def htf_pass(sym, side, candles_htf, htf_tf):
    """Higher-timeframe boundary gate. Migrated onto the LIVE bias read (2026-09-13, Task 8): bt.bias_allows
    over bt.lr.bias_at (scripts/htf_context.py via scripts/live_rules.py) replaces the pre-2026-09-13
    rolling-percentile proxy (bt.htf_allows over a percentile series this function used to compute inline from
    `candles_htf`). `candles_htf` is already causal (fetch_candles/drop_forming upstream), so its LAST element
    IS the last CLOSED bar of `htf_tf` as of this tick -- exactly the bar a live bias read would use; unlike the
    old proxy, no `at_time` lookup is needed to find "the htf bar that had closed by the signal's own time".

    Returns None -- not False -- when the live rules cannot be asked here at ALL: htf_tf has no bt.P entry, no
    candles were fetched, or automation.SCAN_WINDOW has no entry for htf_tf (a pre-existing gap from Task 4/6
    for "2H"/"30m" -- bt.scan() already raises the same KeyError for those timeframes today; ict_scan_bars()
    above is the same guard used for the ICT setup path). None means "structurally unable to judge", which is
    kept distinct from False ("judged and refused") purely for the LOGGED record -- the two are different facts
    worth telling apart later. It is NOT permission: the caller (tick()) blocks a setup that declared htf:true
    on anything other than an explicit True (2026-09-13, Task 8 fix round 1 -- a bare `is False` check used to
    let None sail through as if the gate had opened, which is a fail-OPEN order gate; every other gate this
    task touched fails closed on missing data -- scan-loop.sh, bias_allows' own neutral/unknown refusal,
    live_rules.window raising rather than clamping -- and htf_pass's caller now matches that)."""
    if not candles_htf or htf_tf not in bt.P:
        return None
    if ict_scan_bars(htf_tf) is None:
        return None
    methods = bt.resolve_methods(sym)
    bias, _ = bt.lr.bias_at(candles_htf, len(candles_htf) - 1, htf_tf, methods)
    return bt.bias_allows(bias, side)


# ---------------------------------------------------------------- sizing and orders
_MIN_NOTIONAL = {}; _MT5_SYMBOLS = {}


def min_notional(sym):
    if sym not in _MIN_NOTIONAL:
        try:
            m = re.search(r"'MIN_NOTIONAL'.*?'notional': '([0-9.]+)'", order("filters", sym))
            _MIN_NOTIONAL[sym] = float(m.group(1)) if m else 50.0
        except Exception:
            _MIN_NOTIONAL[sym] = 50.0
    return _MIN_NOTIONAL[sym]


def mt5_symbol(sym):
    """Contract data the bridge EA publishes (tick_size, tick_value, volume_min/max/step, digits)."""
    if sym not in _MT5_SYMBOLS:
        _MT5_SYMBOLS[sym] = mt5_json("symbol", sym)
    return _MT5_SYMBOLS[sym]


def client_id(setup_id, sym, sig):
    return "t5-" + hashlib.sha1(f"{setup_id}|{sym}|{sig['side']}|{sig['time']}".encode()).hexdigest()[:20]


def size(equity, entry, stop, risk_mult, leverage=LEVERAGE):
    r = abs(entry - stop); risk_usd = equity * RISK_PCT * risk_mult; qty = risk_usd / r
    cap = equity * NOTIONAL_CAP_PCT * leverage
    if qty * entry > cap:
        qty = cap / entry
    return qty, risk_usd


def mt5_lots(sym, equity, entry, stop, risk_mult):
    """Lots so that the stop distance loses risk_usd: risk / (ticks in the stop x tick_value). Rounded DOWN to volume_step."""
    info = mt5_symbol(sym); risk_usd = equity * RISK_PCT * risk_mult
    ticks = abs(entry - stop) / float(info["tick_size"]); per_lot = ticks * float(info["tick_value"])
    lots = risk_usd / per_lot if per_lot > 0 else 0.0
    step = float(info["volume_step"]); lots = int(lots / step) * step
    lots = min(lots, float(info["volume_max"]))
    return round(lots, 8), risk_usd, per_lot


def plan_of(sym, st, sig, qty, px, stop, tp, risk_usd):
    return dict(symbol=sym, strategy=st["id"], tf=st["tf"], method=st["method"], side=sig["side"].upper(), qty=qty, price=px, stop=stop, tp=tp,
                leverage=LEVERAGE if st["execution"] == "futures" else 1, risk_usd=round(risk_usd, 2), notional=round(float(qty) * float(px), 2),
                sweep_time=sig["time"], mss_time=sig["mss_time"], expires_bar_left=sig["bars_left"], htf_pass=sig["htf_pass"], r_planned=round(sig["r_planned"], 2),
                execution=st["execution"], mgmt=st.get("mgmt", "be"))


def place_limit(sym, st, sig, equity, risk_mult, live):
    long = sig["side"] == "long"; venue = st["execution"]
    if venue == "mt5":
        info = mt5_symbol(sym); d = int(info.get("digits", 2))
        lots, risk_usd, per_lot = mt5_lots(sym, equity, sig["entry"], sig["stop"], risk_mult)
        px = f"{sig['entry']:.{d}f}"; stop = f"{sig['stop']:.{d}f}"; tp = f"{sig['target']:.{d}f}"
        plan = plan_of(sym, st, sig, f"{lots:g}", px, stop, tp, min(risk_usd, lots * per_lot))
        if lots < float(info["volume_min"]):
            log("skip", venue="mt5", why=f"lots {lots:g} below volume_min {info['volume_min']} (risk too small for this stop)", **plan); return None
        if not live:
            log("dry_run_limit", venue="mt5", **plan); return None
        cid = client_id(st["id"], sym, sig)
        o = mt5_json("limit", sym, "buy" if long else "sell", f"{lots:g}", px, stop, tp, cid)
        if not o.get("ok"):
            log("rejected", venue="mt5", note=f"MT5 retcode {o.get('retcode')} {o.get('comment')}", **plan); return None
        pend = dict(plan, order_id=o["ticket"], client_id=cid, placed_at=iso(now()), bars_waited=0)
        log("limit_placed", venue="mt5", **pend)
        return pend
    qty, risk_usd = size(equity, sig["entry"], sig["stop"], risk_mult)
    qty_r = order("round-qty", sym, f"{qty:.8f}").strip(); px_r = order("round-price", sym, f"{sig['entry']:.8f}").strip()
    stop_r = order("round-price", sym, f"{sig['stop']:.8f}").strip(); tp_r = order("round-price", sym, f"{sig['target']:.8f}").strip()
    plan = plan_of(sym, st, sig, qty_r, px_r, stop_r, tp_r, min(risk_usd, float(qty_r) * abs(float(px_r) - float(stop_r))))
    if float(qty_r) * float(px_r) < min_notional(sym):
        log("skip", why=f"notional below exchange minimum {min_notional(sym)}", **plan); return None
    if not live:
        log("dry_run_limit", **plan); return None
    sh(ORDER, "set-margin-type", sym, "ISOLATED", check=False)
    order("set-leverage", sym, str(LEVERAGE))
    cid = client_id(st["id"], sym, sig)
    try:
        o = order_json("open-long-limit" if long else "open-short-limit", sym, qty_r, px_r, cid)
    except RuntimeError as e:
        if "-5022" in str(e):
            log("gtx_rejected", note="post-only limit would have taken liquidity -- signal dropped", **plan); return None
        o = order_json("order-by-client-id", sym, cid)
        if not o.get("orderId"):
            raise
    if o.get("status") == "EXPIRED" or not o.get("orderId"):
        log("gtx_rejected", note="post-only limit would have taken liquidity -- signal dropped", **plan); return None
    pend = dict(plan, order_id=o["orderId"], client_id=cid, placed_at=iso(now()), bars_waited=0)
    log("limit_placed", **pend)
    return pend


def place_market(sym, st, sig, equity, risk_mult, live):
    """Wyckoff entry at the close of the entry bar: MARKET order, then the protective orders (futures) / SL+TP attached (MT5)."""
    long = sig["side"] == "long"; venue = st["execution"]
    if venue == "mt5":
        info = mt5_symbol(sym); d = int(info.get("digits", 2))
        lots, risk_usd, per_lot = mt5_lots(sym, equity, sig["entry"], sig["stop"], risk_mult)
        stop = f"{sig['stop']:.{d}f}"; tp = f"{sig['target']:.{d}f}"
        plan = plan_of(sym, st, sig, f"{lots:g}", f"{sig['entry']:.{d}f}", stop, tp, min(risk_usd, lots * per_lot)); plan["order_type"] = "market"
        if lots < float(info["volume_min"]):
            log("skip", venue="mt5", why=f"lots {lots:g} below volume_min {info['volume_min']}", **plan); return None
        if not live:
            log("dry_run_market", venue="mt5", **plan); return None
        cid = client_id(st["id"], sym, sig)
        o = mt5_json("market", sym, "buy" if long else "sell", f"{lots:g}", stop, tp, cid)
        if not o.get("ok"):
            log("rejected", venue="mt5", note=f"MT5 retcode {o.get('retcode')} {o.get('comment')}", **plan); return None
        pend = dict(plan, order_id=o["ticket"], client_id=cid, placed_at=iso(now()), bars_waited=0, price=f"{float(o.get('price') or sig['entry']):.{d}f}")
        return open_position(sym, pend, float(o.get("volume") or lots), float(o.get("price") or sig["entry"]), live, position_ticket=o.get("ticket"))
    qty, risk_usd = size(equity, sig["entry"], sig["stop"], risk_mult)
    qty_r = order("round-qty", sym, f"{qty:.8f}").strip(); px_r = order("round-price", sym, f"{sig['entry']:.8f}").strip()
    stop_r = order("round-price", sym, f"{sig['stop']:.8f}").strip(); tp_r = order("round-price", sym, f"{sig['target']:.8f}").strip()
    plan = plan_of(sym, st, sig, qty_r, px_r, stop_r, tp_r, min(risk_usd, float(qty_r) * abs(float(px_r) - float(stop_r)))); plan["order_type"] = "market"
    if float(qty_r) * float(px_r) < min_notional(sym):
        log("skip", why=f"notional below exchange minimum {min_notional(sym)}", **plan); return None
    if not live:
        log("dry_run_market", **plan); return None
    sh(ORDER, "set-margin-type", sym, "ISOLATED", check=False)
    order("set-leverage", sym, str(LEVERAGE))
    o = order_json("open-long" if long else "open-short", sym, qty_r)
    if not o.get("orderId"):
        log("rejected", note="market order not accepted", **plan); return None
    avg_px = float(o.get("avgPrice") or 0) or float(px_r); filled = float(o.get("executedQty") or qty_r)
    pend = dict(plan, order_id=o["orderId"], client_id=client_id(st["id"], sym, sig), placed_at=iso(now()), bars_waited=0, price=f"{avg_px:.8f}")
    return open_position(sym, pend, filled, avg_px, live)


class UnprotectedPositionError(RuntimeError):
    """The one case a naked leveraged position may exist: a filled entry's protective stop could not be placed
    AND the emergency close (MARKET reduceOnly) also failed. Callers MUST halt hard on this (write the STOP
    kill switch) rather than let it surface as an ordinary connector error -- PILOT-13, 2026-09-13 incident."""
    def __init__(self, symbol, qty, reason):
        self.symbol = symbol; self.qty = qty
        super().__init__(f"UNPROTECTED POSITION {symbol} qty={qty}: {reason}")


def _emergency_close(sym):
    """Best-effort MARKET reduceOnly flatten of `sym` right after a protective-order failure. Re-derives qty
    from the exchange's own position-risk (via close-position) rather than trusting our fill record, since the
    exchange is the source of truth for what is actually open. Returns (True, detail) on success, else
    (False, error)."""
    try:
        return True, order_json("close-position", sym)
    except Exception as e:
        return False, str(e)[:300]


def open_position(sym, pend, filled_qty, avg_px, live, position_ticket=None):
    """PILOT-13 (2026-09-13): placing the protective stop is part of opening a position, not a step after it.
    A stop-market failure here used to raise straight out of this function AFTER the entry had already filled
    on the exchange -- leaving a naked position while callers' state bookkeeping (pending/positions) never ran.
    Now: a stop-market failure triggers an immediate emergency close (MARKET reduceOnly) before anything can
    surface; only if THAT also fails do we raise UnprotectedPositionError, which callers must turn into a hard
    halt (see tick()). A take-profit failure is handled differently on purpose (see below): it does NOT unwind
    the position, because the stop -- already placed at this point -- is what bounds the loss; a missing
    take-profit only forgoes an automatic exit at the target, not protection against further loss."""
    venue = pend["execution"]; long = pend["side"] == "LONG"
    sl = tp = {}
    if venue == "futures" and live:
        prot = "SELL" if long else "BUY"
        try:
            sl = order_json("stop-market", sym, prot, pend["stop"])
        except Exception as e:
            stop_err = str(e)[:200]
            closed, detail = _emergency_close(sym)
            if not closed:
                raise UnprotectedPositionError(sym, filled_qty, f"stop-market failed ({stop_err}) AND emergency close also failed ({detail})")
            log("protection_failed_closed", venue=venue, symbol=sym, qty=filled_qty, entry=avg_px, stage="stop",
                reason=stop_err, close=detail,
                note="protective stop could not be placed -- the just-filled entry was closed immediately (market, reduceOnly), no naked position left open")
            return None
        try:
            tp = order_json("take-profit-market", sym, prot, pend["tp"])
        except Exception as e:
            tp = {}
            log("tp_placement_failed", venue=venue, symbol=sym, qty=filled_qty, reason=str(e)[:200],
                note="stop is already in place and bounds the loss -- a missing take-profit only forgoes an "
                     "automatic exit at the target, so the position is left open, not unwound")
    r = abs(avg_px - float(pend["stop"]))
    pos = dict(side=pend["side"], strategy=pend["strategy"], tf=pend["tf"], method=pend["method"], execution=venue, mgmt=pend["mgmt"],
               qty=f"{filled_qty:.8f}".rstrip("0").rstrip("."), entry=avg_px, entry_order=pend["order_id"], client_id=pend.get("client_id"),
               position_ticket=position_ticket, stop=float(pend["stop"]), tp=float(pend["tp"]), stop_order=sl.get("orderId"), tp_order=tp.get("orderId"),
               leverage=pend["leverage"], opened_at=iso(now()), bars=0, risk_usd=round(r * filled_qty, 2), be=False, be_level=(avg_px + r) if long else (avg_px - r),
               htf_pass=pend["htf_pass"], sweep_time=pend["sweep_time"], mss_time=pend["mss_time"], risk_pct=RISK_PCT)
    log("entry", venue=venue, symbol=sym, market=("mt5_demo" if venue == "mt5" else MARKET_LABEL), env=ENV_NAME, **pos)
    return pos


def close_record(sym, pos, px, via, qty, pnl=None):
    sign = 1 if pos["side"] == "LONG" else -1
    if pnl is None:
        pnl = (px - pos["entry"]) * float(qty) * sign
    return dict(symbol=sym, side=pos["side"], strategy=pos["strategy"], tf=pos["tf"], execution=pos["execution"], exit=px, via=via, pnl=round(pnl, 2),
                r=round(pnl / pos["risk_usd"], 2) if pos["risk_usd"] else None, entry=pos["entry"], qty=qty, opened_at=pos["opened_at"], closed_at=iso(now()),
                htf_pass=pos["htf_pass"], be=pos["be"])


def manage_pending(sym, pend, live, bars_elapsed):
    """('filled', qty, px, position_ticket) | ('waiting', ...) | ('gone', ...)."""
    if not live:
        return "waiting", None, None, None
    if pend["execution"] == "mt5":
        st = mt5_json("order-status", str(pend["order_id"]))
        if st.get("state") == "filled":
            return "filled", float(st.get("volume") or pend["qty"]), float(st.get("price") or pend["price"]), st.get("position_ticket")
        pend["bars_waited"] = pend.get("bars_waited", 0) + bars_elapsed
        if st.get("state") in ("canceled", "expired", "rejected", "missing"):
            return "gone", None, None, None
        if pend["bars_waited"] >= pend["expires_bar_left"] + 1:
            mt5_json("cancel", str(pend["order_id"])); log("limit_expired", venue="mt5", symbol=sym, order_id=pend["order_id"])
            st = mt5_json("order-status", str(pend["order_id"]))
            if st.get("state") == "filled":
                return "filled", float(st.get("volume") or pend["qty"]), float(st.get("price") or pend["price"]), st.get("position_ticket")
            return "gone", None, None, None
        return "waiting", None, None, None
    st = order_json("order-status", sym, str(pend["order_id"])); status = st.get("status"); ex = float(st.get("executedQty") or 0)
    if status == "FILLED":
        return "filled", ex, float(st.get("avgPrice") or pend["price"]), None
    pend["bars_waited"] = pend.get("bars_waited", 0) + bars_elapsed
    if status in ("CANCELED", "EXPIRED", "REJECTED"):
        return ("filled", ex, float(st.get("avgPrice") or pend["price"]), None) if ex > 0 else ("gone", None, None, None)
    if pend["bars_waited"] >= pend["expires_bar_left"] + 1:
        sh(ORDER, "cancel-order", sym, str(pend["order_id"]), check=False)
        st = order_json("order-status", sym, str(pend["order_id"])); ex = float(st.get("executedQty") or 0)
        log("limit_expired", symbol=sym, order_id=pend["order_id"], executed=ex)
        return ("filled", ex, float(st.get("avgPrice") or pend["price"]), None) if ex > 0 else ("gone", None, None, None)
    return "waiting", None, None, None


def manage_position(sym, pos, candles, live, bars_elapsed):
    """Exit detection, breakeven on a closed candle, time stop. Returns a close record or None."""
    horizon = bt.P[pos["tf"]]["H"]; venue = pos["execution"]; long = pos["side"] == "LONG"
    since = [x for x in candles if x["time"] >= pos["opened_at"][:16] + ":00Z"]
    if venue == "mt5":
        if live:
            st = mt5_json("position-status", str(pos["position_ticket"] or pos["entry_order"]))
            if st.get("state") == "closed":
                via = "TP" if st.get("reason") == "tp" else ("BE" if (pos["be"] and st.get("reason") == "sl") else ("SL" if st.get("reason") == "sl" else "OTHER"))
                return close_record(sym, pos, float(st.get("price_close") or 0), via, pos["qty"], pnl=float(st.get("profit") or 0))
        pos["bars"] += bars_elapsed
        if pos.get("mgmt") == "be" and not pos["be"] and any((x["high"] >= pos["be_level"]) if long else (x["low"] <= pos["be_level"]) for x in since):
            if live:
                r = mt5_json("modify", str(pos["position_ticket"] or pos["entry_order"]), f"{pos['entry']:.5f}", f"{pos['tp']:.5f}")
                if r.get("ok"):
                    pos["stop"] = pos["entry"]; pos["be"] = True; log("breakeven", venue="mt5", symbol=sym, stop=pos["stop"])
            else:
                pos["stop"] = pos["entry"]; pos["be"] = True; log("dry_run_breakeven", venue="mt5", symbol=sym, stop=pos["stop"])
        if pos["bars"] >= horizon and live:
            r = mt5_json("close", str(pos["position_ticket"] or pos["entry_order"]))
            if r.get("ok"):
                return close_record(sym, pos, float(r.get("price") or 0), "TIME", pos["qty"], pnl=float(r.get("profit") or 0))
        return None
    for leg in ("tp_order", "stop_order"):
        oid = pos.get(leg)
        if not oid or not live:
            continue
        st = order_json("order-status", sym, str(oid))
        if st.get("status") == "FILLED":
            px = float(st.get("avgPrice") or 0) or float(st.get("stopPrice") or pos["tp" if leg == "tp_order" else "stop"])
            sh(ORDER, "cancel-all", sym, check=False)
            return close_record(sym, pos, px, "TP" if leg == "tp_order" else ("BE" if pos["be"] else "SL"), st.get("executedQty") or pos["qty"])
    pos["bars"] += bars_elapsed
    if pos.get("mgmt") == "be" and not pos["be"] and any((x["high"] >= pos["be_level"]) if long else (x["low"] <= pos["be_level"]) for x in since):
        new_stop = order("round-price", sym, f"{pos['entry']:.8f}").strip() if live else f"{pos['entry']:.8f}"
        if live:
            prot = "SELL" if long else "BUY"
            new = order_json("stop-market", sym, prot, new_stop)        # new stop FIRST, confirmed, then cancel the old (PILOT-12)
            if new.get("orderId") and order_json("order-status", sym, str(new["orderId"])).get("status") in ("NEW", "PARTIALLY_FILLED", "FILLED"):
                if pos.get("stop_order"):
                    sh(ORDER, "cancel-order", sym, str(pos["stop_order"]), check=False)
                pos["stop_order"] = new["orderId"]; pos["stop"] = float(new_stop); pos["be"] = True
                log("breakeven", symbol=sym, stop=pos["stop"], order_id=new["orderId"])
        else:
            pos["stop"] = float(new_stop); pos["be"] = True; log("dry_run_breakeven", symbol=sym, stop=pos["stop"])
    if pos["bars"] >= horizon:
        if not live:
            return None
        sh(ORDER, "cancel-all", sym, check=False)
        o = order_json("close-position", sym)
        px = float(o.get("avgPrice") or 0) or float(order_json("price", sym)["price"])
        return close_record(sym, pos, px, "TIME", o.get("executedQty") or pos["qty"])
    return None


# ---------------------------------------------------------------- tick
def halt(s, why):
    s["halted"] = dict(at=iso(now()), why=why)
    os.makedirs(PILOT_DIR, exist_ok=True)
    open(STOP, "a").write(f"{iso(now())} strategy-runner halt: {why}\n")
    log("halt", why=why, stop_file=os.path.relpath(STOP, ROOT))


def venue_of(sym):
    return "futures" if sym in CRYPTO else "mt5"


def tick(live, tick_time=None, ignore_gate=False):
    s = load_state(); setups_cfg = load_setups()
    # NO early return on an empty selection: steps 1 and 2 below manage positions and pending orders that were
    # opened under a previous configuration, and a resting futures limit carries no stop until open_position()
    # sees it fill. Returning here would leave it naked. Spec §2.2.
    dry_override = (not live) and ignore_gate
    if os.path.exists(STOP) and not dry_override:
        for sym, pend in list(s["pending"].items()):
            if live:
                (mt5_json("cancel", str(pend["order_id"])) if pend["execution"] == "mt5" else sh(ORDER, "cancel-order", sym, str(pend["order_id"]), check=False))
            log("stop_cancel_pending", venue=pend["execution"], symbol=sym, order_id=pend.get("order_id")); del s["pending"][sym]
        save_state(s); log("halt", why="STOP file present", open_positions=list(s["positions"])); return
    gate = automation_gate()
    if gate and not dry_override:
        log("halt", why=gate); return
    if dry_override and (gate or os.path.exists(STOP)):
        log("note", why=f"dry run ignoring the gate/kill switch ({gate or 'STOP file'}) -- no order can be sent in this mode")
    t = tick_time or now(); today = t.strftime("%Y-%m-%d")
    if s["day"] != today:
        s["day"] = today; s["trades_today"] = {}
    venues_used = {st["execution"] for st in setups_cfg} | {p["execution"] for p in list(s["positions"].values()) + list(s["pending"].values())}
    # Two readings per venue, deliberately kept separate (2026-09-13 fix):
    #   equity        -- true account equity. ONLY input to the EQUITY_HALT_FRAC guard and its equity_start
    #                    baseline. Margin reserved by a resting order/open position is still the trader's
    #                    money, not a loss -- the guard must not fire on it.
    #   sizing_equity -- free margin for futures (Binance availableBalance, via usdt_free()), true equity for
    #                    MT5 (mt5_equity() -- no free-margin distinction on that venue, see mt5_equity()).
    #                    Feeds place_market()/place_limit() exactly as before this fix; sizing/order-placement
    #                    behaviour is intentionally UNCHANGED here -- do not fold this into `equity` above.
    equity = {}
    sizing_equity = {}
    for v in venues_used:
        try:
            if live:
                if v == "futures":
                    bal = usdt_balance(); equity[v] = bal["equity"]; sizing_equity[v] = bal["free"]
                else:
                    equity[v] = sizing_equity[v] = mt5_equity()
            else:
                equity[v] = sizing_equity[v] = s["venues"][v]["equity_start"] or 10000.0
            s["errors"] = 0
        except Exception as e:
            s["errors"] += 1; log("error", venue=v, where="balance", msg=str(e)[:200])
            if s["errors"] >= ERROR_HALT:
                halt(s, f"{ERROR_HALT} consecutive connector errors")
            save_state(s); return
        # LIVE ONLY. A dry run reads a NOTIONAL equity (the `or 10000.0` above), so seeding the baseline from it
        # poisons the live halt check: the next live tick compares the real balance against a number that was never
        # real and halts instantly. (That is exactly what happened on 2026-09-12 -- a dry run wrote equity_start=10000
        # into the shared state file while the testnet account held 5000, and the next live tick halted at once.)
        # For the same reason a dry run must never reach halt(), which writes the STOP kill switch.
        if not live:
            continue
        if s["venues"][v]["equity_start"] is None:
            s["venues"][v]["equity_start"] = equity[v]
        if equity[v] <= EQUITY_HALT_FRAC * s["venues"][v]["equity_start"]:
            halt(s, f"{v}: equity {equity[v]:.2f} <= {EQUITY_HALT_FRAC:.0%} of start {s['venues'][v]['equity_start']:.2f}"); save_state(s); return
    last = parse_t(s["last_tick"]) if s.get("last_tick") else None
    bars_elapsed = {tf: (max(1, int((t - last).total_seconds() // TF_SEC[tf])) if last else 1) for tf in TF_SEC}
    need = set()
    for st in setups_cfg:
        if due(st["tf"], t, st["market"]):
            for sym in enabled_symbols(st["market"]):
                need.add((st["market"], sym, st["tf"]))
                if HTF_OF.get(st["tf"]):
                    need.add((st["market"], sym, HTF_OF[st["tf"]]))
    for sym, p in list(s["positions"].items()) + list(s["pending"].items()):
        need.add(("crypto" if sym in CRYPTO else "cfd", sym, p["tf"]))
    # htf_pass() and ict_live_setups() both read scripts/live_rules.py now (2026-09-13, Task 8), which needs its
    # OWN trailing window per tf (automation.SCAN_WINDOW, up to 576 bars) -- larger than WINDOW (300), which
    # stays enough for WYCKOFF/WYCKOFF-BOOK/COMBINED's own setup detection. Widen the fetch for exactly the
    # (market, tf) pairs live_rules will be asked about -- an ICT setup's own entry tf, and EVERY setup's HTF_OF
    # tf (htf_pass runs for every method, not just ICT) -- so read_at()/bias_at() ever see a full window.
    # Non-ICT methods still see candles[...][-WINDOW:] at the point they're used below, so their input is
    # byte-identical to what fetch_candles(..., window=WINDOW) alone would have produced.
    wide_tf_bars = {}
    for st in setups_cfg:
        for cand_tf in (st["tf"] if st["method"] == "ICT" else None, HTF_OF.get(st["tf"])):
            if not cand_tf:
                continue
            b = ict_scan_bars(cand_tf)
            if b:
                key = (st["market"], cand_tf); wide_tf_bars[key] = max(wide_tf_bars.get(key, 0), b)
    candles = {}
    for market, sym, tf in sorted(need):
        b = wide_tf_bars.get((market, tf))
        try:
            candles[(sym, tf)] = fetch_candles(sym, tf, market, t, window=(max(WINDOW, b) if b else WINDOW))
        except Exception as e:
            log("error", venue=venue_of(sym), where=f"candles {sym} {tf}", msg=str(e)[:200])
    # 1. positions
    for sym in list(s["positions"]):
        pos = s["positions"][sym]
        try:
            rec = manage_position(sym, pos, candles.get((sym, pos["tf"]), []), live, bars_elapsed[pos["tf"]])
        except Exception as e:
            s["errors"] += 1; log("error", venue=pos["execution"], where=f"manage {sym}", msg=str(e)[:200]); continue
        if rec:
            vs = s["venues"][pos["execution"]]; vs["closed"].append(rec); del s["positions"][sym]
            vs["consec_losses"] = 0 if rec["pnl"] > 0 else (vs["consec_losses"] + 1 if rec["pnl"] < 0 else vs["consec_losses"])
            log("exit", venue=pos["execution"], **rec)
    # 2. pending limits
    for sym in list(s["pending"]):
        pend = s["pending"][sym]
        try:
            state, qty, px, pt = manage_pending(sym, pend, live, bars_elapsed[pend["tf"]])
        except Exception as e:
            s["errors"] += 1; log("error", venue=pend["execution"], where=f"pending {sym}", msg=str(e)[:200]); continue
        if state == "filled":
            try:
                pos = open_position(sym, pend, qty, px, live, pt)
            except UnprotectedPositionError as e:
                del s["pending"][sym]  # PILOT-13: never leave a stale pending entry once the exchange fill is known
                halt(s, str(e)); save_state(s); return
            del s["pending"][sym]
            s["trades_today"][sym] = s["trades_today"].get(sym, 0) + 1
            if pos:
                s["positions"][sym] = pos
        elif state == "gone":
            del s["pending"][sym]
    for v in VENUES:
        if s["venues"][v]["consec_losses"] >= CONSEC_LOSS_HALT:
            halt(s, f"{v}: {CONSEC_LOSS_HALT} consecutive losses"); save_state(s); return
    if s["errors"] >= ERROR_HALT:
        halt(s, f"{ERROR_HALT} consecutive connector errors"); save_state(s); return
    blackout = event_blackout(t)
    # 2b. reconcile with each venue before new risk (PILOT-06)
    foreign = set()
    if live:
        if "futures" in venues_used:
            try:
                for prow in order_json("position-risk"):
                    if abs(float(prow.get("positionAmt") or 0)) > 0 and prow["symbol"] not in s["positions"]:
                        foreign.add(prow["symbol"])
                for orow in order_json("open-orders"):
                    sym_o = orow["symbol"]
                    known = {str(s["pending"].get(sym_o, {}).get("order_id"))} | {str(s["positions"].get(sym_o, {}).get(k)) for k in ("stop_order", "tp_order")}
                    if str(orow.get("orderId")) not in known:
                        foreign.add(sym_o)
            except Exception as e:
                s["errors"] += 1; log("error", where="reconcile", msg=str(e)[:200]); foreign |= set(CRYPTO)
        if "mt5" in venues_used:
            try:
                snap = mt5_json("state")
                mine = {str(p.get("position_ticket")) for p in s["positions"].values()} | {str(p.get("entry_order")) for p in s["positions"].values()} | {str(p["order_id"]) for p in s["pending"].values()}
                for prow in snap.get("positions", []):
                    if str(prow.get("ticket")) not in mine and str(prow.get("order_ticket")) not in mine:
                        foreign.add(prow["symbol"])
                for orow in snap.get("orders", []):
                    if str(orow.get("ticket")) not in mine:
                        foreign.add(orow["symbol"])
            except Exception as e:
                s["errors"] += 1; log("error", venue="mt5", where="reconcile", msg=str(e)[:200]); foreign |= set(CFD)
        if foreign:
            log("reconcile", note="symbols with venue state this runner does not own -- no new entries there", symbols=sorted(foreign))
    # 3. signals -- the preset filters NEW entries only (spec §4.3); steps 1 and 2 above are never filtered.
    # Read AUTOMATION_CONFIG once for the whole tick and reuse per-market dims, rather than re-opening/re-parsing
    # the file inside allowed_methods() on every setup below. On a read failure use None (not {}) per market so
    # allowed_methods() re-tries and falls through to its OWN except-Exception fallback (set(METHODS), fail-OPEN
    # -- "unconfigured = behave exactly as before this switch existed"). Passing {} here would fail CLOSED
    # instead: runner_methods({}) is the empty set because every runner method requires >=1 dimension, so every
    # method would look preset-blocked -- the opposite of allowed_methods()'s own documented fallback. Not
    # reachable on the live path (automation_gate() already refuses a tick on a missing/unreadable config), but
    # the two fallbacks must still agree.
    try:
        _cfg = json.load(open(AUTOMATION_CONFIG, encoding="utf-8"))
        _dims_by_market = {m: _cfg.get("markets", {}).get(m, {}).get("dimensions", {}) for m in ("crypto", "cfd")}
    except Exception:
        _dims_by_market = {"crypto": None, "cfd": None}
    for st in setups_cfg:
        if not due(st["tf"], t, st["market"]):
            continue
        if st["method"] not in allowed_methods(st["market"], _dims_by_market.get(st["market"])):
            log("preset_filtered", setup=st["id"], market=st["market"], method=st["method"],
                why="method not permitted by the current method preset")
            continue
        # 2026-09-13, Task 8 fix round 1: ict_live_setups() silently returns [] when live never scans this
        # setup's entry tf (automation.SCAN_WINDOW has no "2H"/"30m" entry). Silent-empty in an order loop looks
        # identical to a quiet market -- make it loud instead, once per tick this setup is due, naming the
        # setup id and the timeframe, so the reason is IN the pilot log rather than inferred from an absence.
        # Do NOT invent a window size here: live never scans 2H/30m, so there is no live value to copy.
        if st["method"] == "ICT" and ict_scan_bars(st["tf"]) is None:
            log("unscannable_tf", setup=st["id"], market=st["market"], method=st["method"], tf=st["tf"],
                why=f"automation.SCAN_WINDOW has no entry for {st['tf']} -- live never scans this timeframe, so "
                    f"this ICT setup can never produce a signal until that gap is closed")
            continue
        venue = st["execution"]
        for sym in enabled_symbols(st["market"]):
            c = candles.get((sym, st["tf"]))
            if not c or len(c) < bt.P[st["tf"]]["R"] + 10:
                continue
            # ICT reads the (possibly widened, see wide_tf_bars above) fetched array as-is; every other method
            # gets exactly the last WINDOW bars, whether or not this (sym, tf) happened to be widened for ICT
            # or an HTF read elsewhere -- so their input is unchanged by this migration.
            c_for_setups = c if st["method"] == "ICT" else c[-WINDOW:]
            for side in ("long", "short"):
                try:
                    sigs = setups(st["method"], side, c_for_setups, st["tf"], st.get("ict_disp", False), st.get("ict_pd", False), st.get("std_origin") or "pivot", sym=sym) if mreg.scan_of(st["method"]) == "ict" else setups_wyckoff(st["method"], side, c_for_setups, st["tf"])
                except Exception as e:
                    log("error", venue=venue, where=f"setups {st['id']} {sym} {side}", msg=str(e)[:200]); continue
                for sig in sigs:
                    key = f"{st['id']}-{sym}-{side}-{sig['time']}"
                    if key in s["seen"]:
                        continue
                    s["seen"].append(key); s["seen"] = s["seen"][-800:]
                    sig["htf_pass"] = htf_pass(sym, side, candles.get((sym, HTF_OF.get(st["tf"]))), HTF_OF.get(st["tf"]))
                    open_same = [k for k, p in list(s["positions"].items()) + list(s["pending"].items()) if p["execution"] == venue]
                    reasons = []
                    if sym in s["positions"] or sym in s["pending"]:
                        reasons.append("đã có vị thế/lệnh chờ")
                    if len(open_same) >= MAX_OPEN[venue]:
                        reasons.append(f"đủ {MAX_OPEN[venue]} vị thế ({venue})")
                    if s["trades_today"].get(sym, 0) >= MAX_TRADES_PER_DAY:
                        reasons.append("đủ lệnh trong ngày")
                    if blackout:
                        reasons.append(f"blackout sự kiện {blackout}")
                    if sym in foreign:
                        reasons.append("sàn đang có vị thế/lệnh không thuộc runner này")
                    # FAIL CLOSED (2026-09-13, Task 8 fix round 1): a setup that declares htf:true is asking for a
                    # higher-timeframe gate; if that gate cannot be evaluated, the answer is NOT permission. Before
                    # this fix, htf_pass() could only return True/False (a percentile it could always compute from
                    # bt.P), so `is False` was equivalent to `is not True` -- checking only for False cost nothing.
                    # Now htf_pass() reads the live rules, which can genuinely be unable to judge (None) for
                    # reasons that have nothing to do with the actual bias -- no candles fetched, htf_tf not in
                    # bt.P, or automation.SCAN_WINDOW has no entry for htf_tf (the 2H/30m gap) -- and `is False`
                    # would let every one of those sail through as if the gate had opened. Block on anything other
                    # than an explicit True: only a live bias read that actually ran and agreed with `side` permits.
                    if st.get("htf") and sig["htf_pass"] is not True:
                        reasons.append("khung lớn không cho hướng này" if sig["htf_pass"] is False else "khung lớn: không đọc được bias (thiếu dữ liệu/không quét được khung này)")
                    log("signal", venue=venue, symbol=sym, strategy=st["id"], side=side, sweep_time=sig["time"], mss_time=sig["mss_time"], entry=sig["entry"], stop=sig["stop"],
                        target=sig["target"], r_planned=round(sig["r_planned"], 2), vol_type=sig["vol_type"], htf_pass=sig["htf_pass"], ok=not reasons, reasons=reasons)
                    if reasons:
                        continue
                    risk_mult = 0.5 if s["venues"][venue]["consec_losses"] >= 2 else 1.0
                    try:
                        if sig.get("entry_now"):
                            pos = place_market(sym, st, sig, sizing_equity.get(venue, 10000.0), risk_mult, live)
                            if pos:
                                s["positions"][sym] = pos; s["trades_today"][sym] = s["trades_today"].get(sym, 0) + 1
                            pend = None
                        else:
                            pend = place_limit(sym, st, sig, sizing_equity.get(venue, 10000.0), risk_mult, live)
                    except UnprotectedPositionError as e:
                        halt(s, str(e)); save_state(s); return
                    except Exception as e:
                        s["errors"] += 1; log("error", venue=venue, where=f"place {sym}", msg=str(e)[:200]); pend = None
                    if pend:
                        s["pending"][sym] = pend
    s["last_tick"] = iso(t)
    save_state(s)


# ---------------------------------------------------------------- replay (parity with the backtest, no orders)
def replay(setup_ids, bars=600):
    report = []
    for st in load_setups():
        if setup_ids != ["all"] and st["id"] not in setup_ids:
            continue
        bt.OPTS.update(mgmt=st.get("mgmt", "be"), htf=False, sides=("long", "short"), min_rr=0.0, types=(1, 2, 3), range_touches=0, entry="book", combined_entry="limit")
        # The EXECUTION list, not st["symbols"]: replay must cover exactly what the live loop trades
        # (enabled_symbols, line ~824) or parity is checked on a different universe than the one that
        # places orders. Not config-gated -- a market switched off still deserves its parity check.
        # Symbols with no history file are skipped below.
        for sym in (CRYPTO if st["market"] == "crypto" else CFD):
            p = f"{ROOT}/data/history/ohlcv.{sym}.{st['tf']}.json"
            if not os.path.exists(p):
                continue
            span = json.load(open(p))["candles"][-bars:]
            placements = {}; wy = mreg.scan_of(st["method"]) == "wyckoff"
            for k in range(WINDOW, len(span) + 1):
                window = span[k - WINDOW:k]
                for side in ("long", "short"):
                    sigs = setups_wyckoff(st["method"], side, window, st["tf"]) if wy else setups(st["method"], side, window, st["tf"], st.get("ict_disp", False), st.get("ict_pd", False), st.get("std_origin") or "pivot", sym=sym)
                    for sig in sigs:
                        placements.setdefault((side, sig["time"]), dict(sig, first_seen=window[-1]["time"]))
            sc = bt.scan(sym, st["tf"], only=(st["method"],)); span_start = span[WINDOW - 1]["time"]  # only the method being checked -- skip the rest of scan()'s work, esp. the live ICT scanner when unused (2026-09-13)
            trades = [t for t in sc["trades"][st["method"]] if span_start <= t["time"] <= span[-1]["time"] and (not wy or t["entry_time"] >= span_start)]
            matched = unmatched = 0; details = []
            for t in trades:
                key_t = t["time"] + ("-D" if t.get("leg") == "phase_d" else "")
                pl = placements.get((t["side"], key_t))
                ok = pl is not None and abs(pl["entry"] - t["entry"]) < 1e-9 and abs(pl["stop"] - t["stop"]) < 1e-9 and abs(pl["target"] - t["target"]) < 1e-9
                matched += ok; unmatched += (not ok)
                if not ok:
                    details.append(dict(time=t["time"], side=t["side"], bt=dict(entry=t["entry"], stop=t["stop"], target=t["target"]), runner=(None if pl is None else dict(entry=pl["entry"], stop=pl["stop"], target=pl["target"]))))
            report.append(dict(setup=st["id"], symbol=sym, tf=st["tf"], method=st["method"], backtest_trades=len(trades), matched=matched, unmatched=unmatched,
                               runner_placements=len(placements), mismatches=details[:10]))
    return report


def report_state(s):
    lines = [f"TOP5 RUNNER [env {ENV_NAME}] {iso(now())} started {s['started']} halted: {s.get('halted')}"]
    for v in VENUES:
        vs = s["venues"][v]
        lines.append(f"{v}: equity start {vs['equity_start']} | closed {len(vs['closed'])} | realised {sum(c['pnl'] for c in vs['closed']):+.2f} | consec losses {vs['consec_losses']}")
    allc = [c for v in VENUES for c in s["venues"][v]["closed"]]
    for st in load_setups():
        cl = [c for c in allc if c["strategy"] == st["id"]]
        if cl:
            lines.append(f"  {st['id']}: n={len(cl)} avgR {sum(c['r'] or 0 for c in cl) / len(cl):+.2f}")
    for sym, p in s["positions"].items():
        lines.append(f"  OPEN {sym} {p['side']} {p['strategy']} [{p['execution']}] entry {p['entry']} stop {p['stop']} tp {p['tp']} be={p['be']} bars {p['bars']}")
    for sym, p in s["pending"].items():
        lines.append(f"  PENDING {sym} {p['side']} {p['strategy']} [{p['execution']}] limit {p['price']} waited {p.get('bars_waited', 0)}/{p['expires_bar_left']}")
    print("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--replay", nargs="+", default=None, help="setup ids or 'all'"); ap.add_argument("--bars", type=int, default=600)
    ap.add_argument("--report", action="store_true"); ap.add_argument("--flatten", action="store_true"); ap.add_argument("--list", action="store_true"); ap.add_argument("--tick-time", default=None)
    ap.add_argument("--ignore-gate", action="store_true", help="DRY RUN ONLY: evaluate signals even while /automation refuses the tick (never sends orders)")
    ap.add_argument("--tick-seconds", action="store_true", help="print the loop period implied by the fastest selected timeframe (used by pilot-loop.sh)")
    a = ap.parse_args()
    if a.tick_seconds:
        tfs = [st["tf"] for st in load_setups()] or ["30m"]
        print(min(TF_SEC[tf] for tf in tfs)); return
    if a.list:
        for st in load_setups():
            flags = f" disp={st.get('ict_disp', False)} pd={st.get('ict_pd', False)} std_origin={st.get('std_origin', 'pivot')}" if mreg.scan_of(st["method"]) == "ict" else ""
            blocked = "" if st["method"] in allowed_methods(st["market"]) else "  [preset: blocked]"
            print(f"{st.get('rank', '-')}. {st['id']}: {st['market']} {st['tf']} {st['method']}{flags} htf={st.get('htf')} mgmt={st.get('mgmt')} exec={st['execution']} symbols={','.join(st['symbols'])}{blocked}")
        return
    if a.replay:
        print(json.dumps(replay(a.replay, a.bars), indent=1)); return
    s = load_state()
    if a.report:
        report_state(s); return
    if a.flatten:
        for sym, p in list(s["pending"].items()):
            (mt5_json("cancel", str(p["order_id"])) if p["execution"] == "mt5" else sh(ORDER, "cancel-order", sym, str(p["order_id"]), check=False))
            log("flatten_cancel", venue=p["execution"], symbol=sym, order_id=p["order_id"]); del s["pending"][sym]
        for sym, p in list(s["positions"].items()):
            if p["execution"] == "mt5":
                r = mt5_json("close", str(p["position_ticket"] or p["entry_order"])); rec = close_record(sym, p, float(r.get("price") or 0), "FLATTEN", p["qty"], pnl=float(r.get("profit") or 0))
            else:
                sh(ORDER, "cancel-all", sym, check=False); o = order_json("close-position", sym)
                px = float(o.get("avgPrice") or 0) or float(order_json("price", sym)["price"]); rec = close_record(sym, p, px, "FLATTEN", o.get("executedQty") or p["qty"])
            s["venues"][p["execution"]]["closed"].append(rec); log("exit", venue=p["execution"], **rec); del s["positions"][sym]
        save_state(s); report_state(s); return
    live = a.live and not a.dry_run
    tt = parse_t(a.tick_time) if a.tick_time else None
    tick(live, tt, ignore_gate=a.ignore_gate and not live)


if __name__ == "__main__":
    main()
