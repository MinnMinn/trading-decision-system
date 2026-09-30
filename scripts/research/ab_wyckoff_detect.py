"""Byte-identity A/B for a wyckoff_rules.py speed change: runs detect_accumulations / detect_distributions from the
ORIGINAL module file (path given, e.g. `git show <rev>:scripts/wyckoff_rules.py > /tmp/orig.py`) and from the working
tree on the same inputs and compares json.dumps(records, sort_keys=True) sha256.
Usage: BT_HISTORY_ROOT=data/history/ftmo python3 scripts/research/ab_wyckoff_detect.py ORIG.py SYM TF DECISION_TIME_ISO [--orig-too-slow-skip]
Inputs: the PIT-truncated (<= DECISION_TIME) prefix of SYM/TF, the whole prefix as ONE detection window."""
import hashlib
import importlib.util
import json
import os
import sys
import time

SCR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCR)
orig_path, sym, tf, dt = sys.argv[1:5]
spec = importlib.util.spec_from_file_location("bt", os.path.join(SCR, "backtest-methods.py"))
bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt)
bt.pit_cutoff("2024-03-01T00:00:00Z")
so = importlib.util.spec_from_file_location("wyckoff_rules_orig", orig_path)
W0 = importlib.util.module_from_spec(so)
so.loader.exec_module(W0)
c, _ = bt.load(sym, tf)
trunc = bt._pit.series_as_of(c, tf, dt, symbol=sym)
O = [x["open"] for x in trunc]; H = [x["high"] for x in trunc]; L = [x["low"] for x in trunc]
C = [x["close"] for x in trunc]; V = [x.get("volume", 0) for x in trunc]
P = {k: v for k, v in bt.W.PARAMS.items()}
P0 = {k: v for k, v in W0.PARAMS.items()}
assert P == P0, "PARAMS differ between original and working tree"
out = {}
for label, mod in (("orig", W0), ("new", bt.W)):
    t = time.time()
    a = mod.detect_accumulations(O, H, L, C, V, volume_kind="tick", P=dict(mod.PARAMS, fx_w1_tr_low_st=True, fx_w2_st_below_sc=True, fx_w3_mSOW_spring=True, fx_w5_vp_abandon=True))
    d = mod.detect_distributions(O, H, L, C, V, volume_kind="tick", P=dict(mod.PARAMS, fx_w1_tr_low_st=True, fx_w2_st_below_sc=True, fx_w3_mSOW_spring=True, fx_w5_vp_abandon=True))
    el = time.time() - t
    h = hashlib.sha256(json.dumps([a, d], sort_keys=True, default=str).encode()).hexdigest()
    out[label] = h
    print(f"{label}: prefix={len(trunc)} bars records={len(a)}/{len(d)} secs={el:.1f} sha256={h}", flush=True)
print("IDENTICAL" if out["orig"] == out["new"] else "DIFFERENT")
