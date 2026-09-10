#!/usr/bin/env python3
"""Validate the Sonnet 'đánh giá cục bộ' files against the scanner facts (numbers-from-code guard).
Usage: check-model-prose.py <style> [--strict]
Checks per symbol: file exists; head with 'dữ liệu tới HH:MM UTC' equal to the facts' last candle; a verdict in the
allowed set; at least one <span class="cite">; SETUP TIỀM NĂNG only if facts has a complete setup; every number
with >= 3 significant digits in the prose must appear among the facts' numbers (compared as digit strings).
Exit 0 = OK, 1 = structural failure, 2 = unknown numbers (fabrication risk)."""
import json, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
style = sys.argv[1]
VERDICTS = ("SETUP TIỀM NĂNG", "THEO DÕI LONG", "THEO DÕI SHORT", "CHỜ")
facts = json.load(open(f"{ROOT}/data/live/prelim/{style}.facts.json", encoding="utf-8"))


def digits(x):
    s = f"{x}"; s = s.rstrip("0").rstrip(".") if "." in s else s
    return re.sub(r"[^0-9]", "", s)


def collect(o, acc):
    if isinstance(o, dict):
        for v in o.values(): collect(v, acc)
    elif isinstance(o, list):
        for v in o: collect(v, acc)
    elif isinstance(o, (int, float)) and not isinstance(o, bool):
        acc.add(digits(o)); acc.add(digits(round(o, 2))); acc.add(digits(round(o, 1))); acc.add(digits(round(o)))
        acc.add(digits(round(o * 100, 1))); acc.add(digits(round(o * 100)))  # pct as %
    elif isinstance(o, str) and re.match(r"\d{4}-\d\d-\d\dT", o):
        acc.add(o[11:16].replace(":", "")); acc.add(o[5:16].replace("-", "").replace("T", "").replace(":", ""))


status, unknown_total = 0, 0
for sym, d in facts["symbols"].items():
    p = f"{ROOT}/data/live/prelim/{style}.{sym}.model.html"
    if not os.path.exists(p): print(f"{sym}: MISSING {p}"); status = max(status, 1); continue
    h = open(p, encoding="utf-8").read()
    hm = re.search(r'dữ liệu tới (\d\d:\d\d) UTC', h)
    want = d["last_time"][11:16]
    if not hm or hm.group(1) != want: print(f"{sym}: head timestamp {hm and hm.group(1)} != facts {want}"); status = max(status, 1)
    vm = re.search(r"<strong>([^<]+)</strong>", h); verdict = vm.group(1).strip() if vm else None
    if verdict not in VERDICTS: print(f"{sym}: verdict '{verdict}' not in {VERDICTS}"); status = max(status, 1)
    if 'class="cite"' not in h: print(f"{sym}: no cite span"); status = max(status, 1)
    su = d.get("setup") or {}
    if verdict == "SETUP TIỀM NĂNG" and not su.get("complete"): print(f"{sym}: SETUP TIỀM NĂNG but facts has no complete setup"); status = max(status, 1)
    allowed = set(); collect(d, allowed); allowed |= {"1", "3", "15", "180", "288", "120"}
    prose = re.sub(r'<span class="cite">.*?</span>', "", h, flags=re.S)
    prose = re.sub(r"<[^>]+>", " ", prose)
    nums = re.findall(r"\d[\d.,]*\d|\d", prose)
    unknown = sorted({t for t in nums if len(re.sub(r'[^0-9]', '', t)) >= 3 and re.sub(r"[^0-9]", "", t) not in allowed and not re.match(r"^\d\d:\d\d$", t)})
    if unknown: print(f"{sym}: numbers not in facts: {unknown}"); unknown_total += len(unknown)
    else: print(f"{sym}: OK ({verdict})")
if unknown_total and status == 0: status = 2
print("RESULT:", "OK" if status == 0 else ("STRUCTURE FAIL" if status == 1 else "UNKNOWN NUMBERS"))
sys.exit(status)
