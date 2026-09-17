#!/usr/bin/env python3
"""Validate a layer-3 narrative file (data/live/narrative/<style>.json) before it is rendered or published.

Usage: check-narrative.py <style> [--narrative PATH] [--facts PATH] [--ctx-facts PATH] [--snapshot-dir DIR]

Checks (schema: docs/architecture/schemas/narrative.schema.json):
  structure   required keys, verdict set, invalidation owner, ISO times, events inside the working window, cites present
  purity      every per-method text/label through scripts/method_purity.py (one method, one vocabulary)
  numbers     every >=3-digit number in prose exists in: the style's facts, the context style's facts, or the OHLCV values
              of the two candle windows (snapshot copies when --snapshot-dir is given, else the live files)
  anchors     every trading_range price and every ICT level price in the narrative is also a level in
              data/live/anchors.<style>.json (the scanner compares against anchors — the two files must agree)
Exit 0 = OK, 1 = structure, 2 = unknown numbers, 3 = purity violation. Prints RESULT: OK on success.
"""
import importlib.util, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import method_purity as mp          # noqa: E402
import numbers_guard as ng          # noqa: E402
_spec = importlib.util.spec_from_file_location("build_artifact", os.path.join(ROOT, "scripts", "build-artifact.py"))
_ba = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_ba)
STYLES = _ba.STYLES
VERDICTS = ("SETUP TIỀM NĂNG", "THEO DÕI LONG", "THEO DÕI SHORT", "CHỜ")
import htf_context as htf              # noqa: E402
import methods as _M                   # noqa: E402

OWNERS = _M.invalidation_owners()      # docs/architecture/methods.json is the one list; never hand-keep it here
CTX_STYLE = {k: v for k, v in htf.CONTEXT_STYLE.items() if v}
ISO = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

# ---- Wyckoff phase grammar (knowledge/wyckoff/advance.md §2.7–2.8, WA p71–86 / p101–112). Encoded as hard rules because on
# 2026-09-11 a full analysis labelled ETH "A → C → D": no Phase B, a Phase C without any test event, and an "SOS"
# on 0.99× volume that the book would call UA. Vocabulary and phase membership are the book's; the volume floor for
# SOS/SOW is the book's own definition ("mở rộng chênh lệch giá và tăng khối lượng", WA p83–84).
PHASE_ORDER = "ABCDE"
EVENT_VOCAB = {  # canonical event token -> allowed phases (accumulation / distribution share letters)
    "PS": "A", "SC": "A", "AR": "AB", "ST": "AB", "UA": "B", "MSOW": "B", "MSOS": "B",
    "SPRING": "C", "SHAKEOUT": "C", "TEST": "CD", "LPS": "CD", "SOS": "DE", "BU": "D",
    "PSY": "A", "BC": "A", "BCLX": "A", "UT": "B", "UTAD": "C", "SOW": "DE", "LPSY": "CD",
    "CHOBEV": "ABCDE", "CHOCH": "ABCDE",   # change-of-behaviour markers, WA p67–71 / knowledge/wyckoff/advance.md §2.6 — any phase
}
EVENT_TOKEN = re.compile(r"^(PS|SC|AR|ST|UA|mSOW|mSOS|Spring|Shakeout|Test|LPS|SOS|BU|PSY|BC|BCLX|UT|UTAD|SOW|LPSY|CHoBEV|CHoCH)\b", re.I)
KL_RE = re.compile(r"KL\s*([0-9]+(?:[.,][0-9]+)?)\s*[x×]", re.I)


def phase_grammar(sym, wy, bad):
    """Structure rules a Wyckoff read cannot violate. Every failure cites the section it comes from."""
    pre = f"{sym}: "
    phases = wy.get("phases") or []
    letters = []
    for ph in phases:
        m = re.match(r"\s*(?:pha|phase)?\s*([A-Ea-e])\b", str(ph.get("label", "")), re.I)
        if not m:
            bad(pre + f"phase label {ph.get('label')!r} must start with the letter A–E (knowledge/wyckoff/advance.md §2.7)"); return
        letters.append(m.group(1).upper())
    if phases:
        want = PHASE_ORDER[:len(letters)]
        if "".join(letters) != want:
            bad(pre + f"phases are {'→'.join(letters)}; Wyckoff phases are contiguous from A ({'→'.join(want)}): Phase C tests the cause built in "
                      f"Phase B and cannot exist without it (knowledge/wyckoff/advance.md §2.7.2–2.7.3, WA p77–80); Phase D needs a completed Phase C test (§2.7.4)")
        for a, b in zip(phases, phases[1:]):
            if a.get("to") and a["to"] != b.get("from"):
                bad(pre + f"phase {a.get('label')!r} ends at {a['to']} but the next phase starts at {b.get('from')} — phases must be contiguous in time")
            if b.get("from", "") < a.get("from", ""):
                bad(pre + "phases are not in chronological order")
        if wy.get("phase") and wy["phase"].upper() != letters[-1]:
            bad(pre + f"wyckoff.phase is {wy['phase']!r} but the last phase band is {letters[-1]!r}")
    # events: vocabulary, membership, volume floor for SOS/SOW
    def phase_at(t):
        cur = None
        for ph, L in zip(phases, letters):
            if ph.get("from", "") <= t and (not ph.get("to") or t < ph["to"]):
                cur = L
        return cur
    seen = {}
    for e in wy.get("events") or []:
        lbl = str(e.get("label", "")); m = EVENT_TOKEN.match(lbl.strip())
        if not m:
            bad(pre + f"event label {lbl!r} does not start with a Wyckoff event name (PS/SC/AR/ST/UA/Spring/Shakeout/Test/LPS/SOS/BU · PSY/BC/UT/UTAD/SOW/LPSY · CHoBEV/CHoCH — knowledge/wyckoff/advance.md §2.6–2.8)"); continue
        tok = m.group(1).upper(); L = phase_at(e.get("time", ""))
        seen.setdefault(L, set()).add(tok)
        if L and L not in EVENT_VOCAB.get(tok, PHASE_ORDER):
            bad(pre + f"event {lbl!r} sits in Phase {L} but {tok} belongs to Phase {'/'.join(EVENT_VOCAB[tok])} (knowledge/wyckoff/advance.md §2.7–2.8)")
        km = KL_RE.search(lbl)
        if tok in ("SOS", "SOW") and km and float(km.group(1).replace(",", ".")) < 1.0:
            bad(pre + f"event {lbl!r}: an {tok} is 'mở rộng chênh lệch giá và tăng khối lượng' (WA p83–84, knowledge/wyckoff/advance.md §2.7.4); on below-average "
                      f"volume a break above AR inside the range is UA (bull trap, WA p78/p88) — relabel, do not call it SOS")
    if "C" in letters and not (seen.get("C", set()) & {"SPRING", "SHAKEOUT", "TEST", "LPS", "UTAD"}):
        bad(pre + "Phase C has no test event (Spring / Shakeout / Test / LPS[C] · UTAD) — Phase C is that test (knowledge/wyckoff/advance.md §2.7.3, WA p79–83)")
    if "D" in letters and not (seen.get("D", set()) | seen.get("E", set())) & {"SOS", "SOW", "LPS", "LPSY", "BU"}:
        bad(pre + "Phase D has no SOS/LPS/BU (or SOW/LPSY) event — Phase D is 'cầu áp đảo cung' shown by SOS then LPS (knowledge/wyckoff/advance.md §2.7.4)")
    if "A" in letters and not (seen.get("A", set()) & {"SC", "BC", "BCLX"}):
        bad(pre + "Phase A has no SC (or BC) event — Phase A is the stopping action SC→AR→ST (knowledge/wyckoff/advance.md §2.7.1)")



def arg(flag, default=None):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def main():
    style = sys.argv[1]
    S = STYLES[style]
    path = arg("--narrative", f"{ROOT}/data/live/narrative/{style}.json")
    snap = arg("--snapshot-dir")
    facts = json.load(open(arg("--facts", f"{ROOT}/data/live/prelim/{style}.facts.json"), encoding="utf-8"))
    ctx_style = CTX_STYLE.get(style)
    ctx_facts_path = arg("--ctx-facts", f"{ROOT}/data/live/prelim/{ctx_style}.facts.json" if ctx_style else None)
    ctx_facts = json.load(open(ctx_facts_path, encoding="utf-8")) if ctx_facts_path and os.path.exists(ctx_facts_path) else {}
    anchors = json.load(open(f"{ROOT}/data/live/anchors.{style}.json", encoding="utf-8")) if os.path.exists(f"{ROOT}/data/live/anchors.{style}.json") else {}
    try:
        n = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        print(f"cannot read {path}: {e}"); print("RESULT: STRUCTURE FAIL"); sys.exit(1)
    status = 0
    problems = []

    def bad(msg):
        problems.append(msg)

    if n.get("style") != style: bad(f"style is {n.get('style')!r}, expected {style!r}")
    if not ISO.match(n.get("updated", "")): bad("updated is not an ISO Z timestamp")
    if n.get("mode") not in ("NORMAL", "ENHANCED", "STRICT"): bad(f"mode {n.get('mode')!r}")
    if not (n.get("headline") or {}).get("text"): bad("headline.text missing")
    win = (facts.get("window_first"), facts.get("window_last"))
    allowed = ng.allowed_numbers(facts, ctx_facts) | {"1", "3", "15", "180", "288", "120", "240", "200"}

    def candles(sym, tf, nn):
        import glob as _g
        cands = ([os.path.join(snap, f"ohlcv.{sym}.{tf}.json")] + sorted(_g.glob(os.path.join(snap, "local-eval-*", f"ohlcv.{sym}.{tf}.json")), reverse=True)) if snap else []
        src = next((c for c in cands if os.path.exists(c)), f"{ROOT}/data/live/{'mt5-bridge' if sym in _ba.MT5 else 'market-data'}/ohlcv.{sym}.{tf}.json")
        return json.load(open(src, encoding="utf-8"))["candles"][-nn:]

    unknown_total = 0
    for sym, key, disp, kind in S["syms"]:
        d = n.get("symbols", {}).get(sym)
        if not d: bad(f"{sym}: missing"); continue
        pre = f"{sym}: "
        if d.get("verdict") not in VERDICTS: bad(pre + f"verdict {d.get('verdict')!r} not in {VERDICTS}")
        su = ((facts.get("symbols") or {}).get(sym) or {}).get("setup") or {}
        if d.get("verdict") == "SETUP TIỀM NĂNG" and not su.get("complete"): bad(pre + "SETUP TIỀM NĂNG but facts has no complete setup")
        inv = d.get("invalidation")
        if inv and inv.get("owner") not in OWNERS: bad(pre + f"invalidation.owner {inv.get('owner')!r}")
        # The invalidation level is what sizing and stop management use (.claude/skills/ict-skill/SKILL.md §"one
        # invalidation owner"). A disengaged method may not own it, or a switched-off read still sets the stop.
        if inv and inv.get("owner") in OWNERS and inv["owner"] not in htf.engaged_methods(style):
            bad(pre + f"invalidation.owner is {inv['owner']!r} but that dimension is off in /automation — the stop would be owned by a method this run does not read")
        for m in ("wyckoff", "ict"):
            t = (d.get(m) or {}).get("text_html", "")
            if not t.strip(): bad(pre + f"{m}.text_html empty")
            elif 'class="cite"' not in t: bad(pre + f"{m}.text_html has no <span class=\"cite\">")
        if not (d.get("synthesis_html") or "").strip(): bad(pre + "synthesis_html empty")
        wy = d.get("wyckoff") or {}
        for e in wy.get("events", []) or []:
            if not ISO.match(e.get("time", "")): bad(pre + f"event time {e.get('time')!r} not ISO")
            elif win[0] and not (win[0] <= e["time"] <= win[1]): bad(pre + f"event {e.get('label')!r} at {e['time']} is outside the working window {win[0]}..{win[1]}")
            if len(e.get("label", "")) > 34: bad(pre + f"event label too long for the chart: {e.get('label')!r}")
        for ph in wy.get("phases", []) or []:
            if not ISO.match(ph.get("from", "")): bad(pre + f"phase from {ph.get('from')!r} not ISO")
        phase_grammar(sym, wy, bad)
        cw = ((d.get("context") or {}).get("wyckoff") or {})
        if cw.get("phases") or cw.get("events"):
            phase_grammar(sym + " (context)", cw, bad)
        # giảm khung (knowledge/wyckoff/advance.md §2.7, WA p93–96): the context read is mandatory when a context window exists, and the
        # working-timeframe verdict must respect the higher-timeframe structure
        if ctx_style:
            # A context read is mandatory only for the methods /automation has ENGAGED. Requiring the Wyckoff one
            # unconditionally made an ICT-only narrative impossible to validate, which is the method switch leaking
            # back in through the validator (user decision 2026-09-13).
            engaged = htf.engaged_methods(style)
            ci = (d.get("context") or {}).get("ict") or {}
            if "wyckoff" in engaged:
                if not (cw.get("text_html") or "").strip() or 'class="cite"' not in cw.get("text_html", ""):
                    bad(pre + "context.wyckoff.text_html missing or uncited — the higher-timeframe Wyckoff read is mandatory (giảm khung, knowledge/wyckoff/advance.md §2.7)")
                if not (cw.get("structure") or cw.get("phase")):
                    bad(pre + "context.wyckoff needs structure + phase (or structure 'chưa xác lập') so the bias can be derived")
                if (cw.get("phase") or "").upper()[:1] == "B" and not ((cw.get("trading_range") or {}).get("high") and (cw.get("trading_range") or {}).get("low")):
                    bad(pre + "context.wyckoff is Phase B but has no trading_range {high, low} — the boundary rule (WA p93, p201) needs the higher-timeframe AR / SC-ST levels")
            if "ict" in engaged and not (ci.get("text_html") or "").strip():
                bad(pre + "context.ict.text_html missing — the higher-timeframe ICT read is mandatory")
            ctx_facts_sym = ((ctx_facts.get("symbols") or {}).get(sym) or {})
            bias, basis = htf.bias_of({"structure": cw.get("structure"), "phase": cw.get("phase"), "trading_range": cw.get("trading_range")},
                                      ctx_facts_sym, methods=engaged)
            side = (su.get("side") or "").lower() or None
            for p_ in htf.check_verdict(d.get("verdict"), side, {"tf": htf.STYLE_TF.get(ctx_style, "?"), "bias": bias}, d.get("synthesis_html", "")):
                bad(pre + p_)
        # anchors consistency
        aprices = {L["price"] for L in ((anchors.get("symbols") or {}).get(sym) or {}).get("levels", [])}
        tr = wy.get("trading_range") or {}
        for k in ("high", "low"):
            if tr.get(k) is not None and tr[k] not in aprices: bad(pre + f"trading_range.{k} {tr[k]} is not a level in anchors.{style}.json")
        for L in (d.get("ict") or {}).get("levels", []) or []:
            if L.get("price") not in aprices: bad(pre + f"ict level {L.get('label')!r} {L.get('price')} is not a level in anchors.{style}.json")
        # purity
        res = mp.check_blocks(mp.narrative_blocks(d))
        if res:
            status = max(status, 3); print(f"{sym}: PURITY\n{mp.report(res)}")
        # numbers
        allowed_sym = set(allowed) | ng.candle_numbers(candles(sym, S["tf"], S["n"]))
        for _t in (S["tiers"] or {}).values():
            if not _t: continue
            try: allowed_sym |= ng.candle_numbers(candles(sym, _t["tf"], _t["n"]))
            except FileNotFoundError: pass
        texts = [(f"{m}.text_html", (d.get(m) or {}).get("text_html", "")) for m in ("wyckoff", "ict", "footprint", "heatmap")]
        texts += [("synthesis_html", d.get("synthesis_html", "")), ("lookback_html", d.get("lookback_html", ""))]
        texts += [(f"event {e.get('label')!r}", e.get("label", "")) for e in wy.get("events", []) or []]
        texts += [(f"timeline {r.get('time')}", " ".join(str(r.get(k, "")) for k in ("event", "wyckoff", "ict"))) for r in d.get("timeline", []) or []]
        ctx = d.get("context") or {}
        texts += [("context.wyckoff", (ctx.get("wyckoff") or {}).get("text_html", "")), ("context.ict", (ctx.get("ict") or {}).get("text_html", ""))]
        texts += [(f"context event {e.get('label')!r}", e.get("label", "")) for e in (ctx.get("wyckoff") or {}).get("events", []) or []]
        for name, t in texts:
            u = ng.unknown_numbers(t, allowed_sym)
            if u: print(f"{sym}: numbers not in facts/candles in {name}: {u}"); unknown_total += len(u)
        if not [p for p in problems if p.startswith(pre)] and not res: print(f"{sym}: OK ({d.get('verdict')})")
    for p in problems: print("STRUCTURE:", p)
    if problems: status = max(status, 1)
    if unknown_total and status < 2: status = 2
    print("RESULT:", {0: "OK", 1: "STRUCTURE FAIL", 2: "UNKNOWN NUMBERS", 3: "PURITY FAIL"}[status])
    sys.exit(status)


if __name__ == "__main__":
    main()
