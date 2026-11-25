"""Ordinary doctor routes from an obsolete confirmed recording to a reviewed revision."""

import hashlib
import io
import json
import secrets
import sqlite3
import time
import wave
from contextlib import closing

import pymupdf
import pytest
import httpx
from playwright.sync_api import expect, sync_playwright

from tests.test_doctor_itemized_approval_playwright import RunningServer


MANUAL_CHIEF = "本人右腕痛两天。"
HISTORY_ONLY = "既往资料由陪同人员另行核对。"
UNSAVED = "同一医生另一标签中的文字仍需保存。"


def _audio_material():
    # A deterministic audio container and synthetic ASR output keep the test offline.
    lines = ["这两天右手腕有点疼，这次问的是我自己的手腕。", "我上个月碰过左腕。", "本人这次的影像报告待回。"]
    stream = io.BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        wav.writeframes(bytes(16000 * 2 * 4))
    segments = [
        {
            "segment_id": f"synthetic-segment-{i}",
            "text": line,
            "role": "待确认",
            "speaker": speaker,
            "speaker_id": speaker,
            "start_time": float(i),
            "end_time": i + 0.8,
        }
        for i, (line, speaker) in enumerate(zip(lines, ["spk0", "spk1", "spk1"], strict=True))
    ]
    return stream.getvalue(), {
        "engine": "synthetic",
        "text": "\n".join(lines),
        "conversation_text": "\n".join(lines),
        "segments": segments,
    }


def _write_json(path, document):
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf8")


def _pdf_record(content):
    with pymupdf.open(stream=content, filetype="pdf") as document:
        return "".join("".join(page.get_text() for page in document).split())


def _sha(content):
    return hashlib.sha256(content).hexdigest()


class Visit:
    def __init__(self, server, client):
        self.server = server
        self.client = client
        self.eid = self.api(
            "POST",
            "/encounters",
            {"patient_deidentified_id": "SYN-SOURCE-REVIEW", "patient_display_name": "合成音频修订"},
        )["id"]
        self.encounter = f"/encounters/{self.eid}"
        for action in ("check-in", "start"):
            self.api("POST", f"{self.encounter}/{action}")
        sid = self.api("POST", "/asr/sessions?recognition_mode=follow")["session_id"]
        self.session = f"/asr/sessions/{sid}/result"
        wav, raw = _audio_material()
        r = client.post(
            server.base_url + "/api/audio/upload", files={"file": ("source.wav", wav, "audio/wav")}
        )
        r.raise_for_status()
        aid = r.json()["audio_id"]
        uploads = server.root / "uploads"
        info = uploads / "asr_sessions" / sid / "session.json"
        _write_json(
            info,
            dict(
                json.loads(info.read_bytes()),
                audio_id=aid,
                filename="source.wav",
                engine=raw["engine"],
                status="completed",
            ),
        )
        self.source = dict(raw, audio_id=aid)
        _write_json(info.with_name("result.json"), self.source)
        _write_json(uploads / (aid + ".transcript.json"), self.source)
        assert self.role("陪同人员") == "passed"
        self.tid = self.api("POST", f"/audio/{aid}/generate-record?encounter_id={self.eid}")["task_id"]
        self.task = f"/tasks/{self.tid}"
        self.review = self.task + "/audio-source-revision"
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.api("GET", self.encounter).get("current_revision"):
                break
            time.sleep(0.05)
        result = self.api("GET", self.task)["result_json"]
        self.r1 = self.api("GET", self.encounter)["current_revision"]
        fields = result["fields"]
        fields["chief_complaint"].update(value=MANUAL_CHIEF, missing=False, status="complete")
        fields["past_history"].update(value=HISTORY_ONLY, missing=False, status="complete")
        self.api(
            "POST",
            self.task + "/review",
            {
                "fields": fields,
                "manual_takeover_fields": ["chief_complaint", "past_history"],
                "expected_revision_id": self.r1["id"],
                "expected_content_hash": self.r1["content_hash"],
            },
        )
        self.r2 = self.api("GET", self.encounter)["current_revision"]
        assert self.r2["revision_no"] == 2

    def api(self, method, route, body=None):
        r = self.client.request(method, self.server.base_url + "/api" + route, json=body, timeout=15)
        assert r.is_success, (route, r.status_code, r.text[:500])
        return r.json()

    def role(self, new_role):
        result = self.api(
            "PATCH",
            self.session,
            {
                "speaker_roles": [
                    {"speaker_id": "spk0", "role": "患者"},
                    {"speaker_id": "spk1", "role": new_role, "reviewed_by_doctor": new_role != "待确认"},
                ]
            },
        )
        return result["asr_result"]["role_quality"]["status"]

    def open(self, page):
        url = self.server.base_url + f"/static/doctor.html?encounter_id={self.eid}#encounter"
        if page.url == url:
            page.reload()
        else:
            page.goto(url)
        expect(page.locator("#patientProfile")).to_contain_text("E-" + str(self.eid))
        expect(page.locator('#recordFields [data-field="chief_complaint"]').first).to_be_visible()

    def rows(self):
        with closing(sqlite3.connect(self.server.root / "edge.sqlite3")) as db:
            return db.execute(
                "SELECT * FROM record_revision WHERE task_id=? ORDER BY revision_no", (self.tid,)
            ).fetchall()

    def download(self, sha):
        r = self.client.get(
            self.server.base_url + "/api" + self.task + "/exports/pdf", params={"sha256": sha}
        )
        assert r.is_success, r.status_code
        return r.content


@pytest.fixture
def doctor(tmp_path):
    name, password, admin = "audio-revision-user", secrets.token_urlsafe(18), secrets.token_urlsafe(18)
    server = RunningServer(
        {
            "MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD": admin,
            "ASR_PREWARM_ENABLED": "0",
            "MRA_IDENTITY_MAP_PATH": str(tmp_path / "identity.sqlite"),
            "RECORD_PROVIDER_MODE": "demo",
        }
    )
    try:
        with httpx.Client(trust_env=False, timeout=20) as client, sync_playwright() as pw:
            base = server.base_url + "/api/auth/"
            for action, data in [
                ("login", {"username": "admin", "password": admin}),
                (
                    "users",
                    {
                        "username": name,
                        "password": password,
                        "display_name": "合成修订医生",
                        "role": "doctor",
                    },
                ),
                ("logout", {}),
                ("login", {"username": name, "password": password}),
            ]:
                client.post(base + action, json=data).raise_for_status()
            assert client.get(base + "me").json()["role"] == "doctor"
            browser = pw.chromium.launch()
            try:
                context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
                page = context.new_page()
                page.goto(server.base_url + "/static/doctor.html")
                page.locator("#loginUsername").fill(name)
                page.locator("#loginPassword").fill(password)
                page.locator("#loginForm button[type=submit]").click()
                expect(page.locator("#authUserLabel")).to_contain_text("合成修订医生")
                yield Visit(server, client), page
            finally:
                browser.close()
    finally:
        server.close()


def _sign_and_download(page, visit, path):
    pan = page.locator("#recordFields .approval-disclosure")
    if pan.get_attribute("open") is None:
        pan.locator(":scope > summary").click()
    regular = pan.locator("[data-approval-confirm-regular]")
    if regular.is_visible():
        regular.click()
    for attr, action in (
        ("data-approval-missing-key", "accept_missing"),
        ("data-approval-diagnosis-index", "delete_ai_candidate"),
    ):
        buttons = pan.locator(f'[{attr}][data-approval-action="{action}"]')
        for key in [v.get_attribute(attr) for v in buttons.all()]:
            pan.locator(f'[{attr}="{key}"][data-approval-action="{action}"]').click()
    for risk in pan.locator("[data-approval-risk-key]").all():
        if risk.is_visible():
            risk.click()
    with page.expect_response(
        lambda r: r.url.endswith(visit.task + "/approve") and r.request.method == "POST"
    ) as approve:
        page.locator("#confirmFieldsButton").click()
    assert approve.value.status == 200, approve.value.text()
    with page.expect_download() as dl:
        page.locator("#exportButton").click()
    dl.value.save_as(path)
    pdf = path.read_bytes()
    assert pdf.startswith(b"%PDF-") and pdf == visit.download(_sha(pdf))
    return pdf


def test_doctor_reconciles_audio_without_overwriting_old_revisions_or_unsaved_text(doctor, tmp_path):
    visit, page = doctor
    original_rows = visit.rows()
    assert visit.role("待确认") != "passed"
    visit.open(page)
    expect(page.locator(".approval-checklist .reference-notice")).to_be_visible()
    entry = page.locator("[data-review-audio-revision]:visible").first
    expect(entry).to_be_hidden()
    assert visit.role("医生") == "passed"
    visit.open(page)
    expect(entry).to_be_visible()
    other = page.context.new_page()
    visit.open(other)
    card = other.locator('#recordFields [data-field="chief_complaint"]').first
    card.locator("[data-record-edit-field]").first.click()
    editor = card.locator("[data-record-field-input]")
    editor.fill(UNSAVED)
    other_entry = other.locator("[data-review-audio-revision]:visible").first
    if other_entry.is_visible():
        other_entry.click()
    expect(other.locator("#audioRevisionDialog")).to_be_hidden()
    expect(editor).to_have_value(UNSAVED)
    posts = []
    page.on(
        "request",
        lambda req: (
            posts.append(req.url) if req.method == "POST" and req.url.endswith(visit.review) else None
        ),
    )
    dialog = page.locator("#audioRevisionDialog")
    page.bring_to_front()
    measurements = {}
    playback = {}
    for width in (1366, 390, 320):
        page.set_viewport_size({"width": width, "height": 850})
        entry.click()
        expect(dialog).to_be_visible()
        expect(dialog.locator('select[data-revision-key="chief_complaint"]')).to_be_visible()
        expect(dialog).to_contain_text(MANUAL_CHIEF)
        assert not page.locator("#audioRevisionForm").evaluate("form => form.checkValidity()")
        if width == 1366:
            page.screenshot(path=str(tmp_path / "office-dialog-open.png"))
            page.locator("#saveAudioRevision").click()
            expect(dialog).to_be_visible()
            assert not posts
        measurements[str(width)] = dialog.evaluate("""e=>({
            windowWidth: innerWidth, pageWidth: document.documentElement.scrollWidth,
            dialogWidth: e.clientWidth, dialogScrollWidth: e.scrollWidth,
            left:e.getBoundingClientRect().left, right:e.getBoundingClientRect().right})""")
        size = measurements[str(width)]
        assert size["left"] >= 0 and size["right"] <= width + 1
        assert size["dialogScrollWidth"] <= size["dialogWidth"] + 1
        assert size["pageWidth"] <= width
        page.screenshot(path=str(tmp_path / f"revision-dialog-{width}.png"))
        if width == 390:
            second = dialog.locator("[data-audio-revision-start]").nth(1)
            expect(second.locator("..")).to_contain_text("身份已订正")
            player = dialog.locator("#audioRevisionPlayer")
            start = float(second.get_attribute("data-audio-revision-start"))
            assert start == visit.source["segments"][1]["start_time"]
            second.focus()
            page.keyboard.press("Enter")
            page.wait_for_function(
                """start => {const p=document.querySelector('#audioRevisionPlayer');
                 return !p.paused && p.currentTime > start+0.15;}""",
                arg=start,
                timeout=7000,
            )
            playback = player.evaluate(
                "p=>({time:p.currentTime, duration:p.duration, url:new URL(p.currentSrc).pathname})"
            )
            assert playback["url"] == f"/api/audio/{visit.source['audio_id']}/media"
            playback["segment_start"] = start
            page.screenshot(path=str(tmp_path / "revision-dialog-390-listening.png"))
        if width != 320:
            page.keyboard.press("Escape")
            expect(dialog).to_be_hidden()
            assert page.locator("#audioRevisionPlayer").evaluate("p=>p.paused")
    expected = set(visit.api("GET", visit.review)["previous_values"])
    for key in expected:
        select = dialog.locator(f'select[data-revision-key="{key}"]')
        select.select_option("retain_as_doctor" if key == "chief_complaint" else "history_only")
    add = dialog.locator("#audioRevisionAdd")
    if "auxiliary_exam" not in expected:
        add.select_option("auxiliary_exam")
    dialog.locator('select[data-revision-key="auxiliary_exam"]').select_option("quote:2")
    page.locator("#audioRevisionConfirmed").check()
    button = page.locator("#saveAudioRevision")
    button.focus()
    expect(button).to_be_in_viewport()
    assert button.evaluate("""b=>{const r=b.getBoundingClientRect();
        return b.contains(document.elementFromPoint(r.left+r.width/2, r.top+r.height/2));}""")
    page.screenshot(path=str(tmp_path / "revision-dialog-320-save.png"))
    with page.expect_response(
        lambda r: r.url.endswith(visit.review) and r.request.method == "POST"
    ) as receipt:
        page.locator("#saveAudioRevision").click()
    assert receipt.value.status == 200, receipt.value.text()
    expect(dialog).to_be_hidden()
    expect(page.locator("#recordFields .approval-disclosure > summary")).to_be_focused()
    rows = visit.rows()
    assert len(rows) == 3 and rows[:2] == original_rows
    result = visit.api("GET", visit.task)["result_json"]
    assert result["fields"]["chief_complaint"]["value"] == MANUAL_CHIEF
    assert result["fields"]["chief_complaint"]["source_spans"] == []
    assert not result["fields"]["past_history"]["value"]
    assert [s["role"] for s in result["asr_source"]["segments"]] == ["患者", "医生", "医生"]
    selected_quote = result["fields"]["auxiliary_exam"]["source_spans"][0]
    assert selected_quote["segment_id"] == visit.source["segments"][2]["segment_id"]
    expect(editor).to_have_value(UNSAVED)
    with other.expect_response(
        lambda r: r.url.endswith(visit.task + "/review") and r.request.method == "POST"
    ) as stale:
        other.locator("#saveDraftButton").click()
    assert stale.value.status == 409
    expect(editor).to_have_value(UNSAVED)
    assert visit.rows() == rows
    page.set_viewport_size({"width": 1366, "height": 900})
    expected_revision = visit.api("GET", visit.encounter)["current_revision"]
    assert expected_revision["revision_no"] == 3
    pdf = _sign_and_download(page, visit, tmp_path / "R3.pdf")
    paper = _pdf_record(pdf)
    assert MANUAL_CHIEF in paper and selected_quote["text"] in paper and HISTORY_ONLY not in paper
    page.screenshot(path=str(tmp_path / "R3-signed.png"))
    _write_json(
        tmp_path / "r3-receipt.json",
        {
            "revision_no": 3,
            "old_rows_unchanged": True,
            "stale_http": 409,
            "pdf_sha256": _sha(pdf),
            "widths": measurements,
            "keyboard_playback": playback,
            "request_choices": receipt.value.request.post_data_json["choices"],
        },
    )


def test_signed_record_keeps_original_pdf_after_roles_change(doctor, tmp_path):
    visit, page = doctor
    visit.open(page)
    pdf = _sign_and_download(page, visit, tmp_path / "original.pdf")
    assert HISTORY_ONLY in _pdf_record(pdf)
    old_rows = visit.rows()
    assert visit.role("待确认") != "passed"
    assert visit.role("医生") == "passed"
    visit.open(page)
    expect(page.locator(".approval-checklist .reference-notice")).to_be_visible()
    expect(page.locator("[data-review-audio-revision]:visible")).to_have_count(0)
    page.screenshot(path=str(tmp_path / "old-signed-reprint.png"))
    with page.expect_download() as dl:
        page.locator("#exportButton").click()
    copy = tmp_path / "reprint.pdf"
    dl.value.save_as(copy)
    assert copy.read_bytes() == pdf and visit.rows() == old_rows
    _write_json(
        tmp_path / "original-receipt.json",
        {
            "revision_no": 2,
            "old_sha256": _sha(pdf),
            "reprint_sha256": _sha(copy.read_bytes()),
            "old_rows_unchanged": True,
        },
    )


@pytest.mark.parametrize(
    "concurrent_change, reason",
    [
        ("source", "stale_audio_source"),
        ("record", "stale_record_revision"),
    ],
)
def test_open_choices_survive_moved_source_or_record(doctor, tmp_path, concurrent_change, reason):
    visit, page = doctor
    assert visit.role("医生") == "passed"
    visit.open(page)
    page.locator("[data-review-audio-revision]:visible").first.click()
    dialog = page.locator("#audioRevisionDialog")
    chief = dialog.locator('select[data-revision-key="chief_complaint"]')
    past = dialog.locator('select[data-revision-key="past_history"]')
    chief.select_option("retain_as_doctor")
    past.select_option("history_only")
    for item in dialog.locator("select[data-revision-key]").all():
        if not item.input_value():
            item.select_option("history_only")
    page.locator("#audioRevisionConfirmed").check()
    if concurrent_change == "source":
        assert visit.role("患者") == "passed"
    else:
        fields = visit.api("GET", visit.task)["result_json"]["fields"]
        fields["chief_complaint"]["value"] = "本轮另行保存的人工主诉。"
        visit.api(
            "POST",
            visit.task + "/review",
            {
                "fields": fields,
                "manual_takeover_fields": ["chief_complaint"],
                "expected_revision_id": visit.r2["id"],
                "expected_content_hash": visit.r2["content_hash"],
            },
        )
    before = visit.rows()
    with page.expect_response(lambda r: r.url.endswith(visit.review) and r.request.method == "POST") as rr:
        dialog.locator("#saveAudioRevision").click()
    response = rr.value
    assert response.status == 409 and response.json()["detail"]["reason_code"] == reason, response.text()
    expect(dialog).to_be_visible()
    expect(chief).to_have_value("retain_as_doctor")
    expect(past).to_have_value("history_only")
    expect(page.locator("#audioRevisionConfirmed")).to_be_checked()
    notice = page.locator("#audioRevisionStatus")
    expect(notice).to_be_focused()
    expect(notice).to_contain_text("变化" if concurrent_change == "source" else "版本")
    assert before == visit.rows()
    _write_json(
        tmp_path / "conflict-receipt.json",
        {
            "reason": reason,
            "http": response.status,
            "page_notice": notice.inner_text(),
            "record_revisions_after_rejected_action": len(before),
            "retained_choices": [chief.input_value(), past.input_value()],
        },
    )
