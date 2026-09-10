#!/usr/bin/env python3
"""Deterministic data patch for the chart artifacts (numbers from code, not from an agent's ad-hoc script).

Usage: patch-arrays.py <artifact.html> <style> [--snapshot-dir DIR]
  style: scalping (1m×180, BTC/ETH/SOL) | daytrade (15m×288) | swing (1D×120) | gold (15m×200, XAUUSD) | gold-swing (1D×120)

Patches ONLY: the candle arrays (`const BTC = [...]` etc.), the first `ranges` entry's low/high of each drawChart call,
the highest-index flag (the "hiện tại" marker) to the last bar, and the `.symbol-stats` numbers. Everything else is
left byte-identical. Reads candles from data/live/market-data (crypto) or data/live/mt5-bridge (MT5 symbols); with
--snapshot-dir the candles are copied there first so the page and the facts of that read agree.
Prints the last label per array and exits nonzero if any array/range/flag could not be patched."""
import json, os, re, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STYLES = {
    "scalping":   {"tf": "1m",  "n": 180, "label": "%H:%M",       "symbols": [("BTCUSDT", "BTC"), ("ETHUSDT", "ETH"), ("SOLUSDT", "SOL")]},
    "daytrade":   {"tf": "15m", "n": 288, "label": "%m-%d %H:%M", "symbols": [("BTCUSDT", "BTC"), ("ETHUSDT", "ETH"), ("SOLUSDT", "SOL")]},
    "swing":      {"tf": "1D",  "n": 120, "label": "%m-%d",       "symbols": [("BTCUSDT", "BTC"), ("ETHUSDT", "ETH"), ("SOLUSDT", "SOL")]},
    "gold":       {"tf": "15m", "n": 200, "label": "%m-%d %H:%M", "symbols": [("XAUUSD", "XAU")]},
    "gold-swing": {"tf": "1D",  "n": 120, "label": "%m-%d",       "symbols": [("XAUUSD", "XAU")]},
}
MT5 = {"XAUUSD", "XAGUSD", "USOIL", "UKOIL"}


def label(iso, fmt):
    import datetime
    return datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").strftime(fmt)


def fmt_like(v, sample):
    """Format v the way the page already formats numbers: detect decimals and separator style from `sample`."""
    nums = re.findall(r"[\d][\d.,]*", sample)
    ref = nums[-1] if nums else "0.00"
    en = bool(re.search(r"\.\d{1,2}$", ref)) or ("," in ref and "." not in ref and not re.search(r",\d{2}$", ref))
    dec = 2 if re.search(r"[.,]\d{2}$", ref) else 0
    s = f"{v:,.{dec}f}"
    return s if en else s.replace(",", "X").replace(".", ",").replace("X", ".")


def main():
    args = sys.argv[1:]
    snap = None
    if "--snapshot-dir" in args:
        i = args.index("--snapshot-dir"); snap = args[i + 1]; del args[i:i + 2]
    path, style = args[0], args[1]
    cfg = STYLES[style]; n = cfg["n"]; tf = cfg["tf"]
    h = open(path, encoding="utf-8").read(); orig = h
    ok = True
    for sym, var in cfg["symbols"]:
        src = f"{ROOT}/data/live/{'mt5-bridge' if sym in MT5 else 'market-data'}/ohlcv.{sym}.{tf}.json"
        rows = json.load(open(src))["candles"][-n:]
        if snap:
            os.makedirs(snap, exist_ok=True); shutil.copy(src, os.path.join(snap, f"ohlcv.{sym}.{tf}.json"))
        js = "const %s = [\n" % var + ",\n".join(f'  ["{label(r["time"], cfg["label"])}", {r["open"]}, {r["high"]}, {r["low"]}, {r["close"]}]' for r in rows) + "\n];"
        h, k = re.subn(rf"const {var} = \[.*?\];", lambda m: js, h, count=1, flags=re.S)
        if k != 1: print(f"{var}: array not found", file=sys.stderr); ok = False; continue
        lo, hi = min(r["low"] for r in rows), max(r["high"] for r in rows); last = rows[-1]["close"]
        # drawChart block for this symbol
        key = var.lower()
        m = re.search(rf"drawChart\('chart-{key}',\s*{var},\s*\{{(.*?)\n\s*\}}\);", h, re.S)
        if not m: print(f"{var}: drawChart block not found", file=sys.stderr); ok = False; continue
        block = m.group(0)
        nb, k1 = re.subn(r"(ranges\s*:\s*\[\s*\{[^}]*?low:\s*)[-\d.]+(\s*,\s*high:\s*)[-\d.]+", lambda mm: f"{mm.group(1)}{lo}{mm.group(2)}{hi}", block, count=1, flags=re.S)
        idxs = [(int(x.group(1)), x.span(1)) for x in re.finditer(r"\{i:\s*(\d+)", nb)]
        if idxs:
            mi, (a, b) = max(idxs, key=lambda t: t[0]); nb = nb[:a] + str(n - 1) + nb[b:]
        h = h.replace(block, nb, 1)
        if k1 != 1: print(f"{var}: ranges low/high not patched", file=sys.stderr); ok = False
        # symbol-stats: keep the prefix text, replace numbers
        sec = re.search(rf'<section class="symbol" id="sec-{key}">.*?<div class="symbol-stats"><span>([^<]*?): [^<]*</span><span>([^<]*?): [^<]*</span></div>', h, re.S)
        if sec:
            sample = re.search(r'<div class="symbol-stats">(.*?)</div>', sec.group(0), re.S).group(1)
            new = f'<div class="symbol-stats"><span>{sec.group(1)}: {fmt_like(lo, sample)}–{fmt_like(hi, sample)}</span><span>{sec.group(2)}: {fmt_like(last, sample)}</span></div>'
            h = h[:sec.start()] + re.sub(r'<div class="symbol-stats">.*?</div>', lambda _m: new, sec.group(0), count=1, flags=re.S) + h[sec.end():]
        else:
            print(f"{var}: symbol-stats not found (left unchanged)", file=sys.stderr)
        print(f"{var}: {label(rows[0]['time'], cfg['label'])} .. {label(rows[-1]['time'], cfg['label'])} ({len(rows)} rows) range {lo}-{hi} last {last}")
    if h != orig:
        open(path, "w", encoding="utf-8").write(h)
    # sanity: node parse of the script block
    scripts = re.findall(r"<script>(.*?)</script>", h, re.S)
    if scripts:
        tmp = path + ".check.js"; open(tmp, "w", encoding="utf-8").write("\n".join(scripts))
        rc = os.system(f"node --check '{tmp}' >/dev/null 2>&1"); os.remove(tmp)
        if rc != 0: print("node --check FAILED", file=sys.stderr); ok = False
    print("PATCH", "OK" if ok else "FAILED"); sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
