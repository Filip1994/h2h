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
BET_FILES = (ROOT / "bets.json", ROOT / "predictions.json")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def raw_odds_records() -> tuple[list[dict[str, Any]], Counter[str], Counter[str], Counter[str]]:
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
                fixture = None
                params = record.get("params") or {}
                for key in ("fixture", "id"):
                    if params.get(key) is not None:
                        try:
                            fixture = int(params[key])
                            break
                        except (TypeError, ValueError):
                            pass
                if fixture is None:
                    continue
                captured = parse_dt(record.get("captured_at"))
                if captured is None:
                    continue
                records.append({"fixture_id": fixture, "captured_at": captured, "response": response, "record": record})
                for book in response:
                    for bookmaker in book.get("bookmakers") or []:
                        bookmaker_counts[str(bookmaker.get("id") or bookmaker.get("name") or "unknown")] += 1
                        for market in bookmaker.get("bets") or bookmaker.get("markets") or []:
                            market_counts[str(market.get("id") or market.get("name") or "unknown")] += 1
    return records, endpoint_counts, bookmaker_counts, market_counts


def quote_rows(record: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    captured = record["captured_at"]
    fixture = record["fixture_id"]
    for bookmaker_container in record["response"]:
        for bookmaker in bookmaker_container.get("bookmakers") or []:
            bid = bookmaker.get("id")
            bname = bookmaker.get("name")
            blogo = bookmaker.get("logo")
            for market in bookmaker.get("bets") or bookmaker.get("markets") or []:
                mname = str(market.get("name") or market.get("key") or market.get("id") or "")
                selections = market.get("values") or market.get("outcomes") or []
                for selection in selections:
                    odd = selection.get("odd")
                    if odd is None:
                        odd = selection.get("price")
                    if odd is None:
                        continue
                    rows.append({
                        "fixture_id": fixture,
                        "captured_at": captured,
                        "bookmaker_id": bid,
                        "bookmaker": bname,
                        "bookmaker_logo": blogo,
                        "market": mname,
                        "selection": selection.get("value") or selection.get("name") or selection.get("key"),
                        "odd": odd,
                        "opposite_odd": None,
                        "update": bookmaker.get("update") or market.get("update") or selection.get("update"),
                    })
    return rows


def normalize_market(value: Any) -> str:
    s = str(value or "").upper().strip().replace(" ", "_")
    aliases = {
        "UNDER_2.5": "UNDER_2_5", "OVER_2.5": "OVER_2_5",
        "UNDER_2_5": "UNDER_2_5", "OVER_2_5": "OVER_2_5",
        "BTTS_YES": "BTTS_YES", "BTTS_NO": "BTTS_NO",
    }
    return aliases.get(s, s)


def pick_key(item: dict[str, Any]) -> tuple[int, str, int] | None:
    try:
        return int(item["event_id"]), normalize_market(item.get("market")), int(item["bookmaker_id"])
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

    raw_records, endpoint_counts, bookmaker_counts, market_counts = raw_odds_records()
    quotes: list[dict[str, Any]] = []
    for record in raw_records:
        quotes.extend(quote_rows(record))

    quotes_by_key: dict[tuple[int, str, int], list[dict[str, Any]]] = defaultdict(list)
    for q in quotes:
        quotes_by_key[(q["fixture_id"], normalize_market(q["market"]), int(q["bookmaker_id"] or 0))].append(q)
    for values in quotes_by_key.values():
        values.sort(key=lambda x: x["captured_at"])

    coverage = Counter()
    missing_examples: list[dict[str, Any]] = []
    for bet in bets:
        key = pick_key(bet)
        if key is None:
            continue
        pick_at = parse_dt(bet.get("odds_captured_at") or bet.get("created_at"))
        values = quotes_by_key.get(key, [])
        pre_pick = [q for q in values if pick_at is None or q["captured_at"] <= pick_at]
        opening = pre_pick[0] if pre_pick else None
        closing = bet.get("closing_odd") is not None and parse_dt(bet.get("closing_odds_captured_at")) is not None
        if opening and closing:
            coverage["FULLY_AUDITABLE"] += 1
        elif opening or closing:
            coverage["PARTIAL"] += 1
        else:
            coverage["UNRECOVERABLE"] += 1
        if pick_at is None or not values:
            missing_examples.append({"id": bet.get("id"), "match": bet.get("match"), "reason": "no matching archived odds before pick"})

    logos = sum(1 for q in quotes if q.get("bookmaker_logo"))
    public_codes = []
    for path in (ROOT / "index.html", ROOT / "strong-signals.html", ROOT / "main.py", ROOT / "src"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            if re.search(r"\b(?:UNDER_2_5|OVER_2_5|BTTS_YES|BTTS_NO)\b", text):
                public_codes.append(str(path.relative_to(ROOT)))
        elif path.is_dir():
            for child in path.rglob("*.py"):
                text = child.read_text(encoding="utf-8", errors="replace")
                if "UNDER_2_5" in text or "OVER_2_5" in text or "BTTS_YES" in text or "BTTS_NO" in text:
                    continue

    workflow_paths = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    schedules = {}
    for path in workflow_paths:
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
            "odds_response_records": len(raw_records),
            "odds_quote_rows": len(quotes),
            "unique_fixture_bookmaker_market": len(quotes_by_key),
            "bookmakers": bookmaker_counts.most_common(15),
            "markets": market_counts.most_common(15),
            "provider_logo_present_rows": logos,
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
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                runs = json.load(response).get("workflow_runs", [])
            result["actions"] = {
                "runs": len(runs),
                "scheduled_runs": sum(1 for r in runs if r.get("event") == "schedule"),
                "scheduled_by_workflow": dict(Counter(r.get("name") for r in runs if r.get("event") == "schedule")),
                "recent_scheduled": [
                    {"name": r.get("name"), "id": r.get("id"), "status": r.get("status"), "conclusion": r.get("conclusion"), "created_at": r.get("created_at"), "head_sha": r.get("head_sha")}
                    for r in runs if r.get("event") == "schedule"
                ][:20],
            }
        except Exception as exc:  # audit must still produce a report if GitHub API is temporarily unavailable
            result["actions"] = {"error": str(exc)}

    return result


def markdown(data: dict[str, Any]) -> str:
    f = data["files"]
    r = data["raw_api"]
    c = data["historical_coverage"]
    lines = [
        "# QuantBet Odds Lifecycle — Phase 0 Forensic Audit",
        "",
        f"Generated: `{data['generated_at']}`",
        "",
        "## Executive conclusion",
        "",
        "The current main branch already has an append-only canonical snapshot layer and T-5/CLV tooling, but the audit shows the lifecycle is not yet fully canonical end-to-end: Entry snapshots are created from the pick record rather than independently selected from the earliest archived observation, Strong Signals has a separate alert-closing path, and workflow persistence is split across several jobs. The implementation phase must unify these boundaries without changing decision mathematics.",
        "",
        "## A. Source inventory",
        f"- Raw API archive: `{f['raw_api_files']}` JSONL files, `{f['raw_api_bytes']:,}` bytes.",
        f"- Canonical odds ledger: `{f['odds_snapshot_lines']}` JSONL snapshots, `{f['odds_snapshot_bytes']:,}` bytes.",
        f"- Production bets: `{f['bets']}`; predictions: `{f['predictions']}`.",
        "- Provider source: API-Football `odds` responses are archived with `captured_at`, endpoint, request parameters and full payload.",
        "- Canonical persistence: `src/quantbot/persistence.py` and `tools/persist_clv.py`.",
        "- Closing capture: `.github/workflows/closing-capture.yml` plus `src/quantbot/closing.py`/alert lifecycle.",
        "- CLV persistence: `.github/workflows/clv-persistence.yml`.",
        "- Watchlist/Strong Signals: `.github/workflows/watchlist.yml`, `.github/workflows/intraday.yml` and `src/quantbot/alert_lifecycle.py`.",
        "",
        "## B. Provider evidence",
        f"- Archived odds response records: `{r['odds_response_records']}`; extracted quote rows: `{r['odds_quote_rows']}`; unique fixture/bookmaker/market keys: `{r['unique_fixture_bookmaker_market']}`.",
        f"- Provider bookmaker logo metadata observed on `{r['provider_logo_present_rows']}` extracted quote rows.",
        f"- Representative extracted schema: `{json.dumps(r['sample_odds_schema'], ensure_ascii=False, default=str)}`.",
        "- The provider archive is timestamped by our capture (`captured_at`). A historical opening price is therefore not a provider-native field; Opening can only be reconstructed from the earliest valid observation our archive actually contains.",
        "",
        "## C. Historical lifecycle coverage",
        f"- `FULLY_AUDITABLE`: `{c.get('FULLY_AUDITABLE', 0)}`",
        f"- `PARTIAL`: `{c.get('PARTIAL', 0)}`",
        f"- `UNRECOVERABLE`: `{c.get('UNRECOVERABLE', 0)}`",
        "- Important: `PARTIAL`/`UNRECOVERABLE` are not filled with guessed prices. They remain explicitly incomplete until real source observations prove the missing stage.",
        "",
        "## D. Concrete root causes found",
        "1. **Opening is not yet a first-class independent observation.** `record_prediction_quote()` persists the pick quote as `ENTRY`; historical reconstruction exists only as `INTERMEDIATE` snapshots. The product contract therefore needs an explicit Opening selector derived from the earliest valid archived observation for the exact fixture/market/bookmaker.",
        "2. **Strong Signals closing is stored in `intraday_alerts.json` using `closing_5m_*`, while canonical Production CLV uses `bets.json` + `odds_snapshots.jsonl`.** This is a linkage boundary, not merely a display issue.",
        "3. **CLV can exist on a bet while `clv_status` remains `NOT_COMPUTABLE` when no Entry snapshot is linked.** That is an auditability defect: the system must distinguish a mathematically present legacy value from a fully linked lifecycle.",
        "4. **Raw archive persistence is workflow-dependent.** Daily/intraday/watchlist/closing jobs each stage different subsets, creating race/persistence boundaries that must be made explicit and append-safe.",
        "5. **Machine market codes remain legitimate backend values and appear in implementation files.** Public rendering must use one canonical mapping; backend codes must not leak through any public surface.",
        "",
        "## E. Cadence audit",
    ]
    for workflow, crons in data["workflow_schedules"].items():
        lines.append(f"- `{workflow}`: `{', '.join(crons) if crons else 'no schedule'}`")
    if "actions" in data:
        a = data["actions"]
        lines += [
            "",
            "### Observed Actions history",
            f"- Recent workflow runs inspected: `{a.get('runs')}`.",
            f"- Scheduled runs in the inspected window: `{a.get('scheduled_runs')}`.",
            f"- Scheduled runs by workflow: `{a.get('scheduled_by_workflow')}`.",
        ]
    lines += [
        "",
        "## F. Missing-record investigation",
        "The current archive audit does not fabricate a Verona/Arezzo match when no exact record is present. Any concrete missing record is classified by exact fixture/market/bookmaker key and archive evidence. The implementation must add a regression fixture for Verona/Arezzo (or an equivalent exact missing-data case) so the failure mode is permanently testable.",
        "",
        "## G. Validation / failure visibility",
        "Current quote extraction enforces bookmaker identity, market parsing and overround validation. API errors are raised as `APIError`. The main gap is observability of rejected quotes: the implementation must persist a reason-coded lifecycle/audit event rather than silently dropping an otherwise relevant candidate.",
        "",
        "## H. Implementation gate",
        "The implementation phase is permitted only after this report has been reviewed/attached. No model, calibration, EV/edge, risk/Kelly, league eligibility or betting-rule mathematics is changed by the lifecycle repair.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = audit()
    report = markdown(data)
    print(report)
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
