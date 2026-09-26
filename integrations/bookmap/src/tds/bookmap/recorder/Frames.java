package tds.bookmap.recorder;

/**
 * Wire constants for docs/contracts/bookmap-recorder-frames.md. Every value here is mirrored in
 * scripts/bookmap_frames.py; the contract's parameter table is the single source and a Python test parses it.
 */
final class Frames {
    private Frames() {
    }

    /** Compile-time constant (BMREC-03): the only path the add-on ever opens, for writing only (BMREC-05). */
    static final String PIPE_PATH = "\\\\.\\pipe\\tds-bookmap-recorder-h1";

    static final int SCHEMA_VERSION = 1;
    static final int HEADER_BYTES = 36;
    static final int FRAME_MAX_BYTES = 4096;
    static final int STRING_MAX_BYTES = 256;

    static final int QUEUE_CAPACITY = 65536;
    static final long HEARTBEAT_INTERVAL_MS = 1000L;
    static final long TIME_RECORD_MIN_INTERVAL_NS = 100_000_000L;
    static final long RECONNECT_BACKOFF_INITIAL_MS = 250L;
    static final long RECONNECT_BACKOFF_CAP_MS = 30_000L;
    static final long STOP_JOIN_TIMEOUT_MS = 2000L;

    static final int MODE_HISTORICAL = 0;
    static final int MODE_LIVE = 3;

    static final int T_HELLO = 1;
    static final int T_DEPTH = 2;
    static final int T_TRADE = 3;
    static final int T_TIME = 4;
    static final int T_MODE = 5;
    static final int T_CONNECTION = 6;
    static final int T_HEARTBEAT = 7;
    static final int T_GAP = 8;
    static final int T_SNAPSHOT_END = 9;
    static final int T_CHECKPOINT_BEGIN = 10;
    static final int T_CHECKPOINT_LEVEL = 11;
    static final int T_CHECKPOINT_END = 12;
    static final int T_ADDON_STOP = 13;

    static final int CONN_LOST = 1;
    static final int CONN_RESTORED = 2;
    static final int CONN_LOGIN_FAILED = 3;
    static final int CONN_LOGIN_SUCCESSFUL = 4;
    static final int CONN_MONITOR_ACTIVE = 5;
    static final int CONN_MONITOR_UNAVAILABLE = 6;

    static final int GAP_QUEUE_OVERFLOW = 1;

    static final int CKPT_SESSION_START = 1;
    static final int CKPT_AFTER_GAP = 2;
    static final int CKPT_AFTER_SNAPSHOT_END = 3;
}
