#!/usr/bin/env python3
"""Fail if VERSION, frontend/package.json, and an optional git tag disagree."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STABLE_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "tag",
        nargs="?",
        help="Git tag or refs/tags/vX.Y.Z value that must match VERSION",
    )
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root")
    return parser.parse_args(argv)


def load_version_file(root: Path) -> str:
    path = root / "VERSION"
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise SystemExit(f"unable to read {path}: {exc}") from exc
    if not STABLE_VERSION.fullmatch(value):
        raise SystemExit(f"VERSION {value!r} is not a stable X.Y.Z version")
    return value


def load_package_version(root: Path) -> str:
    path = root / "frontend" / "package.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"unable to read {path}: {exc}") from exc
    value = payload.get("version") if isinstance(payload, dict) else None
    if not isinstance(value, str) or not STABLE_VERSION.fullmatch(value):
        raise SystemExit(f"frontend/package.json version {value!r} is not a stable X.Y.Z version")
    return value


def normalize_tag(tag: str) -> str:
    value = tag.strip()
    if value.startswith("refs/tags/"):
        value = value.removeprefix("refs/tags/")
    if value.startswith("v"):
        value = value[1:]
    return value


def verify(root: Path, tag: str | None = None) -> str:
    version = load_version_file(root)
    package = load_package_version(root)
    errors: list[str] = []
    if version != package:
        errors.append(f"VERSION {version!r} != frontend/package.json {package!r}")
    if tag:
        normalized = normalize_tag(tag)
        if normalized != version:
            errors.append(f"git tag {tag!r} != VERSION {version!r}")
    if errors:
        raise SystemExit("\n".join(errors))
    return version


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    version = verify(args.root, args.tag)
    print(f"version {version} is consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
