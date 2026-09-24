#!/usr/bin/env python3
"""Windows backend for the process layer of `/automation` -- the launchd / caffeinate / pgrep equivalents.

docs/plans/2026-09-20-windows-migration.md step 11: "Task Scheduler thay launchd". scripts/automation.py keeps
the decisions (what to install, when to refuse, which STOP file); this module only answers the OS questions it
used to ask launchctl, caffeinate and pgrep. Nothing here decides trading behaviour.

    pythonw scripts/win_services.py scanner      one scanner pass (scheduled every minute)
    pythonw scripts/win_services.py pilot        keep-alive: start scripts/pilot-loop.sh unless one is running
    pythonw scripts/win_services.py keepawake    hold the machine awake until killed

Why pythonw + a scheduled task, not a Windows service: a per-user scheduled task needs no admin rights and
runs in the user's session (where MT5 and the Credential Manager entries live), and pythonw has no console,
so a once-a-minute task does not flash a window. The bash children get CREATE_NO_WINDOW: a hidden console
they and every python3 they spawn inherit.

KeepAlive semantics (launchd KeepAlive=true for the pilot): the pilot task fires at logon and every 5 minutes;
each firing starts a loop ONLY if none is running and no STOP file exists -- never a second loop, because a
second loop double-trades the same account (automation.py running_pilots()).
"""
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASK_FOLDER = "\\TradingDecisionSystem\\"
CREATE_NO_WINDOW = 0x08000000
DETACHED = 0x00000008 | 0x00000200          # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
PILOT_DIR = os.path.join(ROOT, "data", "live", "pilot-futures")
# The Windows command line of a pilot loop, however it was started (Task Scheduler, Git Bash, automation.py).
PILOT_CMD_RE = re.compile(r"bash(\.exe)?\"?\s+\S*scripts[/\\]pilot-loop\.sh(\s|$)|"
                          r"python3?(w)?(\.exe)?\"?\s+\S*scripts[/\\]strategy-runner\.py\s.*--live", re.I)


def bash_exe():
    """Git Bash, never WSL's System32\\bash.exe (a different filesystem and a different python3)."""
    for p in (os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Git", "bin", "bash.exe"),
              os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Git", "bin", "bash.exe")):
        if os.path.exists(p):
            return p
    w = shutil.which("bash")
    if w and "system32" not in w.lower():
        return w
    raise RuntimeError("Git Bash not found -- install Git for Windows (the loops are bash scripts)")


def pythonw_exe():
    w = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return w if os.path.exists(w) else sys.executable


# ---------------------------------------------------------------------------------------------- processes
def alive(pid):
    """Probe without side effects. NEVER os.kill(pid, 0) on Windows: there any signal other than CTRL_* is
    TerminateProcess, so the 'is it alive?' check would kill the pilot loop it was asking about."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    h = k32.OpenProcess(0x1000, False, pid)            # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = ctypes.c_ulong()
        if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
            return False
        return code.value == 259                        # STILL_ACTIVE
    finally:
        k32.CloseHandle(h)


def processes():
    """[(pid, ppid, commandline)] for every process of this user, via CIM (no third-party package)."""
    ps = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine } | "
          "Select-Object ProcessId,ParentProcessId,CommandLine | ConvertTo-Json -Compress")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True,
                           text=True, timeout=60, creationflags=CREATE_NO_WINDOW)
        rows = json.loads(r.stdout or "[]")
    except Exception:
        return None                                     # unknown, NOT "none running" -- callers must not fail open
    rows = rows if isinstance(rows, list) else [rows]
    return [(int(x["ProcessId"]), int(x["ParentProcessId"]), x["CommandLine"]) for x in rows]


def pilot_pids():
    """Top-level pilot loops only: Git's bin\\bash.exe re-executes usr\\bin\\bash.exe, and strategy-runner.py
    runs as a child of the loop -- neither child is a second loop. None = could not tell."""
    procs = processes()
    if procs is None:
        return None
    me = {os.getpid(), os.getppid()}
    hits = {pid: ppid for pid, ppid, cmd in procs if PILOT_CMD_RE.search(cmd) and pid not in me}
    return sorted(pid for pid, ppid in hits.items() if ppid not in hits)


def kill_tree(pid):
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(int(pid))], capture_output=True,
                   creationflags=CREATE_NO_WINDOW)


def spawn_detached(argv, log_path=None, env=None):
    out = open(log_path, "a") if log_path else subprocess.DEVNULL
    try:
        p = subprocess.Popen(argv, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=out,
                             stderr=subprocess.STDOUT, creationflags=DETACHED | CREATE_NO_WINDOW)
    finally:
        if log_path:
            out.close()
    return p.pid


# ------------------------------------------------------------------------------------------ task scheduler
def _schtasks(*args):
    try:
        r = subprocess.run(["schtasks", *args], capture_output=True, text=True, timeout=60,
                           creationflags=CREATE_NO_WINDOW)
    except Exception as e:
        return 1, str(e)
    return r.returncode, (r.stdout + r.stderr).strip()


def task_name(label):
    return TASK_FOLDER + label


def task_loaded(label):
    return _schtasks("/Query", "/TN", task_name(label))[0] == 0


def install_task(label, role):
    """role 'scanner' -> every minute; 'pilot' -> at logon + every 5 minutes (keep-alive). Returns (ok, note)."""
    action = f'"{pythonw_exe()}" "{os.path.join(ROOT, "scripts", "win_services.py")}" {role}'
    if len(action) > 261:
        return False, f"task action longer than schtasks' 261-char limit: {action}"
    name = task_name(label)
    if role == "scanner":
        rc, out = _schtasks("/Create", "/F", "/TN", name, "/TR", action, "/SC", "MINUTE", "/MO", "1")
    else:
        rc, out = _schtasks("/Create", "/F", "/TN", name, "/TR", action, "/SC", "MINUTE", "/MO", "5")
        if rc == 0:                                     # plus at logon, like launchd RunAtLoad
            _schtasks("/Create", "/F", "/TN", name + "-logon", "/TR", action, "/SC", "ONLOGON")
    if rc != 0:
        return False, f"schtasks /Create failed for {name}: {out}"
    _schtasks("/Run", "/TN", name)                      # RunAtLoad: start now, not in a minute
    return True, f"installed + started scheduled task {name}"


def remove_task(label, role):
    name = task_name(label)
    for n in (name, name + "-logon"):
        _schtasks("/Delete", "/F", "/TN", n)
    note = f"scheduled task {name} removed"
    if role == "pilot":                                 # launchd bootout terminates the loop; so does this
        pids = pilot_pids() or []
        for pid in pids:
            kill_tree(pid)
        if pids:
            note += f"; pilot loop(s) stopped: {', '.join(map(str, pids))}"
    return note


# ------------------------------------------------------------------------------------------------ roles
def _child_env(**extra):
    """UTF-8 mode for every python3 the loops start: bare open() is cp1252 on Windows and the scripts write
    Vietnamese text (ict-scan.py failed on every style without it)."""
    return dict(os.environ, PYTHONUTF8="1", **extra)


def run_scanner():
    subprocess.run([bash_exe(), "scripts/scan-loop.sh"], cwd=ROOT, stdin=subprocess.DEVNULL, env=_child_env(),
                   stdout=open(os.path.join(ROOT, "data", "live", "scan-loop.out"), "a"),
                   stderr=open(os.path.join(ROOT, "data", "live", "scan-loop.err"), "a"),
                   creationflags=CREATE_NO_WINDOW)


def run_pilot_keepalive():
    os.makedirs(PILOT_DIR, exist_ok=True)
    log = os.path.join(PILOT_DIR, "loop.log")
    if os.path.exists(os.path.join(PILOT_DIR, "STOP")):
        return                                          # the kill switch wins; the loop would exit anyway
    running = pilot_pids()
    if running is None or running:
        return                                          # one loop only; unknown counts as running
    with open(log, "a") as f:
        f.write(f"--- pilot loop started by Task Scheduler keep-alive at "
                f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} ---\n")
    spawn_detached([bash_exe(), "scripts/pilot-loop.sh"], log_path=log,
                   env=_child_env(PILOT_END="never"))


def run_keepawake():
    """caffeinate -dims: keep the system awake while this process lives (display may sleep)."""
    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
    k32 = ctypes.WinDLL("kernel32")
    while True:
        k32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        time.sleep(300)


def start_keepawake():
    return spawn_detached([pythonw_exe(), os.path.join(ROOT, "scripts", "win_services.py"), "keepawake"])


if __name__ == "__main__":
    role = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = {"scanner": run_scanner, "pilot": run_pilot_keepalive, "keepawake": run_keepawake}.get(role)
    if fn is None:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        sys.exit(1)
    fn()
