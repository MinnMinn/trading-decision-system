"""Recording files, manifest and event log for the H1 recorder (contract §6; BMREC-16, -18..-22, -24, -25).

- Files live OUTSIDE any git worktree (BMREC-18): `refuse_if_in_worktree()` checks both `git rev-parse` and a
  walk up the parents for a `.git` entry, and refuses on either.
- Every record carries length + CRC32; the CRC is accident detection only (BMREC-20). `read_records()` stops at the
  first bad record and reports the offset and truncated tail; it never repairs, skips or rewrites.
- A closed file is flushed, fsynced, hashed, set read-only and never reopened for write (BMREC-19). Nothing in
  this module deletes, renames or replaces anything under the recording root (BMREC-24).
- Manifest and event log are append-only JSON lines with relative names only (BMREC-22).
"""
import hashlib
import json
import os
import shutil
import stat
import struct
import subprocess
import zlib

FILE_FORMAT_VERSION = 1
MAGIC = b"BMREC\x00\x01\n"
NOTE_MAX_BYTES = 262144
FREE_SPACE_FLOOR_BYTES = 20 * 1024 ** 3
FREE_SPACE_RESUME_BYTES = 25 * 1024 ** 3

ORIGIN_ADDON, ORIGIN_NOTE = 0, 1
NOTES = {"SESSION_START": 1, "SESSION_END": 2, "BOOK_CHECKPOINT": 3, "VALIDATION_FAILURE": 4, "GAP": 5,
         "BOOK_STATE": 6, "CLOCK": 7, "RECON_DEPTH": 8, "RECON_AGGTRADES": 9, "EXCHANGE_FILTERS": 10,
         "STREAM_STATE": 11}
NOTE_NAMES = {v: k for k, v in NOTES.items()}
_REC_HEAD = struct.Struct(">II")
_BODY_HEAD = struct.Struct(">Bq")


class StorageRefused(RuntimeError):
    pass


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- BMREC-18: never inside a worktree


def inside_git_worktree(path):
    """True if `path` (or its nearest existing ancestor) is inside a git worktree, by either test."""
    p = os.path.abspath(path)
    probe = p
    while not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    cur = probe
    while True:
        if os.path.exists(os.path.join(cur, ".git")):
            return True
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    try:
        r = subprocess.run(["git", "-C", probe, "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                           timeout=20)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def refuse_if_in_worktree(path, what="recording root"):
    if inside_git_worktree(path):
        raise StorageRefused(f"{what} resolves inside a git worktree; refusing (BMREC-18)")


# ---------------------------------------------------------------- BMREC-16: free-space floor


def free_bytes(path):
    probe = os.path.abspath(path)
    while not os.path.exists(probe):
        probe = os.path.dirname(probe)
    return shutil.disk_usage(probe).free


# ---------------------------------------------------------------- append-only JSON lines


class JsonLines:
    """Append-only JSON-lines file (manifest.jsonl, events.jsonl). Opened in append mode only."""

    def __init__(self, path):
        self.path = path
        self.fh = open(path, "a", encoding="utf-8", newline="\n")

    def append(self, obj):
        self.fh.write(json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n")
        self.fh.flush()

    def close(self, read_only=False):
        if self.fh:
            self.fh.flush()
            os.fsync(self.fh.fileno())
            self.fh.close()
            self.fh = None
            if read_only:
                make_read_only(self.path)


def make_read_only(path):
    os.chmod(path, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)


def read_jsonl(path):
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


# ---------------------------------------------------------------- recording files


def encode_record(origin, arrival_ns, payload):
    body = _BODY_HEAD.pack(origin, arrival_ns) + payload
    return _REC_HEAD.pack(len(body), zlib.crc32(body) & 0xFFFFFFFF) + body


def encode_note(note, arrival_ns, obj):
    data = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(data) > NOTE_MAX_BYTES:
        raise ValueError(f"note {note} exceeds NOTE_MAX_BYTES")
    return encode_record(ORIGIN_NOTE, arrival_ns, bytes([NOTES[note]]) + data)


class RecordingFile:
    """One hourly file. Created with O_EXCL (never an existing file), append-only while open, read-only after."""

    def __init__(self, path, header):
        self.path = path
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o644)
        self.fh = os.fdopen(fd, "wb", buffering=1 << 20)
        hj = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.fh.write(MAGIC + struct.pack(">I", len(hj)) + hj + struct.pack(">I", zlib.crc32(hj) & 0xFFFFFFFF))
        self.records = 0
        self.first_arrival = None
        self.last_arrival = None
        self.modes = {}
        self.gaps = 0

    def write(self, origin, arrival_ns, payload):
        self.fh.write(encode_record(origin, arrival_ns, payload))
        self._count(arrival_ns)

    def note(self, note, arrival_ns, obj):
        self.fh.write(encode_note(note, arrival_ns, obj))
        if note == "GAP":
            self.gaps += 1
        self._count(arrival_ns)

    def _count(self, arrival_ns):
        self.records += 1
        if self.first_arrival is None:
            self.first_arrival = arrival_ns
        self.last_arrival = arrival_ns

    def count_mode(self, mode_name):
        self.modes[mode_name] = self.modes.get(mode_name, 0) + 1

    def flush(self):
        self.fh.flush()

    def close(self):
        """Flush, fsync, close, hash, set read-only. Returns (sha256, bytes)."""
        self.fh.flush()
        os.fsync(self.fh.fileno())
        self.fh.close()
        sha = sha256_file(self.path)
        size = os.path.getsize(self.path)
        make_read_only(self.path)
        return sha, size


def read_header(fh):
    magic = fh.read(len(MAGIC))
    if magic != MAGIC:
        raise ValueError("bad magic")
    (n,) = struct.unpack(">I", fh.read(4))
    if n > 16 * 1024 * 1024:
        raise ValueError("header too large")
    hj = fh.read(n)
    (crc,) = struct.unpack(">I", fh.read(4))
    if zlib.crc32(hj) & 0xFFFFFFFF != crc:
        raise ValueError("header CRC mismatch")
    return json.loads(hj.decode("utf-8"))


def read_records(path):
    """Walk a file. Returns {"header", "records": [(origin, arrival_ns, payload)], "ok", "bad_offset",
    "truncated_tail_bytes"}. Stops at the first bad record; never repairs (BMREC-20)."""
    size = os.path.getsize(path)
    out = {"header": None, "records": [], "ok": True, "bad_offset": None, "truncated_tail_bytes": 0}
    with open(path, "rb") as fh:
        try:
            out["header"] = read_header(fh)
        except (ValueError, struct.error) as e:
            out.update(ok=False, bad_offset=0, truncated_tail_bytes=size, error=f"header: {e}")
            return out
        while True:
            off = fh.tell()
            head = fh.read(_REC_HEAD.size)
            if not head:
                break
            if len(head) < _REC_HEAD.size:
                out.update(ok=False, bad_offset=off, truncated_tail_bytes=size - off, error="short record header")
                break
            n, crc = _REC_HEAD.unpack(head)
            if n < _BODY_HEAD.size or n > NOTE_MAX_BYTES + 64:
                out.update(ok=False, bad_offset=off, truncated_tail_bytes=size - off, error="bad record length")
                break
            body = fh.read(n)
            if len(body) < n:
                out.update(ok=False, bad_offset=off, truncated_tail_bytes=size - off, error="truncated record")
                break
            if zlib.crc32(body) & 0xFFFFFFFF != crc:
                out.update(ok=False, bad_offset=off, truncated_tail_bytes=size - off, error="CRC mismatch")
                break
            origin, arrival = _BODY_HEAD.unpack_from(body, 0)
            out["records"].append((origin, arrival, body[_BODY_HEAD.size:]))
    return out


def decode_note(payload):
    return NOTE_NAMES.get(payload[0], f"UNKNOWN_{payload[0]}"), json.loads(payload[1:].decode("utf-8"))


# ---------------------------------------------------------------- manifest verification (BMREC-21)


def contained_path(root, rel):
    """root/rel, or None when rel is absolute or climbs out of root (manifest lines and CLI arguments are data)."""
    if os.path.isabs(rel) or os.path.splitdrive(rel)[0]:
        return None
    base = os.path.realpath(root)
    p = os.path.realpath(os.path.join(base, rel))
    return p if os.path.commonpath([base, p]) == base and p != base else None


def verify_run(run_dir):
    """Recompute every closed file's SHA-256 against the manifest. Returns (ok, lines)."""
    man = os.path.join(run_dir, "manifest.jsonl")
    entries = read_jsonl(man)
    lines, ok = [], True
    closed = [e for e in entries if e.get("kind") in ("file_closed", "recovered_close")]
    for e in closed:
        p = contained_path(run_dir, e["file"])
        if p is None:
            ok = False
            lines.append(f"OUTSIDE_RUN_DIR {e['file']}")
            continue
        if not os.path.exists(p):
            ok = False
            lines.append(f"MISSING {e['file']}")
            continue
        got = sha256_file(p)
        if got != e["sha256"]:
            ok = False
            lines.append(f"HASH_MISMATCH {e['file']} manifest={e['sha256']} actual={got}")
        else:
            lines.append(f"OK {e['file']} {got}")
    if not closed:
        lines.append("NO_CLOSED_FILES")
    return ok, lines


def dir_inventory(dirs):
    """BMREC-08: file names + SHA-256 of jars in the configured add-on directories. Labels, never paths."""
    inv = []
    for d in dirs:
        label, path = d["label"], d["path"]
        if not os.path.isdir(path):
            inv.append({"dir": label, "status": "MISSING"})
            continue
        for fn in sorted(os.listdir(path)):
            if fn.lower().endswith(".jar") and os.path.isfile(os.path.join(path, fn)):
                inv.append({"dir": label, "file": fn, "sha256": sha256_file(os.path.join(path, fn))})
    return inv
