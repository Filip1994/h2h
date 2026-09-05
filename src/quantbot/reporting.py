from __future__ import annotations

import html
import smtplib
from datetime import UTC, datetime
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
    query = urlencode({"title": f"SKIP_{bet_id}", "body": "Automatski zahtev: prebaci navedeni PENDING tip u SKIPPED status."})
    return f"https://github.com/{repository}/issues/new?{query}"


def build_email(result: GenerationResult, settings: Settings, generated_at: datetime) -> tuple[str, str]:
    analytics = result.analytics
    mode = "PAPER" if settings.paper_mode else "LIVE"
    cards: list[str] = []
    for bet in result.new_bets:
        kickoff = datetime.fromisoformat(str(bet["kickoff"])).astimezone(settings.timezone)
        cards.append(
            f'''<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px;margin:0 0 12px;">
              <div style="font-size:15px;font-weight:700;">⚽ {_esc(bet["match"])}</div>
              <div style="color:#8b949e;font-size:12px;margin-top:6px;">{_esc(bet["league"])} · ⏰ {kickoff:%H:%M}</div>
              <div style="margin-top:7px;">👉 <b>{_esc(bet["market_display"])}</b> · kvota <b>{float(bet["odd"]):.2f}</b></div>
              <div style="color:#c9d1d9;font-size:12px;margin-top:6px;">Model {100*float(bet["model_probability"]):.1f}% · odluka {100*float(bet["decision_probability"]):.1f}% · EV {100*float(bet["expected_value"]):+.1f}%</div>
              <div style="margin-top:6px;">💰 <b>{_money(float(bet["stake"]))} RSD</b> · {_esc(mode)}</div>
              <div style="margin-top:8px;"><a href="{_esc(_skip_url(settings.github_repository, str(bet["id"]))) }" style="color:#ff7b72;">Preskoči tip</a></div>
            </div>'''
        )
    picks_html = "".join(cards) or '<div style="background:#161b22;padding:14px;border-radius:8px;color:#8b949e;">Danas nema tipa koji prolazi sve filtere. To je normalan rezultat.</div>'
    roi_color = "#3fb950" if analytics.roi >= 0 else "#f85149"
    cutoff = generated_at.astimezone(UTC).isoformat()
    body = f'''<!doctype html><html><body style="margin:0;background:#0d1117;font-family:Arial,sans-serif;color:#f0f6fc;"><div style="max-width:680px;margin:auto;padding:14px;">
      <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px;text-align:center;">
        <div style="font-size:19px;font-weight:700;">⚡ QUANTBET · {_esc(mode)}</div>
        <div style="color:#8b949e;font-size:12px;margin-top:5px;">{generated_at:%d.%m.%Y. %H:%M} · {len(result.new_bets)} novih tipova · {result.api_requests} API zahteva</div>
        <div style="color:#8b949e;font-size:11px;margin-top:5px;">H2H uticaj: 0% · data cutoff: {_esc(cutoff)}</div>
        <table width="100%" cellspacing="0" cellpadding="6" style="margin-top:10px;font-size:12px;"><tr>
          <td>🏦 Banka<br><b>{_money(analytics.current_bank)} RSD</b></td><td>📈 ROI<br><b style="color:{roi_color};">{100*analytics.roi:+.2f}%</b></td><td>🎯 Win rate<br><b>{100*analytics.win_rate:.1f}% ({analytics.completed_count})</b></td><td>📉 DD<br><b>{100*analytics.current_drawdown:.1f}%</b></td>
        </tr></table>
      </div>
      <div style="margin-top:14px;">{picks_html}</div>
      <div style="color:#8b949e;font-size:11px;margin-top:12px;">Model proceni verovatnoću → kalibracija je proveri → tržišna cena se uporedi → ako dokaz nije dovoljno jak, nema opklade. H2H se trenutno samo meri u pozadini i ne utiče na odluku.</div>
    </div></body></html>'''
    subject = f"⚡ QuantBet {mode}: {len(result.new_bets)} tipova · ROI {100*analytics.roi:+.1f}% · {generated_at:%d.%m.%Y.}"
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
            server.sendmail(settings.gmail_user, [settings.email_to], message.as_string())
        return True
    except (OSError, smtplib.SMTPException) as exc:
        print(f"⚠️ Email nije poslat: {exc}")
        return False
