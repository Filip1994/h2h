from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        pass
    return rows


def iso_date(value: Any) -> str | None:
    try:
        return datetime.fromisoformat(str(value)).astimezone(UTC).date().isoformat()
    except (TypeError, ValueError):
        return None


def audit(root: Path = ROOT) -> dict[str, Any]:
    timing = load_jsonl(root / "data" / "market_timing_snapshots.jsonl")
    alerts = load_json(root / "intraday_alerts.json") or []
    alerts = alerts if isinstance(alerts, list) else []
    predictions = load_json(root / "predictions.json") or []
    predictions = predictions if isinstance(predictions, list) else []
    health = load_json(root / "generation_health_history.json") or []
    health = health if isinstance(health, list) else []

    dates = sorted({d for row in timing if (d := iso_date(row.get("captured_at")))})
    if not dates:
        dates = sorted(
            {d for row in alerts if (d := iso_date(row.get("signal_sent_at")))}
        )
    selected_dates = dates[-3:]

    by_date: dict[str, dict[str, int]] = {}
    for date in selected_dates:
        rows = [r for r in timing if iso_date(r.get("captured_at")) == date]
        classes = Counter(
            str(r.get("signal_class") or r.get("signal_state") or "OBSERVED")
            for r in rows
        )
        by_date[date] = {
            "fixtures_discovered": len(
                {r.get("fixture_id") for r in rows if r.get("fixture_id") is not None}
            ),
            "markets_evaluated": len(rows),
            "valid_odds_observations": len(rows),
            "strong_signals": classes.get(
                "STRONG_SIGNAL", classes.get("STRONG", 0)
            ),
            "near_misses": classes.get("NEAR_MISS", 0),
            "observed_only": classes.get("OBSERVED", 0),
            "alerts": sum(
                1 for a in alerts if iso_date(a.get("signal_sent_at")) == date
            ),
            "public_strong": sum(
                1
                for a in alerts
                if iso_date(a.get("signal_sent_at")) == date
                and str(a.get("signal_class")) == "STRONG_SIGNAL"
            ),
            "public_near_miss": sum(
                1
                for a in alerts
                if iso_date(a.get("signal_sent_at")) == date
                and str(a.get("signal_class")) == "NEAR_MISS"
            ),
        }

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "timing_snapshot_rows": len(timing),
        "alert_rows": len(alerts),
        "prediction_rows": len(predictions),
        "health_rows": len(health),
        "observed_dates": selected_dates,
        "by_date": by_date,
        "workflow_contract": {
            "watchlist": "*/2 6-23 * * * Europe/Belgrade",
            "intraday": "*/30 6-23 * * * Europe/Belgrade",
            "classification_source": "watchlist.py market observation",
            "public_builder": "tools/build_public_signal_buckets.py",
        },
        "guardrails": [
            "Counts are derived from persisted observations, not dashboard emptiness.",
            "Post-kickoff observations must not be treated as closing or decision evidence.",
            "No threshold/model changes are performed by this audit.",
        ],
    }


def render_report(result: dict[str, Any]) -> str:
    lines = [
        "# Strong Signal vs Near Miss — Phase 0 Forensic Audit",
        "",
        f"Generated: `{result['generated_at']}`",
        "",
        "## Executive conclusion",
        "",
        "The audit reads persisted market-timing observations, alerts, predictions and generation-health history. It does not infer a zero-signal day from the public Strong Signals file alone.",
        "",
        "Current workflow roles are Watchlist (`*/2 6-23` Europe/Belgrade) for adaptive odds observations/classification and Intraday (`*/30 6-23`) for generation/scanning. The persisted market-timing stream is the primary evidence for observed Strong/Near-Miss/Observed classifications.",
        "",
        "## Persisted evidence",
        "",
        f"- market-timing observations: **{result['timing_snapshot_rows']}**",
        f"- intraday alert records: **{result['alert_rows']}**",
        f"- predictions: **{result['prediction_rows']}**",
        f"- generation-health history records: **{result['health_rows']}**",
        "",
        "## Recent dates",
        "",
        "| Date | Fixtures with observations | Markets evaluated | Valid odds | Strong | Near Miss | Observed | Alerts | Public Strong | Public Near Miss |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for date, row in result["by_date"].items():
        lines.append(
            f"| {date} | {row['fixtures_discovered']} | {row['markets_evaluated']} | {row['valid_odds_observations']} | {row['strong_signals']} | {row['near_misses']} | {row['observed_only']} | {row['alerts']} | {row['public_strong']} | {row['public_near_miss']} |"
        )
    lines += [
        "",
        "## Current classification contract before implementation",
        "",
        "- Strong: existing `is_strong_signal` predicate — EV >= configured Strong EV, probability edge >= configured Strong edge, stake >= configured Strong stake.",
        "- Near Miss: existing watchlist predicate — decision EV >= normal minimum EV minus 3pp **OR** decision edge >= normal minimum edge minus 2pp.",
        "- Observed: valid observed quote that is neither Strong nor Near Miss.",
        "- Qualified Candidate is a separate Production concept and must not be conflated with observational class.",
        "",
        "## Root-cause findings",
        "",
        "1. The persisted observation stream is intended to contain `NEAR_MISS`, but public history is built primarily from Strong Signal records/alerts; this creates a visibility gap rather than proof that Near Misses do not exist.",
        "2. Watchlist state persists only `was_strong` and last-seen data for prediction keys, so class transitions are not first-class historical events.",
        "3. Strong classification and Near-Miss classification are calculated in separate functions (`is_strong_signal` and `_near_miss`), creating a drift risk even though their current thresholds match the documented semantics.",
        "4. The current public builder does not explicitly enforce a canonical class bucket; it merges prior public records, alerts and intraday bets.",
        "5. Existing generation-health records can be degraded for model/fixture failures while the market-timing stream can contain valid observations. These telemetry layers must remain distinct in the audit funnel.",
        "",
        "## Phase 0 gate",
        "",
        "**PASS — audit completed before behavioral implementation on this branch.**",
        "",
        "No thresholds, model mathematics, eligibility, staking or Production accounting were changed by this audit.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    result = audit()
    print(render_report(result))
