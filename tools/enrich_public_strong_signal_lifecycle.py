from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantbot.odds_lifecycle import lifecycle_contract, parse_capture


SNAPSHOTS = ROOT / "data" / "odds_snapshots.jsonl"
PUBLIC_FILES = (ROOT / "strong_signals.json", ROOT / "strong_signal_ledger.json")


def load_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    rows.append(value)
    except OSError:
        return rows
    return rows


def key(row: dict[str, Any]) -> tuple[int, str, int] | None:
    try:
        return int(row["event_id"]), str(row["market"]), int(row["bookmaker_id"])
    except (KeyError, TypeError, ValueError):
        return None


def enrich_row(
    row: dict[str, Any],
    grouped: dict[tuple[int, str, int], list[dict[str, Any]]],
) -> str:
    identity = key(row)
    if identity is None:
        row["lifecycle_coverage"] = "UNRECOVERABLE"
        row["lifecycle_unavailable_reason"] = "INVALID_LIFECYCLE_IDENTITY"
        return "UNRECOVERABLE"

    pick_at = parse_capture(row.get("odds_captured_at") or row.get("signal_sent_at"))
    kickoff = parse_capture(row.get("kickoff"))
    if pick_at is None:
        row["lifecycle_coverage"] = "UNRECOVERABLE"
        row["lifecycle_unavailable_reason"] = "PICK_TIME_UNAVAILABLE"
        return "UNRECOVERABLE"

    contract = lifecycle_contract(
        grouped.get(identity, []),
        pick_at=pick_at,
        kickoff=kickoff,
    )

    opening = contract["opening"]
    pick = contract["pick"]
    closing = contract["closing"]

    # Preserve the decision/pick odds already persisted on the Strong Signal.
    # The lifecycle authority is used only to attach evidence and missing-stage
    # reasons; it never changes model, EV, edge, stake or virtual accounting.
    if opening:
        row["opening_odd"] = opening.get("odd")
        row["opening_opposite_odd"] = opening.get("opposite_odd")
        row["opening_odds_captured_at"] = opening.get("odds_captured_at")
        row["opening_snapshot_id"] = opening.get("snapshot_id")
    else:
        row["opening_odd"] = None
        row["opening_opposite_odd"] = None
        row["opening_odds_captured_at"] = None
        row["opening_snapshot_id"] = None

    if pick:
        row["pick_snapshot_id"] = pick.get("snapshot_id")
        row["pick_odds_captured_at"] = pick.get("odds_captured_at")
    else:
        row["pick_snapshot_id"] = None
        row["pick_odds_captured_at"] = row.get("odds_captured_at")

    if closing:
        row["closing_odd"] = closing.get("odd")
        row["closing_opposite_odd"] = closing.get("opposite_odd")
        row["closing_odds_captured_at"] = closing.get("odds_captured_at")
        row["closing_snapshot_id"] = closing.get("snapshot_id")
    else:
        row["closing_odd"] = None
        row["closing_opposite_odd"] = None
        row["closing_odds_captured_at"] = None
        row["closing_snapshot_id"] = None

    row["lifecycle_schema_version"] = contract["schema_version"]
    row["lifecycle_coverage"] = contract["coverage"]
    row["opening_available"] = contract["opening_available"]
    row["pick_available"] = contract["pick_available"]
    row["closing_available"] = contract["closing_available"]
    row["opening_unavailable_reason"] = contract["opening_unavailable_reason"]
    row["pick_unavailable_reason"] = contract["pick_unavailable_reason"]
    row["closing_unavailable_reason"] = contract["closing_unavailable_reason"]
    row["clv_odds_pct"] = contract["clv_odds_pct"]
    row["clv_available"] = contract["clv_available"]
    row["clv_status"] = contract["clv_status"]
    return str(contract["coverage"])


def enrich(root: Path = ROOT) -> dict[str, int]:
    observations = load_jsonl(root / "data" / "odds_snapshots.jsonl")
    grouped: dict[tuple[int, str, int], list[dict[str, Any]]] = defaultdict(list)
    for item in observations:
        identity = key(item)
        if identity is not None and parse_capture(item.get("odds_captured_at")) is not None:
            grouped[identity].append(item)

    for rows in grouped.values():
        rows.sort(key=lambda item: parse_capture(item["odds_captured_at"]))

    stats = defaultdict(int)
    for path in PUBLIC_FILES:
        rows = load_json(path)
        for row in rows:
            coverage = enrich_row(row, grouped)
            stats[f"{path.name}:{coverage}"] += 1
        path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    return dict(stats)


if __name__ == "__main__":
    print(json.dumps(enrich(), sort_keys=True))
