from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.audit_anchor import append_anchor, anchor_path, verify_with_anchor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Anchor the audit hash chain head outside SQLite and verify against it."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    anchor = subparsers.add_parser("anchor", help="Append the current chain head to the anchor file.")
    anchor.add_argument("--file", type=Path, default=None)

    verify = subparsers.add_parser("verify", help="Verify the chain and the latest anchor.")
    verify.add_argument("--file", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "anchor":
        entry = append_anchor(args.file)
        print(json.dumps({"anchor": entry, "file": str(anchor_path(args.file))}, ensure_ascii=False))
        return 0
    if args.command == "verify":
        report = verify_with_anchor(args.file)
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report.get("ok") else 1
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
