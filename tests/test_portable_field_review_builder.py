"""Keep the r4.2 source boundary testable from a shallow checkout."""
from hashlib import sha256
from pathlib import Path
import runpy
import subprocess

import pytest


BUILDER = Path(__file__).resolve().parents[1] / "experiments/course-defense-20261118/field-review-trial/build.py"


def test_r42_keeps_existing_release_manifest(tmp_path):
    manifest = tmp_path / "发布指纹.json"
    manifest.write_bytes(b"previous edition")
    build = runpy.run_path(str(BUILDER))["build"]
    with pytest.raises(ValueError, match="全新的输出目录"):
        build(tmp_path / "base.zip", tmp_path, "a" * 40, r4_2=True)
    assert manifest.read_bytes() == b"previous edition"


def html_for(script: str, css: str) -> str:
    script_stamp = sha256(script.encode()).hexdigest()[:16]
    css_stamp = sha256(css.encode()).hexdigest()[:16]
    return f'<link href="./doctor-workspace.css?v={css_stamp}">\n<script src="./doctor.js?v={script_stamp}"></script>\n'


def commit_files(repo: Path, files: dict[str, str]) -> str:
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode())
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=Builder Test", "-c", "user.email=test@example.invalid",
                    "-c", "commit.gpgsign=false", "commit", "-qm", "Fixture"], cwd=repo, check=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()


@pytest.mark.parametrize("failure", [None, "app/main.py", "docs/pilot/doctor-v1/manual.html",
                                     "scripts/package_help.py", "extra_html", "stale_css_stamp", "stale_js_stamp"])
def test_r42_packages_only_approved_changes(tmp_path, monkeypatch, failure):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=tmp_path, check=True)
    old = "console.log(1);"
    new = "console.log(2);"
    old_css = "main { display: block; }"
    new_css = "main { display: grid; }"
    baseline = commit_files(tmp_path, {
        "static/doctor.js": old, "static/doctor-workspace.css": old_css, "static/doctor.html": html_for(old, old_css),
        "scripts/package_help.py": 'ALLOWLIST = ["manual.html"]\n',
        "docs/pilot/doctor-v1/manual.html": "approved text",
    })
    files = {"static/doctor.js": new, "static/doctor-workspace.css": new_css, "static/doctor.html": html_for(new, new_css)}
    if failure == "extra_html":
        files["static/doctor.html"] += "unreviewed change"
    elif failure == "stale_js_stamp":
        files["static/doctor.html"] = html_for(old, new_css)
    elif failure == "stale_css_stamp":
        files["static/doctor.html"] = html_for(new, old_css)
    elif failure:
        files[failure] = "unreviewed"
    candidate = commit_files(tmp_path, files)
    check = runpy.run_path(str(BUILDER))["verify_r42_changes"]
    monkeypatch.setitem(check.__globals__, "REPO", tmp_path)
    monkeypatch.setitem(check.__globals__, "R41_COMMIT", baseline)

    if failure:
        with pytest.raises(ValueError, match="r4.2"):
            check(candidate)
    else:
        assert check(candidate) == ["static/doctor-workspace.css", "static/doctor.html", "static/doctor.js"]
