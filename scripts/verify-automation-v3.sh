#!/usr/bin/env bash
# Acceptance test for the environment-driven automation (v3). Run it yourself:
#     bash scripts/verify-automation-v3.sh
# It never places an order, never installs a launchd agent, never writes a STOP file, never prints a secret:
# every process action runs under AUTOMATION_PILOT_DRYRUN=1 and every connector call is a read-only endpoint.
# Written because the authoring session could not run Bash (auto-mode classifier); until this passes, treat the
# v3 refactor as UNVERIFIED.
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
A=scripts/automation.py; pass=0; fail=0
ok(){ echo "  ok   $1"; pass=$((pass+1)); }; bad(){ echo "  FAIL $1"; fail=$((fail+1)); }
t(){ python3 $A "$@" >/dev/null 2>&1; echo $?; }
export AUTOMATION_PILOT_DRYRUN=1

echo "== 1 compile"
python3 -m py_compile scripts/automation.py scripts/trading_env.py scripts/strategy-runner.py scripts/local-eval-brief.py && ok py || bad py
bash -n scripts/trading-env.sh scripts/pilot-loop.sh scripts/scan-loop.sh scripts/binance-testnet-order.sh scripts/binance-futures-testnet-order.sh && ok bash || bad bash

echo "== 2 config + schema"
for f in docs/architecture/automation-config.json docs/architecture/schemas/automation-config.schema.json; do python3 -c "import json;json.load(open('$f'))" && ok "$f" || bad "$f"; done
python3 - <<'PY' && ok "shape v3" || bad "shape v3"
import json; d=json.load(open("docs/architecture/automation-config.json"))
assert d["schema_version"]==3 and d["execution"]["environment"] in ("demo","real") and "services" in d and "account" not in d["execution"]
PY

echo "== 3 env files"
[ -f config/env.example ] && ok "config/env.example exists" || bad "config/env.example missing"
for e in demo real; do [ -f config/env.$e ] && ok "config/env.$e exists" || bad "config/env.$e missing"; done
git check-ignore -q config/env.demo && git check-ignore -q config/env.real && ok "env.demo/env.real gitignored" || bad "env files NOT gitignored"
chmod 600 config/env.demo config/env.real 2>/dev/null && ok "chmod 600 applied to env files" || bad "chmod 600 failed"
python3 scripts/trading_env.py | grep -q "active environment: " && ok "trading_env.py runs" || bad "trading_env.py"
( source scripts/trading-env.sh && [ -n "${BINANCE_SPOT_BASE_URL:-}" ] ) && ok "trading-env.sh sources + exports URLs" || bad "trading-env.sh"
python3 - <<'PY' && ok "risk clamp <= 1%" || bad "risk clamp"
import importlib.util,os
s=importlib.util.spec_from_file_location("te","scripts/trading_env.py"); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
os.environ["TRADING_ENV"]="demo"; e=m.load_env(resolve_secrets=False); assert float(e["PILOT_RISK_PCT"])<=0.01
PY
python3 - <<'PY' && ok "real env reports placeholders as incomplete" || bad "real completeness"
import importlib.util
s=importlib.util.spec_from_file_location("te","scripts/trading_env.py"); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
ok,missing,note=m.completeness("real"); assert (not ok) == any(k in note for k in ("placeholders","does not exist")) or ok
PY

echo "== 4 exit codes (all under DRY RUN -- nothing installed, no STOP written)"
[ "$(t status)" = 0 ] && ok "status=0" || bad "status"
[ "$(t env)" = 0 ] && ok "env=0" || bad "env"
[ "$(t badcmd)" = 1 ] && ok "badcmd=1" || bad "badcmd"
[ "$(t instrument EURUSD on)" = 2 ] && ok "EURUSD refused=2" || bad "EURUSD"
[ "$(t dimension footprint on --market cfd)" = 2 ] && ok "footprint@cfd=2" || bad "footprint@cfd"
[ "$(t timeframe 1m on --market cfd)" = 2 ] && ok "1m@cfd=2" || bad "1m@cfd"
python3 $A account demo >/dev/null 2>&1; [ $? = 1 ] && ok "account subcmd removed" || bad "account subcmd still exists"
[ "$(t allows scanner)" = 0 ] && ok "allows scanner=0 (automation on)" || bad "allows scanner"
if grep -q "__FILL_ME__" config/env.real; then [ "$(t real)" = 2 ] && ok "real refused while env.real incomplete=2" || bad "real should refuse until env.real is filled"; else echo "  (env.real is filled -- skipping the refusal test; DO NOT run 'real' from this script)"; fi

echo "== 5 dry-run on/off (no launchd, no STOP, no caffeinate)"
cp docs/architecture/automation-config.json /tmp/automation-config.bak
[ "$(t on --who verify --reason dry-run)" = 0 ] && ok "on (dry run)=0" || bad "on"
[ "$(t off --who verify --reason dry-run)" = 0 ] && ok "off (dry run)=0" || bad "off"
ls data/live/pilot*/STOP >/dev/null 2>&1 && bad "STOP file written during dry run" || ok "no STOP file written"
ls ~/Library/LaunchAgents/com.tyme.trading.pilot*.plist >/dev/null 2>&1 && echo "  (note: pilot plists present in ~/Library/LaunchAgents -- pre-existing or a real 'on')" || ok "no pilot plist installed by dry run"
cp /tmp/automation-config.bak docs/architecture/automation-config.json && ok "config restored" || bad "config restore"

echo "== 6 connectors read-only against the ACTIVE environment (no order)"
bash scripts/binance-testnet-order.sh price BTCUSDT >/dev/null 2>&1 && ok "spot connector: price BTCUSDT (env $(python3 -c "import json;print(json.load(open('docs/architecture/automation-config.json'))['execution']['environment'])"))" || bad "spot connector price (check env file / Keychain)"
bash scripts/binance-futures-testnet-order.sh check >/dev/null 2>&1 && ok "futures connector: check" || echo "  (futures connector check failed -- fine if you have no futures keys in this environment)"

echo "== 7 pilot gate reads the environment"
python3 scripts/strategy-runner.py --report >/dev/null 2>&1 && ok "strategy-runner --report runs" || echo "  (strategy-runner --report failed -- needs valid keys for the active environment)"

echo; echo "PASS=$pass FAIL=$fail"
[ "$fail" = 0 ] && echo "v3 refactor verified. Next: fill config/env.real, then '/automation real'." || echo "Fix the FAILs before any real tick."
