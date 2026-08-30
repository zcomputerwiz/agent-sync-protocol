import json
import unittest
from pathlib import Path

class TestFixtures(unittest.TestCase):
    def setUp(self):
        self.fixtures_dir = Path(__file__).parent / "fixtures"

    def _load_json(self, name):
        with open(self.fixtures_dir / name, "r") as f:
            return json.load(f)

    def _assert_attestation_shape(self, data):
        self.assertIn("schema_version", data)
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["namespace"], "agent-sync-protocol")
        self.assertIn("fleet_id", data)
        self.assertIn("channel", data)
        self.assertIn(data["channel"], ("bus", "artifacts"))
        self.assertIn("publisher", data)
        self.assertIn("path", data)
        self.assertIn("sha256", data)
        self.assertEqual(len(data["sha256"]), 64)
        self.assertIn("message_id", data)
        self.assertIn("created_at", data)
        self.assertIn("expires_at", data)

    def test_valid_signature_fixture(self):
        data = self._load_json("valid_signature.json")
        self._assert_attestation_shape(data)
        self.assertTrue((self.fixtures_dir / "valid_signature.json.sig").exists())

    def test_missing_signature_fixture(self):
        data = self._load_json("missing_signature.json")
        self._assert_attestation_shape(data)
        self.assertFalse((self.fixtures_dir / "missing_signature.json.sig").exists())

    def test_unknown_signer_fixture(self):
        data = self._load_json("unknown_signer.json")
        self._assert_attestation_shape(data)
        self.assertTrue((self.fixtures_dir / "unknown_signer.json.sig").exists())

    def test_path_relabelling_fixture(self):
        data = self._load_json("path_relabelling.json")
        self._assert_attestation_shape(data)
        self.assertNotEqual(data["path"], "inbox/payload.json")
        self.assertEqual(data["path"], "inbox/different_payload.json")
        self.assertTrue((self.fixtures_dir / "path_relabelling.json.sig").exists())

    def test_duplicate_message_id_fixture(self):
        data = self._load_json("duplicate_message_id.json")
        self._assert_attestation_shape(data)
        self.assertTrue((self.fixtures_dir / "duplicate_message_id.json.sig").exists())

    def test_expired_halt_fixture(self):
        data = self._load_json("expired_halt.json")
        self._assert_attestation_shape(data)
        self.assertIsNotNone(data["expires_at"])
        # Should differ from the base one in an intended way
        self.assertTrue((self.fixtures_dir / "expired_halt.json.sig").exists())

    def test_valid_resume_fixture(self):
        data = self._load_json("valid_resume.json")
        self._assert_attestation_shape(data)
        self.assertEqual(data["channel"], "artifacts")
        self.assertTrue((self.fixtures_dir / "valid_resume.json.sig").exists())

if __name__ == "__main__":
    unittest.main()
