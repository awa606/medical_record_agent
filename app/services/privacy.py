"""Local identity mapping and anonymous outward text, never clinical substitution."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
import logging
import traceback
from pathlib import Path

def enabled() -> bool:
    flag = os.getenv("MRA_ANONYMIZE")
    return flag.lower() in {"1", "true", "yes"} if flag is not None else os.getenv("RECORD_PROVIDER_MODE", "demo") == "edge"

def _connection():
    from app.db import get_db_path
    path = Path(get_db_path()).with_suffix(".identity-map.sqlite3")
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.execute("CREATE TABLE IF NOT EXISTS identities (original TEXT PRIMARY KEY, alias TEXT NOT NULL, kind TEXT NOT NULL)")
    return connection

def register_identity(value: str, kind: str = "姓名") -> str:
    if not enabled() or not value or value.startswith(("患者-", "[已脱敏", "SIM-")):
        return value
    alias = ("患者-" if kind == "姓名" else "[已脱敏-" + kind + "-") + uuid.uuid4().hex[:8] + ("" if kind == "姓名" else "]")
    connection = _connection()
    try:
        with connection:
            connection.execute("INSERT OR IGNORE INTO identities VALUES (?,?,?)", (value, alias, kind))
            return connection.execute("SELECT alias FROM identities WHERE original=?", (value,)).fetchone()[0]
    finally:
        connection.close()

def anonymize_text(text: str) -> str:
    if not enabled() or not isinstance(text, str) or not text:
        return text
    for match in re.finditer(r"(?:姓名[是为：:\s]*|我叫|患者叫|患者姓名[：:\s]*)([\u4e00-\u9fff]{2,4})(?=[，,。；;\s]|$)", text):
        register_identity(match.group(1))
    for match in re.finditer(r"(?<!\d)(?:\d{17}[\dXx]|1[3-9]\d{9})(?!\d)", text):
        value = match.group(0)
        register_identity(value, "身份证" if len(value) == 18 else "联系方式")
    for match in re.finditer(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text):
        register_identity(match.group(0), "联系方式")
    connection = _connection()
    try:
        identities = connection.execute("SELECT original,alias FROM identities ORDER BY length(original) DESC").fetchall()
    finally:
        connection.close()
    for original, alias in identities:
        text = text.replace(original, alias)
    return text

def anonymize_payload(value):
    if not enabled():
        return value
    if isinstance(value, dict):
        for key in ("patient_display_name", "patient_name"):
            if isinstance(value.get(key), str):
                register_identity(value[key])
        return {key: anonymize_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [anonymize_payload(item) for item in value]
    if isinstance(value, str):
        return anonymize_text(value)
    return value


def anonymous_sse_frame(frame: bytes) -> bytes:
    text = frame.decode("utf-8")
    lines = text.replace("\r\n", "\n").split("\n")
    data = "\n".join(line[5:].lstrip(" ") for line in lines if line.startswith("data:"))
    if data:
        try:
            safe = json.dumps(anonymize_payload(json.loads(data)), ensure_ascii=False)
            lines = [line for line in lines if not line.startswith("data:")]
            lines.append("data: " + safe)
        except ValueError:
            lines = [anonymize_text(line) for line in lines]
    return anonymize_text("\n".join(lines)).encode("utf-8")


def install_anonymous_logging() -> None:
    previous = logging.getLogRecordFactory()
    if getattr(previous, "anonymous_records", False):
        return
    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        if enabled():
            try:
                from urllib.parse import unquote
                if record.name == 'uvicorn.access' and isinstance(record.args, tuple):
                    # AccessFormatter unpacks the original five arguments.
                    record.args = tuple(anonymize_text(unquote(arg)) if isinstance(arg, str) else arg for arg in record.args)
                else:
                    record.msg = anonymize_text(unquote(record.getMessage()))
                    record.args = ()
                if record.exc_info:
                    record.exc_text = anonymize_text("".join(traceback.format_exception(*record.exc_info)))
                    record.exc_info = None
            except Exception:
                record.msg, record.args, record.exc_info, record.exc_text = "[anonymous log unavailable]", (), None, None
        return record
    factory.anonymous_records = True
    logging.setLogRecordFactory(factory)

class AnonymousResponses:
    """Sanitize JSON and SSE at the final ASGI boundary without buffering streams."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or not enabled():
            return await self.app(scope, receive, send)
        start = None
        content_type = ""
        buffer = b""
        async def wrapped(message):
            nonlocal start, content_type, buffer
            if message["type"] == "http.response.start":
                start = dict(message)
                headers = message.get("headers", [])
                content_type = dict(headers).get(b"content-type", b"").decode()
                if "application/json" in content_type or "text/event-stream" in content_type:
                    start["headers"] = [(k,v) for k,v in headers if k.lower() not in {b"content-length", b"etag"}]
                    if "text/event-stream" in content_type:
                        await send(start)
                    return
                await send(message)
            elif message["type"] == "http.response.body" and "application/json" in content_type:
                buffer += message.get("body", b"")
                if not message.get("more_body"):
                    try:
                        body = json.dumps(anonymize_payload(json.loads(buffer)), ensure_ascii=False).encode()
                    except (ValueError, UnicodeError):
                        body = b'{"detail":"anonymous response serialization failed"}'
                        start["status"] = 500
                    await send(start)
                    await send({**message, "body": body})
            elif message["type"] == "http.response.body" and "text/event-stream" in content_type:
                buffer += message.get("body", b"")
                while match := re.search(rb"\r?\n\r?\n", buffer):
                    frame, buffer = buffer[:match.start()], buffer[match.end():]
                    await send({"type":"http.response.body", "body":anonymous_sse_frame(frame)+b"\n\n", "more_body":True})
                if not message.get("more_body"):
                    await send({**message,"body":anonymous_sse_frame(buffer)})
            else:
                await send(message)
        await self.app(scope, receive, wrapped)
