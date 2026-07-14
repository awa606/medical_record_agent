"""Check whether the Docker host port can be bound locally.

This is mainly useful on Windows where Hyper-V / WinNAT may reserve port
ranges. The script does not require administrator privileges.
"""

from __future__ import annotations

import argparse
import json
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


@dataclass(frozen=True)
class PortScanResult:
    start: int
    end: int
    recommended_port: int | None
    checked: list[PortCheckResult]


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


def scan_ports(start: int, end: int) -> PortScanResult:
    if start > end:
        raise ValueError("start port must be <= end port")
    checked: list[PortCheckResult] = []
    recommended_port: int | None = None
    for port in range(start, end + 1):
        result = check_port(port)
        checked.append(result)
        if recommended_port is None and result.bindable:
            recommended_port = port
    return PortScanResult(start=start, end=end, recommended_port=recommended_port, checked=checked)


def result_to_dict(result: PortCheckResult) -> dict[str, object]:
    return {
        "port": result.port,
        "bindable": result.bindable,
        "excluded": result.excluded,
        "reason": result.reason,
    }


def print_single_result(result: PortCheckResult, output_format: str) -> None:
    status = "ok" if result.bindable else "blocked"
    if output_format == "json":
        print(json.dumps(result_to_dict(result), ensure_ascii=False))
    elif output_format == "env":
        if result.bindable:
            print(f"MRA_HOST_PORT={result.port}")
        else:
            print(f"# port {result.port} blocked: {result.reason}")
    else:
        print(f"port={result.port} status={status} excluded={str(result.excluded).lower()} reason={result.reason}")


def print_scan_result(scan: PortScanResult, output_format: str) -> None:
    if output_format == "json":
        print(
            json.dumps(
                {
                    "start": scan.start,
                    "end": scan.end,
                    "recommended_port": scan.recommended_port,
                    "checked": [result_to_dict(result) for result in scan.checked],
                },
                ensure_ascii=False,
            )
        )
    elif output_format == "env":
        if scan.recommended_port is None:
            print(f"# no bindable port found in {scan.start}-{scan.end}")
        else:
            print(f"MRA_HOST_PORT={scan.recommended_port}")
    else:
        if scan.recommended_port is None:
            print(f"range={scan.start}-{scan.end} recommended=none")
        else:
            print(f"range={scan.start}-{scan.end} recommended={scan.recommended_port}")
        for result in scan.checked:
            status = "ok" if result.bindable else "blocked"
            print(f"port={result.port} status={status} excluded={str(result.excluded).lower()} reason={result.reason}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Docker host port availability.")
    parser.add_argument("--port", type=int, default=2626)
    parser.add_argument("--start", type=int, default=None, help="Scan start port, for example 2600.")
    parser.add_argument("--end", type=int, default=None, help="Scan end port, for example 2699.")
    parser.add_argument("--format", choices=["text", "env", "json"], default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.start is not None or args.end is not None:
        start = 2600 if args.start is None else args.start
        end = 2699 if args.end is None else args.end
        scan = scan_ports(start, end)
        print_scan_result(scan, args.format)
        return 0 if scan.recommended_port is not None else 2
    result = check_port(args.port)
    print_single_result(result, args.format)
    return 0 if result.bindable else 2


if __name__ == "__main__":
    raise SystemExit(main())
