"""One system: one engine, one style vocabulary, one risk decision.

User decision 2026-09-13: keep strategy-runner.py on three horizons (scalping 15m / day 1H / swing 4H) at
planned R:R >= 3 and 3 % risk; delete demo-pilot.py, the execution.pilot_profile switch, the ten-value STYLE
map and the gold-* names. These tests exist because every one of those was a SECOND way to express something
the system already expressed once, and the duplicates drifted: the floor drifted (2R vs 3R), the risk ceiling
drifted (1 % vs 3 %), and `scalping` meant 1m in one vocabulary and 15m in the other.

The method-preset switch is deliberately NOT covered here -- all six presets and the control panel stay.
"""
import json, os, re, unittest

from srcscan import code_lines, code_text   # the ONE source-scanning helper; see scripts/tests/srcscan.py

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


def load_script(name):
    """Import one of the hyphenated scripts by PATH. `importlib.import_module` cannot reach `local-eval-brief.py`
    or `build-artifact.py` -- a hyphen is not a legal module name and underscoring the string just asks for a
    module that does not exist. This is the same spec_from_file_location loader test_timeframe_ladder.py uses."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(name.replace("-", "_")[:-3], os.path.join(SCRIPTS, name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


HORIZONS = ("scalping", "day", "swing")
HORIZON_TF = {"scalping": "15m", "day": "1h", "swing": "4h"}
STYLES = {("crypto", "15m"): "scalping", ("crypto", "1h"): "day", ("crypto", "4h"): "swing",
          ("cfd", "15m"): "cfd-scalping", ("cfd", "1h"): "cfd-day", ("cfd", "4h"): "cfd-swing"}
# No skip list. An earlier draft of these scans carried a PENDING_FLAT_CONSUMERS tuple while the six flat-name
# consumers were still being renamed; it is deliberately gone rather than left empty, because a skip list that
# outlives its reason is exactly the second, drifting source this whole change exists to remove.


class OneStyleVocabulary(unittest.TestCase):
    """Before 2026-09-13 there were two vocabularies: automation.STYLE mapped (market, tf) to ten HAND-WRITTEN
    labels (scalping/daytrade/1h/4h/swing + five gold-*), while rank-setups.HORIZONS mapped three horizon names to
    timeframe SETS. They overlapped and DISAGREED -- `scalping` was 1m in one and 15m in the other, `swing` was 1D
    in one and 4H in the other. Now there is one authored source (HORIZONS + HORIZON_TF) and STYLE is DERIVED from
    it, so a flat style name cannot drift from the horizon it belongs to."""

    def setUp(self):
        import importlib
        self.auto = importlib.import_module("automation")

    def test_horizons_are_the_only_authored_names(self):
        self.assertEqual(tuple(self.auto.HORIZONS), HORIZONS)

    def test_each_horizon_maps_to_exactly_one_timeframe(self):
        self.assertEqual(self.auto.HORIZON_TF, HORIZON_TF)

    def test_style_is_derived_from_the_horizon_table(self):
        """Six flat names, three horizons, two markets -- and each name's horizon half must map back through
        HORIZON_TF to the timeframe its own key carries. A hand-edited STYLE entry fails here."""
        self.assertEqual(self.auto.STYLE, STYLES)
        for (m, tf), style in self.auto.STYLE.items():
            hz = style[4:] if style.startswith("cfd-") else style
            self.assertIn(hz, HORIZONS, f"{style} is not one of the three horizons")
            self.assertEqual(HORIZON_TF[hz], tf, f"{style} claims {tf}, HORIZON_TF says {HORIZON_TF[hz]}")
            self.assertEqual(self.auto.market_of_style(style), m, f"market_of_style({style}) != {m}")

    def test_the_dropped_timeframes_are_not_scanned(self):
        """1m and 5m were entry windows; 1D was the swing entry. All three leave the SCANNED set (decision 3)."""
        for m, tfs in self.auto.MARKET_TIMEFRAMES.items():
            self.assertEqual(tfs, ["15m", "1h", "4h"], f"{m} still scans {tfs}")
        for gone in ("1m", "5m", "1D"):
            self.assertNotIn(gone, self.auto.TIMEFRAMES, f"{gone} is still a selectable timeframe")

    def test_no_gold_prefixed_names_survive(self):
        """The cfd market is distinguished by a `cfd-` prefix now, the way pilot-top5.json uses a market field.

        This asserted `re.search(r'"gold(-[a-z0-9]+)?"')` until the 2026-09-13 review: requiring DOUBLE QUOTES
        around the token meant it matched none of the places the name actually lived -- not
        `AUTO_STYLES="${AUTO_STYLES:-...,gold,gold-1h}"`, not `case "$STYLE" in scalping|gold-scalp)`, not
        `run_style 5m gold-scalp`, not single-quoted Python. It would have passed against an UNCHANGED
        scan-loop.sh and model-read.sh. That was the fifth vacuous test in this plan; a plain substring test over
        code_lines() is what its sibling below already does, and it covers bash.
        """
        for path in sources():
            for i, line in code_lines(path):
                self.assertNotIn("gold", line, f"{path}:{i} keeps a gold-* style name")

    def test_daytrade_is_not_a_name_any_more(self):
        """`daytrade` (15m) and `day` (1H) were two names one keystroke apart for different timeframes."""
        for path in sources():
            for i, line in code_lines(path):
                self.assertNotIn("daytrade", line, f"{path}:{i} keeps the superseded `daytrade` name")

    def test_every_style_still_has_a_full_context_ladder(self):
        """Dropping 1D from the SCANNED set must not leave swing without a bias tier -- PAGE_RUNGS keeps 1D and
        1W as context-only rungs, and this asserts that the distinction actually holds."""
        for style in STYLES.values():
            tiers = self.auto.TIERS[style]
            self.assertIsNotNone(tiers["structure"], f"{style} lost its structure tier")
            self.assertIsNotNone(tiers["bias"], f"{style} lost its bias tier")

    def test_a_tier_never_points_at_the_other_market(self):
        """TIERS is built per market; a crypto style's structure tier must not resolve to a cfd style."""
        for (m, _tf), style in self.auto.STYLE.items():
            for name in ("structure", "bias"):
                t = self.auto.TIERS[style][name]
                if t and t["style"]:
                    self.assertEqual(self.auto.market_of_style(t["style"]), m,
                                     f"{style}.{name} points at {t['style']}, the other market")


ARTIFACTS = os.path.join(ROOT, "docs", "architecture", "artifacts.json")
RETIRED_URLS = {                       # style -> the page that style USED to publish, before the 2026-09-13 collapse
    "scalping@1m": "59f0b15b-9d2c-4ac7-b15f-f630ae4a1c49",
    "swing@1D": "c5cb9060-4e2a-4a53-be8c-f4c911c28961",
    "gold-scalp@5m": "7238cd92-2b73-49c9-819f-02edba87018d",
    "gold-swing@1D": "7013f87b-0ee2-43c8-9372-7bb6d929d326",
}


class FlatStyleConsumersFollowTheVocabulary(unittest.TestCase):
    """Six consumers key off the flat style name and carry no market field. Two names were REUSED for a different
    timeframe (scalping 1m -> 15m, swing 1D -> 4h), so every one of these tables had a stale-value trap."""

    def setUp(self):
        import importlib
        self.auto = importlib.import_module("automation")
        with open(ARTIFACTS, encoding="utf-8") as f:
            self.artifacts = json.load(f)["styles"]

    def test_every_style_has_exactly_one_artifact_entry(self):
        self.assertEqual(sorted(self.artifacts), sorted(self.auto.STYLE.values()))

    def test_no_reused_name_inherited_a_retired_page(self):
        """THE hazard: `scalping` means 15m now. If its url were still the 1m page's, the publish tick would push
        15m content onto the page the user knows as the 1m scalping page."""
        for style, entry in self.artifacts.items():
            for what, uid in RETIRED_URLS.items():
                self.assertNotIn(uid, entry.get("url", ""),
                                 f"{style} inherited the retired {what} page")

    def test_scalping_inherited_the_fifteen_minute_page(self):
        self.assertIn("46b302c5", self.artifacts["scalping"]["url"])
        self.assertIn("97773ba6", self.artifacts["cfd-scalping"]["url"])

    def test_styles_with_no_page_yet_are_pending_not_wrong(self):
        for style in ("day", "swing", "cfd-day", "cfd-swing"):
            self.assertEqual(self.artifacts[style]["url"], "PENDING",
                             f"{style} has no page yet; the registry's own convention is PENDING")

    def test_local_eval_brief_covers_exactly_the_six_styles(self):
        self.assertEqual(sorted(load_script("local-eval-brief.py").TF),
                         sorted(self.auto.STYLE.values()))

    def test_build_artifact_covers_exactly_the_six_styles(self):
        self.assertEqual(sorted(load_script("build-artifact.py").STYLES),
                         sorted(self.auto.STYLE.values()))

    def test_every_headless_prompt_names_a_live_style(self):
        """A prompt file for a retired style is a cron pointing at nothing: model-read.sh exits 2 on a missing
        prompt, but a SURVIVING prompt for a deleted style would run a read no page consumes."""
        live = set(self.auto.STYLE.values())
        for fn in sorted(os.listdir(os.path.join(ROOT, "integrations", "headless"))):
            style = re.sub(r"-(local-read|daily-full)\.md$", "", fn)
            self.assertIn(style, live, f"integrations/headless/{fn} names a retired style")

    def test_scan_loop_default_styles_are_the_live_ones(self):
        src = open(os.path.join(ROOT, "scripts", "scan-loop.sh"), encoding="utf-8").read()
        m = re.search(r'AUTO_STYLES="\$\{AUTO_STYLES:-([^}"]*)\}"', src)
        self.assertIsNotNone(m, "AUTO_STYLES default not found")
        self.assertEqual(sorted(m.group(1).split(",")), sorted(self.auto.STYLE.values()))

    def test_narrative_schema_enumerates_the_six(self):
        with open(os.path.join(ROOT, "docs", "architecture", "schemas", "narrative.schema.json"),
                  encoding="utf-8") as f:
            enum = json.load(f)["properties"]["style"]["enum"]
        self.assertEqual(sorted(enum), sorted(self.auto.STYLE.values()))


class RankSetupsAgreesWithTheOneVocabulary(unittest.TestCase):
    """rank-setups.HORIZONS held timeframe SETS that ranged over timeframes the scanner no longer runs -- the
    scalping set also named the retired five-minute rung, day also named 30m/2H, swing also named 1D. It writes
    pilot-top5.json, which selects what the live engine trades, so a horizon that can select a 30m setup the
    scanner never scans is a selection nothing can execute."""

    def setUp(self):
        import importlib
        self.auto = importlib.import_module("automation")
        self.rank = load_script("rank-setups.py")

    def test_one_timeframe_per_horizon(self):
        self.assertEqual(self.rank.HORIZONS, {"scalping": "15m", "day": "1H", "swing": "4H"})

    def test_it_agrees_with_automation_case_insensitively(self):
        """rank-setups spells timeframes 1H/4H, automation spells them 1h/4h -- same rungs, different case. The
        spelling difference is load-bearing: rank-setups' strings index the backtest row data."""
        self.assertEqual({h: tf.lower() for h, tf in self.rank.HORIZONS.items()},
                         {h: tf.lower() for h, tf in self.auto.HORIZON_TF.items()})

    def test_the_cfd_timeframe_table_holds_only_live_rungs(self):
        """CFD_TFS was a SECOND stale timeframe table, read at three sites -- two of them the non-horizons modes,
        so it does not disappear with the horizons loop. A superset is harmless today and rots unnoticed."""
        self.assertEqual(self.rank.CFD_TFS, {"15m", "1H", "4H"})


class NoBeforeAfterDocs(unittest.TestCase):
    """These compared the legacy arrangement to the live one. The legacy arrangement is deleted, so they
    describe a system that cannot be run -- and a reader cannot tell which file is the current state. Git
    history keeps them if the comparison is ever needed again."""

    SUPERSEDED = ("2026-09-13-legacy-full-run.md", "2026-09-13-live-full-run.md",
                  "2026-09-13-live-rules-vs-legacy.md", "2026-09-13-stability-cfd-live.md",
                  "2026-09-13-stability-crypto-live.md", "2026-09-13-top-setups-live.md")

    def test_they_are_deleted(self):
        for fn in self.SUPERSEDED:
            self.assertFalse(os.path.exists(os.path.join(ROOT, "docs", "backtests", fn)), f"{fn} still present")

    # Dated records, not live citations -- the same three directories test_doc_citations.py skips. The plan
    # itself lives in docs/plans/ and names all six files in SUPERSEDED and in its own `git rm`, so without this
    # the test could never pass.
    HISTORICAL = ("docs/plans", "docs/audits", "docs/prompts")

    def test_nothing_links_to_them(self):
        """A dead evidence link is worse than no link: it reads as a citation."""
        for dirpath, _, files in os.walk(os.path.join(ROOT, "docs")):
            rel_dir = os.path.relpath(dirpath, ROOT)
            if rel_dir.startswith(self.HISTORICAL):
                continue
            for fn in files:
                if not fn.endswith(".md"):
                    continue
                p = os.path.join(dirpath, fn)
                src = open(p, encoding="utf-8").read()
                for dead in self.SUPERSEDED:
                    self.assertNotIn(dead, src, f"{os.path.relpath(p, ROOT)} links to deleted {dead}")
