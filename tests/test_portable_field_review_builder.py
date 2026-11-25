"""Verify the portable application boundaries using isolated Git histories."""
from hashlib import sha256
from pathlib import Path
import runpy
import subprocess

import pytest


BUILDER = Path(__file__).resolve().parents[1] / "experiments/course-defense-20261118/field-review-trial/build.py"


@pytest.mark.parametrize("edition", ["r4_2", "r4_3", "r4_4", "r4_5", "r4_6"])
def test_keeps_existing_release_manifest(tmp_path, edition):
    manifest = tmp_path / "发布指纹.json"
    manifest.write_bytes(b"previous edition")
    build = runpy.run_path(str(BUILDER))["build"]
    with pytest.raises(ValueError, match="全新的输出目录"):
        build(tmp_path / "base.zip", tmp_path, "a" * 40, **{edition: True})
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
    monkeypatch.setitem(check.__globals__, "R42_COMMIT", candidate)

    if failure:
        with pytest.raises(ValueError, match="r4.2"):
            check(candidate)
    else:
        assert check(candidate) == ["static/doctor-workspace.css", "static/doctor.html", "static/doctor.js"]

@pytest.mark.parametrize("failure", [None, "extra_html", "stale_js_stamp", "static/doctor-workspace.css",
                                     "app/main.py", "docs/pilot/doctor-v1/manual.html", "scripts/package_help.py"])
def test_r43_excludes_new_app_from_old_edition_and_limits_changes(tmp_path, monkeypatch, failure):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=tmp_path, check=True)
    old_js, candidate_js, released_js, new_js = ("one()", "two()", "three()", "four()")
    old_css, css = ("main {margin: 1px}", "main {margin: 2px}")
    r41 = commit_files(tmp_path, {
        "static/doctor.js": old_js, "static/doctor-workspace.css": old_css,
        "static/doctor.html": html_for(old_js, old_css), "scripts/package_help.py": 'ALLOWLIST = ["manual.html"]',
        "docs/pilot/doctor-v1/manual.html": "frozen manual",
    })
    prior_candidate = commit_files(tmp_path, {"static/doctor.js": candidate_js, "static/doctor-workspace.css": css,
                                            "static/doctor.html": html_for(candidate_js, css)})
    r42 = commit_files(tmp_path, {"static/doctor.js": released_js, "static/doctor.html": html_for(released_js, css)})
    files = {"static/doctor.js": new_js, "static/doctor.html": html_for(new_js, css)}
    if failure == "extra_html":
        files["static/doctor.html"] += "unreviewed markup"
    elif failure == "stale_js_stamp":
        files["static/doctor.html"] = html_for(released_js, css)
    elif failure:
        files[failure] = "unapproved content"
    candidate = commit_files(tmp_path, files)
    functions = runpy.run_path(str(BUILDER))
    r42_check, r43_check = functions["verify_r42_changes"], functions["verify_r43_changes"]
    monkeypatch.setitem(r42_check.__globals__, "REPO", tmp_path)
    monkeypatch.setitem(r42_check.__globals__, "R41_COMMIT", r41)
    monkeypatch.setitem(r42_check.__globals__, "R42_COMMIT", r42)
    monkeypatch.setitem(r43_check.__globals__, "R43_COMMIT", candidate)
    assert len(r42_check(prior_candidate)) == 3
    assert len(r42_check(r42)) == 3
    with pytest.raises(ValueError, match="r4.2"):
        r42_check(candidate)
    with pytest.raises(ValueError, match="r4.3"):
        r43_check(prior_candidate)
    with pytest.raises(ValueError, match="r4.3"):
        r43_check(r42)
    if failure:
        with pytest.raises(ValueError, match="r4.3"):
            r43_check(candidate)
    else:
        assert r43_check(candidate) == ["static/doctor.html", "static/doctor.js"]


@pytest.mark.parametrize("failure", [None, "missing_backend", "missing_manual", "missing_index", "extra_html",
                                     "stale_js_stamp", "app/main.py", "static/doctor-workspace.css",
                                     "scripts/package_help.py", "docs/pilot/doctor-v1/other.html"])
def test_r44_freezes_application_help_and_knowledge_changes(tmp_path, monkeypatch, failure):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=tmp_path, check=True)
    css = "main { margin: 0; }"
    backend, manual, index = "app/services/knowledge_store.py", "docs/pilot/doctor-v1/manual.html", "static/help/index.html"
    r42 = commit_files(tmp_path, {
        "static/doctor.js": "r42()", "static/doctor.html": html_for("r42()", css), "static/doctor-workspace.css": css,
        backend: "value = 1", manual: "old manual", index: "old index",
        "scripts/package_help.py": 'ALLOWLIST = ["manual.html", "other.html"]',
        "docs/pilot/doctor-v1/other.html": "frozen help",
    })
    r43 = commit_files(tmp_path, {"static/doctor.js": "r43()", "static/doctor.html": html_for("r43()", css)})
    changes = {"static/doctor.js": "r44()", "static/doctor.html": html_for("r44()", css),
               backend: "value = 2", manual: "new manual", index: "new index"}
    expected = sorted(changes)
    missing = {"missing_backend": backend, "missing_manual": manual, "missing_index": index}
    if failure in missing:
        del changes[missing[failure]]
    elif failure == "extra_html":
        changes["static/doctor.html"] += "unapproved markup"
    elif failure == "stale_js_stamp":
        changes["static/doctor.html"] = html_for("r42()", css)
    elif failure:
        changes[failure] = "unapproved change"
    r44 = commit_files(tmp_path, changes)
    functions = runpy.run_path(str(BUILDER))
    check = functions["verify_r44_changes"]
    for key, value in (("REPO", tmp_path), ("R42_COMMIT", r42), ("R43_COMMIT", r43), ("R44_COMMIT", r44)):
        monkeypatch.setitem(check.__globals__, key, value)
    assert functions["verify_r43_changes"](r43) == ["static/doctor.html", "static/doctor.js"]
    with pytest.raises(ValueError, match="r4.3"):
        functions["verify_r43_changes"](r44)
    with pytest.raises(ValueError, match="r4.4"):
        check(r43)
    if failure:
        with pytest.raises(ValueError, match="r4.4"):
            check(r44)
    else:
        assert check(r44) == expected
        later = commit_files(tmp_path, {backend: "value = 3"})
        with pytest.raises(ValueError, match="r4.4"):
            check(later)


@pytest.mark.parametrize("failure", [None, "app/services/knowledge_store.py", "docs/pilot/doctor-v1/manual.html",
                                     "extra_html", "stale_js_stamp"])
def test_r45_freezes_only_the_doctor_script_and_its_stamp(tmp_path, monkeypatch, failure):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=tmp_path, check=True)
    css = "main { margin: 0; }"
    previous = commit_files(tmp_path, {
        "static/doctor.js": "old()", "static/doctor.html": html_for("old()", css),
        "scripts/package_help.py": 'ALLOWLIST = ["manual.html"]', "docs/pilot/doctor-v1/manual.html": "manual",
        "app/services/knowledge_store.py": "value = 1",
    })
    changed = {"static/doctor.js": "new()", "static/doctor.html": html_for("new()", css)}
    if failure == "extra_html":
        changed["static/doctor.html"] += "unreviewed markup"
    elif failure == "stale_js_stamp":
        changed["static/doctor.html"] = html_for("wrong()", css)
    elif failure:
        changed[failure] = "unreviewed"
    current = commit_files(tmp_path, changed)
    functions = runpy.run_path(str(BUILDER))
    verify = functions["verify_r45_changes"]
    for key, value in (("REPO", tmp_path), ("R44_COMMIT", previous), ("R45_COMMIT", current)):
        monkeypatch.setitem(verify.__globals__, key, value)
    with pytest.raises(ValueError, match="r4.5"):
        verify(previous)
    with pytest.raises(ValueError, match="r4.4"):
        functions["verify_r44_changes"](current)
    if failure:
        with pytest.raises(ValueError, match="r4.5"):
            verify(current)
    else:
        assert verify(current) == ["static/doctor.html", "static/doctor.js"]
        descendant = commit_files(tmp_path, {"static/doctor.js": "another()",
                                              "static/doctor.html": html_for("another()", css)})
        with pytest.raises(ValueError, match="r4.5"):
            verify(descendant)


@pytest.mark.parametrize("failure", [None, "extra_asset", "stale_css", "stale_script", "duplicate_stamp"])
def test_r46_freezes_the_reviewed_markup_and_its_two_assets(tmp_path, monkeypatch, failure):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=tmp_path, check=True)
    previous = commit_files(tmp_path, {
        "static/doctor.js": "old()", "static/doctor-workspace.css": "body { color: navy; }",
        "static/doctor.html": html_for("old()", "body { color: navy; }"),
        "scripts/package_help.py": 'ALLOWLIST = ["manual.html"]', "docs/pilot/doctor-v1/manual.html": "manual",
    })
    script, css = "new()", ".encounter { display: grid; }"
    html = html_for("old()" if failure == "stale_script" else script, "" if failure == "stale_css" else css)
    changes = {"static/doctor.js": script, "static/doctor-workspace.css": css,
               "static/doctor.html": html + "<main>患者摘要和病历</main>"}
    if failure == "extra_asset":
        changes["static/another.js"] = "other()"
    if failure == "duplicate_stamp":
        changes["static/doctor.html"] += html
    current = commit_files(tmp_path, changes)
    functions = runpy.run_path(str(BUILDER))
    verify = functions["verify_r46_changes"]
    for key, value in (("REPO", tmp_path), ("R45_COMMIT", previous), ("R46_COMMIT", current)):
        monkeypatch.setitem(verify.__globals__, key, value)
    with pytest.raises(ValueError, match="r4.6"):
        verify(previous)
    with pytest.raises(ValueError, match="r4.5"):
        functions["verify_r45_changes"](current)
    if failure:
        with pytest.raises(ValueError, match="r4.6"):
            verify(current)
    else:
        assert verify(current) == sorted(changes)
