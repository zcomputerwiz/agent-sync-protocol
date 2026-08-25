"""Focused stdlib tests for sync_tools.resolve_dir (R1-R7 semantics).

Covers: canonical path validation (R2), structural validation, transitive
resolution, CONFLICT, CYCLE, BROKEN_REF both directions, R6 absent-supersedes
informational, per-file READY gating, R7 authority with REQUIRED publisher +
operator ratification representation, fail-closed selection (any exception ->
artifacts == {}), the real 0B triple shape (two duplicate unpinned artifacts
superseded by one pinned manifest), and same-path overwrite = BROKEN_REF.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "sync_tools",
    Path(__file__).resolve().parents[1] / "sync_tools.py")
sync_tools = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sync_tools)

DATE = "2026-08-24T00:00:00Z"


def pair(root: Path, rel: str, content: bytes):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    side = p.with_suffix(p.suffix + ".sha256")
    side.write_text(f"{digest}  {p.name}\n", encoding="utf-8")
    return {"path": rel.replace("\\", "/"), "sha256": digest}


def node_of(ref):
    return f"{ref['path']}#{ref['sha256']}"


def manifest(root: Path, name: str, obj, ready: bool = True):
    if not name.startswith("CLOSED_"):
        name = f"CLOSED_{name}"
    obj.setdefault("schema_version", 1)
    obj.setdefault("status", "superseded")
    obj.setdefault("date", DATE)
    blob = json.dumps(obj, indent=2, sort_keys=True).encode("utf-8")
    p = root / name
    p.write_bytes(blob)
    if ready:
        digest = hashlib.sha256(blob).hexdigest()
        p.with_suffix(".json.sha256").write_text(
            f"{digest}  {p.name}\n", encoding="utf-8")


def resolve(root: Path):
    return sync_tools.resolve_dir(root)


def kinds(res):
    return sorted({e["kind"] for e in res["exceptions"]})


def statuses(res):
    return {k: v["status"] for k, v in res["artifacts"].items()}


class SupersessionResolveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def test_invalid_manifest_fails_closed(self):
        pair(self.root, "a.json", b"{}")
        manifest(self.root, "bad.json", {"schema_version": 2})
        res = resolve(self.root)
        self.assertIn("INVALID_MANIFEST", kinds(res))
        self.assertEqual({}, res["artifacts"])  # fail closed

    def test_root_escape_rejected(self):
        good = pair(self.root, "safe/new.json", b"NEW")
        manifest(self.root, "escape.json",
                 {"from": "n", "reason": "r",
                  "supersedes": [{"path": "../outside.json",
                                  "sha256": "a" * 64,
                                  "publisher": "n"}],
                  "replacement": good})
        res = resolve(self.root)
        self.assertIn("INVALID_MANIFEST", kinds(res))
        self.assertEqual({}, res["artifacts"])

    def test_non_canonical_paths_rejected(self):
        good = pair(self.root, "safe/new.json", b"NEW")
        for bad_path in ("sub/../old.json", "./old.json",
                         "C:/old.json", "old\\old.json"):
            manifest(self.root, "nc.json",
                     {"from": "n", "reason": "r",
                      "supersedes": [{"path": bad_path,
                                      "sha256": "a" * 64,
                                      "publisher": "n"}],
                      "replacement": good})
            res = resolve(self.root)
            self.assertIn("INVALID_MANIFEST", kinds(res), bad_path)

    def test_missing_publisher_is_invalid(self):
        good = pair(self.root, "new.json", b"NEW")
        old = pair(self.root, "old.json", b"OLD")
        entry = {"path": old["path"], "sha256": old["sha256"]}  # no publisher
        manifest(self.root, "nopub.json",
                 {"from": "n", "reason": "r", "supersedes": [entry],
                  "replacement": good})
        res = resolve(self.root)
        self.assertIn("INVALID_MANIFEST", kinds(res))
        self.assertEqual({}, res["artifacts"])

    def test_bad_date_and_reason_rejected(self):
        old = pair(self.root, "o1.json", b"O")
        new = pair(self.root, "n1.json", b"N")
        entry = dict(old, publisher="n")
        manifest(self.root, "c1.json",
                 {"from": "n", "date": "yesterday", "reason": "r",
                  "supersedes": [entry], "replacement": new})
        manifest(self.root, "c2.json",
                 {"from": "n", "date": DATE, "reason": "",
                  "supersedes": [entry], "replacement": new})
        res = resolve(self.root)
        self.assertEqual(2, len(
            [e for e in res["exceptions"]
             if e["kind"] == "INVALID_MANIFEST"]))
        self.assertEqual({}, res["artifacts"])

    # ------------------------------------------------------------------
    # Happy paths
    # ------------------------------------------------------------------

    def test_transitive_resolution(self):
        a = pair(self.root, "old_a.json", b"A")
        b = pair(self.root, "mid_b.json", b"B")
        c = pair(self.root, "new_c.json", b"C")
        manifest(self.root, "m1.json",
                 {"from": "n", "reason": "r", "supersedes": [dict(a, publisher="n")],
                  "replacement": b})
        manifest(self.root, "m2.json",
                 {"from": "n", "reason": "r", "supersedes": [dict(b, publisher="n")],
                  "replacement": c})
        res = resolve(self.root)
        st = statuses(res)
        self.assertEqual([], res["exceptions"])
        self.assertEqual("SUPERSEDED", st[node_of(a)])
        self.assertEqual(node_of(c), res["artifacts"][node_of(a)]["by"])
        self.assertEqual("SUPERSEDED", st[node_of(b)])
        self.assertEqual("ACTIVE", st[node_of(c)])

    def test_withdrawal_without_replacement(self):
        old = pair(self.root, "old.json", b"O")
        manifest(self.root, "w.json",
                 {"from": "n", "reason": "r", "supersedes": [dict(old, publisher="n")],
                  "replacement": None})
        res = resolve(self.root)
        self.assertEqual([], res["exceptions"])
        self.assertEqual("WITHDRAWN", statuses(res)[node_of(old)])

    def test_withdrawal_vs_replacement_conflict(self):
        old = pair(self.root, "old.json", b"O")
        new = pair(self.root, "new.json", b"N")
        manifest(self.root, "w.json",
                 {"from": "n", "reason": "r", "supersedes": [dict(old, publisher="n")],
                  "replacement": None})
        manifest(self.root, "r.json",
                 {"from": "n", "reason": "r", "supersedes": [dict(old, publisher="n")],
                  "replacement": new})
        res = resolve(self.root)
        self.assertIn("CONFLICT", kinds(res))
        self.assertEqual({}, res["artifacts"])  # fail closed

    def test_operator_ratified_request_applies(self):
        old = pair(self.root, "old.json", b"O")
        new = pair(self.root, "new.json", b"N")
        entry = dict(old, publisher="someoneElse")
        manifest(self.root, "req.json",
                 {"from": "operator", "reason": "r", "supersedes": [entry],
                  "replacement": new, "operator_ratified": True})
        res = resolve(self.root)
        self.assertEqual([], res["exceptions"])
        self.assertEqual("SUPERSEDED", statuses(res)[node_of(old)])

    def test_unratified_cross_node_request_not_applied(self):
        old = pair(self.root, "old.json", b"O")
        new = pair(self.root, "new.json", b"N")
        entry = dict(old, publisher="someoneElse")
        manifest(self.root, "req.json",
                 {"from": "nX", "reason": "r", "supersedes": [entry],
                  "replacement": new})
        res = resolve(self.root)
        self.assertEqual([], res["exceptions"])
        self.assertEqual(1, len(res["requested"]))
        self.assertEqual({}, res["artifacts"])  # fail closed, nothing applied

    # ------------------------------------------------------------------
    # Fail-closed selection on any exception
    # ------------------------------------------------------------------

    def test_conflict_selects_nothing(self):
        old = pair(self.root, "old.json", b"O")
        r1 = pair(self.root, "r1.json", b"R1")
        r2 = pair(self.root, "r2.json", b"R2")
        base = {"from": "nA", "reason": "r", "supersedes":
                [dict(old, publisher="nA")]}
        manifest(self.root, "m1.json", {**base, "replacement": r1})
        manifest(self.root, "m2.json", {**base, "replacement": r2})
        res = resolve(self.root)
        self.assertIn("CONFLICT", kinds(res))
        self.assertEqual({}, res["artifacts"])

    def test_broken_supersedes_mismatch_selects_nothing(self):
        old = pair(self.root, "old.json", b"OLD")
        repl = pair(self.root, "repl.json", b"REPL")
        (self.root / "repl.json").write_bytes(b"TAMPERED")
        manifest(self.root, "m1.json",
                 {"from": "n", "reason": "r",
                  "supersedes": [dict(old, sha256="0" * 64, publisher="n")],
                  "replacement": repl})
        res = resolve(self.root)
        self.assertIn("BROKEN_REF", kinds(res))
        self.assertEqual({}, res["artifacts"])

    def test_cycle_selects_nothing(self):
        a = pair(self.root, "a.json", b"A")
        b = pair(self.root, "b.json", b"B")
        manifest(self.root, "m1.json",
                 {"from": "n", "reason": "r", "supersedes": [dict(a, publisher="n")],
                  "replacement": b})
        manifest(self.root, "m2.json",
                 {"from": "n", "reason": "r", "supersedes": [dict(b, publisher="n")],
                  "replacement": a})
        res = resolve(self.root)
        self.assertIn("CYCLE", kinds(res))
        self.assertEqual({}, res["artifacts"])

    # ------------------------------------------------------------------
    # Real shapes
    # ------------------------------------------------------------------

    def test_0b_triple_two_duplicates_one_pinned(self):
        dup_bytes = b"batch32-eval"
        d1 = pair(self.root, "eval_n36_seed_44.json", dup_bytes)
        d2 = pair(self.root, "eval_rwkv_n36_seed_44.json", dup_bytes)
        pin = pair(self.root, "eval_rwkv_n36_seed_44_epoch_005.json",
                   b"batch128-eval")
        manifest(self.root, "closure.json",
                 {"from": "antigravity-ampere",
                  "reason": "pre-pin evaluations lack recorded settings",
                  "supersedes": [
                      dict(d1, publisher="antigravity-ampere"),
                      dict(d2, publisher="antigravity-ampere")],
                  "replacement": pin})
        res = resolve(self.root)
        self.assertEqual([], res["exceptions"])
        st = statuses(res)
        self.assertEqual("SUPERSEDED", st[node_of(d1)])
        self.assertEqual("SUPERSEDED", st[node_of(d2)])
        self.assertEqual("ACTIVE", st[node_of(pin)])

    def test_batch_size_distinct_path_supersession(self):
        old = pair(self.root, "e/eval_b32.json", b"batch32")
        new = pair(self.root, "e/eval_b128.json", b"batch128")
        manifest(self.root, "closure.json",
                 {"from": "n", "reason": "r",
                  "supersedes": [dict(old, publisher="n")],
                  "replacement": new})
        res = resolve(self.root)
        self.assertEqual([], res["exceptions"])
        st = statuses(res)
        self.assertEqual("SUPERSEDED", st[node_of(old)])
        self.assertEqual("ACTIVE", st[node_of(new)])

    def test_same_path_overwrite_is_broken_ref(self):
        # Ada's analyzer incident: same path re-published with different
        # bytes after the sidecar was written -> mismatch, fail closed.
        old_ref = pair(self.root, "e/eval.json", b"batch32")
        pair(self.root, "e/eval.json", b"TAMPERED-batch128")
        manifest(self.root, "closure.json",
                 {"from": "n", "reason": "r",
                  "supersedes": [dict(old_ref, publisher="n")],
                  "replacement": None})
        res = resolve(self.root)
        self.assertIn("BROKEN_REF", kinds(res))
        self.assertEqual({}, res["artifacts"])

    # ------------------------------------------------------------------
    # Determinism + gating
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Shannon v2 adversarial regressions
    # ------------------------------------------------------------------

    def test_missing_sha256_is_invalid_not_crash(self):
        good = pair(self.root, "new.json", b"NEW")
        old = pair(self.root, "old.json", b"OLD")
        entry = {"path": old["path"], "publisher": "n"}  # sha256 omitted
        manifest(self.root, "m1.json",
                 {"from": "n", "reason": "r", "supersedes": [entry],
                  "replacement": good})
        res = resolve(self.root)
        self.assertIn("INVALID_MANIFEST", kinds(res))
        self.assertEqual({}, res["artifacts"])

    def test_uppercase_and_short_sha_rejected(self):
        new = pair(self.root, "new.json", b"NEW")
        for bad in ("A" * 64, "abc"):
            old_ref = pair(self.root, f"o_{bad[:3]}.json", b"O")
            manifest(self.root, "c.json",
                     {"from": "n", "reason": "r",
                      "supersedes": [dict(old_ref, sha256=bad,
                                          publisher="n")],
                      "replacement": new})
            res = resolve(self.root)
            self.assertIn("INVALID_MANIFEST", kinds(res), bad)
            (self.root / "CLOSED_c.json").unlink()
            (self.root / "CLOSED_c.json.sha256").unlink()

    def test_replacement_without_ready_sidecar_broken_ref(self):
        old = pair(self.root, "old.json", b"O")
        (self.root / "new.json").write_bytes(b"NEW")  # no sidecar -> not READY
        repl = {"path": "new.json", "sha256":
                hashlib.sha256(b"NEW").hexdigest()}
        manifest(self.root, "m1.json",
                 {"from": "n", "reason": "r", "supersedes": [dict(old, publisher="n")],
                  "replacement": repl})
        res = resolve(self.root)
        self.assertIn("BROKEN_REF", kinds(res))
        self.assertEqual({}, res["artifacts"])

    def test_case_mismatched_path_treated_as_absent(self):
        pair(self.root, "Case/New.json", b"NEW")  # actual case differs
        ghost = {"path": "case/new.json", "sha256": "a" * 64, "publisher": "n"}
        repl = {"path": "real/repl.json", "sha256": "b" * 64}  # absent
        manifest(self.root, "m1.json",
                 {"from": "n", "reason": "r",
                  "supersedes": [ghost], "replacement": repl})
        res = resolve(self.root)
        self.assertIn("BROKEN_REF", kinds(res))  # replacement absent fails
        details = " ".join(e["detail"] for e in res["exceptions"])
        self.assertNotIn("case/new.json#", [d for d in []] or details)

    def test_cross_node_self_ratification_is_inert(self):
        old = pair(self.root, "old.json", b"O")
        new = pair(self.root, "new.json", b"N")
        entry = dict(old, publisher="someoneElse")
        manifest(self.root, "req.json",
                 {"from": "nX", "reason": "r", "supersedes": [entry],
                  "replacement": new, "operator_ratified": True})
        res = resolve(self.root)
        self.assertEqual([], res["exceptions"])
        self.assertEqual(1, len(res["requested"]))
        self.assertEqual({}, res["artifacts"])

    def test_deterministic_across_runs(self):
        old = pair(self.root, "old.json", b"O")
        new = pair(self.root, "new.json", b"N")
        manifest(self.root, "CLOSED_c.json",
                 {"from": "n", "reason": "r",
                  "supersedes": [dict(old, publisher="n")],
                  "replacement": new})
        r1 = resolve(self.root)
        r2 = resolve(self.root)
        self.assertEqual([], r1["exceptions"])
        self.assertEqual(r1["artifacts"], r2["artifacts"])
        self.assertEqual(r1["exceptions"], r2["exceptions"])

    def test_not_ready_manifest_excluded(self):
        good = pair(self.root, "x.json", b"X")
        pair(self.root, "y.json", b"Y")  # stays unreferenced
        manifest(self.root, "stale.json",
                 {"from": "n", "reason": "r",
                  "supersedes": [dict(good, publisher="n")],
                  "replacement": {"path": "y.json", "sha256":
                                  hashlib.sha256(b"Y").hexdigest()}},
                 ready=False)
        res = resolve(self.root)
        skipped_names = [s.split("/")[-1].split("\\")[-1]
                         for s in res["skipped_not_ready"]]
        self.assertTrue(any(n.endswith("stale.json") for n in skipped_names),
                        skipped_names)
        # P1: a skipped (non-READY) manifest must not be parsed or applied.
        self.assertEqual([], res["manifests"])
        self.assertEqual({}, res["artifacts"])

    def test_impossible_rfc3339_rejected(self):
        old = pair(self.root, "old.json", b"O")
        new = pair(self.root, "new.json", b"N")
        entry = dict(old, publisher="n")
        manifest(self.root, "c1.json",
                 {"from": "n", "date": "2026-99-99T99:99:99Z", "reason": "r",
                  "supersedes": [entry], "replacement": new})
        res = resolve(self.root)
        self.assertIn("INVALID_MANIFEST", kinds(res))
        self.assertEqual({}, res["artifacts"])

    def test_numeric_offset_without_colon_rejected(self):
        old = pair(self.root, "old.json", b"O")
        new = pair(self.root, "new.json", b"N")
        entry = dict(old, publisher="n")
        # RFC3339 5.6: time-numoffset requires the colon; +0000 is invalid.
        manifest(self.root, "c2.json",
                 {"from": "n", "date": "2026-08-24T00:00:00+0000",
                  "reason": "r", "supersedes": [entry], "replacement": new})
        res = resolve(self.root)
        self.assertIn("INVALID_MANIFEST", kinds(res))
        self.assertEqual({}, res["artifacts"])
        # colon-bearing equivalent stays valid
        manifest(self.root, "c3.json",
                 {"from": "n", "date": "2026-08-24T00:00:00+00:00",
                  "reason": "r", "supersedes": [entry], "replacement": new})
        res2 = resolve(self.root)
        self.assertNotIn("INVALID_MANIFEST", kinds(res2))

    def test_absent_supersedes_is_informational_r6(self):
        repl = pair(self.root, "new.json", b"NEW")
        ghost = {"path": "gone/old.json", "sha256": "a" * 64, "publisher": "n"}
        manifest(self.root, "m1.json",
                 {"from": "n", "reason": "r", "supersedes": [ghost],
                  "replacement": repl})
        res = resolve(self.root)
        self.assertEqual([], res["exceptions"])
        self.assertEqual(1, len(res["informational"]))
        self.assertEqual("ACTIVE", statuses(res)[node_of(repl)])


if __name__ == "__main__":
    unittest.main()
