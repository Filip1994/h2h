from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw_api"
SNAP = ROOT / "data" / "odds_snapshots.jsonl"


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        ).astimezone(UTC)
    except ValueError:
        return None


def raw_odds_records() -> tuple[
    list[dict[str, Any]], Counter[str], Counter[str], Counter[str]
]:
    records: list[dict[str, Any]] = []
    endpoint_counts: Counter[str] = Counter()
    bookmaker_counts: Counter[str] = Counter()
    market_counts: Counter[str] = Counter()
    for path in sorted(RAW.glob("*.jsonl")):
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                endpoint = str(record.get("endpoint") or "")
                endpoint_counts[endpoint] += 1
                if endpoint != "odds":
                    continue
                response = (record.get("payload") or {}).get("response")
                if not isinstance(response, list):
                    continue
                params = record.get("params") or {}
                fixture = None
                for param in ("fixture", "id"):
                    if params.get(param) is not None:
                        try:
                            fixture = int(params[param])
                            break
                        except (TypeError, ValueError):
                            pass
                captured = parse_dt(record.get("captured_at"))
                if fixture is None or captured is None:
                    continue
                records.append(
                    {
                        "fixture_id": fixture,
                        "captured_at": captured,
                        "response": response,
                    }
                )
                for container in response:
                    for bookmaker in container.get("bookmakers") or []:
                        bookmaker_counts[
                            str(bookmaker.get("id") or bookmaker.get("name") or "unknown")
                        ] += 1
                        for market in bookmaker.get("bets") or []:
                            market_counts[
                                str(market.get("id") or market.get("name") or "unknown")
                            ] += 1
    return records, endpoint_counts, bookmaker_counts, market_counts


def quote_rows(record: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for container in record["response"]:
        for bookmaker in container.get("bookmakers") or []:
            bid = bookmaker.get("id")
            for market in bookmaker.get("bets") or []:
                name = str(market.get("name") or market.get("id") or "")
                values = market.get("values") or []
                for selection in values:
                    odd = selection.get("odd")
                    if odd is None:
                        continue
                    rows.append(
                        {
                            "fixture_id": record["fixture_id"],
                            "captured_at": record["captured_at"],
                            "bookmaker_id": bid,
                            "bookmaker": bookmaker.get("name"),
                            "bookmaker_logo": bookmaker.get("logo"),
                            "market": name,
                            "selection": selection.get("value"),
                            "odd": odd,
                            "update": bookmaker.get("update"),
                        }
                    )
    return rows


def normalize_market(value: Any) -> str:
    value = str(value or "").upper().strip().replace(" ", "_")
    return {
        "UNDER_2.5": "UNDER_2_5",
        "OVER_2.5": "OVER_2_5",
    }.get(value, value)


def pick_key(item: dict[str, Any]) -> tuple[int, str, int] | None:
    try:
        return (
            int(item["event_id"]),
            normalize_market(item.get("market")),
            int(item["bookmaker_id"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def audit() -> dict[str, Any]:
    bets = load_json(ROOT / "bets.json") or []
    predictions = load_json(ROOT / "predictions.json") or []
    snapshots = []
    if SNAP.exists():
        with SNAP.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    snapshots.append(item)

    records, endpoint_counts, bookmaker_counts, market_counts = raw_odds_records()
    quotes: list[dict[str, Any]] = []
    for record in records:
        quotes.extend(quote_rows(record))

    by_key: dict[tuple[int, str, int], list[dict[str, Any]]] = defaultdict(list)
    for quote in quotes:
        key = (
            quote["fixture_id"],
            normalize_market(quote["market"]),
            int(quote["bookmaker_id"] or 0),
        )
        by_key[key].append(quote)
    for values in by_key.values():
        values.sort(key=lambda item: item["captured_at"])

    coverage: Counter[str] = Counter()
    missing_examples: list[dict[str, Any]] = []
    for bet in bets:
        key = pick_key(bet)
        if key is None:
            continue
        pick_at = parse_dt(bet.get("odds_captured_at") or bet.get("created_at"))
        values = by_key.get(key, [])
        pre_pick = [
            quote for quote in values if pick_at is None or quote["captured_at"] <= pick_at
        ]
        opening = bool(pre_pick)
        closing = bool(
            bet.get("closing_odd") is not None
            and parse_dt(bet.get("closing_odds_captured_at"))
        )
        if opening and closing:
            coverage["FULLY_AUDITABLE"] += 1
        elif opening or closing:
            coverage["PARTIAL"] += 1
        else:
            coverage["UNRECOVERABLE"] += 1
            missing_examples.append(
                {
                    "id": bet.get("id"),
                    "match": bet.get("match"),
                    "reason": "no matching archived odds before pick",
                }
            )

    public_codes = []
    for path in (ROOT / "index.html", ROOT / "strong-signals.html"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"\b(?:UNDER_2_5|OVER_2_5|BTTS_YES|BTTS_NO)\b", text):
            public_codes.append(str(path.relative_to(ROOT)))

    schedules = {}
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        text = path.read_text(encoding="utf-8", errors="replace")
        schedules[path.name] = re.findall(r'cron:\s*"([^"]+)"', text)

    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "files": {
            "raw_api_files": len(list(RAW.glob("*.jsonl"))),
            "raw_api_bytes": sum(p.stat().st_size for p in RAW.glob("*.jsonl")),
            "odds_snapshot_bytes": SNAP.stat().st_size if SNAP.exists() else 0,
            "odds_snapshot_lines": len(snapshots),
            "bets": len(bets),
            "predictions": len(predictions),
        },
        "raw_api": {
            "total_records": sum(endpoint_counts.values()),
            "endpoint_counts": dict(endpoint_counts),
            "odds_response_records": len(records),
            "odds_quote_rows": len(quotes),
            "unique_fixture_bookmaker_market": len(by_key),
            "bookmakers": bookmaker_counts.most_common(15),
            "markets": market_counts.most_common(15),
            "provider_logo_present_rows": sum(
                1 for quote in quotes if quote.get("bookmaker_logo")
            ),
            "sample_odds_schema": quotes[0] if quotes else None,
        },
        "historical_coverage": dict(coverage),
        "missing_examples": missing_examples[:10],
        "public_machine_code_files": public_codes,
        "workflow_schedules": schedules,
    }

    token = os.environ.get("GITHUB_TOKEN")
    if token:
        url = "https://api.github.com/repos/Filip1994/h2h/actions/runs?per_page=100"
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                runs = json.load(response).get("workflow_runs", [])
            scheduled = [run for run in runs if run.get("event") == "schedule"]
            result["actions"] = {
                "runs": len(runs),
                "scheduled_runs": len(scheduled),
                "scheduled_by_workflow": dict(
                    Counter(run.get("name") for run in scheduled)
                ),
                "recent_scheduled": [
                    {
                        "name": run.get("name"),
                        "id": run.get("id"),
                        "status": run.get("status"),
                        "conclusion": run.get("conclusion"),
                        "created_at": run.get("created_at"),
                        "head_sha": run.get("head_sha"),
                    }
                    for run in scheduled[:20]
                ],
            }
        except Exception as exc:  # pragma: no cover - network is optional in tests
            result["actions"] = {"error": str(exc)}

    return result


def markdown(data: dict[str, Any]) -> str:
    files = data["files"]
    raw = data["raw_api"]
    coverage = data["historical_coverage"]
    lines = [
        "# QuantBet Odds Lifecycle — Phase 0 Forensic Audit",
        "",
        f"Generated: `{data['generated_at']}`",
        "",
        "## Executive conclusion",
        "",
        "The current main branch has an append-only snapshot layer and separate T-5/CLV tooling, but the lifecycle is not fully canonical: ENTRY is created from the pick record, Strong Signals uses a separate alert-closing path, and persistence is split across workflows. The repair phase must unify these boundaries without changing decision mathematics.",
        "",
        "## A. Source inventory",
        f"- Raw API archive: `{files['raw_api_files']}` JSONL files, `{files['raw_api_bytes']:,}` bytes.",
        f"- Canonical odds ledger: `{files['odds_snapshot_lines']}` JSONL snapshots, `{files['odds_snapshot_bytes']:,}` bytes.",
        f"- Production bets: `{files['bets']}`; predictions: `{files['predictions']}`.",
        "- Provider archive: API-Football `odds` responses include our capture timestamp, endpoint, request parameters and payload.",
        "- Persistence: `src/quantbot/persistence.py` and `tools/persist_clv.py`.",
        "- Closing: `.github/workflows/closing-capture.yml` and alert/closing modules.",
        "- CLV: `.github/workflows/clv-persistence.yml`.",
        "- Strong Signals: watchlist/intraday workflows plus `src/quantbot/alert_lifecycle.py`.",
        "",
        "## B. Provider evidence",
        f"- Archived odds responses: `{raw['odds_response_records']}`; extracted quote rows: `{raw['odds_quote_rows']}`; unique fixture/bookmaker/market keys: `{raw['unique_fixture_bookmaker_market']}`.",
        f"- Provider bookmaker logo metadata observed on `{raw['provider_logo_present_rows']}` quote rows.",
        f"- Representative extracted quote: `{json.dumps(raw['sample_odds_schema'], ensure_ascii=False, default=str)}`.",
        "- Opening is not provider-native historical data in this archive. A defensible Opening must be the earliest valid observation our own archive contains for the exact fixture/market/bookmaker.",
        "",
        "## C. Historical lifecycle coverage",
        f"- `FULLY_AUDITABLE`: `{coverage.get('FULLY_AUDITABLE', 0)}`",
        f"- `PARTIAL`: `{coverage.get('PARTIAL', 0)}`",
        f"- `UNRECOVERABLE`: `{coverage.get('UNRECOVERABLE', 0)}`",
        "- No missing stage is filled by inference or bookmaker substitution.",
        "",
        "## D. Root causes",
        "1. ENTRY currently represents the pick quote, so Opening is not independently selected from the earliest archived valid observation.",
        "2. Strong Signals stores T-5 closing data in `intraday_alerts.json`, while Production canonical closing/CLV is stored through `bets.json` and `data/odds_snapshots.jsonl`.",
        "3. Legacy CLV can exist without a linked Entry snapshot, so mathematical presence and auditability are currently conflated.",
        "4. Raw archive and snapshot persistence is distributed across several concurrent workflows, creating race/push boundaries that need explicit reconciliation.",
        "5. Backend market codes are legitimate internal values but must never leak into public presentation.",
        "",
        "## E. Cadence",
    ]
    for workflow, crons in data["workflow_schedules"].items():
        lines.append(f"- `{workflow}`: `{', '.join(crons) if crons else 'no schedule'}`")
    if "actions" in data and "error" not in data["actions"]:
        actions = data["actions"]
        lines += [
            "",
            "### Observed Actions history",
            f"- Runs inspected: `{actions['runs']}`.",
            f"- Scheduled runs: `{actions['scheduled_runs']}`.",
            f"- Scheduled runs by workflow: `{actions['scheduled_by_workflow']}`.",
        ]
    elif "actions" in data:
        lines.append(f"- Actions API audit unavailable: `{data['actions'].get('error')}`")
    lines += [
        "",
        "## F. Missing records",
        "Exact missing records are classified only when fixture/market/bookmaker evidence is present. The implementation must add a Verona/Arezzo regression fixture (or equivalent exact missing-data case) so the failure remains testable.",
        "",
        "## G. Implementation gate",
        "Phase 0 is complete when this report is attached to the PR before product lifecycle changes. The repair must preserve Dixon-Coles, calibration, EV/edge, risk/Kelly, eligibility and accounting separation.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = markdown(audit())
    print(report)
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
