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
import instruments as I  # noqa: E402

# (short id for CSS/HTML ids, display name, price-format kind: "int" or "2" decimals) -- presentation-only;
# the symbol SET itself comes from instruments.py (single source of truth, SYSTEM-DESIGN.md §1), never hand-kept here.
CRYPTO_META = {
    "BTCUSDT": ("btc", "BTC/USDT", "int"),
    "ETHUSDT": ("eth", "ETH/USDT", "2"),
    "SOLUSDT": ("sol", "SOL/USDT", "2"),
    "ASTERUSDT": ("aster", "ASTER/USDT", "2"),
    "VIRTUALUSDT": ("virtual", "VIRTUAL/USDT", "2"),
    "SUIUSDT": ("sui", "SUI/USDT", "2"),
    "TAOUSDT": ("tao", "TAO/USDT", "2"),
    "RENDERUSDT": ("render", "RENDER/USDT", "2"),
    "ONDOUSDT": ("ondo", "ONDO/USDT", "2"),
}
CRYPTO = [(sym, *CRYPTO_META[sym]) for sym in I.analysis("crypto")]
GOLD = [("XAUUSD", "xau", "XAU/USD", "2")]
MT5 = {"XAUUSD", "XAGUSD", "USOIL", "UKOIL"}
TF_MIN = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "1H": 60, "2H": 120, "4H": 240, "1D": 1440, "1W": 10080}
# Per-timeframe window spec (bars, axis label, human horizon). Bar counts are project parameters (no source gives them;
# they only need to hold the previous day/week/month for the PDH/PWH/PMH reads, knowledge/04 §2.8).
TF_SPEC = {"1m": (360, "%H:%M", "6 giờ"), "5m": (576, "%m-%d %H:%M", "48 giờ"), "15m": (576, "%m-%d %H:%M", "6 ngày"),
           "1H": (480, "%m-%d %H:%M", "20 ngày"), "4H": (360, "%m-%d %H:%M", "60 ngày"), "1D": (240, "%m-%d", "8 tháng"), "1W": (208, "%y-%m-%d", "4 năm")}
TF_LABEL = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1H", "4h": "4H", "1D": "1D", "1W": "1W"}   # automation spelling -> file spelling
TIER_NAME = {"bias": "Bias", "structure": "Cấu trúc", "entry": "Vào lệnh"}
TIER_ORDER = ("bias", "structure", "entry")
import importlib.util as _iu
_as = _iu.spec_from_file_location("automation", os.path.join(ROOT, "scripts", "automation.py")); _auto = _iu.module_from_spec(_as); _as.loader.exec_module(_auto)


def _style(tf, syms, name, kz):
    n, lbl, hz = TF_SPEC[tf]
    return dict(tf=tf, n=n, lbl=lbl, syms=syms, name=name, horizon=f"{tf} × {n} ({hz})", kz=kz)


# The three tiers of every style come from ONE table: scripts/automation.py TIERS (docs/architecture/timeframe-mapping.md).
STYLES = {
    "scalping":   _style("1m",  CRYPTO, "Crypto Scalping", False),
    "daytrade":   _style("15m", CRYPTO, "Crypto Day", True),
    "1h":         _style("1H",  CRYPTO, "Crypto 1H", True),
    "4h":         _style("4H",  CRYPTO, "Crypto 4H", False),
    "swing":      _style("1D",  CRYPTO, "Crypto Swing", False),
    "gold-scalp": _style("5m",  GOLD,   "CFD Scalping", True),
    "gold":       _style("15m", GOLD,   "CFD Day", True),
    "gold-1h":    _style("1H",  GOLD,   "CFD 1H", True),
    "gold-4h":    _style("4H",  GOLD,   "CFD 4H", False),
    "gold-swing": _style("1D",  GOLD,   "CFD Swing", False),
}
for _st, _S in STYLES.items():
    _S["tiers"] = {}
    for _name in ("bias", "structure"):
        _t = _auto.TIERS[_st].get(_name)
        if _t:
            _tf = TF_LABEL[_t["tf"]]; _n, _lbl, _hz = TF_SPEC[_tf]
            _S["tiers"][_name] = dict(tf=_tf, n=_n, lbl=_lbl, style=_t["style"], horizon=f"{_tf} × {_n} ({_hz})")
        else:
            _S["tiers"][_name] = None
VERDICT_CLASS = [("SETUP", "setup"), ("THEO DÕI LONG", "long"), ("THEO DÕI SHORT", "short"), ("PHÁ", "warn"), ("CHỜ", "wait")]
import htf_context as htf  # noqa: E402
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


PLAN_FIELDS = ("id", "direction", "entry", "stop_loss", "targets", "planned_rr", "status", "rehearsal_mode", "date_opened", "setup_type")


def trade_plans(sym):
    """PLANNED / OPEN trade records for this instrument from trades/index.jsonl (the derived rollup, never hand-edited —
    SYSTEM-DESIGN §5). Read-only: the chart draws entry/stop/targets, it never writes a trade."""
    out = []
    try:
        with open(f"{ROOT}/trades/index.jsonl", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                if r.get("instrument") == sym and r.get("status") in ("PLANNED", "OPEN"):
                    out.append({k: r.get(k) for k in PLAN_FIELDS})
    except FileNotFoundError:
        pass
    return out


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
    if an.get("verdict"):
        rc = an.get("ref_close") or {}
        s.append(f"<li>Verdict theo luật so với mốc neo của phân tích đầy đủ gần nhất: <b>{esc(an['verdict'])}</b> (nến đóng {when(rc.get('time'))} = {fmtn(rc.get('close'), kind)}).</li>")
    else:
        s.append("<li>Chưa có mốc neo từ phân tích đầy đủ — scanner chỉ có stance theo luật cố định.</li>")
    for L in by["mixed"] + by["neutral"]:
        s.append(f"<li>Mốc neo (tổng hợp): {level_line(L, kind)}</li>")
    s.append(f"<li>Stance scanner: <b>{esc(d['stance'])}</b> (luật cố định, tham số dự án — không phải nhận định của mô hình).</li>")
    synth = "<ul>" + "".join(s) + "</ul>"
    return dict(ts=d.get("last_time"), stance=d["stance"], verdict=(an.get("verdict_short") or an.get("verdict")), wyckoff=wyckoff, ict=ict, synth=synth, facts=d)


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
    return f'<section class="glossary" id="sec-glossary"><details><summary>Thuật ngữ theo phương pháp <span class="muted">(mở khi cần)</span></summary><div class="gl-grid">{out}</div></details></section>'


def wy_json(wy):
    """Narrative wyckoff -> the chart overlay (TR, events, phases), addressed by candle time."""
    tr = (wy or {}).get("trading_range") or None
    return dict(tr=(dict(high=tr.get("high"), low=tr.get("low"), high_label=tr.get("high_label", "AR"), low_label=tr.get("low_label", "SC")) | {"from": tr.get("from")} if tr else None),
                events=[dict(time=e.get("time"), label=e.get("label", ""), up=bool(e.get("up"))) for e in (wy or {}).get("events", [])],
                phases=[{"from": p.get("from"), "to": p.get("to"), "label": p.get("label", "")} for p in (wy or {}).get("phases", [])])


BIAS_CLS = {"long": "long", "short": "short", "neutral": "wait", "unknown": "wait"}
BIAS_VI = {"long": "LONG", "short": "SHORT", "neutral": "TRUNG LẬP", "unknown": "CHƯA RÕ"}


def ladder(S, sym, kind, cur_verdict, l1, n3, tier_ctx, gate_name):
    """Three rows, top-down: Bias -> Cấu trúc -> Vào lệnh. Each row answers ONE question per method (Wyckoff: structure +
    phase + TR; ICT: dealing-range position + last MSS) and ends in one conclusion chip. Wording for a missing rung is
    printed, never skipped (docs/architecture/timeframe-mapping.md)."""
    tfmin = lambda tf: TF_MIN.get(tf, 0)
    ratio = lambda hi, lo: (f"×{tfmin(hi) / tfmin(lo):g}" if tfmin(hi) and tfmin(lo) else "")

    def wy_cell(w):
        if not w or not (w.get("structure") or w.get("phase")):
            return '<span class="muted">chưa có đọc Wyckoff cho khung này</span>'
        tr = w.get("trading_range") or {}
        out = f'<b>{esc(w.get("structure") or "chưa xác lập")}</b>' + (f' · pha <b>{esc(w["phase"])}</b>' if w.get("phase") else "")
        if tr.get("high") is not None and tr.get("low") is not None:
            out += f'<div class="ld-kv">{esc(tr.get("low_label", "SC"))} {fmtn(tr["low"], kind)} – {esc(tr.get("high_label", "AR"))} {fmtn(tr["high"], kind)}</div>'
        if w.get("updated"):
            out += f'<div class="ld-kv muted">đọc {esc(str(w["updated"])[:16])}Z</div>'
        return out

    def ict_cell(f):
        if not f or f.get("pct") is None:
            return '<span class="muted">chưa quét</span>'
        zone = "discount" if f["pct"] < 0.5 else "premium"
        out = f'<b>{f["pct"] * 100:.0f}%</b> dealing range ({fmtn(f.get("lo"), kind)}–{fmtn(f.get("hi"), kind)}) · <b>{zone}</b>'
        m = f.get("last_mss")
        out += f'<div class="ld-kv">MSS gần nhất: {"tăng" if m.get("type") == "bull" else "giảm"} qua {fmtn(m.get("level"), kind)}</div>' if m else '<div class="ld-kv muted">chưa có MSS trong cửa sổ</div>'
        return out

    rows = []
    for name in ("bias", "structure"):
        t = S["tiers"].get(name); c = tier_ctx.get(name)
        below = S["tiers"]["structure"]["tf"] if (name == "bias" and S["tiers"].get("structure")) else S["tf"]
        if not t:
            rows.append((name, "—", "", '<span class="muted">không lấy khung chậm hơn (khung tháng)</span>', '<span class="muted">—</span>', '<span class="chip chip-wait">—</span>', False))
            continue
        head = f'{t["tf"]} <span class="ld-ratio">{ratio(t["tf"], below)}</span>'
        if not t["style"]:
            rows.append((name, head, "chỉ chart, chưa quét", '<span class="muted">không có đọc — chỉ có chart</span>', '<span class="muted">không có số liệu</span>', '<span class="chip chip-wait">—</span>', False))
            continue
        chipv = f'<span class="chip chip-{BIAS_CLS.get(c["bias"], "wait")} chip-lg" title="{esc(c.get("basis", ""))}">{BIAS_VI.get(c["bias"], "?")}</span>' if c else '<span class="chip chip-wait">chưa quét</span>'
        rows.append((name, head, f'cập nhật {hhmm(c.get("last_time")) if c else "—"}Z', wy_cell(c and c.get("wyckoff")), ict_cell(c), chipv, name == gate_name))
    wy = (n3 or {}).get("wyckoff") or {}
    rows.append(("entry", S["tf"], f'cập nhật {hhmm(l1["ts"]) if l1 else "—"}Z', wy_cell({**wy, "updated": (n3 or {}).get("_updated_iso")} if wy else None), ict_cell(l1 and l1.get("facts")), chip(cur_verdict, "chip-lg"), False))
    body = '<div class="ld-head ld-corner">Tầng</div><div class="ld-head lane-wyckoff"><span class="lane-dot"></span>Wyckoff</div><div class="ld-head lane-ict"><span class="lane-dot"></span>ICT</div><div class="ld-head">Kết luận</div>'
    for name, head, sub, wc, ic, ch, is_gate in rows:
        g = " gate" if is_gate else ""
        body += (f'<div class="ld-tier{g}"><div class="ld-name">{TIER_NAME[name]}</div><div class="ld-tf">{head}</div><div class="ld-sub">{esc(sub)}</div></div>'
                 f'<div class="ld-cell lane-wyckoff{g}">{wc}</div><div class="ld-cell lane-ict{g}">{ic}</div><div class="ld-cell ld-verdict{g}">{ch}' + ('<div class="ld-sub">tầng quyết định verdict</div>' if is_gate else '') + '</div>')
    return f'<div class="ladder">{body}</div>'


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

/* timeframe ladder: three tiers, top-down, one question per method per tier */
.ladder{display:grid;grid-template-columns:150px minmax(0,1fr) minmax(0,1fr) 150px;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--surface)}
.ld-head{padding:8px 14px;font-family:var(--mono);font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2);background:var(--surface-3);border-bottom:1px solid var(--line);border-left:1px solid var(--line)}
.ld-head.lane-wyckoff,.ld-head.lane-ict{box-shadow:inset 0 -2px 0 var(--lane)} .ld-corner{border-left:0;color:var(--faint)}
.ld-tier{padding:10px 14px;border-top:1px solid var(--line);background:var(--surface-2)}
.ld-name{font-weight:800;font-size:13px} .ld-tf{font-family:var(--mono);font-size:12.5px;color:var(--ink-2);margin-top:1px} .ld-sub{font-family:var(--mono);font-size:10.5px;color:var(--faint);margin-top:2px}
.ld-ratio{font-family:var(--mono);font-size:10.5px;color:var(--faint);font-weight:400}
.ld-cell{padding:10px 14px;border-top:1px solid var(--line);border-left:1px solid var(--line);font-size:12.5px;line-height:1.45}
.ld-cell.lane-wyckoff,.ld-cell.lane-ict{box-shadow:inset 3px 0 0 var(--lane-soft)}
.ld-kv{font-family:var(--mono);font-size:11.5px;color:var(--ink-2);margin-top:3px}
.ld-verdict{display:flex;flex-direction:column;gap:4px;align-items:flex-start;justify-content:center}
.ld-tier.gate,.ld-cell.gate{background:color-mix(in srgb,var(--accent) 6%,var(--surface))}
.ld-tier.gate{box-shadow:inset 3px 0 0 var(--accent)}
.meta-ladder{grid-column:span 2} .ld-step b{font-family:var(--mono)} .ld-arrow{color:var(--faint);margin:0 2px}
.chart-missing .lane-status{padding:14px 16px}
.glossary summary{cursor:pointer;font-weight:800;font-size:15px;margin-bottom:10px}

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
.chart-wrap{padding:4px 6px 4px;position:relative}
.chart{display:block;width:100%;height:440px;cursor:crosshair}
.mode-status{padding:4px 12px 8px;font-family:var(--mono);font-size:11px;color:var(--accent)}
.mode-ruler .chart,.mode-replay .chart{outline:1px dashed var(--accent);outline-offset:-1px}
.zoom button.wide{width:auto;padding:0 6px}
.sw.plan{background:linear-gradient(90deg,var(--down-soft),var(--up-soft));border:1px solid var(--line-strong)}
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
  .ladder{grid-template-columns:1fr} .ld-head{display:none} .ld-cell{border-left:0} .meta-ladder{grid-column:span 1}
  .mx-head{display:none}
  .mx-label{border-top:2px solid var(--line-strong)}
  .mx-cell{border-left:0}
  .mx-cell-tag{display:block}
  .disclaimer{white-space:normal}
  .lanes{margin-left:0}
}
</style>
"""

VENDOR_JS = os.path.join(ROOT, "scripts", "vendor", "lightweight-charts.standalone.production.js")
CHART_JS = os.path.join(ROOT, "scripts", "chart.js")


def js_block(data_json, params_json):
    """The page's script: the vendored TradingView Lightweight Charts (pinned, inlined — no CDN), then scripts/chart.js,
    then the data call. See docs/specs/2026-09-12-chart-lightweight-charts-design.md §1."""
    with open(VENDOR_JS, encoding="utf-8") as f:
        vendor = f.read()
    with open(CHART_JS, encoding="utf-8") as f:
        chart = f.read()
    return ("<script>\n" + vendor + "\n</script>\n<script>\n" + chart + "\n</script>\n"
            "<script>TChart.init(" + data_json + ", " + params_json + ");</script>\n")



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
        note = f"{sym} {S['tf']}: {src or '?'} · cập nhật {upd or '?'}"
        # tiers above the working window (docs/architecture/timeframe-mapping.md; automation.TIERS is the table)
        tier_rows = {}
        for tname in ("bias", "structure"):
            t = S["tiers"].get(tname)
            if not t:
                continue
            try:
                trows, tupd, _ = candles(sym, t["tf"], t["n"], snap)
            except FileNotFoundError:
                continue
            tier_rows[tname] = trows
            note += f" · {TIER_NAME[tname].lower()} {t['tf']} cập nhật {tupd or '?'}"
        src_notes.append(note)
        fsym = (facts.get("symbols") or {}).get(sym)
        l1 = layer1(sym, fsym, kind, S["tf"]) if fsym else None
        l2 = layer2(style, sym)
        n3 = ((narrative or {}).get("symbols") or {}).get(sym)
        if n3:
            n3["_updated"] = when((narrative or {}).get("updated")); n3["_updated_iso"] = (narrative or {}).get("updated")
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
        wy_js = wy_json((n3 or {}).get("wyckoff"))
        # Wyckoff overlay per tier: the tier style's own full analysis (one read per candle series, two pages never disagree);
        # the gate tier falls back to this style's narrative.context when that style has no page yet
        gate_style, gate_name = _auto.gate_style(style)
        tier_ctx = {tn: htf.load_tier(style, tn, sym) for tn in ("bias", "structure")}
        tier_wy = {}
        for tname in tier_rows:
            t = S["tiers"][tname]; twy = {}
            if t["style"]:
                twy = (((read_json(f"{ROOT}/data/live/narrative/{t['style']}.json") or {}).get("symbols") or {}).get(sym) or {}).get("wyckoff") or {}
            if not twy.get("events") and tname == gate_name:
                twy = ((n3 or {}).get("context") or {}).get("wyckoff") or {}
            tier_wy[tname] = wy_json(twy)
        tiers_js = []
        for tname in ("bias", "structure"):
            if tname in tier_rows:
                t = S["tiers"][tname]
                tiers_js.append(dict(key=tname, tf=t["tf"], kz=(t["tf"] in ("15m", "1H")), tfMin=TF_MIN.get(t["tf"], 0), wy=tier_wy[tname], levels=[], compact=True, rows="__ROWS__" + key + tname))
        tiers_js.append(dict(key="entry", tf=S["tf"], kz=S["kz"], tfMin=TF_MIN.get(S["tf"], 0), wy=wy_js, levels=levels, compact=False, rows="__ROWS__" + key + "entry"))
        data_js[key] = dict(fmt=kind, tick=(sym in MT5), market=("metals" if sym in ("XAUUSD", "XAGUSD") else "oil" if sym in MT5 else "crypto"),
                            dims={m: dims[m]["reason"] for m in dims}, tiers=tiers_js, plans=trade_plans(sym), invalidation=(n3 or {}).get("invalidation"))
        rows_store[key] = {**{tn: rows_js(tier_rows[tn], S["tiers"][tn]["lbl"]) for tn in tier_rows}, "entry": rows_js(rows, S["lbl"])}
        # section html: header (one price, one verdict), the ladder (three tiers, both methods), three charts top-down
        lo, hi = min(r["low"] for r in rows), max(r["high"] for r in rows); last = rows[-1]["close"]
        pct = (last - lo) / (hi - lo) if hi > lo else 0
        cur_verdict = (l2 or {}).get("verdict") or (l1 or {}).get("verdict") or "—"
        status_chips.append(f'<span class="st"><span class="mono">{disp.split("/")[0]}</span>{chip(cur_verdict)}</span>')
        head = (f'<div class="sym-head"><div class="sym-name">{disp}</div><div class="sym-last">{fmtn(last, kind)}</div>'
                f'<div class="sym-kv"><span>vị trí trong cửa sổ {S["tf"]} <b>{pct * 100:.0f}%</b></span><span>nến cuối <b>{when(rows[-1]["time"])}</b></span></div>'
                f'<div class="sym-verdict"><span class="lbl">vào lệnh {S["tf"]}</span>{chip(cur_verdict, "chip-lg")}</div></div>')
        ladder_html = ladder(S, sym, kind, cur_verdict, l1, n3, tier_ctx, gate_name)
        charts_html = ""
        for tname in ("bias", "structure"):
            t = S["tiers"].get(tname)
            if not t:
                continue
            if tname not in tier_rows:
                charts_html += f'<div class="chart-block chart-missing"><div class="chart-title"><span><b>{TIER_NAME[tname]}</b> · {t["horizon"]}</span></div><div class="lane-status">chưa có nến {t["tf"]} cho {disp} — khung này chưa được lấy</div></div>'
                continue
            trows = tier_rows[tname]
            charts_html += (f'<div class="chart-block" id="{tname}-{key}"><div class="chart-title"><span><b>{TIER_NAME[tname]}</b> · {t["horizon"]} · {label(trows[0]["time"], t["lbl"])} → {label(trows[-1]["time"], t["lbl"])}</span><span class="zoom"><span class="muted">vùng tô = cửa sổ vào lệnh</span><button data-z="out" title="thu nhỏ">−</button><button data-z="in" title="phóng to">+</button><button data-z="reset" title="toàn bộ cửa sổ">⟲</button></span></div>'
                            f'<div class="chart-wrap"><div class="chart" id="chart-{tname}-{key}"></div><div class="tip"></div></div><div class="mode-status" hidden></div><div class="lane-status" hidden></div></div>')
        charts_html += (f'<div class="chart-block" id="entry-{key}"><div class="chart-title"><span><b>Vào lệnh</b> · {S["horizon"]} · {label(rows[0]["time"], S["lbl"])} → {label(rows[-1]["time"], S["lbl"])}</span><span class="zoom"><span class="muted">lăn chuột = zoom · kéo = dịch · kéo trục = co giãn · End = nến cuối · phím 1–4 đổi phương pháp</span><button data-z="out" title="thu nhỏ">−</button><button data-z="in" title="phóng to">+</button><button data-z="reset" title="toàn bộ cửa sổ">⟲</button><button data-z="ruler" class="wide" title="thước R:R (phím R)">R:R</button><button data-z="replay" class="wide" title="bar replay (phím P)">▶</button></span></div>'
                        f'<div class="chart-wrap"><div class="chart" id="chart-entry-{key}"></div><div class="tip"></div></div><div class="mode-status" hidden></div><div class="lane-status" hidden></div></div>')
        legend = f'<div class="legend" id="legend-{key}"></div>'
        sections.append(f'<section class="symbol" id="sec-{key}">{head}{ladder_html}<div class="charts">{charts_html}{legend}</div>{matrix(key, kind, l1, l2, n3, dims)}{timeline((n3 or {}).get("timeline"))}</section>')

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
    headline = (narrative or {}).get("headline") or {}
    tfmin = lambda tf: TF_MIN.get(tf, 0)
    steps = []
    for tname in ("bias", "structure"):
        t = S["tiers"].get(tname)
        below = (S["tiers"]["structure"]["tf"] if (tname == "bias" and S["tiers"].get("structure")) else S["tf"])
        if t:
            r = f' <span class="ld-ratio">×{tfmin(t["tf"]) / tfmin(below):g}</span>' if tfmin(t["tf"]) and tfmin(below) else ""
            steps.append(f'<span class="ld-step">{TIER_NAME[tname]} <b>{t["tf"]}</b>{r}{"" if t["style"] else " <span class=\"muted\">(chỉ chart)</span>"}</span>')
        else:
            steps.append(f'<span class="ld-step muted">{TIER_NAME[tname]} —</span>')
    steps.append(f'<span class="ld-step">Vào lệnh <b>{S["tf"]}</b></span>')
    _, gate_name = _auto.gate_style(style)
    gate_note = f'tầng quyết định verdict: {TIER_NAME[gate_name]}' if gate_name else 'không có tầng quyết định verdict (chưa quét khung chậm hơn)'
    meta_html = ('<div class="meta">'
                 f'<div class="meta-ladder"><div class="meta-l">Thang khung · đọc từ trên xuống</div><div class="meta-v">{" <span class=\"ld-arrow\">→</span> ".join(steps)}</div><div class="meta-d">{gate_note} · bias không tạo ở khung vào lệnh · liền kề ≥ ×4 (timeframe-mapping.md)</div></div>'
                 + f'<div><div class="meta-l">Sự kiện chính (phân tích đầy đủ gần nhất)</div><div class="meta-v">{headline.get("text", "—")}</div><div class="meta-d">{headline.get("detail", "")}</div></div>'
                 + f'<div><div class="meta-l">Trạng thái (cục bộ)</div><div class="meta-v">{" ".join(status_chips)}</div><div class="meta-d">dữ liệu tới {hhmm(wl)} UTC</div></div>'
                 '</div>')
    lane_btns = "".join(f'<button class="lane-btn lane-{k}{"" if k in ("wyckoff", "ict") else " off"}" data-lane="{k}" onclick="setLane(\'{k}\')" title="phím {i + 1}"><span class="lane-dot"></span>{n}</button>' for i, (k, n) in enumerate(LANES))
    symnav = "".join(f'<a href="#sec-{key}">{disp.split("/")[0]}</a>' for _, key, disp, _ in S["syms"]) + '<a href="#sec-glossary">Thuật ngữ</a>'
    top = (f'<div class="topbar"><div class="topbar-in"><div class="brand"><div class="brand-title">{esc(S["name"])}</div><div class="brand-sub">{S["horizon"]} · dữ liệu tới {hhmm(wl)} UTC</div></div>'
           f'<nav class="symnav">{symnav}</nav><div class="lanes" role="group" aria-label="Phương pháp">{lane_btns}</div></div></div>')
    lede = (f'<div class="lede"><div><p class="eyebrow">{"MT5 bridge (tick volume)" if market == "cfd" else "Binance public REST"} · {S["horizon"]} · phân tích, không phải tín hiệu</p><h1>{esc(S["name"])}</h1>'
            '<p>Ba tầng khung cho mỗi mã — Bias → Cấu trúc → Vào lệnh — đọc bằng Wyckoff (giá + khối lượng) và ICT (cấu trúc giá) riêng rẽ, rồi tổng hợp.</p></div>'
            '<div class="disclaimer">KHÔNG PHẢI TÍN HIỆU GIAO DỊCH · chỉ nghiên cứu</div></div>')
    built = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    footer = (f'<footer><b>Nguồn dữ liệu</b>: {" · ".join(esc(x) for x in src_notes)}<br>'
              f'<b>Lớp 1</b> scanner {esc(facts.get("scanned_at", "—"))} · <b>Lớp 3</b> {esc((narrative or {}).get("updated", "chưa có"))} · <b>trang dựng</b> {built} bởi scripts/build-artifact.py ({style})<br>'
              f'<b>Chế độ</b> {esc(mode)}: Wyckoff + ICT · Footprint/Heatmap: không có nguồn live · <b>Lớp đọc</b>: sơ bộ (máy quét), cục bộ (Sonnet, theo sự kiện), toàn diện (hàng ngày)<br>'
              '<b>Luật</b>: số liệu từ code (SYSTEM-DESIGN §13); mỗi khối phương pháp qua scripts/method_purity.py; Footprint lấy Wyckoff làm nền. Scanner: pivot 3 nến, dung sai đỉnh/đáy bằng nhau 0,08%, FVG ≥ 0,6× biên độ trung vị; ngưỡng khối lượng: docs/architecture/analysis-params.json (tham số dự án, không phải trích dẫn sách).<br>'
              'Chart: TradingView Lightweight Charts™ · Copyright (c) 2025 TradingView, Inc. · <a href="https://www.tradingview.com/" rel="noopener">tradingview.com</a> · Apache-2.0 (scripts/vendor/NOTICE-lightweight-charts.txt)'
              '</footer>')

    data_json = json.dumps(data_js, ensure_ascii=False)
    for _, key, _, _ in S["syms"]:
        for tn, js in rows_store[key].items():
            data_json = data_json.replace(f'"__ROWS__{key}{tn}"', js)
    page = ('<title>' + esc(S["name"]) + '</title>\n'
            + theme.FONTS + '\n'
            + CSS.replace('__TOKENS__', theme.TOKENS) + top + '<div class="page">' + lede + meta_html + "".join(sections) + glossary() + footer + '</div>\n'
            + js_block(data_json, json.dumps(P)))
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
