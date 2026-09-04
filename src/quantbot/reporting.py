from __future__ import annotations

import html
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any
from urllib.parse import urlencode

from .config import Settings
from .engine import GenerationResult


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _money(value: float) -> str:
    return f"{value:,.0f}".replace(",", ".")


def _skip_url(repository: str, bet_id: str) -> str:
    query = urlencode(
        {
            "title": f"SKIP_{bet_id}",
            "body": "Automatski zahtev: prebaci navedeni PENDING tip u SKIPPED status.",
        }
    )
    return f"https://github.com/{repository}/issues/new?{query}"


def build_email(
    result: GenerationResult, settings: Settings, generated_at: datetime
) -> tuple[str, str]:
    analytics = result.analytics
    mode = "PAPER" if settings.paper_mode else "LIVE"
    cards: list[str] = []
    for bet in result.new_bets:
        kickoff = datetime.fromisoformat(str(bet["kickoff"])).astimezone(
            settings.timezone
        )
        history = "".join(
            f'<div style="color:#8b949e;font-size:11px;margin-top:3px;">{_esc(item)}</div>'
            for item in bet.get("h2h_history", [])
        )
        skip_url = _skip_url(settings.github_repository, str(bet["id"]))
        cards.append(
            f"""
            <div style="background:#161b22;border:1px solid #30363d;border-left:4px solid #3fb950;border-radius:8px;padding:14px;margin:0 0 12px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>
                <td style="font-size:15px;font-weight:700;color:#f0f6fc;">⚽ {_esc(bet["match"])}</td>
                <td align="right"><a href="{_esc(skip_url)}" style="background:#da3633;color:#fff;padding:5px 8px;border-radius:5px;text-decoration:none;font-size:11px;">Preskoči</a></td>
              </tr></table>
              <div style="color:#8b949e;font-size:12px;margin-top:7px;">🏆 {_esc(bet["league"])} · ⏰ {kickoff:%H:%M}</div>
              <div style="color:#f0f6fc;font-size:13px;margin-top:7px;">👉 <b>{_esc(bet["market_display"])}</b> · kvota <b>{float(bet["odd"]):.2f}</b> ({_esc(bet["bookmaker"])})</div>
              <div style="color:#c9d1d9;font-size:12px;margin-top:5px;">Model {100 * float(bet["model_probability"]):.1f}% · odluka {100 * float(bet["decision_probability"]):.1f}% · H2H {100 * float(bet["h2h_rate"]):.1f}%/{int(bet["h2h_n"])} · EV <b>{100 * float(bet["expected_value"]):+.1f}%</b></div>
              <div style="color:#3fb950;font-size:13px;margin-top:5px;">💰 Ulog: <b>{_money(float(bet["stake"]))} RSD</b> · {_esc(mode)}</div>
              <div style="border-top:1px solid #30363d;margin-top:8px;padding-top:5px;">{history}</div>
            </div>
            """
        )

    picks_html = (
        "".join(cards)
        or '<div style="color:#8b949e;padding:15px;background:#161b22;border-radius:8px;">Nema tipova koji prolaze H2H + Dixon–Coles + EV + risk filtere.</div>'
    )
    roi_color = "#3fb950" if analytics.roi >= 0 else "#f85149"
    body = f"""
    <!doctype html><html><body style="margin:0;background:#0d1117;font-family:Arial,sans-serif;color:#f0f6fc;">
      <div style="max-width:650px;margin:auto;padding:14px;">
        <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px;margin-bottom:14px;text-align:center;">
          <div style="font-size:19px;font-weight:700;">⚡ QUANTBET · {_esc(mode)}</div>
          <div style="color:#8b949e;font-size:12px;margin-top:4px;">{generated_at:%d.%m.%Y. %H:%M} · {len(result.new_bets)} novih tipova · {result.api_requests} API zahteva</div>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="6" style="margin-top:10px;font-size:12px;"><tr>
            <td>🏦 Banka<br><b>{_money(analytics.current_bank)} RSD</b></td>
            <td>📈 ROI<br><b style="color:{roi_color};">{100 * analytics.roi:+.2f}%</b></td>
            <td>🎯 Win rate<br><b>{100 * analytics.win_rate:.1f}% ({analytics.completed_count})</b></td>
            <td>📉 DD<br><b>{100 * analytics.current_drawdown:.1f}%</b></td>
          </tr></table>
        </div>
        {picks_html}
        <div style="color:#6e7681;font-size:10px;text-align:center;margin-top:14px;">Dixon–Coles · paired-market de-vig · probability haircut · capped fractional Kelly</div>
      </div>
    </body></html>
    """
    subject = f"⚡ QuantBet {mode}: {len(result.new_bets)} tipova · ROI {100 * analytics.roi:+.1f}% · {generated_at:%d.%m.%Y.}"
    return subject, body


def send_email(subject: str, html_body: str, settings: Settings) -> bool:
    if not settings.gmail_user or not settings.gmail_app_pass or not settings.email_to:
        print("⚠️ Gmail secrets nisu podešeni; analiza je sačuvana bez slanja emaila.")
        return False
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = settings.gmail_user
    message["To"] = settings.email_to
    message.attach(MIMEText(html_body, "html", "utf-8"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(settings.gmail_user, settings.gmail_app_pass)
            server.sendmail(
                settings.gmail_user, [settings.email_to], message.as_string()
            )
        return True
    except (OSError, smtplib.SMTPException) as exc:
        print(f"⚠️ Email nije poslat: {exc}")
        return False
