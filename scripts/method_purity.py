#!/usr/bin/env python3
"""Method-vocabulary purity guard (user decision 2026-09-11).

Rule: a block of analysis that belongs to ONE method may only use that method's knowledge and terminology.
  wyckoff   -> no ICT vocabulary (FVG, MSS, order block, BSL/SSL, premium/discount, killzone, liquidity ...)
  ict       -> no Wyckoff vocabulary (SC/AR/ST/Spring/SOS/LPS, phases A-E, CHoCH, Effort-vs-Result, absorption ...)
               and NO volume at all: the ICT corpus has no volume concept (knowledge/10-integrated-method.md section 4.1);
               the only exception is ICT's own "volume imbalance" (a body gap, knowledge/04 section 2.22).
  footprint -> Wyckoff vocabulary allowed (user: "Footprint co the lay 100% kien thuc cua Wyckoff lam nen tang"),
               ICT vocabulary forbidden.
  heatmap   -> no Wyckoff vocabulary, no ICT structural vocabulary; liquidity words are the heatmap's own.
  synthesis -> anything (this is where the methods are combined).

Term lists are this project's parameters (no source prescribes a blocklist). They are deliberately strict: a
false positive costs one rewrite, a leak costs the separation the user asked for. Tune here, in one place.

API: violations(text, method) -> list of (term, snippet); check_blocks(dict{method: text}) -> {method: [...]}.
Text may be HTML; tags and <span class="cite"> contents are stripped before matching (citations may name any source).
"""
import re

# ---- ICT / TTrades vocabulary ---------------------------------------------------------------------------------
ICT_TERMS = [
    r"\bFVG\b", r"fair[ -]value[ -]gap", r"\bMSS\b", r"market[ -]structure[ -]shift", r"order[ -]?blocks?\b", r"\bOB\b",
    r"\bBSL\b", r"\bSSL\b", r"\bERL\b", r"\bIRL\b", r"\bpremium\b", r"\bdiscount\b", r"\bEQ\b", r"equilibrium",
    r"điểm cân bằng", r"kill ?zones?\b", r"displacement", r"dealing[ -]range", r"\bOTE\b", r"\bPO3\b", r"\bAMD\b",
    r"\bCISD\b", r"breaker", r"turtle soup", r"\bSMT\b", r"silver bullet", r"\bPDH\b", r"\bPDL\b", r"\bPWH\b", r"\bPWL\b",
    r"mitigat", r"inducement", r"\bBOS\b", r"\bSIBI\b", r"\bBISI\b", r"consequent encroachment", r"unicorn",
    r"power of three", r"\bICT\b", r"TTrades",
]
# liquidity words: ICT vocabulary for Wyckoff/Footprint blocks, but the Heatmap dimension's own words
LIQUIDITY_TERMS = [r"liquidity", r"thanh khoản", r"\bsweeps?\b", r"\bswept\b", r"\bgrabs?\b", r"\bpools?\b"]

# ---- Wyckoff vocabulary --------------------------------------------------------------------------------------
WYCKOFF_ACRONYMS = r"\b(PS|SC|AR|ST|UA|UT|UTAD|SOS|SOW|LPS|LPSY|BU|BC|BCLX|PSY|CHoCH|CHoBEV|SOT|VAH|VAL|LVN|POC)\b"  # case-sensitive
WYCKOFF_TERMS = [
    r"\bsprings?\b", r"shake-?outs?\b", r"upthrusts?\b", r"cao trào", r"phục hồi tự động", r"automatic rally",
    r"kiểm tra thứ cấp", r"secondary test", r"dấu hiệu sức mạnh", r"dấu hiệu suy yếu", r"sign of strength",
    r"sign of weakness", r"điểm hỗ trợ cuối", r"điểm cung cuối", r"last point of support", r"last point of supply",
    r"vùng giao dịch", r"trading[ -]range", r"\bpha [A-E]\b", r"\bphase [A-E]\b", r"tích lu[ỹy]", r"phân phối",
    r"accumulation", r"distribution", r"nỗ lực", r"\beffort\b", r"hấp thụ", r"absorption", r"composite operator",
    r"tay mạnh", r"tay yếu", r"khối lượng", r"\bvolume\b", r"\bKL\b", r"wyckoff", r"tape[ -]reading", r"đọc băng",
    r"cung (và|/|-|–) ?cầu", r"supply (and|/) ?demand", r"\bmark-?up\b", r"\bmark-?down\b", r"đánh dấu tăng",
    r"đánh dấu giảm", r"climax", r"đối nhãn", r"\bCO plan\b", r"kế hoạch CO", r"cú nhảy qua khe núi", r"phá băng",
    r"value area", r"volume profile",
]
WYCKOFF_TERMS_HEATMAP = [t for t in WYCKOFF_TERMS if t not in (r"khối lượng", r"\bvolume\b", r"\bKL\b")]  # heatmap may say "volume" of an orderbook wall

# exceptions: phrases that contain a forbidden term but belong to the block's own method
EXCEPT = {
    "ict": [r"volume[ -]imbalance", r"\bVI\b"],          # knowledge/04 section 2.22: an ICT body gap, not volume
    "heatmap": [r"liquidation", r"thanh lý"],
}

RULES = {
    "wyckoff":   {"forbidden": ICT_TERMS + LIQUIDITY_TERMS, "cs": [], "label": "ICT"},
    "footprint": {"forbidden": ICT_TERMS + LIQUIDITY_TERMS, "cs": [], "label": "ICT"},
    "ict":       {"forbidden": WYCKOFF_TERMS, "cs": [WYCKOFF_ACRONYMS], "label": "Wyckoff/volume"},
    "heatmap":   {"forbidden": WYCKOFF_TERMS_HEATMAP + [t for t in ICT_TERMS if t not in (r"\bICT\b", r"TTrades")],
                  "cs": [WYCKOFF_ACRONYMS], "label": "Wyckoff/ICT"},
    "synthesis": {"forbidden": [], "cs": [], "label": ""},
}
METHODS = tuple(RULES)


def strip(text):
    """Remove citation spans, tags and entities so only the author's own words are judged."""
    t = re.sub(r'<span class="cite">.*?</span>', " ", text or "", flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"&[a-z]+;", " ", t)


def violations(text, method):
    """[(pattern, snippet)] for every forbidden term found in `text` for `method`. Empty list = pure."""
    if method not in RULES:
        raise ValueError(f"unknown method {method!r}; expected one of {METHODS}")
    rule = RULES[method]
    t = strip(text)
    for ex in EXCEPT.get(method, []):
        t = re.sub(ex, " ", t, flags=re.I)
    out = []
    for pat in rule["forbidden"]:
        for m in re.finditer(pat, t, flags=re.I):
            out.append((pat, t[max(0, m.start() - 30):m.end() + 30].strip()))
    for pat in rule["cs"]:
        for m in re.finditer(pat, t):
            out.append((m.group(0), t[max(0, m.start() - 30):m.end() + 30].strip()))
    return out


def check_blocks(blocks):
    """blocks: {method: text or list of texts} -> {method: [(term, snippet), ...]} (only methods with violations)."""
    res = {}
    for method, texts in blocks.items():
        if isinstance(texts, str):
            texts = [texts]
        v = []
        for txt in texts:
            v += violations(txt, method)
        if v:
            res[method] = v
    return res


def infer_method(text):
    """Which single method a free-text label belongs to: 'wyckoff' | 'ict' | 'mixed' | 'neutral'."""
    has_ict = bool(violations(text, "wyckoff"))
    has_wyk = bool(violations(text, "ict"))
    if has_ict and has_wyk:
        return "mixed"
    if has_ict:
        return "ict"
    if has_wyk:
        return "wyckoff"
    return "neutral"


def report(res):
    lines = []
    for method, v in res.items():
        lines.append(f"{method}: {len(v)} forbidden term(s) ({RULES[method]['label']} vocabulary)")
        seen = set()
        for pat, snip in v:
            key = (pat, snip)
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"  - {pat}: …{snip}…")
    return "\n".join(lines)


def narrative_blocks(n3):
    """Every per-method text of one symbol's layer-3 narrative, grouped by method (for check_blocks)."""
    blocks = {"wyckoff": [], "ict": [], "footprint": [], "heatmap": []}
    if not n3:
        return blocks
    for m in blocks:
        sec = n3.get(m) or {}
        blocks[m] += [sec.get("text_html", "")] + [f"{L.get('label', '')} {L.get('short', '')}" for L in sec.get("levels", [])]
    wy = n3.get("wyckoff") or {}
    tr = wy.get("trading_range") or {}
    blocks["wyckoff"] += [e.get("label", "") for e in wy.get("events", [])] + [str(tr.get("high_label", "")), str(tr.get("low_label", ""))]
    ctx = n3.get("context") or {}
    cw = ctx.get("wyckoff") or {}
    ctr = cw.get("trading_range") or {}
    blocks["wyckoff"] += [cw.get("text_html", "")] + [e.get("label", "") for e in cw.get("events", [])] + [str(ctr.get("high_label", "")), str(ctr.get("low_label", ""))]
    blocks["ict"] += [(ctx.get("ict") or {}).get("text_html", "")]
    for r in n3.get("timeline", []) or []:
        blocks["wyckoff"].append(r.get("wyckoff", "")); blocks["ict"].append(r.get("ict", ""))
    return blocks


def model_blocks(l2):
    """Per-method blocks of one layer-2 model.html already split by build-artifact.layer2 / check-model-prose."""
    return {m: [l2.get(m, "")] for m in ("wyckoff", "ict", "footprint", "heatmap") if l2.get(m)}
