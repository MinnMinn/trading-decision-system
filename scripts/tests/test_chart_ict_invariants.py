"""RETIRED by A2 / ADR 0009 (docs/plans/2026-09-28-methodology-improvement-plan.md §2 item A2;
docs/audits/2026-09-29-a2-chart-from-engine.md).

This file used to run chart.js's OWN `ictAnalyze` -- a second, independent ICT detector that duplicated
scripts/ict-scan.py's pivot/pool/FVG/MSS/OTE/σ-projection logic in the browser -- over real stored history and
re-derived every object it produced from the candles it produced them from (see scripts/tests/ict-invariants.js,
now removed). That was real, load-bearing coverage while chart.js had its own detector: the two implementations
had already been found to disagree (docs/audits/2026-09-28-method-fidelity.md §1.1, §3), and nothing forced them
to agree.

ADR 0009 removes that second detector. `ictAnalyze` is gone from chart.js; the chart now draws
`scripts/structures.py` `ict_structures()`'s own objects, forwarded verbatim by `build-artifact.py`
`ict_json()` (see chart.js `ictFromStructures()`, a pure REGROUPING function -- it detects nothing, so there is
nothing left in chart.js for an invariant check like this one to catch). The detection this file used to verify
independently now has exactly ONE implementation (scripts/ict-scan.py `analyze()`), and its correctness is
covered where that implementation lives:
  * scripts/tests/test_audit_round2_ict.py -- ict-scan.py's own detection fidelity against knowledge/ict/*.
  * scripts/tests/test_structures.py `IctStructuresMatchAnalyze`, `ConfirmationDelay`, `AvailableTimeInvariant`
    -- structures.py's `ict_structures()` is byte-identical to a direct `ict_scan.analyze()` call (so any
    invariant already true of ict-scan.py's own output is transitively true of what the chart draws) plus the
    PIT/confirmation-delay properties this file never checked at all.

Nothing here was duplicated forward: this is a retirement notice, not a restatement of the removed checks
(rules/single-source-of-truth.md) -- the two files above are the sources for ICT detection correctness now.
The two checks kept below are chart.js's own remaining, genuinely file-specific facts: the detector is actually
gone, and the two functions that replaced it are pure (no hidden state, no re-detection).
"""
import json
import os
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHART = os.path.join(ROOT, "scripts", "chart.js")


def _node_available():
    try:
        return subprocess.run(["node", "-e", "0"], capture_output=True).returncode == 0
    except Exception:
        return False


class IctDetectionLivesInExactlyOnePlace(unittest.TestCase):
    def test_chart_js_no_longer_carries_its_own_ict_detector(self):
        src = open(CHART, encoding="utf-8").read()
        self.assertNotIn("ictAnalyze", src, "A2/ADR 0009: chart.js must not detect ICT structure itself")

    @unittest.skipUnless(_node_available(), "node not available")
    def test_ict_from_structures_is_pure_no_detection_no_hidden_state(self):
        """ictFromStructures() must be a pure function of (structs, dealing_range, rows): given the same
        engine structures twice, it must regroup them identically -- there is no candle-scanning left for a
        hidden bug to hide in."""
        rows = [[100.0 + i * 0.1, 100.5 + i * 0.1, 99.5 + i * 0.1, 100.2 + i * 0.1, 10.0,
                 f"2026-01-01T{i:02d}:00:00Z"] for i in range(20)]
        structs = [{"kind": "mss", "type": "bull", "i": 10, "level": 100.0, "disp": True}]
        dr = {"hi": 101.0, "lo": 99.0, "eq": 100.0, "source": "window"}
        r = subprocess.run(["node", "-e",
                            f"const T=require({CHART!r});"
                            f"const rows={json.dumps(rows)}, structs={json.dumps(structs)}, dr={json.dumps(dr)};"
                            "const a=T.ictFromStructures(structs,dr,rows), b=T.ictFromStructures(structs,dr,rows);"
                            "process.stdout.write(JSON.stringify(a)===JSON.stringify(b)?'same':'different')"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        self.assertEqual(r.stdout, "same")


if __name__ == "__main__":
    unittest.main()
