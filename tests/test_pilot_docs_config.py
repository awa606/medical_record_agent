from __future__ import annotations

import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"ghp_[A-Za-z0-9_]{12,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)(api[_-]?key|token|password)[ \t]*[:=][ \t]*['\"]?(?!$)(?![ \t]*$)(?!<)(?!\*\*\*)[A-Za-z0-9_\-]{12,}"),
]


class PilotDocsConfigTests(unittest.TestCase):
    def test_pilot_example_does_not_commit_secret_values(self):
        example = PROJECT_ROOT / "config" / "pilot.department.env.example"
        text = example.read_text(encoding="utf-8")

        self.assertIn("MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD=", text)
        self.assertIn("ONLINE_LLM_API_KEY=", text)
        self.assertNotIn("admin123456", text)
        self.assertNoRealSecret(text)

    def test_pilot_docs_do_not_repeat_obsolete_auth_claim_or_real_secrets(self):
        paths = list((PROJECT_ROOT / "docs" / "pilot").glob("*.md")) + [PROJECT_ROOT / "docs" / "docker_local_deploy.md"]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

        self.assertNotIn("系统没有登录认证", combined)
        self.assertNotIn("当前系统没有登录认证", combined)
        self.assertNoRealSecret(combined)

    def assertNoRealSecret(self, text: str) -> None:
        for pattern in SECRET_PATTERNS:
            self.assertIsNone(pattern.search(text), pattern.pattern)


if __name__ == "__main__":
    unittest.main()
