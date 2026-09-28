"""CLAUDE.md §53 -- THE reader and validator for the Architecture Decision Log in docs/adr/.

§53 asks for eight fields per decision and adds one rule that is easy to read past:

    "When an alternative has been rejected, do not repeatedly reopen it unless new evidence appears."

The repo had dated decisions -- in `SYSTEM-DESIGN.md` sections, in `docs/specs/*` `## Decisions` blocks, in
audit rows -- and no single place to look. "Has this been decided?" had no answer that was not a grep, and
"was this alternative already rejected, and why?" had no answer at all. The second question is the expensive
one: an alternative re-proposed and re-rejected costs the same as the first time.

    import adr

    adr.all_records()                 # every decision, newest first
    adr.rejected_alternatives()       # every alternative anyone has rejected, with the ADR and the reason
    adr.check_reopening("polling instead of a websocket")   # -> the ADR that already rejected it

One decision about the format worth stating: an ADR here is a **markdown file with a YAML-ish frontmatter
block**, not JSON. §53's fields are prose -- context, reason, consequences -- and prose in JSON is unreadable
in a diff, which is where a decision log is actually read.

**ADRs point, they do not restate.** The design detail lives in `SYSTEM-DESIGN.md`; the ADR carries §53's
eight fields and a pointer. Restating would create a second copy that goes stale the first time the design
changes -- the failure `rules/single-source-of-truth.md` exists to prevent.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys as _sys; _sys.path.insert(0, os.path.join(ROOT, "scripts"))  # importable when loaded by path from anywhere
from repo_paths import repo_rel
DIR = os.path.join(ROOT, "docs", "adr")

#: CLAUDE.md §53's own list, in §53's order. A record missing any of these is not an ADR.
FIELDS = ("context", "problem", "decision", "alternatives", "chosen_approach", "reason", "consequences",
          "rejected_alternatives")

#: Fields whose value is a LIST (one entry per alternative). The rest are prose.
LIST_FIELDS = ("alternatives", "rejected_alternatives")

STATUSES = ("ACCEPTED", "SUPERSEDED", "REOPENED")


class MalformedADR(ValueError):
    """A file in docs/adr/ that is not a complete §53 record."""


class AlreadyRejected(RuntimeError):
    """An alternative CLAUDE.md §53 says not to reopen without new evidence."""


def _parse(text, path):
    """Frontmatter + body. The frontmatter carries the eight fields; the body is free prose."""
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        raise MalformedADR(f"{path}: no frontmatter block")
    fm, body, key = {}, m.group(2), None
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("  - "):
            if key not in LIST_FIELDS and key not in ("supersedes", "superseded_by"):
                raise MalformedADR(f"{path}: {key!r} is not a list field but has list items")
            fm.setdefault(key, []).append(line[4:].strip())
            continue
        k, _, v = line.partition(":")
        key = k.strip()
        v = v.strip()
        fm[key] = v if v else ([] if key in LIST_FIELDS else "")
    return fm, body


def _validate(fm, path):
    # List fields are checked separately below, with a message about what their absence costs -- a generic
    # "this field is empty" for `alternatives` buries the actual point.
    missing = [f for f in FIELDS if f not in LIST_FIELDS and not fm.get(f)]
    if missing:
        raise MalformedADR(
            f"{path}: CLAUDE.md §53 requires every field and these are empty -- {', '.join(missing)}.")
    for f in LIST_FIELDS:
        if not isinstance(fm.get(f), list) or not fm[f]:
            why = ("a decision with no alternatives considered was not a decision, it was a default"
                   if f == "alternatives" else
                   "the rejected alternatives are the half that costs the most -- they are what stops the "
                   "same alternative being re-proposed and re-rejected (§53's last sentence)")
            raise MalformedADR(f"{path}: {f!r} must be a non-empty list -- {why}")
    if fm.get("status") not in STATUSES:
        raise MalformedADR(f"{path}: `status` must be one of {list(STATUSES)}")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(fm.get("date") or "")):
        raise MalformedADR(f"{path}: `date` must be YYYY-MM-DD")
    if not str(fm.get("title") or "").strip():
        raise MalformedADR(f"{path}: no `title`")
    return fm


def read(path):
    fm, body = _parse(open(path, encoding="utf-8").read(), path)
    fm = _validate(fm, path)
    fm["_path"] = repo_rel(path, ROOT)
    fm["_body"] = body
    fm["id"] = os.path.basename(path).split("-", 1)[0]
    return fm


def all_records(directory=None):
    d = directory or DIR
    if not os.path.isdir(d):
        return []
    out = []
    for f in sorted(os.listdir(d)):
        if f.endswith(".md") and f != "README.md":
            out.append(read(os.path.join(d, f)))
    out.sort(key=lambda r: (r["date"], r["id"]), reverse=True)
    return out


def rejected_alternatives(directory=None):
    """Every alternative anyone has rejected, with the ADR that rejected it.

    This is the index §53's last sentence needs. Without it, "was this already considered?" is answerable only
    by reading every decision -- which is the same as not being answerable.
    """
    out = []
    for rec in all_records(directory):
        for alt in rec["rejected_alternatives"]:
            out.append({"alternative": alt, "adr": rec["id"], "title": rec["title"],
                        "date": rec["date"], "status": rec["status"], "path": rec["_path"]})
    return out


def check_reopening(proposal, *, directory=None, new_evidence=None):
    """Has this already been rejected? Raises unless the caller brings new evidence.

    §53: "do not repeatedly reopen it unless new evidence appears." The `new_evidence` argument is the
    mechanism: reopening is allowed, and it is allowed *with a reason on the record*. A boolean flag would let
    anyone re-litigate by passing True, so it takes the evidence itself.
    """
    words = {w for w in re.findall(r"[a-z0-9]+", proposal.lower()) if len(w) > 3}
    hits = []
    for r in rejected_alternatives(directory):
        alt_words = {w for w in re.findall(r"[a-z0-9]+", r["alternative"].lower()) if len(w) > 3}
        if alt_words and len(words & alt_words) >= max(2, len(alt_words) // 3):
            hits.append(r)
    if hits and not new_evidence:
        h = hits[0]
        raise AlreadyRejected(
            f"{proposal!r} was already rejected by ADR {h['adr']} ({h['title']}, {h['date']}): "
            f"{h['alternative']}. CLAUDE.md §53: do not repeatedly reopen a rejected alternative unless new "
            f"evidence appears -- pass that evidence as `new_evidence` and it goes on the record with the "
            f"reopening.")
    return {"already_rejected": hits, "reopening_permitted": bool(new_evidence),
            "new_evidence": new_evidence}


def index(directory=None):
    """The chronological log §53 asks for, as markdown. Generated -- never hand-maintained."""
    recs = all_records(directory)
    lines = ["# Architecture Decision Log", "",
             "_Generated by `scripts/adr.py index` from `docs/adr/*.md` — do not edit; edit the ADR._", "",
             f"CLAUDE.md §53. {len(recs)} decision(s). Each records context, problem, decision, alternatives, "
             f"chosen approach, reason, consequences and rejected alternatives.", "",
             "| # | Date | Decision | Status | Rejected |", "|---|---|---|---|---|"]
    for r in recs:
        lines.append(f"| [{r['id']}]({os.path.basename(r['_path'])}) | {r['date']} | {r['title']} | "
                     f"{r['status']} | {len(r['rejected_alternatives'])} |")
    rej = rejected_alternatives(directory)
    lines += ["", "## Rejected alternatives", "",
              "_§53: “When an alternative has been rejected, do not repeatedly reopen it unless new evidence "
              "appears.” This is the index that makes that checkable — `scripts/adr.py` `check_reopening()` "
              "reads it._", "", "| Alternative | Rejected by | Date |", "|---|---|---|"]
    for r in rej:
        lines.append(f"| {r['alternative']} | [{r['adr']}]({os.path.basename(r['path'])}) {r['title']} "
                     f"| {r['date']} |")
    return "\n".join(lines) + "\n"


def describe(directory=None):
    recs = all_records(directory)
    rej = rejected_alternatives(directory)
    return (f"§53 ADR log: {len(recs)} decision(s), {len(rej)} rejected alternative(s) indexed; "
            f"{sum(1 for r in recs if r['status'] == 'SUPERSEDED')} superseded")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="CLAUDE.md §53 Architecture Decision Log.")
    ap.add_argument("cmd", nargs="?", default="list", choices=["list", "index", "rejected", "check"])
    ap.add_argument("--out", default=os.path.join(DIR, "README.md"))
    ap.add_argument("--proposal", default=None)
    a = ap.parse_args()
    if a.cmd == "index":
        os.makedirs(DIR, exist_ok=True)
        open(a.out, "w", encoding="utf-8").write(index())
        print(f"-> {repo_rel(a.out, ROOT)}")
    elif a.cmd == "rejected":
        for r in rejected_alternatives():
            print(f"  [{r['adr']}] {r['alternative']}")
    elif a.cmd == "check":
        print(check_reopening(a.proposal or ""))
    else:
        print(describe())
        for r in all_records():
            print(f"  {r['id']}  {r['date']}  {r['status']:<10} {r['title']}")
