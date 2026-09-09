from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any

TERMINAL = {"WIN", "LOSS", "VOID", "REVIEW", "SKIPPED", "SETTLED"}
STRONG = "STRONG_SIGNAL"


def load_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def key(row: dict[str, Any]) -> str:
    return str(row.get("id") or row.get("signal_id") or row.get("observation_id") or "")


def active(row: dict[str, Any]) -> bool:
    return str(row.get("status") or "PENDING").upper() == "PENDING"


def previous_public(root: Path) -> list[dict[str, Any]]:
    try:
        payload = subprocess.check_output(
            ["git", "show", "HEAD^:strong_signals.json"],
            cwd=root,
            text=True,
        )
        value = json.loads(payload)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def build_evidence(root: Path) -> dict[str, Any]:
    before = previous_public(root)
    after = load_json(root / "strong_signals.json")
    before_ids = {key(x) for x in before if key(x)}
    after_ids = {key(x) for x in after if key(x)}
    new_ids = sorted(after_ids - before_ids)
    duplicated_ids = sorted(
        item for item in after_ids if sum(key(x) == item for x in after) > 1
    )

    events_path = root / "data" / "intraday_signal_events.jsonl"
    new_events: list[dict[str, Any]] = []
    if events_path.exists():
        try:
            previous_events = subprocess.check_output(
                ["git", "show", "HEAD^:data/intraday_signal_events.jsonl"],
                cwd=root,
                text=True,
            ).splitlines()
        except (OSError, subprocess.CalledProcessError):
            previous_events = []
        previous_event_ids = set()
        for line in previous_events:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and value.get("event_id"):
                previous_event_ids.add(str(value["event_id"]))
        try:
            current_lines = events_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            current_lines = []
        for line in current_lines:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(value, dict)
                and str(value.get("event_id")) not in previous_event_ids
            ):
                new_events.append(value)

    strong_after = [
        x for x in after if str(x.get("signal_class") or "").upper() == STRONG
    ]
    new_rows = [x for x in strong_after if key(x) in set(new_ids)]
    history = [x for x in strong_after if not active(x)]
    active_rows = [x for x in strong_after if active(x)]
    near = load_json(root / "near_misses.json")

    return {
        "schema_version": 2,
        "source_run": {
            "workflow": os.environ.get("GITHUB_WORKFLOW", "QuantBet adaptive watchlist monitor"),
            "run_id": os.environ.get("SOURCE_RUN_ID") or None,
            "run_started_at": os.environ.get("SOURCE_RUN_STARTED_AT") or None,
            "data_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip(),
        },
        "strong_signal_provenance": {
            "before_public_strong_signals_total": len(before),
            "after_public_strong_signals_total": len(after),
            "dataset_delta": len(after) - len(before),
            "new_strong_signals": len(new_rows),
            "new_strong_signal_ids": [key(x) for x in new_rows],
            "existing_or_deduplicated_strong_signals": len(strong_after)
            - len(new_rows),
            "duplicate_public_ids": duplicated_ids,
            "active_strong_signals": len(active_rows),
            "history_strong_signals": len(history),
            "new_classification_events": len(new_events),
            "new_classification_event_ids": [
                str(x.get("event_id")) for x in new_events
            ],
            "public_near_misses_total": len(near),
        },
        "reconciliation": {
            "dataset_delta_equals_new_strong_signals": (len(after) - len(before))
            == len(new_rows),
            "new_ids_unique": len(new_ids) == len(set(new_ids)),
            "public_ids_unique": not duplicated_ids,
            "active_status_contract": all(active(x) for x in active_rows),
            "history_excludes_pending": all(not active(x) for x in history),
            "no_new_signal_id_missing_from_public": all(
                key(x) in after_ids for x in new_rows
            ),
            "strong_records_are_isolated": all(
                x.get("virtual_portfolio") == "STRONG_SIGNALS_VIRTUAL"
                and x.get("not_a_production_bet") is True
                for x in strong_after
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="strong_signal_run_evidence.json")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    evidence = build_evidence(root)
    (root / args.output).write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
