#!/usr/bin/env python3
"""Render a chart artifact page from code (user decisions 2026-09-11: overview window, volume on the Wyckoff chart,
layers 1/2/3 each split per method then synthesised, one method = one vocabulary, trader-grade UI).

Usage: build-artifact.py <style> --out FILE [--snapshot-dir DIR] [--narrative PATH] [--check-only] [--allow-impure]
  style: scalping | daytrade | 1h | 4h | swing | gold | gold-1h | gold-4h | gold-swing

Inputs (all read-only here; each has exactly one writer elsewhere):
  data/live/market-data|mt5-bridge/ohlcv.<SYM>.<tf>.json   working window AND the context (HTF) window   (launchd scanner / MT5 EA)
  data/live/prelim/<style>.facts.json (+ .meta.json)         layer 1, đánh giá sơ bộ                       (scripts/ict-scan.py)
  data/live/prelim/<style>.<SYM>.model.html                  layer 2, đánh giá cục bộ, per-method blocks    (Sonnet local read)
  data/live/narrative/<style>.json                           layer 3, đánh giá toàn diện, structured        (Sonnet full analysis)
  data/live/anchors.<style>.json                             named levels the scanner compares against      (full analysis)
  docs/architecture/analysis-params.json                     project volume/spread parameters
  docs/architecture/automation-config.json                   which dimensions are switched on per market

Rules enforced here, not by convention:
  * numbers from code — every price/volume/% on the page is computed from the candle files or copied from facts.json;
    the models' prose is inserted verbatim and was already validated by scripts/check-model-prose.py;
  * one method, one vocabulary — every per-method block (layers 2 and 3, chart flag labels, timeline cells) is run
    through scripts/method_purity.py; any violation aborts the build (exit 2) unless --allow-impure;
  * events are addressed by candle time (ISO), never by array index, so a sliding window cannot detach a label.
Exit codes: 0 built, 1 usage/input error, 2 purity violation.
"""
import argparse, datetime, html, json, os, re, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import method_purity as mp  # noqa: E402
import artifact_theme as theme  # noqa: E402

CRYPTO = [("BTCUSDT", "btc", "BTC/USDT", "int"), ("ETHUSDT", "eth", "ETH/USDT", "2"), ("SOLUSDT", "sol", "SOL/USDT", "2")]
GOLD = [("XAUUSD", "xau", "XAU/USD", "2")]
MT5 = {"XAUUSD", "XAGUSD", "USOIL", "UKOIL"}
TF_MIN = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "1H": 60, "2H": 120, "4H": 240, "1D": 1440, "1W": 10080}
# working window = the style's own (tf, n, label); ctx = the higher-timeframe overview drawn above it.
# The 1h/4h sizes are project parameters (scripts/local-eval-brief.py TF map) -- kept identical here.
STYLES = {
    "scalping":   dict(tf="1m",  n=180, lbl="%H:%M",       ctx=("15m", 288, "%m-%d %H:%M"), syms=CRYPTO, name="Crypto Scalping",       horizon="1m × 180 (3 giờ)", ctx_h="15m × 288 (3 ngày)", kz=False),
    "daytrade":   dict(tf="15m", n=288, lbl="%m-%d %H:%M", ctx=("4H", 180, "%m-%d %H:%M"),  syms=CRYPTO, name="Crypto Day",    horizon="15m × 288 (3 ngày)", ctx_h="4H × 180 (30 ngày)", kz=True),
    "1h":         dict(tf="1H",  n=240, lbl="%m-%d %H:%M", ctx=("1D", 120, "%m-%d"),        syms=CRYPTO, name="Crypto 1H",             horizon="1H × 240 (10 ngày)", ctx_h="1D × 120 (4 tháng)", kz=True),
    "4h":         dict(tf="4H",  n=180, lbl="%m-%d %H:%M", ctx=("1D", 120, "%m-%d"),        syms=CRYPTO, name="Crypto 4H",             horizon="4H × 180 (30 ngày)", ctx_h="1D × 120 (4 tháng)", kz=False),
    "swing":      dict(tf="1D",  n=120, lbl="%m-%d",       ctx=("1W", 104, "%y-%m-%d"),     syms=CRYPTO, name="Crypto Swing",  horizon="1D × 120 (4 tháng)", ctx_h="1W × 104 (2 năm)", kz=False),
    "gold-scalp": dict(tf="5m",  n=288, lbl="%m-%d %H:%M", ctx=("15m", 288, "%m-%d %H:%M"), syms=GOLD,   name="CFD Scalping",          horizon="5m × 288 (24 giờ)", ctx_h="15m × 288 (3 ngày)", kz=True),
    "gold":       dict(tf="15m", n=288, lbl="%m-%d %H:%M", ctx=("4H", 180, "%m-%d %H:%M"),  syms=GOLD,   name="CFD Day",              horizon="15m × 288 (3 ngày)", ctx_h="4H × 180 (30 ngày)", kz=True),
    "gold-1h":    dict(tf="1H",  n=240, lbl="%m-%d %H:%M", ctx=("1D", 120, "%m-%d"),        syms=GOLD,   name="CFD 1H",                   horizon="1H × 240 (10 ngày)", ctx_h="1D × 120 (4 tháng)", kz=True),
    "gold-4h":    dict(tf="4H",  n=180, lbl="%m-%d %H:%M", ctx=("1D", 120, "%m-%d"),        syms=GOLD,   name="CFD 4H",                   horizon="4H × 180 (30 ngày)", ctx_h="1D × 120 (4 tháng)", kz=False),
    "gold-swing": dict(tf="1D",  n=120, lbl="%m-%d",       ctx=("1W", 104, "%y-%m-%d"),     syms=GOLD,   name="CFD Swing",                horizon="1D × 120 (4 tháng)", ctx_h="1W × 104 (2 năm)", kz=False),
}
VERDICT_CLASS = [("SETUP", "setup"), ("THEO DÕI LONG", "long"), ("THEO DÕI SHORT", "short"), ("PHÁ", "warn"), ("CHỜ", "wait")]
# a style whose working window is another style's context window: the context chart reuses that narrative (one read per candle series)
import importlib.util as _iu
_as = _iu.spec_from_file_location("automation", os.path.join(ROOT, "scripts", "automation.py")); _auto = _iu.module_from_spec(_as); _as.loader.exec_module(_auto)
CTX_REUSE = {k: v for k, v in _auto.CONTEXT_STYLE.items() if v}
LANES = [("wyckoff", "Wyckoff"), ("ict", "ICT"), ("footprint", "Footprint"), ("heatmap", "Heatmap")]


# ----------------------------------------------------------------------------------------------- helpers
def esc(s):
    return html.escape(str(s), quote=True)


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def hhmm(iso):
    return iso[11:16] if iso else "—"


def dmy(iso):
    return f"{int(iso[8:10])}/{int(iso[5:7])}" if iso else "—"


def when(iso):
    return f"{dmy(iso)} {hhmm(iso)}Z" if iso else "—"


def label(iso, fmt):
    return datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").strftime(fmt)


def fmtn(v, kind):
    if v is None:
        return "—"
    return f"{v:,.0f}" if kind == "int" else f"{v:,.2f}"


def chip(text, extra=""):
    cls = "wait"
    for k, c in VERDICT_CLASS:
        if str(text).upper().startswith(k):
            cls = c
            break
    return f'<span class="chip chip-{cls}{(" " + extra) if extra else ""}">{esc(text)}</span>'


def candles(sym, tf, n, snap=None):
    src = f"{ROOT}/data/live/{'mt5-bridge' if sym in MT5 else 'market-data'}/ohlcv.{sym}.{tf}.json"
    d = json.load(open(src, encoding="utf-8"))
    if snap:
        os.makedirs(snap, exist_ok=True)
        shutil.copy(src, os.path.join(snap, f"ohlcv.{sym}.{tf}.json"))
    return d["candles"][-n:], d.get("last_updated"), d.get("_source")


def rows_js(rows, fmt):
    return "[" + ",".join(f'["{label(r["time"], fmt)}",{r["open"]},{r["high"]},{r["low"]},{r["close"]},{r.get("volume", 0)},"{r["time"]}"]' for r in rows) + "]"


# ----------------------------------------------------------------------------------------------- layer 1 (scanner facts -> per-method blocks, code-written)
def anchor_method(level):
    m = level.get("method")
    return m if m in ("wyckoff", "ict") else mp.infer_method(level.get("label", "") + " " + level.get("name", ""))


def level_line(L, kind):
    fb = L.get("first_close_beyond")
    s = f'<b>{esc(L["label"])}</b> {fmtn(L["price"], kind)} ({when(L.get("time"))}): nến đóng {"trên" if L["ref_vs"] == "above" else "dưới"} ({L["dist_pct"]:+.2f}%)'
    if fb:
        s += f' · nến đóng vượt đầu tiên {when(fb["time"])} @ {fmtn(fb["close"], kind)} · cực trị sau đó {fmtn(L.get("extreme_since"), kind)}'
    if L.get("forming_beyond"):
        s += " · nến đang hình thành hiện đang vượt"
    return s


def layer1(sym, d, kind, tf):
    """facts.json symbol entry -> dict(ts, stance, verdict, wyckoff, ict, synth) — all text written here, pure by construction."""
    an = d.get("anchors") or {}
    levels = an.get("levels") or []
    by = {"wyckoff": [], "ict": [], "mixed": [], "neutral": []}
    for L in levels:
        by[anchor_method(L)].append(L)
    # Wyckoff: named levels + volume outliers (effort)
    w = []
    for L in by["wyckoff"]:
        w.append(f"<li>{level_line(L, kind)}</li>")
    vol = [e for e in d.get("events_recent", []) if e.get("kind") == "volume"]
    if vol:
        w.append("<li>Khối lượng bất thường gần đây: " + "; ".join(
            f"<b>{e['mult']}×</b> trung bình lúc {hhmm(e['time'])}Z trên nến {'tăng' if e['dir'] == 'up' else 'giảm'}" for e in vol[-4:])
            + " — kiểm tra Nỗ lực–Kết quả trước khi tin vào hướng (bội số theo trung bình cửa sổ, tham số dự án).</li>")
    else:
        w.append("<li>Không có nến khối lượng bất thường trong các nến gần đây (ngưỡng: tham số dự án).</li>")
    w.append(f"<li>Biểu đồ khối lượng và đường trung bình 20 nến nằm dưới chart Wyckoff; nến ≥ ngưỡng cao được tô đậm.</li>")
    wyckoff = "<ul>" + "".join(w) + "</ul>"
    # ICT: range / EQ / MSS / FVG / pools / sweeps / setup
    zone = "discount" if d["pct"] < 0.5 else "premium"
    i = [f"<li>Giá {fmtn(d['last'], kind)} = <b>{d['pct'] * 100:.0f}%</b> dealing range cửa sổ ({fmtn(d['lo'], kind)}–{fmtn(d['hi'], kind)}), <b>{zone}</b>, EQ {fmtn(d['eq'], kind)}.</li>"]
    for L in by["ict"]:
        i.append(f"<li>{level_line(L, kind)}</li>")
    m = d.get("last_mss")
    if m:
        i.append(f"<li>MSS gần nhất: <b>{'tăng' if m['type'] == 'bull' else 'giảm'}</b>, đóng cửa vượt swing {fmtn(m['level'], kind)}.</li>")
    g = d.get("nearest_fvg")
    i.append(f"<li>FVG chưa lấp gần giá nhất: {'tăng' if g['type'] == 'bull' else 'giảm'} {fmtn(g['lo'], kind)}–{fmtn(g['hi'], kind)}.</li>" if g else "<li>Không có FVG chưa lấp gần giá.</li>")
    up = d.get("unswept_pools") or []
    if up:
        i.append("<li>Pool chưa quét: " + ", ".join(f"{p['kind']} {fmtn(p['level'], kind)}" for p in up[-6:]) + ".</li>")
    ev = [e for e in d.get("events_recent", []) if e.get("kind") in ("sweep", "erl_high", "erl_low", "mss_bull", "mss_bear")]
    if ev:
        def ev_s(e):
            if e["kind"] == "sweep":
                return f"quét {e['pool']} {fmtn(e['level'], kind)} @{hhmm(e['time'])}Z"
            if e["kind"].startswith("mss"):
                return f"MSS {'tăng' if e['kind'] == 'mss_bull' else 'giảm'} {fmtn(e['level'], kind)} @{hhmm(e['time'])}Z"
            return f"chạm ERL {'đỉnh' if e['kind'] == 'erl_high' else 'đáy'} {fmtn(e['level'], kind)} @{hhmm(e['time'])}Z"
        i.append("<li>Sự kiện gần đây: " + "; ".join(ev_s(e) for e in ev[-6:]) + ".</li>")
    su = d.get("setup")
    if su and su.get("complete"):
        i.append(f"<li><b>Setup ứng viên {su['side'].upper()}</b>: quét {su['sweep']['pool']} {fmtn(su['sweep']['level'], kind)} @{hhmm(su['sweep']['time'])}Z → MSS {fmtn(su['mss']['level'], kind)} @{hhmm(su['mss']['time'])}Z → FVG {fmtn(su['fvg']['lo'], kind)}–{fmtn(su['fvg']['hi'], kind)}{' đã lấp' if su['fvg'].get('mitigated') else ' chưa lấp'} · entry {fmtn(su['entry'], kind)} · stop {fmtn(su['stop'], kind)} · target {fmtn(su['target'], kind)} ({esc(su.get('target_kind', ''))}) · R = {su['R']} · {'discount' if su.get('in_discount') else 'premium'}.</li>")
    elif su:
        i.append(f"<li>Setup ứng viên {su['side'].upper()} chưa hoàn chỉnh: thiếu {esc(su.get('missing'))}.</li>")
    else:
        i.append("<li>Không có chuỗi quét → MSS cùng chiều trong các nến gần đây.</li>")
    ict = "<ul>" + "".join(i) + "</ul>"
    # synthesis: rule verdict vs anchors + stance + mixed/neutral levels
    s = []
    cx = d.get("context")
    if cx:
        w = cx.get("wyckoff") or {}
        s.append(f"<li><b>Bối cảnh {esc(cx.get('tf'))}</b> (scanner {esc(hhmm(cx.get('scanned_at')) if cx.get('scanned_at') else '—')}Z): "
                 + (f"cấu trúc {esc(w.get('structure'))}, pha {esc(w.get('phase') or '—')} (đọc {esc(str(w.get('updated'))[:16])}Z) · " if w else "chưa có đọc Wyckoff khung lớn · ")
                 + f"giá {fmtn(cx.get('last'), kind)} = {cx['pct'] * 100:.0f}% biên độ khung lớn · " if cx.get('pct') is not None else "")
        s[-1] += f"<b>bias {esc(cx.get('bias', '?').upper())}</b> — {esc(cx.get('basis', ''))}. <span class=\"cite\">[giảm khung: knowledge/07 §2.7, WA p93–96]</span></li>"
    if an.get("verdict"):
        rc = an.get("ref_close") or {}
        s.append(f"<li>Verdict theo luật so với mốc neo của phân tích đầy đủ gần nhất: <b>{esc(an['verdict'])}</b> (nến đóng {when(rc.get('time'))} = {fmtn(rc.get('close'), kind)}).</li>")
    else:
        s.append("<li>Chưa có mốc neo từ phân tích đầy đủ — scanner chỉ có stance theo luật cố định.</li>")
    for L in by["mixed"] + by["neutral"]:
        s.append(f"<li>Mốc neo (tổng hợp): {level_line(L, kind)}</li>")
    s.append(f"<li>Stance scanner: <b>{esc(d['stance'])}</b> — quét theo luật cố định (pivot 3 nến, dung sai đỉnh/đáy bằng nhau 0,08%, FVG ≥ 0,6× biên độ trung vị; tham số dự án), không phải nhận định của mô hình.</li>")
    synth = "<ul>" + "".join(s) + "</ul>"
    return dict(ts=d.get("last_time"), stance=d["stance"], verdict=(an.get("verdict_short") or an.get("verdict")), wyckoff=wyckoff, ict=ict, synth=synth)


# ----------------------------------------------------------------------------------------------- layer 2 (Sonnet local read, per-method blocks)
BLOCK_RE = {m: re.compile(rf'<div class="m-{m}">(.*?)</div>\s*(?=<div class="m-|$)', re.S) for m in ("wyckoff", "ict", "footprint", "heatmap", "synth")}


def layer2(style, sym):
    p = f"{ROOT}/data/live/prelim/{style}.{sym}.model.html"
    if not os.path.exists(p):
        return None
    h = open(p, encoding="utf-8").read()
    ts = re.search(r"dữ liệu tới (\d\d:\d\d) UTC", h)
    vd = re.search(r"<strong>([^<]+)</strong>", h)
    out = dict(ts=ts.group(1) if ts else None, verdict=vd.group(1).strip() if vd else None, legacy=False)
    body = re.sub(r'<div class="prelim-head">.*?</div>', "", h, count=1, flags=re.S)
    found = False
    for m, rx in BLOCK_RE.items():
        mm = rx.search(body)
        out[m] = mm.group(1).strip() if mm else ""
        found = found or bool(mm)
    if not found:          # pre-2026-09-11 flat prose: cannot be attributed to one method -> synthesis column, flagged
        out["legacy"] = True
        out["synth"] = body.strip()
    return out


# ----------------------------------------------------------------------------------------------- page pieces
def lane_status(engaged, reason):
    return "" if engaged else esc(reason)


def matrix(sym_key, kind, l1, l2, l3, dims):
    """The read matrix: rows = layers, columns = methods engaged + synthesis."""
    cols = ["wyckoff", "ict"] + [m for m in ("footprint", "heatmap") if dims[m]["engaged"]]
    head = '<div class="mx-head mx-corner">Lớp đọc</div>' + "".join(f'<div class="mx-head lane-{c}"><span class="lane-dot"></span>{dict(LANES)[c]}</div>' for c in cols) + '<div class="mx-head mx-synth">Tổng hợp</div>'

    def row(title, sub, cells, synth, cls=""):
        out = f'<div class="mx-label {cls}"><div class="mx-title">{title}</div><div class="mx-sub">{sub}</div></div>'
        for c in cols:
            out += f'<div class="mx-cell lane-{c} {cls}" data-col="{c}"><div class="mx-cell-tag">{dict(LANES)[c]}</div>{cells.get(c) or "<p class=\"muted\">—</p>"}</div>'
        out += f'<div class="mx-cell mx-synth {cls}" data-col="synth"><div class="mx-cell-tag">Tổng hợp</div>{synth}</div>'
        return out

    body = head
    # layer 1
    if l1:
        body += row("Sơ bộ", f"scanner · dữ liệu tới {hhmm(l1['ts'])}Z", {"wyckoff": l1["wyckoff"], "ict": l1["ict"]},
                    f'<div class="cell-verdict">{chip(l1["verdict"] or l1["stance"])}</div>{l1["synth"]}')
    else:
        body += row("Sơ bộ", "scanner", {}, '<p class="muted">Chưa có facts.json cho style này.</p>')
    # layer 2
    if l2 and not l2["legacy"]:
        cells = {c: l2.get(c if c != "synth" else "synth") for c in cols}
        body += row("Cục bộ", f"Sonnet · dữ liệu tới {l2['ts'] or '—'}Z", cells, f'<div class="cell-verdict">{chip(l2["verdict"] or "—")}</div>{l2["synth"]}')
    elif l2:
        body += row("Cục bộ", f"Sonnet · dữ liệu tới {l2['ts'] or '—'}Z · <em>định dạng cũ, chưa tách phương pháp</em>", {},
                    f'<div class="cell-verdict">{chip(l2["verdict"] or "—")}</div>{l2["synth"]}')
    else:
        body += row("Cục bộ", "Sonnet", {}, '<p class="muted">Chưa có đánh giá cục bộ.</p>')
    # layer 3
    if l3:
        wy = l3.get("wyckoff") or {}
        ic = l3.get("ict") or {}
        tr = wy.get("trading_range") or {}
        wcell = ""
        badges = [b for b in (wy.get("structure"), (f"Pha {wy['phase']}" if wy.get("phase") else None), wy.get("regime")) if b]
        if badges:
            wcell += '<div class="badges">' + "".join(f'<span class="badge">{esc(b)}</span>' for b in badges) + "</div>"
        if tr:
            wcell += f'<p class="kv"><span>{esc(tr.get("high_label", "đỉnh vùng"))}</span><b>{fmtn(tr.get("high"), kind)}</b><span>{esc(tr.get("low_label", "đáy vùng"))}</span><b>{fmtn(tr.get("low"), kind)}</b></p>'
        wcell += wy.get("text_html", "")
        icell = ""
        lv = ic.get("levels") or []
        if lv:
            icell += '<p class="kv">' + "".join(f"<span>{esc(L.get('label', ''))}</span><b>{fmtn(L.get('price'), kind)}</b>" for L in lv[:6]) + "</p>"
        icell += ic.get("text_html", "")
        cells = {"wyckoff": wcell, "ict": icell}
        for m in ("footprint", "heatmap"):
            if dims[m]["engaged"]:
                cells[m] = (l3.get(m) or {}).get("text_html", "")
        inv = l3.get("invalidation") or {}
        synth = f'<div class="cell-verdict">{chip(l3.get("verdict") or "—")}'
        if inv:
            synth += f' <span class="inv">vô hiệu: {esc(inv.get("rule", ""))} {fmtn(inv.get("level"), kind)} · chủ sở hữu <b>{esc(inv.get("owner", "?"))}</b></span>'
        synth += "</div>"
        if l3.get("lookback_html"):
            synth += f'<div class="sub-h">Nhìn lại</div>{l3["lookback_html"]}'
        synth += f'<div class="sub-h">Hiện tại</div>{l3.get("synthesis_html", "")}'
        body += row("Toàn diện", f"phân tích đầy đủ · {l3.get('_updated', '—')}", cells, synth)
    else:
        body += row("Toàn diện", "phân tích đầy đủ", {}, '<p class="muted">Chưa có phân tích đầy đủ theo định dạng mới (data/live/narrative/&lt;style&gt;.json).</p>')
    notes = [f'<b>{dict(LANES)[m]}</b>: {esc(dims[m]["reason"])}' for m in ("footprint", "heatmap") if not dims[m]["engaged"]]
    foot = f'<div class="mx-foot">{" · ".join(notes)}</div>' if notes else ""
    return f'<div class="matrix cols-{len(cols)}">{body}</div>{foot}'


def timeline(rows):
    if not rows:
        return ""
    trs = "".join(f"<tr><td>{esc(r.get('time', ''))}</td><td>{r.get('event', '')}</td><td class=\"lane-wyckoff\">{r.get('wyckoff', '')}</td><td class=\"lane-ict\">{r.get('ict', '')}</td></tr>" for r in rows)
    return f'<details class="timeline"><summary>Dòng sự kiện của phân tích đầy đủ <span class="muted">({len(rows)} mốc · Wyckoff và ICT ở hai cột riêng)</span></summary><div class="table-wrap"><table class="evidence"><thead><tr><th>Thời gian (UTC)</th><th>Sự kiện</th><th class="lane-wyckoff">Wyckoff</th><th class="lane-ict">ICT</th></tr></thead><tbody>{trs}</tbody></table></div></details>'


GLOSSARY = {
    "wyckoff": [("PS · SC · AR · ST", "Preliminary Support, Selling Climax (Cao trào bán), Automatic Rally, Secondary Test — bốn sự kiện Pha A của tích lũy; TR dựng từ đỉnh AR và đáy SC/ST (knowledge/07 §2.7)."),
                ("Spring / Shakeout / Test", "Pha C: cú xuyên xuống dưới TR rồi đóng lại bên trong; loại 1/2/3 theo khối lượng (knowledge/08 §2.6); Test là nhịp kiểm tra lại trên khối lượng thấp hơn."),
                ("SOS · LPS · BU", "Pha D: Sign of Strength (dấu hiệu sức mạnh), Last Point of Support (điểm hỗ trợ cuối), Back-Up (kiểm tra lại vùng phá vỡ)."),
                ("PSY · BC · UT · UTAD · SOW · LPSY", "Các sự kiện phân phối tương ứng; UT/UTAD chỉ dùng trong phân phối, UA chỉ trong tích lũy (WA p8, knowledge/07 §1.3)."),
                ("CHoBEV / CHoCH", "Ba CHoBEV tạo một CHoCH — cổng bắt buộc trước khi gán nhãn pha (knowledge/07 §2.6)."),
                ("Nỗ lực – Kết quả", "So biên độ nến với khối lượng: hài hoà = tiếp diễn, phân kỳ = cạn kiệt/hấp thụ (knowledge/07 §2.2, §4.1)."),
                ("Pha A–E", "Dừng xu hướng → xây nguyên nhân → kiểm tra → dấu hiệu → hiệu ứng; nhãn pha luôn kèm đối nhãn (knowledge/07 §2.11).")],
    "ict": [("BSL / SSL · ERL / IRL", "Buy-side / sell-side liquidity tại đỉnh/đáy bằng nhau; external vs internal range liquidity (knowledge/04 §2.6–2.7, knowledge/05 §2.13)."),
            ("Sweep vs MSS", "Quét thanh khoản = xuyên qua rồi đóng lại; Market Structure Shift = nến đóng cửa phá swing ngược chiều sau displacement (knowledge/04 §2.14, §2.17)."),
            ("Displacement · FVG", "Nến đẩy mạnh để lại Fair Value Gap (nến 1 và nến 3 không chồng nhau); FVG được vẽ tới khi lấp (knowledge/04 §2.16, §2.21)."),
            ("Order Block", "Nến ngược chiều cuối cùng trước displacement; đường OB = giá mở của nến đó, mean threshold = 0.5 thân; stop chặt = đáy thân (close), stop rộng = đáy cú quét (knowledge/05 §2.5, xác minh lại PDF 2026-09-12)."),
            ("CISD", "Change in State of Delivery: nến đóng qua giá mở của nến đầu tiên trong chuỗi nến ngược màu cuối cùng chạy vào mức; sớm hơn MSS (knowledge/05 §2.3, knowledge/06 §2.3)."),
            ("Dealing range · EQ · premium / discount", "Range = cặp BSL↔SSL chưa quét gần nhất (nơi thanh khoản đang nằm); EQ = 50%; mua ở discount, bán ở premium; khi không có cặp thì dùng biên cửa sổ và ghi rõ (knowledge/04 §2.18–2.19)."),
            ("PDH/PDL · PWH/PWL · phiên Á/London", "Đỉnh/đáy ngày, tuần trước và phiên là mức thanh khoản; râu xuyên rồi đóng lại = failure to displace (đóng khung đảo chiều), thân đóng qua = mức là draw (knowledge/04 §2.8–2.9, §2.12, §2.14). Ranh giới ngày (00Z) và phiên (session-model.md) là giả định dự án."),
            ("OTE · STD", "OTE: fib 1 tại gốc nhịp, 0 tại đỉnh/đáy nhịp, vùng vào 0.62–0.79, nhấn 0.705 (knowledge/04 §2.20). Std: 1 tại cực trị cú quét, 0 tại đỉnh/đáy tạo highest high/lowest low trước đó; −2/−2.5 vùng chốt, −4 mở rộng tối đa (knowledge/05 §2.12, knowledge/06 §2.1.5)."),
            ("Killzone", "Hai bộ giờ EST trong deck, không có luật cho crypto/CFD (knowledge/04 §2.1, §6). Trang vẽ theo docs/architecture/session-model.md: LDN 08–11 Europe/London, NY AM 08:30–11, NY PM 13:30–16 America/New_York, đổi UTC theo ngày; trọng số theo thị trường; không vẽ cuối tuần — tham số dự án.")],
    "footprint": [("POC · Imbalance · Stacked Imbalance", "Mức khối lượng lớn nhất trong nến; chênh lệch chéo bid/ask ≥ tỉ lệ theo công cụ (knowledge/08 §3.2)."),
                  ("Hấp thụ → Cạn kiệt → Phát triển", "Chuỗi đọc tại nến neo Spring/Upthrust (knowledge/08 §5 bước 5)."),
                  ("Delta / Cumulative Delta", "Phân kỳ mạnh/vừa/yếu/ẩn tại vị trí Spring hoặc UTAD (knowledge/08 §3.3).")],
    "heatmap": [("Cụm thanh lý", "Vùng giá tập trung lệnh thanh lý — mục tiêu hoặc điểm quét (master spec)."),
                ("Tường orderbook", "Thanh khoản nằm chờ tập trung; trùng cụm thanh lý thì tính là một quan sát.")],
}


def glossary():
    out = ""
    for key, name in LANES:
        items = "".join(f"<dt>{esc(t)}</dt><dd>{esc(d)}</dd>" for t, d in GLOSSARY[key])
        out += f'<div class="gl lane-{key}"><div class="gl-head"><span class="lane-dot"></span>{name}</div><dl>{items}</dl></div>'
    return f'<section class="glossary" id="sec-glossary"><h2>Thuật ngữ theo phương pháp</h2><div class="gl-grid">{out}</div></section>'


# ----------------------------------------------------------------------------------------------- CSS / JS
CSS = r"""
<style>
__TOKENS__
*{box-sizing:border-box}
html{scroll-behavior:smooth}
@media (prefers-reduced-motion: reduce){ html{scroll-behavior:auto} *{transition:none!important} }
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:14px;line-height:1.55;-webkit-font-smoothing:antialiased}
a{color:var(--accent)}
b,strong{font-weight:700}
.muted{color:var(--muted)}
.mono{font-family:var(--mono)}
.num{font-family:var(--mono);font-variant-numeric:tabular-nums}
.lane-wyckoff{--lane:var(--w);--lane-soft:var(--w-soft)} .lane-ict{--lane:var(--i);--lane-soft:var(--i-soft)}
.lane-footprint{--lane:var(--f);--lane-soft:var(--f-soft)} .lane-heatmap{--lane:var(--h);--lane-soft:var(--h-soft)}
.lane-dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--lane);margin-right:7px;vertical-align:1px}

/* top bar */
.topbar{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--surface) 92%,transparent);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
.topbar-in{max-width:1180px;margin:0 auto;padding:10px 20px;display:flex;align-items:center;gap:18px;flex-wrap:wrap}
.brand{display:flex;flex-direction:column;gap:1px;min-width:220px}
.brand-title{font-weight:800;font-size:15px;letter-spacing:-.01em}
.brand-sub{font-family:var(--mono);font-size:11px;color:var(--muted)}
.symnav{display:flex;gap:4px}
.symnav a{font-family:var(--mono);font-size:12px;font-weight:700;text-decoration:none;color:var(--ink-2);padding:6px 10px;border-radius:6px;border:1px solid transparent}
.symnav a:hover{background:var(--surface-2);border-color:var(--line)}
.lanes{display:flex;gap:2px;margin-left:auto;background:var(--surface-2);border:1px solid var(--line);border-radius:8px;padding:3px}
.lane-btn{font-family:var(--sans);font-weight:700;font-size:12.5px;padding:6px 12px;border-radius:6px;border:1px solid transparent;background:transparent;color:var(--muted);cursor:pointer;display:inline-flex;align-items:center;gap:7px}
.lane-btn .lane-dot{margin:0}
.lane-btn:hover{color:var(--ink)}
.lane-btn.active{background:var(--surface);color:var(--ink);border-color:var(--line-strong);box-shadow:0 1px 2px rgba(0,0,0,.08)}
.lane-btn:focus-visible,.symnav a:focus-visible,summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.lane-btn.off{opacity:.55}

.page{max-width:1180px;margin:0 auto;padding:22px 20px 80px;display:flex;flex-direction:column;gap:22px}
.lede{display:flex;justify-content:space-between;gap:24px;align-items:flex-end;flex-wrap:wrap}
h1{font-size:clamp(22px,3vw,30px);font-weight:800;letter-spacing:-.02em;margin:0;text-wrap:balance}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0 0 6px}
.lede p{margin:6px 0 0;color:var(--ink-2);max-width:66ch}
.disclaimer{font-family:var(--mono);font-size:11px;color:var(--warn);background:var(--warn-soft);padding:6px 10px;border-radius:6px;white-space:nowrap}

.meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));border:1px solid var(--line);border-radius:10px;background:var(--surface);overflow:hidden}
.meta > div{padding:12px 16px;border-right:1px solid var(--line)}
.meta > div:last-child{border-right:0}
.meta-l{font-family:var(--mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);margin-bottom:4px}
.meta-v{font-weight:700;font-size:13.5px}
.meta-d{font-family:var(--mono);font-size:11.5px;color:var(--muted);margin-top:2px}
.meta .chip{margin:0 0 0 4px}
.meta .st{display:inline-flex;align-items:center;white-space:nowrap;margin:2px 10px 2px 0}

section.symbol{background:var(--surface);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);padding:18px 20px 20px;display:flex;flex-direction:column;gap:14px;scroll-margin-top:64px}
.sym-head{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.sym-name{font-family:var(--mono);font-weight:800;font-size:20px;letter-spacing:-.01em}
.sym-last{font-family:var(--mono);font-size:20px;font-variant-numeric:tabular-nums}
.sym-kv{display:flex;gap:16px;font-family:var(--mono);font-size:12px;color:var(--muted);flex-wrap:wrap}
.sym-kv b{color:var(--ink-2);font-weight:600}
.sym-verdict{margin-left:auto;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.sym-verdict .lbl{font-family:var(--mono);font-size:11px;color:var(--faint)}

.chip{display:inline-flex;align-items:center;font-family:var(--mono);font-size:11px;font-weight:700;letter-spacing:.03em;padding:3px 9px;border-radius:999px;border:1px solid transparent;white-space:nowrap}
.chip-wait{background:var(--surface-3);color:var(--ink-2);border-color:var(--line-strong)}
.chip-long{background:var(--up-soft);color:var(--up);border-color:var(--up)}
.chip-short{background:var(--down-soft);color:var(--down);border-color:var(--down)}
.chip-setup{background:var(--w-soft);color:var(--w);border-color:var(--w)}
.chip-warn{background:var(--warn-soft);color:var(--warn);border-color:var(--warn)}
.chip-lg{font-size:12.5px;padding:5px 12px}

.charts{display:flex;flex-direction:column;gap:8px}
.chart-block{border:1px solid var(--line);border-radius:8px;background:var(--surface-2);position:relative}
.chart-title{display:flex;justify-content:space-between;align-items:center;padding:8px 12px 0;font-family:var(--mono);font-size:11px;color:var(--muted)}
.chart-title b{color:var(--ink-2);font-weight:600}
.zoom{display:inline-flex;align-items:center;gap:4px} .zoom .muted{margin-right:6px}
.zoom button{font-family:var(--mono);font-size:12px;font-weight:700;width:24px;height:22px;border-radius:5px;border:1px solid var(--line-strong);background:var(--surface);color:var(--ink-2);cursor:pointer;line-height:1}
.zoom button:hover{background:var(--surface-3)} .zoom button:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
svg.chart{cursor:crosshair} svg.chart:active{cursor:grabbing}
.chart-wrap{padding:4px 6px 4px;overflow-x:auto;position:relative}
svg.chart{display:block;width:100%;height:auto;min-width:720px}
.axis-label{font-family:var(--mono);font-size:9.5px;fill:var(--faint)}
.flag-label{font-family:var(--mono);font-size:10px;font-weight:700;fill:var(--ink)}
.flag-w{fill:var(--w)} .flag-i{fill:var(--i)}
.range-label{font-family:var(--mono);font-size:9.5px;font-weight:700}
.phase-label{font-family:var(--mono);font-size:10px;font-weight:800;fill:var(--w)}
.tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--line-strong);border-radius:6px;padding:6px 9px;font-family:var(--mono);font-size:11px;color:var(--ink);box-shadow:var(--shadow);display:none;z-index:5;white-space:nowrap;line-height:1.5}
.tip .t{color:var(--muted)} .tip .u{color:var(--up)} .tip .d{color:var(--down)}
.lane-status{padding:22px 16px;font-size:13px;color:var(--muted);display:flex;gap:12px;align-items:center}
.lane-status b{color:var(--ink-2)}
.legend{display:flex;gap:16px;align-items:center;font-family:var(--mono);font-size:11px;color:var(--muted);flex-wrap:wrap;padding:0 4px}
.legend > span{display:inline-flex;align-items:center;gap:6px}
.sw{display:inline-block;width:14px;height:8px;border-radius:2px}
.sw.up{border:2px solid var(--up);background:transparent;height:6px} .sw.down{background:var(--down)}
.sw.vol{background:var(--muted);opacity:.5} .sw.volhi{background:var(--w)}
.sw.tr{height:0;border-top:2px dashed var(--w)} .sw.ph{background:var(--w);opacity:.18;height:10px}
.sw.fvgb{background:var(--up);opacity:.35} .sw.fvgs{background:var(--down);opacity:.35} .sw.ob{background:var(--i);opacity:.35}
.sw.liq{height:0;border-top:2px dotted var(--i)} .sw.eq{height:0;border-top:2px dashed var(--i)} .sw.kz{background:var(--i);opacity:.12;height:10px} .sw.lvl{height:0;border-top:2px dashed var(--ink-2)} .sw.cisd{height:0;border-top:2px dashed var(--up)}
.sw.win{background:var(--accent);opacity:.14;height:10px}

/* read matrix */
.matrix{display:grid;grid-template-columns:128px repeat(var(--n),minmax(0,1fr)) minmax(0,1.15fr);border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--surface)}
.matrix.cols-2{--n:2} .matrix.cols-3{--n:3} .matrix.cols-4{--n:4}
.mx-head{padding:9px 14px;font-family:var(--mono);font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2);background:var(--surface-3);border-bottom:1px solid var(--line);border-left:1px solid var(--line)}
.mx-head.lane-wyckoff,.mx-head.lane-ict,.mx-head.lane-footprint,.mx-head.lane-heatmap{box-shadow:inset 0 -2px 0 var(--lane)}
.mx-corner{border-left:0;color:var(--faint)}
.mx-label{padding:12px 14px;border-top:1px solid var(--line);background:var(--surface-2)}
.mx-title{font-weight:800;font-size:13px}
.mx-sub{font-family:var(--mono);font-size:10.5px;color:var(--muted);margin-top:3px;line-height:1.4}
.mx-cell{padding:12px 14px;border-top:1px solid var(--line);border-left:1px solid var(--line);font-size:13px;min-width:0;transition:background .15s}
.mx-cell-tag{display:none;font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--lane,var(--faint));margin-bottom:6px}
.mx-cell ul{margin:0;padding-left:16px;display:flex;flex-direction:column;gap:5px}
.mx-cell p{margin:0 0 7px} .mx-cell p:last-child{margin-bottom:0}
.mx-cell .cite,.mx-cell .cite *{font-family:var(--mono);font-size:10px;color:var(--faint)}
.mx-cell .cite{display:inline;margin-left:4px;overflow-wrap:anywhere}
.mx-synth{background:color-mix(in srgb,var(--surface-2) 60%,var(--surface))}
body[data-lane="wyckoff"] .mx-cell.lane-wyckoff,body[data-lane="ict"] .mx-cell.lane-ict,body[data-lane="footprint"] .mx-cell.lane-footprint,body[data-lane="heatmap"] .mx-cell.lane-heatmap{background:color-mix(in srgb,var(--lane-soft) 45%,var(--surface))}
.cell-verdict{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
.inv{font-family:var(--mono);font-size:11px;color:var(--muted)}
.sub-h{font-family:var(--mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--faint);margin:8px 0 4px}
.badges{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
.badge{font-family:var(--mono);font-size:10.5px;font-weight:700;padding:2px 8px;border-radius:5px;background:var(--lane-soft,var(--surface-3));color:var(--lane,var(--ink-2))}
.kv{display:grid;grid-template-columns:auto auto;gap:2px 10px;font-family:var(--mono);font-size:11.5px;color:var(--muted);margin:0 0 8px!important}
.kv b{color:var(--ink);font-variant-numeric:tabular-nums;text-align:right}
.mx-foot{font-family:var(--mono);font-size:11px;color:var(--muted);padding:6px 4px 0}

details.timeline{border:1px solid var(--line);border-radius:10px;background:var(--surface)}
details.timeline summary{cursor:pointer;padding:10px 14px;font-weight:700;font-size:13px}
details.timeline[open] summary{border-bottom:1px solid var(--line)}
.table-wrap{overflow-x:auto}
table.evidence{width:100%;border-collapse:collapse;font-size:12.5px}
table.evidence th,table.evidence td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--line);vertical-align:top}
table.evidence th{font-family:var(--mono);font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:var(--faint);font-weight:600;background:var(--surface-2)}
table.evidence th.lane-wyckoff,table.evidence th.lane-ict{color:var(--lane)}
table.evidence td:first-child{font-family:var(--mono);white-space:nowrap;color:var(--muted)}
table.evidence td .cite{display:block;font-family:var(--mono);font-size:10px;color:var(--faint);margin-top:3px;overflow-wrap:anywhere}

.glossary h2{font-size:15px;margin:0 0 10px}
.gl-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
.gl{border:1px solid var(--line);border-radius:10px;background:var(--surface);padding:12px 14px;border-top:3px solid var(--lane)}
.gl-head{font-weight:800;font-size:13px;margin-bottom:6px}
.gl dl{margin:0;font-size:12.5px} .gl dt{font-family:var(--mono);font-weight:700;font-size:11.5px;margin-top:8px} .gl dd{margin:2px 0 0;color:var(--ink-2)}

footer{font-family:var(--mono);font-size:11px;color:var(--faint);border-top:1px solid var(--line);padding-top:14px;line-height:1.7}
footer b{color:var(--muted);font-weight:600}

@media (max-width:900px){
  .matrix{grid-template-columns:1fr}
  .mx-head{display:none}
  .mx-label{border-top:2px solid var(--line-strong)}
  .mx-cell{border-left:0}
  .mx-cell-tag{display:block}
  .disclaimer{white-space:normal}
  .lanes{margin-left:0}
}
</style>
"""

JS = r"""
<script>
(function(){
  const DATA = __DATA__;
  const P = __PARAMS__;
  const LANES = ['wyckoff','ict','footprint','heatmap'];
  let lane = 'wyckoff';
  const fmtOf = k => k==='int' ? (v=>Math.round(v).toLocaleString('en-US')) : (v=>v.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}));

  // ---------- ICT engine: price-only, computed from OHLC at render time. No volume input (the ICT corpus has none).
  // Rules per knowledge/04-ttrades-core-A.md, 05-ttrades-core-B.md, 06-ttrades-models.md, page-checked against the PDFs on
  // 2026-09-12 (docs/audits/2026-09-12-ict-pdf-recheck.md). Numeric thresholds are PROJECT PARAMETERS from
  // analysis-params.json project_defined.ict (the decks define concepts, not numbers). Candle times are UTC ISO strings;
  // sessions convert to the exchange-local zone per date (docs/architecture/session-model.md §1) so they follow DST.
  const ICT = P.ict || {};
  const PIV = (ICT.pivot_bars||{}).value ?? 3, EQTOL = ((ICT.equal_level_tolerance_pct||{}).value ?? 0.08)/100, FVGMIN = (ICT.fvg_min_size_median_ratio||{}).value ?? 0.6;
  const DISP = ICT.displacement || {body_min_ratio:0.6, range_min_median_ratio:1.2};
  const SESSIONS = [{key:'asia',name:'ASIA',tz:'America/New_York',a:20,b:24},{key:'london',name:'LDN',tz:'Europe/London',a:8,b:11},{key:'ny_am',name:'NY AM',tz:'America/New_York',a:8.5,b:11},{key:'ny_pm',name:'NY PM',tz:'America/New_York',a:13.5,b:16}];
  const KZ_WEIGHT = {crypto:{london:'reduced',ny_am:'reduced',ny_pm:'none'}, metals:{london:'full',ny_am:'full',ny_pm:'full'}, oil:{london:'reduced',ny_am:'full',ny_pm:'full'}};
  const utcDate = iso => new Date(/Z$/.test(iso)?iso:iso+'Z');
  const localHour = (iso,tz) => { const parts=new Intl.DateTimeFormat('en-GB',{timeZone:tz,hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(utcDate(iso)); let h=0,m=0; parts.forEach(q=>{ if(q.type==='hour')h=(+q.value)%24; if(q.type==='minute')m=+q.value; }); return h+m/60; };
  const weekKey = iso => { const d=utcDate(iso); const dow=(d.getUTCDay()+6)%7; return new Date(d.getTime()-dow*86400000).toISOString().slice(0,10); };
  function ictAnalyze(rows, cfg){
    const n=rows.length, O=i=>rows[i][1], H=i=>rows[i][2], L=i=>rows[i][3], C=i=>rows[i][4], T=i=>rows[i][6];
    const tfMin=cfg.tfMin||0, mkt=cfg.market||'crypto';
    const wlo=Math.min(...rows.map(r=>r[3])), whi=Math.max(...rows.map(r=>r[2]));
    const sizes=rows.map(r=>r[2]-r[3]).sort((a,b)=>a-b), medRange=sizes[Math.floor(n/2)]||0;
    const firstAfter=(start,pred)=>{ for(let q=start;q<n;q++) if(pred(q)) return q; return -1; };
    const sh=[], sl=[];
    for(let i=PIV;i<n-PIV;i++){ let isH=true,isL=true; for(let j=i-PIV;j<=i+PIV;j++){ if(j===i)continue; if(H(j)>H(i))isH=false; if(L(j)<L(i))isL=false; } if(isH)sh.push(i); if(isL)sl.push(i); }
    // FVG: wick-based three-candle gap (k04 §2.21); CE = 0.5 of the gap, entry price and hold/fail line (k04 §2.23, §2.26); drawn until first mitigation
    let fvgs=[];
    for(let i=1;i<n-1;i++){ let f=null; if(H(i-1)<L(i+1)) f={type:'bull',i,lo:H(i-1),hi:L(i+1)}; else if(L(i-1)>H(i+1)) f={type:'bear',i,lo:H(i+1),hi:L(i-1)}; if(!f)continue;
      f.size=f.hi-f.lo; f.ce=(f.hi+f.lo)/2; f.end=n-1; f.mitigated=false; for(let j=i+2;j<n;j++){ if((f.type==='bull'&&L(j)<=f.hi)||(f.type==='bear'&&H(j)>=f.lo)){f.end=j;f.mitigated=true;break;} } fvgs.push(f); }
    fvgs=fvgs.filter(f=>f.size>=FVGMIN*medRange).sort((a,b)=>b.size-a.size).slice(0,10).sort((a,b)=>a.i-b.i);
    // liquidity pools (k04 §2.6-2.7): relatively-equal swing pairs, the nearest single old high / old low, window extremes as ERL
    const tol=((wlo+whi)/2)*EQTOL, liq=[];
    const sweptAt=(kind,level,last)=>firstAfter(last+1, j=>kind==='H'?(H(j)>level&&C(j)<level):(L(j)<level&&C(j)>level));
    const addPool=(kind,idxs,level)=>{ const first=Math.min(...idxs), last=Math.max(...idxs); const swept=sweptAt(kind==='BSL'||kind==='OLD-H'?'H':'L',level,last); liq.push({kind,level,from:first,to:swept>=0?swept:n-1,swept}); };
    for(let a=0;a<sh.length;a++){ for(let b=a+1;b<sh.length;b++){ if(Math.abs(H(sh[a])-H(sh[b]))<=tol&&sh[b]-sh[a]>=4){ addPool('BSL',[sh[a],sh[b]],Math.max(H(sh[a]),H(sh[b]))); break; } } }
    for(let a=0;a<sl.length;a++){ for(let b=a+1;b<sl.length;b++){ if(Math.abs(L(sl[a])-L(sl[b]))<=tol&&sl[b]-sl[a]>=4){ addPool('SSL',[sl[a],sl[b]],Math.min(L(sl[a]),L(sl[b]))); break; } } }
    const seen=[], pools=[]; for(const p of liq.sort((a,b)=>a.from-b.from)){ if(!seen.some(q=>Math.abs(q.level-p.level)<=tol)){seen.push(p);pools.push(p);} }
    const lastC=C(n-1);
    const oldH=[...sh].reverse().find(i=>H(i)>lastC&&!pools.some(p=>Math.abs(p.level-H(i))<=tol)), oldL=[...sl].reverse().find(i=>L(i)<lastC&&!pools.some(p=>Math.abs(p.level-L(i))<=tol));
    if(oldH!==undefined){ addPool('OLD-H',[oldH],H(oldH)); pools.push(liq[liq.length-1]); } if(oldL!==undefined){ addPool('OLD-L',[oldL],L(oldL)); pools.push(liq[liq.length-1]); }
    const hiIdx=rows.findIndex(r=>r[2]===whi), loIdx=rows.findIndex(r=>r[3]===wlo);
    pools.push({kind:'ERL-high',level:whi,from:hiIdx,to:n-1,swept:-1}); pools.push({kind:'ERL-low',level:wlo,from:loIdx,to:n-1,swept:-1});
    // dealing range = nearest unswept BSL above / SSL below the last close (k04 §2.18 "where buyside and sellside liquidity is resting"); fallback = window extremes, reported as such
    const above=pools.filter(p=>p.swept<0&&(p.kind==='BSL'||p.kind==='OLD-H')&&p.level>lastC).map(p=>p.level), below=pools.filter(p=>p.swept<0&&(p.kind==='SSL'||p.kind==='OLD-L')&&p.level<lastC).map(p=>p.level);
    const hi=above.length?Math.min(...above):whi, lo=below.length?Math.max(...below):wlo, eq=(lo+hi)/2, drSource=(above.length&&below.length)?'pools':(above.length||below.length)?'mixed':'window';
    // MSS = body close beyond the swing preceding the raid (k04 §2.17, k05 §2.2) + displacement test (k04 §2.16; thresholds are project parameters);
    // OB = last opposing-close candle before the leg: OPEN line + 0.5 mean threshold, mitigated when price trades back to the open (k05 §2.5);
    // CISD = open of the first candle of the final opposing-colour run into the extreme, confirmed by a close through it (k05 §2.3, k06 §2.3)
    const isDisp=j=>{ const rg=H(j)-L(j); return rg>0 && Math.abs(C(j)-O(j))>=DISP.body_min_ratio*rg && rg>=DISP.range_min_median_ratio*medRange; };
    const runStart=(e,down)=>{ let k=e; if(down?C(k)>=O(k):C(k)<=O(k)) k--; let r=k; while(r>=0&&(down?C(r)<O(r):C(r)>O(r))) r--; return r+1<=k?r+1:null; };
    const mss=[], obs=[], cisd=[]; const piv=[...sh.map(i=>({i,t:'H'})),...sl.map(i=>({i,t:'L'}))].sort((a,b)=>a.i-b.i);
    let lastH=null,lastL=null,bias=0;
    for(let k=0;k<piv.length;k++){ const p=piv[k];
      if(p.t==='H'){ if(lastH!==null&&H(p.i)>H(lastH))bias=+1; lastH=p.i; } else { if(lastL!==null&&L(p.i)<L(lastL))bias=-1; lastL=p.i; }
      const next=k+1<piv.length?piv[k+1].i:n;
      for(let j=p.i+1;j<next;j++){
        if(bias===-1&&lastH!==null&&C(j)>H(lastH)){ const from=lastL??0; let e=from; for(let q=from;q<j;q++) if(L(q)<L(e))e=q; const s0=lastH<=e?lastH:from; let oI=s0; for(let q=s0;q<=e;q++) if(H(q)>H(oI))oI=q;
          mss.push({type:'bull',i:j,level:H(lastH),disp:isDisp(j),ext:L(e),extI:e,origin:H(oI),originI:oI});
          for(let q=j-1;q>=Math.max(0,from);q--){ if(C(q)<O(q)){obs.push({type:'bull',i:q,open:O(q),close:C(q),mt:(O(q)+C(q))/2,until:j});break;} }
          const r=runStart(e,true); if(r!==null) cisd.push({type:'bull',i:r,level:O(r),confirmed:firstAfter(r+1,q=>C(q)>O(r))});
          bias=0; break; }
        if(bias===+1&&lastL!==null&&C(j)<L(lastL)){ const from=lastH??0; let e=from; for(let q=from;q<j;q++) if(H(q)>H(e))e=q; const s0=lastL<=e?lastL:from; let oI=s0; for(let q=s0;q<=e;q++) if(L(q)<L(oI))oI=q;
          mss.push({type:'bear',i:j,level:L(lastL),disp:isDisp(j),ext:H(e),extI:e,origin:L(oI),originI:oI});
          for(let q=j-1;q>=Math.max(0,from);q--){ if(C(q)>O(q)){obs.push({type:'bear',i:q,open:O(q),close:C(q),mt:(O(q)+C(q))/2,until:j});break;} }
          const r=runStart(e,false); if(r!==null) cisd.push({type:'bear',i:r,level:O(r),confirmed:firstAfter(r+1,q=>C(q)<O(r))});
          bias=0; break; }
      } }
    obs.forEach(o=>{ o.end=n-1; o.mitigated=false; for(let j=o.until+1;j<n;j++){ if((o.type==='bull'&&L(j)<=o.open)||(o.type==='bear'&&H(j)>=o.open)){o.end=j;o.mitigated=true;break;} } });
    // OTE on the impulse after the latest MSS (k04 §2.20: 1 at the origin, 0 at the terminus, band 0.62-0.79) and std-dev projections of the
    // manipulation leg (k05 §2.12; k06 §2.1.5: 1 at the sweep extreme, 0 at the high/low that made the highest high / lowest low before it),
    // only while the thesis is alive: no later close back beyond the swept extreme (k04 §3.6 R25)
    let ote=null, std=null; const m=mss[mss.length-1];
    if(m){ const dead=firstAfter(m.i+1, q=>m.type==='bull'?C(q)<m.ext:C(q)>m.ext)>=0;
      if(!dead){ let tI=m.i; for(let q=m.i;q<n;q++){ if(m.type==='bull'?H(q)>H(tI):L(q)<L(tI))tI=q; }
        const term=m.type==='bull'?H(tI):L(tI), leg=Math.abs(term-m.ext);
        if(tI>m.i&&leg>0) ote={from:tI,type:m.type,levels:[0.62,0.705,0.79].map(r=>({r,price:m.type==='bull'?term-r*leg:term+r*leg}))};
        const mleg=Math.abs(m.origin-m.ext); if(mleg>0) std={from:m.i,type:m.type,levels:[2,2.5,4].map(k=>({k,price:m.type==='bull'?m.origin+k*mleg:m.origin-k*mleg}))}; } }
    // sessions (PROJECT-DEFINED, session-model.md §2-4): killzone shading only for windows with a non-zero weight for this market, weekdays only;
    // Asia / London session highs & lows as liquidity levels (k04 §2.9; boundaries are the project's, the decks give none — k04 §6 item 9)
    const kz=[], sess=[]; const spans={};
    if(tfMin>0&&tfMin<=240){ SESSIONS.forEach(z=>{ let start=-1; const out=[]; for(let i=0;i<=n;i++){ let inZ=false; if(i<n){ const d=utcDate(T(i)).getUTCDay(), h=localHour(T(i),z.tz); inZ=d!==0&&d!==6&&h>=z.a&&h<z.b; } if(inZ&&start<0)start=i; if((!inZ||i===n)&&start>=0){out.push({from:start,to:i-1});start=-1;} } spans[z.key]=out; });
      if(cfg.kz){ ['london','ny_am','ny_pm'].forEach(k=>{ const w=(KZ_WEIGHT[mkt]||KZ_WEIGHT.crypto)[k]; if(w==='none')return; const z=SESSIONS.find(q=>q.key===k); (spans[k]||[]).forEach(sp=>kz.push({name:z.name,weight:w,from:sp.from,to:sp.to})); }); }
      if(tfMin<=60){ ['asia','london'].forEach(k=>{ const z=SESSIONS.find(q=>q.key===k); (spans[k]||[]).slice(-3).forEach(sp=>{ let h=-Infinity,l=Infinity; for(let i=sp.from;i<=sp.to;i++){ h=Math.max(h,H(i)); l=Math.min(l,L(i)); }
          const swH=sweptAt('H',h,sp.to), thH=firstAfter(sp.to+1,q=>C(q)>h), swL=sweptAt('L',l,sp.to), thL=firstAfter(sp.to+1,q=>C(q)<l);
          sess.push({name:z.name+' H',level:h,from:sp.from,to:swH>=0?swH:(thH>=0?thH:n-1),swept:swH,through:thH}); sess.push({name:z.name+' L',level:l,from:sp.from,to:swL>=0?swL:(thL>=0?thL:n-1),swept:swL,through:thL}); }); }); } }
    // previous-period levels (k04 §2.8, §2.12): PDH/PDL (day = UTC calendar day — project assumption, the decks use the platform's daily bar),
    // PWH/PWL (week from Monday 00Z), PMH/PML. Wick through + close back = failure to displace (×); body close through = the level was the draw (✓)
    const levels=[]; const periods=[]; if(tfMin>0&&tfMin<=240) periods.push(['PD',iso=>iso.slice(0,10),3]); if(tfMin>=60&&tfMin<=1440) periods.push(['PW',weekKey,2]); if(tfMin>=240) periods.push(['PM',iso=>iso.slice(0,7),2]);
    periods.forEach(([tag,keyOf,keep])=>{ const keys=[], idx={}; for(let i=0;i<n;i++){ const k=keyOf(T(i)); if(!(k in idx)){idx[k]={from:i,to:i,h:H(i),l:L(i)};keys.push(k);} else { const o=idx[k]; o.to=i; o.h=Math.max(o.h,H(i)); o.l=Math.min(o.l,L(i)); } }
      keys.slice(1).slice(-keep).forEach(k=>{ const prev=idx[keys[keys.indexOf(k)-1]], cur=idx[k];
        [['H',prev.h],['L',prev.l]].forEach(([kind,lv])=>{ let swept=-1,through=-1; for(let q=cur.from;q<=cur.to;q++){ if(kind==='H'){ if(C(q)>lv){through=q;break;} if(H(q)>lv){swept=q;break;} } else { if(C(q)<lv){through=q;break;} if(L(q)<lv){swept=q;break;} } }
          levels.push({name:tag+kind,level:lv,from:cur.from,to:cur.to,swept,through}); }); }); });
    const swept=pools.filter(p=>p.swept>=0).sort((a,b)=>b.swept-a.swept).slice(0,4);
    const keptPools=pools.filter(p=>p.swept<0).concat(swept).sort((a,b)=>a.from-b.from);
    const keptMss=mss.slice(-4), keptObs=obs.filter(o=>keptMss.some(q=>q.i===o.until)), keptCisd=cisd.slice(-4);
    return {lo,hi,eq,pct:(lastC-lo)/((hi-lo)||1),drSource,wlo,whi,fvgs:fvgs.slice(-8),pools:keptPools,mss:keptMss,obs:keptObs,cisd:keptCisd,kz,sess,levels,ote,std};
  }

  // ---------- Wyckoff volume read: rolling mean of the previous P.lookback completed bars (project parameter).
  function volStats(rows){
    const n=rows.length, avg=new Array(n).fill(null), ratio=new Array(n).fill(null);
    for(let i=0;i<n;i++){ const a=Math.max(0,i-P.lookback), k=i-a; if(k<3)continue; let s=0; for(let j=a;j<i;j++)s+=rows[j][5]; avg[i]=s/k; ratio[i]=avg[i]?rows[i][5]/avg[i]:null; }
    return {avg,ratio};
  }
  const idxOf=(rows,iso)=>{ if(!iso)return -1; let best=-1; for(let i=0;i<rows.length;i++){ if(rows[i][6]<=iso)best=i; else break; } return best>=0&&rows[best][6]===iso?best:(best>=0&&rows[best][6].slice(0,13)===iso.slice(0,13)?best:-1); };
  const spanOf=(rows,iso)=>{ if(!iso)return -1; for(let i=0;i<rows.length;i++){ if(rows[i][6]>=iso)return i; } return rows.length; };

  const VIEW={};   // per-chart visible slice [a,b) — zoom/pan state survives lane switches
  function drawChart(svg, full, cfg){
    const st = VIEW[svg.id] || (VIEW[svg.id]={a:0,b:full.length});
    const rows = full.slice(st.a, st.b);
    // fixed geometry in every lane and for both charts: the volume pane is always reserved so the page does not jump
    const W=1200, padL=70, padR=128, padT=30, padB=22, volH=76, gap=10, priceH=290, H=padT+priceH+gap+volH+padB;
    svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
    const plotW=W-padL-padR, n=rows.length;
    const lo=Math.min(...rows.map(c=>c[3])), hi=Math.max(...rows.map(c=>c[2])), pad=(hi-lo)*0.07;
    const yMin=lo-pad, yMax=hi+pad;
    const x=i=>padL+(i+0.5)*(plotW/n), y=v=>padT+priceH*(1-(v-yMin)/(yMax-yMin));
    const step=plotW/n, bw=Math.max(1.4,Math.min(7,step*0.62));
    const fmt=cfg.fmt;
    const ict = lane==='ict' ? ictAnalyze(rows, {kz:cfg.kz, tfMin:cfg.tfMin, market:cfg.market}) : null;
    let s='';
    // context window shading (the working window inside the overview)
    if(cfg.window){ const a=spanOf(rows,cfg.window.from); if(a<n){ s+=`<rect x="${x(a)-step/2}" y="${padT}" width="${(n-a)*step}" height="${priceH}" fill="var(--accent)" opacity="0.10"/>`; s+=`<text class="axis-label" x="${x(a)-step/2+4}" y="${padT+11}" fill="var(--accent)">cửa sổ chính →</text>`; } }
    if(ict){ ict.kz.forEach(z=>{ s+=`<rect x="${x(z.from)-step/2}" y="${padT}" width="${(z.to-z.from+1)*step}" height="${priceH}" fill="var(--i)" opacity="${z.weight==='full'?0.10:0.06}"/>`; if(!cfg.compact) s+=`<text class="axis-label" x="${x(z.from)-step/2+3}" y="${padT+10}">${z.name}${z.weight==='reduced'?' ½':''}</text>`; });
      s+=`<rect x="${padL}" y="${y(ict.hi)}" width="${plotW}" height="${Math.max(0,y(ict.eq)-y(ict.hi))}" fill="var(--down)" opacity="0.04"/>`;
      s+=`<rect x="${padL}" y="${y(ict.eq)}" width="${plotW}" height="${Math.max(0,y(ict.lo)-y(ict.eq))}" fill="var(--up)" opacity="0.04"/>`; }
    // Wyckoff phase bands (from the full analysis; addressed by time)
    if(lane==='wyckoff' && cfg.wy && cfg.wy.phases){ let lastLx=-1e9, row=0; cfg.wy.phases.forEach(ph=>{ const a=spanOf(rows,ph.from), b=ph.to?spanOf(rows,ph.to):n; if(a>=n||b<=0)return; const x1=x(Math.max(0,a))-step/2, x2=x(Math.min(n,b)-1)+step/2;
      s+=`<rect x="${x1}" y="${padT}" width="${Math.max(2,x2-x1)}" height="${priceH}" fill="var(--w)" opacity="0.07"/>`; s+=`<line x1="${x1}" y1="${padT}" x2="${x1}" y2="${padT+priceH}" stroke="var(--w)" stroke-width="1" stroke-dasharray="2,4" opacity=".6"/>`;
      const lbl=String(ph.label||'').replace(/^(pha|phase)\s*/i,'').slice(0,2); if(!lbl) return; row = (x1-lastLx<18) ? row+1 : 0; lastLx=x1;
      s+=`<text class="phase-label" x="${x1+4}" y="${padT+12+row*12}">${lbl}</text>`; }); }
    for(let t=0;t<=4;t++){ const v=yMin+(yMax-yMin)*(t/4), yy=y(v); s+=`<line x1="${padL}" y1="${yy}" x2="${W-padR}" y2="${yy}" stroke="var(--line)" stroke-width="1"/>`; s+=`<text class="axis-label" x="${padL-8}" y="${yy+3}" text-anchor="end">${fmt(v)}</text>`; }
    if(ict){ ict.fvgs.forEach(f=>{ const col=f.type==='bull'?'var(--up)':'var(--down)', x1=x(f.i)-step/2, x2=x(f.end)+step/2; s+=`<rect x="${x1}" y="${y(f.hi)}" width="${Math.max(2,x2-x1)}" height="${Math.max(1,y(f.lo)-y(f.hi))}" fill="${col}" opacity="${f.mitigated?0.14:0.28}" stroke="${col}" stroke-width="0.6"/>`; if(!f.mitigated) s+=`<line x1="${x1}" y1="${y(f.ce)}" x2="${x2}" y2="${y(f.ce)}" stroke="${col}" stroke-width="0.8" stroke-dasharray="2,2" opacity=".8"/>`; });
      ict.obs.forEach(o=>{ const x1=x(o.i)-step/2, x2=x(o.end)+step/2, op=o.mitigated?0.35:1, top=y(Math.max(o.open,o.close)), bot=y(Math.min(o.open,o.close));
        s+=`<rect x="${x1}" y="${top}" width="${Math.max(2,x2-x1)}" height="${Math.max(1,bot-top)}" fill="var(--i)" opacity="${0.12*op}"/>`;
        s+=`<line x1="${x1}" y1="${y(o.open)}" x2="${x2}" y2="${y(o.open)}" stroke="var(--i)" stroke-width="1.4" opacity="${op}"/>`; s+=`<line x1="${x1}" y1="${y(o.mt)}" x2="${x2}" y2="${y(o.mt)}" stroke="var(--i)" stroke-width="0.8" stroke-dasharray="3,3" opacity="${op}"/>`;
        if(!cfg.compact) s+=`<text class="flag-label flag-i" x="${x1+3}" y="${y(o.open)+(o.type==='bull'?-3:10)}" opacity="${op}">${o.type==='bull'?'+OB':'-OB'} open · 0.5 MT</text>`; });
      ict.cisd.forEach(c=>{ const col=c.type==='bull'?'var(--up)':'var(--down)', x1=x(c.i)-step/2, x2=c.confirmed>=0?x(c.confirmed):W-padR; s+=`<line x1="${x1}" y1="${y(c.level)}" x2="${x2}" y2="${y(c.level)}" stroke="${col}" stroke-width="1.3" stroke-dasharray="5,2"/>`; if(c.confirmed>=0) s+=`<circle cx="${x(c.confirmed)}" cy="${y(c.level)}" r="2.6" fill="${col}"/>`; if(!cfg.compact) s+=`<text class="flag-label" x="${x1+2}" y="${y(c.level)+(c.type==='bull'?11:-4)}" fill="${col}">CISD${c.confirmed>=0?'':' (chưa đóng qua)'}</text>`; }); }
    rows.forEach((c,i)=>{ const [t,o,h,l,cl]=c, up=cl>=o, cx=x(i), col=up?'var(--up)':'var(--down)';
      s+=`<line x1="${cx}" y1="${y(h)}" x2="${cx}" y2="${y(l)}" stroke="${col}" stroke-width="1"/>`;
      const top=y(Math.max(o,cl)), bot=y(Math.min(o,cl)), bh=Math.max(1,bot-top);
      s+= up ? `<rect x="${cx-bw/2}" y="${top}" width="${bw}" height="${bh}" fill="var(--surface-2)" stroke="${col}" stroke-width="1.1"/>` : `<rect x="${cx-bw/2}" y="${top}" width="${bw}" height="${bh}" fill="${col}"/>`; });
    const every=Math.max(1,Math.ceil(n/(cfg.compact?7:9)));
    rows.forEach((c,i)=>{ if(i%every===0) s+=`<text class="axis-label" x="${x(i)}" y="${H-7}" text-anchor="middle">${c[0]}</text>`; });
    // named levels (anchors) for this lane
    (cfg.levels||[]).filter(L=>L.method===lane||L.method==='neutral').forEach(L=>{ if(L.price<yMin||L.price>yMax)return; const a=Math.max(0,spanOf(rows,L.time)); const col=L.method==='neutral'?'var(--muted)':'var(--lane)';
      s+=`<line x1="${x(a)-step/2}" y1="${y(L.price)}" x2="${W-padR}" y2="${y(L.price)}" stroke="${col}" stroke-width="1.2" stroke-dasharray="6,4"/>`; s+=`<text class="range-label" x="${W-padR+4}" y="${y(L.price)+3}" fill="${col}">${L.short} ${fmt(L.price)}</text>`; });
    if(lane==='wyckoff'){
      const wy=cfg.wy||{};
      if(wy.tr){ const a=Math.max(0,spanOf(rows,wy.tr.from)); const x1=x(a)-step*0.4, x2=W-padR;
        [[wy.tr.high,wy.tr.high_label||'AR'],[wy.tr.low,wy.tr.low_label||'SC']].forEach(([v,lb])=>{ if(v==null||v<yMin||v>yMax)return; s+=`<line x1="${x1}" y1="${y(v)}" x2="${x2}" y2="${y(v)}" stroke="var(--w)" stroke-width="1.6" stroke-dasharray="5,3"/>`; s+=`<text class="range-label" x="${x2+4}" y="${y(v)+3}" fill="var(--w)">${lb} ${fmt(v)}</text>`; }); }
      // event flags: stagger labels that would collide (same side, overlapping x extents) by pushing them outward
      const placed=[]; const evs=(wy.events||[]).map(f=>({f,i:idxOf(rows,f.time)})).filter(o=>o.i>=0).sort((a,b)=>a.i-b.i);
      evs.forEach(({f,i})=>{ const c=rows[i], cx=x(i), ay=f.up?y(c[2]):y(c[3]); const lbl=cfg.compact?f.label.split(' · ')[0]:f.label; const w=lbl.length*5.8;
        let lvl=0; for(;;){ const fy=ay+(f.up?-10-lvl*12:15+lvl*12); const clash=placed.some(p=>p.up===!!f.up && Math.abs(p.y-fy)<11 && (cx-w/2)<p.x2 && (cx+w/2)>p.x1); if(!clash||lvl>=4){ placed.push({up:!!f.up,y:fy,x1:cx-w/2,x2:cx+w/2});
          s+=`<circle cx="${cx}" cy="${ay}" r="3" fill="var(--w)" stroke="var(--surface-2)" stroke-width="1.5"/>`; if(lvl>0) s+=`<line x1="${cx}" y1="${ay}" x2="${cx}" y2="${fy+(f.up?3:-9)}" stroke="var(--w)" stroke-width="0.8" opacity=".7"/>`;
          const ax = cx+w/2>W-padR ? W-padR-2 : (cx-w/2<padL ? padL+2 : cx); const anchor = ax!==cx ? (ax>cx?'end':'start') : 'middle';
          s+=`<text class="flag-label" x="${ax}" y="${fy}" text-anchor="${anchor}">${lbl}</text>`; break; } lvl++; } });
      // now marker
      const li=n-1; s+=`<circle cx="${x(li)}" cy="${y(rows[li][4])}" r="3" fill="var(--ink)" stroke="var(--surface-2)" stroke-width="1.5"/>`;
      // volume pane
      const vsFull=volStats(full), vs={avg:vsFull.avg.slice(st.a,st.b), ratio:vsFull.ratio.slice(st.a,st.b)}, vTop=padT+priceH+gap, vMax=Math.max(...rows.map(r=>r[5]))||1, vy=v=>vTop+volH*(1-v/vMax);
      s+=`<line x1="${padL}" y1="${vTop+volH}" x2="${W-padR}" y2="${vTop+volH}" stroke="var(--line)"/>`;
      rows.forEach((c,i)=>{ const r=vs.ratio[i], up=c[4]>=c[1]; const col = r!=null&&r>=P.high ? 'var(--w)' : (up?'var(--up)':'var(--down)'); const op = r!=null&&r>=P.high ? (r>=P.spike?1:0.85) : 0.42;
        s+=`<rect x="${x(i)-bw/2}" y="${vy(c[5])}" width="${bw}" height="${Math.max(0.5,vTop+volH-vy(c[5]))}" fill="${col}" opacity="${op}"/>`; });
      if(!cfg.compact){ const spikes=rows.map((c,i)=>({i,r:vs.ratio[i]})).filter(o=>o.r!=null&&o.r>=P.spike).sort((a,b)=>b.r-a.r), gapN=Math.ceil(n/40), labeled=[];
        spikes.forEach(o=>{ if(labeled.some(j=>Math.abs(j-o.i)<gapN))return; labeled.push(o.i); s+=`<text class="axis-label" x="${x(o.i)}" y="${vy(rows[o.i][5])-3}" text-anchor="middle" fill="var(--w)">${o.r.toFixed(1)}×</text>`; }); }
      let path='', started=false; rows.forEach((c,i)=>{ if(vs.avg[i]==null)return; path+=(started?'L':'M')+x(i).toFixed(1)+','+vy(vs.avg[i]).toFixed(1); started=true; });
      if(path) s+=`<path d="${path}" fill="none" stroke="var(--ink-2)" stroke-width="1.2" opacity=".8"/>`;
      s+=`<text class="axis-label" x="${padL-8}" y="${vTop+9}" text-anchor="end">KL</text>`; s+=`<text class="axis-label" x="${padL-8}" y="${vTop+volH}" text-anchor="end">0</text>`;
      if(!cfg.compact) s+=`<text class="axis-label" x="${W-padR+4}" y="${vTop+10}">TB ${P.lookback} nến</text>`;
    } else if(ict){
      const vTop=padT+priceH+gap; s+=`<line x1="${padL}" y1="${vTop+volH}" x2="${W-padR}" y2="${vTop+volH}" stroke="var(--line)"/>`; s+=`<text class="axis-label" x="${padL}" y="${vTop+volH/2+3}">khối lượng không thuộc ICT — pane để trống để chart giữ nguyên kích thước khi đổi phương pháp</text>`;
      const xr=W-padR; s+=`<line x1="${padL}" y1="${y(ict.eq)}" x2="${xr}" y2="${y(ict.eq)}" stroke="var(--i)" stroke-width="1.4" stroke-dasharray="6,4"/>`;
      s+=`<text class="range-label" x="${xr+4}" y="${y(ict.eq)+3}" fill="var(--i)">EQ ${fmt(ict.eq)}</text>`; s+=`<text class="axis-label" x="${xr+4}" y="${y(ict.hi)+10}">premium${ict.drSource==='window'?' (biên cửa sổ)':ict.drSource==='mixed'?' (1 biên = cửa sổ)':' (BSL↔SSL)'}</text>`; s+=`<text class="axis-label" x="${xr+4}" y="${y(ict.lo)-4}">discount</text>`;
      ict.pools.forEach(p=>{ const isHigh=p.kind==='BSL'||p.kind==='ERL-high'||p.kind==='OLD-H', col=isHigh?'var(--down)':'var(--up)', x1=x(p.from), x2=x(p.to), old=p.kind.startsWith('OLD');
        s+=`<line x1="${x1}" y1="${y(p.level)}" x2="${x2}" y2="${y(p.level)}" stroke="${col}" stroke-width="${old?0.9:1.2}" stroke-dasharray="2,3"/>`; if(!cfg.compact) s+=`<text class="axis-label" x="${x1}" y="${y(p.level)+(isHigh?-4:10)}" fill="${col}">${p.kind==='ERL-high'?'ERL (BSL)':p.kind==='ERL-low'?'ERL (SSL)':p.kind==='OLD-H'?'old high (BSL)':p.kind==='OLD-L'?'old low (SSL)':p.kind}</text>`;
        if(p.swept>=0){ s+=`<path d="M${x(p.swept)-4},${y(p.level)-4} l8,8 M${x(p.swept)+4},${y(p.level)-4} l-8,8" stroke="${col}" stroke-width="1.8"/>`; } });
      // previous-period and session levels (PDH/PDL/PWH/PWL/PMH/PML; ASIA/LDN H/L): × = wick through + close back (failure to displace), ✓ = body close through
      const lvlLine=(v,name,from,to,swept,through,col)=>{ if(v<yMin||v>yMax)return; const x1=x(from)-step/2, x2=x(Math.min(n-1,to))+step/2; s+=`<line x1="${x1}" y1="${y(v)}" x2="${x2}" y2="${y(v)}" stroke="${col}" stroke-width="1" stroke-dasharray="7,3" opacity=".85"/>`; if(!cfg.compact) s+=`<text class="axis-label" x="${x1+2}" y="${y(v)-3}" fill="${col}">${name}</text>`;
        if(swept>=0) s+=`<path d="M${x(swept)-3.5},${y(v)-3.5} l7,7 M${x(swept)+3.5},${y(v)-3.5} l-7,7" stroke="${col}" stroke-width="1.6"/>`; else if(through>=0) s+=`<path d="M${x(through)-4},${y(v)} l3,3 l5,-6" fill="none" stroke="${col}" stroke-width="1.6"/>`; };
      ict.levels.forEach(l=>lvlLine(l.level,l.name,l.from,l.to,l.swept,l.through,'var(--ink-2)'));
      ict.sess.forEach(l=>lvlLine(l.level,l.name,l.from,l.to,l.swept,l.through,'var(--muted)'));
      ict.mss.forEach(m=>{ const cx=x(m.i), col=m.type==='bull'?'var(--up)':'var(--down)'; s+=`<line x1="${cx}" y1="${y(m.level)}" x2="${cx}" y2="${y(rows[m.i][4])}" stroke="${col}" stroke-width="${m.disp?2:1}" ${m.disp?'':'stroke-dasharray="3,2"'}/>`; if(!cfg.compact) s+=`<text class="flag-label" x="${cx}" y="${m.type==='bull'?y(rows[m.i][4])-6:y(rows[m.i][4])+14}" text-anchor="middle" fill="${col}">${m.disp?'MSS':'đóng qua swing, thiếu displacement'}${m.type==='bull'?'↑':'↓'}</text>`; });
      // OTE band on the impulse after the latest live MSS; std-dev projections of its manipulation leg
      if(ict.ote){ const col=ict.ote.type==='bull'?'var(--up)':'var(--down)', x1=x(ict.ote.from); ict.ote.levels.forEach(l=>{ if(l.price<yMin||l.price>yMax)return; s+=`<line x1="${x1}" y1="${y(l.price)}" x2="${xr}" y2="${y(l.price)}" stroke="${col}" stroke-width="${l.r===0.705?1.4:0.8}" stroke-dasharray="1,3"/>`; if(!cfg.compact) s+=`<text class="axis-label" x="${x1+3}" y="${y(l.price)-2}" fill="${col}">OTE ${l.r}</text>`; }); }
      if(ict.std){ const col='var(--i)', x1=x(ict.std.from); ict.std.levels.forEach(l=>{ if(l.price<yMin||l.price>yMax)return; s+=`<line x1="${x1}" y1="${y(l.price)}" x2="${xr}" y2="${y(l.price)}" stroke="${col}" stroke-width="0.9" stroke-dasharray="8,3,2,3"/>`; s+=`<text class="range-label" x="${xr+4}" y="${y(l.price)+3}" fill="${col}">−${l.k}σ ${fmt(l.price)}</text>`; }); }
      if(!cfg.compact) ict.fvgs.filter(f=>!f.mitigated).sort((a,b)=>b.size-a.size).slice(0,2).forEach(f=>{ s+=`<text class="axis-label" x="${x(f.i)+step}" y="${(y(f.hi)+y(f.lo))/2+3}" fill="${f.type==='bull'?'var(--up)':'var(--down)'}">FVG</text>`; });
      const li=n-1; s+=`<circle cx="${x(li)}" cy="${y(rows[li][4])}" r="3" fill="var(--ink)" stroke="var(--surface-2)" stroke-width="1.5"/>`; s+=`<text class="flag-label" x="${x(li)-6}" y="${y(rows[li][4])-10}" text-anchor="end">now ${(ict.pct*100).toFixed(0)}%</text>`;
    }
    s+=`<line id="${svg.id}-xh" x1="0" y1="${padT}" x2="0" y2="${padT+priceH+gap+volH}" stroke="var(--ink)" stroke-width="1" opacity="0" stroke-dasharray="3,3"/>`;
    svg.innerHTML=s;
    // hover: crosshair + tooltip (index from pointer x in viewBox units)
    const wrap=svg.parentElement, tip=wrap.querySelector('.tip'), xh=svg.querySelector('#'+svg.id+'-xh'), vsF=volStats(full), vs={ratio:vsF.ratio.slice(st.a,st.b)};
    svg.onmousemove=e=>{ const r=svg.getBoundingClientRect(), vx=(e.clientX-r.left)/r.width*W; let i=Math.floor((vx-padL)/step); if(i<0||i>=n){tip.style.display='none';xh.setAttribute('opacity','0');return;}
      const c=rows[i], up=c[4]>=c[1], ratio=vs.ratio[i]; xh.setAttribute('x1',x(i)); xh.setAttribute('x2',x(i)); xh.setAttribute('opacity','0.5');
      let t=`<div class="t">${c[6].slice(5,16).replace('T',' ')}Z</div><div>O ${fmt(c[1])} · H ${fmt(c[2])} · L ${fmt(c[3])}</div><div class="${up?'u':'d'}">C ${fmt(c[4])} (${((c[4]-c[1])/c[1]*100).toFixed(2)}%)</div>`;
      if(lane==='wyckoff') t+=`<div>KL ${c[5].toLocaleString('en-US',{maximumFractionDigits:2})}${ratio!=null?` · ${ratio.toFixed(2)}× TB`:''}</div>`;
      if(ict) t+=`<div class="t">${((c[4]-ict.lo)/(ict.hi-ict.lo)*100).toFixed(0)}% dealing range</div>`;
      tip.innerHTML=t; tip.style.display='block'; const px=e.clientX-r.left; tip.style.left=(px>r.width*0.65?px-tip.offsetWidth-14:px+14)+'px'; tip.style.top=(e.clientY-r.top+12)+'px'; };
    svg.onmouseleave=()=>{ tip.style.display='none'; xh.setAttribute('opacity','0'); if(drag){drag=null;} };
    // zoom (wheel, buttons) and pan (drag) on the visible slice; min 30 bars
    const N=full.length, setView=(a,b)=>{ a=Math.max(0,Math.round(a)); b=Math.min(N,Math.round(b)); if(b-a<30){ const c=(a+b)/2; a=Math.max(0,Math.round(c-15)); b=Math.min(N,a+30); a=b-30; } st.a=a; st.b=b; drawChart(svg, full, cfg); };
    svg.onwheel=e=>{ e.preventDefault(); const r=svg.getBoundingClientRect(), vx=(e.clientX-r.left)/r.width*W, i=st.a+Math.max(0,Math.min(n-1,Math.floor((vx-padL)/step))); const f=e.deltaY<0?1/1.25:1.25; setView(i-(i-st.a)*f, i+(st.b-i)*f); };
    let drag=null; svg.onmousedown=e=>{ drag={x:e.clientX,a:st.a,b:st.b}; e.preventDefault(); };
    svg.onmouseup=()=>{ drag=null; };
    const prevMove=svg.onmousemove; svg.onmousemove=e=>{ if(drag){ const r=svg.getBoundingClientRect(), dx=(e.clientX-drag.x)/r.width*W, di=Math.round(-dx/step); let a=drag.a+di, b=drag.b+di; if(a<0){b-=a;a=0;} if(b>N){a-=b-N;b=N;} if(a!==st.a){ st.a=a; st.b=b; drawChart(svg, full, cfg); } return; } prevMove(e); };
    const ctl=wrap.parentElement.querySelector('.zoom'); if(ctl && !ctl.dataset.wired){ ctl.dataset.wired='1';
      ctl.querySelector('[data-z="in"]').onclick=()=>{ const c=(st.a+st.b)/2, h=(st.b-st.a)/2/1.25; setView(c-h,c+h); };
      ctl.querySelector('[data-z="out"]').onclick=()=>{ const c=(st.a+st.b)/2, h=(st.b-st.a)/2*1.25; setView(c-h,c+h); };
      ctl.querySelector('[data-z="reset"]').onclick=()=>setView(0,N); }
  }

  function render(){
    document.body.dataset.lane=lane;
    document.querySelectorAll('.lane-btn').forEach(b=>b.classList.toggle('active',b.dataset.lane===lane));
    for(const key in DATA){ const d=DATA[key];
      const drawn = lane==='wyckoff'||lane==='ict';
      ['ctx','main'].forEach(which=>{ const rows=which==='ctx'?d.ctx:d.rows; if(!rows)return; const block=document.getElementById(`${which}-${key}`); const wrap=block.querySelector('.chart-wrap'), st=block.querySelector('.lane-status'), svg=block.querySelector('svg');
        wrap.hidden=!drawn; st.hidden=drawn; if(!drawn){ st.innerHTML=`<span class="lane-dot"></span><span><b>${lane==='footprint'?'Footprint':'Heatmap'}</b> — ${d.dims[lane]}</span>`; return; }
        const wy = which==='ctx' ? (d.ctxWy||{}) : (d.wy||{});
        drawChart(svg, rows, {fmt:fmtOf(d.fmt), compact:which==='ctx', kz:which==='ctx'?d.ctxKz:d.kz, tfMin:which==='ctx'?d.ctxTfMin:d.tfMin, market:d.market, wy, levels:which==='ctx'?[]:d.levels, window:which==='ctx'?{from:d.rows[0][6]}:null}); });
      const leg=document.getElementById(`legend-${key}`); leg.hidden=!drawn; if(drawn){ leg.innerHTML = lane==='wyckoff'
        ? `<span><i class="sw up"></i>nến đóng tăng</span><span><i class="sw down"></i>nến đóng giảm</span><span><i class="sw vol"></i>khối lượng${d.tick?' (tick, MT5)':''}</span><span><i class="sw volhi"></i>KL ≥ ${P.high}× TB ${P.lookback} nến (≥ ${P.spike}× ghi số)</span><span><i class="sw tr"></i>biên vùng giao dịch (AR / SC)</span><span><i class="sw ph"></i>pha A–E</span><span>● sự kiện Wyckoff do phân tích đầy đủ đặt</span>`
        : `<span><i class="sw fvgb"></i>FVG tăng</span><span><i class="sw fvgs"></i>FVG giảm (nét chấm = CE 0.5)</span><span><i class="sw ob"></i>OB: đường open + 0.5 mean threshold (mờ = đã chạm open)</span><span><i class="sw liq"></i>BSL / SSL / old high-low / ERL (× = quét, thân không đóng qua)</span><span><i class="sw lvl"></i>PDH/PDL · PWH/PWL · ASIA/LDN H-L (× quét · ✓ đóng qua)</span><span><i class="sw eq"></i>EQ của dealing range BSL↔SSL gần nhất · premium trên / discount dưới</span><span><i class="sw cisd"></i>CISD (● = nến đóng qua)</span>${d.kz?'<span><i class="sw kz"></i>killzone LDN / NY AM / NY PM theo session-model (½ = trọng số giảm)</span>':'<span>killzone: không vẽ ở khung này</span>'}<span>MSS↑/↓ nét đậm = có displacement; nét đứt = đóng qua swing nhưng thiếu displacement</span><span>OTE .62/.705/.79 và −2σ/−2.5σ/−4σ chỉ vẽ cho MSS mới nhất còn hiệu lực</span><span class="muted">ngưỡng số là tham số dự án (analysis-params.json → project_defined.ict)</span>`; }
    }
  }
  window.setLane=l=>{ lane=l; render(); };
  document.addEventListener('keydown',e=>{ if(e.target.tagName==='INPUT')return; const k={'1':'wyckoff','2':'ict','3':'footprint','4':'heatmap'}[e.key]; if(k) setLane(k); });
  render();
})();
</script>
"""


# ----------------------------------------------------------------------------------------------- assembly
def build(style, out, snap=None, narrative_path=None, allow_impure=False, check_only=False):
    S = STYLES[style]
    facts = read_json(f"{ROOT}/data/live/prelim/{style}.facts.json", {}) or {}
    meta = read_json(f"{ROOT}/data/live/prelim/{style}.meta.json", {}) or {}
    anchors = read_json(f"{ROOT}/data/live/anchors.{style}.json", {}) or {}
    narrative = read_json(narrative_path or f"{ROOT}/data/live/narrative/{style}.json")
    params = (read_json(f"{ROOT}/docs/architecture/analysis-params.json", {}) or {}).get("project_defined", {})
    vol_p = params.get("volume", {})
    P = dict(lookback=params.get("lookback_bars", 20), high=vol_p.get("high_min_ratio", 1.5), spike=vol_p.get("spike_min_ratio", 2.5))
    cfg = read_json(f"{ROOT}/docs/architecture/automation-config.json", {}) or {}
    market = "cfd" if style.startswith("gold") else "crypto"
    dim_flags = ((cfg.get("markets") or {}).get(market) or {}).get("dimensions") or {}
    mode = (narrative or {}).get("mode") or "NORMAL"

    purity = {}
    data_js, sections, status_chips, rows_store = {}, [], [], {}
    src_notes = []
    for sym, key, disp, kind in S["syms"]:
        rows, upd, src = candles(sym, S["tf"], S["n"], snap)
        ctx = None
        if S["ctx"]:
            try:
                ctx, cupd, csrc = candles(sym, S["ctx"][0], S["ctx"][1], snap)
            except FileNotFoundError:
                ctx = None
        src_notes.append(f"{sym} {S['tf']}: {src or '?'} · cập nhật {upd or '?'}" + (f" · bối cảnh {S['ctx'][0]} cập nhật {cupd or '?'}" if ctx else ""))
        fsym = (facts.get("symbols") or {}).get(sym)
        l1 = layer1(sym, fsym, kind, S["tf"]) if fsym else None
        l2 = layer2(style, sym)
        n3 = ((narrative or {}).get("symbols") or {}).get(sym)
        if n3:
            n3["_updated"] = when((narrative or {}).get("updated"))
        dims = {}
        for m in ("footprint", "heatmap"):
            flag = dim_flags.get(m)
            has = bool((n3 or {}).get(m, {}).get("text_html")) or bool((l2 or {}).get(m))
            avail = ((n3 or {}).get(m) or {}).get("status") == "available"
            if market == "cfd":
                reason = "không có nguồn CoinGlass cho hàng hoá (SYSTEM-DESIGN §12)"
            elif flag is False:
                reason = "tắt trong /automation"
            elif not avail:
                reason = f"không có nguồn CoinGlass live — không vẽ, không chấm điểm (chế độ {mode}: Wyckoff + ICT)"
            else:
                reason = ""
            dims[m] = {"engaged": bool(avail and has and flag is not False), "reason": reason or "đang dùng"}
        # purity: layer 2 blocks, layer 3 texts, chart labels, timeline cells
        blocks = mp.narrative_blocks(n3)
        if l2 and not l2["legacy"]:
            for m, v in mp.model_blocks(l2).items():
                blocks[m] += v
        res = mp.check_blocks(blocks)
        if res:
            purity[sym] = res
        # levels for the charts: anchors by method
        levels = []
        for L in ((anchors.get("symbols") or {}).get(sym) or {}).get("levels", []):
            m = anchor_method(L)
            levels.append(dict(price=L["price"], time=L.get("time"), method=("neutral" if m in ("mixed", "neutral") else m), short=esc((L.get("short") or L.get("name", "")).replace("_", " ")[:14])))
        wy = (n3 or {}).get("wyckoff") or {}
        tr = wy.get("trading_range") or None
        wy_js = dict(tr=(dict(high=tr.get("high"), low=tr.get("low"), high_label=tr.get("high_label", "AR"), low_label=tr.get("low_label", "SC"), from_=tr.get("from")) if tr else None),
                     events=[dict(time=e.get("time"), label=e.get("label", ""), up=bool(e.get("up"))) for e in wy.get("events", [])],
                     phases=[dict(**{"from": p.get("from"), "to": p.get("to")}, label=p.get("label", "")) for p in wy.get("phases", [])])
        if wy_js["tr"]:
            wy_js["tr"]["from"] = wy_js["tr"].pop("from_")
        cwy = ((n3 or {}).get("context") or {}).get("wyckoff") or {}
        reuse = CTX_REUSE.get(style)
        if reuse and not cwy.get("events"):
            rn = ((read_json(f"{ROOT}/data/live/narrative/{reuse}.json") or {}).get("symbols") or {}).get(sym) or {}
            if rn.get("wyckoff"):
                cwy = {**rn["wyckoff"], "text_html": cwy.get("text_html") or f'<p class="muted">Cấu trúc bối cảnh lấy từ phân tích đầy đủ của trang {reuse} (cùng cửa sổ nến) — hai trang không bao giờ đọc khác nhau trên cùng một chuỗi nến.</p>'}
        ctr = cwy.get("trading_range") or None
        ctx_wy = dict(tr=(dict(high=ctr.get("high"), low=ctr.get("low"), high_label=ctr.get("high_label", "AR"), low_label=ctr.get("low_label", "SC")) | {"from": ctr.get("from")} if ctr else None),
                      events=[dict(time=e.get("time"), label=e.get("label", ""), up=bool(e.get("up"))) for e in cwy.get("events", [])],
                      phases=[{"from": p.get("from"), "to": p.get("to"), "label": p.get("label", "")} for p in cwy.get("phases", [])])
        ctx_tf = S["ctx"][0] if S["ctx"] else None
        data_js[key] = dict(fmt=kind, kz=S["kz"], ctxKz=(ctx_tf in ("15m", "1H")), tfMin=TF_MIN.get(S["tf"], 0), ctxTfMin=TF_MIN.get(ctx_tf, 0), tick=(sym in MT5),
                            market=("metals" if sym in ("XAUUSD", "XAGUSD") else "oil" if sym in MT5 else "crypto"), wy=wy_js, ctxWy=ctx_wy, levels=levels,
                            dims={m: dims[m]["reason"] for m in dims}, rows="__ROWS__" + key, ctx=("__CTX__" + key) if ctx else None)
        rows_store[key] = (rows_js(rows, S["lbl"]), rows_js(ctx, S["ctx"][2]) if ctx else "null")
        # section html
        lo, hi = min(r["low"] for r in rows), max(r["high"] for r in rows); last = rows[-1]["close"]
        pct = (last - lo) / (hi - lo) if hi > lo else 0
        cur_verdict = (l2 or {}).get("verdict") or (l1 or {}).get("verdict") or "—"
        cx = (fsym or {}).get("context") or {}
        bias_chip = ""
        if cx:
            bcls = {"long": "long", "short": "short", "neutral": "wait", "unknown": "wait"}.get(cx.get("bias"), "wait")
            bias_chip = f'<span class="lbl">bối cảnh {esc(cx.get("tf"))}</span><span class="chip chip-{bcls}" title="{esc(cx.get("basis", ""))}">{esc(cx.get("bias", "?").upper())}</span>'
        rule_verdict = (l1 or {}).get("verdict")
        status_chips.append(f'<span class="st"><span class="mono">{disp.split("/")[0]}</span>{chip(cur_verdict)}</span>')
        head = (f'<div class="sym-head"><div class="sym-name">{disp}</div><div class="sym-last">{fmtn(last, kind)}</div>'
                f'<div class="sym-kv"><span>biên độ cửa sổ <b>{fmtn(lo, kind)}–{fmtn(hi, kind)}</b></span><span>vị trí <b>{pct * 100:.0f}%</b></span><span>nến cuối <b>{when(rows[-1]["time"])}</b></span></div>'
                f'<div class="sym-verdict">{bias_chip}<span class="lbl">cục bộ</span>{chip(cur_verdict, "chip-lg")}' + (f'<span class="lbl">luật</span>{chip(rule_verdict)}' if rule_verdict else "") + '</div></div>')
        ctx_html = ""
        if ctx:
            ctx_note = (cwy.get("text_html") or "")
            ctx_html = (f'<div class="chart-block" id="ctx-{key}"><div class="chart-title"><span><b>Bối cảnh</b> · {S["ctx_h"]} · {label(ctx[0]["time"], S["ctx"][2])} → {label(ctx[-1]["time"], S["ctx"][2])}</span><span class="zoom"><span class="muted">vùng tô = cửa sổ chính</span><button data-z="out" title="thu nhỏ">−</button><button data-z="in" title="phóng to">+</button><button data-z="reset" title="toàn bộ cửa sổ">⟲</button></span></div>'
                        f'<div class="chart-wrap"><svg class="chart" id="chart-ctx-{key}"></svg><div class="tip"></div></div><div class="lane-status" hidden></div></div>')
        main_html = (f'<div class="chart-block" id="main-{key}"><div class="chart-title"><span><b>Cửa sổ chính</b> · {S["horizon"]} · {label(rows[0]["time"], S["lbl"])} → {label(rows[-1]["time"], S["lbl"])}</span><span class="zoom"><span class="muted">lăn chuột = zoom · kéo = dịch · phím 1–4 đổi phương pháp</span><button data-z="out" title="thu nhỏ">−</button><button data-z="in" title="phóng to">+</button><button data-z="reset" title="toàn bộ cửa sổ">⟲</button></span></div>'
                     f'<div class="chart-wrap"><svg class="chart" id="chart-main-{key}"></svg><div class="tip"></div></div><div class="lane-status" hidden></div></div>')
        legend = f'<div class="legend" id="legend-{key}"></div>'
        sections.append(f'<section class="symbol" id="sec-{key}">{head}<div class="charts">{ctx_html}{main_html}{legend}</div>{matrix(key, kind, l1, l2, n3, dims)}{timeline((n3 or {}).get("timeline"))}</section>')

    if purity:
        print("PURITY VIOLATIONS (one method, one vocabulary):", file=sys.stderr)
        for sym, res in purity.items():
            print(f"[{sym}]\n{mp.report(res)}", file=sys.stderr)
        if not allow_impure:
            print("BUILD REFUSED — fix the offending block(s) or pass --allow-impure for a local preview.", file=sys.stderr)
            sys.exit(2)
    if check_only:
        print("CHECK OK" if not purity else "CHECK FAILED (impure)"); return

    # meta strip
    wf, wl = meta.get("window_first"), meta.get("window_last")
    engaged = ["Wyckoff", "ICT"] + [dict(LANES)[m] for m in ("footprint", "heatmap") if any(True for _ in [0]) and dim_flags.get(m) and False]
    headline = (narrative or {}).get("headline") or {}
    meta_html = ('<div class="meta">'
                 f'<div><div class="meta-l">Cửa sổ chính</div><div class="meta-v">{S["horizon"]}</div><div class="meta-d">{when(wf)} – {when(wl)}</div></div>'
                 + (f'<div><div class="meta-l">Bối cảnh</div><div class="meta-v">{S["ctx_h"]}</div><div class="meta-d">chart trên, vùng tô = cửa sổ chính</div></div>' if S["ctx"] else "")
                 + f'<div><div class="meta-l">Chế độ</div><div class="meta-v">{esc(mode)}</div><div class="meta-d">{" + ".join(engaged)} · Footprint/Heatmap: không có nguồn live</div></div>'
                 + f'<div><div class="meta-l">Sự kiện chính (phân tích đầy đủ gần nhất)</div><div class="meta-v">{headline.get("text", "—")}</div><div class="meta-d">{headline.get("detail", "")}</div></div>'
                 + f'<div><div class="meta-l">Trạng thái (cục bộ)</div><div class="meta-v">{" ".join(status_chips)}</div><div class="meta-d">dữ liệu tới {hhmm(wl)} UTC</div></div>'
                 '</div>')
    lane_btns = "".join(f'<button class="lane-btn lane-{k}{"" if k in ("wyckoff", "ict") else " off"}" data-lane="{k}" onclick="setLane(\'{k}\')" title="phím {i + 1}"><span class="lane-dot"></span>{n}</button>' for i, (k, n) in enumerate(LANES))
    symnav = "".join(f'<a href="#sec-{key}">{disp.split("/")[0]}</a>' for _, key, disp, _ in S["syms"]) + '<a href="#sec-glossary">Thuật ngữ</a>'
    top = (f'<div class="topbar"><div class="topbar-in"><div class="brand"><div class="brand-title">{esc(S["name"])}</div><div class="brand-sub">{S["horizon"]} · dữ liệu tới {hhmm(wl)} UTC</div></div>'
           f'<nav class="symnav">{symnav}</nav><div class="lanes" role="group" aria-label="Phương pháp">{lane_btns}</div></div></div>')
    lede = (f'<div class="lede"><div><p class="eyebrow">{"MT5 bridge (tick volume)" if market == "cfd" else "Binance public REST"} · {S["horizon"]} · phân tích, không phải tín hiệu</p><h1>{esc(S["name"])}</h1>'
            '<p>Mỗi phương pháp đọc bằng đúng ngôn ngữ của nó — Wyckoff (giá + khối lượng), ICT (cấu trúc giá), Footprint và Heatmap khi có dữ liệu — rồi mới tổng hợp. Ba lớp đọc: sơ bộ (máy quét), cục bộ (Sonnet, theo sự kiện), toàn diện (hàng ngày).</p></div>'
            '<div class="disclaimer">KHÔNG PHẢI TÍN HIỆU GIAO DỊCH · chỉ nghiên cứu</div></div>')
    built = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    footer = (f'<footer><b>Nguồn dữ liệu</b>: {" · ".join(esc(x) for x in src_notes)}<br>'
              f'<b>Lớp 1</b> scanner {esc(facts.get("scanned_at", "—"))} · <b>Lớp 3</b> {esc((narrative or {}).get("updated", "chưa có"))} · <b>trang dựng</b> {built} bởi scripts/build-artifact.py ({style})<br>'
              '<b>Luật</b>: số liệu từ code (SYSTEM-DESIGN §13); mỗi khối phương pháp qua scripts/method_purity.py; Footprint lấy Wyckoff làm nền. Tham số khối lượng: docs/architecture/analysis-params.json (tham số dự án, không phải trích dẫn sách).</footer>')

    data_json = json.dumps(data_js, ensure_ascii=False)
    for _, key, _, _ in S["syms"]:
        data_json = data_json.replace(f'"__ROWS__{key}"', rows_store[key][0]).replace(f'"__CTX__{key}"', rows_store[key][1])
    page = ('<title>' + esc(S["name"]) + '</title>\n'
            + theme.FONTS + '\n'
            + CSS.replace('__TOKENS__', theme.TOKENS) + top + '<div class="page">' + lede + meta_html + "".join(sections) + glossary() + footer + '</div>\n'
            + JS.replace("__DATA__", data_json).replace("__PARAMS__", json.dumps(P)))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    if snap:
        json.dump({"style": style, "built": built, "out": out, "facts_scanned_at": facts.get("scanned_at"), "narrative_updated": (narrative or {}).get("updated"),
                   "sources": src_notes}, open(os.path.join(snap, "build-manifest.json"), "w"), ensure_ascii=False, indent=1)
    print(f"BUILD OK -> {os.path.relpath(out, ROOT) if out.startswith(ROOT) else out} ({len(page) // 1024} KB) · layer1 {facts.get('scanned_at', '—')} · layer3 {(narrative or {}).get('updated', '—')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("style", choices=STYLES.keys()); ap.add_argument("--out"); ap.add_argument("--snapshot-dir")
    ap.add_argument("--narrative"); ap.add_argument("--allow-impure", action="store_true"); ap.add_argument("--check-only", action="store_true")
    a = ap.parse_args()
    if not a.out and not a.check_only:
        ap.error("--out is required unless --check-only")
    build(a.style, a.out or os.devnull, a.snapshot_dir, a.narrative, a.allow_impure, a.check_only)


if __name__ == "__main__":
    main()
