# EN / VI language switch for every published Artifact

**Status:** phase 1 implemented, 2026-09-17. Phase 2 (bilingual model prose) specified here, not built.
**Scope:** the three page families this repo publishes — the chart artifacts, the method control panel, the
trade journal.

## Context

Every published page was Vietnamese-only, with the strings written as literals inside the Python renderers.
There was no i18n infrastructure of any kind: no catalog, no `lang` attribute, no `localStorage`. The one
locale-aware call in the whole repo was a `toLocaleString("vi-VN")` on the panel, while every chart number
formatted `en-US` — an inconsistency, not a system.

The requirement: a visible EN / VI toggle on every artifact, **English default**, covering all user-facing text
and the displayed timezone; a third language later must not mean rewriting the UI; and the switch is
**presentation-only** — it may not touch the domain model, trading logic, calculations, methodology rules, risk,
backtests or decision outcomes.

## Decisions

### 1. Three kinds of text, three different rules

This is the decision the rest follows from. Text on these pages is not one thing:

| Kind | Rule | Where |
|---|---|---|
| **Chrome** — written by a renderer | Bilingual, from the catalog | `docs/architecture/i18n.json` |
| **Machine values** — matched, not read | Never translated; display label only | the verdict enum, structure words, symbols, acronyms |
| **Authored prose** — written by a model or a human | Shown verbatim, marked, never translated | layer 2/3 blocks, anchor labels, trade reviews |

Translating a machine value would change a decision. Translating an analysis would change the analysis. Only
the first row is a translation problem at all.

### 2. `lang`-tagged siblings, one CSS rule

Each fragment is rendered once per locale into sibling elements carrying a real `lang` attribute
(`i18n.dual`), and one generated CSS rule shows one. The active wrapper is `display: contents`, so it vanishes
from layout and never becomes a grid or flex item; the others are `display: none`.

Rejected: a `data-i18n` + JS `textContent` swap. Both approaches need the same parameterized catalog (every
sentence interleaves computed numbers); the swap additionally needs a JS catalog, re-render logic, and special
handling for `<details>`, attributes and print — and it would have to ship parameter *values* to the client and
format them there, which is what "numbers come from code" forbids.

**The wrapper wraps content, never structure.** The `.matrix` and `.ladder` grids place their cells with
`grid-template-columns`, so duplicating a cell would add a column; duplicating what is inside one cannot. The
same trap applies to `<tr>`/`<th>` and `<dl>`/`<dt>`, where a stray `<span>` is invalid markup and the browser
hoists it out of the table entirely.

**There is no build-time language flag.** One artifact URL serves both languages, so every build emits every
locale. A `--lang` flag could publish a monolingual page to a URL whose readers expect the toggle.

### 3. The Artifact host owns `<html>`, so the shim stamps `data-lang`

These pages emit no `<!doctype>`, `<html>` or `<body>` — the Artifact tool wraps them. The renderer therefore
cannot stamp `data-lang` server-side; an inline script at the very top of the document does it before any
content parses. The CSS carries an explicit "no `data-lang` yet → show the default locale only" rule, which is
what covers both that first instant and a viewer with scripting off.

### 4. Timezone follows the language — and every displayed time names its zone

EN → UTC, VI → VNT (UTC+7). A fixed offset, not an IANA zone: Vietnam has had no DST since 1975, and a `zoneinfo`
lookup would make the host's tzdb version a build input, which the reproducibility rules forbid.

**Computation is untouched.** `chart.js` `SESSIONS`/`localHour` and `journal.py`'s session attribution use real
IANA zones and follow DST; none of them reads the display locale.

Two rules live inside the formatters so no call site can forget them:

- **Never a bare clock time.** Every code-rendered time carries its zone name. This is what lets VNT chrome and
  UTC model prose sit on one page without ambiguity.
- **Never a shifted time without its date when the shift crossed midnight.** 23:00 UTC is 06:00 VNT *the next
  day*; `i18n.clock` appends `(18/9)` in that case.

Two pre-existing bugs were fixed in passing, both of the same family: `chart.js` never set
`tickMarkFormatter`, so the axis rendered in the *browser's* zone while the crosshair hard-appended `Z` (they
already disagreed for any viewer outside UTC); and the panel's `formatTs` formatted in the browser's zone with
no suffix at all, on the page that drives `/automation`.

### 5. Numerals do not follow the language

`1,234.56` in both. Swapping decimal and thousands separators between languages on a page full of prices is a
misreading risk with no upside, and keeping them identical is what lets a test assert that every number is
byte-identical across locales — the concrete proof that the switch is presentation-only.

That is a **declaration, not an assumption**: every locale record carries `number_locale`, all of them say
`en-US` today, and `i18n.num()` is the one formatter for the whole project (`build-artifact.fmtn` delegates to
it, `htf_context` formats its basis levels through it, and `js_locales()` ships it so chart.js and the journal
chart read the same field instead of hardcoding `'en-US'`). A locale declaring anything else raises, rather
than being silently formatted en-US anyway while its declaration looks honoured.

### 5b. Runtime-written text stores a key, not a sentence

Almost every string is written at BUILD time, so it ships in both languages as sibling elements and the CSS
picks one. Three places write text at INTERACTION time, into a single element, in whatever language was current
at that moment — and they are therefore the only places a switch can leave the previous language standing:

| Where | What |
|---|---|
| `chart.js` | the R:R-ruler / bar-replay status line (`setMode`) |
| `method-panel.py` | request status, pending notes, the stall banner, the `db` banner, every `formatTs` zone |
| `journal_render.py` | the R-curve chart's time axis (the library caches its tick labels) |

Each stores a *message key* and repaints from a `data-lang` `MutationObserver`. A parameter named `*_key` is
resolved at paint time, never when stored, so one language's word is never frozen inside another's sentence —
the same convention `basis_text` uses below. The panel's repaint calls `paintMarket()` and deliberately **not**
`renderMarket()`: the latter runs `reconcilePending()`, and a presentation event must not advance a pending
write.

### 6. The bias basis travels as data, because it has two audiences

`htf_context`'s `basis` is read by a human on the page *and* fed to the analysis model in the local-read brief.
One formatted string cannot serve both once the page is bilingual, so a basis is a list of
`(tag, message key, params)` and is rendered late: `basis_text(basis, lang)` for the reader,
`basis_text(basis, i18n.AUTHORED)` for the brief. The `bias` value itself — the thing that gates a trade — is
untouched.

Two parameter conventions, both resolved in the target locale at render time:

* `*_key` — a message key.
* `*_word` — a structure word exactly as the narrative stored it. `_structure()` maps it: a known word to the
  catalog's term ("accumulation"), no word at all to "not established", and anything else to the narrative's own
  word **quoted and marked as written** (`“đi ngang”, as written`). The basis lands in a `title` attribute,
  where `vi_source()`'s markup cannot reach, so the quoting is the marking.

**The stored shape is versioned** (`htf_context.BASIS_FORMAT`). Format 1 — a rendered sentence in the authoring
locale — is what `data/live/prelim/*.facts.json` and the point-in-time snapshots under `data/live/model-reads/`
still hold in places; format 2 is the keyed list. `basis_text()` returns a `str` basis unchanged, so those stay
readable; nothing reads the stored value to make a decision, so no data migration is required (`CLAUDE.md` §59).

### 7. The panel's language choice never reaches the `db`

The method panel is an interactive artifact whose `db` rows are the control plane for `/automation`
(`docs/security/2026-09-12-method-panel.md` PANEL-01). Language is per-viewer presentation and lives in
`localStorage` only. PANEL-02's disclosure is printed in whichever language the reader chose; both locales are
in the markup.

### 8. Artifact titles stay stable

A `<title>` is the artifact's identity in the gallery and the browser tab, and the tooling expects it stable
across redeploys. The static titles are unchanged; the toggle sets `document.title` at runtime instead.

The chart pages pass **no** title key, and that is deliberate: a chart page's name is a market name plus a
trading-style term ("Crypto Scalping", "CFD Swing"), both of which this project leaves untranslated everywhere —
the same rule the glossary follows for *Dealing range*, *premium / discount*, *Killzone* and every methodology
name. There is no second rendering to switch to. The panel and the journal, whose names do differ, pass keys.

### 9. Where the choice does and does not survive

Within a page: `localStorage['artifact-lang']`, so it survives `#anchor` navigation, a reload and a new tab.
`?lang=` overrides **and is remembered**, so a shared link's choice sticks rather than evaporating on the next
plain open.

**It does not travel between the three artifacts.** Each is served from its own origin, so storage never
crosses. Nothing links one artifact to another today, so no in-product navigation loses the choice, and a
`?lang=` link carries it — but a reader who opens the panel and then the journal separately starts at English
in each. Disclosed rather than papered over.

## Enforcement

`scripts/tests/test_i18n.py`. The failure mode this feature has is silent — a page that looks finished but
prints one language into the other's UI — so the guarantee is a test, not care:

1. No Vietnamese literal in a renderer (the string never got a catalog entry).
2. Every message carries every locale (`i18n.t` raises rather than falling back, so a gap is a build crash on
   whichever code path renders it).
3. Placeholder sets identical across locales (a translation that drops a `{placeholder}` drops a *number*).
4. Registry display fields carry every locale; generated JSON Schema text stays English-only.
5. **Per-method messages are method-pure in every locale.** `method_purity.py` gates the build for layer 1/2/3
   analysis blocks only — the glossary, ladder, legend and bias basis have no build gate in any language. They
   are checked here instead. The English wording is where this is easy to get wrong: the idiomatic translation
   of *kỳ vọng tiếp diễn tăng* is "expect continued **markup**", and `markup` is Wyckoff vocabulary forbidden in
   an ICT block; the natural English for *cú xuyên* is "**sweep**", a liquidity word forbidden in a Wyckoff one.
6. No measurement frozen into the catalog (it found one: the footer's scanner parameters, now read from
   `analysis-params.json`).
7. Every number identical across locales inside one built page.
8. Every code-rendered clock time names its zone.
9. No raw locale object rendered (`{'en': …}` — it happened once on the panel's preset cards).
10. The built page actually carries the switch CSS, the toggle and the shim (the journal shipped once without
    the CSS, and every language painted at once).
11. **Every runtime `L('key')` is inside the catalog slice its page actually ships.** All three JS runtimes fall
    back to the default locale and then to printing the raw key, so a key outside its slice shows
    `panel.status.waiting` on the page and nothing errors. The tab title shipped exactly this way once. The
    prefixes are read from each renderer's own `js_catalog()` call, so narrowing a slice fails the test instead
    of silently stranding keys.
12. **Nothing shadows `L`.** A local binding named `L` hides the message lookup for its whole block, and the
    failure is silent until that branch runs — `applyLane`'s volume lane declared `const L=[]` for its label
    array, and `ictAnalyze` used `L` for its LOW accessor across 34 call sites.
13. **No orphan keys** — a catalog entry nothing asks for is usually the fossil of a string that moved, whose
    live copy is then a hardcoded literal somewhere.

Checks 7–10 run over **five** built pages — two chart styles (one intraday, one slow, because a slow style's
range labels shift a whole day across the switch), the panel, and a *populated* journal. An empty journal
renders empty states and no ledger rows, review fields or R curve, so it checked the page's chrome and none of
its content.

## Phase 2 — bilingual model prose

Phase 1 leaves the analysis prose in Vietnamese, marked, with the reason stated on the page: translating an
analysis would change it. The weakness is real and is the reason phase 2 should follow: an English reader gets
the conclusions (verdict chips, ladder, meta strip) in English while the *reasoning and the invalidation
condition* stay in Vietnamese, and a reader in a hurry reads only the part they can read. The mitigation today
is that the machine-derived basis behind the bias chip **is** bilingual from phase 1, so the reasoning is not
wholly inaccessible.

Phase 2, in one change:

- `scripts/local-eval-brief.py` rule 6 requires per-method blocks in both languages
  (`<div class="m-ict" lang="en">…</div><div class="m-ict" lang="vi">…</div>`), and rule 5 requires both.
- `scripts/check-model-prose.py` validates the new shape; `build-artifact.py`'s `dữ liệu tới (\d\d:\d\d) UTC`
  regex moves to a language-neutral marker. These three files form one contract and move together.
- `docs/architecture/schemas/narrative.schema.json`: `text_html` / `synthesis_html` / `lookback_html` /
  `headline` / `timeline[].event` become `{en, vi}`; `schema_version` bumps; the reader still accepts a bare
  string so old snapshots keep building.
- `method_purity` runs on both language blocks at the gate.
- `scripts/ict-scan.py` emits its anchor verdict as a key plus parameters instead of a composed Vietnamese
  string (a `facts.json` format change, which is why it is here and not in phase 1).
- The journal's review fields get an optional second-language field; unfilled shows an honest empty state.
- The phase-1 "authored in Vietnamese" marking is removed per page as its prose gains both languages.
