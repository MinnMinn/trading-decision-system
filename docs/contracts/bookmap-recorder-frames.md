# Contract: Bookmap recorder frames (stage H1)

- **Status:** v1, 2026-09-26. Single source for both implementations:
  - Java add-on: `integrations/bookmap/src/tds/bookmap/recorder/` (writer side).
  - Python recorder: `scripts/bookmap_frames.py` (validator), `scripts/bookmap_store.py` (files),
    `scripts/bookmap_recorder.py` (session logic), `scripts/bookmap_rest.py` (reference data).
- **Governing:** `docs/plans/2026-09-26-heatmap-realtime-plan.md` (v3) §1.3-§1.5, §1.8, stage H1;
  `docs/security/2026-09-26-bookmap-recorder-h1.md` rules BMREC-05, -06, -13, -14, -15, -18..-22, -26, -28, -30.
- **Change rule:** any change to a layout, an enum value or a parameter below bumps `SCHEMA_VERSION` (frames) or
  `FILE_FORMAT_VERSION` (files). The recorder accepts exactly one schema version (BMREC-15), so both sides move
  together in one commit. `scripts/tests/test_h1_bookmap_recorder.py` parses the parameter table below and fails
  if the code constants disagree with it.

## 1. Transport

- Windows named pipe `\\.\pipe\tds-bookmap-recorder-h1` (compile-time constant in the add-on, BMREC-03).
- **One-way** (BMREC-05): the add-on only writes, the recorder only reads. The pipe is created inbound-only. There
  is no acknowledgement, command or configuration message from Python to Java of any kind.
- Byte stream. Every frame is `u32 length` (big-endian, length of the payload that follows, excluding these 4
  bytes) followed by the payload. A length of 0 or above `FRAME_MAX_BYTES` closes the connection before any
  allocation (BMREC-15).
- All integers are big-endian two's complement. `f64` is IEEE-754 binary64, big-endian. Every `f64` must be finite.
- `str` = `u16 byte_length` + UTF-8 bytes, `byte_length <= STRING_MAX_BYTES`, printable characters only (no
  control characters). `ostr` (optional string) = `u8 present` (0/1) + `str` when present.
- Booleans are `u8` with value exactly 0 or 1.

## 2. Common header (every frame, 36 bytes)

| Offset | Field | Type | Meaning |
|---|---|---|---|
| 0 | `schema_version` | u16 | Must equal `SCHEMA_VERSION` exactly |
| 2 | `record_type` | u8 | Closed enum, §3 |
| 3 | `mode` | u8 | 0 HISTORICAL, 1 BACKFILL, 2 REPLAY, 3 LIVE (plan §1.4) |
| 4 | `seq` | u64 | Counter in the record type's sequence space (§4) |
| 12 | `addon_recv_ns` | i64 | Add-on wall clock (epoch ns) when the callback fired / the record was generated |
| 20 | `addon_send_ns` | i64 | Add-on wall clock when the frame was put into the write buffer |
| 28 | `bookmap_time_ns` | i64 | Last value of `TimeListener.onTimestamp` seen by the add-on; `-1` = not yet known. **Bookmap's clock, never an exchange event time** (plan §0, §1.3) |

The add-on sends `mode` = HISTORICAL until `HistoricalModeListener.onRealtimeStart`, then LIVE. It never sends
BACKFILL or REPLAY today (the Simplified API gives no reliable signal for them); the values are reserved so a
recording that carries them can be refused. A replay can still reach LIVE: see §7 for why `mode == LIVE` alone
never makes a record live-usable.

## 3. Record types (closed enum)

| Id | Name | Space | Body |
|---|---|---|---|
| 1 | HELLO | forwarder | see §3.1 |
| 2 | DEPTH | capture | `u8 is_bid`, `i32 price_level`, `i32 size` (`size >= 0`; 0 = level removed) |
| 3 | TRADE | capture | `f64 price_level`, `i32 size` (`> 0`), `u8 is_bid_aggressor`, `u8 is_otc`, `u8 is_execution_start`, `u8 is_execution_end` |
| 4 | TIME | capture | empty. Emitted when Bookmap time advanced by at least `TIME_RECORD_MIN_INTERVAL_NS` since the last TIME record |
| 5 | MODE | capture | empty. Header `mode` is the new mode (the LIVE boundary) |
| 6 | CONNECTION | capture | `u8 state`: 1 LOST, 2 RESTORED, 3 LOGIN_FAILED, 4 LOGIN_SUCCESSFUL, 5 MONITOR_ACTIVE, 6 MONITOR_UNAVAILABLE. No text, no reason object (BMREC-06) |
| 7 | HEARTBEAT | forwarder | `u32 queue_depth`, `u32 queue_capacity`, `u64 dropped_total`, `u64 capture_seq_last`, `u64 frames_sent_total`, `u64 ignored_admin_messages`, `u32 pipe_reconnects` |
| 8 | GAP | forwarder | `u8 cause` (1 QUEUE_OVERFLOW), `u64 dropped_count` since the previous GAP |
| 9 | SNAPSHOT_END | capture | empty (`SnapshotEndListener.onSnapshotEnd`) |
| 10 | CHECKPOINT_BEGIN | forwarder | `u8 reason` (1 SESSION_START, 2 AFTER_GAP, 3 AFTER_SNAPSHOT_END), `u8 bookmap_snapshot_complete`, `u32 bid_levels`, `u32 ask_levels`, `u64 capture_seq_at` |
| 11 | CHECKPOINT_LEVEL | forwarder | `u8 is_bid`, `i32 price_level`, `i32 size` (`> 0`) |
| 12 | CHECKPOINT_END | forwarder | `u32 levels_emitted` (must equal `bid_levels + ask_levels`) |
| 13 | ADDON_STOP | forwarder | empty (clean `stop()`) |

**Full resolution (plan §1.0: Heatmap is read on a continuous time × price picture, not on candles).** Every
`onDepth` call is exactly one DEPTH record and every `onTrade` call is exactly one TRADE record, each with its own
`addon_recv_ns` and `bookmap_time_ns`. Nothing is bucketed, coalesced, bar-aggregated or downsampled, in the add-on
or in the recorder. Book checkpoints (§5, and the recorder's per-file BOOK_CHECKPOINT) are **additional** records
that never replace a delta. The only throttled stream is TIME, a clock marker for quiet periods; it carries no
market data, and every DEPTH/TRADE record still carries the latest Bookmap time at full resolution.

Prices are **level numbers**: price = level × `pips`; trade levels can be fractional (plan §0). Sizes are integers
premultiplied by `sizeMultiplier`. Normalization is H2's job, not the recorder's.

### 3.1 HELLO body

`str addon_version`, `str code_sha256` (64 lower-case hex), `str source_sha256` (64 hex), `u32 queue_capacity`,
`u8 connection_monitor` (1 ACTIVE, 0 UNAVAILABLE), `str alias`, `ostr symbol`, `ostr exchange`, `ostr type`,
`ostr full_name`, `ostr requested_symbol`, `f64 pips`, `f64 multiplier`, `f64 size_multiplier`, `i64 data_delay`,
`u8 is_full_depth`, `u8 is_crypto`, `u8 is_api_protected`, `u8 is_nbbo_supported`, `ostr recording_tag`.

**Why the hello carries `code_sha256` and not the jar's own SHA-256.** A jar cannot contain its own hash, and
reading its own file from inside Bookmap needs file-read and class-introspection APIs that BMREC-03 bans. The
build computes `code_sha256` over every class file except `BuildInfo.class` and bakes it into `BuildInfo`; the
pin (`integrations/bookmap/addon-pin.json`) records `code_sha256`, `source_sha256` **and** `jar_sha256`. The
control is BMREC-30: the **recorder** recomputes the jar's SHA-256 at its load location at start-up and at every
connection and compares it with the pin; the hello's `code_sha256`/`source_sha256` must also equal the pin. A
mismatch on either rejects the client with zero records written.

## 4. Sequence spaces and counters

- **Capture space** (DEPTH, TRADE, TIME, MODE, CONNECTION, SNAPSHOT_END): `seq` is assigned under the add-on's
  capture lock at the moment the callback fires, **before** the bounded-queue offer. A record dropped on queue
  overflow therefore leaves a hole the recorder can see. The counter spans the add-on instance (it does not reset
  on a pipe reconnect). Limit, stated wherever it is used: this counter detects only loss **inside the add-on and
  on the pipe**. It says nothing about what Bookmap or the exchange feed lost (plan §1.5).
- **Forwarder space** (HELLO, HEARTBEAT, GAP, CHECKPOINT_*, ADDON_STOP): `seq` starts at 1 with HELLO on every
  pipe connection.
- The recorder checks each space for `seq == previous + 1`. The first capture record of a session sets the
  baseline. `CHECKPOINT_BEGIN.capture_seq_at` must equal the last capture `seq` received in that session (if any);
  the next capture record must be `capture_seq_at + 1`. Any violation writes a GAP note and marks the book
  INVALID (BMREC-15).

## 5. Book checkpoints and validity (plan §1.5, BMREC-14)

- The add-on mirrors the book it has been sent (level → size per side) under the capture lock. On a new pipe
  session, after a queue overflow and after every `onSnapshotEnd`, the forwarder takes the lock, drains the queue,
  copies the mirror, releases the lock, sends the drained records, then a GAP (after overflow only), then
  `CHECKPOINT_BEGIN`, one `CHECKPOINT_LEVEL` per non-empty level, and `CHECKPOINT_END`. The callback thread waits
  only for that in-memory copy, never on I/O (BMREC-17).
- The recorder's book is INVALID at session start, after any gap (counter hole, add-on GAP, session gap, disk
  stop), after any validation failure, after `CONNECTION LOST`, and on a crossed/locked top of book. It becomes
  VALID only on a complete `CHECKPOINT_END` whose `bookmap_snapshot_complete == 1`, with no gap between
  `CHECKPOINT_BEGIN` and `CHECKPOINT_END`, and — after a `LOST` — only when an `onSnapshotEnd` has arrived after the
  `RESTORED` and been followed by such a checkpoint. If Bookmap never re-sends a snapshot after a restore, the
  book stays INVALID: that is the conservative reading of a fact still "to verify" (plan §0).

## 6. Recording files (recorder only; BMREC-18..22)

- Root from `integrations/bookmap/recorder-config.json` (`recordings_root`); refused if it resolves inside any git
  worktree (BMREC-18). One directory per recorder run: `<root>/<run_id>/`.
- Files are hourly by **Python arrival** UTC hour: `<run_id>/<YYYYMMDD>T<HH>Z-s<session>-f<seq>.bmrec`.
- File layout: magic `BMREC\x00\x01\n` (8 bytes), `u32 header_len`, header JSON (UTF-8), `u32 crc32(header)`,
  then records.
- Record layout: `u32 body_len`, `u32 crc32(body)`, body = `u8 origin` + `i64 arrival_ns` + payload.
  - `origin` 0: payload = the validated frame payload exactly as received (header + body, without the length
    prefix). `arrival_ns` = Python `time.time_ns()` when the read that delivered the frame completed. This is the
    record's `availableTime` (plan §1.3).
  - `origin` 1: recorder note. payload = `u8 note_type` + JSON (≤ `NOTE_MAX_BYTES`). Note types: 1 SESSION_START,
    2 SESSION_END, 3 BOOK_CHECKPOINT (first record of every file, so each file replays on its own), 4
    VALIDATION_FAILURE (reason code only, never raw bytes), 5 GAP, 6 BOOK_STATE, 7 CLOCK, 8 RECON_DEPTH, 9
    RECON_AGGTRADES, 10 EXCHANGE_FILTERS, 11 STREAM_STATE.
- The CRC is **accident detection only, not tamper evidence** (BMREC-20). Readers stop at the first bad record and
  report its offset and the truncated tail length; they never repair, skip or rewrite. Tamper evidence is the
  manifest SHA-256 committed to the ledger (BMREC-21).
- Header JSON: `format`, `file_format_version`, `schema_version`, `run_id`, `session_id`, `file_seq`, `segment`,
  `hour_utc`, instrument info and versions from the HELLO, `jar_sha256` (as verified by the recorder),
  `bookmap_version` (from `Bookmap.jar`'s manifest), `exchange_filters` (tick size, step size, status),
  `clock_offset` (vs Binance server time, or `UNKNOWN`), `addon_inventory` (file names + SHA-256 of jars in the
  configured add-on directories, BMREC-08), `recorder_code_sha256`, `params`. No absolute path, host name or user
  name (BMREC-22).
- A closed file is flushed, fsynced, hashed, set read-only, and never reopened for write (BMREC-19).
- Manifest `<run_id>/manifest.jsonl` is append-only: `run_start`, `session_start`, `session_end`, `file_closed`
  (relative name, SHA-256, bytes, records, arrival range, modes, gaps, exchange tick, Bookmap version, segment),
  `recovered_close` (a file left open by a crash, closed on the next start with its truncated tail reported),
  `gap`, `security_event`, `run_end`. A Bookmap version, code SHA, instrument or tick change between sessions
  starts a new `segment` (BMREC-10).
- Event log `<run_id>/events.jsonl` (BMREC-25) lists every start/stop, pipe creation, client accept/reject (reason
  code, executable base name, PID), hello facts, validation-failure counts, gaps and causes, disk stops, and every
  REST fetch (endpoint, request/response time, HTTP status), 429/418.

## 7. Live-usability (plan §1.3-§1.4; enforced in H4, labelled from H1)

A record is live-usable only if **all** hold: `mode == LIVE`; the session's `data_delay == 0` (the value 1 is
`UNKNOWN_DELAY`); `recording_tag` absent; the session passed BMREC-13 and BMREC-30; and, for book-derived use, the
book is VALID. `mode != LIVE` is never live-usable. The recorder labels sessions and files with this flag; H1
makes no decisions.

## 8. Parameters (pre-registered before the first recording; plan H1 "numeric tolerances", N2)

These values are fixed now, before any recorded data has been looked at. Changing one after recording starts is
a research event: bump the version and note it in the ledger.

| Parameter | Value | Meaning |
|---|---|---|
| `SCHEMA_VERSION` | 1 | Frame schema version, exact match |
| `FILE_FORMAT_VERSION` | 1 | Recording file format version |
| `FRAME_MAX_BYTES` | 4096 | Max frame payload; larger closes the connection |
| `STRING_MAX_BYTES` | 256 | Max UTF-8 bytes of one `str` |
| `NOTE_MAX_BYTES` | 262144 | Max JSON bytes of one recorder note (book checkpoints) |
| `QUEUE_CAPACITY` | 65536 | Add-on bounded queue (records) |
| `HEARTBEAT_INTERVAL_MS` | 1000 | Add-on timer heartbeat, independent of market activity |
| `TIME_RECORD_MIN_INTERVAL_NS` | 100000000 | Minimum Bookmap-time step between TIME records |
| `RECONNECT_BACKOFF_INITIAL_MS` | 250 | Add-on pipe reconnect, first delay |
| `RECONNECT_BACKOFF_CAP_MS` | 30000 | Add-on pipe reconnect, cap (doubling) |
| `STOP_JOIN_TIMEOUT_MS` | 2000 | Bound on `stop()` waiting for the forwarder |
| `MAX_CONSECUTIVE_INVALID_FRAMES` | 16 | Consecutive validation failures that close the connection |
| `STREAM_SILENCE_STALE_MS` | 5000 | No frame for this long marks the stream STALE |
| `CLOCK_DRIFT_INVALID_MS` | 5000 | LIVE only: `abs(bookmap_time − addon_recv)` above this marks the stream INVALID |
| `DEPTH_RECON_INTERVAL_S` | 60 | REST depth cross-check period |
| `DEPTH_RECON_REST_LIMIT` | 20 | `limit` sent to `/fapi/v1/depth` |
| `DEPTH_RECON_LEVELS` | 10 | Top levels per side compared |
| `DEPTH_RECON_SAMPLE_MS` | 50 | Book top-N sampling period while a depth request is in flight |
| `DEPTH_RECON_ALIGN_WINDOW_MS` | 250 | A sample must lie within this of the snapshot's `T` (mapped with the clock offset), else UNKNOWN |
| `DEPTH_RECON_MIN_MATCH_FRACTION` | 0.8 | Per side, fraction of compared levels whose price and size match exactly |
| `DEPTH_RECON_FAIL_STREAK_INVALID` | 3 | Consecutive MISMATCH results that mark the book INVALID and alert |
| `AGG_RECON_INTERVAL_S` | 300 | `aggTrades` reconciliation period |
| `AGG_RECON_WINDOW_S` | 60 | Window length compared |
| `AGG_RECON_LAG_S` | 30 | Window ends this long before now |
| `AGG_RECON_VOLUME_REL_TOL` | 0.01 | Per aggressor side, `abs(recorded − rest) / rest` |
| `CLOCK_OFFSET_INTERVAL_S` | 60 | `/fapi/v1/time` period |
| `REST_BUDGET_FRACTION` | 0.1 | Own request weight per minute, as a fraction of the REQUEST_WEIGHT limit read from `exchangeInfo` |
| `REST_IP_HEADROOM_FRACTION` | 0.8 | Skip a request when the last `X-MBX-USED-WEIGHT-1M` exceeds this fraction of the limit (other callers share the IP) |
| `REST_TIMEOUT_S` | 5 | Connect/read timeout |
| `REST_429_BACKOFF_INITIAL_S` | 30 | First back-off after HTTP 429 (or `Retry-After` if larger) |
| `REST_429_BACKOFF_CAP_S` | 600 | Back-off cap |
| `WEIGHT_DEPTH_LIMIT_20` | 2 | Request weight assumed for depth `limit=20` |
| `WEIGHT_AGGTRADES` | 20 | Request weight assumed for `aggTrades` |
| `WEIGHT_EXCHANGEINFO` | 1 | Request weight assumed for `exchangeInfo` |
| `WEIGHT_TIME` | 1 | Request weight assumed for `time` |
| `FREE_SPACE_FLOOR_BYTES` | 21474836480 | 20 GiB: below this the recorder stops writing, records a gap and alerts; it never deletes |
| `FREE_SPACE_RESUME_BYTES` | 26843545600 | 25 GiB: writing resumes above this |
| `TICK_GATE_DEADLINE_S` | 3600 | The first-hour gate: `pips`/tick and `sizeMultiplier`/step must be verified within this, else recording aborts |

The four `WEIGHT_*` values are Binance's published USDⓈ-M weights as understood on 2026-09-26 and are
**assumptions to verify** during the 24 h run. They are not the control: the recorder also reads the IP-wide
`X-MBX-USED-WEIGHT-1M` header on every response and applies `REST_IP_HEADROOM_FRACTION` to it (BMREC-28).

### 8.1 How the cross-checks decide (the rules behind the numbers)

- **Depth.** A REST snapshot has no sequence id shared with Bookmap, so alignment is by time only. While the
  request is in flight the recorder samples its book's top `DEPTH_RECON_LEVELS` every `DEPTH_RECON_SAMPLE_MS`.
  The snapshot's `T` is mapped to local time with the latest clock offset; the closest sample within
  `DEPTH_RECON_ALIGN_WINDOW_MS` is compared. REST prices convert to levels as `price / pips`, which must be an
  integer within 1e-6, and sizes as `qty × sizeMultiplier`, rounded. Result per side: MATCH if the matching fraction
  ≥ `DEPTH_RECON_MIN_MATCH_FRACTION`, else MISMATCH. No sample in the window, an invalid response, a book that is
  not VALID, or a budget refusal gives **UNKNOWN, never MATCH** (BMREC-28, CLAUDE.md §20).
- **aggTrades.** Window `[now − AGG_RECON_LAG_S − AGG_RECON_WINDOW_S, now − AGG_RECON_LAG_S]` in server time.
  Recorded trades are placed in server time as `addon_recv_ns` + clock offset. Compared per aggressor side
  (`m == false` is a buyer-aggressor trade, matching `is_bid_aggressor == 1`): total volume in lots. A response
  that hits the endpoint's 1000-row limit is UNKNOWN (truncated), as is any window touching a gap or a
  non-LIVE record.
- **Clock offset.** `offset_ms = serverTime − (t_send + t_recv) / 2`, with `rtt_ms` recorded beside it.
