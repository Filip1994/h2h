from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "audit"
AUDIT_FILE = AUDIT_DIR / "decision_audit.jsonl"
STATE_FILE = AUDIT_DIR / "decision_audit_state.json"
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


def _record_key(kind: str, record: dict[str, Any]) -> str:
    record_id = str(record.get("id") or record.get("event_id") or "")
    return f"{kind}:{record_id}"


def _state_hash(record: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(record).encode("utf-8")).hexdigest()


def _load_state() -> dict[str, str]:
    if not STATE_FILE.exists():
        return {}
    try:
        payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_state(state: dict[str, str]) -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def append_current_state() -> int:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    state = _load_state()
    now = datetime.now(UTC).isoformat()
    appended = 0
    with AUDIT_FILE.open("a", encoding="utf-8") as handle:
        for kind, path in SOURCES:
            for record in _load_json(path):
                record_key = _record_key(kind, record)
                digest = _state_hash(record)
                if state.get(record_key) == digest:
                    continue
                event = {
                    "event_key": f"{record_key}:{digest}",
                    "event_type": kind,
                    "captured_at": now,
                    "record": record,
                }
                handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
                state[record_key] = digest
                appended += 1
    _save_state(state)
    return appended


if __name__ == "__main__":
    print(f"Decision audit events appended: {append_current_state()}")
