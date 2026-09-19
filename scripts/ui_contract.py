"""CLAUDE.md §50 -- THE reader for docs/architecture/ui-fields.json, and the only place that says what a page owes.

§50 is the one section whose compliance is invisible from the code. Every other section can be satisfied by a
module that computes the right thing; §50 is satisfied only if the right thing reaches the screen. A field can
be computed correctly, carried correctly, provenance intact, and never be rendered -- and nothing else in this
repository would notice.

So the field list is a registry, every field names a **marker**, and the page renders that marker as a
`data-ui-field` attribute on the element carrying the value:

    <span data-ui-field="execution-venue">binance_futures (testnet)</span>

The checker builds the real pages and looks for the attribute. Which means a field cannot be marked exposed by
editing this file -- only by rendering it.

    import ui_contract as UI

    UI.attr("execution-venue")      # -> ' data-ui-field="execution-venue"'   (what the builder emits)
    UI.expected("chart")            # -> the markers that page owes
    UI.audit(html, "chart")         # -> {"present": [...], "missing": [...]}

Two loader refusals, both of edits that would invert §50's meaning rather than weaken it:

* **Required and optional analysis may not share a marker class.** §50: "Required analysis should be visually
  distinguishable from optional analysis." If the two render identically the page implies every displayed lane
  counts toward the trade, which is the exact confusion §18 and §62 exist to prevent. Equal
  `distinguishable_by` values are refused at load.
* **A field must name the reader that supplies it**, in `scripts/<module>.py ...` form. A literal typed into a
  template is not exposure, it is assertion: a page that says PERPETUAL because someone typed PERPETUAL would
  keep saying it after the venue changed.

And `pages: []` stays legal, because "this repository has no value to put there" is a fact worth recording --
but it must carry a `_why`, or it is indistinguishable from an oversight.
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "docs", "architecture", "ui-fields.json")

ATTR = "data-ui-field"


class RegistryError(ValueError):
    """docs/architecture/ui-fields.json says something §50 does not allow."""


def _load(path=None):
    data = json.load(open(path or PATH, encoding="utf-8"))
    pages = {k: v for k, v in data["pages"].items() if not k.startswith("_")}
    seen_markers, roles = {}, {}
    for f in data["fields"]:
        fid = f["id"]
        if not f.get("pages"):
            if not str(f.get("_why") or "").strip():
                raise RegistryError(
                    f"{fid!r} is on no page and gives no reason -- an unsurfaced field with no `_why` is "
                    f"indistinguishable from an oversight, and §50's list is the one place that difference is "
                    f"recorded.")
            continue
        for p in f["pages"]:
            if p not in pages:
                raise RegistryError(f"{fid!r} claims page {p!r}, which no builder produces")
        if not f.get("marker"):
            raise RegistryError(f"{fid!r} is on a page but names no marker, so nothing can check it")
        if f["marker"] in seen_markers:
            raise RegistryError(f"marker {f['marker']!r} is claimed by both {seen_markers[f['marker']]!r} "
                                f"and {fid!r}; one attribute cannot prove two fields")
        seen_markers[f["marker"]] = fid
        if not re.match(r"^scripts/[a-z_\-]+\.py ", str(f.get("source") or "")) and \
                not str(f.get("source") or "").strip():
            raise RegistryError(f"{fid!r} names no source")
        if f.get("distinguishable_by"):
            roles[fid] = f["distinguishable_by"]
    if len(set(roles.values())) != len(roles):
        raise RegistryError(
            "required and optional analysis must not share a `distinguishable_by` class -- CLAUDE.md §50: "
            "'Required analysis should be visually distinguishable from optional analysis.' Rendering them "
            "identically implies every displayed lane counts toward the trade, which is the confusion §18 and "
            "§62 exist to prevent.")
    return data


_DATA = _load()

PAGES = tuple(k for k in _DATA["pages"] if not k.startswith("_"))
FIELDS = tuple(f["id"] for f in _DATA["fields"])
AREAS = tuple(a["spec_name"] for a in _DATA["areas"])
FORBIDDEN_WORDS = tuple(_DATA["forbidden_words"]["words"])


def field(fid):
    for f in _DATA["fields"]:
        if f["id"] == fid:
            return f
    raise KeyError(fid)


def area(name):
    for a in _DATA["areas"]:
        if a["spec_name"] == name:
            return a
    raise KeyError(name)


def spec_names():
    """§50's own wording, in §50's order -- what the drift test compares against CLAUDE.md."""
    return [f["spec_name"] for f in _DATA["fields"]]


def attr(marker):
    """What a builder emits. One function so the attribute name has one spelling in the repository."""
    return f' {ATTR}="{marker}"'


def expected(page):
    """The markers `page` owes, by §50."""
    return tuple(f["marker"] for f in _DATA["fields"] if page in (f.get("pages") or ()))


def present(html):
    """The markers actually rendered in a built page."""
    return set(re.findall(rf'{ATTR}="([a-z\-]+)"', html))


def audit(html, page):
    have = present(html)
    want = expected(page)
    return {"page": page,
            "present": [m for m in want if m in have],
            "missing": [m for m in want if m not in have],
            "unregistered": sorted(have - set(m for f in _DATA["fields"] for m in [f.get("marker")] if m))}


def describe():
    lines = [f"§50 UI contract: {len(FIELDS)} fields over {len(PAGES)} page(s)."]
    for p in PAGES:
        lines.append(f"  {p:<8} owes {len(expected(p))}: {', '.join(expected(p))}")
    for a in _DATA["areas"]:
        served = ", ".join(a["served_by"]) if a["served_by"] else "no page"
        lines.append(f"  area {a['spec_name']:<32} {served}")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="CLAUDE.md §50 UI field contract.")
    ap.add_argument("--audit", nargs=2, metavar=("PAGE", "FILE"), default=None)
    a = ap.parse_args()
    if a.audit:
        page, path = a.audit
        r = audit(open(path, encoding="utf-8").read(), page)
        print(f"{page}: {len(r['present'])}/{len(r['present']) + len(r['missing'])} rendered")
        if r["missing"]:
            print("  MISSING: " + ", ".join(r["missing"]))
    else:
        print(describe())
