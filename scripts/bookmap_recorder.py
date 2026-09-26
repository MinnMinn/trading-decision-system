"""Stage H1 Bookmap recorder (read-only): the Python end of the one-way pipe.

    python scripts/bookmap_recorder.py                       # record (Ctrl+C or --stop to end)
    python scripts/bookmap_recorder.py --stop                # ask a running recorder to stop cleanly
    python scripts/bookmap_recorder.py --preregister-holdout # H1 N4: write the holdout calendar BEFORE recording
    python scripts/bookmap_recorder.py --log-exposure 2026-W40 --reason "..."   # log a human look at a week
    python scripts/bookmap_recorder.py --verify-run <run_id> # recompute file hashes against the manifest
    python scripts/bookmap_recorder.py --backup              # BMREC-23 daily backup with hash verification
    python scripts/bookmap_recorder.py --ledger-manifests    # BMREC-21 append manifest hashes to the tracked ledger
    python scripts/bookmap_recorder.py --record-deletion <run_id>/<file> --reason "..."  # BMREC-24, never deletes

Governing: docs/plans/2026-09-26-heatmap-realtime-plan.md (stage H1, §1.3-§1.5, §1.8),
docs/security/2026-09-26-bookmap-recorder-h1.md (BMREC-*), docs/contracts/bookmap-recorder-frames.md (wire, files,
parameters). This process makes no decision and places no order. It never imports the secret loaders or the order
connector (BMREC-27) and has exactly one outbound network path, scripts/bookmap_rest.py (BMREC-26).
"""
import argparse
import datetime as dt
import hashlib
import heapq
import json
import os
import queue
import subprocess
import sys
import threading
import time
import zipfile
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import bookmap_frames as BF  # noqa: E402
import bookmap_rest as BR  # noqa: E402
import bookmap_store as BS  # noqa: E402

DEFAULT_CONFIG = os.path.join(REPO, "integrations", "bookmap", "recorder-config.json")
EXPOSURE_LOG = os.path.join(REPO, "docs", "research", "bookmap-exposure-log.jsonl")
MANIFEST_LEDGER = os.path.join(REPO, "docs", "research", "bookmap-manifest-ledger.jsonl")
STOP_FILE = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "tds-h1-recorder", "stop-request")

STREAM_SILENCE_STALE_MS = 5000
CLOCK_DRIFT_INVALID_MS = 5000
HELLO_TIMEOUT_S = 10
LOOP_READ_TIMEOUT_MS = 200
FREE_SPACE_CHECK_S = 10
EXCHANGEINFO_REFRESH_S = 3600
TICK_RETRY_S = 60
CHECKPOINT_NOTE_LEVELS = 5000

EXIT_OK, EXIT_PREFLIGHT, EXIT_SQUATTED, EXIT_TICK_GATE, EXIT_ELEVATED = 0, 2, 3, 4, 5


def utc_now():
    return dt.datetime.now(dt.timezone.utc)


def load_config(path):
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    for k in ("pipe_name", "recordings_root", "pinned_client_exe", "addon_jar_path", "pin_file",
              "holdout_calendar"):
        if not cfg.get(k):
            raise SystemExit(f"config {path}: missing {k}")
    return cfg


def _repo_path(cfg, key):
    p = cfg[key]
    return p if os.path.isabs(p) else os.path.join(cfg.get("repo_root", REPO), p)


def recorder_code_sha256():
    h = hashlib.sha256()
    for name in ("bookmap_recorder.py", "bookmap_frames.py", "bookmap_store.py", "bookmap_rest.py",
                 "bookmap_pipe.py"):
        with open(os.path.join(HERE, name), "rb") as fh:
            h.update(name.encode() + b"\0" + fh.read().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


# ---------------------------------------------------------------- live-usability (contract §7)


def live_usable(mode, session, book_valid=None):
    """Never true unless mode == LIVE. H1 only labels; H4 enforces (BMREC-37)."""
    if mode != BF.LIVE:
        return False
    if not session or not session.get("authenticated"):
        return False
    if session.get("data_delay") != 0 or session.get("recording_tag") is not None:
        return False
    if not session.get("stream_valid", False):
        return False
    if book_valid is False:
        return False
    return True


# ---------------------------------------------------------------- pre-registration (plan H1, N4)


def holdout_assignment(iso_year, iso_week, seed, fraction):
    h = hashlib.sha256(f"{seed}:{iso_year}-W{iso_week:02d}".encode()).hexdigest()
    return "holdout" if int(h[:16], 16) / float(2 ** 64) < fraction else "in_sample"


def preregister_holdout(path, seed=None, fraction=0.25, now=None):
    if os.path.exists(path):
        raise SystemExit(f"{os.path.basename(path)} already exists: the calendar is registered once and never "
                         f"rewritten (plan H1 N4). Log exposures with --log-exposure instead.")
    now = now or utc_now()
    seed = seed if seed is not None else int.from_bytes(os.urandom(8), "big")
    y, w, _ = now.isocalendar()
    preview = []
    d = now
    for _ in range(26):
        yy, ww, _ = d.isocalendar()
        preview.append({"week": f"{yy}-W{ww:02d}", "assignment": holdout_assignment(yy, ww, seed, fraction)})
        d += dt.timedelta(days=7)
    doc = {
        "_source": "Plan H1 N4 pre-registration: the in-sample / holdout assignment of EVERY future recorded "
                   "ISO week, fixed before the first recording. Written once by `bookmap_recorder.py "
                   "--preregister-holdout`; commit it before starting the recorder (the recorder refuses to "
                   "record until this file is committed and unmodified). H5 only reads it.",
        "registered_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "first_week": f"{y}-W{w:02d}",
        "rule": "assignment(week) = 'holdout' if int(sha256(f'{seed}:{iso_year}-W{iso_week:02d}')[:16], 16) / 2**64 "
                "< holdout_fraction else 'in_sample'",
        "seed": seed,
        "holdout_fraction": fraction,
        "applies_to": "every ISO week (UTC) of Bookmap recordings, from first_week onward, all instruments",
        "exposure_rule": "Automated quality metrics (hashes, gaps, reconciliation MATCH/MISMATCH counts) do not "
                         "expose a week. Any human or feature-design look at a week's market content does, and is "
                         "logged with `--log-exposure` in docs/research/bookmap-exposure-log.jsonl.",
        "preview_first_26_weeks": preview,
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "x", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
    return doc


def check_preregistration(path, now=None):
    """(ok, reason). The calendar must exist, parse, predate now, and be committed and unmodified in git."""
    now = now or utc_now()
    if not os.path.isfile(path):
        return False, "HOLDOUT_CALENDAR_MISSING (run --preregister-holdout and commit it)"
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        reg = dt.datetime.strptime(doc["registered_at_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        float(doc["holdout_fraction"])
        int(doc["seed"])
    except (OSError, ValueError, KeyError, TypeError):
        return False, "HOLDOUT_CALENDAR_INVALID"
    if reg > now:
        return False, "HOLDOUT_CALENDAR_REGISTERED_IN_FUTURE"
    d = os.path.dirname(path)
    rel = os.path.basename(path)
    tracked = subprocess.run(["git", "-C", d, "ls-files", "--error-unmatch", rel], capture_output=True, text=True)
    if tracked.returncode != 0:
        return False, "HOLDOUT_CALENDAR_NOT_COMMITTED"
    clean = subprocess.run(["git", "-C", d, "diff", "--quiet", "HEAD", "--", rel], capture_output=True, text=True)
    if clean.returncode != 0:
        return False, "HOLDOUT_CALENDAR_MODIFIED_SINCE_COMMIT"
    return True, "OK"


def log_exposure(week, reason, who="owner", path=EXPOSURE_LOG):
    if not reason:
        raise SystemExit("--reason is required: say what was looked at and why")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({"week": week, "exposed_at_utc": utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                             "by": who, "reason": reason}, sort_keys=True) + "\n")


# ---------------------------------------------------------------- the pin (BMREC-30)


def load_pin(cfg):
    with open(_repo_path(cfg, "pin_file"), encoding="utf-8") as fh:
        pin = json.load(fh)
    for k in ("jar_sha256", "code_sha256", "source_sha256"):
        if len(pin.get(k, "")) != 64:
            raise ValueError(f"pin has no valid {k}")
    if (pin.get("check") or {}).get("result") != "PASS":
        raise ValueError("pin check result is not PASS (BMREC-04c)")
    return pin


def jar_matches_pin(cfg, pin):
    p = cfg["addon_jar_path"]
    if not os.path.isfile(p):
        return False, "ADDON_JAR_MISSING"
    got = BS.sha256_file(p)
    return (got == pin["jar_sha256"]), ("OK" if got == pin["jar_sha256"] else "JAR_HASH_MISMATCH")


def bookmap_version(cfg):
    p = cfg.get("bookmap_jar")
    if not p or not os.path.isfile(p):
        return "UNKNOWN"
    try:
        with zipfile.ZipFile(p) as z:
            for line in z.read("META-INF/MANIFEST.MF").decode("utf-8", "replace").splitlines():
                if line.startswith("BookMap-version:"):
                    return line.split(":", 1)[1].strip()[:64]
    except (OSError, KeyError, zipfile.BadZipFile):
        pass
    return "UNKNOWN"


def _norm(p):
    return os.path.normcase(os.path.normpath(os.path.abspath(p)))


def ensure_private_dir(path, BP):
    """BMREC-19: create the root with an owner/SYSTEM/Administrators-only DACL if it does not exist; refuse an
    existing root whose DACL lets Everyone / Authenticated Users / Users (etc.) write. Returns None or a reason."""
    if not os.path.isdir(path):
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        BP.create_private_dir(path)
    bad = BP.others_with_write(BP.path_dacl_sddl(path))
    if bad:
        return (f"{os.path.basename(path)} grants write to broad principals {bad} (BMREC-19). Remove those ACEs "
                f"(icacls <root> /inheritance:r, then grant only your user, SYSTEM and Administrators) or point the "
                f"config at a new folder the recorder can create itself.")
    return None


# ---------------------------------------------------------------- REST worker


class RestWorker:
    """Runs BinancePublic.get() off the pipe-reading thread so a slow request never stalls the pipe."""

    def __init__(self, client):
        self.client = client
        self.jobs = queue.Queue()
        self.results = queue.Queue()
        self.inflight = set()
        self.t = threading.Thread(target=self._run, name="rest-worker", daemon=True)
        self.t.start()

    def submit(self, tag, path, params=None):
        if tag in self.inflight:
            return False
        self.inflight.add(tag)
        self.jobs.put((tag, path, params))
        return True

    def _run(self):
        while True:
            job = self.jobs.get()
            if job is None:
                return
            tag, path, params = job
            try:
                res = self.client.get(path, params)
            except BR.OutboundRefused as e:
                res = {"status": "REFUSED", "http": None, "data": None, "t_send": None, "t_recv": None,
                       "reason": str(e)}
            self.results.put((tag, res))

    def poll(self):
        out = []
        while True:
            try:
                tag, res = self.results.get_nowait()
            except queue.Empty:
                return out
            self.inflight.discard(tag)
            out.append((tag, res))

    def stop(self):
        self.jobs.put(None)


# ---------------------------------------------------------------- the recorder


class Recorder:
    def __init__(self, cfg, *, rest_client=None, clock_ns=time.time_ns, pipe_module=None):
        self.cfg = cfg
        self.clock_ns = clock_ns
        self.root = cfg["recordings_root"]
        self.pin = None
        self.run_id = None
        self.run_dir = None
        self.events = None
        self.manifest = None
        self.file = None
        self.file_seq = 0
        self.session = None
        self.session_seq = 0
        self.prev_session_facts = None
        self.stop_requested = False
        self.started_ns = clock_ns()
        self.pipe_module = pipe_module
        self.rest_client = rest_client
        self.rest = None
        self.disk_paused = False
        self.disk_dropped = 0
        self.last_free_check = 0.0
        self.exit_code = EXIT_OK
        self.code_sha = recorder_code_sha256()
        self.bm_version = bookmap_version(cfg)
        self.clock = None            # latest {"offset_ms", "rtt_ms", "measured_at_ns"}
        self.filters = None          # latest exchange filters
        self.tick_status = BR.UNKNOWN
        self.depth_fail_streak = 0
        self.depth_samples = None    # list while a depth request is in flight
        self.next_due = {}
        self._event_lock = threading.Lock()

    # -------------------------------------------------------------- logging

    def event(self, **kw):
        kw.setdefault("t_ns", self.clock_ns())
        with self._event_lock:          # the REST worker thread logs too
            if self.events:
                self.events.append(kw)
        if kw.get("kind") in ("alert", "security_event"):
            print(f"ALERT: {kw}", file=sys.stderr, flush=True)

    def alert(self, what, **kw):
        self.event(kind="alert", what=what, **kw)

    def security_event(self, what, **kw):
        self.event(kind="security_event", what=what, **kw)
        if self.manifest:
            self.manifest.append({"kind": "security_event", "what": what, "t_ns": self.clock_ns(), **kw})

    # -------------------------------------------------------------- preflight

    def preflight(self):
        """Returns an exit code (0 = ok). Order matters: nothing is written before the root is proven safe."""
        try:
            import bookmap_pipe as BP
        except ImportError as e:
            print(f"PREFLIGHT: {e}", file=sys.stderr)
            return EXIT_PREFLIGHT
        self.pipe_module = self.pipe_module or BP
        if BP.is_elevated():
            print("PREFLIGHT: refusing to run elevated (BMREC-09)", file=sys.stderr)
            return EXIT_ELEVATED
        try:
            BS.refuse_if_in_worktree(self.root)
            if self.cfg.get("backup_root"):
                BS.refuse_if_in_worktree(self.cfg["backup_root"], "backup root")
        except BS.StorageRefused as e:
            print(f"PREFLIGHT: {e}", file=sys.stderr)
            return EXIT_PREFLIGHT
        why = ensure_private_dir(self.root, BP)
        if why:
            print(f"PREFLIGHT: {why}", file=sys.stderr)
            return EXIT_PREFLIGHT
        self._recover_previous_runs()
        self.run_id = utc_now().strftime("%Y%m%dT%H%M%SZ") + "-" + os.urandom(2).hex()
        self.run_dir = os.path.join(self.root, self.run_id)
        os.makedirs(self.run_dir)
        self.events = BS.JsonLines(os.path.join(self.run_dir, "events.jsonl"))
        self.manifest = BS.JsonLines(os.path.join(self.run_dir, "manifest.jsonl"))
        self.event(kind="recorder_start", run_id=self.run_id, recorder_code_sha256=self.code_sha,
                   bookmap_version=self.bm_version, elevated=False)
        self.manifest.append({"kind": "run_start", "run_id": self.run_id, "t_ns": self.clock_ns(),
                              "recorder_code_sha256": self.code_sha, "file_format_version": BS.FILE_FORMAT_VERSION,
                              "schema_version": BF.SCHEMA_VERSION})
        exe = self.cfg["pinned_client_exe"]
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        if not _norm(exe).startswith(_norm(pf) + os.sep):
            self.security_event("PINNED_CLIENT_NOT_UNDER_PROGRAM_FILES", exe_basename=os.path.basename(exe))
            return EXIT_PREFLIGHT
        ok, why = check_preregistration(_repo_path(self.cfg, "holdout_calendar"))
        if not ok:
            self.alert("PREFLIGHT_FAILED", reason=why)
            return EXIT_PREFLIGHT
        try:
            self.pin = load_pin(self.cfg)
        except (OSError, ValueError) as e:
            self.alert("PREFLIGHT_FAILED", reason=f"PIN_INVALID: {e}")
            return EXIT_PREFLIGHT
        ok, why = jar_matches_pin(self.cfg, self.pin)
        if not ok:
            self.security_event("ADDON_JAR_NOT_PINNED", reason=why)
            return EXIT_PREFLIGHT
        if BS.free_bytes(self.root) < BS.FREE_SPACE_FLOOR_BYTES:
            self.alert("DISK_BELOW_FLOOR_AT_START", free_bytes=BS.free_bytes(self.root))
            return EXIT_PREFLIGHT
        return EXIT_OK

    def _recover_previous_runs(self):
        """A file left open by a crash is closed now: hashed as-is, truncated tail reported, set read-only,
        recorded as recovered_close in ITS run's manifest. Nothing is repaired or deleted (BMREC-20, -24)."""
        for run in sorted(os.listdir(self.root)):
            rd = os.path.join(self.root, run)
            man = os.path.join(rd, "manifest.jsonl")
            if not os.path.isfile(man):
                continue
            entries = BS.read_jsonl(man)
            closed = {e["file"] for e in entries if e.get("kind") in ("file_closed", "recovered_close")}
            pending = [f for f in sorted(os.listdir(rd)) if f.endswith(".bmrec") and f not in closed]
            ended = any(e.get("kind") in ("run_end", "run_recovered") for e in entries)
            if not pending and ended:
                continue
            m = BS.JsonLines(man)
            for f in pending:
                p = os.path.join(rd, f)
                walk = BS.read_records(p)
                sha = BS.sha256_file(p)
                BS.make_read_only(p)
                m.append({"kind": "recovered_close", "file": f, "sha256": sha, "bytes": os.path.getsize(p),
                          "records": len(walk["records"]), "clean": walk["ok"], "bad_offset": walk["bad_offset"],
                          "truncated_tail_bytes": walk["truncated_tail_bytes"], "t_ns": self.clock_ns()})
            if not ended:
                m.append({"kind": "run_recovered", "t_ns": self.clock_ns(),
                          "note": "previous recorder process ended without run_end (crash or kill)"})
            m.close()

    # -------------------------------------------------------------- main loop

    def run(self):
        code = self.preflight()
        if code != EXIT_OK:
            self._finish(code)
            return code
        BP = self.pipe_module
        try:
            server = BP.SecurePipeServer(self.cfg["pipe_name"])
        except BP.PipeSquatted as e:
            self.security_event("PIPE_NAME_SQUATTED", detail=str(e))
            self._finish(EXIT_SQUATTED)
            return EXIT_SQUATTED
        except BP.PipeError as e:
            self.security_event("PIPE_CREATE_FAILED", detail=str(e))
            self._finish(EXIT_SQUATTED)
            return EXIT_SQUATTED
        self.event(kind="pipe_created", instances=BP.MAX_INSTANCES, inbound_only=True, reject_remote=True,
                   first_instance=True, dacl=_redact_sid(server.dacl_sddl()))
        if self.cfg.get("rest_enabled"):
            self.rest = RestWorker(self.rest_client or BR.BinancePublic(event=self._rest_event))
            self.rest.submit("exchangeInfo", "/fapi/v1/exchangeInfo")
        try:
            while not self.stop_requested and self.exit_code == EXIT_OK:
                self._check_stop_file()
                if not server.connected:
                    if server.wait_connect(LOOP_READ_TIMEOUT_MS):
                        self._on_connect(server)
                    self._housekeeping()
                    continue
                timeout = BR.DEPTH_RECON_SAMPLE_MS if self.depth_samples is not None else LOOP_READ_TIMEOUT_MS
                data = server.read(timeout)
                arrival = self.clock_ns()
                if data is None:
                    self._end_session("CLIENT_DISCONNECTED")
                    server.disconnect()
                elif data:
                    if not self._feed(data, arrival):
                        self._end_session(self.session.get("close_reason", "CLOSED") if self.session else "CLOSED")
                        server.disconnect()
                self._housekeeping()
        except KeyboardInterrupt:
            self.event(kind="stop_requested", source="ctrl_c")
        finally:
            if self.session:
                self._end_session("RECORDER_STOP")
            server.close()
            if self.rest:
                self.rest.stop()
            self._finish(self.exit_code)
        return self.exit_code

    def _check_stop_file(self):
        try:
            st = os.stat(STOP_FILE)
        except OSError:
            return
        if st.st_mtime_ns > self.started_ns:
            self.event(kind="stop_requested", source="stop_file")
            self.stop_requested = True

    def _finish(self, code):
        self._close_file()
        if self.manifest:
            self.manifest.append({"kind": "run_end", "t_ns": self.clock_ns(), "exit_code": code})
            self.manifest.close(read_only=True)
            self.manifest = None
        if self.events:
            self.event(kind="recorder_stop", exit_code=code)
            self.events.close(read_only=True)
            self.events = None

    # -------------------------------------------------------------- connection / authentication (BMREC-13)

    def _on_connect(self, server):
        BP = self.pipe_module
        try:
            pid = server.client_pid()
            image, sid, logon = BP.process_identity(pid)
        except BP.PipeError as e:
            self._reject(server, "CLIENT_IDENTITY_UNREADABLE", "?", None, detail=str(e))
            return
        base = os.path.basename(image)
        if _norm(image) != _norm(self.cfg["pinned_client_exe"]):
            self._reject(server, "CLIENT_IMAGE_MISMATCH", base, pid)
            return
        if sid != BP.current_user_sid() or logon != BP.current_logon_id():
            self._reject(server, "CLIENT_LOGON_SESSION_MISMATCH", base, pid)
            return
        ok, why = jar_matches_pin(self.cfg, self.pin)
        if not ok:
            self._reject(server, why, base, pid)
            return
        self.session_seq += 1
        self.session = self._new_session(pid, base)
        self.event(kind="client_connected", session_id=self.session_seq, pid=pid, exe_basename=base)

    def _reject(self, server, reason, base, pid, **kw):
        self.security_event("CLIENT_REJECTED", reason=reason, exe_basename=base, pid=pid, **kw)
        server.disconnect()

    def _new_session(self, pid, base):
        return {"id": self.session_seq, "pid": pid, "exe": base, "state": "AWAIT_HELLO",
                "connected_ns": self.clock_ns(), "reader": BF.FrameReader(), "authenticated": False,
                "last_capture_seq": None, "last_fwd_seq": 0, "bids": {}, "asks": {}, "book_valid": False,
                "book_reason": "SESSION_START", "ckpt": None, "lost_state": None, "mode": 0,
                "consecutive_invalid": 0, "last_frame_ns": self.clock_ns(), "stream_valid": True,
                "stream_reason": None, "connection_state": "UNKNOWN", "trades": deque(), "gap_times": deque(),
                "lags": [], "live_records": 0, "records": 0, "hello": None, "stale": False,
                "started_ns": None, "tick_deadline_ns": None}

    # -------------------------------------------------------------- frames

    def _feed(self, data, arrival):
        """Returns False when the connection must be closed."""
        s = self.session
        if s is None:
            return False
        for item in s["reader"].feed(data):
            if item[0] == "error":
                if not self._frame_error(item[1], arrival):
                    return False
                if item[1] in BF.FrameReader.FATAL:
                    s["close_reason"] = f"FRAMING_{item[1]}"
                    return False
                continue
            _, payload, rec = item
            s["last_frame_ns"] = arrival
            if s["stale"]:
                s["stale"] = False
                self._note("STREAM_STATE", arrival, {"state": "FRESH_AFTER_SILENCE"})
            if s["state"] == "AWAIT_HELLO":
                if not self._hello(rec, arrival):
                    return False
                continue
            s["consecutive_invalid"] = 0
            if not self._process(payload, rec, arrival):
                return False
        if s["state"] == "AWAIT_HELLO" and arrival - s["connected_ns"] > HELLO_TIMEOUT_S * 1e9:
            self.security_event("CLIENT_REJECTED", reason="HELLO_TIMEOUT", exe_basename=s["exe"], pid=s["pid"])
            s["close_reason"] = "HELLO_TIMEOUT"
            return False
        return True

    def _frame_error(self, code, arrival):
        s = self.session
        if s["state"] == "AWAIT_HELLO":
            self.security_event("CLIENT_REJECTED", reason=f"HELLO_INVALID_{code}", exe_basename=s["exe"],
                                pid=s["pid"])
            s["close_reason"] = f"HELLO_INVALID_{code}"
            return False
        s["consecutive_invalid"] += 1
        self._note("VALIDATION_FAILURE", arrival, {"reason": code})
        self.event(kind="validation_failure", reason=code, session_id=s["id"])
        self._invalidate(f"VALIDATION_FAILURE_{code}", arrival)
        if s["consecutive_invalid"] >= BF.MAX_CONSECUTIVE_INVALID_FRAMES:
            self.event(kind="connection_closed", reason="TOO_MANY_INVALID_FRAMES", session_id=s["id"])
            s["close_reason"] = "TOO_MANY_INVALID_FRAMES"
            return False
        return True

    def _hello(self, rec, arrival):
        s = self.session
        if rec["type"] != BF.HELLO:
            self.security_event("CLIENT_REJECTED", reason="NO_HELLO", exe_basename=s["exe"], pid=s["pid"])
            s["close_reason"] = "NO_HELLO"
            return False
        if rec["code_sha256"] != self.pin["code_sha256"] or rec["source_sha256"] != self.pin["source_sha256"]:
            self.security_event("CLIENT_REJECTED", reason="HELLO_PIN_MISMATCH", exe_basename=s["exe"],
                                pid=s["pid"], hello_code_sha256=rec["code_sha256"])
            s["close_reason"] = "HELLO_PIN_MISMATCH"
            return False
        if rec["seq"] != 1:
            self.security_event("CLIENT_REJECTED", reason="HELLO_SEQ_NOT_1", exe_basename=s["exe"], pid=s["pid"])
            s["close_reason"] = "HELLO_SEQ_NOT_1"
            return False
        s["state"] = "ACTIVE"
        s["authenticated"] = True
        self.bm_version = bookmap_version(self.cfg)  # re-read per session: Bookmap may have been updated (BMREC-10)
        s["hello"] = rec
        s["last_fwd_seq"] = 1
        s["mode"] = rec["mode"]
        s["data_delay"] = rec["data_delay"]
        s["recording_tag"] = rec["recording_tag"]
        s["connection_state"] = "MONITORED" if rec["connection_monitor"] == "ACTIVE" else "UNKNOWN"
        s["started_ns"] = arrival
        s["tick_deadline_ns"] = arrival + BR.TICK_GATE_DEADLINE_S * 10 ** 9
        s["symbol"] = BR.symbol_from_alias(rec["alias"])
        hello_facts = {k: rec[k] for k in ("addon_version", "code_sha256", "source_sha256", "alias", "symbol",
                                          "exchange", "instrument_type", "full_name", "pips", "multiplier",
                                          "size_multiplier", "data_delay", "is_full_depth", "is_crypto",
                                          "is_api_protected", "is_nbbo_supported", "recording_tag",
                                          "connection_monitor", "queue_capacity")}
        s["hello_facts"] = hello_facts
        inventory = BS.dir_inventory(self.cfg.get("addon_inventory_dirs", []))
        s["inventory"] = inventory
        seg_key = {"bookmap_version": self.bm_version, "code_sha256": rec["code_sha256"], "alias": rec["alias"],
                   "pips": rec["pips"], "size_multiplier": rec["size_multiplier"]}
        s["segment"] = hashlib.sha256(json.dumps(seg_key, sort_keys=True).encode()).hexdigest()[:12]
        prev = self.prev_session_facts or self._last_session_from_previous_runs()
        if prev:
            if prev.get("inventory") != inventory:
                self.security_event("ADDON_INVENTORY_CHANGED", previous=prev.get("inventory"), current=inventory)
            if prev.get("bookmap_version") != self.bm_version:
                self.event(kind="bookmap_version_changed", previous=prev.get("bookmap_version"),
                           current=self.bm_version)
            if prev.get("segment") != s["segment"]:
                self.event(kind="segment_change", previous=prev.get("segment"), current=s["segment"])
            gap_from = prev.get("ended_ns")
            if gap_from:
                self.manifest.append({"kind": "gap", "cause": "SESSION_GAP", "from_arrival_ns": gap_from,
                                      "to_arrival_ns": arrival, "session_id": s["id"]})
        facts = {"kind": "session_start", "session_id": s["id"], "t_ns": arrival, "segment": s["segment"],
                 "bookmap_version": self.bm_version, "hello": hello_facts, "addon_inventory": inventory,
                 "jar_sha256": self.pin["jar_sha256"], "connection_state": s["connection_state"],
                 "live_usable_possible": (rec["data_delay"] == 0 and rec["recording_tag"] is None)}
        self.manifest.append(facts)
        self.event(kind="hello_accepted", session_id=s["id"], hello=hello_facts)
        self._open_file(arrival)
        self._note("SESSION_START", arrival, {"session_id": s["id"], "segment": s["segment"],
                                              "connection_state": s["connection_state"]})
        if self.rest:
            self.rest.submit("exchangeInfo", "/fapi/v1/exchangeInfo")
        if s["symbol"] is None:
            self.alert("TICK_GATE_ABORT", reason="alias does not map to a Binance futures symbol")
            self.exit_code = EXIT_TICK_GATE
        return True

    def _last_session_from_previous_runs(self):
        try:
            runs = sorted(r for r in os.listdir(self.root) if r != self.run_id)
        except OSError:
            return None
        for run in reversed(runs):
            man = os.path.join(self.root, run, "manifest.jsonl")
            if os.path.isfile(man):
                starts = [e for e in BS.read_jsonl(man) if e.get("kind") == "session_start"]
                if starts:
                    e = starts[-1]
                    return {"inventory": e.get("addon_inventory"), "bookmap_version": e.get("bookmap_version"),
                            "segment": e.get("segment")}
        return None

    def _process(self, payload, rec, arrival):
        s = self.session
        t = rec["type"]
        if t == BF.HELLO:
            self._frame_error("DUPLICATE_HELLO", arrival)
            return s["consecutive_invalid"] < BF.MAX_CONSECUTIVE_INVALID_FRAMES
        # sequence spaces (contract §4)
        if t in BF.CAPTURE_SPACE:
            last = s["last_capture_seq"]
            if last is not None and rec["seq"] != last + 1:
                self._gap("CAPTURE_SEQ_GAP", arrival, expected=last + 1, got=rec["seq"])
            s["last_capture_seq"] = rec["seq"]
        else:
            if rec["seq"] != s["last_fwd_seq"] + 1:
                self._gap("FORWARDER_SEQ_GAP", arrival, expected=s["last_fwd_seq"] + 1, got=rec["seq"])
            s["last_fwd_seq"] = rec["seq"]
        s["mode"] = rec["mode"]
        s["lags"].append(arrival - rec["addon_recv_ns"])
        if rec["mode"] == BF.LIVE and t in BF.CAPTURE_SPACE and rec["bookmap_time_ns"] >= 0:
            drift_ms = abs(rec["bookmap_time_ns"] - rec["addon_recv_ns"]) / 1e6
            bad = drift_ms > CLOCK_DRIFT_INVALID_MS
            if bad and s["stream_valid"]:
                s["stream_valid"], s["stream_reason"] = False, "CLOCK_DRIFT"
                self._note("STREAM_STATE", arrival, {"state": "INVALID", "reason": "CLOCK_DRIFT",
                                                     "drift_ms": round(drift_ms, 3)})
                self.event(kind="stream_invalid", reason="CLOCK_DRIFT", drift_ms=round(drift_ms, 3))
            elif not bad and not s["stream_valid"] and s["stream_reason"] == "CLOCK_DRIFT":
                s["stream_valid"], s["stream_reason"] = True, None
                self._note("STREAM_STATE", arrival, {"state": "VALID", "reason": "CLOCK_DRIFT_CLEARED"})
        # book + state
        if t == BF.DEPTH:
            if s["ckpt"] is not None:
                self._frame_error("DEPTH_INSIDE_CHECKPOINT", arrival)
            side = s["bids"] if rec["is_bid"] else s["asks"]
            if rec["size"] == 0:
                side.pop(rec["price_level"], None)
            else:
                side[rec["price_level"]] = rec["size"]
        elif t == BF.TRADE:
            if rec["mode"] == BF.LIVE:
                s["trades"].append((rec["addon_recv_ns"], rec["is_bid_aggressor"], rec["size"]))
                cutoff = arrival - 15 * 60 * 10 ** 9
                while s["trades"] and s["trades"][0][0] < cutoff:
                    s["trades"].popleft()
        elif t == BF.MODE:
            self.event(kind="mode_change", mode=BF.MODES[rec["mode"]], session_id=s["id"])
        elif t == BF.CONNECTION:
            self._connection(rec["state"], arrival)
        elif t == BF.GAP:
            self._gap("ADDON_" + rec["cause"], arrival, dropped=rec["dropped_count"])
        elif t == BF.SNAPSHOT_END:
            if s["lost_state"] == "RESTORED_AWAIT_SNAPSHOT":
                s["lost_state"] = "AWAIT_CHECKPOINT"
        elif t == BF.CHECKPOINT_BEGIN:
            last = s["last_capture_seq"]
            if last is not None and rec["capture_seq_at"] != last:
                self._gap("CHECKPOINT_SEQ_MISMATCH", arrival, expected=last, got=rec["capture_seq_at"])
            s["last_capture_seq"] = rec["capture_seq_at"]
            s["ckpt"] = {"want": rec["bid_levels"] + rec["ask_levels"], "got": 0, "bids": {}, "asks": {},
                         "complete": rec["bookmap_snapshot_complete"], "reason": rec["reason"], "gap": False,
                         "after_restore": s["lost_state"] == "AWAIT_CHECKPOINT"}
        elif t == BF.CHECKPOINT_LEVEL:
            c = s["ckpt"]
            if c is None:
                self._frame_error("LEVEL_OUTSIDE_CHECKPOINT", arrival)
            else:
                (c["bids"] if rec["is_bid"] else c["asks"])[rec["price_level"]] = rec["size"]
                c["got"] += 1
        elif t == BF.CHECKPOINT_END:
            self._checkpoint_end(rec, arrival)
        elif t == BF.ADDON_STOP:
            self.event(kind="addon_stop", session_id=s["id"])
        elif t == BF.HEARTBEAT:
            s["last_heartbeat"] = {k: rec[k] for k in ("queue_depth", "queue_capacity", "dropped_total",
                                                       "capture_seq_last", "frames_sent_total",
                                                       "ignored_admin_messages", "pipe_reconnects")}
        # write
        s["records"] += 1
        if live_usable(rec["mode"], s, s["book_valid"] if t == BF.DEPTH else None):
            s["live_records"] += 1
        if self.file is not None and not self.disk_paused:
            self.file.write(BS.ORIGIN_ADDON, arrival, payload)
            self.file.count_mode(BF.MODES[rec["mode"]])
        elif self.disk_paused:
            self.disk_dropped += 1
        return True

    def _connection(self, state, arrival):
        s = self.session
        self.event(kind="connection_state", state=state, session_id=s["id"])
        if state == "MONITOR_UNAVAILABLE":
            s["connection_state"] = "UNKNOWN"
        elif state == "MONITOR_ACTIVE":
            s["connection_state"] = "MONITORED"
        elif state == "LOST":
            s["lost_state"] = "LOST"
            self._invalidate("CONNECTION_LOST", arrival)
            self.manifest.append({"kind": "gap", "cause": "BOOKMAP_CONNECTION_LOST", "at_arrival_ns": arrival,
                                  "session_id": s["id"]})
        elif state == "RESTORED" and s["lost_state"] == "LOST":
            s["lost_state"] = "RESTORED_AWAIT_SNAPSHOT"

    def _checkpoint_end(self, rec, arrival):
        s = self.session
        c = s["ckpt"]
        s["ckpt"] = None
        if c is None:
            self._frame_error("CHECKPOINT_END_WITHOUT_BEGIN", arrival)
            return
        s["bids"], s["asks"] = c["bids"], c["asks"]
        problems = []
        if rec["levels_emitted"] != c["want"] or c["got"] != c["want"]:
            problems.append("CHECKPOINT_LEVEL_COUNT")
        if c["gap"]:
            problems.append("GAP_DURING_CHECKPOINT")
        if not c["complete"]:
            problems.append("BOOKMAP_SNAPSHOT_INCOMPLETE")
        if s["lost_state"] in ("LOST", "RESTORED_AWAIT_SNAPSHOT"):
            problems.append("AWAITING_SNAPSHOT_AFTER_RESTORE")
        if s["lost_state"] == "AWAIT_CHECKPOINT" and c["after_restore"]:
            s["lost_state"] = None
        crossed = self._crossed()
        if crossed:
            problems.append(crossed)
        if problems:
            self._invalidate("+".join(problems), arrival)
        else:
            self._set_valid(arrival, c["reason"])

    def _crossed(self):
        s = self.session
        if s["bids"] and s["asks"]:
            if max(s["bids"]) >= min(s["asks"]):
                return "CROSSED_OR_LOCKED_BOOK"
        return None

    def _set_valid(self, arrival, why):
        s = self.session
        if not s["book_valid"]:
            s["book_valid"], s["book_reason"] = True, None
            self._note("BOOK_STATE", arrival, {"state": "VALID", "via": why})
            self.event(kind="book_state", state="VALID", via=why, session_id=s["id"])

    def _invalidate(self, reason, arrival):
        s = self.session
        if s is None:
            return
        if s["ckpt"] is not None:
            s["ckpt"]["gap"] = True
        if s["book_valid"] or s["book_reason"] != reason:
            self._note("BOOK_STATE", arrival, {"state": "INVALID", "reason": reason})
            self.event(kind="book_state", state="INVALID", reason=reason, session_id=s["id"])
        s["book_valid"], s["book_reason"] = False, reason

    def _gap(self, cause, arrival, **kw):
        s = self.session
        self._note("GAP", arrival, dict(cause=cause, **kw))
        self.event(kind="gap", cause=cause, session_id=s["id"], **kw)
        self.manifest.append(dict(kind="gap", cause=cause, at_arrival_ns=arrival, session_id=s["id"], **kw))
        s["gap_times"].append(arrival)
        self._invalidate(cause, arrival)

    def _end_session(self, reason):
        s = self.session
        if s is None:
            return
        now = self.clock_ns()
        if s["authenticated"]:
            self._note("SESSION_END", now, {"reason": reason})
            lags = sorted(s["lags"]) or [0]
            self.manifest.append({"kind": "session_end", "session_id": s["id"], "t_ns": now, "reason": reason,
                                  "records": s["records"], "live_usable_records": s["live_records"],
                                  "connection_state": s["connection_state"],
                                  "last_heartbeat": s.get("last_heartbeat"),
                                  "lag_ns_p50": lags[len(lags) // 2], "lag_ns_max": lags[-1]})
            self.prev_session_facts = {"inventory": s["inventory"], "bookmap_version": self.bm_version,
                                       "segment": s["segment"], "ended_ns": now}
        self.event(kind="session_end", session_id=s["id"], reason=reason)
        self._close_file()
        self.session = None

    # -------------------------------------------------------------- files

    def _note(self, note, arrival, obj):
        if self.file is not None and not self.disk_paused:
            self.file.note(note, arrival, obj)

    def _open_file(self, arrival):
        s = self.session
        self.file_seq += 1
        hour = dt.datetime.fromtimestamp(arrival / 1e9, dt.timezone.utc)
        name = f"{hour.strftime('%Y%m%dT%H')}Z-s{s['id']:03d}-f{self.file_seq:04d}.bmrec"
        header = {"format": "tds-bmrec", "file_format_version": BS.FILE_FORMAT_VERSION,
                  "schema_version": BF.SCHEMA_VERSION, "run_id": self.run_id, "session_id": s["id"],
                  "file_seq": self.file_seq, "segment": s["segment"], "hour_utc": hour.strftime("%Y-%m-%dT%H"),
                  "instrument": s["hello_facts"], "jar_sha256": self.pin["jar_sha256"],
                  "bookmap_version": self.bm_version, "exchange_filters": self.filters or "UNKNOWN",
                  "tick_gate": self.tick_status, "clock_offset": self.clock or "UNKNOWN",
                  "addon_inventory": s["inventory"], "recorder_code_sha256": self.code_sha,
                  "connection_state": s["connection_state"],
                  "params": {"frame_max_bytes": BF.FRAME_MAX_BYTES, "clock_drift_invalid_ms": CLOCK_DRIFT_INVALID_MS,
                             "depth_recon_levels": BR.DEPTH_RECON_LEVELS,
                             "depth_recon_align_window_ms": BR.DEPTH_RECON_ALIGN_WINDOW_MS,
                             "depth_recon_min_match_fraction": BR.DEPTH_RECON_MIN_MATCH_FRACTION,
                             "agg_recon_volume_rel_tol": BR.AGG_RECON_VOLUME_REL_TOL}}
        self.file = BS.RecordingFile(os.path.join(self.run_dir, name), header)
        self.file.name = name
        self.file.hour = hour.strftime("%Y%m%dT%H")
        self.file.session_id = s["id"]
        bids = sorted(s["bids"].items(), reverse=True)
        asks = sorted(s["asks"].items())
        levels = [("b", p, q) for p, q in bids] + [("a", p, q) for p, q in asks]
        parts = max(1, (len(levels) + CHECKPOINT_NOTE_LEVELS - 1) // CHECKPOINT_NOTE_LEVELS)
        for i in range(parts):
            chunk = levels[i * CHECKPOINT_NOTE_LEVELS:(i + 1) * CHECKPOINT_NOTE_LEVELS]
            self.file.note("BOOK_CHECKPOINT", arrival, {
                "part": i + 1, "parts": parts, "book_state": "VALID" if s["book_valid"] else "INVALID",
                "reason": s["book_reason"], "last_capture_seq": s["last_capture_seq"],
                "last_forwarder_seq": s["last_fwd_seq"], "mode": BF.MODES.get(s["mode"], "UNKNOWN"),
                "lost_state": s["lost_state"],
                "bids": [[p, q] for side, p, q in chunk if side == "b"],
                "asks": [[p, q] for side, p, q in chunk if side == "a"]})
        self.event(kind="file_opened", file=name, session_id=s["id"])

    def _close_file(self):
        f = self.file
        if f is None:
            return
        self.file = None
        sha, size = f.close()
        self.manifest.append({"kind": "file_closed", "file": f.name, "sha256": sha, "bytes": size,
                              "records": f.records, "first_arrival_ns": f.first_arrival,
                              "last_arrival_ns": f.last_arrival, "modes": f.modes, "gaps": f.gaps,
                              "session_id": f.session_id, "segment": self.session["segment"] if self.session else None,
                              "exchange_tick": (self.filters or {}).get("tickSize", "UNKNOWN"),
                              "tick_gate": self.tick_status, "bookmap_version": self.bm_version})
        self.event(kind="file_closed", file=f.name, sha256=sha, bytes=size)

    # -------------------------------------------------------------- housekeeping

    def _housekeeping(self):
        now = self.clock_ns()
        s = self.session
        # hourly rotation
        if s and s["authenticated"] and self.file is not None:
            hour = dt.datetime.fromtimestamp(now / 1e9, dt.timezone.utc).strftime("%Y%m%dT%H")
            if hour != self.file.hour:
                self._close_file()
                self._open_file(now)
        if self.file is not None:
            self.file.flush()
        # silence
        if s and s["authenticated"] and not s["stale"] and (now - s["last_frame_ns"]) / 1e6 > STREAM_SILENCE_STALE_MS:
            s["stale"] = True
            self._note("STREAM_STATE", now, {"state": "STALE", "silence_ms": (now - s["last_frame_ns"]) // 10 ** 6})
            self.event(kind="stream_stale", session_id=s["id"])
        if s and s["authenticated"] and s["book_valid"]:
            crossed = self._crossed()
            if crossed:
                self._invalidate(crossed, now)
        # free space (BMREC-16)
        t = time.monotonic()
        if t - self.last_free_check >= FREE_SPACE_CHECK_S:
            self.last_free_check = t
            self._disk_check(now)
        # tick gate deadline
        if s and s["authenticated"] and self.tick_status != BR.MATCH and now > s["tick_deadline_ns"]:
            self.alert("TICK_GATE_ABORT", reason="pips/tick not verified within the first hour",
                       status=self.tick_status)
            self.exit_code = EXIT_TICK_GATE
        if self.rest:
            self._rest_schedule(now)
            for tag, res in self.rest.poll():
                self._rest_result(tag, res, now)
        if self.depth_samples is not None and s and s["authenticated"]:
            self.depth_samples.append((now / 1e6, self._top_levels()))
        if s and len(s["lags"]) > 50000:
            lags = sorted(s["lags"])
            self.event(kind="lag_stats", session_id=s["id"], n=len(lags), p50_ns=lags[len(lags) // 2],
                       p99_ns=lags[int(len(lags) * 0.99)], max_ns=lags[-1])
            s["lags"] = []

    def _disk_check(self, now):
        free = BS.free_bytes(self.root)
        if not self.disk_paused and free < BS.FREE_SPACE_FLOOR_BYTES:
            self.alert("DISK_BELOW_FLOOR", free_bytes=free, floor=BS.FREE_SPACE_FLOOR_BYTES)
            self._close_file()
            self.disk_paused = True
            self.disk_dropped = 0
            self.manifest.append({"kind": "gap", "cause": "DISK_FLOOR", "from_arrival_ns": now})
        elif self.disk_paused and free > BS.FREE_SPACE_RESUME_BYTES:
            self.manifest.append({"kind": "gap", "cause": "DISK_FLOOR_END", "to_arrival_ns": now,
                                  "records_not_written": self.disk_dropped})
            self.event(kind="disk_resumed", free_bytes=free, records_not_written=self.disk_dropped)
            self.disk_paused = False
            if self.session and self.session["authenticated"]:
                self._open_file(now)

    def _top_levels(self, n=BR.DEPTH_RECON_LEVELS * 3):
        s = self.session
        return {"bids": [(p, s["bids"][p]) for p in heapq.nlargest(n, s["bids"])],
                "asks": [(p, s["asks"][p]) for p in heapq.nsmallest(n, s["asks"])]}

    # -------------------------------------------------------------- REST schedule and results

    def _due(self, key, now, every_s):
        if now >= self.next_due.get(key, 0):
            self.next_due[key] = now + int(every_s * 1e9)
            return True
        return False

    def _rest_schedule(self, now):
        s = self.session
        if self._due("time", now, BR.CLOCK_OFFSET_INTERVAL_S):
            self.rest.submit("time", "/fapi/v1/time")
        if s and s["authenticated"] and s.get("symbol"):
            every = TICK_RETRY_S if self.tick_status != BR.MATCH else EXCHANGEINFO_REFRESH_S
            if self._due("exchangeInfo", now, every):
                self.rest.submit("exchangeInfo", "/fapi/v1/exchangeInfo")
            if (s["mode"] == BF.LIVE and self._due("depth", now, BR.DEPTH_RECON_INTERVAL_S)
                    and self.rest.submit("depth", "/fapi/v1/depth",
                                         {"symbol": s["symbol"], "limit": BR.DEPTH_RECON_REST_LIMIT})):
                self.depth_samples = [(now / 1e6, self._top_levels())]
                self.depth_book_valid_at_start = s["book_valid"]
            if s["mode"] == BF.LIVE and self.clock and self._due("aggTrades", now, BR.AGG_RECON_INTERVAL_S):
                end_server = int(now / 1e6 + self.clock["offset_ms"]) - BR.AGG_RECON_LAG_S * 1000
                start_server = end_server - BR.AGG_RECON_WINDOW_S * 1000
                self.agg_window = (start_server, end_server)
                self.rest.submit("aggTrades", "/fapi/v1/aggTrades",
                                 {"symbol": s["symbol"], "startTime": start_server, "endTime": end_server,
                                  "limit": 1000})

    def _rest_event(self, **kw):
        self.event(**kw)

    def _rest_result(self, tag, res, now):
        s = self.session
        if tag == "time":
            if res["status"] == "OK":
                self.clock = dict(BR.clock_offset(res["data"]["serverTime"], res["t_send"], res["t_recv"]),
                                  measured_at_ns=now)
                self._note("CLOCK", now, self.clock)
            return
        if tag == "exchangeInfo":
            if not (s and s["authenticated"]):
                return
            filters = BR.exchange_filters(res["data"], s["symbol"]) if res["status"] == "OK" else None
            status, detail = BR.tick_gate(s["hello"]["pips"], s["hello"]["size_multiplier"], filters)
            if filters and self.filters and filters != self.filters:
                self.event(kind="exchange_filters_changed", previous=self.filters, current=filters)
            if filters:
                self.filters = filters
            if status != BR.UNKNOWN:
                self.tick_status = status
            self._note("EXCHANGE_FILTERS", now, {"filters": filters, "status": status, "detail": detail})
            self.event(kind="tick_gate", status=status, detail=detail)
            if status == BR.MISMATCH:
                self.alert("TICK_GATE_ABORT", reason="pips/sizeMultiplier do not match exchangeInfo", detail=detail)
                self.exit_code = EXIT_TICK_GATE
            return
        if tag == "depth":
            samples, self.depth_samples = self.depth_samples, None
            if not (s and s["authenticated"]):
                return
            result, detail = BR.UNKNOWN, {}
            if res["status"] != "OK":
                detail = {"reason": res["reason"]}
            elif not (s["book_valid"] and getattr(self, "depth_book_valid_at_start", False)):
                detail = {"reason": "book not VALID"}
            elif not self.clock:
                detail = {"reason": "clock offset unknown"}
            else:
                target_local = res["data"]["T"] - self.clock["offset_ms"]
                best = BR.pick_sample(samples or [], target_local)
                if best is None:
                    detail = {"reason": "no sample within alignment window"}
                else:
                    result, detail = BR.compare_depth(res["data"], best[2], s["hello"]["pips"],
                                                      s["hello"]["size_multiplier"])
                    detail["align_ms"] = round(best[0], 3)
            self._note("RECON_DEPTH", now, {"result": result, "detail": detail})
            self.event(kind="recon_depth", result=result, detail=detail)
            if result == BR.MISMATCH:
                self.depth_fail_streak += 1
                if self.depth_fail_streak >= BR.DEPTH_RECON_FAIL_STREAK_INVALID:
                    self.alert("DEPTH_RECON_FAIL_STREAK", streak=self.depth_fail_streak)
                    self._invalidate("DEPTH_RECON_FAIL_STREAK", now)
            elif result == BR.MATCH:
                self.depth_fail_streak = 0
            return
        if tag == "aggTrades":
            if not (s and s["authenticated"]):
                return
            start, end = getattr(self, "agg_window", (None, None))
            result, detail = BR.UNKNOWN, {}
            if res["status"] != "OK" or not self.clock:
                detail = {"reason": res["reason"] if res["status"] != "OK" else "clock offset unknown"}
            else:
                off = self.clock["offset_ms"]
                gaps = [g for g in s["gap_times"] if start <= g / 1e6 + off <= end + 60_000]
                if gaps:
                    detail = {"reason": "gap in window"}
                else:
                    recorded = [(b, q) for t_ns, b, q in s["trades"] if start <= t_ns / 1e6 + off <= end]
                    result, detail = BR.compare_aggtrades(res["data"], recorded, s["hello"]["size_multiplier"])
            detail["window_server_ms"] = [start, end]
            self._note("RECON_AGGTRADES", now, {"result": result, "detail": detail})
            self.event(kind="recon_aggtrades", result=result, detail=detail)


def _redact_sid(sddl):
    """Event logs carry no user identifiers (BMREC-22): the owner SID becomes OWNER."""
    import re
    return re.sub(r"S-1-5-21-[0-9-]+", "OWNER", sddl or "")


# ---------------------------------------------------------------- backup (BMREC-23) and ledger (BMREC-21)


def backup(cfg, log=print):
    root, dst_root = cfg["recordings_root"], cfg.get("backup_root")
    if not dst_root:
        raise SystemExit("no backup_root configured")
    BS.refuse_if_in_worktree(dst_root, "backup root")
    import bookmap_pipe as BP
    why = ensure_private_dir(dst_root, BP)
    if why:
        raise SystemExit(f"backup root refused: {why}")
    results, ok = [], True
    for run in sorted(os.listdir(root)):
        rd = os.path.join(root, run)
        man = os.path.join(rd, "manifest.jsonl")
        if not os.path.isfile(man):
            continue
        dd = os.path.join(dst_root, run)
        os.makedirs(dd, exist_ok=True)
        for e in BS.read_jsonl(man):
            if e.get("kind") not in ("file_closed", "recovered_close"):
                continue
            src, dst = os.path.join(rd, e["file"]), os.path.join(dd, e["file"])
            if os.path.exists(dst):
                got = BS.sha256_file(dst)
                status = "ALREADY_OK" if got == e["sha256"] else "BACKUP_HASH_MISMATCH"
            else:
                src_sha = BS.sha256_file(src)
                if src_sha != e["sha256"]:
                    status = "SOURCE_HASH_MISMATCH"
                else:
                    import shutil
                    shutil.copyfile(src, dst + ".partial")
                    got = BS.sha256_file(dst + ".partial")
                    if got == e["sha256"]:
                        os.rename(dst + ".partial", dst)
                        BS.make_read_only(dst)
                        status = "COPIED_OK"
                    else:
                        status = "COPY_HASH_MISMATCH"
            if status not in ("ALREADY_OK", "COPIED_OK"):
                ok = False
            results.append({"run": run, "file": e["file"], "status": status, "sha256": e["sha256"]})
        # the manifest itself: a dated snapshot copy (never overwrites a previous snapshot)
        stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
        import shutil
        shutil.copyfile(man, os.path.join(dd, f"manifest.{stamp}.jsonl"))
    log_path = os.path.join(dst_root, "backup-log.jsonl")
    with open(log_path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({"at_utc": utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"), "ok": ok, "files": results},
                            sort_keys=True) + "\n")
    for r in results:
        log(f"{r['status']:<22} {r['run']}/{r['file']}")
    if not ok:
        print("ALERT: backup verification failed (BMREC-23)", file=sys.stderr)
    return ok


def ledger_manifests(cfg, path=MANIFEST_LEDGER, log=print):
    root = cfg["recordings_root"]
    known = set()
    if os.path.isfile(path):
        for e in BS.read_jsonl(path):
            known.add((e["run_id"], e["manifest_sha256"]))
    added = 0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        for run in sorted(os.listdir(root)):
            man = os.path.join(root, run, "manifest.jsonl")
            if not os.path.isfile(man):
                continue
            sha = BS.sha256_file(man)
            if (run, sha) in known:
                continue
            entries = BS.read_jsonl(man)
            closed = [e for e in entries if e.get("kind") in ("file_closed", "recovered_close")]
            fh.write(json.dumps({"run_id": run, "manifest_sha256": sha, "manifest_lines": len(entries),
                                 "closed_files": len(closed),
                                 "run_ended": any(e.get("kind") == "run_end" for e in entries),
                                 "hashed_at_utc": utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")}, sort_keys=True) + "\n")
            added += 1
            log(f"ledgered {run} manifest {sha}")
    return added


def record_deletion(cfg, rel_file, reason, path=MANIFEST_LEDGER):
    """BMREC-24: the ledger entry an owner writes BEFORE deleting a recording file by hand. This function never
    deletes anything: deletion stays a manual owner action, at whole-file granularity, and is a research event."""
    if not reason:
        raise SystemExit("--reason is required: dropping recorded data is a selection event (CLAUDE.md §9, §43)")
    p = os.path.join(cfg["recordings_root"], rel_file)
    if not os.path.isfile(p):
        raise SystemExit(f"no such recording file: {rel_file}")
    entry = {"kind": "deletion", "file": rel_file.replace("\\", "/"), "sha256": BS.sha256_file(p),
             "bytes": os.path.getsize(p), "reason": reason,
             "recorded_at_utc": utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--stop", action="store_true")
    ap.add_argument("--preregister-holdout", action="store_true")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--holdout-fraction", type=float, default=0.25)
    ap.add_argument("--log-exposure", metavar="ISO_WEEK")
    ap.add_argument("--reason")
    ap.add_argument("--verify-run", metavar="RUN_ID")
    ap.add_argument("--backup", action="store_true")
    ap.add_argument("--ledger-manifests", action="store_true")
    ap.add_argument("--record-deletion", metavar="RUN_ID/FILE")
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    if a.stop:
        os.makedirs(os.path.dirname(STOP_FILE), exist_ok=True)
        with open(STOP_FILE, "w", encoding="utf-8") as fh:
            fh.write(utc_now().isoformat())
        print("stop requested")
        return 0
    if a.preregister_holdout:
        doc = preregister_holdout(_repo_path(cfg, "holdout_calendar"), seed=a.seed, fraction=a.holdout_fraction)
        print(json.dumps({k: doc[k] for k in ("registered_at_utc", "first_week", "seed", "holdout_fraction")}))
        print("Now commit docs/research/bookmap-holdout-calendar.json before starting the recorder.")
        return 0
    if a.log_exposure:
        log_exposure(a.log_exposure, a.reason)
        return 0
    if a.verify_run:
        ok, lines = BS.verify_run(os.path.join(cfg["recordings_root"], a.verify_run))
        print("\n".join(lines))
        print("VERIFY: " + ("OK" if ok else "FAILED"))
        return 0 if ok else 1
    if a.backup:
        return 0 if backup(cfg) else 1
    if a.ledger_manifests:
        ledger_manifests(cfg)
        return 0
    if a.record_deletion:
        print(json.dumps(record_deletion(cfg, a.record_deletion, a.reason)))
        print("Ledgered. Commit docs/research/bookmap-manifest-ledger.jsonl BEFORE deleting the file by hand.")
        return 0
    return Recorder(cfg).run()


if __name__ == "__main__":
    sys.exit(main())
