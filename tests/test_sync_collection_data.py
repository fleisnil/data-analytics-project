import subprocess
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "src"),
)

import sync_collection_data


class SyncCollectionDataTest(unittest.TestCase):
    def run_git(self, root: Path, *args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
        )

    def test_sync_from_local_data_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            self.run_git(root, "init")
            self.run_git(root, "config", "user.name", "Test")
            self.run_git(
                root,
                "config",
                "user.email",
                "test@example.com",
            )

            (root / "README.md").write_text(
                "test",
                encoding="utf-8",
            )
            self.run_git(root, "add", "README.md")
            self.run_git(root, "commit", "-m", "initial")
            self.run_git(root, "branch", "-M", "main")
            self.run_git(root, "checkout", "-b", "data-collection")

            ojp = (
                root
                / "data/interim/ojp_snapshots/"
                "ojp_snapshot_20260930_120000.csv"
            )
            weather = (
                root
                / "data/interim/weather_snapshots/"
                "weather_snapshot_20260930_120000.csv"
            )
            manifest = root / "data/collection_manifest.csv"

            ojp.parent.mkdir(parents=True, exist_ok=True)
            weather.parent.mkdir(parents=True, exist_ok=True)

            ojp.write_text(
                "city,value\nZürich,1\n",
                encoding="utf-8",
            )
            weather.write_text(
                "city,value\nZürich,2\n",
                encoding="utf-8",
            )
            manifest.write_text(
                "ojp_file\nojp_snapshot_20260930_120000.csv\n",
                encoding="utf-8",
            )

            self.run_git(root, "add", "data")
            self.run_git(root, "commit", "-m", "data")
            self.run_git(root, "checkout", "main")

            counts = sync_collection_data.sync_from_ref(
                root,
                "data-collection",
            )

            self.assertEqual(counts["ojp_snapshots"], 1)
            self.assertEqual(counts["weather_snapshots"], 1)
            self.assertEqual(counts["manifest_files"], 1)
            self.assertTrue(ojp.exists())
            self.assertTrue(weather.exists())
            self.assertTrue(manifest.exists())


if __name__ == "__main__":
    unittest.main()
