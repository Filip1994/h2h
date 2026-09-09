from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_META = "watchlist_run_meta.json"


def build_metadata(
    *,
    run_id: str | int,
    run_attempt: str | int,
    workflow: str,
    sha: str,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    timestamp = (generated_at or datetime.now(UTC)).astimezone(UTC).isoformat()
    return {
        "schema_version": 1,
        "producer": "watchlist",
        "producer_workflow": workflow,
        "run_id": str(run_id),
        "run_attempt": int(run_attempt),
        "source_sha": sha,
        "generated_at": timestamp,
        "writer_authority": "CANONICAL_STRONG_NEAR_WATCHLIST",
    }


def is_stale(candidate: dict[str, Any], current: dict[str, Any] | None) -> bool:
    """Reject a candidate produced by an older workflow run.

    Run IDs are monotonically increasing for GitHub Actions runs. Timestamp is
    retained as an audit field, but ordering uses run_id so runner clock skew
    cannot make a newer run look stale.
    """
    if not current:
        return False
    try:
        return int(candidate["run_id"]) < int(current["run_id"])
    except (KeyError, TypeError, ValueError):
        # A malformed existing authority marker is unsafe to overwrite.
        return True


def load_metadata(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def assert_not_stale(candidate_path: Path, current_path: Path) -> None:
    candidate = load_metadata(candidate_path)
    if not candidate:
        raise RuntimeError("Missing or invalid candidate watchlist provenance")
    current = load_metadata(current_path)
    if is_stale(candidate, current):
        current_id = current.get("run_id") if current else "unknown"
        raise RuntimeError(
            f"Stale watchlist writer rejected: candidate run {candidate.get('run_id')} "
            f"< canonical run {current_id}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Guard canonical Strong/Near watchlist writes"
    )
    parser.add_argument("command", choices=("write", "check"))
    parser.add_argument("--path", default=DEFAULT_META)
    parser.add_argument("--current-path", default=DEFAULT_META)
    parser.add_argument("--run-id")
    parser.add_argument("--run-attempt", default="1")
    parser.add_argument("--workflow", default="QuantBet adaptive watchlist monitor")
    parser.add_argument("--sha", default="unknown")
    args = parser.parse_args()

    path = Path(args.path)
    if args.command == "write":
        if not args.run_id:
            raise SystemExit("--run-id is required")
        path.write_text(
            json.dumps(
                build_metadata(
                    run_id=args.run_id,
                    run_attempt=args.run_attempt,
                    workflow=args.workflow,
                    sha=args.sha,
                ),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return 0

    assert_not_stale(path, Path(args.current_path))
    print("Canonical watchlist writer provenance OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
