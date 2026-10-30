"""Capture browser screenshots of the current build for demo evidence.

This drives the real doctor page with Playwright against a self-started server
(Mock provider, temporary database). It is evidence tooling, not a clinical or
visual approval: screenshots are stored under .artifacts and never committed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from tests.test_doctor_itemized_approval_playwright import RunningServer, _login


ROOT = Path(__file__).resolve().parents[1]


def _snap(page, out_dir: Path, name: str, steps: list[dict]) -> None:
    path = out_dir / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    steps.append({"step": name, "ok": path.exists(), "path": str(path), "bytes": path.stat().st_size})


def run(out_dir: Path, viewport: tuple[int, int] = (1440, 900)) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    steps: list[dict] = []
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
            page.goto(f"{server.base_url}/static/doctor.html", wait_until="networkidle")
            _snap(page, out_dir, "01_login", steps)

            _login(page, server.base_url)
            steps.append({"step": "login", "ok": True})
            page.wait_for_timeout(500)
            _snap(page, out_dir, "02_workbench", steps)

            if not page.locator("#localSyntheticPatient").is_visible():
                page.locator("#localRegistrationDisclosure summary").click()
            page.select_option("#localSyntheticPatient", "SIM-DEMO-0929-FEVER")
            page.click("#createLocalEncounterButton")
            page.wait_for_timeout(500)
            _snap(page, out_dir, "03_encounter_created", steps)

            page.locator('#dashboardEncounterList [data-encounter-action="start"]').click()
            page.wait_for_timeout(800)
            steps.append({"step": "start_encounter", "ok": True})
            _snap(page, out_dir, "04_workspace", steps)

            version = page.evaluate("fetch('/version').then(r => r.json())")
            steps.append({"step": "version", "ok": bool(version.get("service")), "detail": version})
            browser.close()
    finally:
        server.close()

    report = {
        "ok": all(step["ok"] for step in steps),
        "base_version": next((s.get("detail") for s in steps if s["step"] == "version"), None),
        "viewport": {"width": viewport[0], "height": viewport[1]},
        "steps": steps,
    }
    (out_dir / "browser_demo.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture doctor-page screenshots of the current build.")
    parser.add_argument("--out-dir", default=str(ROOT / ".artifacts" / "browser-demo-20261030"))
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    args = parser.parse_args(argv)
    report = run(Path(args.out_dir), (args.width, args.height))
    for step in report["steps"]:
        mark = "PASS" if step["ok"] else "FAIL"
        print(f"  [{mark}] {step['step']:<22} {step.get('path') or step.get('detail') or ''}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
