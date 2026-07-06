import os
import tempfile
import unittest
from pathlib import Path

from app.dataset_pipeline.annotation import sample_annotation_set
from app.dataset_pipeline.filtering import build_quality_flags, filter_toyhom_cold_cases, is_cold_candidate
from app.dataset_pipeline.gold_eval import evaluate_on_gold_set
from app.dataset_pipeline.ingest import ingest_toyhom_dataset
from app.dataset_pipeline.jsonl import read_jsonl, write_jsonl
from app.dataset_pipeline.pseudo_emr import build_pseudo_emr_dataset, extract_pseudo_fields


class ToyhomDatasetPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.raw_dir = self.root / "raw_external"
        self.processed_dir = self.root / "processed"
        self.annotation_dir = self.root / "annotation"
        self.output_dir = self.root / "output"
        self.raw_dir.mkdir()
        self.processed_dir.mkdir()
        self.annotation_dir.mkdir()
        self.output_dir.mkdir()

        csv_text = (
            "department,title,ask,answer\n"
            "呼吸科,感冒咳嗽发热2天,我这两天发烧咳嗽，还有鼻塞流鼻涕，吃了感冒药。,建议线下就医。\n"
            "皮肤科,湿疹咨询,皮肤痒，联系电话13812345678。,广告内容。\n"
        )
        (self.raw_dir / "toyhom_sample.csv").write_text(csv_text, encoding="gb18030")

    def tearDown(self):
        os.environ.pop("MEDICAL_RECORD_AGENT_DB", None)
        self.temp_dir.cleanup()

    def test_ingest_reads_gb18030_csv(self):
        output = self.processed_dir / "toyhom_clean.jsonl"
        count = ingest_toyhom_dataset(self.raw_dir, output)

        records = read_jsonl(output)
        self.assertEqual(count, 2)
        self.assertEqual(records[0]["department"], "呼吸科")
        self.assertEqual(records[0]["question"], "我这两天发烧咳嗽，还有鼻塞流鼻涕，吃了感冒药。")
        self.assertTrue(records[0]["case_id"].startswith("toyhom_"))

    def test_keyword_filtering_and_contact_flags(self):
        cold_record = {"title": "感冒咳嗽", "question": "发热鼻塞", "answer": "", "department": "呼吸科"}
        contact_record = {"title": "咨询", "question": "请加微信或电话13812345678", "answer": "", "department": "皮肤科"}

        self.assertTrue(is_cold_candidate(cold_record))
        flags = build_quality_flags(contact_record)
        self.assertTrue(flags["contains_contact_info"])
        self.assertTrue(flags["needs_manual_review"])

    def test_filter_script_output(self):
        clean_path = self.processed_dir / "toyhom_clean.jsonl"
        cold_path = self.processed_dir / "toyhom_cold_candidates.jsonl"
        ingest_toyhom_dataset(self.raw_dir, clean_path)
        count = filter_toyhom_cold_cases(clean_path, cold_path)

        records = read_jsonl(cold_path)
        self.assertEqual(count, 1)
        self.assertIn("发烧", records[0]["matched_keywords"])
        self.assertFalse(records[0]["quality_flags"]["contains_contact_info"])

    def test_pseudo_fields_basic_structure(self):
        record = {
            "title": "感冒咳嗽发热2天",
            "question": "我这两天发烧咳嗽，还有鼻塞流鼻涕，吃了感冒药。",
        }
        fields = extract_pseudo_fields(record)

        self.assertIn("chief_complaint", fields)
        self.assertIn("evidence_text", fields["symptoms"])
        self.assertIn("发热", fields["symptoms"]["value"])
        self.assertFalse(fields["duration"]["missing"])
        self.assertTrue(fields["allergy_history"]["missing"])

    def test_build_annotation_and_gold_evaluation_can_run(self):
        clean_path = self.processed_dir / "toyhom_clean.jsonl"
        cold_path = self.processed_dir / "toyhom_cold_candidates.jsonl"
        pseudo_path = self.processed_dir / "pseudo_emr_cases.jsonl"
        sample_path = self.annotation_dir / "annotation_sample_100.jsonl"
        guide_path = self.annotation_dir / "annotation_guide.md"
        gold_path = self.annotation_dir / "gold_100.jsonl"
        report_path = self.output_dir / "toyhom_gold_evaluation_report.md"

        ingest_toyhom_dataset(self.raw_dir, clean_path)
        filter_toyhom_cold_cases(clean_path, cold_path)
        build_pseudo_emr_dataset(cold_path, pseudo_path)
        sample_count = sample_annotation_set(pseudo_path, sample_path, guide_path, sample_size=1)
        self.assertEqual(sample_count, 1)

        records = read_jsonl(sample_path)
        records[0]["gold_fields"] = records[0]["pseudo_fields"]
        write_jsonl(gold_path, records)

        os.environ["MEDICAL_RECORD_AGENT_DB"] = str(self.root / "test.sqlite3")
        report = evaluate_on_gold_set(gold_path, report_path)

        self.assertEqual(report["aggregate"]["case_count"], 1)
        self.assertTrue(report_path.exists())
        self.assertIn("字段抽取评估报告", report_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
