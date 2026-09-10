from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from quantbot import MODEL_VERSION
from quantbot.calibration import refit_calibration
from quantbot.config import Settings
from quantbot.engine import QuantEngine
from quantbot.generation_health import build_failure_health, build_success_health
from quantbot.monitor import LedgerMonitor, skip_bet
from quantbot.odds_collection import collect as collect_exhaustive_odds
from quantbot.reporting import build_email, send_email
from quantbot.risk import portfolio_analytics
from quantbot.storage import BetStore, atomic_write_json


def write_ledger_meta(settings: Settings, updated_at: datetime) -> None:
    atomic_write_json(
        ROOT / "ledger_meta.json",
        {
            "initial_bank": settings.initial_bank,
            "paper_mode": settings.paper_mode,
            "model_version": MODEL_VERSION,
            "github_repository": settings.github_repository,
            "updated_at": updated_at.isoformat(),
            "decision_timestamp": updated_at.astimezone(UTC).isoformat(),
            "data_cutoff": updated_at.astimezone(UTC).isoformat(),
        },
    )


def write_api_usage(settings: Settings, updated_at: datetime, result) -> None:
    usage = dict(result.api_usage)
    usage.update(
        {
            "timestamp": updated_at.astimezone(UTC).isoformat(),
            "date": updated_at.astimezone(settings.timezone).date().isoformat(),
            "new_bets": len(result.new_bets),
        }
    )
    atomic_write_json(settings.api_usage_file, usage)
    history: list[dict] = []
    if settings.api_usage_history_file.exists():
        try:
            loaded = json.loads(settings.api_usage_history_file.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                history = loaded
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pass
    history.append(usage)
    atomic_write_json(settings.api_usage_history_file, history[-90:])


def write_generation_health(settings: Settings, payload: dict) -> None:
    atomic_write_json(ROOT / "generation_health.json", payload)
    path = ROOT / "generation_health_history.json"
    history: list[dict] = []
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                history = loaded
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pass
    history.append(payload)
    atomic_write_json(path, history[-90:])


def run_generate(*, deliver_email: bool = True) -> int:
    settings = Settings.from_env(ROOT)
    generated_at = datetime.now(settings.timezone)
    engine = QuantEngine(settings)
    try:
        result = engine.generate(generated_at)
    except Exception as exc:
        write_generation_health(
            settings,
            build_failure_health(generated_at, engine.api.usage_snapshot(), exc),
        )
        raise

    write_ledger_meta(settings, generated_at)
    write_api_usage(settings, generated_at, result)
    write_generation_health(settings, build_success_health(generated_at, result))

    subject, html_body = build_email(result, settings, generated_at)
    (ROOT / "report_preview.html").write_text(html_body, encoding="utf-8")
    (ROOT / "report_subject.txt").write_text(subject, encoding="utf-8")
    if deliver_email:
        send_email(subject, html_body, settings)

    for line in result.diagnostics:
        print(line)
    print(f"API usage: {json.dumps(result.api_usage, ensure_ascii=False)}")
    print(f"Production picks: {len(result.new_bets)}")
    return 0


def run_send_report() -> int:
    settings = Settings.from_env(ROOT)
    subject_path = ROOT / "report_subject.txt"
    body_path = ROOT / "report_preview.html"
    if not subject_path.exists() or not body_path.exists():
        raise SystemExit("Nema generisanog reporta; prvo pokreni generate")
    sent = send_email(
        subject_path.read_text(encoding="utf-8"),
        body_path.read_text(encoding="utf-8"),
        settings,
    )
    return 0 if sent or not settings.gmail_user else 1


def run_exhaustive_odds() -> int:
    settings = Settings.from_env(ROOT)
    result = collect_exhaustive_odds(settings)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def run_monitor() -> int:
    settings = Settings.from_env(ROOT)
    result = LedgerMonitor(settings).run()
    print(json.dumps(result, ensure_ascii=False))
    return 0


def run_skip(identifier: str) -> int:
    settings = Settings.from_env(ROOT)
    changed = skip_bet(BetStore(settings.bets_file), identifier)
    print("Production bet marked SKIPPED" if changed else "Pending Production bet not found")
    return 0 if changed else 2


def run_calibrate() -> int:
    settings = Settings.from_env(ROOT)
    result = refit_calibration(
        settings.predictions_file,
        settings.calibration_file,
        min_samples=settings.min_calibration_samples,
        max_ece=settings.max_calibration_ece,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def run_analytics() -> int:
    settings = Settings.from_env(ROOT)
    bets = BetStore(settings.bets_file).load()
    analytics = portfolio_analytics(bets, settings.initial_bank)
    print(
        json.dumps(
            {
                "current_bank": analytics.current_bank,
                "total_profit": analytics.total_profit,
                "total_stake": analytics.total_stake,
                "roi": analytics.roi,
                "win_rate": analytics.win_rate,
                "completed_count": analytics.completed_count,
                "open_stake": analytics.open_stake,
                "daily_stake": analytics.daily_stake,
                "current_drawdown": analytics.current_drawdown,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="QuantBet Football Production")
    sub = cli.add_subparsers(dest="command", required=True)
    generate = sub.add_parser("generate", help="Generate Production picks and email")
    generate.add_argument("--no-email", action="store_true")
    sub.add_parser("send-report", help="Send the last Production email")
    sub.add_parser("capture-odds", help="Capture the 72h odds universe")
    sub.add_parser("monitor", help="Settle finished Production bets")
    sub.add_parser("settle", help="Alias for monitor")
    sub.add_parser("calibrate", help="Refit model calibration manually")
    sub.add_parser("analytics", help="Show Production portfolio metrics")
    skip = sub.add_parser("skip", help="Mark one pending Production bet as SKIPPED")
    skip.add_argument("--id", dest="identifier")
    skip.add_argument("--issue-title")
    return cli


def main() -> int:
    args = parser().parse_args()
    if args.command == "generate":
        return run_generate(deliver_email=not args.no_email)
    if args.command == "send-report":
        return run_send_report()
    if args.command == "capture-odds":
        return run_exhaustive_odds()
    if args.command in {"monitor", "settle"}:
        return run_monitor()
    if args.command == "skip":
        identifier = args.identifier or args.issue_title or os.getenv("ISSUE_TITLE", "")
        if not identifier:
            raise SystemExit("skip requires --id, --issue-title or ISSUE_TITLE")
        return run_skip(identifier)
    if args.command == "calibrate":
        return run_calibrate()
    if args.command == "analytics":
        return run_analytics()
    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
