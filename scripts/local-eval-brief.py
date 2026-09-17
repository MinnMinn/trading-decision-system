#!/usr/bin/env python3
"""Print the brief for a Sonnet 'đánh giá cục bộ' (local read) of one chart style.

Rule of the system (2026-09-10): NUMBERS COME FROM CODE, WORDS FROM THE MODEL. The brief therefore contains the
scanner's FACTS (data/live/prelim/<style>.facts.json) and the last N candles; the model may only quote those
numbers. Output contract for the model is spelled out inside the brief (one HTML file per symbol under
data/live/prelim/<style>.<SYM>.model.html, no publishing). Validate the result with scripts/check-model-prose.py.

Usage: local-eval-brief.py <style> [--bars 40] [--symbols BTCUSDT,ETHUSDT,SOLUSDT] [--events "free text"]
"""
import argparse, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import importlib.util as _iu  # noqa: E402
import instruments as I  # noqa: E402
_as = _iu.spec_from_file_location("automation", os.path.join(ROOT, "scripts", "automation.py"))
_auto = _iu.module_from_spec(_as); _as.loader.exec_module(_auto)
# style -> (timeframe code as scripts/fetch-binance-klines.sh spells it, bars in the window).
# The `cfd-` prefixed styles are XAUUSD via the MT5 bridge (the EA exports 200 bars per timeframe,
# InpBarsToExport); the bare names are crypto. Nine names: three horizons x three markets (forex added 2026-09-17), derived
# in scripts/automation.py (HORIZON_TF / STYLE) -- this table only adds the WINDOW each one reads.
# The 1H/4H window sizes (240 / 180) are PROJECT PARAMETERS -- no source prescribes them; they are ~10 days of
# hourly and ~30 days of 4-hourly bars. On the MT5 bridge a 240-bar 1H request simply yields the 200 bars the EA
# exports until InpBarsToExport is raised.
# Authored per HORIZON, then mapped over every market -- it was written out once per style, so the "six names,
# three horizons x two markets" the comment above describes was six rows that could disagree with each other.
_HZ_WINDOW = {"scalping": ("15m", 288), "day": ("1H", 240), "swing": ("4H", 180)}
TF = {_auto.STYLE[(_m, _auto.HORIZON_TF[_h])]: _w
      for _m in _auto.MARKETS for _h, _w in _HZ_WINDOW.items()}
# Feed directory comes from instruments.py (I.data_dir), keyed by market -- was a hard-coded symbol set.
CITES = """- Trading Range: WA p71–72 · knowledge/07 §2.7 · WMT p023–026 · knowledge/08 §2.4 · Pha A–E (phases): knowledge/07 §2.7–2.10
- Spring/Shakeout (sự kiện): WA p80 · knowledge/07 §2.7.3 · Spring loại 1/2/3 (theo khối lượng): WMT p036–049 · knowledge/08 §2.6
- UT/UTAD: WA p8, knowledge/07 §2.8 · Upthrust loại 1/2/3: WMT p050–064 · knowledge/08 §2.7
- Nỗ lực–Kết quả (hài hoà/phân kỳ): WA p33–39 · knowledge/07 §2.2 · WMT p019–022, p149–154 · knowledge/08 §2.3, §4.1
- PS/SC/AR/ST/UA/SOS/LPS/BU: knowledge/07 §2.7 (tích lũy) · PSY/BCLX/UT/UTAD/SOW/LPSY: knowledge/07 §2.8 (phân phối)
- CHoBEV/CHoCH (cổng bắt buộc trước khi gán nhãn pha): WA p67–71 · knowledge/07 §2.6
- Đối nhãn (kiểm tra gán nhãn sai): WA p150–184 · knowledge/07 §2.11 · Kế hoạch CO theo pha: knowledge/07 §3.4
- Tape Reading chỉ cần biên độ + khối lượng (không cần Delta): WA p221–243 · knowledge/07 §4.1 · SOT: WA p277–292 · knowledge/07 §4.6
- Killzones: docs/TTrades PDFs/1. Killzones.pdf tr.1–2 · knowledge/04 §2.1 — hai bộ giờ EST, không có luật cho crypto/CFD; hệ thống dùng docs/architecture/session-model.md (london 08:00–11:00 Europe/London, ny_am 08:30–11:00 và ny_pm 13:30–16:00 America/New_York, đổi sang UTC theo ngày — tham số dự án, nói rõ); không tính điểm dưới 15m và cuối tuần
- Liquidity: docs/TTrades PDFs/3. Liquidity.pdf tr.1–5 · knowledge/04 §2.6–2.7
- Grab vs MSS: docs/TTrades PDFs/11. MSS_vs_Liquidity_Grab.pdf tr.1–4 · knowledge/04 §2.14, §2.17
- Premium/Discount: docs/TTrades PDFs/8. Discount__Premium.pdf tr.1–5 · knowledge/04 §2.18–2.19 · OTE: docs/TTrades PDFs/9. OTE.pdf tr.1–7 · knowledge/04 §2.20
- FVG: docs/TTrades PDFs/12. Fair_Value_Gaps.pdf tr.1–6 · knowledge/04 §2.21–2.24
- Displacement/MSS: docs/TTrades PDFs/18. Market_Structure_Shift.pdf tr.1–3 · knowledge/05 §2.1–2.2
- Order Block: docs/TTrades PDFs/17. Orderblocks.pdf tr.1–6 · knowledge/05 §2.5 · IRL/ERL: docs/TTrades PDFs/IRL-ERL.pdf tr.1–8 · knowledge/05 §2.13
- Số do hệ thống tính: [tính toán của hệ thống — không phải trích dẫn tài liệu] · không có nguồn: [chưa có nguồn trong docs/]"""


def fmt(sym, v):
    if v is None: return "—"
    return f"{v:,.0f}" if sym.startswith("BTC") else f"{v:,.2f}"


def data_path(sym, tf):
    base = I.data_dir(sym)
    return f"{ROOT}/data/live/{base}/ohlcv.{sym}.{tf}.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("style", choices=TF.keys()); ap.add_argument("--bars", type=int, default=40)
    ap.add_argument("--symbols", default=None); ap.add_argument("--events", default="")
    ap.add_argument("--snapshot-dir", default=os.environ.get("TMPDIR", "/tmp"), help="where to freeze facts + candles for this read")
    ap.add_argument("--manual", action="store_true", help="user-requested one-off read: bypass the /automation gate (crons never pass this)")
    a = ap.parse_args()
    # Automation switch (docs/architecture/automation-config.json, written only by scripts/automation.py).
    # Missing file = unconfigured = behave as before; present file is authoritative and can only stop this read.
    # The (market, timeframe) -> style mapping lives in scripts/automation.py so the vocabulary cannot drift;
    # if that module is unavailable we fail OPEN, exactly as a missing config file does.
    _auto = None
    try:
        import importlib.util
        _s = importlib.util.spec_from_file_location("automation", f"{ROOT}/scripts/automation.py")
        _auto = importlib.util.module_from_spec(_s); _s.loader.exec_module(_auto)
        _ok, _why = _auto.allows("local_read", a.style)
    except Exception:
        _ok, _why = True, None
    if not _ok and not a.manual:
        print(f"# đánh giá cục bộ '{a.style}' tắt: /automation — {_why}  (một lần đọc thủ công theo yêu cầu người dùng: thêm --manual)"); return
    if not _ok and a.manual:
        print(f"# /automation đang tắt ({_why}) — đọc THỦ CÔNG theo yêu cầu người dùng; không có tick nền nào chạy.")
    tf, n = TF[a.style]
    if a.symbols is None:
        # ONE definition of which market a flat style name belongs to: automation.market_of_style -- not a second
        # prefix test here, which is how `gold` came to mean the market in one file and the instrument in another.
        # The `startswith` is reached ONLY when automation.py itself would not import, the same unconfigured path
        # the gate above fails open on; it is the fallback for an unreachable source, not a second source.
        _cfd = _auto.market_of_style(a.style) == "cfd" if _auto else a.style.startswith("cfd-")
        a.symbols = "XAUUSD" if _cfd else "BTCUSDT,ETHUSDT,SOLUSDT"
    # Freeze the scanner outputs for THIS read: the background scanner rewrites facts.json on its own
    # cadence (scalping is 15m since 2026-09-13 -- scan-loop.sh fires it at :01/:16/:31/:46, not every minute),
    # so the model must be judged against the snapshot it was given, not against whatever is newest at check time.
    import shutil, time
    snap_dir = os.path.join(a.snapshot_dir, f"local-eval-{a.style}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}")
    os.makedirs(snap_dir, exist_ok=True)
    facts_path = os.path.join(snap_dir, "facts.json")
    shutil.copy(f"{ROOT}/data/live/prelim/{a.style}.facts.json", facts_path)
    syms = a.symbols.split(",")
    for sym in syms:
        shutil.copy(data_path(sym, tf), os.path.join(snap_dir, f"ohlcv.{sym}.{tf}.json"))
    facts = json.load(open(facts_path, encoding="utf-8"))
    print(f"# Đánh giá cục bộ · {a.style} · {tf}×{n} · dữ liệu tới {facts['window_last']} · scanner chạy {facts['scanned_at']}")
    print(f"SNAPSHOT: {snap_dir}  (facts + candles đã đóng băng cho lần đọc này; scanner nền vẫn cập nhật file gốc)")
    if a.events: print(f"\nSự kiện kích hoạt: {a.events}")
    print("""
## Luật viết (bắt buộc)
1. CHỈ dùng các con số có trong FACTS bên dưới (giá, %, mốc, thời điểm, entry/stop/target/R, bội số volume). Không tự tính, không làm tròn khác đi. Cần một con số không có → viết "chưa có trong facts".
2. Việc của bạn là phán đoán ngữ cảnh mà scanner không làm được: grab-and-reverse hay tiếp diễn; displacement có thật không (nến MSS và volume); FVG có hợp lệ và chưa lấp không; vị trí premium/discount so với vùng giao dịch; Nỗ lực-vs-Kết quả; điều kiện vô hiệu setup.
3. Mỗi đoạn kết thúc bằng <span class="cite">…</span> theo bản đồ trích dẫn. Không bịa nguồn.
4. Kết luận mỗi mã đúng một trong: CHỜ / THEO DÕI LONG / THEO DÕI SHORT / SETUP TIỀM NĂNG. Nếu SETUP TIỀM NĂNG: nêu entry/stop/target/R đúng như facts và điều kiện vô hiệu. Nếu facts không có setup hoàn chỉnh thì không được kết luận SETUP TIỀM NĂNG.
5. Tiếng Việt chuyên ngành, 3–6 câu mỗi mã, không nhắc lại bảng facts.
6. MỖI PHƯƠNG PHÁP MỘT NGÔN NGỮ (quyết định 2026-09-11). Ghi ra đúng một file mỗi mã, không publish, không sửa file nào khác:
   data/live/prelim/<style>.<SYM>.model.html với cấu trúc BẮT BUỘC, đúng thứ tự:
   <div class="prelim-head">Đánh giá cục bộ (Sonnet) · dữ liệu tới HH:MM UTC · <strong>VERDICT</strong></div>
   <div class="m-wyckoff"><p>…<span class="cite">…</span></p>…</div>
   <div class="m-ict"><p>…<span class="cite">…</span></p>…</div>
   <div class="m-synth"><p>…<span class="cite">…</span></p>…</div>
   (HH:MM = giờ của nến cuối trong FACTS của mã đó; VERDICT = một trong bốn kết luận ở mục 4; m-footprint / m-heatmap chỉ thêm khi CoinGlass AVAILABLE.)
   - m-wyckoff: chỉ kiến thức và thuật ngữ Wyckoff (giá + khối lượng: SC/AR/ST/Spring/SOS/LPS, pha A–E, Nỗ lực–Kết quả, hấp thụ, CHoCH…). CẤM mọi từ ICT: FVG, MSS, order block, BSL/SSL/ERL, premium/discount, EQ, killzone, displacement, thanh khoản/liquidity/sweep.
   - m-ict: chỉ kiến thức và thuật ngữ ICT (dealing range, EQ, premium/discount, BSL/SSL, sweep vs MSS, displacement, FVG, OB, killzone…). CẤM mọi từ Wyckoff VÀ CẤM nhắc khối lượng/volume/KL (ICT không có khái niệm khối lượng — knowledge/10 §4.1). Mốc neo có tên Wyckoff (SC, AR…) chỉ được gọi bằng giá.
   - m-synth: tổng hợp — nơi DUY NHẤT được đặt hai phương pháp cạnh nhau: luật khử trùng lặp (knowledge/10 §4.3: mốc Wyckoff trùng mốc ICT = một quan sát), kết luận, entry/stop/target/R (nếu có), điều kiện vô hiệu và chủ sở hữu vô hiệu (Wyckoff hay ICT, knowledge/10 §4.4).
   Máy kiểm tra (scripts/method_purity.py) chặn xuất bản nếu một khối dùng sai từ vựng.
8. THANG KHUNG — GIẢM KHUNG (bắt buộc, knowledge/07 §2.7 "Giảm khung của tích lũy", WA p93–96; knowledge/10 §4.2; docs/architecture/timeframe-mapping.md): mỗi style có ba tầng, đọc từ trên xuống — Bias (khung chậm nhất) → Cấu trúc (khung giữa, ≥ ×4 khung vào lệnh) → Vào lệnh (khung của style này). Mục "THANG KHUNG" bên dưới in số liệu do code tính cho tầng Bias và tầng Cấu trúc, và ghi tầng nào QUYẾT ĐỊNH bias cho verdict. Khối m-synth PHẢI mở đầu bằng câu "<Tên tầng> <khung>: …" (ví dụ "Bias 4h: …") nêu cấu trúc/pha của tầng quyết định và bias; câu thứ hai nói tầng Cấu trúc có cùng hướng hay không. Verdict THEO DÕI đi ngược bias phải ghi rõ "ngược bối cảnh". KHÔNG được kết luận SETUP TIỀM NĂNG ngược bias. Không bao giờ tạo bias từ khung vào lệnh. Khung lớn pha B chỉ cho bias khi giá đang ở biên TR khung lớn theo hướng cấu trúc (tích lũy: 1/3 dưới, nơi CO gom hàng và khung nhỏ in Spring[C]/LPS[C] cục bộ — WA p93, p201; phân phối: 1/3 trên); giữa vùng hoặc biên đối diện thì bias trung lập ("nguồn cung/cầu đang khá cân bằng … chưa cho thấy sự xuất hiện của CO", WA p95) và tối đa là THEO DÕI. Pha A / chưa xác lập: trung lập. scripts/check-model-prose.py kiểm tra cả ba điều này.
7. Sau khi ghi, chạy ĐÚNG lệnh này (so với snapshot của lần đọc này, không so với facts mới hơn):
   python3 scripts/check-model-prose.py <style> --facts <SNAPSHOT>/facts.json
   và sửa cho tới khi nó in `RESULT: OK`. Không chạy lại brief để "đuổi" dữ liệu mới hơn.

## Bản đồ trích dẫn
""" + CITES)
    import importlib.util as _iu
    _hs = _iu.spec_from_file_location("htf_context", f"{ROOT}/scripts/htf_context.py"); _htf = _iu.module_from_spec(_hs); _hs.loader.exec_module(_htf)
    _engaged = _htf.engaged_methods(a.style)
    # Which method blocks THIS run owes. Mục 6 lists the shape of all four; /automation decides which are required,
    # and scripts/check-model-prose.py checks exactly this set. Demanding m-wyckoff in an ICT-only run forced the
    # model to write Wyckoff prose the run does not read (audit 2026-09-13).
    print(f"\n## KHỐI BẮT BUỘC CHO LẦN CHẠY NÀY (/automation): "
          + " + ".join(f"m-{m}" for m in _engaged + ("synth",))
          + (f"  — KHÔNG viết khối m-{', m-'.join(m for m in ('wyckoff', 'ict') if m not in _engaged)}: "
             "dimension đang tắt, khối đó sẽ bị check-model-prose.py từ chối."
             if set(("wyckoff", "ict")) - set(_engaged) else ""))
    print("\n## THANG KHUNG (code tính; luật giảm khung — knowledge/07 §2.7, WA p93–96; docs/architecture/timeframe-mapping.md)")
    print(f"Chỉ in bản đọc của lớp đang bật: {', '.join(_engaged) or '(không có lớp nào)'}.")
    for sym in syms:
        f = lambda v: fmt(sym, v)
        print(f"\n## {sym}"); print("\n".join(_htf.ladder_lines(a.style, sym, f, methods=_engaged)))
    print("\n## FACTS (scanner, không được thay đổi)")
    for sym in syms:
        d = facts["symbols"][sym]; f = lambda v: fmt(sym, v)
        print(f"\n### {sym}")
        print(f"- Giá {f(d['last'])} lúc {d['last_time']} · {d['pct']*100:.0f}% biên độ cửa sổ ({f(d['lo'])}–{f(d['hi'])}) · EQ {f(d['eq'])} · stance scanner: {d['stance']}")
        an = d.get("anchors")
        if an:
            for L in an["levels"]:
                fb = L["first_close_beyond"]
                print(f"- Mốc {L['label']} {f(L['price'])} ({L['time']}): nến đóng tham chiếu {an['ref_close']['time']} = {f(an['ref_close']['close'])} nằm {'trên' if L['ref_vs']=='above' else 'dưới'} ({L['dist_pct']:+.2f}%)"
                      + (f"; nến đóng vượt đầu tiên {fb['time']} @ {f(fb['close'])}; cực trị sau đó {f(L['extreme_since'])}" if fb else "; chưa có nến đóng vượt")
                      + (f"; nến đang hình thành hiện đang vượt" if L['forming_beyond'] else ""))
            print(f"- Verdict theo luật: {an['verdict']}")
        m = d.get("last_mss")
        if m: print(f"- MSS gần nhất: {'tăng' if m['type']=='bull' else 'giảm'}, đóng vượt swing {f(m['level'])}, volume {m.get('vol_mult')}× trung bình")
        g = d.get("nearest_fvg")
        if g: print(f"- FVG chưa lấp gần nhất: {'tăng' if g['type']=='bull' else 'giảm'} {f(g['lo'])}–{f(g['hi'])}")
        up = d.get("unswept_pools") or []
        if up: print("- Pool chưa quét: " + ", ".join(f"{p['kind']} {f(p['level'])}" for p in up[-6:]))
        ev = [e for e in d.get("events_recent", []) if e["kind"] in ("sweep", "mss_bull", "mss_bear", "erl_high", "erl_low", "volume")]
        if ev:
            def ev_s(e):
                if e["kind"] == "sweep": return f"quét {e['pool']} {f(e['level'])} @{e['time'][11:16]}Z"
                if e["kind"].startswith("mss"): return f"MSS {'tăng' if e['kind']=='mss_bull' else 'giảm'} {f(e['level'])} @{e['time'][11:16]}Z"
                if e["kind"] == "volume": return f"volume {e['mult']}× ({'tăng' if e['dir']=='up' else 'giảm'}) @{e['time'][11:16]}Z"
                return f"{e['kind']} {f(e['level'])} @{e['time'][11:16]}Z"
            print("- Sự kiện gần đây: " + "; ".join(ev_s(e) for e in ev[-8:]))
        su = d.get("setup")
        if su:
            if su.get("complete"):
                print(f"- Setup ứng viên {su['side'].upper()}: quét {su['sweep']['pool']} {f(su['sweep']['level'])} @{su['sweep']['time'][11:16]}Z → MSS {f(su['mss']['level'])} @{su['mss']['time'][11:16]}Z (vol {su['mss']['vol_mult']}×) → FVG {f(su['fvg']['lo'])}–{f(su['fvg']['hi'])}{' đã lấp' if su['fvg']['mitigated'] else ' chưa lấp'} · entry {f(su['entry'])} · stop {f(su['stop'])} · target {f(su['target'])} ({su['target_kind']}) · R = {su['R']} · {'discount' if su['in_discount'] else 'premium'}")
            else:
                print(f"- Setup ứng viên {su['side'].upper()} CHƯA hoàn chỉnh: thiếu {su['missing']} (không được kết luận SETUP TIỀM NĂNG)")
        else:
            print("- Setup ứng viên: không có chuỗi quét→MSS cùng chiều trong các nến gần đây")
    print(f"\n## {a.bars} nến gần nhất (time, open, high, low, close, volume/avg)")
    for sym in syms:
        rows = json.load(open(os.path.join(snap_dir, f"ohlcv.{sym}.{tf}.json")))["candles"][-n:]
        avg = sum(r.get("volume", 0) for r in rows) / len(rows) if rows else 0
        print(f"\n{sym}:")
        for r in rows[-a.bars:]:
            print(f"{r['time'][5:16]} {r['open']} {r['high']} {r['low']} {r['close']} {r.get('volume',0)/avg:.2f}x" if avg else f"{r['time'][5:16]} {r['open']} {r['high']} {r['low']} {r['close']}")


if __name__ == "__main__":
    main()
