#!/usr/bin/env python3
"""Higher-timeframe (HTF) context for one chart style — the "giảm khung" (drop-down) rule made code.

Book basis (the only source of the rule): knowledge/07-wyckoff-advance.md §2.7 "Giảm khung của tích lũy" (WA p93–96) —
read the structure and phase on the higher timeframe first, then look for the entry (Spring[C] / LPS[C] / break) on the
lower timeframe *in the direction of the higher-timeframe structure*. In higher-timeframe Phase B the only place to
trade is the Trading Range boundary in the structure's direction (accumulation: the support third where "CO sẽ tiếp
tục tích lũy khi giá tiệm cận vùng hỗ trợ", WA p201, and the m5 "Local accumulation as Spring" of WA p93 forms);
mid-range Phase B is "nguồn cung/cầu đang khá cân bằng … chưa cho thấy sự xuất hiện của CO" — no trade (WA p95).
knowledge/10 §4.2 places regime / Trading Range / phase on the higher timeframe as step 1 of the reading order.

Three tiers per style (docs/architecture/timeframe-mapping.md; scripts/automation.py TIERS is the one table):
  Vào lệnh (E) = the style's own window · Cấu trúc (S) = next rung >= 4x · Bias (B) = next rung >= 4x above S.
  The read that GATES the working-window verdict is the bias tier when a scanned style exists for it, else the
  structure tier (automation.gate_style). Pages show all three tiers; the checkers and the pilot use the gate tier.

What this module gives every consumer (scanner facts, local-read brief, checkers, pilot, page builder):
  tiers(style)                 -> {"structure": tier|None, "bias": tier|None}, tier = {"tf", "style"} (style None = chart only)
  context_style(style)         -> the gate tier's style (scripts/automation.py gate_style)
  load_tier(style, name, sym)  -> dict or None: code facts of that tier's style (prelim/<ctx>.facts.json) + the latest Wyckoff
                                  structure/phase read of that window (narrative/<ctx>.json if that style has a page, else this
                                  style's own narrative `context.wyckoff`) + `bias` and `basis`; carries `tier` = name
  load_context(style, sym)     -> load_tier for the gate tier (what the verdict checks and the pilot filter use)
  bias_of(wyckoff, facts)      -> "long" | "short" | "neutral" | "unknown"  (see table in the function)
  check_verdict(verdict, side, ctx, text) -> list of problems (empty = consistent with the book's top-down rule)
Numbers here are copied from code-written files; the phase/structure words come from the last full analysis and carry
their own `updated` timestamp so staleness is visible.
"""
import importlib.util, json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("automation", os.path.join(ROOT, "scripts", "automation.py"))
_auto = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_auto)
CONTEXT_STYLE = _auto.CONTEXT_STYLE            # style -> gate style (alias kept for older readers)
TIERS = _auto.TIERS
TIER_NAME = {"bias": "Bias", "structure": "Cấu trúc", "entry": "Vào lệnh"}
STYLE_TF = {v: k[1] for k, v in _auto.STYLE.items()}   # style -> timeframe label as /automation spells it

LONG_STRUCT = ("tích lũy", "tích luỹ", "tái tích lũy", "tái tích luỹ")
SHORT_STRUCT = ("phân phối", "tái phân phối")
DIRECTION = {"THEO DÕI LONG": "long", "THEO DÕI SHORT": "short"}


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
# book's own ST-within-one-third-of-the-TR yardstick (WA p150, p166 — knowledge/07 §2.11; analysis-params.json
# sourced.st_within_third_of_tr); using it as the entry-zone width is this project's adaptation, not a printed rule.
BOUNDARY_FRACTION = 1.0 / 3.0


def bias_of(wyckoff, facts):
    """Directional bias the higher timeframe allows, per the book (knowledge/07 §2.7 "Giảm khung" WA p93–96, §3.4 CO plan WA p201–203):
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
        if not ph or ph == "A" or not (is_acc or is_dist):
            return "neutral", f"khung lớn pha {ph or '?'} ({st or 'chưa xác lập'}) — hành động dừng / cấu trúc chưa xác lập, chưa giao dịch theo hướng (knowledge/07 §2.7.1, WA p95–96)"
        if ph in ("C", "D", "E"):
            if is_acc:
                return "long", f"khung lớn {st} pha {ph} — tìm Spring[C]/LPS[C]/phá vỡ theo hướng tăng ở khung nhỏ (WA p93–96, knowledge/07 §2.7)"
            return "short", f"khung lớn {st} pha {ph} — tìm UTAD/LPSY/phá vỡ theo hướng giảm ở khung nhỏ (WA p116–119, knowledge/07 §2.8)"
        # Phase B: boundary rule
        tr = (wyckoff.get("trading_range") or {}); hi, lo = tr.get("high"), tr.get("low"); last = (facts or {}).get("last")
        if hi is None or lo is None or last is None or hi <= lo:
            return "neutral", f"khung lớn {st} pha B nhưng chưa có biên Trading Range (AR / SC-ST) trong bản đọc khung lớn — không xác định được giá đang ở biên nào; chưa giao dịch (WA p95–96)"
        pos = (last - lo) / (hi - lo)
        if is_acc and pos <= BOUNDARY_FRACTION:
            return "long", f"khung lớn {st} pha B, giá ở {pos * 100:.0f}% TR — sát biên dưới (SC/ST), nơi CO gom hàng và khung nhỏ có thể in Spring[C]/LPS[C] cục bộ (WA p93, p201; knowledge/07 §2.7, §3.4)"
        if is_dist and pos >= 1 - BOUNDARY_FRACTION:
            return "short", f"khung lớn {st} pha B, giá ở {pos * 100:.0f}% TR — sát biên trên (BC/UT), nơi CO xả hàng và khung nhỏ có thể in UTAD/LPSY cục bộ (WA p116–119, p206; knowledge/07 §2.8, §3.4)"
        side_note = "biên trên — CO bán ở đây, không phải cơ hội cho công chúng" if is_acc and pos >= 1 - BOUNDARY_FRACTION else ("biên dưới — CO mua ở đây trong phân phối" if is_dist and pos <= BOUNDARY_FRACTION else "giữa vùng")
        return "neutral", f"khung lớn {st} pha B, giá ở {pos * 100:.0f}% TR ({side_note}) — cung/cầu cân bằng, chưa có CO xuất hiện, chưa giao dịch (WA p95–96, p201–203)"
    an = (facts or {}).get("anchors") or {}
    v = (an.get("verdict") or "").upper()
    if v.startswith("PHÁ TRÊN"):
        return "long", "chưa có đọc Wyckoff khung lớn; scanner khung lớn: PHÁ TRÊN mốc neo (tính toán của hệ thống)"
    if v.startswith("PHÁ DƯỚI"):
        return "short", "chưa có đọc Wyckoff khung lớn; scanner khung lớn: PHÁ DƯỚI mốc neo (tính toán của hệ thống)"
    return "unknown", "chưa có đọc Wyckoff khung lớn và scanner khung lớn chưa có mốc neo bị phá"


def load_tier(style, name, sym):
    """Facts + Wyckoff read + bias of one tier ("bias" | "structure") of `style`; None when that tier has no scanned style."""
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
    bias, basis = bias_of(wy, f)
    an = f.get("anchors") or {}
    return {
        "tier": name, "style": ctx, "tf": STYLE_TF.get(ctx, "?"), "scanned_at": facts_all.get("scanned_at"), "window_last": facts_all.get("window_last"),
        "last": f.get("last"), "last_time": f.get("last_time"), "lo": f.get("lo"), "hi": f.get("hi"), "eq": f.get("eq"), "pct": f.get("pct"),
        "stance": f.get("stance"), "verdict": an.get("verdict"), "verdict_short": an.get("verdict_short"),
        "last_mss": f.get("last_mss"), "nearest_fvg": f.get("nearest_fvg"),
        "anchors": [{"label": L.get("label"), "short": L.get("short"), "method": L.get("method"), "price": L.get("price"), "ref_vs": L.get("ref_vs"), "dist_pct": L.get("dist_pct")} for L in an.get("levels", [])],
        "wyckoff": wy, "wyckoff_source": src, "bias": bias, "basis": basis,
    }


def load_context(style, sym):
    """The gate tier's read (bias tier if it has a scanned style, else structure) — what verdict checks and the pilot use."""
    _, name = _auto.gate_style(style)
    return load_tier(style, name, sym) if name else None


def check_verdict(verdict, side, ctx, text):
    """Problems with a lower-timeframe verdict given the higher-timeframe context (book rule, WA p93–96).
       `side` = 'long' | 'short' | None (from the scanner's setup for SETUP TIỀM NĂNG). `text` = the synthesis block."""
    if not ctx:
        return []
    out = []
    plain = re.sub(r"<[^>]+>", " ", text or "").lower()
    tier = TIER_NAME.get(ctx.get("tier") or "bias", "Bias")
    if "bối cảnh" not in plain and "bias" not in plain and "cấu trúc" not in plain:
        out.append(f"khối tổng hợp phải mở đầu bằng câu '{tier} {ctx['tf']}: …' nêu cấu trúc/pha của tầng đó và bias (luật giảm khung, knowledge/07 §2.7, WA p93–96)")
    direction = DIRECTION.get(verdict) or (side if verdict == "SETUP TIỀM NĂNG" else None)
    bias = ctx.get("bias")
    if direction and bias in ("long", "short") and direction != bias:
        if verdict == "SETUP TIỀM NĂNG":
            out.append(f"SETUP TIỀM NĂNG {direction.upper()} ngược bối cảnh khung {ctx['tf']} ({bias}) — sách chỉ vào lệnh theo hướng cấu trúc khung lớn (WA p93–96, knowledge/07 §2.7): hạ xuống THEO DÕI hoặc CHỜ")
        elif "ngược bối cảnh" not in plain:
            out.append(f"verdict {verdict} đi ngược bối cảnh khung {ctx['tf']} ({bias}) mà khối tổng hợp không ghi rõ 'ngược bối cảnh'")
    if verdict == "SETUP TIỀM NĂNG" and bias == "neutral":
        out.append(f"SETUP TIỀM NĂNG khi khung {ctx['tf']} chưa cho hướng (pha A, hoặc pha B mà giá không ở biên TR thuận cấu trúc): 'nguồn cung/cầu đang khá cân bằng … chưa cho thấy sự xuất hiện của CO' (WA p95–96); chỉ biên TR khung lớn theo hướng cấu trúc mới là chỗ giảm khung tìm Spring[C]/LPS[C] (WA p93, p201) — hạ xuống THEO DÕI hoặc CHỜ")
    return out


def brief_lines(ctx, fmt):
    """Vietnamese lines for local-eval-brief.py (numbers only from ctx facts)."""
    if not ctx:
        return ["- (không có tầng này cho style — khung chưa được quét)"]
    L = [f"- Khung {ctx['tf']} (style {ctx['style']}, scanner chạy {ctx.get('scanned_at')}, nến cuối {ctx.get('last_time')}): giá {fmt(ctx.get('last'))} · {('%.0f' % (ctx['pct'] * 100)) if ctx.get('pct') is not None else '—'}% biên độ ({fmt(ctx.get('lo'))}–{fmt(ctx.get('hi'))}) · EQ {fmt(ctx.get('eq'))} · stance {ctx.get('stance')}"]
    if ctx.get("verdict"):
        L.append(f"- Verdict theo luật khung {ctx['tf']}: {ctx['verdict']}")
    for a in ctx.get("anchors") or []:
        L.append(f"- Mốc {a.get('short') or a.get('label')} {fmt(a.get('price'))}: nến đóng {'trên' if a.get('ref_vs') == 'above' else 'dưới'} ({a.get('dist_pct'):+.2f}%)" if a.get("dist_pct") is not None else f"- Mốc {a.get('short') or a.get('label')} {fmt(a.get('price'))}")
    m = ctx.get("last_mss")
    if m:
        L.append(f"- MSS gần nhất khung {ctx['tf']}: {'tăng' if m.get('type') == 'bull' else 'giảm'} tại {fmt(m.get('level'))}")
    w = ctx.get("wyckoff")
    L.append(f"- Đọc Wyckoff khung {ctx['tf']} (phân tích đầy đủ {w.get('updated')}, {ctx.get('wyckoff_source')}): cấu trúc {w.get('structure')}, pha {w.get('phase')}" + (f", TR {fmt((w.get('trading_range') or {}).get('low'))}–{fmt((w.get('trading_range') or {}).get('high'))}" if w.get('trading_range') else ", TR chưa nêu") if w else f"- Chưa có đọc Wyckoff khung {ctx['tf']} (chưa có phân tích đầy đủ)")
    L.append(f"- BIAS khung {ctx['tf']} (code): {ctx['bias'].upper()} — {ctx['basis']}")
    return L


def ladder_lines(style, sym, fmt):
    """The whole ladder for the brief: Bias, then Cấu trúc, each with brief_lines; marks which tier gates the verdict."""
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
        out += brief_lines(load_tier(style, name, sym), fmt) if (t and t["style"]) else []
    return out
