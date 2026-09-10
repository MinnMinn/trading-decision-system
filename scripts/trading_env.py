#!/usr/bin/env python3
"""Trading environment loader (python). Mirror of scripts/trading-env.sh -- keep the two in sync.

    from trading_env import load_env, active_env_name
    env = load_env()                     # dict of the ACTIVE environment (demo | real), secrets resolved
    env = load_env(require=["BINANCE_SPOT_API_KEY", "BINANCE_SPOT_SECRET_KEY"])   # raises EnvIncomplete

active environment = docs/architecture/automation-config.json -> execution.environment, overridable by the
TRADING_ENV environment variable. File = config/env.<name> (template config/env.example).
Secret values "keychain:<service>[@<account>]" are resolved via scripts/get-secret.sh (macOS Keychain).
Values are returned in a dict and never printed by this module.
PILOT_RISK_PCT is clamped to <= 0.01 (hard rule: max 1% per trade) whatever the file says.
"""
import json, os, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "docs", "architecture", "automation-config.json")
GET_SECRET = os.path.join(ROOT, "scripts", "get-secret.sh")
ENV_NAMES = ("demo", "real")
PLACEHOLDER = "__FILL_ME__"
SECRET_SUFFIXES = ("_KEY", "_SECRET_KEY", "_PASSWORD")
MAX_RISK_PCT = 0.01
REQUIRED_URLS = ("BINANCE_SPOT_BASE_URL", "BINANCE_FUTURES_BASE_URL")


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
    cmd = [GET_SECRET, svc] + ([acct] if acct else [])
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
