#!/usr/bin/env python3
"""Render a chart artifact page from code (user decisions 2026-09-11: overview window, volume on the Wyckoff chart,
layers 1/2/3 each split per method then synthesised, one method = one vocabulary, trader-grade UI).

Usage: build-artifact.py <style> --out FILE [--snapshot-dir DIR] [--narrative PATH] [--check-only] [--allow-impure]
  style: scalping | day | swing | cfd-scalping | cfd-day | cfd-swing   (three horizons x two markets;
         the names are derived in scripts/automation.py from HORIZON_TF -- crypto bare, cfd prefixed)

Inputs (all read-only here; each has exactly one writer elsewhere):
  data/live/market-data|mt5-bridge/ohlcv.<SYM>.<tf>.json   working window AND the context (HTF) window   (launchd scanner / MT5 EA)
  data/live/prelim/<style>.facts.json (+ .meta.json)         layer 1, đánh giá sơ bộ                       (scripts/ict-scan.py)
  data/live/prelim/<style>.<SYM>.model.html                  layer 2, đánh giá cục bộ, per-method blocks    (Sonnet local read)
  data/live/narrative/<style>.json                           layer 3, đánh giá toàn diện, structured        (Sonnet full analysis)
  data/live/anchors.<style>.json                             named levels the scanner compares against      (full analysis)
  docs/architecture/analysis-params.json                     project volume/spread parameters
  docs/architecture/automation-config.json                   which dimensions are switched on per market

Rules enforced here, not by convention:
  * numbers from code — every price/volume/% on the page is computed from the candle files or copied from facts.json;
    the models' prose is inserted verbatim and was already validated by scripts/check-model-prose.py;
  * one method, one vocabulary — every per-method block (layers 2 and 3, chart flag labels, timeline cells) is run
    through scripts/method_purity.py; any violation aborts the build (exit 2) unless --allow-impure;
  * events are addressed by candle time (ISO), never by array index, so a sliding window cannot detach a label.
Exit codes: 0 built, 1 usage/input error, 2 purity violation.
"""
import argparse, datetime, html, json, os, re, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from repo_paths import repo_rel
import method_purity as mp  # noqa: E402
import artifact_theme as theme  # noqa: E402
import instruments as I  # noqa: E402
import i18n  # noqa: E402
# CLAUDE.md §50: the page must expose 22 named things. Which 22, and which page owes which, is
# docs/architecture/ui-fields.json read through scripts/ui_contract.py -- and every value below comes from the
# registry that already owns it, never from a literal typed here. A page that says PERPETUAL because someone
# typed PERPETUAL is not exposing the market type, it is asserting it, and it keeps saying it after a change.
import ui_contract as UI  # noqa: E402
import providers as P  # noqa: E402
import sessions as SESS  # noqa: E402
import event_risk as ER  # noqa: E402
import account_profile as AP  # noqa: E402
import quality as Q  # noqa: E402
import trading_system as TS  # noqa: E402
import trading_env  # noqa: E402

# Every user-facing string on this page comes from docs/architecture/i18n.json through scripts/i18n.py, and every
# fragment is rendered once per locale into `lang`-tagged siblings (i18n.dual); one CSS rule shows one. There is
# deliberately NO "build in language X" mode -- one artifact URL serves both languages, so a build flag could
# publish a monolingual page to a URL whose readers expect the toggle.
#
# The rule that keeps this safe: dual() wraps CONTENT, never STRUCTURE. The .matrix and .ladder grids place their
# cells with grid-template-columns, so duplicating a cell would add a column; duplicating what is inside one cannot.
T = i18n.t
DUAL = i18n.dual

# (short id for CSS/HTML ids, display name, price-format kind: "int" or "2" decimals) -- presentation-only;
# the symbol SET itself comes from instruments.py (single source of truth, SYSTEM-DESIGN.md §1), and the
# metadata itself now lives in the optional "display" block of instruments.json, never hand-kept here.
def _meta(sym):
    d = I.display(sym)
    return (sym, d["id"], d["label"], "int" if d["price_decimals"] == 0 else "2")


CRYPTO = [_meta(sym) for sym in I.analysis("crypto")]
# Feed semantics (which live directory, tick volume or traded volume, killzone weighting) come from
# instruments.py -- keyed by market, so a new symbol in an existing market needs no edit here.
# `MT5` is kept as a NAME because check-narrative.py:132 imports it from this module; it is now derived.
MT5 = {s for s in I.analysis() if I.is_tick_volume(s)}
TF_MIN = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "1H": 60, "2H": 120, "4H": 240, "1D": 1440, "1W": 10080}
# Per-timeframe window spec (bars, axis label, human horizon). Bar counts are project parameters (no source gives them;
# they only need to hold the previous day/week/month for the PDH/PWH/PMH reads, knowledge/ict/core-a.md §2.8).
# The third element is an i18n KEY, not a phrase: the window's human horizon is user-facing text and belongs in
# docs/architecture/i18n.json with every other string on the page.
TF_SPEC = {"1m": (360, "%H:%M", "horizon.6h"), "5m": (576, "%m-%d %H:%M", "horizon.48h"), "15m": (576, "%m-%d %H:%M", "horizon.6d"),
           "1H": (480, "%m-%d %H:%M", "horizon.20d"), "4H": (360, "%m-%d %H:%M", "horizon.60d"), "1D": (240, "%m-%d", "horizon.8mo"), "1W": (208, "%y-%m-%d", "horizon.4y")}
TF_LABEL = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1H", "4h": "4H", "1D": "1D", "1W": "1W"}   # automation spelling -> file spelling
TIER_KEY = {"bias": "tier.bias", "structure": "tier.structure", "entry": "tier.entry"}
TIER_ORDER = ("bias", "structure", "entry")


def tier_name(name, lang):
    return T(TIER_KEY[name], lang)


def horizon(spec, lang):
    """'15m × 576 (6 days)' -- the timeframe and bar count are machine facts, only the horizon phrase translates."""
    return f'{spec["tf"]} × {spec["n"]} ({T(spec["hz"], lang)})'
import importlib.util as _iu
_as = _iu.spec_from_file_location("automation", os.path.join(ROOT, "scripts", "automation.py")); _auto = _iu.module_from_spec(_as); _as.loader.exec_module(_auto)
_ms = _iu.spec_from_file_location("methods", os.path.join(ROOT, "scripts", "methods.py")); _methods = _iu.module_from_spec(_ms); _ms.loader.exec_module(_methods)


def _style(tf, syms, name, kz):
    n, lbl, hz = TF_SPEC[tf]
    return dict(tf=tf, n=n, lbl=lbl, syms=syms, name=name, hz=hz, kz=kz)


# The three tiers of every style come from ONE table: scripts/automation.py TIERS (docs/architecture/timeframe-mapping.md).
#
# The style names themselves are derived from automation.STYLE rather than listed here. They were listed -- six
# rows -- which is why adding a market meant editing this table, artifacts.json, local-eval-brief.py and
# scan-loop.sh by hand and hoping all four agreed. Now only the per-market symbol set and human label are
# authored, and both are validated against the registry below.
MARKET_LABEL = {"crypto": "Crypto", "cfd": "CFD", "forex": "Forex"}
# Which symbols a market's pages may draw: the ANALYSIS ALLOWLIST, per market, with no second list anywhere.
#
# `cfd` was a hand-written `[_meta("XAUUSD")]` with a comment explaining that the MT5 EA exports only symbols
# with an attached chart. That comment stopped being true: a silver chart is attached, XAGUSD has 600 live bars
# in every timeframe, and automation-config lists it under markets.cfd.instruments -- and the page silently
# drew gold alone. Silently is the whole problem. §6 requires an unavailable source to be EXPOSED with its
# reason, and a hardcoded list cannot become unavailable, so there was nothing to expose: available analysis
# was suppressed by a literal. Found 2026-09-18 by looking at the built page in a browser.
#
# What replaces it is not "draw everything" either -- USOIL and UKOIL are analysable and have no export at all.
# `drawable()` below splits the allowlist into what has candles and what does not, and the page NAMES the
# second group instead of dropping it (§6, §15: let the rest continue, say why the rest is not there).
STYLE_SYMS = {m: [_meta(s) for s in I.analysis(m)] for m in _auto.MARKETS}
if set(MARKET_LABEL) != set(_auto.MARKETS) or set(STYLE_SYMS) != set(_auto.MARKETS):
    raise KeyError(f"build-artifact: markets are {sorted(_auto.MARKETS)} but this file knows labels for "
                   f"{sorted(MARKET_LABEL)} and symbols for {sorted(STYLE_SYMS)} -- a market with neither "
                   f"would silently have no page at all.")
STYLES = {}
for _m in _auto.MARKETS:
    for _h in _auto.HORIZONS:
        _atf = _auto.HORIZON_TF[_h]
        _ftf = TF_LABEL[_atf]
        STYLES[_auto.STYLE[(_m, _atf)]] = _style(_ftf, STYLE_SYMS[_m], f"{MARKET_LABEL[_m]} {_h.capitalize()}",
                                                 _ftf != "4H")
for _st, _S in STYLES.items():
    _S["tiers"] = {}
    for _name in ("bias", "structure"):
        _t = _auto.TIERS[_st].get(_name)
        if _t:
            _tf = TF_LABEL[_t["tf"]]; _n, _lbl, _hz = TF_SPEC[_tf]
            _S["tiers"][_name] = dict(tf=_tf, n=_n, lbl=_lbl, style=_t["style"], hz=_hz)
        else:
            _S["tiers"][_name] = None
# Verdict / stance values are MACHINE VALUES and stay Vietnamese everywhere they are stored or matched:
# narrative.schema.json pins the four-value enum, ict-scan.py writes `stance` from the same vocabulary,
# check-narrative.py and check-model-prose.py validate against it, and htf_context.DIRECTION maps it to a
# direction. Translating them in storage would change decision plumbing, not presentation. This table keeps
# doing exactly what it always did -- prefix-match the stored string to pick a CSS class -- and the LABEL is
# looked up separately, per locale, in i18n.json.
VERDICT_CLASS = [("SETUP", "setup"), ("THEO DÕI LONG", "long"), ("THEO DÕI SHORT", "short"), ("PHÁ", "warn"), ("CHỜ", "wait")]
import htf_context as htf  # noqa: E402
LANES = [(d, v["label"]) for d, v in _methods.DIMENSIONS.items()]   # source: docs/architecture/methods.json
# Chart-rendering fact scripts/chart.js needs but methods.json does not own (which lanes have a shape-drawing
# engine on the price chart at all). Kept here, injected into __PARAMS__, so chart.js has exactly one place
# to read it instead of hand-keeping its own copy (Task 10b item 4).
#
# Derived from `dimensions.<d>.overlay_engine` (plan docs/plans/2026-09-18-close-feature-gaps.md §0.7), not a
# hand-kept wyckoff/ict literal pair -- that pair used to be typed out in SIX places in this file (here plus
# anchor_method, timeline, ladder, and two `bias_methods`/cols sites), and a 5th dimension gaining an engine
# would have needed all six edited by hand, with nothing failing the build if one was missed.
OVERLAY_LANES = tuple(d for d, _ in LANES if _methods.DIMENSIONS[d].get("overlay_engine"))
# The second pane (under the price chart) per dimension: docs/architecture/methods.json `pane` (kind + label)
# is THE source -- not a second hand-kept lane list. chart.js renders by kind (volume | range_pct |
# unavailable); a 5th dimension needs only a registry entry here plus one render branch there.
PANES = {d: _methods.DIMENSIONS[d]["pane"] for d, _ in LANES}


# ----------------------------------------------------------------------------------------------- helpers
def esc(s):
    return html.escape(str(s), quote=True)


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


# ---- displayed time -------------------------------------------------------------------------------------
# The display zone follows the language (EN -> UTC, VI -> VNT/UTC+7, docs/architecture/i18n.json `locales`).
# This is PRESENTATION ONLY. Nothing here touches a stored time, a candle time, a decision time, or the
# IANA-zone killzone computation in chart.js -- those follow the real exchange zone per date and keep their DST.
#
# EVERY displayed time carries its zone name, always. During phase 1 the model-authored prose still states its
# own times in UTC while the chrome may be reading VNT; a suffix on every code-rendered time is the only thing
# that keeps the two unambiguous on one page. There is no code path here that emits a bare clock time.
def hhmm(iso, lang=i18n.DEFAULT):
    """Clock time. i18n.clock appends the date when the zone shift crossed midnight -- a 23:00 UTC candle is
    06:00 VNT the next morning, and a bare '06:00 VNT' beside a headline dated the 17th is a real misread."""
    return i18n.clock(iso, lang)


def dmy(iso, lang=i18n.DEFAULT):
    d = i18n.shift(iso, lang)
    return f"{d.day}/{d.month}" if d else "—"


def when(iso, lang=i18n.DEFAULT):
    return i18n.stamp(iso, lang, "%-d/%-m %H:%M")


def utc_hhmm(s):
    """A clock time the MODEL wrote, which is UTC by its own contract (local-eval-brief.py rule 6) and arrives
    as a bare 'HH:MM' with no date to shift. It is labelled UTC in every language rather than silently adopting
    the reader's zone -- converting a time whose date we do not know would be a fabrication."""
    return f"{s} UTC" if s else "—"


def verdict_of(l1, l2):
    """(value, source_key) for the status chip -- and WHICH layer said it.

    Until 2026-09-19 this was `l2.verdict or l1.verdict or "—"`, and l1's verdict is always absent: the
    scanner writes `stance`, never `verdict`. So the scanner's reading -- which exists for EVERY instrument --
    was dropped, and six of nine symbols showed an em-dash. An em-dash reads as "nothing is known"; the truth
    was "the scanner looked, the answer is WAIT, and no local read exists yet". CLAUDE.md §20 is explicit that
    a known state must not be presented as an unknown one, and this was the safe direction of that mistake,
    not an exemption from it.

    The source travels with the value because the two are not the same authority: a model's verdict is a
    judgement, the scanner's stance is a fixed rule. Showing both in one pill without saying which would be
    the confusion §50 warns about, so the caller renders the source beside the chip rather than hiding it.
    """
    if (l2 or {}).get("verdict"):
        return l2["verdict"], "status.src.model"
    if (l1 or {}).get("verdict"):
        return l1["verdict"], "status.src.scanner"
    if (l1 or {}).get("stance"):
        return l1["stance"], "status.src.scanner"
    return "—", "status.src.none"


def model_sub(l2, newest_iso, lang):
    """The local row's sub-line: the clock time the model quoted, WHEN it wrote that, and how far behind the
    page's own candles it is.

    The middle part is the one that was missing. A model read states a bare 'HH:MM' and nothing else, so an
    eight-day-old verdict rendered beside today's charts read as today's -- found 2026-09-19 while answering
    "why do only three symbols have a status". The age is computed against the newest candle ON THIS PAGE, not
    against the wall clock, so a page rebuilt from older data does not accuse itself of being stale.
    """
    out = T("matrix.sub.model_at", lang, time=utc_hhmm(l2.get("ts")))
    w = l2.get("written")
    if not w:
        return out
    out += " · " + T("matrix.sub.model_written", lang, when=w[:10])
    try:
        days = (datetime.date.fromisoformat(newest_iso[:10]) - datetime.date.fromisoformat(w[:10])).days
    except (TypeError, ValueError):
        return out
    if days >= 1:
        out += ' · <b class="stale">' + T("matrix.sub.model_stale", lang, days=days) + "</b>"
    return out


def label(iso, fmt, lang=i18n.DEFAULT):
    d = i18n.shift(iso, lang)
    return d.strftime(fmt)


def range_label(first, last, fmt, lang):
    """A chart title's window, '09-01 00:00 → 10-30 20:00 UTC'.

    The zone name goes on the END of the pair rather than on each half: both ends are in the same zone, and
    saying it twice reads as noise. It is not optional -- these two timestamps shift with the language, and a
    shifted range with no zone on it is exactly the ambiguity every other time helper here exists to prevent.
    """
    return f"{label(first, fmt, lang)} → {label(last, fmt, lang)} {i18n.tz_of(lang)[0]}"


def fmtn(v, kind):
    """One number formatter for the whole project — scripts/i18n.py num(), beside the locale records that
    declare it. Kept as a name here because the page code reads better with it."""
    return i18n.num(v, kind)


def verdict_class(text):
    """CSS class from the STORED value. The matching is untouched by localization, on purpose."""
    for k, c in VERDICT_CLASS:
        if str(text).upper().startswith(k):
            return c
    return "wait"


def verdict_label(text, lang):
    """Display label for a stored verdict/stance value.

    The closed vocabulary (the narrative enum plus the scanner's stance and anchor keys) has entries in
    i18n.json. A COMPOSED anchor verdict -- ict-scan.py builds strings like "PHÁ TRÊN AR — xác nhận tiếp diễn
    tăng" -- has none, so it falls through to the stored text and is marked as Vietnamese by the caller. Fixing
    that at the source means teaching the scanner to emit a key plus parameters; that is a facts.json format
    change and it belongs with the phase-2 work, not here.
    """
    key = f"verdict.{str(text).strip()}"
    return T(key, lang) if i18n.has(key) else None


def chip(text, extra=""):
    """A verdict pill. The pill itself carries the .chip classes and is NOT the locale wrapper -- a wrapper is
    `display: contents` when active, which would dissolve the pill's own box.

    Three cases, because "not in the catalog" is not one thing:
      * a known verdict/stance -> the display label, per locale;
      * the em-dash placeholder ("no verdict yet") -> punctuation, not prose, and certainly not Vietnamese;
      * a COMPOSED anchor verdict from ict-scan.py -> authored prose, shown verbatim and marked.
    The middle case used to fall into the third, so an empty chip wore the "Vietnamese source" underline.
    """
    cls = f'chip chip-{verdict_class(text)}{(" " + extra) if extra else ""}'
    label = verdict_label(text, i18n.DEFAULT)
    if label is not None:
        body = DUAL(lambda l: esc(verdict_label(text, l)))
    elif str(text).strip() in ("—", "-", ""):
        body = i18n.tx("ui.dash")
    else:
        body = vi_source(esc(text))
    return f'<span class="{cls}">{body}</span>'


def _series_path(sym, tf):
    return f"{ROOT}/data/live/{I.data_dir(sym)}/ohlcv.{sym}.{tf}.json"


def drawable(syms, tf):
    """Split a market's allowlist into (drawn, absent) by whether the entry timeframe has candles at all.

    CLAUDE.md §6: an unavailable source must be exposed with its reason, not disappeared. §15: unrelated
    analysis continues when it can. So a symbol with no export is NAMED on the page rather than dropped -- and
    the build still refuses outright when NOTHING has data, because a page with no chart on it is not a page,
    it is a misleading blank. That is the state every fx- style is in today.
    """
    drawn = [m for m in syms if os.path.exists(_series_path(m[0], tf))]
    absent = [m for m in syms if m not in drawn]
    return drawn, absent


def candles(sym, tf, n, snap=None):
    src = _series_path(sym, tf)
    if not os.path.exists(src):
        # A missing candle file is a MISSING SOURCE, not a crash. It raised FileNotFoundError with a traceback,
        # which reads like a broken script; it is usually one of two ordinary states, and the operator needs to
        # be told which. On the MT5 bridge the EA only exports a symbol that has a chart attached, so every
        # forex style is in exactly this position until a chart is opened per pair.
        how = ("the MT5 EA (integrations/mt5/ExportOHLCV.mq5) only exports a symbol that has a CHART ATTACHED "
               "in MetaTrader -- open one for this symbol, keep the terminal running, then rebuild"
               if I.data_dir(sym) == "mt5-bridge" else
               "the launchd scanner (scripts/scan-loop.sh) writes these -- check /automation status")
        # Exit 1, deliberately NOT 2: exit 2 means one thing in this script -- a method-purity violation --
        # and the publish tick reads it that way. A missing source is a different fact and must not wear
        # the same code.
        sys.exit(f"no data for {sym} {tf}: {repo_rel(src, ROOT)} does not exist.\n"
                 f"  {how}.\n"
                 f"  Nothing is wrong with the page: a chart drawn from no candles would be a fabrication.")
    d = json.load(open(src, encoding="utf-8"))
    if snap:
        os.makedirs(snap, exist_ok=True)
        shutil.copy(src, os.path.join(snap, f"ohlcv.{sym}.{tf}.json"))
    return d["candles"][-n:], d.get("last_updated"), d.get("_source")


def quality_of(sym, tf):
    """§20's state for the series this page draws, from the one assessor (scripts/quality.py).

    The page already knew a file existed and when it was last written; neither is a quality state. `assess`
    reads the whole file -- structural faults, holes in a continuous series, an age measured against the
    timeframe -- and returns the same six-state vocabulary the Decision Engine gates on, so the page and the
    order path cannot disagree about whether a series is usable.
    """
    src = _series_path(sym, tf)
    d = read_json(src, None)
    return Q.assess(d, tf, symbol=sym)


PLAN_FIELDS = ("id", "direction", "entry", "stop_loss", "targets", "planned_rr", "status", "rehearsal_mode", "date_opened", "setup_type", "expectations")


def trade_plans(sym):
    """PLANNED / OPEN trade records for this instrument from trades/index.jsonl (the derived rollup, never hand-edited —
    SYSTEM-DESIGN §5). Read-only: the chart draws entry/stop/targets, it never writes a trade."""
    out = []
    try:
        with open(f"{ROOT}/trades/index.jsonl", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                if r.get("instrument") == sym and r.get("status") in ("PLANNED", "OPEN"):
                    out.append({k: r.get(k) for k in PLAN_FIELDS})
    except FileNotFoundError:
        pass
    return out


def rows_js(rows, fmt):
    """One candle per row: [open, high, low, close, volume, isoUTC]. scripts/chart.js reads these positions.

    A seventh field used to lead each row -- a Python-formatted time label -- that chart.js never read; it derived
    every time from the ISO at the end. On the scalping page that dead field was 178 KB, 13% of the whole page.
    It also could not survive this change: a pre-formatted label is formatted in ONE locale and one timezone, and
    the page now has two of each. The times are derived client-side from the ISO, which is locale-free.
    """
    return "[" + ",".join(f'[{r["open"]},{r["high"]},{r["low"]},{r["close"]},{r.get("volume", 0)},"{r["time"]}"]' for r in rows) + "]"


# ----------------------------------------------------------------------------------------------- layer 1 (scanner facts -> per-method blocks, code-written)
def anchor_method(level):
    m = level.get("method")
    return m if m in OVERLAY_LANES else mp.infer_method(level.get("label", "") + " " + level.get("name", ""))


vi_source = i18n.vi_source   # authored-in-Vietnamese prose, shown verbatim and marked; see i18n.vi_source


def level_line(L, kind, lang):
    """One anchor level. Rendered into BOTH the Wyckoff and the ICT block, so its wording has to be legal in
    either: no liquidity words (forbidden in a Wyckoff block), no Wyckoff words (forbidden in an ICT block).
    scripts/method_purity.py checks the rendered result in every locale, so a careless translation fails the
    build rather than shipping."""
    fb = L.get("first_close_beyond")
    s = T("l1.level.close_vs", lang, label=vi_source(f'<b>{esc(L["label"])}</b>'), price=fmtn(L["price"], kind),
          time=when(L.get("time"), lang), side=T(f'side.{"above" if L["ref_vs"] == "above" else "below"}', lang),
          pct=f'{L["dist_pct"]:+.2f}%')
    if fb:
        s += T("l1.level.first_close", lang, time=when(fb["time"], lang), price=fmtn(fb["close"], kind),
               extreme=fmtn(L.get("extreme_since"), kind))
    if L.get("forming_beyond"):
        s += T("l1.level.forming", lang)
    return s


def dr_qualifier(src, lang=None):
    """A premium/discount read is only the decks' read when BOTH borders are real liquidity.

    knowledge/ict/core-a.md §2.18 (+ R15): the dealing range is "where sellside and buyside liquidity is
    resting" -- a BSL<->SSL pair. `scripts/ict-scan.py` already reports whether it found one (`dr_source`:
    pools | mixed | window), and on real XAUUSD/BTCUSDT history 52% of point-in-time reads are `mixed` (one
    border is the scan-window edge) -- so a bare "premium"/"discount" on this page was over-claiming the
    decks' term half the time. Added 2026-09-19 (knowledge audit).
    """
    key = {"mixed": "l1.dr.mixed", "window": "l1.dr.window"}.get(src)
    return T(key, lang) if key else ""


def layer1(sym, d, kind, tf):
    """facts.json symbol entry -> dict(ts, stance, verdict, wyckoff, ict, synth).

    Every block is built once per locale and the locales are wrapped as `lang` siblings. That has a second
    effect worth stating: build() feeds these blocks to scripts/method_purity.py, so the checker sees the
    concatenation of BOTH languages and an impure English translation aborts the build (exit 2) exactly the way
    an impure Vietnamese one always did. The English wording here was written against those term lists -- an
    ICT block may not say volume/effort/absorption/markup/trading range, a Wyckoff block may not say
    sweep/swept/liquidity/pools -- which is why some phrasings below are deliberately not the obvious ones.
    """
    an = d.get("anchors") or {}
    levels = an.get("levels") or []
    by = {"wyckoff": [], "ict": [], "mixed": [], "neutral": []}
    for L in levels:
        by[anchor_method(L)].append(L)
    vol = [e for e in d.get("events_recent", []) if e.get("kind") == "volume"]
    ev = [e for e in d.get("events_recent", []) if e.get("kind") in ("sweep", "erl_high", "erl_low", "mss_bull", "mss_bear")]
    m, g, su = d.get("last_mss"), d.get("nearest_fvg"), d.get("setup")
    up = d.get("unswept_pools") or []
    zone_term = "discount" if d["pct"] < 0.5 else "premium"   # ICT's own words, untranslated in either locale

    # ---- Wyckoff: named levels + volume outliers (effort)
    def wyckoff_ul(lang):
        w = [f"<li>{level_line(L, kind, lang)}</li>" for L in by["wyckoff"]]
        if vol:
            items = "; ".join(T("l1.wyckoff.vol_item", lang, mult=f"<b>{e['mult']}×</b>", time=hhmm(e["time"], lang),
                                dir=T("dir.up" if e["dir"] == "up" else "dir.down", lang)) for e in vol[-4:])
            w.append(f'<li>{T("l1.wyckoff.vol_recent", lang, items=items)}</li>')
        else:
            w.append(f'<li>{T("l1.wyckoff.vol_none", lang)}</li>')
        return "<ul>" + "".join(w) + "</ul>"

    # ---- ICT: range / EQ / MSS / FVG / pools / sweeps / setup
    def direction(flag, lang):
        """'bull'/'up' -> the locale's word. One helper, so a direction never gets spelled inline twice."""
        return T("dir.up" if flag else "dir.down", lang)

    def ict_ul(lang):
        # §2.18: only a BSL<->SSL pair is the decks' dealing range, so say it when a border is the window edge.
        zone = zone_term + dr_qualifier(d.get("dr_source"), lang)
        pct = f'<b>{d["pct"] * 100:.0f}%</b>'
        i = [f'<li>{T("l1.ict.range_pos", lang, price=fmtn(d["last"], kind), pct=pct, lo=fmtn(d["lo"], kind), hi=fmtn(d["hi"], kind), zone=f"<b>{zone}</b>", eq=fmtn(d["eq"], kind))}</li>']
        i += [f"<li>{level_line(L, kind, lang)}</li>" for L in by["ict"]]
        if m:
            mss_dir = f'<b>{direction(m["type"] == "bull", lang)}</b>'
            i.append(f'<li>{T("l1.ict.mss", lang, dir=mss_dir, level=fmtn(m["level"], kind))}</li>')
        if g:
            i.append(f'<li>{T("l1.ict.fvg", lang, dir=direction(g["type"] == "bull", lang), lo=fmtn(g["lo"], kind), hi=fmtn(g["hi"], kind))}</li>')
        else:
            i.append(f'<li>{T("l1.ict.fvg_none", lang)}</li>')
        if up:
            i.append(f'<li>{T("l1.ict.pools", lang, items=", ".join(f"{p['kind']} {fmtn(p['level'], kind)}" for p in up[-6:]))}</li>')
        if ev:
            def ev_s(e):
                at = hhmm(e["time"], lang)
                if e["kind"] == "sweep":
                    return T("l1.ict.ev.sweep", lang, pool=e["pool"], level=fmtn(e["level"], kind), time=at)
                if e["kind"].startswith("mss"):
                    return T("l1.ict.ev.mss", lang, dir=direction(e["kind"] == "mss_bull", lang),
                             level=fmtn(e["level"], kind), time=at)
                side = T("side.high" if e["kind"] == "erl_high" else "side.low", lang)
                return T("l1.ict.ev.erl", lang, side=side, level=fmtn(e["level"], kind), time=at)
            i.append(f'<li>{T("l1.ict.events", lang, items="; ".join(ev_s(e) for e in ev[-6:]))}</li>')
        if su and su.get("complete"):
            i.append("<li>" + T("l1.ict.setup.complete", lang, side=f"<b>{su['side'].upper()}</b>",
                                pool=su["sweep"]["pool"], sweep=fmtn(su["sweep"]["level"], kind), sweep_t=hhmm(su["sweep"]["time"], lang),
                                mss=fmtn(su["mss"]["level"], kind), mss_t=hhmm(su["mss"]["time"], lang),
                                fvg_lo=fmtn(su["fvg"]["lo"], kind), fvg_hi=fmtn(su["fvg"]["hi"], kind),
                                fvg_state=T("l1.ict.fvg_mitigated" if su["fvg"].get("mitigated") else "l1.ict.fvg_unmitigated", lang),
                                entry=fmtn(su["entry"], kind), stop=fmtn(su["stop"], kind), target=fmtn(su["target"], kind),
                                target_kind=esc(su.get("target_kind", "")), r=su["R"],
                                zone="discount" if su.get("in_discount") else "premium") + "</li>")
        elif su:
            i.append(f'<li>{T("l1.ict.setup.incomplete", lang, side=su["side"].upper(), missing=esc(su.get("missing")))}</li>')
        else:
            i.append(f'<li>{T("l1.ict.setup.none", lang)}</li>')
        return "<ul>" + "".join(i) + "</ul>"

    # ---- synthesis: rule verdict vs anchors + stance + mixed/neutral levels
    def synth_ul(lang):
        s = []
        if an.get("verdict"):
            rc = an.get("ref_close") or {}
            s.append(f'<li>{T("l1.synth.verdict_anchor", lang, verdict=anchor_verdict_html(an), time=when(rc.get("time"), lang), close=fmtn(rc.get("close"), kind))}</li>')
        else:
            s.append(f'<li>{T("l1.synth.no_anchor", lang)}</li>')
        for L in by["mixed"] + by["neutral"]:
            s.append(f'<li>{T("l1.synth.anchor_mixed", lang, line=level_line(L, kind, lang))}</li>')
        stance = esc(verdict_label(d["stance"], lang) or d["stance"])
        s.append(f'<li>{T("l1.synth.stance", lang, stance=f"<b>{stance}</b>")}</li>')
        return "<ul>" + "".join(s) + "</ul>"

    return dict(ts=d.get("last_time"), stance=d["stance"], verdict=(an.get("verdict_short") or an.get("verdict")),
                wyckoff=DUAL(wyckoff_ul), ict=DUAL(ict_ul), synth=DUAL(synth_ul), facts=d)


def anchor_verdict_html(an):
    """The scanner's anchor verdict as it reaches the page.

    ict-scan.py COMPOSES this string -- "PHÁ TRÊN AR — xác nhận tiếp diễn tăng" -- from a rule key plus a level
    label plus a Vietnamese tail, so there is no closed set to translate against. It is rendered verbatim and
    tagged as Vietnamese rather than guessed at. Teaching the scanner to emit its `verdict_key` plus parameters
    (the key is already there: above_res | below_sup | inside | hold) is the real fix and it changes the
    facts.json format, so it travels with the phase-2 work.
    """
    return vi_source(f'<b>{esc(an["verdict"])}</b>')


# ----------------------------------------------------------------------------------------------- layer 2 (Sonnet local read, per-method blocks)
BLOCK_RE = {m: re.compile(rf'<div class="m-{m}">(.*?)</div>\s*(?=<div class="m-|$)', re.S) for m in ("wyckoff", "ict", "footprint", "heatmap", "synth")}


# The four values a verdict may take. ONE source: the schema the layer-3 narrative is validated against
# (docs/architecture/schemas/narrative.schema.json). scripts/check-model-prose.py holds the same list for the
# layer-2 prose; both now point at the schema rather than each keeping a copy, so a fifth value cannot be
# accepted by one and rejected by the other.
def _verdict_vocab():
    d = read_json(f"{ROOT}/docs/architecture/schemas/narrative.schema.json") or {}
    found = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "verdict" and isinstance(v, dict) and isinstance(v.get("enum"), list):
                    found.append(v["enum"])
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    walk(d)
    if not found:
        raise SystemExit("docs/architecture/schemas/narrative.schema.json: no `verdict` enum -- refusing to "
                         "render verdicts against a vocabulary nobody declared")
    return tuple(found[0])


VERDICT_VOCAB = _verdict_vocab()


def layer2(style, sym):
    p = f"{ROOT}/data/live/prelim/{style}.{sym}.model.html"
    if not os.path.exists(p):
        return None
    h = open(p, encoding="utf-8").read()
    ts = re.search(r"dữ liệu tới (\d\d:\d\d) UTC", h)
    # ANCHORED to the head div and checked against the vocabulary, which is what scripts/check-model-prose.py
    # has always done (its VERDICTS tuple, its `prelim-head` regex). This read used a bare `<strong>` anywhere
    # in the document and validated nothing, so the two disagreed about what the verdict even IS: any bold
    # phrase that happened to come first became the page's verdict chip, and chip() renders an unrecognised
    # value verbatim rather than refusing it. Found 2026-09-19. The vocabulary now has ONE source, the schema
    # the layer-3 narrative is already held to, so a value the checker would reject cannot reach the page.
    vd = re.search(r'<div class="prelim-head">.*?<strong>([^<]+)</strong>', h, re.S)
    # WHEN this read was written. The model states only a bare 'HH:MM' with no date (utc_hhmm's docstring says
    # why the builder must not invent one), so on its own the page could show an eight-day-old verdict beside
    # today's candles and look current -- which is exactly what it was doing on 2026-09-19 (model files of
    # 09-11, charts of 09-19, and the row reading "data through 15:00 UTC"). The FILE's mtime is not an
    # invented date: it is when this artefact was produced, which is the fact a staleness notice needs.
    verdict = vd.group(1).strip() if vd else None
    if verdict is not None and verdict not in VERDICT_VOCAB:
        verdict = None          # not a verdict this system recognises -> no chip, rather than prose in a pill
    out = dict(ts=ts.group(1) if ts else None, verdict=verdict, legacy=False,
               written=datetime.datetime.fromtimestamp(os.path.getmtime(p), datetime.timezone.utc)
                               .strftime("%Y-%m-%dT%H:%M:%SZ"))
    body = re.sub(r'<div class="prelim-head">.*?</div>', "", h, count=1, flags=re.S)
    found = False
    for m, rx in BLOCK_RE.items():
        mm = rx.search(body)
        out[m] = mm.group(1).strip() if mm else ""
        found = found or bool(mm)
    if not found:          # pre-2026-09-11 flat prose: cannot be attributed to one method -> synthesis column, flagged
        out["legacy"] = True
        out["synth"] = body.strip()
    return out


# ----------------------------------------------------------------------------------------------- page pieces
def lane_status(engaged, reason):
    return "" if engaged else esc(reason)


def dim_notes(dims, lanes=None):
    """'<b>Wyckoff</b>: off in /automation' for every disengaged lane -- the reason is always stated, never
    silently dropped. The reason is a (key, params) pair so it can be said in either language."""
    lanes = lanes if lanes is not None else [m for m, _ in LANES]
    out = [(m, dims[m]["reason"]) for m in lanes if not dims.get(m, {}).get("engaged")]
    if not out:
        return ""
    return (f'<span{UI.attr("blocking-reason")}>'
            + DUAL(lambda l: " · ".join(f'<b>{dict(LANES)[m]}</b>: {esc(reason_text(r, l))}' for m, r in out))
            + '</span>')


def reason_text(reason, lang):
    """A dims reason travels as (key, params) so it can be rendered in any locale.

    A parameter may itself be per-locale -- the preset name is -- in which case it arrives as {locale: text} and
    the right one is picked HERE. Pre-rendering it at the call site would freeze one language's word into every
    language's sentence, which is the silent mixing this whole change exists to prevent.
    """
    key, params = reason
    return T(key, lang, **{k: (v[lang] if isinstance(v, dict) else v) for k, v in params.items()})


def matrix(sym_key, kind, l1, l2, l3, dims, newest=None, inv_at=None):
    """The read matrix: rows = layers, columns = methods engaged + synthesis.

    The grid places its cells with grid-template-columns, so the CELLS are never duplicated per locale -- only
    their contents are. Duplicating a cell would add a column.

    `inv_at` (P7.2 item 6, docs/audits/2026-09-24-wyckoff-label-review.md §7): when the scanner's own facts show
    the level closed beyond after `updated` (build-artifact.py invalidated_at()), the layer-3 verdict chip and
    structure badges render as a HISTORICAL read of that date, never as if it were still current -- the model's
    own prose stays untouched (CLAUDE.md §17), only the surrounding chrome says the read is dead.
    """
    # §15: the READ matrix shows every ANALYSED lane, not only the traded one -- "the system may continue
    # analyzing all available methodologies", and the user should "see methodology-specific analysis
    # independently" (§50). The ladder below is the decision grid and stays engaged-only; this is the
    # separation §50 asks for, not an inconsistency between the two.
    cols = [c for c, _ in LANES if dims.get(c, {}).get("analysed") or dims.get(c, {}).get("engaged")]
    if not cols:
        # No lane engaged for this market/config: an empty-columns matrix is a worse signal than none at all
        # (silently implies "nothing to see" rather than "nothing is turned on") -- say so explicitly instead.
        return f'<div class="matrix cols-0"><p class="muted">{i18n.tx("dims.none_on")}</p></div>'
    head = (f'<div class="mx-head mx-corner">{i18n.tx("matrix.head.layer")}</div>'
            + "".join(f'<div class="mx-head lane-{c}'
                      + ('' if dims.get(c, {}).get("engaged") else ' optional-lane')
                      + f'"><span class="lane-dot"></span>{dict(LANES)[c]}'
                      + ('' if dims.get(c, {}).get("engaged")
                         else f'<span class="mx-optional">{i18n.tx("matrix.head.optional")}</span>')
                      + '</div>' for c in cols)
            + f'<div class="mx-head mx-synth"{UI.attr("decision-explanation")}>{i18n.tx("matrix.head.synthesis")}</div>')

    def row(title, sub, cells, synth, cls=""):
        out = f'<div class="mx-label {cls}"><div class="mx-title">{title}</div><div class="mx-sub">{sub}</div></div>'
        for c in cols:
            out += f'<div class="mx-cell lane-{c} {cls}" data-col="{c}"><div class="mx-cell-tag">{dict(LANES)[c]}</div>{cells.get(c) or f"<p class=\"muted\">{i18n.tx('ui.dash')}</p>"}</div>'
        out += f'<div class="mx-cell mx-synth {cls}" data-col="synth"><div class="mx-cell-tag">{i18n.tx("matrix.head.synthesis")}</div>{synth}</div>'
        return out

    def muted(key, **p):
        return f'<p class="muted">{DUAL(lambda l: T(key, l, **p))}</p>'

    body = head
    # layer 1
    if l1:
        body += row(i18n.tx("matrix.row.prelim"),
                    DUAL(lambda l: T("matrix.sub.scanner_at", l, time=hhmm(l1["ts"], l))),
                    {"wyckoff": l1["wyckoff"], "ict": l1["ict"]},
                    f'<div class="cell-verdict">{chip(l1["verdict"] or l1["stance"])}</div>{l1["synth"]}')
    else:
        body += row(i18n.tx("matrix.row.prelim"), i18n.tx("matrix.sub.scanner"), {}, muted("matrix.empty.facts"))
    # layer 2. l2['ts'] is a clock time the MODEL wrote and is UTC by its own contract -- it is quoted, not
    # re-derived, so it keeps its own UTC label in every locale (utc_hhmm); re-rendering a quoted time in the
    # reader's zone would silently disagree with the prose two lines below it.
    if l2 and not l2["legacy"]:
        # Layer 2 is the model's own prose, every block of it -- shown as authored and marked, never translated.
        cells = {c: (vi_source(l2[c], block=True) if l2.get(c) else "") for c in cols}
        body += row(i18n.tx("matrix.row.local"), DUAL(lambda l: model_sub(l2, newest, l)),
                    cells, f'<div class="cell-verdict">{chip(l2["verdict"] or "—")}</div>{vi_source(l2["synth"], block=True) if l2.get("synth") else ""}')
    elif l2:
        body += row(i18n.tx("matrix.row.local"),
                    DUAL(lambda l: model_sub(l2, newest, l) + " · <em>" + T("matrix.sub.legacy_format", l) + "</em>"),
                    {}, f'<div class="cell-verdict">{chip(l2["verdict"] or "—")}</div>{vi_source(l2["synth"], block=True) if l2.get("synth") else ""}')
    else:
        body += row(i18n.tx("matrix.row.local"), i18n.tx("matrix.sub.model"), {}, muted("matrix.empty.local"))
    # layer 3
    if l3:
        wy = l3.get("wyckoff") or {}
        ic = l3.get("ict") or {}
        tr = wy.get("trading_range") or {}
        wcell = ""
        # structure/regime are model words with a bounded vocabulary, so they get a display map; the phase is a
        # letter A-E and the TR border labels are method acronyms (AR, SC) -- both locale-invariant.
        badges = [b for b in (structure_badge(wy.get("structure")),
                              (DUAL(lambda l: T("l3.phase", l, phase=wy["phase"])) if wy.get("phase") else None),
                              structure_badge(wy.get("regime"))) if b]
        if inv_at and badges:
            # P7.2 item 6: "(11/09, hết hiệu lực)" -- the structure badges stay, marked as a historical read.
            badges = [b + " " + DUAL(lambda l: T("l3.invalidated_badge", l, date=dmy(inv_at["time"], l))) for b in badges]
        if badges:
            wcell += '<div class="badges">' + "".join(f'<span class="badge">{b}</span>' for b in badges) + "</div>"
        if tr:
            hi_l = esc(tr["high_label"]) if tr.get("high_label") else i18n.tx("l3.tr.high")
            lo_l = esc(tr["low_label"]) if tr.get("low_label") else i18n.tx("l3.tr.low")
            wcell += f'<p class="kv"><span>{hi_l}</span><b>{fmtn(tr.get("high"), kind)}</b><span>{lo_l}</span><b>{fmtn(tr.get("low"), kind)}</b></p>'
        wcell += vi_source(wy["text_html"], block=True) if wy.get("text_html") else ""
        icell = ""
        lv = ic.get("levels") or []
        if lv:
            # The level LABEL is written by the full analysis ("BSL chưa quét phía trên vùng hiện tại"); the
            # price beside it is computed. Only the label is authored prose.
            icell += '<p class="kv">' + "".join(f"<span>{vi_source(esc(L.get('label', '')))}</span><b>{fmtn(L.get('price'), kind)}</b>" for L in lv[:6]) + "</p>"
        icell += vi_source(ic["text_html"], block=True) if ic.get("text_html") else ""
        cells = {"wyckoff": wcell, "ict": icell}
        for m in ("footprint", "heatmap"):
            if dims[m]["engaged"] or dims[m].get("analysed"):
                txt = (l3.get(m) or {}).get("text_html", "")
                cells[m] = vi_source(txt, block=True) if txt else ""
        inv = l3.get("invalidation") or {}
        # P7.2 item 6: once invalidated_at exists, the layer-3 verdict chip renders as the HISTORICAL verdict --
        # struck through, with "đã vô hiệu <date>" beside it -- rather than silently looking current; "the
        # current state comes from the scanner (verdict_of), which already says PHÁ DƯỚI" (§7). The chip's own
        # text (the model's verdict word) is untouched, per CLAUDE.md §17 -- only the wrapper marks it historical.
        chip_html = f'<s>{chip(l3.get("verdict") or "—")}</s>' if inv_at else chip(l3.get("verdict") or "—")
        synth = f'<div class="cell-verdict">{chip_html}'
        if inv_at:
            synth += f' <span class="inv invalidated-chip">{DUAL(lambda l: T("l3.invalidated_chip", l, date=when(inv_at["time"], l)))}</span>'
        if inv:
            # `rule` is model prose ("đóng cửa dưới"); `owner` is a dimension id, locale-invariant.
            synth += (f' <span class="inv">{DUAL(lambda l: T("l3.invalidation", l, rule=vi_source(esc(inv.get("rule", ""))), level=fmtn(inv.get("level"), kind), owner=f"<b>{esc(inv.get("owner", "?"))}</b>"))}</span>')
        synth += "</div>"
        if l3.get("lookback_html"):
            synth += f'<div class="sub-h">{i18n.tx("l3.lookback")}</div>{vi_source(l3["lookback_html"], block=True)}'
        synth += f'<div class="sub-h">{i18n.tx("l3.now")}</div>'
        synth += vi_source(l3["synthesis_html"], block=True) if l3.get("synthesis_html") else ""
        body += row(i18n.tx("matrix.row.full"),
                    DUAL(lambda l: T("matrix.sub.full_at", l, when=when(l3.get("_updated_iso"), l))), cells, synth)
    else:
        body += row(i18n.tx("matrix.row.full"), i18n.tx("matrix.sub.full"), {}, muted("matrix.empty.full"))
    notes = dim_notes(dims)
    return f'<div class="matrix cols-{len(cols)}">{body}</div>' + (f'<div class="mx-foot">{notes}</div>' if notes else "")


def structure_badge(word):
    """A Wyckoff structure/regime word from the narrative. The vocabulary is bounded -- htf_context.py:51-52
    already treats it as an enum when it decides bias direction -- so it gets a display map. A word outside the
    map is shown verbatim and marked as Vietnamese rather than guessed at."""
    if not word:
        return None
    key = f"structure.{str(word).strip().lower()}"
    if i18n.has(key):
        return DUAL(lambda l: esc(T(key, l)))
    return vi_source(esc(word))


def timeline(rows, dims):
    """`dims` gates the Wyckoff/ICT columns the same way matrix() does (Task 10) -- a disengaged method's column
    is dropped and the reason stated, not silently rendered anyway. This table arrived with the timeframe-ladder
    work (716b32a) after the Task 10 matrix()-only sweep, so it never got that treatment; ladder() had the same gap."""
    if not rows:
        return ""
    # §15: the timeline is a record of what the analysis SAW, so it follows the analysed set like the matrix.
    cols = [m for m, _ in LANES
            if m in OVERLAY_LANES and (dims.get(m, {}).get("analysed") or dims.get(m, {}).get("engaged"))]
    if not cols:
        return ""
    head_cells = "".join(f'<th class="lane-{m}">{dict(LANES)[m]}</th>' for m in cols)
    # Event text and per-method cells are model prose; the time column is a model-written string too, so it
    # keeps the analysis's own UTC labelling rather than being re-derived into the reader's zone.
    trs = "".join("<tr><td>{}</td><td>{}</td>{}</tr>".format(
        esc(r.get('time', '')), vi_source(r.get('event', '')) if r.get('event') else '',
        "".join(f'<td class="lane-{m}">{vi_source(r[m], block=True) if r.get(m) else ""}</td>' for m in cols)) for r in rows)
    names = [dict(LANES)[m] for m in cols]
    notes = dim_notes(dims, list(OVERLAY_LANES))
    summary = DUAL(lambda l: T("timeline.summary", l) + ' <span class="muted">('
                   + T("timeline.count", l, n=len(rows), lanes=T("timeline.lanes_one" if len(names) == 1 else "timeline.lanes_many", l, names=" / ".join(names)))
                   + ")</span>")
    # The locale wrappers go INSIDE each <th>. A <span> between <tr> and <th> is invalid table markup and the
    # browser hoists it out of the table entirely -- the same reason cells are never duplicated in matrix().
    head = f'<th>{i18n.tx("timeline.col.time")}</th><th>{i18n.tx("timeline.col.event")}</th>'
    return (f'<details class="timeline"{UI.attr("expected-path")}><summary>{summary}</summary>'
            f'<div class="table-wrap"><table class="evidence"><thead><tr>{head}{head_cells}</tr></thead><tbody>{trs}</tbody></table></div>'
            + (f'<div class="ld-foot">{notes}</div>' if notes else "") + "</details>")


# Which terms each lane's glossary lists, in order. The TEXT lives in docs/architecture/i18n.json under
# `gloss.<lane>.<id>.t` (term) and `.d` (definition) -- this file holds the structure, never the copy.
#
# The English definitions were written against scripts/method_purity.py's term lists, which are bilingual: a
# Wyckoff definition may not reach for "sweep" (the Vietnamese says "cú xuyên", not "quét", for exactly the same
# reason), and an ICT definition may not reach for "volume", "effort" or "trading range". The build gate does not
# currently check the glossary -- scripts/tests/test_i18n.py does, which is why these definitions are held to the
# same standard as the layer-1 blocks that the gate does check.
GLOSSARY = {
    "wyckoff": ["phase_a_events", "spring", "phase_d_events", "distribution_events", "chobev", "effort_result", "phases"],
    "ict": ["liquidity", "sweep_mss", "displacement_fvg", "order_block", "cisd", "dealing_range", "prev_levels", "ote_std", "killzone"],
    "footprint": ["poc_imbalance", "absorption_seq", "delta"],
    "heatmap": ["liq_cluster", "ob_wall"],
}


def _kv(marker, label_key, value_html, detail=None):
    """One labelled cell of the context strip, carrying the §50 marker the checker looks for."""
    d = f'<div class="ctx-d">{detail}</div>' if detail else ""
    return (f'<div class="ctx-kv"><div class="ctx-l">{i18n.tx(label_key)}</div>'
            f'<div class="ctx-v"{UI.attr(marker)}>{value_html}</div>{d}</div>')


def context_strip(style, market, S, lane_engaged, lane_analysed, dim_flags, syms_quality, now_iso):
    """CLAUDE.md §50 -- the twelve things the chart page did not say out loud.

    Every value is read from the registry that owns it (`ui-fields.json` names which, per field); nothing here
    is a literal. Two of them matter more than the rest:

    * **Execution venue next to data provider.** §4: Data Source != Execution Venue. Both were true of this
      system and neither was on the page, so a reader could not tell that the crypto page draws Binance SPOT
      candles while the pilot trades a PERPETUAL on the futures testnet. The market-type cell prints both for
      the same reason -- collapsing them to one word hides the §20.1 divergence that is on record.
    * **Required vs optional analysis.** §50 asks for them to be visually distinguishable and §62 says why:
      only REQUIRED_FOR_DECISION may gate an entry. The split is computed by `trading_system.classification()`
      over the lanes this page actually engaged -- the same call the order path makes -- so the page cannot
      show one split while the runner uses another.

    Event risk and data quality are point-in-time values on a static page, so both carry their own as-of
    stamp. An event-risk claim with no as-of is a claim about *now* made by a file written hours ago, which is
    §20's "never silently convert STALE to FRESH" happening on a screen instead of in a gate.
    """
    name_of = lambda ms: (" · ".join(dict(LANES).get(m, m) for m in ms)) if ms else i18n.tx("ctx.none")
    md = P.for_role("market_data", market)
    prov = md[0] if md else None
    try:
        venue = P.unattended_venue_for(market)
    except ValueError:
        venue = None
    exec_pids = [p for p in P.for_role("execution", market) if P.PROVIDERS[p]["unattended"]]
    exec_pid = exec_pids[0] if len(exec_pids) == 1 else None
    analysis_mt = P.data_market_type(prov) if prov else "UNKNOWN"
    exec_mt = P.market_type_of(exec_pid) if exec_pid else None

    cells = [_kv("market", "ctx.market", f'<span class="mono">{esc(market)}</span>')]
    mt = (DUAL(lambda l: T("ctx.market_type_split", l, analysis=esc(analysis_mt), execution=esc(exec_mt)))
          if exec_mt and exec_mt != analysis_mt else f'<span class="mono">{esc(analysis_mt)}</span>')
    cells.append(_kv("market-type", "ctx.market_type", mt))
    cells.append(_kv("data-provider", "ctx.data_provider",
                     f'<span class="mono">{esc(prov or i18n.tx("ui.dash"))}</span>',
                     detail=esc(P.status_of(prov)) if prov else None))
    cells.append(_kv("source-venue", "ctx.source_venue",
                     f'<span class="mono">{esc(P.venue_of(prov) if prov else "?")}</span>'))
    cells.append(_kv("execution-venue", "ctx.execution_venue",
                     (f'<span class="mono">{esc(exec_pid)}</span>' if exec_pid
                      else i18n.tx("ctx.execution_none")),
                     detail=(f'<span class="mono">{esc(venue)}</span>' if venue else None)))

    # §21: the session is a first-class domain concept and the page is read inside one.
    now = datetime.datetime.strptime(now_iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    act = SESS.active(now)
    sess = " + ".join(act) if act else SESS.OFF
    cells.append(_kv("session", "ctx.session", f'<span class="mono">{esc(sess)}</span>',
                     detail=DUAL(lambda l: T("ctx.asof", l, time=hhmm(now_iso, l)))))

    # §20, over the candles this page is actually drawing -- not "a file was found".
    worst = "UNKNOWN"
    for st in ("INVALID", "MISSING", "PARTIAL", "STALE", "UNKNOWN", "FRESH"):
        if st in set(syms_quality.values()):
            worst = st
            break
    detail = " · ".join(f'{s.split("USD")[0]} {q}' for s, q in sorted(syms_quality.items()))
    cells.append(_kv("data-quality", "ctx.data_quality", f'<span class="mono">{esc(worst)}</span>',
                     detail=esc(detail)))

    # §24-§32 on a static page: point-in-time, and it says so.
    states = {}
    for sym, _k, _d, _kind in S["syms"]:
        try:
            st, why, _ev = ER.state(sym, at=now, decision_time=now)
        except Exception as e:                                        # noqa: BLE001 -- see below
            st, why = "UNKNOWN", str(e)
        states[sym] = (st, why)
    blocked = [s for s, (st, _w) in states.items() if st != "CLEAR"]
    er_v = (DUAL(lambda l: T("ctx.event_risk_blocked", l)) + " " +
            f'<span class="mono">{esc(", ".join(blocked))}</span>') if blocked else i18n.tx("ctx.event_risk_clear")
    cells.append(_kv("event-risk", "ctx.event_risk", er_v,
                     detail=DUAL(lambda l: T("ctx.asof", l, time=hhmm(now_iso, l)))))

    # §33 + §34: which account's rules an order on this market would obey, and the one risk ceiling.
    prof_id, risk_pct = None, trading_env.MAX_RISK_PCT
    if venue:
        try:
            prof = AP.for_venue(venue, "demo")
            prof_id = prof["id"]
            risk_pct = AP.effective_risk_pct(prof)
        except ValueError:
            prof_id = None
    cells.append(_kv("account-profile", "ctx.account_profile",
                     f'<span class="mono">{esc(prof_id)}</span>' if prof_id else i18n.tx("ctx.none")))
    cells.append(_kv("risk", "ctx.risk",
                     DUAL(lambda l: T("ctx.risk_value", l, pct=f"{risk_pct * 100:g}"))))

    # §15/§50: the ACTIVE selection and the AVAILABLE analysis are two different answers and the page owes
    # both. The topbar's lane buttons are a control listing all four; naming them "active methodology" would be
    # the global-analysis-filter confusion §15 spends a section refusing.
    engaged = [m for m, _ in LANES if lane_engaged.get(m)]
    analysed = [m for m, _ in LANES if lane_analysed.get(m) or lane_engaged.get(m)]
    cells.append(_kv("active-methodology", "ctx.active_methodology",
                     name_of(engaged), detail=DUAL(lambda l: preset_label(dim_flags, market, l))))
    cells.append(_kv("available-methodologies", "ctx.available_methodologies", name_of(analysed)))

    # §35/§62: only REQUIRED_FOR_DECISION may gate. Same call the order path makes.
    try:
        cls = TS.classification(style, engaged=engaged)
    except Exception:                                                 # noqa: BLE001
        cls = {}
    req = sorted({d.split(".", 1)[1] for d, r in cls.items()
                  if r == TS.REQUIRED and d.startswith("methodology.")})
    opt = sorted({d.split(".", 1)[1] for d, r in cls.items()
                  if r != TS.REQUIRED and d.startswith("methodology.")})
    cells.append(f'<div class="ctx-kv ui-req"><div class="ctx-l">{i18n.tx("ctx.required")}</div>'
                 f'<div class="ctx-v"{UI.attr("required-analysis")}>{name_of(req)}</div>'
                 f'<div class="ctx-d">{i18n.tx("ctx.required_note")}</div></div>')
    cells.append(f'<div class="ctx-kv ui-opt"><div class="ctx-l">{i18n.tx("ctx.optional")}</div>'
                 f'<div class="ctx-v"{UI.attr("optional-analysis")}>{name_of(opt)}</div></div>')

    return (f'<section class="ctx" id="sec-context"><div class="ctx-head"><h2>{i18n.tx("ctx.title")}</h2>'
            f'<p class="muted">{i18n.tx("ctx.note")}</p></div>'
            f'<div class="ctx-grid">{"".join(cells)}</div></section>')


def lane_buttons(engaged):
    """Topbar lane toggle buttons. `engaged` is {lane: bool} -- the real dims state (Task 10b item 3; before
    this every lane except wyckoff/ict was hardcoded 'off' regardless of whether it was actually on)."""
    return "".join(
        f'<button class="lane-btn lane-{k}{"" if engaged.get(k) else " off"}" data-lane="{k}" '
        f'onclick="setLane(\'{k}\')" {i18n.attr("title", "lane.key_hint", n=i + 1)}>'
        f'<span class="lane-dot"></span>{n}</button>'
        for i, (k, n) in enumerate(LANES))


def method_clause(engaged, lang):
    """The "read with <methods>" half of the page lede, built from the lanes actually engaged on this page.

    One engaged method gets neither "separately" nor "then synthesised": there is nothing to hold apart and no
    synthesis step to perform. Until 2026-09-17 this whole clause was a plain string literal naming both
    structural methods, so every ICT-only page -- which is what markets.crypto.dimensions has said since
    2026-09-12 -- told its reader that two methods had been read separately and then synthesised. The glosses
    come from methods.json `reads`; a second copy here is exactly how the first version went stale."""
    on = [m for m, _ in LANES if engaged.get(m)]
    if not on:
        return T("lede.no_method", lang)
    named = [f'{_methods.DIMENSIONS[m]["label"]} ({_methods.text(m, "reads", lang)})' for m in on]
    if len(named) == 1:
        return T("lede.read_with_one", lang, method=named[0])
    return T("lede.read_with_many", lang, methods=", ".join(named[:-1]), last=named[-1])


def _configured_flags(dim_flags, market):
    """The four booleans the config actually means for this market. Two conventions have to be reconciled:
    build()'s dims loop treats an ABSENT flag as ON (`flag is not False`) whereas methods.profile_of reads
    plain truthiness, so an absent key would silently invert; and a dimension the market cannot have at all
    (no CoinGlass source outside crypto) is off regardless of what the flag says."""
    have = set(_methods.dimensions(market))
    return {d: (d in have and dim_flags.get(d) is not False) for d in _methods.ALL_DIMENSIONS}


def preset_id(dim_flags, market):
    """The CONFIGURED preset's id, or None when the flag set matches no named preset. Configuration, not
    per-symbol availability. Split out from preset_label so callers that want the IDENTITY (tests, logic) do not
    have to go through a display string that now varies by locale."""
    p = _methods.preset(_methods.profile_of(_configured_flags(dim_flags, market)))
    return p["id"] if p else None


def preset_label(dim_flags, market, lang):
    """The CONFIGURED preset's name for the footer's mode line. Falls back to naming the engaged dimensions --
    those are proper nouns (Wyckoff, ICT) and read the same in every language."""
    flags = _configured_flags(dim_flags, market)
    p = _methods.preset(_methods.profile_of(flags))
    if p:
        return _methods.preset_text(p, "label", lang)
    return " + ".join(_methods.DIMENSIONS[d]["label"] for d in _methods.ALL_DIMENSIONS if flags[d]) or T("dims.none_configured", lang)


def preset_mode(dim_flags, market):
    """The mode the CONFIGURED preset resolves to, via methods.mode_of -- which that function's own docstring
    calls the only place allowed to decide a run is SOLO, and a pure function of the preset id.

    The footer used to pair the narrative's recorded `mode` with a hard-coded "Wyckoff + ICT", and once the
    config went ICT-only it printed "NORMAL: ICT" -- self-contradictory, since NORMAL means a minimum of two
    engaged dimensions (methods.json modes). Pairing the preset's name with the preset's own mode cannot
    contradict itself; where the last full analysis ran under a different mode, build() says so separately
    rather than overwriting one with the other."""
    return _methods.mode_of(_methods.profile_of(_configured_flags(dim_flags, market)))


def no_live_source(engaged, market):
    """The dimensions this market CAN have, is not showing, and whose only feed is CoinGlass -- named, so the
    footer reports the real gap. The previous footer asserted the same two names unconditionally, which would
    have been wrong in both directions once CoinGlass is wired or a Footprint-only preset is selected."""
    off = [_methods.DIMENSIONS[m]["label"] for m, _ in LANES
           if market in _methods.DIMENSIONS[m]["markets"] and not engaged.get(m)
           and not _methods.live_sourced(m, market)]
    if not off:
        return ""
    return DUAL(lambda l: T("dims.no_live_source_named", l, names=" · ".join(off)))


def glossary(engaged):
    """Terminology for the engaged lanes only. It used to walk all of LANES, so an ICT-only page shipped the
    full Wyckoff, Footprint and Heatmap term lists -- vocabulary for three methods it had not read.

    <dt>/<dd> are the locale wrappers' parents, never their children: a <span> between <dl> and <dt> is invalid
    markup and the browser hoists it out of the list, the same trap as table headers."""
    out = ""
    for key, name in LANES:
        if not engaged.get(key):
            continue
        items = "".join(f'<dt>{i18n.tx(f"gloss.{key}.{g}.t")}</dt><dd>{i18n.tx(f"gloss.{key}.{g}.d")}</dd>'
                        for g in GLOSSARY[key])
        out += f'<div class="gl lane-{key}"><div class="gl-head"><span class="lane-dot"></span>{name}</div><dl>{items}</dl></div>'
    if not out:
        out = f'<div class="gl"><div class="gl-head">—</div><dl><dd>{i18n.tx("gloss.none_on")}</dd></dl></div>'
    return (f'<section class="glossary" id="sec-glossary"><details><summary>{i18n.tx("gloss.summary")} '
            f'<span class="muted">({i18n.tx("gloss.open_hint")})</span></summary><div class="gl-grid">{out}</div></details></section>')


def invalidated_at(n3, fsym):
    """P7.1 (docs/audits/2026-09-24-wyckoff-label-review.md §7): derive the invalidation time from the
    scanner's own facts -- never store it in the narrative, and never let a close at or before the narrative's
    own `updated` invalidate it (CLAUDE.md §8 point-in-time: the label was valid when it was written).

    `n3["invalidation"]["level"]` is matched by PRICE against `fsym["anchors"]["levels"][*]["price"]` (the
    scanner's own anchor list, data/live/prelim/<style>.facts.json symbols.<SYM>.anchors.levels) -- that anchor's
    own `first_close_beyond` (scripts/ict-scan.py anchor_facts(), first COMPLETED close beyond the level,
    `ref_i = n-2` never lets the forming candle confirm a break) is the invalidation time, when it exists and
    postdates `updated`. Returns {"time", "close"} or None (not invalidated, or nothing to compare)."""
    inv = (n3 or {}).get("invalidation") or {}
    level = inv.get("level")
    updated = (n3 or {}).get("_updated_iso")
    if level is None or not updated:
        return None
    for L in ((fsym or {}).get("anchors") or {}).get("levels", []) or []:
        if L.get("price") == level:
            fcb = L.get("first_close_beyond")
            if fcb and fcb.get("time") and fcb["time"] > updated:
                return {"time": fcb["time"], "close": fcb.get("close")}
            return None
    return None


def wy_json(wy):
    """Narrative wyckoff -> the chart overlay (TR, events, phases), addressed by candle time.
    `status` (P6.2, docs/audits/2026-09-24-wyckoff-label-review.md) rides through so chart.js can draw a
    'hypothesis' band differently from a 'tested' one (WA p166: do not label mechanically)."""
    tr = (wy or {}).get("trading_range") or None
    return dict(tr=(dict(high=tr.get("high"), low=tr.get("low"), high_label=tr.get("high_label", "AR"), low_label=tr.get("low_label", "SC")) | {"from": tr.get("from")} if tr else None),
                events=[dict(time=e.get("time"), label=e.get("label", ""), up=bool(e.get("up"))) for e in (wy or {}).get("events", [])],
                phases=[{"from": p.get("from"), "to": p.get("to"), "label": p.get("label", ""), "status": p.get("status")} for p in (wy or {}).get("phases", [])])


BIAS_CLS = {"long": "long", "short": "short", "neutral": "wait", "unknown": "wait"}
BIAS_KEY = {"long": "bias.long", "short": "bias.short", "neutral": "bias.neutral", "unknown": "bias.unknown"}


def ladder(S, sym, kind, cur_verdict, l1, n3, tier_ctx, gate_name, dims):
    """Three rows, top-down: Bias -> Structure -> Entry. Each row answers ONE question per method (Wyckoff: structure +
    phase + TR; ICT: dealing-range position + last MSS) and ends in one conclusion chip. Wording for a missing rung is
    printed, never skipped (docs/architecture/timeframe-mapping.md). `dims` gates the method columns the same way
    matrix() does (Task 10): a disengaged method's column is dropped and the reason stated, never silently rendered
    anyway. ladder() arrived with the timeframe-ladder work (716b32a) after the Task 10 matrix()-only sweep, so it
    never got that treatment until now.

    Like matrix(), this is a CSS grid: the cells are placed by grid-template-columns and are never duplicated per
    locale -- only their contents are.
    """
    tfmin = lambda tf: TF_MIN.get(tf, 0)
    ratio = lambda hi, lo: (f"×{tfmin(hi) / tfmin(lo):g}" if tfmin(hi) and tfmin(lo) else "")
    cols = [m for m, _ in LANES if m in OVERLAY_LANES and dims.get(m, {}).get("engaged")]
    if not cols:
        return f'<div class="ladder cols-0"><p class="muted">{i18n.tx("dims.none_on")}</p></div>'

    def muted(key, **p):
        return f'<span class="muted">{DUAL(lambda l: T(key, l, **p))}</span>'

    def wy_cell(w):
        if not w or not (w.get("structure") or w.get("phase")):
            return muted("ladder.no_wyckoff_read")
        tr = w.get("trading_range") or {}
        out = f'<b>{structure_badge(w.get("structure")) or i18n.tx("structure.chưa xác lập")}</b>'
        if w.get("phase"):
            out += " · " + DUAL(lambda l: T("l3.phase", l, phase=f'<b>{esc(w["phase"])}</b>'))
        if tr.get("high") is not None and tr.get("low") is not None:
            # TR border labels are method acronyms (SC, AR) -- locale-invariant.
            out += (f'<div class="ld-kv">{esc(tr.get("low_label", "SC"))} {fmtn(tr["low"], kind)} – '
                    f'{esc(tr.get("high_label", "AR"))} {fmtn(tr["high"], kind)}</div>')
        if w.get("updated"):
            out += f'<div class="ld-kv muted">{DUAL(lambda l: T("ladder.read_at", l, time=when(str(w["updated"])[:19] + "Z", l)))}</div>'
        return out

    def ict_cell(f):
        if not f or f.get("pct") is None:
            return muted("ladder.not_scanned")
        zone_term = "discount" if f["pct"] < 0.5 else "premium"
        zone = f'{zone_term}{DUAL(lambda l: dr_qualifier(f.get("dr_source"), l))}'
        out = f'<b>{f["pct"] * 100:.0f}%</b> dealing range ({fmtn(f.get("lo"), kind)}–{fmtn(f.get("hi"), kind)}) · <b>{zone}</b>'
        m = f.get("last_mss")
        if m:
            out += f'<div class="ld-kv">{DUAL(lambda l: T("ladder.last_mss", l, dir=T("dir.up" if m.get("type") == "bull" else "dir.down", l), level=fmtn(m.get("level"), kind)))}</div>'
        else:
            out += f'<div class="ld-kv muted">{i18n.tx("ladder.no_mss")}</div>'
        return out

    rows = []
    for name in ("bias", "structure"):
        t = S["tiers"].get(name); c = tier_ctx.get(name)
        below = S["tiers"]["structure"]["tf"] if (name == "bias" and S["tiers"].get("structure")) else S["tf"]
        if not t:
            cells = {"wyckoff": muted("ladder.no_slower_tf"), "ict": muted("ui.dash")}
            rows.append((name, "—", "", cells, f'<span class="chip chip-wait">{i18n.tx("ui.dash")}</span>', False))
            continue
        head = f'{t["tf"]} <span class="ld-ratio">{ratio(t["tf"], below)}</span>'
        if not t["style"]:
            cells = {"wyckoff": muted("ladder.chart_only"), "ict": muted("ladder.no_numbers")}
            rows.append((name, head, i18n.tx("ladder.chart_only_sub"), cells, f'<span class="chip chip-wait">{i18n.tx("ui.dash")}</span>', False))
            continue
        if c:
            # `basis` is a (key, params) pair from htf_context, so the tooltip can be said in either language.
            # The tooltip attribute itself cannot carry lang siblings -- the shim swaps it (data-i18n-attr).
            chipv = (f'<span class="chip chip-{BIAS_CLS.get(c["bias"], "wait")} chip-lg" '
                     f'{basis_attr(c.get("basis"))}>{i18n.tx(BIAS_KEY.get(c["bias"], "bias.unknown"))}</span>')
        else:
            chipv = f'<span class="chip chip-wait">{i18n.tx("ladder.not_scanned")}</span>'
        cells = {"wyckoff": wy_cell(c and c.get("wyckoff")), "ict": ict_cell(c)}
        sub = DUAL(lambda l: T("ladder.updated", l, time=hhmm(c.get("last_time"), l) if c else "—"))
        rows.append((name, head, sub, cells, chipv, name == gate_name))
    wy = (n3 or {}).get("wyckoff") or {}
    entry_cells = {"wyckoff": wy_cell({**wy, "updated": (n3 or {}).get("_updated_iso")} if wy else None), "ict": ict_cell(l1 and l1.get("facts"))}
    entry_sub = DUAL(lambda l: T("ladder.updated", l, time=hhmm(l1["ts"], l) if l1 else "—"))
    rows.append(("entry", S["tf"], entry_sub, entry_cells, chip(cur_verdict, "chip-lg"), False))
    body = (f'<div class="ld-head ld-corner">{i18n.tx("ladder.head.tier")}</div>'
            + "".join(f'<div class="ld-head lane-{m}"><span class="lane-dot"></span>{dict(LANES)[m]}</div>' for m in cols)
            + f'<div class="ld-head">{i18n.tx("ladder.head.conclusion")}</div>')
    for name, head, sub, cells, ch, is_gate in rows:
        g = " gate" if is_gate else ""
        body += (f'<div class="ld-tier{g}"><div class="ld-name">{i18n.tx(TIER_KEY[name])}</div><div class="ld-tf">{head}</div><div class="ld-sub">{sub}</div></div>'
                 + "".join(f'<div class="ld-cell lane-{m}{g}">{cells.get(m, "")}</div>' for m in cols)
                 + f'<div class="ld-cell ld-verdict{g}">{ch}'
                 + (f'<div class="ld-sub">{i18n.tx("ladder.gate_note")}</div>' if is_gate else '') + '</div>')
    notes = dim_notes(dims, list(OVERLAY_LANES))
    return f'<div class="ladder cols-{len(cols)}"{UI.attr("setup")}>{body}</div>' + (f'<div class="ld-foot">{notes}</div>' if notes else "")


def zoom_buttons(full=False):
    """The chart's zoom / ruler / replay controls. Their labels are symbols (− + ⟲ ▶ R:R) -- locale-invariant;
    only the tooltips translate, and those go through i18n.attr because an attribute cannot carry siblings."""
    b = (f'<button data-z="out" {i18n.attr("title", "chart.zoom.out")}>−</button>'
         f'<button data-z="in" {i18n.attr("title", "chart.zoom.in")}>+</button>'
         f'<button data-z="reset" {i18n.attr("title", "chart.zoom.reset")}>⟲</button>')
    if full:
        b += (f'<button data-z="ruler" class="wide" {i18n.attr("title", "chart.ruler")}>R:R</button>'
              f'<button data-z="replay" class="wide" {i18n.attr("title", "chart.replay")}>▶</button>')
    return b


def basis_attr(basis):
    """The bias chip's tooltip. htf_context returns `basis` as (key, params) -- the reason the higher timeframe
    allows this direction -- so it can be said in either language. An attribute cannot carry lang siblings, so
    the default locale goes in `title` (correct with JavaScript off) and the shim swaps it on toggle."""
    if not basis:
        return ""
    return i18n.attr_all("title", {l: htf.basis_text(basis, l) for l in i18n.LOCALES})


# ----------------------------------------------------------------------------------------------- CSS / JS
CSS = r"""
<style>
__TOKENS__
__I18N__
*{box-sizing:border-box}
html{scroll-behavior:smooth}
@media (prefers-reduced-motion: reduce){ html{scroll-behavior:auto} *{transition:none!important} }
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:14px;line-height:1.55;-webkit-font-smoothing:antialiased}
a{color:var(--accent)}
b,strong{font-weight:700}
.muted{color:var(--muted)}
.mono{font-family:var(--mono)}
.num{font-family:var(--mono);font-variant-numeric:tabular-nums}
.lane-wyckoff{--lane:var(--w);--lane-soft:var(--w-soft)} .lane-ict{--lane:var(--i);--lane-soft:var(--i-soft)}
.lane-footprint{--lane:var(--f);--lane-soft:var(--f-soft)} .lane-heatmap{--lane:var(--h);--lane-soft:var(--h-soft)}
.lane-dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--lane);margin-right:7px;vertical-align:1px}

/* top bar */
.topbar{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--surface) 92%,transparent);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
.topbar-in{max-width:1180px;margin:0 auto;padding:10px 20px;display:flex;align-items:center;gap:18px;flex-wrap:wrap}
.brand{display:flex;flex-direction:column;gap:1px;min-width:220px}
.brand-title{font-weight:800;font-size:15px;letter-spacing:-.01em}
.brand-sub{font-family:var(--mono);font-size:11px;color:var(--muted)}
.symnav{display:flex;gap:4px}
.symnav a{font-family:var(--mono);font-size:12px;font-weight:700;text-decoration:none;color:var(--ink-2);padding:6px 10px;border-radius:6px;border:1px solid transparent}
.symnav a:hover{background:var(--surface-2);border-color:var(--line)}
.lanes{display:flex;gap:2px;margin-left:auto;background:var(--surface-2);border:1px solid var(--line);border-radius:8px;padding:3px}
.lane-btn{font-family:var(--sans);font-weight:700;font-size:12.5px;padding:6px 12px;border-radius:6px;border:1px solid transparent;background:transparent;color:var(--muted);cursor:pointer;display:inline-flex;align-items:center;gap:7px}
.lane-btn .lane-dot{margin:0}
.lane-btn:hover{color:var(--ink)}
.lane-btn.active{background:var(--surface);color:var(--ink);border-color:var(--line-strong);box-shadow:0 1px 2px rgba(0,0,0,.08)}
.lane-btn:focus-visible,.symnav a:focus-visible,summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.lane-btn.off{opacity:.55}

.page{max-width:1180px;margin:0 auto;padding:22px 20px 80px;display:flex;flex-direction:column;gap:22px}
.lede{display:flex;justify-content:space-between;gap:24px;align-items:flex-end;flex-wrap:wrap}
h1{font-size:clamp(22px,3vw,30px);font-weight:800;letter-spacing:-.02em;margin:0;text-wrap:balance}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0 0 6px}
.lede p{margin:6px 0 0;color:var(--ink-2);max-width:66ch}
.disclaimer{font-family:var(--mono);font-size:11px;color:var(--warn);background:var(--warn-soft);padding:6px 10px;border-radius:6px;white-space:nowrap}

/* CLAUDE.md §50 context strip. `ui-req` and `ui-opt` are the two classes docs/architecture/ui-fields.json
   names as `distinguishable_by`, and the loader refuses them being equal: §50 asks that required analysis be
   visually distinguishable from optional, and rendering them identically implies every displayed lane counts
   toward the trade. Required gets the accent rule and full-strength ink; optional is muted and says so. */
.ctx{margin:18px 0}
.ctx-head h2{font-size:15px;margin:0 0 2px} .ctx-head p{margin:0 0 10px;font-size:12px}
.ctx-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));border:1px solid var(--line);border-radius:10px;background:var(--surface);overflow:hidden}
.ctx-kv{padding:10px 14px;border-right:1px solid var(--line);border-bottom:1px solid var(--line)}
.ctx-l{font-family:var(--mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);margin-bottom:3px}
.ctx-v{font-weight:650;font-size:13px}
.ctx-d{font-size:11px;color:var(--faint);margin-top:3px}
.ctx-kv.ui-req{grid-column:1/-1;border-left:3px solid var(--accent,var(--up));background:color-mix(in srgb,var(--surface) 88%,var(--accent,var(--up)) 12%)}
.ctx-kv.ui-req .ctx-v{font-weight:800}
.ctx-kv.ui-opt{grid-column:1/-1;border-left:3px dashed var(--line)}
.ctx-kv.ui-opt .ctx-l,.ctx-kv.ui-opt .ctx-v{color:var(--faint);font-weight:500}
.meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));border:1px solid var(--line);border-radius:10px;background:var(--surface);overflow:hidden}
.meta > div{padding:12px 16px;border-right:1px solid var(--line)}
.meta > div:last-child{border-right:0}
.meta-l{font-family:var(--mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);margin-bottom:4px}
.meta-v{font-weight:700;font-size:13.5px}
.meta-d{font-family:var(--mono);font-size:11.5px;color:var(--muted);margin-top:2px}
.meta .chip{margin:0 0 0 4px}
.meta .st{display:inline-flex;align-items:center;white-space:nowrap;margin:2px 10px 2px 0}

section.symbol{background:var(--surface);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);padding:18px 20px 20px;display:flex;flex-direction:column;gap:14px;scroll-margin-top:64px}
.sym-head{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.sym-name{font-family:var(--mono);font-weight:800;font-size:20px;letter-spacing:-.01em}
.sym-last{font-family:var(--mono);font-size:20px;font-variant-numeric:tabular-nums}
.sym-kv{display:flex;gap:16px;font-family:var(--mono);font-size:12px;color:var(--muted);flex-wrap:wrap}
.sym-kv b{color:var(--ink-2);font-weight:600}
.sym-verdict{margin-left:auto;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.sym-verdict .lbl{font-family:var(--mono);font-size:11px;color:var(--faint)}

/* timeframe ladder: three tiers, top-down, one question per method per tier */
.ladder{display:grid;grid-template-columns:150px repeat(var(--n),minmax(0,1fr)) 150px;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--surface)}
.ladder.cols-1{--n:1} .ladder.cols-2{--n:2}
.ld-head{padding:8px 14px;font-family:var(--mono);font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2);background:var(--surface-3);border-bottom:1px solid var(--line);border-left:1px solid var(--line)}
.ld-head.lane-wyckoff,.ld-head.lane-ict{box-shadow:inset 0 -2px 0 var(--lane)} .ld-corner{border-left:0;color:var(--faint)}
.ld-tier{padding:10px 14px;border-top:1px solid var(--line);background:var(--surface-2)}
.ld-name{font-weight:800;font-size:13px} .ld-tf{font-family:var(--mono);font-size:12.5px;color:var(--ink-2);margin-top:1px} .ld-sub{font-family:var(--mono);font-size:10.5px;color:var(--faint);margin-top:2px}
.ld-ratio{font-family:var(--mono);font-size:10.5px;color:var(--faint);font-weight:400}
.ld-cell{padding:10px 14px;border-top:1px solid var(--line);border-left:1px solid var(--line);font-size:12.5px;line-height:1.45}
.ld-cell.lane-wyckoff,.ld-cell.lane-ict{box-shadow:inset 3px 0 0 var(--lane-soft)}
.ld-kv{font-family:var(--mono);font-size:11.5px;color:var(--ink-2);margin-top:3px}
.ld-verdict{display:flex;flex-direction:column;gap:4px;align-items:flex-start;justify-content:center}
.ld-tier.gate,.ld-cell.gate{background:color-mix(in srgb,var(--accent) 6%,var(--surface))}
.ld-tier.gate{box-shadow:inset 3px 0 0 var(--accent)}
.meta-ladder{grid-column:span 2} .ld-step b{font-family:var(--mono)} .ld-arrow{color:var(--faint);margin:0 2px}
.chart-missing .lane-status{padding:14px 16px}
.glossary summary{cursor:pointer;font-weight:800;font-size:15px;margin-bottom:10px}

.chip{display:inline-flex;align-items:center;font-family:var(--mono);font-size:11px;font-weight:700;letter-spacing:.03em;padding:3px 9px;border-radius:999px;border:1px solid transparent;white-space:nowrap}
.chip-wait{background:var(--surface-3);color:var(--ink-2);border-color:var(--line-strong)}
.chip-long{background:var(--up-soft);color:var(--up);border-color:var(--up)}
.chip-short{background:var(--down-soft);color:var(--down);border-color:var(--down)}
.chip-setup{background:var(--w-soft);color:var(--w);border-color:var(--w)}
.chip-warn{background:var(--warn-soft);color:var(--warn);border-color:var(--warn)}
.chip-lg{font-size:12.5px;padding:5px 12px}

.charts{display:flex;flex-direction:column;gap:8px}
.chart-block{border:1px solid var(--line);border-radius:8px;background:var(--surface-2);position:relative}
.chart-title{display:flex;justify-content:space-between;align-items:center;padding:8px 12px 0;font-family:var(--mono);font-size:11px;color:var(--muted)}
.chart-title b{color:var(--ink-2);font-weight:600}
.zoom{display:inline-flex;align-items:center;gap:4px} .zoom .muted{margin-right:6px}
.zoom button{font-family:var(--mono);font-size:12px;font-weight:700;width:24px;height:22px;border-radius:5px;border:1px solid var(--line-strong);background:var(--surface);color:var(--ink-2);cursor:pointer;line-height:1}
.zoom button:hover{background:var(--surface-3)} .zoom button:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.chart-wrap{padding:4px 6px 4px;position:relative}
.chart{display:block;width:100%;height:440px;cursor:crosshair}
.mode-status{padding:4px 12px 8px;font-family:var(--mono);font-size:11px;color:var(--accent)}
.mode-ruler .chart,.mode-replay .chart{outline:1px dashed var(--accent);outline-offset:-1px}
.zoom button.wide{width:auto;padding:0 6px}
.sw.plan{background:linear-gradient(90deg,var(--down-soft),var(--up-soft));border:1px solid var(--line-strong)}
.axis-label{font-family:var(--mono);font-size:9.5px;fill:var(--faint)}
.flag-label{font-family:var(--mono);font-size:10px;font-weight:700;fill:var(--ink)}
.flag-w{fill:var(--w)} .flag-i{fill:var(--i)}
.range-label{font-family:var(--mono);font-size:9.5px;font-weight:700}
.phase-label{font-family:var(--mono);font-size:10px;font-weight:800;fill:var(--w)}
.tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--line-strong);border-radius:6px;padding:6px 9px;font-family:var(--mono);font-size:11px;color:var(--ink);box-shadow:var(--shadow);display:none;z-index:5;white-space:nowrap;line-height:1.5}
.tip .t{color:var(--muted)} .tip .u{color:var(--up)} .tip .d{color:var(--down)}
.lane-status{padding:22px 16px;font-size:13px;color:var(--muted);display:flex;gap:12px;align-items:center}
.lane-status[hidden],.legend[hidden]{display:none}
.lane-status b{color:var(--ink-2)}
.legend{display:flex;gap:16px;align-items:center;font-family:var(--mono);font-size:11px;color:var(--muted);flex-wrap:wrap;padding:0 4px}
.legend > span{display:inline-flex;align-items:center;gap:6px}
.sw{display:inline-block;width:14px;height:8px;border-radius:2px}
.sw.up{border:2px solid var(--up);background:transparent;height:6px} .sw.down{background:var(--down)}
.sw.vol{background:var(--muted);opacity:.5} .sw.volhi{background:var(--w)}
.sw.tr{height:0;border-top:2px dashed var(--w)} .sw.ph{background:var(--w);opacity:.18;height:10px}
.sw.fvgb{background:var(--up);opacity:.35} .sw.fvgs{background:var(--down);opacity:.35} .sw.ob{background:var(--i);opacity:.35}
.sw.liq{height:0;border-top:2px dotted var(--i)} .sw.eq{height:0;border-top:2px dashed var(--i)} .sw.kz{background:var(--i);opacity:.12;height:10px} .sw.lvl{height:0;border-top:2px dashed var(--ink-2)} .sw.cisd{height:0;border-top:2px dashed var(--up)}
.sw.win{background:var(--accent);opacity:.14;height:10px}

/* read matrix */
.matrix{display:grid;grid-template-columns:128px repeat(var(--n),minmax(0,1fr)) minmax(0,1.15fr);border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--surface)}
.matrix.cols-1{--n:1} .matrix.cols-2{--n:2} .matrix.cols-3{--n:3} .matrix.cols-4{--n:4}
.mx-head{padding:9px 14px;font-family:var(--mono);font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2);background:var(--surface-3);border-bottom:1px solid var(--line);border-left:1px solid var(--line)}
.mx-head.lane-wyckoff,.mx-head.lane-ict,.mx-head.lane-footprint,.mx-head.lane-heatmap{box-shadow:inset 0 -2px 0 var(--lane)}
/* CLAUDE.md §50: "Required analysis should be visually distinguishable from optional analysis" and "Do not
   visually imply that all displayed analysis contributes to trading confluence." A lane the active system does
   not trade keeps its own colour (it is still that methodology's read) but loses the solid underline that marks
   a decision lane, and says so in words -- colour alone would not carry the distinction. */
.mx-head.optional-lane{box-shadow:inset 0 -2px 0 transparent;border-bottom:1px dashed var(--line-strong)}
.mx-optional{display:block;font-size:9.5px;font-weight:600;letter-spacing:.04em;text-transform:none;color:var(--faint);margin-top:2px}
.mx-corner{border-left:0;color:var(--faint)}
.mx-label{padding:12px 14px;border-top:1px solid var(--line);background:var(--surface-2)}
.mx-title{font-weight:800;font-size:13px}
.mx-sub{font-family:var(--mono);font-size:10.5px;color:var(--muted);margin-top:3px;line-height:1.4}
.mx-cell{padding:12px 14px;border-top:1px solid var(--line);border-left:1px solid var(--line);font-size:13px;min-width:0;transition:background .15s}
.mx-cell-tag{display:none;font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--lane,var(--faint));margin-bottom:6px}
.mx-cell ul{margin:0;padding-left:16px;display:flex;flex-direction:column;gap:5px}
.mx-cell p{margin:0 0 7px} .mx-cell p:last-child{margin-bottom:0}
.mx-cell .cite,.mx-cell .cite *{font-family:var(--mono);font-size:10px;color:var(--faint)}
.mx-cell .cite{display:inline;margin-left:4px;overflow-wrap:anywhere}
.mx-synth{background:color-mix(in srgb,var(--surface-2) 60%,var(--surface))}
body[data-lane="wyckoff"] .mx-cell.lane-wyckoff,body[data-lane="ict"] .mx-cell.lane-ict,body[data-lane="footprint"] .mx-cell.lane-footprint,body[data-lane="heatmap"] .mx-cell.lane-heatmap{background:color-mix(in srgb,var(--lane-soft) 45%,var(--surface))}
.cell-verdict{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
.inv{font-family:var(--mono);font-size:11px;color:var(--muted)}
.sub-h{font-family:var(--mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--faint);margin:8px 0 4px}
.badges{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
.badge{font-family:var(--mono);font-size:10.5px;font-weight:700;padding:2px 8px;border-radius:5px;background:var(--lane-soft,var(--surface-3));color:var(--lane,var(--ink-2))}
.kv{display:grid;grid-template-columns:auto auto;gap:2px 10px;font-family:var(--mono);font-size:11.5px;color:var(--muted);margin:0 0 8px!important}
.kv b{color:var(--ink);font-variant-numeric:tabular-nums;text-align:right}
.mx-foot,.ld-foot{font-family:var(--mono);font-size:11px;color:var(--muted);padding:6px 4px 0}
.stale{color:var(--warn);background:var(--warn-soft);border-radius:4px;padding:1px 5px;font-weight:700}
.src{font-family:var(--mono);font-size:9.5px;color:var(--faint);margin-left:5px}

details.timeline{border:1px solid var(--line);border-radius:10px;background:var(--surface)}
details.timeline summary{cursor:pointer;padding:10px 14px;font-weight:700;font-size:13px}
details.timeline[open] summary{border-bottom:1px solid var(--line)}
.table-wrap{overflow-x:auto}
table.evidence{width:100%;border-collapse:collapse;font-size:12.5px}
table.evidence th,table.evidence td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--line);vertical-align:top}
table.evidence th{font-family:var(--mono);font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:var(--faint);font-weight:600;background:var(--surface-2)}
table.evidence th.lane-wyckoff,table.evidence th.lane-ict{color:var(--lane)}
table.evidence td:first-child{font-family:var(--mono);white-space:nowrap;color:var(--muted)}
table.evidence td .cite{display:block;font-family:var(--mono);font-size:10px;color:var(--faint);margin-top:3px;overflow-wrap:anywhere}

.glossary h2{font-size:15px;margin:0 0 10px}
.gl-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
.gl{border:1px solid var(--line);border-radius:10px;background:var(--surface);padding:12px 14px;border-top:3px solid var(--lane)}
.gl-head{font-weight:800;font-size:13px;margin-bottom:6px}
.gl dl{margin:0;font-size:12.5px} .gl dt{font-family:var(--mono);font-weight:700;font-size:11.5px;margin-top:8px} .gl dd{margin:2px 0 0;color:var(--ink-2)}

footer{font-family:var(--mono);font-size:11px;color:var(--faint);border-top:1px solid var(--line);padding-top:14px;line-height:1.7}
footer b{color:var(--muted);font-weight:600}

@media (max-width:900px){
  .matrix{grid-template-columns:1fr}
  .ladder{grid-template-columns:1fr} .ld-head{display:none} .ld-cell{border-left:0} .meta-ladder{grid-column:span 1}
  .mx-head{display:none}
  .mx-label{border-top:2px solid var(--line-strong)}
  .mx-cell{border-left:0}
  .mx-cell-tag{display:block}
  .disclaimer{white-space:normal}
  .lanes{margin-left:0}
}
</style>
"""

VENDOR_JS = os.path.join(ROOT, "scripts", "vendor", "lightweight-charts.standalone.production.js")
CHART_JS = os.path.join(ROOT, "scripts", "chart.js")


def js_block(data_json, params_json):
    """The page's script: the vendored TradingView Lightweight Charts (pinned, inlined — no CDN), then scripts/chart.js,
    then the data call. See docs/specs/2026-09-12-chart-lightweight-charts-design.md §1."""
    with open(VENDOR_JS, encoding="utf-8") as f:
        vendor = f.read()
    with open(CHART_JS, encoding="utf-8") as f:
        chart = f.read()
    return ("<script>\n" + vendor + "\n</script>\n<script>\n" + chart + "\n</script>\n"
            "<script>TChart.init(" + data_json + ", " + params_json + ");</script>\n")



# ----------------------------------------------------------------------------------------------- assembly
def build(style, out, snap=None, narrative_path=None, allow_impure=False, check_only=False):
    S = dict(STYLES[style])
    # §6/§15: draw every allowlisted symbol whose feed exists, name the ones whose feed does not, and refuse
    # only when none of them has data. `S` is copied first because STYLES is module state shared by every
    # build in the process -- narrowing it in place would leak one style's missing feeds into the next.
    S["syms"], S["absent"] = drawable(S["syms"], S["tf"])
    if not S["syms"]:
        sys.exit(f"no data for any {_auto.market_of_style(style)} symbol on {S['tf']}: "
                 f"{', '.join(m[0] for m in S['absent'])}.\n"
                 f"  {'the MT5 EA only exports a symbol that has a CHART ATTACHED in MetaTrader' if I.data_dir(S['absent'][0][0]) == 'mt5-bridge' else 'the launchd scanner writes these -- check /automation status'}.\n"
                 f"  Nothing is wrong with the page: a chart drawn from no candles would be a fabrication.")
    facts = read_json(f"{ROOT}/data/live/prelim/{style}.facts.json", {}) or {}
    meta = read_json(f"{ROOT}/data/live/prelim/{style}.meta.json", {}) or {}
    anchors = read_json(f"{ROOT}/data/live/anchors.{style}.json", {}) or {}
    narrative = read_json(narrative_path or f"{ROOT}/data/live/narrative/{style}.json")
    params = (read_json(f"{ROOT}/docs/architecture/analysis-params.json", {}) or {}).get("project_defined", {})
    vol_p = params.get("volume", {})
    P = dict(lookback=params.get("lookback_bars", 20), high=vol_p.get("high_min_ratio", 1.5), spike=vol_p.get("spike_min_ratio", 2.5))
    # The footer's scanner line used to spell these three out as literal text ("pivot 3 nến, dung sai 0,08%,
    # FVG >= 0,6x"), which made it a second source for numbers analysis-params.json already owns -- it would
    # have gone stale the first time one was tuned. Reading them here is what scripts/tests/test_i18n.py's
    # "numbers come from code" check is for: it found this while the translation was being written.
    ict_p = params.get("ict", {})
    scan_p = dict(pivot=(ict_p.get("pivot_bars") or {}).get("value", 3),
                  eqtol=f'{(ict_p.get("equal_level_tolerance_pct") or {}).get("value", 0.08):g}%',
                  fvgmin=f'{(ict_p.get("fvg_min_size_median_ratio") or {}).get("value", 0.6):g}')
    # lane facts chart.js reads instead of hand-keeping its own copy (Task 10b item 4)
    P.update(laneOrder=[m for m, _ in LANES], laneLabels=dict(LANES),
             overlayLanes=list(OVERLAY_LANES), panes=PANES,
             # chart.js draws its labels after load, so they cannot be lang-tagged siblings in the HTML; the
             # catalog slice and the locale records (which carry the display timezone) ride in here instead.
             i18n=i18n.js_catalog("chart.", "legend."), locales=i18n.js_locales(), defaultLang=i18n.DEFAULT)
    cfg = read_json(f"{ROOT}/docs/architecture/automation-config.json", {}) or {}
    market = _auto.market_of_style(style)
    dim_flags = ((cfg.get("markets") or {}).get(market) or {}).get("dimensions") or {}
    mode = (narrative or {}).get("mode") or "NORMAL"

    purity = {}
    data_js, sections, status_chips, rows_store = {}, [], [], {}
    src_notes, syms_quality = [], {}
    lane_engaged = {m: False for m, _ in LANES}   # page-wide topbar state: on if engaged for ANY symbol on this page
    lane_analysed = {m: False for m, _ in LANES}  # §15: READ for any symbol, whether or not it may trade
    for sym, key, disp, kind in S["syms"]:
        rows, upd, src = candles(sym, S["tf"], S["n"], snap)
        syms_quality[sym] = quality_of(sym, S["tf"])[0]     # §20 state of the series being drawn
        # One source note per locale: the symbol, timeframe and provider are machine values, only "updated" is a
        # word. Kept as a per-locale dict rather than a rendered string so the footer can say it in either.
        note = {l: f"{sym} {S['tf']}: {src or '?'} · " + T("footer.updated", l, time=upd or "?") for l in i18n.LOCALES}
        # tiers above the working window (docs/architecture/timeframe-mapping.md; automation.TIERS is the table)
        tier_rows = {}
        for tname in ("bias", "structure"):
            t = S["tiers"].get(tname)
            if not t:
                continue
            try:
                trows, tupd, _ = candles(sym, t["tf"], t["n"], snap)
            except FileNotFoundError:
                continue
            tier_rows[tname] = trows
            for l in i18n.LOCALES:
                note[l] += f" · {tier_name(tname, l).lower()} {t['tf']} " + T("footer.updated", l, time=tupd or "?")
        src_notes.append(note)
        fsym = (facts.get("symbols") or {}).get(sym)
        l1 = layer1(sym, fsym, kind, S["tf"]) if fsym else None
        l2 = layer2(style, sym)
        n3 = ((narrative or {}).get("symbols") or {}).get(sym)
        if n3:
            n3["_updated_iso"] = (narrative or {}).get("updated")
        dims = {}
        # CLAUDE.md §15 analysis scope, from the one implementation (methods.analysed_dimensions) that the
        # authoring brief and check-model-prose.py also read -- so a page cannot claim a lane was analysed
        # that the brief never asked anyone to write, nor hide one it did.
        _analysed_dims = set(_methods.analysed_dimensions(market)[0])
        for m, _label in LANES:
            flag = dim_flags.get(m)
            # "Is this dimension's own source live?" -- asked of the capability registry rather than by
            # prefix-matching a vendor name in data_sources, which is what this line used to do. Same boolean
            # today (CoinGlass is the only mock_only provider); the difference is that wiring a second
            # aggregated-intelligence vendor no longer leaves a string test silently wrong (CLAUDE.md §6).
            coinglass = not _methods.live_sourced(m, market)
            has = bool((n3 or {}).get(m, {}).get("text_html")) or bool((l2 or {}).get(m))
            # wyckoff/ict read the candle file the page is already drawing, so "available" is not a CoinGlass
            # question for them -- it's simply "do we have candles for this timeframe" (footprint/heatmap keep
            # the exact status check they always had).
            avail = (((n3 or {}).get(m) or {}).get("status") == "available") if coinglass else bool(rows)
            # A reason travels as (key, params) so it can be said in either language -- and the params that are
            # themselves localized (the preset name) are passed per locale, not pre-rendered into one.
            if market not in _methods.DIMENSIONS[m]["markets"]:
                reason = ("dims.reason.no_commodity_source", {})
            elif flag is False:
                reason = ("dims.reason.off", {})
            elif not avail:
                reason = (("dims.reason.no_live_source",
                           {"mode": preset_mode(dim_flags, market),
                            "preset": {l: preset_label(dim_flags, market, l) for l in i18n.LOCALES}})
                          if coinglass else ("dims.reason.no_candles", {}))
            else:
                reason = None
            engaged = bool(avail and has and flag is not False) if coinglass else bool(avail and flag is not False)
            # CLAUDE.md §15: the trading selection is NOT a global analysis filter. A lane the preset does not
            # trade is still ANALYSED when it has a live source and something was actually written about it --
            # and the page must show it, marked as not counting toward confluence (§18, §50). `analysed` drops
            # the `flag` test and nothing else; `engaged` is untouched, so what may gate a trade is unchanged.
            in_scope = m in _analysed_dims
            analysed = in_scope and (bool(avail and has) if coinglass else bool(avail)) and has
            # Three different states wore the same words before this. Saying "off in /automation" about a lane
            # the analysis scope keeps ON is a false claim about the system's own configuration -- the lane is
            # not traded, which is a different sentence from not read.
            if analysed and not engaged:
                reason = ("dims.reason.analysis_only", {})
            elif in_scope and not engaged and avail:
                reason = ("dims.reason.analysis_pending", {})
            dims[m] = {"engaged": engaged, "analysed": bool(analysed),
                       "reason": reason or ("dims.reason.in_use", {})}
            lane_engaged[m] = lane_engaged[m] or engaged
            lane_analysed[m] = lane_analysed[m] or bool(analysed)
        # purity: layer 1 cells, layer 2 blocks, layer 3 texts, chart labels, timeline cells.
        # Layer 1 was excluded on the assumption that scanner-written text is "pure by construction" -- an
        # assumption, not a check, and the only layer nothing verified (audit 2026-09-13).
        blocks = mp.narrative_blocks(n3)
        if l1:
            for m in OVERLAY_LANES:
                if l1.get(m):
                    blocks[m] += [l1[m]]
        if l2 and not l2["legacy"]:
            for m, v in mp.model_blocks(l2).items():
                blocks[m] += v
        res = mp.check_blocks(blocks)
        if res:
            purity[sym] = res
        # levels for the charts: anchors by method
        levels = []
        for L in ((anchors.get("symbols") or {}).get(sym) or {}).get("levels", []):
            m = anchor_method(L)
            levels.append(dict(price=L["price"], time=L.get("time"), method=("neutral" if m in ("mixed", "neutral") else m), short=esc((L.get("short") or L.get("name", "")).replace("_", " ")[:14])))
        # P7.1 (docs/audits/2026-09-24-wyckoff-label-review.md §7): computed at build time from the scanner's own
        # facts, never stored in the narrative -- the narrative file stays exactly as written (CLAUDE.md §17).
        inv_at = invalidated_at(n3, fsym)
        wy_js = wy_json((n3 or {}).get("wyckoff"))
        # Wyckoff overlay per tier: the tier style's own full analysis (one read per candle series, two pages never disagree);
        # the gate tier falls back to this style's narrative.context when that style has no page yet
        gate_style, gate_name = _auto.gate_style(style)
        # The bias the ladder shows must be read by the SAME methods whose columns the page draws -- `dims` is the
        # page's own engaged set (it also accounts for availability, which the config flags alone do not).
        bias_methods = tuple(m for m in OVERLAY_LANES if dims.get(m, {}).get("engaged"))
        tier_ctx = {tn: htf.load_tier(style, tn, sym, methods=bias_methods) for tn in ("bias", "structure")}
        tier_wy = {}
        for tname in tier_rows:
            t = S["tiers"][tname]; twy = {}
            if t["style"]:
                twy = (((read_json(f"{ROOT}/data/live/narrative/{t['style']}.json") or {}).get("symbols") or {}).get(sym) or {}).get("wyckoff") or {}
            if not twy.get("events") and tname == gate_name:
                twy = ((n3 or {}).get("context") or {}).get("wyckoff") or {}
            tier_wy[tname] = wy_json(twy)
        tiers_js = []
        for tname in ("bias", "structure"):
            if tname in tier_rows:
                t = S["tiers"][tname]
                tiers_js.append(dict(key=tname, tf=t["tf"], kz=(t["tf"] in ("15m", "1H")), tfMin=TF_MIN.get(t["tf"], 0), wy=tier_wy[tname], levels=[], compact=True, rows="__ROWS__" + key + tname))
        tiers_js.append(dict(key="entry", tf=S["tf"], kz=S["kz"], tfMin=TF_MIN.get(S["tf"], 0), wy=wy_js, levels=levels, compact=False, rows="__ROWS__" + key + "entry"))
        # chart.js draws the lane-status text at runtime, so it gets every locale of each reason and picks one.
        data_js[key] = dict(fmt=kind, tick=I.is_tick_volume(sym), market=I.display(sym)["asset_class"],
                            dims={m: {l: reason_text(dims[m]["reason"], l) for l in i18n.LOCALES} for m, _ in LANES},
                            engaged=[m for m, _ in LANES if dims[m]["engaged"]],
                            # §15/§0.7: a lane the active preset does not TRADE may still be ANALYSED (read,
                            # written about) -- chart.js `drawnFor` gates on THIS set, not `engaged`, so a
                            # lane's chart overlay is no longer locked to the trading-selection preset.
                            analysed=[m for m, _ in LANES if dims[m]["analysed"]],
                            tiers=tiers_js, plans=trade_plans(sym),
                            # P7.2 item 4: the entry tier's own narrative `updated` date, for the muted
                            # "Analysis <updated> invalidated <date>" note chart.js draws when the whole read
                            # died before the visible window even starts.
                            updated=(n3 or {}).get("_updated_iso"),
                            invalidation=(dict((n3 or {}).get("invalidation") or {}, **{"invalidated_at": inv_at["time"], "invalidated_close": inv_at["close"]})
                                          if inv_at else (n3 or {}).get("invalidation")))
        rows_store[key] = {**{tn: rows_js(tier_rows[tn], S["tiers"][tn]["lbl"]) for tn in tier_rows}, "entry": rows_js(rows, S["lbl"])}
        # section html: header (one price, one verdict), the ladder (three tiers, both methods), three charts top-down
        lo, hi = min(r["low"] for r in rows), max(r["high"] for r in rows); last = rows[-1]["close"]
        pct = (last - lo) / (hi - lo) if hi > lo else 0
        cur_verdict, verdict_src = verdict_of(l1, l2)
        src_tag = DUAL(lambda l: T(verdict_src, l))
        status_chips.append(f'<span class="st"><span class="mono">{disp.split("/")[0]}</span>{chip(cur_verdict)}'
                            f'<span class="src">{src_tag}</span></span>')
        pos_pct = f'<b>{pct * 100:.0f}%</b>'
        head = (f'<div class="sym-head"><div class="sym-name"{UI.attr("instrument")}>{disp}</div><div class="sym-last">{fmtn(last, kind)}</div>'
                f'<div class="sym-kv"><span>{DUAL(lambda l: T("sym.window_pos", l, tf=S["tf"], pct=pos_pct))}</span>'
                f'<span>{DUAL(lambda l: T("sym.last_candle", l, time=f"<b>{when(rows[-1]["time"], l)}</b>"))}</span></div>'
                f'<div class="sym-verdict"><span class="lbl">{DUAL(lambda l: T("sym.entry_tf", l, tf=S["tf"]))}</span>{chip(cur_verdict, "chip-lg")}</div></div>')
        ladder_html = ladder(S, sym, kind, cur_verdict, l1, n3, tier_ctx, gate_name, dims)
        charts_html = ""
        for tname in ("bias", "structure"):
            t = S["tiers"].get(tname)
            if not t:
                continue
            if tname not in tier_rows:
                charts_html += (f'<div class="chart-block chart-missing"><div class="chart-title"><span><b>{i18n.tx(TIER_KEY[tname])}</b> · '
                                f'{DUAL(lambda l: horizon(t, l))}</span></div>'
                                f'<div class="lane-status">{DUAL(lambda l: T("chart.no_candles", l, tf=t["tf"], sym=disp))}</div></div>')
                continue
            trows = tier_rows[tname]
            charts_html += (f'<div class="chart-block" id="{tname}-{key}"><div class="chart-title"><span><b>{i18n.tx(TIER_KEY[tname])}</b> · '
                            f'{DUAL(lambda l: horizon(t, l) + " · " + range_label(trows[0]["time"], trows[-1]["time"], t["lbl"], l))}</span>'
                            f'<span class="zoom"><span class="muted">{i18n.tx("chart.shaded_is_entry")}</span>{zoom_buttons()}</span></div>'
                            f'<div class="chart-wrap"><div class="chart" id="chart-{tname}-{key}"></div><div class="tip"></div></div><div class="mode-status" hidden></div><div class="lane-status" hidden></div></div>')
        charts_html += (f'<div class="chart-block" id="entry-{key}"><div class="chart-title"><span><b>{i18n.tx("tier.entry")}</b> · '
                        f'{DUAL(lambda l: horizon(S, l) + " · " + range_label(rows[0]["time"], rows[-1]["time"], S["lbl"], l))}</span>'
                        f'<span class="zoom"><span class="muted">{DUAL(lambda l: T("chart.hint", l, n=len(LANES)))}</span>{zoom_buttons(full=True)}</span></div>'
                        f'<div class="chart-wrap"><div class="chart" id="chart-entry-{key}"></div><div class="tip"></div></div><div class="mode-status" hidden></div><div class="lane-status" hidden></div></div>')
        legend = f'<div class="legend" id="legend-{key}"></div>'
        sections.append(f'<section class="symbol" id="sec-{key}">{head}{ladder_html}<div class="charts"{UI.attr("actual-path")}>{charts_html}{legend}</div>{matrix(key, kind, l1, l2, n3, dims, newest=rows[-1]["time"], inv_at=inv_at)}{timeline((n3 or {}).get("timeline"), dims)}</section>')

    if purity:
        print("PURITY VIOLATIONS (one method, one vocabulary):", file=sys.stderr)
        for sym, res in purity.items():
            print(f"[{sym}]\n{mp.report(res)}", file=sys.stderr)
        if not allow_impure:
            print("BUILD REFUSED — fix the offending block(s) or pass --allow-impure for a local preview.", file=sys.stderr)
            sys.exit(2)
    if check_only:
        print("CHECK OK" if not purity else "CHECK FAILED (impure)"); return

    # meta strip
    wf, wl = meta.get("window_first"), meta.get("window_last")
    headline = (narrative or {}).get("headline") or {}
    tfmin = lambda tf: TF_MIN.get(tf, 0)
    _, gate_name = _auto.gate_style(style)

    def steps_html(l):
        out = []
        for tname in ("bias", "structure"):
            t = S["tiers"].get(tname)
            below = (S["tiers"]["structure"]["tf"] if (tname == "bias" and S["tiers"].get("structure")) else S["tf"])
            if t:
                r = f' <span class="ld-ratio">×{tfmin(t["tf"]) / tfmin(below):g}</span>' if tfmin(t["tf"]) and tfmin(below) else ""
                chart_only = "" if t["style"] else f' <span class="muted">({T("meta.chart_only", l)})</span>'
                out.append(f'<span class="ld-step">{tier_name(tname, l)} <b>{t["tf"]}</b>{r}{chart_only}</span>')
            else:
                out.append(f'<span class="ld-step muted">{tier_name(tname, l)} —</span>')
        out.append(f'<span class="ld-step">{tier_name("entry", l)} <b>{S["tf"]}</b></span>')
        return ' <span class="ld-arrow">→</span> '.join(out)

    def gate_note(l):
        return T("meta.gate_tier", l, tier=tier_name(gate_name, l)) if gate_name else T("meta.no_gate_tier", l)

    # `headline` is model prose -- shown as authored and marked, not guessed at.
    hl_text = vi_source(esc(headline["text"])) if headline.get("text") else i18n.tx("ui.dash")
    hl_detail = vi_source(esc(headline["detail"])) if headline.get("detail") else ""
    meta_html = ('<div class="meta">'
                 f'<div class="meta-ladder"><div class="meta-l">{i18n.tx("meta.ladder")}</div>'
                 f'<div class="meta-v">{DUAL(steps_html)}</div>'
                 f'<div class="meta-d">{DUAL(lambda l: gate_note(l) + " · " + T("meta.ladder_note", l))}</div></div>'
                 f'<div><div class="meta-l">{i18n.tx("meta.headline")}</div><div class="meta-v">{hl_text}</div><div class="meta-d">{hl_detail}</div></div>'
                 f'<div><div class="meta-l">{i18n.tx("meta.status")}</div><div class="meta-v">{" ".join(status_chips)}</div>'
                 f'<div class="meta-d">{DUAL(lambda l: T("meta.data_through", l, time=hhmm(wl, l)))}</div></div>'
                 '</div>')
    # The narrative records the mode its own run used; the footer names the mode the config means now.
    # Where they disagree the config changed since the last full analysis -- say so, do not pick a winner.
    _cfg_mode = preset_mode(dim_flags, market)
    if narrative and mode != _cfg_mode:
        def mode_note(l):
            return f' <span class="muted">({T("footer.last_full_mode", l, mode=esc(mode))})</span>'
    else:
        def mode_note(l):
            return ""
    lane_btns = lane_buttons(lane_engaged)
    symnav = ("".join(f'<a href="#sec-{key}">{disp.split("/")[0]}</a>' for _, key, disp, _ in S["syms"])
              + f'<a href="#sec-glossary">{i18n.tx("nav.glossary")}</a>')
    top = (f'<div class="topbar"><div class="topbar-in"><div class="brand"><div class="brand-title">{esc(S["name"])}</div>'
           f'<div class="brand-sub"{UI.attr("freshness")}>{DUAL(lambda l: horizon(S, l) + " · " + T("meta.data_through", l, time=hhmm(wl, l)))}</div></div>'
           f'<nav class="symnav">{symnav}</nav>'
           f'<div class="lanes" role="group" {i18n.attr("aria-label", "nav.methods")}>{lane_btns}</div>'
           f'{i18n.switch_html()}</div></div>')
    feed = "MT5 bridge (tick volume)" if market == "cfd" else "Binance public REST"
    lede = (f'<div class="lede"><div><p class="eyebrow">{DUAL(lambda l: f"{feed} · {horizon(S, l)} · " + T("lede.not_a_signal", l))}</p>'
            f'<h1>{esc(S["name"])}</h1>'
            f'<p>{DUAL(lambda l: T("lede.three_tiers", l, bias=tier_name("bias", l), structure=tier_name("structure", l), entry=tier_name("entry", l), methods=method_clause(lane_engaged, l)))}</p>'
            f'<p class="i18n-authored">{i18n.tx("ui.vi_source.page")}</p></div>'
            f'<div class="disclaimer">{i18n.tx("lede.disclaimer")}</div></div>')
    built = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    footprint_note = (lambda l: "; " + T("footer.footprint_on_wyckoff", l)) if lane_engaged.get("footprint") else (lambda l: "")
    nls = no_live_source(lane_engaged, market)
    # §6: a symbol that is allowlisted for analysis but has no feed is NAMED, not dropped. Before 2026-09-18
    # the cfd page drew a hardcoded [XAUUSD] and said nothing about the rest, so an attached silver chart with
    # 600 live bars simply did not appear -- and neither did the two oil symbols that genuinely have no export.
    # One of those is a suppressed source and the other is an honest absence, and the page could not tell you
    # which, because it never mentioned either.
    absent = (" · " + DUAL(lambda l: T("symbols.absent_named", l,
                                       names=" · ".join(m[2] for m in S["absent"])))) if S["absent"] else ""
    footer = (f'<footer><span{UI.attr("provenance")}>{DUAL(lambda l: f"<b>{T("footer.sources", l)}</b>: " + " · ".join(esc(x[l]) for x in src_notes))}<br>'
              f'{DUAL(lambda l: T("footer.layers_built", l, scanned=esc(facts.get("scanned_at", "—")), narrative=esc((narrative or {}).get("updated") or T("footer.none_yet", l)), built=built, style=style))}<br>'
              f'{DUAL(lambda l: f"<b>{T("footer.mode", l)}</b> {esc(preset_mode(dim_flags, market))}: {esc(preset_label(dim_flags, market, l))}" + mode_note(l))}'
              f'{(" · " + nls) if nls else ""}{absent} · {DUAL(lambda l: f"<b>{T("footer.layers", l)}</b>: " + T("footer.layers_detail", l))}<br>'
              f'{DUAL(lambda l: f"<b>{T("footer.rules", l)}</b>: " + T("footer.rules_detail", l) + footprint_note(l) + ". " + T("footer.scanner_params", l, **scan_p))}<br>'
              'Chart: TradingView Lightweight Charts™ · Copyright (c) 2025 TradingView, Inc. · <a href="https://www.tradingview.com/" rel="noopener">tradingview.com</a> · Apache-2.0 (scripts/vendor/NOTICE-lightweight-charts.txt)'
              '</footer>')

    data_json = json.dumps(data_js, ensure_ascii=False)
    for _, key, _, _ in S["syms"]:
        for tn, js in rows_store[key].items():
            data_json = data_json.replace(f'"__ROWS__{key}{tn}"', js)
    # The language shim runs FIRST, before any content parses: it stamps data-lang on <html> so only one locale
    # has ever been visible. The Artifact tool owns <html>, so the server cannot stamp it -- see i18n.switch_css.
    # The <title> is the artifact's identity in the gallery and tab and stays stable across redeploys.
    #
    # switch_js() takes NO title key here, unlike the panel and the journal, and that is deliberate rather than
    # an omission: a chart page's name is a market name plus a trading-style term ("Crypto Scalping", "CFD
    # Swing"), and this project leaves both untranslated in every language -- the same rule the glossary follows
    # for Dealing range, premium/discount and every methodology name. There is no second rendering for the shim
    # to switch TO. The moment S["name"] becomes localized, it needs a title key, which is what
    # test_i18n.TabTitleFollowsTheLanguage checks for.
    # CHARSET FIRST, before anything else, and within the first 1024 bytes so the browser's encoding pre-scan
    # sees it. The Artifact host wraps this fragment in a head that already declares utf-8, so on a published
    # page it is redundant -- but `--out` also writes a standalone file, and a plain static server sends
    # `text/html` with no charset parameter, at which point the browser falls back to windows-1252 and every
    # Vietnamese character on the page becomes mojibake. The analysis prose IS Vietnamese, so that is the whole
    # document. Found 2026-09-18 by opening a built page in a real browser (document.characterSet came back
    # "windows-1252"); no unit test could have seen it, because the bytes on disk were always correct utf-8.
    page = ('<meta charset="utf-8">\n'
            + '<title>' + esc(S["name"]) + '</title>\n'
            + i18n.switch_js() + '\n'
            + theme.FONTS + '\n'
            + CSS.replace('__TOKENS__', theme.TOKENS).replace('__I18N__', i18n.switch_css())
            + top + '<div class="page">' + lede + meta_html
            + context_strip(style, market, S, lane_engaged, lane_analysed, dim_flags, syms_quality, built) + "".join(sections) + glossary(lane_engaged) + footer + '</div>\n'
            + js_block(data_json, json.dumps(P)))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    if snap:
        json.dump({"style": style, "built": built, "out": out, "facts_scanned_at": facts.get("scanned_at"), "narrative_updated": (narrative or {}).get("updated"),
                   "sources": src_notes}, open(os.path.join(snap, "build-manifest.json"), "w"), ensure_ascii=False, indent=1)
    print(f"BUILD OK -> {repo_rel(out, ROOT) if out.startswith(ROOT) else out} ({len(page) // 1024} KB) · layer1 {facts.get('scanned_at', '—')} · layer3 {(narrative or {}).get('updated', '—')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("style", choices=STYLES.keys()); ap.add_argument("--out"); ap.add_argument("--snapshot-dir")
    ap.add_argument("--narrative"); ap.add_argument("--allow-impure", action="store_true"); ap.add_argument("--check-only", action="store_true")
    a = ap.parse_args()
    if not a.out and not a.check_only:
        ap.error("--out is required unless --check-only")
    build(a.style, a.out or os.devnull, a.snapshot_dir, a.narrative, a.allow_impure, a.check_only)


if __name__ == "__main__":
    main()
