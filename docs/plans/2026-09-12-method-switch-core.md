# Method switch — core (registry, CLI, runner, analysis layer) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Một preset có tên, và một danh sách cặp, điều khiển cả tầng phân tích lẫn tầng pilot — đổi được từ terminal, có test, chưa có trang điều khiển.

**Architecture:** Thêm `docs/architecture/methods.json` làm nguồn duy nhất cho dimension / runner method / preset, song sinh với `instruments.json` đã có (reader + `sync-*.py --check|--write` + test chống trôi). Mọi bản sao hằng số hiện tại (`automation.py MARKET_DIMENSIONS`, `build-artifact.py LANES`, `strategy-runner.py METHODS`, `rank-setups.py RUNNABLE`) đổi thành đọc registry. `automation.py` nhận hai subcommand mới (`method`, `instrument set`) và được vá về tính toàn vẹn khi ghi file. `strategy-runner.py` lọc method ở **bước 3 của tick** và không bao giờ ở `load_setups()`.

**Tech Stack:** Python 3 (stdlib only), `unittest` chạy bằng `pytest`, JSON Schema draft-07.

**Spec:** `docs/specs/2026-09-12-method-switch-design.md` · **Security:** `docs/security/2026-09-12-method-panel.md` (38 rule; ID nào được nhắc trong task thì phải đọc rule đó trước khi code).

**Phạm vi plan này:** mục 3, 4.1, 4.2, 4.3, 4.6 và 9 của spec. **Không** gồm trang Artifact (§4.4) và cron applier (§4.5) — chúng tiêu thụ đúng cái CLI và API mà plan này tạo ra, nên viết kế hoạch cho chúng trước khi cái này tồn tại là đoán chữ ký hàm. Plan B viết sau khi plan này xong.

**Chạy test:** `python3 -m pytest scripts/tests/ -q` từ gốc repo. Một task chỉ xong khi **toàn bộ** thư mục test xanh, không chỉ test mới.

---

### Task 1: Registry `methods.json` + reader `scripts/methods.py`

**Files:**
- Create: `docs/architecture/methods.json`
- Create: `scripts/methods.py`
- Test: `scripts/tests/test_methods.py`

Đọc trước: spec §3.1, §3.2.

- [ ] **Step 1: Viết test thất bại**

Tạo `scripts/tests/test_methods.py`:

```python
"""The method registry has ONE source: docs/architecture/methods.json. Same contract as instruments.json
(SYSTEM-DESIGN.md §1 for instruments; spec docs/specs/2026-09-12-method-switch-design.md §3 for methods)."""
import itertools, os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import methods as M


class Registry(unittest.TestCase):
    def test_dimensions_per_market(self):
        self.assertEqual(M.dimensions("crypto"), ["wyckoff", "ict", "footprint", "heatmap"])
        self.assertEqual(M.dimensions("cfd"), ["wyckoff", "ict"])

    def test_preset_dimension_sets_are_pairwise_distinct(self):
        """profile_of must be a function: two presets may never name the same set of flags."""
        sets = [frozenset(p["dimensions"]) for p in M.PRESETS]
        self.assertEqual(len(sets), len(set(sets)))

    def test_profile_of_round_trips_every_preset(self):
        for p in M.PRESETS:
            self.assertEqual(M.profile_of({d: d in p["dimensions"] for d in M.ALL_DIMENSIONS}), p["id"])

    def test_every_other_combination_is_custom(self):
        named = {frozenset(p["dimensions"]) for p in M.PRESETS}
        n = 0
        for bits in itertools.product([False, True], repeat=len(M.ALL_DIMENSIONS)):
            dims = dict(zip(M.ALL_DIMENSIONS, bits))
            on = frozenset(d for d, v in dims.items() if v)
            if on not in named:
                self.assertEqual(M.profile_of(dims), "custom", f"{sorted(on)} should be custom")
                n += 1
        self.assertEqual(n, 2 ** len(M.ALL_DIMENSIONS) - len(M.PRESETS))

    def test_presets_for_cfd_excludes_coinglass_dimensions(self):
        ids = [p["id"] for p in M.presets_for("cfd")]
        self.assertEqual(ids, ["wyckoff", "ict", "wyckoff+ict"])


class RunnerMethods(unittest.TestCase):
    def test_requires_is_total_over_the_backtest_vocabulary(self):
        """Every method backtest-methods.py can produce must map, or a future RUNNABLE growth KeyErrors."""
        self.assertEqual(set(M.RUNNER_METHODS),
                         {"WYCKOFF", "WYCKOFF-BOOK", "ICT", "COMBINED", "COMBINED-BOOK", "PARTIAL"})

    def test_derivation(self):
        allow = lambda *on: M.runner_methods({d: d in on for d in M.ALL_DIMENSIONS})
        self.assertEqual(allow("wyckoff"), {"WYCKOFF", "WYCKOFF-BOOK"})
        self.assertEqual(allow("ict"), {"ICT"})
        self.assertEqual(allow("wyckoff", "ict"),
                         {"WYCKOFF", "WYCKOFF-BOOK", "ICT", "COMBINED", "COMBINED-BOOK", "PARTIAL"})
        self.assertEqual(allow("wyckoff", "footprint"), {"WYCKOFF", "WYCKOFF-BOOK"})
        self.assertEqual(allow("footprint", "heatmap"), set())
        self.assertEqual(allow(), set())

    def test_runnable_subset_matches_the_runner(self):
        self.assertEqual(M.runnable(), {"ICT", "COMBINED", "WYCKOFF", "WYCKOFF-BOOK"})


class Unverifiable(unittest.TestCase):
    def test_dimensions_with_no_runner_representation(self):
        """Footprint/heatmap never appear in any method's requires -- the page must say so honestly."""
        represented = set().union(*(set(v["requires"]) for v in M.RUNNER_METHODS.values()))
        self.assertEqual(set(M.ALL_DIMENSIONS) - represented, {"footprint", "heatmap"})
```

- [ ] **Step 2: Chạy để chắc chắn nó fail**

Run: `python3 -m pytest scripts/tests/test_methods.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'methods'`

- [ ] **Step 3: Tạo `docs/architecture/methods.json`**

```json
{
  "_comment": "THE single source of truth for the Confluence dimensions, the runner method table and the named presets (spec docs/specs/2026-09-12-method-switch-design.md §3). Nothing else in this repo may hard-code any of the three: scripts/methods.py is the reader, scripts/sync-methods.py regenerates the derived schema enums, and scripts/tests/test_methods_sync.py fails the build if any copy drifts. Twin of instruments.json.",
  "schema_version": 1,

  "dimensions": {
    "wyckoff": {
      "label": "Wyckoff", "markets": ["crypto", "cfd"], "agent": "structure-agent", "skill": "wyckoff-skill",
      "data_sources": ["ohlcv"], "max_points": 25, "lane": "wyckoff",
      "note": "Phase A-E vocabulary, doi nhan tests, Effort-vs-Result, SOT, Volume Profile (user decision 2026-09-10). NOT the same thing as the runner's mechanical WYCKOFF method -- see runner_methods."
    },
    "ict": {
      "label": "ICT", "markets": ["crypto", "cfd"], "agent": "structure-agent", "skill": "ict-skill",
      "data_sources": ["ohlcv"], "max_points": 25, "lane": "ict",
      "note": "knowledge/04-06 carry no volume of any kind; volume is the only orthogonal axis against Wyckoff (SYSTEM-DESIGN.md §6.1)."
    },
    "footprint": {
      "label": "Footprint", "markets": ["crypto"], "agent": "flow-agent", "skill": "footprint-skill",
      "data_sources": ["coinglass_footprint"], "max_points": 25, "lane": "footprint",
      "note": "No commodities source: CoinGlass is crypto-derivatives only (SYSTEM-DESIGN.md §12 item 3)."
    },
    "heatmap": {
      "label": "Heatmap", "markets": ["crypto"], "agent": "liquidity-agent", "skill": "heatmap-skill",
      "data_sources": ["coinglass_heatmap"], "max_points": 25, "lane": "heatmap",
      "note": "Same CoinGlass limit. No ingested knowledge/ source either (SYSTEM-DESIGN.md §12 item 1)."
    }
  },

  "runner_methods": {
    "WYCKOFF":       { "requires": ["wyckoff"],       "runnable": true,  "scan": "wyckoff", "entry": "market" },
    "WYCKOFF-BOOK":  { "requires": ["wyckoff"],       "runnable": true,  "scan": "wyckoff", "entry": "market" },
    "ICT":           { "requires": ["ict"],           "runnable": true,  "scan": "ict",     "entry": "limit"  },
    "COMBINED":      { "requires": ["wyckoff","ict"], "runnable": true,  "scan": "ict",     "entry": "limit"  },
    "COMBINED-BOOK": { "requires": ["wyckoff","ict"], "runnable": false, "scan": "wyckoff", "entry": "market" },
    "PARTIAL":       { "requires": ["wyckoff","ict"], "runnable": false, "scan": "ict",     "entry": "limit"  }
  },
  "_runner_note": "requires[] is the dimension gate, NOT a claim that the runner reproduces that dimension's full read. The runner's WYCKOFF/WYCKOFF-BOOK are mechanical rules (scripts/wyckoff_rules.py: CHoCH gate, TR from SC/AR, Spring vs Shakeout, VP veto); the wyckoff DIMENSION is the skill's discretionary read. Homonyms. runnable=false means backtest-only (scripts/backtest-methods.py:528); scan picks which causal scanner in strategy-runner.py produces the setups.",

  "presets": [
    { "id": "wyckoff",               "label": "Wyckoff",                   "dimensions": ["wyckoff"],                               "tier": "research" },
    { "id": "ict",                   "label": "ICT",                       "dimensions": ["ict"],                                   "tier": "research" },
    { "id": "wyckoff+ict",           "label": "Wyckoff + ICT",             "dimensions": ["wyckoff", "ict"],                        "tier": "trade" },
    { "id": "wyckoff+footprint",     "label": "Wyckoff + Footprint",       "dimensions": ["wyckoff", "footprint"],                  "tier": "trade" },
    { "id": "wyckoff+ict+footprint", "label": "Wyckoff + ICT + Footprint", "dimensions": ["wyckoff", "ict", "footprint"],           "tier": "trade" },
    { "id": "full",                  "label": "Day du 4 chieu",            "dimensions": ["wyckoff", "ict", "footprint", "heatmap"], "tier": "trade" }
  ],
  "_preset_note": "tier research = below the NORMAL minimum of 2 engaged dimensions (SYSTEM-DESIGN.md §6.1), so /analyze can never return TRADE under it; the mechanical pilot still fires. The panel prints that on the card. Preset dimension sets MUST stay pairwise distinct or profile_of stops being a function -- scripts/methods.py raises on load if they collide.",

  "history": [
    { "date": "2026-09-12", "change": "initial registry: 4 dimensions, 6 runner methods, 6 presets",
      "reason": "extracted from automation.py MARKET_DIMENSIONS, build-artifact.py LANES, strategy-runner.py METHODS and rank-setups.py RUNNABLE, which had drifted into 2-3 hand-kept copies",
      "approved_by": "user (in session)" }
  ]
}
```

- [ ] **Step 4: Tạo `scripts/methods.py`**

```python
"""THE reader for docs/architecture/methods.json -- the single source of truth for the Confluence dimensions,
the runner method table and the named presets (spec docs/specs/2026-09-12-method-switch-design.md §3).
Import this; never hard-code a dimension, method or preset list anywhere else.

    import methods as M
    M.dimensions("cfd")        -> ['wyckoff', 'ict']        # dimensions that market can have at all
    M.profile_of(flags)        -> 'wyckoff+ict' | 'custom'  # the NAME of a set of the four flags
    M.runner_methods(flags)    -> {'WYCKOFF', ...}          # methods whose requires[] is satisfied
    M.presets_for("cfd")       -> [preset, ...]             # presets whose dimensions all exist there

Loading enforces the invariant that keeps profile_of a function: no two presets may name the same set of
dimensions. A violation raises at import time rather than silently making one preset unreachable.
"""
import json, os

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "docs", "architecture", "methods.json")


def _load():
    with open(PATH, encoding="utf-8") as fh:
        d = json.load(fh)
    seen = {}
    for p in d["presets"]:
        key = frozenset(p["dimensions"])
        if key in seen:
            raise ValueError(f"{PATH}: presets '{seen[key]}' and '{p['id']}' name the same dimension set "
                             f"{sorted(key)}; profile_of would stop being a function.")
        seen[key] = p["id"]
        unknown = [x for x in p["dimensions"] if x not in d["dimensions"]]
        if unknown:
            raise ValueError(f"{PATH}: preset '{p['id']}' names unknown dimension(s) {unknown}.")
    for name, m in d["runner_methods"].items():
        unknown = [x for x in m["requires"] if x not in d["dimensions"]]
        if unknown:
            raise ValueError(f"{PATH}: runner method '{name}' requires unknown dimension(s) {unknown}.")
    return d


_DATA = _load()
DIMENSIONS = _DATA["dimensions"]
RUNNER_METHODS = _DATA["runner_methods"]
PRESETS = _DATA["presets"]
ALL_DIMENSIONS = list(DIMENSIONS)


def dimensions(market):
    """The dimensions this market can have AT ALL -- the shape, not the on/off state."""
    return [d for d, v in DIMENSIONS.items() if market in v["markets"]]


def markets():
    out = []
    for v in DIMENSIONS.values():
        for m in v["markets"]:
            if m not in out:
                out.append(m)
    return out


def _on(flags):
    return frozenset(d for d in ALL_DIMENSIONS if flags.get(d))


def profile_of(flags):
    """The preset id naming this set of flags, or 'custom'. Pure function of the flags."""
    on = _on(flags)
    for p in PRESETS:
        if frozenset(p["dimensions"]) == on:
            return p["id"]
    return "custom"


def preset(pid):
    for p in PRESETS:
        if p["id"] == pid:
            return p
    return None


def presets_for(market):
    """Presets every one of whose dimensions exists in this market. cfd has no CoinGlass source, so any
    preset naming footprint/heatmap is structurally impossible there (SYSTEM-DESIGN.md §12 item 3)."""
    have = set(dimensions(market))
    return [p for p in PRESETS if set(p["dimensions"]) <= have]


def flags_for(pid):
    """The four booleans a preset means. Raises on an unknown id -- callers must validate first."""
    p = preset(pid)
    if p is None:
        raise KeyError(pid)
    return {d: d in p["dimensions"] for d in ALL_DIMENSIONS}


def runner_methods(flags):
    """Methods whose every required dimension is on. Lookup over requires[], not a hard-coded rule."""
    on = _on(flags)
    return {name for name, m in RUNNER_METHODS.items() if set(m["requires"]) <= on}


def runnable():
    return {name for name, m in RUNNER_METHODS.items() if m["runnable"]}


def scan_of(name):
    return RUNNER_METHODS[name]["scan"]
```

- [ ] **Step 5: Chạy test, phải xanh**

Run: `python3 -m pytest scripts/tests/test_methods.py -q`
Expected: PASS, 8 passed

- [ ] **Step 6: Commit**

```bash
git add docs/architecture/methods.json scripts/methods.py scripts/tests/test_methods.py
git commit -m "methods: single-source registry for dimensions, runner methods and presets"
```

---

### Task 2: `sync-methods.py` sinh lại enum schema, và test chống trôi

**Files:**
- Create: `scripts/sync-methods.py`
- Create: `scripts/tests/test_methods_sync.py`
- Modify: `docs/architecture/schemas/automation-config.schema.json` (do script ghi, không sửa tay)

Đọc trước: spec §3.3. Mẫu để bắt chước: `scripts/sync-instruments.py`.

- [ ] **Step 1: Viết test thất bại**

Tạo `scripts/tests/test_methods_sync.py`:

```python
"""The schema's dimension shape is DERIVED from methods.json. Drift fails the build, exactly as
test_instruments_sync.py does for the symbol enums."""
import importlib.util, json, os, subprocess, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import methods as M

SCHEMA = os.path.join(ROOT, "docs", "architecture", "schemas", "automation-config.schema.json")


class Sync(unittest.TestCase):
    def test_check_mode_is_clean(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "sync-methods.py"), "--check"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, f"drift:\n{r.stdout}\n{r.stderr}")

    def test_schema_dimension_shape_matches_registry(self):
        doc = json.load(open(SCHEMA, encoding="utf-8"))
        for m in M.markets():
            props = doc["properties"]["markets"]["properties"][m]["properties"]["dimensions"]
            self.assertEqual(sorted(props["properties"]), sorted(M.dimensions(m)))
            self.assertEqual(sorted(props["required"]), sorted(M.dimensions(m)))
            self.assertFalse(props["additionalProperties"],
                             "impossible states must be absent from the shape, not settable flags")

    def test_cfd_has_no_coinglass_dimension(self):
        doc = json.load(open(SCHEMA, encoding="utf-8"))
        props = doc["properties"]["markets"]["properties"]["cfd"]["properties"]["dimensions"]["properties"]
        self.assertNotIn("footprint", props)
        self.assertNotIn("heatmap", props)
```

- [ ] **Step 2: Chạy để chắc chắn nó fail**

Run: `python3 -m pytest scripts/tests/test_methods_sync.py -q`
Expected: FAIL — `sync-methods.py` chưa tồn tại, `returncode` khác 0

- [ ] **Step 3: Tạo `scripts/sync-methods.py`**

```python
#!/usr/bin/env python3
"""Regenerate every DERIVED copy of the method registry from the single source
(docs/architecture/methods.json). JSON Schema cannot $ref an enum out of an arbitrary file in a way every
validator honours, so the dimension shape is generated here instead of hand-maintained -- and
scripts/tests/test_methods_sync.py runs this in --check mode so drift fails the build.

    python3 scripts/sync-methods.py --check    # exit 1 and name the drift
    python3 scripts/sync-methods.py --write    # rewrite the derived spots

Derived spots (add new ones HERE, never a new hand-kept list):
  - schemas/automation-config.schema.json  markets.<m>.dimensions.{properties,required}  <- dimensions[*].markets

Generating the shape from dimensions[*].markets is what keeps SYSTEM-DESIGN.md §12's property alive: a market
that has no source for a dimension does not get a flag it would silently ignore -- the key is simply absent and
additionalProperties:false turns a bad config into a validation error.
"""
import argparse, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import methods as M

SCHEMA = os.path.join(ROOT, "docs", "architecture", "schemas", "automation-config.schema.json")


def _desc(market):
    dims = M.dimensions(market)
    if market == "cfd":
        return ("Wyckoff + ICT only -- the 2-of-4 structural cap. GENERATED by scripts/sync-methods.py from "
                "docs/architecture/methods.json; do not hand-edit. Note that even these two are close to "
                "non-independent on the bridge's TICK volume (SYSTEM-DESIGN.md section 6.1): Wyckoff credit is "
                "reduced there, it is not scored at face value.")
    return (f"The {len(dims)} Confluence Score dimensions (SYSTEM-DESIGN.md section 6.2). GENERATED by "
            "scripts/sync-methods.py from docs/architecture/methods.json; do not hand-edit. Disabling one "
            "removes it from engaged_count -- it can only LOWER the number of dimensions available to a "
            "verdict, never raise a score. Below the mode minimum (NORMAL 2, ENHANCED 3, STRICT 3) no live "
            "TRADE verdict can pass at all.")


def desired():
    """(market, block) for every derived dimensions block."""
    out = []
    for m in M.markets():
        dims = M.dimensions(m)
        out.append((m, {
            "type": "object",
            "additionalProperties": False,
            "required": list(dims),
            "description": _desc(m),
            "properties": {d: {"type": "boolean", "description": M.DIMENSIONS[d]["label"]} for d in dims},
        }))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--write", action="store_true")
    a = ap.parse_args()

    doc = json.load(open(SCHEMA, encoding="utf-8"))
    drift = []
    for market, block in desired():
        cur = doc["properties"]["markets"]["properties"][market]["properties"].get("dimensions")
        if cur != block:
            drift.append(market)
            if a.write:
                doc["properties"]["markets"]["properties"][market]["properties"]["dimensions"] = block

    if a.check:
        for m in drift:
            print(f"DRIFT: {os.path.relpath(SCHEMA, ROOT)} markets.{m}.dimensions does not match "
                  f"docs/architecture/methods.json (expected {M.dimensions(m)})")
        return 1 if drift else 0

    if drift:
        with open(SCHEMA, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"wrote {os.path.relpath(SCHEMA, ROOT)}: {', '.join(drift)}")
    else:
        print("no drift; nothing to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Chạy `--write` rồi kiểm bằng mắt**

Run:
```bash
python3 scripts/sync-methods.py --write
git diff --stat docs/architecture/schemas/automation-config.schema.json
```
Expected: file schema đổi (hoặc "no drift" nếu đã khớp). Nếu diff làm **mất** `instruments.items.enum`, dừng lại — script chỉ được đụng khối `dimensions`.

- [ ] **Step 5: Chạy cả hai sync và toàn bộ test**

Run:
```bash
python3 scripts/sync-instruments.py --check && python3 scripts/sync-methods.py --check
python3 -m pytest scripts/tests/ -q
```
Expected: cả hai `--check` exit 0; toàn bộ test xanh

- [ ] **Step 6: Commit**

```bash
git add scripts/sync-methods.py scripts/tests/test_methods_sync.py docs/architecture/schemas/automation-config.schema.json
git commit -m "methods: generate the schema dimension shape from the registry, fail the build on drift"
```

---

### Task 3: `automation.py` đọc registry thay cho hằng số

**Files:**
- Modify: `scripts/automation.py:78-85` (`MARKET_DIMENSIONS`, `DIMENSIONS`), `:1281-1283` (`dimension` subcommand choices)
- Test: `scripts/tests/test_methods.py` (thêm class)

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `scripts/tests/test_methods.py`:

```python
class AutomationUsesRegistry(unittest.TestCase):
    def test_no_hand_kept_dimension_list_left(self):
        """The whole point of the registry: automation.py must not carry a second copy."""
        src = open(os.path.join(ROOT, "scripts", "automation.py"), encoding="utf-8").read()
        self.assertNotIn('"wyckoff", "ict", "footprint", "heatmap"', src)
        self.assertIn("import methods", src)

    def test_market_dimensions_comes_from_the_registry(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("auto", os.path.join(ROOT, "scripts", "automation.py"))
        auto = importlib.util.module_from_spec(spec); spec.loader.exec_module(auto)
        for m in M.markets():
            self.assertEqual(auto.MARKET_DIMENSIONS[m], M.dimensions(m))
```

- [ ] **Step 2: Chạy để chắc chắn nó fail**

Run: `python3 -m pytest scripts/tests/test_methods.py -q -k AutomationUsesRegistry`
Expected: FAIL — `assertNotIn` tìm thấy chuỗi hằng số

- [ ] **Step 3: Sửa `scripts/automation.py`**

Sau khối import `instruments` (quanh `:76`), thêm cùng kiểu nạp module đang dùng cho `instruments`:

```python
_mspec = importlib.util.spec_from_file_location("methods", os.path.join(ROOT, "scripts", "methods.py"))
methods = importlib.util.module_from_spec(_mspec); _mspec.loader.exec_module(methods)
```

Thay hai dòng hằng số ở `:80` và `:84`:

```python
# Which dimensions each market can have AT ALL -- the shape, from docs/architecture/methods.json.
# Footprint/Heatmap have NO commodities source (CoinGlass is crypto-derivatives only) -- SYSTEM-DESIGN.md §12 item 3,
# which is now expressed by those dimensions not listing "cfd" in their markets[].
MARKET_DIMENSIONS = {m: methods.dimensions(m) for m in MARKETS}
DIMENSIONS = list(methods.ALL_DIMENSIONS)                                    # SYSTEM-DESIGN.md §6.2
```

Ở `:1281-1283`, `dimension` subcommand phải lấy `choices` từ `DIMENSIONS` (nếu đang liệt kê tay thì đổi):

```python
    p = audited(sub.add_parser("dimension"))
    p.add_argument("name", choices=DIMENSIONS); p.add_argument("value", choices=["on", "off"])
    p.add_argument("--market", choices=MARKETS)
```

- [ ] **Step 4: Chạy test**

Run: `python3 -m pytest scripts/tests/ -q`
Expected: toàn bộ xanh. Rồi kiểm tay:
```bash
python3 scripts/automation.py status | head -20
```
Expected: dòng `dimensions:` in đúng như trước khi sửa

- [ ] **Step 5: Commit**

```bash
git add scripts/automation.py scripts/tests/test_methods.py
git commit -m "automation: dimension shape comes from the registry, not a second hand-kept copy"
```

---

### Task 4: Toàn vẹn khi ghi config — nguyên tử, khoá, không ghi đè file hỏng, làm sạch audit

**Files:**
- Modify: `scripts/automation.py:270-301` (`load`, `record`, `save`), mọi `cmd_*` gọi `load()`
- Create: `scripts/tests/test_automation_integrity.py`

Đọc trước: rule **CFG-01, CFG-02, CFG-05, CFG-06, CFG-07** trong `docs/security/2026-09-12-method-panel.md`.

> **Vì sao task này đứng trước hai subcommand mới:** hôm nay `load():276-280` in *"refusing to overwrite blindly"* nhưng mọi caller viết `cfg, _, _ = load()` rồi `save(cfg)` — cờ `exists` bị vứt, nên một config hỏng bị ghi đè bằng `DEFAULTS` (bật hết dimension, bật hết layer, `history` rỗng). Thêm người ghi thứ hai trước khi vá chỗ này là nhân rủi ro lên.

- [ ] **Step 1: Viết test thất bại**

Tạo `scripts/tests/test_automation_integrity.py`:

```python
"""Config-write integrity. A second writer (the applier cron) is coming, and today's read-modify-write is
neither atomic nor locked, and silently replaces an unreadable config with permissive defaults.
Rules CFG-01, CFG-02, CFG-05, CFG-06, CFG-07 in docs/security/2026-09-12-method-panel.md."""
import json, os, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AUTO = os.path.join(ROOT, "scripts", "automation.py")
CONFIG = os.path.join(ROOT, "docs", "architecture", "automation-config.json")


class ConfigIntegrity(unittest.TestCase):
    def setUp(self):
        self.backup = tempfile.NamedTemporaryFile(delete=False).name
        shutil.copy(CONFIG, self.backup)

    def tearDown(self):
        shutil.copy(self.backup, CONFIG); os.unlink(self.backup)

    def run_auto(self, *args):
        return subprocess.run([sys.executable, AUTO, *args], capture_output=True, text=True)

    def test_unreadable_config_is_never_overwritten(self):
        """CFG-02: a corrupt file must stop the write, not be replaced by permissive DEFAULTS."""
        open(CONFIG, "w").write("{ this is not json")
        r = self.run_auto("dimension", "heatmap", "off", "--market", "crypto")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("unreadable", (r.stdout + r.stderr).lower())
        self.assertEqual(open(CONFIG).read(), "{ this is not json",
                         "the corrupt file was overwritten -- CFG-02 violated")

    def test_audit_strings_are_sanitised(self):
        """CFG-05: newlines and ANSI in an audit string must not forge a second history row."""
        r = self.run_auto("dimension", "heatmap", "off", "--market", "crypto",
                          "--reason", "line one\nline two\x1b[31mred\x1b[0m")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        row = json.load(open(CONFIG, encoding="utf-8"))["history"][-1]
        self.assertNotIn("\n", row["detail"] or "")
        self.assertNotIn("\x1b", row["detail"] or "")

    def test_write_is_atomic_no_partial_file(self):
        """CFG-01: os.replace, so a reader never sees a truncated file."""
        src = open(AUTO, encoding="utf-8").read()
        self.assertIn("os.replace", src)
        self.assertIn("flock", src)

    def test_evicted_history_rows_are_archived(self):
        """CFG-07: the 200-row ring must not be a silent shredder once a cron writes to it."""
        src = open(AUTO, encoding="utf-8").read()
        self.assertIn("history-archive", src)
```

- [ ] **Step 2: Chạy để chắc chắn nó fail**

Run: `python3 -m pytest scripts/tests/test_automation_integrity.py -q`
Expected: FAIL — 4 test đỏ

- [ ] **Step 3: Sửa `scripts/automation.py`**

Thay `load` / `record` / `save` (`:270-301`):

```python
import fcntl, re

HISTORY_ARCHIVE = os.path.join(ROOT, "data", "live", "history-archive.automation.jsonl")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def clean(s, limit=300):
    """Audit strings may now carry values influenced from outside (the panel applier). Strip control
    characters and ANSI so a history row can never forge a second row or steer a terminal, and cap the
    length so one row cannot crowd the ring. CFG-05."""
    if s is None:
        return None
    return _CTRL.sub(" ", str(s)).strip()[:limit]


def load(require_readable=True):
    """(config, exists, migrated). A MISSING file means UNCONFIGURED: the defaults are what every reader
    assumes, so a clean checkout behaves exactly as it did before this switch existed. An UNREADABLE file is
    different -- it is a corrupt state, and replacing it with permissive defaults would silently turn every
    dimension and every layer back on. CFG-02: callers that intend to write pass require_readable=True (the
    default) and we exit 2 rather than return defaults."""
    if not os.path.exists(CONFIG):
        return json.loads(json.dumps(DEFAULTS)), False, False
    try:
        raw = json.load(open(CONFIG, encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"REFUSED: {CONFIG} is unreadable ({e}); refusing to overwrite it. Fix or delete the file.",
              file=sys.stderr)
        if require_readable:
            raise SystemExit(2)
        return json.loads(json.dumps(DEFAULTS)), False, False
    ver = int(raw.get("schema_version", 1))
    if ver <= 1:
        return migrate_v1(raw), True, True
    if ver == 2:
        return migrate_v2(raw), True, True
    return _deep_merge(json.loads(json.dumps(DEFAULTS)), raw), True, False


def record(cfg, a, action, result):
    cfg["history"].append({"ts": now(), "actor": clean(actor(a), 80), "action": clean(action),
                           "detail": clean(getattr(a, "reason", None)), "result": result})
    if len(cfg["history"]) > HISTORY_MAX:
        evicted, cfg["history"] = cfg["history"][:-HISTORY_MAX], cfg["history"][-HISTORY_MAX:]
        os.makedirs(os.path.dirname(HISTORY_ARCHIVE), exist_ok=True)
        with open(HISTORY_ARCHIVE, "a", encoding="utf-8") as f:      # CFG-07: the ring is not a shredder
            for row in evicted:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")


def save(cfg):
    """CFG-01: atomic and locked. Two writers exist now (a terminal and the applier cron); a truncate-in-place
    write loses one update outright and a crash mid-write leaves a file strategy-runner.py's automation_gate()
    reads as 'unreadable' -- i.e. a pilot outage."""
    cfg["last_updated"] = now()
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    lock = CONFIG + ".lock"
    with open(lock, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            tmp = CONFIG + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, CONFIG)
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)
```

Rồi trong `show()` (`:466-516`), bọc mọi giá trị history khi in bằng `clean()` (CFG-06) — tìm chỗ in `history` và đổi sang in `clean(row["action"])`, `clean(row["detail"])`.

Thêm `data/live/history-archive.automation.jsonl` vào `.gitignore` nếu `data/live/` chưa được ignore cả thư mục (kiểm: `git check-ignore -v data/live/history-archive.automation.jsonl`).

- [ ] **Step 4: Chạy test**

Run: `python3 -m pytest scripts/tests/ -q`
Expected: toàn bộ xanh

- [ ] **Step 5: Commit**

```bash
git add scripts/automation.py scripts/tests/test_automation_integrity.py
git commit -m "automation: atomic locked config writes, never overwrite a corrupt file, sanitise the audit trail"
```

---

### Task 5: `automation.py method <preset>` và `allows master`

**Files:**
- Modify: `scripts/automation.py` (thêm `cmd_method`, `cmd_allows` nhận `master`, đăng ký parser, `show()` in nhãn preset)
- Create: `scripts/tests/test_automation_method.py`

Đọc trước: spec §4.1; rule **CFG-03, CFG-04, CFG-10, CRON-01**.

- [ ] **Step 1: Viết test thất bại**

Tạo `scripts/tests/test_automation_method.py`:

```python
"""`automation.py method` -- the named preset as a set of the four dimension flags.
Rules CFG-03, CFG-04, CFG-10 in docs/security/2026-09-12-method-panel.md."""
import json, os, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import methods as M

AUTO = os.path.join(ROOT, "scripts", "automation.py")
CONFIG = os.path.join(ROOT, "docs", "architecture", "automation-config.json")


class MethodCommand(unittest.TestCase):
    def setUp(self):
        self.backup = tempfile.NamedTemporaryFile(delete=False).name
        shutil.copy(CONFIG, self.backup)

    def tearDown(self):
        shutil.copy(self.backup, CONFIG); os.unlink(self.backup)

    def run_auto(self, *args):
        return subprocess.run([sys.executable, AUTO, *args], capture_output=True, text=True)

    def cfg(self):
        return json.load(open(CONFIG, encoding="utf-8"))

    def test_sets_exactly_the_flags_the_preset_names(self):
        r = self.run_auto("method", "wyckoff+ict", "--market", "crypto")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.cfg()["markets"]["crypto"]["dimensions"],
                         {"wyckoff": True, "ict": True, "footprint": False, "heatmap": False})

    def test_records_history(self):
        self.run_auto("method", "full", "--market", "crypto", "--who", "tester", "--reason", "unit test")
        row = self.cfg()["history"][-1]
        self.assertEqual(row["result"], "applied")
        self.assertIn("full", row["action"])
        self.assertEqual(row["actor"], "tester")

    def test_touches_nothing_but_the_four_flags(self):
        """CFG-10: the write scope is the dimension block, not a licence to rewrite the config."""
        before = self.cfg()
        self.run_auto("method", "wyckoff+footprint", "--market", "crypto")
        after = self.cfg()
        for key in ("enabled", "execution", "layers", "pilot_process", "services"):
            self.assertEqual(before.get(key), after.get(key), f"{key} changed")
        self.assertEqual(before["markets"]["crypto"]["instruments"], after["markets"]["crypto"]["instruments"])
        self.assertEqual(before["markets"]["crypto"]["timeframes"], after["markets"]["crypto"]["timeframes"])
        self.assertEqual(before["markets"]["cfd"], after["markets"]["cfd"])

    def test_refuses_a_preset_the_market_cannot_have(self):
        """cfd has no CoinGlass source: footprint/heatmap presets are structurally impossible there."""
        r = self.run_auto("method", "full", "--market", "cfd")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("REFUSED", r.stdout + r.stderr)
        self.assertEqual(self.cfg()["history"][-1]["result"], "refused")

    def test_refuses_an_unknown_preset_without_touching_the_config(self):
        before = self.cfg()
        r = self.run_auto("method", "wyckoff+telepathy", "--market", "crypto")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(before["markets"], self.cfg()["markets"])

    def test_no_market_applies_to_every_market_that_can_have_the_preset(self):
        r = self.run_auto("method", "wyckoff+ict")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for m in ("crypto", "cfd"):
            self.assertTrue(self.cfg()["markets"][m]["dimensions"]["wyckoff"])
            self.assertTrue(self.cfg()["markets"][m]["dimensions"]["ict"])

    def test_status_prints_the_derived_preset_label(self):
        self.run_auto("method", "wyckoff+ict", "--market", "crypto")
        r = self.run_auto("status")
        self.assertIn("wyckoff+ict", r.stdout)

    def test_status_says_custom_when_no_preset_names_the_flags(self):
        self.run_auto("method", "full", "--market", "crypto")
        self.run_auto("dimension", "ict", "off", "--market", "crypto")
        r = self.run_auto("status")
        self.assertIn("custom", r.stdout)


class AllowsMaster(unittest.TestCase):
    def run_auto(self, *args):
        return subprocess.run([sys.executable, AUTO, *args], capture_output=True, text=True)

    def test_allows_master_exists_and_uses_the_refusal_exit_code(self):
        """CRON-01: the applier gates on exit 0. Exit 2 is REFUSED, exit 1 is a usage error -- an
        applier that treated 'not 2' as permission would run on a typo."""
        r = self.run_auto("allows", "master")
        self.assertIn(r.returncode, (0, 2), r.stdout + r.stderr)

    def test_unknown_allows_target_is_a_usage_error_not_a_refusal(self):
        r = self.run_auto("allows", "masterr")
        self.assertEqual(r.returncode, 1, "usage errors must stay exit 1 so a gate can tell them apart")
```

- [ ] **Step 2: Chạy để chắc chắn nó fail**

Run: `python3 -m pytest scripts/tests/test_automation_method.py -q`
Expected: FAIL — `invalid choice: 'method'`

- [ ] **Step 3: Thêm `cmd_method` vào `scripts/automation.py`**

Đặt ngay trước `cmd_dimension` (`:957`):

```python
def cmd_method(a):
    """Apply a named preset = a set of the four dimension flags. The preset is only a NAME for that set
    (spec §3); nothing new is stored, and scripts/methods.py derives the label back from the flags."""
    cfg, _, _ = load()
    p = methods.preset(a.preset)
    if p is None:                                   # argparse choices should have caught this; belt and braces
        record(cfg, a, f"method {a.preset}", "refused"); save(cfg)
        print(f"REFUSED: unknown preset '{a.preset}'. Known: "
              f"{', '.join(x['id'] for x in methods.PRESETS)}", file=sys.stderr)
        return 2
    targets = [a.market] if a.market else [m for m in MARKETS if p in methods.presets_for(m)]
    bad = [m for m in ([a.market] if a.market else []) if p not in methods.presets_for(m)]
    if bad:
        missing = sorted(set(p["dimensions"]) - set(methods.dimensions(bad[0])))
        record(cfg, a, f"method {a.preset} --market {','.join(bad)}", "refused")
        save(cfg)
        print(f"REFUSED: preset '{a.preset}' needs {', '.join(missing)}, which market '{bad[0]}' has no source "
              f"for (CoinGlass is crypto-derivatives only, SYSTEM-DESIGN.md §12 item 3).", file=sys.stderr)
        show(cfg, True)
        return 2
    want = methods.flags_for(a.preset)
    changed = []
    for m in targets:
        flags = {d: want[d] for d in MARKET_DIMENSIONS[m]}
        if cfg["markets"][m]["dimensions"] != flags:
            changed.append(m)
        cfg["markets"][m]["dimensions"] = flags          # CFG-10: this block and nothing else
    record(cfg, a, f"method {a.preset} --market {','.join(targets)}",
           "applied" if changed else "no-op")
    save(cfg)
    show(cfg, True)
    return 0
```

Trong `show()`, ngay sau dòng in `dimensions:` (`:498-499`), thêm nhãn suy ra:

```python
        prof = methods.profile_of(mk["dimensions"])
        live = [d for d in MARKET_DIMENSIONS[m] if mk["dimensions"].get(d, True)]
        print(f"               method:     {prof}"
              + ("" if prof != "custom" else f"  (set from the terminal: {', '.join(live) or 'none'})")
              + ("" if len(live) >= 2 else "   [below the NORMAL minimum of 2 -- no live TRADE verdict can pass]"))
```

Mở rộng `cmd_allows` (`:1029`) để nhận `master`:

```python
def cmd_allows(a):
    cfg, _, _ = load(require_readable=False)
    if a.layer == "master":
        return 0 if cfg.get("enabled", True) else 2      # CRON-01: 0 = permitted, 2 = refused, never 1
    ...  # phần còn lại giữ nguyên
```

Đăng ký parser (cạnh `:1281`):

```python
    p = audited(sub.add_parser("method"))
    p.add_argument("preset", choices=[x["id"] for x in methods.PRESETS])
    p.add_argument("--market", choices=MARKETS)
```

và đổi `allows` để nhận thêm `master`:

```python
    al = sub.add_parser("allows"); al.add_argument("layer", choices=LAYERS + ["master"])
    al.add_argument("style", nargs="?", default=None)
```

Cuối cùng, trong `main()` cạnh `:1321`:

```python
    if a.cmd == "method":
        return cmd_method(a)
```

- [ ] **Step 4: Chạy test**

Run: `python3 -m pytest scripts/tests/ -q`
Expected: toàn bộ xanh

- [ ] **Step 5: Kiểm tay**

Run:
```bash
python3 scripts/automation.py method wyckoff+ict --market crypto
python3 scripts/automation.py status | grep -A1 "method:"
python3 scripts/automation.py allows master; echo "exit=$?"
git checkout docs/architecture/automation-config.json
```
Expected: status in `method: wyckoff+ict`; `allows master` exit 0

- [ ] **Step 6: Commit**

```bash
git add scripts/automation.py scripts/tests/test_automation_method.py
git commit -m "automation: method <preset> subcommand, allows master gate, derived preset label in status"
```

---

### Task 6: `demo`/`real` thôi ghi đè preset

**Files:**
- Modify: `scripts/automation.py:867` (`apply_preset`), `.claude/commands/automation.md:14`
- Test: `scripts/tests/test_automation_method.py` (thêm class)

Đọc trước: spec §4.1.

- [ ] **Step 1: Viết test thất bại**

Thêm vào `scripts/tests/test_automation_method.py`:

```python
class EnvironmentPresetDoesNotStompMethod(unittest.TestCase):
    def setUp(self):
        self.backup = tempfile.NamedTemporaryFile(delete=False).name
        shutil.copy(CONFIG, self.backup)

    def tearDown(self):
        shutil.copy(self.backup, CONFIG); os.unlink(self.backup)

    def test_demo_preset_preserves_the_chosen_method(self):
        """apply_preset used to do mk["dimensions"] = {d: True ...}, silently erasing the user's preset."""
        subprocess.run([sys.executable, AUTO, "method", "wyckoff+ict", "--market", "crypto"],
                       capture_output=True, text=True)
        before = json.load(open(CONFIG, encoding="utf-8"))["markets"]["crypto"]["dimensions"]
        subprocess.run([sys.executable, AUTO, "demo"], capture_output=True, text=True)
        after = json.load(open(CONFIG, encoding="utf-8"))["markets"]["crypto"]["dimensions"]
        self.assertEqual(before, after, "demo reset the dimensions and wiped the preset")
```

> Nếu `demo` trong môi trường test cố cài launchd agent thì đặt `AUTOMATION_PILOT_DRYRUN=1` trong `env=` của `subprocess.run`, và nếu vẫn có tác dụng phụ thì gọi thẳng `apply_preset` qua import module thay vì chạy subprocess.

- [ ] **Step 2: Chạy để chắc chắn nó fail**

Run: `python3 -m pytest scripts/tests/test_automation_method.py -q -k EnvironmentPreset`
Expected: FAIL — dimensions bị bật hết

- [ ] **Step 3: Sửa `apply_preset` (`:867`)**

Xoá dòng `mk["dimensions"] = {d: True for d in MARKET_DIMENSIONS[m]}` và thay bằng:

```python
        # The method preset is the user's choice and survives an environment switch (spec §4.1). Before this,
        # demo/real turned every dimension back on and silently erased it.
        prof = methods.profile_of(mk["dimensions"])
        enabled_msgs.append(f"{m}: method preset kept as {prof}")
```

Sửa dòng mô tả trong `:872` cho khỏi nói sai (bỏ phần `dimensions {...}` liệt kê bật hết).

Sửa `.claude/commands/automation.md:14`: bỏ cụm "all dimensions each market has" khỏi mô tả `demo`/`real`, thêm "dimensions/preset are left exactly as they are".

- [ ] **Step 4: Chạy test**

Run: `python3 -m pytest scripts/tests/ -q`
Expected: toàn bộ xanh

- [ ] **Step 5: Commit**

```bash
git add scripts/automation.py .claude/commands/automation.md scripts/tests/test_automation_method.py
git commit -m "automation: demo/real no longer erase the chosen method preset"
```

---

### Task 7: `automation.py instrument set` — lệnh gộp cho menu chọn nhiều cặp

**Files:**
- Modify: `scripts/automation.py` (thêm `cmd_instrument_set`, đăng ký parser)
- Create: `scripts/tests/test_automation_instrument_set.py`

Đọc trước: spec §4.6; rule **CFG-11, CFG-12, CFG-13, CFG-14, CFG-15**.

- [ ] **Step 1: Viết test thất bại**

Tạo `scripts/tests/test_automation_instrument_set.py`:

```python
"""`automation.py instrument set` -- the declarative batch behind the panel's multi-select.
Rules CFG-11..CFG-15 in docs/security/2026-09-12-method-panel.md. The batch re-validates independently of
any caller: a future caller may not be the cron."""
import json, os, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import instruments as I

AUTO = os.path.join(ROOT, "scripts", "automation.py")
CONFIG = os.path.join(ROOT, "docs", "architecture", "automation-config.json")


class InstrumentSet(unittest.TestCase):
    def setUp(self):
        self.backup = tempfile.NamedTemporaryFile(delete=False).name
        shutil.copy(CONFIG, self.backup)

    def tearDown(self):
        shutil.copy(self.backup, CONFIG); os.unlink(self.backup)

    def run_auto(self, *args):
        return subprocess.run([sys.executable, AUTO, *args], capture_output=True, text=True)

    def cfg(self):
        return json.load(open(CONFIG, encoding="utf-8"))

    def test_sets_the_whole_list_in_one_history_row(self):
        before = len(self.cfg()["history"])
        r = self.run_auto("instrument", "set", "BTCUSDT,ETHUSDT,SOLUSDT", "--market", "crypto")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.cfg()["markets"]["crypto"]["instruments"], ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
        self.assertEqual(len(self.cfg()["history"]), before + 1, "CFG-11: one batch, one row")

    def test_output_order_is_the_allowlist_order_not_the_input_order(self):
        """CFG-13: a canonical order makes 'did this change?' a value comparison, not a set comparison."""
        self.run_auto("instrument", "set", "SOLUSDT,BTCUSDT", "--market", "crypto")
        self.assertEqual(self.cfg()["markets"]["crypto"]["instruments"], ["BTCUSDT", "SOLUSDT"])

    def test_setting_the_same_list_again_records_nothing(self):
        """CFG-13: a true no-op must not spend a row of the 200-row audit ring."""
        self.run_auto("instrument", "set", "BTCUSDT", "--market", "crypto")
        n = len(self.cfg()["history"])
        r = self.run_auto("instrument", "set", "BTCUSDT", "--market", "crypto")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(len(self.cfg()["history"]), n, "a no-op recorded a history row")

    def test_forex_anywhere_in_the_batch_refuses_the_whole_batch(self):
        """CFG-11 + CFG-12: all-or-nothing, and Forex is refused by the script regardless of caller."""
        before = self.cfg()["markets"]["crypto"]["instruments"]
        r = self.run_auto("instrument", "set", "BTCUSDT,EURUSD", "--market", "crypto")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("Forex", r.stdout + r.stderr)
        self.assertEqual(self.cfg()["markets"]["crypto"]["instruments"], before, "partial batch applied")

    def test_off_allowlist_symbol_refuses_the_whole_batch(self):
        before = self.cfg()["markets"]["crypto"]["instruments"]
        r = self.run_auto("instrument", "set", "BTCUSDT,DOGEUSDT", "--market", "crypto")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.cfg()["markets"]["crypto"]["instruments"], before)

    def test_symbol_from_the_other_market_is_refused(self):
        r = self.run_auto("instrument", "set", "BTCUSDT,XAUUSD", "--market", "crypto")
        self.assertEqual(r.returncode, 2)

    def test_lowercase_is_refused_not_silently_normalised(self):
        """CFG-12: no normalisation of untrusted input -- accept the canonical spelling or refuse."""
        r = self.run_auto("instrument", "set", "btcusdt", "--market", "crypto")
        self.assertEqual(r.returncode, 2)

    def test_duplicates_are_refused(self):
        r = self.run_auto("instrument", "set", "BTCUSDT,BTCUSDT", "--market", "crypto")
        self.assertEqual(r.returncode, 2)

    def test_empty_list_is_allowed_and_explicit(self):
        """CFG-14: no instruments = no new entries in that market. A narrowing, and the safe direction."""
        r = self.run_auto("instrument", "set", "", "--market", "crypto")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.cfg()["markets"]["crypto"]["instruments"], [])
        self.assertEqual(self.cfg()["history"][-1]["result"], "applied")

    def test_never_adds_a_symbol_absent_from_instruments_json(self):
        """CFG-15: instruments.json is the ceiling; this command can never raise it."""
        for m in I.MARKETS:
            self.run_auto("instrument", "set", ",".join(I.analysis(m)), "--market", m)
            self.assertTrue(set(self.cfg()["markets"][m]["instruments"]) <= set(I.analysis(m)))
```

- [ ] **Step 2: Chạy để chắc chắn nó fail**

Run: `python3 -m pytest scripts/tests/test_automation_instrument_set.py -q`
Expected: FAIL — `instrument set` chưa tồn tại

- [ ] **Step 3: Thêm `cmd_instrument_set` vào `scripts/automation.py`**

Đặt ngay sau `cmd_instrument` (`:1028`):

```python
def cmd_instrument_set(a):
    """Declarative batch: `instrument set BTCUSDT,ETHUSDT --market crypto` replaces the whole list in ONE
    write and ONE history row (CFG-11). The single-symbol form stays for terminal use; this one exists
    because the panel sends a full desired set and nine symbols must not cost nine rows of a 200-row ring.

    Validation is re-done here, independently of whoever called (CFG-12): a future caller may not be the
    applier cron. Nothing is normalised -- a value either is the canonical allowlist spelling or is refused."""
    m = a.market
    raw = [s for s in (a.symbols or "").split(",") if s != ""]
    universe = MARKET_INSTRUMENTS[m]
    problems = []
    for sym in raw:
        if sym[:3] in FX_CODES and sym[3:6] in FX_CODES:
            problems.append(f"{sym}: Forex is prohibited outright (SYSTEM-DESIGN.md §1)")
        elif sym not in universe:
            problems.append(f"{sym}: not on the {m} allowlist ({', '.join(universe)})")
    if len(set(raw)) != len(raw):
        problems.append(f"duplicate symbols in {','.join(raw)}")

    cfg, _, _ = load()
    if problems:                                        # CFG-11: all-or-nothing, config untouched
        record(cfg, a, f"instrument set {','.join(raw) or '(none)'} --market {m}", "refused")
        save(cfg)
        print("REFUSED: " + "; ".join(problems), file=sys.stderr)
        show(cfg, True)
        return 2

    want = [s for s in universe if s in set(raw)]       # CFG-13: canonical order
    if cfg["markets"][m]["instruments"] == want:
        print(f"no-op: {m} instruments already {', '.join(want) or '(none)'}")
        return 0                                        # CFG-13: a true no-op records nothing
    cfg["markets"][m]["instruments"] = want
    record(cfg, a, f"instrument set {','.join(want) or '(none)'} --market {m}", "applied")
    save(cfg)
    for sym in want:
        probe = os.path.join(ROOT, "data", "live", DATA_DIR[m], f"ohlcv.{sym}.15m.json")
        if not os.path.exists(probe):
            print(f"  NOTE: no data on disk for {sym} yet ({rel(probe)}). The flag is set; the source is not wired.")
    if not want:
        print(f"  NOTE: {m} has no instruments selected -- no NEW entries will be opened there. Positions and "
              f"pending orders already open are still managed (strategy-runner.py:766-767).")
    show(cfg, True)
    return 0
```

Đăng ký parser — `instrument` giờ có hai dạng, nên dùng subparser lồng hoặc kiểm positional. Cách đơn giản và rõ:

```python
    p = audited(sub.add_parser("instrument"))
    p.add_argument("symbol", help="a SYMBOL, or the literal word 'set'")
    p.add_argument("value", help="on|off for a single symbol; the comma-separated list when symbol is 'set'")
    p.add_argument("--market", choices=MARKETS)
```

và trong `main()`:

```python
    if a.cmd == "instrument":
        if a.symbol == "set":
            if not a.market:
                print("usage: instrument set <SYM,SYM,...> --market <crypto|cfd>", file=sys.stderr)
                return 1
            a.symbols = a.value
            return cmd_instrument_set(a)
        return cmd_instrument(a)
```

> `instrument set "" --market crypto` truyền chuỗi rỗng làm `value`, nên `argparse` vẫn nhận đủ hai positional.

- [ ] **Step 4: Chạy test**

Run: `python3 -m pytest scripts/tests/ -q`
Expected: toàn bộ xanh

- [ ] **Step 5: Commit**

```bash
git add scripts/automation.py scripts/tests/test_automation_instrument_set.py
git commit -m "automation: instrument set batch -- one write, one row, all-or-nothing, re-validated"
```

---

### Task 8: `strategy-runner.py` — lọc method ở bước 3, không bao giờ ở `load_setups()`

**Files:**
- Modify: `scripts/strategy-runner.py:86` (`METHODS`), `:717-719` (early return), `:833` (bước 3), `:952` (`--list`)
- Test: `scripts/tests/test_strategy_runner.py` (thêm class)

Đọc trước: spec §2.2 và §4.3. **Đây là task có rủi ro cao nhất trong plan.**

> Vì sao: `:718-719` `if not setups_cfg: return` nằm trước khối huỷ pending của STOP file (`:720`), trước `automation_gate()` (`:728`), trước quản lý vị thế (`:781`) và pending (`:786`). Lọc ở `load_setups()` sẽ khiến một preset hẹp làm tick thoát sớm: vị thế mở mất breakeven và time stop, còn một lệnh limit futures đang chờ khớp thành vị thế **không stop** (`place_limit:543` chỉ gửi `open-long-limit`; SL/TP đặt ở `open_position:596-597` sau khi thấy khớp).

- [ ] **Step 1: Viết test thất bại**

Thêm vào `scripts/tests/test_strategy_runner.py`:

```python
class PresetFilter(unittest.TestCase):
    """The preset filters NEW signals only. An open position taken under a previous preset must still be
    managed -- spec §2.2, the sharpest bug the design review caught."""

    def cfg_with(self, dims, instruments=("BTCUSDT",)):
        return {"enabled": True, "layers": {"pilot": True},
                "markets": {"crypto": {"enabled": True, "instruments": list(instruments), "dimensions": dims},
                            "cfd": {"enabled": False, "instruments": [], "dimensions": {"wyckoff": True, "ict": True}}},
                "execution": {"environment": "demo", "pilot_profile": "top5"}}

    def _with_config(self, cfg, fn):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(cfg, tmp); tmp.close()
        old = sr.AUTOMATION_CONFIG; sr.AUTOMATION_CONFIG = tmp.name
        try:
            return fn()
        finally:
            sr.AUTOMATION_CONFIG = old; os.unlink(tmp.name)

    def test_load_setups_is_never_preset_filtered(self):
        """Filtering there would narrow replay parity, --list and the loop period. Spec §4.3."""
        cfg = self.cfg_with({"wyckoff": False, "ict": False, "footprint": False, "heatmap": False})
        n = self._with_config(cfg, lambda: len(sr.load_setups()))
        self.assertGreater(n, 0, "load_setups() must return the selection regardless of preset")

    def test_allowed_methods_reflects_the_preset(self):
        wy = self.cfg_with({"wyckoff": True, "ict": False, "footprint": False, "heatmap": False})
        got = self._with_config(wy, lambda: sr.allowed_methods("crypto"))
        self.assertEqual(got, {"WYCKOFF", "WYCKOFF-BOOK"})
        none = self.cfg_with({"wyckoff": False, "ict": False, "footprint": False, "heatmap": False})
        self.assertEqual(self._with_config(none, lambda: sr.allowed_methods("crypto")), set())

    def test_tick_still_manages_an_open_position_when_the_preset_blocks_every_method(self):
        """The regression that matters: no early return before step 1/2."""
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        head = src[src.index("def tick("):src.index("    # 1. positions")]
        self.assertNotIn("no runnable setup", head,
                         "the empty-setups early return still precedes position management")

    def test_step_three_filters_by_allowed_methods(self):
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        body = src[src.index("    # 3. signals"):]
        self.assertIn("allowed_methods", body.split("def ")[0])

    def test_unticked_instrument_with_an_open_position_still_gets_candles(self):
        """Instrument narrowing grandfathers too: :766-767 adds every symbol holding a position or a pending
        order to the candle need set WITHOUT consulting enabled_symbols. Lock that in."""
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        head = src[src.index("    need = set()"):src.index("    # 1. positions")]
        self.assertIn('s["positions"].items()', head)
        self.assertIn('s["pending"].items()', head)

    def test_enabled_symbols_narrows_but_never_widens(self):
        cfg = self.cfg_with({"wyckoff": True, "ict": True, "footprint": False, "heatmap": False},
                            instruments=("BTCUSDT",))
        got = self._with_config(cfg, lambda: sr.enabled_symbols("crypto"))
        self.assertEqual(got, ["BTCUSDT"])
        empty = self.cfg_with({"wyckoff": True, "ict": True, "footprint": False, "heatmap": False},
                              instruments=())
        self.assertEqual(self._with_config(empty, lambda: sr.enabled_symbols("crypto")), [])


class ScanDispatchFromRegistry(unittest.TestCase):
    def test_no_hard_coded_method_tuple_picks_the_scanner(self):
        """Adding a runner method must be a registry entry plus a scan function, not another if/elif arm."""
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        self.assertNotIn('st["method"] in ("ICT", "COMBINED")', src)
        self.assertNotIn('in ("WYCKOFF", "WYCKOFF-BOOK")', src)
        self.assertIn("scan_of", src)
```

- [ ] **Step 2: Chạy để chắc chắn nó fail**

Run: `python3 -m pytest scripts/tests/test_strategy_runner.py -q -k PresetFilter`
Expected: FAIL — `sr.allowed_methods` chưa tồn tại

- [ ] **Step 3: Sửa `scripts/strategy-runner.py`**

`:86` đổi `METHODS` sang registry (module `methods.py` nạp cùng kiểu với `instruments`):

```python
_mspec = importlib.util.spec_from_file_location("methods", os.path.join(ROOT, "scripts", "methods.py"))
mreg = importlib.util.module_from_spec(_mspec); _mspec.loader.exec_module(mreg)
METHODS = tuple(sorted(mreg.runnable()))   # ICT/COMBINED = limit at the FVG edge; WYCKOFF* = market at the bar close
```

Thêm hàm mới cạnh `enabled_symbols` (`:175`):

```python
def allowed_methods(market):
    """Runner methods the current method preset permits for this market. Empty set = no NEW entries; open
    positions and pending orders are still managed (spec §4.3, grandfather)."""
    try:
        c = json.load(open(AUTOMATION_CONFIG, encoding="utf-8"))
        dims = c.get("markets", {}).get(market, {}).get("dimensions", {})
    except Exception:
        return set(METHODS)                    # unconfigured = behave exactly as before this switch existed
    return mreg.runner_methods(dims) & set(METHODS)
```

Ở `:717-719`, **bỏ** early return:

```python
def tick(live, tick_time=None, ignore_gate=False):
    s = load_state(); setups_cfg = load_setups()
    # NO early return on an empty selection: steps 1 and 2 below manage positions and pending orders that were
    # opened under a previous configuration, and a resting futures limit carries no stop until open_position()
    # sees it fill (place_limit:543 vs open_position:596). Returning here would leave it naked. Spec §2.2.
```

Ở `:833`, lọc bước 3:

```python
    # 3. signals -- the preset filters NEW entries only (spec §4.3); steps 1 and 2 above are never filtered.
    for st in setups_cfg:
        if st["method"] not in allowed_methods(st["market"]):
            log("preset_filtered", setup=st["id"], market=st["market"], method=st["method"],
                why="method not permitted by the current method preset")
            continue
        if not due(st["tf"], t, st["market"]):
            continue
```

Ở `:842` và `:905`, bỏ hai chỗ chọn scanner bằng bộ tên cứng, dùng trường `scan` của registry:

```python
# :842 (tick, step 3) -- was: ... if st["method"] in ("ICT", "COMBINED") else setups_wyckoff(...)
sigs = (setups(st["method"], side, c, st["tf"], st.get("ict_target") or "range", st.get("ict_disp", False),
               st.get("ict_pd", False), st.get("std_origin") or "pivot")
        if mreg.scan_of(st["method"]) == "ict" else setups_wyckoff(st["method"], side, c, st["tf"]))
```

```python
# :901 and :905 (replay) -- was: wy = st["method"] in ("WYCKOFF", "WYCKOFF-BOOK")
wy = mreg.scan_of(st["method"]) == "wyckoff"
```

Dòng `:953` dựng `flags` cũng dùng cùng điều kiện:

```python
flags = (f" disp={st.get('ict_disp', False)} pd={st.get('ict_pd', False)} "
         f"std_origin={st.get('std_origin', 'pivot')}") if mreg.scan_of(st["method"]) == "ict" else ""
```

Ở `:952` (`--list`), chú thích thay vì giấu dòng:

```python
            blocked = "" if st["method"] in allowed_methods(st["market"]) else "  [preset: blocked]"
            print(f"{st.get('rank', '-')}. {st['id']}: ... symbols={','.join(st['symbols'])}{blocked}")
```
(giữ nguyên phần `...` đang có, chỉ nối thêm `{blocked}`)

- [ ] **Step 4: Chạy test**

Run: `python3 -m pytest scripts/tests/ -q`
Expected: toàn bộ xanh — **đặc biệt `ParityWithBacktest` phải còn xanh**, nó chứng minh `load_setups()` không bị bóp méo

- [ ] **Step 5: Kiểm tay bằng dry run**

Run:
```bash
python3 scripts/automation.py method wyckoff --market crypto
python3 scripts/strategy-runner.py --list | tail -5
git checkout docs/architecture/automation-config.json
```
Expected: setup dùng `ICT`/`COMBINED` hiện `[preset: blocked]`, setup `WYCKOFF*` thì không

- [ ] **Step 6: Commit**

```bash
git add scripts/strategy-runner.py scripts/tests/test_strategy_runner.py
git commit -m "runner: preset filters new signals at tick step 3; open positions are grandfathered"
```

---

### Task 9: `rank-setups.py` lấy `RUNNABLE` từ registry

**Files:**
- Modify: `scripts/rank-setups.py:35`
- Test: `scripts/tests/test_methods.py` (thêm vào class `AutomationUsesRegistry`)

- [ ] **Step 1: Viết test thất bại**

Thêm vào class `AutomationUsesRegistry` trong `scripts/tests/test_methods.py`:

```python
    def test_rank_setups_has_no_second_method_list(self):
        src = open(os.path.join(ROOT, "scripts", "rank-setups.py"), encoding="utf-8").read()
        self.assertNotIn('{"ICT", "COMBINED", "WYCKOFF", "WYCKOFF-BOOK"}', src)
        self.assertIn("methods", src)
```

- [ ] **Step 2: Chạy để chắc chắn nó fail**

Run: `python3 -m pytest scripts/tests/test_methods.py -q -k rank_setups`
Expected: FAIL

- [ ] **Step 3: Sửa `scripts/rank-setups.py:35`**

```python
_mspec = importlib.util.spec_from_file_location("methods", os.path.join(ROOT, "scripts", "methods.py"))
mreg = importlib.util.module_from_spec(_mspec); _mspec.loader.exec_module(mreg)
RUNNABLE = mreg.runnable()   # executed by scripts/strategy-runner.py; source: docs/architecture/methods.json
```
(thêm `import importlib.util` nếu file chưa có)

- [ ] **Step 4: Chạy test**

Run: `python3 -m pytest scripts/tests/ -q`
Expected: toàn bộ xanh

- [ ] **Step 5: Commit**

```bash
git add scripts/rank-setups.py scripts/tests/test_methods.py
git commit -m "rank-setups: the runnable method set comes from the registry"
```

---

### Task 10: Cờ `wyckoff`/`ict` thành cờ thật trong trang chart

**Files:**
- Modify: `scripts/build-artifact.py:90` (`LANES`), `:281` (`matrix`), `:677-690` (vòng `dims`)
- Test: `scripts/tests/test_build_artifact.py` (thêm test)

Đọc trước: spec §2.1, §4.2.

- [ ] **Step 1: Viết test thất bại**

Thêm vào `scripts/tests/test_build_artifact.py`:

```python
class DimensionFlagsAreReal(unittest.TestCase):
    def test_lanes_come_from_the_registry(self):
        src = open(os.path.join(ROOT, "scripts", "build-artifact.py"), encoding="utf-8").read()
        self.assertNotIn('[("wyckoff", "Wyckoff"), ("ict", "ICT")', src)

    def test_matrix_columns_drop_a_disengaged_wyckoff_or_ict(self):
        """Before this, cols hardcoded ["wyckoff","ict"], so turning the flags off changed nothing."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("ba", os.path.join(ROOT, "scripts", "build-artifact.py"))
        ba = importlib.util.module_from_spec(spec); spec.loader.exec_module(ba)
        dims = {d: {"engaged": d == "wyckoff", "reason": ""} for d in ("wyckoff", "ict", "footprint", "heatmap")}
        html = ba.matrix("btc", "int", None, None, None, dims)
        self.assertIn("lane-wyckoff", html)
        self.assertNotIn("lane-ict", html)
```

- [ ] **Step 2: Chạy để chắc chắn nó fail**

Run: `python3 -m pytest scripts/tests/test_build_artifact.py -q -k DimensionFlags`
Expected: FAIL

- [ ] **Step 3: Sửa `scripts/build-artifact.py`**

`:90`:
```python
LANES = [(d, v["label"]) for d, v in _methods.DIMENSIONS.items()]   # source: docs/architecture/methods.json
```
(nạp `_methods` cạnh chỗ đã nạp `_auto`, cùng kiểu `importlib.util`)

`:281`:
```python
    cols = [c for c, _ in LANES if dims.get(c, {}).get("engaged")] or [c for c, _ in LANES]
```

`:677-690`: vòng `for m in ("footprint", "heatmap")` phủ cả bốn lane. Thay nguyên khối bằng:

```python
        dims = {}
        for m, _label in LANES:
            flag = dim_flags.get(m)
            coinglass = "coinglass_footprint" in _methods.DIMENSIONS[m]["data_sources"] \
                or "coinglass_heatmap" in _methods.DIMENSIONS[m]["data_sources"]
            has = bool((n3 or {}).get(m, {}).get("text_html")) or bool((l2 or {}).get(m))
            # wyckoff/ict read the candle file the page is already drawing, so "available" is not a
            # CoinGlass question for them; footprint/heatmap keep the status check they had.
            avail = (((n3 or {}).get(m) or {}).get("status") == "available") if coinglass else bool(rows)
            if market not in _methods.DIMENSIONS[m]["markets"]:
                reason = "không có nguồn CoinGlass cho hàng hoá (SYSTEM-DESIGN §12)"
            elif flag is False:
                reason = f"tắt trong /automation (preset {_methods.profile_of(dim_flags)})"
            elif not avail:
                reason = ("không có nguồn CoinGlass live — không vẽ, không chấm điểm" if coinglass
                          else "không có nến cho khung này")
            else:
                reason = ""
            engaged = bool(avail and flag is not False and market in _methods.DIMENSIONS[m]["markets"])
            dims[m] = {"engaged": engaged and (has or not coinglass), "reason": reason or "đang dùng"}
```

> Khác biệt so với bản cũ: `has` (có prose của model) vẫn bắt buộc với footprint/heatmap như trước, nhưng không bắt buộc với wyckoff/ict — hai lane đó luôn vẽ được từ nến kể cả khi chưa có bài đọc của model, đúng như hành vi hôm nay.

- [ ] **Step 4: Chạy test và dựng thử một trang**

Run:
```bash
python3 -m pytest scripts/tests/ -q
python3 scripts/build-artifact.py daytrade --out /tmp/t.html --check-only && echo BUILD_OK
```
Expected: test xanh; build in `BUILD OK` (hoặc báo thiếu dữ liệu đầu vào — chấp nhận được, miễn không phải TypeError/KeyError)

- [ ] **Step 5: Commit**

```bash
git add scripts/build-artifact.py scripts/tests/test_build_artifact.py
git commit -m "artifact: chart lanes come from the registry and honour the wyckoff/ict flags"
```

---

### Task 11: `methods.py --dispatch-plan` và bước 5 của `/analyze`

**Files:**
- Modify: `scripts/methods.py` (thêm `dispatch_plan` + CLI), `.claude/commands/analyze.md:25-32`
- Test: `scripts/tests/test_methods.py` (thêm class)

Đọc trước: spec §4.2.

- [ ] **Step 1: Viết test thất bại**

Thêm vào `scripts/tests/test_methods.py`:

```python
class DispatchPlan(unittest.TestCase):
    def plan(self, instrument, cfg):
        import json, tempfile
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(cfg, tmp); tmp.close()
        try:
            return M.dispatch_plan(instrument, config_path=tmp.name)
        finally:
            os.unlink(tmp.name)

    def base(self, crypto_dims):
        return {"markets": {"crypto": {"enabled": True, "dimensions": crypto_dims},
                            "cfd": {"enabled": True, "dimensions": {"wyckoff": True, "ict": True}}}}

    def test_cfd_never_dispatches_coinglass_agents(self):
        p = self.plan("XAUUSD", self.base({"wyckoff": True, "ict": True, "footprint": True, "heatmap": True}))
        self.assertNotIn("flow-agent", p["dispatch"])
        self.assertNotIn("liquidity-agent", p["dispatch"])
        self.assertTrue(any("CoinGlass" in r for r in p["skipped"].values()))

    def test_a_disabled_dimension_is_skipped_with_a_reason(self):
        p = self.plan("BTCUSDT", self.base({"wyckoff": True, "ict": False, "footprint": True, "heatmap": False}))
        self.assertIn("ict", p["skipped"])
        self.assertIn("heatmap", p["skipped"])
        self.assertIn("flow-agent", p["dispatch"])

    def test_structure_agent_is_dropped_when_both_its_dimensions_are_off(self):
        p = self.plan("BTCUSDT", self.base({"wyckoff": False, "ict": False, "footprint": True, "heatmap": True}))
        self.assertNotIn("structure-agent", p["dispatch"])

    def test_plan_reports_the_engaged_count_and_the_normal_minimum(self):
        p = self.plan("BTCUSDT", self.base({"wyckoff": True, "ict": False, "footprint": False, "heatmap": False}))
        self.assertEqual(p["engaged_count"], 1)
        self.assertFalse(p["meets_normal_minimum"])
```

- [ ] **Step 2: Chạy để chắc chắn nó fail**

Run: `python3 -m pytest scripts/tests/test_methods.py -q -k DispatchPlan`
Expected: FAIL — `M.dispatch_plan` chưa tồn tại

- [ ] **Step 3: Thêm vào `scripts/methods.py`**

```python
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "docs", "architecture", "automation-config.json")
NORMAL_MINIMUM = 2          # SYSTEM-DESIGN.md §6.1


def dispatch_plan(instrument, config_path=None):
    """Which read-only agents /analyze must dispatch for this instrument, and why each skipped one is skipped.
    The gating logic lives here so .claude/commands/analyze.md does not have to be edited when a dimension is
    added (spec §4.2). A missing config means UNCONFIGURED: dispatch everything, as before the switch existed."""
    import json as _json
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import instruments as _I
    market = _I.market_of(instrument)
    if market is None:
        raise ValueError(f"{instrument} is not on the allowlist (docs/architecture/instruments.json)")
    try:
        with open(config_path or CONFIG_PATH, encoding="utf-8") as fh:
            flags = (_json.load(fh).get("markets", {}).get(market, {}) or {}).get("dimensions", {})
    except (OSError, ValueError):
        flags = {d: True for d in dimensions(market)}
    dispatch, skipped, engaged = [], {}, []
    for d in ALL_DIMENSIONS:
        agent = DIMENSIONS[d]["agent"]
        if market not in DIMENSIONS[d]["markets"]:
            skipped[d] = (f"{market} has no source for {d} -- CoinGlass is crypto-derivatives only "
                          f"(SYSTEM-DESIGN.md §12 item 3)")
        elif not flags.get(d, True):
            skipped[d] = f"dimensions.{d} is off in /automation (method preset "\
                         f"{profile_of({k: flags.get(k, True) for k in ALL_DIMENSIONS})})"
        else:
            engaged.append(d)
            if agent not in dispatch:
                dispatch.append(agent)
    return {"instrument": instrument, "market": market, "dispatch": dispatch, "skipped": skipped,
            "engaged": engaged, "engaged_count": len(engaged),
            "meets_normal_minimum": len(engaged) >= NORMAL_MINIMUM,
            "preset": profile_of({k: flags.get(k, True) for k in ALL_DIMENSIONS})}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Method registry reader.")
    ap.add_argument("--dispatch-plan", metavar="INSTRUMENT")
    args = ap.parse_args()
    if args.dispatch_plan:
        p = dispatch_plan(args.dispatch_plan)
        print(f"instrument: {p['instrument']} ({p['market']})   method preset: {p['preset']}")
        print(f"DISPATCH:   {', '.join(p['dispatch']) or '(none)'}")
        for d, why in p["skipped"].items():
            print(f"SKIP {d}: {why}")
        print(f"engaged_count = {p['engaged_count']}; NORMAL minimum {NORMAL_MINIMUM} "
              f"{'met' if p['meets_normal_minimum'] else 'NOT met -- verdict is NO TRADE on count alone'}")
```

Thêm `import sys` vào đầu `scripts/methods.py`.

- [ ] **Step 4: Sửa `.claude/commands/analyze.md` bước 5**

Thay ba gạch đầu dòng liệt kê agent bằng:

```markdown
5. **Dispatch the read-only agents** (single message, parallel Agent tool calls where the harness supports it).
   **First run `python3 scripts/methods.py --dispatch-plan <INSTRUMENT>`.** It prints the method preset in force,
   a `DISPATCH:` line naming exactly which agents to dispatch, one `SKIP <dimension>:` line per skipped dimension
   with the reason, and the engaged count against the NORMAL minimum. Dispatch exactly what `DISPATCH:` names and
   nothing else; pass each agent the instrument, the timeframes, the data-source paths, and (for flow-agent) the
   anchor candle structure-agent identified. **Reproduce every `SKIP` line verbatim in your output**, and remind
   the reader that a skipped dimension lowers `engaged_count`, which can fall below the locked mode's minimum
   (NORMAL ≥2, ENHANCED/STRICT ≥3, §6.1/§6.2) and force NO TRADE on count alone — a configuration outcome, not a
   market read. Do not maintain a list of agents in this file; the registry
   (`docs/architecture/methods.json`) is the source, so adding a dimension needs no edit here.
```

- [ ] **Step 5: Chạy test và thử CLI**

Run:
```bash
python3 -m pytest scripts/tests/ -q
python3 scripts/methods.py --dispatch-plan BTCUSDT
python3 scripts/methods.py --dispatch-plan XAUUSD
```
Expected: test xanh; XAUUSD in hai dòng `SKIP footprint:` và `SKIP heatmap:` nêu lý do CoinGlass

- [ ] **Step 6: Commit**

```bash
git add scripts/methods.py .claude/commands/analyze.md scripts/tests/test_methods.py
git commit -m "analyze: agent dispatch derives from the registry; the wyckoff/ict flags finally gate something"
```

---

### Task 12: Metadata hiển thị của instrument về `instruments.json`

**Files:**
- Modify: `docs/architecture/instruments.json`, `scripts/instruments.py`, `scripts/build-artifact.py:35-46`
- Test: `scripts/tests/test_instruments_sync.py` (thêm test)

Đọc trước: spec §3.4.

- [ ] **Step 1: Viết test thất bại**

Thêm vào `scripts/tests/test_instruments_sync.py`:

```python
class DisplayMetadata(unittest.TestCase):
    def test_every_allowlisted_symbol_has_display_metadata(self):
        """build-artifact.py used to keep a parallel hand-kept CRYPTO_META dict and index it directly, so a
        symbol added to instruments.json crashed the build with a KeyError."""
        for sym in I.analysis():
            d = I.display(sym)
            self.assertTrue(d["id"] and d["label"])
            self.assertIsInstance(d["price_decimals"], int)

    def test_display_falls_back_without_an_entry(self):
        d = I.display("ZZZUSDT")
        self.assertEqual(d["id"], "zzz")
        self.assertEqual(d["price_decimals"], 2)

    def test_build_artifact_has_no_parallel_symbol_table(self):
        src = open(os.path.join(ROOT, "scripts", "build-artifact.py"), encoding="utf-8").read()
        self.assertNotIn("CRYPTO_META = {", src)
```

- [ ] **Step 2: Chạy để chắc chắn nó fail**

Run: `python3 -m pytest scripts/tests/test_instruments_sync.py -q -k Display`
Expected: FAIL — `I.display` chưa tồn tại

- [ ] **Step 3: Thêm khối `display` vào `docs/architecture/instruments.json`**

Thêm ở cấp cao nhất (chỉ ghi đè khi mặc định suy ra sai):

```json
  "display": {
    "_comment": "OPTIONAL presentation metadata. A symbol with no entry gets id = lowercase symbol minus the USDT suffix, label = the symbol, price_decimals = 2. Override only when the default is wrong.",
    "BTCUSDT":   { "label": "BTC/USDT", "price_decimals": 0 },
    "ETHUSDT":   { "label": "ETH/USDT" },
    "SOLUSDT":   { "label": "SOL/USDT" },
    "ASTERUSDT": { "label": "ASTER/USDT" },
    "VIRTUALUSDT": { "label": "VIRTUAL/USDT" },
    "SUIUSDT":   { "label": "SUI/USDT" },
    "TAOUSDT":   { "label": "TAO/USDT" },
    "RENDERUSDT": { "label": "RENDER/USDT" },
    "ONDOUSDT":  { "label": "ONDO/USDT" },
    "XAUUSD":    { "label": "XAU/USD" },
    "XAGUSD":    { "label": "XAG/USD" },
    "USOIL":     { "label": "USOIL" },
    "UKOIL":     { "label": "UKOIL" }
  },
```

> `price_decimals: 0` cho BTCUSDT khớp với `"int"` mà `CRYPTO_META` đang dùng; các symbol khác đang dùng `"2"` nên rơi vào mặc định.

- [ ] **Step 4: Thêm `display()` vào `scripts/instruments.py`**

```python
_DISPLAY = {k: v for k, v in (_DATA.get("display") or {}).items() if not k.startswith("_")}


def display(symbol):
    """Presentation metadata, with a derived default so adding a symbol needs no second edit anywhere."""
    over = _DISPLAY.get(symbol, {})
    base = symbol[:-4].lower() if symbol.endswith("USDT") else symbol.lower()
    return {"id": over.get("id", base),
            "label": over.get("label", symbol),
            "price_decimals": int(over.get("price_decimals", 2))}
```

- [ ] **Step 5: Sửa `scripts/build-artifact.py:35-46`**

Xoá cả dict `CRYPTO_META` và thay hai dòng dựng danh sách:

```python
def _meta(sym):
    d = I.display(sym)
    return (sym, d["id"], d["label"], "int" if d["price_decimals"] == 0 else "2")


CRYPTO = [_meta(sym) for sym in I.analysis("crypto")]
GOLD = [_meta("XAUUSD")]
```

- [ ] **Step 6: Chạy test và dựng thử**

Run:
```bash
python3 -m pytest scripts/tests/ -q
python3 scripts/build-artifact.py daytrade --out /tmp/t.html --check-only && echo BUILD_OK
```
Expected: test xanh; build không KeyError

- [ ] **Step 7: Commit**

```bash
git add docs/architecture/instruments.json scripts/instruments.py scripts/build-artifact.py scripts/tests/test_instruments_sync.py
git commit -m "instruments: display metadata joins the single source; adding a symbol needs one file again"
```

---

### Task 13: Cập nhật tài liệu kiến trúc

**Files:**
- Modify: `docs/architecture/SYSTEM-DESIGN.md:102-110` (§6.2 rubric), `:203` (§12 item 6), `:174` (bảng `/automation`)
- Modify: `.claude/commands/automation.md` (mục lệnh)

- [ ] **Step 1: Tổng quát hoá công thức §6.2**

Ở `:107`, thay `(engaged_count × 25)` bằng tổng `max_points` lấy từ registry:

```markdown
2. `raw_pct = (sum of points across engaged dimensions / sum of those dimensions' max_points) × 100` — the
   per-dimension maximum is `docs/architecture/methods.json` `dimensions.<name>.max_points` (25 for all four
   today), so adding a fifth dimension needs no change to this formula. E.g. 3 engaged dimensions scoring
   22/25 each → raw_pct = 66/75 × 100 = **88** … (phần còn lại giữ nguyên)
```

- [ ] **Step 2: Sửa dòng đã cũ ở §12 item 6 (`:203`)**

Thay cụm "today only XAUUSD is exported (`data/live/mt5-bridge/`)" bằng:

```markdown
today XAUUSD and XAGUSD are exported (`data/live/mt5-bridge/`, verified 2026-09-12); USOIL/UKOIL still have none
```

Kiểm lại trước khi ghi: `ls data/live/mt5-bridge/*.json | sed 's/.*ohlcv\.//;s/\..*//' | sort -u`

- [ ] **Step 3: Thêm hai subcommand vào bảng `/automation` (`:174`) và `.claude/commands/automation.md`**

Thêm vào danh sách subcommand trong docstring của `scripts/automation.py` và trong `.claude/commands/automation.md`:

```
  method <preset> [--market crypto|cfd]          named set of the four dimension flags (docs/architecture/methods.json)
  instrument set <SYM,SYM,...> --market <m>      replace the whole instrument list in one write
  allows master                                  exit 0 if the master switch is on, 2 if off
```

Thêm một đoạn ngắn vào `SYSTEM-DESIGN.md` §6.2 trỏ tới registry:

```markdown
The four dimensions, the runner method table and the named presets live in `docs/architecture/methods.json`
(reader `scripts/methods.py`, regenerator `scripts/sync-methods.py`, drift test
`scripts/tests/test_methods_sync.py`) — the same single-source pattern as `instruments.json`. Nothing else may
hard-code any of the three. Design: `docs/specs/2026-09-12-method-switch-design.md`.
```

- [ ] **Step 4: Chạy toàn bộ test lần cuối**

Run:
```bash
python3 scripts/sync-instruments.py --check && python3 scripts/sync-methods.py --check
python3 -m pytest scripts/tests/ -q
```
Expected: cả hai `--check` exit 0; toàn bộ test xanh

- [ ] **Step 5: Commit**

```bash
git add docs/architecture/SYSTEM-DESIGN.md .claude/commands/automation.md scripts/automation.py
git commit -m "docs: registry pointer, generalised the §6.2 rubric, refreshed the stale MT5 export line"
```

---

## Sau plan này

Plan B (`docs/plans/2026-09-12-method-panel.md`, viết sau khi plan này xong) phủ §4.4 và §4.5 của spec: `scripts/method-panel.py` dựng trang Artifact có `db` với `rules: [{path: "", read: "owner", write: "owner"}]`, và `integrations/crons/method-switch.md`. Nó tiêu thụ đúng cái CLI mà plan này vừa tạo (`method`, `instrument set`, `allows master`) và các rule PANEL-*/CRON-* trong mô hình đe doạ.

**Điều kiện tiên quyết trước khi chạy trang không người trông:** CFG-07 (lưu trữ dòng history bị đẩy ra) và CFG-13 (no-op không ghi) đã nằm trong Task 4 và Task 7 của plan này, đúng như mô hình đe doạ yêu cầu.
