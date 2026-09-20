"""The headless model layer (scripts/model-read.sh + integrations/headless/*.md) runs Sonnet with `claude -p`:
no permission prompts, nobody to answer a question. 2026-09-20, first time a daily-full actually reached the
model (the launchd fix in test_scan_loop.py): it stopped after ONE turn to ask whether it may read
knowledge/ -- the prompt forbade opening `knowledge/` in one sentence and required reading
knowledge/integrated/method.md in the next. The same prompts hard-coded BTCUSDT/ETHUSDT/SOLUSDT (nine enabled)
and a 288-bar window (the scanner reads 576), and scripts/local-eval-brief.py defaulted to the same three names
-- so check-narrative.py reported every other enabled symbol as `missing`. These pin the fixes.
"""
import glob, importlib.util, os, re, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROMPTS = sorted(glob.glob(os.path.join(ROOT, "integrations", "headless", "*.md")))


def _load(name, rel):
    s = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


class BriefSymbolSource(unittest.TestCase):
    def test_default_symbols_are_the_instruments_automation_enabled(self):
        brief = _load("local_eval_brief", "scripts/local-eval-brief.py")
        auto = _load("automation", "scripts/automation.py")
        cfg, _, _ = auto.load()
        for style in brief.TF:
            want = auto.enabled_instruments(cfg, auto.market_of_style(style))
            self.assertEqual(list(brief.default_symbols(style)), list(want),
                             f"{style}: the brief must cover the symbols /automation enabled (what scan-loop.sh "
                             f"and check-narrative.py use), not a hard-coded list")


class ScannerSymbolSource(unittest.TestCase):
    def test_ict_scan_has_no_hardcoded_symbol_default(self):
        src = open(os.path.join(ROOT, "scripts", "ict-scan.py"), encoding="utf-8").read()
        self.assertNotIn('default="BTCUSDT', src, "ict-scan.py --symbols must default to the /automation-enabled list: "
                                                  "the headless full analysis confirms its verdicts with it")


class HeadlessPrompts(unittest.TestCase):
    def setUp(self):
        self.assertTrue(PROMPTS, "no headless prompts found")
        self.texts = {os.path.basename(p): open(p, encoding="utf-8").read() for p in PROMPTS}

    def test_no_prompt_hardcodes_a_symbol(self):
        I = _load("instruments", "scripts/instruments.py")
        for fn, t in self.texts.items():
            hits = [s for s in I.analysis() if re.search(rf"\b{re.escape(s)}\b", t)]
            self.assertEqual(hits, [], f"{fn} names {hits}: the symbol list has ONE source "
                                       f"(docs/architecture/instruments.json via the brief), never the prompt")

    def test_no_prompt_hardcodes_a_bar_count(self):
        for fn, t in self.texts.items():
            self.assertIsNone(re.search(r"\b\d+-bar window\b|--n \d+", t),
                              f"{fn} carries a literal bar count; the window is scripts/automation.py SCAN_WINDOW, "
                              f"printed by the brief")

    def test_prompts_do_not_forbid_the_files_they_require_and_never_ask(self):
        for fn, t in self.texts.items():
            self.assertIsNone(re.search(r"Do NOT open[^.]*knowledge/", t),
                              f"{fn} forbids reading knowledge/ and then requires knowledge/ -- the headless model "
                              f"stopped to ask which one wins (2026-09-20)")
            self.assertIn("never stop to ask", t, f"{fn}: a `claude -p` run has nobody to answer; say so")


if __name__ == "__main__":
    unittest.main()
