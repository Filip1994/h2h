from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class BaseballSettings:
    """Baseball-only settings; keeps Football configuration untouched."""

    api_key: str
    api_base_url: str
    api_request_budget: int
    api_max_attempts: int
    api_retry_base_seconds: float
    cache_dir: Path
    timezone_name: str
    paper_mode: bool

    @classmethod
    def from_env(cls, root: Path) -> "BaseballSettings":
        def integer(name: str, default: int) -> int:
            return int(os.getenv(name, str(default)).strip())

        def floating(name: str, default: float) -> float:
            return float(os.getenv(name, str(default)).strip())

        return cls(
            api_key=os.getenv("API_BASEBALL_KEY", "").strip(),
            api_base_url=os.getenv(
                "API_BASEBALL_BASE_URL", "https://v1.baseball.api-sports.io"
            ).rstrip("/"),
            api_request_budget=integer("BASEBALL_API_REQUEST_BUDGET", 7500),
            api_max_attempts=integer("BASEBALL_API_MAX_ATTEMPTS", 3),
            api_retry_base_seconds=floating("BASEBALL_API_RETRY_BASE_SECONDS", 1.0),
            cache_dir=root / ".cache" / "baseball-api",
            timezone_name=os.getenv("TIMEZONE", "Europe/Belgrade").strip(),
            paper_mode=os.getenv("PAPER_MODE", "true").strip().lower() in {"1", "true", "yes", "on"},
        )

    def validate(self) -> None:
        if self.api_request_budget < 1:
            raise ValueError("BASEBALL_API_REQUEST_BUDGET must be positive")
        if self.api_max_attempts < 1:
            raise ValueError("BASEBALL_API_MAX_ATTEMPTS must be at least 1")
        if not 0.0 <= self.api_retry_base_seconds <= 30.0:
            raise ValueError("BASEBALL_API_RETRY_BASE_SECONDS must be between 0 and 30")
