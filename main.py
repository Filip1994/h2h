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
from quantbot.alerts import (
    build_strong_signal_email,
    is_strong_signal,
    send_strong_signal_email,
)
from quantbot.calibration import refit_calibration
from quantbot.closing import (
    build_closing_day_email,
    capture_five_minute_closing_quotes,
    send_html_email,
)
from quantbot.config import Settings
from quantbot.engine import QuantEngine
from quantbot.monitor import LedgerMonitor, skip_bet
from quantbot.reporting import build_email, send_email
from quantbot.risk import portfolio_analytics
from quantbot.storage import BetStore, atomic_write_json
from quantbot.watchlist import run_watchlist


def write_ledger_meta(settings: Settings, updated_at: datetime) -> None:
    payload = {
        "initial_bank": settings.initial_bank,
        "paper_mode": settings.paper_mode,
        "model_version": MODEL_VERSION,
        "github_repository": settings.github_repository,
        "updated_at": updated_at.isoformat(),
        "decision_timestamp": updated_at.astimezone(UTC).isoformat(),
        "data_cutoff": updated_at.astimezone(UTC).isoformat(),
        "h2h_telemetry_enabled": settings.h2h_telemetry_enabled,
    }
    atomic_write_json(ROOT / "ledger_meta.json", payload)


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
            loaded = json.loads(
                settings.api_usage_history_file.read_text(encoding="utf-8")
            )
            if isinstance(loaded, list):
                history = loaded
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            history = []
    history.append(usage)
    atomic_write_json(settings.api_usage_history_file, history[-90:])


def run_generate(*, deliver_email: bool = True) -> int:
    settings = Settings.from_env(ROOT)
    generated_at = datetime.now(settings.timezone)
    result = QuantEngine(settings).generate(generated_at)
    write_ledger_meta(settings, generated_at)
    write_api_usage(settings, generated_at, result)

    if settings.intraday_mode:
        strong = tuple(
            bet for bet in result.new_bets if is_strong_signal(bet, settings)
        )
        subject, html_body = build_strong_signal_email(result, settings, generated_at)
        (ROOT / "report_preview.html").write_text(html_body, encoding="utf-8")
        (ROOT / "report_subject.txt").write_text(subject, encoding="utf-8")
        if deliver_email and settings.intraday_alert_enabled and strong:
            send_strong_signal_email(subject, html_body, settings)
        print(f"🚨 Strong signals: {len(strong)} / new bets: {len(result.new_bets)}")
    else:
        subject, html_body = build_email(result, settings, generated_at)
        (ROOT / "report_preview.html").write_text(html_body, encoding="utf-8")
        (ROOT / "report_subject.txt").write_text(subject, encoding="utf-8")
        if deliver_email:
            send_email(subject, html_body, settings)

    for line in result.diagnostics:
        print(line)
    print(f"API usage: {json.dumps(result.api_usage, ensure_ascii=False)}")
    print(f"✅ Sačuvano novih tipova: {len(result.new_bets)}")
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


def run_watchlist_command() -> int:
    settings = Settings.from_env(ROOT)
    result = run_watchlist(settings)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def run_capture_closing() -> int:
    settings = Settings.from_env(ROOT)
    captured = capture_five_minute_closing_quotes(settings)
    print(f"📌 T-5 closing snapshots captured: {captured}")
    return 0


def run_closing_report(day: str | None = None) -> int:
    settings = Settings.from_env(ROOT)
    target_day = day or datetime.now(settings.timezone).date().isoformat()
    bets = BetStore(settings.bets_file).load()
    selected = [
        b
        for b in bets
        if str(b.get("date") or str(b.get("created_at") or "")[:10]) == target_day
        and str(b.get("signal_source", "")) in {"DAILY_BULLETIN", "INTRADAY_ALERT"}
    ]
    alerts_path = ROOT / "intraday_alerts.json"
    if alerts_path.exists():
        try:
            alerts = json.loads(alerts_path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            alerts = []
        if isinstance(alerts, list):
            linked_ids = {str(b.get("id")) for b in selected}
            for alert in alerts:
                if not isinstance(alert, dict):
                    continue
                alert_day = str(alert.get("signal_sent_at") or "")[:10]
                if alert_day != target_day:
                    continue
                linked_id = str(alert.get("linked_bet_id") or "")
                if linked_id and linked_id in linked_ids:
                    continue
                selected.append(alert)
    subject, html_body = build_closing_day_email(settings, target_day, selected)
    (ROOT / "closing_report_preview.html").write_text(html_body, encoding="utf-8")
    (ROOT / "closing_report_subject.txt").write_text(subject, encoding="utf-8")
    send_html_email(subject, html_body, settings)
    print(f"📘 Closing day report: {target_day} · {len(selected)} signals")
    return 0


def run_monitor() -> int:
    settings = Settings.from_env(ROOT)
    result = LedgerMonitor(settings).run()
    print(json.dumps(result, ensure_ascii=False))
    return 0


def run_skip(identifier: str) -> int:
    settings = Settings.from_env(ROOT)
    changed = skip_bet(BetStore(settings.bets_file), identifier)
    print(
        "✅ Tip je prebačen u SKIPPED."
        if changed
        else "⚠️ PENDING tip sa tim ID-em nije pronađen."
    )
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
    cli = argparse.ArgumentParser(description="QuantBet H2H v2")
    subcommands = cli.add_subparsers(dest="command", required=True)
    generate = subcommands.add_parser(
        "generate", help="Generiši dnevni ili intraday bilten"
    )
    generate.add_argument("--no-email", action="store_true")
    subcommands.add_parser(
        "send-report", help="Pošalji poslednji generisani email report"
    )
    subcommands.add_parser(
        "watchlist", help="Adaptivno prati pikove i near-miss signale"
    )
    subcommands.add_parser("monitor", help="Snimi closing odds i poravnaj rezultate")
    subcommands.add_parser(
        "capture-closing", help="Snimi T-5 closing odds za signalizovane utakmice"
    )
    closing = subcommands.add_parser(
        "closing-report", help="Pošalji završni closing-day bilten"
    )
    closing.add_argument("--day")
    subcommands.add_parser("settle", help="Alias za monitor")
    subcommands.add_parser(
        "calibrate", help="Refituj Platt kalibraciju iz OOS prediction ledgera"
    )
    subcommands.add_parser("analytics", help="Prikaži portfolio metrike")
    skip = subcommands.add_parser("skip", help="Prebaci tačan bet ID u SKIPPED")
    skip.add_argument("--id", dest="identifier")
    skip.add_argument("--issue-title")
    return cli


def main() -> int:
    args = parser().parse_args()
    if args.command == "generate":
        return run_generate(deliver_email=not args.no_email)
    if args.command == "send-report":
        return run_send_report()
    if args.command == "watchlist":
        return run_watchlist_command()
    if args.command == "monitor" or args.command == "settle":
        return run_monitor()
    if args.command == "capture-closing":
        return run_capture_closing()
    if args.command == "closing-report":
        return run_closing_report(args.day)
    if args.command == "calibrate":
        return run_calibrate()
    if args.command == "analytics":
        return run_analytics()
    if args.command == "skip":
        identifier = args.identifier or args.issue_title or os.getenv("ISSUE_TITLE", "")
        if not identifier:
            raise SystemExit("skip zahteva --id, --issue-title ili ISSUE_TITLE")
        return run_skip(identifier)
    raise SystemExit(f"Nepoznata komanda: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
