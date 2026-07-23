from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol


SAMPLE_CONVERSATION = (
    "[医生] 你好，哪里不舒服？\n"
    "[患者] 我发热三天，最高体温39度，伴有咳嗽，没有胸痛。\n"
    "[医生] 之前做过什么处理？\n"
    "[患者] 吃过布洛芬，退热后又反复发热，既往无明确药物过敏。"
)


class PilotSmokeError(RuntimeError):
    pass


class JsonClient(Protocol):
    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        ...


@dataclass
class UrlLibJsonClient:
    base_url: str
    timeout_seconds: float = 30.0
    opener: urllib.request.OpenerDirector = field(init=False)

    def __post_init__(self) -> None:
        cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
        self.base_url = self.base_url.rstrip("/")

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = urllib.parse.urljoin(f"{self.base_url}/", path.lstrip("/"))
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
        try:
            with self.opener.open(request, timeout=self.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise PilotSmokeError(f"{method.upper()} {path} returned {exc.code}: {error_body[:500]}") from exc
        except urllib.error.URLError as exc:
            raise PilotSmokeError(f"{method.upper()} {path} failed: {exc.reason}") from exc
        if not response_body:
            return {}
        return json.loads(response_body)


def run_smoke(
    client: JsonClient,
    *,
    username: str,
    password: str,
    timeout_seconds: float,
    poll_interval_seconds: float = 1.0,
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []

    health = client.request("GET", "/health")
    _require(health.get("status") == "ok", "health check did not return ok")
    steps.append({"name": "health", "ok": True})

    ready = client.request("GET", "/ready")
    _require(ready.get("status") == "ready", "readiness check did not return ready")
    steps.append({"name": "ready", "ok": True})

    login = client.request("POST", "/api/auth/login", {"username": username, "password": password})
    user = login.get("user") if isinstance(login, dict) else None
    _require(isinstance(user, dict) and user.get("username") == username, "login did not return requested user")
    steps.append({"name": "login", "ok": True, "username": username})

    generated = client.request("POST", "/api/records/generate", {"conversation_text": SAMPLE_CONVERSATION})
    task_id = generated.get("task_id")
    _require(isinstance(task_id, int), "record generation did not return task_id")
    steps.append({"name": "generate", "ok": True, "task_id": task_id})

    task = _poll_task_ready(client, task_id, timeout_seconds=timeout_seconds, poll_interval_seconds=poll_interval_seconds)
    result = task.get("result_json")
    _require(isinstance(result, dict), "completed task has no result_json")
    fields = result.get("fields")
    _require(isinstance(fields, dict), "completed task has no fields")
    steps.append({"name": "task_completed", "ok": True, "status": task.get("status")})

    reviewed = client.request("POST", f"/api/tasks/{task_id}/review", {"fields": fields})
    _require(_task_result(reviewed).get("reviewed") is True, "review did not mark task reviewed")
    steps.append({"name": "review", "ok": True})

    approved = client.request("POST", f"/api/tasks/{task_id}/approve")
    _require(_task_result(approved).get("approved") is True, "approval did not mark task approved")
    steps.append({"name": "approve", "ok": True})

    readiness = client.request("GET", f"/api/tasks/{task_id}/export-readiness")
    _require(readiness.get("ready") is True and readiness.get("blocked") is False, "export readiness is blocked")
    steps.append({"name": "export_readiness", "ok": True})

    exported = client.request("POST", f"/api/tasks/{task_id}/export")
    exports = exported.get("exports")
    _require(isinstance(exports, dict) and exports, "export did not return export paths")
    steps.append({"name": "export", "ok": True, "export_keys": sorted(exports)})

    return {"ok": True, "task_id": task_id, "steps": steps}


def _poll_task_ready(
    client: JsonClient,
    task_id: int,
    *,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_task: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last_task = client.request("GET", f"/api/tasks/{task_id}")
        if last_task.get("status") == "WAITING_DOCTOR_REVIEW" and isinstance(last_task.get("result_json"), dict):
            return last_task
        if last_task.get("status") == "FAILED":
            raise PilotSmokeError(f"task {task_id} failed: {last_task.get('error_message')}")
        time.sleep(poll_interval_seconds)
    raise PilotSmokeError(f"task {task_id} did not complete before timeout; last status={last_task.get('status')}")


def _task_result(task_payload: dict[str, Any]) -> dict[str, Any]:
    result = task_payload.get("result_json")
    if not isinstance(result, dict):
        raise PilotSmokeError("task response has no result_json")
    return result


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PilotSmokeError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one-command department pilot smoke test.")
    parser.add_argument("--base-url", required=True, help="Base URL such as http://127.0.0.1:2626")
    parser.add_argument("--username", default="pilot_admin", help="Pilot user to log in as.")
    parser.add_argument(
        "--password-env",
        default="MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD",
        help="Environment variable containing the login password.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    password = os.environ.get(args.password_env)
    if not password:
        report = {
            "ok": False,
            "error": f"Password environment variable is not set: {args.password_env}",
        }
    else:
        try:
            report = run_smoke(
                UrlLibJsonClient(args.base_url, timeout_seconds=args.timeout_seconds),
                username=args.username,
                password=password,
                timeout_seconds=args.timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - CLI should summarize the failing smoke step.
            report = {"ok": False, "error": str(exc)}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_format_text_report(report))
    return 0 if report.get("ok") else 1


def _format_text_report(report: dict[str, Any]) -> str:
    if not report.get("ok"):
        return f"pilot smoke: FAILED\n{report.get('error', 'unknown error')}"
    lines = [f"pilot smoke: OK (task_id={report.get('task_id')})"]
    for step in report.get("steps", []):
        lines.append(f"[OK] {step['name']}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
