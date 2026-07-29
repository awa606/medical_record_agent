from __future__ import annotations

from playwright.sync_api import expect, sync_playwright

from tests.test_doctor_itemized_approval_playwright import RunningServer, _login


VIEWPORTS = [(1366, 768), (1440, 900), (1920, 1080)]


def _segments(count: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(count):
        role = "doctor" if index % 2 == 0 else "patient"
        text = (
            f"第 {index + 1} 段：请说明发热、咳嗽和胸闷持续时间，是否伴随气促、胸痛、用药反应。"
            "这段中文用于验证转写正文不会被角色提示压缩成逐字竖排。"
            if role == "doctor"
            else f"第 {index + 1} 段：我发热咳嗽三天，最高体温三十八点五度，昨天服药后仍反复。"
            "这段患者回答用于验证长转写在固定列宽下仍保持正常段落。"
        )
        rows.append(
            {
                "segment_id": f"seg-{index}",
                "speaker": role,
                "speaker_id": "spk-doctor" if role == "doctor" else "spk-patient",
                "role": role,
                "text": text,
                "start_time": index * 4,
                "end_time": index * 4 + 3,
                "role_warning": "系统自动推定",
            }
        )
    return rows


def _layout_payload(segment_count: int) -> dict[str, object]:
    segments = _segments(segment_count)
    conversation = "\n".join(f"[{row['role']}] {row['text']}" for row in segments)
    return {
        "asr": {
            "audio_id": "layout-transcript",
            "text": conversation,
            "conversation_text": conversation,
            "segments": segments,
        },
        "fields": {
            "chief_complaint": {
                "value": "fever cough chest tightness for three days",
                "missing": False,
                "status": "partial",
                "confidence": 0.8,
                "source_spans": [],
                "doctor_review_status": "pending",
            },
            "present_illness": {
                "value": "patient reports fever cough and chest tightness",
                "missing": False,
                "status": "partial",
                "confidence": 0.7,
                "source_spans": [],
                "doctor_review_status": "pending",
            },
            "past_history": {
                "value": "not collected",
                "missing": True,
                "status": "missing",
                "confidence": 0.3,
                "source_spans": [],
            },
            "allergy_history": {
                "value": "not collected",
                "missing": True,
                "status": "missing",
                "confidence": 0.3,
                "source_spans": [],
            },
            "physical_exam": {
                "value": "pending exam",
                "missing": True,
                "status": "missing",
                "confidence": 0.3,
                "source_spans": [],
            },
            "candidate_diagnoses": [
                {
                    "name": "fever workup",
                    "confidence": 0.76,
                    "reason": "fever cough chest tightness",
                    "evidence": [{"text": "fever cough chest tightness"}],
                    "risk_warnings": ["chest tightness needs review"],
                    "suggested_checks": ["CBC", "chest imaging"],
                    "follow_up_questions": ["how long?"],
                    "doctor_review_status": "pending",
                }
            ],
        },
        "readiness": {
            "ready": False,
            "revision_id": 1,
            "content_hash": "layout-hash",
            "incomplete_items": [{"key": "missing:past_history"}],
        },
    }


def _inject_layout_state(page, segment_count: int) -> None:
    page.evaluate(
        """
        (payload) => {
          const state = window.__MRA_APP_STATE__;
          state.currentAsrResult = payload.asr;
          state.currentInputText = payload.asr.conversation_text;
          state.currentTaskId = 1;
          state.taskStatus = "reviewed";
          state.currentTask = { task_id: 1, current_stage: "reviewed" };
          state.currentRecordFields = payload.fields;
          state.currentExportReadiness = payload.readiness;
          window.setProductView("encounter");
          window.renderAll();
        }
        """,
        _layout_payload(segment_count),
    )
    page.wait_for_timeout(250)


def _layout_metrics(page) -> dict[str, object]:
    return page.evaluate(
        """
        () => {
          const rect = (element) => {
            const box = element.getBoundingClientRect();
            return {
              top: box.top,
              right: box.right,
              bottom: box.bottom,
              left: box.left,
              width: box.width,
              height: box.height,
            };
          };
          const transcript = document.querySelector("#transcriptList");
          const workbench = document.querySelector(".workbench");
          const actionBar = document.querySelector(".encounter-action-bar");
          const productMain = document.querySelector(".product-main");
          const firstText = document.querySelector(".transcript-row-text");
          const firstRoleWarning = document.querySelector(".transcript-role-warning");
          const textStyle = firstText ? getComputedStyle(firstText) : null;
          const before = transcript.scrollTop;
          transcript.scrollTop = Math.min(800, transcript.scrollHeight);
          const after = transcript.scrollTop;
          const transcriptBox = rect(transcript);
          const workbenchBox = rect(workbench);
          const actionBox = rect(actionBar);
          const firstTextBox = firstText ? rect(firstText) : null;
          const firstRoleWarningBox = firstRoleWarning ? rect(firstRoleWarning) : null;
          const overlapWidth = Math.max(0, Math.min(transcriptBox.right, actionBox.right) - Math.max(transcriptBox.left, actionBox.left));
          const overlapHeight = Math.max(0, Math.min(transcriptBox.bottom, actionBox.bottom) - Math.max(transcriptBox.top, actionBox.top));
          return {
            viewport: { width: innerWidth, height: innerHeight },
            bodyScrollWidth: document.documentElement.scrollWidth,
            bodyClientWidth: document.documentElement.clientWidth,
            productMainScrollHeight: productMain.scrollHeight,
            productMainClientHeight: productMain.clientHeight,
            transcriptScrollHeight: transcript.scrollHeight,
            transcriptClientHeight: transcript.clientHeight,
            transcriptOverflowY: getComputedStyle(transcript).overflowY,
            transcriptScrollBefore: before,
            transcriptScrollAfter: after,
            actionBar: actionBox,
            transcript: transcriptBox,
            workbench: workbenchBox,
            firstText: firstTextBox,
            firstRoleWarning: firstRoleWarningBox,
            textWhiteSpace: textStyle?.whiteSpace || "",
            textWordBreak: textStyle?.wordBreak || "",
            textOverflowWrap: textStyle?.overflowWrap || "",
            roleWarningCount: document.querySelectorAll(".transcript-role-warning").length,
            overlapArea: overlapWidth * overlapHeight,
          };
        }
        """
    )


def _assert_footer_button_clickable(page, selector: str) -> None:
    page.evaluate(
        """
        (selector) => {
          window.__MRA_LAYOUT_CLICKED__ = false;
          const button = document.querySelector(selector);
          button.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopImmediatePropagation();
            window.__MRA_LAYOUT_CLICKED__ = true;
          }, { capture: true, once: true });
        }
        """,
        selector,
    )
    page.locator(selector).click()
    assert page.evaluate("window.__MRA_LAYOUT_CLICKED__") is True


def test_long_transcript_scrolls_inside_transcript_region_and_action_bar_is_clickable() -> None:
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            for width, height in VIEWPORTS:
                context = browser.new_context(viewport={"width": width, "height": height})
                page = context.new_page()
                _login(page, server.base_url)
                _inject_layout_state(page, 90)

                metrics = _layout_metrics(page)
                assert metrics["bodyScrollWidth"] <= metrics["bodyClientWidth"]
                assert metrics["transcriptScrollHeight"] > metrics["transcriptClientHeight"]
                assert metrics["transcriptOverflowY"] in {"auto", "scroll"}
                assert metrics["transcriptScrollAfter"] > metrics["transcriptScrollBefore"]
                assert metrics["overlapArea"] == 0
                assert metrics["roleWarningCount"] > 0
                assert metrics["firstText"]["width"] >= 115
                assert metrics["textWhiteSpace"] == "normal"
                assert metrics["textWordBreak"] == "normal"
                assert metrics["textOverflowWrap"] == "normal"
                assert metrics["actionBar"]["top"] >= 0
                assert metrics["actionBar"]["bottom"] <= height

                _assert_footer_button_clickable(page, "#confirmFieldsButton")
                page.evaluate("document.querySelector('#transcriptList').scrollTop = document.querySelector('#transcriptList').scrollHeight")
                _assert_footer_button_clickable(page, "#confirmFieldsButton")
                context.close()
            browser.close()
    finally:
        server.close()


def test_short_transcript_keeps_action_bar_visible_without_horizontal_overflow() -> None:
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            _login(page, server.base_url)
            _inject_layout_state(page, 2)

            metrics = _layout_metrics(page)
            assert metrics["bodyScrollWidth"] <= metrics["bodyClientWidth"]
            assert metrics["transcriptScrollHeight"] >= metrics["transcriptClientHeight"]
            assert metrics["overlapArea"] == 0
            assert metrics["roleWarningCount"] > 0
            assert metrics["firstText"]["width"] >= 115
            assert metrics["actionBar"]["top"] >= 0
            assert metrics["actionBar"]["bottom"] <= 900
            _assert_footer_button_clickable(page, "#confirmFieldsButton")
            browser.close()
    finally:
        server.close()
