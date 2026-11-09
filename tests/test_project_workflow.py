import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import project_workflow as workflow


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write(self, relative, value="data"):
        file = self.root / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(value, encoding="utf-8")

    def prepare_inputs(self):
        self.write("data/interim/ojp_snapshots/ojp_snapshot_example.csv")
        self.write("data/interim/weather_snapshots/weather_snapshot_example.csv")
        for file in workflow.input_groups(self.root)["SQL and geographic reference"]:
            self.write(file.relative_to(self.root))
        self.write("src/model_regression.py")
        self.write("pyproject.toml")
        self.write("uv.lock")

    def test_preflight_is_read_only_and_does_not_touch_existing_report(self):
        self.write(workflow.SUMMARY, "previous result")
        with self.assertRaisesRegex(RuntimeError, "left untouched"):
            workflow.run_pipeline(self.root)
        self.assertEqual((self.root / workflow.SUMMARY).read_text(), "previous result")
        self.assertFalse((self.root / workflow.MANIFEST).exists())

    def test_pipeline_runs_local_stages_and_verification_detects_drift(self):
        self.prepare_inputs()
        self.write("results/figures/old.png")

        def fake_child(root, script):
            self.assertEqual(root, self.root)
            self.assertNotIn("collect", script)
            if script.endswith("final_results.py"):
                for relative in workflow.REQUIRED_OUTPUTS:
                    self.write(relative)
                self.write("results/figures/12_regression_model_mae.png")

        with patch.object(workflow, "run_child", side_effect=fake_child) as run:
            workflow.run_pipeline(self.root)
        self.assertEqual(run.call_count, len(workflow.STAGES))
        summary = (self.root / workflow.SUMMARY).read_text(encoding="utf-8")
        self.assertIn("12_regression_model_mae.png", summary)
        self.assertNotIn("old.png", summary)
        self.assertTrue(workflow.verify(self.root))
        self.write("data/interim/weather_snapshots/weather_snapshot_new.csv")
        self.assertFalse(workflow.verify(self.root))

    def test_failed_stage_marks_run_failed_and_stops(self):
        self.prepare_inputs()
        with patch.object(workflow, "run_child", side_effect=RuntimeError("fixture error")) as run:
            with self.assertRaisesRegex(RuntimeError, "fixture error"):
                workflow.run_pipeline(self.root)
        self.assertEqual(run.call_count, 1)
        manifest = json.loads((self.root / workflow.MANIFEST).read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "failed")
        self.assertEqual(manifest["stages"], {"build_dataset": "failed"})
        self.assertFalse(workflow.verify(self.root))

    def test_verify_rejects_output_path_escape(self):
        self.prepare_inputs()
        manifest = {
            "schema_version": 1, "status": "completed", "inputs": {}, "code": {},
            "outputs": dict.fromkeys([*workflow.REQUIRED_OUTPUTS, workflow.SUMMARY.as_posix(), "../outside.txt"]),
        }
        workflow.write_manifest(self.root, manifest)
        self.assertFalse(workflow.verify(self.root))
