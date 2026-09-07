from __future__ import annotations

import json
import os
import smtplib
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from .config import BaseballSettings

PREDICTIONS_FILE = "baseball_predictions.json"
SIGNALS_FILE = "baseball_intraday_signals.json"


def _load(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _save(path: Path, payload: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _strong(row: dict[str, Any]) -> bool:
    ev = float(row.get("expected_value") or 0.0)
    edge = float(row.get("probability_edge") or 0.0)
    return ev >= 0.10 and edge >= 0.05


def scan_once(root: Path, now: datetime | None = None) -> dict[str, int]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    predictions = _load(root / PREDICTIONS_FILE)
    signals = _load(root / SIGNALS_FILE)
    existing_ids = {str(item.get("id")) for item in signals}
    created: list[dict[str, Any]] = []
    for row in predictions:
        if str(row.get("status", "PENDING")).upper() not in {"PENDING", "WATCH"}:
            continue
        kickoff_raw = row.get("kickoff")
        if not kickoff_raw:
            continue
        try:
            kickoff = datetime.fromisoformat(str(kickoff_raw).replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            continue
        seconds = (kickoff - now).total_seconds()
        if seconds <= 300 or seconds > 6 * 3600:
            continue
        if not _strong(row):
            continue
        signal_id = f"{row.get('id', row.get('game_id'))}:{now.strftime('%Y%m%d%H%M')}"
        if signal_id in existing_ids:
            continue
        signal = {
            "id": signal_id,
            "signal_source": "BASEBALL_INTRADAY_ALERT",
            "created_at": now.isoformat(),
            "status": "PAPER_SIGNAL",
            "decision": "UPLATI SADA",
            "game_id": row.get("game_id"),
            "league": row.get("league"),
            "match": row.get("match") or f"{row.get('away', '')} @ {row.get('home', '')}",
            "kickoff": kickoff.isoformat(),
            "market": row.get("market"),
            "market_display": row.get("market_display", row.get("market")),
            "odd": row.get("odd"),
            "bookmaker": row.get("bookmaker"),
            "model_probability": row.get("model_probability"),
            "calibrated_probability": row.get("calibrated_probability"),
            "probability_edge": row.get("probability_edge"),
            "expected_value": row.get("expected_value"),
            "entry_valid_until": now.isoformat(),
            "entry_snapshot_at": row.get("snapshot_at") or row.get("odds_captured_at") or now.isoformat(),
        }
        created.append(signal)
        existing_ids.add(signal_id)
    if created:
        signals.extend(created)
        _save(root / SIGNALS_FILE, signals)
    return {"predictions": len(predictions), "new_signals": len(created), "signals_total": len(signals)}


def send_alerts(root: Path, settings: BaseballSettings, now: datetime | None = None) -> int:
    alerts = _load(root / SIGNALS_FILE)
    pending = [item for item in alerts if item.get("status") == "PAPER_SIGNAL" and not item.get("alert_sent_at")]
    if not pending or not os.getenv("GMAIL_USER") or not os.getenv("GMAIL_APP_PASS") or not os.getenv("EMAIL_TO"):
        return 0
    now = (now or datetime.now(UTC)).astimezone(UTC)
    for signal in pending:
        message = MIMEMultipart("alternative")
        message["Subject"] = f"⚾ UPLATI SADA · {signal.get('match')} · {signal.get('market_display')}"
        message["From"] = os.environ["GMAIL_USER"]
        message["To"] = os.environ["EMAIL_TO"]
        body = (
            f"<h2>⚾ UPLATI SADA</h2>"
            f"<p><b>{signal.get('match')}</b><br>{signal.get('league')}<br>"
            f"{signal.get('market_display')} @ {signal.get('odd')} · {signal.get('bookmaker')}</p>"
            f"<p>Model {float(signal.get('model_probability') or 0)*100:.1f}% · "
            f"Edge {float(signal.get('probability_edge') or 0)*100:+.1f}pp · "
            f"EV {float(signal.get('expected_value') or 0)*100:+.1f}%</p>"
            f"<p>Paper signal · generated {now.isoformat()}</p>"
        )
        message.attach(MIMEText(body, "html", "utf-8"))
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
                server.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASS"])
                server.sendmail(os.environ["GMAIL_USER"], [os.environ["EMAIL_TO"]], message.as_string())
        except (OSError, smtplib.SMTPException):
            continue
        signal["alert_sent_at"] = now.isoformat()
    _save(root / SIGNALS_FILE, alerts)
    return len([item for item in pending if item.get("alert_sent_at")])
