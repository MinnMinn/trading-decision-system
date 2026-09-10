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
TF = {"scalping": ("1m", 180), "daytrade": ("15m", 288), "swing": ("1D", 120)}
CITES = """- Trading Range: WMT p023–026 · knowledge/07 §2.4 · Pha (phases): WMT p025–032 · knowledge/07 §2.5
- Spring: WMT p036–049 · knowledge/07 §2.6 · Upthrust: WMT p050–064 · knowledge/07 §2.7
- Effort-vs-Result: WMT p019–022, p149–154 · knowledge/07 §2.3, §4.1 · SOS/SOW: knowledge/07 §6
- SC/AR/ST/LPS: [thuật ngữ Wyckoff cổ điển — KHÔNG có trong docs/; knowledge/07 §2.5]
- Killzones: docs/TTrades PDFs/1. Killzones.pdf tr.1–2 · knowledge/04 §2.1 (London 06–09Z, NY AM 11–14Z; vô nghĩa trên 1m — nói rõ)
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("style", choices=TF.keys()); ap.add_argument("--bars", type=int, default=40)
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT"); ap.add_argument("--events", default="")
    ap.add_argument("--snapshot-dir", default=os.environ.get("TMPDIR", "/tmp"), help="where to freeze facts + candles for this read")
    a = ap.parse_args()
    tf, n = TF[a.style]
    # Freeze the scanner outputs for THIS read: the background scanner rewrites facts.json every minute (scalping),
    # so the model must be judged against the snapshot it was given, not against whatever is newest at check time.
    import shutil, time
    snap_dir = os.path.join(a.snapshot_dir, f"local-eval-{a.style}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}")
    os.makedirs(snap_dir, exist_ok=True)
    facts_path = os.path.join(snap_dir, "facts.json")
    shutil.copy(f"{ROOT}/data/live/prelim/{a.style}.facts.json", facts_path)
    syms = a.symbols.split(",")
    for sym in syms:
        shutil.copy(f"{ROOT}/data/live/market-data/ohlcv.{sym}.{tf}.json", os.path.join(snap_dir, f"ohlcv.{sym}.{tf}.json"))
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
6. Ghi ra đúng 3 file, không publish, không sửa file nào khác:
   data/live/prelim/<style>.<SYM>.model.html với cấu trúc:
   <div class="prelim-head">Đánh giá cục bộ (Sonnet) · dữ liệu tới HH:MM UTC · <strong>VERDICT</strong></div><p>…<span class="cite">…</span></p>…
   (HH:MM = giờ của nến cuối trong FACTS của mã đó; VERDICT = một trong bốn kết luận ở mục 4.)
7. Sau khi ghi, chạy ĐÚNG lệnh này (so với snapshot của lần đọc này, không so với facts mới hơn):
   python3 scripts/check-model-prose.py <style> --facts <SNAPSHOT>/facts.json
   và sửa cho tới khi nó in `RESULT: OK`. Không chạy lại brief để "đuổi" dữ liệu mới hơn.

## Bản đồ trích dẫn
""" + CITES)
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
