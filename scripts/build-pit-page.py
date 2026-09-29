#!/usr/bin/env python3
"""A3t -- build a chart page as the engine would have drawn it at a chosen historical decision time T.

    BT_HISTORY_ROOT=data/history/ftmo python3 scripts/build-pit-page.py \\
        --symbol XAUUSD --tf 15m --at 2023-06-15T14:00:00Z --out /tmp/pit-xau.html [--method ICT|WYCKOFF-BOOK]

What the page is (docs/plans/2026-09-28-methodology-improvement-plan.md section 2, A3 / A3t): the input to the image
gate. A reviewer judges the DRAWING against knowledge/, never outcomes, so the page holds
  * only bars whose `available_time` (open + one bar, normalized.available_time) is <= T -- selected by
    pit.series_as_of, the repo's one point-in-time seam (CLAUDE.md section 8), never by a formed/open-time compare;
  * only the engine's own structure objects (structures.ict_structures / wyckoff_structures) computed on that
    prefix, through the SAME build-artifact.py functions the live page uses (ict_json / wy_json_engine / rows_js /
    js_block / chart.js) -- the drawing logic is reused, not forked;
  * no trade plans, no invalidation level, no narrative, no outcome marker: the data block ships `plans=[]`.

Development only. T (and therefore every bar drawn) must be strictly before DEV_CUTOFF, the constant of
scripts/diagnose-methods.py (prop-search VALIDATION_START) -- read from there, not restated. A T at/after the
cutoff, or a symbol/window with no bar available by T, is REFUSED (non-zero exit). Note the history reader parses
a whole file, so later rows are held in memory by the shared reader; they are dropped by series_as_of before
anything is computed or written, and the page never contains them.

Window: the last TF_SPEC bar count of the prefix (the size the live page draws for this timeframe).
"""
import argparse, datetime, html, importlib.util, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

METHOD_LANE = {"ICT": "ict", "WYCKOFF-BOOK": "wyckoff"}


def _load(fname, modname):
    spec = importlib.util.spec_from_file_location(modname, os.path.join(ROOT, "scripts", fname))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Refused(Exception):
    """A request outside the development window, or with nothing to draw. Becomes a non-zero exit."""


def dev_cutoff():
    """The development cutoff, from its one home (scripts/diagnose-methods.py `DEV_CUTOFF`)."""
    return _load("diagnose-methods.py", "diagnose_methods_cutoff").DEV_CUTOFF


def _utc(iso):
    if not isinstance(iso, str) or not iso.endswith("Z"):
        raise Refused(f"time {iso!r} refused: give an ISO-8601 UTC time ending in Z, e.g. 2023-06-15T14:00:00Z")
    try:
        dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        raise Refused(f"time {iso!r} refused: not an ISO-8601 UTC time")
    if dt.tzinfo is None:       # e.g. a date-only "<date>Z" parses naive; comparing it to an aware cutoff would raise
        raise Refused(f"time {iso!r} refused: give a full ISO-8601 UTC time ending in Z, e.g. 2023-06-15T14:00:00Z")
    return dt


def check_at(at):
    """Refuse a decision time at/after the development cutoff. Returns the aware UTC datetime."""
    cutoff = dev_cutoff()
    t = _utc(at)
    if t >= _utc(cutoff):
        raise Refused(f"--at {at} refused: charts are rendered for DEVELOPMENT data only, strictly before {cutoff}. "
                      f"Nothing was read or written.")
    return t


def pit_rows(sym, tf, at, root=None, n=None):
    """The last `n` bars (default: this timeframe's live window) knowable at `at`, from the shared history reader."""
    import history_store as HS, pit
    t = check_at(at)
    doc, path = HS.read_doc(sym, tf, root=root)
    if doc is None:
        raise Refused(f"no history for {sym} {tf} under {root or HS.history_root()} (set BT_HISTORY_ROOT).")
    prefix = pit.series_as_of(doc["candles"], tf, t, symbol=sym)
    if not prefix:
        raise Refused(f"{sym} {tf} has no bar available at or before {at} in {path}: the requested window lies "
                      f"outside this symbol's development history. Nothing was drawn.")
    if n is None:
        spec = _load("build-artifact.py", "build_artifact_pit").TF_SPEC
        if tf not in spec:
            raise Refused(f"unknown timeframe {tf!r}: one of {sorted(spec)}")
        n = spec[tf][0]
    return prefix[-n:]


def entry_data(rows, sym, tf, method):
    """The chart's data block for one symbol/one tier/one lane -- built with build-artifact's own functions."""
    b = _load("build-artifact.py", "build_artifact_pit")
    import instruments as I
    lane = METHOD_LANE[method]
    kind = "int" if I.display(sym)["price_decimals"] == 0 else "2"
    if lane == "ict":
        wy, ict = {"tr": None, "events": [], "phases": []}, b.ict_json(rows, tf)
    else:
        wy, ict = b.wy_json_engine(rows, tf, sym, kind), {"structures": [], "dealing_range": {}, "bias": None}
    off = {l: f"not requested ({method} only)" for l in b.i18n.LOCALES}
    return b, dict(fmt=kind, tick=I.is_tick_volume(sym), market=I.display(sym)["asset_class"],
                   dims={m: (off if m != lane else {l: "" for l in b.i18n.LOCALES}) for m, _ in b.LANES},
                   engaged=[lane], analysed=[lane],
                   tiers=[dict(key="entry", tf=tf, kz=(tf != "4H"), tfMin=b.TF_MIN.get(tf, 0), wy=wy, ict=ict,
                               quality=None, levels=[], compact=False, rows="__ROWS__")],
                   plans=[], updated=None, invalidation=None)


def render(sym, tf, at, method, rows, root=None):
    b, data = entry_data(rows, sym, tf, method)
    key = "pit"
    data_json = json.dumps({key: data}, ensure_ascii=False).replace('"__ROWS__"', b.rows_js(rows, "%m-%d %H:%M"))
    esc = html.escape
    title = f"{sym} {tf} as of {at} ({method}, point-in-time)"
    block = (f'<div class="chart-block" id="entry-{key}"><div class="chart-title"><span><b>{esc(title)}</b> · '
             f'{esc(rows[0]["time"])} .. {esc(rows[-1]["time"])} · {len(rows)} bars</span>'
             f'<span class="zoom">{b.zoom_buttons(full=True)}</span></div>'
             f'<div class="chart-wrap"><div class="chart" id="chart-entry-{key}"></div><div class="tip"></div></div>'
             f'<div class="mode-status" hidden></div><div class="lane-status" hidden></div></div>'
             f'<div class="legend" id="legend-{key}"></div>')
    P = b.chart_params(dict(lookback=20, high=1.5, spike=2.5))
    return ('<meta charset="utf-8">\n<title>' + esc(title) + '</title>\n' + b.i18n.switch_js() + '\n' + b.theme.FONTS + '\n'
            + b.CSS.replace('__TOKENS__', b.theme.TOKENS).replace('__I18N__', b.i18n.switch_css())
            + '<div class="page"><h1>' + esc(title) + '</h1>'
            + '<p class="muted">Point-in-time drawing: only bars available at or before the decision time; '
              'engine structure objects computed on that prefix. Development data only.</p>'
            + block + '</div>\n' + b.js_block(data_json, json.dumps(P)))


def build(sym, tf, at, out, method="ICT", root=None):
    if method not in METHOD_LANE:
        raise Refused(f"--method {method!r} refused: one of {sorted(METHOD_LANE)}")
    rows = pit_rows(sym, tf, at, root=root)
    page = render(sym, tf, at, method, rows, root=root)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", required=True); ap.add_argument("--tf", required=True)
    ap.add_argument("--at", required=True, help="decision time T, ISO-8601 UTC (Z), strictly before the development cutoff")
    ap.add_argument("--out", required=True); ap.add_argument("--method", default="ICT", choices=sorted(METHOD_LANE))
    a = ap.parse_args(argv)
    try:
        rows = build(a.symbol, a.tf, a.at, a.out, a.method)
    except Refused as e:
        sys.exit(f"REFUSED: {e}")
    print(f"PIT PAGE OK -> {a.out} ({a.symbol} {a.tf} {a.method}, {len(rows)} bars, last bar open {rows[-1]['time']}, as of {a.at})")


if __name__ == "__main__":
    main()
