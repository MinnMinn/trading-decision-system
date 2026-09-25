#!/usr/bin/env python3
"""Pick the N most CONSISTENT setups per market from stability-report JSON files and write the pilot's selection file.

Usage: rank-setups.py --crypto data/history/stability/crypto-*.json --cfd data/history/stability/cfd-*.json
                      [--n 20] [--min-trades-crypto 100] [--min-trades-cfd 40] [--out docs/backtests/<file>.md] [--select docs/architecture/pilot-top20.json]

A "setup" = (market, timeframe, method, ICT target model, configuration A/B/C). Rows are ranked by: not blown up → share of
positive quarters → share of positive years → worst quarter → stability ratio (quarter mean / σ × √n). One row per
(timeframe, method) survives (the best target model and configuration), so the top N are N different rules, not one rule at
several targets or fee assumptions. Eligible rule families come from the registry (RUNNABLE = mreg.runnable(),
below), never hardcoded here -- currently ICT (LIMIT at the FVG edge) and WYCKOFF-BOOK (MARKET on the close of
the entry bar: Spring reclaim / Test / BU), exactly as the backtest. (WYCKOFF, the mechanical proxy, and
COMBINED were removed 2026-09-19 -- docs/audits/2026-09-19-knowledge-fidelity.md finding 6.)

The selection file (single writer: this script) is read by scripts/strategy-runner.py and shown by `/automation pilot profile top20`.
CFD setups get execution "mt5" (demo account through integrations/mt5/OrderBridge.mq5 + scripts/mt5-order-bridge.py) and only the three
live timeframes the MT5 EA exports or the runner can aggregate (CFD_TFS: 15m, 1H, 4H). Every number here is a code proxy over research history — for CFD that is
Yahoo Finance futures data (scripts/fetch-history-cfd.py), not the CFD quotes the pilot will trade on.
"""
import argparse, datetime, glob, importlib.util, json, os
# Per-setup keys a rewrite must carry over. The ICT switch trio (ict_disp / ict_pd / std_origin) and the
# scripts/ict-flags-1y.py that tuned them were deleted 2026-09-19 (knowledge audit finding 11): none of the
# three could change an ICT setup, so a year of "decisions" about them measured noise. Nothing is carried now.
FLAG_KEYS = ()


def carry_flags(selection, path):
    """Keep the deck-faithful switches of setups whose id already exists in the selection file (they are decided separately)."""
    try:
        prev = {st["id"]: st for st in json.load(open(path, encoding="utf-8")).get("setups", [])}
    except Exception:
        return selection
    for st in selection["setups"]:
        for k in FLAG_KEYS:
            if k in prev.get(st["id"], {}):
                st[k] = prev[st["id"]][k]
    return selection


def _global_rule_params(st):
    """The global detection parameters that apply to one setup (CLAUDE.md §14, scripts/setup_version.py).

    Resolved from backtest-methods' own state so the version tracks the numbers the rules actually ran with.
    RISK / START / RUIN_FRAC are deliberately absent: they size a position, they do not change which bars
    qualify, and folding them in would churn every version whenever the risk ceiling moved."""
    return {"min_rr": bt.MIN_RR, "stop_buffer_pct": bt.STOP_BUFFER_PCT,
            "displacement": dict(bt.DISP), "volume": dict(bt.VOL),
            "per_timeframe": dict(bt.P.get(st.get("tf"), {}))}


def finalize(selection, path):
    """Carry the deck-faithful switches, THEN stamp rule versions. One function because every write path
    already calls the first half, and a fourth write path that forgot the second half would silently ship
    setups a trade cannot be tied back to -- which is the whole defect §14 names."""
    return SV.stamp(carry_flags(selection, path), _global_rule_params)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys as _sys; _sys.path.insert(0, os.path.join(ROOT, "scripts"))
import setup_version as SV      # CLAUDE.md §14: a setup carries the version of the rules it IS
import research_validity as RV  # CLAUDE.md §38: a selection may not be made from invalid research
import instruments as _I        # the ONE allowlist: a symbol set typed here would outlive the registry
_mspec = importlib.util.spec_from_file_location("methods", os.path.join(ROOT, "scripts", "methods.py"))
mreg = importlib.util.module_from_spec(_mspec); _mspec.loader.exec_module(mreg)
# backtest-methods holds the resolved detection parameters a setup's rule version is computed over
# (CLAUDE.md §14). Loaded the same way as `methods` above -- the filename has a dash, so it cannot be a
# plain import.
_btspec = importlib.util.spec_from_file_location("bt", os.path.join(ROOT, "scripts", "backtest-methods.py"))
bt = importlib.util.module_from_spec(_btspec); _btspec.loader.exec_module(bt)
RUNNABLE = mreg.runnable()   # executed by scripts/strategy-runner.py; source: docs/architecture/methods.json
# The three live rungs only (user decision 2026-09-13). Was a seven-rung superset that also named the retired
# five- and thirty-minute rungs, the two-hour rung and the daily -- harmless while it was a superset of the live
# set, which is exactly why it would have rotted unnoticed.
CFD_TFS = {"15m", "1H", "4H"}
# user decision 2026-09-11 (evening): one setup per HORIZON per market -- scalping / day / swing -- even where the backtest edge is weak.
# One timeframe per horizon (user decision 2026-09-13), matching automation.HORIZON_TF. Was a SET per horizon,
# which could select a setup at a rung the scanner does not run -- a selection nothing could execute.
HORIZONS = {"scalping": "15m", "day": "1H", "swing": "4H"}
HORIZON_MIN_TRADES = {"scalping": 60, "day": 60, "swing": 12}
# The config table has ONE author: scripts/stability-report.py, which is what produced the rows being ranked.
# This file used to keep its own copy with the fees written out -- 0.0005 / 0.0002 / 0.0002 -- and on
# 2026-09-18 that copy stamped `fee_assumed: 0.0002` onto two CFD setups whose MT5 account pays 0.0005 on both
# sides. A second copy of a domain rule is not a convenience, it is a second answer (CLAUDE.md §58); the fee
# now comes from the venue through `config_fee()`, the same call the ranked rows were priced with.
_ss = importlib.util.spec_from_file_location("stability_report", f"{ROOT}/scripts/stability-report.py")
_SR = importlib.util.module_from_spec(_ss); _ss.loader.exec_module(_SR)
CFG_DESC = _SR.CONFIGS


def fee_assumed_for(cfg_name, market):
    """What the ranked row was actually priced at, resolved through the venue -- never a literal here."""
    return _SR.config_fee(CFG_DESC[cfg_name], market)


UNSTAMPED = "UNSTAMPED"     # a stability file written before 2026-09-18, when §38 verdicts did not exist
SOURCE_VALIDITY = {}        # relpath -> the §38 block of each file this process read (for the written artifacts)
REFUSED = []                # (relpath, reason) for every file §38 would not let this selection use


def load_rows(paths, market, *, require_stamped=False):
    """Rows from stability-report JSON files, minus any file CLAUDE.md §38 says may not be selected from.

    This is the one place all three ranking modes read their input, so it is the one place the §38 gate
    belongs. "Never silently produce a trustworthy-looking performance result from invalid research" applies
    with particular force here: these rows do not end in a report, they end in `pilot-top20.json`, which is what
    the runner places orders from.

    Two verdicts are refused outright (`INVALID`, and anything not in the allow-list). `UNSTAMPED` -- a file
    written before the verdict existed -- is NOT silently trusted and NOT silently dropped: `research_validity.
    read()` raises, this call site catches, and the fact is carried onto every row, into the selection file and
    into the report. Dropping them instead would empty the pilot's entire input on the day the stamp was
    introduced, which is a live-behaviour change dressed as a documentation fix (§59); `--require-stamped`
    makes the strict behaviour available now and should become the default once every stability file has been
    regenerated by a stamping `stability-report.py`.
    """
    rows = []
    for p in paths:
        d = json.load(open(p, encoding="utf-8"))
        rel = os.path.relpath(p, ROOT).replace(os.sep, "/")    # repo paths are POSIX in every written artifact
        try:
            block = RV.read(d, where=rel)
            # UNVERIFIED is allowed: it means nothing fired but some §38 conditions have no detector yet
            # (docs/architecture/research-validity.json says which and why). Every run today is in that state;
            # refusing it would refuse all research rather than the invalid kind.
            RV.require(block, where=rel, allow=(RV.VALID, RV.FLAGGED, RV.UNVERIFIED))
        except RV.Unstamped as exc:
            if require_stamped:
                REFUSED.append((rel, str(exc))); print(f"§38 REFUSED {rel}: unstamped", file=_sys.stderr); continue
            block = {"verdict": UNSTAMPED, "findings": [], "unchecked": list(RV.ORDER),
                     "_note": "written before scripts/research_validity.py existed; nothing was assessed"}
            print(f"§38 WARNING {rel}: no research-validity verdict (pre-2026-09-18 file). Rows from it are "
                  f"used but marked {UNSTAMPED}; re-run stability-report.py to assess it.", file=_sys.stderr)
        except RV.InvalidResearch as exc:
            REFUSED.append((rel, str(exc))); print(f"§38 REFUSED {exc}", file=_sys.stderr); continue
        SOURCE_VALIDITY[rel] = block
        target = os.path.basename(p).rsplit("-", 1)[1].rsplit(".", 1)[0]    # crypto-std25.json / crypto-scalp-std25.json -> std25
        for r in d["rows"]:
            rows.append(dict(r, market=market, target=(target if r["method"] == "ICT" else "border"),
                             file=rel, research_validity=block["verdict"]))
    return rows


def validity_note():
    """One line for the report, and the block the selection file carries. Never empty: a selection whose
    sources were all unassessed must say so as plainly as one whose sources were clean."""
    per = {rel: b["verdict"] for rel, b in SOURCE_VALIDITY.items()}
    # UNSTAMPED ranks ABOVE FLAGGED: a flagged run was assessed and its defects are named, while an unstamped
    # one is entirely unknown, and unknown is the worse thing to be selecting from.
    return {"per_source": per,
            "worst": RV.worst(per.values(), extra={UNSTAMPED: 3}) if per else UNSTAMPED,
            "refused": [{"source": s, "reason": w} for s, w in REFUSED],
            "source": "docs/architecture/research-validity.json (CLAUDE.md §38)"}


def validity_markdown():
    v = validity_note()
    bad = sorted({k for k, vv in v["per_source"].items() if vv not in (RV.VALID,)})
    line = f"_CLAUDE.md §38 — tính hợp lệ của nghiên cứu nguồn: **{v['worst']}**._"
    if bad:
        line += " Nguồn không HỢP LỆ hoàn toàn: " + ", ".join(f"`{k}` ({v['per_source'][k]})" for k in bad) + "."
    if v["refused"]:
        line += " **Bị từ chối (không dùng để chọn):** " + ", ".join(f"`{r['source']}`" for r in v["refused"]) + "."
    return line


MIN_WINDOW_DAYS = 90   # 3 months: below this a row has no evidence either way, so it is not rankable (see solvent())


def solvent(r, window=None):
    """Is this row allowed to be selected at all? User decision 2026-09-13, replacing the 2026-09-11 rule that
    filled every (horizon, method) slot with the best available candidate even when that candidate lost money.

    Three conditions, all required:
      1. At least MIN_WINDOW_DAYS of measured history. Profitable over 71 days is not evidence -- that was the
         CFD case (2026-07-02 -> 2026-09-11) where every rule was being judged on ten weeks.
      2. Did not blow the account up.
      3. Actually made money. "Did not blow up" is a much lower bar than "made money": the row that forced this
         change, CFD 1H WYCKOFF, ended its ranking window at $988 from $10,000.

    Measured as `ann > 0`, not `final > START`: `ann` is already on every row (so this module needs no dependency
    on backtest-methods just to learn the account size), it is the same field main_horizons() already uses for the
    `negative_backtest` flag, and it is strictly monotonic in `final` -- ann = ((final/START)**(365/days) - 1),
    so ann > 0 and final > START are the same condition.

    Why here rather than in main_horizons(): every caller of rank() -- the top-N mode and the horizons mode --
    picks rules that will place real orders. A rule that loses money should not be selectable from either.
    """
    if window == "oos6m":
        # INT-5: judged on the IN-SAMPLE side only -- the window that ends at the cutoff. Nothing on or after
        # the cutoff may make a row selectable (that is what the OOS side is for).
        m = (r.get("oos6m") or {}).get("in_sample")
        if not m:
            return False
        try:
            days = (datetime.date.fromisoformat(m["until"][:10]) - datetime.date.fromisoformat(m["since"][:10])).days
        except (ValueError, KeyError, TypeError):
            return False
        return days >= MIN_WINDOW_DAYS and m.get("ruin") is None and m.get("ann", 0) > 0
    m = r["w1y"] if window == "1y" else r
    start = r["w1y"]["since"] if window == "1y" and r.get("w1y", {}).get("since") else r["first"]
    try:
        days = (datetime.date.fromisoformat(r["last"][:10]) - datetime.date.fromisoformat(max(start, r["first"])[:10])).days
    except (ValueError, KeyError, TypeError):
        return False                      # unparseable dates: no evidence, fail closed
    return days >= MIN_WINDOW_DAYS and m.get("ruin") is None and m.get("ann", 0) > 0


def _num(v):
    """A §39 value as a float, or None. Unwraps {"value": ...} and refuses an unavailable() marker -- an
    unmeasurable metric must never sort as a number (same rule as scripts/ranking.py `_num`)."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        if "unavailable" in v:
            return None
        for k in ("value", "fraction", "mean"):
            if isinstance(v.get(k), (int, float)):
                return float(v[k])
    return None


RANK_NOTES = []        # per-market notes about how the ranking mode was resolved; printed and stored


def _passable(rows):
    """Can the account these rows were simulated under actually be PASSED?

    True only when at least one row carries a real (non-`unavailable`) prop_pass_probability. That is
    equivalent to the profile declaring both an initial_balance and a profit_target, but it is read off the
    data rather than re-deriving the rule here (scripts/performance.py owns it)."""
    return any(_num((r.get("perf") or {}).get("prop_pass_probability")) is not None for r in rows)


def _pass_estimate(v):
    """The pass probability to RANK on: the conservative (lower) end of its spread when the estimate is
    flagged wide, the point value otherwise.

    §39's `spread` is a nested bootstrap -- it resamples the observed trades themselves, so it answers "how
    much does this number depend on which trades happened to occur". On a 14-trade population that band runs
    roughly 0 to 1, and the point estimate (66%) is not evidence of anything. Ranking on the point value let a
    14-trade row outrank a 51-trade row measured at 60%, i.e. selected on noise. Taking the lower bound is the
    standard pessimistic reading under uncertainty and it makes a bigger sample win ties by default.
    """
    if isinstance(v, dict) and v.get("low_confidence"):
        band = (v.get("spread") or {}).get("prop_pass_probability")
        if isinstance(band, (list, tuple)) and len(band) == 2 and isinstance(band[0], (int, float)):
            return float(band[0])
    return _num(v)


def prop_key(r):
    """Sort key for `--rank-by prop-pass`: "which rule passes THIS account's challenge most often".

    User decision 2026-09-19. The old key (`consistency`: share of positive quarters first) is account-blind,
    and on the FTMO-conditioned CFD table it selected two rules that BOTH fail the challenge while rules that
    pass sat in the same file. The account is the thing being traded, so it is the thing to rank by.

    Order, most significant first:
      1. survived the account's own rules on this history (`failed_by` is None) -- a fact, not an estimate;
      2. prop_pass_probability (§39, higher is better) -- the bootstrap estimate of passing;
      3. account_failure_probability (lower is better);
      4. max_drawdown (lower is better) -- the binding constraint on every failing row measured so far;
      5. expectancy (higher is better) -- the tie-break, and the only one that is not account-shaped.

    A row whose pass probability is unmeasurable sorts LAST on that key rather than winning by being unmeasured.
    `low_confidence` (n below the registry's `low_confidence_below`) is NOT used to reorder -- it is carried onto
    the selection so the reader sees which estimates are wide.
    """
    perf = r.get("perf") or {}
    pp = _pass_estimate(perf.get("prop_pass_probability"))
    af = _num(perf.get("account_failure_probability"))
    dd = _num(perf.get("max_drawdown"))
    ex = _num(perf.get("expectancy"))
    return ((r.get("failed_by") is None),
            (pp is not None, pp if pp is not None else 0.0),
            (af is not None, -(af if af is not None else 0.0)),
            (dd is not None, -(dd if dd is not None else 0.0)),
            (ex is not None, ex if ex is not None else 0.0))


def rank(rows, min_trades, window=None, rank_by="consistency"):
    """window=None: whole history (consistency first). window='1y': the row's last-365-day metrics -- not blown up, then share of
    positive quarters in that year, then the year's return, then its worst quarter (user decision 2026-09-11: 'hiệu quả nhất trong 1 năm').

    Rows that fail solvent() are dropped before sorting, so an empty return means "nothing here earned selection",
    and every caller already renders that as an empty slot rather than a fallback."""
    rows = [r for r in rows if solvent(r, window)]
    if rank_by == "prop-pass":
        # `solvent()` already dropped the blown-up and the money-losing rows; this adds the account's own
        # verdict, which is the whole point of the mode: a rule that broke the challenge is not selectable
        # no matter how consistent its quarters were.
        ok = [r for r in rows if r.get("n", 0) >= min_trades and r.get("failed_by") is None]
        ok.sort(key=prop_key, reverse=True)
    elif window == "oos6m":
        # Same ordering as `1y`, read from the in-sample block ONLY. The OOS block is never consulted here:
        # ranking on it would be selecting on the holdout (INT-5).
        ok = [r for r in rows if r["oos6m"]["in_sample"]["n"] >= min_trades]
        ok.sort(key=lambda r: (r["oos6m"]["in_sample"]["ruin"] is None, r["oos6m"]["in_sample"]["q_pos"],
                               r["oos6m"]["in_sample"]["ann"], r["oos6m"]["in_sample"]["q_worst"]), reverse=True)
    elif window == "1y":
        ok = [r for r in rows if r.get("w1y") and r["w1y"]["n"] >= min_trades]
        ok.sort(key=lambda r: (r["w1y"]["ruin"] is None, r["w1y"]["q_pos"], r["w1y"]["ann"], r["w1y"]["q_worst"]), reverse=True)
    else:
        ok = [r for r in rows if r["n"] >= min_trades]
        ok.sort(key=lambda r: (r["ruin"] is None, r["q_pos"], r["y_pos"] / max(1, r["y_n"]), r["q_worst"], r["stab"]), reverse=True)
    best = {}
    for r in ok:
        key = (r["tf"], r["method"])          # one rule family per (timeframe, method): the best target model and configuration survive
        if key not in best:
            best[key] = r
    return list(best.values())


def fmt(r, window=None):
    fin = f"CHÁY {r['ruin'][:10]}" if r["ruin"] else f"${r['final']:,.0f}"
    yrs = " / ".join(f"{v:+.0f}" for _, v in r["years"])
    if window == "1y":
        w = r["w1y"]; f1 = f"CHÁY {w['ruin'][:10]}" if w["ruin"] else f"${w['final']:,.0f}"
        return (f"| {r['tf']} | {r['method']} | {r['target']} | {r['cfg']} | {w['n']} | {f1} | {w['ann']:+.1f}% | −{w['dd']:.1f}% | {w['q_pos']:.0f}% | {w['q_worst']:+.1f}% | "
                f"{r['n']} · {r['ann']:+.1f}%/năm · {r['q_pos']:.0f}% quý dương · {r['y_pos']}/{r['y_n']} năm |")
    return (f"| {r['tf']} | {r['method']} | {r['target']} | {r['cfg']} | {r['n']} | {fin} | {r['ann']:+.1f}% | −{r['dd']:.1f}% | {r['q_pos']:.0f}% | "
            f"{r['q_worst']:+.1f}% | {r['stab']:+.2f} | {r['y_pos']}/{r['y_n']} ({yrs}) |")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--crypto", nargs="*", default=glob.glob(f"{ROOT}/data/history/stability/crypto-*.json"))
    ap.add_argument("--cfd", nargs="*", default=glob.glob(f"{ROOT}/data/history/stability/cfd-*.json"))
    ap.add_argument("--n", type=int, default=20); ap.add_argument("--min-trades-crypto", type=int, default=100); ap.add_argument("--min-trades-cfd", type=int, default=40)  # --window 1y lowers these: see main()
    ap.add_argument("--out"); ap.add_argument("--select")
    # Defaults DERIVED, not typed. `--cfd-symbols` used to read "XAUUSD,XAGUSD,USOIL,UKOIL"; when USOIL/UKOIL
    # left the execution list on 2026-09-18 (no such symbol on the broker) that literal would have written them
    # straight back into pilot-top20.json on the next ranking run, with nothing failing. The crypto default stays
    # the BACKTESTED subset rather than the execution list -- selection may only claim symbols that were
    # measured (instruments.json `backtested`), and that is a narrower set on purpose.
    ap.add_argument("--crypto-symbols", default=",".join(_I.backtested("crypto")))
    ap.add_argument("--cfd-symbols", default=",".join(_I.execution("cfd")))
    ap.add_argument("--horizons", action="store_true", help="select the best rule per horizon (scalping/day/swing) per market instead of the top N overall")
    ap.add_argument("--window", choices=["all", "1y", "oos6m"], default="all",
                    help="1y = rank on the last 365 days of each row (`/automation on setup top N`). oos6m (with "
                         "--horizons; the `/automation on` default since round 4b / INT-5) = rank on the 365 days "
                         "BEFORE a cutoff derived from the data (last bar date - 6 months), then enable a pick "
                         "only if its held-out last 6 months are profitable; a failed pick leaves its slot EMPTY")
    ap.add_argument("--rank-by", choices=["consistency", "prop-pass"], default="consistency",
                    help="consistency = share of positive quarters first (account-blind, the pre-2026-09-19 "
                         "rule). prop-pass = rank by whether THIS account's challenge is passed: survived the "
                         "account, then prop_pass_probability, then account_failure_probability, then max "
                         "drawdown, then expectancy. Requires --account-rows.")
    ap.add_argument("--account-rows", nargs="*", default=None,
                    help="stability files produced with `stability-report.py --account <id>` (rows carry "
                         "`failed_by` and the §39 account metrics). Used INSTEAD of the account-free files "
                         "when --rank-by prop-pass.")
    ap.add_argument("--require-stamped", action="store_true", help="CLAUDE.md §38: refuse stability files that carry no research-validity verdict (default: use them, marked UNSTAMPED)")
    a = ap.parse_args(); today = datetime.date.today().isoformat()
    if a.window == "oos6m":
        if not a.horizons:
            ap.error("--window oos6m is implemented for --horizons selection only")
        if a.rank_by != "consistency":
            ap.error("--window oos6m ranks by consistency on the in-sample window; --rank-by prop-pass is not supported with it")
        return main_horizons_oos(a, today)
    if a.horizons:
        if a.window == "1y":
            if a.min_trades_crypto == 100: a.min_trades_crypto = 30
            if a.min_trades_cfd == 40: a.min_trades_cfd = 15
        return main_horizons(a, today)
    if a.window == "1y":
        if a.min_trades_crypto == 100: a.min_trades_crypto = 30
        if a.min_trades_cfd == 40: a.min_trades_cfd = 15
        return main_window_1y(a, today)
    L = [f"# Top {a.n} setup mỗi thị trường — xếp theo độ ổn định — {today}", "",
         "_`scripts/rank-setups.py` trên các file `stability-report.py --json`. Tiêu chí: không cháy → tỉ lệ quý dương → tỉ lệ năm dương → quý tệ nhất → tỉ số ổn định. Mỗi (khung, luật) giữ một target và cấu hình tốt nhất, nên 5 dòng là 5 luật khác nhau. Cấu hình A = phí taker 0,05 %, không quản lý; B = phí maker 0,02 % + hoà vốn +1R; C = B + lọc khung lớn. Cả long lẫn short. Mọi số là proxy code trên lịch sử nghiên cứu._", ""]
    selection = dict(generated=today, note="Written by scripts/rank-setups.py. Read by scripts/strategy-runner.py (pilot profile top20) and shown by /automation pilot profile. CFD execution = MT5 demo account via the file order bridge; crypto = Binance futures testnet.", setups=[])
    for market, paths, mn, syms in (("crypto", a.crypto, a.min_trades_crypto, a.crypto_symbols.split(",")), ("cfd", a.cfd, a.min_trades_cfd, a.cfd_symbols.split(","))):
        rows = load_rows(sorted(paths), market, require_stamped=a.require_stamped)
        if not rows:
            L += [f"## {market.upper()}: chưa có dữ liệu xếp hạng", ""]; continue
        ranked = rank(rows, mn)
        eligible = [r for r in ranked if r["method"] in RUNNABLE and (market == "crypto" or r["tf"] in CFD_TFS)]
        top = eligible[:a.n]
        L += [f"## {market.upper()} — top {a.n} (≥ {mn} lệnh; {len(rows)} dòng xét, {len(ranked)} luật khác nhau)", "",
              "| Khung | Luật | Target | Cấu hình | Lệnh | Vốn cuối ($10k) | %/năm | Sụt giảm | Quý dương | Quý tệ nhất | Ổn định | Năm dương (từng năm %) |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in top:
            L.append(fmt(r))
        skipped = [r for r in ranked[:a.n + 3] if r not in eligible]
        if skipped:
            L += ["", "Xếp cao nhưng không chạy được trong pilot (luật chưa có trong runner hoặc khung MT5 không xuất): " + ", ".join(f"{r['tf']} {r['method']} {r['target']} {r['cfg']}" for r in skipped)]
        L.append("")
        for i, r in enumerate(top, 1):
            cfg = CFG_DESC[r["cfg"]]
            # ict_target is NOT stamped here (2026-09-13): its only reader, backtest-methods.py's legacy ICT
            # target-model switch, was deleted -- the live ICT path takes its target from ict_scan.setup_candidate
            # and never consults it. Stamping an explicit null would still tell a reader "a target model concept
            # applies to ICT setups", which is no longer true; dropping the key is the honest schema.
            selection["setups"].append(dict(id=f"{market}-{r['method'].lower()}-{r['tf'].lower()}-{r['target']}-{r['cfg'].lower()}", rank=i, market=market, symbols=syms, tf=r["tf"], method=r["method"],
                                            htf=cfg["htf"], mgmt=cfg["mgmt"], fee_assumed=fee_assumed_for(r["cfg"], market),
                                            execution="futures" if market == "crypto" else "mt5",
                                            backtest=dict(n=r["n"], ann_pct=round(r["ann"], 1), max_dd_pct=round(r["dd"], 1), q_pos_pct=round(r["q_pos"]), years_pos=f"{r['y_pos']}/{r['y_n']}", period=f"{r['first']}→{r['last']}", source=r["file"])))
    L += ["", validity_markdown()]
    md = "\n".join(L) + "\n"; print(md)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(md)
    if a.select:
        selection = finalize(selection, a.select)
        selection["research_validity"] = validity_note()
        json.dump(selection, open(a.select, "w", encoding="utf-8"), indent=1, ensure_ascii=False); print(f"-> {a.select} ({len(selection['setups'])} setups)")


def main_window_1y(a, today):
    L = [f"# Top {a.n} setup mỗi thị trường — hiệu quả 12 tháng gần nhất — {today}", "",
         "_`scripts/rank-setups.py --window 1y` (được `/automation on setup top N` gọi). Xếp theo cửa sổ 365 ngày cuối của mỗi dòng: không cháy → tỉ lệ quý dương trong năm → lợi nhuận năm → quý tệ nhất; mỗi (khung, luật) giữ một target và cấu hình. Cột cuối là toàn bộ lịch sử để đối chiếu. Cả long lẫn short; số là proxy code trên lịch sử nghiên cứu (CFD = futures Yahoo)._", ""]
    selection = dict(generated=today, mode=f"top{a.n}-1y", note=f"Written by scripts/rank-setups.py --window 1y --n {a.n} (from `/automation on setup top {a.n}`). Read by scripts/strategy-runner.py. Crypto = Binance futures testnet, CFD = MT5 demo via the file order bridge.", setups=[])
    for market, paths, mn, syms in (("crypto", a.crypto, a.min_trades_crypto, a.crypto_symbols.split(",")), ("cfd", a.cfd, a.min_trades_cfd, a.cfd_symbols.split(","))):
        rows = load_rows(sorted(paths), market, require_stamped=a.require_stamped)
        ranked = [r for r in rank(rows, mn, "1y") if r["method"] in RUNNABLE and (market == "crypto" or r["tf"] in CFD_TFS)]
        top = ranked[:a.n]
        L += [f"## {market.upper()} — top {a.n} (≥ {mn} lệnh trong 12 tháng; {len(rows)} dòng xét)", "",
              "| Khung | Luật | Target | Cấu hình | Lệnh 1 năm | Vốn cuối 1 năm ($10k) | % 1 năm | Sụt giảm 1 năm | Quý dương | Quý tệ nhất | Toàn lịch sử |", "|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in top:
            L.append(fmt(r, "1y"))
        if not top:
            L.append("| — | không đủ lệnh trong 12 tháng | | | | | | | | | |")
        L.append("")
        for i, r in enumerate(top, 1):
            cfg = CFG_DESC[r["cfg"]]; w = r["w1y"]
            # ict_target dropped (see the top-level rank() call above for why).
            selection["setups"].append(dict(id=f"{market}-{r['method'].lower()}-{r['tf'].lower()}-{r['target']}-{r['cfg'].lower()}", rank=i, market=market, symbols=syms, tf=r["tf"], method=r["method"],
                                            htf=cfg["htf"], mgmt=cfg["mgmt"], fee_assumed=fee_assumed_for(r["cfg"], market),
                                            execution="futures" if market == "crypto" else "mt5", negative_backtest=bool(w["ann"] < 0),
                                            backtest=dict(window="1y", n=w["n"], ann_pct=round(w["ann"], 1), max_dd_pct=round(w["dd"], 1), q_pos_pct=round(w["q_pos"]), since=w["since"],
                                                          full_n=r["n"], full_ann_pct=round(r["ann"], 1), full_q_pos_pct=round(r["q_pos"]), years_pos=f"{r['y_pos']}/{r['y_n']}", source=r["file"])))
    L += ["", validity_markdown()]
    md = "\n".join(L) + "\n"; print(md)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(md)
    if a.select:
        selection = finalize(selection, a.select)
        selection["research_validity"] = validity_note()
        json.dump(selection, open(a.select, "w", encoding="utf-8"), indent=1, ensure_ascii=False); print(f"-> {a.select} ({len(selection['setups'])} setups)")


def main_horizons(a, today):
    L = [f"# Setup theo khung — scalping / day / swing — mỗi thị trường — {today}", "",
         "_`scripts/rank-setups.py --horizons`. Quyết định người dùng 2026-09-11 (mở rộng 2026-09-13): mỗi thị trường chạy đủ 3 khung cho MỖI luật chạy được (RUNNABLE — WYCKOFF-BOOK, ICT; WYCKOFF và COMBINED đã bị xoá 2026-09-19, xem docs/audits/2026-09-19-knowledge-fidelity.md finding 6). Sửa 2026-09-13 (quyết định người dùng): một ô CHỈ được lấp bởi luật có ≥ 3 tháng dữ liệu, không cháy, VÀ có lãi — không ai qua thì **bỏ trống ô**, không lấp bằng đứa đỡ tệ nhất. Trước đó ô được lấp kể cả khi mọi ứng viên đều lỗ, và lần xếp hạng 2026-09-13 đã chọn một luật CFD kết thúc ở $988 trên vốn $10.000. Lý do: `strategy-runner.py`'s `allowed_methods()` chỉ cho phép các luật mà method-switch preset đang bật; chọn theo (khung, luật) thay vì chỉ theo khung đảm bảo mọi preset (dù chỉ bật một luật, ví dụ ICT-only) vẫn có đủ 3 khung, thay vì chỉ có khung mà luật đó tình cờ thắng khi so giữa các luật. Trong mỗi (khung, luật), cấu hình/target tốt nhất theo cùng tiêu chí (không cháy → quý dương → năm dương → quý tệ nhất) — dòng âm được in nghiêng. Sửa tiếp 2026-09-13: mỗi khung chỉ ứng với MỘT timeframe — scalping 15m, day 1H, swing 4H — đúng như `automation.HORIZON_TF`; trước đó mỗi khung là một TẬP timeframe (kể cả 5m/30m/2H/1D) mà scanner không còn quét, nên có thể chọn ra setup không gì chạy được. Trong đó scalping 15m bị phí và trượt giá ăn nhiều nhất. Một khung có thể không đủ lệnh cho MỘT luật cụ thể dù các luật khác ở cùng khung có đủ — dòng đó vẫn được in để việc thiếu setup luôn hiện rõ, không âm thầm giảm số lượng._", ""]
    selection = dict(generated=today, mode="horizons", note="Written by scripts/rank-setups.py --horizons. One setup per (horizon, method) per market -- every RUNNABLE method gets its own scalping/day/swing setups so any method-switch preset (strategy-runner.py allowed_methods()) still covers all 3 horizons (user decision 2026-09-11, extended 2026-09-13 for the per-method split). Crypto = Binance futures testnet, CFD = MT5 demo via the file order bridge.", setups=[])
    methods_order = sorted(RUNNABLE)   # deterministic order; RUNNABLE comes from the registry (scripts/methods.py runnable()), never hardcoded here
    for market, paths, syms in (("crypto", a.crypto, a.crypto_symbols.split(",")), ("cfd", a.cfd, a.cfd_symbols.split(","))):
        mode = getattr(a, "rank_by", "consistency")
        if mode == "prop-pass":
            # Rank on the ACCOUNT-conditioned rows: those were simulated under the profile's own failure
            # rules, so `failed_by` and the §39 account metrics on them are real rather than unavailable.
            apaths = [q for q in (a.account_rows or []) if os.path.basename(q).startswith(market + "-")]
            if not apaths:
                raise SystemExit(f"--rank-by prop-pass needs --account-rows for {market}: a stability file "
                                 f"written by `stability-report.py --account <id> --json "
                                 f"data/history/stability/{market}-<id>.json`. Ranking a challenge by "
                                 f"account-free rows would rank it by numbers the account never saw.")
            rows = load_rows(sorted(apaths), market, require_stamped=a.require_stamped)
            # A challenge can only be PASSED by an account that declares what passing means. The crypto pilot
            # account is a testnet DEMO: no initial_balance, no profit_target, so §39's prop_pass_probability
            # and account_failure_probability are unavailable BY THE PROFILE (scripts/performance.py
            # `_account_terms`), not by a gap in the data. Ranking that market by "pass rate" would rank it by
            # a column of markers. Fall back to consistency for THAT market only -- loudly, and on the record:
            # a silent fallback is the thing CLAUDE.md forbids, not a declared one.
            if not _passable(rows):
                acct = next((r.get("account") for r in rows if r.get("account")), "?")
                note = (f"{market}: account {acct!r} declares no initial_balance/profit_target, so it cannot be "
                        f"passed -- ranked by CONSISTENCY, not prop-pass (CLAUDE.md §33/§39).")
                RANK_NOTES.append(note); print(f"NOTE {note}", file=_sys.stderr)
                mode = "consistency"
        else:
            rows = load_rows(sorted(paths), market, require_stamped=a.require_stamped)
        L += [f"## {market.upper()}", "", "| Khung | TF | Luật | Target | Cấu hình | Lệnh | Vốn cuối ($10k) | %/năm | Sụt giảm | Quý dương | Quý tệ nhất | Ổn định | Năm dương (từng năm %) |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for hz, tf in HORIZONS.items():
            mn = HORIZON_MIN_TRADES[hz] if a.window != "1y" else {"scalping": 20, "day": 15, "swing": 6}[hz]
            for method in methods_order:
                candidates = [r for r in rows if r["tf"] == tf and r["method"] == method and (market == "crypto" or r["tf"] in CFD_TFS)]
                ranked = rank(candidates, mn, a.window if a.window == "1y" else None, rank_by=mode)
                if not ranked:
                    L.append(f"| {hz} | — | {method} | — | — | — | không đủ dữ liệu / lệnh | | | | | | |"); continue
                r = ranked[0]; w = r["w1y"] if a.window == "1y" else r; row = fmt(r, a.window if a.window == "1y" else None).replace("| ", "| " + hz + " | ", 1)
                L.append(row if w["ann"] >= 0 else row.replace(f"| {hz} |", f"| *{hz}* |", 1))
                cfg = CFG_DESC[r["cfg"]]
                # ict_target dropped (see the top-level rank() call above for why).
                selection["setups"].append(dict(id=f"{market}-{hz}-{r['method'].lower()}-{r['tf'].lower()}-{r['target']}-{r['cfg'].lower()}", horizon=hz, rank=len(selection["setups"]) + 1, market=market, symbols=syms, tf=r["tf"], method=r["method"],
                                                htf=cfg["htf"], mgmt=cfg["mgmt"], fee_assumed=fee_assumed_for(r["cfg"], market),
                                                execution="futures" if market == "crypto" else "mt5", negative_backtest=bool(w["ann"] < 0),
                                                backtest=dict(window=a.window, n=w["n"], ann_pct=round(w["ann"], 1), max_dd_pct=round(w["dd"], 1), q_pos_pct=round(w["q_pos"]), full_n=r["n"], full_ann_pct=round(r["ann"], 1), years_pos=f"{r['y_pos']}/{r['y_n']}", period=f"{r['first']}→{r['last']}", source=r["file"])))
        L.append("")
    if a.window == "1y":
        L[0] = L[0].replace("— mỗi thị trường —", "— mỗi thị trường — xếp trên 12 tháng gần nhất —"); selection["mode"] = "horizons-1y"
    if RANK_NOTES:
        L += ["", "_Cách xếp hạng quyết định theo từng thị trường:_ " + " · ".join(RANK_NOTES)]
        selection["rank_notes"] = list(RANK_NOTES)
    selection["rank_by"] = getattr(a, "rank_by", "consistency")
    L += ["", validity_markdown()]
    md = "\n".join(L) + "\n"; print(md)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(md)
    if a.select:
        selection = finalize(selection, a.select)
        selection["research_validity"] = validity_note()
        json.dump(selection, open(a.select, "w", encoding="utf-8"), indent=1, ensure_ascii=False); print(f"-> {a.select} ({len(selection['setups'])} setups)")


# ---------------------------------------------------------------- INT-5: OOS-holdout selection (--window oos6m)
#
# docs/audits/2026-09-24-system-audit.md INT-5: `--horizons --window 1y` selected setups on the same window it
# then reported them on -- no out-of-sample evidence at all. Here selection reads ONLY each row's in-sample
# block (the 365 days that END at a data-derived cutoff, written by stability-report.py), and the in-sample
# winner of each (market, horizon, method) slot is then judged on the held-out months after the cutoff:
#   ENABLED       OOS net expectancy > 0 R AND OOS net P&L > 0 (both after costs)
#   REJECTED_OOS  otherwise -- the slot is left EMPTY. There is NO fallback to the in-sample runner-up: picking
#                 the next row BECAUSE the first failed the holdout would be selecting on the holdout.
#   EMPTY         no row passed the in-sample gates at all (as in the other modes)
# Every rejected pick stays on the record (selection file `rejected_oos`, and the report) with its numbers.
# Once this has run, the OOS window has influenced which setups trade, so it is EXPOSED (CLAUDE.md §44) and
# is recorded as such; it may not later be described as untouched validation data.
OOS_MIN_TRADES = {"scalping": 20, "day": 15, "swing": 6}   # in-sample minimums: the same as --horizons --window 1y
ENABLED, REJECTED_OOS, EMPTY = "ENABLED", "REJECTED_OOS", "EMPTY"


def require_oos_blocks(rows):
    """Every row must carry stability-report.py's `oos6m` block; a file written before INT-5 cannot be used."""
    missing = sorted({r["file"] for r in rows if not (r.get("oos6m") or {}).get("in_sample")})
    if missing:
        raise SystemExit("--window oos6m: no in-sample/OOS split in " + ", ".join(missing) + " -- regenerate "
                         "with the current scripts/stability-report.py (it writes the `oos6m` block)")


def market_cutoff(rows, market):
    """The ONE cutoff every row of this market was split at. Candidates judged on different holdouts are not
    comparable, so a mixture is refused rather than resolved."""
    cuts = sorted({r["oos6m"]["cutoff"] for r in rows})
    if len(cuts) != 1:
        raise SystemExit(f"--window oos6m: {market} rows were split at {len(cuts)} different cutoffs {cuts}; "
                         f"regenerate the {market} stability files from the same dataset")
    return cuts[0]


def oos_verdict(r):
    """(passed, reason) for the in-sample pick `r`, from its OOS block alone."""
    o = r["oos6m"]["oos"]
    if not o.get("n"):
        return False, "no trades in the OOS window: profitability is unmeasured, not assumed"
    ex, pnl = o.get("expectancy_R"), o.get("net_pnl")
    why = []
    if ex is None:
        why.append("OOS expectancy unavailable")
    elif not ex > 0:
        why.append(f"OOS net expectancy {ex:+.3f} R <= 0")
    if pnl is None or not pnl > 0:
        why.append(f"OOS net P&L {'n/a' if pnl is None else f'{pnl:+,.2f}'} <= 0")
    if o.get("ruin"):
        why.append(f"account failed in the OOS window ({o['ruin'][:10]})")
    return (not why), ("; ".join(why) if why else f"OOS net expectancy {ex:+.3f} R > 0 and net P&L {pnl:+,.2f} > 0")


def select_oos(rows, market):
    """Pure: the slot decisions and the experiment budget for one market. Never reads an OOS number before
    the in-sample winner of a slot is fixed."""
    budget = dict(candidate_rows=0, rankable_in_sample=0, slots=0, selected_in_sample=0, passed_oos=0,
                  rejected_oos=0, empty_in_sample=0)
    slots = []
    for hz, tf in HORIZONS.items():
        mn = OOS_MIN_TRADES[hz]
        for method in sorted(RUNNABLE):
            cands = [r for r in rows if r["tf"] == tf and r["method"] == method and (market == "crypto" or tf in CFD_TFS)]
            budget["slots"] += 1; budget["candidate_rows"] += len(cands)
            budget["rankable_in_sample"] += sum(1 for r in cands if solvent(r, "oos6m") and r["oos6m"]["in_sample"]["n"] >= mn)
            ranked = rank(cands, mn, "oos6m")
            slot = dict(market=market, horizon=hz, tf=tf, method=method, min_trades_in_sample=mn, candidates=len(cands))
            if not ranked:
                budget["empty_in_sample"] += 1
                slots.append(dict(slot, status=EMPTY, pick=None,
                                  reason=f"no candidate passed the in-sample gates (>= {MIN_WINDOW_DAYS} days, not "
                                         f"ruined, profitable, >= {mn} trades)"))
                continue
            pick = ranked[0]                      # FIXED here, before any OOS number is looked at
            budget["selected_in_sample"] += 1
            passed, why = oos_verdict(pick)
            budget["passed_oos" if passed else "rejected_oos"] += 1
            slots.append(dict(slot, status=ENABLED if passed else REJECTED_OOS, pick=pick, reason=why))
    return slots, budget


def _setup_id(market, hz, r):
    return f"{market}-{hz}-{r['method'].lower()}-{r['tf'].lower()}-{r['target']}-{r['cfg'].lower()}"


def _side(b):
    """The five reported numbers of one IS/OOS block, rounded for the written artifacts."""
    return dict(n=b["n"], expectancy_R=(None if b.get("expectancy_R") is None else round(b["expectancy_R"], 4)),
                profit_factor=(None if b.get("profit_factor") is None else round(b["profit_factor"], 3)),
                net_pnl=round(b["net_pnl"], 2), max_dd_pct=round(b["dd"], 2), ann_pct=round(b["ann"], 1),
                q_pos_pct=round(b["q_pos"]), ruin=b.get("ruin"), since=b["since"], until=b["until"])


def _source_meta(paths):
    """Per stability file: when it was generated, from which data and code, and its split."""
    out = {}
    for p in sorted(paths):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        ds = d.get("dataset_snapshot") or {}
        out[os.path.relpath(p, ROOT).replace(os.sep, "/")] = dict(
            generated=d.get("generated"), dataset_snapshot_id=ds.get("snapshot_id"),
            snapshot_error=ds.get("snapshot_error"), code_version=ds.get("code_version"),
            requested_but_absent=ds.get("requested_but_absent"), oos_holdout=d.get("oos_holdout"),
            run_params=d.get("run_params"), research_validity=(d.get("research_validity") or {}).get("verdict"))
    return out


def _fmt_num(v, f):
    return "n/a" if v is None else format(v, f)


def main_horizons_oos(a, today):
    import snapshot as _snap
    code = _snap.code_version()
    prev_exposure = {}
    if a.select and os.path.exists(a.select):
        try:
            with open(a.select, encoding="utf-8") as fh:
                prev_exposure = json.load(fh).get("oos_holdout") or {}
        except (OSError, ValueError):
            prev_exposure = {}
    selection = dict(generated=today, mode="horizons-oos6m", rank_by="consistency",
                     note="Written by scripts/rank-setups.py --horizons --window oos6m (INT-5). One setup per "
                          "(horizon, method) per market, chosen on the 365 days BEFORE a data-derived cutoff and "
                          "ENABLED only if profitable on the held-out months after it; failed picks are listed in "
                          "`rejected_oos` and their slot is left empty (no runner-up fallback). Crypto = Binance "
                          "futures testnet, CFD = MT5 demo via the file order bridge.",
                     setups=[], rejected_oos=[], empty_slots=[], oos_holdout={}, experiment_budget={},
                     code_version=code)
    all_slots, totals = [], {}
    sources = {}
    for market, paths, syms in (("crypto", a.crypto, a.crypto_symbols.split(",")), ("cfd", a.cfd, a.cfd_symbols.split(","))):
        rows = load_rows(sorted(paths), market, require_stamped=a.require_stamped)
        sources.update(_source_meta(paths))
        if not rows:
            selection["oos_holdout"][market] = dict(status="NO_DATA"); continue
        require_oos_blocks(rows)
        cutoff = market_cutoff(rows, market)
        last_bar = max(r["oos6m"]["dataset_last_bar"] for r in rows)
        slots, budget = select_oos(rows, market)
        for k, v in budget.items():
            totals[k] = totals.get(k, 0) + v
        selection["experiment_budget"][market] = budget
        uses = list(((prev_exposure.get(market) or {}).get("uses")) or [])
        prior_same = [u for u in uses if u.get("cutoff") == cutoff]
        uses.append(dict(date=today, cutoff=cutoff, by="rank-setups.py --horizons --window oos6m"))
        selection["oos_holdout"][market] = dict(
            cutoff=cutoff, dataset_last_bar=last_bar, oos_period=f"{cutoff[:10]} -> {last_bar[:10]}",
            in_sample_period=f"{rows[0]['oos6m']['in_sample']['since']} -> {cutoff[:10]}" if rows else None,
            status="EXPOSED",
            exposure=("this window has now decided which setups are enabled (CLAUDE.md §44): it is EXPOSED "
                      "and may not be called pristine/untouched validation data again"),
            times_used_for_selection=len(prior_same) + 1, uses=uses)
        for s in slots:
            s["symbols"] = syms
            all_slots.append(s)
            r = s["pick"]
            if s["status"] == EMPTY:
                selection["empty_slots"].append(dict(market=market, horizon=s["horizon"], tf=s["tf"], method=s["method"],
                                                     candidates=s["candidates"], reason=s["reason"]))
                continue
            cfg = CFG_DESC[r["cfg"]]
            bt_block = dict(window="oos6m", cutoff=cutoff, source=r["file"],
                            in_sample=_side(r["oos6m"]["in_sample"]), oos=_side(r["oos6m"]["oos"]),
                            # the keys /automation prints (automation.py apply_setup_spec) -- IN-SAMPLE values,
                            # since those are what the choice was made on; the OOS block sits beside them.
                            n=r["oos6m"]["in_sample"]["n"], ann_pct=round(r["oos6m"]["in_sample"]["ann"], 1),
                            max_dd_pct=round(r["oos6m"]["in_sample"]["dd"], 1), q_pos_pct=round(r["oos6m"]["in_sample"]["q_pos"]),
                            full_n=r["n"], full_ann_pct=round(r["ann"], 1), years_pos=f"{r['y_pos']}/{r['y_n']}",
                            period=f"{r['first']}→{r['last']}")
            entry = dict(id=_setup_id(market, s["horizon"], r), horizon=s["horizon"], market=market, symbols=syms,
                         tf=r["tf"], method=r["method"], htf=cfg["htf"], mgmt=cfg["mgmt"],
                         fee_assumed=fee_assumed_for(r["cfg"], market),
                         execution="futures" if market == "crypto" else "mt5", backtest=bt_block,
                         oos_decision=s["status"], oos_reason=s["reason"])
            if s["status"] == ENABLED:
                entry = dict(entry, rank=len(selection["setups"]) + 1, negative_backtest=False)
                selection["setups"].append(entry)
            else:
                selection["rejected_oos"].append(entry)
    selection["experiment_budget"]["total"] = totals
    selection["experiment_budget"]["_note"] = (
        "CLAUDE.md §43. candidate_rows = every (timeframe, method, configuration, target/account file) row "
        "considered for a slot; rankable_in_sample = those that passed the in-sample gates; selected_in_sample = "
        "slots with an in-sample winner (at most one per slot); passed_oos + rejected_oos = selected_in_sample. "
        "Configurations A/B/C and the account-conditioned files are each a candidate, so this is the number of "
        "hypotheses the holdout was asked to adjudicate among, not the number of rules.")
    selection["sources"] = sources
    selection["research_validity"] = validity_note()
    md = oos_markdown(selection, all_slots, today)
    print(md)
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(md)
    if a.select:
        selection = finalize(selection, a.select)
        # §47: rejected candidates stay traceable -- versioned exactly like the enabled ones.
        SV.stamp({"setups": selection["rejected_oos"]}, _global_rule_params)
        with open(a.select, "w", encoding="utf-8") as fh:
            json.dump(selection, fh, indent=1, ensure_ascii=False)
        print(f"-> {a.select} ({len(selection['setups'])} enabled, {len(selection['rejected_oos'])} rejected by OOS, "
              f"{len(selection['empty_slots'])} empty)")
    return selection


def oos_markdown(selection, slots, today):
    code = selection.get("code_version") or {}
    L = [f"# OOS-holdout setup selection (horizons, oos6m) — {today}", "",
         "_`scripts/rank-setups.py --horizons --window oos6m` — audit round 4b, finding INT-5 "
         "(docs/audits/2026-09-24-system-audit.md). Selection reads ONLY the in-sample window (the 365 days "
         "ending at the cutoff); the in-sample winner of each (market, horizon, method) slot is ENABLED only if "
         "its held-out months after the cutoff have net expectancy > 0 R AND net P&L > 0 after costs. A pick that "
         "fails is REJECTED and its slot stays EMPTY — no fallback to the runner-up (that would select on the "
         "holdout). Trades are assigned by ENTRY time: entry < cutoff → in-sample (even if it closes after), "
         "entry ≥ cutoff → OOS. Each side is simulated as its own fresh $10,000 account with live-parity sizing "
         "and per-method entry pricing (round 4a). Every number is a code proxy over research history._", "",
         "## Holdout", ""]
    for m, h in selection["oos_holdout"].items():
        if h.get("status") == "NO_DATA":
            L.append(f"- **{m}**: no stability rows"); continue
        L.append(f"- **{m}**: cutoff **{h['cutoff']}** (dataset last bar {h['dataset_last_bar']} − 6 calendar "
                 f"months, derived from the data); in-sample {h['in_sample_period']}; OOS {h['oos_period']}.")
    L += ["", "**The OOS period is now EXPOSED** (CLAUDE.md §44): it has decided which setups are enabled, so it may "
          "not later be described as pristine or untouched validation data. "
          + " ".join(f"{m}: used for selection {h.get('times_used_for_selection', '?')} time(s) at this cutoff."
                     for m, h in selection["oos_holdout"].items() if h.get("cutoff")), "",
          "## Provenance", "",
          f"- Code version (rank-setups run): `{code.get('git_sha')}`" + (f" — dirty: {code.get('dirty_note')}" if code.get("dirty") else ""),
          "- Stability sources (dataset snapshot id · generated · stability-report code SHA · §38 verdict):"]
    for rel, s in selection.get("sources", {}).items():
        cv = s.get("code_version") or {}
        L.append(f"  - `{rel}` · snapshot `{s.get('dataset_snapshot_id') or s.get('snapshot_error')}` · {s.get('generated')} · "
                 f"`{(cv.get('git_sha') or '?')[:12]}`{' (dirty)' if cv.get('dirty') else ''} · {s.get('research_validity')}"
                 + (f" · absent series: {', '.join(s['requested_but_absent'])}" if s.get("requested_but_absent") else ""))
    L += ["", "## Experiment budget (CLAUDE.md §43)", "",
          "| Market | Slots | Candidate rows | Rankable in-sample | Selected in-sample | Passed OOS | Rejected by OOS | Empty (no in-sample winner) |",
          "|---|---|---|---|---|---|---|---|"]
    for m, b in selection["experiment_budget"].items():
        if m.startswith("_"):
            continue
        L.append(f"| {m} | {b['slots']} | {b['candidate_rows']} | {b['rankable_in_sample']} | {b['selected_in_sample']} | "
                 f"{b['passed_oos']} | {b['rejected_oos']} | {b['empty_in_sample']} |")
    L += ["", "_" + selection["experiment_budget"]["_note"] + "_", "",
          "## Per slot: in-sample vs OOS", "",
          "| Market | Horizon | TF | Method | Pick (target · cfg) | IS n | IS exp R | IS PF | IS net P&L | IS max DD | OOS n | OOS exp R | OOS PF | OOS net P&L | OOS max DD | Decision | Reason |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in slots:
        r = s["pick"]
        if r is None:
            L.append(f"| {s['market']} | {s['horizon']} | {s['tf']} | {s['method']} | — | | | | | | | | | | | **EMPTY** | {s['reason']} |")
            continue
        i, o = _side(r["oos6m"]["in_sample"]), _side(r["oos6m"]["oos"])
        cells = []
        for b in (i, o):
            cells += [str(b["n"]), _fmt_num(b["expectancy_R"], "+.3f"), _fmt_num(b["profit_factor"], ".2f"),
                      f"${b['net_pnl']:+,.0f}", f"−{b['max_dd_pct']:.1f}%"]
        dec = "**ENABLED**" if s["status"] == ENABLED else "**REJECTED**"
        L.append(f"| {s['market']} | {s['horizon']} | {s['tf']} | {s['method']} | {r['target']} · {r['cfg']} (`{r['file'].rsplit('/', 1)[-1]}`) | "
                 + " | ".join(cells) + f" | {dec} | {s['reason']} |")
    en = [x["id"] for x in selection["setups"]]
    L += ["", f"**Enabled ({len(en)}):** " + (", ".join(f"`{x}`" for x in en) if en else "none"),
          f"**Rejected by OOS ({len(selection['rejected_oos'])}):** "
          + (", ".join(f"`{x['id']}`" for x in selection["rejected_oos"]) if selection["rejected_oos"] else "none"),
          "", "_Limitations: each side is a fresh account, so a position opened in-sample does not block an OOS entry "
          "on the same symbol (the one-position rule is applied within each side only). OOS P&L is simulated, not "
          "realised; the §38 flags of the source files (unmodelled slippage/spread/funding, required inputs the "
          "engine never consults) apply to both sides._", "", validity_markdown()]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
