"""BMREC-15 frame validator for docs/contracts/bookmap-recorder-frames.md (the single source).

Frames are parsed with `struct` into plain dicts of ints/floats/bools/strs. Nothing is ever deserialized as an
object: no pickle, marshal, eval, yaml or class-instantiating JSON hooks (BMREC-15).

    import bookmap_frames as BF
    r = BF.FrameReader()
    for item in r.feed(data):          # item is ("frame", payload_bytes, dict) or ("error", code)
        ...
    BF.parse_payload(payload)          # -> dict, or raises FrameError(code)

Standard library only (BMREC-32).
"""
import math
import struct

# ---- contract §8 parameters mirrored here (a test parses the contract table and compares)
SCHEMA_VERSION = 1
FRAME_MAX_BYTES = 4096
STRING_MAX_BYTES = 256
QUEUE_CAPACITY = 65536
HEARTBEAT_INTERVAL_MS = 1000
TIME_RECORD_MIN_INTERVAL_NS = 100_000_000
RECONNECT_BACKOFF_INITIAL_MS = 250
RECONNECT_BACKOFF_CAP_MS = 30_000
STOP_JOIN_TIMEOUT_MS = 2000
MAX_CONSECUTIVE_INVALID_FRAMES = 16

PIPE_NAME = r"\\.\pipe\tds-bookmap-recorder-h1"
HEADER = struct.Struct(">HBBQqqq")
assert HEADER.size == 36

MODES = {0: "HISTORICAL", 1: "BACKFILL", 2: "REPLAY", 3: "LIVE"}
LIVE = 3

HELLO, DEPTH, TRADE, TIME, MODE, CONNECTION, HEARTBEAT, GAP, SNAPSHOT_END = 1, 2, 3, 4, 5, 6, 7, 8, 9
CHECKPOINT_BEGIN, CHECKPOINT_LEVEL, CHECKPOINT_END, ADDON_STOP = 10, 11, 12, 13
TYPE_NAMES = {HELLO: "HELLO", DEPTH: "DEPTH", TRADE: "TRADE", TIME: "TIME", MODE: "MODE",
              CONNECTION: "CONNECTION", HEARTBEAT: "HEARTBEAT", GAP: "GAP", SNAPSHOT_END: "SNAPSHOT_END",
              CHECKPOINT_BEGIN: "CHECKPOINT_BEGIN", CHECKPOINT_LEVEL: "CHECKPOINT_LEVEL",
              CHECKPOINT_END: "CHECKPOINT_END", ADDON_STOP: "ADDON_STOP"}
CAPTURE_SPACE = frozenset({DEPTH, TRADE, TIME, MODE, CONNECTION, SNAPSHOT_END})
FORWARDER_SPACE = frozenset({HELLO, HEARTBEAT, GAP, CHECKPOINT_BEGIN, CHECKPOINT_LEVEL, CHECKPOINT_END,
                             ADDON_STOP})
CONN_STATES = {1: "LOST", 2: "RESTORED", 3: "LOGIN_FAILED", 4: "LOGIN_SUCCESSFUL", 5: "MONITOR_ACTIVE",
               6: "MONITOR_UNAVAILABLE"}
GAP_CAUSES = {1: "QUEUE_OVERFLOW"}
CKPT_REASONS = {1: "SESSION_START", 2: "AFTER_GAP", 3: "AFTER_SNAPSHOT_END"}

I32_MIN, I32_MAX = -(2 ** 31), 2 ** 31 - 1


class FrameError(ValueError):
    """Validation failure. `.code` is a short reason code; raw bytes are never carried (BMREC-15)."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


class _Cur:
    __slots__ = ("b", "o")

    def __init__(self, b, o):
        self.b, self.o = b, o

    def take(self, fmt):
        s = struct.Struct(">" + fmt)
        if self.o + s.size > len(self.b):
            raise FrameError("TRUNCATED_BODY")
        v = s.unpack_from(self.b, self.o)
        self.o += s.size
        return v if len(v) > 1 else v[0]

    def boolean(self):
        v = self.take("B")
        if v not in (0, 1):
            raise FrameError("BAD_BOOL")
        return bool(v)

    def f64(self):
        v = self.take("d")
        if not math.isfinite(v):
            raise FrameError("NON_FINITE")
        return v

    def string(self):
        n = self.take("H")
        if n > STRING_MAX_BYTES:
            raise FrameError("STRING_TOO_LONG")
        if self.o + n > len(self.b):
            raise FrameError("TRUNCATED_BODY")
        raw = self.b[self.o:self.o + n]
        self.o += n
        try:
            s = raw.decode("utf-8", "strict")
        except UnicodeDecodeError:
            raise FrameError("BAD_UTF8") from None
        if any(ord(c) < 0x20 or ord(c) == 0x7F for c in s):
            raise FrameError("CONTROL_CHAR")
        return s

    def ostring(self):
        return self.string() if self.boolean() else None

    def done(self):
        if self.o != len(self.b):
            raise FrameError("TRAILING_BYTES")


def parse_payload(p):
    """Validate one frame payload (header + body, no length prefix). Returns a plain dict."""
    if len(p) < HEADER.size:
        raise FrameError("SHORT_HEADER")
    ver, rtype, mode, seq, recv, send, bmt = HEADER.unpack_from(p, 0)
    if ver != SCHEMA_VERSION:
        raise FrameError("SCHEMA_MISMATCH")
    if rtype not in TYPE_NAMES:
        raise FrameError("UNKNOWN_TYPE")
    if mode not in MODES:
        raise FrameError("BAD_MODE")
    if seq < 1 or seq >= 2 ** 63:
        raise FrameError("BAD_SEQ")
    if recv <= 0 or send <= 0:
        raise FrameError("BAD_TIMESTAMP")
    if bmt < -1:
        raise FrameError("BAD_BOOKMAP_TIME")
    r = {"type": rtype, "type_name": TYPE_NAMES[rtype], "mode": mode, "seq": seq, "addon_recv_ns": recv,
         "addon_send_ns": send, "bookmap_time_ns": bmt}
    c = _Cur(p, HEADER.size)
    if rtype == HELLO:
        r["addon_version"] = c.string()
        r["code_sha256"] = c.string()
        r["source_sha256"] = c.string()
        for k in ("code_sha256", "source_sha256"):
            if len(r[k]) != 64 or any(ch not in "0123456789abcdef" for ch in r[k]):
                raise FrameError("BAD_SHA")
        r["queue_capacity"] = c.take("I")
        r["connection_monitor"] = "ACTIVE" if c.boolean() else "UNAVAILABLE"
        r["alias"] = c.string()
        for k in ("symbol", "exchange", "instrument_type", "full_name", "requested_symbol"):
            r[k] = c.ostring()
        r["pips"] = c.f64()
        r["multiplier"] = c.f64()
        r["size_multiplier"] = c.f64()
        if r["pips"] <= 0 or r["size_multiplier"] <= 0:
            raise FrameError("BAD_INSTRUMENT")
        r["data_delay"] = c.take("q")
        for k in ("is_full_depth", "is_crypto", "is_api_protected", "is_nbbo_supported"):
            r[k] = c.boolean()
        r["recording_tag"] = c.ostring()
    elif rtype == DEPTH:
        r["is_bid"] = c.boolean()
        r["price_level"] = c.take("i")
        r["size"] = c.take("i")
        if r["size"] < 0:
            raise FrameError("NEGATIVE_SIZE")
    elif rtype == TRADE:
        r["price_level"] = c.f64()
        r["size"] = c.take("i")
        if r["size"] <= 0:
            raise FrameError("NON_POSITIVE_TRADE_SIZE")
        r["is_bid_aggressor"] = c.boolean()
        r["is_otc"] = c.boolean()
        r["is_execution_start"] = c.boolean()
        r["is_execution_end"] = c.boolean()
    elif rtype == CONNECTION:
        st = c.take("B")
        if st not in CONN_STATES:
            raise FrameError("BAD_CONNECTION_STATE")
        r["state"] = CONN_STATES[st]
    elif rtype == HEARTBEAT:
        (r["queue_depth"], r["queue_capacity"], r["dropped_total"], r["capture_seq_last"], r["frames_sent_total"],
         r["ignored_admin_messages"], r["pipe_reconnects"]) = c.take("IIQQQQI")
        if r["queue_depth"] > r["queue_capacity"]:
            raise FrameError("BAD_QUEUE_DEPTH")
    elif rtype == GAP:
        cause = c.take("B")
        if cause not in GAP_CAUSES:
            raise FrameError("BAD_GAP_CAUSE")
        r["cause"] = GAP_CAUSES[cause]
        r["dropped_count"] = c.take("Q")
    elif rtype == CHECKPOINT_BEGIN:
        reason = c.take("B")
        if reason not in CKPT_REASONS:
            raise FrameError("BAD_CHECKPOINT_REASON")
        r["reason"] = CKPT_REASONS[reason]
        r["bookmap_snapshot_complete"] = c.boolean()
        r["bid_levels"], r["ask_levels"], r["capture_seq_at"] = c.take("IIQ")
    elif rtype == CHECKPOINT_LEVEL:
        r["is_bid"] = c.boolean()
        r["price_level"] = c.take("i")
        r["size"] = c.take("i")
        if r["size"] <= 0:
            raise FrameError("NON_POSITIVE_LEVEL_SIZE")
    elif rtype == CHECKPOINT_END:
        r["levels_emitted"] = c.take("I")
    # TIME, MODE, SNAPSHOT_END, ADDON_STOP: empty bodies
    c.done()
    return r


class FrameReader:
    """Length-prefixed stream splitter with the size cap checked BEFORE any allocation (BMREC-15).

    feed() yields ("frame", payload, record) or ("error", code). An "error" of FRAME_TOO_LARGE / ZERO_LENGTH is
    fatal for the connection (the stream can no longer be framed); the caller must close it.
    """
    FATAL = frozenset({"FRAME_TOO_LARGE", "ZERO_LENGTH"})

    def __init__(self, max_frame=FRAME_MAX_BYTES):
        self.max_frame = max_frame
        self.buf = bytearray()
        self.dead = False

    def feed(self, data):
        if self.dead:
            return
        self.buf += data
        while True:
            if len(self.buf) < 4:
                return
            (n,) = struct.unpack_from(">I", self.buf, 0)
            if n == 0:
                self.dead = True
                yield ("error", "ZERO_LENGTH")
                return
            if n > self.max_frame:
                self.dead = True
                yield ("error", "FRAME_TOO_LARGE")
                return
            if len(self.buf) < 4 + n:
                return
            payload = bytes(self.buf[4:4 + n])
            del self.buf[:4 + n]
            try:
                yield ("frame", payload, parse_payload(payload))
            except FrameError as e:
                yield ("error", e.code)

    def pending_bytes(self):
        return len(self.buf)


# ---- encoder (used by tests and the Python fake client; the Java add-on is the production writer)


def _str(s):
    b = s.encode("utf-8")
    return struct.pack(">H", len(b)) + b


def _ostr(s):
    return b"\x00" if s is None else b"\x01" + _str(s)


def encode(rtype, seq, *, mode=0, recv_ns=1, send_ns=1, bookmap_ns=-1, body=b"", schema=SCHEMA_VERSION):
    payload = HEADER.pack(schema, rtype, mode, seq, recv_ns, send_ns, bookmap_ns) + body
    return struct.pack(">I", len(payload)) + payload


def hello_body(*, code_sha256, source_sha256, alias="BTCUSDT@BNF", pips=0.1, size_multiplier=1000.0,
               data_delay=0, recording_tag=None, monitor=True, version="h1-1", symbol="BTCUSDT",
               full_name="BTCUSDT@BNF", multiplier=1.0):
    return (_str(version) + _str(code_sha256) + _str(source_sha256) + struct.pack(">I", QUEUE_CAPACITY)
            + bytes([1 if monitor else 0]) + _str(alias) + _ostr(symbol) + _ostr("BNF") + _ostr("crypto")
            + _ostr(full_name) + _ostr(None) + struct.pack(">ddd", pips, multiplier, size_multiplier)
            + struct.pack(">q", data_delay) + bytes([1, 1, 0, 0]) + _ostr(recording_tag))


def depth_body(is_bid, price, size):
    return struct.pack(">Bii", 1 if is_bid else 0, price, size)


def trade_body(price, size, bid_aggressor=True):
    return struct.pack(">diBBBB", price, size, 1 if bid_aggressor else 0, 0, 0, 0)


def checkpoint_begin_body(reason, complete, bids, asks, capture_seq_at):
    return struct.pack(">BBIIQ", reason, 1 if complete else 0, bids, asks, capture_seq_at)


def checkpoint_level_body(is_bid, price, size):
    return struct.pack(">Bii", 1 if is_bid else 0, price, size)


def heartbeat_body(queue_depth=0, dropped_total=0, capture_seq_last=0, frames=0):
    return struct.pack(">IIQQQQI", queue_depth, QUEUE_CAPACITY, dropped_total, capture_seq_last, frames, 0, 0)
