"""Tests for the section 3.2 copy-out and archive-extraction guards.

These two helpers shipped with no tests and no callers. They are the mechanical
part of the no-execution rule -- the step that moves a payload out of the share
before anything looks at it -- so they are the last place to take on trust.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sync_tools import find_share_root, is_safe_archive_member, quarantine_copy


class TestFindShareRoot(unittest.TestCase):
    def test_finds_the_folder_marked_by_stfolder(self):
        with tempfile.TemporaryDirectory() as tmp:
            share = Path(tmp) / "share"
            (share / ".stfolder").mkdir(parents=True)
            deep = share / "a" / "b"
            deep.mkdir(parents=True)
            payload = deep / "p.txt"
            payload.write_text("x")
            self.assertEqual(find_share_root(payload), share.resolve())

    def test_returns_none_outside_a_share(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = Path(tmp) / "p.txt"
            payload.write_text("x")
            self.assertIsNone(find_share_root(payload))


class TestQuarantineCopy(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.share = self.root / "share"
        (self.share / ".stfolder").mkdir(parents=True)
        self.payload = self.share / "inbox" / "thing.py"
        self.payload.parent.mkdir(parents=True)
        self.payload.write_text("print('hello')\n")
        self.local = self.root / "quarantine"

    def tearDown(self):
        self._tmp.cleanup()

    def test_copies_out_of_the_share(self):
        target = quarantine_copy(self.payload, self.local)
        self.assertTrue(target.exists())
        self.assertEqual(target.read_text(), "print('hello')\n")
        self.assertEqual(target.parent, self.local.resolve())

    def test_creates_the_quarantine_directory(self):
        nested = self.local / "deep" / "deeper"
        self.assertFalse(nested.exists())
        quarantine_copy(self.payload, nested)
        self.assertTrue(nested.is_dir())

    def test_refuses_a_destination_inside_the_share(self):
        with self.assertRaises(ValueError) as ctx:
            quarantine_copy(self.payload, self.share / "elsewhere")
        self.assertIn("inside the share", str(ctx.exception))

    def test_refuses_the_share_root_itself(self):
        with self.assertRaises(ValueError):
            quarantine_copy(self.payload, self.share)

    def test_refuses_when_the_share_cannot_be_located(self):
        """The fail-open case: no .stfolder means no boundary to check against.

        The shipped version fell back to the working directory here, which made
        the containment check pass for essentially any destination.
        """
        loose = self.root / "loose"
        loose.mkdir()
        orphan = loose / "thing.py"
        orphan.write_text("x")
        with self.assertRaises(ValueError) as ctx:
            quarantine_copy(orphan, self.root / "q2")
        self.assertIn("cannot locate the share root", str(ctx.exception))

    def test_an_explicit_share_root_is_still_enforced(self):
        loose = self.root / "loose2"
        loose.mkdir()
        orphan = loose / "thing.py"
        orphan.write_text("x")
        quarantine_copy(orphan, self.root / "q3", share_root=loose)
        with self.assertRaises(ValueError):
            quarantine_copy(orphan, loose / "inner", share_root=loose)

    def test_the_working_directory_does_not_decide_the_answer(self):
        """Regression: the outcome must not depend on where the tool was run."""
        outside = self.root / "outside"
        outside.mkdir()
        cwd = os.getcwd()
        try:
            os.chdir(self.share)
            target = quarantine_copy(self.payload, outside)
            self.assertTrue(target.exists())
            with self.assertRaises(ValueError):
                quarantine_copy(self.payload, self.share / "nope")
        finally:
            os.chdir(cwd)


class TestArchiveMemberSafety(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dest = Path(self._tmp.name) / "extract"
        self.dest.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_accepts_ordinary_members(self):
        for member in ("a.txt", "sub/dir/b.txt", "./c.txt"):
            self.assertTrue(is_safe_archive_member(member, self.dest), member)

    def test_rejects_parent_traversal(self):
        for member in ("../evil", "../../evil", "sub/../../evil",
                       "a/b/../../../evil", ".."):
            self.assertFalse(is_safe_archive_member(member, self.dest), member)

    def test_rejects_absolute_paths(self):
        for member in ("/etc/passwd", "//server/share/x", "/"):
            self.assertFalse(is_safe_archive_member(member, self.dest), member)

    def test_rejects_windows_style_escapes(self):
        for member in ("..\\\\evil", "sub\\\\..\\\\..\\\\evil", "\\\\evil"):
            self.assertFalse(is_safe_archive_member(member, self.dest), member)

    def test_rejects_a_path_that_escapes_through_a_symlink(self):
        outside = Path(self._tmp.name) / "outside"
        outside.mkdir()
        link = self.dest / "link"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not permitted on this platform")
        self.assertFalse(is_safe_archive_member("link/evil.txt", self.dest))

    def test_rejects_the_empty_member(self):
        self.assertFalse(is_safe_archive_member("", self.dest))


if __name__ == "__main__":
    unittest.main()
