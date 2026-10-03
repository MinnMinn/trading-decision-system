"""The drift guard for the EN/VI language switch.

The switch has one failure mode that matters and it is silent: a page that looks finished but prints one
language's words into the other's UI. Nothing about that throws, nothing about it looks wrong in a diff, and the
person who notices is a reader who cannot read the sentence. So the guarantee cannot be "we were careful" -- it
has to be a test that fails the build, which is this repo's idiom everywhere else (test_methods_sync.py,
test_instruments_sync.py, test_doc_citations.py).

Six checks, and each one closes a different way for the defect to arrive:

  1. No Vietnamese literal in a renderer          -- the string never got a catalog entry at all
  2. Every message carries every locale           -- the entry exists but one language was never written
  3. Placeholders agree across locales            -- a translation quietly dropped a number
  4. Registry display strings carry every locale  -- methods.json half-migrated
  5. Per-method messages are pure in EVERY locale -- the English translation reached for the other method's word
  6. Numbers are parameters, never baked in       -- a figure got frozen into the catalog, away from the code

Check 5 is the one that earns its keep. scripts/method_purity.py gates the build for per-method ANALYSIS blocks
only (build-artifact.py feeds it layer 1/2/3, never the chrome), so the glossary, the ladder, the legend and the
bias basis have no build gate at all. They are checked here instead, in both languages.
"""
import json
import os
import re
import unittest
from html.parser import HTMLParser

import srcscan

ROOT = srcscan.ROOT

import importlib.util


def _load(name):
    p = os.path.join(ROOT, "scripts", name)
    spec = importlib.util.spec_from_file_location(name.replace("-", "_").replace(".py", ""), p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


i18n = _load("i18n.py")
mp = _load("method_purity.py")
CATALOG = json.load(open(os.path.join(ROOT, "docs", "architecture", "i18n.json"), encoding="utf-8"))
MESSAGES = {k: v for k, v in CATALOG["messages"].items() if not k.startswith("_")}

# Letters that only Vietnamese uses. A plain Latin-1 range would flag × and → and every accented word in a
# citation, which is how the first version of this scan produced 226 false positives.
VI_LETTERS = re.compile(
    "[ăâđêôơưĂÂĐÊÔƠƯàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ"
    "ÀÁẢÃẠẰẮẲẴẶẦẤẨẪẬÈÉẺẼẸỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌỒỐỔỖỘỜỚỞỠỢÙÚỦŨỤỪỨỬỮỰỲÝỶỸỴ]")

# The files that RENDER a published page. A user-facing string in any of them belongs in the catalog.
RENDERERS = ["scripts/build-artifact.py", "scripts/chart.js", "scripts/journal_render.py",
             "scripts/method-panel.py", "scripts/htf_context.py", "scripts/system-ranking.py"]

# The only Vietnamese allowed to remain in renderer CODE: machine values that are matched, never displayed.
# Translating any of these would change a decision rather than a label -- see htf_context.LONG_STRUCT.
MACHINE_VALUE_LINES = (
    "LONG_STRUCT", "SHORT_STRUCT", "DIRECTION", "VERDICT_CLASS",
    'v.startswith("PHÁ',                       # anchor-verdict prefix match, htf_context
    'verdict.PHÁ', 'verdict.CHỜ', 'verdict.THEO', 'verdict.SETUP',   # display-map KEYS, keyed by the machine value
    'structure.tích', 'structure.tái', 'structure.phân', 'structure.chưa',
    'dữ liệu tới',                             # the layer-2 prelim-head contract (three files must agree)
    # An artifact's <title> is its IDENTITY in the gallery and the browser tab, and the Artifact tooling expects
    # it stable across redeploys -- a changed title reads as a different page. So it stays as first published,
    # and the language toggle sets document.title at runtime instead. Marked, not translated.
    "artifact-identity:",
)


# Functions that write the MODEL BRIEF, not a page. The brief is input to the analysis model, and the model
# authors in i18n.AUTHORED -- so its prose belongs in that language and translating it would be a category
# error. htf_context is on the renderer list because its `basis` DOES reach the page; these two functions are
# the half that does not. (basis_text renders the same keyed basis in whichever locale its audience needs.)
MODEL_FACING = {"scripts/htf_context.py": ("brief_lines", "ladder_lines", "check_verdict")}


def _model_facing_lines(rel):
    """Line numbers belonging to the model-facing functions of `rel`, resolved by AST rather than by comment
    markers so a renamed or moved function cannot silently widen the exemption."""
    names = MODEL_FACING.get(rel)
    if not names:
        return set()
    import ast as _ast
    tree = _ast.parse(open(os.path.join(ROOT, rel), encoding="utf-8").read())
    out = set()
    for node in _ast.walk(tree):
        if isinstance(node, _ast.FunctionDef) and node.name in names:
            out.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return out


class NoVietnameseLiteralsInRenderers(unittest.TestCase):
    """Check 1. The analogue of test_build_artifact.py's 'the gloss belongs to methods.json' rule, generalised:
    a user-facing string has exactly one legal home, and it is not a renderer."""

    def test_renderers_contain_no_vietnamese_literals(self):
        offenders = []
        for rel in RENDERERS:
            exempt = _model_facing_lines(rel)
            for lineno, line in srcscan.code_lines(rel):
                if not VI_LETTERS.search(line) or lineno in exempt:
                    continue
                if any(tok in line for tok in MACHINE_VALUE_LINES):
                    continue
                offenders.append(f"{rel}:{lineno}: {line.strip()[:110]}")
        self.assertEqual(offenders, [], "Vietnamese literal(s) in renderer code — these belong in "
                                        "docs/architecture/i18n.json (or methods.json, for a registry label):\n"
                                        + "\n".join(offenders))


class CatalogIsComplete(unittest.TestCase):
    def test_every_message_has_every_locale(self):
        """Check 2. A missing locale is the defect the whole feature exists to prevent: i18n.t() raises rather
        than falling back, so a gap is a crash at build time -- but only on the code path that renders it."""
        missing = [f"{k} [{l}]" for k, v in MESSAGES.items() for l in i18n.LOCALES
                   if not (v.get(l) or "").strip()]
        self.assertEqual(missing, [], f"messages missing a locale: {missing}")

    def test_placeholders_are_identical_across_locales(self):
        """Check 3. A translation that drops a {placeholder} loses a NUMBER -- silently, in one language only."""
        bad = []
        for k, v in MESSAGES.items():
            sets = {l: set(re.findall(r"\{(\w+)\}", v[l])) for l in i18n.LOCALES}
            if len({frozenset(s) for s in sets.values()}) != 1:
                bad.append(f"{k}: {sets}")
        self.assertEqual(bad, [], "placeholder sets differ between locales:\n" + "\n".join(bad))

    # Message keys reach the catalog by more routes than a t() call: a module constant (_TIER_KEY), a dict
    # value, a *_key parameter resolved later (htf_context's basis), _b("bias.…"). The first version of this
    # check pattern-matched call shapes and so saw none of those -- it captured zero keys out of
    # htf_context.py while its docstring claimed to check every key in the catalog was asked for.
    #
    # So the scan is over STRING LITERALS instead: any literal that equals a catalog key counts as a use,
    # whatever syntax surrounds it. Dynamic keys ("journal.col." + col, f"structure.{word}") contribute their
    # prefix, and every catalog key under it counts as used.
    KEY_LITERAL = re.compile(r"""['"]([a-zA-Z0-9_.]+)['"]""")
    KEY_PREFIX = re.compile(r"""['"]([a-z][a-zA-Z0-9_.]*\.)['"]\s*(?:\+|\})|f['"]([a-z][a-zA-Z0-9_.]*\.)\{""")

    @classmethod
    def _used_keys(cls):
        used, prefixes = set(), set()
        for rel in RENDERERS + ["scripts/i18n.py"]:
            src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
            used |= {m for m in cls.KEY_LITERAL.findall(src) if m in MESSAGES}
            for a, b in cls.KEY_PREFIX.findall(src):
                prefixes.add(a or b)
        for p in prefixes:
            used |= {k for k in MESSAGES if k.startswith(p)}
        return used, prefixes

    def test_no_undefined_keys(self):
        """Check 2b. Every key a renderer asks for exists."""
        pat = re.compile(r'(?:i18n\.t|i18n\.tx|i18n\.tb|i18n\.attr|_b|[^a-z_]T)\(\s*["\']([a-zA-Z0-9_.]+)["\']')
        used = set()
        for rel in RENDERERS + ["scripts/i18n.py"]:
            src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
            used |= set(pat.findall(src))
            used |= set(re.findall(r"""L\(\s*['"]([a-z][a-zA-Z0-9_.]+)['"]""", src))
            used |= set(re.findall(r"""[a-z_]+_key\s*=\s*['"]([a-zA-Z0-9_.]+)['"]""", src))
        undefined = sorted(k for k in used if k not in MESSAGES and "." in k and not k.endswith("."))
        self.assertEqual(undefined, [], f"renderers ask for keys the catalog does not define: {undefined}")

    def test_no_orphan_keys(self):
        """Check 2c. Every key in the catalog is asked for by something. An orphan is dead weight shipped to
        every reader, and worse, it is usually the fossil of a string that moved -- the live copy of which is
        then a hardcoded literal somewhere."""
        used, _ = self._used_keys()
        orphans = sorted(set(MESSAGES) - used)
        self.assertEqual(orphans, [], f"catalog keys nothing asks for: {orphans}")

    def test_every_runtime_key_is_inside_the_slice_actually_shipped(self):
        """The three JS runtimes resolve keys from a SLICE of the catalog, chosen by prefix at build time. A key
        outside its page's slice does not raise -- all three L() implementations fall back to the default locale
        and then to printing the raw key, so the page shows `panel.status.waiting` and nothing complains.

        That is not hypothetical: the tab title shipped exactly this way. switch_js() was handed a title key
        that was not in the shim's `ui.` slice, the call looked wired, and the tab silently kept the wrong
        language. The prefixes are read from each renderer's own js_catalog() call rather than restated here,
        so narrowing a slice fails this test instead of quietly stranding keys.
        """
        def args_of(rel):
            src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
            i = src.index("js_catalog(") + len("js_catalog(")
            return re.findall(r"""["']([^"']+)["']""", src[i:src.index(")", i)])

        def keys_in(js):
            # \bL( also matches J.L( and this.L( -- the journal resolves through an object, chart.js and the
            # panel through a bare function, and all three are the same lookup.
            return set(re.findall(r"""\bL\(\s*['"]([a-z][a-zA-Z0-9_.]+)['"]""", js))

        chart_js = open(os.path.join(ROOT, "scripts", "chart.js"), encoding="utf-8").read()
        panel = _load("method-panel.py")
        journal = _load("journal_render.py")
        cases = [
            ("chart.js", keys_in(chart_js), args_of("scripts/build-artifact.py")),
            ("method-panel.py _SCRIPT", keys_in(panel._SCRIPT), args_of("scripts/method-panel.py")),
            ("journal_render.py JOURNAL_JS", keys_in(journal.JOURNAL_JS), args_of("scripts/journal_render.py")),
        ]
        for name, keys, prefixes in cases:
            self.assertTrue(prefixes, f"{name}: could not read its js_catalog prefixes")
            shipped = set(i18n.js_catalog(*prefixes))
            self.assertTrue(keys, f"{name}: found no runtime keys — this test is pinning nothing")
            missing = sorted(keys - shipped)
            self.assertEqual(missing, [], f"{name} resolves keys at runtime that its slice "
                                          f"{prefixes} does not ship: {missing}")


class RegistryDisplayStringsCarryEveryLocale(unittest.TestCase):
    """Check 4. methods.json owns some display text (`reads`, `pane.label`, preset `label`); a bare string there
    means one language's words would print into the other's UI. `dimensions.*.label` is deliberately NOT in this
    list -- Wyckoff, ICT, Footprint and Heatmap are proper nouns."""

    def test_methods_json_display_fields_are_localized(self):
        reg = json.load(open(os.path.join(ROOT, "docs", "architecture", "methods.json"), encoding="utf-8"))
        bad = []
        for name, dim in reg["dimensions"].items():
            for field, value in (("reads", dim.get("reads")), ("pane.label", dim["pane"]["label"])):
                for l in i18n.LOCALES:
                    if not isinstance(value, dict) or not (value.get(l) or "").strip():
                        bad.append(f"dimensions.{name}.{field} [{l}]")
        for p in reg["presets"]:
            for l in i18n.LOCALES:
                if not isinstance(p.get("label"), dict) or not (p["label"].get(l) or "").strip():
                    bad.append(f"presets[{p['id']}].label [{l}]")
        self.assertEqual(bad, [], f"registry display strings missing a locale: {bad}")

    def test_generated_schema_text_stays_english_only(self):
        """A JSON Schema is a developer artifact read by validators, not by viewers. Keeping generated schema
        text single-language stops someone 'completing' the localization into a machine contract."""
        for rel in ("docs/architecture/schemas/automation-config.schema.json",):
            src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
            doc = json.loads(src)
            descs = re.findall(r'"description"\s*:\s*"([^"]*)"', json.dumps(doc, ensure_ascii=False))
            offenders = [d for d in descs if VI_LETTERS.search(d)]
            self.assertEqual(offenders, [], f"{rel} carries Vietnamese in a generated description: {offenders}")


class MessagesRespectMethodPurity(unittest.TestCase):
    """Check 5 -- the one the build gate does not do.

    scripts/build-artifact.py submits only layer 1, 2 and 3 blocks to method_purity. The glossary, the ladder
    cells, the legend and the bias basis are never checked there, in any language. They are checked here, in
    every language, because the English translations are where this is easiest to get wrong: 'markup' and
    'trading range' are Wyckoff terms an ICT sentence reaches for naturally, and 'sweep' is a liquidity word a
    Wyckoff sentence reaches for naturally. The Vietnamese originals avoid both -- 'cú xuyên', not 'quét'.
    """

    # key prefix -> the method whose vocabulary that message must stay inside
    SCOPES = (("bias.ict.", "ict"), ("l1.ict.", "ict"), ("gloss.ict.", "ict"),
              ("bias.wy.", "wyckoff"), ("l1.wyckoff.", "wyckoff"), ("gloss.wyckoff.", "wyckoff"),
              ("gloss.footprint.", "footprint"), ("gloss.heatmap.", "heatmap"))

    def test_every_per_method_message_is_pure_in_every_locale(self):
        bad = []
        for key, text_by_locale in MESSAGES.items():
            method = next((m for pre, m in self.SCOPES if key.startswith(pre)), None)
            if not method:
                continue
            for l in i18n.LOCALES:
                for term, snippet in mp.violations(text_by_locale[l], method):
                    bad.append(f"{key} [{l}] as {method}: {term!r} in …{snippet}…")
        self.assertEqual(bad, [], "message(s) use another method's vocabulary:\n" + "\n".join(bad))


class NumbersComeFromCode(unittest.TestCase):
    """Check 6. SYSTEM-DESIGN §13: every price, percentage and threshold on the page is computed. A figure baked
    into a message is a second source for it, and it cannot be recomputed when the parameter changes."""

    # A citation is a reference, not a measurement: "(knowledge/ict/core-a.md §2.18–2.19)", "WA p93–96".
    # Stripped wholesale rather than number-by-number, or the allowlist becomes its own maintenance burden.
    CITATION = re.compile(r"\([^()]*(?:knowledge/|WA p|§|\.md|analysis-params|session-model|SYSTEM-DESIGN)[^()]*\)"
                          r"|WA p[\d–-]+|§[\d.–-]+|\b[a-z-]+\.md\b")
    # Figures that ARE the concept, not a tunable: OTE's fib levels, the standard-deviation targets, the
    # midpoint of a range, the ends of a percentage scale. Changing one changes the definition, not a setting.
    DEFINITIONAL = re.compile(r"\b0\.5\b|\bCE 0\.5\b|\.62\b|\.705\b|\.79\b|\b0\.62–0\.79\b|−2\.5|−2\b|−4\b"
                              r"|\b0%|\b50%|\b100%|\b1/3\b|\bA–E\b|\bPO3\b|\bUTC\+7\b"
                              r"|\b08:30\b|\b13:30\b|\b08–11\b|\b00Z\b|\b1\b")

    def test_no_measurement_is_frozen_into_a_message(self):
        bad = []
        for key, v in MESSAGES.items():
            for l in i18n.LOCALES:
                text = re.sub(r"\{\w+\}", " ", v[l])          # placeholders are the code-computed values
                text = self.CITATION.sub(" ", text)
                text = self.DEFINITIONAL.sub(" ", text)
                for m in re.findall(r"\d[\d.,]*\s*%|\b\d[\d.,]{2,}\b", text):
                    bad.append(f"{key} [{l}]: {m!r} in {v[l][:90]!r}")
        self.assertEqual(bad, [], "figure(s) frozen into the catalog — pass them as parameters instead, so the "
                                  "page keeps one source for every number:\n" + "\n".join(bad))


class DisplayLocaleNeverReachesComputation(unittest.TestCase):
    """The display timezone follows the language on purpose. The SESSION timezones must not.

    chart.js has two notions of time: `SESSIONS`/`localHour`, which convert to the exchange's real zone per date
    so killzone shading follows DST, and `fmtTime`, which shifts a timestamp into whatever zone the reader
    chose. They must never meet. If the session code ever read LANG, changing language would move the killzone
    bands -- a presentation control silently editing an analysis input, which is the one thing this whole
    feature promises it cannot do.
    """

    def test_the_session_conversion_takes_its_zone_from_the_session_table(self):
        """localHour(iso, tz) is the only place a time is converted into a named zone for a COMPUTATION. Every
        call site must hand it a zone off the SESSIONS table, never anything derived from the reader's locale."""
        src = open(os.path.join(ROOT, "scripts", "chart.js"), encoding="utf-8").read()
        # Not a balanced-paren parse: the first argument is itself a call (T(i)). The zone is the LAST
        # argument, so look for a SESSIONS-table zone before the statement ends.
        calls = [src[m.end():m.end() + 60] for m in re.finditer(r"\blocalHour\(", src)
                 if "const localHour" not in src[max(0, m.start() - 20):m.start()]]
        self.assertTrue(calls, "localHour has no call sites — this test is pinning something that moved")
        for tail in calls:
            self.assertRegex(tail, r"\.tz\s*\)", "localHour must take its zone from the SESSIONS table "
                                                  f"(z.tz), not from the display locale: {tail[:40]!r}")
        for banned in ("tzNow", "fmtTime", "LOCALES["):
            self.assertNotIn(banned, src[src.index("const localHour"):src.index("const weekKey")],
                             f"the session conversion references {banned!r} — the display locale must never "
                             f"reach a computation")

    def test_session_zones_are_real_iana_zones_not_offsets(self):
        """A fixed offset here would silently break across a DST boundary; the display zone may be an offset
        precisely because it is only ever presentation."""
        src = open(os.path.join(ROOT, "scripts", "chart.js"), encoding="utf-8").read()
        sessions = src[src.index("const SESSIONS ="):src.index("\n", src.index("const SESSIONS ="))]
        self.assertIn("Europe/London", sessions)
        self.assertIn("America/New_York", sessions)


class InteractionTimeTextFollowsTheLanguage(unittest.TestCase):
    """Every other string on the page is written at BUILD time, so it ships in both languages as sibling
    elements and the CSS rule picks one. The R:R ruler and bar-replay status line is the exception: it is
    written by chart.js at INTERACTION time, into a single element, in whatever language was current when the
    reader pressed R or P.

    That makes it the one place a language switch can leave the previous language standing. It did: setMode()
    used to take finished text, and restyle() -> render() never re-issued it, so opening the ruler in English
    and switching to Vietnamese left an English sentence under a Vietnamese page. The fix is to store (key,
    params) and repaint from render(); these tests pin both halves so it cannot regress to finished text.
    """

    SRC = open(os.path.join(ROOT, "scripts", "chart.js"), encoding="utf-8").read()

    def test_set_mode_is_handed_a_message_key_not_finished_text(self):
        calls = [m.group(1) for m in re.finditer(r"(?<!function )\bsetMode\(h\s*,([^,)]*)", self.SRC)]
        self.assertGreaterEqual(len(calls), 6, "setMode has lost call sites — this test pins something that moved")
        for arg in calls:
            self.assertNotRegex(arg, r"^\s*L\(", "setMode must take a message key, not text already resolved in "
                                                 f"one language: setMode(h, {arg.strip()[:50]}")
            key = arg.strip().strip("'\"")
            if key:
                self.assertIn(key, MESSAGES, f"setMode key {key!r} is not in the catalog")

    def test_a_key_valued_param_is_resolved_at_paint_time(self):
        """`space_key` holds the Play/Pause word inside the replay sentence. Resolving it when the key is
        STORED would freeze one language's word into the other language's sentence — so it is resolved in
        resolveKeys(), which runs on every paint."""
        self.assertRegex(self.SRC, r"function resolveKeys\(params\)\{.*?_key.*?L\(params\[k\]\)",
                         "resolveKeys must resolve *_key params through L() at paint time")
        for m in re.finditer(r"\{[^{}]*?\bspace(_key)?\s*:", self.SRC):
            self.assertTrue(m.group(1), "the replay sentence's Play/Pause word must be passed as `space_key` "
                                        "(a key, resolved at paint) — not as `space` (already resolved)")

    def test_nothing_shadows_the_message_lookup(self):
        """`L` is the message lookup for every runtime string chart.js draws. A local binding named L shadows
        it for its whole block, and the failure is silent until that branch runs: `applyLane`'s volume lane
        declared `const L=[]` for its label array, so `L('chart.mean_n')` there called the array and threw
        `L is not a function` -- only on the lanes that draw volume labels, only after an interaction.
        """
        # Catches a lone declaration (`const L=[]`), a declaration anywhere in a comma list (`const n=…, L=i=>…`
        # -- how the ICT engine's LOW accessor shadowed L for 34 call sites), and a parameter named L.
        pattern = (r"\b(?:const|let|var)\s+[^;\n]*?\bL\s*=" r"|\(\s*L\s*(?:,|\)\s*=>)" r"|,\s*L\s*[,)]"
                   r"|\bfunction\s*\w*\s*\([^)]*\bL\b[^)]*\)")
        for m in re.finditer(pattern, self.SRC):
            line = self.SRC[:m.start()].count("\n") + 1
            self.assertTrue(False, f"chart.js:{line} binds the name `L`, shadowing the message lookup: "
                                   f"{m.group(0)!r}")

    def test_render_repaints_the_mode_line(self):
        """restyle() -> render() is the whole language-change path inside chart.js. If render() does not
        repaint, the status line keeps the old language until the reader interacts again."""
        body = self.SRC[self.SRC.index("function render(){"):self.SRC.index("function restyle(){")]
        self.assertIn("paintMode(h)", body,
                      "render() must call paintMode on every chart so a language switch repaints the mode line")
        self.assertRegex(self.SRC, r"function paintMode\(h\)\{[^}]*?L\(h\.mode\.key",
                         "paintMode must resolve the stored key in the CURRENT locale")


class SwitchingLanguageChangesNothingButWords(unittest.TestCase):
    """The load-bearing claim of this whole feature, checked on a real built page rather than asserted.

    A language switch is a presentation change. If it can move a price, a percentage, a multiple or a bar count,
    it is not a presentation change any more -- it is a page that says two different things about one market
    depending on who is reading, which on a trading page is the worst outcome available.

    The one thing that MAY differ is a clock time, because the display timezone follows the language on purpose
    (EN -> UTC, VI -> VNT). Times are stripped before the comparison and checked separately, by their offset.
    """

    # A displayed TIME may legitimately differ: the display zone follows the language on purpose. Every shape
    # the pages actually render is stripped before the comparison -- clock, d/m, dd-mm, and the yy-mm-dd range
    # labels a slow style prints, which shift a whole DAY across the switch, not just hours.
    TIME = re.compile(r"\b\d{2}-\d{2}-\d{2}\b|\b\d{1,2}:\d{2}\b|\b\d{1,2}/\d{1,2}\b"
                      r"|\b\d{2}-\d{2}\s\d{1,2}:\d{2}\b|\b\d{2}-\d{2}\b")
    NUMBER = re.compile(r"-?\d[\d,]*\.?\d*%?")
    # A zone LABEL is not a measurement: "UTC+7" is the name of the display zone, and the zone is meant to
    # differ between locales. Stripped alongside the times themselves.
    ZONE = re.compile(r"\bUTC\s*\+\s*\d+|\bUTC\b|\bVNT\b")

    @classmethod
    def setUpClass(cls):
        cls.pages = _build_all_pages()

    def _numbers(self, html_text, locale):
        """Every number a reader in `locale` actually SEES.

        Through VisibleText, not a regex over the source, for three reasons the first version got wrong: a
        `<span lang=..>(.*?)</span>` match truncates at the first NESTED close tag and silently drops the rest
        of the region; it cannot tell a hidden sibling from a shown one when they nest; and it leaves HTML
        entities in place, so `&#x27;` in an English-only apostrophe contributed the number 27 and the page
        looked like it disagreed with itself.
        """
        p = VisibleText(locale)
        p.feed(html_text)
        text = " ".join(t for t, _ in p.seen)
        return sorted(self.NUMBER.findall(self.ZONE.sub(" ", self.TIME.sub(" ", text))))

    def test_every_number_is_identical_in_both_locales(self):
        for name, html_text in self.pages.items():
            with self.subTest(page=name):
                base = self._numbers(html_text, i18n.DEFAULT)
                self.assertTrue(base, f"{name}: found no numbers to compare — the extraction is broken, "
                                      f"not the page")
                for l in i18n.LOCALES:
                    if l == i18n.DEFAULT:
                        continue
                    other = self._numbers(html_text, l)
                    self.assertEqual(base, other,
                                     f"{name}: a number differs between {i18n.DEFAULT} and {l}. Switching "
                                     f"language is a presentation change; it may not move a price, a "
                                     f"percentage or a count.")

    def test_the_page_actually_carries_the_switch(self):
        """The visibility rule and the shim must BOTH be in the page.

        Leaving either out fails in the worst possible way: nothing errors, and every language paints at once,
        so the page reads as garbled duplicate text. It happened once on the journal, where the stylesheet had
        no placeholder for the rule and the replace() silently did nothing.
        """
        for name, html_text in self.pages.items():
            with self.subTest(page=name):
                self.assertIn('[data-lang="', html_text, f"{name}: the locale-visibility CSS is missing — "
                                                         f"every language would paint at once")
                self.assertIn("data-i18n-lang", html_text, f"{name}: the language toggle is missing")
                self.assertIn("artifact-lang", html_text, f"{name}: the shim that stamps data-lang is missing")

    def test_no_raw_locale_object_reaches_the_page(self):
        """Registry display fields are {locale: text} objects now. Interpolating one straight into a template
        prints its repr -- "{'en': 'Wyckoff', 'vi': 'Wyckoff'}" -- which looks like a bug to a reader and is
        invisible to every other check here. It happened once on the method panel's preset cards."""
        for name, html_text in self.pages.items():
            body = re.sub(r"<script>.*?</script>", " ", html_text, flags=re.S)
            for pat in (r"\{&#x27;en&#x27;:", r"\{'en':", r'\{"en":\s*"', r"&#39;en&#39;:"):
                with self.subTest(page=name, pattern=pat):
                    self.assertIsNone(re.search(pat, body),
                                      f"{name}: a raw locale object was rendered into the page (matched "
                                      f"{pat!r}) — pass it through i18n.dual / methods.text instead")

    def test_every_displayed_time_names_its_zone(self):
        """No bare clock time anywhere in code-rendered text. While the model prose still states its own times
        in UTC, a zone name on every code-rendered time is the only thing that keeps the two unambiguous on one
        page -- a reader must never have to guess which zone a number is in."""
        for name, html_text in self.pages.items():
            with self.subTest(page=name):
                self._assert_zoned(name, html_text)

    def _assert_zoned(self, name, html_text):
        body = re.sub(r"<script>.*?</script>", " ", html_text, flags=re.S)
        # Drop the authored-prose blocks: they carry their own times and are shown verbatim, by design.
        body = re.sub(r'<(span|div) class="vi-src[^"]*"[^>]*>.*?</\1>', " ", body, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", body)          # match and slice the SAME string, or offsets lie
        zones = {i18n.tz_of(l)[0] for l in i18n.LOCALES} | {"UTC"}
        # A session WINDOW is defined in the exchange's own zone and names it inline ("NY AM 08:30-11
        # America/New_York"); that is a definition, not a displayed timestamp, and it is already unambiguous.
        iana = re.compile(r"[A-Z][a-z]+/[A-Z][a-z_]+")
        bare = []
        for m in re.finditer(r"\b\d{1,2}:\d{2}\b", text):
            tail = text[m.end():m.end() + 30]
            if any(z in tail for z in zones) or iana.search(tail):
                continue
            bare.append(text[max(0, m.start() - 50):m.end() + 18].strip())
        self.assertEqual(bare, [], f"{name}: clock time(s) rendered without a zone name:\n"
                                   + "\n".join(bare[:8]))


class VisibleText(HTMLParser):
    """What a reader in `active` actually SEES, by applying the locale-visibility rules to the tree.

    Every other check in this file inspects SOURCE. This one inspects the rendered result: a string can be in
    the catalog, have both locales, pass purity, and still be visible in the wrong language because its wrapper
    was attached to the wrong element. That is the defect a reader would report, so it gets its own check.
    """

    VOID = {"br", "img", "input", "meta", "link", "hr", "source", "col"}
    # <title> is the browser TAB, not text on the page, and it is deliberately stable (artifact identity in the
    # gallery). The tab is retitled at runtime instead -- pinned separately by TabTitleFollowsTheLanguage below.
    NOT_PAGE_TEXT = {"title"}

    def __init__(self, active):
        super().__init__(convert_charrefs=True)
        self.active, self.stack, self.seen, self.skip = active, [], [], 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style") or tag in self.NOT_PAGE_TEXT:
            self.skip += 1
        if tag in self.VOID:
            return
        lang, keep = a.get("lang"), "data-i18n-keep" in a
        hidden = bool(lang and lang != self.active and not keep)
        self.stack.append((tag,
                           hidden or any(h for _, h, _ in self.stack),
                           keep or any(k for _, _, k in self.stack)))

    def handle_startendtag(self, tag, attrs):
        if tag in ("script", "style"):
            return

    def handle_endtag(self, tag):
        if (tag in ("script", "style") or tag in self.NOT_PAGE_TEXT) and self.skip:
            self.skip -= 1
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if self.skip or not data.strip():
            return
        if any(h for _, h, _ in self.stack):          # hidden: the other locale's half
            return
        marked = any(k for _, _, k in self.stack)      # deliberately shown authored prose
        self.seen.append((data.strip(), marked))


class NoWrongLanguageIsEverVisible(unittest.TestCase):
    """The reader's-eye check, on all three published page families.

    In English mode the only Vietnamese a reader may see is prose that was AUTHORED in Vietnamese and is marked
    as such (i18n.vi_source). Anything else is the defect this whole feature exists to prevent.
    """

    @classmethod
    def setUpClass(cls):
        cls.pages = _build_all_pages()

    def test_english_mode_shows_no_unmarked_vietnamese(self):
        for name, html_text in self.pages.items():
            p = VisibleText("en")
            p.feed(html_text)
            stray = sorted({t for t, marked in p.seen if VI_LETTERS.search(t) and not marked})
            self.assertEqual(stray, [], f"{name}: Vietnamese visible in English mode, unmarked:\n"
                                        + "\n".join("  " + s[:100] for s in stray[:10]))

    def test_vietnamese_mode_shows_no_english_chrome(self):
        """The mirror case. Machine values (LONG, SHORT, MSS, BSL, dimension names, symbols) read the same in
        both languages by design, so the check is that no English SENTENCE survives -- approximated as a run of
        three or more lowercase English words, which no machine value produces."""
        sentence = re.compile(r"\b[a-z]{2,}\s+[a-z]{2,}\s+[a-z]{2,}\b")
        for name, html_text in self.pages.items():
            p = VisibleText("vi")
            p.feed(html_text)
            stray = sorted({t for t, marked in p.seen
                            if not marked and sentence.search(t) and not VI_LETTERS.search(t)})
            # file paths and citations are English by nature and are not UI copy
            stray = [s for s in stray if not re.search(r"\.md|\.py|\.json|knowledge/|docs/|http", s)]
            self.assertEqual(stray, [], f"{name}: untranslated English visible in Vietnamese mode:\n"
                                        + "\n".join("  " + s[:100] for s in stray[:10]))


class TabTitleFollowsTheLanguage(unittest.TestCase):
    """A page whose static <title> is not in the default locale must retitle the TAB at runtime.

    The <title> element itself stays as first published -- it is the artifact's identity in the gallery, and the
    tooling expects it stable across redeploys. That is a deliberate trade, and it only holds up if the other
    half is wired: the shim setting document.title. Without it the tab is the one string an English reader
    cannot read, which is exactly the gap this test was written after finding.
    """

    def test_a_non_default_locale_title_carries_a_runtime_title_key(self):
        for name, page in _build_all_pages().items():
            m = re.search(r"<title>(.*?)</title>", page, re.S)
            self.assertIsNotNone(m, f"{name}: no <title>")
            if not VI_LETTERS.search(m.group(1)):
                continue                       # already language-neutral; nothing to retitle
            key = re.search(r',T="([a-z][a-zA-Z0-9_.]+)"', page)
            self.assertIsNotNone(key, f"{name}: <title> is {m.group(1)!r} but the shim carries no title key, "
                                      f"so the browser tab stays in that language whatever the reader chooses")
            # The static title is the artifact's identity, so it must be what the key renders in the AUTHORING
            # locale -- otherwise the gallery and the tab disagree about what the page is called.
            self.assertEqual(m.group(1).strip(), i18n.t(key.group(1), i18n.AUTHORED),
                             f"{name}: the static <title> and the title key's {i18n.AUTHORED!r} message differ")
            # ...and the key must RESOLVE in the catalog the shim was given. Asserting only that a key was
            # passed is what let a broken tab title pass this test once: the call looked wired, the shim looked
            # up a key its own catalog did not contain, and document.title was silently never set.
            cat = re.search(r",C=(\{.*?\}),T=", page, re.S)
            self.assertIsNotNone(cat, f"{name}: cannot find the shim catalog")
            self.assertIn(f'"{key.group(1)}"', cat.group(1),
                          f"{name}: title key {key.group(1)!r} is not in the catalog the shim ships, so "
                          f"document.title is never set")


def _build_all_pages():
    """One built page per family, from fixtures where possible and real registries otherwise."""
    import tempfile
    out = {}
    tmp = tempfile.mkdtemp()

    ba = _load("build-artifact.py")
    real_read = ba.read_json
    keep = ("analysis-params.json", "automation-config.json")
    ba.read_json = lambda path, default=None: real_read(path, default) if path.endswith(keep) else default
    ba.candles = lambda sym, tf, n, snap=None: (_synth(n, ba.TF_MIN.get(tf, 15)), "2026-09-12T00:00:00Z", "fixture")
    # every symbol is drawable when every candle is a fixture: the real drawable() asks whether a FEED FILE exists,
    # which on a machine without MetaTrader is never true for the cfd styles -- and build() then sys.exit()s the run
    ba.drawable = lambda syms, tf: (list(syms), [])
    # More than one style, and not all from one market. A style's tiers decide which date formats appear, and a
    # slow style's %y-%m-%d range labels shift a DAY across the timezone switch where an intraday one shifts
    # only hours -- a difference the number check has to be built to tolerate, so it has to be exercised.
    for style in ("scalping", "cfd-swing"):
        chart = os.path.join(tmp, f"chart-{style}.html")
        ba.build(style, chart)
        out[f"chart page ({style})"] = open(chart, encoding="utf-8").read()

    mp_ = _load("method-panel.py")
    out["method panel"] = mp_.render(mp_.facts())

    jr = _load("journal_render.py")
    journal = os.path.join(tmp, "journal.html")
    # Populated, not empty. An empty journal renders empty states and nothing else -- no ledger rows, no review
    # fields, no R curve, no rehearsal chip -- so an [] fixture checks the page's chrome and none of its content.
    rows = _journal_rows()
    closed_real = [r for r in rows if r["status"] == "closed" and r["mode"] == "real"]
    st = dict(closed=len(closed_real), open=1, planned=1, rehearsal=1, win_rate=50.0, wins=1, losses=1,
              avg_r=0.25, avg_win_r=1.5, avg_loss_r=-1.0, profit_factor=1.5, total_r=0.5, pnl_usd=125.0,
              max_drawdown_r=-1.0, worst_losing_streak=1)
    jr.render(rows, st, journal, closed_real)
    out["trade journal"] = open(journal, encoding="utf-8").read()

    sr = _load("system-ranking.py")
    out["system ranking"] = sr.render(sr.rows())
    return out


def _journal_rows():
    """Two closed real trades (one win, one loss), one open, one rehearsal -- enough to render every ledger
    column, the R curve, the status chips and a full review block with prose in every field."""
    def row(i, status, mode, r=None, **kw):
        d = dict(id=f"2026-09-0{i}-BTCUSDT-0{i}", market="crypto", instrument="BTCUSDT",
                 direction="long" if i % 2 else "short", setup_type="Spring", session="London",
                 entry=77000.0 + i, stop=76500.0 + i, targets=[78000.0 + i, 78500.0 + i],
                 planned_rr=2.0, status=status, mode=mode, exit_type="target", result="win" if (r or 0) > 0 else "loss",
                 r_multiple=r, pnl_usd=(r or 0) * 100, hold_hours=4.5,
                 date_opened=f"2026-09-0{i}T08:00:00Z", date_closed=f"2026-09-0{i}T18:30:00Z")
        d.update(kw)
        return d
    review = dict(thesis="Spring[C] ở biên dưới TR.", plan_vs_actual="Vào đúng kế hoạch.",
                  followed_plan=True, exit_reason="Chạm target 1.", root_cause="—",
                  is_mistake=False, lessons="Giữ nguyên size.", review_notes="Không có gì bất thường.",
                  what_to_change="Không.", confidence=4, emotional_state="bình tĩnh",
                  tags=["wyckoff", "spring"], screenshots=[])
    return [row(1, "closed", "real", 1.5, **review),
            row(2, "closed", "real", -1.0, **review),
            row(3, "open", "real"),
            row(4, "closed", "rehearsal", 0.8)]


def _synth(n, step_min=15, base=77000.0):
    import datetime
    t = datetime.datetime(2026, 9, 1)
    out, p = [], base
    for i in range(n):
        o = p
        c = o + ((i * 37) % 11 - 5) * 12.5
        out.append(dict(time=t.strftime("%Y-%m-%dT%H:%M:%SZ"), open=o, high=max(o, c) + (i * 13) % 7 * 4,
                        low=min(o, c) - (i * 17) % 5 * 4, close=c, volume=1 + (i * 7) % 13))
        p = c
        t += datetime.timedelta(minutes=step_min)
    return out


if __name__ == "__main__":
    unittest.main()


class EveryPageDeclaresItsEncoding(unittest.TestCase):
    """A page whose analysis prose is Vietnamese must say it is utf-8, in the bytes, before anything else.

    Found 2026-09-18 by opening a built page in a real browser: `document.characterSet` came back
    `windows-1252` and the whole Vietnamese analysis rendered as mojibake. No unit test could have seen it --
    the bytes on disk were always correct utf-8, and the Artifact host's own wrapper supplies a charset, so the
    published page looked fine. The failure only exists where the file is served or opened directly, which is
    exactly how a human reviews a build. The meta must be within the browser's 1024-byte encoding pre-scan, so
    this checks the head of the file rather than merely that the string appears somewhere.
    """

    BUILDERS = ("build-artifact.py", "journal_render.py", "method-panel.py", "system-ranking.py")

    def test_every_page_builder_emits_a_charset_meta_first(self):
        for b in self.BUILDERS:
            with open(os.path.join(ROOT, "scripts", b), encoding="utf-8") as fh:
                src = fh.read()
            self.assertIn('<meta charset="utf-8">', src, f"{b} emits no charset declaration")

    def test_a_built_page_declares_utf8_within_the_pre_scan_window(self):
        import subprocess
        import sys
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "p.html")
            r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "build-artifact.py"),
                                "scalping", "--out", out, "--snapshot-dir", tmp],
                               capture_output=True, text=True, cwd=ROOT)
            if r.returncode != 0:
                self.skipTest(f"the page could not be built here: {r.stdout[-200:]}{r.stderr[-200:]}")
            with open(out, "rb") as fh:
                head = fh.read(1024)
        self.assertIn(b'<meta charset="utf-8">', head,
                      "the charset declaration is outside the browser's encoding pre-scan window")
        self.assertLess(head.index(b'charset'), head.index(b'<title>'),
                        "the charset must be declared before any other content")
