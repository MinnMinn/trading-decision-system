#!/usr/bin/env python3
"""Numbers-from-code guard shared by check-model-prose.py (layer 2) and check-narrative.py (layer 3).

allowed_numbers(obj) walks any JSON-like object and returns the set of digit-strings a model may quote: every number
in several rounded/fixed-decimal forms, percentages (x100), and the HH:MM / MM-DD HH:MM forms of ISO timestamps.
unknown_numbers(text, allowed) returns the >=3-digit numbers in `text` (citations and tags stripped) not in the set.
"""
import re


def digits(x):
    s = f"{x}"
    s = s.rstrip("0").rstrip(".") if "." in s else s
    return re.sub(r"[^0-9]", "", s)


def collect(o, acc):
    if isinstance(o, dict):
        for v in o.values():
            collect(v, acc)
    elif isinstance(o, list):
        for v in o:
            collect(v, acc)
    elif isinstance(o, bool):
        return
    elif isinstance(o, (int, float)):
        acc.add(digits(o)); acc.add(digits(round(o, 2))); acc.add(digits(round(o, 1))); acc.add(digits(round(o)))
        acc.add(re.sub(r"[^0-9]", "", f"{o:.2f}")); acc.add(re.sub(r"[^0-9]", "", f"{o:.1f}"))
        acc.add(digits(round(o * 100, 1))); acc.add(digits(round(o * 100)))
        acc.add(re.sub(r"[^0-9]", "", f"{o * 100:.1f}")); acc.add(re.sub(r"[^0-9]", "", f"{o * 100:.0f}"))
    elif isinstance(o, str) and re.match(r"\d{4}-\d\d-\d\dT", o):
        acc.add(o[11:16].replace(":", "")); acc.add(o[5:16].replace("-", "").replace("T", "").replace(":", ""))
        acc.add(o[8:10].lstrip("0") + o[5:7].lstrip("0"))          # d/m as written in Vietnamese prose (10/9)
        acc.add(o[:4]); acc.add(o[:10].replace("-", ""))            # the year, and the full date
    elif isinstance(o, str):
        for t in re.findall(r"\d[\d.,]*\d|\d", o):
            acc.add(re.sub(r"[^0-9]", "", t))


def allowed_numbers(*objs):
    acc = set()
    for o in objs:
        collect(o, acc)
    return acc


def candle_numbers(rows):
    """Every OHLCV value of a candle window, plus the window's volume mean and per-bar ratios (2 dp), plus timestamps."""
    acc = set()
    vols = [r.get("volume", 0) for r in rows]
    avg = sum(vols) / len(vols) if vols else 0
    for r in rows:
        collect([r["open"], r["high"], r["low"], r["close"], r.get("volume", 0), r["time"]], acc)
        if avg:
            collect(round(r.get("volume", 0) / avg, 2), acc)
    return acc


def unknown_numbers(text, allowed, min_digits=3):
    prose = re.sub(r'<span class="cite">.*?</span>', "", text or "", flags=re.S)
    prose = re.sub(r"<[^>]+>", " ", prose)
    nums = re.findall(r"\d[\d.,]*\d|\d", prose)
    return sorted({t for t in nums if len(re.sub(r"[^0-9]", "", t)) >= min_digits
                   and re.sub(r"[^0-9]", "", t) not in allowed and not re.match(r"^\d\d:\d\d$", t)})
