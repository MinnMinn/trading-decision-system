# BMREC compliance map — stage H1 (2026-09-26)

Every rule marked **BLOCKING-H1** in `docs/security/2026-09-26-bookmap-recorder-h1.md`, mapped to the code or
document that satisfies it and the test or evidence that checks it. Test names refer to
`scripts/tests/test_h1_bookmap_recorder.py` (class.method); "e2e" means `integrations/bookmap/test/run_e2e.py`;
"build" means `integrations/bookmap/build.py` (fixtures in `tools/allowlist_fixtures.py`).

Status: **Met** · **Met, owner action** (the code side is done; the rule also needs a step only the owner can take,
listed in the README) · **Met, with concern** (see Concerns below).

| Rule | Status | Satisfied by | Checked by |
|---|---|---|---|
| BMREC-01 allowlist bytecode check on the final jar | Met | `tools/allowlist_check.py` + `allowlist.json` (types, members, bootstraps), run by `build.py` on the staged jar | build: 23 BMREC-01 must-fail fixtures (sendOrder/updateOrder on Api, Layer1ApiProvider, Layer1ApiTradingProvider; login/sendUserMessage/close on provider types; trading listener/listenable; Orders/Position/Balance listeners and adapters; `@Layer1TradingStrategy`, `@UnrestrictedData`; registerIndicator*); `TestJavaAllowlistChecker.test_fixtures` |
| BMREC-02 one getProvider site, admin listener only | Met | `AdminConnectionHook.apply` (local variable only); checker's slot/data-flow rule | build: 8 BMREC-02 fixtures (stored in field, passed to method, trading overload, second site, site in another class, returned, cast, other provider method); e2e "connection state MONITORED" |
| BMREC-03 no dynamic reach, no I/O except one pipe open | Met | JDK member allowlist; native/indy/ldc/condy rules; single `FileOutputStream(<ldc \\.\pipe\...>, true)` in `Forwarder.openPipe` | build: 27 BMREC-03 fixtures (reflection, MethodHandles, Class.forName, ClassLoader, URLClassLoader, ServiceLoader, Unsafe, context loader, System.load/loadLibrary/exit, native, Runtime.exec, ProcessBuilder, Socket, URL, HttpClient, SocketChannel, Object streams, Files, FileWriter, non-pipe path, second pipe site, dynamic path, 1-arg ctor, SwitchBootstraps indy) |
| BMREC-04 check tested, mandatory, bound to the pin | Met | `build.py` is the only build; fixtures run on every build; jar reaches `dist/` only after PASS; without `--update-pin` a jar that does not reproduce `addon-pin.json` is deleted; pin holds jar/code/source SHA, JDK, check result | `D:/tmp-tests/h1-build.log` (62 must-fail fixtures failed as expected, clean jar passed, pin reproduced); `TestJavaAllowlistChecker.test_pin_matches_the_built_jar` |
| BMREC-05 one-way pipe | Met | Add-on: FileOutputStream only (no read member allowlisted); recorder: `PIPE_ACCESS_INBOUND` | build: fixtures FileInputStream, RandomAccessFile, getChannel; `TestPipeSecurity.test_creation_flags`, `test_second_instance_and_read_access_are_refused` (client cannot open for read) |
| BMREC-06 admin callbacks → enumerated states | Met | `ConnectionListener` never reads arguments; CONNECTION body is one enum byte; text messages only counted | `TestValidator.test_connection_record_has_no_free_text_field`; e2e "no admin free text anywhere" (marker string) |
| BMREC-07 Bookmap key-less, attested | Met, owner action | Dated owner statement in the security review §9 (2026-09-26); README setup step 4 (re-review trigger) | Security review §9 row Q1 |
| BMREC-08 know what else runs in the JVM | Met, owner action | Jar inventory (name + SHA-256, labels not paths) in every session header and manifest; change → `ADDON_INVENTORY_CHANGED` security event; dirs from Bookmap's own log | `TestSessionProcessing.test_addon_inventory_and_bookmap_version_changes_are_logged`; owner disables the third-party add-ons listed in README step 5 |
| BMREC-09 nothing elevated | Met, owner action | Recorder refuses to run elevated (`is_elevated`, exit 5); README: normal window, Task Scheduler without highest privileges | `TestPipeSecurity.test_preflight_refuses_when_elevated` |
| BMREC-10 Bookmap version is identity | Met | Version read from `Bookmap.jar` manifest into every header/manifest; change → event + new `segment` | `test_addon_inventory_and_bookmap_version_changes_are_logged` |
| BMREC-11 explicit pipe security | Met | `bookmap_pipe.SecurePipeServer`: SDDL `O:<sid>D:P(A;;GA;;;<sid>)`, FIRST_PIPE_INSTANCE, REJECT_REMOTE_CLIENTS, 1 instance, inbound; stdlib multiprocessing listener unused | `TestPipeSecurity.test_dacl_is_owner_only` (reads back the DACL), `test_second_instance_and_read_access_are_refused`, `test_creation_flags`; `TestStaticRules.test_no_secret_loader_order_path_or_credential_store` |
| BMREC-12 squatted name = stop | Met | `PipeSquatted` → security event, exit 3, no retry, no other name | `TestPipeSecurity.test_squatted_name_makes_the_recorder_exit_nonzero` (real subprocess) |
| BMREC-13 authenticate every client first | Met, with concern C1 | `_on_connect`: kernel PID → image path == pinned exe, same user SID and logon session, jar on disk == pin; then HELLO first with code/source SHA == pin; any failure → disconnect, zero records, reason code, re-listen | `TestPipeSecurity.test_client_with_unpinned_process_path_is_rejected_with_zero_records`, `test_pinned_client_with_wrong_jar_on_disk_is_rejected`, `test_pinned_client_with_wrong_hello_is_rejected_then_good_client_records`; `TestSessionProcessing.test_hello_code_sha_mismatch_writes_zero_records`, `test_first_frame_must_be_hello`; preflight requires the pinned exe under Program Files (`test_preflight_requires_the_pinned_client_under_program_files`) |
| BMREC-14 sessions are segments | Met | Session id per connection; new session starts INVALID; `SESSION_GAP` in manifest | `TestSessionProcessing.test_reconnect_is_two_sessions_and_one_gap` |
| BMREC-15 validated, never deserialized | Met | `bookmap_frames.py` (struct only): cap before allocation, closed enums, exact schema, finite floats, ranges, counters per space, failure → reason-code note, INVALID, close after 16 | `TestValidator.*`, `TestSessionProcessing.test_checkpoint_makes_book_valid_and_counter_gap_invalidates`, `test_validation_failure_is_a_reason_code_never_a_market_record`, `test_too_many_invalid_frames_close_the_connection` |
| BMREC-16 bounded resources | Met | 64 KiB pipe buffer, 4 KiB frame cap, bounded trade window; free-space floor 20 GiB → stop writing, gap, alert, never delete; resume at 25 GiB | `TestSessionProcessing.test_disk_floor_stops_writing_records_gap_and_never_deletes` |
| BMREC-17 Bookmap never waits | Met | Non-blocking `offer` into a 65 536 bounded queue under an in-memory lock; drops counted → GAP + checkpoint; daemon forwarder; `stop()` bounded 2 s; capped backoff | e2e scenario 2: 70 000 callbacks with no recorder, max 0.07 ms per callback, GAP with the drop count, depth recorded + dropped = 70 000; e2e `stop()` returned in ≤ 1 ms |
| BMREC-18 recordings outside the worktree | Met | `recordings_root` = `C:\TradingData\bookmap-recordings`; `refuse_if_in_worktree` (git + `.git` walk) at start and for backups; only in-repo artefact (`dist/`) is git-ignored | `TestStorageLocation.*` incl. `test_recorder_preflight_refuses_a_root_inside_the_repo`, `test_build_outputs_inside_the_repo_are_ignored` |
| BMREC-19 root ACL; closed files stay closed | Met | Recorder creates the root with owner/SYSTEM/Administrators-only protected DACL and refuses a root writable by broad principals; files created `O_EXCL`, read-only on close | `TestPipeSecurity.test_recording_root_is_created_private`, `test_broad_write_aces_are_detected_and_refused`; `TestFiles.test_round_trip_and_read_only`; `D:/tmp-tests/h1-icacls.log` |
| BMREC-20 length + CRC, no silent repair | Met | Per-record `u32 len` + CRC32; reader stops at first bad record, reports offset/tail, never writes; crash-left files closed as-is (`recovered_close`) | `TestFiles.test_truncated_tail_is_reported_not_repaired`, `test_flipped_byte_stops_at_that_record`, `test_crash_left_file_is_recovered_as_is` |
| BMREC-21 manifest hashes committed before looking | Met, owner action | SHA-256 per closed file in append-only `manifest.jsonl`; `--verify-run`; `--ledger-manifests` → `docs/research/bookmap-manifest-ledger.jsonl` for the owner to commit daily | `TestFiles.test_manifest_hash_matches_files_and_detects_an_edit`; e2e verify |
| BMREC-22 nothing identifying | Met | Relative names only; SID redacted in events; strings from Bookmap validated printable ≤ 256 bytes | `TestFiles.test_manifest_has_no_absolute_paths`; e2e manifest check |
| BMREC-23 verified backup | Met, owner action | `--backup` to `D:\TradingData-backup\bookmap-recordings` (private DACL, outside worktree), SHA-256 verified, never overwrites, dated manifest snapshots, `backup-log.jsonl`, ALERT on mismatch | `TestStorageLocation.test_backup_verifies_hashes_and_flags_a_bad_source`; e2e backup; owner schedules daily |
| BMREC-24 no automatic deletion | Met | Nothing in the recorder deletes/renames under the root; `--record-deletion` ledgers a manual deletion and never deletes | `TestStaticRules.test_nothing_deletes_under_the_recording_root`; `TestSessionProcessing.test_record_deletion_ledgers_and_never_deletes` |
| BMREC-25 recorder event log | Met | `<run>/events.jsonl` (append-only, read-only at end): start/stop, pipe created, accept/reject (reason, exe base name, PID), hello facts, validation failures, gaps, disk stops, every REST fetch (endpoint, times, HTTP status), 429/418 | Event kinds asserted across `TestSessionProcessing`, `TestPipeSecurity`, e2e |
| BMREC-26 one outbound chokepoint | Met | `bookmap_rest.BinancePublic.get`: HTTPS GET to `fapi.binance.com` only, 4 paths, per-path params, default TLS context, redirects refused, timeouts | `TestOutboundAllowlist.test_non_allowlisted_host_path_method_and_params_are_refused_before_a_socket`; `TestStaticRules.test_tls_is_never_weakened_and_nothing_is_signed`, `test_the_only_network_module_is_bookmap_rest`; 24 h egress check is an owner step (README) |
| BMREC-27 no secrets, no order path | Met | No import of the secret loaders or order connector; no credential store, no `config/env.*`, nothing under `C:\Bookmap\Config` | `TestStaticRules.test_imports_are_stdlib_or_own_modules_only`, `test_no_secret_loader_order_path_or_credential_store` |
| BMREC-28 rate budget; validated reference data | Met, with concern C3 | Limit read from `exchangeInfo`; own weight ≤ 10 % of it per minute; skip when IP-wide used weight > 80 %; 429 back-off; 418 halts all calls; schema validation; invalid/refused → UNKNOWN | `TestOutboundAllowlist.test_budget_starts_with_exchangeinfo_and_uses_its_limit`, `test_429_backs_off_and_418_halts`, `test_malformed_body_is_invalid_and_never_a_match` |
| BMREC-30 jar pin verified by the recorder | Met, with concern C2 | Recorder hashes the jar at `C:\TradingData\bookmap-addon\tds-h1-recorder.jar` at start and at every connection against `addon-pin.json`; hello code/source SHA must equal the pin | `TestPipeSecurity.test_pinned_client_with_wrong_jar_on_disk_is_rejected`; e2e "built jar equals the committed pin", "hello carried the pinned code SHA" |
| BMREC-31 dependency-free build | Met | Pinned `javac 21.0.12`; compile classpath = `bm-simplified-api-wrapper.jar` + `bm-l1api.jar` (compile-only, hashes in the pin); jar holds only the project package + manifest | `D:/tmp-tests/h1-build.log` (JDK version, `jar tf`); fixture `jar_foreign_package` |
| BMREC-32 Python dependencies | Met | Standard library only (Win32 security via `ctypes`) | `TestStaticRules.test_imports_are_stdlib_or_own_modules_only` |
| BMREC-34 add-on dirs not writable by others | Met, owner decision recorded | Single human account on this PC (security review §9, Q5) → recorded and accepted per the rule's own text | `D:/tmp-tests/h1-icacls.log`; concern C1 |
| BMREC-35 logs carry no secrets or account text | Met | The add-on logs nothing; recorder logs only enumerated/validated fields, SID redacted | e2e marker check; `TestFiles.test_manifest_has_no_absolute_paths` |

Not blocking H1 and not implemented here: BMREC-33 (CI scanning, DEFERRED-H2), BMREC-36..39 (DEFERRED-H2/H4).
BMREC-29 is reserved.

## Concerns (read before the first recording)

- **C1 — `C:\Program Files\Bookmap` is writable by `BUILTIN\Users`.** Read-only `icacls` shows
  `BUILTIN\Users:(OI)(CI)(F)` on `C:\Program Files\Bookmap` and on `C:\Bookmap`. BMREC-13 pins the client executable
  partly because "standard users cannot write" under Program Files; on this install they can. With one human
  account (Q5) this adds nothing a same-user attacker could not already do (security review §2, "honest limit of
  TB2"), so it is accepted under BMREC-34's single-account clause. If a second account is ever created, removing
  that ACE (administrator) becomes a precondition for recording.
- **C2 — the hello carries `code_sha256`, not the jar's own SHA-256.** A jar cannot contain its own hash, and
  reading its own file from inside Bookmap needs APIs BMREC-03 bans. The pin records jar, code and source hashes; the
  recorder recomputes the jar hash from disk (the control BMREC-30 names) and the hello must match the pin's
  code/source hashes. The pin's "source git SHA" is `source_sha256` (hash of the committed sources) plus
  `built_from_commit` (the parent commit), because the pin is committed together with the source it describes.
- **C3 — request weights are assumptions to verify.** `WEIGHT_*` in the contract are Binance's published weights as
  understood on 2026-09-26; the IP-wide `X-MBX-USED-WEIGHT-1M` header is the actual control. Confirm during the
  24 h run.
- **C4 — facts H1 still has to observe in real Bookmap** (plan §0): whether Bookmap calls the connection listener
  obtained through the Simplified wrapper (the e2e harness proves the add-on reaches and registers it; only a real
  disconnect proves Bookmap calls it), whether `onRealtimeStart` fires, what `onSnapshotEnd` means after a
  reconnect, `pips` vs tick, `isFullDepth`, auto re-enable. The recorder is conservative on each: `MONITOR_UNAVAILABLE`
  → `connection_state=UNKNOWN`; no `onRealtimeStart` → never LIVE; no snapshot after a restore → book stays INVALID;
  tick mismatch or no verification within an hour → recording aborts.
- **C5 — one instrument per recorder in H1.** The pipe has exactly one instance (BMREC-11), so a second enabled chart
  stays idle. Recording several instruments needs multiplexing or more pipes, which is a security re-review.
