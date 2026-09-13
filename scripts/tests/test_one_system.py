"""One system: one engine, one style vocabulary, one risk decision.

User decision 2026-09-13: keep strategy-runner.py on three horizons (scalping 15m / day 1H / swing 4H) at
planned R:R >= 3 and 3 % risk; delete demo-pilot.py, the execution.pilot_profile switch, the ten-value STYLE
map and the gold-* names. These tests exist because every one of those was a SECOND way to express something
the system already expressed once, and the duplicates drifted: the floor drifted (2R vs 3R), the risk ceiling
drifted (1 % vs 3 %), and `scalping` meant 1m in one vocabulary and 15m in the other.

The method-preset switch is deliberately NOT covered here -- all six presets and the control panel stay.
"""
import json, os, re, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(ROOT, "scripts")
CONFIG = os.path.join(ROOT, "docs", "architecture", "automation-config.json")


def sources():
    """Every tracked python/bash source, minus this test file."""
    out = {}
    for d in (SCRIPTS, os.path.join(SCRIPTS, "tests")):
        for fn in sorted(os.listdir(d)):
            if fn.endswith((".py", ".sh")) and fn != "test_one_system.py":
                out[os.path.relpath(os.path.join(d, fn), ROOT)] = open(os.path.join(d, fn), encoding="utf-8").read()
    return out


def code_lines(rel):
    """Lines of `rel` with comments AND docstrings removed, 1-indexed as (lineno, text).

    Why docstrings too: a test that bans a token everywhere also bans the sentence EXPLAINING why the token was
    removed. That bit three times on 2026-09-13 -- including forcing an implementer to edit unrelated docstrings
    in htf_context.py just to satisfy a scan. Prose may discuss a deleted thing; code may not resolve it.
    """
    src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
    skip = set()
    if rel.endswith(".py"):
        import ast
        tree = ast.parse(src)
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if not isinstance(body, list) or not body:
                continue
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
               and isinstance(first.value.value, str):
                skip.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    out = []
    for i, line in enumerate(src.splitlines(), 1):
        if i in skip or line.lstrip().startswith(("#", "<!--")):
            continue
        out.append((i, line))
    return out


class LegacyEngineIsGone(unittest.TestCase):
    def test_the_file_does_not_exist(self):
        self.assertFalse(os.path.exists(os.path.join(SCRIPTS, "demo-pilot.py")))

    def test_nothing_executes_it(self):
        """A dangling reference in the loop script is a crash at 3am, not a lint warning."""
        for path, src in sources().items():
            for i, line in enumerate(src.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                self.assertNotIn("demo-pilot.py", line, f"{path}:{i} still references the deleted engine")
                self.assertNotIn("demo_pilot", line, f"{path}:{i} still references the deleted engine")

    def test_the_profile_switch_is_gone(self):
        """Two profiles meant two rule sets on one account; there is one engine now, so a profile key can only
        select 'the engine' or 'nothing at all' -- and the second option is a footgun, not a feature."""
        for path, src in sources().items():
            for i, line in enumerate(src.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                self.assertNotIn("pilot_profile", line, f"{path}:{i} still reads the deleted profile key")

    def test_the_profile_subcommand_is_not_still_accepted(self):
        """Deleting the handler but leaving the argparse choice is worse than leaving both: `automation.py pilot
        profile top5` then exits 0 and prints the status block, so a user who types it believes they changed
        something. A removed command must REFUSE, not fall through."""
        src = open(os.path.join(SCRIPTS, "automation.py"), encoding="utf-8").read()
        for line in src.splitlines():
            if "choices=" in line and '"profile"' in line:
                self.fail(f"`profile` is still an accepted pilot action: {line.strip()}")

    def test_no_template_or_doc_claims_the_legacy_engine_still_runs(self):
        """config/env.example is copied by hand into config/env.<env>. A comment there asserting that a second
        order path clamps risk differently is a false statement about a file that no longer exists."""
        for rel in ("config/env.example",):
            src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
            self.assertNotIn("demo-pilot", src, f"{rel} still describes the deleted engine")

    def test_no_code_path_resolves_a_market_the_registries_do_not_know(self):
        """Spec review 2026-09-13 (CRITICAL x2). Narrowing PILOT_MARKETS to ["futures"] and dropping
        PILOT_LABEL["spot"] left two stale "spot" defaults behind, because the task's file list was scoped by
        line number and never named them:

        1. automation.py's `pilot start` resolved `market = ... or "spot"` and then indexed PILOT_LABEL with it
           -- an uncaught KeyError on the plain `pilot start` command, which no test exercised.
        2. pilot-loop.sh defaulted PILOT_MARKET to "spot" and pointed its state dir at data/live/pilot, which
           PILOT_STOP no longer covers. A loop started that way places real orders and `/automation off` cannot
           reach its kill switch -- and since the loop no longer branches on market at all, PILOT_MARKET had
           stopped selecting a STRATEGY and only selected a DIRECTORY.

        The registries are the single source; nothing may resolve a market outside them."""
        import importlib
        auto = importlib.import_module("automation")
        self.assertEqual(list(auto.PILOT_LABEL), auto.PILOT_MARKETS,
                         "PILOT_LABEL and PILOT_MARKETS must cover exactly the same markets")
        for rel in ("scripts/automation.py", "scripts/pilot-loop.sh",
                    "integrations/launchd/com.tyme.trading.pilot.futures.plist"):
            for i, line in code_lines(rel):
                st = line.lstrip()
                self.assertNotIn('"spot"', line, f"{rel}:{i} still resolves a deleted market: {st}")
                self.assertNotIn("'spot'", line, f"{rel}:{i} still resolves a deleted market: {st}")
                self.assertNotIn("<string>spot</string>", line, f"{rel}:{i} hardcodes the deleted market: {st}")

    def test_the_kill_switch_covers_every_state_dir_the_loop_can_use(self):
        """PILOT_STOP is what `/automation off` writes. If the loop can run with a state dir PILOT_STOP does not
        name, that loop is unstoppable through the tool while still placing orders."""
        import importlib, re
        auto = importlib.import_module("automation")
        code = "\n".join(l for l in open(os.path.join(ROOT, "scripts", "pilot-loop.sh"),
                                          encoding="utf-8").read().splitlines()
                          if not l.lstrip().startswith("#"))
        dirs = set(re.findall(r"data/live/(pilot[a-z-]*)", code))
        covered = {os.path.basename(os.path.dirname(p)) for p in auto.PILOT_STOP}
        self.assertTrue(dirs and dirs <= covered,
                        f"pilot-loop.sh can use {sorted(dirs)} but PILOT_STOP only covers {sorted(covered)}")

    def test_the_config_carries_no_profile_key(self):
        cfg = json.load(open(CONFIG, encoding="utf-8"))
        self.assertNotIn("pilot_profile", cfg.get("execution", {}))
