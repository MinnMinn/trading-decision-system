"""BMREC-01..05 + BMREC-31: allowlist bytecode check over the FINAL add-on jar (never the source tree).

    python allowlist_check.py <jar> [--allowlist <json>] [--dump]

Exit 0 = PASS, 1 = FAIL (violations printed, one per line, each tagged with the BMREC rule it breaks),
2 = usage / unreadable input. Standard library only (BMREC-32).

What it enforces (docs/security/2026-09-26-bookmap-recorder-h1.md §5.1):
- Every type the jar mentions (class constants, and every `L...;` inside any descriptor, signature or annotation
  string) is either in the project package or on the committed allowlist. velox types -> BMREC-01, JDK -> BMREC-03.
- Every field/method reference to a non-project owner is on the member allowlist (owner, name, descriptor). This is
  an ALLOWLIST: sendOrder/updateOrder/login/sendUserMessage/close/registerIndicator* on any owner fail because they
  are not listed, not because a denylist names them.
- BMREC-02: exactly one Api.getProvider call, in the allowlisted class/method; its result goes only into one local
  slot whose every load is immediately the receiver of add/removeListener(Layer1ApiAdminListener); no field,
  declared method descriptor, checkcast or instanceof mentions a provider type.
- BMREC-03: no native method; invokedynamic only with LambdaMetafactory.metafactory / StringConcatFactory
  .makeConcatWithConstants; no ldc of MethodHandle/MethodType/Dynamic constants; exactly one FileOutputStream
  construction, in the allowlisted class/method, whose path argument is an ldc string constant beginning with
  \\\\.\\pipe\\ .
- BMREC-05: the pipe stream's allowed members contain no read method (FileOutputStream has none; FileInputStream
  and RandomAccessFile are not allowlisted types).
- BMREC-31: the jar holds only META-INF/MANIFEST.MF and classes under the project package.
"""
import io
import json
import os
import re
import struct
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ALLOWLIST = os.path.join(os.path.dirname(HERE), "allowlist.json")

TYPE_RE = re.compile(r"L([A-Za-z_$][A-Za-z0-9_$]*(?:/[A-Za-z0-9_$]+)*);")


class ClassFormatError(ValueError):
    pass


# ---------------------------------------------------------------- class-file parsing


class ClassFile:
    def __init__(self, data, name):
        self.name = name
        self.r = io.BytesIO(data)
        self.cp = [None]
        self._parse()

    def u1(self):
        b = self.r.read(1)
        if len(b) != 1:
            raise ClassFormatError(f"{self.name}: truncated")
        return b[0]

    def u2(self):
        b = self.r.read(2)
        if len(b) != 2:
            raise ClassFormatError(f"{self.name}: truncated")
        return struct.unpack(">H", b)[0]

    def u4(self):
        b = self.r.read(4)
        if len(b) != 4:
            raise ClassFormatError(f"{self.name}: truncated")
        return struct.unpack(">I", b)[0]

    def bytes_(self, n):
        b = self.r.read(n)
        if len(b) != n:
            raise ClassFormatError(f"{self.name}: truncated")
        return b

    def _parse(self):
        if self.u4() != 0xCAFEBABE:
            raise ClassFormatError(f"{self.name}: bad magic")
        self.minor, self.major = self.u2(), self.u2()
        n = self.u2()
        i = 1
        while i < n:
            tag = self.u1()
            if tag == 1:
                ln = self.u2()
                self.cp.append(("Utf8", self.bytes_(ln).decode("utf-8", "surrogatepass")))
            elif tag in (3, 4):
                self.cp.append(("Num", self.bytes_(4)))
            elif tag in (5, 6):
                self.cp.append(("Num", self.bytes_(8)))
                self.cp.append(None)
                i += 1
            elif tag == 7:
                self.cp.append(("Class", self.u2()))
            elif tag == 8:
                self.cp.append(("String", self.u2()))
            elif tag in (9, 10, 11):
                kind = {9: "Fieldref", 10: "Methodref", 11: "InterfaceMethodref"}[tag]
                self.cp.append((kind, self.u2(), self.u2()))
            elif tag == 12:
                self.cp.append(("NameAndType", self.u2(), self.u2()))
            elif tag == 15:
                self.cp.append(("MethodHandle", self.u1(), self.u2()))
            elif tag == 16:
                self.cp.append(("MethodType", self.u2()))
            elif tag == 17:
                self.cp.append(("Dynamic", self.u2(), self.u2()))
            elif tag == 18:
                self.cp.append(("InvokeDynamic", self.u2(), self.u2()))
            elif tag in (19, 20):
                self.cp.append(("ModPkg", self.u2()))
            else:
                raise ClassFormatError(f"{self.name}: unknown constant tag {tag}")
            i += 1
        self.access = self.u2()
        self.this_class = self.class_name(self.u2())
        sup = self.u2()
        self.super_class = self.class_name(sup) if sup else None
        self.interfaces = [self.class_name(self.u2()) for _ in range(self.u2())]
        self.fields = [self._member() for _ in range(self.u2())]
        self.methods = [self._member() for _ in range(self.u2())]
        self.attributes = self._attrs()

    def _member(self):
        acc, name, desc = self.u2(), self.utf8(self.u2()), self.utf8(self.u2())
        return {"access": acc, "name": name, "desc": desc, "attrs": self._attrs()}

    def _attrs(self):
        out = {}
        for _ in range(self.u2()):
            name = self.utf8(self.u2())
            out.setdefault(name, []).append(self.bytes_(self.u4()))
        return out

    def utf8(self, idx):
        e = self.cp[idx]
        if not e or e[0] != "Utf8":
            raise ClassFormatError(f"{self.name}: cp#{idx} is not Utf8")
        return e[1]

    def class_name(self, idx):
        e = self.cp[idx]
        if not e or e[0] != "Class":
            raise ClassFormatError(f"{self.name}: cp#{idx} is not Class")
        return self.utf8(e[1])

    def member_ref(self, idx):
        e = self.cp[idx]
        if not e or e[0] not in ("Fieldref", "Methodref", "InterfaceMethodref"):
            raise ClassFormatError(f"{self.name}: cp#{idx} is not a member ref")
        nat = self.cp[e[2]]
        return e[0], self.class_name(e[1]), self.utf8(nat[1]), self.utf8(nat[2])

    def bootstrap_methods(self):
        out = []
        for raw in self.attributes.get("BootstrapMethods", []):
            r = io.BytesIO(raw)
            (n,) = struct.unpack(">H", r.read(2))
            for _ in range(n):
                ref, nargs = struct.unpack(">HH", r.read(4))
                args = struct.unpack(">" + "H" * nargs, r.read(2 * nargs)) if nargs else ()
                out.append((ref, args))
        return out


def instructions(code):
    """Yield (pc, opcode, operand_bytes) over one Code attribute's bytecode."""
    pc = 0
    n = len(code)
    while pc < n:
        op = code[pc]
        if op == 0xAA:  # tableswitch
            p = pc + 1 + ((3 - (pc % 4)) % 4)
            low, high = struct.unpack(">ii", code[p + 4:p + 12])
            ln = (p - pc) + 12 + 4 * (high - low + 1)
        elif op == 0xAB:  # lookupswitch
            p = pc + 1 + ((3 - (pc % 4)) % 4)
            (npairs,) = struct.unpack(">i", code[p + 4:p + 8])
            ln = (p - pc) + 8 + 8 * npairs
        elif op == 0xC4:  # wide
            ln = 6 if code[pc + 1] == 0x84 else 4
        else:
            ln = OPLEN.get(op)
            if ln is None:
                raise ClassFormatError(f"unknown opcode 0x{op:02x} at pc {pc}")
        yield pc, op, code[pc + 1:pc + ln]
        pc += ln


OPLEN = {}
for _op in range(0x00, 0x10):
    OPLEN[_op] = 1
OPLEN.update({0x10: 2, 0x11: 3, 0x12: 2, 0x13: 3, 0x14: 3})
for _op in range(0x15, 0x1A):
    OPLEN[_op] = 2
for _op in range(0x1A, 0x36):
    OPLEN[_op] = 1
for _op in range(0x36, 0x3B):
    OPLEN[_op] = 2
for _op in range(0x3B, 0x84):
    OPLEN[_op] = 1
OPLEN[0x84] = 3
for _op in range(0x85, 0x99):
    OPLEN[_op] = 1
for _op in range(0x99, 0xA9):
    OPLEN[_op] = 3
OPLEN[0xA9] = 2
for _op in range(0xAC, 0xB2):
    OPLEN[_op] = 1
for _op in range(0xB2, 0xB9):
    OPLEN[_op] = 3
OPLEN.update({0xB9: 5, 0xBA: 5, 0xBB: 3, 0xBC: 2, 0xBD: 3, 0xBE: 1, 0xBF: 1, 0xC0: 3, 0xC1: 3, 0xC2: 1,
              0xC3: 1, 0xC5: 4, 0xC6: 3, 0xC7: 3, 0xC8: 5, 0xC9: 5})

INVOKES = (0xB6, 0xB7, 0xB8, 0xB9)
FIELD_OPS = (0xB2, 0xB3, 0xB4, 0xB5)
ALOAD_N = {0x2A: 0, 0x2B: 1, 0x2C: 2, 0x2D: 3}
ASTORE_N = {0x4B: 0, 0x4C: 1, 0x4D: 2, 0x4E: 3}
REF_PUSH_SIMPLE = set(ALOAD_N) | {0x19, 0xB2, 0xB4, 0x01}  # aload_n, aload, getstatic, getfield, aconst_null


def _u2(b, o=0):
    return struct.unpack(">H", b[o:o + 2])[0]


def local_index(op, operand):
    if op in ALOAD_N:
        return ALOAD_N[op]
    if op in ASTORE_N:
        return ASTORE_N[op]
    if op in (0x19, 0x3A):
        return operand[0]
    return None


# ---------------------------------------------------------------- the check


def load_allowlist(path):
    with open(path, encoding="utf-8") as fh:
        a = json.load(fh)
    a["_types"] = set(a["allowed_types"])
    a["_members"] = {(m["owner"], m["name"], m["desc"]) for m in a["allowed_members"]}
    return a


def check_jar(jar_path, allowlist):
    """Return (violations, facts). violations: list of (rule, message)."""
    v = []
    facts = {"classes": 0, "getprovider_sites": [], "pipe_sites": [], "external_members": set(),
             "external_types": set()}
    pkg = allowlist["project_package"].rstrip("/") + "/"
    try:
        zf = zipfile.ZipFile(jar_path)
    except (OSError, zipfile.BadZipFile) as e:
        return [("BMREC-04", f"cannot open jar: {e}")], facts
    with zf:
        classes = []
        for info in zf.infolist():
            n = info.filename
            if n in ("META-INF/", "META-INF/MANIFEST.MF"):
                continue
            if n.endswith("/") and pkg.startswith(n):
                continue  # directory entries on the way to the package
            if not (n.startswith(pkg) and n.endswith(".class")):
                v.append(("BMREC-31", f"jar entry outside the project package: {n}"))
                continue
            try:
                classes.append(ClassFile(zf.read(n), n))
            except (ClassFormatError, struct.error, IndexError) as e:
                v.append(("BMREC-04", f"unparseable class {n}: {e}"))
    facts["classes"] = len(classes)
    if not classes:
        v.append(("BMREC-04", "jar contains no project classes"))
    for cf in classes:
        _check_class(cf, allowlist, pkg, v, facts)
    gp = facts["getprovider_sites"]
    want = allowlist["getprovider_site"]
    if len(gp) != 1:
        v.append(("BMREC-02", f"Api.getProvider must be invoked at exactly one site; found {len(gp)}: {gp}"))
    elif (gp[0][0], gp[0][1]) != (want["class"], want["method"]):
        v.append(("BMREC-02", f"getProvider site {gp[0][:2]} is not the audited {want['class']}.{want['method']}"))
    ps = facts["pipe_sites"]
    pw = allowlist["pipe_site"]
    if len(ps) != 1:
        v.append(("BMREC-03", f"exactly one FileOutputStream construction is allowed; found {len(ps)}: {ps}"))
    elif (ps[0][0], ps[0][1]) != (pw["class"], pw["method"]):
        v.append(("BMREC-03", f"pipe-open site {ps[0][:2]} is not the audited {pw['class']}.{pw['method']}"))
    return v, facts


def _rule_for(owner):
    return "BMREC-01" if owner.startswith("velox/") else "BMREC-03"


def _is_project(t, pkg):
    return t.startswith(pkg)


def _check_class(cf, a, pkg, v, facts):
    types, members = a["_types"], a["_members"]
    provider_types = set(a["provider_types"])
    here = cf.this_class
    # --- types: every Class constant and every L...; in any Utf8 (descriptors, signatures, annotations)
    seen = set()
    for e in cf.cp:
        if e and e[0] == "Class":
            name = cf.utf8(e[1])
            while name.startswith("["):
                name = name[1:]
            if name.startswith("L") and name.endswith(";"):
                name = name[1:-1]
            if len(name) == 1 and name in "BCDFIJSZV":
                continue
            seen.add(name)
        elif e and e[0] == "Utf8":
            for m in TYPE_RE.finditer(e[1]):
                seen.add(m.group(1))
        elif e and e[0] == "Dynamic":
            v.append(("BMREC-03", f"{here}: CONSTANT_Dynamic (condy) is not allowed"))
    for t in sorted(seen):
        if _is_project(t, pkg):
            continue
        facts["external_types"].add(t)
        if t not in types:
            v.append((_rule_for(t), f"{here}: type {t} is not on the allowlist"))
    # --- declared members must not carry provider types (BMREC-02: not stored, passed, returned)
    for f in cf.fields:
        for m in TYPE_RE.finditer(f["desc"] + " ".join(_sigs(cf, f))):
            if m.group(1) in provider_types:
                v.append(("BMREC-02", f"{here}.{f['name']}: field of provider type {m.group(1)}"))
    for meth in cf.methods:
        if meth["access"] & 0x0100:
            v.append(("BMREC-03", f"{here}.{meth['name']}{meth['desc']}: native method"))
        for m in TYPE_RE.finditer(meth["desc"] + " ".join(_sigs(cf, meth))):
            if m.group(1) in provider_types:
                v.append(("BMREC-02", f"{here}.{meth['name']}{meth['desc']}: method descriptor carries provider "
                                      f"type {m.group(1)} (passed or returned)"))
    # --- member refs
    for idx, e in enumerate(cf.cp):
        if e and e[0] in ("Fieldref", "Methodref", "InterfaceMethodref"):
            _, owner, name, desc = cf.member_ref(idx)
            owner_base = owner.lstrip("[")
            if owner_base.startswith("L"):
                owner_base = owner_base[1:-1]
            if _is_project(owner_base, pkg):
                continue
            if owner.startswith("["):
                if (("[", name, desc) in members):
                    continue
            facts["external_members"].add((owner, name, desc))
            if (owner, name, desc) not in members:
                v.append((_rule_for(owner_base), f"{here}: member {owner}.{name}{desc} is not on the allowlist"))
    # --- bootstrap methods (invokedynamic)
    allowed_bsm = {(b["owner"], b["name"]) for b in a["allowed_bootstraps"]}
    bsm_arg_idx = set()
    for ref, args in cf.bootstrap_methods():
        mh = cf.cp[ref]
        _, owner, name, _desc = cf.member_ref(mh[2])
        if (owner, name) not in allowed_bsm:
            v.append(("BMREC-03", f"{here}: invokedynamic bootstrap {owner}.{name} is not allowed"))
        bsm_arg_idx.update(args)
    # --- code
    for meth in cf.methods:
        for raw in meth["attrs"].get("Code", []):
            _check_code(cf, meth, raw, a, pkg, provider_types, bsm_arg_idx, v, facts)


def _sigs(cf, member):
    out = []
    for raw in member["attrs"].get("Signature", []):
        out.append(cf.utf8(_u2(raw)))
    return out


def _check_code(cf, meth, raw, a, pkg, provider_types, bsm_arg_idx, v, facts):
    here = f"{cf.this_class}.{meth['name']}{meth['desc']}"
    code_len = struct.unpack(">I", raw[4:8])[0]
    code = raw[8:8 + code_len]
    ins = list(instructions(code))
    gp_owner_names = {(g["owner"], g["name"], g["desc"]) for g in a["getprovider_refs"]}
    admin_calls = {(m["owner"], m["name"], m["desc"]) for m in a["provider_admin_calls"]}
    provider_slots = []
    for i, (pc, op, operand) in enumerate(ins):
        if op in (0x12, 0x13):
            idx = operand[0] if op == 0x12 else _u2(operand)
            e = cf.cp[idx]
            if e and e[0] in ("MethodHandle", "MethodType", "Dynamic"):
                v.append(("BMREC-03", f"{here}@{pc}: ldc of a {e[0]} constant"))
        if op in (0xC0, 0xC1):
            t = cf.class_name(_u2(operand))
            if t.lstrip("[L").startswith("velox/"):
                v.append(("BMREC-02", f"{here}@{pc}: {'checkcast' if op == 0xC0 else 'instanceof'} to velox type {t}"))
        if op == 0xBB and cf.class_name(_u2(operand)) == "java/io/FileOutputStream":
            pass  # counted at the <init> call below
        if op in INVOKES:
            kind, owner, name, desc = cf.member_ref(_u2(operand))
            if (owner, name, desc) in gp_owner_names or (owner.startswith("velox/") and name == "getProvider"):
                facts["getprovider_sites"].append((cf.this_class, meth["name"], pc))
                slot = _getprovider_result_slot(ins, i)
                if slot is None:
                    v.append(("BMREC-02", f"{here}@{pc}: getProvider() result must go straight into a local "
                                          f"variable (astore) and nowhere else"))
                else:
                    provider_slots.append((slot, pc))
            if owner == "java/io/FileOutputStream" and name == "<init>":
                facts["pipe_sites"].append((cf.this_class, meth["name"], pc))
                _check_pipe_site(cf, here, ins, i, desc, a, v)
    for slot, gp_pc in provider_slots:
        _check_provider_slot(cf, here, ins, slot, gp_pc, admin_calls, v)


def _getprovider_result_slot(ins, i):
    if i + 1 >= len(ins):
        return None
    _, op, operand = ins[i + 1]
    if op in ASTORE_N or op == 0x3A:
        return local_index(op, operand)
    return None


def _check_provider_slot(cf, here, ins, slot, gp_pc, admin_calls, v):
    for j, (pc, op, operand) in enumerate(ins):
        idx = local_index(op, operand)
        if idx != slot:
            continue
        if op in ASTORE_N or op == 0x3A:
            prev = ins[j - 1] if j > 0 else None
            if prev is None or prev[0] != gp_pc:
                v.append(("BMREC-02", f"{here}@{pc}: the provider's local slot {slot} is also written elsewhere"))
            continue
        if op in ALOAD_N or op == 0x19:
            ok = False
            if j + 2 < len(ins):
                _, op1, _ = ins[j + 1]
                _, op2, opd2 = ins[j + 2]
                if op1 in REF_PUSH_SIMPLE and op1 != 0x01 and op2 in (0xB6, 0xB9):
                    _, owner, name, desc = cf.member_ref(_u2(opd2))
                    ok = (owner, name, desc) in admin_calls
                    # a pushed ref must not be the provider itself (e.g. aload slot; aload slot; call)
                    if local_index(op1, ins[j + 1][2]) == slot:
                        ok = False
            if not ok:
                v.append(("BMREC-02", f"{here}@{pc}: provider (local {slot}) used other than as the receiver of "
                                      f"add/removeListener(Layer1ApiAdminListener)"))


def _check_pipe_site(cf, here, ins, i, desc, a, v):
    prefix = a["pipe_site"]["path_prefix"]
    if desc != "(Ljava/lang/String;Z)V":
        v.append(("BMREC-03", f"{here}: FileOutputStream must be constructed as (String path, true); got {desc}"))
        return
    if i < 2:
        v.append(("BMREC-03", f"{here}: FileOutputStream path is not a compile-time constant"))
        return
    _, op_ldc, opd_ldc = ins[i - 2]
    _, op_flag, _ = ins[i - 1]
    if op_ldc not in (0x12, 0x13):
        v.append(("BMREC-03", f"{here}: FileOutputStream path is not an ldc string constant"))
        return
    e = cf.cp[opd_ldc[0] if op_ldc == 0x12 else _u2(opd_ldc)]
    if not e or e[0] != "String":
        v.append(("BMREC-03", f"{here}: FileOutputStream path constant is not a String"))
        return
    s = cf.utf8(e[1])
    if not s.startswith(prefix):
        v.append(("BMREC-03", f"{here}: FileOutputStream path {s!r} does not start with {prefix!r}"))
    if op_flag != 0x04:  # iconst_1
        v.append(("BMREC-03", f"{here}: FileOutputStream append flag must be the constant true"))


def main(argv):
    args = list(argv)
    allow = DEFAULT_ALLOWLIST
    dump = False
    if "--allowlist" in args:
        k = args.index("--allowlist")
        allow = args[k + 1]
        del args[k:k + 2]
    if "--dump" in args:
        dump = True
        args.remove("--dump")
    if len(args) != 1:
        print(__doc__.splitlines()[2].strip())
        return 2
    a = load_allowlist(allow)
    violations, facts = check_jar(args[0], a)
    if dump:
        for t in sorted(facts["external_types"]):
            print("TYPE", t)
        for m in sorted(facts["external_members"]):
            print("MEMBER", *m)
    print(f"allowlist-check: jar={os.path.basename(args[0])} classes={facts['classes']} "
          f"getProvider_sites={facts['getprovider_sites']} pipe_sites={facts['pipe_sites']}")
    for rule, msg in violations:
        print(f"VIOLATION {rule}: {msg}")
    print("RESULT: " + ("FAIL" if violations else "PASS"))
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
