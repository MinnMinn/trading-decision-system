#!/usr/bin/env python3
"""Insert/refresh the deterministic 'Nhận định sơ bộ' blocks in an artifact HTML file.
Usage: inject-prelim.py <artifact.html> <style>   (style = scalping | daytrade | swing)
Reads data/live/prelim/<style>.<SYM>.html (written by scripts/ict-scan.py) and places each into
<div class="prelim" id="prelim-<sym>"> right after that symbol's ICT legend. Idempotent."""
import re, sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
path, style = sys.argv[1], sys.argv[2]
h = open(path, encoding="utf-8").read()
CSS = """
  .prelim{ border-left:3px solid var(--accent); background:var(--surface-2); border-radius:6px; padding:10px 14px; font-size:13.5px; color:var(--ink); }
  .prelim-head{ font-family:var(--mono); font-size:10.5px; letter-spacing:.08em; text-transform:uppercase; color:var(--accent-ink); margin-bottom:6px; }
  .prelim p{ margin:0 0 6px; } .prelim p:last-child{ margin-bottom:0; color:var(--ink-muted); font-size:12.5px; }
"""
if ".prelim{" not in h:
    h = h.replace("</style>", CSS + "</style>", 1)
for sym, key in (("BTCUSDT", "btc"), ("ETHUSDT", "eth"), ("SOLUSDT", "sol")):
    snippet_path = f"{ROOT}/data/live/prelim/{style}.{sym}.html"
    if not os.path.exists(snippet_path):
        continue
    snippet = open(snippet_path, encoding="utf-8").read().strip()
    block = f'<div class="prelim" id="prelim-{key}">{snippet}</div>'
    if f'id="prelim-{key}"' in h:
        h = re.sub(rf'<div class="prelim" id="prelim-{key}">.*?</div>(?=\s*<div class="table-wrap">)', block, h, count=1, flags=re.S)
    else:
        # insert after the ICT legend of this symbol's section
        m = re.search(rf'(<section class="symbol" id="sec-{key}">.*?<div class="legend legend-ict">.*?</div>\n)', h, re.S)
        if not m:
            print(f"WARN: no legend-ict found for {key}", file=sys.stderr); continue
        h = h[:m.end()] + "    " + block + "\n" + h[m.end():]
# meta-strip: window + current state are deterministic -> refresh them from the scanner's meta.json
meta_path = f"{ROOT}/data/live/prelim/{style}.meta.json"
if os.path.exists(meta_path):
    import json
    m = json.load(open(meta_path, encoding="utf-8"))
    def hhmm(t): return t[11:16]
    def dmy(t): return f"{int(t[8:10])}/{int(t[5:7])}"
    if style == "swing":
        win = f"{dmy(m['window_first'])} – {dmy(m['window_last'])}/{m['window_last'][:4]}"
    else:
        f_, l_ = m["window_first"], m["window_last"]
        win = f"{hhmm(f_)} – {hhmm(l_)} UTC, {dmy(l_)}" if f_[:10] == l_[:10] else f"{dmy(f_)} {hhmm(f_)} – {dmy(l_)} {hhmm(l_)} UTC"
    short = {"BTCUSDT": "BTC", "ETHUSDT": "ETH", "SOLUSDT": "SOL"}
    stances = " · ".join(f"{short[k]} {v['stance']}" for k, v in m["symbols"].items())
    pcts = " · ".join(f"{short[k]} {v['pct']*100:.0f}%" for k, v in m["symbols"].items())
    dim = f"{pcts} của range · dữ liệu tới {hhmm(m['window_last'])} UTC"
    h = re.sub(r'(<div class="meta-label">Cửa sổ</div><div class="meta-value">[^<]*</div><div class="meta-value dim">)[^<]*(</div>)',
               lambda mm: mm.group(1) + win + mm.group(2), h, count=1)
    h = re.sub(r'(<div class="meta-label">Trạng thái hiện tại</div><div class="meta-value">)[^<]*(</div><div class="meta-value dim">)[^<]*(</div>)',
               lambda mm: mm.group(1) + stances + mm.group(2) + dim + mm.group(3), h, count=1)
    # key-event cell: mark that it comes from the last full analysis, not the data tick
    h = re.sub(r'(<div class="meta-label">)Sự kiện chính(</div>)', r'\1Sự kiện chính (theo phân tích đầy đủ gần nhất)\2', h, count=1)
    print("meta-strip refreshed:", win, "|", stances)
open(path, "w", encoding="utf-8").write(h)
print("prelim injected:", sum(1 for k in ("btc","eth","sol") if f'id="prelim-{k}"' in h), "of 3")
