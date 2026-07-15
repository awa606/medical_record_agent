import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.evaluate_speaker_role_dataset import (
    DatasetValidationError,
    evaluate_dataset,
    load_dataset,
    main,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = PROJECT_ROOT / "data" / "asr_eval" / "frozen_clinical_v1"
MANIFEST = DATASET_DIR / "manifest.json"


class FrozenClinicalSpeakerRoleDatasetTests(unittest.TestCase):
    def test_manifest_loads_and_covers_required_scenarios(self):
        dataset = load_dataset(MANIFEST)

        self.assertEqual(dataset["dataset_version"], "frozen_clinical_v1")
        self.assertEqual(len(dataset["samples"]), 6)
        scenario_types = {item["manifest"]["scenario_type"] for item in dataset["samples"]}
        self.assertIn("two_party_clean", scenario_types)
        self.assertIn("three_party_family", scenario_types)
        self.assertIn("single_reader_counterexample", scenario_types)
        self.assertIn("noisy_background", scenario_types)
        self.assertIn("interruption", scenario_types)
        self.assertIn("overlap", scenario_types)

    def test_evaluate_dataset_computes_baseline_metrics(self):
        report = evaluate_dataset(MANIFEST)

        self.assertEqual(report["sample_count"], 6)
        self.assertEqual(report["split_counts"], {"calibration": 3, "test": 3})
        self.assertEqual(report["metrics"]["high_confidence_error_count"], 0)
        self.assertGreaterEqual(report["metrics"]["role_accuracy"], 0.95)
        self.assertGreater(report["metrics"]["auto_accept_coverage"], 0)
        self.assertGreater(report["metrics"]["mixed_utterance_rate"], 0)
        self.assertEqual(report["hash_status"]["failed_count"], 0)

    def test_cli_writes_json_and_markdown_reports(self):
        import sys

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "baseline.json"
            old_argv = sys.argv
            try:
                sys.argv = [
                    "evaluate_speaker_role_dataset.py",
                    "--manifest",
                    str(MANIFEST),
                    "--output",
                    str(output),
                ]
                self.assertEqual(main(), 0)
            finally:
                sys.argv = old_argv

            self.assertTrue(output.exists())
            self.assertTrue(output.with_suffix(".md").exists())
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertIn("keyword_recall", payload["metrics"])

    def test_bad_fixture_hash_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dataset = Path(temp_dir) / "dataset"
            shutil.copytree(DATASET_DIR, temp_dataset)
            manifest_path = temp_dataset / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["samples"][0]["sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            with self.assertRaises(DatasetValidationError):
                load_dataset(manifest_path)

    def test_bad_annotation_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dataset = Path(temp_dir) / "dataset"
            shutil.copytree(DATASET_DIR, temp_dataset)
            manifest_path = temp_dataset / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            annotation_path = temp_dataset / manifest["samples"][0]["annotation_path"]
            annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
            annotation.pop("speaker_roles")
            annotation_path.write_text(json.dumps(annotation, ensure_ascii=False), encoding="utf-8")

            with self.assertRaises(DatasetValidationError):
                load_dataset(manifest_path)

    def test_calibration_and_test_splits_are_disjoint(self):
        dataset = load_dataset(MANIFEST)
        calibration = {
            item["manifest"]["sample_id"]
            for item in dataset["samples"]
            if item["manifest"]["split"] == "calibration"
        }
        test = {
            item["manifest"]["sample_id"]
            for item in dataset["samples"]
            if item["manifest"]["split"] == "test"
        }

        self.assertTrue(calibration)
        self.assertTrue(test)
        self.assertFalse(calibration & test)


if __name__ == "__main__":
    unittest.main()
