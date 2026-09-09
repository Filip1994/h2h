from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import Settings
from .quota import GlobalQuotaExceeded, GlobalQuotaGovernor


class APIError(RuntimeError):
    pass


class APIBudgetExceeded(APIError):
    pass


class APIFootballClient:
    ARCHIVE_SCHEMA_VERSION = 1

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.request_count = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.rate_limit_events = 0
        self.retry_events = 0
        self.budget_exhaustion_events = 0
        self.http_errors: Counter[str] = Counter()
        self.api_error_events = 0
        self.network_error_events = 0
        self.endpoint_requests: Counter[str] = Counter()
        self.endpoint_cache_hits: Counter[str] = Counter()
        self.settings.cache_dir.mkdir(parents=True, exist_ok=True)
        self.settings.root.joinpath("data", "raw_api").mkdir(
            parents=True, exist_ok=True
        )
        self.quota = GlobalQuotaGovernor(
            self.settings.root / "data" / "football_api_quota.json",
            self.settings.api_request_budget,
            self.settings.api_budget_reserve,
        )

    def _archive_path(self, captured_at: datetime) -> Path:
        return (
            self.settings.root
            / "data"
            / "raw_api"
            / f"{captured_at.astimezone(UTC).date().isoformat()}.jsonl"
        )

    def _archive_response(
        self,
        endpoint: str,
        params: dict[str, Any],
        payload: dict[str, Any],
        captured_at: datetime,
        request_url: str,
    ) -> None:
        record = {
            "schema_version": self.ARCHIVE_SCHEMA_VERSION,
            "captured_at": captured_at.astimezone(UTC).isoformat(),
            "endpoint": endpoint,
            "params": params,
            "request_url": request_url,
            "request_count": self.request_count,
            "github_run_id": os.getenv("GITHUB_RUN_ID"),
            "github_workflow": os.getenv("GITHUB_WORKFLOW"),
            "github_sha": os.getenv("GITHUB_SHA"),
            "payload": payload,
        }
        path = self._archive_path(captured_at)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())

    def _cache_path(self, endpoint: str, params: dict[str, Any]) -> Path:
        canonical = json.dumps(
            [endpoint, sorted(params.items())], ensure_ascii=True, separators=(",", ":")
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return self.settings.cache_dir / f"{digest}.json"

    def _read_cache(self, path: Path) -> list[dict[str, Any]] | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if float(payload["expires_at"]) <= time.time():
                return None
            response = payload["response"]
            return response if isinstance(response, list) else None
        except (
            FileNotFoundError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            return None

    def _write_cache(
        self, path: Path, response: list[dict[str, Any]], ttl_seconds: int
    ) -> None:
        if ttl_seconds <= 0:
            return
        payload = {"expires_at": time.time() + ttl_seconds, "response": response}
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        *,
        ttl_seconds: int = 0,
        reserve_protected: bool = False,
    ) -> list[dict[str, Any]]:
        params = {
            key: value for key, value in (params or {}).items() if value is not None
        }
        cache_path = self._cache_path(endpoint, params)
        cached = self._read_cache(cache_path)
        if cached is not None:
            self.cache_hits += 1
            self.endpoint_cache_hits[endpoint] += 1
            return cached
        self.cache_misses += 1

        query = urlencode(params)
        url = f"{self.settings.api_base_url}/{endpoint.lstrip('/')}"
        if query:
            url = f"{url}?{query}"
        if not self.settings.api_key:
            raise APIError("API_FOOTBALL_KEY nije podešen")

        raw = ""
        for attempt in range(self.settings.api_max_attempts):
            usable_budget = self.settings.api_request_budget - (
                0 if reserve_protected else self.settings.api_budget_reserve
            )
            if self.request_count >= usable_budget:
                self.budget_exhaustion_events += 1
                raise APIBudgetExceeded(
                    "Run je dostigao API radni budžet od "
                    f"{usable_budget} zahteva; rezerva={self.settings.api_budget_reserve}"
                )
            workflow = (
                os.getenv("GITHUB_WORKFLOW") or os.getenv("GITHUB_JOB") or "local"
            )
            try:
                reservation_id = self.quota.reserve(
                    workflow, endpoint, "GET", protected=reserve_protected
                )
            except GlobalQuotaExceeded as exc:
                self.budget_exhaustion_events += 1
                raise APIBudgetExceeded(str(exc)) from exc

            # The provider request is now chargeable. Mark it consumed before
            # network I/O so a process crash/timeout cannot leave an uncharged
            # reservation and make the global ledger under-report usage.
            self.quota.consume(reservation_id)
            request = Request(
                url,
                headers={
                    "x-apisports-key": self.settings.api_key,
                    "Accept": "application/json",
                },
                method="GET",
            )
            self.request_count += 1
            self.endpoint_requests[endpoint] += 1
            try:
                with urlopen(request, timeout=20) as response:
                    raw = response.read().decode("utf-8")
                break
            except HTTPError as exc:
                self.http_errors[str(exc.code)] += 1
                if exc.code == 429:
                    self.rate_limit_events += 1
                retryable = exc.code == 429 or 500 <= exc.code <= 599
                if retryable and attempt + 1 < self.settings.api_max_attempts:
                    self.retry_events += 1
                    headers = exc.headers or {}
                    self._retry_delay(attempt, headers.get("Retry-After"))
                    continue
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                raise APIError(f"API HTTP {exc.code} za {endpoint}: {detail}") from exc
            except (URLError, TimeoutError) as exc:
                self.network_error_events += 1
                if attempt + 1 < self.settings.api_max_attempts:
                    self.retry_events += 1
                    self._retry_delay(attempt)
                    continue
                reason = getattr(exc, "reason", str(exc))
                raise APIError(f"API mrežna greška za {endpoint}: {reason}") from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            self.api_error_events += 1
            raise APIError(f"API nije vratio validan JSON za {endpoint}") from exc

        errors = payload.get("errors")
        if errors:
            self.api_error_events += 1
            raise APIError(f"API greška za endpoint {endpoint}: {errors}")
        result = payload.get("response")
        if not isinstance(result, list):
            self.api_error_events += 1
            raise APIError(f"Neočekivan API odgovor za endpoint {endpoint}")

        captured_at = datetime.now(UTC)
        self._archive_response(endpoint, params, payload, captured_at, url)
        self._write_cache(cache_path, result, ttl_seconds)
        return result

    def usage_snapshot(self) -> dict[str, Any]:
        return {
            "request_count": self.request_count,
            "request_budget": self.settings.api_request_budget,
            "working_budget": self.settings.api_request_budget
            - self.settings.api_budget_reserve,
            "reserve": self.settings.api_budget_reserve,
            "remaining_working": max(
                0,
                self.settings.api_request_budget
                - self.settings.api_budget_reserve
                - self.request_count,
            ),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate": round(
                self.cache_hits / max(1, self.cache_hits + self.cache_misses), 6
            ),
            "rate_limit_events": self.rate_limit_events,
            "retry_events": self.retry_events,
            "budget_exhaustion_events": self.budget_exhaustion_events,
            "http_errors": dict(sorted(self.http_errors.items())),
            "api_error_events": self.api_error_events,
            "network_error_events": self.network_error_events,
            "endpoint_requests": dict(sorted(self.endpoint_requests.items())),
            "endpoint_cache_hits": dict(sorted(self.endpoint_cache_hits.items())),
            "global_quota": self.quota.snapshot(),
        }

    def _retry_delay(self, attempt: int, retry_after: str | None = None) -> None:
        delay = self.settings.api_retry_base_seconds * (2**attempt)
        if retry_after:
            try:
                delay = max(delay, float(retry_after))
            except ValueError:
                pass
        time.sleep(min(delay, 30.0))

    def fixtures_by_date(self, date_iso: str) -> list[dict[str, Any]]:
        return self.get(
            "fixtures",
            {"date": date_iso, "timezone": self.settings.timezone_name},
            ttl_seconds=600,
        )

    def fixture(self, fixture_id: int) -> list[dict[str, Any]]:
        return self.get("fixtures", {"id": fixture_id}, ttl_seconds=300)

    def league_season_fixtures(
        self, league_id: int, season: int
    ) -> list[dict[str, Any]]:
        return self.get(
            "fixtures", {"league": league_id, "season": season, "status": "FT"}, ttl_seconds=21_600
        )

    def odds(self, fixture_id: int) -> list[dict[str, Any]]:
        return self.get("odds", {"fixture": fixture_id}, ttl_seconds=120)
