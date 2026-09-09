from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from quantbot.config import Settings
from tools.bookmaker_inventory import (
    build_report,
    extract_observed_bookmakers,
    normalize_catalogue,
    write_report,
)


def test_normalize_catalogue_preserves_identity_and_sorts() -> None:
    rows = [
        {"id": "11", "name": "Beta", "country": "World"},
        {"id": 8, "name": "Alpha", "code": "ALP"},
        {"id": None, "name": "Invalid"},
        {"id": 9, "name": ""},
    ]
    assert normalize_catalogue(rows) == [
        {"id": 8, "name": "Alpha", "code": "ALP"},
        {"id": 11, "name": "Beta", "country": "World"},
    ]


def test_extract_observed_bookmakers_deduplicates_exact_ids() -> None:
    rows = [
        {"id": 11, "name": "Beta"},
        {"id": "8", "name": "Alpha"},
        {"id": 11, "name": "Beta", "country": "World"},
    ]
    assert extract_observed_bookmakers(rows) == [
        {"id": 8, "name": "Alpha"},
        {"id": 11, "name": "Beta", "country": "World"},
    ]


def test_write_report_is_human_and_csv_friendly(tmp_path: Path) -> None:
    settings = Settings.from_env(tmp_path)
    report = build_report(
        [{"id": 8, "name": "Alpha"}, {"id": 11, "name": "Beta"}],
        [{"id": 11, "name": "Beta"}],
        started_at=datetime(2026, 9, 10, tzinfo=UTC),
        completed_at=datetime(2026, 9, 10, 0, 1, tzinfo=UTC),
        settings=settings,
        observation_window_hours=24,
    )
    json_path, csv_path = write_report(report, tmp_path / "out")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["catalogue"]["count"] == 2
    assert payload["catalogue"]["bookmakers"][0]["id"] == 8
    assert payload["fixture_odds_observed"]["bookmakers"] == [{"id": 11, "name": "Beta"}]
    csv_text = csv_path.read_text(encoding="utf-8")
    assert "id,name" in csv_text
    assert "8,Alpha" in csv_text
