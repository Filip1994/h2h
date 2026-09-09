from __future__ import annotations

import argparse
import csv
import json
import os
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quantbot.api import APIFootballClient
from quantbot.config import Settings

SCHEMA_VERSION = 1


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_catalogue(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize /odds/bookmakers rows without filtering by geography or policy."""
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        bookmaker_id = _as_int(row.get("id"))
        name = row.get("name")
        if bookmaker_id is None or not isinstance(name, str) or not name.strip():
            continue
        item = {"id": bookmaker_id, "name": name.strip()}
        for key in ("country", "code", "region", "logo"):
            value = row.get(key)
            if value not in (None, ""):
                item[key] = value
        normalized.append(item)
    return sorted(normalized, key=lambda item: (item["id"], item["name"].casefold()))


def extract_observed_bookmakers(
    odds_rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract exact bookmaker identities from fixture /odds response rows."""
    seen: dict[int, dict[str, Any]] = {}
    for row in odds_rows:
        if not isinstance(row, dict):
            continue
        bookmaker_id = _as_int(row.get("id"))
        name = row.get("name")
        if bookmaker_id is None or not isinstance(name, str) or not name.strip():
            continue
        item = {"id": bookmaker_id, "name": name.strip()}
        for key in ("country", "logo"):
            value = row.get(key)
            if value not in (None, ""):
                item[key] = value
        seen[bookmaker_id] = item
    return [seen[key] for key in sorted(seen)]


def _iter_archived_odds(root: Path, since: datetime) -> Iterable[dict[str, Any]]:
    archive_dir = root / "data" / "raw_api"
    if not archive_dir.exists():
        return
    for path in sorted(archive_dir.glob("*.jsonl")):
        try:
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    captured = record.get("captured_at")
                    if not isinstance(captured, str):
                        continue
                    try:
                        captured_at = datetime.fromisoformat(captured)
                    except ValueError:
                        continue
                    if captured_at < since or record.get("endpoint") != "odds":
                        continue
                    payload = record.get("payload", {})
                    response = (
                        payload.get("response", []) if isinstance(payload, dict) else []
                    )
                    for fixture in response if isinstance(response, list) else []:
                        bookmakers = (
                            fixture.get("bookmakers", [])
                            if isinstance(fixture, dict)
                            else []
                        )
                        for bookmaker in (
                            bookmakers if isinstance(bookmakers, list) else []
                        ):
                            if isinstance(bookmaker, dict):
                                yield bookmaker
        except OSError:
            continue


def build_report(
    catalogue: list[dict[str, Any]],
    observed: list[dict[str, Any]],
    *,
    started_at: datetime,
    completed_at: datetime,
    settings: Settings,
    observation_window_hours: int,
) -> dict[str, Any]:
    observed_ids = {row["id"] for row in observed}
    return {
        "schema_version": SCHEMA_VERSION,
        "report_type": "api_football_bookmaker_inventory",
        "generated_at": completed_at.astimezone(UTC).isoformat(),
        "started_at": started_at.astimezone(UTC).isoformat(),
        "api": {
            "base_url": settings.api_base_url,
            "endpoint": "odds/bookmakers",
            "account_scope": "configured API credentials",
            "request_source": "live API response",
        },
        "policy": {
            "filtered": False,
            "geography_filter": None,
            "licensing_filter": None,
            "production_bookmaker_policy_applied": False,
        },
        "catalogue": {
            "count": len(catalogue),
            "bookmakers": catalogue,
        },
        "fixture_odds_observed": {
            "count": len(observed),
            "observation_window_hours": observation_window_hours,
            "source": "persisted API odds archive generated during the diagnostic window",
            "bookmakers": observed,
        },
        "catalogue_not_observed_in_window": [
            row for row in catalogue if row["id"] not in observed_ids
        ],
        "runtime": {
            "github_run_id": os.getenv("GITHUB_RUN_ID"),
            "github_workflow": os.getenv("GITHUB_WORKFLOW"),
            "github_sha": os.getenv("GITHUB_SHA"),
        },
    }


def write_report(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "bookmaker_inventory.json"
    csv_path = output_dir / "bookmaker_inventory.csv"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "id",
                "name",
                "country",
                "code",
                "region",
                "logo",
                "catalogue",
                "observed_in_fixture_odds",
            ],
        )
        writer.writeheader()
        observed_ids = {
            row["id"] for row in report["fixture_odds_observed"]["bookmakers"]
        }
        for row in report["catalogue"]["bookmakers"]:
            writer.writerow(
                {
                    **{
                        key: row.get(key, "")
                        for key in ("id", "name", "country", "code", "region", "logo")
                    },
                    "catalogue": True,
                    "observed_in_fixture_odds": row["id"] in observed_ids,
                }
            )
    return json_path, csv_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a complete API-Football bookmaker inventory."
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("diagnostics/bookmakers")
    )
    parser.add_argument("--observation-window-hours", type=int, default=24)
    args = parser.parse_args()
    if args.observation_window_hours < 0:
        raise SystemExit("--observation-window-hours mora biti >= 0")

    started_at = datetime.now(UTC)
    settings = Settings.from_env()
    client = APIFootballClient(settings)
    catalogue = normalize_catalogue(client.get("odds/bookmakers"))
    if not catalogue:
        raise RuntimeError(
            "API /odds/bookmakers je vratio prazan ili nevalidan katalog"
        )
    window_start = started_at
    observed = extract_observed_bookmakers(
        _iter_archived_odds(settings.root, window_start)
    )
    completed_at = datetime.now(UTC)
    report = build_report(
        catalogue,
        observed,
        started_at=started_at,
        completed_at=completed_at,
        settings=settings,
        observation_window_hours=args.observation_window_hours,
    )
    json_path, csv_path = write_report(report, args.output_dir)
    print(f"Bookmaker catalogue: {len(catalogue)}")
    print(f"Fixture /odds bookmakers observed in diagnostic window: {len(observed)}")
    print(f"JSON artifact: {json_path}")
    print(f"CSV artifact: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
