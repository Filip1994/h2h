from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_evidence(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def source_run_id(evidence: dict[str, Any] | None) -> int | None:
    if not evidence:
        return None
    try:
        return int((evidence.get("source_run") or {})["run_id"])
    except (KeyError, TypeError, ValueError):
        return None


def is_stale(source_run: str | int, current: dict[str, Any] | None) -> bool:
    """Return True when evidence cannot supersede canonical evidence."""
    candidate_id = int(source_run)
    current_id = source_run_id(current)
    if current_id is None:
        return bool(current)
    return candidate_id < current_id


def assert_publishable(source_run: str | int, current_path: Path) -> None:
    current = load_evidence(current_path)
    if current_path.exists() and current is None:
        raise RuntimeError(
            "Existing Strong Signal evidence is malformed; refusing overwrite"
        )
    if is_stale(source_run, current):
        current_id = source_run_id(current)
        raise RuntimeError(
            f"Stale Strong Signal evidence rejected: source run {source_run} "
            f"< canonical evidence run {current_id}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Guard Strong Signal provenance publication ordering"
    )
    parser.add_argument("check", choices=("check",))
    parser.add_argument("--source-run", required=True)
    parser.add_argument("--current-path", required=True)
    args = parser.parse_args()
    assert_publishable(args.source_run, Path(args.current_path))
    print("Strong Signal provenance publication guard OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
