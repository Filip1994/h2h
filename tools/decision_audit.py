from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUDIT_FILE = ROOT / "audit" / "decision_audit.jsonl"
SOURCES = (
    ("PREDICTION", ROOT / "predictions.json"),
    ("BET", ROOT / "bets.json"),
)


def _load_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise TypeError(f"{path} mora sadržati JSON listu")
    return [item for item in payload if isinstance(item, dict)]


def _canonical(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _event_key(kind: str, record: dict[str, Any]) -> str:
    record_id = str(record.get("id") or record.get("event_id") or "")
    digest = hashlib.sha256(_canonical(record).encode("utf-8")).hexdigest()
    return f"{kind}:{record_id}:{digest}"


def _existing_keys() -> set[str]:
    if not AUDIT_FILE.exists():
        return set()
    keys: set[str] = set()
    with AUDIT_FILE.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and event.get("event_key"):
                keys.add(str(event["event_key"]))
    return keys


def append_current_state() -> int:
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    known = _existing_keys()
    now = datetime.now(UTC).isoformat()
    appended = 0
    with AUDIT_FILE.open("a", encoding="utf-8") as handle:
        for kind, path in SOURCES:
            for record in _load_json(path):
                event_key = _event_key(kind, record)
                if event_key in known:
                    continue
                event = {
                    "event_key": event_key,
                    "event_type": kind,
                    "captured_at": now,
                    "record": record,
                }
                handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
                known.add(event_key)
                appended += 1
    return appended


if __name__ == "__main__":
    print(f"Decision audit events appended: {append_current_state()}")
