#!/usr/bin/env python3
"""Insert/refresh the automatic read blocks in an artifact HTML file.
Usage: inject-prelim.py <artifact.html> <style>   (style = scalping | daytrade | swing)

Composes, per symbol, <div class="prelim" id="prelim-<sym>"> from three code-owned pieces:
  1. data/live/prelim/<style>.<SYM>.html        scanner snippet: head + FACTS table (+ scanner prose, see below)
  2. data/live/prelim/<style>.<SYM>.model.html  optional 'đánh giá cục bộ' prose written by the Sonnet local read;
                                                spliced at the <!--MODEL--> placeholder, shown with its own timestamp
  3. data/live/prelim/<style>.meta.json         meta-strip window / current state (verdict if anchors exist, else stance)
Display policy (decided 2026-09-10): scalping shows the scanner prose ('nhận định sơ bộ'); daytrade and swing show
only the facts table + model prose (scanner prose stripped) because at 15m/1D the Sonnet local read replaces it.
Idempotent: re-running only refreshes the blocks and the meta-strip."""
import re, sys, os, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
path, style = sys.argv[1], sys.argv[2]
SHOW_SCANNER_PROSE = {"scalping": True, "daytrade": False, "swing": False}.get(style, True)
h = open(path, encoding="utf-8").read()
CSS = """
  .prelim{ border-left:3px solid var(--accent); background:var(--surface-2); border-radius:6px; padding:10px 14px; font-size:13.5px; color:var(--ink); }
  .prelim-head{ font-family:var(--mono); font-size:10.5px; letter-spacing:.08em; text-transform:uppercase; color:var(--accent-ink); margin-bottom:6px; }
  .prelim p{ margin:0 0 6px; } .prelim .prelim-scan p:last-child{ margin-bottom:0; color:var(--ink-muted); font-size:12.5px; }
  .prelim table.facts{ width:100%; border-collapse:collapse; margin:4px 0 8px; font-size:12.5px; }
  .prelim table.facts th{ text-align:left; white-space:nowrap; padding:3px 8px 3px 0; color:var(--ink-muted); font-weight:600; vertical-align:top; width:1%; }
  .prelim table.facts td{ padding:3px 0; font-variant-numeric:tabular-nums; }
  .prelim .facts-note{ color:var(--ink-muted); font-size:11.5px; margin:0 0 8px; }
  .prelim-model{ border-top:1px dashed var(--line); padding-top:8px; margin:8px 0; }
  .prelim-model .prelim-head{ color:var(--ink); }
"""
if ".prelim{" not in h:
    h = h.replace("</style>", CSS + "</style>", 1)
elif "table.facts" not in h:
    h = h.replace("</style>", CSS + "</style>", 1)
for sym, key in (("BTCUSDT", "btc"), ("ETHUSDT", "eth"), ("SOLUSDT", "sol")):
    snippet_path = f"{ROOT}/data/live/prelim/{style}.{sym}.html"
    if not os.path.exists(snippet_path):
        continue
    snippet = open(snippet_path, encoding="utf-8").read().strip()
    model_path = f"{ROOT}/data/live/prelim/{style}.{sym}.model.html"
    model = open(model_path, encoding="utf-8").read().strip() if os.path.exists(model_path) else ""
    snippet = snippet.replace("<!--MODEL-->", f'<div class="prelim-model">{model}</div>' if model else "")
    if not SHOW_SCANNER_PROSE:
        snippet = re.sub(r'<div class="prelim-scan">.*?</div>', "", snippet, count=1, flags=re.S)
        snippet = snippet.replace("Nhận định sơ bộ tự động", "Số liệu tự động (scanner)", 1)
    block = f'<div class="prelim" id="prelim-{key}">{snippet}</div>'
    if f'id="prelim-{key}"' in h:
        h = re.sub(rf'<div class="prelim" id="prelim-{key}">.*?</div>(?=\s*<div class="table-wrap">)', lambda _m: block, h, count=1, flags=re.S)
    else:
        m = re.search(rf'(<section class="symbol" id="sec-{key}">.*?<div class="legend legend-ict">.*?</div>\n)', h, re.S)
        if not m:
            print(f"WARN: no legend-ict found for {key}", file=sys.stderr); continue
        h = h[:m.end()] + "    " + block + "\n" + h[m.end():]
meta_path = f"{ROOT}/data/live/prelim/{style}.meta.json"
if os.path.exists(meta_path):
    m = json.load(open(meta_path, encoding="utf-8"))
    def hhmm(t): return t[11:16]
    def dmy(t): return f"{int(t[8:10])}/{int(t[5:7])}"
    if style == "swing":
        win = f"{dmy(m['window_first'])} – {dmy(m['window_last'])}/{m['window_last'][:4]}"
    else:
        f_, l_ = m["window_first"], m["window_last"]
        win = f"{hhmm(f_)} – {hhmm(l_)} UTC, {dmy(l_)}" if f_[:10] == l_[:10] else f"{dmy(f_)} {hhmm(f_)} – {dmy(l_)} {hhmm(l_)} UTC"
    short = {"BTCUSDT": "BTC", "ETHUSDT": "ETH", "SOLUSDT": "SOL"}
    def state_of(v):
        vd = v.get("verdict_short") or v.get("verdict")
        return (vd.split(" — ")[0] if vd else v["stance"]) + (f" ({v['setup']})" if v.get("setup") else "")
    stances = " · ".join(f"{short[k]} {state_of(v)}" for k, v in m["symbols"].items())
    pcts = " · ".join(f"{short[k]} {v['pct']*100:.0f}%" for k, v in m["symbols"].items())
    dim = f"{pcts} của range · dữ liệu tới {hhmm(m['window_last'])} UTC"
    h = re.sub(r'(<div class="meta-label">Cửa sổ</div><div class="meta-value">[^<]*</div><div class="meta-value dim">)[^<]*(</div>)',
               lambda mm: mm.group(1) + win + mm.group(2), h, count=1)
    h = re.sub(r'(<div class="meta-label">Trạng thái hiện tại</div><div class="meta-value">)[^<]*(</div><div class="meta-value dim">)[^<]*(</div>)',
               lambda mm: mm.group(1) + stances + mm.group(2) + dim + mm.group(3), h, count=1)
    h = re.sub(r'(<div class="meta-label">)Sự kiện chính(</div>)', r'\1Sự kiện chính (theo phân tích đầy đủ gần nhất)\2', h, count=1)
    print("meta-strip refreshed:", win, "|", stances)
open(path, "w", encoding="utf-8").write(h)
print("prelim injected:", sum(1 for k in ("btc","eth","sol") if f'id="prelim-{k}"' in h), "of 3")
