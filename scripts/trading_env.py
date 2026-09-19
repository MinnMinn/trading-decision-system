#!/usr/bin/env python3
"""Trading environment loader (python). Mirror of scripts/trading-env.sh -- keep the two in sync.

    from trading_env import load_env, active_env_name
    env = load_env()                     # dict of the ACTIVE environment (demo | real), secrets resolved
    env = load_env(require=["BINANCE_SPOT_API_KEY", "BINANCE_SPOT_SECRET_KEY"])   # raises EnvIncomplete

active environment = docs/architecture/automation-config.json -> execution.environment, overridable by the
TRADING_ENV environment variable. File = config/env.<name> (template config/env.example).
Secret values "keychain:<service>[@<account>]" are resolved via scripts/get_secret.py (the OS's own
credential store: macOS Keychain, Windows Credential Manager, libsecret on Linux).
Values are returned in a dict and never printed by this module.
PILOT_RISK_PCT is clamped to <= MAX_RISK_PCT whatever the file says. MAX_RISK_PCT is read once, here, from
docs/architecture/risk-config.json -- strategy-runner.RISK_CEILING and scripts/trading-env.sh both read it from
this module rather than keeping a copy of the number.
"""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "docs", "architecture", "automation-config.json")
# The ONE secret reader. Was scripts/get-secret.sh (macOS `security`); now a Python reader that answers
# the same question on macOS, Windows and Linux, because the platform moves to Windows and
# `security` does not exist there (docs/plans/2026-09-20-windows-migration.md §2). The reference
# syntax CLAUDE.md declares -- keychain:<service>[@<account>] -- is unchanged, so no env file, no
# registry and no caller moves.
GET_SECRET = os.path.join(ROOT, "scripts", "get_secret.py")
ENV_NAMES = ("demo", "real")
PLACEHOLDER = "__FILL_ME__"
SECRET_SUFFIXES = ("_KEY", "_SECRET_KEY", "_PASSWORD")
REQUIRED_URLS = ("BINANCE_SPOT_BASE_URL", "BINANCE_FUTURES_BASE_URL")
ANALYSIS_PARAMS = os.path.join(ROOT, "docs", "architecture", "analysis-params.json")
RISK_CONFIG = os.path.join(ROOT, "docs", "architecture", "risk-config.json")


def _read_max_risk_pct(path=None):
    """The per-trade risk ceiling, validated. Raises on anything it cannot trust.

    Unified at 1 % by user decision 2026-09-17. Until then this module held the literal 0.03 while
    risk-config.json, risk-skill/SKILL.md and risk-agent.md all said 0.01 -- so the automated pilot path sized
    at three times the ceiling the manual /execute path enforced, and the SessionStart hook announced 3 % to
    every session. Two paths, two numbers, no reader in common: the fourth instance of that shape in this repo
    (the planned-R:R floor, the ceiling in trading-env.sh, style-keyed runtime state). The fix is the same one
    min_rr() already uses -- the number is authored in JSON, exactly one reader validates it, and an unreadable
    value refuses rather than guessing.

    RAISES rather than returning None, unlike min_rr(). MAX_RISK_PCT is consumed as a module constant, so a
    None would reach `min(v, None)` as a TypeError deep inside a sizing call, and the shell twin
    (scripts/trading-env.sh) would print the string "None", sail past its own `-z` guard and export an empty
    PILOT_RISK_PCT. Raising here makes both callers fail closed: the Python importer stops, and the shell's
    `python3 -c` exits nonzero with empty stdout, which is exactly what its guard already checks for.

    Rejects bool, non-numbers, NaN, <= 0, and > 1 -- a risk FRACTION above 1.0 would mean over 100 % of equity
    per trade and is far more likely to be `3` typed for "3 %" than a real instruction."""
    try:
        v = json.load(open(path or RISK_CONFIG, encoding="utf-8"))["max_risk_pct"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise RuntimeError(f"cannot read max_risk_pct from {path or RISK_CONFIG} ({e}) -- refusing to assume a "
                           f"per-trade risk ceiling. A guessed ceiling is a position size nobody decided.") from e
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or not (0 < v <= 1):
        raise RuntimeError(f"max_risk_pct in {path or RISK_CONFIG} is {v!r}, not a fraction in (0, 1] -- refusing. "
                           f"Express the ceiling as a FRACTION of equity, never as a percentage number.")
    return float(v)


# The ONE per-trade risk ceiling. The clamp exists in two layers (here on the file value, again in
# strategy-runner) but the NUMBER must not: strategy-runner.RISK_CEILING and scripts/trading-env.sh both read
# it from here. Authored in docs/architecture/risk-config.json; twin of min_rr() below.
# Evidence for the floor it is paired with: docs/backtests/2026-09-13-rr-floor-and-risk.md.
MAX_RISK_PCT = _read_max_risk_pct()


def min_rr(path=None):
    """The planned-R:R floor, validated. Returns the float, or None if it cannot be trusted.

    Lives here because this module is the thing the live order path already imports -- strategy-runner.py (via
    backtest-methods) -- so the floor gets one reader and one validation instead of a per-file copy. It is the
    twin of MAX_RISK_PCT above: same decision, same single-definition rule.

    Returns None (never a fallback number) on: unreadable/absent file, bad JSON, missing key, and any value that
    is not a positive real float -- bool, string, 0, negative and NaN all rejected. Callers MUST treat None as
    "refuse", not as "no floor": security review 2026-09-13 (F1) found backtest-methods defaulting to 2.0 here,
    which would have let the runner silently trade the superseded 2R floor at the 3 % risk ceiling if the key
    were ever dropped -- the one combination docs/backtests/2026-09-13-rr-floor-and-risk.md rules out."""
    try:
        v = json.load(open(path or ANALYSIS_PARAMS, encoding="utf-8"))["project_defined"]["ict"]["min_rr"]["value"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v <= 0:
        return None
    return float(v)


class EnvIncomplete(RuntimeError):
    """A required value is missing or still a placeholder. Every execution path treats this as exit 2."""


def active_env_name():
    n = os.environ.get("TRADING_ENV")
    if n:
        return n
    try:
        c = json.load(open(CONFIG, encoding="utf-8"))
        return (c.get("execution") or {}).get("environment") or "demo"
    except Exception:
        return "demo"


def env_file(name=None):
    return os.path.join(ROOT, "config", f"env.{name or active_env_name()}")


def _resolve(value):
    if not value.startswith("keychain:"):
        return value
    ref = value[len("keychain:"):]
    svc, _, acct = ref.partition("@")
    # Invoked through sys.executable, not by shebang: Windows does not honour `#!` lines, and the platform
    # is moving there (docs/plans/2026-09-20-windows-migration.md). Same reason the reader itself is Python.
    cmd = [sys.executable, GET_SECRET, svc] + ([acct] if acct else [])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except Exception:
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def parse_env_file(path, resolve_secrets=True):
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if not key or not all(ch.isalnum() or ch == "_" for ch in key) or not key.isupper():
                continue
            val = val.strip()
            if resolve_secrets and key.endswith(SECRET_SUFFIXES):
                val = _resolve(val)
            out[key] = val
    return out


def load_env(require=(), name=None, resolve_secrets=True):
    name = name or active_env_name()
    path = env_file(name)
    if not os.path.exists(path):
        raise EnvIncomplete(f"environment '{name}' has no file at config/env.{name} (copy config/env.example)")
    env = parse_env_file(path, resolve_secrets=resolve_secrets)
    env.setdefault("TRADING_ENV_NAME", name)
    env["TRADING_ENV_ACTIVE"] = name
    for k in REQUIRED_URLS:
        if not env.get(k):
            raise EnvIncomplete(f"{k} missing in config/env.{name}")
    missing = [k for k in require if not env.get(k) or env.get(k) == PLACEHOLDER]
    if missing:
        raise EnvIncomplete(f"environment '{name}' incomplete -- not set in config/env.{name}: " + ", ".join(missing))
    try:
        env["PILOT_RISK_PCT"] = str(min(float(env.get("PILOT_RISK_PCT", "0.005")), MAX_RISK_PCT))
    except ValueError:
        env["PILOT_RISK_PCT"] = "0.005"
    return env


def completeness(name=None, keys=("BINANCE_SPOT_API_KEY", "BINANCE_SPOT_SECRET_KEY")):
    """(ok, missing_keys, note) for status displays -- resolves nothing, prints nothing secret."""
    name = name or active_env_name()
    path = env_file(name)
    if not os.path.exists(path):
        return False, list(keys), f"config/env.{name} does not exist"
    raw = parse_env_file(path, resolve_secrets=False)
    missing = [k for k in keys if not raw.get(k) or raw.get(k) == PLACEHOLDER]
    return (not missing), missing, ("complete" if not missing else "placeholders remain: " + ", ".join(missing))


def is_real(name=None):
    return (name or active_env_name()) == "real"


if __name__ == "__main__":   # `python3 scripts/trading_env.py` -> prints the active environment NAME only
    ok, missing, note = completeness()
    print(f"active environment: {active_env_name()}  file: config/env.{active_env_name()}  spot keys: {note}")
