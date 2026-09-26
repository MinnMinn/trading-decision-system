"""End-to-end local test of stage H1 (never touches Bookmap, never records real market data).

    python integrations/bookmap/test/run_e2e.py [--log D:/tmp-tests/h1-e2e.log]

1. Checks the built jar (integrations/bookmap/dist/) equals the committed pin.
2. Creates a throw-away holdout pre-registration in a temp git repo (committed, as the recorder requires).
3. Starts the REAL recorder (scripts/bookmap_recorder.py) on the REAL pipe name with a temp recordings root OUTSIDE
   the worktree, pinned client = the JDK's java.exe (under Program Files, as BMREC-13 requires).
4. Runs E2EHarness: a fake Bookmap host driving the REAL add-on jar (hello with the pinned code/source SHA).
5. Stops the recorder with --stop and verifies: manifest hashes, record counts, book VALID after the checkpoint,
   connection-loss gap, no admin free text anywhere (BMREC-06), stop() bounded (BMREC-17).
Exit 0 only if every check passes.
"""
import datetime as dt
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BM = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(BM))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import bookmap_frames as BF  # noqa: E402
import bookmap_recorder as BRC  # noqa: E402
import bookmap_store as BS  # noqa: E402

JDK = os.environ.get("TDS_JDK_HOME", r"C:\Program Files\Microsoft\jdk-21.0.12.101-hotspot")
LIB = os.environ.get("TDS_BOOKMAP_LIB", r"C:\Program Files\Bookmap\lib")
JAR = os.path.join(BM, "dist", "tds-h1-recorder.jar")
PIN = os.path.join(BM, "addon-pin.json")
MARKER = b"marker-should-never-appear-in-output"


def main():
    log_path = sys.argv[sys.argv.index("--log") + 1] if "--log" in sys.argv else None
    base = os.path.join(os.environ.get("TDS_E2E_BASE", r"D:\tmp-tests"),
                        "h1-e2e-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    os.makedirs(base)
    lines = []

    def log(msg):
        print(msg, flush=True)
        lines.append(msg)

    checks = []

    def check(name, ok, detail=""):
        checks.append(ok)
        log(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))

    try:
        log(f"base dir: {base}")
        with open(PIN, encoding="utf-8") as fh:
            pin = json.load(fh)
        check("built jar equals the committed pin (BMREC-30)", BS.sha256_file(JAR) == pin["jar_sha256"],
              pin["jar_sha256"])
        # 2. pre-registration in a temp git repo
        prereg_repo = os.path.join(base, "prereg-repo")
        os.makedirs(prereg_repo)
        g = ["git", "-C", prereg_repo]
        subprocess.run(g + ["init", "-q"], check=True)
        cal = os.path.join(prereg_repo, "bookmap-holdout-calendar.json")
        BRC.preregister_holdout(cal, seed=12345)
        subprocess.run(g + ["add", "."], check=True)
        subprocess.run(g + ["-c", "user.name=e2e", "-c", "user.email=e2e@invalid", "commit", "-q", "-m", "prereg"],
                       check=True)
        root = os.path.join(base, "recordings")
        check("recordings root is outside any git worktree (BMREC-18)", not BS.inside_git_worktree(root))
        cfg = {"pipe_name": BF.PIPE_NAME, "recordings_root": root, "backup_root": os.path.join(base, "backup"),
               "pinned_client_exe": os.path.join(JDK, "bin", "java.exe"), "addon_jar_path": JAR, "pin_file": PIN,
               "holdout_calendar": cal, "bookmap_jar": os.path.join(os.path.dirname(LIB), "Bookmap.jar"),
               "addon_inventory_dirs": [{"label": "h1-dist", "path": os.path.dirname(JAR)}],
               "rest_enabled": False}
        cfg_path = os.path.join(base, "config.json")
        with open(cfg_path, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=1)
        # 3. recorder
        env = dict(os.environ, PYTHONUTF8="1")
        rec = subprocess.Popen([sys.executable, os.path.join(REPO, "scripts", "bookmap_recorder.py"),
                                "--config", cfg_path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, env=env)
        run_dir = None
        for _ in range(100):
            time.sleep(0.1)
            if os.path.isdir(root):
                runs = [r for r in os.listdir(root) if os.path.isdir(os.path.join(root, r))]
                if runs:
                    run_dir = os.path.join(root, runs[0])
                    ev = os.path.join(run_dir, "events.jsonl")
                    if os.path.exists(ev) and "pipe_created" in open(ev, encoding="utf-8").read():
                        break
            if rec.poll() is not None:
                break
        check("recorder started and created the pipe", run_dir is not None and rec.poll() is None)
        # 4. harness
        cls = os.path.join(base, "harness-classes")
        cp = os.pathsep.join([os.path.join(LIB, "bm-simplified-api-wrapper.jar"), os.path.join(LIB, "bm-l1api.jar"),
                              JAR])
        comp = subprocess.run([os.path.join(JDK, "bin", "javac.exe"), "-cp", cp, "-d", cls,
                               os.path.join(HERE, "E2EHarness.java")], capture_output=True, text=True)
        check("harness compiles", comp.returncode == 0, comp.stderr.strip()[:300])
        t0 = time.time()
        har = subprocess.run([os.path.join(JDK, "bin", "java.exe"), "-cp", cp + os.pathsep + cls, "E2EHarness"],
                             capture_output=True, text=True, timeout=120)
        log("harness stdout: " + har.stdout.strip())
        if har.stderr.strip():
            log("harness stderr: " + har.stderr.strip()[:2000])
        check("harness exit 0 (stop() bounded, admin listener removed)", har.returncode == 0,
              f"rc={har.returncode}, {time.time() - t0:.1f}s")
        time.sleep(1.0)
        # 5. stop
        subprocess.run([sys.executable, os.path.join(REPO, "scripts", "bookmap_recorder.py"), "--config", cfg_path,
                        "--stop"], check=True, env=env)
        out, _ = rec.communicate(timeout=60)
        if out.strip():
            log("recorder output: " + out.strip()[:3000])
        check("recorder exited 0 after --stop", rec.returncode == 0, f"rc={rec.returncode}")
        # verification
        man = BS.read_jsonl(os.path.join(run_dir, "manifest.jsonl"))
        events = BS.read_jsonl(os.path.join(run_dir, "events.jsonl"))
        kinds = [e["kind"] for e in man]
        log("manifest kinds: " + ", ".join(kinds))
        ok, vlines = BS.verify_run(run_dir)
        for vl in vlines:
            log("  verify: " + vl)
        check("manifest SHA-256 of every closed file matches (BMREC-21)", ok)
        check("exactly one session accepted", kinds.count("session_start") == 1)
        check("no client rejected", not [e for e in man if e.get("kind") == "security_event"],
              str([e.get("reason") for e in man if e.get("kind") == "security_event"]))
        closed = [e for e in man if e["kind"] == "file_closed"]
        types = {}
        notes = {}
        book_states = []
        for c in closed:
            walk = BS.read_records(os.path.join(run_dir, c["file"]))
            check(f"file {c['file']} walks clean (CRC)", walk["ok"])
            check(f"file {c['file']} is read-only after close (BMREC-19)",
                  not os.access(os.path.join(run_dir, c["file"]), os.W_OK))
            for origin, _arr, payload in walk["records"]:
                if origin == BS.ORIGIN_ADDON:
                    r = BF.parse_payload(payload)
                    types[r["type_name"]] = types.get(r["type_name"], 0) + 1
                else:
                    n, obj = BS.decode_note(payload)
                    notes[n] = notes.get(n, 0) + 1
                    if n == "BOOK_STATE":
                        book_states.append(obj)
        log(f"add-on record types: {types}")
        log(f"recorder notes: {notes}")
        log(f"book states: {book_states}")
        check("all 260 onDepth callbacks recorded, one record each (10 snapshot + 250 deltas; full resolution)",
              types.get("DEPTH", 0) == 10 + 200 + 50, str(types.get("DEPTH")))
        check("all 20 trades recorded", types.get("TRADE", 0) == 20, str(types.get("TRADE")))
        check("timer heartbeats recorded", types.get("HEARTBEAT", 0) >= 2, str(types.get("HEARTBEAT")))
        check("LIVE boundary recorded", types.get("MODE", 0) == 1)
        check("book VALID after the complete checkpoint", any(b.get("state") == "VALID" for b in book_states))
        check("connection LOST made the book INVALID",
              any(b.get("state") == "INVALID" and b.get("reason") == "CONNECTION_LOST" for b in book_states))
        check("book VALID again only after RESTORED + snapshot + checkpoint",
              book_states and book_states[-1].get("state") == "VALID")
        check("connection loss is a manifest gap",
              any(e.get("kind") == "gap" and e.get("cause") == "BOOKMAP_CONNECTION_LOST" for e in man))
        check("connection state MONITORED (admin listener reachable)",
              [e for e in man if e["kind"] == "session_start"][0]["connection_state"] == "MONITORED")
        blob = b""
        for fn in os.listdir(run_dir):
            with open(os.path.join(run_dir, fn), "rb") as fh:
                blob += fh.read()
        check("no admin free text anywhere in the recording (BMREC-06)", MARKER not in blob)
        check("no absolute path / user name in manifest (BMREC-22)",
              ":\\\\" not in open(os.path.join(run_dir, "manifest.jsonl"), encoding="utf-8").read()
              and "Users" not in open(os.path.join(run_dir, "manifest.jsonl"), encoding="utf-8").read())
        acc = [e for e in events if e["kind"] == "hello_accepted"]
        check("hello carried the pinned code SHA", acc and acc[0]["hello"]["code_sha256"] == pin["code_sha256"])
        # backup
        ok_b = BRC.backup(cfg, log=lambda m: log("  backup: " + m))
        check("backup copies verified by SHA-256 (BMREC-23)", ok_b)

        # ---- scenario 2 (BMREC-17): recorder down while 70 000 callbacks arrive -> bounded queue overflows
        log("-- scenario 2: queue overflow while the recorder is down (BMREC-17)")
        cfg2 = dict(cfg, recordings_root=os.path.join(base, "recordings-overflow"),
                    backup_root=os.path.join(base, "backup-overflow"))
        cfg2_path = os.path.join(base, "config-overflow.json")
        with open(cfg2_path, "w", encoding="utf-8") as fh:
            json.dump(cfg2, fh, indent=1)
        har2 = subprocess.Popen([os.path.join(JDK, "bin", "java.exe"), "-cp", cp + os.pathsep + cls, "E2EHarness",
                                 "overflow"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        first = har2.stdout.readline().strip()
        log("harness: " + first)
        max_ms = float(first.split("maxCallbackMs=")[1]) if "maxCallbackMs=" in first else 1e9
        check("70 000 callbacks with no recorder never blocked (max single callback < 100 ms)", max_ms < 100,
              f"max {max_ms:.3f} ms")
        time.sleep(2.0)  # recorder starts AFTER the overflow (stale stop-request mtime is older than its start)
        rec2 = subprocess.Popen([sys.executable, os.path.join(REPO, "scripts", "bookmap_recorder.py"),
                                 "--config", cfg2_path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, env=env)
        rest_out, _ = har2.communicate(timeout=120)
        log("harness: " + rest_out.strip())
        check("overflow harness exit 0", har2.returncode == 0, f"rc={har2.returncode}")
        time.sleep(1.0)
        subprocess.run([sys.executable, os.path.join(REPO, "scripts", "bookmap_recorder.py"), "--config", cfg2_path,
                        "--stop"], check=True, env=env)
        out2, _ = rec2.communicate(timeout=60)
        if out2.strip():
            log("recorder output: " + out2.strip()[:3000])
        check("overflow recorder exited 0", rec2.returncode == 0, f"rc={rec2.returncode}")
        root2 = cfg2["recordings_root"]
        run2 = os.path.join(root2, [r for r in os.listdir(root2) if os.path.isdir(os.path.join(root2, r))][0])
        man2 = BS.read_jsonl(os.path.join(run2, "manifest.jsonl"))
        gaps2 = [e for e in man2 if e["kind"] == "gap"]
        log(f"overflow gaps: {[(g['cause'], g.get('dropped'), g.get('expected'), g.get('got')) for g in gaps2]}")
        dropped = sum(g.get("dropped", 0) for g in gaps2 if g["cause"] == "ADDON_QUEUE_OVERFLOW")
        check("queue overflow is recorded as an add-on GAP with its count (nothing dropped silently)", dropped > 0,
              f"dropped={dropped}")
        depth2 = 0
        states2 = []
        for c in [e for e in man2 if e["kind"] == "file_closed"]:
            for origin, _a, payload in BS.read_records(os.path.join(run2, c["file"]))["records"]:
                if origin == BS.ORIGIN_ADDON:
                    if BF.parse_payload(payload)["type"] == BF.DEPTH:
                        depth2 += 1
                elif BS.decode_note(payload)[0] == "BOOK_STATE":
                    states2.append(BS.decode_note(payload)[1])
        check("recorded depth + dropped == 70 000 callbacks", depth2 + dropped == 70_000,
              f"recorded={depth2} dropped={dropped}")
        check("book INVALID at the gap, VALID again only after the post-gap checkpoint",
              any(s.get("state") == "INVALID" and "OVERFLOW" in (s.get("reason") or "") for s in states2)
              and states2[-1].get("state") == "VALID", str(states2))
        check("overflow run manifest verifies", BS.verify_run(run2)[0])
    except Exception as e:  # noqa: BLE001 - the harness reports, never hides
        log(f"[FAIL] exception: {type(e).__name__}: {e}")
        checks.append(False)
    result = "E2E RESULT: " + ("PASS" if checks and all(checks) else "FAIL") + f" ({sum(checks)}/{len(checks)})"
    log(result)
    if log_path:
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    return 0 if checks and all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
