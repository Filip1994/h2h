from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .types import BLOCKING_STATUSES


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


class BetStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"{self.path} nije validan JSON; odbijam da prepišem ledger"
            ) from exc
        if not isinstance(payload, list):
            raise TypeError(f"{self.path} mora sadržati JSON listu")
        if any(not isinstance(item, dict) for item in payload):
            raise TypeError(
                f"{self.path} sadrži nevalidan zapis; odbijam da menjam ledger"
            )
        return payload

    def save(self, bets: list[dict[str, Any]]) -> None:
        atomic_write_json(self.path, bets)

    @staticmethod
    def blocked_fixture_ids(bets: list[dict[str, Any]]) -> set[int]:
        blocked: set[int] = set()
        for bet in bets:
            if str(bet.get("status", "")).upper() not in BLOCKING_STATUSES:
                continue
            fixture_id = bet.get("event_id")
            if fixture_id is not None:
                blocked.add(int(fixture_id))
        return blocked

    def append_unique_fixtures(
        self, new_bets: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        bets = self.load()
        blocked = self.blocked_fixture_ids(bets)
        appended: list[dict[str, Any]] = []
        for bet in new_bets:
            fixture_id = int(bet["event_id"])
            if fixture_id in blocked:
                continue
            bets.append(bet)
            appended.append(bet)
            blocked.add(fixture_id)
        if appended:
            self.save(bets)
        return appended

    def update(self, mutator: Callable[[list[dict[str, Any]]], bool]) -> bool:
        bets = self.load()
        changed = mutator(bets)
        if changed:
            self.save(bets)
        return changed


class PredictionStore(BetStore):
    def append_unique(self, new_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        records = self.load()
        existing = {str(record.get("id")): record for record in records}
        appended: list[dict[str, Any]] = []
        changed = False
        for record in new_records:
            record_id = str(record["id"])
            if record_id in existing:
                current = existing[record_id]
                if (
                    record.get("selected") is True
                    and current.get("selected") is not True
                    and current.get("status") == "PENDING"
                ):
                    current.update(record)
                    changed = True
                continue
            records.append(record)
            appended.append(record)
            existing[record_id] = record
            changed = True
        if changed:
            self.save(records)
        return appended
