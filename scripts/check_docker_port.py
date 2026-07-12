"""Check whether the Docker host port can be bound locally.

This is mainly useful on Windows where Hyper-V / WinNAT may reserve port
ranges. The script does not require administrator privileges.
"""

from __future__ import annotations

import argparse
import platform
import socket
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class PortCheckResult:
    port: int
    bindable: bool
    excluded: bool
    reason: str


def parse_excluded_ranges(output: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for raw_line in output.splitlines():
        parts = raw_line.split()
        if len(parts) < 2:
            continue
        if parts[0].isdigit() and parts[1].isdigit():
            ranges.append((int(parts[0]), int(parts[1])))
    return ranges


def is_port_excluded(port: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= port <= end for start, end in ranges)


def get_windows_excluded_ranges() -> list[tuple[int, int]]:
    if platform.system().lower() != "windows":
        return []
    try:
        completed = subprocess.run(
            ["netsh", "interface", "ipv4", "show", "excludedportrange", "protocol=tcp"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return parse_excluded_ranges(completed.stdout)


def can_bind_port(port: int, host: str = "0.0.0.0") -> tuple[bool, str]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError as exc:
            return False, str(exc)
    return True, "bind check passed"


def check_port(port: int) -> PortCheckResult:
    ranges = get_windows_excluded_ranges()
    excluded = is_port_excluded(port, ranges)
    bindable, bind_reason = can_bind_port(port)
    if bindable:
        reason = "port is bindable"
    elif excluded:
        reason = f"port is inside a Windows excluded TCP range; bind error: {bind_reason}"
    else:
        reason = f"port is not bindable; bind error: {bind_reason}"
    return PortCheckResult(port=port, bindable=bindable, excluded=excluded, reason=reason)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Docker host port availability.")
    parser.add_argument("--port", type=int, default=2626)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = check_port(args.port)
    status = "ok" if result.bindable else "blocked"
    print(f"port={result.port} status={status} excluded={str(result.excluded).lower()} reason={result.reason}")
    return 0 if result.bindable else 2


if __name__ == "__main__":
    raise SystemExit(main())
