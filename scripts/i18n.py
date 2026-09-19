#!/usr/bin/env python3
"""The reader for docs/architecture/i18n.json -- THE single source of truth for every user-facing string the
published pages render from code, and for the locale records (display timezone, html lang) that go with them.

Twin of scripts/methods.py and scripts/instruments.py: the JSON is authored, this module is the only reader,
and scripts/tests/test_i18n.py fails the build if a renderer grows a literal instead of a key.

Three rules this module exists to enforce:

  1. NO SILENT FALLBACK. t() raises on a missing key or a missing locale. A page that quietly prints the
     Vietnamese string because the English one was never written is exactly the "unintentional mixing" the
     feature is meant to prevent, and it would ship looking fine.

  2. NUMBERS ARE PARAMETERS, NEVER TRANSLATED. Every price/%/time is computed by the caller (build-artifact.py's
     fmtn/hhmm/when, SYSTEM-DESIGN.md §13 "numbers from code") and passed in as a {placeholder}. The message
     carries words and punctuation only, so the same number reaches both locales byte-identical.

  3. A PAGE CARRIES EVERY LOCALE. dual() renders its fragment once per locale into sibling elements tagged with
     a real `lang` attribute; CSS (artifact_theme.SWITCH_CSS) shows one. There is deliberately no "build in
     language X" mode: one artifact URL serves both languages, and a build flag could publish a monolingual
     page to a URL whose readers expect the toggle.

API:
  t(key, lang, **params)      -> str         one locale's string, formatted
  tx(key, **params)           -> html        inline dual-rendered <span lang=..>, ready to drop in a template
  tb(key, **params)           -> html        block dual-rendered <div lang=..>
  dual(fn, tag=, cls=)        -> html        fn(lang) -> html, for a fragment that interleaves computed HTML
  LOCALES / DEFAULT / tz_of(lang) / shift(iso, lang) / stamp(iso, lang)
  js_catalog(prefix)          -> dict        the slice chart.js needs, injected through build-artifact's __PARAMS__
"""
import datetime
import html
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "docs", "architecture", "i18n.json")

_DOC = json.load(open(PATH, encoding="utf-8"))
LOCALES = tuple(_DOC["locales"])            # authored order == the order the toggle renders
DEFAULT = _DOC["default"]
_LOC = _DOC["locales"]
_MSG = _DOC["messages"]

if DEFAULT not in _LOC:
    raise ValueError(f"{PATH}: default locale {DEFAULT!r} is not one of {sorted(_LOC)}")

_PARAM = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

# The locale the ANALYSIS PROSE is authored in today: the headless model reads write Vietnamese
# (scripts/local-eval-brief.py rule 5), and the human's trade reviews are Vietnamese too. Phase 2 has the model
# author both languages at source, at which point this stops being a single value. Named here so the "this
# passage is in another language" treatment is driven by a fact, not by assuming everything non-English is prose.
AUTHORED = "vi"


# --------------------------------------------------------------------------------------------- locale records
def locale(lang):
    try:
        return _LOC[lang]
    except KeyError:
        raise KeyError(f"i18n: unknown locale {lang!r}; i18n.json declares {list(LOCALES)}") from None


def tz_of(lang):
    """(display name, offset minutes) for this locale. PRESENTATION ONLY.

    The offset shifts what a timestamp READS AS on the page. It never touches a stored time, a candle time, a
    decision time, or the IANA-zone session/killzone computation in chart.js (SESSIONS) and journal.py -- those
    convert from the real exchange zone per date and must keep following DST regardless of who is reading.
    """
    tz = locale(lang)["tz"]
    return tz["name"], tz["offset_minutes"]


def num(v, kind="float", lang=DEFAULT):
    """Format a number for display. Lives here, beside the locale records, because it is the one presentation
    helper every renderer needs -- the page, the chart, the bias basis, the model brief.

    Numerals are deliberately IDENTICAL in every locale. A price rendered 1.234,56 in the ladder while the chart
    tooltip beside it reads 1,234.56 and the model prose reads 1,234.56 would be three renderings of one number
    on one screen: a misreading risk with no upside. It is also what lets the tests assert every number is
    byte-identical across locales, which is the proof that the switch is presentation-only.

    That decision is DATA, not an assumption baked in here: it is `number_locale` on each locale record. A
    locale that declared something else would need a formatter this module does not have, so it raises rather
    than quietly formatting en-US anyway and leaving the declaration to look honoured. No silent fallback.
    """
    loc = locale(lang)["number_locale"]
    if loc != "en-US":
        raise NotImplementedError(
            f"i18n: locale {lang!r} declares number_locale={loc!r}; only 'en-US' grouping is implemented. "
            f"Implement it in i18n.num() rather than letting the declaration be ignored.")
    if v is None:
        return t("ui.dash", lang)
    return f"{v:,.0f}" if kind == "int" else f"{v:,.2f}"


def _utc(iso):
    """Parse a stored UTC timestamp. Tolerant of the shapes that actually appear on disk -- seconds omitted
    ("...T11:00Z"), date only, with or without the Z -- because a display helper must not be the thing that
    fails a build. The helpers this replaced sliced the string instead of parsing it, so they never cared;
    a fixed-width strptime would have turned a 16-character timestamp into a crash."""
    if not iso:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"i18n: {iso!r} is not an ISO timestamp") from None
    return dt.replace(tzinfo=None) if dt.tzinfo is None else dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)


def shift(iso, lang):
    """UTC ISO string -> datetime shifted into this locale's display zone. Returns None for a falsy input."""
    dt = _utc(iso)
    return None if dt is None else dt + datetime.timedelta(minutes=tz_of(lang)[1])


def clock(iso, lang):
    """A displayed clock time, ALWAYS carrying its zone name, and its DATE whenever the shift crossed midnight.

    Two rules, both load-bearing on a trading page:

      * Never a bare clock time. During phase 1 the model-authored prose still states its own times in UTC while
        the chrome may be reading VNT; a zone name on every code-rendered time is the only thing that keeps the
        two unambiguous side by side.
      * Never a shifted time without its date when the shift moved the day. A 23:00 UTC candle is 06:00 VNT the
        NEXT morning; printing a bare "06:00 VNT" beside a headline dated the 17th is a genuine misread, not a
        cosmetic one. The check lives here, inside the formatter, so no call site can forget it.
    """
    d = shift(iso, lang)
    if d is None:
        return "—"
    s = f'{d.strftime("%H:%M")} {tz_of(lang)[0]}'
    utc_day = _utc(iso).date()
    return s if d.date() == utc_day else f"{s} ({d.day}/{d.month})"


def stamp(iso, lang, fmt="%d/%m %H:%M"):
    """A displayed date+time, always carrying its zone name. No rollover suffix is needed: the date is present."""
    d = shift(iso, lang)
    return "—" if d is None else f"{d.strftime(fmt)} {tz_of(lang)[0]}"


# --------------------------------------------------------------------------------------------- messages
def t(key, lang, **params):
    """One locale's message, formatted. Raises on a missing key, a missing locale, or a missing parameter --
    never falls back to another language."""
    try:
        entry = _MSG[key]
    except KeyError:
        raise KeyError(f"i18n: no message {key!r} in {os.path.relpath(PATH, ROOT)}") from None
    try:
        s = entry[lang]
    except KeyError:
        raise KeyError(f"i18n: message {key!r} has no {lang!r} translation "
                       f"(has {sorted(k for k in entry if k in _LOC)})") from None
    if not params:
        return s
    try:
        return s.format(**params)
    except KeyError as e:
        raise KeyError(f"i18n: message {key!r} [{lang}] wants parameter {e.args[0]!r}, which was not passed") from None


def params_of(key, lang):
    """The {placeholder} names a message uses -- the parity check in test_i18n.py compares these across locales."""
    return set(_PARAM.findall(_MSG[key][lang]))


def keys():
    return tuple(_MSG)


def has(key):
    """Whether the catalog carries this key. For value-keyed lookups (`verdict.<stored value>`) where a miss is
    an expected, meaningful state -- a composed string with no catalog entry -- rather than an authoring bug."""
    return key in _MSG


# --------------------------------------------------------------------------------------------- dual rendering
def dual(fn, tag="span", cls=None):
    """Render fn(lang) once per locale into sibling elements carrying a real `lang` attribute.

    Wraps CONTENT, never structure: the grids on these pages (.matrix, .ladder) place their cells with
    grid-template-columns, so duplicating a cell would add a column. Duplicating what is INSIDE a cell cannot.
    Callers therefore pass the cell's contents here, not the cell.
    """
    c = f' class="{cls}"' if cls else ""
    return "".join(f'<{tag} lang="{l}"{c}>{fn(l)}</{tag}>' for l in LOCALES)


def tx(key, **params):
    """Inline dual-rendered message."""
    return dual(lambda l: t(key, l, **params))


def tb(key, **params):
    """Block dual-rendered message."""
    return dual(lambda l: t(key, l, **params), tag="div")


def vi_source(html_fragment, block=False):
    """Mark a fragment AUTHORED IN VIETNAMESE by a model or a human and inserted verbatim.

    Three kinds of text reach these pages: chrome written by the renderers (bilingual, from this catalog),
    machine values (never translated), and authored prose. This is the third.

    It keeps `lang="vi"` -- which is simply true, and lets a screen reader pronounce it correctly -- plus
    `data-i18n-keep`, which exempts it from the locale-visibility rule so it stays READABLE in English mode
    instead of vanishing. It is never machine-translated on the way through: translating an analysis would
    change the analysis, and what a reader should get is the author's own words with the boundary marked.

    Callers: anchor level labels and the scanner's composed anchor verdict (authored into
    data/live/anchors.<style>.json by the full analysis), the layer-2 and layer-3 model blocks, the narrative
    headline, and the journal's human review fields.
    """
    if not block:
        return f'<span class="vi-src" lang="vi" data-i18n-keep>{html_fragment}</span>'
    tag = "".join(f'<span lang="{l}">{html.escape(t("ui.vi_source.tag", l))}</span>' for l in LOCALES)
    return (f'<div class="vi-src vi-block" lang="vi" data-i18n-keep>'
            f'<div class="vi-tag">{tag}</div>{html_fragment}</div>')


def attr_all(name, texts):
    """An attribute value (title, aria-label, ...) in every locale.

    An attribute cannot carry `lang` siblings, so this is the one place the switch works by swapping rather than
    by showing and hiding. Every locale's value is RESOLVED HERE, at build time, and parked in a data attribute;
    the shim only copies strings across. Nothing is formatted at runtime, so a tooltip carrying a computed number
    is as deterministic as the rest of the page. The real attribute holds the default locale, so the tooltip is
    correct before the shim runs and when scripting is off.
    """
    q = lambda s: html.escape(str(s), quote=True)
    return " ".join([f'{name}="{q(texts[DEFAULT])}"']
                    + [f'data-i18n-{name}-{l}="{q(texts[l])}"' for l in LOCALES])


def attr(name, key, **params):
    return attr_all(name, {l: t(key, l, **params) for l in LOCALES})


# --------------------------------------------------------------------------------------------- the JS side
def js_catalog(*prefixes):
    """The messages chart.js (and the toggle shim) resolve at runtime, as {key: {lang: text}}.

    chart.js draws its labels onto the chart after load, so those strings cannot be lang-tagged siblings in the
    HTML. They ride in through build-artifact.py's existing __PARAMS__ object instead.
    """
    return {k: {l: v[l] for l in LOCALES} for k, v in _MSG.items() if any(k.startswith(p) for p in prefixes)}


def js_locales():
    """Locale records for the client: tz name/offset for the chart axis and crosshair, label for the toggle,
    and number_locale -- which the canvas and the axis read for the same reason i18n.num() does, so the
    declaration governs every number on the page rather than only the ones Python formats."""
    return {l: {"label": _LOC[l]["label"], "name": _LOC[l]["name"],
                "tz": _LOC[l]["tz"], "number_locale": _LOC[l]["number_locale"]} for l in LOCALES}


# --------------------------------------------------------------------------------------------- the switch itself
# Lives here, not in artifact_theme.py, on purpose: all three page families must import THIS module to render a
# string at all, whereas method-panel.py deliberately does not use artifact_theme's palette. Putting the switch
# beside the strings is what stops the panel needing a theme it does not want in order to get a toggle.
#
# The rules are GENERATED from LOCALES: a third language is a row in i18n.json, not a CSS edit.
def switch_css():
    """The visibility rules, GENERATED from LOCALES -- a third language is a row in i18n.json, not a CSS edit.

    Three rules, and the order matters:

      1. `[lang=..]` inside a page that has no data-lang yet shows the DEFAULT locale only. This rule is
         load-bearing, not a nicety: the Artifact tool owns <html> and <body>, so the renderer cannot stamp
         data-lang server-side -- the shim does it, and until the shim runs there IS no data-lang. Without this
         rule every language paints at once for that first instant, and for the whole page when scripting is off.
      2. Once data-lang is set, hide every locale that is not the active one.
      3. The ACTIVE locale's wrapper is `display: contents`, not `display: block/inline`. The wrapper then
         vanishes from layout entirely, so a localized fragment behaves exactly as if the span were not there --
         inline flow inside a <p>, grid cells, flex items all unaffected. This is what lets dual() wrap content
         anywhere without the wrapper itself becoming a grid or flex item.
    """
    others = [b for b in LOCALES if b != DEFAULT]
    pre = ", ".join(f'[lang="{b}"]:not([data-i18n-keep])' for b in others)
    hide = ", ".join(f'[data-lang="{a}"] [lang="{b}"]:not([data-i18n-keep])'
                     for a in LOCALES for b in LOCALES if a != b)
    show = ", ".join(f'[data-lang="{a}"] [lang="{a}"]' for a in LOCALES)
    return f"""
:root:not([data-lang]) :where({pre}) {{ display: none; }}
{hide} {{ display: none !important; }}
{show} {{ display: contents; }}
.i18n-switch {{ display:inline-flex; gap:2px; padding:3px; border-radius:8px;
  border:1px solid var(--line, rgba(127,127,127,.35)); background:var(--surface-2, rgba(127,127,127,.08)); }}
.i18n-switch button {{ font:inherit; font-size:11.5px; font-weight:700; letter-spacing:.04em; padding:5px 10px;
  border-radius:6px; border:1px solid transparent; background:transparent; color:var(--muted, inherit);
  cursor:pointer; line-height:1; }}
.i18n-switch button:hover {{ color:var(--ink, inherit); }}
.i18n-switch button[aria-pressed="true"] {{ background:var(--surface, rgba(127,127,127,.18));
  color:var(--ink, inherit); border-color:var(--line-strong, rgba(127,127,127,.5)); }}
.i18n-switch button:focus-visible {{ outline:2px solid var(--accent, #2F5FC9); outline-offset:2px; }}
.i18n-tz {{ font-size:11px; color:var(--faint, inherit); margin-left:8px; align-self:center; }}
.i18n-authored {{ font-size:11px; line-height:1.5; color:var(--warn, #B5731C);
  background:var(--warn-soft, rgba(181,115,28,.12)); border-radius:6px; padding:4px 8px; margin:0 0 8px; }}
/* The "this analysis is written in {AUTHORED}" notice has nothing to say to a reader who is already reading
   in {AUTHORED}. It is an explanation of a language boundary, and in that locale there is no boundary. */
:root[data-lang="{AUTHORED}"] .i18n-authored {{ display: none; }}

/* Prose authored in {AUTHORED} and shown verbatim in every language (i18n.vi_source). Marked, never hidden and
   never machine-translated: translating an analysis would change the analysis, so the honest thing to show is
   the author's own words with the language boundary visible. The marking appears only when the UI is NOT in the
   authoring language, which is the only case where a reader needs to be told. */
:root:not([data-lang="{AUTHORED}"]) .vi-src {{ text-decoration:underline dotted var(--faint, #8592A2) 1px;
  text-underline-offset:3px; }}
:root:not([data-lang="{AUTHORED}"]) .vi-block {{ display:block; text-decoration:none;
  border-left:2px solid var(--line-strong, rgba(127,127,127,.5)); padding-left:10px; }}
.vi-tag {{ display:none; font-size:9.5px; letter-spacing:.06em; text-transform:uppercase;
  color:var(--faint, #8592A2); margin-bottom:4px; }}
:root:not([data-lang="{AUTHORED}"]) .vi-block > .vi-tag {{ display:block; }}
"""


def switch_html():
    """The EN/VI control. `aria-pressed` carries the state, so the active button is announced, not just coloured.

    Each button's tooltip names the language it switches TO, in that language -- a reader who cannot read the
    current UI language can still read the button that gets them out of it.
    """
    btns = "".join(
        f'<button type="button" data-i18n-lang="{l}" aria-pressed="{"true" if l == DEFAULT else "false"}" '
        f'title="{html.escape(t("ui.lang.switch_to", l, name=_LOC[l]["name"]), quote=True)}">'
        f'{html.escape(_LOC[l]["label"])}</button>'
        for l in LOCALES)
    tzs = "".join(f'<span lang="{l}">{html.escape(t("ui.tz.note", l, tz=_LOC[l]["tz"]["note"]))}</span>'
                  for l in LOCALES)
    return (f'<div class="i18n-switch" role="group" {attr("aria-label", "ui.lang.group")}>'
            f"{btns}</div><span class=\"i18n-tz\">{tzs}</span>")


def switch_js(title_key=None):
    """Stamps data-lang before anything paints, wires the buttons, and tells the page when the language changed.

    Ordering matters: this runs at the TOP of the document, so by the time the first localized element parses,
    data-lang is already on <html> and only one locale has ever been visible -- no flash, no reflow.

    localStorage is wrapped because it THROWS outright in some contexts (artifact thumbnail capture, a browser
    set to block site data), not merely returns null; an unguarded read would take the whole page down. A failed
    read simply leaves the default locale, which is a correct page.
    """
    tk = json.dumps(title_key)
    # The shim's catalog is the `ui.*` slice PLUS the title key, wherever it lives. Passing a key whose message
    # the shim cannot resolve is worse than passing none: the call looks wired, the tab silently never changes.
    cat = js_catalog("ui.")
    if title_key:
        if title_key not in _MSG:
            raise KeyError(f"i18n.switch_js: title key {title_key!r} is not in {os.path.relpath(PATH, ROOT)}")
        cat[title_key] = {l: t(title_key, l) for l in LOCALES}
    return ("<script>(function(){var L=" + json.dumps(list(LOCALES)) + ",D=" + json.dumps(DEFAULT) +
            ",C=" + json.dumps(cat) + ",T=" + tk + ","
            "A=['title','aria-label','placeholder'];"
            "var R=document.documentElement;"
            # ?lang= is an explicit choice by the reader, so it is REMEMBERED, not just honoured once. It used
            # to apply and evaporate: open a ?lang=vi link, come back later without the parameter, and the page
            # was English again. Storage is per-artifact-origin, so this is also the only way a choice travels
            # between the three artifacts at all -- see SYSTEM-DESIGN §15.2.
            "function get(){try{var u=new URLSearchParams(location.search).get('lang');if(L.indexOf(u)>=0){"
            "try{localStorage.setItem('artifact-lang',u);}catch(e){}return u;}}catch(e){}"
            "try{var v=localStorage.getItem('artifact-lang');if(L.indexOf(v)>=0)return v;}catch(e){}return D;}"
            "function apply(l){R.setAttribute('data-lang',l);R.setAttribute('lang',l);"
            "document.querySelectorAll('[data-i18n-lang]').forEach(function(b){"
            "b.setAttribute('aria-pressed',String(b.getAttribute('data-i18n-lang')===l));});"
            "A.forEach(function(n){document.querySelectorAll('[data-i18n-'+n+'-'+l+']').forEach(function(e){"
            "e.setAttribute(n,e.getAttribute('data-i18n-'+n+'-'+l));});});"
            "if(T&&C[T]&&C[T][l])document.title=C[T][l];"
            "try{document.dispatchEvent(new CustomEvent('langchange',{detail:{lang:l}}));}catch(e){}}"
            "apply(get());"
            "document.addEventListener('click',function(ev){var b=ev.target.closest&&ev.target.closest('[data-i18n-lang]');"
            "if(!b)return;var l=b.getAttribute('data-i18n-lang');"
            "try{localStorage.setItem('artifact-lang',l);}catch(e){}apply(l);});"
            "document.addEventListener('DOMContentLoaded',function(){apply(R.getAttribute('data-lang')||D);});"
            "})();</script>")
