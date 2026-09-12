#!/usr/bin/env python3
"""Validate the Sonnet 'đánh giá cục bộ' files against the scanner facts (numbers-from-code guard) and the
one-method-one-vocabulary rule (scripts/method_purity.py).
Usage: check-model-prose.py <style> [--facts PATH]   (PATH = the snapshot facts.json printed by local-eval-brief.py)

Per symbol, data/live/prelim/<style>.<SYM>.model.html must contain, in this order:
  <div class="prelim-head">Đánh giá cục bộ (Sonnet) · dữ liệu tới HH:MM UTC · <strong>VERDICT</strong></div>
  <div class="m-wyckoff">…</div>      Wyckoff read, Wyckoff vocabulary only (price + volume)
  <div class="m-ict">…</div>          ICT read, ICT vocabulary only, no volume
  <div class="m-footprint">…</div>    optional, only when CoinGlass footprint data is AVAILABLE
  <div class="m-heatmap">…</div>      optional, only when CoinGlass heatmap data is AVAILABLE
  <div class="m-synth">…</div>        the combined read (de-duplication, verdict reasoning, invalidation) — any vocabulary
Checks: head timestamp equals the facts' last candle; verdict in the allowed set; a cite span in every block;
SETUP TIỀM NĂNG only if facts has a complete setup; every number with >= 3 significant digits appears among the
facts' numbers; every method block is pure.
Exit 0 = OK, 1 = structural failure, 2 = unknown numbers (fabrication risk), 3 = purity violation."""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import method_purity as mp   # noqa: E402
import numbers_guard as ng   # noqa: E402
import htf_context as htf    # noqa: E402

style = sys.argv[1]
VERDICTS = ("SETUP TIỀM NĂNG", "THEO DÕI LONG", "THEO DÕI SHORT", "CHỜ")
BLOCKS = ("wyckoff", "ict", "footprint", "heatmap", "synth")
facts_path = sys.argv[sys.argv.index("--facts") + 1] if "--facts" in sys.argv else f"{ROOT}/data/live/prelim/{style}.facts.json"
facts = json.load(open(facts_path, encoding="utf-8"))
print("facts:", facts_path, "| window_last", facts.get("window_last"))


def split_blocks(h):
    out = {}
    for m in BLOCKS:
        mm = re.search(rf'<div class="m-{m}">(.*?)</div>\s*(?=<div class="m-|$)', h, re.S)
        if mm:
            out[m] = mm.group(1).strip()
    return out


status, unknown_total = 0, 0
for sym, d in facts["symbols"].items():
    p = f"{ROOT}/data/live/prelim/{style}.{sym}.model.html"
    if not os.path.exists(p):
        print(f"{sym}: MISSING {p}"); status = max(status, 1); continue
    h = open(p, encoding="utf-8").read()
    hm = re.search(r'dữ liệu tới (\d\d:\d\d) UTC', h)
    want = d["last_time"][11:16]
    if not hm or hm.group(1) != want:
        print(f"{sym}: head timestamp {hm and hm.group(1)} != facts {want}"); status = max(status, 1)
    vm = re.search(r'<div class="prelim-head">.*?<strong>([^<]+)</strong>', h, re.S)
    verdict = vm.group(1).strip() if vm else None
    if verdict not in VERDICTS:
        print(f"{sym}: verdict '{verdict}' not in {VERDICTS}"); status = max(status, 1)
    blocks = split_blocks(h)
    for m in ("wyckoff", "ict", "synth"):
        if m not in blocks or not blocks[m]:
            print(f"{sym}: missing <div class=\"m-{m}\"> block"); status = max(status, 1)
        elif 'class="cite"' not in blocks[m]:
            print(f"{sym}: no cite span in m-{m}"); status = max(status, 1)
    su = d.get("setup") or {}
    if verdict == "SETUP TIỀM NĂNG" and not su.get("complete"):
        print(f"{sym}: SETUP TIỀM NĂNG but facts has no complete setup"); status = max(status, 1)
    allowed = ng.allowed_numbers(d) | {"1", "3", "15", "180", "288", "120", "240", "200"}
    unknown = ng.unknown_numbers(h, allowed)
    if unknown:
        print(f"{sym}: numbers not in facts: {unknown}"); unknown_total += len(unknown)
    ctx = d.get("context") if "context" in d else htf.load_context(style, sym)
    side = ((d.get("setup") or {}).get("side") or "").lower() or None
    for p_ in htf.check_verdict(verdict, side, ctx, blocks.get("synth", "")):
        print(f"{sym}: THANG KHUNG — {p_}"); status = max(status, 1)
    res = mp.check_blocks({m: v for m, v in blocks.items() if m != "synth"})
    if res:
        print(f"{sym}: PURITY\n{mp.report(res)}"); status = max(status, 3)
    if not unknown and not res and status < 1:
        print(f"{sym}: OK ({verdict})")
if unknown_total and status < 2:
    status = 2
print("RESULT:", {0: "OK", 1: "STRUCTURE FAIL", 2: "UNKNOWN NUMBERS", 3: "PURITY FAIL"}[status])
sys.exit(status)
