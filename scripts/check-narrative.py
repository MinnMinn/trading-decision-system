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
import wyckoff_rules as wr          # noqa: E402  -- reused deterministically (never re-derived by eye), per
                                     # docs/audits/2026-09-24-wyckoff-label-review.md P1.1/P2.1: "Values are
                                     # computed deterministically from the snapshot candles by reusing the
                                     # wyckoff_rules.py functions. They are not trusted from the model."
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
PRICE_RE = re.compile(r"(\d[\d,]*\.?\d*)")
RATIO_RE = re.compile(r"\d+(?:[.,]\d+)?\s*[x×]", re.I)
SOLE_VOLUME_RE = re.compile(r"(hợp lệ[^.<]*?(khối lượng|KL)\b|(khối lượng|KL)\b[^.<]*?hợp lệ|valid[^.<]*\bvolume\b|\bvolume\b[^.<]*valid)", re.I)

# đối nhãn (WA p150–159) records where ST[A] and the Phase-B tests sit in the TR's thirds -- see wyckoff_rules.py R3/R3b.
DOI_NHAN_SIGNS = ("supports", "neutral", "contradicts")
# P1.1/P2.1/P3.1 (docs/audits/2026-09-24-wyckoff-label-review.md): tokens whose confirming bar must exist in the
# candles up to `updated` (point-in-time, CLAUDE.md §8) before the label may drop its "?" candidate marker.
CONFIRM_TOKENS = ("SOS", "SOW", "LPS", "BU", "LPSY", "TEST")
# Phase C's / Phase D's own defining test event, mirroring the hard membership rule already enforced below
# (phase_grammar "Phase C has no test event" / "Phase D has no SOS/LPS/BU"). Kept as one named table so the two
# checks -- "member of the phase" and "confirmed enough to OPEN the phase" -- read the same vocabulary.
PHASE_OPENING_EVENTS = {"C": {"SPRING", "SHAKEOUT", "TEST", "LPS", "UTAD"}, "D": {"SOS", "SOW", "LPS", "LPSY", "BU"}}


def event_price(label):
    """First number in an event label -- the price the model wrote, e.g. 'Spring[C] 4,289.57' -> 4289.57.
    Used where a check compares the model's OWN number against a declared border, with no candle lookup needed
    (P1.2: a context Spring must sit beyond the context trading_range, using the narrative's own two numbers)."""
    m = PRICE_RE.search(label)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _avg(xs, i, n):
    w = xs[max(0, i - n):i]
    return sum(w) / len(w) if w else 0.0


def _label_confirmed(label):
    return not str(label or "").rstrip().endswith("?")


def sos_confirmed(rows, tr_hi, event_time, lookback=None, commit=None):
    """R11-style SOS/SOW confirmation (WA p83-85; scripts/wyckoff_rules.py R11), restricted by the caller to
    candles at or before the narrative's own `updated` (CLAUDE.md §8: never let a later candle confirm an
    earlier label). True = confirmed, False = refused (the candles up to `updated` disprove it), None = not
    enough completed candles yet past the event bar to know either way."""
    if tr_hi is None or not rows:
        return None
    lookback = wr.PARAMS["lookback"] if lookback is None else lookback
    commit = wr.COMMIT if commit is None else commit
    times = [r["time"] for r in rows]
    if event_time not in times:
        return None
    i = times.index(event_time)
    closes = [r["close"] for r in rows]; highs = [r["high"] for r in rows]; lows = [r["low"] for r in rows]; vols = [r.get("volume", 0) for r in rows]
    spread = [h - l for h, l in zip(highs, lows)]
    if closes[i] <= tr_hi or spread[i] < _avg(spread, i, lookback) or vols[i] < _avg(vols, i, lookback):
        return False
    for j in range(i, min(i + commit, len(closes))):
        if closes[j] <= tr_hi:
            return False
    if i + commit > len(closes):
        return None
    return True


def pullback_confirmed(rows, event_time, bearish=False):
    """Project simplification of R8/R11's pullback reclaim for LPS/BU/LPSY/Test (WA p84-85: the last supply
    'được hấp thụ mạnh và đẩy giá lên lại' -- demand pushes price back beyond the event bar). This is NOT a
    replica of wyckoff_rules.py R8/R11 (those need the SOS's own volume and the pullback zone test, which a
    single narrative event does not carry) -- it is a narrative-validation proxy: confirmed once a later
    candle's close moves back beyond the event bar's own high (accumulation-side: LPS/BU/Test) or low
    (distribution-side: LPSY, and a Test written on the short side)."""
    if not rows:
        return None
    times = [r["time"] for r in rows]
    if event_time not in times:
        return None
    i = times.index(event_time)
    highs = [r["high"] for r in rows]; lows = [r["low"] for r in rows]; closes = [r["close"] for r in rows]
    for j in range(i + 1, len(closes)):
        if bearish:
            if closes[j] < lows[i]:
                return True
        else:
            if closes[j] > highs[i]:
                return True
    return None if i == len(closes) - 1 else False


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
    # P3.1 (docs/audits/2026-09-24-wyckoff-label-review.md; WA p93/p161 own "?" notation): a "?"-suffixed event
    # is a CANDIDATE, not a confirmed one -- seen_confirmed excludes it, so it cannot by itself open Phase C/D.
    seen_confirmed = {}
    for e in wy.get("events") or []:
        lbl = str(e.get("label", "")); m = EVENT_TOKEN.match(lbl.strip())
        if not m:
            bad(pre + f"event label {lbl!r} does not start with a Wyckoff event name (PS/SC/AR/ST/UA/Spring/Shakeout/Test/LPS/SOS/BU · PSY/BC/UT/UTAD/SOW/LPSY · CHoBEV/CHoCH — knowledge/wyckoff/advance.md §2.6–2.8)"); continue
        tok = m.group(1).upper(); L = phase_at(e.get("time", ""))
        seen.setdefault(L, set()).add(tok)
        if _label_confirmed(lbl):
            seen_confirmed.setdefault(L, set()).add(tok)
        # An event OUTSIDE every phase band was silently unchecked: phase_at returns None, so the vocabulary
        # rule below never ran and the chart drew it anyway, as part of a structure it does not belong to.
        # Found 2026-09-19 from a reader's comment on the BTC bias chart: SOS 2026-09-03, ST 2026-09-04 and
        # UA 2026-09-09 were drawn alongside an SC of 2026-09-10 whose Phase A began that day -- three events
        # from an EARLIER range, rendered as one sequence, so the picture read SOS→ST→UA→SC→Spring. Wyckoff
        # does not run that way round: the SC opens the range that the ST retests and the SOS leaves
        # (knowledge/wyckoff/advance.md §2.7.1-§2.7.4). Two events above the declared AR made it plainer
        # still -- an ST retests the SC area, below the AR, by construction.
        if phases and L is None:
            bad(pre + f"event {lbl!r} at {e.get('time')} lies outside every phase band "
                      f"(the first begins {phases[0].get('from')}) — it belongs to a different structure and "
                      f"must not be drawn on this one (knowledge/wyckoff/advance.md §2.7)")
            continue
        if L and L not in EVENT_VOCAB.get(tok, PHASE_ORDER):
            bad(pre + f"event {lbl!r} sits in Phase {L} but {tok} belongs to Phase {'/'.join(EVENT_VOCAB[tok])} (knowledge/wyckoff/advance.md §2.7–2.8)")
        km = KL_RE.search(lbl)
        if tok in ("SOS", "SOW") and km and float(km.group(1).replace(",", ".")) < 1.0:
            bad(pre + f"event {lbl!r}: an {tok} is 'mở rộng chênh lệch giá và tăng khối lượng' (WA p83–84, knowledge/wyckoff/advance.md §2.7.4); on below-average "
                      f"volume a break above AR inside the range is UA (bull trap, WA p78/p88) — relabel, do not call it SOS")
    if "C" in letters and not (seen.get("C", set()) & PHASE_OPENING_EVENTS["C"]):
        bad(pre + "Phase C has no test event (Spring / Shakeout / Test / LPS[C] · UTAD) — Phase C is that test (knowledge/wyckoff/advance.md §2.7.3, WA p79–83)")
    elif "C" in letters and not (seen_confirmed.get("C", set()) & PHASE_OPENING_EVENTS["C"]):
        bad(pre + "Phase C's only test event is an unconfirmed '?' candidate — a '?' event cannot open a phase "
                  "(WA p93/p161 '?' notation; docs/audits/2026-09-24-wyckoff-label-review.md P3.1)")
    if "D" in letters and not (seen.get("D", set()) | seen.get("E", set())) & PHASE_OPENING_EVENTS["D"]:
        bad(pre + "Phase D has no SOS/LPS/BU (or SOW/LPSY) event — Phase D is 'cầu áp đảo cung' shown by SOS then LPS (knowledge/wyckoff/advance.md §2.7.4)")
    elif "D" in letters and not ((seen_confirmed.get("D", set()) | seen_confirmed.get("E", set())) & PHASE_OPENING_EVENTS["D"]):
        bad(pre + "Phase D's only qualifying event is an unconfirmed '?' candidate (e.g. 'SOS[D]?') — a '?' event "
                  "cannot open a phase (WA p93/p161 '?' notation; docs/audits/2026-09-24-wyckoff-label-review.md P3.1)")
    if "A" in letters and not (seen.get("A", set()) & {"SC", "BC", "BCLX"}):
        bad(pre + "Phase A has no SC (or BC) event — Phase A is the stopping action SC→AR→ST (knowledge/wyckoff/advance.md §2.7.1)")
    # The trading range and the phases must describe ONE structure. A range that starts before the structure
    # does, or after it, is two reads stitched together -- which is how the foreign events above got in.
    tr = wy.get("trading_range") or {}
    if phases and tr.get("from") and tr["from"] < phases[0].get("from", ""):
        # Only PREDATING is refused. A range stamped a bar or two AFTER Phase A opens is ordinary bookkeeping
        # -- the range is not drawable until the AR completes the SC/AR pair -- and flagging that would be
        # noise that gets ignored. A range that begins BEFORE its own stopping action cannot be the same
        # structure, and is how foreign events get stitched into a read.
        bad(pre + f"trading_range starts {tr['from']}, BEFORE Phase {letters[0]} at {phases[0].get('from')} — "
                  f"a range cannot predate the stopping action it is drawn from "
                  f"(knowledge/wyckoff/advance.md §2.7.1)")


def context_spring_checks(sym, cw, bad):
    """P1.2 (docs/audits/2026-09-24-wyckoff-label-review.md): a Spring/UTAD in the CONTEXT (higher-timeframe)
    read must actually breach the context trading_range border (WA p80 'giá dưới mức thấp nhất của Trading
    Range'). Checked from the narrative's own two numbers -- the event price and the declared border -- with no
    candle lookup: this is exactly the critique's concrete case (4H 'Spring 4,289.57' against a 4H TR low of
    4,285.91 the label itself never crosses)."""
    pre = f"{sym} (context): "
    tr = cw.get("trading_range") or {}
    lo, hi = tr.get("low"), tr.get("high")
    for e in cw.get("events") or []:
        lbl = str(e.get("label", "")); m = EVENT_TOKEN.match(lbl.strip())
        if not m:
            continue
        tok = m.group(1).upper(); px = event_price(lbl)
        if px is None:
            continue
        if tok == "SPRING" and lo is not None and px >= lo:
            bad(pre + f"event {lbl!r}: a context-timeframe Spring must trade below the context trading_range low "
                      f"({lo}) — WA p80; this bar's own recorded price never crosses it "
                      f"(docs/audits/2026-09-24-wyckoff-label-review.md P1.2)")
        if tok == "UTAD" and hi is not None and px <= hi:
            bad(pre + f"event {lbl!r}: a context-timeframe UTAD must trade above the context trading_range high "
                      f"({hi}) — WA p101 mirror of WA p80 (docs/audits/2026-09-24-wyckoff-label-review.md P1.2)")


def doi_nhan_and_spring_checks(sym, wy, rows, synthesis_html, bad):
    """P1.1 (docs/audits/2026-09-24-wyckoff-label-review.md): every Spring/Shakeout event carries a volume_type
    (1/2/3) that AGREES with the ratio computed from candles (method.md A6: "Values are computed
    deterministically ... not trusted from the model"); wyckoff.doi_nhan.st_sign is recorded (WA p150, Dấu hiệu
    1); when it 'contradicts' (ST below SC), the phase may not sit past C without wyckoff.alternative (P6.1) AND
    the synthesis naming the contradiction; the Spring event bar's own close sits back above trading_range.low
    (WA p80's "đảo chiều để đóng trong Trading Range") -- a close still below it is refused (real invalidation
    at write time, not a rendering question), a close above trading_range.high in the SAME bar is a WARNING
    only (the book has no rule for a one-bar Spring-plus-breakout, docs/audits/2026-09-24-wyckoff-label-review.md
    §1(c) point 3)."""
    pre = f"{sym}: "
    tr = wy.get("trading_range") or {}
    tr_lo, tr_hi = tr.get("low"), tr.get("high")
    times = [r["time"] for r in rows] if rows else []
    closes = [r["close"] for r in rows] if rows else []
    vols = [r.get("volume", 0) for r in rows] if rows else []
    lookback = wr.PARAMS["lookback"]

    for e in wy.get("events") or []:
        lbl = str(e.get("label", "")); m = EVENT_TOKEN.match(lbl.strip())
        if not m:
            continue
        tok = m.group(1).upper()
        if tok not in ("SPRING", "SHAKEOUT"):
            continue
        vt = e.get("volume_type")
        if vt not in (1, 2, 3):
            bad(pre + f"event {lbl!r} needs volume_type (1/2/3, WMT Bảng 2.1 p049) — method.md A6 requires both "
                      f"the WA event class and the WMT volume type, recorded, not collapsed "
                      f"(docs/audits/2026-09-24-wyckoff-label-review.md P1.1)")
        etime = e.get("time")
        if etime in times:
            i = times.index(etime)
            av = _avg(vols, i, lookback)
            if av:
                ratio = vols[i] / av
                computed = 1 if ratio < wr.VOL["low_max_ratio"] else (3 if ratio > wr.VOL["high_min_ratio"] else 2)
                if vt in (1, 2, 3) and vt != computed:
                    bad(pre + f"event {lbl!r}: volume_type {vt} does not match the ratio computed from candles "
                              f"({ratio:.2f}× → type {computed}, WMT Bảng 2.1 p049) — not trusted from the model")
            if tr_lo is not None:
                close = closes[i]
                if close <= tr_lo:
                    bad(pre + f"event {lbl!r}: the Spring/Shakeout bar's own close ({close}) never came back above "
                              f"trading_range.low ({tr_lo}) — WA p80 requires the reversal to close back inside the "
                              f"range; this is not a Spring by definition at write time "
                              f"(docs/audits/2026-09-24-wyckoff-label-review.md P1.1)")
                elif tr_hi is not None and close > tr_hi:
                    print(f"{sym}: WARNING event {lbl!r} closed above trading_range.high ({tr_hi}) in the same bar "
                          f"— Spring and breakout in one bar, Phase C with no Test; the book has no rule for this "
                          f"case, so it is a warning, not a failure (docs/audits/2026-09-24-wyckoff-label-review.md §1(c))")

    doi_nhan = wy.get("doi_nhan") or {}
    st_sign = doi_nhan.get("st_sign")
    if wy.get("phases") or wy.get("events"):
        if st_sign not in DOI_NHAN_SIGNS:
            bad(pre + "wyckoff.doi_nhan.st_sign missing — ST[A] position against the SC/AR border must be "
                      "recorded (WA p150, đối nhãn Dấu hiệu 1; docs/audits/2026-09-24-wyckoff-label-review.md P1.1)")
        elif st_sign == "contradicts":
            phases = wy.get("phases") or []
            last_letter = None
            for ph in phases:
                mm = re.match(r"\s*(?:pha|phase)?\s*([A-Ea-e])\b", str(ph.get("label", "")), re.I)
                if mm:
                    last_letter = mm.group(1).upper()
            plain_syn = re.sub(r"<[^>]+>", " ", synthesis_html or "").lower()
            names_contradiction = any(k in plain_syn for k in ("mâu thuẫn", "contradiction"))
            if last_letter in ("D", "E") and not ((wy.get("alternative") or "").strip() and names_contradiction):
                bad(pre + "doi_nhan.st_sign is 'contradicts' (ST below SC, WA p150 — early sign of redistribution/"
                          "distribution) but the phase has advanced past C without wyckoff.alternative naming the "
                          "competing reading AND the synthesis stating the contradiction "
                          "(docs/audits/2026-09-24-wyckoff-label-review.md P1.1, P6.1; CLAUDE.md §19)")


def confirmation_grammar(sym, wy, rows, updated, bad):
    """P2.1/P3.1 (docs/audits/2026-09-24-wyckoff-label-review.md): an SOS/SOW must pass the R11-style
    deterministic test (sos_confirmed) and an LPS/BU/LPSY/Test must pass its pullback-reclaim proxy
    (pullback_confirmed), both computed ONLY from candles at or before `updated` (CLAUDE.md §8 point-in-time —
    never let a later candle confirm an earlier label). A token that fails, or cannot yet be told either way,
    must be written as a '?' candidate (WA p93/p161's own notation) or the check refuses it."""
    pre = f"{sym}: "
    if not rows:
        return
    rows_pit = [r for r in rows if r.get("time", "") <= updated]
    tr = wy.get("trading_range") or {}
    for e in wy.get("events") or []:
        lbl = str(e.get("label", "")); m = EVENT_TOKEN.match(lbl.strip())
        if not m:
            continue
        tok = m.group(1).upper()
        if tok not in CONFIRM_TOKENS:
            continue
        marked_unconfirmed = not _label_confirmed(lbl)
        if tok in ("SOS", "SOW"):
            ok = sos_confirmed(rows_pit, tr.get("high"), e.get("time"))
        else:
            ok = pullback_confirmed(rows_pit, e.get("time"), bearish=(tok == "LPSY"))
        if ok is False and not marked_unconfirmed:
            bad(pre + f"event {lbl!r} does not pass its confirmation test on the candles up to {updated} — write it "
                      f"as a candidate ending in '?' (WA p93/p161 '?' convention; "
                      f"docs/audits/2026-09-24-wyckoff-label-review.md P2.1/P3.1), or correct the read")
        elif ok is None and not marked_unconfirmed:
            bad(pre + f"event {lbl!r}: not enough completed candles since it printed to confirm it at {updated} — "
                      f"write it as a candidate ending in '?' until the confirming bars exist "
                      f"(docs/audits/2026-09-24-wyckoff-label-review.md P2.1/P3.1)")


def alternative_and_status_checks(sym, wy, bad):
    """P6.1/P6.2 (docs/audits/2026-09-24-wyckoff-label-review.md): wyckoff.alternative is a required short cited
    paragraph naming the competing reading (WA2-27: prepare BOTH scenarios at a border break); every phases[]
    item carries status 'tested' | 'hypothesis', and 'tested' requires that phase's own confirming event (per
    PHASE_OPENING_EVENTS) to exist AND be confirmed (no trailing '?') — anything else is a hypothesis
    (method.md A4: "a phase call that has not been tested ... must be reported as one")."""
    pre = f"{sym}: "
    if wy.get("phases") or wy.get("events"):
        if not (wy.get("alternative") or "").strip():
            bad(pre + "wyckoff.alternative missing — a short cited paragraph naming the competing reading is "
                      "required at every border read (WA2-27; docs/audits/2026-09-24-wyckoff-label-review.md P6.1)")
    events = wy.get("events") or []
    for ph in wy.get("phases") or []:
        status = ph.get("status")
        if status not in ("tested", "hypothesis"):
            bad(pre + f"phase {ph.get('label')!r} needs status 'tested' or 'hypothesis' (WA p166 warns against "
                      f"labelling mechanically; docs/audits/2026-09-24-wyckoff-label-review.md P6.2)")
            continue
        m = re.match(r"\s*(?:pha|phase)?\s*([A-Ea-e])\b", str(ph.get("label", "")), re.I)
        L = m.group(1).upper() if m else None
        required = PHASE_OPENING_EVENTS.get(L)
        if status == "tested" and required is not None:
            frm, to = ph.get("from", ""), ph.get("to")
            in_phase = [e for e in events if frm <= e.get("time", "") and (not to or e["time"] < to)]
            confirmed_tokens = set()
            for e in in_phase:
                mm = EVENT_TOKEN.match(str(e.get("label", "")).strip())
                if mm and _label_confirmed(e.get("label", "")):
                    confirmed_tokens.add(mm.group(1).upper())
            if not (confirmed_tokens & required):
                bad(pre + f"phase {ph.get('label')!r} is marked status 'tested' but its confirming event "
                          f"({'/'.join(sorted(required))}) is missing or still an unconfirmed '?' candidate "
                          f"(docs/audits/2026-09-24-wyckoff-label-review.md P6.2)")


def tick_volume_checks(sym, wy, cw, is_tick, bad):
    """P5.1 (docs/audits/2026-09-24-wyckoff-label-review.md): on a tick-volume feed, volume may not be the SOLE
    stated validator of an event ('hợp lệ vì khối lượng ...'), and every printed ratio must carry a tick marker
    so a reader cannot mistake it for real traded volume (WMT p131-133 flags tick-based Delta as unreliable;
    method.md §4.1/§6.3 extend the caution to plain volume on this project's tick feeds)."""
    if not is_tick:
        return
    pre = f"{sym}: "
    for label, text in ((f"wyckoff.text_html", wy.get("text_html", "")), (f"context.wyckoff.text_html", cw.get("text_html", ""))):
        if not text:
            continue
        if SOLE_VOLUME_RE.search(text):
            bad(pre + f"{label} validates an event by volume alone ('hợp lệ vì khối lượng ...') on a tick-volume "
                      f"feed — volume may be reported but must not be the sole deciding criterion "
                      f"(WMT p131-133; docs/audits/2026-09-24-wyckoff-label-review.md P5.1)")
        plain = re.sub(r"<[^>]+>", " ", text)
        for m in RATIO_RE.finditer(plain):
            window = plain[m.end():m.end() + 12]
            if "tick" not in window.lower():
                bad(pre + f"{label}: volume ratio {m.group(0)!r} has no '(tick)' marker on a tick-volume feed "
                          f"(docs/audits/2026-09-24-wyckoff-label-review.md P5.1)")


def event_window(wy, win):
    """(lo, hi) between which a Wyckoff event of `wy` may be dated. `win` is the scanner's working window
    (facts.window_first, facts.window_last). The upper bound is always the last candle (point-in-time: no event
    after the data). The lower bound is the START OF THE STRUCTURE when that predates the window --
    `trading_range.from`, else the earliest phase band -- because a range that opened before the window is
    still the range being read: 2026-09-20 the first headless daily-full could carry only Shakeout + BU for BTC
    (SC/AR 09-10 and the UA 15 min before the window were refused), and the shortfall was blamed on the model.
    chart.js drops what falls before its own window (idxOf -> -1), so an earlier event never draws wrongly."""
    lo, hi = win
    starts = []
    tr_from = ((wy or {}).get("trading_range") or {}).get("from")
    if tr_from: starts.append(tr_from)
    starts += [ph.get("from") for ph in ((wy or {}).get("phases") or []) if ph.get("from")]
    if lo and starts:
        lo = min([lo] + starts)
    return (lo, hi)


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
        ew = event_window(wy, win)   # structure origin .. last candle, not the bare scanner window (see event_window)
        for e in wy.get("events", []) or []:
            if not ISO.match(e.get("time", "")): bad(pre + f"event time {e.get('time')!r} not ISO")
            elif ew[0] and not (ew[0] <= e["time"] <= ew[1]): bad(pre + f"event {e.get('label')!r} at {e['time']} is outside the structure's span {ew[0]}..{ew[1]} (trading_range.from / first phase .. last candle)")
            if len(e.get("label", "")) > 34: bad(pre + f"event label too long for the chart: {e.get('label')!r}")
        for ph in wy.get("phases", []) or []:
            if not ISO.match(ph.get("from", "")): bad(pre + f"phase from {ph.get('from')!r} not ISO")
        phase_grammar(sym, wy, bad)
        cw = ((d.get("context") or {}).get("wyckoff") or {})
        if cw.get("phases") or cw.get("events"):
            phase_grammar(sym + " (context)", cw, bad)
            context_spring_checks(sym, cw, bad)   # P1.2
        rows_full = candles(sym, S["tf"], S["n"])
        doi_nhan_and_spring_checks(sym, wy, rows_full, d.get("synthesis_html", ""), bad)   # P1.1
        confirmation_grammar(sym, wy, rows_full, n.get("updated", ""), bad)                 # P2.1 / P3.1
        alternative_and_status_checks(sym, wy, bad)                                          # P6.1 / P6.2
        tick_volume_checks(sym, wy, cw, _ba.I.is_tick_volume(sym), bad)                       # P5.1
        # giảm khung (knowledge/wyckoff/advance.md §2.7, WA p93–96): the context read is mandatory when a context window exists, and the
        # working-timeframe verdict must respect the higher-timeframe structure
        if ctx_style:
            # A context read is mandatory for the methods still ANALYSED (CLAUDE.md §15), not only for the one
            # the preset trades: the brief asks for both and the page shows both, so requiring only the traded
            # one would let the displayed lane go unvalidated. The 2026-09-13 fix this replaces was right that
            # an unconditional demand is wrong -- a dimension with no live source is still not required, which
            # analysed_methods enforces. NOTE the deliberate asymmetry with the invalidation-owner check above:
            # that one stays ENGAGED, because a lane that cannot vote must not set the stop.
            analysed = htf.analysed_methods(style)
            ci = (d.get("context") or {}).get("ict") or {}
            if "wyckoff" in analysed:
                if not (cw.get("text_html") or "").strip() or 'class="cite"' not in cw.get("text_html", ""):
                    bad(pre + "context.wyckoff.text_html missing or uncited — the higher-timeframe Wyckoff read is mandatory (giảm khung, knowledge/wyckoff/advance.md §2.7)")
                if not (cw.get("structure") or cw.get("phase")):
                    bad(pre + "context.wyckoff needs structure + phase (or structure 'chưa xác lập') so the bias can be derived")
                if (cw.get("phase") or "").upper()[:1] == "B" and not ((cw.get("trading_range") or {}).get("high") and (cw.get("trading_range") or {}).get("low")):
                    bad(pre + "context.wyckoff is Phase B but has no trading_range {high, low} — the boundary rule (WA p93, p201) needs the higher-timeframe AR / SC-ST levels")
            if "ict" in analysed and not (ci.get("text_html") or "").strip():
                bad(pre + "context.ict.text_html missing — the higher-timeframe ICT read is mandatory")
            ctx_facts_sym = ((ctx_facts.get("symbols") or {}).get(sym) or {})
            # P4.1/P4.2 (docs/audits/2026-09-24-wyckoff-label-review.md): the two HTF readings are checked
            # SEPARATELY here (unlike the ENGAGED-only bias_of() a few lines below, which is what the verdict is
            # graded against) so a disagreement between the two ANALYSED context lanes is never silently
            # dropped just because only one of them is engaged for this style's market.
            if "wyckoff" in analysed and "ict" in analysed and (cw.get("text_html") or "").strip() and (ci.get("text_html") or "").strip():
                if not (wy.get("nesting") or "").strip():
                    bad(pre + "wyckoff.nesting missing — where the working-timeframe range sits inside the "
                              "higher-timeframe one must be recorded whenever a context read exists (WA2-19/20; "
                              "docs/audits/2026-09-24-wyckoff-label-review.md P4.2)")
                cw_wy = {"structure": cw.get("structure"), "phase": cw.get("phase"), "trading_range": cw.get("trading_range")}
                wy_ctx_bias, _ = htf.wyckoff_bias(cw_wy, ctx_facts_sym)
                ict_ctx_bias, _ = htf.ict_bias(ctx_facts_sym)
                if wy_ctx_bias in ("long", "short") and ict_ctx_bias in ("long", "short") and wy_ctx_bias != ict_ctx_bias:
                    plain_syn = re.sub(r"<[^>]+>", " ", d.get("synthesis_html", "") or "").lower()
                    names_both = "wyckoff" in plain_syn and "ict" in plain_syn
                    names_contradiction = any(k in plain_syn for k in ("mâu thuẫn", "contradiction"))
                    if not (names_both and names_contradiction):
                        bad(pre + f"context Wyckoff ({wy_ctx_bias}) and ICT ({ict_ctx_bias}) bias disagree but the "
                                  f"synthesis does not name both methods and state the Contradiction "
                                  f"(CLAUDE.md §19; method.md §4.2 item 3; "
                                  f"docs/audits/2026-09-24-wyckoff-label-review.md P4.1)")
            # ENGAGED, deliberately -- the bias this verdict is checked against must rest on the methods that
            # may qualify a trade, never on the wider analysed set (§18). The two sets are named apart here so
            # a future edit cannot swap one for the other by accident.
            bias, basis = htf.bias_of({"structure": cw.get("structure"), "phase": cw.get("phase"), "trading_range": cw.get("trading_range")},
                                      ctx_facts_sym, methods=htf.engaged_methods(style))
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
        allowed_sym = set(allowed) | ng.candle_numbers(rows_full)
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
