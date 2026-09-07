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

from .config import BaseballSettings


class BaseballAPIError(RuntimeError):
    pass


class BaseballAPIBudgetExceeded(BaseballAPIError):
    pass


class BaseballAPIClient:
    """API-Sports Baseball client with persistent cache and per-run budget."""

    def __init__(self, settings: BaseballSettings) -> None:
        settings.validate()
        self.settings = settings
        self.request_count = 0
        self.cache_hits = 0
        self.settings.cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def remaining_budget(self) -> int:
        return max(0, self.settings.api_request_budget - self.request_count)

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
            if isinstance(response, list):
                self.cache_hits += 1
                return response
        except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None
        return None

    def _write_cache(self, path: Path, response: list[dict[str, Any]], ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        payload = {"expires_at": time.time() + ttl_seconds, "response": response}
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
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
        params = {key: value for key, value in (params or {}).items() if value is not None}
        cache_path = self._cache_path(endpoint, params)
        cached = self._read_cache(cache_path)
        if cached is not None:
            return cached

        if not self.settings.api_key:
            raise BaseballAPIError("API_BASEBALL_KEY is not configured")
        if self.request_count >= self.settings.api_request_budget:
            raise BaseballAPIBudgetExceeded(
                f"Baseball API budget exhausted at {self.settings.api_request_budget} requests"
            )

        query = urlencode(params)
        url = f"{self.settings.api_base_url}/{endpoint.lstrip('/')}"
        if query:
            url = f"{url}?{query}"

        raw = ""
        for attempt in range(self.settings.api_max_attempts):
            if self.request_count >= self.settings.api_request_budget:
                raise BaseballAPIBudgetExceeded(
                    f"Baseball API budget exhausted at {self.settings.api_request_budget} requests"
                )
            request = Request(
                url,
                headers={"x-apisports-key": self.settings.api_key, "Accept": "application/json"},
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
                    retry_after = (exc.headers or {}).get("Retry-After")
                    self._retry_delay(attempt, retry_after)
                    continue
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                raise BaseballAPIError(f"API HTTP {exc.code} for {endpoint}: {detail}") from exc
            except (URLError, TimeoutError) as exc:
                if attempt + 1 < self.settings.api_max_attempts:
                    self._retry_delay(attempt)
                    continue
                reason = getattr(exc, "reason", str(exc))
                raise BaseballAPIError(f"API network error for {endpoint}: {reason}") from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BaseballAPIError(f"API returned invalid JSON for {endpoint}") from exc

        errors = payload.get("errors")
        if errors:
            raise BaseballAPIError(f"API error for {endpoint}: {errors}")
        result = payload.get("response")
        if not isinstance(result, list):
            raise BaseballAPIError(f"Unexpected API response for {endpoint}")

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

    def games_by_date(self, date_iso: str) -> list[dict[str, Any]]:
        return self.get("games", {"date": date_iso}, ttl_seconds=300)

    def game(self, game_id: int) -> list[dict[str, Any]]:
        return self.get("games", {"id": game_id}, ttl_seconds=120)

    def games_by_league_season(self, league_id: int, season: int) -> list[dict[str, Any]]:
        return self.get("games", {"league": league_id, "season": season}, ttl_seconds=21_600)

    def standings(self, league_id: int, season: int) -> list[dict[str, Any]]:
        return self.get("standings", {"league": league_id, "season": season}, ttl_seconds=21_600)

    def team_statistics(self, team_id: int, league_id: int, season: int) -> list[dict[str, Any]]:
        return self.get(
            "teams/statistics",
            {"team": team_id, "league": league_id, "season": season},
            ttl_seconds=86_400,
        )

    def player_statistics(self, player_id: int, season: int) -> list[dict[str, Any]]:
        return self.get("players/statistics", {"id": player_id, "season": season}, ttl_seconds=86_400)

    def odds(self, game_id: int) -> list[dict[str, Any]]:
        return self.get("odds", {"game": game_id}, ttl_seconds=120)
