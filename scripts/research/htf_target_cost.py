"""Cost of ONE bt._htf_wyckoff_target() call (W7, OPTS fx_w7_htf_target) vs the HTF prefix length it detects on.
Profiling only. Usage: BT_HISTORY_ROOT=data/history/ftmo python3 scripts/research/htf_target_cost.py DECISION_TIME_ISO [...]
Splits the call into its two parts: pit.series_as_of() over the whole HTF series, and wyckoff_records() on the prefix."""
import hashlib
import importlib.util
import json
import os
import sys
import time

SCR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCR)
spec = importlib.util.spec_from_file_location("bt", os.path.join(SCR, "backtest-methods.py"))
bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt)
bt.pit_cutoff("2024-03-01T00:00:00Z")
sym, tf = "XAUUSD", "1m"
h = bt.HTF_OF[tf]
c, _ = bt.load(sym, h)
print(f"HTF of {tf} = {h}: {len(c)} bars, first {c[0]['time']}, last {c[-1]['time']}", flush=True)
for dt in sys.argv[1:]:
    t0 = time.time()
    trunc = bt._pit.series_as_of(c, h, dt, symbol=sym)
    t1 = time.time()
    O_ = [x["open"] for x in trunc]; H_ = [x["high"] for x in trunc]; L_ = [x["low"] for x in trunc]
    C_ = [x["close"] for x in trunc]; V_ = [x.get("volume", 0) for x in trunc]
    wp = bt._wy_params(bt.P[h]["sob"])
    recs = bt._structures.wyckoff_records(O_, H_, L_, C_, V_, P=wp, volume_kind="tick", side="long")
    t2 = time.time()
    recs_s = bt._structures.wyckoff_records(O_, H_, L_, C_, V_, P=wp, volume_kind="tick", side="short")
    t3 = time.time()
    hl = hashlib.sha256(json.dumps(recs, sort_keys=True, default=str).encode()).hexdigest()[:16]
    hs = hashlib.sha256(json.dumps(recs_s, sort_keys=True, default=str).encode()).hexdigest()[:16]
    print(f"{dt}: prefix={len(trunc)} bars  series_as_of={t1 - t0:.2f}s  detect_long={t2 - t1:.2f}s  "
          f"detect_short={t3 - t2:.2f}s records={len(recs)}/{len(recs_s)} sha256[:16] long={hl} short={hs}", flush=True)
