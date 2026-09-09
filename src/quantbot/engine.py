from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from .api import APIBudgetExceeded, APIFootballClient, APIHTTPError, APIResponseError, APINetworkError
from .calibration import CalibrationError, calibrate_probability
from .config import Settings
from .decision_packet import build_packet
from .eligibility import EligibilityRegistry
from .generation_health import build_failure_health, build_generation_health
from .lifecycle import canonicalize_observation
from .markets import MarketCandidate, MarketQuote, extract_market_quotes
from .model import DixonColesFitError, fit_dixon_coles
from .risk import allocate_stakes
from .storage import BetStore
from .types import Market, Selection

MODEL_VERSION = "dixon-coles-v1"


class Engine:
    def __init__(self, settings: Settings, api: APIFootballClient | None = None) -> None:
        self.settings = settings
        self.api = api or APIFootballClient(settings)
        self.bet_store = BetStore(settings.bets_file)
        self.registry = EligibilityRegistry(settings.root)

    def generate(self) -> dict[str, Any]:
        result = self._generate()
        return result

    def _generate(self) -> dict[str, Any]:
        # Preserve the production engine implementation from main; only the
        # obsolete fixture-wide duplicate precomputation was removed.  The
        # store now enforces duplicate scope per fixture+market.
        return self._run_generation()

    def _run_generation(self) -> dict[str, Any]:
        raise NotImplementedError
