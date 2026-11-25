"""Offline browser checks for the organizer's anonymous three-case receipt.

Set MRA_TIMELINE_REVIEW_ZIP to exercise the pinned distribution itself. Otherwise
a temporary page pins the SHA of a generated test ZIP; the production HTML has
no test override. MRA_TIMELINE_REVIEW_EVIDENCE optionally retains screenshots
and redacted receipts.
"""
import hashlib
import json
import os
from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile

import pytest
from playwright.sync_api import expect, sync_playwright


PAGE = Path(__file__).resolve().parents[1] / "experiments/clinical-review-20261124/visit_timeline_intake.html"
PIN = "167679e8e34ae951f7c59f30f133f16352110619584263430c566006ea1830ef"
ORIGIN = "项目原创合成书面材料。角色台词、就诊号、报告和时间均虚构。"
DATES = {
    "A": ("2026-06-09 09:12", "2026-06-09 11:05", "L01"),
    "B": ("2026-06-12 14:17", "2026-06-12 15:40", "R01"),
    "C": ("2026-07-02 10:08", "2026-07-02 13:10", "N01"),
}


def complete(code):
    case = "SYN-TM-" + code
    _, end, late = DATES[code]
    return {
        "format": "MRA-visit-time-portable-1", "encounter": case, "origin": ORIGIN,
        "visibleThrough": end, "phase": 3, "completion": "complete",
        "entries": [
            {"stage": 1, "text": "独立模拟初诊-不进回执", "sourceIds": [case + "-T01"],
             "lockedAt": "2026-11-24T01:10:12.000Z"},
            {"stage": 2, "text": "独立模拟补记-不进回执", "sourceIds": [case + "-" + late],
             "lockedAt": "2026-11-24T01:11:12.000Z"},
        ],
    }


def to_upload(payload, name="不进回执样件.json", *, sorted_keys=False):
    return {"name": name, "mimeType": "application/json",
            "buffer": json.dumps(payload, ensure_ascii=False, sort_keys=sorted_keys).encode()}


@pytest.fixture(scope="module")
def runtime(tmp_path_factory):
    folder = tmp_path_factory.mktemp("portable-intake")
    actual = os.environ.get("MRA_TIMELINE_REVIEW_ZIP")
    if actual:
        archive = Path(actual)
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == PIN
        page = Path(os.environ.get("MRA_TIMELINE_REVIEW_PAGE", PAGE)).resolve()
        assert page.read_bytes() == PAGE.read_bytes()
        with ZipFile(archive) as z:
            exercise = folder / "export.html"
            exercise.write_bytes(z.read("三例就诊盲练.html"))
    else:
        archive = folder / "synthetic.zip"
        with ZipFile(archive, "w") as z:
            z.writestr("synthetic.txt", b"offline test package")
        text = PAGE.read_text(encoding="utf8")
        assert text.count(PIN) == 1
        page = folder / "test-pin.html"
        page.write_text(text.replace(PIN, hashlib.sha256(archive.read_bytes()).hexdigest()), encoding="utf8")
        exercise = None
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel=os.environ.get("MRA_REVIEW_BROWSER") or None)
        yield browser, page, archive, exercise
        browser.close()


def real_exports(context, exercise):
    """Drive the frozen exercise itself, keep the browser's exact downloaded bytes."""
    if exercise is None:
        return [to_upload(complete(code)) for code in DATES]
    page = context.new_page()
    page.goto(exercise.as_uri())
    files = []
    for index, code in enumerate(DATES):
        page.locator("#case").select_option(str(index))
        for stage in ("初诊", "补记"):
            page.locator("#statement").fill("独立模拟" + stage + "-不进回执")
            page.locator("fieldset input").first.check()
            page.locator("#advance").click()
        with page.expect_download() as event:
            page.get_by_role("button", name="下载本例作答").click()
        item = event.value
        files.append({"name": item.suggested_filename, "mimeType": "application/json",
                      "buffer": Path(item.path()).read_bytes()})
        assert json.loads(files[-1]["buffer"])["encounter"] == "SYN-TM-" + code
    page.close()
    return files


def choose_package(p, path, expected="冻结题包一致"):
    p.locator("#package").set_input_files(path)
    expect(p.locator("#package-status")).to_contain_text(expected)


def assign(p, group):
    p.get_by_label("匿名领包代码").fill(group)
    p.get_by_label("领包用途").select_option(label="工程模拟")
    p.locator("#issued").check()


def add_files(p, files):
    previous = int(p.locator("#total").inner_text())
    p.locator("#files").set_input_files(files)
    p.get_by_role("button", name="登记所选答卷").focus()
    p.keyboard.press("Enter")
    expect(p.locator("#total")).to_have_text(str(previous + len(files)))


def download_receipt(p):
    with p.expect_download() as event:
        p.get_by_role("button", name="下载组织者回执").click()
    item = event.value
    assert item.suggested_filename == "三例评阅组织者回执.json"
    raw = Path(item.path()).read_bytes()
    for secret in ("不进回执", ".json", "独立模拟初诊"):
        assert secret not in raw.decode()
    return json.loads(raw)


def keep_evidence(p, width, receipt, label):
    configured = os.environ.get("MRA_TIMELINE_REVIEW_EVIDENCE")
    if configured:
        directory = Path(configured)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{width}_{label}.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf8")
        p.locator("#result-title").scroll_into_view_if_needed()
        p.screenshot(path=directory / f"{width}_{label}.png")


@pytest.mark.parametrize("width", [1366, 390])
def test_three_complete_repeat_conflict_and_independence(runtime, width):
    browser, html, archive, exercise = runtime
    context = browser.new_context(offline=True, accept_downloads=True, viewport={"width": width, "height": 850})
    network = []
    context.on("request", lambda req: network.append(req.url) if req.url.startswith(("http:", "https:")) else None)
    p = context.new_page()
    p.goto(html.as_uri())
    p.keyboard.press("Tab")
    assert p.locator("#package").evaluate("n=>n===document.activeElement")
    expect(p.locator("#export")).to_be_disabled()
    choose_package(p, archive)
    assign(p, "G01")
    original = real_exports(context, exercise)
    add_files(p, original)
    expect(p.locator("#ready")).to_have_text("1")
    first = download_receipt(p)
    assert first["accepted_group_cases"] == 3
    assert [r["raw_sha256"] for r in first["files"]] == [hashlib.sha256(x["buffer"]).hexdigest() for x in original]
    assert all(len(r["stages"]) == 2 and all(s["locked"] for s in r["stages"]) for r in first["files"])
    for row, original_file in zip(first["files"], original):
        assert [s["locked_at"] for s in row["stages"]] == [s["lockedAt"] for s in json.loads(original_file["buffer"])["entries"]]
    first_summary = p.locator("#rows summary").first
    first_summary.focus()
    p.keyboard.press("Enter")
    expect(p.locator("#rows details").first).to_contain_text("截至 " + DATES["A"][0])
    expect(p.locator("#rows details").first).to_contain_text("SYN-TM-A-L01")
    keep_evidence(p, width, first, "三例齐收")

    a = json.loads(original[0]["buffer"])
    add_files(p, [original[0], to_upload(a, sorted_keys=True)])
    copies = download_receipt(p)
    assert copies["accepted_group_cases"] == 3 and copies["complete_groups"] == 1
    assert [r["decision"] for r in copies["files"]][-2:] == ["重复文件，合计一份", "内容等同，合计一份"]

    changed = deepcopy(a)
    changed["entries"][1]["text"] += "另稿"
    add_files(p, [to_upload(changed)])
    conflict = download_receipt(p)
    assert conflict["accepted_group_cases"] == 2 and conflict["complete_groups"] == 0
    assert all(r["decision"] == "同组同例异稿，全部暂缓" for r in conflict["files"] if r["encounter"] == "SYN-TM-A")
    assign(p, "G02")
    add_files(p, [original[0]])
    result = download_receipt(p)
    assert result["accepted_group_cases"] == 3 and result["complete_groups"] == 0
    assert result["groups"][0]["conflicts"] == ["SYN-TM-A"]
    assert all(g["check_independence"] == ["SYN-TM-A"] for g in result["groups"])
    assert result["files"][-1]["cross_group"]
    assert not p.evaluate("document.documentElement.scrollWidth > innerWidth")
    assert not network
    keep_evidence(p, width, result, "重复异稿与跨组")
    p.reload()
    expect(p.locator("#total")).to_have_text("0")
    expect(p.locator("#group")).to_have_value("")
    choose_package(p, archive)
    assign(p, "G01")
    add_files(p, original)
    reopened = download_receipt(p)
    assert reopened["files"] == first["files"]
    assert reopened["groups"] == first["groups"]
    context.close()


def test_bad_inputs_pending_and_partial_dont_mask_complete(runtime):
    browser, html, archive, _ = runtime
    context = browser.new_context(offline=True, accept_downloads=True)
    p = context.new_page()
    p.goto(html.as_uri())
    good = complete("A")
    add_files(p, [to_upload(good)])
    choose_package(p, {"name":"wrong.zip", "mimeType":"application/zip", "buffer":b"wrong"}, "题包指纹不符")
    assign(p, "G03")
    add_files(p, [to_upload(good)])
    choose_package(p, archive)
    assert not p.locator("#issued").is_checked()
    add_files(p, [to_upload(good)])
    assign(p, "G03")
    invalid = []
    for edit in [
        lambda v: v.update(format="MRA-visit-time-1"),
        lambda v: v.update(origin="其他题源"),
        lambda v: v.update(visibleThrough=DATES["A"][0]),
        lambda v: v["entries"][0].update(sourceIds=["SYN-TM-A-L01"]),
        lambda v: v["entries"][0].update(sourceIds=["SYN-TM-B-T01"]),
        lambda v: v["entries"][1].update(lockedAt=None),
        lambda v: v["entries"][1].update(lockedAt="2026-11-23T01:11:12.000Z"),
        lambda v: v["entries"][0].update(lockedAt="2026-02-30T01:11:12.000Z"),
        lambda v: v["entries"][0].update(text=" "),
        lambda v: v["entries"][0].update(sourceIds=["SYN-TM-A-T01"] * 2),
        lambda v: v.update(extra="unexpected"),
        lambda v: v.update(encounter="SYN-TM-X"),
    ]:
        v=deepcopy(good)
        edit(v)
        invalid.append(to_upload(v))
    empty=dict(good, visibleThrough=DATES["A"][0], phase=1, completion="not_started", entries=[])
    pending=dict(good, phase=2, completion="in_progress", entries=good["entries"][:1])
    draft=deepcopy(pending)
    draft["entries"].append({"stage":2, "text":"未锁稿", "sourceIds":[], "lockedAt":None})
    bad_json={"name":"bad.json","mimeType":"application/json","buffer":b"\xff"}
    add_files(p, [bad_json, *invalid, to_upload(empty), to_upload(pending), to_upload(draft), to_upload(good)])
    result=download_receipt(p)
    decisions=[r["decision"] for r in result["files"]]
    assert decisions[:3] == ["题包待核", "题包待核", "领包关联待核"]
    assert decisions.count("退回核对") == 1 + len(invalid)
    assert decisions[-4:] == ["未开始", "未完成", "未完成", "完整，计入一份"]
    assert result["accepted_group_cases"] == 1 and result["complete_groups"] == 0
    assert result["files"][-2]["stages"][1]["locked"] is False
    assert result["files"][1]["assignment"]["package_status"] == "题包指纹不符"
    assert result["files"][0]["assignment"]["package_sha256"] is None
    keep_evidence(p, 1280, result, "异常与阶段")
    p.locator("#purpose").select_option(label="教学练习")
    p.locator("#issued").check()
    add_files(p, [bad_json])
    assert download_receipt(p)["accepted_group_cases"] == 1
    context.close()
