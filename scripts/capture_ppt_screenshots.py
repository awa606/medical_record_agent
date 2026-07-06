from __future__ import annotations

import argparse
import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "docs" / "final_report" / "images" / "ppt"
RUN_LOG = PROJECT_ROOT / "docs" / "dev_logs" / "runs" / "2026-06-20_fever_01_final_demo.md"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TASK_ID = 38
DEFAULT_AUDIO_ID = "9b3dd889e50042408fdc7ed4ac7c34ee"


@dataclass
class CaptureResult:
    path: Path
    note: str
    needs_review: bool = False


def main() -> int:
    args = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed. Please run:")
        print("python -m pip install playwright")
        print("python -m playwright install chromium")
        return 1

    results: list[CaptureResult] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1100},
            device_scale_factor=1,
            locale="zh-CN",
        )
        page = context.new_page()
        results.append(capture_debug_page(page, args.base_url, args.task_id, args.audio_id))
        results.append(capture_run_log(page))
        results.append(capture_evidence_chain(page))
        browser.close()

    print("PPT evidence screenshots:")
    for result in results:
        status = "NEEDS_REVIEW" if result.needs_review else "OK"
        print(f"- {status}: {result.path} ({result.note})")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture real evidence screenshots for PPT page 12.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Local FastAPI service base URL.")
    parser.add_argument("--task-id", type=int, default=DEFAULT_TASK_ID, help="Task id to load in debug page.")
    parser.add_argument("--audio-id", default=DEFAULT_AUDIO_ID, help="Audio id used for Agent Trace ASR context.")
    return parser.parse_args()


def capture_debug_page(page, base_url: str, task_id: int, audio_id: str) -> CaptureResult:
    output = OUTPUT_DIR / "fig12_debug_page.png"
    url = f"{base_url.rstrip('/')}/static/debug.html"
    api_note = ""
    needs_review = False

    try:
        page.goto(url, wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(800)
    except Exception as exc:
        fallback_debug_unavailable_page(page, url, task_id, exc)
        page.screenshot(path=str(output), full_page=True)
        return CaptureResult(
            output,
            f"debug.html unavailable: {exc}; 需要人工确认服务启动后重新截图 task_id={task_id}",
            needs_review=True,
        )

    task: dict[str, Any] | None = None
    steps: list[dict[str, Any]] | None = None
    trace: dict[str, Any] | None = None
    safety: dict[str, Any] | None = None

    try:
        task = fetch_json(f"{base_url.rstrip('/')}/api/tasks/{task_id}")
        steps = fetch_json(f"{base_url.rstrip('/')}/api/tasks/{task_id}/steps")
        trace = fetch_json(f"{base_url.rstrip('/')}/api/tasks/{task_id}/trace?audio_id={quote(audio_id)}")
        result_json = task.get("result_json") if isinstance(task, dict) else None
        safety = result_json.get("safety_check") if isinstance(result_json, dict) else None
        api_note = f"loaded task_id={task_id} from API"
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        api_note = (
            f"could not auto-load task_id={task_id}: {exc}; "
            "需要人工选择 task_id=38 后重新截图"
        )
        needs_review = True

    page.evaluate("() => { if (window.openDebugDrawer) window.openDebugDrawer(); }")
    if task is not None:
        page.evaluate(
            """({taskId, audioId, task, steps, trace, safety}) => {
                const setText = (id, value) => {
                  const node = document.getElementById(id);
                  if (node) node.textContent = value;
                };
                const setJson = (id, value) => {
                  const node = document.getElementById(id);
                  if (node) node.textContent = JSON.stringify(value, null, 2);
                };
                setText("debugTaskIdLabel", String(taskId));
                setText("debugAudioIdLabel", audioId || "-");
                setText("sessionId", `task-${taskId}`);
                setJson("debugAgentTraceJson", trace);
                setJson("debugTaskJson", task);
                setJson("debugStepsJson", steps);
                setJson("debugSafetyJson", safety || {});
                setText(
                  "debugRunLogCommand",
                  `python scripts/save_run_log.py --task-id ${taskId} --audio-id ${audioId || "xxx"} --title fever_01_demo`
                );
                document.querySelectorAll("#debugDrawer details").forEach((detail) => { detail.open = true; });
              }""",
            {
                "taskId": task_id,
                "audioId": audio_id,
                "task": task,
                "steps": steps or [],
                "trace": trace or {},
                "safety": safety or {},
            },
        )

    page.add_style_tag(
        content="""
          body { background: #f3f4f6 !important; }
          .drawer-backdrop { display: none !important; }
          #drawer {
            position: static !important;
            transform: none !important;
            width: 100% !important;
            max-width: none !important;
            min-height: auto !important;
            box-shadow: none !important;
            border: 0 !important;
            padding: 20px !important;
          }
          #drawer.active { transform: none !important; }
          #debugDrawer { display: grid !important; grid-template-columns: 1fr 1fr; gap: 14px; }
          #debugDrawer details { display: block !important; border: 1px solid #dbeafe !important; border-radius: 12px !important; background: #fff !important; padding: 12px !important; }
          #debugDrawer pre { max-height: 260px !important; overflow: auto !important; white-space: pre-wrap !important; word-break: break-word !important; font-size: 12px !important; line-height: 1.45 !important; }
          #debugDrawer details:nth-of-type(4),
          #debugDrawer details:nth-of-type(6),
          #debugDrawer details:nth-of-type(7),
          #debugDrawer details:nth-of-type(8) { grid-column: span 1; }
          .drawer-header { position: sticky !important; top: 0 !important; background: #fff !important; z-index: 2 !important; border-bottom: 1px solid #dbeafe !important; }
        """
    )
    page.wait_for_timeout(500)
    page.screenshot(path=str(output), full_page=True)
    return CaptureResult(output, api_note, needs_review)


def fallback_debug_unavailable_page(page, url: str, task_id: int, exc: Exception) -> None:
    page.set_content(
        f"""
        <!doctype html>
        <html lang="zh-CN">
        <head>
          <meta charset="utf-8" />
          <style>
            body {{
              margin: 0;
              padding: 40px;
              background: #f3f4f6;
              font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
              color: #111827;
            }}
            .box {{
              max-width: 1080px;
              margin: 0 auto;
              background: #fff;
              border: 2px solid #fecaca;
              border-radius: 16px;
              padding: 30px;
              box-shadow: 0 12px 34px rgba(15, 23, 42, 0.08);
            }}
            h1 {{ color: #b91c1c; margin-top: 0; }}
            code {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 2px 6px; }}
            .note {{ margin-top: 20px; padding: 14px 16px; border-radius: 12px; background: #fff7ed; color: #9a3412; }}
          </style>
        </head>
        <body>
          <main class="box">
            <h1>debug.html 截图需要人工复查</h1>
            <p>脚本尝试访问 <code>{html.escape(url)}</code>，但当前无法打开页面。</p>
            <p>优先截图任务：<code>task_id={task_id}</code>。</p>
            <p>错误信息：<code>{html.escape(str(exc))}</code></p>
            <div class="note">请确认本地服务已运行后，人工打开 debug.html 并选择 task_id=38，重新截图 Task JSON / Steps JSON / Safety JSON / Agent Trace 区域。</div>
          </main>
        </body>
        </html>
        """,
        wait_until="load",
    )


def capture_run_log(page) -> CaptureResult:
    output = OUTPUT_DIR / "fig12_run_log.png"
    markdown_text = RUN_LOG.read_text(encoding="utf-8")
    html_body = markdown_to_html(markdown_text)
    html_page = f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <style>
        body {{
          margin: 0;
          padding: 28px;
          background: #f3f4f6;
          color: #111827;
          font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
        }}
        .page {{
          max-width: 1180px;
          margin: 0 auto;
          background: #fff;
          border: 1px solid #dbeafe;
          border-radius: 16px;
          box-shadow: 0 12px 34px rgba(15, 23, 42, 0.08);
          padding: 28px 34px;
        }}
        h1 {{ font-size: 26px; margin: 0 0 20px; color: #1d4ed8; }}
        h2 {{ font-size: 19px; margin: 22px 0 10px; color: #1f2937; border-left: 5px solid #3b82f6; padding-left: 10px; }}
        ul {{ margin: 8px 0 12px 22px; padding: 0; }}
        li {{ margin: 5px 0; line-height: 1.6; }}
        table {{ width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 13px; }}
        th, td {{ border: 1px solid #d1d5db; padding: 8px; vertical-align: top; }}
        th {{ background: #eff6ff; color: #1e40af; }}
        code, pre {{ font-family: Consolas, "Courier New", monospace; }}
        .source-note {{
          color: #4b5563;
          background: #f9fafb;
          border: 1px solid #e5e7eb;
          border-radius: 10px;
          padding: 10px 12px;
          margin-bottom: 14px;
        }}
        strong, b {{ color: #111827; }}
      </style>
    </head>
    <body>
      <main class="page">
        <div class="source-note">Source: docs/dev_logs/runs/2026-06-20_fever_01_final_demo.md</div>
        {html_body}
      </main>
    </body>
    </html>
    """
    page.set_content(html_page, wait_until="load")
    page.set_viewport_size({"width": 1280, "height": 1600})
    page.screenshot(path=str(output), full_page=True)
    return CaptureResult(output, "rendered existing Markdown run log")


def capture_evidence_chain(page) -> CaptureResult:
    output = OUTPUT_DIR / "fig12_debug_runlog_evidence_chain.png"
    html_page = """
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <style>
        body {
          margin: 0;
          background: #f3f4f6;
          font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
          color: #111827;
        }
        .canvas {
          width: 1280px;
          height: 720px;
          box-sizing: border-box;
          padding: 46px 56px;
          background: #f8fafc;
        }
        h1 {
          margin: 0 0 12px;
          font-size: 30px;
          color: #1e3a8a;
        }
        .subtitle {
          margin-bottom: 38px;
          color: #475569;
          font-size: 18px;
        }
        .flow {
          display: grid;
          grid-template-columns: 1fr 92px 1fr 92px 1fr;
          align-items: center;
          gap: 0;
        }
        .card {
          min-height: 240px;
          background: #fff;
          border: 2px solid #bfdbfe;
          border-radius: 18px;
          box-shadow: 0 14px 32px rgba(15, 23, 42, 0.08);
          padding: 26px;
          box-sizing: border-box;
        }
        .card h2 {
          margin: 0 0 18px;
          font-size: 24px;
          color: #1d4ed8;
        }
        .card p {
          margin: 8px 0;
          font-size: 17px;
          line-height: 1.55;
          color: #334155;
        }
        .pill {
          display: inline-block;
          margin-top: 14px;
          padding: 8px 12px;
          border-radius: 999px;
          background: #eff6ff;
          color: #1d4ed8;
          font-size: 15px;
          font-weight: 700;
        }
        .arrow {
          text-align: center;
          color: #2563eb;
          font-size: 46px;
          font-weight: 800;
        }
        .footer {
          margin-top: 44px;
          border-left: 6px solid #22c55e;
          background: #f0fdf4;
          padding: 18px 22px;
          border-radius: 14px;
          color: #166534;
          font-size: 18px;
        }
      </style>
    </head>
    <body>
      <section class="canvas">
        <h1>PPT 第 12 页证据链</h1>
        <div class="subtitle">调试页 JSON、运行日志脚本和 Markdown 运行日志形成可追踪证据链。</div>
        <div class="flow">
          <div class="card">
            <h2>debug.html</h2>
            <p>展示 Task JSON、Steps JSON、Safety JSON、Agent Trace。</p>
            <p>用于说明系统执行过程不是黑箱。</p>
            <span class="pill">课程调试与评分证据</span>
          </div>
          <div class="arrow">→</div>
          <div class="card">
            <h2>save_run_log.py</h2>
            <p>输入 task_id 和 audio_id。</p>
            <p>读取任务、ASRResult、步骤、安全校验和 Agent Trace。</p>
            <span class="pill">自动沉淀运行记录</span>
          </div>
          <div class="arrow">→</div>
          <div class="card">
            <h2>Markdown 运行日志</h2>
            <p>记录 ASR engine、role_strategy、WAITING_DOCTOR_REVIEW。</p>
            <p>记录 export_allowed=false 与医生审核边界。</p>
            <span class="pill">可复盘、可提交</span>
          </div>
        </div>
        <div class="footer">
          证据链用途：支撑 Agent Trace、Human-in-the-loop、安全校验和演示结果复盘。
        </div>
      </section>
    </body>
    </html>
    """
    page.set_content(html_page, wait_until="load")
    page.set_viewport_size({"width": 1280, "height": 720})
    page.screenshot(path=str(output), full_page=False)
    return CaptureResult(output, "generated evidence-chain diagram")


def fetch_json(url: str) -> Any:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def markdown_to_html(markdown_text: str) -> str:
    try:
        import markdown

        return markdown.markdown(markdown_text, extensions=["tables", "fenced_code"])
    except ImportError:
        return fallback_markdown_to_html(markdown_text)


def fallback_markdown_to_html(markdown_text: str) -> str:
    parts: list[str] = []
    in_list = False
    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        if not line:
            if in_list:
                parts.append("</ul>")
                in_list = False
            continue
        if line.startswith("# "):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<h1>{html.escape(line[2:].strip())}</h1>")
        elif line.startswith("## "):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<h2>{html.escape(line[3:].strip())}</h2>")
        elif line.startswith("- "):
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{html.escape(line[2:].strip())}</li>")
        else:
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<p>{html.escape(line)}</p>")
    if in_list:
        parts.append("</ul>")
    return "\n".join(parts)


if __name__ == "__main__":
    raise SystemExit(main())
