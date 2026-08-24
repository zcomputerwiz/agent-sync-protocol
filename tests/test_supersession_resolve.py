"""Focused stdlib tests for sync_tools.resolve_dir (R1-R7 semantics).

Covers: structural validation, transitive resolution, CONFLICT, CYCLE,
BROKEN_REF (both directions), R6 absent-supersedes-informational, per-file
READY gating, R7 authoritative-vs-REQUESTED, the real 0B triple shape
(two duplicate unpinned artifacts superseded by one pinned manifest), and
the batch-size supersession shape (same path, old sha -> new sha).
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
    blob = json.dumps(obj, indent=2, sort_keys=True).encode("utf-8")
    p = root / name
    p.write_bytes(blob)
    if ready:
        digest = hashlib.sha256(blob).hexdigest()
        p.with_suffix(".json.sha256").write_text(
            f"{digest}  {p.name}\n", encoding="utf-8")


def resolve(root: Path):
    return sync_tools.resolve_dir(root)


def statuses(res):
    return {k: v["status"] for k, v in res["artifacts"].items()}


def kinds(res):
    return sorted({e["kind"] for e in res["exceptions"]})


class SupersessionResolveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_validation_invalid_manifest_is_exception(self):
        pair(self.root, "a.json", b"{}")
        manifest(self.root, "bad.json", {"schema_version": 2})
        res = resolve(self.root)
        self.assertIn("INVALID_MANIFEST", kinds(res))
        self.assertEqual({}, res["artifacts"])

    def test_transitive_resolution(self):
        a = pair(self.root, "old_a.json", b"A")
        b = pair(self.root, "mid_b.json", b"B")
        c = pair(self.root, "new_c.json", b"C")
        m1 = {"schema_version": 1, "status": "superseded", "from": "n1",
              "date": "2026-08-24T00:00:00Z", "reason": "r1",
              "supersedes": [a],
              "replacement": {"path": b["path"], "sha256": b["sha256"]}}
        m2 = {"schema_version": 1, "status": "superseded", "from": "n1",
              "date": "2026-08-24T00:00:01Z", "reason": "r2",
              "supersedes": [b],
              "replacement": {"path": c["path"], "sha256": c["sha256"]}}
        manifest(self.root, "m1.json", m1)
        manifest(self.root, "m2.json", m2)
        res = resolve(self.root)
        st = statuses(res)
        self.assertEqual(st[node_of(a)], "SUPERSEDED")
        self.assertEqual(res["artifacts"][node_of(a)]["by"], node_of(c))
        self.assertEqual(st[node_of(b)], "SUPERSEDED")
        self.assertEqual(res["exceptions"], [])

    def test_conflict_fails_closed(self):
        old = pair(self.root, "old.json", b"OLD")
        r1 = pair(self.root, "r1.json", b"R1")
        r2 = pair(self.root, "r2.json", b"R2")
        # SAME author node issuing two closures with different replacements:
        # genuinely contradictory, must fail closed.
        base = {"schema_version": 1, "status": "superseded",
                "date": "2026-08-24T00:00:00Z", "from": "nA",
                "supersedes": [old]}
        manifest(self.root, "m1.json", {**base, "replacement": r1})
        manifest(self.root, "m2.json", {**base, "replacement": r2})
        res = resolve(self.root)
        self.assertIn("CONFLICT", kinds(res))

    def test_cycle_detected(self):
        a = pair(self.root, "a.json", b"A")
        b = pair(self.root, "b.json", b"B")
        base = {"schema_version": 1, "status": "superseded",
                "date": "d", "from": "n"}
        manifest(self.root, "m1.json",
                 {**base, "supersedes": [a], "replacement": b})
        manifest(self.root, "m2.json",
                 {**base, "supersedes": [b], "replacement": a})
        res = resolve(self.root)
        self.assertIn("CYCLE", kinds(res))

    def test_broken_replacement_and_supersedes_mismatch(self):
        old = pair(self.root, "old.json", b"OLD")
        repl = pair(self.root, "repl.json", b"REPL")
        (self.root / "repl.json").write_bytes(b"TAMPERED")
        manifest(self.root, "m1.json",
                 {"schema_version": 1, "status": "superseded", "from": "n",
                  "date": "d",
                  "supersedes": [dict(old, sha256="0" * 64)],
                  "replacement": repl})
        res = resolve(self.root)
        self.assertIn("BROKEN_REF", kinds(res))

    def test_absent_supersedes_is_informational_r6(self):
        repl = pair(self.root, "new.json", b"NEW")
        ghost = {"path": "gone/old.json", "sha256": "a" * 64}
        manifest(self.root, "m1.json",
                 {"schema_version": 1, "status": "superseded", "from": "n",
                  "date": "d", "supersedes": [ghost],
                  "replacement": repl})
        res = resolve(self.root)
        self.assertEqual([], res["exceptions"])
        self.assertEqual(1, len(res["informational"]))
        self.assertEqual("ACTIVE", statuses(res)[node_of(repl)])

    def test_not_ready_manifest_excluded(self):
        good = pair(self.root, "x.json", b"X")
        pair(self.root, "y.json", b"Y")  # stays unreferenced
        m = {"schema_version": 1, "status": "superseded", "from": "n",
             "date": "d", "supersedes": [good],
             "replacement": {"path": "y.json", "sha256": "b" * 64}}
        manifest(self.root, "stale.json", m, ready=False)
        res = resolve(self.root)
        skipped_names = [s.split("/")[-1].split("\\")[-1]
                         for s in res["skipped_not_ready"]]
        self.assertTrue(any(n.endswith("stale.json") for n in skipped_names),
                        skipped_names)
        self.assertEqual({}, res["artifacts"])

    def test_authority_requested_not_applied(self):
        old = pair(self.root, "old.json", b"OLD")
        new = pair(self.root, "new.json", b"NEW")
        # entry publisher differs from manifest author -> REQUESTED (R7)
        entry = dict(old, publisher="someoneElse")
        manifest(self.root, "req.json",
                 {"schema_version": 1, "status": "superseded", "from": "nX",
                  "date": "d", "supersedes": [entry], "replacement": new})
        res = resolve(self.root)
        self.assertEqual({}, res["artifacts"])
        self.assertEqual(1, len(res["requested"]))
        self.assertEqual([], res["exceptions"])

    def test_0b_triple_two_duplicates_one_pinned(self):
        dup_bytes = b"batch32-eval"
        d1 = pair(self.root, "eval_n36_seed_44.json", dup_bytes)
        d2 = pair(self.root, "eval_rwkv_n36_seed_44.json", dup_bytes)
        pin = pair(self.root, "eval_rwkv_n36_seed_44_epoch_005.json",
                   b"batch128-eval")
        manifest(self.root, "closure.json",
                 {"schema_version": 1, "status": "superseded",
                  "from": "antigravity-ampere", "date": "2026-08-24T15:00:00Z",
                  "reason": "pre-pin evaluations lack recorded settings",
                  "supersedes": [
                      dict(d1, publisher="antigravity-ampere"),
                      dict(d2, publisher="antigravity-ampere")],
                  "replacement": pin})
        res = resolve(self.root)
        st = statuses(res)
        self.assertEqual("SUPERSEDED", st[node_of(d1)])
        self.assertEqual("SUPERSEDED", st[node_of(d2)])
        self.assertEqual("ACTIVE", st[node_of(pin)])
        self.assertEqual(node_of(pin), res["artifacts"][node_of(d1)]["by"])

    def test_batch_size_same_path_new_hash(self):
        old_ref = {"path": "e/eval.json", "sha256": "c" * 64}
        new = pair(self.root, "e/eval.json", b"batch128-recorded")
        manifest(self.root, "closure.json",
                 {"schema_version": 1, "status": "superseded", "from": "n",
                  "date": "d",
                  "supersedes": [dict(old_ref, publisher="n")],
                  "replacement": new})
        res = resolve(self.root)
        self.assertEqual("SUPERSEDED",
                         statuses(res)[node_of(old_ref)])
        self.assertEqual("ACTIVE", statuses(res)[node_of(new)])

    def test_deterministic_across_runs(self):
        old = pair(self.root, "old.json", b"O")
        new = pair(self.root, "new.json", b"N")
        manifest(self.root, "CLOSED_c.json",
                 {"schema_version": 1, "status": "superseded", "from": "n",
                  "date": "d", "supersedes": [old], "replacement": new})
        r1 = resolve(self.root)
        r2 = resolve(self.root)
        self.assertEqual(r1["artifacts"], r2["artifacts"])
        self.assertEqual(r1["exceptions"], r2["exceptions"])


if __name__ == "__main__":
    unittest.main()
