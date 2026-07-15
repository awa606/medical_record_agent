import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate_executable_speaker_role_dataset import (
    ExecutableDatasetValidationError,
    evaluate_dataset,
    load_dataset,
    main,
)


DATASET_DIR = PROJECT_ROOT / "data" / "asr_eval" / "executable_clinical_v1"
MANIFEST = DATASET_DIR / "manifest.json"
RULES_PREDICTIONS = DATASET_DIR / "predictions" / "rules"


class ExecutableClinicalSpeakerRoleDatasetTests(unittest.TestCase):
    def test_manifest_loads_required_sample_count_and_scenarios(self):
        dataset = load_dataset(MANIFEST)

        self.assertEqual(dataset["dataset_version"], "executable_clinical_v1")
        self.assertEqual(len(dataset["samples"]), 23)
        self.assertEqual(dataset["all_split_counts"], {"calibration": 12, "test": 11})

        scenario_counts: dict[str, int] = {}
        for item in dataset["samples"]:
            scenario = item["manifest"]["scenario_type"]
            scenario_counts[scenario] = scenario_counts.get(scenario, 0) + 1

        self.assertEqual(scenario_counts["two_party"], 10)
        self.assertEqual(scenario_counts["three_party_family"], 5)
        self.assertEqual(scenario_counts["single_reader_counterexample"], 3)
        self.assertEqual(scenario_counts["noisy_background"], 2)
        self.assertEqual(scenario_counts["interruption"], 1)
        self.assertEqual(scenario_counts["overlap"], 1)
        self.assertEqual(scenario_counts["noise_interruption_overlap"], 1)

    def test_truth_annotations_do_not_embed_predictions(self):
        dataset = load_dataset(MANIFEST)

        for item in dataset["samples"]:
            annotation = item["annotation"]
            self.assertNotIn("baseline_prediction", annotation)
            self.assertNotIn("prediction", annotation)
            self.assertNotIn("speaker_decisions", annotation)

    def test_rules_report_contains_provider_grouped_product_metrics(self):
        report = evaluate_dataset(MANIFEST, provider="rules")

        self.assertEqual(report["sample_count"], 23)
        self.assertIn("rules", report["provider_reports"])
        self.assertTrue(report["provider_reports"]["rules"]["counts_as_product_accuracy"])
        self.assertEqual(report["metrics"]["high_confidence_error_count"], 0)
        self.assertGreaterEqual(report["metrics"]["role_accuracy"], 0.95)
        self.assertIn("role_accuracy", report["confidence_intervals_95"])
        self.assertEqual(report["hash_status"]["verified_count"], 23)

    def test_cli_generates_independent_prediction_artifacts_and_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "rules.json"
            prediction_dir = Path(temp_dir) / "predictions" / "rules"
            old_argv = sys.argv
            try:
                sys.argv = [
                    "evaluate_executable_speaker_role_dataset.py",
                    "--manifest",
                    str(MANIFEST),
                    "--provider",
                    "rules",
                    "--generate-predictions",
                    "--prediction-dir",
                    str(prediction_dir),
                    "--output",
                    str(output),
                ]
                self.assertEqual(main(), 0)
            finally:
                sys.argv = old_argv

            self.assertTrue(output.exists())
            self.assertTrue(output.with_suffix(".md").exists())
            generated_predictions = list(prediction_dir.glob("*.prediction.json"))
            self.assertEqual(len(generated_predictions), 23)

    def test_audio_paths_are_scoped_to_lfs_attributes(self):
        gitattributes = (PROJECT_ROOT / ".gitattributes").read_text(encoding="utf-8")

        self.assertIn("data/asr_eval/executable_clinical_v1/audio/**/*.wav filter=lfs", gitattributes)
        self.assertIn("data/asr_eval/executable_clinical_v1/audio/**/*.flac filter=lfs", gitattributes)

    def test_bad_audio_hash_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = _write_absolute_manifest(Path(temp_dir))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["samples"][0]["sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            with self.assertRaises(ExecutableDatasetValidationError):
                load_dataset(manifest_path)

    def test_missing_audio_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = _write_absolute_manifest(Path(temp_dir))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["samples"][0]["audio_ref"] = str(Path(temp_dir) / "missing.wav")
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            with self.assertRaises(ExecutableDatasetValidationError):
                load_dataset(manifest_path)

    def test_truth_annotation_with_prediction_fields_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            manifest_path = _write_absolute_manifest(temp_dir_path)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            annotation = json.loads(Path(manifest["samples"][0]["annotation_path"]).read_text(encoding="utf-8"))
            annotation["baseline_prediction"] = {"speaker_roles": {"spk0": "doctor"}}
            bad_annotation_path = temp_dir_path / "bad_annotation.json"
            bad_annotation_path.write_text(json.dumps(annotation, ensure_ascii=False), encoding="utf-8")
            manifest["samples"][0]["annotation_path"] = str(bad_annotation_path)
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            with self.assertRaises(ExecutableDatasetValidationError):
                load_dataset(manifest_path)

    def test_bad_prediction_schema_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            prediction_dir = _copy_prediction_dir(Path(temp_dir) / "predictions")
            first_prediction = next(prediction_dir.glob("*.prediction.json"))
            payload = json.loads(first_prediction.read_text(encoding="utf-8"))
            payload["speaker_decisions"][0].pop("raw_confidence")
            first_prediction.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            with self.assertRaises(ExecutableDatasetValidationError):
                evaluate_dataset(MANIFEST, provider="rules", prediction_dir=prediction_dir)

    def test_mock_predictions_are_excluded_from_product_metrics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            prediction_dir = _copy_prediction_dir(Path(temp_dir) / "mock_predictions")
            for path in prediction_dir.glob("*.prediction.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload["provider"] = "mock"
                payload["provider_version"] = "mock-smoke-v1"
                for decision in payload["speaker_decisions"]:
                    decision["provider"] = "mock"
                    decision["provider_version"] = "mock-smoke-v1"
                path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            report = evaluate_dataset(MANIFEST, provider="mock", prediction_dir=prediction_dir)

            self.assertFalse(report["counts_as_product_accuracy"])
            self.assertTrue(report["mock_excluded_from_product_metrics"])
            self.assertFalse(report["provider_reports"]["mock"]["counts_as_product_accuracy"])

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

    def test_calibration_mode_refuses_test_split(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_argv = sys.argv
            try:
                sys.argv = [
                    "evaluate_executable_speaker_role_dataset.py",
                    "--manifest",
                    str(MANIFEST),
                    "--provider",
                    "rules",
                    "--split",
                    "test",
                    "--calibrate",
                    "--output",
                    str(Path(temp_dir) / "report.json"),
                ]
                self.assertEqual(main(), 2)
            finally:
                sys.argv = old_argv


def _write_absolute_manifest(temp_dir: Path) -> Path:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for sample in manifest["samples"]:
        sample["audio_ref"] = str((DATASET_DIR / sample["audio_ref"]).resolve())
        sample["annotation_path"] = str((DATASET_DIR / sample["annotation_path"]).resolve())
    manifest_path = temp_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return manifest_path


def _copy_prediction_dir(target: Path) -> Path:
    shutil.copytree(RULES_PREDICTIONS, target)
    return target


if __name__ == "__main__":
    unittest.main()
