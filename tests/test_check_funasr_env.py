import subprocess
import sys
import unittest


class CheckFunASREnvScriptTests(unittest.TestCase):
    def test_check_funasr_env_script_runs(self):
        result = subprocess.run(
            [sys.executable, "scripts/check_funasr_env.py"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("sys.executable:", result.stdout)
        self.assertIn("torch", result.stdout)
        self.assertIn("funasr", result.stdout)
        self.assertIn("from funasr import AutoModel:", result.stdout)


if __name__ == "__main__":
    unittest.main()
