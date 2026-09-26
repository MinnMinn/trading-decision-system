# Security review — Bookmap recorder, stage H1 (read-only add-on → named pipe → Python recorder)

Date: 2026-09-26 · Reviewer: security-engineer-subagent · Status: **advisory, pre-implementation (no H1 code exists yet)**
Design under review: `docs/plans/2026-09-26-heatmap-realtime-plan.md` (v3): §0, §1 (esp. 1.3-1.8), stage H1 (lines 87-139).
Rule prefix: **BMREC-NN** (new; no collision found in the repo). Prior models are cited, not restated:
`docs/security/2026-09-11-top5-pilot.md` (PILOT-NN), `docs/security/2026-09-12-method-panel.md` (PANEL/CRON/CFG-NN).

References read: `~/.claude/references/security-review/checklist.md` (OWASP), `~/.claude/references/data-privacy-patterns.md`.
Same as the method-panel review: **this system holds no customer PII and has no multi-tenant authz**, so the PII
classification, KYC and MAS/PDPA sections do not apply. What carries over is input validation, integrity, secrets, and
the "no PII in logs" rule for the owner's own identifiers.

Severity scale (same as prior reviews): **CRITICAL** blocks the first recording · **HIGH** blocks the H1 exit (24 h run)
· **MEDIUM/LOW** fix before recordings are used for H5 research. Gate column: **BLOCKING-H1** or **DEFERRED-H2/H4**.

### Facts verified this session (cited below by these tags)

| Tag | Fact | Source |
|---|---|---|
| F1 | `Api.getProvider()` returns `velox.api.layer1.Layer1ApiProvider` ("Allows advanced actions that require direct access to L1 stack") | `D:/tmp-tests/bmdoc/velox/api/layer1/simplified/Api.html:170-172, 515-518` |
| F2 | `Layer1ApiProvider` **extends** `Layer1ApiTradingProvider` and `Layer1ApiAdminProvider` (and the Data/Instrument providers) | `D:/tmp-tests/bmdoc/l1/velox/api/layer1/Layer1ApiProvider.html:98-99` |
| F3 | `Layer1ApiTradingProvider` declares `sendOrder`, `updateOrder` | `.../l1/velox/api/layer1/Layer1ApiTradingProvider.html:120,125` |
| F4 | `Layer1ApiAdminProvider` declares `close`, `getCurrentTime`, `getSource`, `getSupportedFeatures`, **`login`**, **`sendUserMessage`** | `.../l1/velox/api/layer1/Layer1ApiAdminProvider.html:120-146` |
| F5 | `Api` itself exposes `sendOrder`, `updateOrder`, `sendUserMessage`, `registerIndicator*` | `.../simplified/Api.html:180-244` |
| F6 | `addListener`/`removeListener` exist on both `Layer1ApiAdminListenable` and `Layer1ApiTradingListenable` (same name, different parameter type) | `.../l1/velox/api/layer1/Layer1ApiAdminListenable.html:114,119`, `Layer1ApiTradingListenable.html:114,119` |
| F7 | `Layer1ApiAdminListener` callbacks: `onConnectionLost`, `onConnectionRestored`, `onLoginFailed`, `onLoginSuccessful`, `onSystemTextMessage`, `onUserMessage` | `.../l1/velox/api/layer1/Layer1ApiAdminListener.html:116-144` |
| F8 | The Simplified API offers account-data listeners: `OrdersListener`, `PositionListener`, `BalanceListener` (+ adapters) | `D:/tmp-tests/bmdoc/velox/api/layer1/simplified/` file listing |
| F9 | Python stdlib `multiprocessing.connection` pipe listener calls `CreateNamedPipe(..., PIPE_UNLIMITED_INSTANCES, ..., NULL)` — default security descriptor, no `PIPE_REJECT_REMOTE_CLIENTS` | `C:/Users/nguye/AppData/Local/Programs/Python/Python314/Lib/multiprocessing/connection.py:713-723` |
| F10 | `Connection.recv()` unpickles the payload (`_ForkingPickler.loads`) | same file `:256-261` |
| F11 | Default named-pipe security descriptor: "grant full control to the LocalSystem account, administrators, and the creator owner. They also grant **read access to members of the Everyone group and the anonymous account**." `FILE_FLAG_FIRST_PIPE_INSTANCE`: a second creation "fails with ERROR_ACCESS_DENIED". `PIPE_REJECT_REMOTE_CLIENTS`: "Connections from remote clients are automatically rejected." | Microsoft Learn, CreateNamedPipeA (fetched 2026-09-26) |
| F12 | Repo policy: ignored data was deliberately re-tracked ("push everything that was ignored, except sensitive files"); `data/` history is tracked | `.gitignore:18-24, 78-80` |
| F13 | The repo's signing connector serves both `testnet.binancefuture.com` and **`fapi.binance.com` (REAL MONEY)**; public calls to `/fapi/v1/exchangeInfo`, `/fapi/v1/time` already exist | `scripts/binance-futures-testnet-order.sh:7,110,132` |
| F14 | Existing background jobs are Task Scheduler tasks created by `schtasks /Create` without a run-level flag | `scripts/win_services.py:122-153` |

**Owner statement (2026-09-26, relayed by the coordinator):** no Binance API key/secret has been entered into Bookmap;
the Binance Futures connection is data-only via the Bookmap Global subscription. Credential stores were not read to
confirm this (by instruction); it is recorded as an owner attestation (BMREC-07).

**Not verified (do not assume):** which process image Bookmap's JVM runs as; where Bookmap copies/loads a user add-on jar from; whether
the feed is USDⓈ-M (`fapi`) or COIN-M; the ACL on `C:\Bookmap`; Bookmap's data-licensing terms for stored recordings.

---

## 1. What is new, in one sentence

For the first time, code written by this project runs **inside a third-party process connected to the Binance mainnet
market-data feed** — data-only today, per the owner's statement, but one settings change away from holding mainnet
account keys — and that code is handed an object (`Api`, and via `getProvider()` a `Layer1ApiProvider`)
whose type includes order placement (F1-F5). Everything else here — the pipe, the recorder, the files — is ordinary
local plumbing whose main risks are fake data and lost data, not money.

## 2. Assets, actors, trust boundaries

| Asset | Classification | Where |
|---|---|---|
| Owner's **mainnet** Binance account — **not reachable from Bookmap today** (no keys entered, owner statement 2026-09-26); becomes reachable if keys are ever added | financial — highest | would be Bookmap config (not read) |
| Bookmap JVM integrity (all add-ons share it) | execution integrity | `C:\Program Files\Bookmap`, `C:\Bookmap` |
| Add-on jar | code integrity | build output → Bookmap add-on location (TBD) |
| The feed on the pipe | research-data integrity (public market data, no PII) | `\\.\pipe\<name>` |
| Recording files + manifest | **irreplaceable** research data; §10 dataset identity | recording root (see BMREC-18) |
| Research ledger entries for recordings (hashes, holdout calendar) | research integrity / non-repudiation | repo (tracked) |
| Binance testnet keys in Windows Credential Manager | financial (testnet) | must stay untouched by H1 |

**Actors.** The owner (single Windows user); Bookmap and its built-in Binance adapter; other Bookmap add-ons in the same
JVM; the recorder (Python, long-running, owner's user); Binance public REST; *any other process running as the owner*
(browser extensions, a compromised pip package); *any other local Windows account* (if one exists); a network peer.

**Trust boundaries.**
- **TB1** Bookmap JVM ↔ add-on (in-process, no isolation: the add-on can reach anything Bookmap exposes).
- **TB2** add-on → pipe → recorder (cross-process, same user).
- **TB3** recorder → filesystem (recordings, logs, manifest).
- **TB4** recorder → Binance public REST (internet).
- **TB5** build machine → jar → Bookmap load location (supply chain).
- **TB6** recording root → backup target.

**The honest limit of TB2.** Every control on the pipe is bounded by the Windows user account: a process already running
as the owner can inject into Bookmap's JVM, read any file the owner can, and replace the jar. Pipe controls defend
against *other* users, remote clients, accidental/buggy local processes and opportunistic squatting — not against
malware already running as the owner. That residual is accepted and stated, not engineered around (§7).

## 3. STRIDE

### 3.1 The add-on inside Bookmap (TB1)

| | Threat | Finding |
|---|---|---|
| **S** | The add-on is mistaken for, or registers as, a trading strategy | `@Layer1TradingStrategy` exists (`.../annotations/Layer1TradingStrategy.html`) and would change how Bookmap treats the module. → BMREC-01 |
| **T** | The add-on places, modifies or cancels orders | Order methods are on `Api` itself (F5) **and** on the object `getProvider()` returns (F1-F3). The plan's check ("no `sendOrder`/`updateOrder`, one `getProvider` call site", H1 lines 89-92) only looks at the `Api` surface: once the single allowed site holds a `Layer1ApiProvider`, `provider.sendOrder(...)` is a *different* method reference (owner type `Layer1ApiTradingProvider`/`Layer1ApiProvider`) that a name-on-`Api` check can miss, and `login`/`sendUserMessage` (F4) are not mentioned at all. A **denylist is the wrong shape**; the check must be an allowlist over the compiled bytecode. → BMREC-01, BMREC-02 |
| **T** | The check is bypassed dynamically | Reflection, `MethodHandles`, `Class.forName`, custom class loaders or JNI reach any method without a static call site. → BMREC-03 |
| **R** | No record of what code ran | Without a pinned hash of the *checked* jar, "the add-on is read-only" is a claim about a source tree, not about what Bookmap loaded. → BMREC-04, BMREC-30 |
| **I** | Account data leaves Bookmap | Implementing `OrdersListener`/`PositionListener`/`BalanceListener` (F8), or the trading `addListener` overload (F6), would forward the owner's orders, positions and balances into the recordings. `onSystemTextMessage`/`onUserMessage`/`onLoginFailed` (F7) may carry account or login text. → BMREC-01, BMREC-06 |
| **D** | The add-on stalls Bookmap | A blocking write on Bookmap's callback thread, or a forwarder that never exits on `stop()`, hangs the chart the owner uses for discretionary trading. → BMREC-17 |
| **E** | A command channel into a process holding the trading provider | If the add-on ever *reads* from the pipe, anything that can write to the pipe gains a path into the JVM that holds `Layer1ApiProvider`. → BMREC-05 |

### 3.2 Bookmap itself as a component

| | Threat | Finding |
|---|---|---|
| **S** | Bookmap's Binance session is a trading-capable mainnet identity | **Not present today:** the owner states no key/secret has been entered; the connection is data-only via the Bookmap Global subscription. The threat reappears the moment a key is added (e.g. to see own orders on the chart). Bookmap shows the **mainnet** book (plan §1.6), so any future key would be a real-money key, sitting in a JVM where `getProvider()` hands out a trading provider (F1-F3). → BMREC-07 (attest now, re-review on change) |
| **T** | Other add-ons in the same JVM | Any enabled third-party add-on has the same in-process reach as ours; our allowlist does not constrain it. → BMREC-08 |
| **T** | Add-on directories writable by other local accounts | `C:\Bookmap` is a root-level folder; root-level folders on `C:` may inherit write for Authenticated Users — **not verified**. If so, another local account can replace any add-on jar. → BMREC-34 |
| **R** | Bookmap version changes silently (auto-update) | A version change can change callback semantics under recordings that look identical. → BMREC-10 |
| **I** | Bookmap logs | Bookmap writes its own logs under `C:\Bookmap\Logs`; the add-on must not add secrets or account text to them. → BMREC-35 |
| **D** | Subscription/licence/login loss | Stops data; covered as a quality state (plan §1.5, H4 failure handling), not a security control. |
| **E** | Bookmap or the recorder runs elevated | An elevated JVM gives every add-on administrator reach; an elevated recorder changes the pipe's effective ACL semantics. → BMREC-09 |

### 3.3 The named pipe (TB2)

| | Threat | Finding |
|---|---|---|
| **S** | **Fake-feed injection while Bookmap is down** | When no legitimate client is connected, any local process can connect to the recorder's pipe and write plausible market records into irreplaceable research data. The plan (H2 line 151-153) already rejects a bare localhost port for this reason; the same threat applies to a pipe unless the client is authenticated. → BMREC-13, BMREC-14 |
| **S** | **Pipe-name squatting while the recorder is down** | Pipe names are a global namespace. If another process creates `\\.\pipe\<name>` first, (a) the recorder must not silently start as a second instance, and (b) the add-on, as a client, would stream to the squatter. (b) leaks only public market data plus instrument info and versions — low — but only if the pipe is one-way (a two-way pipe would let the squatter talk back into the JVM: 3.1 E). → BMREC-05, BMREC-12 |
| **S** | Stdlib pipe listener is insecure by default | `multiprocessing.connection` creates the pipe with a NULL security descriptor (Everyone + anonymous read, F9, F11), unlimited instances (F9) and accepts remote clients (no `PIPE_REJECT_REMOTE_CLIENTS`). → BMREC-11 |
| **T** | Malformed or hostile frames | Oversized length prefix (memory exhaustion), NaN/Inf prices, negative sizes, unknown record types, counter jumps. → BMREC-15 |
| **T** | Insecure deserialization | `Connection.recv()` unpickles (F10): a pickle from any connected client is arbitrary code execution in the recorder. → BMREC-15 |
| **R** | Who sent the data | Without per-connection attribution (client PID/image, hello frame, jar hash), a recording cannot show that it came from the pinned add-on. → BMREC-13, BMREC-25 |
| **I** | Other users read the feed | Default DACL grants Everyone read (F11). Public data, so low — but the same DACL is what lets another account *connect*, which is the S threat. → BMREC-11 |
| **D** | Connection hogging | With unlimited instances, a rogue client can occupy instances; with one instance, a rogue client occupying it while Bookmap reconnects blocks the real feed. → BMREC-11, BMREC-13 (reject fast, then re-listen) |
| **E** | Pipe as an entry into the JVM or recorder | Covered by one-way pipe (BMREC-05) and no pickle (BMREC-15). |

### 3.4 The Python recorder process

| | Threat | Finding |
|---|---|---|
| **S** | Recorder impersonates or reuses the trading identity | Nothing in H1 needs a key; any import of the secret loaders or the signing connector (F13) is a scope violation. → BMREC-27 |
| **T** | Recorder "repairs" data | Silently fixing a bad CRC, filling a gap, or re-ordering records falsifies §10/§38. → BMREC-20 |
| **R** | Undocumented rejections and gaps | Rejected clients, validation failures and disk stops must leave evidence. → BMREC-25 |
| **I** | Paths, username, hostname leak into committed artefacts | Manifest hashes go into the tracked ledger; absolute paths under `C:\Users\<name>` identify the owner. → BMREC-22 |
| **D** | Disk full, memory growth | Irreplaceable data plus a system drive shared with Bookmap/Windows. → BMREC-16 |
| **E** | Overprivileged runtime | Scheduled-task pattern exists (F14); it must stay non-elevated. → BMREC-09 |

### 3.5 Recording files and backups (TB3, TB6)

| | Threat | Finding |
|---|---|---|
| **S** | — | Files carry no identity; attribution is via manifest + ledger (T/R rows). |
| **T** | **Silent post-hoc edits bias research** | A week edited or dropped after someone has looked at it is a look-ahead/selection event (CLAUDE.md §9, §43-44). CRC detects accidents, not edits. → BMREC-20, BMREC-21, BMREC-24 |
| **T** | **Recordings inside the worktree get committed or wiped** | The repo's policy re-tracks previously ignored data (F12), so a "git-ignored directory" is one policy change away from committing gigabytes of vendor data to a remote; and `git clean -x` deletes ignored files, destroying irreplaceable data. → BMREC-18 |
| **R** | "Which bytes were the dataset?" | The manifest hash committed to the ledger is the §10 snapshot identity and the tamper-evidence. → BMREC-21 |
| **I** | Redistribution of vendor data | Recorded Bookmap data may be subject to Bookmap/Binance licence terms — **I do not know those terms**. Keeping recordings out of the pushed repo avoids accidental redistribution. → BMREC-18, BMREC-23 (open question Q6) |
| **D** | Single-disk loss | "Irreplaceable" (plan §1.1) + one disk = one failure from total loss. → BMREC-23 |
| **E** | Other accounts write the recording root | → BMREC-19 |

### 3.6 Outbound Binance public calls (TB4)

| | Threat | Finding |
|---|---|---|
| **S** | MITM / wrong host | Disabled TLS verification or a redirect to another host would let a peer feed fake reference snapshots into the cross-check, making a divergent book "reconcile". → BMREC-26 |
| **T** | Bad reference data accepted | A malformed/partial REST response treated as a "match" hides a divergent book. → BMREC-28 |
| **R** | Cross-check provenance | Each reference fetch must be recorded (endpoint, request time, response time, status) so the reconciliation is auditable. → BMREC-25 |
| **I** | Key leakage | Only if the recorder signs requests — it must not. → BMREC-26, BMREC-27 |
| **D** | **IP-wide rate-limit ban** | Binance limits are per IP; the recorder shares the IP with every other Binance caller on this machine. An aggressive cross-check (depth snapshots are heavy) can get the IP throttled or banned and take down the rest of the platform's data feeds. → BMREC-28 |
| **E** | — | Unsigned public GETs carry no authority. |

### 3.7 Supply chain (TB5): add-on jar and Python dependencies

| | Threat | Finding |
|---|---|---|
| **S** | A different jar is loaded than the one checked | Pinning is only meaningful if a party *other than the jar itself* verifies it; a tampered jar would skip its own self-check. → BMREC-30 |
| **T** | Third-party code bundled into the jar | Shading any library into the add-on imports its reach into the Bookmap JVM. → BMREC-31 |
| **T** | Python dependency compromise | The recorder is long-running with the owner's file access; a new dependency (e.g. for Win32 security APIs) is new code in that process. → BMREC-32 |
| **R** | Unreproducible build | Without JDK version, classpath and source SHA recorded next to the pin, the pin cannot be re-derived. → BMREC-30, BMREC-31 |
| **I/D/E** | — | Subsumed by the rows above. |

## 4. OWASP Top 10 (2021)

| | Applies? | Rules |
|---|---|---|
| A01 Broken access control | **Yes** — pipe DACL/instances/remote clients; recording-root ACL; add-on's access to the trading provider. | BMREC-01, 02, 05, 11, 13, 19, 34 |
| A02 Cryptographic failures | **Partly.** TLS verification on outbound calls; SHA-256 manifest/jar pins. No encryption at rest needed — recordings are public market data with no PII (explicit decision, not an omission). | BMREC-21, 26, 30 |
| A03 Injection | **Yes** — hostile frames into the recorder. | BMREC-15 |
| A04 Insecure design | **Yes** — denylist-shaped trading check; two-way pipe; recordings in the worktree. | BMREC-01, 05, 18 |
| A05 Security misconfiguration | **Yes** — stdlib pipe defaults (F9/F11); elevated processes; writable add-on dirs. | BMREC-09, 11, 34 |
| A06 Vulnerable/outdated components | **Yes** — add-on build inputs, Python deps, Bookmap version. | BMREC-10, 31, 32, 33 |
| A07 Identification & authentication failures | **Yes** — pipe client authentication; Bookmap's Binance credentials. | BMREC-07, 13 |
| A08 Software & data integrity failures | **Yes — the central one for research.** Jar pin; per-record CRC; manifest hashes in ledger; pickle. | BMREC-15, 20, 21, 24, 30 |
| A09 Logging & monitoring failures | **Yes** — rejections, gaps, disk stops, rate-limit responses must be evidenced; logs must not carry secrets/paths. | BMREC-22, 25, 35 |
| A10 SSRF | **Low but real** — the recorder builds URLs; a host/path allowlist at one chokepoint removes the class. | BMREC-26 |
| XSS / XXE | Not applicable: no browser surface and no XML in H1. |  — |

---

## 5. Rules (binding on implementation)

Each rule: WHAT must be true · domain · severity · gate · the finding it closes · how a reviewer verifies it.
Domains: **addon** (Java add-on + its build), **recorder** (Python), **ops** (owner/host configuration), **research**
(ledger/manifests).

### 5.1 Trading-capability exclusion (addon)

**BMREC-01 (CRITICAL, A01/A04/A08) · addon · BLOCKING-H1 — an allowlist bytecode check on the final jar.**
A build step MUST parse every `.class` in the **final jar** (not the source tree) and fail the build unless every
reference to a `velox.api.*` type or member is on an explicit, committed allowlist. The allowlist is expected to contain
only: the module annotations (`@Layer1SimpleAttachable`, `@Layer1ApiVersion`, optionally `@Layer1StrategyName`); the
data-listener interfaces the module implements (depth, trade, time, historical-mode, snapshot-end — exactly those
needed for plan H1 "Capture"); `InstrumentInfo` field reads; `Api.getProvider` (one site, BMREC-02);
`Layer1ApiAdminListenable.addListener/removeListener` with a `Layer1ApiAdminListener` parameter; and the
`Layer1ApiAdminListener` callbacks. Anything else fails, and the following MUST be named in the check's own tests as
must-fail cases: `sendOrder` and `updateOrder` on **any** owner type (`Api`, `Layer1ApiProvider`,
`Layer1ApiTradingProvider`); `login`, `sendUserMessage`, `close` on any `velox.api.layer1` provider type (F4);
any reference to `Layer1ApiTradingProvider`, `Layer1ApiTradingListener`, `Layer1ApiTradingListenable`; implementing or
referencing `OrdersListener`, `PositionListener`, `BalanceListener` or their adapters (F8); the
`@Layer1TradingStrategy` and `@UnrestrictedData` annotations; `registerIndicator*` (not needed by a recorder).
*Closes:* 3.1 S/T/I. *Verify:* the check runs as part of the one build command and exits non-zero on violation; the
must-fail fixtures of BMREC-04 each fail it.

**BMREC-02 (CRITICAL, A01) · addon · BLOCKING-H1 — `getProvider()` is one call site whose result is used for one thing.**
Exactly one invocation of `Api.getProvider` in exactly one named class and method (both recorded in the allowlist).
Its return value MUST only be the receiver of `addListener`/`removeListener` with a `Layer1ApiAdminListener` argument
(descriptor-checked, because the trading overload has the same name, F6). It MUST NOT be stored in any field
(no `putfield`/`putstatic` of a provider type), returned, passed as an argument, or cast. Rationale: `getProvider()`
returns `Layer1ApiProvider`, which *is* a `Layer1ApiTradingProvider` (F1-F3); the plan's "one call site" is necessary
but not sufficient.
*Closes:* 3.1 T. *Verify:* check output lists exactly one site; must-fail fixtures for "stored in field",
"passed to a method", "trading `addListener` overload".

**BMREC-03 (CRITICAL, A04/A08) · addon · BLOCKING-H1 — no dynamic reach, no I/O except one pipe open.**
The same check MUST fail on any reference to: `java.lang.reflect.*`; `MethodHandles.Lookup` find/unreflect methods;
`Class.forName`, `ClassLoader` (subclassing, `defineClass`, `URLClassLoader`), `ServiceLoader`; `sun.misc.Unsafe` /
`jdk.internal.*`; `System.load`/`loadLibrary` and any `native` method; `Runtime.exec`, `ProcessBuilder`;
`java.net.*`, `java.net.http.*`, socket channels; `ObjectInputStream`/`ObjectOutputStream`; any file write API — with
**one** allowlisted site that opens the pipe for writing, whose path is a compile-time constant beginning with
`\\.\pipe\`. `invokedynamic` is allowed only with the `LambdaMetafactory` and `StringConcatFactory` bootstraps.
*Closes:* 3.1 T (bypass), plan §1.8 "no network calls, writes no files". *Verify:* must-fail fixtures per item.

**BMREC-04 (HIGH, A08/A09) · addon · BLOCKING-H1 — the check is tested, mandatory, and bound to the pin.**
(a) A fixture set of small classes, one per forbidden item in BMREC-01..03, each MUST make the check fail (a mutation
test of the check itself); one clean fixture MUST pass. (b) The check runs inside the only supported build command —
there is no build path that produces a jar without it. (c) The check's pass output, the jar's SHA-256 and the source git
SHA are written together (BMREC-30). A jar whose hash is not in such a record is not a loadable artefact.
*Closes:* 3.1 R. *Verify:* run the fixture suite — N fail, 1 pass; delete the check step and confirm the build fails.

**BMREC-05 (CRITICAL, A01/A04) · addon + recorder · BLOCKING-H1 — the pipe is one-way.**
The add-on MUST only write to the pipe and MUST NOT read a single byte from it; there is no Python→Java message of any
kind (no acks, no config, no commands). The recorder creates the pipe inbound-only. Flow control is the add-on's bounded
queue (BMREC-17), not a reply channel. Rationale: a readable pipe is a command channel into a JVM holding the trading
provider, reachable by whoever owns the server end — including a squatter (3.3 S).
*Closes:* 3.1 E, 3.3 S(b), 3.3 E. *Verify:* BMREC-01 check has no read method on the pipe stream in the allowlist;
recorder test asserts the pipe open mode is inbound-only.

**BMREC-06 (MEDIUM, A09) · addon · BLOCKING-H1 — admin callbacks become enumerated states only.**
`onConnectionLost/Restored`, `onLoginFailed/Successful` map to a fixed enum in the record stream. The text or object
content of `onSystemTextMessage`, `onUserMessage` and any login-failure reason MUST NOT be forwarded, logged or
`toString()`-ed into a record. A `onUserMessage` of an unexpected type is counted, not described.
*Closes:* 3.1 I. *Verify:* schema has no free-text field on connection records; unit test feeds a message with a
marker string and asserts it appears nowhere in the output.

**Full Level1 API switch.** If the add-on moves to the full Level1 API (`@Layer1Attachable`, plan H1 lines 93-95), the
module's API surface changes; BMREC-01..03 MUST be re-derived and this review re-run **before** that change merges.

### 5.2 Bookmap as a component, and secrets (ops)

**BMREC-07 (CRITICAL, A07/A01) · ops · BLOCKING-H1 — Bookmap stays key-less; any future key is read-only and triggers
re-review. Established without reading any credential store.**
- **Current state (satisfied, by attestation):** the owner stated on 2026-09-26 that no Binance API key/secret has
  been entered into Bookmap; the Binance Futures connection is data-only via the Bookmap Global subscription. Before
  the first recording, record this as a dated owner attestation in the repo (research ledger or the ADR 0009 draft),
  stating "no key" and the source (Bookmap connection settings UI). Never read `keys.db` or Credential Manager to
  "confirm" it.
- **If a key is ever added to Bookmap:** recording under H1 MUST stop (or not start) until this threat model is
  re-reviewed. The key MUST be read-only on Binance's API-management page for the mainnet account: futures/spot
  trading disabled, withdrawals disabled, IP-restricted to this machine if Binance offers it. Record only the key's
  *label* and permission set, never the key or secret. A key with any trading or withdrawal permission is never
  acceptable in Bookmap. Rationale: other add-ons in the same JVM (BMREC-08) and any future bug are not constrained by
  BMREC-01..03, and `getProvider()` hands out a trading provider (F1-F3).
- **Detection of change:** re-attest at each Bookmap reinstall/update and each time the Binance connection is edited.
  At session start the recorder logs the connection's login events as enumerated states (BMREC-06). The owner
  checks, at each re-attestation, that the connection shows no key fields filled in.
*Closes:* 3.2 S. *Verify:* the dated attestation line exists in the repo with outcome "no key"; no secret material in it
(`git grep -nE "[A-Za-z0-9]{64}"` over the entry → none); the re-review trigger is written in ADR 0009 when it is
drafted (H2).

**BMREC-08 (HIGH, A08) · ops + recorder · BLOCKING-H1 — know what else runs in the JVM.**
At H1 start the owner records which add-ons are enabled in Bookmap; only Bookmap-bundled modules and the recorder add-on
are enabled during recording. The recorder writes, into each session header, the file names and SHA-256 of jars present
in Bookmap's user add-on directories (paths determined at H1 start, not assumed); a change between sessions is logged
as a security event. Reading jar files is not reading a credential store; the recorder MUST NOT read any other file
under `C:\Bookmap\Config`.
*Closes:* 3.2 T. *Verify:* session header shows the inventory; adding a dummy jar produces the event.

**BMREC-09 (HIGH, A05) · ops · BLOCKING-H1 — nothing elevated.**
Bookmap and the recorder run as the owner's standard user, not "Run as administrator", and the recorder is not a
service under LocalSystem. If it is scheduled, it uses the existing `schtasks` pattern (F14) without a highest-run-level
option.
*Closes:* 3.2 E, 3.4 E. *Verify:* the recorder logs its token elevation state at start and refuses to run elevated;
Task Scheduler entry shows "Run with highest privileges" unchecked.

**BMREC-10 (MEDIUM, A06/A08) · recorder · BLOCKING-H1 — Bookmap version is identity.**
Bookmap version is in every file header (plan already requires it); a version change between sessions is logged as an
event and starts a new dataset segment in the manifest. Re-run the H1 "to verify" facts (plan §0) after a Bookmap update
before its recordings are used in H5.
*Closes:* 3.2 R. *Verify:* manifest shows segment boundary on a version change.

**BMREC-34 (MEDIUM, A01/A05) · ops · BLOCKING-H1 — add-on directories are not writable by other accounts.**
Run `icacls` on `C:\Bookmap` and on the directory Bookmap loads the add-on from; no write/modify ACE for
`Authenticated Users`, `Users`, or `Everyone`. If present and other accounts exist on the PC, remove them (inheritance
break on `C:\Bookmap`) — owner decision. If this is a single-account PC, record that and accept.
*Closes:* 3.2 T. *Verify:* saved `icacls` output in the H1 evidence.

### 5.3 The named pipe (recorder)

**BMREC-11 (CRITICAL, A01/A05) · recorder · BLOCKING-H1 — explicit pipe security, never the stdlib defaults.**
The recorder creates the pipe with: an **explicit security descriptor** whose DACL grants access only to the owner's
user SID (SYSTEM/Administrators optional, nothing else — no Everyone, no Anonymous, no NETWORK, no Authenticated Users);
`PIPE_REJECT_REMOTE_CLIENTS`; `FILE_FLAG_FIRST_PIPE_INSTANCE`; **max instances = 1**; inbound access (BMREC-05).
`multiprocessing.connection.Listener`/`Client` MUST NOT be used for this pipe: it passes a NULL descriptor (Everyone +
anonymous read, F11), unlimited instances and accepts remote clients (F9).
*Closes:* 3.3 S/I/D. *Verify:* a test reads back the created pipe's DACL (e.g. via `GetSecurityInfo`) and asserts the
exact ACE set; a second `CreateNamedPipe` on the same name fails; `grep -n "multiprocessing.connection" <recorder>` → none.

**BMREC-12 (CRITICAL, A01) · recorder · BLOCKING-H1 — a squatted name is a stop, not a detour.**
If pipe creation fails because the name exists (`ERROR_ACCESS_DENIED` under `FILE_FLAG_FIRST_PIPE_INSTANCE`, F11) or
for any other reason, the recorder exits non-zero, logs a security event and alerts. It MUST NOT choose another name,
retry under a suffix, or connect to the existing pipe as a client.
*Closes:* 3.3 S(a). *Verify:* pre-create the name from a test process, start the recorder → non-zero exit + event.

**BMREC-13 (CRITICAL, A07/A01) · recorder · BLOCKING-H1 — authenticate every client before recording anything.**
On each connection, before any market record is written: (1) obtain the client PID from the pipe
(`GetNamedPipeClientProcessId`), resolve its executable path, and require an exact match with the Bookmap JVM
executable path pinned in recorder config (determined empirically at H1 start; it MUST lie under the Bookmap install
directory in `C:\Program Files`, which standard users cannot write) and the same logon session; (2) require a hello
frame as the first frame: protocol/schema version, add-on git SHA, add-on jar SHA-256; the jar SHA MUST equal the pin
(BMREC-30). Any failure: disconnect, write zero market records, log the reason code and the executable's base name,
re-listen. A per-session shared secret delivered through an ACL'd file (plan H2 line 151-152 alternative) adds nothing
over (1)+(2) against a same-user attacker and is not required.
*Closes:* 3.3 S/R/D. *Verify:* a Python test client connecting to the pipe is rejected with zero records written; a
hello with a wrong jar SHA is rejected.

**BMREC-14 (HIGH, A08) · recorder · BLOCKING-H1 — sessions are segments, and a reconnect is not continuity.**
Each accepted connection is a session id in the file and manifest. A new session starts with the book INVALID until a
snapshot completes (plan §1.5), and the gap between sessions is recorded as a gap even if timestamps look contiguous.
No record is ever attributed to a session other than the connection it arrived on.
*Closes:* 3.3 S (fake feed between real sessions). *Verify:* disconnect/reconnect test → manifest shows two sessions and
one gap.

**BMREC-15 (CRITICAL, A03/A08) · recorder · BLOCKING-H1 — frames are validated, never deserialized as objects.**
- Wire format is length-prefixed; the length is checked against a fixed maximum frame size **before** allocation; a
  larger length closes the connection.
- Record type is a closed enum; schema version must equal the recorder's exactly.
- Every field is type- and range-checked: integers within their declared width; depth size ≥ 0; trade size > 0;
  booleans strict; mode ∈ {HISTORICAL, BACKFILL, REPLAY, LIVE}; every floating value finite (reject NaN, ±Inf).
- The add-on's counter must be exactly previous + 1, otherwise a gap record is written.
- No pickle, `marshal`, `eval`, `yaml.load`, or class-instantiating JSON hooks. `Connection.recv()` is forbidden (F10).
  If JSON is used, the frame cap bounds its size, and nesting depth is bounded.
- A frame that fails validation is **not** written as a market record. The recorder writes a validation-failure
  record: reason code only, never the raw bytes. The stream is marked INVALID from that point until the next valid
  snapshot. After a fixed number of consecutive failures the connection is closed.
*Closes:* 3.3 T/E. *Verify:* fuzz/table test: oversize length, NaN price, Inf size, unknown type, wrong schema, counter
jump, truncated frame — each produces the expected failure record and no market record.

**BMREC-16 (HIGH, DoS) · recorder · BLOCKING-H1 — bounded resources.**
Fixed-size read buffers; no unbounded in-memory accumulation; a documented free-space floor on the recording volume
below which the recorder stops writing, records a gap, and alerts (it never deletes old data to make room).
*Closes:* 3.4 D. *Verify:* test with a tiny quota / mocked free-space → gap + alert, no deletion.

**BMREC-17 (MEDIUM, DoS) · addon · BLOCKING-H1 — Bookmap never waits on the recorder.**
Callbacks enqueue with a non-blocking offer into a bounded queue; overflow increments a counter that is emitted as a gap
record (plan H1 lines 103-106); the forwarder is a daemon thread; `stop()` unregisters the admin listener and ends the
forwarder within a bounded time; pipe failures reconnect with capped exponential backoff (no busy loop).
*Closes:* 3.1 D. *Verify:* recorder paused 60 s → Bookmap UI responsive, gap recorded; `stop()` returns within the
bound in a unit test.

### 5.4 Recording storage and integrity (recorder, research, ops)

**BMREC-18 (CRITICAL, A04/A08) · recorder + ops · BLOCKING-H1 — recordings live outside the git worktree.**
The recording root is configured (env var or config) and MUST resolve **outside** any git worktree; the recorder refuses
to start if `git -C <root> rev-parse --show-toplevel` succeeds. Rationale: this repo re-tracks formerly ignored data by
policy (F12), so "git-ignored" is not a durable guarantee, and `git clean -x` deletes ignored files — one command from
losing irreplaceable data. Belt and braces: if any recorder artefact (manifest drafts, temp files) is ever written inside
the repo, its pattern is in `.gitignore` with a test using `git check-ignore -q`.
**This changes plan H1 line 116 — see §6 item 1.**
*Closes:* 3.5 T/I. *Verify:* start the recorder with a root inside the repo → refuses; `test_recording_root_outside_worktree`.

**BMREC-19 (HIGH, A01) · ops + recorder · BLOCKING-H1 — recording root ACL, and closed files stay closed.**
The root grants the owner full control and SYSTEM/Administrators by inheritance; no write for `Users`,
`Authenticated Users`, `Everyone`. The recorder opens only the current hour's file for append/create-new; a closed file
is never reopened for write and gets the read-only attribute on close.
*Closes:* 3.5 E/T. *Verify:* `icacls <root>` saved in evidence; test that the writer never opens an existing closed file
in a write mode.

**BMREC-20 (HIGH, A08) · recorder · BLOCKING-H1 — per-record length + CRC, and no silent repair.**
Every record carries length and a CRC (plan H1 line 113). The CRC is documented as **accident detection only, not
tamper evidence**. Readers stop at the first bad record, report the offset and the truncated tail length, and never
"fix", skip-and-continue silently, or rewrite a file.
*Closes:* 3.4 T, 3.5 T. *Verify:* flip one byte mid-file → reader reports offset; file bytes unchanged.

**BMREC-21 (CRITICAL, A08) · recorder + research · BLOCKING-H1 — manifest hashes are committed before anyone looks.**
On closing each file the recorder writes its SHA-256 into the run manifest; the manifest records gaps, sessions, modes,
Bookmap version, exchange tick and time range (plan H1 line 114). The manifest's own SHA-256 (at least daily, and at
every week boundary of the pre-registered calendar, plan H1 lines 122-126) is committed to the tracked research ledger
**before** any human or feature-design look at that week's content. A file whose hash does not match its committed
manifest entry is INVALID for research (§38). This, not the CRC, is the tamper-evidence of the §10 snapshot.
*Closes:* 3.5 T/R. *Verify:* `test_manifest_hash_matches_files`; a hand-edited file fails verification; ledger commit
timestamps precede any exposure-log entry for the same week.

**BMREC-22 (HIGH, A09) · recorder · BLOCKING-H1 — nothing identifying in headers, manifests or ledger lines.**
No absolute paths (they contain the Windows user name), no host name, no Windows user name, no Bookmap account
email/licence/machine id, no API-key label. Only relative file names, versions, SHAs, `InstrumentInfo`, exchange
filters, time ranges and quality facts.
*Closes:* 3.4 I. *Verify:* `test_manifest_has_no_absolute_paths`; grep a manifest for `:\\` and `Users` → none.

**BMREC-23 (HIGH, A08/availability) · ops · BLOCKING-H1 (before the 24 h exit) — verified off-disk backup.**
At least daily, closed files and manifests are copied to a second physical device or private storage (owner's choice,
Q2); each copy is verified by recomputing SHA-256 against the manifest; a verification failure alerts. The target is not
publicly shared or linked. Encryption at rest is not required (public market data, no PII); a private destination is.
*Closes:* 3.5 D/I. *Verify:* backup log with per-file hash-match results for one day.

**BMREC-24 (HIGH, A08) · research + ops · BLOCKING-H1 — no automatic deletion; every deletion is a research event.**
No retention job deletes recordings in H1. Deletion is an explicit owner action at whole-file granularity, recorded in
the research ledger with date, files, hashes and reason, because dropping selected weeks is a selection-bias event
(CLAUDE.md §9, §43). A storage estimate (plan H1 line 117) and a free-space alert (BMREC-16) replace deletion as the
capacity control.
*Closes:* 3.5 T. *Verify:* `grep -nE "unlink|remove|rmtree|os\.replace" <recorder>` shows no call that targets the
recording root; the ledger template has the deletion-entry shape.

**BMREC-25 (MEDIUM, A09) · recorder · BLOCKING-H1 — the recorder's own event log.**
Append-only, inside the recording root, listed in the manifest: start/stop, pipe created, client accepted/rejected
(reason code, executable base name, PID), hello contents (versions and SHAs), validation-failure counts, gaps and their
cause, disk stops, each REST reference fetch (endpoint, request/response time, HTTP status), 429/418 events.
*Closes:* 3.3 R, 3.4 R, 3.6 R. *Verify:* 24 h run log contains each event type exercised in tests.

### 5.5 Outbound network (recorder)

**BMREC-26 (CRITICAL, A02/A10) · recorder · BLOCKING-H1 — one chokepoint, host + path allowlist, unsigned, verified TLS.**
Every outbound request goes through one function that allows only HTTPS `GET` to the venue host matching the book
Bookmap records — expected `fapi.binance.com` for USDⓈ-M futures (to verify, Q3) — and only the paths
`/fapi/v1/depth`, `/fapi/v1/aggTrades`, `/fapi/v1/exchangeInfo`, `/fapi/v1/time` (the latter two already used by the
repo, F13). No API-key header, no signature, no query parameters beyond the endpoint's public ones. TLS certificate and
host-name verification stay on (default context; no "unverified" context anywhere); redirects are not followed to any
other host; explicit connect/read timeouts. The **testnet** host is not on the list, because testnet is a different
book (plan §1.6).
*Closes:* 3.6 S/I, A10. *Verify:* unit test — any other host/path/method raises before a socket opens;
`grep -nE "_create_unverified_context|CERT_NONE|check_hostname *= *False|X-MBX-APIKEY|signature" <recorder>` → none;
during the 24 h run, the recorder process's remote endpoints resolve only to the allowlisted host.

**BMREC-27 (CRITICAL, A02) · recorder · BLOCKING-H1 — the recorder never touches secrets or the order path.**
The recorder MUST NOT import `scripts/trading_env.py` or `scripts/get_secret.py`, read `config/env.*`, query Windows
Credential Manager, read anything under `C:\Bookmap\Config`, or invoke `scripts/binance-futures-testnet-order.sh`
(which can target mainnet, F13). PILOT-28/29 apply by principle.
*Closes:* 3.4 S, 3.6 I. *Verify:* import-graph test over the recorder package; grep for the four names → none.

**BMREC-28 (HIGH, DoS/A08) · recorder · BLOCKING-H1 — a rate budget that protects the shared IP, and reference data is
validated.**
The cross-check and reconciliation schedule MUST fit a documented request-weight budget that is a stated fraction of
the limits Binance publishes (read from `exchangeInfo`'s rate-limit section at start, not hard-coded from memory),
leaving headroom for every other Binance caller on this machine. On HTTP 429 the recorder backs off; on HTTP 418 it
stops all outbound calls and alerts. REST responses are schema-validated (types, finite numbers, non-empty book sides)
before use; a failed or invalid fetch makes that cross-check **UNKNOWN**, never "match" (CLAUDE.md §20).
*Closes:* 3.6 D/T. *Verify:* simulated 429 → backoff; 418 → no further calls; malformed body → UNKNOWN record.

*BMREC-29: reserved, not issued (its egress-corroboration content is in BMREC-26's verification step).*

### 5.6 Supply chain (addon, recorder)

**BMREC-30 (CRITICAL, A08) · addon + recorder · BLOCKING-H1 — jar pin verified by the recorder, not by the jar.**
A committed pin file holds: jar SHA-256, source git SHA, JDK version, and the BMREC-01 check result. The **recorder**
recomputes the SHA-256 of the jar at Bookmap's actual load location (determined at H1 start) at startup and at every
client connection, and compares it with the pin and with the hello frame's claim (BMREC-13). Mismatch: reject the
client, log, alert. A jar's self-check is optional telemetry, never the control. The pin changes only in a commit that
also carries the check output.
*Closes:* 3.1 R, 3.7 S/R. **Refines plan H1 line 98 ("checked at load") — §6 item 5.** *Verify:* replace the loaded jar
with a rebuilt-but-different jar → client rejected.

**BMREC-31 (HIGH, A06/A08) · addon · BLOCKING-H1 — controlled, dependency-free build.**
Build with the pinned JDK 21; compile classpath is only the Bookmap API jars from `C:\Program Files\Bookmap\lib`, used
compile-only (not bundled). No third-party Java dependency in H1. The jar contains only project classes and a manifest
(`jar tf` listing checked in the build). If a build tool is introduced, its wrapper/distribution checksum is verified.
*Closes:* 3.7 T/R. *Verify:* `jar tf` listing has only the project package; the build log shows the JDK version.

**BMREC-32 (HIGH, A06) · recorder · BLOCKING-H1 — Python dependencies.**
Stdlib only by default (PILOT-33). BMREC-11 needs the Win32 security APIs: implement via `ctypes` (stdlib) or take one
reviewed third-party package; if a package is taken, it is pinned to an exact version **with hash** in a committed lock
file installed with hash-checking, and scanned for known vulnerabilities (pip-audit or equivalent) before H1 exit. The
choice is TechLead's (Q4).
*Closes:* 3.7 T. *Verify:* lock file with hashes exists, or `grep` shows stdlib-only imports.

**BMREC-33 (MEDIUM, A06) · devops · DEFERRED-H2 — CI scanning.**
Recommended, not mandated: secret scanning (gitleaks or trufflehog) pre-commit; SAST over the recorder (Semgrep or
CodeQL); dependency scan (pip-audit / Grype / Trivy) if BMREC-32 admits a package. Run BMREC-01 check in CI when CI
exists.

### 5.7 Logging (addon, recorder)

**BMREC-35 (HIGH, A09) · addon + recorder · BLOCKING-H1 — logs carry no secrets and no account text.**
Add-on log lines (in Bookmap's log) contain only lifecycle facts (loaded, connected, queue depth, overflow counts,
versions/SHAs). Recorder logs follow BMREC-22 and pass the same scrubbing principle as PILOT-29 for any string that
originated in Bookmap. Recorder logs live with the recordings, not in the repo.
*Closes:* 3.2 I, 3.4 I. *Verify:* grep a 24 h run's logs for `@`, `apiKey`, `secret`, `Users\\` → none.

### 5.8 Deferred rules (recorded now so H2/H4 inherit them)

**BMREC-36 (HIGH, A03/A08) · recorder/backend · DEFERRED-H2 — one parser.** `bookmap_bridge` reads recordings and the
live stream only through the BMREC-15 validator; no second parser, no "fast path" that skips validation.

**BMREC-37 (CRITICAL, A01/A08) · backend · DEFERRED-H4 — security state gates live use.** A live session is usable as
REQUIRED_FOR_DECISION input only if BMREC-13 and BMREC-30 passed for that session, BMREC-07's outcome is "no key" or
"read-only" and still current (re-attested after the last Bookmap connection change), and connection state is known (not UNKNOWN, plan H1 line 95). Any security event in the session marks it
INVALID → entry blocked (CLAUDE.md §20, §36).

**BMREC-38 (CRITICAL, A01) · addon/backend · DEFERRED-H4 — execution never goes through Bookmap.** H4 orders go through
the project's own connector (PILOT rules), never through Bookmap's provider; BMREC-01..03 stay in force unchanged when H4
exists. Any proposal to trade via Bookmap is a new threat model.

**BMREC-39 (HIGH, A01) · backend · DEFERRED-H4 — fan-out inside Python.** The H4 consumer receives the stream from the
recorder process, not from a second pipe instance or a localhost port; any new IPC endpoint needs its own review.

---

## 6. What the plan must change

The main session decides; implementers should not follow the plan over this list silently.

1. **H1 line 116, "a git-ignored directory outside tracked `data/`"** → a directory **outside the git worktree**
   (BMREC-18). Reason: repo policy re-tracks ignored data (F12) and `git clean -x` deletes it.
2. **H1 lines 89-92, the build-time check.** "No `sendOrder`/`updateOrder` + one `getProvider` site" is a denylist on the
   `Api` surface; `getProvider()` returns a `Layer1ApiProvider` that *is* a trading provider and also exposes `login`,
   `sendUserMessage` (F1-F4). Replace with an allowlist bytecode check on the final jar, with a ban on reflection
   and dynamic loading, and must-fail fixtures (BMREC-01..04).
3. **§1.8 "to be confirmed in the Security review" (Python as pipe server): confirmed, with conditions.** Do not use
   `multiprocessing.connection`: it creates the pipe with a NULL security descriptor, unlimited instances, accepts
   remote clients, and unpickles on `recv()` (F9, F10). Use an explicit DACL + first-instance + reject-remote + one
   instance (BMREC-11), and authenticate the client (BMREC-13).
4. **The plan does not say the pipe is one-way. It must be** (BMREC-05).
5. **H1 line 98, "hash pinned and checked at load"**: specify *who* checks. The recorder verifies the on-disk jar, not
   the jar itself (BMREC-30).
6. **H2 lines 151-152, "or a per-session HMAC key in an ACL'd file"**: against a same-user attacker it adds nothing
   over an owner-only DACL plus client-image check. Drop it or keep it optional (BMREC-13).
7. **H1 line 97, "Bookmap's own exchange connection uses no API keys, or read-only keys"**: met today (owner: no key,
   data-only). The plan must add the persistence rule: adding any key to Bookmap stops H1 until re-review, and any such
   key must be read-only (BMREC-07).
8. **Not in the plan: retention is a research-integrity matter.** Deletion of recorded weeks must be ledgered
   (BMREC-24). Manifest hashes must be committed before exposure (BMREC-21).
9. **Not in the plan: rate budget for the REST cross-check** on a shared IP (BMREC-28).

## 7. Residual risks (accepted, stated)

- **A process already running as the owner defeats every local control here.** It can inject into Bookmap's JVM,
  swap the jar between checks, or write into the recording root. BMREC-21 (hashes committed to git before exposure) is
  the control that still holds afterwards: tampering *after* commit is detectable.
- **In-JVM exposure depends on BMREC-07.** Our add-on cannot place orders (BMREC-01..03), but other code in the same
  JVM could. Today Bookmap holds no key (owner statement), so that exposure is bounded to market data. The risk that
  remains is drift: a key added later for convenience. BMREC-07's re-review trigger is the control for that.
- **CRC ≠ integrity.** Between file close and manifest commit there is a window where edits are undetectable. The window
  is at most one manifest-commit interval (BMREC-21).

## 8. Open questions for the owner

1. **Q1 — answered 2026-09-26:** no key; data-only. Remaining action: write the dated attestation line into the repo
   (BMREC-07) before the first recording.
2. **Q2 — Backup target** for irreplaceable recordings (second disk, NAS, private cloud)? (BMREC-23)
3. **Q3 — Which Binance futures product** does Bookmap's `BinanceFuturesProvider` connection stream (USDⓈ-M `fapi`
   vs COIN-M)? This decides the outbound allowlist host (BMREC-26).
4. **Q4 (TechLead)** — Win32 pipe security via `ctypes` or a reviewed third-party package? (BMREC-11, BMREC-32)
5. **Q5 — Other Windows accounts** on this PC? This decides whether BMREC-34/19 ACL findings are live or academic.
6. **Q6 — Licence terms:** do Bookmap/Binance terms restrict storing or sharing recorded depth data? I do not know. The
   rules keep recordings private and out of the pushed repo either way.
7. **Q7 — Recording root path** (outside the worktree, on a non-system volume, with room for the storage estimate).

---

Quality gate: STRIDE covered for all seven components (§3.1-3.7), with explicit "—" rows where a category does not
apply; OWASP Top 10 mapped with not-applicable entries (§4); every rule cites its finding, names a domain, carries a
severity, a gate and a verification step; prior rules are cited (PILOT-28/29/33), not restated; no implementation code;
no secrets, keys or PII in this document; credential stores were not read.

Last updated: 2026-09-26.

## 9. Owner answers (2026-09-26, recorded verbatim in substance)

| Question | Answer | Consequence |
|---|---|---|
| Q1 — Binance keys in Bookmap? | "Tao chưa kết nối key vào Bookmap" — no key entered; the Binance Futures connection is data-only via the Bookmap Global subscription. | BMREC-07 satisfied as of this date. Adding any key later stops H1 until re-review; only read-only keys are acceptable. |
| Q2 — backup target | Drive D: (separate physical HDD in the same PC). | BMREC-23 satisfied for H1 with an on-machine, different-disk backup. Residual risk: not off-site; an off-site copy (cloud/external) remains recommended. |
| Q3 — USDⓈ-M or COIN-M | Determined from Bookmap logs, not asked: instruments `BTCUSDT@BNF`/`ETHUSDT@BNF`, host `fapi.binance.com` → USDⓈ-M. | BMREC-26 allowed host = `fapi.binance.com`. |
| Q5 — other Windows accounts | Determined via `net user`: only the owner's interactive account (`nguye`) plus built-in system accounts. | BMREC-19/34 still apply (defence in depth) but no second human account exists today. |
| Q6 — licence permits storing recorded depth for personal research | Owner confirms it is permitted. | Recording may proceed. |
| Q7 — recording folder | `C:\TradingData\bookmap-recordings` (SSD, outside every git worktree). | BMREC-18 location fixed; backup mirrors to a folder on D: outside the repo. |
