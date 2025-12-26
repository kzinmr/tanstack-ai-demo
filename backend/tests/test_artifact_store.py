import os
import sys
import unittest

import pandas as pd


sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
)

from backend.store import ArtifactStore  # noqa: E402


class ArtifactStoreTests(unittest.TestCase):
    def test_store_and_get(self) -> None:
        store = ArtifactStore(ttl_minutes=30)
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})

        artifact = store.store("run123", df)
        fetched = store.get("run123", artifact.id)

        self.assertIsNotNone(fetched)
        self.assertTrue(artifact.id.startswith("a_run123"))
        self.assertEqual(fetched.id, artifact.id)
        self.assertEqual(fetched.original_row_count, 2)

    def test_run_id_namespace(self) -> None:
        store = ArtifactStore(ttl_minutes=30)
        df = pd.DataFrame({"x": [1]})

        artifact_a = store.store("run_a", df)
        store.store("run_b", df)

        self.assertIsNotNone(store.get("run_a", artifact_a.id))
        self.assertIsNone(store.get("run_b", artifact_a.id))

    def test_get_dataframe(self) -> None:
        store = ArtifactStore(ttl_minutes=30)
        df = pd.DataFrame({"x": [1, 2]})
        artifact = store.store("run123", df)

        loaded = store.get_dataframe("run123", artifact.id)
        self.assertIsNotNone(loaded)
        self.assertEqual(list(loaded.columns), ["x"])

    def test_ttl_expiration(self) -> None:
        store = ArtifactStore(ttl_minutes=0)
        df = pd.DataFrame({"x": [1]})
        artifact = store.store("run123", df)

        expired = store.cleanup_expired()
        self.assertGreaterEqual(expired, 1)
        self.assertIsNone(store.get("run123", artifact.id))


if __name__ == "__main__":
    unittest.main()
