#!/usr/bin/env python3
"""One forward cycle, the ONE command the scheduler runs every 5 minutes (Windows Task Scheduler / macOS launchd):

    python scripts/forward_cycle.py

1. `scripts/mt5_time.py sync`                     MT5 server time -> UTC for the live bridge files
2. `fvg_forward.py accumulate`                    live 5m bars -> rolling store (no manual history re-export needed)
3. `fvg_forward.py scan` + `resolve`              forward PAPER record of every watched component
4. `fvg_demo.py tick`                             DEMO orders (no-op unless docs/architecture/fvg-demo.json enabled=true)

A lock file prevents two cycles overlapping (a lock older than 15 minutes is taken over). Every step's outcome goes to
data/live/forward/cycle.log; a failing step is logged and the later steps still run (a sync failure must not stop exits)."""
import datetime
import importlib.util
import os
import subprocess
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FWD = os.path.join(ROOT, "data", "live", "forward")
LOCK = os.path.join(FWD, "cycle.lock")
CYCLE_LOG = os.path.join(FWD, "cycle.log")
STALE_LOCK = datetime.timedelta(minutes=15)


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _log(msg):
    os.makedirs(FWD, exist_ok=True)
    with open(CYCLE_LOG, "a", encoding="utf-8") as fh:
        fh.write(f"{_now().strftime('%Y-%m-%dT%H:%M:%SZ')} {msg}\n")


def _lock():
    os.makedirs(FWD, exist_ok=True)
    if os.path.exists(LOCK):
        age = _now() - datetime.datetime.fromtimestamp(os.path.getmtime(LOCK), datetime.timezone.utc)
        if age < STALE_LOCK:
            return False
        _log(f"taking over a stale lock ({age})")
        os.remove(LOCK)
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False


def _mod(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _step(name, fn):
    try:
        out = fn()
        _log(f"OK   {name}: {out!r}"[:500])
    except SystemExit as e:
        _log(f"EXIT {name}: {e}")
    except Exception:
        _log(f"FAIL {name}: " + traceback.format_exc().replace("\n", " | ")[:1500])


def main():
    if not _lock():
        _log("skipped: another cycle holds the lock")
        return 0
    try:
        _step("mt5_time sync", lambda: subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "mt5_time.py"), "sync"],
                                                       capture_output=True, text=True, timeout=120).returncode)
        ff = _mod("fvg_forward", "scripts/research/fvg_forward.py")
        _step("accumulate", ff.cmd_accumulate)
        _step("scan", lambda: len(ff.cmd_scan()))
        _step("resolve", ff.cmd_resolve)
        fd = _mod("fvg_demo", "scripts/fvg_demo.py")
        _step("demo tick", fd.tick)
    finally:
        try:
            os.remove(LOCK)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
