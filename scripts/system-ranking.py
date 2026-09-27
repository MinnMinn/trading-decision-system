#!/usr/bin/env python3
"""CLAUDE.md §48 SYSTEM RANKING -- the page. docs/audits/2026-09-18-feature-audit.md row 5: "Artifact thống kê
xếp hạng độ hiệu quả các system" was MISSING -- `scripts/ranking.py` had every exposure §48 requires and no
caller.

This module is that caller, over the repository's own registries:

    docs/architecture/trading-systems.json systems  x  data/history/stability/*.json rows
                                  matched by (market, tf, method, cfg)

    import system_ranking as SR   # (loaded via importlib elsewhere -- the filename has a dash)
    SR.rows()                     # one dict per (Trading System, selected setup), every §48 exposure present
    SR.render(SR.rows())          # the built page, ONE document carrying both locales (see render() docstring)

Two things this module refuses to do, both of them §48's own refusals:

1. **No blended score.** `render()` calls `scripts/ranking.py rank()` once per objective in
   `docs/architecture/ranking.json`'s own order and renders one table per objective. The `custom` objective is
   skipped, with a note, rather than given a table: §48 requires a custom objective to declare its own keys, and
   a page cannot supply that on a caller's behalf without becoming the very blend §48 forbids.
2. **No invented number.** Every §39 metric on a row is copied from the matched stability row's `perf` block
   unchanged -- `performance.unavailable()` stays a marker all the way to the screen, rendered as an em dash
   with its reason in `title=`, never silently completed.

`positive_period_share` and `worst_period` are the two `consistency` objective keys that do not live in the
§39 `perf` block (confirmed absent: no stability row's `perf` carries either). They are derived here from the
stability row's OWN quarterly figures (`q_pos`, `q_worst`) rather than invented -- `q_pos` is already the share
of positive quarters (0-100), just relabelled to a 0-1 fraction to match every other §39 fraction on this page.
"""
import argparse
import html
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from repo_paths import repo_rel
import trading_system as TS
import account_profile as AP       # noqa: E402
import performance as P           # noqa: E402
import ranking as R               # noqa: E402
import ui_contract as UI          # noqa: E402
import i18n                       # noqa: E402
import artifact_theme as theme    # noqa: E402


def _rank_setups_module():
    """scripts/rank-setups.py -- imported the way rank-setups.py imports stability-report.py, because its
    filename has a dash. `load_rows()` is THE reader that applies the §38 validity gate; this module must not
    grow a second one."""
    spec = importlib.util.spec_from_file_location(
        "rank_setups", os.path.join(ROOT, "scripts", "rank-setups.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


RS = _rank_setups_module()


def esc(s):
    return html.escape(str(s), quote=True)


# --------------------------------------------------------------------------------------------------- rows()
def _cfg_of(pilot_id):
    """The stability row's cfg letter, read off the tail of the pilot-selection.json id
    (`f"...-{cfg.lower()}"`, scripts/rank-setups.py `_setup_id`) -- never re-typed."""
    return pilot_id.rsplit("-", 1)[-1].upper()


_STAB_CACHE = {}


class NoStabilityRow(LookupError):
    """A pilot-selection.json setup names a (tf, method, cfg) this module could not find in its own stability
    source. A matching gap, not something to fuzzy-match past."""


def _stability(source_rel, market):
    """(config_snapshot, {(tf, method, cfg): row}, §38 verdict block) for one stability file, read once."""
    key = (source_rel, market)
    if key in _STAB_CACHE:
        return _STAB_CACHE[key]
    path = os.path.join(ROOT, source_rel)
    raw = json.load(open(path, encoding="utf-8"))
    rs_rows = RS.load_rows([path], market)
    by_key = {}
    for r in rs_rows:
        by_key.setdefault((r["tf"], r["method"], r["cfg"]), r)
    result = (raw.get("config_snapshot") or {}, by_key, RS.SOURCE_VALIDITY.get(source_rel))
    _STAB_CACHE[key] = result
    return result


def _unwrap_perf(perf, key):
    """A §39 value, copied UNCHANGED -- or an `unavailable()` marker naming which key this row's `perf` block
    never had, never a silently invented number."""
    return perf.get(key, P.unavailable(f"§39 metrics block has no {key!r} for this row"))


def _row(style, prow, srow, config_snapshot, validity_block, account=None):
    perf = srow.get("perf") or {}
    ea = (config_snapshot.get("fields") or {}).get("execution_assumptions") or {}
    q_pos, q_worst = srow.get("q_pos"), srow.get("q_worst")
    return {
        # `account` is whichever account these numbers were simulated under: the one this call was made for,
        # or -- when the SELECTION's own stability source is already an account file (a selection row whose
        # `backtest.source` names an account-conditioned stability file) -- the one the row itself records. Without the
        # fallback an account-conditioned base row carried real §39 account metrics while claiming no
        # account, which is exactly the "where did this number come from" failure the label exists to prevent.
        "id": f"{style}::{prow['id']}" + (f"@{account}" if account else ""),
        "trading_system": style,
        "setup_id": prow["id"] + (f" @ {account}" if account else ""),
        "account": account or srow.get("account"),
        "failed_by": srow.get("failed_by"),
        "n": perf.get("n", srow.get("n")),
        # ranking.py's _num() special-cases "not_ruined" by reading THIS field, not a "not_ruined" key.
        "ruin": srow.get("ruin"),
        "expectancy": _unwrap_perf(perf, "expectancy"),
        "max_drawdown": _unwrap_perf(perf, "max_drawdown"),
        "time_in_drawdown": _unwrap_perf(perf, "time_in_drawdown"),
        "account_failure_probability": _unwrap_perf(perf, "account_failure_probability"),
        "prop_pass_probability": _unwrap_perf(perf, "prop_pass_probability"),
        "sortino": _unwrap_perf(perf, "sortino"),
        "sharpe": _unwrap_perf(perf, "sharpe"),
        "positive_period_share": (q_pos / 100.0) if isinstance(q_pos, (int, float))
            else P.unavailable("stability row carries no q_pos (share of positive quarters)"),
        "worst_period": q_worst if isinstance(q_worst, (int, float))
            else P.unavailable("stability row carries no q_worst (worst quarter return)"),
        # ---- CLAUDE.md §48 "always expose" -- the seven ranking.exposure_gaps() checks on every row.
        "ranking_objective": (
            "consistency (docs/architecture/ranking.json's 'consistency' objective, applied for display on "
            "this page only; the pilot's selection is NOT a ranking -- ADR 0008 enables every system that "
            "passes docs/architecture/selection-criteria.json on in-sample and OOS)"),
        "metrics": perf,
        "sample_size": perf.get("n", srow.get("n")),
        "validation_state": validity_block or P.unavailable("no §38 verdict recorded for this stability file"),
        "test_period": f"{srow.get('first')}..{srow.get('last')}",
        "assumptions": {
            "account": account or "none (personal blown-account rule only)",
            "fee_assumed": prow.get("fee_assumed"), "mgmt": prow.get("mgmt"), "htf": prow.get("htf"),
            "stop_buffer_pct": ea.get("stop_buffer_pct"), "slippage": ea.get("slippage"),
            "funding": ea.get("funding"), "fill_model": ea.get("fill_model"),
        },
        "robustness_status": srow.get("robustness") or P.unavailable(
            "no walk-forward / perturbation run recorded (§45)"),
    }


def account_sources(source_rel):
    """The account-conditioned siblings of a stability source, as [(account_id, source_rel)].

    `stability-report.py --account <id> --json data/history/stability/<market>-<id>.json` writes a file whose
    rows were simulated under THAT account's failure rules (CLAUDE.md §33/§39: `prop_pass_probability`,
    `account_failure_probability`, `failed_by` are only real there). Discovered on disk, next to the live
    file, one per declared profile id -- never invented: a profile with no file simply has no rows here.
    """
    d, base = os.path.split(source_rel)
    market = base.split("-", 1)[0]
    out = []
    for pid in sorted(AP.PROFILES):
        rel = os.path.join(d, f"{market}-{pid}.json")
        if os.path.exists(os.path.join(ROOT, rel)):
            out.append((pid, rel))
    return out


def rows():
    """One row per (Trading System, selected setup) -- docs/architecture/trading-systems.json `styles()` x
    each style's `setups()` (pilot-selection.json rows sharing its market+horizon), matched to their stability
    source by (market, tf, method, cfg). A style with no selected setup contributes no row.

    Plus one row per ACCOUNT-conditioned stability file found beside the source (account_sources()): the same
    setup measured under a declared account's own failure rules, labelled with the account id, so the
    Survival and Prop Pass Rate objectives have real numbers to rank instead of `unavailable` markers."""
    out = []
    for style in TS.styles():
        sysd = TS.get(style)
        for prow in TS.setups(style):
            source = prow["backtest"]["source"]
            config_snapshot, by_key, validity = _stability(source, sysd["market"])
            cfg = _cfg_of(prow["id"])
            srow = by_key.get((prow["tf"], prow["method"], cfg))
            if srow is None:
                raise NoStabilityRow(
                    f"{style}: setup {prow['id']!r} names (tf={prow['tf']!r}, method={prow['method']!r}, "
                    f"cfg={cfg!r}) with no matching row in {source}")
            out.append(_row(style, prow, srow, config_snapshot, validity))
            for account_id, arel in account_sources(source):
                a_snap, a_by_key, a_validity = _stability(arel, sysd["market"])
                arow = a_by_key.get((prow["tf"], prow["method"], cfg))
                if arow is None:
                    continue                       # that account file did not cover this setup: no row, no guess
                out.append(_row(style, prow, arow, a_snap, a_validity, account=account_id))
    return out


# --------------------------------------------------------------------------------------------------- render()
NON_CUSTOM = tuple(oid for oid in R.OBJECTIVE_ORDER if oid != "custom")

_CSS = """
.ranking-page{max-width:1180px;margin:0 auto;padding:24px 20px 60px;font-family:var(--sans);color:var(--ink);background:var(--bg)}
.ranking-page h1{font-size:22px;margin:0 0 6px}
.ranking-page .intro,.ranking-page .no-universal-score{color:var(--muted);font-size:13px;max-width:78ch;line-height:1.5}
.ranking-page .no-universal-score{border-left:3px solid var(--accent);padding-left:10px;margin:12px 0 24px}
.ranking-objective{margin:28px 0;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:16px}
.ranking-objective h2{margin:0 0 4px;font-size:16px}
.ranking-objective .caption{color:var(--muted);font-size:12.5px;margin:0 0 12px}
.ranking-objective table{border-collapse:collapse;width:100%;font-size:12.5px}
.ranking-objective th,.ranking-objective td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
.ranking-objective code{font-family:var(--mono);font-size:11.5px;color:var(--ink-2)}
.unavail{color:var(--muted);cursor:help;border-bottom:1px dotted var(--faint)}
.ranking-custom-note{color:var(--muted);font-size:12.5px;margin:8px 0 28px}
.exposure-report{margin:24px 0;background:var(--surface-2);border:1px solid var(--line);border-radius:10px;padding:16px}
.exposure-report h2{margin:0 0 8px;font-size:15px}
.exposure-report ul{margin:0;padding-left:18px;font-size:12.5px;color:var(--ink-2)}
.ranking-head{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:6px}
.ranking-head h1{margin:0}
"""

# The artifact's identity in the gallery and the browser tab. Kept STABLE across redeploys -- a changed title
# reads as a different page. The language toggle sets document.title at runtime instead (i18n.switch_js), so
# the tab still reads in the chosen language. Same value as the i18n.json "ranking.page.title" message (both
# locales identical -- it is the §50 area name, a proper noun, not translated).
TITLE = "System Performance & Ranking"   # artifact-identity: stable across redeploys


def _fmt_metric(v, lang, kind="float"):
    """One §39 value, formatted -- or `performance.unavailable()`'s reason as an em dash with the reason in
    `title=`. Never a bare None, never a silently zeroed unavailable marker."""
    if P.is_unavailable(v):
        reason = esc(v.get("unavailable", ""))
        dash = esc(i18n.t("ui.dash", lang))
        return f'<span class="unavail" title="{reason}">{dash}</span>'
    if isinstance(v, dict):
        for k in ("value", "fraction", "mean"):
            if isinstance(v.get(k), (int, float)):
                return i18n.num(v[k], kind=kind, lang=lang)
        return esc(json.dumps(v, ensure_ascii=False))
    if isinstance(v, (int, float)):
        return i18n.num(v, kind=kind, lang=lang)
    return esc(v) if v not in (None, "") else esc(i18n.t("ui.dash", lang))


_INT_KEYS = {"n", "sample_size"}


def _fmt_key(row, key, lang):
    if key == "not_ruined":
        ruin = row.get("ruin")
        return (i18n.t("ranking.not_ruined.alive", lang) if not ruin
                else esc(i18n.t("ranking.not_ruined.ruined", lang, date=str(ruin))))
    return _fmt_metric(row.get(key), lang, kind="int" if key in _INT_KEYS else "float")


def _objective_table(oid, res, lang):
    o = R.objective(oid)
    keys = res["keys"]
    body_rows = []
    for entry in res["ranked"]:
        row = entry["row"]
        decided = entry["decided_by"] or i18n.t("ranking.decided_by.none", lang)
        missing = ", ".join(entry["missing_exposure_names"]) or esc(i18n.t("ui.dash", lang))
        assumptions = row.get("assumptions") or {}
        validation = row.get("validation_state")
        verdict = validation.get("verdict") if isinstance(validation, dict) else validation
        key_cells = "".join(f"<td>{_fmt_key(row, k, lang)}</td>" for k in keys)
        body_rows.append(
            "<tr>"
            f'<td>{entry["rank"]}</td>'
            f'<td>{esc(row["trading_system"])}</td>'
            f'<td>{esc(row["setup_id"])}</td>'
            + key_cells +
            f'<td{UI.attr("ranking-sample-size")}>{_fmt_metric(row.get("sample_size"), lang, kind="int")}</td>'
            f'<td>{esc(decided)}</td>'
            f'<td{UI.attr("ranking-validation-state")} title="{esc(json.dumps(validation, ensure_ascii=False))}">{esc(verdict) if verdict else esc(i18n.t("ui.dash", lang))}</td>'
            f'<td{UI.attr("ranking-test-period")}>{esc(row.get("test_period"))}</td>'
            f'<td{UI.attr("ranking-assumptions")} title="{esc(json.dumps(assumptions, ensure_ascii=False))}">{esc(assumptions.get("fee_assumed")) if assumptions.get("fee_assumed") is not None else esc(i18n.t("ui.dash", lang))}</td>'
            f'<td{UI.attr("ranking-robustness")}>{_fmt_metric(row.get("robustness_status"), lang)}</td>'
            f'<td>{esc(missing)}</td>'
            "</tr>")
    header_keys = "".join(f"<th><code>{esc(k)}</code></th>" for k in keys)
    caption = i18n.t("ranking.objective.caption", lang, name=o["spec_name"], keys=" > ".join(keys))
    header = (
        f'<th>{esc(i18n.t("ranking.col.rank", lang))}</th>'
        f'<th>{esc(i18n.t("ranking.col.trading_system", lang))}</th>'
        f'<th>{esc(i18n.t("ranking.col.setup", lang))}</th>'
        + header_keys +
        f'<th>{esc(i18n.t("ranking.col.n", lang))}</th>'
        f'<th>{esc(i18n.t("ranking.col.decided_by", lang))}</th>'
        f'<th>{esc(i18n.t("ranking.col.validation_state", lang))}</th>'
        f'<th>{esc(i18n.t("ranking.col.test_period", lang))}</th>'
        f'<th>{esc(i18n.t("ranking.col.assumptions", lang))}</th>'
        f'<th>{esc(i18n.t("ranking.col.robustness", lang))}</th>'
        f'<th>{esc(i18n.t("ranking.col.missing", lang))}</th>')
    tbody = "\n".join(body_rows)
    return (f'<section class="ranking-objective"{UI.attr("ranking-objective")}>'
            f'<h2>{esc(o["spec_name"])}</h2><p class="caption">{esc(caption)}</p>'
            f'<table><thead><tr>{header}</tr></thead>\n<tbody>\n{tbody}\n</tbody></table>\n'
            f'</section>')


def _exposure_report_html(all_rows, lang):
    report = R.exposure_report(all_rows)
    items = []
    for eid in R.EXPOSURES:
        info = report[eid]
        line = f'{esc(R.EXPOSURE_NAMES[eid])}: {info["supplied"]}/{info["of"]}'
        if info["missing_from"]:
            line += (f' — {esc(i18n.t("ranking.exposure_report.missing_from", lang))}: '
                     + esc(", ".join(str(x) for x in info["missing_from"])))
        items.append(f"<li>{line}</li>")
    li = "\n".join(items)
    return (f'<section class="exposure-report"><h2>{esc(i18n.t("ranking.exposure_report.title", lang))}</h2>'
            f'<ul>\n{li}\n</ul></section>')


def render(all_rows):
    """The built page -- ONE standalone document carrying BOTH locales as lang-tagged siblings, same pattern as
    scripts/journal_render.py and scripts/method-panel.py: i18n.dual() renders each fragment once per locale,
    i18n.switch_css() hides every locale but the active one, i18n.switch_js() stamps data-lang before paint and
    wires the EN/VI buttons (i18n.switch_html()). Until 2026-09-18 this page built two STANDALONE documents
    (main() wrote one file per locale) with no in-page switch -- the only one of the three §50 UI areas
    (Trading Control Center, Trade Journal & Performance, System Performance & Ranking) without the toggle the
    other two already carry. Charset stays first, within the browser's encoding pre-scan window."""
    sections = []
    for oid in NON_CUSTOM:
        res = R.rank(all_rows, objective_id=oid)
        sections.append(i18n.dual(lambda l, oid=oid, res=res: _objective_table(oid, res, l), tag="div"))
    custom = R.objective("custom")
    sections.append(
        '<p class="ranking-custom-note">'
        + i18n.dual(lambda l: esc(i18n.t("ranking.custom.note", l, name=custom["spec_name"])))
        + '</p>')
    return (
        '<meta charset="utf-8">\n'
        f'<title>{TITLE}</title>\n'
        + i18n.switch_js("ranking.page.title") + "\n"
        + theme.FONTS + "\n<style>" + theme.TOKENS + _CSS + i18n.switch_css() + "</style>\n"
        + '<div class="ranking-page">\n'
        + f'<div class="ranking-head"><h1>{i18n.tx("ranking.page.title")}</h1>{i18n.switch_html()}</div>\n'
        + f'<p class="intro">{i18n.tx("ranking.page.intro")}</p>\n'
        + f'<p class="no-universal-score">{i18n.tx("ranking.no_universal_score")}</p>\n'
        + "\n".join(sections)
        + "\n" + i18n.dual(lambda l: _exposure_report_html(all_rows, l), tag="div")
        + "\n</div>")


# --------------------------------------------------------------------------------------------------- CLI
DEFAULT_OUT_DIR = os.path.join(ROOT, "data", "live")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR,
                     help="directory to write .vi-system-ranking.html into (default: data/live)")
    a = ap.parse_args()
    all_rows = rows()
    os.makedirs(a.out_dir, exist_ok=True)
    # ONE file, both locales -- same convention as the nine style pages in docs/architecture/artifacts.json
    # (each published once, at its `out` path, under the AUTHORED-locale prefix even though the page itself is
    # dual-locale). Matches artifacts.json pages.system-ranking.out, which already names this exact file.
    out = os.path.join(a.out_dir, ".vi-system-ranking.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(render(all_rows))
    print(f"wrote {len(all_rows)} row(s) -> {repo_rel(out, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
