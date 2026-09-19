"""CLAUDE.md §42 -- twenty-two fields, ten lifecycle stages, and "Experiment records must be immutable."

Nothing in this repo recorded an experiment at all. Backtests were run by hand, their parameters lived in a
shell history, and the only trace that a candidate had ever been evaluated was a markdown file somebody
remembered to write. §43 (experiment budget) and §44 (OOS exposure) are both impossible on top of that,
because both need to count what was tried.

The tests below attack the three claims separately:

**Completeness** — a record that seals without a seed or a dataset snapshot is not "mostly filed", it is a
result nobody can reproduce (§46). Sealing must be impossible.

**Immutability** — checked three ways, because a convention catches none of them: the sealed mapping raises on
mutation, `write()` refuses an existing path, and `load()` re-checks the content hash. The last is the one
that matters: an edit through an editor or a merge does not go through this module at all.

**A decision is a successor, not an edit.** The experiment as run and the judgement passed on it are two facts
with two timestamps, and the first must survive the second.
"""
import json
import os
import shutil
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import experiment as X
import outcomes as O

REGISTRY = os.path.join(ROOT, "docs", "architecture", "experiments.json")
SRC = open(os.path.join(ROOT, "scripts", "experiment.py"), encoding="utf-8").read()


def _bullets(after, until):
    spec = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
    section = spec.split("42. EXPERIMENT INFRASTRUCTURE", 1)[1].split("43. EXPERIMENT BUDGET", 1)[0]
    body = section.split(after, 1)[1].split(until, 1)[0]
    return [ln[2:].strip() for ln in body.splitlines() if ln.startswith("- ")]


def _full(store=None, **over):
    """A record with every §42 field accounted for -- the only kind that can seal."""
    r = X.Record(hypothesis="a wider stop survives the noise MAE shows",
                 motivation="three repeated stop-outs inside 0.2R of entry",
                 parent_trading_system_version="v1", candidate_version="v1.1",
                 **{k: v for k, v in over.items() if k in ("experiment_id", "at")})
    filler = {
        "failure_pattern": "cluster: setup=crypto-scalping-ict-15m, blocked_on=None, n=4",
        "dataset_snapshot": {"snapshot_id": "abc"}, "configuration_snapshot": {"fields": {}},
        "account_configuration": {"rules": {}}, "risk_configuration": {"max_risk_pct": 0.01},
        "news_configuration": {"pre": 10, "post": 10}, "session_configuration": {"sessions": []},
        "parameters": {"stop_buffer_pct": {"from": 0.0005, "to": 0.0015}},
        "random_seed": 20260918, "test_periods": {"in_sample": "2023-2024", "oos": "2025"},
        "validation_method": "walk-forward", "metrics": {"n": 120, "expectancy": 0.21},
        "robustness_results": X.unavailable("§45 is not implemented"), "system_version": "trading-systems v1",
    }
    filler.update({k: v for k, v in over.items() if k in X.ORDER})
    for k, v in filler.items():
        r.set(k, v)
    return r


class TheRegistryIsTheSpec(unittest.TestCase):
    def test_all_twenty_two_required_fields_are_declared_in_order(self):
        self.assertEqual([X.spec_name(f) for f in X.ORDER],
                         _bullets("Every experiment must record:", "Experiment records must be immutable"))

    def test_the_ten_lifecycle_stages_are_declared_in_order(self):
        self.assertEqual(len(X.LIFECYCLE), 10)
        self.assertEqual(X.STAGE_ORDER[0], "observation")
        self.assertEqual(X.STAGE_ORDER[-1], "approval_rejection")

    def test_every_lifecycle_stage_maps_onto_a_real_41_pipeline_stage(self):
        # Without the mapping the two lists drift into describing different processes.
        for s in X.LIFECYCLE:
            self.assertIn(s["stage_of_41"], O.STAGE_ORDER, s["id"])

    def test_a_registry_stage_with_no_41_mapping_is_refused(self):
        data = json.load(open(REGISTRY, encoding="utf-8"))
        data["lifecycle"][0].pop("stage_of_41")
        p = os.path.join(ROOT, "scripts", "tests", "__mutant-exp.json")
        try:
            json.dump(data, open(p, "w"))
            with self.assertRaises(X.RegistryError):
                X._load(p)
        finally:
            os.remove(p)

    def test_pending_is_declared_and_explained_as_not_one_of_42s_own_words(self):
        self.assertIn(X.PENDING, X.DECISIONS)
        self.assertIn("not one of §42's own words", X._DATA["_pending"])


class CompletenessIsCheckedAtSealTime(unittest.TestCase):
    def test_a_full_record_seals(self):
        self.assertIsInstance(_full().seal(), types.MappingProxyType)

    def test_a_record_missing_any_field_cannot_seal_and_the_error_names_it(self):
        r = _full()
        del r._v["random_seed"]
        with self.assertRaises(X.Incomplete) as cm:
            r.seal()
        self.assertIn("random seed", str(cm.exception))

    def test_every_declared_field_is_individually_required(self):
        # Not a sample: each of the twenty-two must be load-bearing.
        for fid in X.ORDER:
            r = _full()
            del r._v[fid]
            with self.assertRaises(X.Incomplete, msg=fid):
                r.seal()

    def test_a_field_may_be_unavailable_but_must_say_why(self):
        self.assertIn("unavailable", X.unavailable("§45 is not implemented"))
        with self.assertRaises(ValueError):
            X.unavailable("")

    def test_none_is_refused_so_an_absence_cannot_masquerade_as_a_value(self):
        with self.assertRaises(ValueError):
            _full().set("random_seed", None)

    def test_a_blank_string_is_refused(self):
        with self.assertRaises(ValueError):
            _full().set("hypothesis", "   ")

    def test_an_undeclared_field_is_refused(self):
        with self.assertRaises(X.NotDeclared):
            _full().set("gut_feel", "strong")

    def test_the_code_version_records_whether_the_tree_was_dirty(self):
        # A dirty tree means the commit does NOT identify the code that ran (§46).
        cv = X.code_version()
        if X.is_unavailable(cv):
            self.skipTest("not a git checkout")
        self.assertIn("commit", cv)
        self.assertIn("dirty", cv)
        self.assertIsInstance(cv["dirty"], bool)


class Immutability(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_a_sealed_record_raises_on_mutation(self):
        sealed = _full().seal()
        with self.assertRaises(TypeError):
            sealed["hypothesis"] = "something else"

    def test_writing_twice_to_the_same_id_is_refused(self):
        sealed = _full().seal()
        X.write(sealed, store=self.d)
        with self.assertRaises(X.Immutable) as cm:
            X.write(sealed, store=self.d)
        self.assertIn("successor", str(cm.exception))

    def test_an_unsealed_dict_cannot_be_written_as_though_it_were_evidence(self):
        with self.assertRaises(X.Immutable):
            X.write({"experiment_id": "x"}, store=self.d)

    def test_an_edited_record_is_detected_on_load(self):
        # The one that matters: an edit through an editor or a merge never goes through this module.
        sealed = _full().seal()
        p = X.write(sealed, store=self.d)
        d = json.load(open(p, encoding="utf-8"))
        d["metrics"]["expectancy"] = 9.99
        json.dump(d, open(p, "w"))
        with self.assertRaises(X.Tampered) as cm:
            X.load(sealed["experiment_id"], store=self.d)
        self.assertIn("immutable", str(cm.exception))

    def test_an_untouched_record_loads_back_identical(self):
        sealed = _full().seal()
        X.write(sealed, store=self.d)
        back = X.load(sealed["experiment_id"], store=self.d)
        for f in X.ORDER:
            self.assertEqual(back[f], sealed[f], f)

    def test_the_hash_covers_every_required_field_and_nothing_else(self):
        # A hash over a subset would leave the rest editable; a hash over the whole file would change when a
        # future writer adds a comment key.
        #
        # `at` is PINNED. Record.__init__ stamps `timestamp` from the clock at SECOND resolution and the seal
        # hashes it, so two records built either side of a second boundary hash differently -- which is
        # correct behaviour and made this test flaky: it passed only when both calls landed in the same
        # second, and failed on 2026-09-19 under a loaded machine. What the test is about is whether the hash
        # covers the CONTENT; the clock is noise here, so it is held still.
        at = "2026-09-19T00:00:00Z"
        a = _full(at=at).seal()
        b = _full(at=at).seal()
        self.assertEqual(a["content_sha256"], b["content_sha256"])
        c = _full(at=at, random_seed=1).seal()
        self.assertNotEqual(a["content_sha256"], c["content_sha256"],
                            "changing a §42 field must change the hash")

    def test_the_timestamp_is_part_of_what_is_sealed(self):
        """The flakiness above was a real property, not a bug: two runs of the same experiment at different
        times are different records, and the hash must say so."""
        a = _full(at="2026-09-19T00:00:00Z").seal()
        b = _full(at="2026-09-19T00:00:01Z").seal()
        self.assertNotEqual(a["content_sha256"], b["content_sha256"])


class ADecisionIsASuccessorNotAnEdit(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.sealed = _full().seal()
        X.write(self.sealed, store=self.d)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_a_human_decision_files_a_new_record_naming_its_predecessor(self):
        out = X.decide(self.sealed, "APPROVED", actor="human", note="ok", store=self.d)
        self.assertEqual(out["decision"]["decision"], "APPROVED")
        self.assertEqual(out["decision"]["predecessor"], self.sealed["experiment_id"])
        self.assertEqual(out["decision"]["predecessor_sha256"], self.sealed["content_sha256"])

    def test_the_original_record_is_untouched_by_the_decision(self):
        X.decide(self.sealed, "REJECTED", actor="human", store=self.d)
        back = X.load(self.sealed["experiment_id"], store=self.d)
        self.assertEqual(back["decision"]["decision"], X.PENDING)

    def test_a_model_cannot_decide_an_experiment(self):
        with self.assertRaises(PermissionError) as cm:
            X.decide(self.sealed, "APPROVED", actor="learning-agent", store=self.d)
        self.assertIn("NEVER silently rewrite", str(cm.exception))

    def test_pending_cannot_be_recorded_as_a_decision(self):
        # It is the value BEFORE a decision, not one of them.
        with self.assertRaises(ValueError):
            X.decide(self.sealed, X.PENDING, actor="human", store=self.d)

    def test_both_records_survive_in_the_store(self):
        X.decide(self.sealed, "DEFERRED", actor="human", store=self.d)
        ids = {r["experiment_id"] for r in X.all_records(self.d)}
        self.assertIn(self.sealed["experiment_id"], ids)
        self.assertIn(self.sealed["experiment_id"] + "-decision", ids)

    def test_a_tampered_record_is_skipped_by_the_bulk_reader_rather_than_returned(self):
        p = os.path.join(self.d, f"{self.sealed['experiment_id']}.json")
        d = json.load(open(p, encoding="utf-8")); d["hypothesis"] = "rewritten"
        json.dump(d, open(p, "w"))
        self.assertEqual(X.all_records(self.d), [])


class TheStoreIsUsableEndToEnd(unittest.TestCase):
    def test_a_record_can_be_built_from_the_repositorys_own_snapshots(self):
        # The fields are not decorative: each maps onto something this repo already produces.
        import snapshot as S
        import account_profile as AP
        import performance as P
        r = X.Record(hypothesis="h", motivation="m", parent_trading_system_version="v1",
                     candidate_version="v1.1")
        r.set("dataset_snapshot", S.dataset_snapshot([("BTCUSDT", "4H")],
                                                     base=os.path.join(ROOT, "data", "history")))
        r.set("account_configuration", AP.snapshot(AP.get("pilot-mt5-demo")))
        r.set("metrics", P.metrics([{"R": 1.0}, {"R": -1.0}]))
        for fid in r.missing():
            r.set(fid, X.unavailable("not part of this smoke record"))
        sealed = r.seal()
        self.assertEqual(sealed["metrics"]["n"], 2)
        self.assertIn("snapshot_id", sealed["dataset_snapshot"])

    def test_describe_names_the_versions_and_the_decision(self):
        line = X.describe(_full().seal())
        self.assertIn("v1 -> v1.1", line)
        self.assertIn(X.PENDING, line)

    def test_describe_lists_the_fields_that_are_unavailable(self):
        # A record whose robustness is unavailable must not read like one whose robustness passed.
        self.assertIn("robustness results", X.describe(_full().seal()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
