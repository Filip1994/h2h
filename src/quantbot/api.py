from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import Settings


class APIError(RuntimeError):
    pass


class APIBudgetExceeded(APIError):
    pass


class APIFootballClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.request_count = 0
        self.settings.cache_dir.mkdir(parents=True, exist_ok=True)

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
    ) -> list[dict[str, Any]]:
        params = {
            key: value for key, value in (params or {}).items() if value is not None
        }
        cache_path = self._cache_path(endpoint, params)
        cached = self._read_cache(cache_path)
        if cached is not None:
            return cached

        query = urlencode(params)
        url = f"{self.settings.api_base_url}/{endpoint.lstrip('/')}"
        if query:
            url = f"{url}?{query}"
        if not self.settings.api_key:
            raise APIError("API_FOOTBALL_KEY nije podešen")

        raw = ""
        for attempt in range(self.settings.api_max_attempts):
            if self.request_count >= self.settings.api_request_budget:
                raise APIBudgetExceeded(
                    "Run je dostigao API budžet od "
                    f"{self.settings.api_request_budget} zahteva"
                )
            request = Request(
                url,
                headers={
                    "x-apisports-key": self.settings.api_key,
                    "Accept": "application/json",
                },
                method="GET",
            )
            self.request_count += 1
            try:
                with urlopen(request, timeout=20) as response:
                    raw = response.read().decode("utf-8")
                break
            except HTTPError as exc:
                retryable = exc.code == 429 or 500 <= exc.code <= 599
                if retryable and attempt + 1 < self.settings.api_max_attempts:
                    headers = exc.headers or {}
                    self._retry_delay(attempt, headers.get("Retry-After"))
                    continue
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                raise APIError(f"API HTTP {exc.code} za {endpoint}: {detail}") from exc
            except (URLError, TimeoutError) as exc:
                if attempt + 1 < self.settings.api_max_attempts:
                    self._retry_delay(attempt)
                    continue
                reason = getattr(exc, "reason", str(exc))
                raise APIError(f"API mrežna greška za {endpoint}: {reason}") from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise APIError(f"API nije vratio validan JSON za {endpoint}") from exc

        errors = payload.get("errors")
        if errors:
            raise APIError(f"API greška za {endpoint}: {errors}")
        result = payload.get("response")
        if not isinstance(result, list):
            raise APIError(f"Neočekivan API odgovor za {endpoint}")

        self._write_cache(cache_path, result, ttl_seconds)
        return result

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

    def head_to_head(self, home_id: int, away_id: int) -> list[dict[str, Any]]:
        return self.get(
            "fixtures/headtohead",
            {"h2h": f"{home_id}-{away_id}"},
            ttl_seconds=43_200,
        )

    def league_season_fixtures(
        self, league_id: int, season: int
    ) -> list[dict[str, Any]]:
        return self.get(
            "fixtures",
            {"league": league_id, "season": season, "status": "FT"},
            ttl_seconds=21_600,
        )

    def odds(self, fixture_id: int) -> list[dict[str, Any]]:
        return self.get("odds", {"fixture": fixture_id}, ttl_seconds=120)
