# Bookmap H1 recorder (read-only) — operator guide

Stage H1 of `docs/plans/2026-09-26-heatmap-realtime-plan.md`: record Bookmap's Binance USDⓈ-M order book and trades
at full resolution, read-only, for later research. **Nothing here trades, decides, or touches an account.**

- Security rules: `docs/security/2026-09-26-bookmap-recorder-h1.md` (BMREC-01..39). Compliance map:
  [`BMREC-compliance.md`](BMREC-compliance.md).
- Wire format, file format and every numeric tolerance: `docs/contracts/bookmap-recorder-frames.md`.
- Pieces:
  - Java add-on (runs inside Bookmap): `src/tds/bookmap/recorder/`, built by `build.ps1` → `dist/tds-h1-recorder.jar`.
    It only captures and forwards over a one-way named pipe. No orders, no network, no files.
  - Python recorder (runs in a normal terminal): `scripts/bookmap_recorder.py`. It owns the pipe, checks who is
    connecting, writes the recordings outside the repo, and makes the only outbound calls (public Binance data).

Facts found on this PC on 2026-09-26 and used below: Bookmap 7.6.0 build 29 runs as
`C:\Program Files\Bookmap\Bookmap.exe` (the Java runtime is inside that process). Bookmap loads a manually added
add-on jar **from wherever you pick it** (your other add-ons load from `D:\Trading\Bookmap\add-ons`). The menu names
below come from Bookmap's own UI text (`Bookmap.jar`, `resources/locale/Bookmap.properties`).

## One-time setup

All commands are PowerShell in a **normal (not "Run as administrator")** window, from the repo root.

1. **Build the add-on and check it reproduces the committed pin.**
   ```powershell
   .\integrations\bookmap\build.ps1
   ```
   It must end with `pin reproduced` and `BUILD OK`. The build compiles against Bookmap's own API jars only, runs 62
   must-fail tests of the security check, then runs the check on the final jar. If it says the jar does not
   reproduce the pin, stop: do not load anything.

2. **Put the jar in its own folder** (this exact path is pinned in `recorder-config.json`):
   ```powershell
   New-Item -ItemType Directory -Force C:\TradingData\bookmap-addon | Out-Null
   Copy-Item .\integrations\bookmap\dist\tds-h1-recorder.jar C:\TradingData\bookmap-addon\
   ```
   The recorder refuses any client if this file's SHA-256 differs from `addon-pin.json` (BMREC-30).

3. **Pre-register the holdout calendar (before the first recording, once, ever).**
   ```powershell
   python scripts\bookmap_recorder.py --preregister-holdout
   git add docs\research\bookmap-holdout-calendar.json
   git commit -m "research: pre-register Bookmap holdout calendar (plan H1 N4)"
   ```
   The recorder will not record until this file is committed and unmodified. It assigns every future ISO week to
   in-sample or holdout by a fixed rule. From now on, if you (or anyone designing features) look at a week's market
   content, log it first: `python scripts\bookmap_recorder.py --log-exposure 2026-W41 --reason "what and why"`.

4. **Bookmap connection stays key-less (BMREC-07).** Your 2026-09-26 statement (no Binance key in Bookmap) is recorded
   in the security review §9. If you ever add a key to Bookmap, stop recording and ask for a re-review first.

5. **Only Bookmap's own modules and this add-on enabled while recording (BMREC-08).** On 2026-09-26 Bookmap's log
   showed third-party add-ons loading from `D:\Trading\Bookmap\add-ons` (`trading-to-win.jar`, `ttw-mvp.jar`,
   `volumeflow.jar`) and the plugin `multi-account-trading` in `C:\Bookmap\API\Layer1ApiModules`. Disable them
   (untick them in the add-on list) for recording sessions. The recorder writes the jar inventory of those folders
   into every session and raises a security event when it changes.

6. **Folder permissions (BMREC-19, BMREC-34).** The recorder creates `C:\TradingData\bookmap-recordings` itself with
   access for your user, SYSTEM and Administrators only, and refuses a pre-existing folder that lets other
   users write. Read-only checks found that `C:\Program Files\Bookmap` and `C:\Bookmap` grant `BUILTIN\Users` full
   control (saved in the H1 evidence). This PC has one human account, so the security review accepts it. If
   another account is ever added, remove that permission (administrator, your decision) before recording.

## Start a recording

1. **Start the recorder first**, in a normal PowerShell window, and leave it open:
   ```powershell
   python scripts\bookmap_recorder.py
   ```
   It prints nothing while healthy; problems print as `ALERT: ...`. Exit codes: 0 ok, 2 preflight refused (reason on
   screen or in `events.jsonl`), 3 pipe name already taken (another recorder, or something squatting the name —
   treat it as a security event), 4 tick-size gate failed, 5 running elevated.

2. **Load the add-on in Bookmap** (one time; afterwards it stays in the list):
   - Open **Settings → Configure add-ons** (or the *Configure Add-ons* button in the toolbar).
   - Click **Add...**; in *Select add-on file...* choose `C:\TradingData\bookmap-addon\tds-h1-recorder.jar`.
   - It appears as **TDS H1 Recorder (read-only)**. Enable it on **exactly one** chart, for example
     `BTCUSDT@BNF`. A second enabled chart stays idle on purpose: H1 records one instrument per recorder.
   - Bookmap never needs to grant this add-on trading permission. If Bookmap asks for trading permission for it,
     answer no and report it: that would mean something is wrong.
   - Leave *Auto load* / *Auto enable* at your choice. Whether the add-on re-enables itself after a Bookmap restart is
     one of the facts H1 must record (plan §0), so note what happens.

3. **Check that it is recording** (replace `<run>` with the newest folder in `C:\TradingData\bookmap-recordings`):
   ```powershell
   Get-ChildItem C:\TradingData\bookmap-recordings | Sort-Object Name | Select-Object -Last 1
   Get-Content C:\TradingData\bookmap-recordings\<run>\events.jsonl -Tail 20 -Wait
   ```
   Within a few seconds you should see `client_connected`, `hello_accepted`, `file_opened`, then
   `book_state ... VALID`. Within a minute: `tick_gate` with `MATCH` (Bookmap's price step equals Binance's tick
   size; a `MISMATCH` stops the recorder by design), then `recon_depth` and later `recon_aggtrades` results. A
   `.bmrec` file in the run folder keeps growing. `client_rejected`/`security_event` lines mean the connection was
   refused; the reason code says why (for example `JAR_HASH_MISMATCH` means the jar in `C:\TradingData\bookmap-addon`
   is not the pinned build).

## Stop a recording

1. In Bookmap, untick **TDS H1 Recorder (read-only)** (or close Bookmap). The add-on stops within 2 seconds.
2. Stop the recorder: press **Ctrl+C** in its window, or from any window
   `python scripts\bookmap_recorder.py --stop`.
3. Verify the run's files against its manifest:
   ```powershell
   python scripts\bookmap_recorder.py --verify-run <run>
   ```
   It must end with `VERIFY: OK`. Closed files are read-only; never edit or rename them.

## Every day while recording

```powershell
python scripts\bookmap_recorder.py --backup            # copies closed files to D:\TradingData-backup\..., checks SHA-256
python scripts\bookmap_recorder.py --ledger-manifests  # appends manifest hashes to docs\research\bookmap-manifest-ledger.jsonl
git add docs\research\bookmap-manifest-ledger.jsonl; git commit -m "research: ledger Bookmap manifests"
```
Commit the manifest hashes **before** anyone looks at that day's data (BMREC-21). The backup never overwrites; a
`*_HASH_MISMATCH` line or an `ALERT` means stop and investigate. To schedule the backup, use Task Scheduler with
*Run with highest privileges* **unticked** (BMREC-09).

Deleting recorded data is a research event, never automatic (BMREC-24): first
`python scripts\bookmap_recorder.py --record-deletion <run>\<file> --reason "..."`, commit the ledger, then delete by
hand.

## What to write down during the 24-hour H1 exit run (plan §0 "to verify")

- Whether `pips` equals Binance's tick (the `tick_gate` event says) and whether `isFullDepth` is set (session header).
- What `onSnapshotEnd` means in practice (count `SNAPSHOT_END` records; the recorder logs every one).
- Whether a connection drop in Bookmap shows `connection_state LOST` / `RESTORED` in `events.jsonl` (pull the network
  cable for a few seconds once). The e2e test proves the add-on reaches the connection listener through the
  Simplified API; this run proves Bookmap actually calls it.
- Whether the add-on re-enables after a Bookmap restart.
- Bookmap CPU/RAM with and without the add-on (Task Manager, 10 minutes each).
- That the recorder talks only to `fapi.binance.com`:
  `Get-NetTCPConnection -OwningProcess (Get-Process python | Select-Object -First 1).Id`.

## For developers

- Build: `integrations/bookmap/build.py [--update-pin]` is the only build path. `--update-pin` is for an intentional
  source change; commit the new `addon-pin.json` together with the source.
- Tests: `cd scripts/tests; python -m unittest test_h1_bookmap_recorder -v`.
- End-to-end (uses the real pipe name, so no real recorder may be running):
  `python integrations/bookmap/test/run_e2e.py`. It drives the real jar through a fake Bookmap host
  (`test/E2EHarness.java`), including a queue-overflow scenario.
- Moving the add-on to the full Level1 API, adding a listener, or touching `allowlist.json` needs a security re-review
  (BMREC-01 "Full Level1 API switch").
