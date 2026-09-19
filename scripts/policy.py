"""CLAUDE.md §56-§62 -- THE reader for docs/architecture/policy.json, and the self-review as a command.

These seven sections read as process advice, and the compliance ledger recorded six of them as **POLICY** --
its word for "true by intention". Intentions are not checkable. Four of them turn out to be:

* **§56** phases: a later phase's artifact existing without the earlier phase's is the exact thing
  "do not implement future phases speculatively during earlier phases" forbids, and it is a file check.
* **§57** names nine speculative things by name. Whether any of them is in the tree is a scan.
* **§58**'s `Avoid` list: five of its nine are already pinned by a test somewhere -- nobody had collected them,
  so nobody could tell which four are conventions rather than invariants. Saying which is the point;
  "meaningful names" has no test and pretending otherwise would make the other five worth less.
* **§60** is thirty-five questions whose answers the suite already knows.

The last one is why this module exists:

    python3 scripts/policy.py --review

§60 says "before declaring work complete, review:" and then asks *is PIT preserved?*, *can required analysis
accidentally be bypassed?*, *can AI modify production silently?* Every one of those has a test. Collecting
them turns the self-review from a promise into a command whose output is a list of resolved citations -- and a
citation that stops resolving fails here, rather than being discovered during whatever incident it was written
to prevent.

Each item declares the answer §60 requires AND the test that produces it, because the answer on its own would
just be a second claim. Citations may name a test directly, or reference a §54 invariant by name -- those
resolve through `docs/architecture/test-coverage.json`, so the repository keeps one citation list, not two.
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "docs", "architecture", "policy.json")
COVERAGE = os.path.join(ROOT, "docs", "architecture", "test-coverage.json")


class RegistryError(ValueError):
    """docs/architecture/policy.json says something CLAUDE.md §56-§62 does not allow."""


def _load(path=None):
    data = json.load(open(path or PATH, encoding="utf-8"))
    for item in data["self_review"]:
        if item["must_be"] not in ("YES", "NO"):
            raise RegistryError(f"{item['question']!r}: `must_be` is YES or NO")
        if not str(item.get("answered_by") or "").strip():
            raise RegistryError(
                f"{item['question']!r} has no `answered_by` -- CLAUDE.md §60 is a review to RUN, and an item "
                f"with an answer and no test is the self-assessment this registry exists to replace.")
    prev = None
    for row in data["phases"]:
        n = int(row["phase"].split()[1])
        if prev is not None and n != prev + 1:
            raise RegistryError("phases must be consecutive")
        prev = n
    for row in data["not_speculative"]:
        if not row.get("markers") and not row.get("_why"):
            raise RegistryError(
                f"{row['thing']!r}: a §57 item that is neither scanned for nor explained is an unexamined "
                f"claim that the repository does not contain it.")
    ch = data["change_safety"]
    for rec in ch["recorded_changes"]:
        if not str(rec.get("invalidates") or "").strip():
            raise RegistryError(
                f"{rec['what']!r} does not say what it invalidates -- CLAUDE.md §59's sentence is about the "
                f"word SILENTLY, and a recorded semantics change with no consequence recorded is still silent.")
    return data


_DATA = _load()

PHASES = tuple(r["phase"] for r in _DATA["phases"])
SELF_REVIEW = tuple(_DATA["self_review"])
REPORT_ITEMS = tuple(_DATA["final_report"])
SPECULATIVE = tuple(r["thing"] for r in _DATA["not_speculative"])


def phase(name):
    for r in _DATA["phases"]:
        if r["phase"] == name:
            return r
    raise KeyError(name)


def coding_rules():
    return _DATA["coding_rules"]


def change_safety():
    return _DATA["change_safety"]


def non_negotiable():
    return _DATA["non_negotiable"]


def _coverage_citation(invariant):
    data = json.load(open(COVERAGE, encoding="utf-8"))
    for row in data["invariants"]:
        if row["spec_name"] == invariant:
            return row.get("by")
    return None


def resolve(answered_by):
    """`path::test_function`, or None plus the reason it does not resolve.

    An `invariant:<name>` reference is looked up in the §54 registry, so a question answered by an invariant
    the suite already proves does not need a second citation to keep in step.
    """
    citation = answered_by
    if answered_by.startswith("invariant:"):
        citation = _coverage_citation(answered_by.split(":", 1)[1])
        if not citation:
            return None, f"{answered_by!r} names no §54 invariant"
    if "::" not in str(citation):
        return None, f"{citation!r} is not path::test_function"
    path, fn = citation.split("::", 1)
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        return None, f"{path} does not exist"
    if not re.search(rf"^\s+def {re.escape(fn)}\(", open(full, encoding="utf-8").read(), re.M):
        return None, f"{path} has no test named {fn}"
    return citation, None


def review():
    """§60, as rows. Each carries the answer the spec requires and the test that produces it."""
    out = []
    for item in SELF_REVIEW:
        citation, why = resolve(item["answered_by"])
        out.append({**item, "citation": citation, "unresolved": why})
    return out


#: Directories the §57 scan does not walk. `data/` is market data, `knowledge/` is ingested methodology
#: literature, `mock/` is fixtures -- none of them is code that could introduce a dependency.
SCAN_SKIP = {".git", "node_modules", "data", "knowledge", "mock", "__pycache__", ".playwright-mcp", ".goal"}
SCAN_EXT = (".py", ".sh", ".json", ".yml", ".yaml", ".mq5", ".js", ".toml", ".cfg", ".ini")

#: The three files that NAME the markers in order to look for them. Scanning them finds the search terms, not
#: a dependency -- the classic way a self-check reports itself.
SCAN_EXEMPT = {os.path.join("docs", "architecture", "policy.json"),
               os.path.join("scripts", "policy.py"),
               os.path.join("scripts", "tests", "test_policy.py")}


def speculative_findings(root=None):
    """§57: anything in the tree matching a marker for one of the nine speculative things.

    Empty is the claim §57 makes about a repository that has kept phase discipline, and this is what turns
    that claim into a check. A hit is not automatically a violation -- it is a thing to look at.
    """
    root = root or ROOT
    out = []
    files = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [x for x in dn if x not in SCAN_SKIP and not x.startswith(".")]
        for f in fn:
            if f.endswith(SCAN_EXT):
                rel = os.path.relpath(os.path.join(dp, f), root)
                if rel not in SCAN_EXEMPT:
                    files.append((rel, os.path.join(dp, f)))
    for row in _DATA["not_speculative"]:
        for m in row.get("markers") or []:
            for rel, full in files:
                if m.lower() in os.path.basename(rel).lower():
                    out.append((row["thing"], m, rel))
                    continue
                try:
                    src = open(full, encoding="utf-8", errors="ignore").read()
                except OSError:
                    continue
                if re.search(rf"\b{re.escape(m)}\b", src):
                    out.append((row["thing"], m, rel))
    return out


def missing_artifacts():
    """§56: a declared phase artifact that is not on disk. Empty is the answer the phases claim."""
    out = []
    for row in _DATA["phases"]:
        for a in row["artifacts"]:
            if not os.path.exists(os.path.join(ROOT, a)):
                out.append((row["phase"], a))
    return out


def describe():
    rows = review()
    bad = [r for r in rows if r["unresolved"]]
    lines = [f"§56-§62 policy: {len(PHASES)} phases, {len(SELF_REVIEW)} self-review questions, "
             f"{len(REPORT_ITEMS)} final-report items.",
             f"  §60 self-review: {len(rows) - len(bad)}/{len(rows)} questions resolve to a real test."]
    for r in bad:
        lines.append(f"  UNRESOLVED  {r['question']}  -- {r['unresolved']}")
    miss = missing_artifacts()
    lines.append(f"  §56 artifacts: {'all present' if not miss else miss}")
    spec = speculative_findings()
    lines.append(f"  §57 speculative: {'none found' if not spec else spec}")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="CLAUDE.md §56-§62 policy sections.")
    ap.add_argument("--review", action="store_true", help="print §60's self-review with its citations")
    a = ap.parse_args()
    if a.review:
        group = None
        for r in review():
            if r["group"] != group:
                group = r["group"]
                print(f"\n{group}")
            mark = "  " if not r["unresolved"] else "!!"
            print(f"{mark} [{r['must_be']:<3}] {r['question']}")
            print(f"        {r['citation'] or r['unresolved']}")
    else:
        print(describe())
