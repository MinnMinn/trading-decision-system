"""Shared temp-directory redirect for the two write paths a test run must never touch: scripts/latency.py's
`data/live/latency/<date>.jsonl` and scripts/strategy-runner.py's single-account `data/live/pilot-futures/`
(pilot-selection-state.json, pilot-selection-log.jsonl, pilot-selection-mt5-log.jsonl, STOP).

Extracted 2026-09-27 when the same redirect turned out to be needed by five test files (test_account_profile,
test_decision_order, test_latency, test_strategy_runner, test_trading_system) -- each reaches one or both of
these writers by loading scripts/strategy-runner.py (which does `import latency as LAT`) and calling `tick()`,
directly or through a monkeypatched dry run, and none of them are supposed to leave the repo's own live data
touched. Only test_strategy_runner.py's `PerAccountScope` had a save/restore idiom before this, and only for
the ACCOUNT-BOUND half (`bind_account(<id>)`); nothing covered the single-account defaults a bare `sr.tick()`
call or a `--dry-run` subprocess actually uses.

Two different mechanisms, because the two writers pick up a redirect differently:

* `latency.DIR` is a genuine `sys.modules` singleton: however many times scripts/strategy-runner.py itself
  gets reloaded via `importlib.util.spec_from_file_location` across these five files, its own
  `import latency as LAT` resolves to the SAME cached module object. Patching the attribute directly, once,
  therefore wins for every caller regardless of import order or how many times strategy-runner.py was
  reloaded.
* scripts/strategy-runner.py's PILOT_DIR/STATE/LOG/MT5_LOG/STOP are NOT a singleton -- each fresh load
  re-evaluates `PILOT_DIR = os.environ.get("TRADING_TEST_PILOT_DIR") or <the real path>` (and derives
  STATE/LOG/MT5_LOG/STOP from it) at module-exec time, so only an env var set BEFORE that load can reach it.
  Setting the var here, for the rest of the process, covers every subsequent load a test file makes -- and,
  being an environment variable rather than an in-process attribute, is inherited by a subprocess this
  process spawns too, which is the only way to redirect a `strategy-runner.py --dry-run` child process's
  writes without threading a CLI flag through it.

Both env vars are named for the one thing they must still equal after the redirect: the pilot directory value
ends in literal `pilot-futures` and the latency directory in literal `latency`, because
`test_strategy_runner.PerAccountScope.test_binding_none_restores_the_houses_paths_exactly` asserts
`sr.PILOT_DIR.endswith("pilot-futures")`, and `bind_account(None)` re-reads this SAME env var -- so the
redirected value has to satisfy that assertion exactly like the real path does.

This does NOT touch the per-account branch of `bind_account()` (`data/live/accounts/<id>/`): no test in this
tree calls `bind_account(<a real id>)` and then a real, unmocked `log()`/`save_state()` -- `PerAccountScope`
only asserts path SHAPE, and every other class that reaches `sr.tick()` monkeypatches `sr.log` first -- so
there is nothing observed to redirect there.
"""
import os
import shutil
import tempfile

import latency

LATENCY_ENV = "TRADING_TEST_LATENCY_DIR"
PILOT_ENV = "TRADING_TEST_PILOT_DIR"


def redirect():
    """Point both writers at a fresh temp directory for the rest of this process.

    Call once per test file, from `setUpModule` (the redirect is process-global state -- os.environ and a
    module attribute -- so there is nothing to gain from doing it more than once per file, and every test
    class in these five files already shares one `sr`/`latency` regardless).

    Returns `restore` -- call it from `tearDownModule` to put `latency.DIR` back, drop the two env vars (or
    restore whatever they held before, if this process is itself nested inside another caller of `redirect`),
    and remove the temp directory.
    """
    root = tempfile.mkdtemp(prefix="trading-test-live-")
    lat_dir = os.path.join(root, "latency")
    pilot_dir = os.path.join(root, "pilot-futures")

    saved_env = {k: os.environ.get(k) for k in (LATENCY_ENV, PILOT_ENV)}
    saved_latency_dir = latency.DIR

    os.environ[LATENCY_ENV] = lat_dir
    os.environ[PILOT_ENV] = pilot_dir
    # Covers the case where `latency` (the sys.modules singleton) was already imported -- with the real
    # default -- by something else earlier in this process, before the env var above could apply.
    latency.DIR = lat_dir

    def restore():
        latency.DIR = saved_latency_dir
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(root, ignore_errors=True)

    return restore
