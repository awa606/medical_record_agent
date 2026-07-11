import tarfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.prepare_three_speaker_public_sample import (
    _parse_textgrid,
    _relative_turns,
    _safe_extract,
    _select_window,
    _write_rttm,
)


class PrepareThreeSpeakerPublicSampleTests(unittest.TestCase):
    def test_textgrid_three_speaker_window_can_write_rttm(self):
        textgrid = """
File type = "ooTextFile"
Object class = "TextGrid"

item [1]:
    class = "IntervalTier"
    name = "speaker_A"
    intervals [1]:
        xmin = 0
        xmax = 2.2
        text = "你好"
item [2]:
    class = "IntervalTier"
    name = "speaker_B"
    intervals [1]:
        xmin = 2.0
        xmax = 4.1
        text = "我发热"
item [3]:
    class = "IntervalTier"
    name = "speaker_C"
    intervals [1]:
        xmin = 3.5
        xmax = 5.0
        text = "我是家属"
"""
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.TextGrid"
            path.write_text(textgrid, encoding="utf-8")
            turns = _parse_textgrid(path)
            self.assertEqual({turn.speaker_id for turn in turns}, {"speaker_A", "speaker_B", "speaker_C"})

            window = _select_window(turns, duration=5.0, min_speakers=3)
            self.assertEqual(window, (0.0, 5.0))

            relative = _relative_turns(turns, start=0.0, end=5.0)
            rttm = Path(tmp) / "three_speaker_alimeeting_01.rttm"
            _write_rttm(rttm, relative, "three_speaker_alimeeting_01")

            lines = rttm.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 3)
            self.assertTrue(all(line.startswith("SPEAKER three_speaker_alimeeting_01") for line in lines))

    def test_safe_extract_rejects_path_traversal(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "unsafe.tar"
            payload = root / "payload.txt"
            payload.write_text("x", encoding="utf-8")
            with tarfile.open(archive, "w") as tar:
                tar.add(payload, arcname="../evil.txt")

            with tarfile.open(archive, "r") as tar:
                with self.assertRaises(RuntimeError):
                    _safe_extract(tar, root / "extract")


if __name__ == "__main__":
    unittest.main()
