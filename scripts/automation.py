#!/usr/bin/env python3
"""Automation switch v3 -- the single writer of docs/architecture/automation-config.json
(schema: docs/architecture/schemas/automation-config.schema.json; layers: docs/architecture/data-sources.md
"Chart refresh: three-layer read" and SYSTEM-DESIGN.md §9.x).

WHAT `on` / `off` MEAN (user decision 2026-09-10):
  on   -> everything comes back, exactly like after a reboot + `/automation on`: master switch on, the scanner
          launchd agent installed + bootstrapped, one pilot launchd agent per market in PILOT_MARKETS installed +
          bootstrapped (KeepAlive, PILOT_END=never), a `caffeinate` keep-awake started, MT5 bridge freshness checked
          (CFD data needs MT5 open first -- warned, not blocked).
  off  -> everything stops, like the state right after a shutdown: master switch off, kill switches written,
          pilot + scanner launchd agents booted out AND their plists removed from ~/Library/LaunchAgents (so a
          reboot does NOT resurrect them), keep-awake killed.
  demo / real -> set execution.environment to that name, apply the preset (both markets, every instrument that has
          data on disk, EVERY timeframe ON: scalping 15m, day 1h, swing 4h); dimensions and the chosen
          method preset are left exactly as they are (spec docs/specs/2026-09-12-method-switch-design.md §4.1 --
          before this, demo/real turned every dimension back on and silently erased the user's preset), then `on`.
          `real` refuses (exit 2) only while config/env.real still has placeholder secrets.

ENVIRONMENT: execution.environment ("demo" | "real") selects config/env.<name> (template config/env.example),
loaded by scripts/trading-env.sh (bash) / scripts/trading_env.py (python). It is set by `demo` / `real` or by
hand in the config file; the order connectors and the pilot read it on every call. Nothing here refuses an
environment on policy grounds. Hard rules that stay in every environment: the instrument allowlist,
PILOT_RISK_PCT <= 1% (clamped by the loaders).

v3 shape (schema_version 3): per-MARKET config (crypto | cfd | forex) with instruments, Confluence dimensions (§6.2) and
timeframes; (market, timeframe) maps to the chart-style vocabulary (STYLE below), which is DERIVED from the three
authored horizons (HORIZONS / HORIZON_TF: scalping 15m, day 1h, swing 4h) -- crypto keeps the bare horizon word,
cfd takes `cfd-`, forex takes `fx-`. `services` records what `on` installed so `off` can remove exactly that.

Subcommands
  status [--json]                     full effective configuration + warnings (safe any time, works with no file)
  env                                 active environment name + whether its file is complete (never prints a secret)
  demo | real                         set environment + preset + bring everything up
  on  [--who W] [--reason R]          bring everything up in the CURRENT environment
  off [--who W] [--reason R]          stop everything (persists across reboot)
  market <crypto|cfd|forex> <on|off>
  timeframe <15m|1h|4h> <on|off> [--market crypto|cfd|forex]   one scanned set, all markets (scalping|day|swing)
  dimension <wyckoff|ict|footprint|heatmap> <on|off> [--market crypto|cfd|forex]   footprint/heatmap: crypto only
  method <preset> [--market crypto|cfd|forex]   apply a named preset from docs/architecture/methods.json as a set of the
                                      dimension flags; the preset is only a NAME for that set, nothing extra is
                                      stored. Presets: wyckoff | ict | wyckoff+ict | wyckoff+footprint |
                                      wyckoff+ict+footprint | full. Refuses (2) a preset whose dimensions the
                                      target market has no source for; with no --market it applies only to the
                                      markets that can hold it and prints which it skipped.
  instrument <SYMBOL> <on|off>        allowlist only; market inferred from the symbol
  instrument set <SYM,SYM,...> --market <crypto|cfd>   declarative batch: REPLACE that market's whole list in ONE
                                      write and ONE history row. All-or-nothing -- any off-allowlist
                                      symbol or any duplicate refuses (2) and leaves the config untouched. An empty
                                      list is legal and means "no NEW entries in this market"; open positions and
                                      resting orders are still managed.
  layer <scanner|local_read|pilot> <on|off>
  pilot <start|stop|status|adopt> [--market futures] [--no-launchd]   one venue since 2026-09-13
  on|demo [setup top <N> | setup horizons]   default (no spec) = `setup horizons`: one setup per horizon (scalping/day/swing) per market,
                                      ranked on the last 12 months; `setup top N` = N crypto + N CFD. Both write
                                      docs/architecture/pilot-top20.json, which the loop reads every tick; there is
                                      no profile switch (the legacy engine was deleted 2026-09-13).
  allows <scanner|local_read|pilot> [style]     exit 0 if permitted, 2 if not (for shell gates)
  allows master                       exit 0 only if the config exists AND `enabled` is true. Fails CLOSED on a
                                      missing or corrupt file, unlike the three layer forms above, which treat
                                      "unconfigured" as permitted -- this is the one gate an unattended cron
                                      trusts to permit a write, so "no policy" must not read as "allowed".
  history [-n N]

Exit codes: 0 applied/no-op, 1 usage error, 2 REFUSED (off-allowlist symbol, impossible market/timeframe/
dimension pair, incomplete environment file, or a pilot start blocked by a running duplicate / STOP file).

Test-only environment overrides (never set these in normal use):
  AUTOMATION_PILOT_DRYRUN=1            `pilot start` spawns `sleep 30` instead of scripts/pilot-loop.sh and marks
                                       pilot_process.dry_run; `pilot stop` / `off` PRINT the STOP path they would
                                       write and do NOT create it (a real STOP file kills a human's running loop).
  AUTOMATION_PILOT_PGREP_PATTERN=...   pattern used to detect already-running pilot loops.
"""
import argparse, datetime, json, os, re, shutil, subprocess, sys
import importlib.util

try:                                    # POSIX
    import fcntl

    def _lock(f):
        fcntl.flock(f, fcntl.LOCK_EX)

    def _unlock(f):
        fcntl.flock(f, fcntl.LOCK_UN)
except ImportError:                     # Windows has no fcntl (docs/plans/2026-09-20-windows-migration.md)
    import msvcrt

    def _lock(f):
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)    # blocking; raises after ~10 s of contention

    def _unlock(f):
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "docs", "architecture", "automation-config.json")
SCHEMA_VERSION = 3
ENV_NAMES = ["demo", "real"]
LAUNCH_AGENTS = os.path.expanduser("~/Library/LaunchAgents")
SCANNER_LABEL = "com.tyme.trading.scanner"
# One venue since 2026-09-13 (PILOT_MARKETS below); the spot label belonged to the deleted legacy engine.
PILOT_LABEL = {"futures": "com.tyme.trading.pilot.futures"}
PLIST_SRC = {"scanner": os.path.join(ROOT, "integrations", "launchd", "com.tyme.trading.scanner.plist"),
             "pilot": os.path.join(ROOT, "integrations", "launchd", "com.tyme.trading.pilot.futures.plist")}

# Windows: Task Scheduler / SetThreadExecutionState / CIM stand in for launchd / caffeinate / pgrep. The
# decisions below stay here; scripts/win_services.py only answers the OS questions (migration plan step 11).
WIN = os.name == "nt"
if WIN:
    _wspec = importlib.util.spec_from_file_location("win_services", os.path.join(ROOT, "scripts", "win_services.py"))
    win_services = importlib.util.module_from_spec(_wspec); _wspec.loader.exec_module(win_services)

_tspec = importlib.util.spec_from_file_location("trading_env", os.path.join(ROOT, "scripts", "trading_env.py"))
trading_env = importlib.util.module_from_spec(_tspec); _tspec.loader.exec_module(trading_env)

# Instrument allowlist: THE single source is docs/architecture/instruments.json, read through scripts/instruments.py.
# Never hard-code a symbol list here again -- scripts/tests/test_instruments_sync.py fails the build on drift.
# ANALYSIS != EXECUTION: this list is what the scanner and /analyze may touch; the pilot and the order connectors
# use instruments.execution(), a subset, so a watch-only symbol can never reach a venue.
_ispec = importlib.util.spec_from_file_location("instruments", os.path.join(ROOT, "scripts", "instruments.py"))
instruments = importlib.util.module_from_spec(_ispec); _ispec.loader.exec_module(instruments)
# The market vocabulary itself is the registry's too. This module kept its own ["crypto", "cfd"] literal
# directly above the import that could have told it -- so adding a market meant editing both, and disagreeing
# between them would have produced a market with instruments and no config node (or the reverse).
MARKETS = list(instruments.MARKETS)
MARKET_INSTRUMENTS = {m: instruments.analysis(m) for m in MARKETS}
_mspec = importlib.util.spec_from_file_location("methods", os.path.join(ROOT, "scripts", "methods.py"))
methods = importlib.util.module_from_spec(_mspec); _mspec.loader.exec_module(methods)  # import methods as a sibling script, not a package
# Which dimensions each market can have AT ALL -- the shape, from docs/architecture/methods.json.
# Footprint/Heatmap have NO commodities source (CoinGlass is crypto-derivatives only) -- SYSTEM-DESIGN.md §12 item 3,
# which is now expressed by those dimensions not listing "cfd" in their markets[].
MARKET_DIMENSIONS = {m: methods.dimensions(m) for m in MARKETS}
# One scanned set for both markets (user decision 2026-09-13). 1m and 5m were the two scalping entry windows and
# 1D was the swing entry; all three leave the scanned set when the horizons become 15m/1h/4h. 1D and 1W stay in
# PAGE_RUNGS below as context-only rungs, which is what keeps swing a full ladder. The MT5 EA
# (integrations/mt5/ExportOHLCV.mq5) exports 1W/1D/4H/1H/15m/5m, so every scanned cfd rung has a source.
# One authored list, mapped over every market -- it was written out once per market, so the "one scanned set"
# the comment above promises was actually N copies that could drift. The per-market SHAPE is deliberate and
# stays (see cmd_timeframe: the day a market has a different rung, this table is where it is expressed).
_SCANNED_TF = ["15m", "1h", "4h"]
MARKET_TIMEFRAMES = {m: list(_SCANNED_TF) for m in MARKETS}
DIMENSIONS = list(methods.ALL_DIMENSIONS)                                    # SYSTEM-DESIGN.md §6.2
TIMEFRAMES = ["15m", "1h", "4h"]
LAYERS = ["scanner", "local_read", "pilot"]
# Every allowlisted symbol, summed over MARKETS -- it named the two markets by hand, which silently excluded
# any third one from the refusal message that is supposed to list what IS allowed.
ALLOWED_INSTRUMENTS = instruments.analysis()
# (COMMODITIES = set(MARKET_INSTRUMENTS["cfd"]) lived here and was read by nothing -- deleted 2026-09-17.)
# FX_CODES and the two currency-pair refusals it fed were deleted 2026-09-17 (user decision: the Forex
# prohibition is lifted). They were never the gate -- docs/security/2026-09-12-method-panel.md:489-491 recorded
# that the pair test was redundant with the allowlist check, existing "to give the *right message*" while the
# allowlist gave "the *right answer*". With the prohibition gone the message was the only thing it did, and it
# was wrong. A currency pair is now refused, or not, on exactly the same ground as every other symbol: whether
# docs/architecture/instruments.json lists it.
HISTORY_MAX = 200
HISTORY_ARCHIVE = os.path.join(ROOT, "data", "live", "history-archive.automation.jsonl")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")

# ONE authored style vocabulary (user decision 2026-09-13): three horizons, one timeframe each, shared by both
# markets. The flat (market, timeframe) -> name table below is DERIVED from it, not authored a second time -- it
# exists because scan-loop.sh, model-read.sh, build-artifact.py, artifacts.json and local-eval-brief.py key off a
# single flat name and carry no market field. Crypto keeps the bare horizon word; cfd takes a `cfd-` prefix.
# This replaces ten hand-written labels -- five per market, the cfd half named after the INSTRUMENT rather than the
# market -- which disagreed with rank-setups.HORIZONS about what `scalping` and `swing` meant (1m vs 15m, 1D vs 4H).
# The retired names are spelled out once, in scripts/tests/test_one_system.py OneStyleVocabulary, so that no live
# source keeps a token a grep is meant to prove gone.
HORIZONS = ["scalping", "day", "swing"]
HORIZON_TF = {"scalping": "15m", "day": "1h", "swing": "4h"}
TF_HORIZON = {tf: hz for hz, tf in HORIZON_TF.items()}
# Crypto keeps the bare horizon word; every other market takes a prefix. forex -> fx-scalping/fx-day/fx-swing.
STYLE_PREFIX = {"crypto": "", "cfd": "cfd-", "forex": "fx-"}
if set(STYLE_PREFIX) != set(MARKETS):
    raise KeyError(f"STYLE_PREFIX covers {sorted(STYLE_PREFIX)} but MARKETS is {sorted(MARKETS)} -- a market\n"
                   f"with no style prefix would silently collide with crypto's bare horizon names.")
STYLE = {(m, HORIZON_TF[h]): STYLE_PREFIX[m] + h for m in MARKETS for h in HORIZONS}
STYLE_MARKET_TF = {v: k for k, v in STYLE.items()}
# How many bars the live scanner reads per timeframe, and how many count as "recent" for event detection.
# THE one table: scripts/scan-loop.sh reads it (it used to hardcode the numbers). scripts/live_rules.py (Task 2,
# not yet created) will reproduce the live window from it, so a backtest sees exactly the window the scanner saw.
SCAN_WINDOW = {
    "1m":  {"bars": 360, "recent": 4},
    "5m":  {"bars": 576, "recent": 4},
    "15m": {"bars": 576, "recent": 2},
    "1H":  {"bars": 480, "recent": 2},
    "4H":  {"bars": 360, "recent": 2},
    "1D":  {"bars": 240, "recent": 1},
}
# ---- Timeframe ladder: ONE rule, ONE table (docs/architecture/timeframe-mapping.md §3, §5). ----------------------------
# Three tiers per style: Vào lệnh (E, the style's own window) -> Cấu trúc (S) -> Bias (B). Adjacent tiers are the next
# available rung at least MIN_TIER_RATIO× slower ("rule of four", DailyFX/IG; Elder's factor of five; the TTrades pairing
# table W→H4, D→H1, H4→M15, M15→M1 is this ladder with the middle rung skipped). The pilot and the backtest derive their
# structure filter from the same function over the rungs THEY have (next_rung), so no second table exists.
TF_MINUTES = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "1H": 60, "2h": 120, "2H": 120, "4h": 240, "4H": 240,
              "1D": 1440, "1W": 10080}
MIN_TIER_RATIO = 4


def next_rung(tf, available):
    """The slowest-nearest timeframe in `available` that is >= MIN_TIER_RATIO x `tf`; None when there is none."""
    m = TF_MINUTES[tf]
    cands = sorted((TF_MINUTES[t], t) for t in available if TF_MINUTES[t] >= MIN_TIER_RATIO * m)
    return cands[0][1] if cands else None


def ladder(tf, available):
    """(structure_tf, bias_tf) for an entry timeframe over the rungs available in this context."""
    s = next_rung(tf, available)
    return s, (next_rung(s, available) if s else None)


# Rungs the pages can draw: every scanned timeframe per market plus 1D and 1W, which are fetched as CONTEXT for the
# slower horizons and never scanned. Dropping 1m/5m here cannot change any ladder -- next_rung only ever looks
# upward from the entry timeframe -- and keeping 1D/1W is what leaves `swing` (4h) a full structure+bias ladder.
PAGE_RUNGS = {m: _SCANNED_TF + ["1D", "1W"] for m in MARKETS}
# style -> {"structure": tier, "bias": tier}; tier = {"tf": ..., "style": style-or-None} (None style = chart only, no read).
TIERS = {}
for (_mkt, _tf), _style in STYLE.items():
    _s, _b = ladder(_tf, PAGE_RUNGS[_mkt])
    TIERS[_style] = {k: ({"tf": t, "style": STYLE.get((_mkt, t))} if t else None) for k, t in (("structure", _s), ("bias", _b))}


def gate_style(style):
    """The tier whose read GATES the working-window verdict (giảm khung, WA p93–96): the bias tier when a scanned style
    exists for it, else the structure tier. Returns (style, tier_name) or (None, None)."""
    for name in ("bias", "structure"):
        t = TIERS[style].get(name)
        if t and t["style"]:
            return t["style"], name
    return None, None


# Backwards-compatible alias: style -> gate style (read by htf_context.py, check-narrative.py, the pilot).
CONTEXT_STYLE = {st: gate_style(st)[0] for st in TIERS}
# Where each market's OHLCV lands; the 15m file is the "is this instrument actually wired up?" probe.
# Authored once in instruments.py (it was copied here and in method-panel.py, and as a symbol set in five
# more files) -- the directory is a property of the market's FEED, so it belongs beside the allowlist.
DATA_DIR = instruments.DATA_DIR

# One engine, one venue (user decision 2026-09-13). The second entry ran the deleted legacy engine.
PILOT_MARKETS = ["futures"]
# Anchored: match the bash process that IS the loop ("bash scripts/pilot-loop.sh" from a terminal, or
# "/bin/bash /abs/path/scripts/pilot-loop.sh" from launchd) -- not any shell whose command text merely
# mentions the file (a verification one-liner containing this string once produced a phantom PID).
PGREP_PATTERN = os.environ.get("AUTOMATION_PILOT_PGREP_PATTERN", r"^(/bin/)?bash (/[^ ]*/)?scripts/pilot-loop\.sh( |$)|^python3 (/[^ ]*/)?scripts/strategy-runner\.py .*--live")


def dryrun():
    return os.environ.get("AUTOMATION_PILOT_DRYRUN") == "1"


def pilot_dir(market):
    """State/log/STOP directory for a pilot market. One venue since 2026-09-13, so one directory.

    The `"pilot" if market == "spot"` branch is gone: `data/live/pilot` belonged to the deleted spot engine and
    is not in PILOT_STOP, so anything that resolved to it got a kill switch `/automation off` could not write.
    Unknown markets now raise instead of silently landing there."""
    if market not in PILOT_MARKETS:
        raise KeyError(f"unknown pilot market {market!r}; known: {', '.join(PILOT_MARKETS)}")
    return os.path.join(ROOT, "data", "live", "pilot-futures")


def stop_path(market):
    return os.path.join(pilot_dir(market), "STOP")


def log_path(market):
    return os.path.join(pilot_dir(market), "loop.log")


PILOT_STOP = [stop_path(m) for m in PILOT_MARKETS]


def rel(p):
    return os.path.relpath(p, ROOT)


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def actor(a):
    return getattr(a, "who", None) or os.environ.get("AUTOMATION_ACTOR") or os.environ.get("USER") or "unknown"


def market_of(sym):
    for m in MARKETS:
        if sym in MARKET_INSTRUMENTS[m]:
            return m
    return None


def market_of_style(style):
    """Which market's dimension flags a chart style obeys. One definition — build-artifact.py and htf_context.py
    both read it here rather than re-deriving it. (Before 2026-09-13 the prefix was `gold`, which named the
    instrument, not the market.)

    Answered by LOOKUP in the derived STYLE table, not by testing for a prefix. It used to read
    `"cfd" if style.startswith("cfd-") else "crypto"`, which is not a two-market simplification but a wrong
    answer for any third market: every fx- style would have quietly obeyed CRYPTO's dimension flags -- picking up
    footprint and heatmap, which have no forex source at all -- and nothing would have failed.

    An unrecognised non-empty style RAISES. Defaulting it to crypto is precisely the failure above."""
    if not style:
        return "crypto"
    hit = STYLE_MARKET_TF.get(style)
    if hit is None:
        raise KeyError(f"unknown style {style!r}; known: {', '.join(sorted(STYLE_MARKET_TF))}")
    return hit[0]


def _market_default(m):
    """The shape a market takes in a config that does not mention it.

    `enabled` is the market's REGISTERED default (instruments.json markets.<m>.default_enabled), not a blanket
    True. A market whose feed has no data -- forex today: the MT5 EA exports only symbols with an attached
    chart, and no FX chart is attached -- must not arrive enabled, because enabling it sets a flag over an
    empty directory and every downstream reader then reports a market that cannot produce a single candle."""
    return {"enabled": instruments.default_enabled(m), "instruments": list(MARKET_INSTRUMENTS[m]),
            "dimensions": {d: True for d in MARKET_DIMENSIONS[m]},
            "timeframes": {t: True for t in MARKET_TIMEFRAMES[m]}}


DEFAULTS = {
    "schema_version": SCHEMA_VERSION,
    "_comment": "Written by scripts/automation.py (/automation). execution.environment may ALSO be edited by hand "
                "to switch between config/env.demo and config/env.real; `/automation demo|real` writes it too. "
                "The schema at docs/architecture/schemas/automation-config.schema.json is the contract.",
    "enabled": True,
    "execution": {
        "environment": "demo",
        "_note": "demo = Binance TESTNET via config/env.demo; real = Binance MAINNET (real money) via "
                 "config/env.real. Switch by hand here or with `/automation demo|real`. The connectors and the "
                 "pilot read this on every call; an environment file with placeholder secrets refuses to execute.",
    },
    "markets": {m: _market_default(m) for m in MARKETS},
    "layers": {l: True for l in LAYERS},
    "services": {"scanner_agent": False, "pilot_agents": [], "keepawake_pid": None},
    "pilot_process": None,
    "last_updated": None,
    "history": [],
}


def _deep_merge(base, over):
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def migrate_v1(old):
    """v1 (flat dimensions/timeframes-as-styles/instruments) -> v2 (per-market). Nothing is silently turned ON:
    every v1 flag lands on its v2 counterpart, and the two styles v1 never had (1h, 4h) inherit the fail-open
    default the rest of the system already assumes for an unknown key."""
    cfg = json.loads(json.dumps(DEFAULTS))
    cfg["enabled"] = bool(old.get("enabled", True))
    cfg["execution"]["environment"] = _env_from_legacy(old.get("execution") or {})
    old_dims = old.get("dimensions") or {}
    old_styles = old.get("timeframes") or {}
    old_inst = set(old.get("instruments") or ALLOWED_INSTRUMENTS)
    for m in MARKETS:
        mk = cfg["markets"][m]
        mk["instruments"] = [s for s in MARKET_INSTRUMENTS[m] if s in old_inst]
        mk["enabled"] = bool(mk["instruments"])
        mk["dimensions"] = {d: bool(old_dims.get(d, True)) for d in MARKET_DIMENSIONS[m]}
        mk["timeframes"] = {t: bool(old_styles.get(STYLE[(m, t)], True)) for t in MARKET_TIMEFRAMES[m]}
    cfg["layers"] = {l: bool((old.get("layers") or {}).get(l, True)) for l in LAYERS}
    cfg["last_updated"] = old.get("last_updated")
    cfg["history"] = list(old.get("history") or [])[-HISTORY_MAX:]
    return cfg


def _env_from_legacy(execution):
    """v1/v2 execution.account -> v3 execution.environment."""
    if execution.get("environment") in ENV_NAMES:
        return execution["environment"]
    acct = execution.get("account", "demo_testnet")
    return "real" if acct == "real_mainnet" else "demo"


def migrate_v2(old):
    """v2 (per-market, execution.account) -> v3 (execution.environment, services). Everything else is kept."""
    cfg = _deep_merge(json.loads(json.dumps(DEFAULTS)), {k: v for k, v in old.items() if k != "execution"})
    cfg["schema_version"] = SCHEMA_VERSION
    cfg["execution"] = json.loads(json.dumps(DEFAULTS["execution"]))
    cfg["execution"]["environment"] = _env_from_legacy(old.get("execution") or {})
    return cfg


def clean(s, limit=300):
    """Audit strings may now carry values influenced from outside (the panel applier). Strip control
    characters and ANSI so a history row can never forge a second row or steer a terminal, and cap the
    length so one row cannot crowd the ring. CFG-05."""
    if s is None:
        return None
    return _CTRL.sub(" ", str(s)).strip()[:limit]


def load(require_readable=True):
    """(config, exists, migrated). A MISSING file means UNCONFIGURED: the defaults are what every reader
    assumes, so a clean checkout behaves exactly as it did before this switch existed. An UNREADABLE file is
    different -- it is a corrupt state, and replacing it with permissive defaults would silently turn every
    dimension and every layer back on. CFG-02: callers that intend to write pass require_readable=True (the
    default) and we exit 2 rather than return defaults."""
    if not os.path.exists(CONFIG):
        return json.loads(json.dumps(DEFAULTS)), False, False
    try:
        raw = json.load(open(CONFIG, encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"REFUSED: {CONFIG} is unreadable ({e}); refusing to overwrite it. Fix or delete the file.",
              file=sys.stderr)
        if require_readable:
            raise SystemExit(2)
        return json.loads(json.dumps(DEFAULTS)), False, False
    ver = int(raw.get("schema_version", 1))
    if ver <= 1:
        return migrate_v1(raw), True, True
    if ver == 2:
        return migrate_v2(raw), True, True
    return _deep_merge(json.loads(json.dumps(DEFAULTS)), raw), True, False


def record(cfg, a, action, result):
    cfg["history"].append({"ts": now(), "actor": clean(actor(a), 80), "action": clean(action),
                           "detail": clean(getattr(a, "reason", None)), "result": result})
    if len(cfg["history"]) > HISTORY_MAX:
        evicted, cfg["history"] = cfg["history"][:-HISTORY_MAX], cfg["history"][-HISTORY_MAX:]
        os.makedirs(os.path.dirname(HISTORY_ARCHIVE), exist_ok=True)
        with open(HISTORY_ARCHIVE, "a", encoding="utf-8") as f:      # CFG-07: the ring is not a shredder
            for row in evicted:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")


def save(cfg):
    """CFG-01: atomic and locked. Two writers exist now (a terminal and the applier cron); a truncate-in-place
    write loses one update outright and a crash mid-write leaves a file strategy-runner.py's automation_gate()
    reads as 'unreadable' -- i.e. a pilot outage."""
    cfg["last_updated"] = now()
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    lock = CONFIG + ".lock"
    with open(lock, "w") as lf:
        _lock(lf)
        try:
            tmp = CONFIG + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, CONFIG)
        finally:
            _unlock(lf)


# ---------- readers used by scan-loop.sh / local-eval-brief.py ----------
def enabled_styles(cfg=None):
    """The chart styles the scanner and the local read are permitted to run, in STYLE order."""
    if cfg is None:
        cfg, _, _ = load(require_readable=False)
    out = []
    for (m, tf), style in STYLE.items():
        mk = cfg.get("markets", {}).get(m, {})
        if mk.get("enabled", True) and mk.get("timeframes", {}).get(tf, True):
            out.append(style)
    return [s for s in STYLE.values() if s in out]


def enabled_instruments(cfg=None, market=None):
    if cfg is None:
        cfg, _, _ = load(require_readable=False)
    out = []
    for m in ([market] if market else MARKETS):
        mk = cfg.get("markets", {}).get(m, {})
        if mk.get("enabled", True):
            out += [s for s in MARKET_INSTRUMENTS[m] if s in mk.get("instruments", MARKET_INSTRUMENTS[m])]
    return out


def allows(layer, style=None):
    """(ok, reason). True if `layer` may act and, when given, `style`'s (market, timeframe) is on.
    Unconfigured => allowed (no policy, no behaviour change). This can only ever STOP something."""
    cfg, exists, _ = load(require_readable=False)
    if not exists:
        return True, None
    if not cfg.get("enabled", True):
        return False, "automation master switch is OFF (scripts/automation.py off)"
    if not cfg.get("layers", {}).get(layer, True):
        return False, f"layers.{layer} is off (scripts/automation.py layer {layer} off)"
    if style is not None:
        mtf = STYLE_MARKET_TF.get(style)
        if mtf is None:
            return True, None                      # unknown style: not this switch's business
        m, tf = mtf
        mk = cfg.get("markets", {}).get(m, {})
        if not mk.get("enabled", True):
            return False, f"market '{m}' is off (scripts/automation.py market {m} off)"
        if not mk.get("timeframes", {}).get(tf, True):
            return False, f"timeframe {tf} is off for market '{m}' " \
                          f"(scripts/automation.py timeframe {tf} off --market {m})"
    return True, None


# ---------- pilot process ----------
def alive(pid):
    if WIN:                 # os.kill(pid, 0) is TerminateProcess on Windows -- it would kill what it probes
        return win_services.alive(pid)
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def _pilot_market():
    """The market a running scripts/pilot-loop.sh is on. One venue since 2026-09-13, so there is one answer.

    Replaces _market_from_env() + _market_from_logs(). Both became unreachable-as-designed the moment
    pilot-loop.sh stopped taking PILOT_MARKET: _market_from_env() grepped a running process's environment for
    `PILOT_MARKET=`, which nothing sets any more, so it always returned None; _market_from_logs() then guessed
    from whichever loop.log was newest and fell back to the literal "spot" -- a market this tool can no longer
    stop, which would have mislabelled a live futures loop as unmanageable.
    """
    return PILOT_MARKETS[0]


def running_pilots():
    """[(pid, market)] for every live scripts/pilot-loop.sh, whether or not this config knows about it.
    A pilot the human started in their own terminal is invisible to pilot_process -- it must still block a
    second start, otherwise /automation would silently duplicate a live TESTNET loop."""
    if WIN:
        pids = win_services.pilot_pids()
        if pids is None:    # could not enumerate processes: say so loudly rather than report "none running"
            raise RuntimeError("cannot enumerate processes (PowerShell Get-CimInstance failed); refusing to "
                               "assume no pilot loop is running")
        return [(p, _pilot_market()) for p in pids]
    try:
        out = subprocess.run(["pgrep", "-f", PGREP_PATTERN], capture_output=True, text=True, timeout=10).stdout
        own = {os.getpid(), os.getppid()}  # never count this process or the shell that launched it
    except Exception:
        return []
    pids = [int(x) for x in out.split() if x.strip().isdigit() and int(x) not in own]
    return [(p, _pilot_market()) for p in pids]


def write_stop(reason_prefix="  "):
    """Write both kill switches -- or, under AUTOMATION_PILOT_DRYRUN, only say what would be written.
    A STOP file that exists for even one tick kills a human's running loop, so the dry run must not create it."""
    written = []
    for p in PILOT_STOP:
        if dryrun():
            print(f"{reason_prefix}DRY RUN: would write kill switch {rel(p)} (NOT created)")
            continue
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "a").close()
        written.append(p)
        print(f"{reason_prefix}kill switch written: {rel(p)}")
    return written


# ---------- status ----------
def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def warnings(cfg, exists):
    w = []
    if not exists:
        w.append(f"No config file yet ({rel(CONFIG)}). These are the built-in defaults; every gate treats "
                 f"'unconfigured' as 'no policy' and behaves as before. Any mutating subcommand creates it.")
    envname = cfg["execution"].get("environment", "demo")
    ok, missing, note = trading_env.completeness(envname)
    if envname == "real":
        w.append("environment = REAL (Binance MAINNET, real money) via config/env.real -- "
                 + ("secrets present." if ok else f"INCOMPLETE ({note}); every execution path refuses until filled."))
    elif not ok:
        w.append(f"environment = demo but config/env.demo is incomplete ({note}).")
    svc = cfg.get("services") or {}
    if cfg["enabled"] and not svc.get("scanner_agent"):
        w.append("automation is ON but the scanner launchd agent is not recorded as installed -- run `/automation on`.")
    for m in MARKETS:
        mk = cfg["markets"][m]
        if not mk["enabled"]:
            continue
        live = [d for d in MARKET_DIMENSIONS[m] if mk["dimensions"].get(d, True)]
        # The minimum is per MODE, not a flat 2. A single-dimension preset runs in SOLO (minimum 1, threshold 85
        # instead of NORMAL's 70) since 2026-09-12 -- so one enabled dimension is a valid trading configuration
        # when it came from a declared single-dimension preset, and warning about it is a false alarm.
        # methods.mode_of() is the only thing allowed to answer this: it reads the preset's own declared mode and
        # falls back to NORMAL for a 'custom' flag set, which keeps SOLO from being reachable by hand-toggling
        # dimensions rather than by choosing a preset (SYSTEM-DESIGN.md §6.2, preset-not-runtime safeguard).
        prof = methods.profile_of(mk["dimensions"])
        mode = methods.mode_of(prof)
        minimum = methods.MODES[mode]["minimum"]
        if len(live) < minimum:
            w.append(f"{m}: preset '{prof}' runs in {mode} mode, which needs at least {minimum} engaged "
                     f"dimension(s), but only {len(live)} is enabled -- no live TRADE verdict can pass for "
                     f"{m} instruments (SYSTEM-DESIGN.md §6.2).")
        # Switching a dimension off orphans any trade whose STOP that dimension owns. The narrative stays on disk
        # claiming an owner this configuration no longer reads, and check-narrative.py refuses it -- so say which
        # files need a fresh full analysis at switch time, not only when the checker next runs.
        off_owners = [d for d in methods.invalidation_owners() if d in MARKET_DIMENSIONS[m] and not mk["dimensions"].get(d, True)]
        if off_owners:
            orphans = []
            for st in sorted(s for s in TIERS if market_of_style(s) == m):
                n = _read_json(os.path.join(ROOT, "data", "live", "narrative", f"{st}.json"))
                for sym, d in ((n or {}).get("symbols") or {}).items():
                    if ((d or {}).get("invalidation") or {}).get("owner") in off_owners:
                        orphans.append(f"{st}/{sym}")
            if orphans:
                w.append(f"{m}: {', '.join(off_owners)} is off but {len(orphans)} narrative(s) still name it as "
                         f"invalidation.owner -- the stop is owned by a read this configuration does not make. "
                         f"Re-run the full analysis for: {', '.join(orphans)}.")

        if m == "crypto" and (mk["dimensions"].get("footprint") or mk["dimensions"].get("heatmap")):
            w.append("Footprint/Heatmap depend on CoinGlass -- check coinglass_* source state via /status; a MOCK "
                     "source can rehearse but can never satisfy the Independent-Confluence Check (data-sources.md).")
        if m == "cfd" and mk["instruments"]:
            w.append("CFD instruments are structurally capped at NORMAL mode (Wyckoff + ICT only; §12 item 3) and "
                     "the MT5 EA exports one charted symbol at a time -- 1W/1D/4H/1H/15m/5m, which covers the "
                     "scanned 15m/1h/4h plus the 1D/1W context charts (§12 item 6).")
            missing = [s for s in mk["instruments"] if not os.path.exists(
                os.path.join(ROOT, "data", "live", DATA_DIR["cfd"], f"ohlcv.{s}.15m.json"))]
            if missing:
                w.append("CFD instrument(s) enabled with no MT5 export on disk: " + ", ".join(missing) +
                         " -- attach integrations/mt5/ExportOHLCV.mq5 to a chart for each, or turn them off.")
    if cfg["layers"]["pilot"] and cfg["enabled"] and not (cfg.get("services") or {}).get("pilot_agents"):
        w.append("Pilot layer is PERMITTED but no pilot launchd agent is installed -- `/automation on` installs "
                 "one per market in PILOT_MARKETS (config/env.<environment>).")
    pp = cfg.get("pilot_process")
    if pp and pp.get("pid") and alive(pp["pid"]) and not pp.get("stopped_at"):
        w.append(f"Pilot loop RUNNING: pid {pp['pid']} ({pp.get('market')}) since {pp.get('started_at')} -- "
                 f"kill switch {rel(stop_path(pp.get('market') or PILOT_MARKETS[0]))}.")
    managed = bool(pp and pp.get("launchd_label") and _agent_loaded(pp["launchd_label"]))
    unrecorded = [(p, m) for p, m in running_pilots()
                  if not (pp and pp.get("pid") == p) and not (managed and m == pp.get("market"))]
    if unrecorded:
        w.append("Pilot loop(s) running but NOT recorded in this file: " +
                 ", ".join(f"pid {p} ({m})" for p, m in unrecorded) +
                 " -- `pilot adopt` records one into pilot_process. Do not start a second loop.")
    present = [rel(p) for p in PILOT_STOP if os.path.exists(p)]
    if present:
        w.append("Kill switch present: " + ", ".join(present) + " (pilot loop exits on the next tick).")
    return w


def show(cfg, exists, as_json=False, brief=False):
    if as_json:
        print(json.dumps(cfg, indent=2, ensure_ascii=False))
        return
    onoff = lambda b: "ON " if b else "off"
    envname = cfg["execution"].get("environment", "demo")
    print(f"AUTOMATION: {'ON' if cfg['enabled'] else 'OFF'}   "
          f"environment: {envname.upper()} ({'TESTNET' if envname == 'demo' else 'REAL MONEY'})"
          + (f"   (setup {cfg['execution']['setup_spec']})" if cfg['execution'].get('setup_spec') else ""))
    if brief:
        svc = cfg.get("services") or {}
        print(f"  scanner: {'installed' if svc.get('scanner_agent') else 'not installed'}; "
              f"pilot: {', '.join(svc.get('pilot_agents') or []) or 'none'}; "
              f"keep-awake: {'yes' if svc.get('keepawake_pid') else 'no'}")
        for w in warnings(cfg, exists):
            print("  ! " + w)
        return
    # Full details (for /status)
    print(f"  file:        {rel(CONFIG)}{'' if exists else '  [not created yet -- defaults]'}")
    print(f"  updated:     {cfg['last_updated'] or '(never)'}")
    print("  layers:      " + "  ".join(f"{onoff(cfg['layers'][l])} {l}" for l in LAYERS))
    svc = cfg.get("services") or {}
    print(f"  services:    scanner agent {'installed' if svc.get('scanner_agent') else 'not installed'}; "
          f"pilot agents {', '.join(svc.get('pilot_agents') or []) or 'none'}; "
          f"keep-awake pid {svc.get('keepawake_pid') or 'none'}")
    for m in MARKETS:
        mk = cfg["markets"][m]
        styles = [STYLE[(m, tf)] for tf in MARKET_TIMEFRAMES[m] if mk["timeframes"].get(tf, True)] \
            if mk["enabled"] else []
        print(f"  {m:<7}      [{'ON ' if mk['enabled'] else 'off'}]  instruments: "
              + (", ".join(mk["instruments"]) or "(none)"))
        print("               dimensions: " + "  ".join(f"{onoff(mk['dimensions'].get(d, True))} {d}"
                                                        for d in MARKET_DIMENSIONS[m]))
        print("               timeframes: " + "  ".join(f"{onoff(mk['timeframes'].get(t, True))} {t}"
                                                        for t in MARKET_TIMEFRAMES[m]))
        prof = methods.profile_of(mk["dimensions"])
        mode = methods.mode_of(prof)
        minimum, threshold = methods.MODES[mode]["minimum"], methods.MODES[mode]["threshold"]
        live = [d for d in MARKET_DIMENSIONS[m] if mk["dimensions"].get(d, True)]
        print(f"               method:     {prof}  [{mode}: min {minimum} dimension(s), score {threshold}]"
              + ("" if prof != "custom" else f"  (set from the terminal: {', '.join(live) or 'none'})")
              + ("" if len(live) >= minimum else f"   [only {len(live)} enabled -- no live TRADE verdict can pass]"))
        print("               styles on:  " + (", ".join(styles) or "(none)"))
    pp = cfg.get("pilot_process")
    if pp:
        state = "stopped_at " + pp["stopped_at"] if pp.get("stopped_at") else \
                ("alive" if alive(pp.get("pid")) else "not running")
        print(f"  pilot proc:  pid {pp.get('pid')} {pp.get('market')} {state}"
              f"{'  [DRY RUN placeholder]' if pp.get('dry_run') else ''}  started {pp.get('started_at')} "
              f"by {pp.get('started_by')}")
    else:
        print("  pilot proc:  none recorded")
    for h in cfg["history"][-3:]:
        print(f"  last change: {clean(h.get('ts'))} {clean(h.get('actor'))} {clean(h.get('action'))} -> "
              f"{clean(h.get('result'))}" + (f" ({clean(h.get('detail'))})" if h.get("detail") else ""))
    for w in warnings(cfg, exists):
        print("  ! " + w)


# ---------- launchd services (what `on` installs and `off` removes) ----------
def _uid():
    return os.getuid()


def _launchctl(*args, check=False):
    try:
        r = subprocess.run(["launchctl", *args], capture_output=True, text=True, timeout=30)
    except Exception as e:
        return 1, str(e)
    return r.returncode, (r.stdout + r.stderr).strip()


def _agent_loaded(label):
    if WIN:
        return win_services.task_loaded(label)
    rc, out = _launchctl("print", f"gui/{_uid()}/{label}")
    return rc == 0


def _role(label):
    return "scanner" if label == SCANNER_LABEL else "pilot"


def _install_agent(label, src, env_overrides=None):
    """Copy the plist into ~/Library/LaunchAgents (rewriting Label / EnvironmentVariables as needed) and bootstrap it.
    On Windows: a per-user scheduled task running scripts/win_services.py <role> (PILOT_END=never is set there).
    Returns (ok, note)."""
    if WIN:
        if dryrun():
            return True, f"DRY RUN: would install scheduled task {win_services.task_name(label)}"
        return win_services.install_task(label, _role(label))
    os.makedirs(LAUNCH_AGENTS, exist_ok=True)
    dst = os.path.join(LAUNCH_AGENTS, f"{label}.plist")
    txt = open(src, encoding="utf-8").read()
    base_label = os.path.basename(src)[:-len(".plist")]
    txt = txt.replace(f"<string>{base_label}</string>", f"<string>{label}</string>", 1)
    for k, v in (env_overrides or {}).items():
        marker = f"<key>{k}</key><string>"
        if marker in txt:
            head, _, tail = txt.partition(marker)
            _, _, rest = tail.partition("</string>")
            txt = head + marker + v + "</string>" + rest
        else:
            txt = txt.replace("<key>PATH</key>", f"<key>{k}</key><string>{v}</string>\n    <key>PATH</key>", 1)
    if dryrun():
        return True, f"DRY RUN: would install {dst} and bootstrap gui/{_uid()}/{label}"
    with open(dst, "w", encoding="utf-8") as f:
        f.write(txt)
    if _agent_loaded(label):
        _launchctl("bootout", f"gui/{_uid()}/{label}")
    rc, out = _launchctl("bootstrap", f"gui/{_uid()}", dst)
    if rc != 0:
        rc2, out2 = _launchctl("load", "-w", dst)          # older launchctl fallback
        if rc2 != 0:
            return False, f"launchctl bootstrap failed for {label}: {out or out2}"
    return True, f"installed + bootstrapped {label} ({rel(dst) if dst.startswith(ROOT) else dst})"


def _remove_agent(label):
    if WIN:
        if dryrun():
            return f"DRY RUN: would delete scheduled task {win_services.task_name(label)}"
        return win_services.remove_task(label, _role(label))
    dst = os.path.join(LAUNCH_AGENTS, f"{label}.plist")
    if dryrun():
        return f"DRY RUN: would bootout gui/{_uid()}/{label} and remove {dst}"
    if _agent_loaded(label):
        _launchctl("bootout", f"gui/{_uid()}/{label}")
    if os.path.exists(dst):
        os.remove(dst)
    return f"booted out + removed {label}"


def _start_keepawake(cfg):
    pid = (cfg.get("services") or {}).get("keepawake_pid")
    if pid and alive(pid):
        return f"keep-awake already running (pid {pid})"
    if dryrun():
        return "DRY RUN: would start `caffeinate -dims`"
    if WIN:
        try:
            pid = win_services.start_keepawake()
            cfg.setdefault("services", {})["keepawake_pid"] = pid
            return f"keep-awake started (SetThreadExecutionState, pid {pid}) -- the pilot loop needs the host awake"
        except Exception as e:
            return f"keep-awake NOT started ({e}); set Windows power options so the PC does not sleep"
    try:
        p = subprocess.Popen(["caffeinate", "-dims"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
        cfg.setdefault("services", {})["keepawake_pid"] = p.pid
        return f"keep-awake started (caffeinate -dims, pid {p.pid}) -- the pilot loop needs the host awake (§9.x)"
    except Exception as e:
        return f"keep-awake NOT started ({e}); run `caffeinate -dims` yourself if the Mac may sleep"


def _stop_keepawake(cfg):
    pid = (cfg.get("services") or {}).get("keepawake_pid")
    if pid and alive(pid) and not dryrun():
        if WIN:
            win_services.kill_tree(pid)
        try:
            if not WIN:
                os.kill(int(pid), 15)
        except OSError:
            pass
    cfg.setdefault("services", {})["keepawake_pid"] = None
    return f"keep-awake stopped (pid {pid})" if pid else "no keep-awake to stop"


def mt5_freshness(cfg):
    """(fresh, note) for the CFD bridge. Not a gate: the user opens MT5 first; we only say what we see."""
    mk = cfg["markets"]["cfd"]
    if not mk["enabled"] or not mk["instruments"]:
        return True, "cfd market off or no instruments -- MT5 not needed"
    try:
        env = trading_env.load_env(resolve_secrets=False)
        max_age = float(env.get("MT5_BRIDGE_MAX_AGE_MIN", 30))
        bdir = os.path.join(ROOT, env.get("MT5_BRIDGE_DIR", "data/live/mt5-bridge"))
    except Exception:
        max_age, bdir = 30.0, os.path.join(ROOT, "data", "live", "mt5-bridge")
    stale = []
    for sym in mk["instruments"]:
        p = os.path.join(bdir, f"ohlcv.{sym}.15m.json")
        if not os.path.exists(p):
            stale.append(f"{sym}: no bridge file")
            continue
        age = (datetime.datetime.now().timestamp() - os.path.getmtime(p)) / 60
        if age > max_age:
            stale.append(f"{sym}: last export {age:.0f} min ago (> {max_age:.0f})")
    if stale:
        return False, ("MT5 bridge NOT fresh -- open MetaTrader 5 with integrations/mt5/ExportOHLCV.mq5 attached, "
                       "then the CFD styles resume by themselves: " + "; ".join(stale))
    return True, "MT5 bridge fresh for " + ", ".join(mk["instruments"])


def bring_up(cfg, a):
    """`on`: install/refresh the scanner agent, the pilot agents for PILOT_MARKETS, keep-awake; report MT5."""
    notes = []
    cfg["enabled"] = True
    cfg.setdefault("services", {"scanner_agent": False, "pilot_agents": [], "keepawake_pid": None})
    envname = cfg["execution"].get("environment", "demo")
    try:
        env = trading_env.load_env(resolve_secrets=False)
    except trading_env.EnvIncomplete as e:
        env = {}
        notes.append(f"! environment '{envname}' problem: {e}")
    if cfg["layers"]["scanner"]:
        ok, note = _install_agent(SCANNER_LABEL, PLIST_SRC["scanner"])
        cfg["services"]["scanner_agent"] = bool(ok) and not dryrun()
        notes.append(("+ " if ok else "! ") + note)
    else:
        notes.append("- scanner layer is off; scanner agent not installed")
    fresh, mnote = mt5_freshness(cfg)
    notes.append(("+ " if fresh else "! ") + mnote)
    if cfg["layers"]["pilot"] and cfg["markets"]["crypto"]["enabled"]:
        wanted = [m.strip() for m in (env.get("PILOT_MARKETS", PILOT_MARKETS[0])).split(",") if m.strip() in PILOT_MARKETS]
        # A loop started outside launchd (a terminal, nohup) trades the same account. Never install a managed
        # loop next to it: that would double-trade. The user stops it first (touch its STOP file) or adopts it.
        unmanaged = [(p, m) for p, m in running_pilots()
                     if not any(_agent_loaded(PILOT_LABEL[x]) for x in PILOT_MARKETS)]
        for m in wanted:
            if _agent_loaded(PILOT_LABEL[m]):
                notes.append(f"+ pilot [{m}] agent already installed and loaded ({PILOT_LABEL[m]}) -- left as is")
                if PILOT_LABEL[m] not in cfg["services"]["pilot_agents"]:
                    cfg["services"]["pilot_agents"].append(PILOT_LABEL[m])
                continue
            if unmanaged:
                notes.append(f"! pilot [{m}] NOT installed: a pilot loop is already running outside launchd ("
                             + ", ".join(f"pid {p} ({mm})" for p, mm in unmanaged)
                             + "). Stop it first (touch data/live/pilot*/STOP, wait one tick) or `pilot adopt` it, "
                               "then run `/automation on` again -- installing a second loop would double-trade.")
                continue
            # One venue, one key pair. The branch here used to pick the SPOT keys for the deleted market; with
            # one venue it was unreachable, and picking those keys for a futures order path would sign against
            # the wrong API.
            keys = ("BINANCE_FUTURES_API_KEY", "BINANCE_FUTURES_SECRET_KEY")
            ok, missing, cnote = trading_env.completeness(envname, keys)
            if not ok:
                notes.append(f"! pilot [{m}] NOT started: environment '{envname}' incomplete ({cnote})")
                continue
            sp = stop_path(m)
            if os.path.exists(sp) and not dryrun():
                os.remove(sp)
                notes.append(f"+ removed kill switch {rel(sp)} (on = re-arm)")
            ok, note = _install_agent(PILOT_LABEL[m], PLIST_SRC["pilot"], {"PILOT_END": "never"})
            notes.append(("+ " if ok else "! ") + f"pilot [{m}] {note}")
            if ok and not dryrun() and PILOT_LABEL[m] not in cfg["services"]["pilot_agents"]:
                cfg["services"]["pilot_agents"].append(PILOT_LABEL[m])
            cfg["pilot_process"] = {"pid": 0, "market": m, "started_at": now(), "started_by": actor(a),
                                    "log": rel(log_path(m)), "launchd_label": PILOT_LABEL[m]}
    else:
        notes.append("- pilot layer off or crypto market off; no pilot agent installed")
    notes.append("+ " + _start_keepawake(cfg))
    return notes


def tear_down(cfg, a):
    """`off`: kill switches, boot out + remove every agent we installed (and the scanner), stop keep-awake."""
    notes = []
    cfg["enabled"] = False
    svc = cfg.setdefault("services", {"scanner_agent": False, "pilot_agents": [], "keepawake_pid": None})
    write_stop()
    seen = set()
    for label in list(svc.get("pilot_agents") or []) + list(PILOT_LABEL.values()):
        if label in seen:
            continue
        seen.add(label)
        if label in (svc.get("pilot_agents") or []) or _agent_loaded(label):
            notes.append("+ " + _remove_agent(label))
    svc["pilot_agents"] = []
    notes.append("+ " + _remove_agent(SCANNER_LABEL))
    svc["scanner_agent"] = False
    notes.append("+ " + _stop_keepawake(cfg))
    pp = cfg.get("pilot_process")
    if pp and not pp.get("stopped_at"):
        pp["stopped_at"] = now()
    others = running_pilots()
    if others:
        notes.append("! pilot loop(s) still running outside launchd (they exit on their next tick because the "
                     "STOP files are written): " + ", ".join(f"pid {p} ({m})" for p, m in others))
    return notes


# ---------- session crons (the Claude-side chart layers) ----------
def _cron_templates_module():
    spec = importlib.util.spec_from_file_location("cron_templates", os.path.join(ROOT, "scripts", "cron-templates.py"))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def session_cron_block(on):
    """Print exactly what to CronCreate. No instructional prose."""
    if not on:
        print("SESSION CRONS: automation is OFF. Delete all [trading-cron:* jobs if any exist.")
        return
    try:
        ct = _cron_templates_module()
    except Exception as e:
        print(f"ERROR: could not load cron-templates.py ({e})")
        return
    scratch = os.environ.get("AUTOMATION_SCRATCHPAD") or os.path.join(os.environ.get("TMPDIR", "/tmp"), "trading-crons-scratch")
    outdir = os.path.join(scratch, "crons")
    os.makedirs(outdir, exist_ok=True)
    cfg = ct.config()
    print("SESSION CRONS: CronCreate each line below:")
    n = 0
    for meta, body in ct.templates():
        ok, why = ct.enabled(meta, cfg)
        if not ok:
            continue
        prompt = ct.render(meta, body, scratch)
        p = os.path.join(outdir, f"{meta['name']}.prompt.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write(prompt)
        n += 1
        model = meta.get("model")
        print(f"  CronCreate({meta.get('cron')!r}, prompt_file={p}" + (f", model={model}" if model in ("haiku", "sonnet", "opus") else "") + ")")   # main-session = the session's own model
    print(f"Then CronList to confirm {n} jobs. They expire after 7 days.")

# ---------- mutating subcommands ----------
def apply_setup_spec(cfg, a):
    """`setup top N` (user decision 2026-09-11): rank the last 365 days with scripts/rank-setups.py, write docs/architecture/pilot-top20.json
    with N crypto + N CFD setups. Returns (rc, lines). `setup` absent -> no change."""
    spec = [x.lower() for x in (getattr(a, "setup", None) or [])]
    sel = os.path.join(ROOT, "docs", "architecture", "pilot-top20.json"); out = os.path.join(ROOT, "docs", "backtests", "top-setups-latest.md")
    cfd_syms = ",".join(cfg["markets"]["cfd"]["instruments"] or ["XAUUSD"]); crypto_syms = ",".join(cfg["markets"]["crypto"]["instruments"] or MARKET_INSTRUMENTS["crypto"])
    if not spec:
        # user decision 2026-09-11 (night): plain `on`/`demo` runs scalping + day + swing for crypto AND CFD -- one setup per horizon per
        # market, ranked on the last 12 months -- unless a `setup top N` selection is in force (execution.setup_spec starts with "top").
        if (cfg["execution"].get("setup_spec") or "").startswith("top") and os.path.exists(sel):
            return 0, [f"keeps the selection `{cfg['execution']['setup_spec']}` ({rel(sel)}); `on setup horizons` re-selects per horizon"]
        spec = ["setup", "horizons"]
    if spec == ["setup", "horizons"]:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "rank-setups.py"), "--horizons", "--window", "1y", "--select", sel, "--out", out,
                            "--crypto-symbols", crypto_syms, "--cfd-symbols", cfd_syms], capture_output=True, text=True)
        if r.returncode != 0:
            return 2, [f"rank-setups.py --horizons failed: {r.stderr.strip()[:300]}"]
        try:
            setups = json.load(open(sel, encoding="utf-8"))["setups"]
        except Exception as e:
            return 2, [f"selection file unreadable after ranking: {e}"]
        cfg["execution"]["setup_spec"] = "horizons (1y)"
        record(cfg, a, "setup horizons", "applied")
        lines = [f"SETUP HORIZONS: {len(setups)} setups (scalping / day / swing per market, ranked on the last 12 months) -> {rel(sel)} (table {rel(out)})"]
        for st in setups:
            b = st.get("backtest", {})
            lines.append(f"  {st['rank']}. {st['id']}: {st['market']} {st['horizon']} {st['tf']} {st['method']} htf={st.get('htf')} exec={st['execution']} | 1y: n={b.get('n')} {b.get('ann_pct')}% DD -{b.get('max_dd_pct')}% quarters+ {b.get('q_pos_pct')}%"
                         + ("  [BACKTEST ÂM]" if st.get("negative_backtest") else ""))
        for m in ("crypto", "cfd"):
            missing = [h for h in ("scalping", "day", "swing") if not any(st["market"] == m and st["horizon"] == h for st in setups)]
            if missing:
                lines.append(f"  ! {m}: no {', '.join(missing)} setup met the minimum trade count -- that horizon will not be traded")
        return 0, lines
    if len(spec) != 3 or spec[0] != "setup" or spec[1] != "top" or not spec[2].isdigit() or not (1 <= int(spec[2]) <= 10):
        return 1, [f"usage: on|demo [setup top <1..10> | setup horizons]  (got: {' '.join(spec)})"]
    n = int(spec[2])
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "rank-setups.py"), "--window", "1y", "--n", str(n), "--select", sel, "--out", out,
                        "--crypto-symbols", crypto_syms, "--cfd-symbols", cfd_syms], capture_output=True, text=True)
    if r.returncode != 0:
        return 2, [f"rank-setups.py failed: {r.stderr.strip()[:300]}"]
    try:
        setups = json.load(open(sel, encoding="utf-8"))["setups"]
    except Exception as e:
        return 2, [f"selection file unreadable after ranking: {e}"]
    cfg["execution"]["setup_spec"] = f"top {n} (1y)"
    record(cfg, a, f"setup top {n}", "applied")
    lines = [f"SETUP TOP {n}: {len(setups)} setups selected on the last 12 months -> {rel(sel)} (table {rel(out)})"]
    for st in setups:
        b = st.get("backtest", {})
        lines.append(f"  {st['rank']}. {st['id']}: {st['market']} {st['tf']} {st['method']} htf={st.get('htf')} exec={st['execution']} | 1y: n={b.get('n')} {b.get('ann_pct')}% DD -{b.get('max_dd_pct')}% quarters+ {b.get('q_pos_pct')}%"
                     + ("  [BACKTEST ÂM]" if st.get("negative_backtest") else ""))
    missing = [m for m in ("crypto", "cfd") if not any(st["market"] == m for st in setups)]
    if missing:
        lines.append(f"  ! no {', '.join(missing)} setup met the minimum trade count in the last year -- that market will not be traded")
    return 0, lines


def cmd_master(a):
    cfg, exists, _ = load(require_readable=True)
    want = a.cmd == "on"
    if want:
        rc, lines = apply_setup_spec(cfg, a)
        for l in lines:
            print(l)
        if rc:
            save(cfg); return rc
    notes = bring_up(cfg, a) if want else tear_down(cfg, a)
    record(cfg, a, a.cmd, "applied")
    save(cfg)
    print(f"AUTOMATION {'ON' if want else 'OFF'} -- environment {cfg['execution'].get('environment', 'demo').upper()}")
    for n in notes:
        print("  " + n)
    session_cron_block(want)
    if want:
        print("\nWHAT HAPPENS NOW: launchd runs scanner, pilot, keep-awake in background. Session crons run while this session is open (7-day max).")
        print("  Watch: tail -f data/live/pilot/loop.log    (entry/exit verdicts)")
        print("         tail -f data/live/scan-loop.log     (scanner ticks)")
    show(cfg, True, brief=True)
    return 0


def cmd_env(a):
    cfg, exists, _ = load(require_readable=False)
    envname = cfg["execution"].get("environment", "demo")
    # One venue, one key pair to report. This printed two lines -- trading_env.completeness()'s default (the SPOT
    # keys) and then the futures keys -- which for a futures-only system meant the first line reported the
    # completeness of credentials nothing uses, directly above the ones that matter.
    ok, missing, note = trading_env.completeness(envname, ("BINANCE_FUTURES_API_KEY", "BINANCE_FUTURES_SECRET_KEY"))
    print(f"environment: {envname}  file: config/env.{envname}  futures secrets: {note}")
    print("  switch: `/automation demo|real`, or edit execution.environment in " + rel(CONFIG))
    return 0


def apply_preset(cfg, a, envname):
    """Shared by `demo` and `real`: environment + both markets + data-backed instruments + EVERY timeframe ON (all three horizons)."""
    enabled_msgs, skipped_msgs = [], []
    cfg["execution"]["environment"] = envname
    cfg["enabled"] = True
    for l in LAYERS:
        cfg["layers"][l] = True
    enabled_msgs.append(f"environment {envname.upper()}; master switch ON; layers scanner + local_read + pilot ON")
    for m in MARKETS:
        mk = cfg["markets"][m]
        mk["enabled"] = True
        keep = []
        for sym in MARKET_INSTRUMENTS[m]:
            probe = os.path.join(ROOT, "data", "live", DATA_DIR[m], f"ohlcv.{sym}.15m.json")
            if os.path.exists(probe):
                keep.append(sym)
            else:
                skipped_msgs.append(f"{sym} skipped: no {'MT5 export' if m == 'cfd' else 'Binance data'} on disk "
                                    f"({rel(probe)})")
        mk["instruments"] = keep
        # The method preset is the user's choice and survives an environment switch (spec §4.1). Before this,
        # demo/real turned every dimension back on and silently erased it.
        prof = methods.profile_of(mk["dimensions"])
        enabled_msgs.append(f"{m}: method preset kept as {prof}")
        for t in MARKET_TIMEFRAMES[m]:          # every timeframe of the market: scalping (15m), day (1h), swing (4h) -- user decision 2026-09-13
            mk["timeframes"][t] = True
        on_tfs = [t for t in MARKET_TIMEFRAMES[m] if mk["timeframes"].get(t, True)]
        enabled_msgs.append(f"{m}: instruments {', '.join(keep) or '(none)'}; timeframes ON {', '.join(on_tfs)} "
                            f"-> styles {', '.join(STYLE[(m, t)] for t in on_tfs)}")
        if not keep:
            skipped_msgs.append(f"{m}: no instrument has data on disk, so every {m} style will no-op")
    skipped_msgs.append("cfd dimensions footprint/heatmap do not exist -- no CoinGlass source for commodities "
                        "(SYSTEM-DESIGN.md §12 item 3)")
    skipped_msgs.append("scanned timeframes are 15m/1h/4h for both markets (scalping/day/swing) -- 1m, 5m and 1D "
                        "left the scanned set on 2026-09-13; 1D and 1W are still fetched as context charts")
    return enabled_msgs, skipped_msgs


def cmd_preset(a):
    envname = a.cmd
    cfg, exists, _ = load(require_readable=True)
    if envname == "real":
        ok, missing, note = trading_env.completeness("real")
        if not ok:
            record(cfg, a, "real", "refused")
            save(cfg)
            print(f"REFUSED: config/env.real is incomplete ({note}). Fill in the real account's keys "
                  f"(see the header of that file), then run `/automation real` again. Nothing was changed.",
                  file=sys.stderr)
            show(cfg, exists)
            return 2
    rc, lines = apply_setup_spec(cfg, a)
    for l in lines:
        print(l)
    if rc:
        save(cfg); return rc
    enabled_msgs, skipped_msgs = apply_preset(cfg, a, envname)
    record(cfg, a, f"{envname} (preset)", "applied")
    save(cfg)
    print(f"{envname.upper()} PRESET APPLIED")
    for s in enabled_msgs:
        print("  + " + s)
    for s in skipped_msgs:
        print("  - " + s)
    notes = bring_up(cfg, a)
    record(cfg, a, f"{envname} -> on", "applied")
    save(cfg)
    for n in notes:
        print("  " + n)
    session_cron_block(True)
    show(cfg, True)
    return 0


def cmd_market(a):
    cfg, _, _ = load(require_readable=True)
    want = a.value == "on"
    mk = cfg["markets"][a.name]
    result = "no-op" if mk["enabled"] == want else "applied"
    mk["enabled"] = want
    record(cfg, a, f"market {a.name}={a.value}", result)
    save(cfg)
    show(cfg, True)
    return 0


def cmd_timeframe(a):
    cfg, _, _ = load(require_readable=True)
    targets = [a.market] if a.market else [m for m in MARKETS if a.name in MARKET_TIMEFRAMES[m]]
    bad = [m for m in targets if a.name not in MARKET_TIMEFRAMES[m]]
    if bad:
        record(cfg, a, f"timeframe {a.name}={a.value} --market {','.join(bad)}", "refused")
        save(cfg)
        # Both markets scan the same three horizons since 2026-09-13, so argparse's `choices` already rejects
        # everything this branch would catch. It stays because MARKET_TIMEFRAMES is per-market BY SHAPE: the day a
        # market loses a rung, this refuses instead of writing a flag nothing reads.
        print(f"REFUSED: timeframe {a.name} does not exist for market '{bad[0]}'. The scanned set is one horizon "
              f"per timeframe (automation.HORIZON_TF: scalping 15m, day 1h, swing 4h); 1D and 1W are context "
              f"charts only and are not switchable here. "
              f"{bad[0]} timeframes: {', '.join(MARKET_TIMEFRAMES[bad[0]])}.", file=sys.stderr)
        show(cfg, True)
        return 2
    want = a.value == "on"
    changed = False
    for m in targets:
        if cfg["markets"][m]["timeframes"].get(a.name) != want:
            changed = True
        cfg["markets"][m]["timeframes"][a.name] = want
    record(cfg, a, f"timeframe {a.name}={a.value} --market {','.join(targets)}",
           "applied" if changed else "no-op")
    save(cfg)
    print("  styles affected: " + ", ".join(STYLE[(m, a.name)] for m in targets))
    show(cfg, True)
    return 0


def cmd_method(a):
    """Apply a named preset = a set of the four dimension flags. The preset is only a NAME for that set
    (spec §3); nothing new is stored, and scripts/methods.py derives the label back from the flags."""
    cfg, _, _ = load(require_readable=True)
    p = methods.preset(a.preset)
    if p is None:                                   # argparse choices should have caught this; belt and braces
        record(cfg, a, f"method {a.preset}", "refused"); save(cfg)
        print(f"REFUSED: unknown preset '{a.preset}'. Known: "
              f"{', '.join(x['id'] for x in methods.PRESETS)}", file=sys.stderr)
        return 2
    targets = [a.market] if a.market else [m for m in MARKETS if p in methods.presets_for(m)]
    bad = [m for m in ([a.market] if a.market else []) if p not in methods.presets_for(m)]
    if bad:
        missing = sorted(set(p["dimensions"]) - set(methods.dimensions(bad[0])))
        record(cfg, a, f"method {a.preset} --market {','.join(bad)}", "refused")
        save(cfg)
        print(f"REFUSED: preset '{a.preset}' needs {', '.join(missing)}, which market '{bad[0]}' has no source "
              f"for (CoinGlass is crypto-derivatives only, SYSTEM-DESIGN.md §12 item 3).", file=sys.stderr)
        show(cfg, True)
        return 2
    skipped = [] if a.market else [m for m in MARKETS if m not in targets]
    if skipped:
        print(f"NOTE: preset '{a.preset}' was not applied to {', '.join(skipped)} (no CoinGlass source there); "
              f"applied only to {', '.join(targets)}. Pass --market to target one market explicitly.",
              file=sys.stderr)
    want = methods.flags_for(a.preset)
    changed = []
    for m in targets:
        flags = {d: want[d] for d in MARKET_DIMENSIONS[m]}
        if cfg["markets"][m]["dimensions"] != flags:
            changed.append(m)
        cfg["markets"][m]["dimensions"] = flags          # CFG-10: this block and nothing else
    record(cfg, a, f"method {a.preset} --market {','.join(targets)}",
           "applied" if changed else "no-op")
    save(cfg)
    show(cfg, True)
    return 0


def cmd_dimension(a):
    cfg, _, _ = load(require_readable=True)
    targets = [a.market] if a.market else [m for m in MARKETS if a.name in MARKET_DIMENSIONS[m]]
    bad = [m for m in targets if a.name not in MARKET_DIMENSIONS[m]]
    if bad:
        record(cfg, a, f"dimension {a.name}={a.value} --market {','.join(bad)}", "refused")
        save(cfg)
        print(f"REFUSED: dimension '{a.name}' does not exist for market '{bad[0]}'. Footprint and Heatmap have no "
              f"CFD data source at all -- CoinGlass is crypto-derivatives only, so XAUUSD/XAGUSD/USOIL/UKOIL are "
              f"structurally capped at Wyckoff + ICT, i.e. NORMAL mode (SYSTEM-DESIGN.md §12 item 3). This is a "
              f"structural limit, not a flag: the schema has no such key to set.", file=sys.stderr)
        show(cfg, True)
        return 2
    want = a.value == "on"
    changed = False
    for m in targets:
        if cfg["markets"][m]["dimensions"].get(a.name) != want:
            changed = True
        cfg["markets"][m]["dimensions"][a.name] = want
    record(cfg, a, f"dimension {a.name}={a.value} --market {','.join(targets)}",
           "applied" if changed else "no-op")
    save(cfg)
    show(cfg, True)
    return 0


def cmd_layer(a):
    cfg, _, _ = load(require_readable=True)
    want = a.value == "on"
    result = "no-op" if cfg["layers"][a.name] == want else "applied"
    cfg["layers"][a.name] = want
    record(cfg, a, f"layer {a.name}={a.value}", result)
    save(cfg)
    if a.name == "pilot" and want:
        print("  NOTE: `layer pilot on` records PERMISSION only. Nothing is started. "
              "`pilot start` is what starts it, and only when you ask.")
    show(cfg, True)
    return 0


def cmd_instrument(a):
    sym = a.symbol.upper()
    cfg, _, _ = load(require_readable=True)
    m = market_of(sym)
    if m is None:
        record(cfg, a, f"instrument {sym}={a.value}", "refused")
        save(cfg)
        print(f"REFUSED: {sym} is not on the instrument allowlist "
              f"({', '.join(ALLOWED_INSTRUMENTS)}) -- SYSTEM-DESIGN.md §1.", file=sys.stderr)
        show(cfg, True)
        return 2
    cur = set(cfg["markets"][m]["instruments"])
    want = a.value == "on"
    result = "no-op" if (sym in cur) == want else "applied"
    cur = (cur | {sym}) if want else (cur - {sym})
    cfg["markets"][m]["instruments"] = [s for s in MARKET_INSTRUMENTS[m] if s in cur]
    record(cfg, a, f"instrument {sym}={a.value} (market {m})", result)
    save(cfg)
    if want and not os.path.exists(os.path.join(ROOT, "data", "live", DATA_DIR[m], f"ohlcv.{sym}.15m.json")):
        print(f"  NOTE: no data on disk for {sym} yet "
              f"(data/live/{DATA_DIR[m]}/ohlcv.{sym}.15m.json). The flag is set; the source is not wired.")
    show(cfg, True)
    return 0


def cmd_instrument_set(a):
    """Declarative batch: `instrument set BTCUSDT,ETHUSDT --market crypto` replaces the whole list in ONE
    write and ONE history row (CFG-11). The single-symbol form stays for terminal use; this one exists
    because the panel sends a full desired set and nine symbols must not cost nine rows of a 200-row ring.

    Validation is re-done here, independently of whoever called (CFG-12): a future caller may not be the
    applier cron. Nothing is normalised -- a value either is the canonical allowlist spelling or is refused."""
    m = a.market
    raw = [s for s in (a.symbols or "").split(",") if s != ""]
    universe = MARKET_INSTRUMENTS[m]
    problems = []
    for sym in raw:
        if sym not in universe:
            problems.append(f"{sym}: not on the {m} allowlist ({', '.join(universe)})")
    if len(set(raw)) != len(raw):
        problems.append(f"duplicate symbols in {','.join(raw)}")

    cfg, _, _ = load()
    if problems:                                        # CFG-11: all-or-nothing, config untouched
        record(cfg, a, f"instrument set {','.join(raw) or '(none)'} --market {m}", "refused")
        save(cfg)
        print("REFUSED: " + "; ".join(problems), file=sys.stderr)
        show(cfg, True)
        return 2

    want = [s for s in universe if s in set(raw)]       # CFG-13: canonical order
    if cfg["markets"][m]["instruments"] == want:
        print(f"no-op: {m} instruments already {', '.join(want) or '(none)'}")
        return 0                                        # CFG-13: a true no-op records nothing
    cfg["markets"][m]["instruments"] = want
    record(cfg, a, f"instrument set {','.join(want) or '(none)'} --market {m}", "applied")
    save(cfg)
    for sym in want:
        probe = os.path.join(ROOT, "data", "live", DATA_DIR[m], f"ohlcv.{sym}.15m.json")
        if not os.path.exists(probe):
            print(f"  NOTE: no data on disk for {sym} yet ({rel(probe)}). The flag is set; the source is not wired.")
    if not want:
        print(f"  NOTE: {m} has no instruments selected -- no NEW entries will be opened there. Positions and "
              f"pending orders already open are still managed (strategy-runner.py:766-767).")
    show(cfg, True)
    return 0


def cmd_allows(a):
    if a.layer == "master":
        # CFG-03: this form must fail closed. `allows()` treats "config does not exist" as unconfigured =>
        # allowed, which is right for scanner/local_read/pilot (pure read paths, no behaviour change on a
        # clean checkout) but wrong for the one gate an unattended cron trusts to permit a write: a missing
        # or corrupt config must read as "not permitted", not as "no policy".
        cfg, exists, _ = load(require_readable=False)
        return 0 if (exists and cfg.get("enabled", True)) else 2
    ok, reason = allows(a.layer, getattr(a, "style", None))
    if not ok:
        print(reason)
    return 0 if ok else 2


# ---------- pilot ----------
def _refuse(cfg, a, action, msg):
    record(cfg, a, action, "refused")
    save(cfg)
    print("REFUSED: " + msg, file=sys.stderr)
    show(cfg, True)
    return 2


def pilot_start(a, cfg=None, embedded=False):
    """Start scripts/pilot-loop.sh detached. Returns (rc, note). Every refusal is a hard stop -- this function
    never 'fixes' a blocker for you (it will not remove a STOP file, will not enable a layer)."""
    own = cfg is None
    if own:
        cfg, _, _ = load(require_readable=True)
    # Default to the one venue there is, read from the registry rather than written out again. This used to
    # fall back to the literal "spot"; when PILOT_MARKETS narrowed to futures and PILOT_LABEL lost its spot key
    # (2026-09-13) that turned the plain `pilot start` into an uncaught KeyError at PILOT_LABEL[market].
    market = getattr(a, "market", None) or PILOT_MARKETS[0]
    action = f"pilot start --market {market}"
    if not cfg["enabled"]:
        return 2, "master switch is OFF -- run `/automation demo` (or `on`) first. Nothing was started."
    if not cfg["layers"]["pilot"]:
        return 2, "layers.pilot is off -- `/automation layer pilot on` first. Nothing was started."
    if not cfg["markets"]["crypto"]["enabled"]:
        return 2, ("markets.crypto is off and the pilot only trades the crypto `execution` list "
                   f"({', '.join(instruments.execution('crypto'))}) -- "
                   "`/automation market crypto on` first. Nothing was started.")
    envname = cfg["execution"].get("environment", "demo")
    # One venue, one key pair. The branch here used to pick the deleted market's keys; picking those for a
    # futures order path would sign against the wrong API.
    keys = ("BINANCE_FUTURES_API_KEY", "BINANCE_FUTURES_SECRET_KEY")
    ok, missing, cnote = trading_env.completeness(envname, keys)
    if not ok:
        return 2, (f"environment '{envname}' is incomplete ({cnote}). Fill config/env.{envname} first. "
                   f"Nothing was started.")
    sp = stop_path(market)
    if os.path.exists(sp):
        return 2, (f"kill switch present: {rel(sp)}. The loop would exit on its first tick. Removing it is YOUR "
                   f"action, never mine:\n    rm {rel(sp)}\n  Nothing was started.")
    pp = cfg.get("pilot_process")
    if pp and pp.get("pid") and alive(pp["pid"]) and not pp.get("stopped_at"):
        return 2, (f"a pilot loop is already recorded and alive: pid {pp['pid']} ({pp.get('market')}), started "
                   f"{pp.get('started_at')}. Nothing was started.")
    others = [(p, m) for p, m in running_pilots() if not (pp and pp.get("pid") == p)]
    if others:
        lst = ", ".join(f"pid {p} ({m})" for p, m in others)
        return 2, (f"a pilot loop is ALREADY RUNNING but is not recorded in this config: {lst}. It was started "
                   f"outside /automation (a human terminal, most likely). Starting a second loop would double-trade "
                   f"the same TESTNET account. Adopt it instead:\n"
                   f"    python3 scripts/automation.py pilot adopt --market {others[0][1]}\n"
                   f"  Nothing was started.")
    d = pilot_dir(market)
    os.makedirs(d, exist_ok=True)
    lp = log_path(market)
    use_launchd = not getattr(a, "no_launchd", False) and not dryrun() and (WIN or shutil.which("launchctl"))
    if use_launchd:
        ok, note = _install_agent(PILOT_LABEL[market], PLIST_SRC["pilot"], {"PILOT_END": "never"})
        if not ok:
            return 2, note + " Nothing was started."
        cfg.setdefault("services", {"scanner_agent": False, "pilot_agents": [], "keepawake_pid": None})
        if PILOT_LABEL[market] not in cfg["services"]["pilot_agents"]:
            cfg["services"]["pilot_agents"].append(PILOT_LABEL[market])
        cfg["pilot_process"] = {"pid": 0, "market": market, "started_at": now(), "started_by": actor(a),
                                "log": rel(lp), "launchd_label": PILOT_LABEL[market]}
        record(cfg, a, action, "applied")
        if own:
            save(cfg)
        return 0, (f"pilot [{market}] {note}; environment {envname.upper()}; log {rel(lp)}\n"
                   f"  kill switch: {rel(sp)} (or `/automation pilot stop`). launchd KeepAlive restarts the loop "
                   f"after a crash and at login while the agent stays installed; `/automation off` removes it.")
    env = dict(os.environ, PILOT_MARKET=market, PILOT_END="never")
    cmd = [sys.executable, "-c", "import time; time.sleep(30)"] if dryrun() \
        else ["bash", os.path.join(ROOT, "scripts", "pilot-loop.sh")]
    with open(lp, "a") as lf:
        lf.write(f"--- {'DRY RUN placeholder' if dryrun() else 'pilot loop'} started by "
                 f"scripts/automation.py at {now()} ---\n")
        lf.flush()
        proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
    cfg["pilot_process"] = {"pid": proc.pid, "market": market, "started_at": now(),
                            "started_by": actor(a), "log": rel(lp)}
    if dryrun():
        cfg["pilot_process"]["dry_run"] = True
    record(cfg, a, action, "applied")
    if own:
        save(cfg)
    note = (f"pilot {'DRY RUN placeholder' if dryrun() else 'loop'} started detached (no launchd): pid {proc.pid} "
            f"({market}), environment {envname.upper()}, log {rel(lp)}\n  kill switch: {rel(sp)} "
            f"(create it to stop the loop on its next tick, or run `/automation pilot stop`)")
    return 0, note


def cmd_pilot(a):
    # Mixed read/write: action in {profile, start, stop, adopt} mutates and calls save(); action == "status"
    # (the fallthrough) only reads. Classified as a write path (require_readable=True) because a single load()
    # serves the whole dispatch -- relaxing it here would let a corrupt config's DEFAULTS silently reach the
    # mutating branches (CFG-02). Cost: `pilot status` on a corrupt config now also exits 2 instead of showing
    # defaults; acceptable because `status`/`env`/`allows`/`history` remain the documented always-safe readers.
    cfg, exists, _ = load(require_readable=True)
    market = a.market or (cfg.get("pilot_process") or {}).get("market") or PILOT_MARKETS[0]

    if a.action == "start":
        rc, note = pilot_start(a, cfg)
        if rc != 0:
            return _refuse(cfg, a, f"pilot start --market {a.market or PILOT_MARKETS[0]}", note)
        save(cfg)
        print("  " + note.replace("\n", "\n  "))
        show(cfg, True)
        return 0

    if a.action == "stop":
        svc = cfg.setdefault("services", {"scanner_agent": False, "pilot_agents": [], "keepawake_pid": None})
        for label in list(svc.get("pilot_agents") or []):
            print("  " + _remove_agent(label))
        svc["pilot_agents"] = []
        write_stop()
        pp = cfg.get("pilot_process")
        if pp and not pp.get("stopped_at"):
            pp["stopped_at"] = now()          # kept, not deleted: pilot_process is the audit trail
        record(cfg, a, "pilot stop", "applied")
        save(cfg)
        if dryrun():
            print("  DRY RUN: no kill switch was created and no agent removed.")
        else:
            print("  Any loop still running outside launchd exits on its next tick (<= 15 min). "
                  "`/automation on` or `pilot start` re-arms (they remove the STOP files).")
        show(cfg, True)
        return 0

    if a.action == "adopt":
        found = running_pilots()
        if not found:
            return _refuse(cfg, a, "pilot adopt", "no scripts/pilot-loop.sh process is running -- nothing to adopt.")
        if a.market:
            found = [(p, m) for p, m in found if m == a.market] or found[:1]
        if len(found) > 1:
            return _refuse(cfg, a, "pilot adopt",
                           "more than one pilot loop is running (" +
                           ", ".join(f"pid {p} ({m})" for p, m in found) +
                           ") -- name one with --market futures.")
        pid, mkt = found[0]
        cfg["pilot_process"] = {"pid": pid, "market": a.market or mkt, "started_at": now(),
                                "started_by": "human (adopted)", "log": rel(log_path(a.market or mkt))}
        record(cfg, a, f"pilot adopt pid={pid} market={a.market or mkt}", "applied")
        save(cfg)
        print(f"  adopted the already-running loop: pid {pid} ({a.market or mkt}). started_at is the ADOPTION "
              f"time, not the real start time -- the loop was started outside /automation.")
        show(cfg, True)
        return 0

    # status
    pp = cfg.get("pilot_process")
    print(f"PILOT [{market}]")
    if pp:
        print(f"  recorded:    pid {pp.get('pid')} ({pp.get('market')}) started {pp.get('started_at')} by "
              f"{pp.get('started_by')}{'  [DRY RUN placeholder]' if pp.get('dry_run') else ''}")
        print(f"  pid alive:   {'YES' if alive(pp.get('pid')) else 'no'}"
              + (f"   stopped_at {pp['stopped_at']}" if pp.get("stopped_at") else ""))
    else:
        print("  recorded:    none")
    found = running_pilots()
    print("  processes:   " + (", ".join(f"pid {p} ({m})" +
                                         ("" if pp and pp.get("pid") == p else " [NOT recorded -- `pilot adopt`]")
                                         for p, m in found) or "no scripts/pilot-loop.sh running"))
    for m in PILOT_MARKETS:
        sp = stop_path(m)
        print(f"  STOP [{m}]:  {'PRESENT ' + rel(sp) + ' -- loop exits next tick' if os.path.exists(sp) else 'absent'}")
    lp = log_path(market)
    if os.path.exists(lp):
        try:
            lines = [l.rstrip() for l in open(lp, encoding="utf-8", errors="replace").read().splitlines() if l.strip()]
            print(f"  last log:    {lines[-1] if lines else '(empty)'}   [{rel(lp)}]")
        except OSError as e:
            print(f"  last log:    unreadable ({e})")
    else:
        print(f"  last log:    no {rel(lp)} yet")
    return 0


# ---------- presets ----------
# `demo` and `real` share cmd_preset() above: environment + preset + bring_up().
def cmd_demo(a):
    return cmd_preset(a)
    show(cfg, True)
    return 0


def cmd_history(a):
    cfg, exists, _ = load(require_readable=False)
    if not cfg["history"]:
        print("(no history yet)" if exists else "(no config file yet -- nothing has been changed)")
        return 0
    for h in cfg["history"][-a.n:]:
        print(f"{clean(h.get('ts'))}  {clean(h.get('actor')) or '':<16} {clean(h.get('action')) or '':<40} "
              f"{clean(h.get('result'))}" + (f"  ({clean(h.get('detail'))})" if h.get("detail") else ""))
    return 0


def main():
    class _P(argparse.ArgumentParser):
        """Usage errors must exit 1, not argparse's default 2 -- 2 is reserved here for REFUSED
        (mainnet / off-allowlist symbol / impossible market pair / blocked pilot start), and a caller has to be able to tell a
        typo from a safety refusal."""
        def error(self, message):
            self.print_usage(sys.stderr)
            sys.stderr.write(f"{self.prog}: error: {message}\n")
            raise SystemExit(1)

    ap = _P(description="Automation switch v3. on/off = bring everything up / stop everything; demo|real = environment + preset + on.")
    sub = ap.add_subparsers(dest="cmd", parser_class=_P)

    def audited(p):
        p.add_argument("--who", default=None, help="who is making this change (audit trail)")
        p.add_argument("--reason", default=None, help="why (audit trail)")
        return p

    st = sub.add_parser("status"); st.add_argument("--json", action="store_true")
    sub.add_parser("env")
    al = sub.add_parser("allows"); al.add_argument("layer", choices=LAYERS + ["master"])
    al.add_argument("style", nargs="?", default=None)
    p = audited(sub.add_parser("demo")); p.add_argument("setup", nargs="*", default=[]); p = audited(sub.add_parser("real")); p.add_argument("setup", nargs="*", default=[])
    p = audited(sub.add_parser("on")); p.add_argument("setup", nargs="*", default=[], help="optional: `setup top N` = rank the last 12 months, select N crypto + N CFD setups, then bring everything up")
    audited(sub.add_parser("off"))
    p = audited(sub.add_parser("market"))
    p.add_argument("name", choices=MARKETS); p.add_argument("value", choices=["on", "off"])
    p = audited(sub.add_parser("timeframe"))
    p.add_argument("name", choices=TIMEFRAMES); p.add_argument("value", choices=["on", "off"])
    p.add_argument("--market", choices=MARKETS, default=None)
    p = audited(sub.add_parser("dimension"))
    p.add_argument("name", choices=DIMENSIONS); p.add_argument("value", choices=["on", "off"])
    p.add_argument("--market", choices=MARKETS, default=None)
    p = audited(sub.add_parser("method"))
    p.add_argument("preset", choices=[x["id"] for x in methods.PRESETS])
    p.add_argument("--market", choices=MARKETS, default=None)
    p = audited(sub.add_parser("instrument"))
    p.add_argument("symbol", help="a SYMBOL, or the literal word 'set'")
    p.add_argument("value", help="on|off for a single symbol; the comma-separated list when symbol is 'set'")
    p.add_argument("--market", choices=MARKETS)
    p = audited(sub.add_parser("layer"))
    p.add_argument("name", choices=LAYERS); p.add_argument("value", choices=["on", "off"])
    p = audited(sub.add_parser("pilot"))
    # `profile` was removed with the second engine (2026-09-13): one engine means a profile can only select
    # "the engine" or "nothing", and layers.pilot already expresses the second. Dropped from `choices` as well
    # as from the handler -- leaving it accepted made `pilot profile top20` exit 0 and print the status block,
    # so a user who typed it would believe they had changed something.
    p.add_argument("action", choices=["start", "stop", "status", "adopt"])
    p.add_argument("--market", choices=PILOT_MARKETS, default=None)
    p.add_argument("--no-launchd", action="store_true", help="start detached from this shell instead of as a launchd agent")
    h = sub.add_parser("history"); h.add_argument("-n", type=int, default=20)

    a = ap.parse_args()
    if a.cmd is None:
        a.cmd = "status"; a.json = False       # no args = status, per .claude/commands/automation.md

    # v1/v2 -> v3 migration, once, in place, with an audit row. Done here (not in load()) so that a reader such as
    # scan-loop.sh never writes this file as a side effect of gating a pass. require_readable=False: this is a
    # pre-dispatch probe shared by every subcommand including read-only ones (status/env/allows/history), so it
    # must never exit 2 on a corrupt file -- migrated can only be True for a file that parsed (v1/v2), so this
    # relaxation never weakens CFG-02 for the actual migration write below. Write subcommands re-load with their
    # own require_readable=True call and refuse independently.
    cfg, exists, migrated = load(require_readable=False)
    if migrated and exists and a.cmd not in ("allows",):
        record(cfg, a, f"migrate schema_version -> {SCHEMA_VERSION}", "applied")
        save(cfg)
        print(f"# migrated {rel(CONFIG)} to schema_version {SCHEMA_VERSION} "
              f"(execution.account -> execution.environment, services added); recorded in history[].")

    if a.cmd == "status":
        cfg, exists, _ = load(require_readable=False); show(cfg, exists, a.json); return 0
    if a.cmd == "env":
        return cmd_env(a)
    if a.cmd == "allows":
        return cmd_allows(a)
    if a.cmd in ("on", "off"):
        return cmd_master(a)
    if a.cmd in ("demo", "real"):
        return cmd_preset(a)
    if a.cmd == "market":
        return cmd_market(a)
    if a.cmd == "timeframe":
        return cmd_timeframe(a)
    if a.cmd == "dimension":
        return cmd_dimension(a)
    if a.cmd == "method":
        return cmd_method(a)
    if a.cmd == "layer":
        return cmd_layer(a)
    if a.cmd == "instrument":
        if a.symbol == "set":
            if not a.market:
                print("usage: instrument set <SYM,SYM,...> --market <crypto|cfd>", file=sys.stderr)
                return 1
            a.symbols = a.value
            return cmd_instrument_set(a)
        if a.value not in ("on", "off"):
            print(f"usage: instrument <SYMBOL> on|off  (got value={a.value!r})", file=sys.stderr)
            return 1
        return cmd_instrument(a)
    if a.cmd == "pilot":
        return cmd_pilot(a)
    if a.cmd == "history":
        return cmd_history(a)
    return 1


if __name__ == "__main__":
    sys.exit(main())
