# fmt: off
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
from .presentation import (
    clv_label,
    market_display,
    odds_lifecycle,
    skip_reason,
    status_display,
)


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _money(value: float) -> str:
    return f"{value:,.0f}".replace(",", ".")


def _bookmaker_domain(name: str) -> str:
    key = name.casefold().replace(" ", "")
    known = {
        "bet365": "bet365.com", "1xbet": "1xbet.com", "betfair": "betfair.com",
        "pinnacle": "pinnacle.com", "unibet": "unibet.com", "betsson": "betsson.com",
        "williamhill": "williamhill.com", "betvictor": "betvictor.com", "888sport": "888sport.com",
        "mozzart": "mozzartbet.com", "meridian": "meridianbet.com", "maxbet": "maxbet.rs",
        "soccerbet": "soccerbet.rs", "admiralbet": "admiralbet.rs", "balkanbet": "balkanbet.rs",
        "superbet": "superbet.rs",
    }
    for token, domain in known.items():
        if token in key:
            return domain
    return ""


def _bookmaker_logo(name: str) -> str:
    domain = _bookmaker_domain(name)
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=64" if domain else ""


def _skip_url(repository: str, bet_id: str) -> str:
    query = urlencode({"title": f"SKIP_{bet_id}", "body": "Automatski zahtev: prebaci navedeni PENDING tip u SKIPPED status."})
    return f"https://github.com/{repository}/issues/new?{query}"


def _odds_lifecycle_html(bet: dict[str, Any]) -> str:
    life = odds_lifecycle(bet)

    def fmt(value: Any) -> str:
        return f"{float(value):.2f}" if value is not None else "—"

    return (
        f"OPENING {fmt(life['opening'])} → PICK {fmt(life['pick'])} → "
        f"CLOSING {fmt(life['closing'])}"
    )


def build_email(result: GenerationResult, settings: Settings, generated_at: datetime) -> tuple[str, str]:
    analytics = result.analytics
    mode = "PAPER" if settings.paper_mode else "LIVE"
    cards: list[str] = []
    for bet in result.new_bets:
        kickoff = datetime.fromisoformat(str(bet["kickoff"])).astimezone(settings.timezone)
        logo = _bookmaker_logo(str(bet.get("bookmaker") or ""))
        logo_html = f'<img src="{_esc(logo)}" width="24" height="24" alt="" style="vertical-align:middle;border-radius:5px;margin-right:7px;">' if logo else ""
        skip = skip_reason(bet)
        skip_html = f'<div style="font-size:10px;color:#ffd166;margin-top:7px;">SKIP REASON: {_esc(skip)}</div>' if skip else ""
        cards.append(f'''<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#0d1a2b;border:1px solid #203b5c;border-radius:14px;margin:0 0 14px;overflow:hidden;"><tr><td style="padding:16px 18px 8px;"><div style="font-size:16px;font-weight:800;color:#eef7ff;">⚽ {_esc(bet["match"])}</div><div style="font-size:11px;color:#7f9ab8;margin-top:5px;">{_esc(bet["league"])} · KICKOFF {kickoff:%H:%M}</div></td></tr><tr><td style="padding:6px 18px 12px;"><span style="font-size:9px;letter-spacing:1px;color:#6f8eac;">MARKET</span><br><b style="font-size:15px;color:#fff;">{_esc(market_display(bet.get("market_display") or bet.get("market")))}</b></td></tr><tr><td style="padding:0 18px 8px;color:#a9bfd5;font-size:11px;">{_esc(_odds_lifecycle_html(bet))} · CLV {clv_label(bet.get("clv_odds_pct"))}</td></tr><tr><td style="padding:0 18px 12px;color:#a9bfd5;font-size:12px;">MODEL <b style="color:#eef7ff;">{100 * float(bet["model_probability"]):.1f}%</b> · DECISION <b style="color:#eef7ff;">{100 * float(bet["decision_probability"]):.1f}%</b> · EV <b style="color:#45f0a5;">{100 * float(bet["expected_value"]):+.1f}%</b></td></tr><tr><td style="padding:10px 18px;background:#0a1524;border-top:1px solid #203b5c;">{logo_html}<b style="color:#eef7ff;">{_esc(bet.get("bookmaker") or "Bookmaker")}</b> <span style="color:#45f0a5;font-size:17px;font-weight:800;">{_money(float(bet["stake"]))} RSD</span> <span style="color:#718aa4;font-size:11px;">· {_esc(mode)} · STATUS {status_display(bet.get("status"))}</span>{skip_html}</td></tr><tr><td style="padding:10px 18px 14px;"><a href="{_esc(_skip_url(settings.github_repository, str(bet["id"]))) }" style="color:#ff8a9a;text-decoration:none;font-size:10px;font-weight:700;">↳ PRESKOČI TIP</a></td></tr></table>''')
    picks_html = "".join(cards) or '<div style="background:#0d1a2b;border:1px solid #203b5c;border-radius:14px;padding:18px;color:#7f9ab8;">NO QUALIFIED PICKS · FILTERS HELD.</div>'
    roi_color = "#45f0a5" if analytics.roi >= 0 else "#ff5f6d"
    cutoff = generated_at.astimezone(UTC).isoformat()
    body = f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;background:#050b14;font-family:Arial,Helvetica,sans-serif;color:#eef7ff;"><table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#050b14;"><tr><td align="center" style="padding:24px 10px;"><table role="presentation" width="680" cellspacing="0" cellpadding="0" style="max-width:680px;width:100%;background:#081321;border:1px solid #193451;border-radius:20px;overflow:hidden;"><tr><td style="padding:26px 24px 20px;background:#0b1929;border-bottom:1px solid #1c3855;"><div style="font-size:10px;letter-spacing:3px;color:#5f87ab;font-weight:800;">QUANTBET // INTELLIGENCE FEED</div><div style="font-size:25px;font-weight:900;margin-top:7px;">⚡ DAILY BULLETIN</div><div style="margin-top:7px;font-size:12px;color:#7f9ab8;">{generated_at:%d.%m.%Y · %H:%M} · <span style="color:#45d9ff;">{_esc(mode)} MODE</span> · {len(result.new_bets)} NEW SIGNALS</div></td></tr><tr><td style="padding:18px 20px;"><table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td width="25%" style="padding:12px 6px;background:#0d1a2b;border:1px solid #203b5c;text-align:center;"><div style="font-size:9px;color:#6f8eac;letter-spacing:1px;">BANK</div><b style="font-size:15px;">{_money(analytics.current_bank)} RSD</b></td><td width="25%" style="padding:12px 6px;background:#0d1a2b;border:1px solid #203b5c;text-align:center;"><div style="font-size:9px;color:#6f8eac;letter-spacing:1px;">ROI</div><b style="font-size:15px;color:{roi_color};">{100 * analytics.roi:+.2f}%</b></td><td width="25%" style="padding:12px 6px;background:#0d1a2b;border:1px solid #203b5c;text-align:center;"><div style="font-size:9px;color:#6f8eac;letter-spacing:1px;">WIN RATE</div><b style="font-size:15px;">{100 * analytics.win_rate:.1f}%</b></td><td width="25%" style="padding:12px 6px;background:#0d1a2b;border:1px solid #203b5c;text-align:center;"><div style="font-size:9px;color:#6f8eac;letter-spacing:1px;">DRAWDOWN</div><b style="font-size:15px;">{100 * analytics.current_drawdown:.1f}%</b></td></tr></table></td></tr><tr><td style="padding:0 20px 6px;"><div style="font-size:11px;letter-spacing:2px;color:#5f87ab;font-weight:800;">TODAY'S SIGNALS</div></td></tr><tr><td style="padding:8px 20px 12px;">{picks_html}</td></tr><tr><td style="padding:12px 20px 22px;color:#718aa4;font-size:10px;line-height:1.7;">MODEL → CALIBRATION → MARKET → RISK. No signal means no bet. Data cutoff: {_esc(cutoff)}.</td></tr><tr><td style="padding:13px 20px;background:#06101c;border-top:1px solid #193451;color:#4f6d89;font-size:9px;text-align:center;letter-spacing:1px;">QUANTBET · TRANSPARENT PAPER VALIDATION · ALL STAKES IN RSD</td></tr></table></td></tr></table></body></html>'''
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
            server.sendmail(settings.gmail_user, [settings.email_to], message.as_string())
        return True
    except (OSError, smtplib.SMTPException) as exc:
        print(f"⚠️ Email nije poslat: {exc}")
        return False
# fmt: on
