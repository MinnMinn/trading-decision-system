#!/usr/bin/env python3
"""The pilot -- mechanical runner for the setups selected in docs/architecture/pilot-selection.json
(written by scripts/rank-setups.py from the stability backtests). Crypto setups trade Binance USDT-M FUTURES TESTNET
(scripts/binance-futures-testnet-order.sh); CFD setups trade the MT5 DEMO account through the file bridge
(scripts/mt5-order-bridge.py + integrations/mt5/OrderBridge.mq5). Real trades, fake money, on both venues.

The one execution engine (user decision 2026-09-13: the legacy engine and the profile switch that used to choose
between them were deleted). Run by scripts/pilot-loop.sh every tick-seconds. No LLM decides an order. This runner REFUSES to
tick when execution.environment is "real" (user decision 2026-09-11: demo/testnet pilot first) and the MT5 bridge EA refuses
non-demo accounts on its side too.

Rules = the backtest, function for function (scripts/backtest-methods.py, imported; parameters bt.P[tf]). Only
  the two RUNNABLE methods can ever be selected into pilot-selection.json and reach this runner:
  WYCKOFF-BOOK  scripts/wyckoff_rules.py structures on the window (CHoCH gate, TR from SC/AR, Phase B, Spring vs Shakeout, VP veto, Test, Phase D
            BU) -- MARKET at the entry bar close; Phase D target = TR top + 1 TR. (The "WYCKOFF" mechanical
            proxy -- rolling R-bar min/max as the trading range, no CHoCH gate, no Phase A/B -- was removed
            2026-09-19: docs/audits/2026-09-19-knowledge-fidelity.md finding 6. This is now the only Wyckoff
            engine in the runner.)
  ICT       sourced from the LIVE rules (ict_live_setups -> live_rules.ict_scan.setup_candidate), same as bt.scan's ICT branch:
            sweep of the last 3-bar pivot -> MSS body close within K -> FVG complete before the MSS -> LIMIT at the FVG near edge;
            stop = excursion extreme -/+ 0.05 %; target = the live scanner's su["target"] (no configurable target model --
            the six-way range/std2/std25/std4/erl_next/irl switch and bt.ict_target() were deleted 2026-09-13, dead since
            the legacy ICT branch that was their only caller was removed)
  (COMBINED-BOOK -- the book Wyckoff engine + the ICT confirmation, LIMIT at the FVG edge -- exists in
  scripts/backtest-methods.py but is runnable=false (docs/architecture/methods.json): backtest-only, never
  selectable into pilot-selection.json. The earlier "COMBINED" and "PARTIAL" methods, which paired the same removed
  proxy Spring with an ICT confirmation, were removed with it, 2026-09-19.)
  Entry = LIMIT valid K bars after the MSS (post-only GTX on Binance; a pending order with SL/TP attached on MT5); no fill -> no
  trade. Management = STOP_MARKET + TAKE_PROFIT_MARKET closePosition (futures) or the position's own SL/TP (MT5); breakeven at +1R
  on a CLOSED candle when the setup says mgmt=be (WMT p272); time stop after H bars. The higher-timeframe boundary filter
  (bt.htf_allows on HTF_OF[tf]) is logged as htf_pass for every signal; orders obey it only for setups with htf=true.
Risk: PILOT_RISK_PCT of equity per trade (env file, clamped <= RISK_CEILING = trading_env.MAX_RISK_PCT, 1 %), halved after 2 consecutive
losses; every entry must plan >= MIN_RR (analysis-params.json; 2R since 2026-09-19) or it is refused; futures notional <= 25 % of
equity x leverage 3, ISOLATED; MT5 lots from the bridge's contract data, capped by the EA's InpMaxLots. One position or resting
order per symbol; the position cap, the per-symbol daily entry cap and the leverage come from the venue's ACCOUNT PROFILE
(docs/architecture/account-profiles.json, CLAUDE.md §33) -- they are the account's rules, not this file's constants.
Halts (STOP file written with the reason): the account profile's max_total_drawdown (15 % from start, per venue) and its
declared failure conditions (5 consecutive losses, per venue); 3 consecutive connector errors (infrastructure, not an account rule). Refused per tick: kill switch, automation gate (master/pilot layer/market/profile/environment), event blackout.
Reconcile (PILOT-06): venue positions/orders this runner does not own block new entries in that symbol.
Files (this runner is their only writer): data/live/pilot-futures/pilot-selection-state.json, pilot-selection-log.jsonl (crypto), pilot-selection-mt5-log.jsonl (CFD),
candles/ohlcv.<SYM>.<TF>.json (private Binance copies). CFD candles are READ from data/live/mt5-bridge/ (the export EA writes them).
Journal: scripts/journal.py sync-pilot --market futures-selection | cfd-mt5.
Usage: strategy-runner.py --live | --dry-run [--ignore-gate] [--tick-time ISO] | --replay <setup-id|all> [--bars N] | --report | --flatten | --list | --tick-seconds
"""
import argparse, contextlib, datetime, hashlib, importlib.util, json, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
_spec = importlib.util.spec_from_file_location("bt", os.path.join(ROOT, "scripts", "backtest-methods.py")); bt = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(bt)
import wyckoff_rules as W
_tspec = importlib.util.spec_from_file_location("trading_env", os.path.join(ROOT, "scripts", "trading_env.py")); trading_env = importlib.util.module_from_spec(_tspec); _tspec.loader.exec_module(trading_env)

import providers as P
import normalized as N          # the normalized data layer: one definition of "when did this become knowable"
import quality as Q             # CLAUDE.md §20: the six data-quality states, and what a failing one does
import event_risk as ER        # CLAUDE.md §24-§32: the event-risk gate, fail-CLOSED
import account_profile as AP   # CLAUDE.md §33: the account's own rules, not this file's constants
import mandates as MD           # the account<->setup table; order attribution reads it (plan §0.3 item 1)
import execution_safety as ES  # CLAUDE.md §51: what the KEY can do, which reading this file cannot establish
import risk_model as RM        # CLAUDE.md §34: fees, slippage and exposure in the risk calculation
import trading_system as TS    # CLAUDE.md §35: which dependencies may gate an entry, and which may never
import decision_order as DO    # CLAUDE.md §36: the canonical 17-step ordering, recorded per decision
import expectation as X        # CLAUDE.md §17: to_json() for the plan/log payload -- see expectation_producer
import expectation_producer as EP  # CLAUDE.md §17/plan §0.5: the ONE caller of expectation.create() on this path
import trader_constraints as TC  # plan §0.9: a trader's own, tighten-only constraints per methodology
import sessions as SESS          # CLAUDE.md §21: the one session reader (the trader `sessions` constraint needs it)
import latency as LAT          # CLAUDE.md §40: the ten stamps the live path must record, and p50/p95/p99/max
import feed_health as FH       # CLAUDE.md §52: the faults that only exist BETWEEN polls
import mt5_time as MT5T         # audit PAR-5: EA v1.03 exports raw server time; convert with the declared IANA zone
# Provider identity is DATA, not a path typed here (CLAUDE.md §2: "Binance must NOT become the architectural
# center"). These three constants used to be literal script paths, which meant choosing a different venue or a
# different market-data source required editing this file -- the live order engine -- rather than a registry.
# They now resolve through docs/architecture/providers.json, which also refuses at import if a declared
# connector is missing from disk. The VALUES are unchanged; scripts/tests/test_providers.py pins that.
# Still hard-coded and tracked as CLAUDE.md §4 work: the `if venue == "mt5"` branching below. Identity is data;
# routing is not yet (SYSTEM-DESIGN.md §16.1).
ORDER = P.adapter("binance_futures")
MT5 = P.adapter("mt5_bridge")
FETCH = P.market_data_adapter("binance_public")
# ---------------------------------------------------------------- per-account scope
#
# ACCOUNT is None in the house's own single-account mode, and every path below then resolves EXACTLY as it did
# before 2026-09-19 -- the existing pilot is byte-for-byte unaffected. `--account <id>` binds a customer
# account (docs/plans/2026-09-18... see docs/plans/2026-09-19-multi-account.md Pha 1) and moves this process's
# state, logs, candle cache and kill switch under data/live/accounts/<id>/.
#
# Why the paths are REBOUND globals rather than functions: they are module constants that tests and other
# scripts already read and override by name. Turning them into calls would be the larger change and would buy
# nothing -- a process serves one account for its whole life (one process per account, plan §4), so binding
# once at startup is the whole requirement.
ACCOUNT = None
GLOBAL_STOP = os.path.join(ROOT, "data", "live", "STOP")   # halts EVERY account; see bind_account()
PILOT_DIR = os.path.join(ROOT, "data", "live", "pilot-futures")
# SHARED across every account, deliberately, and NOT rebound by bind_account(). Candles are public market
# data: BTCUSDT 15m is the same bytes for every customer, so giving each account its own copy would multiply
# the feed load by N for no difference in content -- 26 provider calls per tick becomes 26N, and the market-
# data rate limit is per IP, not per key. It would also make the accounts disagree about the market whenever
# their fetches landed either side of a bar close, which is the opposite of what per-account isolation is for.
# What IS per-account is everything a customer owns or can lose: state, logs, kill switch.
CANDLES = os.path.join(ROOT, "data", "live", "candles-cache")
MT5_DIR = os.path.join(ROOT, "data", "live", "mt5-bridge")
STATE = os.path.join(PILOT_DIR, "pilot-selection-state.json")
LOG = os.path.join(PILOT_DIR, "pilot-selection-log.jsonl")
MT5_LOG = os.path.join(PILOT_DIR, "pilot-selection-mt5-log.jsonl")
STOP = os.path.join(PILOT_DIR, "STOP")
AUTOMATION_CONFIG = os.path.join(ROOT, "docs", "architecture", "automation-config.json")
SELECTION = os.path.join(ROOT, "docs", "architecture", "pilot-selection.json")
_ispec = importlib.util.spec_from_file_location("instruments", os.path.join(ROOT, "scripts", "instruments.py"))
instruments = importlib.util.module_from_spec(_ispec); _ispec.loader.exec_module(instruments)
# EXECUTION list (docs/architecture/instruments.json) -- the orderable subset, never the analysis allowlist.
CRYPTO = instruments.execution("crypto"); CFD = instruments.execution("cfd")
_mspec = importlib.util.spec_from_file_location("methods", os.path.join(ROOT, "scripts", "methods.py"))
mreg = importlib.util.module_from_spec(_mspec); _mspec.loader.exec_module(mreg)
# STRUCTURE tier = the next runner timeframe >= 4x (scripts/automation.py next_rung -- the one ladder rule, docs/architecture/
# timeframe-mapping.md). Over the runner's rungs this yields 5m->30m, 15m->1H, 30m->2H, 1H->4H, 2H->1D, 4H->1D, 1D->None,
# identical to the table the backtests were run with (scripts/tests/test_timeframe_ladder.py pins it).
RUNNER_TFS = ["5m", "15m", "30m", "1H", "2H", "4H", "1D"]
# CLAUDE.md §40 latency instrumentation. ONE active trace per tick, held here so the helpers further down
# (fetch_candles, risk_precheck, place_*) can time their own stage without threading a parameter through
# every call site of a 1,600-line order path. `_span` is a no-op when no tick is active -- a --report or a
# --list run must not open a trace, and nothing in the order path may fail because measurement is off.
_LAT = None


def _t0():
    """A monotonic start for a §40 stage that cannot be wrapped in a `with` without re-indenting the live
    order path. Returns None when no tick trace is active, and `_rec` then does nothing."""
    return time.perf_counter_ns() if _LAT is not None else None


def _rec(stage, t0):
    if _LAT is None or t0 is None:
        return
    try:
        _LAT.record(stage, t0)
    except Exception:
        pass                          # measurement never fails a tick (§1)


@contextlib.contextmanager
def _span(stage):
    """Time one §40 stage on the active tick trace, or do nothing when there is none.

    BEST EFFORT by construction: §1 puts execution safety above measurement, so a recorder that raises must
    not be able to refuse a trade. The only exception that CAN come out of here is the caller's own.
    """
    tr = _LAT
    if tr is None:
        yield
        return
    with tr.span(stage):
        yield


import importlib.util as _iu
_as = _iu.spec_from_file_location("automation", os.path.join(ROOT, "scripts", "automation.py")); _auto = _iu.module_from_spec(_as); _as.loader.exec_module(_auto)
HTF_OF = {tf: _auto.next_rung(tf, RUNNER_TFS) for tf in RUNNER_TFS}
WINDOW = bt.WYCKOFF_WINDOW   # the live WYCKOFF-BOOK window; ONE number with bt.scan()'s (see bt.wyckoff_fires)
NOTIONAL_CAP_PCT = 0.25
# The position cap, the daily entry cap, the leverage, the drawdown halt and the consecutive-loss halt used to
# be five literals here. They are not runner settings -- they are the ACCOUNT's rules, and CLAUDE.md §33 makes
# the Account Profile a first-class object precisely so that a second account can have different ones and a
# research run can record which set was in force (§11). They now live in docs/architecture/account-profiles.json
# and are read through scripts/account_profile.py; the VALUES are unchanged except `mt5` max_positions, which
# used to be len(CFD) and so ignored the seven FX majors routed to the same account (SPEC-COMPLIANCE §4 flagged
# it as belonging here). RISK NOTE, unchanged and still worth reading: max simultaneous risk = slots x
# PILOT_RISK_PCT -- at the 1 % ceiling and a nine-symbol crypto book that is 9 %, and crypto is near-perfectly
# correlated in a dump, so a full book is closer to ONE leveraged beta bet than to nine independent ones. The
# account's max_total_drawdown is what bounds the damage. Dial it back by lowering PILOT_RISK_PCT in
# config/env.<env>, or the book by editing the profile -- not by editing this file.
ERROR_HALT = 3   # NOT an account rule: a connector that errors three times running is an infrastructure fault
STOP_BUFFER_PCT = bt.STOP_BUFFER_PCT
TF_SEC = {"5m": 300, "15m": 900, "30m": 1800, "1H": 3600, "2H": 7200, "4H": 14400, "1D": 86400}
VENUES = ("futures", "mt5")
METHODS = tuple(sorted(mreg.runnable()))   # ICT = limit at the FVG edge; WYCKOFF-BOOK = market at the bar close

ENV_NAME = trading_env.active_env_name()
try:
    _env = trading_env.load_env(resolve_secrets=False); ENV_ERROR = None
except trading_env.EnvIncomplete as e:
    _env, ENV_ERROR = {}, str(e)

# --- Account Profiles (CLAUDE.md §33) ------------------------------------------------------------
# One profile per (venue, environment). Resolution is deferred and the failure is KEPT rather than raised at
# import, for a specific reason: there is deliberately no profile for environment "real", and an account with
# no declared rules must stop ORDERS, not stop `--report` from telling you what the account is holding.
_PROFILES, _PROFILE_ERROR = {}, {}
for _v in VENUES:
    try:
        _PROFILES[_v] = AP.for_venue(_v, ENV_NAME)
    except ValueError as _e:
        _PROFILE_ERROR[_v] = str(_e)


def profile(venue):
    """The Account Profile whose rules this venue's orders obey, or a refusal naming what is undeclared."""
    if venue not in _PROFILES:
        raise ValueError(f"no account rules are declared for venue {venue!r} in environment {ENV_NAME!r}, so "
                         f"nothing may be traded on it: {_PROFILE_ERROR.get(venue, 'unknown venue')}")
    return _PROFILES[venue]


def _account_survival_block(prof, facts):
    """DEC-6 (CLAUDE.md §20/§33): a declared account-survival rule (max_daily_loss, trailing_drawdown, a
    custom failure condition, a consistency rule) whose basis fact this runner does not supply reports
    UNKNOWN from AP.account_state() -- and AP.halt_check() only ever HALTS on HALT/HUMAN/BLOCK_ENTRY, never
    on UNKNOWN, by design (an unmeasurable account is not a proven breach). That left such a rule silently
    unenforced in EITHER direction: not halted (correct) and, until this fix, not blocking new entries either
    (wrong -- §20 forbids treating an unresolved UNKNOWN as a pass). Returns a reason string to block NEW
    ENTRIES with, or None. Never call this for a HALT decision -- see the docstring above.
    """
    unknown = [f for f in AP.account_state(prof, facts) if f["state"] == AP.UNKNOWN]
    return "; ".join(f"{f['rule']}: {f['why']}" for f in unknown) if unknown else None


def futures_leverage():
    """Leverage for the crypto venue, from its account profile (was the literal `LEVERAGE = 3`)."""
    return AP.max_leverage(profile("futures"))
# Per-trade risk ceiling. 1 % since 2026-09-17, by explicit user decision, UNIFYING the two ceilings this repo
# had been carrying: 3 % on this path (trading_env's literal) and 1 % everywhere the manual /execute path looks
# (risk-config.json, risk-skill, risk-agent, and the SessionStart hook). Both are now the same number and it has
# one reader, trading_env.MAX_RISK_PCT, sourced from docs/architecture/risk-config.json.
#
# The 3R planned-R:R floor below is UNCHANGED by that, and the reason is worth stating rather than assuming:
# under fixed-fractional sizing, expectancy in R is scale-free in the risk fraction, so every R-multiple in the
# 2026-09-13 evidence still holds -- lowering 3 % -> 1 % divides the absolute drawdown by three and leaves the
# floor's justification intact. What that evidence measured, on the last year of ICT 15m setups across the nine
# crypto instruments: with the 3R floor, 3 % risk returned +180 % with a 29 % drawdown and never tripped
# EQUITY_HALT_FRAC; at 1 % the same trades are the same sequence of R-multiples on a third of the stake.
# 5 % was REJECTED, not merely disfavoured: its equity curve crossed -15 % from start on 2025-10-12, which halts
# this runner permanently (line ~963) -- the backtest does not model that halt, so its +366 % is unreachable
# here. Do not raise the ceiling without also deciding what happens to EQUITY_HALT_FRAC; that is a separate
# decision and it has not been made. Evidence: docs/backtests/2026-09-13-rr-floor-and-risk.md.
RISK_CEILING = trading_env.MAX_RISK_PCT   # one source, see scripts/trading_env.py
try:
    RISK_PCT = min(RISK_CEILING, max(0.0, float(_env.get("PILOT_RISK_PCT", 0.005))))
except (TypeError, ValueError):
    RISK_PCT = 0.005
MIN_RR = bt.MIN_RR   # planned-R:R floor, one source: docs/architecture/analysis-params.json
MARKET_LABEL = f"futures_{'mainnet' if ENV_NAME == 'real' else 'testnet'}"


# ---------------------------------------------------------------- infrastructure
def now():
    return datetime.datetime.now(datetime.timezone.utc)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_t(s):
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)


def bar_open_time(iso_ts, tf):
    """PAR-1: floor `iso_ts` down to the open time of the `tf` bar it falls in -- epoch-aligned, the same grid
    the candle cache's own bars are stamped on. Used to anchor a position's entry to the BAR it filled in,
    never to the wall-clock minute of the tick that noticed the fill (see `manage_position`'s `since`)."""
    sec = TF_SEC[tf]
    epoch = int(parse_t(iso_ts).timestamp())
    return iso(datetime.datetime.fromtimestamp(epoch - (epoch % sec), tz=datetime.timezone.utc))


# Per-venue log destination, keyed by execution alias rather than by an `if venue == "mt5"` (CLAUDE.md §4).
# A lookup with an explicit default is the same behaviour as the old conditional -- an unknown alias writes to
# the futures log exactly as `else` did -- but adding a third venue is now a dict entry instead of an edit to
# the logging function. `.get` and not `[]` on purpose: losing a log line is never worth raising inside the
# path that records why something was refused.
VENUE_LOG = {"mt5": MT5_LOG}


def bind_account(account_id):
    """Point this process at ONE account: its own state, logs, candle cache and kill switch.

    Isolation is the requirement (plan §0.3 item 2). Before this, `STOP` was one file for every venue and
    every account, so one customer breaching a drawdown limit halted everybody; `pilot-selection-state.json` was one
    file written with a bare `open(..., "w")`, so two processes would have silently overwritten each other's
    positions. Scoping the paths is what makes one process per account safe to run.

    The kill switch is now TWO-TIER: GLOBAL_STOP halts every account and this account's own STOP halts only
    this one. `halted()` checks both, so an operator keeps one lever that stops everything and one per
    customer -- and a customer's own failure stops that customer alone.

    Passing None restores the house's single-account paths exactly, which is what every existing test and the
    running pilot rely on.
    """
    global ACCOUNT, PILOT_DIR, STATE, LOG, MT5_LOG, STOP, VENUE_LOG
    ACCOUNT = account_id
    if account_id is None:
        PILOT_DIR = os.path.join(ROOT, "data", "live", "pilot-futures")
    else:
        if account_id not in AP.PROFILES:
            raise SystemExit(f"--account {account_id!r} is not in {AP.PATH}. An order path must not guess "
                             f"whose rules apply (CLAUDE.md §33).")
        try:
            AP.for_account(account_id)      # refuses a research template, and says so
        except ValueError as e:
            raise SystemExit(f"--account {account_id!r}: {e}") from None
        PILOT_DIR = os.path.join(ROOT, "data", "live", "accounts", account_id)
    STATE = os.path.join(PILOT_DIR, "pilot-selection-state.json")
    LOG = os.path.join(PILOT_DIR, "pilot-selection-log.jsonl")
    MT5_LOG = os.path.join(PILOT_DIR, "pilot-selection-mt5-log.jsonl")
    STOP = os.path.join(PILOT_DIR, "STOP")
    VENUE_LOG = {"mt5": MT5_LOG}
    return PILOT_DIR


def halted():
    """True when THIS account must not trade: its own kill switch, or the estate-wide one."""
    return os.path.exists(STOP) or os.path.exists(GLOBAL_STOP)


def log(kind, venue="futures", **kw):
    os.makedirs(PILOT_DIR, exist_ok=True)
    # `account` on every record: with N customers, a log line that does not say whose it is cannot be used to
    # answer a customer's question, to bill, or to settle a dispute (plan §0.3 item 1).
    rec = {"t": iso(now()), "kind": kind, **({"account": ACCOUNT} if ACCOUNT else {}), **kw}
    with open(VENUE_LOG.get(venue, LOG), "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps(rec, ensure_ascii=False))


def sh(*args, check=True, env=None):
    # Windows cannot exec a .sh file directly (WinError 193: %1 is not a valid Win32
    # application) -- there is no shebang interpreter lookup outside a POSIX exec().
    # Route through bash (Git Bash on this platform) so the connector scripts run unchanged.
    if os.name == "nt" and args and str(args[0]).endswith(".sh"):
        args = ("bash",) + args
    r = subprocess.run(args, capture_output=True, text=True, env=env)
    if check and r.returncode != 0:
        raise RuntimeError(f"{os.path.basename(args[0])} {' '.join(args[1:3])} failed: {r.stderr.strip()[:300]}")
    return r.stdout


def order(*args):
    return sh(ORDER, *args)


def order_json(*args):
    out = order(*args)
    return json.loads(out) if out.strip() else {}


def mt5_bridge_subdir():
    r"""The Common\Files subfolder this account's MT5 terminal uses. `bridge` in single-account mode.

    Several MT5 terminals can run on one machine -- one per customer account, since a terminal is logged into
    exactly one account -- but terminals in the same installation SHARE Common\Files. The connector consumes
    res-<id>.json (reads it, then deletes it), so two accounts pointed at one folder would race to eat each
    other's replies and one customer's fill could be reported to another. Giving each terminal its own folder
    (EA input InpBridgeDir) and each runner the matching name is what makes N CFD accounts on one machine safe.
    """
    return "bridge" if not ACCOUNT else f"bridge-{ACCOUNT}"


def mt5_json(*args):
    out = sh("python3", MT5, *args, env=dict(os.environ, MT5_BRIDGE_SUBDIR=mt5_bridge_subdir()))
    return json.loads(out) if out.strip() else {}


def load_setups():
    """The ENABLED systems of the selection file, and nothing else (ADR 0008). No selection file, or an
    unreadable one, means nothing is enabled -- the runner trades nothing rather than a built-in default. (A
    hard-coded fallback setup used to be returned when the file was absent: a coverage fallback, which ADR 0008
    removed.)"""
    if not os.path.exists(SELECTION):
        return []
    try:
        with open(SELECTION, encoding="utf-8") as fh:
            doc = json.load(fh)
        return [s for s in doc["setups"] if s.get("method") in METHODS and s.get("execution") in VENUES]
    except Exception:
        return []


def automation_gate():
    """Reason to refuse this tick, or None. Can only stop, never start. Missing/unreadable config = refuse (PILOT-03)."""
    if not os.path.exists(AUTOMATION_CONFIG):
        return "no automation config -- the pilot runs only under /automation"
    try:
        c = json.load(open(AUTOMATION_CONFIG, encoding="utf-8"))
    except Exception:
        return "automation config unreadable"
    if not c.get("enabled", True):
        return "automation master switch is OFF"
    if not c.get("layers", {}).get("pilot", True):
        return "pilot layer disabled"
    # (deleted 2026-09-13) the pilot_profile refusal: there is one engine now, so the only thing this
    # key could still express is "run nothing", which layers.pilot already expresses.
    if c.get("execution", {}).get("environment", "demo") == "real":
        return "environment is REAL -- the pilot is demo/testnet only (user decision 2026-09-11); refusing"
    if ENV_ERROR:
        return f"environment '{ENV_NAME}' unusable -- {ENV_ERROR}"
    ok, missing, note = trading_env.completeness(ENV_NAME, ("BINANCE_FUTURES_API_KEY", "BINANCE_FUTURES_SECRET_KEY"))
    if not ok:
        return f"environment '{ENV_NAME}' incomplete -- fill {', '.join(missing)}"
    # §51's last unheld sentence: "Never require withdrawal permission." It was true and unasserted -- a key
    # minted with withdrawal rights would have traded exactly as well and nothing would have said so. A key
    # KNOWN to have them refuses here in any environment; an UNREAD scope refuses only where §51 says the
    # assumption is unsafe (environment 'real'), because the mainnet-only apiRestrictions endpoint means a
    # testnet key cannot be probed at all and UNKNOWN is its normal, honest state.
    scope_refusal = ES.gate_reason("binance_spot", ENV_NAME)
    if scope_refusal:
        return scope_refusal
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


def event_blackout(t=None, sym=None):
    """Whether a NEW ENTRY is barred by Event Risk right now -- the reason, or None when clear.

    CLAUDE.md §24-§32, delegated to scripts/event_risk.py. What this replaced, and why it could not be
    patched: it ran a regex for `YYYY-MM-DD HH:MM` over the ENTIRE TEXT of `event-calendar.md` and blocked
    within +/-30 minutes of any match. So the file's own "How to add an entry" EXAMPLE was a live blackout;
    a row written `17:00Z - 20:00Z` became two POINT events leaving 17:30-19:30 unprotected (§30's exact
    prohibition, in a three-hour FOMC window); and every failure returned None, which this caller reads as
    "no news" -- §32's exact prohibition, on the code path that places orders.

    `sym` is now required in practice: §26 says an event does not reach every instrument. Called without
    one the question has no answer, so it fails CLOSED rather than answering for an instrument nobody named.
    """
    if sym is None:
        return "event risk asked without an instrument -- §26 makes relevance per-instrument, so there is " \
               "no global answer; blocking rather than guessing"
    when = t or now()
    # §33: the ACCOUNT may add its own news rule on top of the calendar policy -- a prop account that forbids
    # entries within 30 minutes of any MEDIUM release, say. `tighten_calendar` applies it and REFUSES a value
    # that would shorten a buffer or unrestrict an impact level, so an account cannot opt out of §24 by
    # writing a config key. No account declares one today, and the call then returns the calendar unchanged.
    try:
        cal = AP.tighten_calendar(profile(venue_of(sym)), ER.load(at=when))
    except ER.CalendarUnavailable as exc:
        return f"{exc.reason} -> configured fail-safe: {exc.action}"
    hit, why = ER.blocked(sym, at=when, cal=cal)
    if hit:
        return why
    # DEC-7 (CLAUDE.md §25 'UNKNOWN: never silently treated as LOW'): `ER.windows()` only gates an
    # UNKNOWN-impact event when the caller passes mode='STRICT' (test_event_risk.py pins this: NORMAL must
    # NOT restrict on UNKNOWN, only LOW does that in the code's own vocabulary -- see
    # test_unknown_is_not_low_strict_mode_treats_it_as_no_trade). This runner has no Trading-System
    # methodology-mode concept to pass (§16 mode is a separate, unbuilt dimension), so `mode` here is always
    # None and `policy.by_impact.UNKNOWN.strict_no_trade: true` (event-calendar.json) can never take effect --
    # the exact defect DEC-7 names. Fixing that requires threading a real mode, which is out of round-1 scope.
    # What IS in scope, and what the fix critique asks for as the minimal compliant step: a relevant
    # UNKNOWN-impact event inside its own would-be window must not look IDENTICAL to genuine "no news" --
    # `ER.windows(..., mode="STRICT")` asks the same calendar "would this gate under the configured
    # strict_no_trade flag", purely to DISCLOSE the answer in a decision-record log line. It does not change
    # whether this function blocks (still None below), so it cannot make NORMAL behave like STRICT.
    for _a, _b, evs in ER.windows(sym, cal=cal, decision_time=when, mode="STRICT"):
        if _a <= when <= _b and any((e.get("impact") or "UNKNOWN").upper() == "UNKNOWN" for e in evs):
            names = ", ".join(e.get("name", e.get("id", "?")) for e in evs)
            log("unknown_event_disclosed", venue=venue_of(sym), symbol=sym, at=iso(when), events=names,
                note="an UNKNOWN-impact event is inside its restricted window right now; the calendar's own "
                     "strict_no_trade=true would block this entry in STRICT mode, but this runner has no "
                     "methodology-mode input to engage it, so the entry proceeds -- disclosed, not silently "
                     "treated as a LOW-impact 'no news' clear (CLAUDE.md §25)")
            break
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


_MT5_IDENTITY_OK = None


def mt5_assert_identity():
    """Refuse unless the terminal answering us IS the account this process is trading for.

    Defence in depth, and the second half of the multi-account MT5 story. The first half is isolation by
    construction: each terminal gets its own command/response folder (mt5_bridge_subdir, EA input
    InpBridgeDir), so files cannot cross. This half assumes that failed anyway -- a symlink repointed, a
    terminal restarted on the wrong login, a folder name typed once and wrongly -- and turns the consequence
    from "customer A's order was placed on customer B's account" into a logged refusal.

    That asymmetry is the whole reason it is worth a round trip: isolation-only fails SILENTLY and in the
    worst possible direction. Somebody else's money is the one place to pay for a second check.

    The expected login comes from the environment (MT5_ACCOUNT_LOGIN in config/env.<env>, gitignored, never
    a tracked registry). Checked once per process: a terminal does not change account mid-run, and this is on
    the order path.
    """
    global _MT5_IDENTITY_OK
    if _MT5_IDENTITY_OK is not None:
        return _MT5_IDENTITY_OK
    want = (_env.get("MT5_ACCOUNT_LOGIN") or "").strip()
    if not want:
        if ACCOUNT:
            raise RuntimeError(
                f"--account {ACCOUNT!r}: MT5_ACCOUNT_LOGIN is not set, so there is nothing to check the "
                f"terminal's identity against. With several accounts on one machine an unverified terminal "
                f"is an order placed on whoever happens to be logged in; refusing (CLAUDE.md §51).")
        _MT5_IDENTITY_OK = True      # house single-account mode: unchanged behaviour
        return True
    got = str((mt5_json("account") or {}).get("login") or "")
    if got != want:
        raise RuntimeError(
            f"MT5 terminal reports login {got!r} but this process trades account "
            f"{ACCOUNT or '(house)'!r}, whose configured login is {want!r}. Refusing every order: the "
            f"command folder ({mt5_bridge_subdir()}) is reaching the wrong terminal, or that terminal is "
            f"logged into the wrong account.")
    _MT5_IDENTITY_OK = True
    return True


def mt5_equity():
    """MT5's own ACCOUNT_EQUITY (balance + floating P/L of open positions, integrations/mt5/OrderBridge.mq5
    JN("equity", AccountInfoDouble(ACCOUNT_EQUITY))) -- this already IS true equity, not free margin (that
    field is separately exported as margin_free and this runner does not read it). No Binance-style
    free-margin confusion on this venue; used unchanged for both the halt guard and MT5 lot sizing."""
    mt5_assert_identity()
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


def _cache_has_last_closed(sym, tf, window, t=None):
    """True when the SHARED candle cache already holds the most recent CLOSED bar for (sym, tf).

    Why this exists: every account runs its own process, and before this each one shelled out to the provider
    for all 18 crypto (symbol, timeframe) pairs on every tick. With N customers that is 18N calls into a rate
    limit that is per IP, not per key -- the feed, not the CPU, becomes the thing that caps how many accounts
    a machine can serve. The cache is shared and the bytes are identical for everyone, so the first runner to
    tick after a bar close refreshes it and the rest read it: 18 calls per tick window instead of 18N.

    Deliberately conservative in the direction that matters. It returns False -- fetch -- on anything it
    cannot establish: no file, unreadable file, unknown timeframe, too few bars for the caller's window, a
    last bar that is not exactly the expected one. Serving a stale window would be a §20 violation on the hot
    path; one redundant HTTP call is not. The freshness gate in _require_quality still runs either way, so a
    cache this function wrongly accepts is still caught downstream rather than traded on.
    """
    try:
        step = N.tf_seconds(tf)
    except ValueError:          # normalized.tf_seconds RAISES on an unknown timeframe rather than returning
        return False            # None; an unknown tf means we cannot say the cache is current, so refetch
    if not step:
        return False
    now_ = (t or now()).timestamp()
    # The most recent bar that has CLOSED opened one full period before the current, still-forming one.
    want = datetime.datetime.fromtimestamp((now_ // step) * step - step, tz=datetime.timezone.utc)
    try:
        d = json.load(open(f"{CANDLES}/ohlcv.{sym}.{tf}.json"))
        c = d["candles"]
    except (OSError, ValueError, KeyError):
        return False
    if len(c) < window:
        return False
    return c[-1]["time"] == iso(want) or c[-1]["time"] == iso(want + datetime.timedelta(seconds=step))


def drop_forming(c, tf, t):
    """Drop a bar that has not finished forming: its close is not knowable yet.

    The condition is `available_time(bar) > now` -- the bar's own open plus one period. That rule now has ONE
    definition, scripts/normalized.py available_time(), because CLAUDE.md §7/§8 need the same notion of "when
    did this become knowable" for news, corrections and derived analytics, not just for candles. The
    behaviour here is unchanged and scripts/tests/test_normalized.py pins the equivalence against the old
    inline expression for every timeframe the runner uses."""
    if c and N.available_time(c[-1], tf) > t:
        c = c[:-1]
    return c


# CLAUDE.md §38 prerequisite, implemented minimally here because §20 surfaced it (see _require_quality).
# Every data-quality fault a REPLAY walked over, so the run that produced a result can be judged on the data
# that produced it. §38 owns what is finally done with these; this is the record they need to exist.
QUALITY_FLAGS = []
_REPLAY_QUALITY = {}   # (symbol, timeframe) already assessed this replay -- the file does not change mid-run


def _require_quality(sym, tf, series, allow=("FRESH",), now=None, at=None, feed_state=None):
    """CLAUDE.md §20 on the hot path: a required input that fails its quality requirement stops the decision.

    Candles are REQUIRED_FOR_DECISION for every setup this runner evaluates -- there is no setup that can be
    read without them -- so the §20 outcome here is the strictest one the state maps to, and raising is how
    this runner already expresses it: tick()'s fetch loop catches per (symbol, timeframe), logs the reason and
    leaves that pair with no candles, so the instrument gets WAIT / NO DECISION while the others proceed. That
    is the §62 shape -- one lane's failed required input must not stop the run, and must not be walked past.

    Before this existed, the CFD branch checked staleness and nothing else, and the crypto branch checked
    nothing at all: a Binance response with a hole in it, an out-of-order bar or a high below its low was
    scanned as though it were whole.

    **Live gates, replay flags, and that asymmetry is the point.** A live entry on a holed window is an unsafe
    decision with nothing after it to correct the record, so §20 blocks it. A replay is research: §38 says an
    affected run must be "flagged OR invalidated", and refusing to run at all would delete the finding along
    with the result. Running this over the stored history found a real one -- BTCUSDT, ETHUSDT and SOLUSDT all
    miss the 2023-03-24T13:00Z bar in their 1H files (two bars on 30m), one provider outage that every
    backtest over that range has silently replayed as whole. Blocking would have hidden it in an exception;
    flagging puts it in the run's own record, which is what §38 asks for.
    """
    if at is not None:
        # A replay re-reads the same stored file every tick, and the file does not change mid-run, so the
        # verdict is computed once per (symbol, timeframe). Without this the O(bars) structural walk would run
        # thousands of times over identical bytes and the same flag would be printed once per tick.
        key = (sym, tf)
        if key in _REPLAY_QUALITY:
            return
        _REPLAY_QUALITY[key] = True
    state, why = Q.assess(series, tf, symbol=sym, now=now)
    # CLAUDE.md §52: a poll-to-poll fault (stalled feed, gap since the last poll, a revised closed bar) is
    # invisible to Q.assess(), which looks inside ONE response. When feed_health has one, the STRICTER of the
    # two states decides -- §20's own rule, applied to a second source of the same vocabulary rather than to a
    # second gate.
    if feed_state and feed_state not in allow:
        state, why = feed_state, f"{why}; feed health (§52): {feed_state}"
    if state in allow:
        return
    decision, _ = Q.gate({"candles": state}, required=("candles",), allow=allow)
    msg = f"{sym} {tf} candles are {state} -> {decision} (CLAUDE.md §20): {why}"
    if at is not None:
        QUALITY_FLAGS.append({"symbol": sym, "tf": tf, "state": state, "reason": why})
        print(f"DATA-QUALITY FLAG (CLAUDE.md §38): {msg}", file=sys.stderr)
        return
    raise RuntimeError(msg)


def fetch_candles(sym, tf, market, t, at=None, window=None):
    """Closed candles only. Crypto: private Binance copy. CFD: the MT5 export file (2H aggregated from 1H). --replay: history cut at `at`.
    `window`: candle count to return, default WINDOW (300) -- enough for WYCKOFF-BOOK. ICT setups need
    live_rules' own (larger, per-tf) trailing window, see ict_scan_bars() in tick() below (2026-09-13, Task 8)."""
    window = window or WINDOW
    # CLAUDE.md §40: `provider_receive` is the fetch, `normalization` is the work that turns the provider's
    # rows into candles this engine can read (the aggregation and the §20 quality gate). They are timed
    # separately because they fail and regress for different reasons: one is the network, the other is us.
    if at is not None:
        d = json.load(open(f"{ROOT}/data/history/ohlcv.{sym}.{tf}.json"))
        # A replay reads a stored file, so FRESHNESS is meaningless (nothing is late in 2024) but STRUCTURE is
        # not: CLAUDE.md §38 invalidates a research run on "corrupted provider data", and a holed or
        # out-of-order history would otherwise be replayed as if whole.
        _require_quality(sym, tf, d, allow=("FRESH", "STALE", "UNKNOWN"), at=at)
        return [x for x in d["candles"] if x["time"] <= at][-window:]
    if market == "crypto":
        env = dict(os.environ, KLINES_OUT_DIR=CANDLES)
        with _span("provider_receive"):
            if not _cache_has_last_closed(sym, tf, window, t):
                r = subprocess.run(["bash", FETCH, sym, tf, str(window)], capture_output=True, text=True, env=env)
                if r.returncode != 0:
                    raise RuntimeError(f"fetch {sym} {tf}: {r.stderr.strip()[:200]}")
        with _span("normalization"):
            d = json.load(open(f"{CANDLES}/ohlcv.{sym}.{tf}.json"))
            _require_quality(sym, tf, d, now=t)
            c = d["candles"]
    else:
        src_tf = {"2H": "1H", "30m": "15m"}.get(tf, tf)          # the export EA writes 5m/15m/1H/4H/1D/1W; 30m and 2H are aggregated
        p = f"{MT5_DIR}/ohlcv.{sym}.{src_tf}.json"
        with _span("provider_receive"):   # §40: the PAR-5 conversion is part of receiving the export, so it is timed with it
            MT5T.sync_live(MT5_DIR, symbols={sym}, timeframes={src_tf}, log=lambda m: log("note", why=m))   # PAR-5: .server.json -> .json (no-op for a pre-v1.03 EA)
        if not os.path.exists(p):
            raise RuntimeError(f"no MT5 export for {sym} {src_tf}")
        with _span("provider_receive"):
            d = json.load(open(p))
        # §52 / drill 2026-09-18: the EA's bar stamps jitter by ±1 s around the grid; snap them BEFORE the
        # quality and feed-health reads so a clock artefact never reads as "the series went backwards".
        c = d["candles"] = N.snap_series(d["candles"], src_tf)
        if d.get("last_updated") and (t - parse_t(d["last_updated"])).total_seconds() > 2 * TF_SEC[src_tf] + 900:
            raise RuntimeError(f"MT5 export for {sym} {src_tf} is stale ({d['last_updated']})")
        # The line above is this feed's own staleness rule and it stays: the MT5 export is pushed by an EA on a
        # schedule §20's generic 3-bar rule does not know about. What it never checked is whether the exported
        # bars are SOUND -- so the structural half runs here too, with STALE already ruled out above.
        with _span("normalization"):
            _require_quality(sym, src_tf, d, allow=("FRESH", "STALE", "UNKNOWN"), now=t)
            if tf == "2H":
                c = aggregate(c, 2)
            elif tf == "30m":
                c = aggregate_minutes(c, 30)
    out = drop_forming(c, tf, t)[-window:]
    # CLAUDE.md §52: the faults that live BETWEEN polls -- a stalled feed serving identical bytes, bars
    # missing since the last poll, a series that went backwards, a closed bar quietly revised. Every one of
    # those returns a response §20 finds perfectly valid, because §20 looks inside ONE response. The state is
    # mapped onto §20's own vocabulary and handed to the same gate: §52 says realtime quality must feed the
    # rules the Decision Engine already uses, and a second gate here would be a second place to allow an entry.
    if at is None and out:
        try:
            obs = FH.observe("mt5_bridge" if market != "crypto" else "binance_public", sym, tf, out,
                             last_updated=d.get("last_updated"), now=iso(t))
            if obs["state"] not in (FH.HEALTHY, FH.UNKNOWN):
                log("feed_health", symbol=sym, tf=tf, state=obs["state"], findings=obs["findings"])
                _require_quality(sym, tf, {"candles": out, "last_updated": d.get("last_updated")},
                                 allow=("FRESH",), now=t, feed_state=FH.as_quality(obs))
            elif obs["recovered"]:
                log("feed_recovered", symbol=sym, tf=tf, findings=obs["findings"])
        except RuntimeError:
            raise                          # a §20 refusal is the point; let it reach tick()'s handler
        except Exception as exc:
            log("note", why=f"feed-health observation failed for {sym} {tf}: {str(exc)[:120]}")
    # §40 `market_event`: the close time of the bar this decision will read. Transport-bound -- we POLL, so
    # the gap between the bar closing and us holding it is the poll interval, not our latency. Recorded so
    # that lag is visible, and summarised apart from the hot stages so it can never be mistaken for one.
    if out and _LAT is not None:
        try:
            _LAT.mark("market_event", max(0.0, (t - parse_t(out[-1]["time"])).total_seconds() * 1000.0))
        except Exception:
            pass                      # measurement never fails a tick (§1)
    return out


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
    two disagreed by roughly an order of magnitude (measured in the legacy-vs-live comparison, deleted with the
    legacy engine on 2026-09-13 -- docs/plans/2026-09-13-collapse-to-one-system.md Task 4). This
    function asks the SAME live scanner the SAME question bt.ict_setups_live asks, at every bar of the window:
    live_rules.read_at() for the facts, live_rules.ict_scan.setup_candidate() for the setup, require
    complete + pd_ok, gate on bt.bias_allows(live_rules.bias_at(...)[0], side). The one difference from
    bt.ict_setups_live: that function decides whether the LIMIT eventually filled (a completed BACKTEST trade,
    via bt.fvg_fill); this one decides whether the LIMIT is STILL working as of the last closed bar (a NEW
    order for the runner to place) -- same fvg_fill call, opposite reading of its result: fvg_fill returning
    non-None (a (bar, outcome) pair) means the limit ALREADY triggered on an earlier bar (an earlier tick
    should already have placed and filled it -- not a new signal); still within its K-bar expiry with no
    trigger at all means it is still a working, placeable order.

    ICT-8 (docs/audits/2026-09-24-system-audit.md): a bar that reaches the stop necessarily also reaches the
    FVG near edge first (for a long, stop < edge always), so fvg_fill now reports that bar as a trigger too
    (outcome "filled_and_stopped") instead of the pre-2026-09-24 behaviour of returning None. `fill is not
    None` below therefore already refuses to offer this as a NEW order once its own invalidation level has
    traded since mss_i -- no separate stop-touch check is needed here.

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


def live_trader():
    """The trader whose custom constraints apply on the live path (automation-config.json execution.trader),
    or None. None is the default and means: the platform's own floors and nothing tighter (plan §0.9).

    The key is NOT in automation.py's DEFAULTS on purpose: `automation.py method|market|...` deep-merges the
    defaults on every write, and a test (CFG-10) holds that those commands touch nothing but their own block.
    It is declared in docs/architecture/schemas/automation-config.schema.json and set by hand."""
    try:
        return json.load(open(AUTOMATION_CONFIG, encoding="utf-8")).get("execution", {}).get("trader") or None
    except Exception:
        return None


def trader_overlay(st, trader):
    """The tightened knobs for this setup under `trader`'s constraints: the overlay of EVERY methodology the
    setup's rule family requires (COMBINED-BOOK -> wyckoff AND ict, each may only tighten), or {} without a trader.

    Keys: `min_rr` (the floor rr_reason applies), `_sessions` (a frozenset of allowed labels, or absent),
    `_max_trades_per_day`, and the BOOL_TRUE_ONLY flags (`htf`, `sloped_gate`) merged
    onto the setup row before its detector runs. Plan §0.9 / CLAUDE.md §35 "Custom Constraints".
    """
    if not trader:
        return {}
    ov = {"min_rr": MIN_RR, **{k: bool(st.get(k)) for k in TC.BOOL_TRUE_ONLY}}
    for dim in mreg.RUNNER_METHODS[st["method"]]["requires"]:
        ov = TC.overlay(ov, trader, dim)
    return ov


def rr_reason(sig, venue, floor=None):
    """Why this signal fails the planned-R:R floor, or None if it passes. `floor` (a trader's tighter floor,
    plan §0.9) can only RAISE the platform floor -- max() below -- never lower it.

    Called from the one reasons[] block every method's signal passes through -- not from each setups() branch:
    ICT and WYCKOFF-BOOK both emit r_planned and both must obey the same floor, and a per-branch copy would
    drift. User decision 2026-09-13: MIN_RR = 3R; 2026-09-19: 2R, the source's own number (both recorded in
    docs/architecture/analysis-params.json `_basis` and policy.json). Before this gate the
    floor existed only as an advisory note printed by ict-scan.py:359 while every decision path ran min_rr=0.0,
    so the runner took setups planning as little as 0.00R -- 38 % of last year's planned under 2R.

    FAILS CLOSED on an unreadable floor too (MIN_RR None, from trading_env.min_rr via bt) -- added after the
    2026-09-13 security review (F1) found this path inheriting a 2.0 fallback that the other live order path did not have, so
    a dropped analysis-params key would have put the live runner back on the superseded 2R floor at the 3 % risk
    ceiling. In practice bt raises at import when the floor is unreadable, so this branch is the second layer.

    FAILS CLOSED on a missing, non-numeric or NaN r_planned, for the same reason the htf gate does (see there):
    an R:R that could not be computed is not permission to trade. Note `rr != rr` is the NaN test -- a NaN would
    make a plain `rr < MIN_RR` False and open the gate, which is exactly the direction that must not happen."""
    if MIN_RR is None:
        return "không đọc được sàn R/R kế hoạch (docs/architecture/analysis-params.json)"
    rr = sig.get("r_planned")
    if not isinstance(rr, (int, float)) or isinstance(rr, bool) or rr != rr:
        return "không tính được R/R kế hoạch"
    # NET of fees since 2026-09-18 (CLAUDE.md §34). `r_planned` is gross -- |target-entry|/|entry-stop| -- but
    # the floor was MEASURED net: analysis-params.json's own basis line says "fee 0.05 %/side", and the
    # backtest behind it subtracts 2*fee/dist from every R (backtest-methods.py:517). Comparing a gross number
    # to a net floor admitted trades the evidence rejected, and by more the tighter the stop: at 0.05 %/side a
    # 1 % stop costs 0.10R and a 0.2 % stop costs 0.50R. The order type is not a guess either -- `entry_now`
    # means a MARKET order at the bar close (taker); everything else rests a post-only GTX limit (maker).
    #
    # DEC-3/PAR-2 (2026-09-24): the EXIT is priced separately from the entry, and is ALWAYS taker -- every
    # exit on this venue is a STOP_MARKET / TAKE_PROFIT_MARKET (or a market close for the time stop), never a
    # resting maker order, regardless of how the entry was placed. Pricing both sides at the entry's order
    # type understated the round-trip cost for every ICT signal (maker entry, taker exit): the gate admitted
    # net-R:R numbers the real fill would not have cleared. On MT5 maker == taker (risk-config.json), so this
    # is a no-op there.
    try:
        r = RM.net_r(sig["entry"], sig["stop"], sig["target"], venue,
                     "taker" if sig.get("entry_now") else "maker", exit_order_type="taker")
    except (RM.RiskRefused, KeyError, TypeError, ValueError) as exc:
        return f"không tính được R/R sau phí: {exc}"
    eff = MIN_RR if floor is None else max(MIN_RR, floor)
    if r["net_r"] < eff:
        who = " (sàn riêng của trader)" if eff > MIN_RR else ""
        return (f"R/R sau phí {r['net_r']:.2f} < {eff} tối thiểu{who} "
                f"(gộp {r['gross_r']:.2f} − {r['cost_r']:.2f}R phí)")
    return None


def setups(method, side, candles, tf, sym=None):
    """Every setup of `method`/`side` in the window whose LIMIT would still be working at the last closed bar.
    ICT (2026-09-13, Task 8): sourced from the LIVE rules -- see ict_live_setups() above -- migrated off the
    legacy bt.all_pivots/bt.find_ict/bt.ict_target proxies so the runner and bt.scan() agree on what an ICT
    setup is. `sym` is required for this path (method resolution, see ict_live_setups); it is otherwise unused.

    `method` is only ever "ICT" here: callers route on `mreg.scan_of(method) == "ict"`, and ICT was the only
    RUNNER_METHOD left with `scan: "ict"` after COMBINED and PARTIAL were removed 2026-09-19
    (docs/audits/2026-09-19-knowledge-fidelity.md finding 6) -- their branch (a Spring/Upthrust proxy identical
    to bt.scan's removed COMBINED block, confirmed by bt.find_ict, LIMIT at the FVG edge) is deleted with them
    The `ict_disp` / `ict_pd` / `std_origin` keyword arguments were REMOVED 2026-09-19 (knowledge audit
    finding 11) rather than kept for call-site compatibility: none of the three could change an ICT setup.
    Displacement is now mandatory inside the scanner, R13's premium/discount gate is `pd_ok` in
    scripts/ict-scan.py and refused unconditionally, and the STDEV fib-0 anchor is the deck's (Model11 p20)."""
    if method != "ICT":
        raise ValueError(f"strategy-runner.setups(): {method!r} is not ICT -- COMBINED and PARTIAL were removed "
                         f"2026-09-19 (docs/audits/2026-09-19-knowledge-fidelity.md finding 6); every other "
                         f"runnable method routes through setups_wyckoff(), not here (see mreg.scan_of)")
    return ict_live_setups(side, candles, tf, sym)


def setups_wyckoff(method, side, candles, tf, sym=None):
    """WYCKOFF-BOOK entries that fire on the LAST CLOSED bar (market at its close). Returns dicts with
    entry_now=True; no limit, no expiry. Only the last bar can be an entry -- earlier bars were our earlier ticks.

    The read itself is bt.wyckoff_fires() -- the SAME function bt.scan() calls window by window since 2026-09-19,
    so this runner and the backtest cannot drift (CLAUDE.md §37); before that the two were parallel copies, and
    the backtest's copy, detecting over the whole history at once, took a Phase D entry the causal read here
    could not see (XAGUSD 4H 2026-07-20; see wyckoff_fires' docstring). The structure gates (sloped / đối
    nhãn / st_min) are read from bt.OPTS inside it.

    `method` is not read below: every RUNNER_METHODS name whose `scan` is "wyckoff" -- mreg.scan_of -- routes
    here, currently WYCKOFF-BOOK and the non-runnable COMBINED-BOOK. The "WYCKOFF" mechanical proxy this
    function used to ALSO detect via a separate branch was removed 2026-09-19 (docs/audits/2026-09-19-knowledge-fidelity.md
    finding 6) along with the runner method of the same name."""
    out = []
    for f in bt.wyckoff_fires(side, candles, tf, sym):
        out.append(dict(time=f["t0"] + ("-D" if f["leg"] == "phase_d" else ""), vol_type=f["rec"]["vol_type"], side=side, entry_now=True,
                        entry=f["entry"], stop=f["stop"], target=f["target"], mss_time=None, bars_left=0, leg=f["leg"],
                        r_planned=abs(f["target"] - f["entry"]) / abs(f["entry"] - f["stop"])))
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
    """The venue's own MIN_NOTIONAL filter for this symbol, or a refusal (CLAUDE.md §34 "instrument
    specifications", §58 "no magic fallback").

    Until 2026-09-18 this swallowed every exception and returned a literal 50.0 -- a number no venue
    published, used to decide whether a real order was large enough to send. Both failure modes were silent
    and both were wrong in a direction that matters: too high and a valid order is skipped; too low and the
    venue rejects it after the runner has already booked the attempt. An instrument specification the venue
    did not answer is UNKNOWN, and an order sized against an unknown minimum is an order sized against a
    guess."""
    if sym not in _MIN_NOTIONAL:
        try:
            raw = order("filters", sym)
        except Exception as exc:
            raise RM.RiskRefused(f"could not read {sym}'s exchange filters ({str(exc)[:120]}); MIN_NOTIONAL "
                                 f"is unknown and will not be guessed")
        # Parse the filter OBJECT, not a span of text. The first version of this read
        # `'MIN_NOTIONAL'.*?'notional': '([0-9.]+)'`, which silently requires the venue to print the keys in
        # that order. Binance does not: BTCUSDT comes back `{'filterType': 'MIN_NOTIONAL', 'notional': '50'}`
        # and SOLUSDT comes back `{'notional': '5', 'filterType': 'MIN_NOTIONAL'}`. So three of the nine
        # execution symbols (SOL, RENDER, ONDO) refused to size on 2026-09-18 against a filter the venue had
        # published -- found by running a real dry tick, not by a test, because every test stubbed this out.
        found = None
        for blob in re.findall(r"\{[^{}]*\}", raw):
            if "'MIN_NOTIONAL'" in blob:
                m = re.search(r"'notional': '([0-9.]+)'", blob)
                if m:
                    found = float(m.group(1))
                break
        if found is None:
            raise RM.RiskRefused(f"{sym}'s exchange filters carry no readable MIN_NOTIONAL entry; refusing "
                                 f"to assume one")
        _MIN_NOTIONAL[sym] = found
    return _MIN_NOTIONAL[sym]


def mt5_symbol(sym):
    """Contract data the bridge EA publishes (tick_size, tick_value, volume_min/max/step, digits)."""
    if sym not in _MT5_SYMBOLS:
        _MT5_SYMBOLS[sym] = mt5_json("symbol", sym)
    return _MT5_SYMBOLS[sym]


def client_id(setup_id, sym, sig):
    """The id the venue sees. Unique per (account, setup, symbol, side, signal time).

    A drill order (docs/plans/2026-09-18-close-feature-gaps.md §0.11) is findable at the venue by its prefix
    alone, so a post-drill audit never has to guess which fill was the rehearsal.

    ACCOUNT is in the digest since 2026-09-19. Without it, two accounts taking the same signal mint the SAME
    newClientOrderId -- which a venue rejects as a duplicate, so the second customer silently loses the trade
    and the rejection looks like a venue fault rather than an id collision (plan §0.3 item 1).
    """
    prefix = "drill-" if sig.get("drill") else "t5-"
    seed = f"{ACCOUNT or '-'}|{setup_id}|{sym}|{sig['side']}|{sig['time']}"
    return prefix + hashlib.sha1(seed.encode()).hexdigest()[:20]


DRILL_RR = 3.5          # GROSS planned R of the synthetic signal. The live floor (bt.MIN_RR; 2.0 since 2026-09-19, was 3.0) is applied NET of fees
                        # (§37, 2026-09-18): with the 0.4 % minimum stop a taker round-trip costs up to 0.25R, so 3.0 gross
                        # would be refused by the gate it is meant to exercise. 3.5 gross clears the floor and still exercises it.
DRILL_MIN_STOP_PCT = 0.004


def drill_signal(candles, side):
    """The ONE synthetic signal a `--drill` tick evaluates (plan §0.11): a market entry at the last CLOSED bar's
    close, stop = max(0.4 %, 1.5 x mean true range over 20 bars) away, target = DRILL_RR (3.5R gross) beyond.

    Everything after this function is the real decision walk -- data quality, event risk, session, account,
    HTF gate, risk calculation and validation, final news, eligibility, `tr.verify()`, the venue submit. The
    drill replaces the SETUP DETECTION step only, because that is the one step whose timing nobody controls:
    proving that "a signal becomes an order and comes back to the page" cannot wait for the market to produce
    a Spring at a convenient hour. A refusal by any later step is a real refusal and is logged as one.
    """
    if len(candles) < 21:
        raise ValueError("drill needs at least 21 closed bars (20 for the true-range mean plus the entry bar)")
    last = candles[-1]
    trs = []
    for prev, cur in zip(candles[-21:-1], candles[-20:]):
        trs.append(max(cur["high"] - cur["low"], abs(cur["high"] - prev["close"]), abs(cur["low"] - prev["close"])))
    entry = float(last["close"])
    risk = max(DRILL_MIN_STOP_PCT * entry, 1.5 * sum(trs) / len(trs))
    long = side == "long"
    stop = entry - risk if long else entry + risk
    target = entry + DRILL_RR * risk if long else entry - DRILL_RR * risk
    return dict(time=last["time"], mss_time=last["time"], vol_type=1, side=side, entry_now=True, entry=entry,
                stop=stop, target=target, bars_left=0, r_planned=DRILL_RR, drill=True)


def parse_drill(spec):
    """`--drill <setup-id>:<symbol>:<long|short>` -> dict, or a ValueError naming what is wrong."""
    parts = (spec or "").split(":")
    if len(parts) != 3 or not all(parts):
        raise ValueError(f"--drill wants <setup-id>:<symbol>:<long|short>, got {spec!r}")
    setup_id, sym, side = parts
    if side not in ("long", "short"):
        raise ValueError(f"--drill side must be long or short, got {side!r}")
    return {"setup": setup_id, "symbol": sym, "side": side}


def drill_refusal(drill, *, live, env_name, config_env, gate_reason, setups_known, symbols_enabled):
    """Why this drill may NOT run, or None. Pure so the refusals are testable without a venue.

    §51: a drill is a REAL order on fake money and nothing else. Every condition here is a condition under
    which "fake money" or "nothing else" would stop being true.
    """
    if not live:
        return "a drill places a real testnet/demo order and needs --live (it is refused in --dry-run)"
    if env_name != "demo":
        return f"a drill runs only in the demo environment; the active environment is {env_name!r}"
    if config_env != "demo":
        return f"a drill runs only while automation-config.json execution.environment is 'demo' (it is {config_env!r})"
    if gate_reason:
        return f"the automation gate refuses the tick, so it refuses the drill too: {gate_reason}"
    if drill["setup"] not in setups_known:
        return f"no selected setup {drill['setup']!r} (have {sorted(setups_known)})"
    if drill["symbol"] not in symbols_enabled:
        return f"{drill['symbol']!r} is not an enabled execution symbol for that setup's market ({sorted(symbols_enabled)})"
    return None


def size(equity, entry, stop, risk_mult, leverage=None, *, entry_order_type="taker", exit_order_type="taker",
         venue="futures"):
    """qty so that the loss AT THE STOP -- price distance AND the round-trip fee -- equals risk_usd.

    DEC-4 (CLAUDE.md §34 'fees, slippage'): sizing on price distance alone understates the realised loss at
    the stop by the round-trip fee, so it exceeds the 1 % ceiling (worse the tighter the stop). Every exit on
    this venue is a STOP_MARKET/TAKE_PROFIT_MARKET (taker); `entry_order_type` is the setup's own -- ICT
    rests a maker limit, WYCKOFF-BOOK enters at market/taker -- and callers pass it accordingly. Fails the
    same way `min_notional`/`mt5_symbol` do (RM.RiskRefused) rather than silently sizing on a guessed fee.

    Round-4 note: the backtest's own sizing (backtest-methods.py simulate(), PAR-4) still sizes on price
    distance alone, so this is a LIVE-ONLY fix and widens the existing live/backtest sizing mismatch PAR-4
    already tracks -- not fixed here (scripts/backtest-methods.py is out of round-1 scope).
    """
    leverage = futures_leverage() if leverage is None else leverage
    r = abs(entry - stop); risk_usd = equity * RISK_PCT * risk_mult
    entry_fee = RM.costs(venue, entry_order_type)["fee_pct_per_side"]
    exit_fee = RM.costs(venue, exit_order_type)["fee_pct_per_side"]
    per_unit = r + entry * entry_fee + stop * exit_fee
    qty = risk_usd / per_unit
    cap = equity * NOTIONAL_CAP_PCT * leverage
    if qty * entry > cap:
        qty = cap / entry
    return qty, risk_usd


def mt5_lots(sym, equity, entry, stop, risk_mult, *, entry_order_type="taker", exit_order_type="taker"):
    """Lots so that the stop distance AND the round-trip fee lose risk_usd (DEC-4, same reasoning as `size`
    above): risk / ((ticks in the all-in loss) x tick_value). Rounded DOWN to volume_step.

    On MT5, maker_pct_per_side == taker_pct_per_side (risk-config.json: the broker prices in the spread, not
    a side-dependent commission), so `entry_order_type`/`exit_order_type` do not change the number today --
    they exist so a future asymmetric MT5 cost model does not need a second call site change."""
    info = mt5_symbol(sym); risk_usd = equity * RISK_PCT * risk_mult
    entry_fee = RM.costs("mt5", entry_order_type)["fee_pct_per_side"]
    exit_fee = RM.costs("mt5", exit_order_type)["fee_pct_per_side"]
    value_per_price_unit = float(info["tick_value"]) / float(info["tick_size"])
    per_unit = abs(entry - stop) + entry * entry_fee + stop * exit_fee
    per_lot = per_unit * value_per_price_unit
    lots = risk_usd / per_lot if per_lot > 0 else 0.0
    step = float(info["volume_step"]); lots = int(lots / step) * step
    lots = min(lots, float(info["volume_max"]))
    return round(lots, 8), risk_usd, per_lot


def risk_precheck(sym, st, sig, equity, risk_mult):
    """CLAUDE.md §36 step 12 -- the RISK CALCULATION, run at its canonical position. Refusal string, or None.

    Until 2026-09-18 the two calculations that can refuse -- `min_notional()` (futures) and the volume_min
    floor (MT5) -- ran inside `place_limit()`/`place_market()`, which is §36 step 17. So a signal that could
    not be sized was declared eligible at step 16 and then silently did nothing at 17. §36 puts risk
    calculation at 12 and risk validation at 13, both BEFORE final eligibility, precisely so that "cannot be
    sized" is a decision rather than an anticlimax.

    It computes no order payload: rounding, the venue call and the final guard stay in `place_*()`, which
    remains the authority (its guard runs on the ROUNDED quantity, this one on the raw). The precheck exists
    to move the REFUSAL, not to duplicate the arithmetic.
    """
    try:
        if st["execution"] == "mt5":
            info = mt5_symbol(sym)
            lots, _risk_usd, _per_lot = mt5_lots(sym, equity, sig["entry"], sig["stop"], risk_mult)
            if lots < float(info["volume_min"]):
                return (f"không đủ khối lượng: {lots:g} lot < volume_min {info['volume_min']} "
                        f"(rủi ro quá nhỏ so với khoảng stop)")
        else:
            qty, _risk_usd = size(equity, sig["entry"], sig["stop"], risk_mult,
                                  entry_order_type="taker" if sig.get("entry_now") else "maker")
            floor = min_notional(sym)
            if qty * sig["entry"] < floor:
                return f"giá trị lệnh {qty * sig['entry']:.2f} < tối thiểu sàn {floor}"
    except RM.RiskRefused as exc:
        return f"không tính được kích thước lệnh: {exc}"
    except Exception as exc:                         # a venue/bridge failure is UNKNOWN, never permission
        return f"không tính được kích thước lệnh: {str(exc)[:160]}"
    return None


def mandate_of(setup_id):
    """The mandate id under which THIS account is running `setup_id`, or None.

    Attribution (docs/plans/2026-09-19-multi-account.md §0.3 item 1): a customer asking "which methodology
    took this trade, on which version, under which agreement" must be answerable from the record alone, and
    for billing the same record is the invoice line. None in the house's own single-account mode, where there
    is no agreement to point at -- absent rather than invented.
    """
    if not ACCOUNT:
        return None
    try:
        rows = MD.for_account(ACCOUNT)
    except Exception:            # a mandate table this process cannot read must not stop an order it already
        return None              # decided on other grounds; the missing attribution shows up as a null field
    return next((m["id"] for m in rows if m["setup"] == setup_id), None)


def plan_of(sym, st, sig, qty, px, stop, tp, risk_usd, expectations=None):
    return dict(symbol=sym, strategy=st["id"], setup_version=st.get("rule_version"), mandate=mandate_of(st["id"]), tf=st["tf"], method=st["method"], side=sig["side"].upper(), qty=qty, price=px, stop=stop, tp=tp,
                leverage=futures_leverage() if st["execution"] == "futures" else 1, risk_usd=round(risk_usd, 2), notional=round(float(qty) * float(px), 2),
                sweep_time=sig["time"], mss_time=sig["mss_time"], expires_bar_left=sig["bars_left"], htf_pass=sig["htf_pass"], r_planned=round(sig["r_planned"], 2),
                execution=st["execution"], mgmt=st.get("mgmt", "be"), drill=bool(sig.get("drill")),
                # §0.6: one to_json() blob per EP.from_signal() record (step 11) -- never rebuilt here, so the
                # plan's ids match the ones the step-11 expectation trace entry already named.
                expectations=[X.to_json(r) for r in (expectations or [])])


def place_limit(sym, st, sig, equity, risk_mult, live, expectations=None):
    long = sig["side"] == "long"; venue = st["execution"]
    if venue == "mt5":
        info = mt5_symbol(sym); d = int(info.get("digits", 2))
        lots, risk_usd, per_lot = mt5_lots(sym, equity, sig["entry"], sig["stop"], risk_mult)
        px = f"{sig['entry']:.{d}f}"; stop = f"{sig['stop']:.{d}f}"; tp = f"{sig['target']:.{d}f}"
        plan = plan_of(sym, st, sig, f"{lots:g}", px, stop, tp, min(risk_usd, lots * per_lot), expectations=expectations)
        if lots < float(info["volume_min"]):
            log("skip", venue="mt5", why=f"lots {lots:g} below volume_min {info['volume_min']} (risk too small for this stop)", **plan); return None
        if not live:
            log("dry_run_limit", venue="mt5", **plan); return None
        cid = client_id(st["id"], sym, sig)
        # §40 `order_submission` / `provider_acknowledgement`: the venue call, and the work that turns its
        # answer into a confirmed order id. A synchronous REST/file bridge cannot separate "sent" from
        # "answered", so the call is the submission and the confirmation that follows is the acknowledgement.
        _ack = None
        with _span("order_submission"):
            o = mt5_json("limit", sym, "buy" if long else "sell", f"{lots:g}", px, stop, tp, cid)
        _ack = _t0()
        if not o.get("ok"):
            log("rejected", venue="mt5", note=f"MT5 retcode {o.get('retcode')} {o.get('comment')}", **plan); return None
        pend = dict(plan, order_id=o["ticket"], client_id=cid, placed_at=iso(now()), bars_waited=0)
        _rec("provider_acknowledgement", _ack)
        log("limit_placed", venue="mt5", **pend)
        return pend
    # A post-only GTX limit is a MAKER entry; every exit is still taker (DEC-4, size()'s own docstring).
    qty, risk_usd = size(equity, sig["entry"], sig["stop"], risk_mult, entry_order_type="maker")
    qty_r = order("round-qty", sym, f"{qty:.8f}").strip(); px_r = order("round-price", sym, f"{sig['entry']:.8f}").strip()
    stop_r = order("round-price", sym, f"{sig['stop']:.8f}").strip(); tp_r = order("round-price", sym, f"{sig['target']:.8f}").strip()
    plan = plan_of(sym, st, sig, qty_r, px_r, stop_r, tp_r, min(risk_usd, float(qty_r) * abs(float(px_r) - float(stop_r))), expectations=expectations)
    try:
        floor_notional = min_notional(sym)
    except RM.RiskRefused as exc:
        log("skip", why=f"không đọc được MIN_NOTIONAL: {exc}", **plan); return None
    if float(qty_r) * float(px_r) < floor_notional:
        log("skip", why=f"notional below exchange minimum {floor_notional}", **plan); return None
    if not live:
        log("dry_run_limit", **plan); return None
    sh(ORDER, "set-margin-type", sym, "ISOLATED", check=False)
    order("set-leverage", sym, str(futures_leverage()))
    cid = client_id(st["id"], sym, sig)
    _ack = None
    try:
        with _span("order_submission"):
            o = order_json("open-long-limit" if long else "open-short-limit", sym, qty_r, px_r, cid)
        _ack = _t0()
    except RuntimeError as e:
        if "-5022" in str(e):
            log("gtx_rejected", note="post-only limit would have taken liquidity -- signal dropped", **plan); return None
        # The recovery lookup is part of getting an acknowledgement, so it is timed as one.
        _ack = _t0()
        o = order_json("order-by-client-id", sym, cid)
        if not o.get("orderId"):
            raise
    if o.get("status") == "EXPIRED" or not o.get("orderId"):
        log("gtx_rejected", note="post-only limit would have taken liquidity -- signal dropped", **plan); return None
    pend = dict(plan, order_id=o["orderId"], client_id=cid, placed_at=iso(now()), bars_waited=0)
    _rec("provider_acknowledgement", _ack)
    log("limit_placed", **pend)
    return pend


FILL_POLLS = 5          # order-status polls before a market fill is declared unreadable (0.4 s apart)


def market_fill(sym, o, qty_r, *, polls=FILL_POLLS, sleep=0.4):
    """(avg_px, filled_qty) of a MARKET order, from the VENUE -- never from the plan.

    Found by the 2026-09-18 drill (docs/audits/2026-09-18-e2e-drill.md): the testnet's RESULT response carried
    `avgPrice: "0"` for an order that had in fact filled at 79 767, and the previous line here fell back to the
    PLANNED price (80 073). Every downstream number -- the stop distance, the recorded R, the realised P&L, the
    journal's Edge Log -- then measured a fill that never happened (-0.99R recorded, -0.24R real). §37/§39: the
    fill is a venue fact. Poll the order until the venue states it; if it will not, raise -- a position whose
    entry is unknown is reported as such (UNKNOWN, §20), not guessed.
    """
    avg = float(o.get("avgPrice") or 0); qty = float(o.get("executedQty") or 0)
    for _ in range(polls):
        if avg > 0 and qty > 0:
            return avg, qty
        time.sleep(sleep)
        st = order_json("order-status", sym, str(o["orderId"]))
        avg = float(st.get("avgPrice") or 0); qty = float(st.get("executedQty") or 0)
    if avg > 0 and qty > 0:
        return avg, qty
    raise RuntimeError(f"{sym} market order {o.get('orderId')}: fill price unreadable after {polls} polls "
                       f"(avgPrice={avg}, executedQty={qty}); refusing to record the planned price as the fill")


FILL_RISK_TOLERANCE = 0.10  # DEC-5: how far the realised loss-at-stop may exceed the PLANNED risk_usd
                            # before it is disclosed as a breach. Not a new risk ceiling -- RISK_CEILING is
                            # that -- this is only how sensitive the disclosure is to ordinary fill noise.


def revalidate_fill(sym, pos, planned_risk_usd, entry_order_type):
    """CLAUDE.md §34 'Risk must be validated before execution' / §51 'Before execution validate: ... risk';
    §55 adversarial 'stale price / changed market' -- DEC-5.

    A MARKET order is sized and R:R-checked (steps 12-13) against the last bar's CLOSE; the venue can fill
    away from that price, and nothing re-checked the ACTUAL fill until now. This cannot undo a fill already
    booked -- the only safe unwind is a second order against the book, and the DEC-5 fix critique is explicit
    that this needs its own design decision, not one made inside a risk-revalidation helper -- so it
    DISCLOSES a breach (a `fill_risk_breach` log line) rather than silently recording a plan that was never
    true of the trade that was actually taken.
    """
    breaches = []
    if planned_risk_usd and pos["risk_usd"] > planned_risk_usd * (1 + FILL_RISK_TOLERANCE):
        breaches.append({"check": "risk_usd", "planned": round(planned_risk_usd, 2), "actual": round(pos["risk_usd"], 2)})
    try:
        rr = RM.net_r(pos["entry"], pos["stop"], pos["tp"], pos["execution"], entry_order_type, exit_order_type="taker")
        if MIN_RR is not None and rr["net_r"] < MIN_RR:
            breaches.append({"check": "net_rr", "actual_net_r": round(rr["net_r"], 3), "floor": MIN_RR})
    except RM.RiskRefused:
        pass          # the pre-submit check already required a computable R:R; a refusal recomputing it at
                      # the fill price is not new information worth a second refusal on an open position
    if breaches:
        log("fill_risk_breach", venue=pos["execution"], symbol=sym, fill_price=pos["entry"], breaches=breaches,
            note="the fill differed enough from the planned entry that the risk or R:R this trade was "
                 "approved under no longer holds at the actual fill price (DEC-5); the position is already "
                 "open, so this is a disclosure for human review, not a block")
    return breaches


def _safe_revalidate_fill(sym, pos, planned_risk_usd, entry_order_type):
    """Code review fix round 1 (DEC-5, BLOCKING): `revalidate_fill` itself only swallows `RM.RiskRefused`
    (a known, expected refusal). Any OTHER exception -- a KeyError on a malformed `pos`, a connector hiccup
    inside `RM.net_r`'s config read, anything unforeseen -- used to propagate straight out of `place_market()`
    AFTER the entry (and its protective stop, already placed by `open_position`) had already filled and been
    protected on the exchange. `place_market()` would then never reach its own `return pos`, so the caller in
    `tick()` would never add the position to `s["positions"]` -- an already-protected, already-real position
    silently dropped from the runner's own bookkeeping. Disclosure (DEC-5's whole point) must never be able to
    cost the runner its record of a position that is already safely opened.
    """
    try:
        return revalidate_fill(sym, pos, planned_risk_usd, entry_order_type)
    except Exception as exc:
        log("fill_revalidate_error", venue=pos.get("execution"), symbol=sym, msg=str(exc)[:200],
            note="revalidate_fill() raised after the entry and its protective stop were already placed -- "
                 "the position is kept (this is a disclosure step, not a gate) and the failure is only logged")
        return None


def place_market(sym, st, sig, equity, risk_mult, live, expectations=None, entry_bar_time=None):
    """Wyckoff entry at the close of the entry bar: MARKET order, then the protective orders (futures) / SL+TP attached (MT5).

    `entry_bar_time` (PAR-1): the open time of the bar whose CLOSE is this entry -- wyckoff_fires() only fires
    on the last bar of the window it was given, so the caller (tick(), which holds that window) passes its
    open time straight through to open_position(); `sig["time"]` cannot be used for this because it carries
    the structure's Spring/SOS bar (or, for a Phase D fire, that time with a literal "-D" suffix appended --
    a dedup key, not a timestamp), not the entry bar.
    """
    long = sig["side"] == "long"; venue = st["execution"]
    if venue == "mt5":
        info = mt5_symbol(sym); d = int(info.get("digits", 2))
        lots, risk_usd, per_lot = mt5_lots(sym, equity, sig["entry"], sig["stop"], risk_mult)
        stop = f"{sig['stop']:.{d}f}"; tp = f"{sig['target']:.{d}f}"
        plan = plan_of(sym, st, sig, f"{lots:g}", f"{sig['entry']:.{d}f}", stop, tp, min(risk_usd, lots * per_lot), expectations=expectations); plan["order_type"] = "market"
        if lots < float(info["volume_min"]):
            log("skip", venue="mt5", why=f"lots {lots:g} below volume_min {info['volume_min']}", **plan); return None
        if not live:
            log("dry_run_market", venue="mt5", **plan); return None
        cid = client_id(st["id"], sym, sig)
        with _span("order_submission"):
            o = mt5_json("market", sym, "buy" if long else "sell", f"{lots:g}", stop, tp, cid)
        _ack = _t0()
        if not o.get("ok"):
            log("rejected", venue="mt5", note=f"MT5 retcode {o.get('retcode')} {o.get('comment')}", **plan); return None
        pend = dict(plan, order_id=o["ticket"], client_id=cid, placed_at=iso(now()), bars_waited=0, price=f"{float(o.get('price') or sig['entry']):.{d}f}")
        _rec("provider_acknowledgement", _ack)
        pos = open_position(sym, pend, float(o.get("volume") or lots), float(o.get("price") or sig["entry"]), live, position_ticket=o.get("ticket"), entry_bar_time=entry_bar_time)
        if pos is not None:
            _safe_revalidate_fill(sym, pos, risk_usd, "taker")
        return pos
    # Wyckoff enters at the bar close (market/taker); size() prices the exit as taker regardless.
    qty, risk_usd = size(equity, sig["entry"], sig["stop"], risk_mult, entry_order_type="taker")
    qty_r = order("round-qty", sym, f"{qty:.8f}").strip(); px_r = order("round-price", sym, f"{sig['entry']:.8f}").strip()
    stop_r = order("round-price", sym, f"{sig['stop']:.8f}").strip(); tp_r = order("round-price", sym, f"{sig['target']:.8f}").strip()
    plan = plan_of(sym, st, sig, qty_r, px_r, stop_r, tp_r, min(risk_usd, float(qty_r) * abs(float(px_r) - float(stop_r))), expectations=expectations); plan["order_type"] = "market"
    try:
        floor_notional = min_notional(sym)
    except RM.RiskRefused as exc:
        log("skip", why=f"không đọc được MIN_NOTIONAL: {exc}", **plan); return None
    if float(qty_r) * float(px_r) < floor_notional:
        log("skip", why=f"notional below exchange minimum {floor_notional}", **plan); return None
    if not live:
        log("dry_run_market", **plan); return None
    sh(ORDER, "set-margin-type", sym, "ISOLATED", check=False)
    order("set-leverage", sym, str(futures_leverage()))
    with _span("order_submission"):
        o = order_json("open-long" if long else "open-short", sym, qty_r)
    _ack = _t0()
    if not o.get("orderId"):
        log("rejected", note="market order not accepted", **plan); return None
    avg_px, filled = market_fill(sym, o, qty_r)
    pend = dict(plan, order_id=o["orderId"], client_id=client_id(st["id"], sym, sig), placed_at=iso(now()), bars_waited=0, price=f"{avg_px:.8f}")
    _rec("provider_acknowledgement", _ack)
    # §40 `fill`: a MARKET order is filled at acknowledgement, so the venue's own fill is known here. A LIMIT
    # order's fill is learned on a later tick's reconcile and is transport-bound by construction.
    pos = open_position(sym, pend, filled, avg_px, live, entry_bar_time=entry_bar_time)
    if pos is not None:
        _safe_revalidate_fill(sym, pos, risk_usd, "taker")
    return pos


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


def open_position(sym, pend, filled_qty, avg_px, live, position_ticket=None, entry_bar_time=None):
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
    # DEC-2: for MT5, `filled_qty` is LOTS, not units -- risk_usd = price distance x lots silently drops the
    # contract multiplier (per_lot = tick_value/tick_size), so the recorded R-multiple was wrong by that
    # factor on every MT5 exit (close_record divides pnl by this risk_usd). Futures `filled_qty` is already
    # in the instrument's own units, so price distance x qty is correct there unchanged.
    if venue == "mt5":
        info = mt5_symbol(sym)
        risk_usd = r * (float(info["tick_value"]) / float(info["tick_size"])) * filled_qty
    else:
        risk_usd = r * filled_qty
    # PAR-1 (CLAUDE.md §37): the bar the entry actually filled in -- never the wall-clock minute of the tick
    # that noticed it, which is what `manage_position`'s `since` used to anchor on and which excludes the
    # first bar after entry forever (that bar's OPEN is always earlier than the detecting tick's minute).
    # Callers that know the entry bar (place_market, from the same window it detected the signal on) pass it;
    # a caller that does not (a limit fill, only known when a later tick's reconcile discovers it) falls back
    # to flooring "now" to this tf's grid -- an approximation, not exact to the fill minute, but no longer
    # excludes the correct bar by a full period the way the wall-clock anchor did.
    entry_bar_time = entry_bar_time or bar_open_time(iso(now()), pend["tf"])
    pos = dict(side=pend["side"], strategy=pend["strategy"], tf=pend["tf"], method=pend["method"], execution=venue, mgmt=pend["mgmt"],
               qty=f"{filled_qty:.8f}".rstrip("0").rstrip("."), entry=avg_px, entry_order=pend["order_id"], client_id=pend.get("client_id"),
               position_ticket=position_ticket, stop=float(pend["stop"]), tp=float(pend["tp"]), stop_order=sl.get("orderId"), tp_order=tp.get("orderId"),
               leverage=pend["leverage"], opened_at=iso(now()), entry_bar_time=entry_bar_time, bars=0, risk_usd=round(risk_usd, 2), be=False, be_level=(avg_px + r) if long else (avg_px - r),
               htf_pass=pend["htf_pass"], sweep_time=pend["sweep_time"], mss_time=pend["mss_time"], risk_pct=RISK_PCT,
               # §0.6: carried from the plan (already to_json()'d expectation.create() records, step 11), not
               # rebuilt -- log("entry", ..., **pos) is what scripts/journal.py sync_pilot reads `expectations` from.
               expectations=pend.get("expectations") or [],
               # plan §0.11: the drill flag rides the plan -> pending -> position -> `entry` log row -> journal, so
               # a rehearsal order is never counted as an edge anywhere downstream.
               drill=bool(pend.get("drill")))
    log("entry", venue=venue, symbol=sym, market=("mt5_demo" if venue == "mt5" else MARKET_LABEL), env=ENV_NAME, **pos)
    return pos


def mt5_close(ticket, *, polls=5, sleep=0.4):
    """Close an MT5 position and return `(price, profit)` from the VENUE.

    The EA's `close` reply deliberately carries `profit: 0` with the note "read position_status after the deal
    settles" (integrations/mt5/OrderBridge.mq5), so the old `float(r.get("profit") or 0)` recorded 0.0 for every
    MT5 close -- the 2026-09-18 drill flattened XAUUSD at -44 on the demo equity and the journal said 0.0
    (docs/audits/2026-09-18-e2e-drill.md §4.3). Poll `position-status` until it reports `state: closed` and
    take its `price_close` / `profit` (deal profit + commission + swap, summed by the EA). If it never settles,
    fall back to the close price with profit None -- close_record then computes the gross P&L from prices
    and the record says the venue profit was UNREADABLE rather than 0.
    """
    r = mt5_json("close", str(ticket))
    price = float(r.get("price") or 0)
    for _ in range(polls):
        time.sleep(sleep)
        st = mt5_json("position-status", str(ticket))
        if st.get("state") == "closed":
            return float(st.get("price_close") or price), (float(st["profit"]) if st.get("profit") is not None else None)
    return price, None


def close_record(sym, pos, px, via, qty, pnl=None):
    """DEC-8 (CLAUDE.md §37/§39): when no caller supplies the venue's own realised P&L -- true for every
    futures exit today; MT5's `pnl` is always passed in already net of commission/swap, see `mt5_close` --
    this used to compute GROSS P&L from prices only, while the backtest that selected these setups books NET
    of the round-trip fee (backtest-methods.py:1016, net_R = R - fee_R). Live-vs-backtest comparisons were
    biased in the live pilot's favour, and a fee-losing breakeven exit (gross P&L ~= 0) was never counted as
    a loss for consec_losses. `pnl`/`r` below are now NET for a computed close; `pnl_gross` keeps the
    price-only figure that used to be the whole story, so nothing here is a silent number change."""
    sign = 1 if pos["side"] == "LONG" else -1
    gross = (px - pos["entry"]) * float(qty) * sign
    computed = pnl is None
    if computed:
        try:
            # Code review fix round 1 (nit): mreg.scan_of() raises KeyError for a method name the registry
            # does not declare -- not RM.RiskRefused -- so it must be inside the same catch as the fee read
            # below, or an unknown/renamed method breaks the close path outright instead of falling back.
            entry_type = "maker" if mreg.scan_of(pos["method"]) == "ict" else "taker"
            fee_entry = RM.costs(pos["execution"], entry_type)["fee_pct_per_side"]
            fee_exit = RM.costs(pos["execution"], "taker")["fee_pct_per_side"]
            pnl = gross - (pos["entry"] * fee_entry + px * fee_exit) * float(qty)
        except (RM.RiskRefused, KeyError):
            pnl = gross          # an unreadable fee must not block recording the close; it is disclosed via
                                 # the absent `pnl_gross`-vs-`pnl` gap rather than assumed to be zero
    rec = dict(symbol=sym, side=pos["side"], strategy=pos["strategy"], tf=pos["tf"], execution=pos["execution"], exit=px, via=via, pnl=round(pnl, 2),
                r=round(pnl / pos["risk_usd"], 2) if pos["risk_usd"] else None, entry=pos["entry"], qty=qty, opened_at=pos["opened_at"], closed_at=iso(now()),
                htf_pass=pos["htf_pass"], be=pos["be"])
    if computed:
        rec["pnl_gross"] = round(gross, 2)
    return rec


def manage_pending(sym, pend, live, bars_elapsed, t=None):
    """('filled', qty, px, position_ticket) | ('waiting', ...) | ('gone', ...).

    DEC-1 (CLAUDE.md §24/§31/§32): a RESTING order must not be allowed to fill inside an event-risk blackout.
    Before this fix, event_blackout() was checked ONLY at placement (the decision-engine step 14 in tick());
    once resting, a limit could keep working through a blackout that opened after it was placed and fill
    inside the ±10 minute NEW ENTRY window §24 forbids. Checked here, every tick this order is still pending,
    with a one-bar (this order's own timeframe) look-ahead so a window opening between two ticks is still
    very likely caught before it is missed entirely -- cancelled the same way the STOP kill switch cancels a
    working order (_tick()'s halted() branch, 'stop_cancel_pending').

    Residual gap the fix critique names and this does not close: the look-ahead is one bar of THIS order's
    own timeframe, not the runner's actual tick cadence (which this function has no way to read), so a
    restricted window shorter than the gap between two real ticks could still open and close between them
    unseen. The default window is >=20 minutes (pre_minutes + post_minutes); the fastest configured setups in
    this pilot are 15m, well inside that margin.
    """
    if not live:
        return "waiting", None, None, None
    when = t or now()
    why = event_blackout(when, sym) or event_blackout(when + datetime.timedelta(seconds=TF_SEC[pend["tf"]]), sym)
    if why:
        # Code review fix round 1 (DEC-1, BLOCKING): the cancel and the fill can race -- the venue may have
        # already matched this order in the instant before the cancel reaches it. Returning "gone" here
        # unconditionally used to let _tick() delete the pending entry believing nothing happened, while a
        # real, now-untracked, STOP-LESS position sat on the exchange. Re-check order status AFTER the cancel,
        # exactly like the expiry-cancel branches below, and route a filled/partially-filled order through the
        # normal "filled" return so _tick() calls open_position() (which places the stop) instead of dropping it.
        if pend["execution"] == "mt5":
            mt5_json("cancel", str(pend["order_id"]))
            st = mt5_json("order-status", str(pend["order_id"]))
            log("event_cancel_pending", venue="mt5", symbol=sym, order_id=pend["order_id"], why=why,
                fill_state=st.get("state"))
            if st.get("state") == "filled":
                return "filled", float(st.get("volume") or pend["qty"]), float(st.get("price") or pend["price"]), st.get("position_ticket")
            return "gone", None, None, None
        sh(ORDER, "cancel-order", sym, str(pend["order_id"]), check=False)
        st = order_json("order-status", sym, str(pend["order_id"])); ex = float(st.get("executedQty") or 0)
        log("event_cancel_pending", venue=pend["execution"], symbol=sym, order_id=pend["order_id"], why=why, executed=ex)
        return ("filled", ex, float(st.get("avgPrice") or pend["price"]), None) if ex > 0 else ("gone", None, None, None)
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
    # PAR-1 (CLAUDE.md §37): anchored on the ENTRY BAR's own open time, strictly after it -- not on the
    # wall-clock minute of the tick that noticed the fill. `opened_at` is that wall clock, and it is always
    # AFTER the entry bar's close (the fill is discovered on a LATER tick than the bar that produced it), so
    # filtering on it excluded the first bar after entry forever: the backtest arms breakeven starting on that
    # exact bar (walk() runs from entry_bar+1) and never on the entry/fill bar itself, which is why this is a
    # strict `>` against `entry_bar_time`, not `>=`. A position opened before this fix has no `entry_bar_time`
    # on disk; falling back to the old wall-clock anchor there is the ONLY safe choice -- guessing a bar time
    # for a position already this runner does not know precisely would be inventing history, not recovering it.
    since_anchor = pos.get("entry_bar_time") or (pos["opened_at"][:16] + ":00Z")
    cmp = (lambda t: t > since_anchor) if pos.get("entry_bar_time") else (lambda t: t >= since_anchor)
    since = [x for x in candles if cmp(x["time"])]
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
            px_c, profit = mt5_close(pos["position_ticket"] or pos["entry_order"])
            if px_c:
                return close_record(sym, pos, px_c, "TIME", pos["qty"], pnl=profit)
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
    """Which execution venue this symbol's orders go to, resolved from the registry (CLAUDE.md §4).

    Was `"futures" if sym in CRYPTO else "mt5"` -- a symbol-membership test with two faults. It hard-coded the
    market->venue mapping in the order engine, and its `else` was fail-OPEN: any symbol the engine did not
    recognise, including a typo or a symbol removed from the allowlist, resolved to the MT5 venue rather than
    refusing. In a path that decides where an order is submitted, "I don't recognise this, I'll use MT5" is
    exactly the silent provider switching CLAUDE.md §6 forbids.

    Now: market comes from the instrument allowlist, venue comes from the provider registry's single
    unattended execution provider for that market, and an unknown symbol raises. The resolved values are
    unchanged for every allowlisted symbol (crypto->futures, cfd->mt5, forex->mt5); scripts/tests/
    test_execution_router.py pins that equivalence symbol by symbol.
    """
    market = instruments.market_of(sym)
    if market is None:
        raise ValueError(f"{sym} is not on the instrument allowlist (docs/architecture/instruments.json); "
                         f"refusing to guess a venue for it")
    return P.unattended_venue_for(market)


def tick(live, tick_time=None, ignore_gate=False, drill=None):
    """One pass of the live loop.

    CLAUDE.md §40: the whole pass runs inside ONE latency trace, opened here and written on the way out
    whatever happened -- the STOP-file return, the automation-gate return, the halt return, an exception. The
    module-level `_LAT` is what lets `fetch_candles`, `risk_precheck` and `place_*` time their own stage
    without a parameter threaded through every call site of a 1,700-line order path; it is cleared in the same
    `finally` that writes the trace, so nothing outside a tick can record into a stale one.
    """
    global _LAT
    with LAT.tick("live" if live else "dry") as _trace:
        _LAT = _trace
        try:
            return _tick(live, tick_time, ignore_gate, drill)
        finally:
            _LAT = None


def _tick(live, tick_time=None, ignore_gate=False, drill=None):
    s = load_state(); setups_cfg = load_setups()
    # NO early return on an empty selection: steps 1 and 2 below manage positions and pending orders that were
    # opened under a previous configuration, and a resting futures limit carries no stop until open_position()
    # sees it fill. Returning here would leave it naked. Spec §2.2.
    dry_override = (not live) and ignore_gate
    if halted() and not dry_override:
        for sym, pend in list(s["pending"].items()):
            if live:
                (mt5_json("cancel", str(pend["order_id"])) if pend["execution"] == "mt5" else sh(ORDER, "cancel-order", sym, str(pend["order_id"]), check=False))
            log("stop_cancel_pending", venue=pend["execution"], symbol=sym, order_id=pend.get("order_id")); del s["pending"][sym]
        save_state(s); log("halt", why=("estate-wide STOP file present" if os.path.exists(GLOBAL_STOP) else "this account's STOP file present"), open_positions=list(s["positions"])); return
    gate = automation_gate()
    if gate and not dry_override:
        log("halt", why=gate); return
    if dry_override and (gate or halted()):
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
    account_block = {}   # venue -> why NEW ENTRIES are refused by an account rule that did not halt the account
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
        # The account's own survival rules (§33): max total drawdown, daily loss, trailing drawdown, and the
        # declared failure conditions, all evaluated by the profile rather than by a constant in this file. A
        # rule whose input is missing reports UNKNOWN and is NOT treated as passed -- but UNKNOWN does not
        # write the kill switch either, because "I could not read the balance" is not "the account is down".
        # DEC-6: it MUST still block new entries, the same as a resolved BLOCK_ENTRY would -- see
        # `_account_survival_block` below, which is what actually enforces the "not treated as passed" half
        # of that sentence (halt_check() alone only ever returns HALT/HUMAN/BLOCK_ENTRY, never UNKNOWN).
        facts_v = {"equity": equity[v], "equity_start": s["venues"][v]["equity_start"],
                  "consec_losses": s["venues"][v]["consec_losses"]}
        act, why = AP.halt_check(profile(v), facts_v)
        if act == AP.HALT:
            halt(s, f"{v}: {why}"); save_state(s); return
        if act is not None:
            # Blocks ENTRIES, not the tick. Stopping here would also stop management -- breakeven moves, time
            # stops, reconciliation -- and leaving an open position unmanaged is not the conservative outcome
            # (§31: news-style restrictions apply to new entries; open positions are governed separately).
            account_block[v] = why; log("account-rule", venue=v, action=act, msg=why)
        else:
            block_why = _account_survival_block(profile(v), facts_v)
            if block_why:
                account_block[v] = block_why; log("account-rule", venue=v, action=AP.UNKNOWN, msg=block_why)
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
    # stays enough for WYCKOFF-BOOK's own setup detection. Widen the fetch for exactly the
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
            state, qty, px, pt = manage_pending(sym, pend, live, bars_elapsed[pend["tf"]], t=t)
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
    # Re-checked here, after this tick's closes have been booked, because a trade that just lost can be the
    # one that trips the account's failure condition. Same profile, same evaluator as the equity block above.
    for v in venues_used:
        facts_v = {"equity": equity.get(v), "equity_start": s["venues"][v]["equity_start"],
                  "consec_losses": s["venues"][v]["consec_losses"]}
        act, why = AP.halt_check(profile(v), facts_v)
        if act == AP.HALT:
            halt(s, f"{v}: {why}"); save_state(s); return
        if act is not None and v not in account_block:
            account_block[v] = why; log("account-rule", venue=v, action=act, msg=why)
        elif live and v not in account_block:
            # LIVE ONLY, same reasoning as the equity block above: `equity_start` (and any other basis fact)
            # is never captured for a dry run, so an UNKNOWN here is "we do not run a real account in dry
            # mode", not DEC-6's "the runner can never supply this fact" -- blocking a dry tick's decision
            # record on it would be a false positive on every dry run and every fixture that does not bother
            # seeding venues.equity_start, not a real DEC-6 case.
            block_why = _account_survival_block(profile(v), facts_v)
            if block_why:
                account_block[v] = block_why; log("account-rule", venue=v, action=AP.UNKNOWN, msg=block_why)
    if s["errors"] >= ERROR_HALT:
        halt(s, f"{ERROR_HALT} consecutive connector errors"); save_state(s); return
    # Event risk is evaluated PER INSTRUMENT, further down, not once per tick: CLAUDE.md §26 says an event
    # does not reach every instrument, and a single tick-wide answer would have to be either "block
    # everything an EIA release touches" or "block nothing", both of which are wrong for eight of the nine
    # symbols. It used to be computed here, once, and applied to all of them.
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
    # 2c. §36 step 3 -- EVENT RISK PRECHECK, once per tick, and deliberately NOT the same question as step 14.
    # The precheck asks whether the calendar can be consulted at all; step 14 asks whether THIS instrument is
    # inside a restricted window. §36 keeps them apart and calls this one "an early safety and data-availability
    # check". Until 2026-09-18 the live path had only step 14, so a calendar that could not be read was
    # discovered once per signal, deep inside the order loop, instead of once per tick before any work.
    # It blocks NEW ENTRIES for this tick and nothing else: steps 1 and 2 above must still manage what is open
    # (§31 -- news restrictions apply to new entries; open positions are governed separately).
    try:
        ER.load(at=t)
        event_precheck = None
    except ER.CalendarUnavailable as exc:
        event_precheck = f"{exc.reason} -> fail-safe: {exc.action}"
        log("event_precheck", action=exc.action, why=exc.reason,
            note="§32: a calendar that cannot be read is not 'no news' -- new entries blocked for this tick")
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
    trader = live_trader()
    for st in setups_cfg:
        # plan §0.9: a trader's tighten-only overlay for this setup's methodologies. Bool flags are merged
        # onto a COPY of the row before its detector runs; min_rr / sessions / daily cap apply at their steps.
        ov = trader_overlay(st, trader)
        if ov:
            st = dict(st, **{k: True for k in TC.BOOL_TRUE_ONLY if ov.get(k)})
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
                # §40 `analytics_update`: the derived analytics and the REQUIRED methodology read for this
                # (setup, symbol, side). This is the stage §40 is most concerned about -- it is the one the
                # Decision Engine must wait for, and the one a latency optimisation would be tempted to skip.
                try:
                    with _span("analytics_update"):
                        sigs = setups(st["method"], side, c_for_setups, st["tf"], sym=sym) if mreg.scan_of(st["method"]) == "ict" else setups_wyckoff(st["method"], side, c_for_setups, st["tf"], sym=sym)
                    # Plan §0.11: a drill tick evaluates ONE synthetic signal and nothing else. `sigs` from the
                    # real detectors are dropped on a drill tick so that a genuine signal cannot ride along
                    # with the rehearsal and place a second, un-asked-for order.
                    if drill is not None:
                        sigs = ([drill_signal(c_for_setups, side)]
                                if (st["id"], sym, side) == (drill["setup"], drill["symbol"], drill["side"]) else [])
                except Exception as e:
                    log("error", venue=venue, where=f"setups {st['id']} {sym} {side}", msg=str(e)[:200]); continue
                _sig_t0 = _t0()          # required analysis is ready here; the gap to the walk is §40's queueing latency
                for sig in sigs:
                    key = f"{st['id']}-{sym}-{side}-{sig['time']}"
                    if key in s["seen"]:
                        continue
                    s["seen"].append(key); s["seen"] = s["seen"][-800:]
                    sig["htf_pass"] = htf_pass(sym, side, candles.get((sym, HTF_OF.get(st["tf"]))), HTF_OF.get(st["tf"]))
                    open_same = [k for k, p in list(s["positions"].items()) + list(s["pending"].items()) if p["execution"] == venue]
                    reasons = []
                    # CLAUDE.md §35/§62: every reason below that comes from a DEPENDENCY is added through
                    # `blocked_on`, which refuses unless the active Trading System classifies that dependency
                    # REQUIRED_FOR_DECISION. Blocking an entry on an OPTIONAL_FOR_ANALYSIS /
                    # VISUALIZATION_ONLY / RESEARCH_ONLY input is a defect the moment it is written, and this
                    # makes it an exception instead of a trade that quietly never happens. `blocked_on` is a
                    # no-op on the pass path -- it only runs when something is about to block.
                    ts_style = TS.for_setup(st)["id"]
                    def blocked_on(dep, why, _st=st, _style=ts_style, _sym=sym):
                        TS.assert_may_gate(_style, dep, setup=_st, instrument=_sym)
                        return why
                    # CLAUDE.md §36: the checks below now run in the CANONICAL ORDER and record themselves in
                    # a Trace, which raises if a step is taken out of order, if a step that may not block
                    # blocks, or if an order is generated after something blocked. Several of these values
                    # were COMPUTED earlier in the tick (the candles' quality, the account's survival state,
                    # the venue reconciliation, the event-risk precheck) -- computing early and consulting at
                    # the canonical position is not reordering; reordering would be letting an early result
                    # skip a later gate, which is what the Trace exists to catch.
                    # §40 `decision_start` / `decision_end`: the queueing gap before the walk, and the walk
                    # itself. Recorded at BOTH exits below -- the blocked signal that `continue`s and the
                    # eligible one that reaches execution -- because a timer stopped only on the path that
                    # places an order measures the fast cases and drops the refusals.
                    _rec("decision_start", _sig_t0)
                    _dec_t0 = _t0()
                    tr = DO.Trace(ts_style, setup=st, instrument=sym)
                    tr.ok("market_instrument", "on the instruments.json execution list for this market")
                    tr.ok("data_quality", "fetch_candles() admitted the series through _require_quality()")
                    if event_precheck:                                     # 3 -- per tick, §32 fail-safe
                        reasons.append(blocked_on("event_risk.calendar", f"lịch sự kiện: {event_precheck}"))
                        tr.block("event_precheck", event_precheck, dep="event_risk.calendar")
                    else:
                        tr.ok("event_precheck")
                    # 4. Session validation (A4, 2026-09-18): the profile's OWN session_restrictions finding,
                    # read from account_profile.entry_gate. Before this fix the step was unconditionally
                    # tr.skip()'d regardless of whether an account actually declared a session rule, so a
                    # profile with session_restrictions gated nowhere on the live path even though
                    # account_profile.py already computed the finding every tick. entry_gate is called ONCE
                    # here; its non-session findings feed step 5 below so the same rule is never reported
                    # twice under two different steps.
                    gate_findings = AP.entry_gate(
                        profile(venue), {"open_positions": len(open_same),
                                         "trades_today": s["trades_today"].get(sym, 0), "at": t})
                    session_finding = next((f for f in gate_findings if f["rule"] == "session_restrictions"), None)
                    # plan §0.9: the trader's own session set narrows whatever the account allows.
                    if ov.get("_sessions") is not None and SESS.primary(t) not in ov["_sessions"]:
                        session_finding = {"rule": "session_restrictions", "state": AP.BLOCK_ENTRY,
                                           "why": f"trader {trader}: chỉ vào lệnh trong phiên {sorted(ov['_sessions'])}, hiện tại {SESS.primary(t)}"}
                    if session_finding and session_finding["state"] in AP.BLOCKING:
                        reasons.append(blocked_on("account.profile_rules", session_finding["why"]))
                        tr.block("session", session_finding["why"], dep="account.profile_rules")
                    else:
                        tr.ok("session", session_finding["why"] if session_finding else
                             "account declares no session_restrictions")
                    # 5. §33 account constraints, evaluated by the profile: position cap, per-symbol daily
                    # entry cap, and (for an account that declares them) overnight / weekend / news rules.
                    # session_restrictions is excluded here -- it is step 4's own finding, above. A declared
                    # rule whose input is missing reports UNKNOWN and refuses the entry -- it is never
                    # silently passed.
                    acct = [f["why"] for f in gate_findings
                           if f["rule"] != "session_restrictions" and f["state"] in AP.BLOCKING]
                    if account_block.get(venue):
                        acct.append(f"luật tài khoản: {account_block[venue]}")
                    if ov.get("_max_trades_per_day") is not None and s["trades_today"].get(sym, 0) >= ov["_max_trades_per_day"]:
                        acct.append(f"trader {trader}: đủ {ov['_max_trades_per_day']} lệnh/ngày cho {sym}")
                    reasons += [blocked_on("account.profile_rules", w) for w in acct]
                    (tr.block("account_constraints", "; ".join(acct), dep="account.profile_rules")
                     if acct else tr.ok("account_constraints"))
                    tr.ok("methodology_applicability", f"{st['method']} permitted by the current preset")
                    tr.ok("required_evidence", "the mechanical analytics ran inside setups()")
                    tr.skip("required_methodology", "the runner trades rule families, not the discretionary "
                                                    "dimensions -- decision-order.json step 8")
                    tr.ok("setup_detection", f"{st['method']} produced a {side} signal at {sig['time']}")
                    # FAIL CLOSED (2026-09-13, Task 8 fix round 1): a setup that declares htf:true is asking for a
                    # higher-timeframe gate; if that gate cannot be evaluated, the answer is NOT permission. Before
                    # this fix, htf_pass() could only return True/False (a percentile it could always compute from
                    # bt.P), so `is False` was equivalent to `is not True` -- checking only for False cost nothing.
                    # Now htf_pass() reads the live rules, which can genuinely be unable to judge (None) for
                    # reasons that have nothing to do with the actual bias -- no candles fetched, htf_tf not in
                    # bt.P, or automation.SCAN_WINDOW has no entry for htf_tf (the 2H/30m gap) -- and `is False`
                    # would let every one of those sail through as if the gate had opened. Block on anything other
                    # than an explicit True: only a live bias read that actually ran and agreed with `side` permits.
                    # 10. The higher-timeframe gate, fail-CLOSED.
                    htf_why = None
                    if st.get("htf") and sig["htf_pass"] is not True:
                        htf_why = ("khung lớn không cho hướng này" if sig["htf_pass"] is False else
                                   "khung lớn: không đọc được bias (thiếu dữ liệu/không quét được khung này)")
                        reasons.append(blocked_on("analytics.htf_bias", htf_why))
                    (tr.block("entry_condition", htf_why, dep="analytics.htf_bias") if htf_why
                     else tr.ok("entry_condition"))
                    # 11. §17 expectation. The rule families always emit a target, so the input is present --
                    # and `display.expected_path` is VISUALIZATION_ONLY, so this step could not block on it
                    # even if it wanted to (§35 assert_may_gate would raise). One record PER DIMENSION the
                    # setup's rule family requires (COMBINED-BOOK -> wyckoff + ict, §17 "never merged"), built ONCE
                    # here with a fixed created_at so the ids named in this trace are the SAME ids place_limit/
                    # place_market later persist onto the plan (§0.6) -- a second from_signal() call with a
                    # fresh timestamp would mint different ids for the identical thesis.
                    exp_created_at = iso(now())
                    exp_records = EP.from_signal(sig, st, sym, created_at=exp_created_at)
                    tr.ok("expectation", f"target {sig['target']} · expectation "
                                        + ", ".join(r["id"] for r in exp_records))
                    # 12-13. Risk CALCULATION then risk VALIDATION, both before final eligibility (§36).
                    risk_mult = 0.5 if s["venues"][venue]["consec_losses"] >= 2 else 1.0
                    with _span("risk_validation"):       # §40: §36 steps 12-13, the sizing that can refuse
                        size_why = risk_precheck(sym, st, sig, sizing_equity.get(venue, 10000.0), risk_mult)
                    if size_why:
                        reasons.append(blocked_on("risk.position_size", size_why))
                    (tr.block("risk_calculation", size_why, dep="risk.position_size") if size_why
                     else tr.ok("risk_calculation"))
                    rr_why = rr_reason(sig, venue, floor=ov.get("min_rr"))
                    if rr_why:
                        reasons.append(blocked_on("risk.net_rr", rr_why))
                    (tr.block("risk_validation", rr_why, dep="risk.net_rr") if rr_why
                     else tr.ok("risk_validation"))
                    # 14. FINAL event/news validation -- per instrument, unlike step 3's per-tick precheck.
                    blackout = event_blackout(t, sym)
                    if blackout:
                        reasons.append(blocked_on("event_risk.calendar", f"blackout sự kiện {blackout}"))
                    (tr.block("event_final", blackout, dep="event_risk.calendar") if blackout
                     else tr.ok("event_final"))
                    tr.skip("contradiction_confluence", "the runner engages no discretionary dimension -- "
                                                        "decision-order.json step 15")
                    # 16. Final eligibility: this runner's book against the venue's, and the verdict.
                    elig = []
                    if sym in s["positions"] or sym in s["pending"]:
                        elig.append("đã có vị thế/lệnh chờ")     # the runner's own book, not an analysis input
                    if sym in foreign:
                        elig.append(blocked_on("venue.reconciliation",
                                               "sàn đang có vị thế/lệnh không thuộc runner này"))
                    reasons += elig
                    # Only ELIG's own findings block here. A reason raised at an earlier step is already
                    # recorded there and is the decision; recording it again at 16 with an empty `why` would
                    # be a second, emptier version of the same refusal.
                    (tr.block("eligibility", "; ".join(elig),
                              dep="venue.reconciliation" if sym in foreign else None)
                     if elig else tr.ok("eligibility"))
                    # The signal record is written AFTER the walk finishes, so `decision_trace` shows the
                    # whole walk including step 17 -- logging at 16 would have made every trace stop one step
                    # short of the only step that places an order.
                    def _log_signal():
                        log("signal", venue=venue, symbol=sym, strategy=st["id"], side=side, sweep_time=sig["time"], mss_time=sig["mss_time"], entry=sig["entry"], stop=sig["stop"],
                            target=sig["target"], r_planned=round(sig["r_planned"], 2), vol_type=sig["vol_type"], htf_pass=sig["htf_pass"], ok=not reasons, reasons=reasons,
                            drill=bool(sig.get("drill")), decision_trace=tr.as_log())
                    if reasons:
                        _rec("decision_end", _dec_t0)
                        _log_signal()
                        continue
                    # 17. Execution instruction. `verify()` is the last word: it raises if an order is about
                    # to be generated after any step blocked, which is §62 with an exception attached.
                    tr.ok("execution_instruction")
                    tr.verify()
                    _rec("decision_end", _dec_t0)
                    _log_signal()
                    try:
                        if sig.get("entry_now"):
                            # PAR-1: the entry bar is the last bar of the exact window setups_wyckoff() fired
                            # on (wyckoff_fires() only ever fires on candles[-1] of what it is given).
                            pos = place_market(sym, st, sig, sizing_equity.get(venue, 10000.0), risk_mult, live, expectations=exp_records,
                                              entry_bar_time=c_for_setups[-1]["time"])
                            if pos:
                                s["positions"][sym] = pos; s["trades_today"][sym] = s["trades_today"].get(sym, 0) + 1
                            pend = None
                        else:
                            pend = place_limit(sym, st, sig, sizing_equity.get(venue, 10000.0), risk_mult, live, expectations=exp_records)
                    except UnprotectedPositionError as e:
                        halt(s, str(e)); save_state(s); return
                    except Exception as e:
                        s["errors"] += 1; log("error", venue=venue, where=f"place {sym}", msg=str(e)[:200]); pend = None
                    if pend:
                        s["pending"][sym] = pend
    s["last_tick"] = iso(t)
    save_state(s)


# ---------------------------------------------------------------- replay (parity with the backtest, no orders)
def replay(setup_ids, bars=900):
    """Parity between THIS runner and bt.scan(), setup by setup.

    The trailing window must be the one the method actually reads, per timeframe. It used to be the module
    constant WINDOW (300) for every method and every tf -- but the live ICT scanner reads
    automation.SCAN_WINDOW bars (576 on 15m, 480 on 1H, 360 on 4H) and live_rules.read_at returns None on
    anything short of the full window, by design ("Live never scans on a partial window, so neither does
    this"). So every ICT replay handed the scanner 300 bars, got nothing back, and reported zero runner
    placements -- and the comparison passed for as long as the backtest also found nothing in the span.
    ICT parity was therefore never actually checked; the first backtest trade to appear in a replay span
    surfaced it as a mismatch (2026-09-19, after the ICT scanner gained the deck's Old Highs & Lows pools).

    `bars` must exceed that window or there is no k to iterate at all, which is why the default moved from
    600 to 900: 600 leaves only 24 steps on 15m and zero margin if SCAN_WINDOW grows.
    """
    report = []
    for st in load_setups():
        if setup_ids != ["all"] and st["id"] not in setup_ids:
            continue
        # min_rr NOT pinned (2026-09-13): it inherits bt.OPTS' default (= bt.MIN_RR = the same 3R floor that
        # rr_reason() applies to live signals). replay() exists to check parity between this runner and the
        # backtest; pinning 0.0 here would have it compare the live path -- which now refuses sub-3R setups --
        # against a backtest that still takes them, and report the difference as a parity failure.
        bt.OPTS.update(mgmt=st.get("mgmt", "be"), htf=False, sides=("long", "short"), types=(1, 2, 3), range_touches=0, entry="book", combined_entry="limit")
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
            # WYCKOFF-BOOK detects over whatever window it is given; ICT refuses anything short of the live
            # window. Ask live_rules for the number rather than restating it (see the docstring above).
            w_bars = WINDOW if wy else bt.lr.scan_spec(st["tf"])[0]
            if len(span) < w_bars:
                report.append(dict(setup=st["id"], symbol=sym, tf=st["tf"], method=st["method"],
                                   backtest_trades=0, matched=0, unmatched=0, runner_placements=0,
                                   skipped=f"span of {len(span)} bars is shorter than the {w_bars}-bar window "
                                           f"{st['method']} reads on {st['tf']}; raise replay(bars=...)",
                                   mismatches=[]))
                continue
            for k in range(w_bars, len(span) + 1):
                window = span[k - w_bars:k]
                for side in ("long", "short"):
                    sigs = setups_wyckoff(st["method"], side, window, st["tf"], sym=sym) if wy else setups(st["method"], side, window, st["tf"], sym=sym)
                    for sig in sigs:
                        placements.setdefault((side, sig["time"]), dict(sig, first_seen=window[-1]["time"]))
            sc = bt.scan(sym, st["tf"], only=(st["method"],)); span_start = span[w_bars - 1]["time"]  # only the method being checked -- skip the rest of scan()'s work, esp. the live ICT scanner when unused (2026-09-13)
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
    lines = [f"PILOT RUNNER [env {ENV_NAME}] {iso(now())} started {s['started']} halted: {s.get('halted')}"]
    for v in VENUES:
        vs = s["venues"][v]
        lines.append(f"{v}: equity start {vs['equity_start']} | closed {len(vs['closed'])} | realised {sum(c['pnl'] for c in vs['closed']):+.2f} | consec losses {vs['consec_losses']}")
        # Which ACCOUNT's rules this venue is trading under (§33), and how the account stands against them
        # right now. Printed rather than implied: a limit you cannot see is a limit you cannot check.
        try:
            prof = profile(v)
        except ValueError as e:
            lines.append(f"  account: {e}"); continue
        lines.append(f"  account: {AP.describe(prof)}")
        for f in AP.account_state(prof, {"equity": vs["equity_start"], "equity_start": vs["equity_start"],
                                         "consec_losses": vs["consec_losses"]}):
            lines.append(f"    ! {f['rule']}: {f['state']} -- {f['why']}")
    # §35: which Trading System governs each selected setup, and what it declares may gate that setup's entry.
    # Printed for the same reason the account rules above are: a gating set you cannot see is one you cannot
    # check, and this is the list §62 says nothing may be quietly added to or dropped from.
    for st in load_setups():
        try:
            style = TS.for_setup(st)["id"]
        except KeyError as e:
            lines.append(f"  {st['id']}: no Trading System -- {e}"); continue
        req = TS.required(style, setup=st)
        lines.append(f"  {st['id']}: system {style} {TS.get(style)['version']} "
                     f"({TS.get(style)['dependency_profile']}) gates on {len(req)}: {', '.join(req)}")
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
    ap.add_argument("--account", default=None, metavar="ID",
                    help="run for ONE customer account (docs/architecture/account-profiles.json id): its own "
                         "state, logs, candle cache and kill switch under data/live/accounts/<id>/. Omitted, "
                         "the house's single-account paths are used, exactly as before.")
    ap.add_argument("--live", action="store_true"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--replay", nargs="+", default=None, help="setup ids or 'all'"); ap.add_argument("--bars", type=int, default=900)
    ap.add_argument("--report", action="store_true"); ap.add_argument("--flatten", action="store_true"); ap.add_argument("--list", action="store_true"); ap.add_argument("--tick-time", default=None)
    ap.add_argument("--ignore-gate", action="store_true", help="DRY RUN ONLY: evaluate signals even while /automation refuses the tick (never sends orders)")
    ap.add_argument("--tick-seconds", action="store_true", help="print the loop period implied by the fastest selected timeframe (used by pilot-loop.sh)")
    ap.add_argument("--drill", default=None, metavar="SETUP:SYMBOL:SIDE",
                    help="DEMO ONLY, needs --live: replace setup detection for ONE (setup, symbol, side) with a synthetic 3R market "
                         "signal at the last closed bar and run the whole decision walk + venue submit for real (plan §0.11)")
    a = ap.parse_args()
    # Bind BEFORE anything reads a path: load_state, log and the kill-switch check all resolve through the
    # module globals bind_account() rewrites (plan §0.3 item 2).
    bind_account(a.account)
    if a.tick_seconds:
        tfs = [st["tf"] for st in load_setups()] or ["30m"]
        print(min(TF_SEC[tf] for tf in tfs)); return
    if a.list:
        for st in load_setups():
            flags = " disp=bắt buộc pd=bắt buộc" if mreg.scan_of(st["method"]) == "ict" else ""
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
                px_c, profit = mt5_close(p["position_ticket"] or p["entry_order"]); rec = close_record(sym, p, px_c, "FLATTEN", p["qty"], pnl=profit)
            else:
                sh(ORDER, "cancel-all", sym, check=False); o = order_json("close-position", sym)
                px = float(o.get("avgPrice") or 0) or float(order_json("price", sym)["price"]); rec = close_record(sym, p, px, "FLATTEN", o.get("executedQty") or p["qty"])
            s["venues"][p["execution"]]["closed"].append(rec); log("exit", venue=p["execution"], **rec); del s["positions"][sym]
        save_state(s); report_state(s); return
    live = a.live and not a.dry_run
    tt = parse_t(a.tick_time) if a.tick_time else None
    drill = None
    if a.drill:
        drill = parse_drill(a.drill)
        try:
            cfg_env = json.load(open(AUTOMATION_CONFIG, encoding="utf-8")).get("execution", {}).get("environment", "demo")
        except Exception:
            cfg_env = None
        known = {st["id"]: st for st in load_setups()}
        enabled = set(enabled_symbols(known[drill["setup"]]["market"])) if drill["setup"] in known else set()
        why = drill_refusal(drill, live=live, env_name=ENV_NAME, config_env=cfg_env, gate_reason=automation_gate(),
                            setups_known=set(known), symbols_enabled=enabled)
        if why:
            log("drill_refused", why=why, drill=drill)
            raise SystemExit(f"drill refused: {why}")
        log("drill_start", drill=drill, env=ENV_NAME)
    tick(live, tt, ignore_gate=a.ignore_gate and not live, drill=drill)


if __name__ == "__main__":
    main()
