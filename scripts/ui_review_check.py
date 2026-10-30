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

from tests.test_doctor_itemized_approval_playwright import RunningServer, _login


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".artifacts" / "ui-review-20261030"

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
    ok = result["textFailureCount"] == 0 and result["overlapCount"] == 0 and result["overflowX"] <= 1
    steps.append({"step": f"audit_{name}", "ok": ok, "detail": result})
    page.screenshot(path=str(OUT / f"audit_{name}.png"), full_page=True)


def run() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    if not (ROOT / "static" / "help" / "manual.html").exists():
        subprocess.run([sys.executable, "scripts/package_help.py"], cwd=ROOT, check=True)
    steps: list[dict] = []
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
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

            page.evaluate("createRecordTask('患者发热咳嗽两天，最高38.2度，没有胸痛，没有药物过敏史。')")
            page.wait_for_selector("#recordFields .record-section", timeout=60000)
            page.wait_for_timeout(1800)

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
            audit(page, "workspace", steps)

            page.set_viewport_size({"width": 1280, "height": 800})
            page.wait_for_timeout(400)
            audit(page, "workspace_1280", steps)
            page.set_viewport_size({"width": 1440, "height": 900})

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

            for help_page in ("manual", "feedback", "maintenance", "dual-environment", "course-demo", "viewer-section"):
                page.goto(f"{server.base_url}/static/help/{help_page}.html")
                page.wait_for_timeout(400)
                audit(page, f"help_{help_page}", steps)

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
