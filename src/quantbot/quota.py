from __future__ import annotations

import fcntl
import json
import os
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class GlobalQuotaExceeded(RuntimeError):
    """Raised when a request would breach the protected daily provider reserve."""


class GlobalQuotaStateError(RuntimeError):
    """Raised when the canonical daily quota ledger is missing or inconsistent."""


class GlobalQuotaGovernor:
    SCHEMA_VERSION = 1
    RESERVATION_TTL_SECONDS = 7200

    def __init__(self, path: Path, daily_capacity: int, safety_reserve: int) -> None:
        self.path = path
        self.daily_capacity = max(0, int(daily_capacity))
        self.safety_reserve = max(0, int(safety_reserve))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def _lock(self):
        handle = self.lock_path.open("a+")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return handle

    def _new_day(self, today: str) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "date": today,
            "daily_capacity": self.daily_capacity,
            "safety_reserve": self.safety_reserve,
            "consumed": 0,
            "reserved": 0,
            "consumed_by_workflow": {},
            "reserved_by_workflow": {},
            "requests": [],
        }

    def _validate_existing(self, payload: dict[str, Any], today: str) -> None:
        required = {
            "schema_version",
            "date",
            "daily_capacity",
            "safety_reserve",
            "consumed",
            "reserved",
            "consumed_by_workflow",
            "reserved_by_workflow",
            "requests",
        }
        if not required.issubset(payload):
            raise GlobalQuotaStateError(
                "GLOBAL_QUOTA_STATE_INVALID: missing ledger fields"
            )
        if payload["schema_version"] != self.SCHEMA_VERSION:
            raise GlobalQuotaStateError(
                "GLOBAL_QUOTA_STATE_INVALID: unsupported schema"
            )
        if payload["date"] != today:
            return
        if int(payload["daily_capacity"]) != self.daily_capacity:
            raise GlobalQuotaStateError(
                "GLOBAL_QUOTA_CONFIG_MISMATCH: daily capacity differs from canonical ledger"
            )
        if int(payload["safety_reserve"]) != self.safety_reserve:
            raise GlobalQuotaStateError(
                "GLOBAL_QUOTA_CONFIG_MISMATCH: safety reserve differs from canonical ledger"
            )
        if int(payload["consumed"]) < 0 or int(payload["reserved"]) < 0:
            raise GlobalQuotaStateError("GLOBAL_QUOTA_STATE_INVALID: negative totals")
        if int(payload["consumed"]) + int(payload["reserved"]) > int(
            payload["daily_capacity"]
        ):
            raise GlobalQuotaStateError(
                "GLOBAL_QUOTA_STATE_INVALID: totals exceed capacity"
            )
        if not isinstance(payload["requests"], list):
            raise GlobalQuotaStateError(
                "GLOBAL_QUOTA_STATE_INVALID: requests is not a list"
            )

    def _load(self) -> dict[str, Any]:
        today = datetime.now(UTC).date().isoformat()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            payload = self._new_day(today)
        except (json.JSONDecodeError, OSError) as exc:
            raise GlobalQuotaStateError(
                "GLOBAL_QUOTA_STATE_INVALID: unreadable ledger"
            ) from exc
        if not isinstance(payload, dict):
            raise GlobalQuotaStateError(
                "GLOBAL_QUOTA_STATE_INVALID: ledger is not an object"
            )
        self._validate_existing(payload, today)
        if payload.get("date") != today:
            payload = self._new_day(today)
        now = time.time()
        active = []
        expired = 0
        for item in payload.get("requests", []):
            if (
                item.get("status") == "reserved"
                and now - float(item.get("timestamp_epoch", now))
                > self.RESERVATION_TTL_SECONDS
            ):
                item["status"] = "expired"
                expired += 1
                workflow = str(item.get("workflow", "unknown"))
                payload["reserved"] = max(0, int(payload.get("reserved", 0)) - 1)
                rbw = payload.setdefault("reserved_by_workflow", {})
                rbw[workflow] = max(0, int(rbw.get(workflow, 0)) - 1)
            active.append(item)
        payload["requests"] = active
        if expired:
            self._save_unlocked(payload)
        return payload

    def _save_unlocked(self, payload: dict[str, Any]) -> None:
        fd, name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(
                    payload,
                    handle,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def reserve(
        self,
        workflow: str,
        endpoint: str,
        request_type: str = "GET",
        *,
        protected: bool = False,
    ) -> str:
        cost = 1
        lock = self._lock()
        try:
            payload = self._load()
            available = (
                int(payload["daily_capacity"])
                - int(payload["consumed"])
                - int(payload["reserved"])
            )
            floor = 0 if protected else int(payload["safety_reserve"])
            if available < cost + floor:
                raise GlobalQuotaExceeded(
                    f"GLOBAL_QUOTA_PRESSURE: available={available}, reserve={floor}, workflow={workflow}, endpoint={endpoint}"
                )
            reservation_id = uuid.uuid4().hex
            now = datetime.now(UTC)
            payload["reserved"] += cost
            payload.setdefault("reserved_by_workflow", {})[workflow] = (
                payload.setdefault("reserved_by_workflow", {}).get(workflow, 0) + cost
            )
            payload.setdefault("requests", []).append(
                {
                    "reservation_id": reservation_id,
                    "timestamp": now.isoformat(),
                    "timestamp_epoch": time.time(),
                    "workflow": workflow,
                    "endpoint": endpoint,
                    "request_type": request_type,
                    "cost": cost,
                    "status": "reserved",
                }
            )
            self._save_unlocked(payload)
            return reservation_id
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()

    def consume(self, reservation_id: str) -> None:
        lock = self._lock()
        try:
            payload = self._load()
            for item in payload.get("requests", []):
                if (
                    item.get("reservation_id") != reservation_id
                    or item.get("status") != "reserved"
                ):
                    continue
                cost = int(item.get("cost", 1))
                workflow = str(item.get("workflow", "unknown"))
                item["status"] = "consumed"
                payload["reserved"] = max(0, int(payload["reserved"]) - cost)
                payload["consumed"] = int(payload["consumed"]) + cost
                rbw = payload.setdefault("reserved_by_workflow", {})
                rbw[workflow] = max(0, int(rbw.get(workflow, 0)) - cost)
                cbw = payload.setdefault("consumed_by_workflow", {})
                cbw[workflow] = int(cbw.get(workflow, 0)) + cost
                self._save_unlocked(payload)
                return
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()

    def snapshot(self) -> dict[str, Any]:
        lock = self._lock()
        try:
            payload = self._load()
            remaining = max(
                0,
                int(payload["daily_capacity"])
                - int(payload["consumed"])
                - int(payload["reserved"]),
            )
            if remaining <= 0:
                state = "RESERVE_EXHAUSTED"
            elif remaining <= int(payload["safety_reserve"]):
                state = "RESERVE_PRESSURE"
            else:
                state = "HEALTHY"
            return {
                "date": payload["date"],
                "daily_capacity": int(payload["daily_capacity"]),
                "safety_reserve": int(payload["safety_reserve"]),
                "consumed": int(payload["consumed"]),
                "reserved": int(payload["reserved"]),
                "remaining_unallocated": remaining,
                "consumed_by_workflow": dict(
                    sorted(payload.get("consumed_by_workflow", {}).items())
                ),
                "reserved_by_workflow": dict(
                    sorted(payload.get("reserved_by_workflow", {}).items())
                ),
                "quota_pressure_state": state,
                "request_count": len(payload.get("requests", [])),
            }
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()
