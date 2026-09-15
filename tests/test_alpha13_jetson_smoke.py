import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_alpha13_jetson_smoke.py"


def test_dry_run_refuses_non_jetson_without_claiming_pass():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(result.stdout)
    if payload["hardware_detected"]:
        assert result.returncode == 0
        assert payload["result"] == "READY_FOR_PREFLIGHT"
    else:
        assert result.returncode == 3
        assert payload["result"] == "HARDWARE_BLOCKED"
    assert payload["claims"] == {
        "jetson_pass": False,
        "provider_pass": False,
        "alpha_pass": False,
    }
    assert "funasr_isolated_smoke" in payload["planned_stages"]

