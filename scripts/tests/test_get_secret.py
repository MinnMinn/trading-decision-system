"""The one secret reader, and the rules it exists to keep.

scripts/get_secret.py replaced scripts/get-secret.sh on 2026-09-19 because the platform moves to Windows
(docs/plans/2026-09-20-windows-migration.md) and macOS's `security` command does not exist there. The
reference syntax CLAUDE.md declares -- keychain:<service>[@<account>] -- is deliberately unchanged, so no env
file, registry or caller moves; only what answers the question changes.
"""
import importlib.util
import os
import platform
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "get_secret.py")


def _mod():
    spec = importlib.util.spec_from_file_location("get_secret", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


GS = _mod()


class ItRefusesRatherThanReturningNothing(unittest.TestCase):
    """An empty API key does not fail -- it sends an UNAUTHENTICATED request, which looks like a venue
    problem rather than a configuration one. So absent must be loud."""

    def test_a_missing_secret_raises(self):
        with self.assertRaises(GS.SecretError):
            GS.get("trading-system-definitely-not-a-real-service", "nobody")

    def test_an_empty_value_is_treated_as_absent(self):
        saved = dict(GS.BACKENDS)
        try:
            GS.BACKENDS[platform.system()] = lambda s, a: ""
            with self.assertRaises(GS.SecretError) as cm:
                GS.get("svc", "acct")
            self.assertIn("EMPTY", str(cm.exception))
        finally:
            GS.BACKENDS.clear(); GS.BACKENDS.update(saved)

    def test_an_unwired_platform_refuses_instead_of_reading_disk(self):
        saved = dict(GS.BACKENDS)
        try:
            GS.BACKENDS.clear()
            with self.assertRaises(GS.SecretError) as cm:
                GS.get("svc")
            self.assertIn("refusing rather than reading a secret from disk", str(cm.exception))
        finally:
            GS.BACKENDS.clear(); GS.BACKENDS.update(saved)

    def test_the_cli_exits_non_zero_and_prints_nothing_on_stdout(self):
        r = subprocess.run([sys.executable, SCRIPT, "trading-system-not-real", "nobody"],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "", "a failed lookup must put nothing on stdout, not an empty-ish string")
        self.assertTrue(r.stderr.strip())


class TheSecretNeverLeavesStdout(unittest.TestCase):
    def test_no_backend_logs_or_prints_the_value(self):
        src = open(SCRIPT, encoding="utf-8").read()
        body = src.split('def main(', 1)[0]
        for bad in ("print(value", "print(out", "logging", "log("):
            self.assertNotIn(bad, body, f"{bad!r} appears above main(); the secret must only reach stdout")

    def test_the_error_message_names_the_service_not_the_value(self):
        try:
            GS.get("trading-system-not-real", "nobody")
        except GS.SecretError as exc:
            self.assertIn("trading-system-not-real", str(exc))


class EveryPlatformWeShipOnHasABackend(unittest.TestCase):
    def test_macos_windows_and_linux_are_wired(self):
        for system in ("Darwin", "Windows", "Linux"):
            self.assertIn(system, GS.BACKENDS, f"no credential store wired for {system}")

    def test_there_is_no_fallback_between_stores(self):
        """If this platform's store does not have it, that is the answer -- silently trying another store
        would make 'where is this secret' unanswerable."""
        src = open(SCRIPT, encoding="utf-8").read()
        self.assertIn("No fallback between stores", src)

    def test_this_platforms_backend_actually_runs(self):
        """Not that the secret exists -- that the backend executes and fails in the expected way."""
        with self.assertRaises(GS.SecretError):
            GS.BACKENDS[platform.system()]("trading-system-not-real", "nobody")


class TheCallersMovedWithIt(unittest.TestCase):
    def test_trading_env_points_at_the_python_reader(self):
        """A historical mention of the old name in a comment is fine and wanted; what must not survive is an
        INVOCATION of it."""
        src = open(os.path.join(ROOT, "scripts", "trading_env.py"), encoding="utf-8").read()
        self.assertIn('"get_secret.py"', src)
        self.assertNotIn('"get-secret.sh"', src, "trading_env still resolves a path to the shell reader")

    def test_trading_env_can_actually_resolve_a_reference(self):
        """Guards the import the rewrite nearly missed: `sys` was not imported, so every keychain: reference
        would have raised NameError inside _resolve and been swallowed into an empty secret."""
        spec = importlib.util.spec_from_file_location("trading_env_t",
                                                      os.path.join(ROOT, "scripts", "trading_env.py"))
        te = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(te)
        self.assertEqual(te._resolve("plain-value"), "plain-value")
        self.assertEqual(te._resolve("keychain:trading-system-not-real@nobody"), "",
                         "an unresolvable reference must come back empty, not explode")

    def test_trading_env_invokes_it_through_the_interpreter_not_a_shebang(self):
        """Windows does not honour `#!` lines."""
        src = open(os.path.join(ROOT, "scripts", "trading_env.py"), encoding="utf-8").read()
        self.assertIn("sys.executable, GET_SECRET", src)

    def test_the_bash_mirror_points_at_it_too(self):
        src = open(os.path.join(ROOT, "scripts", "trading-env.sh"), encoding="utf-8").read()
        self.assertIn("get_secret.py", src)
        for line in src.splitlines():
            if line.lstrip().startswith("#"):
                continue
            self.assertNotIn("get-secret.sh", line, f"the shell mirror still invokes it: {line.strip()}")


if __name__ == "__main__":
    unittest.main()
