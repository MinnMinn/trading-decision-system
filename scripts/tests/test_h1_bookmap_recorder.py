"""Stage H1 Bookmap recorder: validator, pipe security, authentication, files, manifest, storage location,
outbound allowlist, static import rules, live-usability, and the Java allowlist checker's fixtures.

Governing: docs/security/2026-09-26-bookmap-recorder-h1.md (BMREC-*), docs/contracts/bookmap-recorder-frames.md,
docs/plans/2026-09-26-heatmap-realtime-plan.md stage H1. Windows-only where the pipe is involved (plan §0).
"""
import ast
import io
import json
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import bookmap_frames as BF  # noqa: E402
import bookmap_rest as BR  # noqa: E402
import bookmap_store as BS  # noqa: E402
import bookmap_recorder as BRC  # noqa: E402

try:
    import bookmap_pipe as BP
except ImportError:  # pragma: no cover
    BP = None

BM = os.path.join(ROOT, "integrations", "bookmap")
CONTRACT = os.path.join(ROOT, "docs", "contracts", "bookmap-recorder-frames.md")
JDK = os.environ.get("TDS_JDK_HOME", r"C:\Program Files\Microsoft\jdk-21.0.12.101-hotspot")
LIB = os.environ.get("TDS_BOOKMAP_LIB", r"C:\Program Files\Bookmap\lib")
TMP_BASE = os.environ.get("TMP") or tempfile.gettempdir()
CODE, SRC = "a" * 64, "b" * 64
PROGRAM_FILES = os.environ.get("ProgramFiles", r"C:\Program Files")


def tmpdir(test):
    d = tempfile.mkdtemp(prefix="h1-test-", dir=TMP_BASE)

    def _rm():
        for r, _ds, fs in os.walk(d):
            for f in fs:
                try:
                    os.chmod(os.path.join(r, f), stat.S_IWRITE | stat.S_IREAD)
                except OSError:
                    pass
        shutil.rmtree(d, ignore_errors=True)
    test.addCleanup(_rm)
    return d


def make_env(test, *, pinned_exe=None, pipe_name=None, jar_bytes=b"fake-jar"):
    """Temp recordings root (outside the worktree), a fake jar + matching pin, and a committed pre-registration."""
    base = tmpdir(test)
    jar = os.path.join(base, "addon.jar")
    with open(jar, "wb") as fh:
        fh.write(jar_bytes)
    pin = {"jar_sha256": BS.sha256_file(jar), "code_sha256": CODE, "source_sha256": SRC, "check": {"result": "PASS"}}
    pin_path = os.path.join(base, "pin.json")
    with open(pin_path, "w", encoding="utf-8") as fh:
        json.dump(pin, fh)
    repo = os.path.join(base, "prereg-repo")
    os.makedirs(repo)
    subprocess.run(["git", "-C", repo, "init", "-q"], check=True)
    cal = os.path.join(repo, "cal.json")
    BRC.preregister_holdout(cal, seed=7)
    subprocess.run(["git", "-C", repo, "add", "."], check=True)
    subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@invalid", "commit", "-q", "-m",
                    "p"], check=True)
    cfg = {"pipe_name": pipe_name or rf"\\.\pipe\tds-h1-test-{os.getpid()}-{time.time_ns()}",
           "recordings_root": os.path.join(base, "rec"), "backup_root": os.path.join(base, "backup"),
           "pinned_client_exe": pinned_exe or os.path.join(PROGRAM_FILES, "Bookmap", "Bookmap.exe"),
           "addon_jar_path": jar, "pin_file": pin_path, "holdout_calendar": cal, "bookmap_jar": "",
           "addon_inventory_dirs": [], "rest_enabled": False}
    return base, cfg, pin


def bare_recorder(test, cfg=None, pin=None):
    """A Recorder with its run directory and logs open, bypassing preflight (unit-level session tests)."""
    if cfg is None:
        _b, cfg, pin = make_env(test)
    r = BRC.Recorder(cfg)
    os.makedirs(cfg["recordings_root"], exist_ok=True)
    r.run_id = "run-test"
    r.run_dir = os.path.join(cfg["recordings_root"], r.run_id)
    os.makedirs(r.run_dir)
    r.events = BS.JsonLines(os.path.join(r.run_dir, "events.jsonl"))
    r.manifest = BS.JsonLines(os.path.join(r.run_dir, "manifest.jsonl"))
    r.pin = pin
    test.addCleanup(lambda: (r.events and r.events.close(), r.manifest and r.manifest.close(),
                             r.file and r.file.close()))
    return r


def start_session(r, pid=4242, exe="Bookmap.exe"):
    r.session_seq += 1
    r.session = r._new_session(pid, exe)
    return r.session


def hello(seq=1, code=CODE, src=SRC, **kw):
    return BF.encode(BF.HELLO, seq, recv_ns=10, send_ns=10, body=BF.hello_body(code_sha256=code, source_sha256=src,
                                                                                **kw))


def depth(seq, is_bid, price, size, mode=BF.LIVE):
    return BF.encode(BF.DEPTH, seq, mode=mode, recv_ns=time.time_ns(), send_ns=time.time_ns(),
                     body=BF.depth_body(is_bid, price, size))


def checkpoint(fwd_seq, capture_at, bids, asks, complete=True, reason=1):
    out = BF.encode(BF.CHECKPOINT_BEGIN, fwd_seq, recv_ns=5, send_ns=5,
                    body=BF.checkpoint_begin_body(reason, complete, len(bids), len(asks), capture_at))
    s = fwd_seq
    for p, q in bids:
        s += 1
        out += BF.encode(BF.CHECKPOINT_LEVEL, s, recv_ns=5, send_ns=5, body=BF.checkpoint_level_body(True, p, q))
    for p, q in asks:
        s += 1
        out += BF.encode(BF.CHECKPOINT_LEVEL, s, recv_ns=5, send_ns=5, body=BF.checkpoint_level_body(False, p, q))
    s += 1
    out += BF.encode(BF.CHECKPOINT_END, s, recv_ns=5, send_ns=5, body=struct.pack(">I", len(bids) + len(asks)))
    return out, s


def run_records(run_dir):
    out = []
    for f in sorted(os.listdir(run_dir)):
        if f.endswith(".bmrec"):
            out += BS.read_records(os.path.join(run_dir, f))["records"]
    return out


def notes_of(records, name=None):
    out = []
    for origin, _a, payload in records:
        if origin == BS.ORIGIN_NOTE:
            n, obj = BS.decode_note(payload)
            if name is None or n == name:
                out.append((n, obj))
    return out


def addon_records(records):
    return [BF.parse_payload(p) for o, _a, p in records if o == BS.ORIGIN_ADDON]


# =====================================================================================================================
class TestContractParameters(unittest.TestCase):
    """The contract's parameter table is the single source; code constants must equal it."""

    def test_code_constants_equal_the_contract_table(self):
        with open(CONTRACT, encoding="utf-8") as fh:
            text = fh.read()
        table = dict(re.findall(r"^\| `([A-Z0-9_]+)` \| ([0-9.]+) \|", text, flags=re.M))
        code = {"SCHEMA_VERSION": BF.SCHEMA_VERSION, "FILE_FORMAT_VERSION": BS.FILE_FORMAT_VERSION,
                "FRAME_MAX_BYTES": BF.FRAME_MAX_BYTES, "STRING_MAX_BYTES": BF.STRING_MAX_BYTES,
                "NOTE_MAX_BYTES": BS.NOTE_MAX_BYTES, "QUEUE_CAPACITY": BF.QUEUE_CAPACITY,
                "HEARTBEAT_INTERVAL_MS": BF.HEARTBEAT_INTERVAL_MS,
                "TIME_RECORD_MIN_INTERVAL_NS": BF.TIME_RECORD_MIN_INTERVAL_NS,
                "RECONNECT_BACKOFF_INITIAL_MS": BF.RECONNECT_BACKOFF_INITIAL_MS,
                "RECONNECT_BACKOFF_CAP_MS": BF.RECONNECT_BACKOFF_CAP_MS, "STOP_JOIN_TIMEOUT_MS": BF.STOP_JOIN_TIMEOUT_MS,
                "MAX_CONSECUTIVE_INVALID_FRAMES": BF.MAX_CONSECUTIVE_INVALID_FRAMES,
                "STREAM_SILENCE_STALE_MS": BRC.STREAM_SILENCE_STALE_MS,
                "CLOCK_DRIFT_INVALID_MS": BRC.CLOCK_DRIFT_INVALID_MS,
                "FREE_SPACE_FLOOR_BYTES": BS.FREE_SPACE_FLOOR_BYTES,
                "FREE_SPACE_RESUME_BYTES": BS.FREE_SPACE_RESUME_BYTES}
        for name in ("DEPTH_RECON_INTERVAL_S", "DEPTH_RECON_REST_LIMIT", "DEPTH_RECON_LEVELS", "DEPTH_RECON_SAMPLE_MS",
                     "DEPTH_RECON_ALIGN_WINDOW_MS", "DEPTH_RECON_MIN_MATCH_FRACTION",
                     "DEPTH_RECON_FAIL_STREAK_INVALID", "AGG_RECON_INTERVAL_S", "AGG_RECON_WINDOW_S",
                     "AGG_RECON_LAG_S", "AGG_RECON_VOLUME_REL_TOL", "CLOCK_OFFSET_INTERVAL_S", "REST_BUDGET_FRACTION",
                     "REST_IP_HEADROOM_FRACTION", "REST_TIMEOUT_S", "REST_429_BACKOFF_INITIAL_S",
                     "REST_429_BACKOFF_CAP_S", "WEIGHT_DEPTH_LIMIT_20", "WEIGHT_AGGTRADES", "WEIGHT_EXCHANGEINFO",
                     "WEIGHT_TIME", "TICK_GATE_DEADLINE_S"):
            code[name] = getattr(BR, name)
        self.assertEqual(set(table), set(code), "contract table and code disagree on WHICH parameters exist")
        for k, v in code.items():
            self.assertEqual(float(table[k]), float(v), k)

    def test_java_constants_equal_the_contract(self):
        with open(os.path.join(BM, "src", "tds", "bookmap", "recorder", "Frames.java"), encoding="utf-8") as fh:
            java = fh.read()
        for name, val in (("SCHEMA_VERSION", BF.SCHEMA_VERSION), ("FRAME_MAX_BYTES", BF.FRAME_MAX_BYTES),
                          ("STRING_MAX_BYTES", BF.STRING_MAX_BYTES), ("QUEUE_CAPACITY", BF.QUEUE_CAPACITY),
                          ("HEARTBEAT_INTERVAL_MS", BF.HEARTBEAT_INTERVAL_MS),
                          ("TIME_RECORD_MIN_INTERVAL_NS", BF.TIME_RECORD_MIN_INTERVAL_NS),
                          ("RECONNECT_BACKOFF_INITIAL_MS", BF.RECONNECT_BACKOFF_INITIAL_MS),
                          ("RECONNECT_BACKOFF_CAP_MS", BF.RECONNECT_BACKOFF_CAP_MS),
                          ("STOP_JOIN_TIMEOUT_MS", BF.STOP_JOIN_TIMEOUT_MS)):
            m = re.search(rf"\b{name}\s*=\s*([0-9_]+)L?;", java)
            self.assertIsNotNone(m, name)
            self.assertEqual(int(m.group(1).replace("_", "")), val, name)
        self.assertIn('PIPE_PATH = "\\\\\\\\.\\\\pipe\\\\tds-bookmap-recorder-h1"', java)
        self.assertEqual(BF.PIPE_NAME, r"\\.\pipe\tds-bookmap-recorder-h1")


# =====================================================================================================================
class TestValidator(unittest.TestCase):
    """BMREC-15: length cap before allocation, closed enums, exact schema, finite floats, typed fields."""

    def feed_one(self, data):
        return list(BF.FrameReader().feed(data))

    def test_valid_frames_round_trip(self):
        items = self.feed_one(hello() + depth(1, True, 100, 5))
        self.assertEqual([i[0] for i in items], ["frame", "frame"])
        self.assertEqual(items[1][2]["price_level"], 100)

    def test_oversize_length_closes_before_allocation(self):
        r = BF.FrameReader()
        items = list(r.feed(struct.pack(">I", BF.FRAME_MAX_BYTES + 1)))  # only 4 bytes delivered
        self.assertEqual(items, [("error", "FRAME_TOO_LARGE")])
        self.assertTrue(r.dead)
        self.assertEqual(list(r.feed(b"x" * 100)), [])  # nothing more is ever parsed on this connection

    def test_zero_length_is_fatal(self):
        self.assertEqual(self.feed_one(struct.pack(">I", 0)), [("error", "ZERO_LENGTH")])

    def test_nan_and_inf_are_rejected(self):
        nan_trade = BF.encode(BF.TRADE, 1, recv_ns=1, send_ns=1, body=struct.pack(">diBBBB", float("nan"), 1, 1, 0, 0, 0))
        inf_trade = BF.encode(BF.TRADE, 1, recv_ns=1, send_ns=1, body=struct.pack(">diBBBB", float("inf"), 1, 1, 0, 0, 0))
        inf_pips = BF.encode(BF.HELLO, 1, recv_ns=1, send_ns=1,
                             body=BF.hello_body(code_sha256=CODE, source_sha256=SRC, pips=float("inf")))
        for f in (nan_trade, inf_trade, inf_pips):
            self.assertEqual(self.feed_one(f), [("error", "NON_FINITE")])

    def test_unknown_type_and_schema_mismatch(self):
        self.assertEqual(self.feed_one(BF.encode(99, 1, recv_ns=1, send_ns=1)), [("error", "UNKNOWN_TYPE")])
        self.assertEqual(self.feed_one(BF.encode(BF.TIME, 1, recv_ns=1, send_ns=1, schema=2)),
                         [("error", "SCHEMA_MISMATCH")])

    def test_field_ranges(self):
        cases = {
            "NEGATIVE_SIZE": BF.encode(BF.DEPTH, 1, recv_ns=1, send_ns=1, body=struct.pack(">Bii", 1, 5, -1)),
            "NON_POSITIVE_TRADE_SIZE": BF.encode(BF.TRADE, 1, recv_ns=1, send_ns=1, body=BF.trade_body(1.0, 0)),
            "BAD_BOOL": BF.encode(BF.DEPTH, 1, recv_ns=1, send_ns=1, body=struct.pack(">Bii", 2, 5, 1)),
            "BAD_MODE": BF.encode(BF.TIME, 1, mode=9, recv_ns=1, send_ns=1),
            "TRUNCATED_BODY": BF.encode(BF.DEPTH, 1, recv_ns=1, send_ns=1, body=b"\x01\x00"),
            "TRAILING_BYTES": BF.encode(BF.TIME, 1, recv_ns=1, send_ns=1, body=b"\x00"),
            "BAD_CONNECTION_STATE": BF.encode(BF.CONNECTION, 1, recv_ns=1, send_ns=1, body=b"\x09"),
            "BAD_SEQ": BF.encode(BF.TIME, 0, recv_ns=1, send_ns=1),
            "STRING_TOO_LONG": BF.encode(BF.HELLO, 1, recv_ns=1, send_ns=1,
                                         body=BF.hello_body(code_sha256=CODE, source_sha256=SRC, alias="X" * 300)),
            "CONTROL_CHAR": BF.encode(BF.HELLO, 1, recv_ns=1, send_ns=1,
                                      body=BF.hello_body(code_sha256=CODE, source_sha256=SRC, alias="A\nB")),
        }
        for code, frame in cases.items():
            self.assertEqual(self.feed_one(frame), [("error", code)], code)

    def test_connection_record_has_no_free_text_field(self):
        """BMREC-06: a CONNECTION body is exactly one enum byte."""
        ok = BF.encode(BF.CONNECTION, 1, recv_ns=1, send_ns=1, body=b"\x01")
        self.assertEqual(self.feed_one(ok)[0][2]["state"], "LOST")
        self.assertEqual(self.feed_one(BF.encode(BF.CONNECTION, 1, recv_ns=1, send_ns=1, body=b"\x01abc")),
                         [("error", "TRAILING_BYTES")])

    def test_validator_never_deserializes_objects(self):
        with open(os.path.join(ROOT, "scripts", "bookmap_frames.py"), encoding="utf-8") as fh:
            src = fh.read()
        tree = ast.parse(src)
        names = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
        mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual((names | mods) - {None}, {"math", "struct"})


# =====================================================================================================================
class TestSessionProcessing(unittest.TestCase):
    """Recorder session logic, fed through the real FrameReader (no pipe)."""

    def test_hello_code_sha_mismatch_writes_zero_records(self):
        r = bare_recorder(self)
        start_session(r)
        self.assertFalse(r._feed(hello(code="c" * 64) + depth(1, True, 100, 5), time.time_ns()))
        self.assertEqual([f for f in os.listdir(r.run_dir) if f.endswith(".bmrec")], [])
        r.manifest.close()
        man = BS.read_jsonl(os.path.join(r.run_dir, "manifest.jsonl"))
        self.assertEqual([e["reason"] for e in man if e["kind"] == "security_event"], ["HELLO_PIN_MISMATCH"])

    def test_first_frame_must_be_hello(self):
        r = bare_recorder(self)
        start_session(r)
        self.assertFalse(r._feed(depth(1, True, 100, 5), time.time_ns()))
        self.assertEqual([f for f in os.listdir(r.run_dir) if f.endswith(".bmrec")], [])

    def _accepted(self):
        r = bare_recorder(self)
        start_session(r)
        self.assertTrue(r._feed(hello(), time.time_ns()))
        return r

    def test_checkpoint_makes_book_valid_and_counter_gap_invalidates(self):
        r = self._accepted()
        ck, last = checkpoint(2, 10, [(99, 5), (98, 1)], [(101, 4)])
        self.assertTrue(r._feed(ck, time.time_ns()))
        self.assertTrue(r.session["book_valid"])
        self.assertTrue(r._feed(depth(11, True, 99, 6), time.time_ns()))   # contiguous
        self.assertTrue(r.session["book_valid"])
        self.assertTrue(r._feed(depth(13, True, 99, 7), time.time_ns()))   # 12 missing
        self.assertFalse(r.session["book_valid"])
        r._end_session("TEST")
        recs = run_records(r.run_dir)
        gaps = notes_of(recs, "GAP")
        self.assertEqual(gaps[0][1]["cause"], "CAPTURE_SEQ_GAP")
        self.assertEqual((gaps[0][1]["expected"], gaps[0][1]["got"]), (12, 13))
        r.manifest.close()
        man = BS.read_jsonl(os.path.join(r.run_dir, "manifest.jsonl"))
        self.assertTrue(any(e["kind"] == "gap" and e["cause"] == "CAPTURE_SEQ_GAP" for e in man))

    def test_incomplete_snapshot_checkpoint_stays_invalid(self):
        r = self._accepted()
        ck, _ = checkpoint(2, 1, [(99, 5)], [(101, 4)], complete=False)
        r._feed(ck, time.time_ns())
        self.assertFalse(r.session["book_valid"])
        self.assertIn("BOOKMAP_SNAPSHOT_INCOMPLETE", r.session["book_reason"])

    def test_crossed_book_is_invalid(self):
        r = self._accepted()
        ck, _ = checkpoint(2, 1, [(101, 5)], [(100, 4)])
        r._feed(ck, time.time_ns())
        self.assertFalse(r.session["book_valid"])
        self.assertIn("CROSSED_OR_LOCKED_BOOK", r.session["book_reason"])

    def test_validation_failure_is_a_reason_code_never_a_market_record(self):
        r = self._accepted()
        bad = BF.encode(BF.TRADE, 1, recv_ns=1, send_ns=1, body=struct.pack(">diBBBB", float("nan"), 1, 1, 0, 0, 0))
        self.assertTrue(r._feed(bad, time.time_ns()))
        r._end_session("TEST")
        recs = run_records(r.run_dir)
        self.assertEqual(addon_records(recs), [])  # the hello is not written; the bad trade is not written
        self.assertEqual(notes_of(recs, "VALIDATION_FAILURE")[0][1], {"reason": "NON_FINITE"})

    def test_too_many_invalid_frames_close_the_connection(self):
        r = self._accepted()
        bad = BF.encode(99, 1, recv_ns=1, send_ns=1)
        self.assertFalse(r._feed(bad * BF.MAX_CONSECUTIVE_INVALID_FRAMES, time.time_ns()))

    def test_reconnect_is_two_sessions_and_one_gap(self):
        """BMREC-14."""
        r = self._accepted()
        r._end_session("CLIENT_DISCONNECTED")
        start_session(r)
        self.assertTrue(r._feed(hello(), time.time_ns()))
        self.assertFalse(r.session["book_valid"])  # a new session starts INVALID
        r._end_session("TEST")
        r.manifest.close()
        man = BS.read_jsonl(os.path.join(r.run_dir, "manifest.jsonl"))
        self.assertEqual(sum(1 for e in man if e["kind"] == "session_start"), 2)
        self.assertEqual([e["cause"] for e in man if e["kind"] == "gap"], ["SESSION_GAP"])

    def test_connection_lost_needs_restore_snapshot_and_checkpoint(self):
        r = self._accepted()
        ck, last = checkpoint(2, 1, [(99, 5)], [(101, 4)])
        r._feed(ck, time.time_ns())
        self.assertTrue(r.session["book_valid"])
        conn = lambda seq, st: BF.encode(BF.CONNECTION, seq, recv_ns=1, send_ns=1, body=bytes([st]))  # noqa: E731
        r._feed(conn(2, 1), time.time_ns())  # LOST
        self.assertFalse(r.session["book_valid"])
        ck2, last = checkpoint(last + 1, 2, [(99, 5)], [(101, 4)], reason=2)
        r._feed(ck2, time.time_ns())  # a checkpoint before RESTORED+snapshot does not count
        self.assertFalse(r.session["book_valid"])
        r._feed(conn(3, 2), time.time_ns())  # RESTORED
        r._feed(BF.encode(BF.SNAPSHOT_END, 4, recv_ns=1, send_ns=1), time.time_ns())
        ck3, _ = checkpoint(last + 1, 4, [(99, 5)], [(101, 4)], reason=3)
        r._feed(ck3, time.time_ns())
        self.assertTrue(r.session["book_valid"])

    def test_monitor_unavailable_means_connection_state_unknown(self):
        r = self._accepted()
        r._feed(BF.encode(BF.CONNECTION, 1, recv_ns=1, send_ns=1, body=b"\x06"), time.time_ns())
        self.assertEqual(r.session["connection_state"], "UNKNOWN")

    def test_every_depth_delta_is_recorded_at_full_resolution(self):
        """Plan §1.0: no bucketing, no coalescing -- 500 deltas on one level are 500 records."""
        r = self._accepted()
        ck, _ = checkpoint(2, 0, [(99, 5)], [(101, 4)])
        r._feed(ck, time.time_ns())
        data = b"".join(depth(i, True, 99, i) for i in range(1, 501))
        r._feed(data, time.time_ns())
        r._end_session("TEST")
        recs = [x for x in addon_records(run_records(r.run_dir)) if x["type"] == BF.DEPTH]
        self.assertEqual([x["size"] for x in recs], list(range(1, 501)))

    def test_disk_floor_stops_writing_records_gap_and_never_deletes(self):
        """BMREC-16."""
        r = self._accepted()
        r._feed(depth(1, True, 99, 1), time.time_ns())
        with mock.patch.object(BS, "free_bytes", return_value=1024):
            r._disk_check(time.time_ns())
        self.assertTrue(r.disk_paused)
        files_before = sorted(os.listdir(r.run_dir))
        r._feed(depth(2, True, 99, 2), time.time_ns())
        self.assertEqual(r.disk_dropped, 1)
        with mock.patch.object(BS, "free_bytes", return_value=BS.FREE_SPACE_RESUME_BYTES + 1):
            r._disk_check(time.time_ns())
        self.assertFalse(r.disk_paused)
        r._end_session("TEST")
        r.events.close()
        r.manifest.close()
        man = BS.read_jsonl(os.path.join(r.run_dir, "manifest.jsonl"))
        self.assertEqual([e["cause"] for e in man if e["kind"] == "gap"], ["DISK_FLOOR", "DISK_FLOOR_END"])
        for f in files_before:
            self.assertTrue(os.path.exists(os.path.join(r.run_dir, f)), f)
        ev = BS.read_jsonl(os.path.join(r.run_dir, "events.jsonl"))
        self.assertTrue(any(e["kind"] == "alert" and e["what"] == "DISK_BELOW_FLOOR" for e in ev))

    def test_addon_inventory_and_bookmap_version_changes_are_logged(self):
        """BMREC-08 (a jar appears in an add-on directory between sessions) and BMREC-10 (version = segment)."""
        base, cfg, pin = make_env(self)
        addons = os.path.join(base, "addons")
        os.makedirs(addons)
        cfg["addon_inventory_dirs"] = [{"label": "owner-manual-addons", "path": addons}]
        cfg["bookmap_jar"] = os.path.join(base, "Bookmap.jar")

        def fake_bookmap(version):
            with zipfile.ZipFile(cfg["bookmap_jar"], "w") as z:
                z.writestr("META-INF/MANIFEST.MF", f"Manifest-Version: 1.0\nBookMap-version: {version}\n")
        fake_bookmap("7.6.0 build:29")
        r = bare_recorder(self, cfg, pin)
        start_session(r)
        r._feed(hello(), time.time_ns())
        r._end_session("TEST")
        with open(os.path.join(addons, "dummy.jar"), "wb") as fh:
            fh.write(b"new")
        fake_bookmap("7.6.1 build:3")  # Bookmap updated while the recorder kept running
        start_session(r)
        r._feed(hello(), time.time_ns())
        r._end_session("TEST")
        r.events.close()
        r.manifest.close()
        ev = BS.read_jsonl(os.path.join(r.run_dir, "events.jsonl"))
        man = BS.read_jsonl(os.path.join(r.run_dir, "manifest.jsonl"))
        sec = [e for e in man if e["kind"] == "security_event"]
        self.assertEqual([e["what"] for e in sec], ["ADDON_INVENTORY_CHANGED"])
        self.assertEqual(sec[0]["current"][0]["file"], "dummy.jar")
        self.assertTrue(any(e["kind"] == "bookmap_version_changed" for e in ev))
        segs = [e["segment"] for e in man if e["kind"] == "session_start"]
        self.assertNotEqual(segs[0], segs[1], "a Bookmap version change starts a new dataset segment")
        headers = [BS.read_records(os.path.join(r.run_dir, f))["header"] for f in sorted(os.listdir(r.run_dir))
                   if f.endswith(".bmrec")]
        self.assertEqual([h["bookmap_version"] for h in headers], ["7.6.0 build:29", "7.6.1 build:3"])
        self.assertEqual(headers[1]["addon_inventory"][0]["file"], "dummy.jar")

    def test_record_deletion_ledgers_and_never_deletes(self):
        """BMREC-24."""
        _b, cfg, _pin = make_env(self)
        rd = os.path.join(cfg["recordings_root"], "run1")
        os.makedirs(rd)
        f = BS.RecordingFile(os.path.join(rd, "a.bmrec"), {})
        f.write(0, 1, b"x")
        sha, _size = f.close()
        ledger = os.path.join(tmpdir(self), "ledger.jsonl")
        e = BRC.record_deletion(cfg, "run1/a.bmrec", "disk full test", path=ledger)
        self.assertEqual((e["kind"], e["sha256"]), ("deletion", sha))
        self.assertTrue(os.path.exists(os.path.join(rd, "a.bmrec")))
        with self.assertRaises(SystemExit):
            BRC.record_deletion(cfg, "run1/a.bmrec", "", path=ledger)
        for bad in ("../outside.bmrec", "run1/../../outside.bmrec", os.path.abspath(ledger)):
            with self.assertRaises(SystemExit, msg=bad):
                BRC.record_deletion(cfg, bad, "traversal", path=ledger)

    def test_live_clock_drift_marks_stream_invalid(self):
        r = self._accepted()
        now = time.time_ns()
        f = BF.encode(BF.TIME, 1, mode=BF.LIVE, recv_ns=now, send_ns=now, bookmap_ns=now - 10 * 10 ** 9)
        r._feed(f, now)
        self.assertFalse(r.session["stream_valid"])
        hist = self._accepted()
        f = BF.encode(BF.TIME, 1, mode=0, recv_ns=now, send_ns=now, bookmap_ns=now - 10 * 10 ** 9)
        hist._feed(f, now)
        self.assertTrue(hist.session["stream_valid"], "the drift check runs in LIVE mode only (plan §1.9)")


# =====================================================================================================================
class TestLiveUsability(unittest.TestCase):
    GOOD = {"authenticated": True, "data_delay": 0, "recording_tag": None, "stream_valid": True}

    def test_mode_other_than_live_is_never_live_usable(self):
        for mode in (0, 1, 2):
            self.assertFalse(BRC.live_usable(mode, dict(self.GOOD), True), BF.MODES[mode])

    def test_live_requires_every_condition(self):
        self.assertTrue(BRC.live_usable(BF.LIVE, dict(self.GOOD), True))
        for k, v in (("data_delay", 1), ("data_delay", 5), ("recording_tag", "rec"), ("authenticated", False),
                     ("stream_valid", False)):
            self.assertFalse(BRC.live_usable(BF.LIVE, dict(self.GOOD, **{k: v})), k)
        self.assertFalse(BRC.live_usable(BF.LIVE, dict(self.GOOD), book_valid=False))

    def test_replay_marked_session_never_counts_live_records(self):
        r = bare_recorder(self)
        start_session(r)
        r._feed(hello(recording_tag="replay-x"), time.time_ns())
        r._feed(depth(1, True, 1, 1, mode=BF.LIVE), time.time_ns())
        self.assertEqual(r.session["live_records"], 0)


# =====================================================================================================================
class TestFiles(unittest.TestCase):
    """BMREC-19/20/21: CRC per record, truncated-tail handling without repair, manifest hashes, read-only."""

    def write_file(self, d, n=20):
        p = os.path.join(d, "f.bmrec")
        f = BS.RecordingFile(p, {"hello": "x"})
        for i in range(n):
            f.write(BS.ORIGIN_ADDON, 1000 + i, bytes([i]) * 40)
        f.note("GAP", 5000, {"cause": "TEST"})
        sha, size = f.close()
        return p, sha, size

    def test_round_trip_and_read_only(self):
        d = tmpdir(self)
        p, sha, _ = self.write_file(d)
        w = BS.read_records(p)
        self.assertTrue(w["ok"])
        self.assertEqual(len(w["records"]), 21)
        self.assertEqual(w["records"][3], (0, 1003, bytes([3]) * 40))
        self.assertEqual(BS.decode_note(w["records"][-1][2]), ("GAP", {"cause": "TEST"}))
        self.assertFalse(os.access(p, os.W_OK))
        with self.assertRaises(FileExistsError):
            BS.RecordingFile(p, {})  # O_EXCL: a closed file is never reopened for write

    def test_truncated_tail_is_reported_not_repaired(self):
        d = tmpdir(self)
        p, _sha, size = self.write_file(d)
        t = os.path.join(d, "t.bmrec")
        with open(p, "rb") as fh:
            data = fh.read()
        with open(t, "wb") as fh:
            fh.write(data[:-7])
        before = BS.sha256_file(t)
        w = BS.read_records(t)
        self.assertFalse(w["ok"])
        self.assertEqual(len(w["records"]), 20)
        self.assertEqual(w["truncated_tail_bytes"], size - 7 - w["bad_offset"])
        self.assertEqual(BS.sha256_file(t), before, "the reader must never modify the file")

    def test_flipped_byte_stops_at_that_record(self):
        d = tmpdir(self)
        p, _sha, _size = self.write_file(d)
        t = os.path.join(d, "t.bmrec")
        data = bytearray(open(p, "rb").read())
        data[len(data) // 2] ^= 0xFF
        open(t, "wb").write(data)
        w = BS.read_records(t)
        self.assertFalse(w["ok"])
        self.assertIsNotNone(w["bad_offset"])
        self.assertLess(len(w["records"]), 21)

    def test_manifest_hash_matches_files_and_detects_an_edit(self):
        d = tmpdir(self)
        p, sha, size = self.write_file(d)
        m = BS.JsonLines(os.path.join(d, "manifest.jsonl"))
        m.append({"kind": "file_closed", "file": "f.bmrec", "sha256": sha, "bytes": size})
        m.close()
        ok, _lines = BS.verify_run(d)
        self.assertTrue(ok)
        os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
        with open(p, "r+b") as fh:
            fh.seek(40)
            b = fh.read(1)
            fh.seek(40)
            fh.write(bytes([b[0] ^ 0xFF]))
        ok, lines = BS.verify_run(d)
        self.assertFalse(ok)
        self.assertTrue(lines[0].startswith("HASH_MISMATCH"))

    def test_manifest_entry_outside_run_dir_is_refused(self):
        """A manifest line naming ../x or an absolute path is not followed out of the run folder."""
        root = tmpdir(self)
        d = os.path.join(root, "run1")
        os.makedirs(d)
        p, sha, size = self.write_file(root)
        m = BS.JsonLines(os.path.join(d, "manifest.jsonl"))
        m.append({"kind": "file_closed", "file": "../" + os.path.basename(p), "sha256": sha, "bytes": size})
        m.append({"kind": "file_closed", "file": p, "sha256": sha, "bytes": size})
        m.close()
        ok, lines = BS.verify_run(d)
        self.assertFalse(ok)
        self.assertEqual([ln.split()[0] for ln in lines], ["OUTSIDE_RUN_DIR", "OUTSIDE_RUN_DIR"])

    def test_manifest_has_no_absolute_paths(self):
        """BMREC-22 over a real session's manifest and event log."""
        r = bare_recorder(self)
        start_session(r)
        r._feed(hello(), time.time_ns())
        r._end_session("TEST")
        r.manifest.close()
        r.events.close()
        for name in ("manifest.jsonl", "events.jsonl"):
            text = open(os.path.join(r.run_dir, name), encoding="utf-8").read()
            self.assertNotRegex(text, r"[A-Za-z]:\\\\", name)
            self.assertNotIn("Users", text, name)
            self.assertNotIn(os.environ.get("USERNAME", "\0"), text, name)

    def test_crash_left_file_is_recovered_as_is(self):
        _b, cfg, pin = make_env(self)
        root = cfg["recordings_root"]
        rd = os.path.join(root, "oldrun")
        os.makedirs(rd)
        f = BS.RecordingFile(os.path.join(rd, "x.bmrec"), {})
        f.write(0, 1, b"abc")
        f.fh.flush()
        f.fh.close()  # "crash": never hashed, never in the manifest
        with open(os.path.join(rd, "x.bmrec"), "ab") as fh:
            fh.write(b"\x00\x00")  # torn tail
        BS.JsonLines(os.path.join(rd, "manifest.jsonl")).close()
        r = BRC.Recorder(cfg)
        r._recover_previous_runs()
        man = BS.read_jsonl(os.path.join(rd, "manifest.jsonl"))
        rc = [e for e in man if e["kind"] == "recovered_close"][0]
        self.assertFalse(rc["clean"])
        self.assertEqual(rc["records"], 1)
        self.assertEqual(rc["truncated_tail_bytes"], 2)
        self.assertEqual(rc["sha256"], BS.sha256_file(os.path.join(rd, "x.bmrec")))
        self.assertTrue(any(e["kind"] == "run_recovered" for e in man))


# =====================================================================================================================
class TestStorageLocation(unittest.TestCase):
    """BMREC-18: recordings (and backups) never live inside a git worktree."""

    def test_refuses_inside_this_worktree(self):
        with self.assertRaises(BS.StorageRefused):
            BS.refuse_if_in_worktree(os.path.join(ROOT, "data", "bookmap-recordings"))

    def test_accepts_outside(self):
        BS.refuse_if_in_worktree(tmpdir(self))

    def test_recorder_preflight_refuses_a_root_inside_the_repo(self):
        _b, cfg, _pin = make_env(self)
        cfg["recordings_root"] = os.path.join(ROOT, "should-never-be-created-h1")
        self.assertEqual(BRC.Recorder(cfg).preflight(), BRC.EXIT_PREFLIGHT)
        self.assertFalse(os.path.exists(cfg["recordings_root"]))

    def test_backup_refuses_a_root_inside_the_repo(self):
        _b, cfg, _pin = make_env(self)
        cfg["backup_root"] = os.path.join(ROOT, "should-never-be-created-h1-backup")
        with self.assertRaises(BS.StorageRefused):
            BRC.backup(cfg)

    def test_build_outputs_inside_the_repo_are_ignored(self):
        """Belt and braces (BMREC-18): the only recorder-related artefacts written inside the repo are build
        outputs, and they are git-ignored."""
        r = subprocess.run(["git", "-C", ROOT, "check-ignore", "-q", "integrations/bookmap/dist/tds-h1-recorder.jar"])
        self.assertEqual(r.returncode, 0)

    def test_backup_verifies_hashes_and_flags_a_bad_source(self):
        _b, cfg, _pin = make_env(self)
        rd = os.path.join(cfg["recordings_root"], "run1")
        os.makedirs(rd)
        f = BS.RecordingFile(os.path.join(rd, "a.bmrec"), {})
        f.write(0, 1, b"x")
        sha, size = f.close()
        m = BS.JsonLines(os.path.join(rd, "manifest.jsonl"))
        m.append({"kind": "file_closed", "file": "a.bmrec", "sha256": sha, "bytes": size})
        m.append({"kind": "file_closed", "file": "b.bmrec", "sha256": "0" * 64, "bytes": 1})
        m.close()
        with open(os.path.join(rd, "b.bmrec"), "wb") as fh:
            fh.write(b"tampered")
        out = []
        self.assertFalse(BRC.backup(cfg, log=out.append))
        self.assertTrue(any(line.startswith("COPIED_OK") and "a.bmrec" in line for line in out))
        self.assertTrue(any(line.startswith("SOURCE_HASH_MISMATCH") and "b.bmrec" in line for line in out))
        self.assertEqual(BS.sha256_file(os.path.join(cfg["backup_root"], "run1", "a.bmrec")), sha)


# =====================================================================================================================
class TestPreregistration(unittest.TestCase):
    """Plan H1 N4: the holdout calendar exists, is committed and unmodified before the first recording."""

    def test_missing_calendar_blocks(self):
        ok, why = BRC.check_preregistration(os.path.join(tmpdir(self), "nope.json"))
        self.assertFalse(ok)
        self.assertIn("MISSING", why)

    def test_uncommitted_then_committed_then_modified(self):
        d = tmpdir(self)
        subprocess.run(["git", "-C", d, "init", "-q"], check=True)
        cal = os.path.join(d, "cal.json")
        doc = BRC.preregister_holdout(cal, seed=1)
        self.assertEqual(BRC.check_preregistration(cal), (False, "HOLDOUT_CALENDAR_NOT_COMMITTED"))
        subprocess.run(["git", "-C", d, "add", "."], check=True)
        subprocess.run(["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@invalid", "commit", "-q", "-m", "p"],
                       check=True)
        self.assertEqual(BRC.check_preregistration(cal), (True, "OK"))
        with self.assertRaises(SystemExit):
            BRC.preregister_holdout(cal)  # registered once, never rewritten
        with open(cal, "a", encoding="utf-8") as fh:
            fh.write(" ")
        self.assertEqual(BRC.check_preregistration(cal), (False, "HOLDOUT_CALENDAR_MODIFIED_SINCE_COMMIT"))
        self.assertEqual(len(doc["preview_first_26_weeks"]), 26)

    def test_assignment_is_deterministic_and_near_fraction(self):
        a = [BRC.holdout_assignment(2027, w, 99, 0.25) for w in range(1, 53)]
        self.assertEqual(a, [BRC.holdout_assignment(2027, w, 99, 0.25) for w in range(1, 53)])
        self.assertTrue(4 <= a.count("holdout") <= 22)

    def test_preflight_refuses_without_preregistration(self):
        _b, cfg, _pin = make_env(self)
        cfg["holdout_calendar"] = os.path.join(tmpdir(self), "missing.json")
        r = BRC.Recorder(cfg)
        self.assertEqual(r.preflight(), BRC.EXIT_PREFLIGHT)
        r._finish(BRC.EXIT_PREFLIGHT)


# =====================================================================================================================
class TestOutboundAllowlist(unittest.TestCase):
    """BMREC-26/28: one chokepoint, host + path + parameter allowlist, budget, 429/418, validation."""

    class Opener:
        def __init__(self, responses):
            self.responses = list(responses)
            self.calls = []

        def open(self, req, timeout=None):
            self.calls.append(req.full_url)
            status, body, headers = self.responses.pop(0)
            if status != 200:
                import urllib.error
                raise urllib.error.HTTPError(req.full_url, status, "x", headers, io.BytesIO(body))
            resp = mock.MagicMock()
            resp.status = status
            resp.headers = headers
            resp.read.return_value = body
            resp.__enter__.return_value = resp
            return resp

    INFO = json.dumps({"rateLimits": [{"rateLimitType": "REQUEST_WEIGHT", "interval": "MINUTE", "intervalNum": 1,
                                       "limit": 2400}],
                       "symbols": [{"symbol": "BTCUSDT", "filters": [
                           {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                           {"filterType": "LOT_SIZE", "stepSize": "0.001"}]}]}).encode()

    def test_non_allowlisted_host_path_method_and_params_are_refused_before_a_socket(self):
        for url in ("https://api.binance.com/fapi/v1/time", "https://testnet.binancefuture.com/fapi/v1/time",
                    "http://fapi.binance.com/fapi/v1/time", "https://fapi.binance.com/fapi/v1/order",
                    "https://fapi.binance.com:8443/fapi/v1/time", "https://evil@fapi.binance.com/fapi/v1/time",
                    "https://fapi.binance.com/fapi/v1/depth?symbol=BTCUSDT&signature=x"):
            with self.assertRaises(BR.OutboundRefused, msg=url):
                BR.check_url(url)
        with self.assertRaises(BR.OutboundRefused):
            BR.check_url("https://fapi.binance.com/fapi/v1/time", method="POST")
        with self.assertRaises(BR.OutboundRefused):
            BR.build_url("/fapi/v2/account")
        with self.assertRaises(BR.OutboundRefused):
            BR.build_url("/fapi/v1/depth", {"symbol": "BTCUSDT", "timestamp": 1})
        with self.assertRaises(BR.OutboundRefused):
            BR.build_url("/fapi/v1/depth", {"symbol": "BTC&x=1"})
        op = self.Opener([])
        c = BR.BinancePublic(opener=op)
        with self.assertRaises(BR.OutboundRefused):
            c.get("/fapi/v1/order", {"symbol": "BTCUSDT"})
        self.assertEqual(op.calls, [])

    def test_budget_starts_with_exchangeinfo_and_uses_its_limit(self):
        op = self.Opener([(200, self.INFO, {"X-MBX-USED-WEIGHT-1M": "10"})])
        c = BR.BinancePublic(opener=op)
        self.assertEqual(c.get("/fapi/v1/time")["reason"], "LIMIT_UNKNOWN")  # limit not read yet
        self.assertEqual(c.get("/fapi/v1/exchangeInfo")["status"], "OK")
        self.assertEqual(c.limit_per_min, 2400)
        c.own = [(c.clock(), 239)]
        self.assertEqual(c.budget_ok("/fapi/v1/depth"), (False, "OWN_BUDGET"))
        c.own = []
        c.ip_used = 2000
        self.assertEqual(c.budget_ok("/fapi/v1/time"), (False, "IP_HEADROOM"))

    def test_429_backs_off_and_418_halts(self):
        op = self.Opener([(200, self.INFO, {}), (429, b"", {"Retry-After": "7"}), (418, b"", {})])
        c = BR.BinancePublic(opener=op)
        c.get("/fapi/v1/exchangeInfo")
        self.assertEqual(c.get("/fapi/v1/time")["http"], 429)
        self.assertEqual(c.budget_ok("/fapi/v1/time"), (False, "BACKOFF_429"))
        c.backoff_until = 0
        self.assertEqual(c.get("/fapi/v1/time")["http"], 418)
        n = len(op.calls)
        self.assertEqual(c.get("/fapi/v1/time")["reason"], "HALTED_418")
        self.assertEqual(len(op.calls), n, "no call after 418")

    def test_malformed_body_is_invalid_and_never_a_match(self):
        op = self.Opener([(200, self.INFO, {}), (200, b'{"lastUpdateId":1,"E":1,"T":1,"bids":[],"asks":[]}', {})])
        c = BR.BinancePublic(opener=op)
        c.get("/fapi/v1/exchangeInfo")
        res = c.get("/fapi/v1/depth", {"symbol": "BTCUSDT", "limit": 20})
        self.assertEqual(res["status"], "INVALID")

    def test_tick_gate(self):
        f = BR.exchange_filters(json.loads(self.INFO), "BTCUSDT")
        self.assertEqual(BR.tick_gate(0.1, 1000.0, f)[0], BR.MATCH)
        self.assertEqual(BR.tick_gate(1.0, 1000.0, f)[0], BR.MISMATCH)
        self.assertEqual(BR.tick_gate(0.1, 100.0, f)[0], BR.MISMATCH)
        self.assertEqual(BR.tick_gate(0.1, 1000.0, None)[0], BR.UNKNOWN)
        self.assertEqual(BR.symbol_from_alias("BTCUSDT@BNF"), "BTCUSDT")

    def test_depth_and_aggtrades_comparison(self):
        rest = {"bids": [["65000.0", "1.000"], ["64999.9", "0.500"]], "asks": [["65000.1", "2.000"]]}
        sample = {"bids": [(650000, 1000), (649999, 500)], "asks": [(650001, 2000)]}
        self.assertEqual(BR.compare_depth(rest, sample, 0.1, 1000.0, n=10)[0], BR.MATCH)
        sample["bids"] = [(650000, 999), (649999, 1)]
        self.assertEqual(BR.compare_depth(rest, sample, 0.1, 1000.0, n=10)[0], BR.MISMATCH)
        self.assertIsNone(BR.pick_sample([(0.0, sample)], 1000.0))
        rows = [{"T": 1, "m": False, "p": "1", "q": "1.000"}, {"T": 2, "m": True, "p": "1", "q": "0.500"}]
        self.assertEqual(BR.compare_aggtrades(rows, [(True, 1000), (False, 500)], 1000.0)[0], BR.MATCH)
        self.assertEqual(BR.compare_aggtrades(rows, [(True, 900), (False, 500)], 1000.0)[0], BR.MISMATCH)
        self.assertEqual(BR.compare_aggtrades(rows * 500, [], 1000.0)[0], BR.UNKNOWN)


# =====================================================================================================================
class TestStaticRules(unittest.TestCase):
    """BMREC-26/27/32 and the security review's grep verifications, as tests."""

    MODULES = ("bookmap_recorder.py", "bookmap_frames.py", "bookmap_store.py", "bookmap_rest.py", "bookmap_pipe.py")
    STDLIB = {"argparse", "datetime", "hashlib", "heapq", "json", "os", "queue", "subprocess", "sys", "threading",
              "time", "zipfile", "collections", "math", "struct", "shutil", "stat", "zlib", "ssl", "urllib",
              "urllib.error", "urllib.parse", "urllib.request", "decimal", "ctypes", "ctypes.wintypes", "re"}
    OWN = {"bookmap_frames", "bookmap_rest", "bookmap_store", "bookmap_pipe"}

    def src(self, name):
        with open(os.path.join(ROOT, "scripts", name), encoding="utf-8") as fh:
            return fh.read()

    def test_imports_are_stdlib_or_own_modules_only(self):
        for name in self.MODULES:
            tree = ast.parse(self.src(name))
            for n in ast.walk(tree):
                if isinstance(n, ast.Import):
                    mods = [a.name for a in n.names]
                elif isinstance(n, ast.ImportFrom):
                    mods = [n.module]
                else:
                    continue
                for m in mods:
                    self.assertIn(m, self.STDLIB | self.OWN, f"{name} imports {m}")

    def test_no_secret_loader_order_path_or_credential_store(self):
        banned = ("trading_env", "get_secret", "config/env", "config\\env", "binance-futures-testnet-order",
                  "keys.db", "CredRead", "Credential Manager", "multiprocessing.connection", "pickle.", "marshal.",
                  "yaml.load", "eval(")
        for name in self.MODULES:
            text = self.src(name)
            for b in banned:
                self.assertNotIn(b, text, f"{name} mentions {b}")

    def test_tls_is_never_weakened_and_nothing_is_signed(self):
        pat = re.compile(r"_create_unverified_context|CERT_NONE|check_hostname *= *False|X-MBX-APIKEY|signature")
        for name in self.MODULES:
            self.assertIsNone(pat.search(self.src(name)), name)

    def test_nothing_deletes_under_the_recording_root(self):
        pat = re.compile(r"unlink|remove\(|rmtree|os\.replace")
        for name in self.MODULES:
            self.assertIsNone(pat.search(self.src(name)), name)

    def test_the_only_network_module_is_bookmap_rest(self):
        for name in self.MODULES:
            if name == "bookmap_rest.py":
                continue
            text = self.src(name)
            for b in ("urllib", "http.client", "socket", "ssl"):
                self.assertNotRegex(text, rf"^\s*(import|from)\s+{re.escape(b)}", f"{name} imports {b}")


# =====================================================================================================================
@unittest.skipUnless(os.name == "nt" and BP is not None, "Win32 named pipe")
class TestPipeSecurity(unittest.TestCase):
    """BMREC-05/11/12/13 against the real Win32 pipe."""

    def name(self):
        return rf"\\.\pipe\tds-h1-test-{os.getpid()}-{time.time_ns()}"

    def test_creation_flags(self):
        self.assertTrue(BP.OPEN_MODE & BP.PIPE_ACCESS_INBOUND)
        self.assertTrue(BP.OPEN_MODE & BP.FILE_FLAG_FIRST_PIPE_INSTANCE)
        self.assertFalse(BP.OPEN_MODE & 0x2, "never outbound/duplex")
        self.assertTrue(BP.PIPE_MODE & BP.PIPE_REJECT_REMOTE_CLIENTS)
        self.assertEqual(BP.MAX_INSTANCES, 1)

    def test_dacl_is_owner_only(self):
        s = BP.SecurePipeServer(self.name())
        self.addCleanup(s.close)
        sddl = s.dacl_sddl()
        dacl = sddl.split("D:", 1)[1]
        aces = re.findall(r"\(([^)]*)\)", dacl)
        self.assertTrue(dacl.startswith("P"), "protected DACL: nothing inherited")
        self.assertEqual(len(aces), 1, sddl)
        self.assertEqual(aces[0].split(";")[-1], BP.current_user_sid())
        for trustee in ("WD", "AN", "NU", "AU", "BU", "SY", "BA", "IU"):
            self.assertNotIn(f";{trustee})", sddl)

    def test_second_instance_and_read_access_are_refused(self):
        n = self.name()
        s = BP.SecurePipeServer(n)
        self.addCleanup(s.close)
        with self.assertRaises(BP.PipeSquatted):
            BP.SecurePipeServer(n)
        with self.assertRaises(BP.PipeError):
            BP.PipeClient(n, access=BP.GENERIC_READ)  # inbound-only: a client cannot open it for reading

    def test_squatted_name_makes_the_recorder_exit_nonzero(self):
        """BMREC-12: pre-create the name from this process, start the recorder -> exit 3 + security event."""
        n = self.name()
        h = BP.create_squatter(n)
        self.addCleanup(BP.close_handle, h)
        _b, cfg, _pin = make_env(self, pipe_name=n)
        cfg_path = os.path.join(_b, "cfg.json")
        with open(cfg_path, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)
        p = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "bookmap_recorder.py"), "--config", cfg_path],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, BRC.EXIT_SQUATTED, p.stdout + p.stderr)
        run = os.listdir(cfg["recordings_root"])[0]
        man = BS.read_jsonl(os.path.join(cfg["recordings_root"], run, "manifest.jsonl"))
        self.assertEqual([e["what"] for e in man if e["kind"] == "security_event"], ["PIPE_NAME_SQUATTED"])

    def _run_recorder_in_thread(self, cfg, pin):
        r = BRC.Recorder(cfg)
        # preflight would refuse a pinned client outside Program Files; these tests pin paths explicitly
        r.pipe_module = BP
        os.makedirs(cfg["recordings_root"], exist_ok=True)
        r.run_id = "run-pipe"
        r.run_dir = os.path.join(cfg["recordings_root"], r.run_id)
        os.makedirs(r.run_dir)
        r.events = BS.JsonLines(os.path.join(r.run_dir, "events.jsonl"))
        r.manifest = BS.JsonLines(os.path.join(r.run_dir, "manifest.jsonl"))
        r.pin = pin
        r.preflight = lambda: BRC.EXIT_OK
        t = threading.Thread(target=r.run, daemon=True)
        t.start()
        for _ in range(100):
            if os.path.exists(r.run_dir) and "pipe_created" in open(os.path.join(r.run_dir, "events.jsonl"),
                                                                    encoding="utf-8").read():
                break
            time.sleep(0.05)
        return r, t

    def _stop(self, r, t):
        r.stop_requested = True
        t.join(10)
        self.assertFalse(t.is_alive())
        return BS.read_jsonl(os.path.join(r.run_dir, "manifest.jsonl"))

    def test_client_with_unpinned_process_path_is_rejected_with_zero_records(self):
        _b, cfg, pin = make_env(self, pinned_exe=os.path.join(PROGRAM_FILES, "Bookmap", "Bookmap.exe"))
        r, t = self._run_recorder_in_thread(cfg, pin)
        c = BP.PipeClient(cfg["pipe_name"])
        try:
            c.write(hello() + depth(1, True, 1, 1))  # a perfect hello from the WRONG process
        except BP.PipeError:
            pass
        time.sleep(0.8)
        c.close()
        man = self._stop(r, t)
        rej = [e for e in man if e["kind"] == "security_event"]
        self.assertEqual(rej[0]["reason"], "CLIENT_IMAGE_MISMATCH")
        self.assertEqual(rej[0]["exe_basename"].lower(), os.path.basename(sys.executable).lower())
        self.assertEqual([f for f in os.listdir(r.run_dir) if f.endswith(".bmrec")], [])

    def test_pinned_client_with_wrong_jar_on_disk_is_rejected(self):
        _b, cfg, pin = make_env(self, pinned_exe=sys.executable)
        with open(cfg["addon_jar_path"], "ab") as fh:
            fh.write(b"tamper")  # the loaded jar no longer matches the pin (BMREC-30)
        r, t = self._run_recorder_in_thread(cfg, pin)
        c = BP.PipeClient(cfg["pipe_name"])
        try:
            c.write(hello())
        except BP.PipeError:
            pass
        time.sleep(0.8)
        c.close()
        man = self._stop(r, t)
        self.assertEqual([e["reason"] for e in man if e["kind"] == "security_event"], ["JAR_HASH_MISMATCH"])
        self.assertEqual([f for f in os.listdir(r.run_dir) if f.endswith(".bmrec")], [])

    def test_pinned_client_with_wrong_hello_is_rejected_then_good_client_records(self):
        _b, cfg, pin = make_env(self, pinned_exe=sys.executable)
        r, t = self._run_recorder_in_thread(cfg, pin)
        c = BP.PipeClient(cfg["pipe_name"])
        try:
            c.write(hello(code="d" * 64))
        except BP.PipeError:
            pass
        time.sleep(0.6)
        c.close()
        time.sleep(0.4)
        c = BP.PipeClient(cfg["pipe_name"])
        ck, _ = checkpoint(2, 0, [(99, 5)], [(101, 4)])
        c.write(hello() + ck + depth(1, True, 99, 6))
        time.sleep(0.8)
        c.close()
        time.sleep(0.4)
        man = self._stop(r, t)
        self.assertEqual([e["reason"] for e in man if e["kind"] == "security_event"], ["HELLO_PIN_MISMATCH"])
        self.assertEqual(sum(1 for e in man if e["kind"] == "session_start"), 1)
        self.assertTrue(BS.verify_run(r.run_dir)[0])
        recs = addon_records(run_records(r.run_dir))
        self.assertEqual([x["type_name"] for x in recs if x["type"] == BF.DEPTH], ["DEPTH"])

    def test_recording_root_is_created_private(self):
        """BMREC-19: the recorder creates its root with owner/SYSTEM/Administrators only."""
        d = os.path.join(tmpdir(self), "private-root")
        self.assertIsNone(BRC.ensure_private_dir(d, BP))
        sddl = BP.path_dacl_sddl(d)
        self.assertEqual(BP.others_with_write(sddl), [], sddl)
        self.assertTrue(sddl.split("D:", 1)[1].startswith("P"), sddl)

    def test_broad_write_aces_are_detected_and_refused(self):
        self.assertTrue(BP.others_with_write("D:(A;OICI;0x1301bf;;;AU)"))
        self.assertTrue(BP.others_with_write("D:(A;;FA;;;WD)"))
        self.assertTrue(BP.others_with_write("D:(A;OICI;FA;;;BU)"))
        self.assertEqual(BP.others_with_write("D:(A;OICI;0x1200a9;;;BU)(A;OICI;FA;;;SY)"), [])
        d = os.path.join(tmpdir(self), "shared-root")
        os.makedirs(d)
        with mock.patch.object(BP, "path_dacl_sddl", return_value="D:(A;OICI;0x1301bf;;;AU)"):
            self.assertIn("BMREC-19", BRC.ensure_private_dir(d, BP))

    def test_preflight_refuses_when_elevated(self):
        _b, cfg, _pin = make_env(self)
        with mock.patch.object(BP, "is_elevated", return_value=True):
            self.assertEqual(BRC.Recorder(cfg).preflight(), BRC.EXIT_ELEVATED)

    def test_preflight_requires_the_pinned_client_under_program_files(self):
        _b, cfg, _pin = make_env(self, pinned_exe=sys.executable)
        r = BRC.Recorder(cfg)
        self.assertEqual(r.preflight(), BRC.EXIT_PREFLIGHT)
        r._finish(BRC.EXIT_PREFLIGHT)


# =====================================================================================================================
@unittest.skipUnless(os.path.isfile(os.path.join(JDK, "bin", "javac.exe"))
                     and os.path.isfile(os.path.join(LIB, "bm-l1api.jar"))
                     and os.path.isfile(os.path.join(BM, "dist", "tds-h1-recorder.jar")),
                     "needs the pinned JDK, Bookmap's API jars and a built add-on (integrations/bookmap/build.py)")
class TestJavaAllowlistChecker(unittest.TestCase):
    """BMREC-04(a): the checker's must-fail fixtures each fail for their own reason; the real jar passes."""

    def test_fixtures(self):
        sys.path.insert(0, os.path.join(BM, "tools"))
        import allowlist_check as AC
        import allowlist_fixtures as AF
        d = tmpdir(self)
        jar = os.path.join(BM, "dist", "tds-h1-recorder.jar")
        classes = os.path.join(d, "classes")
        with zipfile.ZipFile(jar) as z:
            z.extractall(classes)
        allow = AC.load_allowlist(os.path.join(BM, "allowlist.json"))
        results = AF.run(os.path.join(JDK, "bin", "javac.exe"), classes,
                         [os.path.join(LIB, "bm-simplified-api-wrapper.jar"), os.path.join(LIB, "bm-l1api.jar")],
                         d, allow, jar)
        self.assertTrue(results[0]["ok"], results[0]["violations"])
        bad = [r["name"] for r in results[1:] if not r["ok"]]
        self.assertEqual(bad, [])
        self.assertGreaterEqual(len(results) - 1, 60)
        named = {r["name"] for r in results}
        for must in ("api_sendOrder", "provider_sendOrder", "provider_login", "provider_sendUserMessage",
                     "provider_close", "trading_listener", "orders_listener", "position_listener", "balance_listener",
                     "trading_strategy_annotation", "unrestricted_data_annotation", "register_indicator",
                     "getprovider_stored_in_field", "getprovider_passed_to_method", "getprovider_trading_overload",
                     "reflection_method", "class_forName", "native_method", "runtime_exec", "net_socket",
                     "object_input_stream", "fos_non_pipe_path", "pipe_read_file_input_stream"):
            self.assertIn(must, named)

    def test_pin_matches_the_built_jar(self):
        with open(os.path.join(BM, "addon-pin.json"), encoding="utf-8") as fh:
            pin = json.load(fh)
        self.assertEqual(BS.sha256_file(os.path.join(BM, "dist", "tds-h1-recorder.jar")), pin["jar_sha256"])
        self.assertEqual(pin["check"]["result"], "PASS")
        self.assertEqual(pin["check"]["must_fail_fixtures"], pin["check"]["must_fail_failed_as_expected"])


if __name__ == "__main__":
    unittest.main()
