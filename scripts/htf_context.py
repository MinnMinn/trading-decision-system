#!/usr/bin/env python3
"""Higher-timeframe (HTF) context for one chart style — the "giảm khung" (drop-down) rule made code.

Book basis (the only source of the rule): knowledge/wyckoff/advance.md §2.7 "Giảm khung của tích lũy" (WA p93–96) —
read the structure and phase on the higher timeframe first, then look for the entry (Spring[C] / LPS[C] / break) on the
lower timeframe *in the direction of the higher-timeframe structure*. In higher-timeframe Phase B the only place to
trade is the Trading Range boundary in the structure's direction (accumulation: the support third where "CO sẽ tiếp
tục tích lũy khi giá tiệm cận vùng hỗ trợ", WA p201, and the m5 "Local accumulation as Spring" of WA p93 forms);
mid-range Phase B is "nguồn cung/cầu đang khá cân bằng … chưa cho thấy sự xuất hiện của CO" — no trade (WA p95).
knowledge/integrated/method.md §4.2 places regime / Trading Range / phase on the higher timeframe as step 1 of the reading order.

Three tiers per style (docs/architecture/timeframe-mapping.md; scripts/automation.py TIERS is the one table):
  Vào lệnh (E) = the style's own window · Cấu trúc (S) = next rung >= 4x · Bias (B) = next rung >= 4x above S.
  The read that GATES the working-window verdict is the bias tier when a scanned style exists for it, else the
  structure tier (automation.gate_style). Pages show all three tiers; the checkers and the pilot use the gate tier.

Bias is read PER METHOD, and only by the methods /automation has engaged (user decision 2026-09-13). Before that,
bias came from the Wyckoff read alone, so `dimension wyckoff off` dropped the Wyckoff column from every page while
the Wyckoff narrative went on deciding every verdict — and a style with no Wyckoff narrative fell to "unknown"
instead of falling back to ICT. ICT has its own directional bias (`ict_bias`): the draw on liquidity plus the last
MSS by body close. Two engaged methods disagreeing is a contradiction to RAISE — neutral, both readings in `basis`.

What this module gives every consumer (scanner facts, local-read brief, checkers, pilot, page builder):
  tiers(style)                 -> {"structure": tier|None, "bias": tier|None}, tier = {"tf", "style"} (style None = chart only)
  context_style(style)         -> the gate tier's style (scripts/automation.py gate_style)
  engaged_methods(style[,cfg]) -> ("wyckoff","ict") subset switched on for that style's market in /automation
                                  -- TRADING eligibility. Feeds bias_of / the verdict / the scanner / backtests.
  analysed_methods(style)      -> ("wyckoff","ict") subset still ANALYSED for that style's market (CLAUDE.md §15,
                                  methods.analysed_dimensions). A superset of engaged_methods under the default
                                  `available` scope. Feeds AUTHORING and DISPLAY only -- never the verdict.
  load_tier(style, name, sym[, methods])  -> dict or None: code facts of that tier's style (prelim/<ctx>.facts.json) + the
                                  Wyckoff structure/phase read of that window (narrative/<ctx>.json if that style has a page,
                                  else this style's own narrative `context.wyckoff`) + `bias` and `basis`; `tier` = name.
                                  methods=None resolves from /automation; pass a tuple only to PIN a caller.
  load_context(style, sym[, methods])     -> load_tier for the gate tier (what the verdict checks and the pilot filter use)
  wyckoff_bias(wyckoff, facts) / ict_bias(facts) -> one method's ("long"|"short"|"neutral"|"unknown", basis)
  bias_of(wyckoff, facts[, methods])      -> the combined read; `methods` defaults to ("wyckoff",), the pre-2026-09-13
                                  behaviour, so an un-plumbed caller is unchanged.
  check_verdict(verdict, side, ctx, text) -> list of problems (empty = consistent with the book's top-down rule)
Numbers here are copied from code-written files; the phase/structure words come from the last full analysis and carry
their own `updated` timestamp so staleness is visible.
"""
import importlib.util, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("automation", os.path.join(ROOT, "scripts", "automation.py"))
_auto = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_auto)
_mspec = importlib.util.spec_from_file_location("method_purity", os.path.join(ROOT, "scripts", "method_purity.py"))
_mp = importlib.util.module_from_spec(_mspec); _mspec.loader.exec_module(_mp)   # label -> method, for unlabelled anchors
CONTEXT_STYLE = _auto.CONTEXT_STYLE            # style -> gate style (alias kept for older readers)
TIERS = _auto.TIERS
STYLE_TF = {v: k[1] for k, v in _auto.STYLE.items()}   # style -> timeframe label as /automation spells it

# MACHINE VALUES. These are matched against the words the narrative stores, and the match decides a DIRECTION.
# They are not display text and must never be translated here: doing so would change which trades are allowed,
# not how they are described. The display labels live in docs/architecture/i18n.json under `structure.*`.
LONG_STRUCT = ("tích lũy", "tích luỹ", "tái tích lũy", "tái tích luỹ")
SHORT_STRUCT = ("phân phối", "tái phân phối")
DIRECTION = {"THEO DÕI LONG": "long", "THEO DÕI SHORT": "short"}

sys.path.insert(0, os.path.join(ROOT, "scripts"))
import i18n as _i18n  # noqa: E402
import methods as _methods  # noqa: E402  -- CLAUDE.md §15 analysis scope (analysed_methods_for_market)

# Tier names as the MODEL BRIEF spells them -- brief_lines/ladder_lines/check_verdict are written in the
# locale the analysis model authors in (i18n.AUTHORED), so these come from the catalog in that locale rather
# than being spelled here. The PAGE never reads this: build-artifact.py renders tier names per reader locale.
TIER_NAME = {k: _i18n.t(f"tier.{k}", _i18n.AUTHORED) for k in ("bias", "structure", "entry")}


# The shape of `basis` as load_tier STORES it into data/live/prelim/<style>.facts.json (`context.basis`), and
# into the point-in-time research snapshots under data/live/model-reads/**. CLAUDE.md §59: this changed, so it
# is versioned rather than swapped silently.
#   1  a rendered sentence, in the locale the analysis model authors in
#   2  a list of (tag, message key, params) parts -- renderable into ANY locale, which is why it changed
# Format 1 snapshots stay on disk and stay readable: basis_text() returns a str basis unchanged. Nothing reads
# the STORED value to make a decision (the page and the brief both recompute via load_tier; check-model-prose.py
# reads only ctx["bias"]), so no data migration is required -- and `bias` itself, the value that gates a trade,
# has the same type and the same values in both formats.
BASIS_FORMAT = 2

# ---- the basis ------------------------------------------------------------------------------------------
# A bias comes with a REASON, and that reason has two audiences: the page (read by a human, in the language they
# chose) and the model brief (read by the analysis model, in the language it authors in). One formatted string
# cannot serve both once the page is bilingual, so a basis travels as DATA -- a list of (tag, message key,
# params) parts -- and is rendered late, per audience.
#
# The `bias` value itself is untouched by any of this. It is the thing that gates a trade.
def _b(key, **params):
    """One basis part, untagged."""
    return [(None, key, params)]


def basis_text(basis, lang):
    """Render a keyed basis into one locale's sentence. `[wyckoff]`-style tags are dimension ids -- machine
    values, identical in every language."""
    if not basis:
        return ""
    # A rendered basis from an older facts.json (before the keyed shape) is already one locale's sentence. Show
    # it as it was written rather than crashing on it -- see load_tier's BASIS_FORMAT note.
    if isinstance(basis, str):
        return basis
    parts = []
    for tag, key, params in basis:
        # Two parameter-name conventions, both resolved in the TARGET locale here rather than at the call site,
        # because resolving early would freeze one language's word into every language's sentence -- precisely
        # the silent mixing this whole change exists to prevent.
        #   *_key   a message key
        #   *_word  a structure word as the narrative stored it (see _structure)
        p = {}
        for k, v in params.items():
            if k.endswith("_key"):
                p[k[:-4]] = _i18n.t(v, lang)
            elif k.endswith("_word"):
                p[k[:-5]] = _structure(v, lang)
            else:
                p[k] = v
        s = _i18n.t(key, lang, **p)
        parts.append(f"[{tag}] {s}" if tag else s)
    # A part that ends in a colon is a HEADER for what follows ("the two reading layers disagree:"), so it runs
    # straight into the next clause instead of being separated from it by a bullet.
    out = parts[0]
    for s in parts[1:]:
        out += (" " if out.rstrip().endswith(":") else " · ") + s
    return out


def _structure(word, lang):
    """A stored structure word rendered for a reader.

    Three cases, and each one used to be wrong in a different way:
      - no word at all      -> "not established". It used to interpolate an empty string, so the page read
                               "higher timeframe phase A () — stopping action…".
      - a known word        -> the catalog's term for it, so an English reader gets "accumulation".
      - anything else       -> the narrative's own word, QUOTED and marked as written. It used to be dropped
                               raw into the English sentence ("higher timeframe phase C (đi ngang)"), which is
                               unmarked Vietnamese in English mode. This basis lands in a `title` attribute,
                               where vi_source()'s markup cannot reach, so the quoting is the marking.
    """
    w = (word or "").strip()
    if not w:
        return _i18n.t("structure.unestablished", lang)
    key = f"structure.{w.lower()}"
    return _i18n.t(key, lang) if _i18n.has(key) else _i18n.t("structure.as_written", lang, word=w)


def context_style(style):
    return _auto.gate_style(style)[0]


def tiers(style):
    return TIERS.get(style) or {"structure": None, "bias": None}


def _read(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return None


# Zone parameter: "at the boundary" = within the outer third of the higher-timeframe Trading Range. The third is the
# book's own ST-within-one-third-of-the-TR yardstick (WA p150, p166 — knowledge/wyckoff/advance.md §2.11; analysis-params.json
# sourced.st_within_third_of_tr); using it as the entry-zone width is this project's adaptation, not a printed rule.
BOUNDARY_FRACTION = 1.0 / 3.0


DRAW_LABELS = {"1D": ("PDH", "PDL"), "1W": ("PWH", "PWL")}


def _draw_labels(tf):
    """What ICT calls the previous candle's extremes on THIS tier's timeframe: the previous candle of a daily chart
    IS the previous day (knowledge/ict/core-a.md §2.12 PDH/PDL), of a weekly the previous week, of an intraday chart the
    previous candle (§2.11 PCH/PCL on H4/H1/M30/M15). One computation, named for the rung it is read on."""
    return DRAW_LABELS.get((tf or "").upper(), ("PCH", "PCL"))


def ict_bias(facts):
    """ICT's own directional bias — this dimension has one, and it is not a phase story (.claude/skills/ict-skill/SKILL.md §1):
       - the DRAW ON LIQUIDITY: a body close *through* the previous candle's high/low means that level was the draw,
         expect continuation; a wick through with the body failing to close beyond is **failure to displace**, so the
         opposite level becomes the new draw (knowledge/ict/core-a.md §2.11, §2.12, §2.14, §3.2 R5–R8);
       - STRUCTURAL FALSIFICATION: the last confirmed MSS on this timeframe, by body close (knowledge/ict/core-b.md §2.2).
       Draw and MSS disagreeing is a contradiction to state, not to resolve quietly — it returns neutral.
       The basis text must stay pure ICT vocabulary (method_purity.RULES["ict"]): it is rendered on the page and fed
       to the model brief, so a Wyckoff word here would leak the method switch straight back in."""
    pc = (facts or {}).get("prev_candle") or {}
    hi_lbl, lo_lbl = _draw_labels(pc.get("tf"))
    # Formatted HERE, through the one project formatter, so the basis prints 77,505.67 exactly as the ladder
    # and the chart beside it do. A raw float in a param printed 77505.67 in the tooltip while the page printed
    # 77,505.67 for the same level -- two renderings of one number on one screen.
    hi_px, lo_px = _i18n.num(pc.get("pch")), _i18n.num(pc.get("pcl"))
    draw, draw_why = None, None
    hi_s, lo_s = pc.get("pch_state"), pc.get("pcl_state")
    if hi_s == "closed_through":
        draw, draw_why = "long", _b("bias.ict.draw_through", level=f"{hi_lbl} {hi_px}", dir_key="dir.up")
    elif hi_s == "swept":
        draw, draw_why = "short", _b("bias.ict.failed_displace", level=f"{hi_lbl} {hi_px}", other=f"{lo_lbl} {lo_px}")
    lo_dir, lo_why = None, None
    if lo_s == "closed_through":
        lo_dir, lo_why = "short", _b("bias.ict.draw_through", level=f"{lo_lbl} {lo_px}", dir_key="dir.down")
    elif lo_s == "swept":
        lo_dir, lo_why = "long", _b("bias.ict.failed_displace", level=f"{lo_lbl} {lo_px}", other=f"{hi_lbl} {hi_px}")
    if draw and lo_dir and draw != lo_dir:
        return "neutral", _b("bias.ict.contradiction") + draw_why + lo_why
    if lo_dir and not draw:
        draw, draw_why = lo_dir, lo_why

    m = (facts or {}).get("last_mss") or None
    mss_dir = ("long" if m.get("type") == "bull" else "short") if m else None
    mss_why = _b("bias.ict.mss", dir_key="dir.up" if mss_dir == "long" else "dir.down", level=_i18n.num(m.get("level"))) if m else None

    if draw and mss_dir:
        if draw == mss_dir:
            return draw, draw_why + mss_why
        return "neutral", _b("bias.ict.contradiction") + draw_why + mss_why
    if draw:
        return draw, draw_why
    if mss_dir:
        return mss_dir, mss_why
    return "unknown", _b("bias.ict.nothing")


def wyckoff_bias(wyckoff, facts):
    """Directional bias the higher timeframe allows, per the book (knowledge/wyckoff/advance.md §2.7 "Giảm khung" WA p93–96, §3.4 CO plan WA p201–203):
       - accumulation / re-accumulation in Phase C, D or E -> long; distribution / re-distribution in C, D, E -> short;
       - Phase B: the lower timeframe may only trade the higher-timeframe *boundary* in the direction of the structure —
         accumulation with price in the lower third of the TR (SC/ST support, where "CO sẽ tiếp tục tích lũy khi giá tiệm
         cận vùng hỗ trợ", WA p201, and where the m5 "Local accumulation as Spring" of WA p93 forms) -> long; distribution
         with price in the upper third (BC/UT resistance) -> short; mid-range or the opposite boundary -> neutral
         (WA p95–96: "nguồn cung/cầu đang khá cân bằng … chưa cho thấy sự xuất hiện của CO");
       - Phase A or 'chưa xác lập' -> neutral (stopping action, structure not yet established);
       - no Wyckoff read at all -> the scanner's anchor verdict (PHÁ TRÊN -> long, PHÁ DƯỚI -> short), else unknown.
       `wyckoff` may carry trading_range {high, low}; `facts` carries the higher-timeframe `last` close."""
    if wyckoff and (wyckoff.get("structure") or wyckoff.get("phase")):
        st = (wyckoff.get("structure") or "").lower(); ph = (wyckoff.get("phase") or "").upper()[:1]
        is_acc = any(k in st for k in LONG_STRUCT); is_dist = any(k in st for k in SHORT_STRUCT)
        # `st` is a machine value above (the substring match decides direction) and a display value below.
        # It travels as `structure_word` -- raw, exactly as the narrative stored it -- and _structure() turns it
        # into the reader's language at render time. Choosing the display form HERE would have to choose a
        # language here, and this same basis is rendered twice: once for the page, once for the model brief.
        sd = {"structure_word": st}
        if not ph or ph == "A" or not (is_acc or is_dist):
            return "neutral", _b("bias.wy.not_established", phase=ph or "?", **sd)
        if ph in ("C", "D", "E"):
            if is_acc:
                return "long", _b("bias.wy.acc_cde", phase=ph, **sd)
            return "short", _b("bias.wy.dist_cde", phase=ph, **sd)
        # Phase B: boundary rule
        tr = (wyckoff.get("trading_range") or {}); hi, lo = tr.get("high"), tr.get("low"); last = (facts or {}).get("last")
        if hi is None or lo is None or last is None or hi <= lo:
            return "neutral", _b("bias.wy.b_no_tr", **sd)
        pos = (last - lo) / (hi - lo)
        pct = f"{pos * 100:.0f}%"
        if is_acc and pos <= BOUNDARY_FRACTION:
            return "long", _b("bias.wy.b_lower_edge", pct=pct, **sd)
        if is_dist and pos >= 1 - BOUNDARY_FRACTION:
            return "short", _b("bias.wy.b_upper_edge", pct=pct, **sd)
        if is_acc and pos >= 1 - BOUNDARY_FRACTION:
            side_key = "bias.wy.side.upper_in_acc"
        elif is_dist and pos <= BOUNDARY_FRACTION:
            side_key = "bias.wy.side.lower_in_dist"
        else:
            side_key = "bias.wy.side.mid"
        return "neutral", _b("bias.wy.b_neutral", pct=pct, side_key=side_key, **sd)
    an = (facts or {}).get("anchors") or {}
    v = (an.get("verdict") or "").upper()
    if v.startswith("PHÁ TRÊN"):
        return "long", _b("bias.wy.anchor_only", verdict_key="verdict.PHÁ TRÊN")
    if v.startswith("PHÁ DƯỚI"):
        return "short", _b("bias.wy.anchor_only", verdict_key="verdict.PHÁ DƯỚI")
    return "unknown", _b("bias.wy.nothing")


METHOD_BIAS = {"wyckoff": wyckoff_bias, "ict": lambda wy, f: ict_bias(f)}
BIAS_METHODS = ("wyckoff", "ict")


def engaged_methods_for_market(market, cfg=None):
    """The bias-reading methods ENGAGED for `market`, per /automation. Flag semantics mirror build-artifact.py's
    (`flag is not False`), so an absent key means on. Order is BIAS_METHODS, not dict order, so the basis string
    reads the same way every run. engaged_methods(style) below resolves `market` from a chart style and delegates
    here, so there is ONE implementation a caller with only a market (e.g. a backtest resolving from a symbol via
    automation.market_of) can also reach directly."""
    if cfg is None:
        cfg = _read(_auto.CONFIG) or {}
    flags = (((cfg.get("markets") or {}).get(market) or {}).get("dimensions")) or {}
    return tuple(m for m in BIAS_METHODS if flags.get(m) is not False)


def engaged_methods(style, cfg=None):
    """The bias-reading methods ENGAGED for `style`'s market, per /automation. See engaged_methods_for_market for
    the flag semantics; this just resolves the market from the style first."""
    return engaged_methods_for_market(_auto.market_of_style(style), cfg=cfg)


def analysed_methods_for_market(market):
    """The bias-reading methods still ANALYSED for `market` (CLAUDE.md §15) -- NOT the ones that may qualify a
    trade. Delegates to methods.analysed_dimensions so the scope rule has one implementation, then narrows to
    BIAS_METHODS because this module only knows how to read those two.

    Deliberately takes no `cfg` override: the analysis scope lives in the same config file, and the one caller
    that needs to pin behaviour (a test) can point CONFIG_PATH at a fixture. Order is BIAS_METHODS order, so
    the block list reads the same way every run.
    """
    analysed, _, _ = _methods.analysed_dimensions(market)
    return tuple(m for m in BIAS_METHODS if m in analysed)


def analysed_methods(style):
    """The bias-reading methods still ANALYSED for `style`'s market. See analysed_methods_for_market."""
    return analysed_methods_for_market(_auto.market_of_style(style))


def bias_of(wyckoff, facts, methods=("wyckoff",)):
    """The tier's directional bias, read by the methods that are ENGAGED — the method switch has to reach the
    decision layer, not just the columns that get drawn (user decision 2026-09-13).

    `methods` defaults to ("wyckoff",), which is exactly what this function did before it took the argument, so
    callers that have not been plumbed yet keep their current behaviour verbatim.

    Two engaged methods disagreeing is a **Contradiction to raise**, not something to resolve quietly
    (.claude/skills/ict-skill/SKILL.md §1; user decision 2026-09-13) -> neutral, with both readings in the basis.
    A method returning "unknown" is SILENT (no data), not dissenting, so the other method stands alone; a method
    returning "neutral" has read the tape and found no direction, which is a real reading and forces neutral."""
    reads = {}
    for m in BIAS_METHODS:
        if m in (methods or ()):
            b, why = METHOD_BIAS[m](wyckoff, facts)
            if b != "unknown":
                reads[m] = (b, why)

    def tagged(m, parts):
        """Tag every part of one method's basis with that method's id, so a combined basis says which reading
        each clause came from. The tag is a dimension id -- a machine value, the same in every language."""
        return [(m, key, params) for _, key, params in parts]

    if not reads:
        if not methods:
            return "unknown", _b("bias.none_engaged")
        out = []
        for m in BIAS_METHODS:
            if m in methods:
                out += tagged(m, METHOD_BIAS[m](wyckoff, facts)[1])
        return "unknown", out
    if len(reads) == 1:
        m, (b, why) = next(iter(reads.items()))
        return b, tagged(m, why)
    sides = {b for b, _ in reads.values()}
    combined = [p for m, (b, why) in reads.items() for p in tagged(m, why)]
    if len(sides) == 1:
        return sides.pop(), combined
    return "neutral", _b("bias.contradiction_two") + combined


def load_tier(style, name, sym, methods=None):
    """Facts + Wyckoff read + bias of one tier ("bias" | "structure") of `style`; None when that tier has no scanned style.
    `methods` = the engaged bias readers; None resolves them from /automation (bias_methods). Pass an explicit
    tuple only to pin a caller to a fixed set."""
    if methods is None:
        methods = engaged_methods(style)
    t = tiers(style).get(name)
    ctx = t["style"] if t else None
    if not ctx:
        return None
    facts_all = _read(f"{ROOT}/data/live/prelim/{ctx}.facts.json") or {}
    f = (facts_all.get("symbols") or {}).get(sym) or {}
    # HTF Wyckoff read: the tier style's own narrative when it has a page, else this style's narrative.context (gate tier only)
    wy, src = None, None
    n_ctx = _read(f"{ROOT}/data/live/narrative/{ctx}.json")
    if n_ctx and (n_ctx.get("symbols") or {}).get(sym, {}).get("wyckoff"):
        w = n_ctx["symbols"][sym]["wyckoff"]; wy = {"structure": w.get("structure"), "phase": w.get("phase"), "trading_range": w.get("trading_range"), "updated": n_ctx.get("updated")}; src = f"data/live/narrative/{ctx}.json"
    elif ctx == context_style(style):
        n_own = _read(f"{ROOT}/data/live/narrative/{style}.json")
        cw = (((n_own or {}).get("symbols") or {}).get(sym) or {}).get("context", {}).get("wyckoff") if n_own else None
        if cw and (cw.get("structure") or cw.get("phase")):
            wy = {"structure": cw.get("structure"), "phase": cw.get("phase"), "trading_range": cw.get("trading_range"), "updated": n_own.get("updated")}; src = f"data/live/narrative/{style}.json (context)"
    bias, basis = bias_of(wy, f, methods=methods)
    an = f.get("anchors") or {}
    return {
        "tier": name, "style": ctx, "tf": STYLE_TF.get(ctx, "?"), "scanned_at": facts_all.get("scanned_at"), "window_last": facts_all.get("window_last"),
        "last": f.get("last"), "last_time": f.get("last_time"), "lo": f.get("lo"), "hi": f.get("hi"), "eq": f.get("eq"), "pct": f.get("pct"),
        "stance": f.get("stance"), "verdict": an.get("verdict"), "verdict_short": an.get("verdict_short"),
        "last_mss": f.get("last_mss"), "nearest_fvg": f.get("nearest_fvg"), "prev_candle": f.get("prev_candle"),
        "anchors": [{"label": L.get("label"), "short": L.get("short"), "method": L.get("method"), "price": L.get("price"), "ref_vs": L.get("ref_vs"), "dist_pct": L.get("dist_pct")} for L in an.get("levels", [])],
        "wyckoff": wy, "wyckoff_source": src, "bias": bias, "basis": basis, "basis_format": BASIS_FORMAT,
    }


def load_context(style, sym, methods=None):
    """The gate tier's read (bias tier if it has a scanned style, else structure) — what verdict checks and the pilot use."""
    _, name = _auto.gate_style(style)
    return load_tier(style, name, sym, methods=methods) if name else None


def check_verdict(verdict, side, ctx, text):
    """Problems with a lower-timeframe verdict given the higher-timeframe context (book rule, WA p93–96).
       `side` = 'long' | 'short' | None (from the scanner's setup for SETUP TIỀM NĂNG). `text` = the synthesis block."""
    if not ctx:
        return []
    out = []
    plain = re.sub(r"<[^>]+>", " ", text or "").lower()
    tier = TIER_NAME.get(ctx.get("tier") or "bias", "Bias")
    if "bối cảnh" not in plain and "bias" not in plain and "cấu trúc" not in plain:
        out.append(f"khối tổng hợp phải mở đầu bằng câu '{tier} {ctx['tf']}: …' nêu cấu trúc/pha của tầng đó và bias (luật giảm khung, knowledge/wyckoff/advance.md §2.7, WA p93–96)")
    direction = DIRECTION.get(verdict) or (side if verdict == "SETUP TIỀM NĂNG" else None)
    bias = ctx.get("bias")
    if direction and bias in ("long", "short") and direction != bias:
        if verdict == "SETUP TIỀM NĂNG":
            out.append(f"SETUP TIỀM NĂNG {direction.upper()} ngược bối cảnh khung {ctx['tf']} ({bias}) — sách chỉ vào lệnh theo hướng cấu trúc khung lớn (WA p93–96, knowledge/wyckoff/advance.md §2.7): hạ xuống THEO DÕI hoặc CHỜ")
        elif "ngược bối cảnh" not in plain:
            out.append(f"verdict {verdict} đi ngược bối cảnh khung {ctx['tf']} ({bias}) mà khối tổng hợp không ghi rõ 'ngược bối cảnh'")
    if verdict == "SETUP TIỀM NĂNG" and bias == "neutral":
        out.append(f"SETUP TIỀM NĂNG khi khung {ctx['tf']} chưa cho hướng (pha A, hoặc pha B mà giá không ở biên TR thuận cấu trúc): 'nguồn cung/cầu đang khá cân bằng … chưa cho thấy sự xuất hiện của CO' (WA p95–96); chỉ biên TR khung lớn theo hướng cấu trúc mới là chỗ giảm khung tìm Spring[C]/LPS[C] (WA p93, p201) — hạ xuống THEO DÕI hoặc CHỜ")
    return out


def brief_lines(ctx, fmt, methods=("wyckoff", "ict"), reading=None):
    """Vietnamese lines for local-eval-brief.py (numbers only from ctx facts).

    Two different questions, deliberately two arguments (CLAUDE.md §15):

    `methods`  = the ENGAGED readers -- the ones whose read produced `ctx['bias']`, i.e. the ones that may
                 qualify a trade. Named on the BIAS line so the model can see what the direction rests on.
    `reading`  = the ANALYSED readers -- the ones whose material may be printed and whose anchors keep their
                 NAMES. Defaults to `methods`, so every caller that has not been plumbed behaves exactly as
                 before; the brief passes the wider analysed set, because §15's rule is that the trading
                 selection "is NOT a global analysis filter".

    Before 2026-09-18 these were one argument, and the consequence was the §15 defect itself: selecting the
    ICT preset stopped Wyckoff from being READ, not just from being traded.
    """
    reading = tuple(reading) if reading is not None else tuple(methods)
    if not ctx:
        return ["- (không có tầng này cho style — khung chưa được quét)"]
    L = [f"- Khung {ctx['tf']} (style {ctx['style']}, scanner chạy {ctx.get('scanned_at')}, nến cuối {ctx.get('last_time')}): giá {fmt(ctx.get('last'))} · {('%.0f' % (ctx['pct'] * 100)) if ctx.get('pct') is not None else '—'}% biên độ ({fmt(ctx.get('lo'))}–{fmt(ctx.get('hi'))}) · EQ {fmt(ctx.get('eq'))} · stance {ctx.get('stance')}"]
    if ctx.get("verdict"):
        L.append(f"- Verdict theo luật khung {ctx['tf']}: {ctx['verdict']}")
    for a in ctx.get("anchors") or []:
        # A disengaged method's anchor is still a price the engaged read may react to, but its NAME is that
        # method's vocabulary — give the level, drop the label (local-eval-brief.py mục 6: "Mốc neo có tên
        # Wyckoff (SC, AR…) chỉ được gọi bằng giá"). Anchors marked mixed/neutral belong to no single method.
        am = a.get("method")
        if am not in ("wyckoff", "ict"):   # facts written before the scanner carried the field through
            am = _mp.infer_method(f"{a.get('label') or ''} {a.get('short') or ''} {a.get('name') or ''}")
        named = not (am in ("wyckoff", "ict") and am not in reading)
        who = (a.get("short") or a.get("label")) if named else "(không tên — lớp đọc đang tắt)"
        L.append(f"- Mốc {who} {fmt(a.get('price'))}: nến đóng {'trên' if a.get('ref_vs') == 'above' else 'dưới'} ({a.get('dist_pct'):+.2f}%)" if a.get("dist_pct") is not None else f"- Mốc {who} {fmt(a.get('price'))}")
    m = ctx.get("last_mss")
    if m and "ict" in reading:
        L.append(f"- MSS gần nhất khung {ctx['tf']}: {'tăng' if m.get('type') == 'bull' else 'giảm'} tại {fmt(m.get('level'))}")
        pc = ctx.get("prev_candle") or {}
        if pc.get("tf"):
            hi_lbl, lo_lbl = _draw_labels(pc["tf"])
            L.append(f"- Draw khung {ctx['tf']}: {hi_lbl} {fmt(pc.get('pch'))} ({pc.get('pch_state')}) · {lo_lbl} {fmt(pc.get('pcl'))} ({pc.get('pcl_state')})")
    if "wyckoff" in reading:
        w = ctx.get("wyckoff")
        L.append(f"- Đọc Wyckoff khung {ctx['tf']} (phân tích đầy đủ {w.get('updated')}, {ctx.get('wyckoff_source')}): cấu trúc {w.get('structure')}, pha {w.get('phase')}" + (f", TR {fmt((w.get('trading_range') or {}).get('low'))}–{fmt((w.get('trading_range') or {}).get('high'))}" if w.get('trading_range') else ", TR chưa nêu") if w else f"- Chưa có đọc Wyckoff khung {ctx['tf']} (chưa có phân tích đầy đủ)")
    # The brief is read by the ANALYSIS MODEL, which authors in i18n.AUTHORED -- so the basis renders in that
    # locale here, while the same keyed basis renders in the reader's locale on the page. One source, two
    # audiences, neither of them getting the other's language.
    # §15/§18: when the read set is WIDER than the traded set, say so on the line that carries the direction.
    # Otherwise the model sees Wyckoff material above a bias it did not feed and reasonably assumes it did.
    extra = [m for m in reading if m not in methods]
    who = f" (chỉ từ: {', '.join(methods) or 'không lớp nào'}" + (
        f"; {', '.join(extra)} chỉ để PHÂN TÍCH, không vào bias)" if extra else ")")
    L.append(f"- BIAS khung {ctx['tf']} (code){who}: {ctx['bias'].upper()} — "
             f"{basis_text(ctx['basis'], _i18n.AUTHORED)}")
    return L


def ladder_lines(style, sym, fmt, methods=None, reading=None):
    """The whole ladder for the brief: Bias, then Cấu trúc, each with brief_lines; marks which tier gates the verdict.

    `methods` None resolves the ENGAGED set from /automation — the brief must not widen what feeds the bias.
    `reading` None resolves the ANALYSED set (CLAUDE.md §15) — the material the model may write about, which
    under the default `available` scope is a superset. The bias is still computed from `methods` alone:
    load_tier is passed `methods`, never `reading`.
    """
    if methods is None:
        methods = engaged_methods(style)
    if reading is None:
        reading = analysed_methods(style)
    _, gate = _auto.gate_style(style)
    out = []
    for name in ("bias", "structure"):
        t = tiers(style).get(name)
        head = f"### {TIER_NAME[name]}" + (f" — khung {t['tf']}" if t else " — không có (khung chậm hơn không được lấy)")
        if t and not t["style"]:
            head += " (chỉ có chart, chưa quét — không có số liệu)"
        if name == gate:
            head += " · TẦNG QUYẾT ĐỊNH BIAS cho verdict"
        out.append(head)
        out += brief_lines(load_tier(style, name, sym, methods=methods), fmt, methods,
                           reading=reading) if (t and t["style"]) else []
    return out
