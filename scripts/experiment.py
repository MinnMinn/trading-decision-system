"""CLAUDE.md §42 -- THE reader and writer for the experiment store declared in docs/architecture/experiments.json.

§42 asks for a ten-stage lifecycle, twenty-two recorded fields per experiment, and one sentence with teeth:

    "Experiment records must be immutable."

Nothing in this repo recorded an experiment at all. Backtests were run by hand, their parameters lived in a
shell history, and the only trace that a candidate had ever been evaluated was a markdown file somebody
remembered to write. §43 (experiment budget) and §44 (OOS exposure) are both impossible on top of that,
because both need to count what was tried.

    import experiment as X

    rec = X.Record(hypothesis="...", motivation="...", parent_trading_system_version="v1",
                   candidate_version="v1.1")
    rec.set("dataset_snapshot", snap).set("metrics", perf).set("random_seed", 20260918)
    sealed = rec.seal()                     # refuses while a field is neither set nor explicitly unavailable
    X.write(sealed)                         # refuses to overwrite an existing id

    X.load(eid)["hypothesis"]               # a MappingProxyType: mutating it raises

Three properties, each closing a way an experiment record stops being evidence:

1. **Completeness is checked at seal time, not at read time.** Every one of §42's twenty-two fields must be
   set or explicitly marked `unavailable(reason)`. A record missing `random_seed` is not "mostly recorded" --
   it is a result nobody can reproduce (§46), and it should be impossible to file.
2. **Immutable three ways.** The sealed mapping raises on mutation; `write()` refuses a path that exists; and
   the record carries a content hash that `load()` re-checks. A convention would catch none of these; the
   point is not that nobody would edit a record, it is that an edited one must be DETECTABLE.
3. **A decision is a successor record, not an edit.** `decide()` seals a NEW record naming its predecessor.
   The experiment as run, and the judgement passed on it, are two facts with two timestamps -- and the first
   one stays exactly as it was when the evidence was complete.
"""
import copy
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

PATH = os.path.join(ROOT, "docs", "architecture", "experiments.json")
STORE = os.path.join(ROOT, "docs", "experiments")

PENDING = "PENDING"


class RegistryError(ValueError):
    """The §42 registry itself is wrong -- raised at import."""


class NotDeclared(KeyError):
    """Something used a field or lifecycle stage CLAUDE.md §42 does not name."""


class Incomplete(ValueError):
    """A record tried to seal without every §42 field accounted for."""


class Immutable(RuntimeError):
    """Something tried to change a sealed experiment record."""


class Tampered(RuntimeError):
    """A stored record's content does not match the hash it was sealed with."""


def _load(path=None):
    path = path or PATH
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    fields = data.get("fields")
    if not isinstance(fields, list) or not fields:
        raise RegistryError(f"{path}: `fields` must be a non-empty list")
    seen = set()
    for f in fields:
        for k in ("id", "spec_name", "kind", "definition"):
            if not str(f.get(k) or "").strip():
                raise RegistryError(f"{path}: field {f.get('id')!r} has no {k!r}")
        if f["id"] in seen:
            raise RegistryError(f"{path}: duplicate field id {f['id']!r}")
        seen.add(f["id"])
    stages = data.get("lifecycle") or []
    for i, s in enumerate(stages, start=1):
        if s.get("n") != i:
            raise RegistryError(f"{path}: lifecycle stage {s.get('id')!r} is at position {i} but declares "
                                f"n={s.get('n')}; §42's lifecycle IS the order")
        if not str(s.get("stage_of_41") or "").strip():
            raise RegistryError(
                f"{path}: lifecycle stage {s['id']!r} does not say which §41 pipeline stage it corresponds "
                f"to. Without that mapping the two lists drift into describing different processes.")
    if PENDING not in (data.get("decisions") or ()):
        raise RegistryError(f"{path}: `decisions` must include {PENDING!r} -- the honest value of the decision "
                            f"field before a human has decided")
    return data, {f["id"]: f for f in fields}, tuple(f["id"] for f in fields), tuple(stages)


_DATA, FIELDS, ORDER, LIFECYCLE = _load()
STAGE_ORDER = tuple(s["id"] for s in LIFECYCLE)
DECISIONS = tuple(_DATA["decisions"])


def field(fid):
    f = FIELDS.get(fid)
    if f is None:
        raise NotDeclared(f"no §42 field {fid!r}; the twenty-two are {list(ORDER)}")
    return f


def spec_name(fid):
    return field(fid)["spec_name"]


def unavailable(reason):
    """The value of a §42 field that genuinely does not apply or could not be captured.

    Explicit, and required to say why. A field left absent and a field that could not be captured are
    different facts, and only one of them is a defect -- but a missing key cannot tell them apart.
    """
    if not str(reason or "").strip():
        raise ValueError("an unavailable §42 field must say why; 'not applicable' with no reason is how a "
                         "missing snapshot becomes a footnote")
    return {"unavailable": reason}


def is_unavailable(v):
    return isinstance(v, dict) and "unavailable" in v


def code_version():
    """The git commit this ran at, and whether the tree was dirty.

    A dirty tree means the commit does NOT identify the code, and §46 makes that the difference between a
    reproducible result and a plausible one -- so it is recorded rather than rounded off.
    """
    def _git(*a):
        try:
            return subprocess.run(["git", "-C", ROOT, *a], capture_output=True, text=True,
                                  timeout=20).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""
    sha = _git("rev-parse", "HEAD")
    if not sha:
        return unavailable("not a git checkout, or git is unavailable here")
    dirty = bool(_git("status", "--porcelain"))
    return {"commit": sha, "dirty": dirty,
            "_note": ("the working tree had uncommitted changes, so this commit does NOT identify the code "
                      "this experiment ran (§46)") if dirty else None}


def _slug(text, n=40):
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return s[:n] or "experiment"


def _digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                     default=str).encode("utf-8")).hexdigest()


class Record:
    """One §42 experiment, under construction. Becomes immutable at `seal()`."""

    def __init__(self, *, hypothesis, motivation, parent_trading_system_version, candidate_version,
                 experiment_id=None, at=None):
        self._v = {}
        now = at or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.set("timestamp", now)
        self.set("hypothesis", hypothesis)
        self.set("motivation", motivation)
        self.set("parent_trading_system_version", parent_trading_system_version)
        self.set("candidate_version", candidate_version)
        self.set("experiment_id", experiment_id or f"{now[:10]}-{_slug(hypothesis)}")
        self.set("code_version", code_version())
        self.set("decision", {"decision": PENDING, "by": None})

    def set(self, fid, value):
        f = field(fid)
        if value is None:
            raise ValueError(f"§42 field {fid!r} ({f['spec_name']}) cannot be None -- use "
                             f"experiment.unavailable(reason) so the absence carries its reason")
        if isinstance(value, str) and not value.strip():
            raise ValueError(f"§42 field {fid!r} ({f['spec_name']}) cannot be blank")
        self._v[fid] = value
        return self

    def missing(self):
        return tuple(f for f in ORDER if f not in self._v)

    def seal(self):
        """Freeze this record. Refuses while any §42 field is neither set nor explicitly unavailable.

        Completeness is checked HERE rather than when somebody reads the record, because a record missing its
        seed or its dataset snapshot is not partially filed -- it is a result nobody can reproduce, and it
        should be impossible to file at all.
        """
        miss = self.missing()
        if miss:
            raise Incomplete(
                f"cannot seal experiment {self._v.get('experiment_id')!r}: CLAUDE.md §42 requires every field "
                f"and these are unaccounted for -- {', '.join(spec_name(m) for m in miss)}. Set each, or mark "
                f"it experiment.unavailable(reason).")
        payload = {k: copy.deepcopy(self._v[k]) for k in ORDER}
        payload["_source"] = "docs/architecture/experiments.json (CLAUDE.md §42)"
        payload["content_sha256"] = _digest({k: payload[k] for k in ORDER})
        return types.MappingProxyType(payload)


def path_of(eid):
    return os.path.join(STORE, f"{eid}.json")


def write(sealed, *, store=None):
    """Append one sealed record to the store. Refuses to overwrite.

    §42: 'Experiment records must be immutable.' An overwrite is the most ordinary way an immutable record
    stops being one, so the writer refuses rather than trusting the caller to have chosen a fresh id.
    """
    if not isinstance(sealed, types.MappingProxyType):
        raise Immutable("write() takes a SEALED record (experiment.Record.seal()); an ordinary dict is still "
                        "mutable and would be written as though it were evidence")
    d = store or STORE
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{sealed['experiment_id']}.json")
    if os.path.exists(p):
        raise Immutable(f"{os.path.relpath(p, ROOT)} already exists. A §42 record is immutable: file a "
                        f"successor that names this one as its predecessor rather than replacing it.")
    with open(p, "x", encoding="utf-8") as fh:            # "x": the filesystem enforces it too
        json.dump(dict(sealed), fh, ensure_ascii=False, indent=1, default=str)
    return p


def load(eid, *, store=None):
    """Read one record back, re-checking the hash it was sealed with.

    The hash is what makes the immutability claim checkable rather than merely stated: an edit through any
    route -- an editor, a script, a merge -- changes the content and not the stored digest.
    """
    p = os.path.join(store or STORE, f"{eid}.json")
    with open(p, encoding="utf-8") as fh:
        d = json.load(fh)
    want = d.get("content_sha256")
    got = _digest({k: d.get(k) for k in ORDER})
    if want != got:
        raise Tampered(f"{os.path.relpath(p, ROOT)} does not match the hash it was sealed with "
                       f"({want} != {got}). CLAUDE.md §42: experiment records are immutable, and this one has "
                       f"been changed since it was filed.")
    return types.MappingProxyType(d)


def decide(sealed, decision, *, actor, note=None, store=None, at=None):
    """Record a human decision as a SUCCESSOR record, never as an edit.

    The experiment as run and the judgement passed on it are two facts with two timestamps. Editing the first
    to carry the second destroys the only evidence of what was known at the time the evidence was complete.
    §41 owns who may decide; this function refuses anyone else for the same reason it does.
    """
    if decision not in DECISIONS or decision == PENDING:
        raise ValueError(f"{decision!r} is not a §42 decision; they are "
                         f"{[d for d in DECISIONS if d != PENDING]}")
    if str(actor).strip().lower() != "human":
        raise PermissionError(
            f"{actor!r} may not decide an experiment. CLAUDE.md §41: 'AI must NEVER silently rewrite the "
            f"production Trading System', and an approval recorded by a model is exactly that with a "
            f"paper trail attached.")
    now = at or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = Record(hypothesis=sealed["hypothesis"], motivation=sealed["motivation"],
               parent_trading_system_version=sealed["parent_trading_system_version"],
               candidate_version=sealed["candidate_version"],
               experiment_id=f"{sealed['experiment_id']}-decision", at=now)
    for f in ORDER:
        if f not in ("experiment_id", "timestamp", "decision", "code_version"):
            r.set(f, sealed[f])
    r.set("decision", {"decision": decision, "by": actor, "note": note, "at": now,
                       "predecessor": sealed["experiment_id"],
                       "predecessor_sha256": sealed["content_sha256"]})
    out = r.seal()
    write(out, store=store)
    return out


def all_records(store=None):
    d = store or STORE
    if not os.path.isdir(d):
        return []
    out = []
    for f in sorted(os.listdir(d)):
        if f.endswith(".json"):
            try:
                out.append(load(f[:-5], store=d))
            except (Tampered, ValueError, OSError):
                continue
    return out


def describe(sealed):
    dec = sealed["decision"]
    un = [f for f in ORDER if is_unavailable(sealed[f])]
    line = (f"{sealed['experiment_id']} · {sealed['parent_trading_system_version']} -> "
            f"{sealed['candidate_version']} · {dec.get('decision')}")
    if un:
        line += f" · unavailable: {', '.join(spec_name(f) for f in un)}"
    return line


if __name__ == "__main__":
    print(f"CLAUDE.md §42 -- {len(ORDER)} required fields, {len(LIFECYCLE)} lifecycle stages\n")
    for s in LIFECYCLE:
        print(f"{s['n']:>2}. {s['spec_name']:<22} (§41: {s['stage_of_41']})")
    print()
    for fid in ORDER:
        print(f"  {fid:<32} {FIELDS[fid]['kind']}")
    recs = all_records()
    print(f"\nstore: {len(recs)} record(s) under {os.path.relpath(STORE, ROOT)}")
    for r in recs:
        print("  " + describe(r))
