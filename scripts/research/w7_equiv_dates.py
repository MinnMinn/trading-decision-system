"""`_htf_wyckoff_target` answers at many decision times across the WHOLE real HTF history (XAUUSD 1m -> 5m, PIT cutoff
2024-03-01), both sides, in a fixed pseudo-random order that repeats some queries (cache hits). Research tooling only
(docs/audits/2026-10-01-w7-speed.md). Run in a BASE tree and in the working tree; the printed sha256 must agree:

  BT_HISTORY_ROOT=<root>/data/history/ftmo python3 scripts/research/w7_equiv_dates.py [N_DATES] [SEED]

Decision times are 1m bar closes (what `_fires_from` passes: `available_time(bar, "1m")` as ISO Z) drawn uniformly from the
1m series' own bars, plus the exact 5m bar-close boundaries around a few of them."""
import hashlib
import importlib.util
import json
import os
import random
import sys
import time

SCR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCR)
n_dates = int(sys.argv[1]) if len(sys.argv) > 1 else 60
seed = int(sys.argv[2]) if len(sys.argv) > 2 else 20261001
spec = importlib.util.spec_from_file_location("bt", os.path.join(SCR, "backtest-methods.py"))
bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt)
bt.pit_cutoff("2024-03-01T00:00:00Z")
for k in ("fx_w1_tr_low_st", "fx_w2_st_below_sc", "fx_w3_mSOW_spring", "fx_w5_vp_abandon", "fx_w7_htf_target"):
    bt.OPTS[k] = True
sym = "XAUUSD"
c1, _ = bt.load(sym, "1m")
rnd = random.Random(seed)
times = []
for _ in range(n_dates):
    i = rnd.randrange(len(c1))
    t = bt._N.available_time({"time": c1[i]["time"]}, "1m").isoformat().replace("+00:00", "Z")
    times.append(t)
    if rnd.random() < 0.3:      # the bar-boundary neighbours: one minute before / after the same 5m close
        for dm in (-60, 60):
            import datetime
            tt = bt._N._parse(t) + datetime.timedelta(seconds=dm)
            times.append(tt.isoformat().replace("+00:00", "Z"))
queries = [(s, t) for t in times for s in ("long", "short")]
queries += rnd.sample(queries, len(queries) // 4)          # repeats
rnd.shuffle(queries)
log = []
t0 = time.time()
for side, t in queries:
    log.append((t, side, bt._htf_wyckoff_target(sym, "1m", side, t)))
dt = time.time() - t0
print(json.dumps(dict(queries=len(queries), distinct=len(set((x[0], x[1]) for x in log)),
                      non_none=sum(1 for x in log if x[2] is not None), secs=round(dt, 1),
                      sha256=hashlib.sha256(json.dumps(log).encode()).hexdigest())), flush=True)
