"""UI review pass: record regions, help navigation, contrast and overlap.

Starts an isolated server (mock provider, temporary database), drives the real
doctor page with Chromium, and writes screenshots plus a JSON report to
.artifacts. Process evidence only; not clinical or visual sign-off.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from tests.test_doctor_itemized_approval_playwright import (
    RunningServer,
    _login,
    _prepare_review_fixture,
    _select_all_review_items,
)


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".artifacts" / "ui-review-20261030"
AXE_JS = ROOT / "tests" / "assets" / "axe.min.js"

AXE_RUN = r"""
async () => {
  if (typeof axe === "undefined") return { error: "axe-not-loaded", violations: [] };
  const result = await axe.run(document, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"] },
  });
  return {
    error: null,
    violations: result.violations
      .filter((item) => ["serious", "critical"].includes(item.impact))
      .map((item) => ({ id: item.id, impact: item.impact, nodes: item.nodes.length, help: item.help })),
  };
}
"""

AUDIT_JS = r"""
() => {
  const parse = (value) => {
    const m = value.match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/);
    return m ? { r: +m[1], g: +m[2], b: +m[3], a: m[4] === undefined ? 1 : +m[4] } : null;
  };
  const lum = ({ r, g, b }) => {
    const f = (c) => { c /= 255; return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const ratio = (a, b) => {
    const la = lum(a), lb = lum(b);
    return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
  };
  const blend = (top, bottom) => ({
    r: top.r * top.a + bottom.r * (1 - top.a),
    g: top.g * top.a + bottom.g * (1 - top.a),
    b: top.b * top.a + bottom.b * (1 - top.a),
    a: 1,
  });
  const backgroundOf = (el) => {
    let node = el;
    const layers = [];
    while (node && node !== document.documentElement) {
      const style = getComputedStyle(node);
      const parsed = parse(style.backgroundColor);
      if (parsed && parsed.a > 0) layers.push(parsed);
      node = node.parentElement;
    }
    let result = { r: 255, g: 255, b: 255, a: 1 };
    for (let i = layers.length - 1; i >= 0; i -= 1) result = blend(layers[i], result);
    return result;
  };
  const scope = document.querySelector('dialog[open]') || document.body;
  const hasImageBackground = (el) => {
    let node = el;
    while (node && node !== document.documentElement) {
      if (getComputedStyle(node).backgroundImage !== 'none') return true;
      node = node.parentElement;
    }
    return false;
  };
  const textFailures = [];
  const nodes = [...scope.querySelectorAll('body *, dialog *')].filter((el) => {
    if (!el.childNodes.length) return false;
    const text = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent.trim()).join('');
    if (!text) return false;
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && +style.opacity > 0.3 && !hasImageBackground(el);
  });
  for (const el of nodes) {
    const style = getComputedStyle(el);
    const fg = parse(style.color);
    if (!fg) continue;
    const bg = backgroundOf(el);
    const size = parseFloat(style.fontSize);
    const bold = +style.fontWeight >= 700;
    const large = size >= 24 || (size >= 18.66 && bold);
    const need = large ? 3 : 4.5;
    const value = ratio(fg.a < 1 ? blend(fg, bg) : fg, bg);
    if (value + 0.01 < need) {
      textFailures.push({
        text: el.textContent.trim().slice(0, 40),
        color: style.color,
        background: `rgb(${Math.round(bg.r)}, ${Math.round(bg.g)}, ${Math.round(bg.b)})`,
        ratio: Math.round(value * 100) / 100,
        need,
        fontSize: size,
      });
    }
  }
  const rects = [...scope.querySelectorAll('button, a[href], input, select, textarea, [role="button"]')]
    .filter((el) => {
      const r = el.getBoundingClientRect();
      const s = getComputedStyle(el);
      return r.width > 2 && r.height > 2 && s.visibility !== 'hidden' && s.display !== 'none'
        && !el.closest('[hidden]') && !el.closest('details:not([open])');
    })
    .map((el) => ({ el, r: el.getBoundingClientRect() }));
  const topmost = (el, r) => {
    const x = Math.min(Math.max(r.left + r.width / 2, 0), window.innerWidth - 1);
    const y = Math.min(Math.max(r.top + r.height / 2, 0), window.innerHeight - 1);
    const hit = document.elementFromPoint(x, y);
    return Boolean(hit) && (el === hit || el.contains(hit) || hit.contains(el));
  };
  const overlaps = [];
  for (let i = 0; i < rects.length; i += 1) {
    for (let j = i + 1; j < rects.length; j += 1) {
      const a = rects[i], b = rects[j];
      if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
      if (!topmost(a.el, a.r) || !topmost(b.el, b.r)) continue;
      const w = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left);
      const h = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
      if (w > 4 && h > 4) overlaps.push({ a: a.el.outerHTML.slice(0, 60), b: b.el.outerHTML.slice(0, 60), area: Math.round(w * h) });
    }
  }
  return {
    textFailures: textFailures.slice(0, 25),
    textFailureCount: textFailures.length,
    overlaps: overlaps.slice(0, 15),
    overlapCount: overlaps.length,
    overflowX: Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth),
  };
}
"""


def audit(page: Page, name: str, steps: list[dict]) -> None:
    result = page.evaluate(AUDIT_JS)
    axe_result = {"error": "axe-missing", "violations": []}
    if AXE_JS.is_file():
        if not page.evaluate("typeof axe !== 'undefined'"):
            page.add_script_tag(path=str(AXE_JS))
        axe_result = page.evaluate(AXE_RUN)
    ok = (
        result["textFailureCount"] == 0
        and result["overlapCount"] == 0
        and result["overflowX"] <= 1
        and not axe_result["violations"]
    )
    steps.append({
        "step": f"audit_{name}",
        "ok": ok,
        "detail": {**result, "axe": axe_result},
    })
    page.screenshot(path=str(OUT / f"audit_{name}.png"), full_page=True)


def run() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    if not (ROOT / "static" / "help" / "manual.html").exists() or not (ROOT / "static" / "help" / "help-nav.js").exists():
        subprocess.run([sys.executable, "scripts/package_help.py"], cwd=ROOT, check=True)
    steps: list[dict] = []
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
            page = context.new_page()
            page.goto(f"{server.base_url}/static/doctor.html")
            page.wait_for_timeout(500)
            audit(page, "login", steps)
            _login(page, server.base_url)

            if not page.locator("#localSyntheticPatient").is_visible():
                page.locator("#localRegistrationDisclosure summary").click()
            page.select_option("#localSyntheticPatient", "SIM-DEMO-0929-FEVER")
            page.click("#createLocalEncounterButton")
            page.locator('#dashboardEncounterList [data-encounter-action="start"]').click()
            page.wait_for_timeout(600)

            audit(page, "empty_record_state", steps)

            page.evaluate("createRecordTask('患者发热咳嗽两天，最高38.2度，没有胸痛，没有药物过敏史。')")
            page.wait_for_selector("#recordFields .record-section", timeout=60000)
            page.wait_for_timeout(1800)

            page.evaluate("void exportRecord()")
            page.wait_for_timeout(900)
            audit(page, "export_blocked_state", steps)
            page.evaluate("closeDrawer()")
            page.wait_for_timeout(200)

            headings = page.locator("#recordFields .record-section-head h3").all_inner_texts()
            steps.append({"step": "record_sections", "ok": len(headings) >= 5, "detail": headings})
            steps.append({
                "step": "expected_sections",
                "ok": all(name in headings for name in ("就诊信息", "主诉与现病史", "既往史与过敏", "体格检查", "诊断与处理")),
                "detail": headings,
            })
            section_cards = page.evaluate("""() => [...document.querySelectorAll('#recordFields .record-section')].map(section => ({
                title: section.querySelector('.record-section-head h3')?.textContent.trim() || '',
                cards: section.querySelectorAll('.field-card').length,
            }))""")
            steps.append({
                "step": "section_contents",
                "ok": all(item["cards"] >= 1 for item in section_cards if item["title"] != "就诊信息"),
                "detail": section_cards,
            })
            section_status = page.evaluate("""() => [...document.querySelectorAll('#recordFields .record-section-status')].map(button => ({
                text: button.textContent.trim(),
                tone: [...button.classList].find(name => ['done', 'pending', 'conflict', 'neutral'].includes(name)) || '',
            }))""")
            steps.append({
                "step": "section_status",
                "ok": len(section_status) >= 4 and all(item["tone"] for item in section_status),
                "detail": section_status,
            })
            pending_badge = page.locator("#recordFields .record-section-status.pending, #recordFields .record-section-status.conflict").first
            if pending_badge.count():
                pending_badge.click()
                page.wait_for_timeout(500)
                focused_field = page.evaluate("document.activeElement?.getAttribute('data-field') || ''")
                steps.append({"step": "section_jump", "ok": bool(focused_field), "detail": focused_field})

            task_before_reload = page.evaluate("window.__MRA_APP_STATE__?.currentTaskId")
            page.reload()
            page.wait_for_selector("#recordFields .record-section", timeout=60000)
            page.wait_for_timeout(1200)
            task_after_reload = page.evaluate("window.__MRA_APP_STATE__?.currentTaskId")
            steps.append({
                "step": "session_recovery",
                "ok": task_before_reload == task_after_reload and page.locator("#recordFields .record-section").count() >= 5,
                "detail": {"before": task_before_reload, "after": task_after_reload},
            })
            audit(page, "session_recovery", steps)
            audit(page, "workspace", steps)

            page.click("#editRecordButton")
            page.wait_for_timeout(400)
            page.locator('textarea[data-record-field-input="present_illness"]').evaluate("el => { el.focus(); el.scrollIntoView({ block: 'center' }); }")
            page.wait_for_timeout(300)
            audit(page, "record_edit_mode", steps)
            page.click("#cancelRecordEditButton")
            page.wait_for_timeout(300)

            page.set_viewport_size({"width": 1280, "height": 800})
            page.wait_for_timeout(400)
            audit(page, "workspace_1280", steps)
            page.set_viewport_size({"width": 1920, "height": 1080})
            page.wait_for_timeout(400)
            audit(page, "workspace_1920", steps)
            page.set_viewport_size({"width": 720, "height": 450})
            page.wait_for_timeout(400)
            audit(page, "workspace_720_zoom", steps)
            page.set_viewport_size({"width": 375, "height": 812})
            page.wait_for_timeout(400)
            audit(page, "workspace_375", steps)
            page.set_viewport_size({"width": 320, "height": 640})
            page.wait_for_timeout(400)
            audit(page, "workspace_320_reflow", steps)
            page.click("#openEmbeddedHelpButton")
            page.frame_locator("#embeddedHelpFrame").locator("h1").wait_for(timeout=20000)
            audit(page, "help_drawer_320", steps)
            page.click("#closeEmbeddedHelpButton")
            page.wait_for_timeout(300)
            page.click("#openWorklistButton")
            page.wait_for_timeout(300)
            steps.append({
                "step": "worklist_320_access",
                "ok": page.evaluate("appState.productView") == "workbench" and page.locator("#encounterSearchInput").is_visible(),
                "detail": "320px 可打开查找就诊",
            })
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
            page.click('button[data-product-view-target="admin"]')
            page.wait_for_timeout(300)
            steps.append({
                "step": "admin_320_access",
                "ok": page.locator("#adminHome").is_visible(),
                "detail": "320px 可进入管理后台",
            })
            page.click('button[data-product-view-target="encounter"]')
            page.wait_for_timeout(300)
            page.set_viewport_size({"width": 1440, "height": 900})
            page.wait_for_timeout(400)
            page.evaluate("""() => {
                const fields = appState.currentRecordFields;
                window.__longOriginal = fields.chief_complaint.value;
                fields.chief_complaint.value = '患者主诉：' + '反复发热咳嗽两周，'.repeat(80)
                    + 'https://example.com/' + 'a'.repeat(220);
                fields.chief_complaint.missing = false;
                renderFields();
            }""")
            page.wait_for_timeout(400)
            long_text = page.evaluate("""() => {
                const card = document.querySelector('[data-field="chief_complaint"]');
                const value = card?.querySelector('.field-value');
                return {
                    docOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                    valueHeight: Math.round(value?.getBoundingClientRect().height || 0),
                    clipped: Boolean(value && value.scrollHeight > value.clientHeight + 2),
                };
            }""")
            steps.append({"step": "long_text_layout", "ok": long_text["docOverflow"] <= 1 and not long_text["clipped"] and long_text["valueHeight"] > 100, "detail": long_text})
            audit(page, "long_text", steps)
            page.evaluate("""() => {
                appState.currentRecordFields.chief_complaint.value = window.__longOriginal;
                renderFields();
            }""")
            page.wait_for_timeout(300)

            page.evaluate("refreshExportReadiness()")
            page.wait_for_function("window.__MRA_APP_STATE__?.currentExportReadiness?.revision_id", timeout=20000)
            _select_all_review_items(page)
            page.evaluate("confirmFields()")
            page.wait_for_function("window.__MRA_APP_STATE__?.currentTask?.current_stage === 'approved'", timeout=20000)
            page.wait_for_timeout(400)
            audit(page, "approved_state", steps)

            page.evaluate("exportRecord()")
            page.wait_for_function("window.__MRA_APP_STATE__?.currentTask?.current_stage === 'exported'", timeout=20000)
            page.wait_for_timeout(400)
            audit(page, "exported_state", steps)
            page.evaluate("closeDrawer()")
            page.wait_for_timeout(300)

            page.emulate_media(reduced_motion="reduce")
            transition = page.evaluate("getComputedStyle(document.querySelector('.record-section-status')).transitionDuration")
            steps.append({"step": "reduced_motion", "ok": transition in ("0.01ms", "1e-05s", "0s"), "detail": transition})
            page.emulate_media(reduced_motion="no-preference")

            focus_issues = []
            for _ in range(20):
                page.keyboard.press("Tab")
                page.wait_for_timeout(40)
                issue = page.evaluate("""() => {
                    const el = document.activeElement;
                    if (!el || el === document.body) return null;
                    const rect = el.getBoundingClientRect();
                    const style = getComputedStyle(el);
                    const hit = document.elementFromPoint(
                        Math.min(Math.max(rect.left + rect.width / 2, 0), window.innerWidth - 1),
                        Math.min(Math.max(rect.top + rect.height / 2, 0), window.innerHeight - 1)
                    );
                    const hasRing = style.outlineWidth !== "0px" || style.boxShadow !== "none";
                    const covered = !(hit && (hit === el || el.contains(hit)));
                    return hasRing && !covered ? null : { id: el.id, tag: el.tagName, hasRing, covered };
                }""")
                if issue:
                    focus_issues.append(issue)
            steps.append({"step": "keyboard_focus", "ok": not focus_issues, "detail": focus_issues[:5]})

            page.click("#openEmbeddedHelpButton")
            page.wait_for_timeout(300)
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            steps.append({
                "step": "keyboard_escape_help",
                "ok": not page.locator("#helpDialog").evaluate("d => d.open")
                and page.evaluate("document.activeElement?.id") == "openEmbeddedHelpButton",
                "detail": page.evaluate("document.activeElement?.id"),
            })

            page.goto(f"{server.base_url}/static/doctor.html")
            page.wait_for_timeout(600)
            page.keyboard.press("Tab")
            skip_class = page.evaluate("document.activeElement?.className || ''")
            page.keyboard.press("Enter")
            page.wait_for_timeout(200)
            skip_target = page.evaluate("document.activeElement?.id || ''")
            steps.append({
                "step": "skip_link",
                "ok": "skip-link" in skip_class and skip_target == "mainContent",
                "detail": {"first": skip_class, "target": skip_target},
            })
            page.goto(f"{server.base_url}/static/doctor.html")
            page.wait_for_timeout(600)

            page.click("#openEmbeddedHelpButton")
            frame = page.frame_locator("#embeddedHelpFrame")
            frame.locator("h1").wait_for(timeout=20000)
            audit(page, "help_index", steps)

            frame.locator('a[href="manual.html"]').first.click()
            page.wait_for_timeout(1200)
            manual_heading = frame.locator("h1").inner_text()
            steps.append({"step": "help_manual", "ok": "手册" in manual_heading, "detail": manual_heading})
            audit(page, "help_manual", steps)

            page.click("#helpBackButton")
            page.wait_for_timeout(1200)
            index_heading = frame.locator("h1").inner_text()
            steps.append({"step": "help_back", "ok": "使用帮助" in index_heading, "detail": index_heading})
            page.click("#closeEmbeddedHelpButton")
            steps.append({"step": "help_close", "ok": not page.locator("#helpDialog").evaluate("d => d.open")})

            page.click("#openEmbeddedHelpButton")
            page.wait_for_timeout(400)
            page.go_back()
            page.wait_for_timeout(500)
            steps.append({
                "step": "help_browser_back",
                "ok": not page.locator("#helpDialog").evaluate("d => d.open"),
                "detail": "浏览器后退关闭帮助抽屉",
            })

            for help_page in ("manual", "feedback", "maintenance", "dual-environment", "course-demo", "viewer-section"):
                page.goto(f"{server.base_url}/static/help/{help_page}.html")
                page.wait_for_timeout(400)
                audit(page, f"help_{help_page}", steps)
                steps.append({
                    "step": f"help_back_button_{help_page}",
                    "ok": page.locator(".help-nav-back").is_visible(),
                    "detail": "独立帮助页返回按钮",
                })

            page.goto(f"{server.base_url}/static/help/index.html")
            page.wait_for_timeout(400)
            page.locator('a[href="manual.html"]').first.click()
            page.wait_for_timeout(600)
            page.locator(".help-nav-back").click()
            page.wait_for_timeout(600)
            steps.append({
                "step": "help_standalone_back_navigation",
                "ok": page.url.rstrip("/").endswith("/static/help/index.html"),
                "detail": page.url,
            })

            page.goto(f"{server.base_url}/static/doctor.html")
            page.wait_for_timeout(600)

            page.set_viewport_size({"width": 320, "height": 640})
            page.goto(f"{server.base_url}/static/help/manual.html")
            page.wait_for_timeout(400)
            audit(page, "help_manual_320", steps)
            steps.append({
                "step": "help_back_button_320",
                "ok": page.locator(".help-nav-back").is_visible(),
                "detail": "320px 独立帮助页返回按钮",
            })
            for help_page in ("feedback", "maintenance", "dual-environment", "course-demo", "viewer-section"):
                page.goto(f"{server.base_url}/static/help/{help_page}.html")
                page.wait_for_timeout(300)
                audit(page, f"help_{help_page}_320", steps)
            page.set_viewport_size({"width": 1440, "height": 900})
            page.goto(f"{server.base_url}/static/doctor.html")
            page.wait_for_timeout(600)

            page.click("#openWorklistButton")
            page.wait_for_timeout(500)
            audit(page, "worklist", steps)
            page.keyboard.press("Escape")

            page.click('button[data-product-view-target="admin"]')
            page.wait_for_timeout(600)
            audit(page, "admin", steps)

            page.click("#knowledgeTabSearch")
            page.fill("#knowledgeTestQuery", "流感的临床表现")
            page.click("#knowledgeTestSearchForm button[type=submit]")
            page.wait_for_timeout(900)
            audit(page, "admin_knowledge_search", steps)

            for path, name in (("/static/index.html", "app_index"), ("/static/debug.html", "debug")):
                page.goto(f"{server.base_url}{path}")
                page.wait_for_timeout(500)
                audit(page, name, steps)

            upload_context = browser.new_context(viewport={"width": 1440, "height": 900})
            upload_page = upload_context.new_page()
            _login(upload_page, server.base_url)
            if not upload_page.locator("#localSyntheticPatient").is_visible():
                upload_page.locator("#localRegistrationDisclosure summary").click()
            upload_page.select_option("#localSyntheticPatient", "SIM-DEMO-0929-FEVER")
            upload_page.click("#createLocalEncounterButton")
            upload_page.locator('#dashboardEncounterList [data-encounter-action="start"]').click()
            upload_page.wait_for_timeout(600)
            upload_page.evaluate("openAudioTranscribe()")
            upload_page.wait_for_timeout(300)
            upload_page.set_input_files("#audioFileInput", {"name": "bad.wav", "mimeType": "audio/wav", "buffer": b"not-a-wav"})
            upload_page.click("#submitAudioButton")
            upload_page.wait_for_timeout(2200)
            upload_error = upload_page.evaluate("window.__MRA_APP_STATE__?.lastActionError || ''")
            steps.append({"step": "upload_error_consistent", "ok": bool(upload_error), "detail": upload_error[:80]})
            audit(upload_page, "upload_error_state", steps)
            upload_context.close()

            conflict_context = browser.new_context(viewport={"width": 1440, "height": 900})
            conflict_page = conflict_context.new_page()
            _login(conflict_page, server.base_url)
            if not conflict_page.locator("#localSyntheticPatient").is_visible():
                conflict_page.locator("#localRegistrationDisclosure summary").click()
            conflict_page.select_option("#localSyntheticPatient", "SIM-DEMO-0929-FEVER")
            conflict_page.click("#createLocalEncounterButton")
            conflict_page.locator('#dashboardEncounterList [data-encounter-action="start"]').click()
            conflict_page.wait_for_timeout(600)
            _prepare_review_fixture(conflict_page)
            conflict_page.wait_for_timeout(1200)
            audit(conflict_page, "approval_conflict_state", steps)

            conflict_page.locator('[data-field="physical_exam"] [data-field-resolution="doctor_entry"]').click()
            conflict_page.locator('[data-record-field-input="physical_exam"]').fill("")
            conflict_page.click("#saveDraftButton")
            conflict_page.wait_for_function("!window.__MRA_APP_STATE__.recordEditMode", timeout=15000)
            _select_all_review_items(conflict_page)
            conflict_page.evaluate("confirmFields()")
            conflict_page.wait_for_function("window.__MRA_APP_STATE__?.currentTask?.current_stage === 'approved'", timeout=20000)
            conflict_page.wait_for_timeout(400)
            audit(conflict_page, "conflict_resolved_state", steps)

            conflict_page.evaluate("void exportRecord()")
            conflict_page.wait_for_function("window.__MRA_APP_STATE__?.currentTask?.current_stage === 'exported'", timeout=20000)
            conflict_page.wait_for_timeout(400)
            audit(conflict_page, "conflict_export_state", steps)
            conflict_context.close()

            browser.close()
    finally:
        server.close()

    report = {"ok": all(step["ok"] for step in steps), "steps": steps}
    (OUT / "ui_review.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    report = run()
    for step in report["steps"]:
        detail = step.get("detail")
        if isinstance(detail, dict):
            detail = f"contrast={detail.get('textFailureCount')} overlap={detail.get('overlapCount')} overflowX={detail.get('overflowX')}"
        elif isinstance(detail, list):
            detail = " | ".join(str(item) for item in detail[:6])
        print(f"  [{'PASS' if step['ok'] else 'FAIL'}] {step['step']:<22} {detail or step.get('path') or ''}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
