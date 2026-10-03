#!/usr/bin/env python3
"""Coarse per-component risk-weight grid over the baseline + F4 components (DESIGN on already-read history, 72 combinations --
the number is disclosed so the best row is read as a selection maximum, not an estimate).

    python3 scripts/research/book_weights.py"""
import importlib.util
import itertools
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location("book_sim", os.path.join(ROOT, "scripts", "research", "book_sim.py"))
BS = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BS)
NAMES = ["H7_XAUUSD_eod", "E5_XAUUSD_24", "E5_US500_48", "G9_XAUUSD_eod", "G9_XAGUSD_eod"]
GRID = ((1.0, 0.5), (1.0, 0.5, 0.25), (1.0, 0.5, 0.25), (0, 0.5, 1.0), (0, 0.5))


def main():
    tr = {k: BS.trades(*BS.COMPONENTS[k]) for k in NAMES}
    lo = max(min(t["entry_time"] for t in tr[c]) for c in NAMES)
    rows = []
    for w in itertools.product(*GRID):
        book = [dict(t, R=t["R"] * wt) for c, wt in zip(NAMES, w) if wt for t in tr[c] if t["entry_time"] >= lo]
        _mu, _sd, sh = BS.daily_profile(book)
        p1 = BS.FB.summarise_replay(BS.FB.replay(book, 0.01, 0.10, None))
        pc = BS.FB.summarise_replay(BS.FB.replay(book, 0.01, 0.10, 120))
        rows.append((sh, w, p1["pass"], p1["fail"], p1["median_days_to_pass"], pc["pass"]))
    rows.sort(key=lambda r: -r[0])
    print(f"span from {lo}; weights x 1 % per trade over {NAMES}; {len(rows)} combinations")
    for r in rows:
        print(f"sharpe/d {r[0]:.2f} w={r[1]} P1 {r[2]:.2f} fail {r[3]:.2f} median {r[4]} d  P1<=120d {r[5]:.2f}")


if __name__ == "__main__":
    main()
