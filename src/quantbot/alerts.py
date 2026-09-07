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


def _bookmaker_domain(name: str) -> str:
    key = name.casefold().replace(" ", "")
    known = {
        "bet365": "bet365.com",
        "1xbet": "1xbet.com",
        "betfair": "betfair.com",
        "pinnacle": "pinnacle.com",
        "unibet": "unibet.com",
        "betsson": "betsson.com",
        "williamhill": "williamhill.com",
        "betvictor": "betvictor.com",
        "888sport": "888sport.com",
        "mozzart": "mozzartbet.com",
        "meridian": "meridianbet.com",
        "maxbet": "maxbet.rs",
        "soccerbet": "soccerbet.rs",
        "admiralbet": "admiralbet.rs",
        "balkanbet": "balkanbet.rs",
        "superbet": "superbet.rs",
    }
    for token, domain in known.items():
        if token in key:
            return domain
    return ""


def bookmaker_logo_url(name: str) -> str:
    domain = _bookmaker_domain(name)
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=64" if domain else ""


def _skip_url(repository: str, bet_id: str) -> str:
    query = urlencode({"title": f"SKIP_{bet_id}", "body": "Automatski zahtev: prebaci navedeni PENDING tip u SKIPPED status."})
    return f"https://github.com/{repository}/issues/new?{query}"


def is_strong_signal(bet: dict[str, Any], settings: Settings) -> bool:
    return (
        float(bet.get("expected_value") or 0.0) >= settings.strong_signal_min_ev
        and float(bet.get("probability_edge") or 0.0) >= settings.strong_signal_min_edge
        and float(bet.get("stake") or 0.0) >= settings.strong_signal_min_stake
    )


def build_strong_signal_email(result: GenerationResult, settings: Settings, generated_at: datetime) -> tuple[str, str]:
    strong = [bet for bet in result.new_bets if is_strong_signal(bet, settings)]
    cards: list[str] = []
    for bet in strong:
        logo = bookmaker_logo_url(str(bet.get("bookmaker") or ""))
        logo_html = f'<img src="{_esc(logo)}" width="28" height="28" alt="" style="vertical-align:middle;border-radius:6px;margin-right:8px;">' if logo else ""
        kickoff = str(bet.get("kickoff", ""))
        cards.append(f'''<table width="100%" cellspacing="0" cellpadding="0" style="background:#0d1a2b;border:1px solid #244c67;border-radius:16px;margin:0 0 14px;"><tr><td style="padding:18px;"><div style="font-size:10px;letter-spacing:2px;color:#ffbd5c;font-weight:900;">🚨 STRONG SIGNAL</div><div style="font-size:18px;font-weight:900;color:#fff;margin-top:6px;">⚽ {_esc(bet.get("match"))}</div><div style="font-size:12px;color:#7f9ab8;margin:6px 0 14px;">{_esc(bet.get("league"))} · kickoff {_esc(kickoff)}</div><div style="font-size:13px;color:#c4d7e8;">{_esc(bet.get("market_display", bet.get("market")))} · <b style="color:#45d9ff;">@ {float(bet.get("odd") or 0):.2f}</b></div><div style="margin-top:10px;font-size:12px;color:#a9bfd5;">MODEL {100*float(bet.get("model_probability") or 0):.1f}% · DECISION {100*float(bet.get("decision_probability") or 0):.1f}% · EV <b style="color:#45f0a5;">{100*float(bet.get("expected_value") or 0):+.1f}%</b> · EDGE <b style="color:#45f0a5;">{100*float(bet.get("probability_edge") or 0):+.1f}pp</b></div><div style="margin-top:14px;padding-top:12px;border-top:1px solid #203b5c;">{logo_html}<b style="color:#eef7ff;">{_esc(bet.get("bookmaker") or "Bookmaker")}</b> · <b style="color:#45f0a5;">{_money(float(bet.get("stake") or 0))} RSD</b></div><div style="margin-top:12px;"><a href="{_esc(_skip_url(settings.github_repository, str(bet.get("id"))))}" style="color:#ff8a9a;text-decoration:none;font-size:10px;font-weight:800;">↳ PRESKOČI TIP</a></div></td></tr></table>''')
    body = f'''<!doctype html><html><body style="margin:0;background:#050b14;font-family:Arial,Helvetica,sans-serif;color:#eef7ff;"><table width="100%" cellspacing="0" cellpadding="0"><tr><td align="center" style="padding:24px 10px;"><table width="680" cellspacing="0" cellpadding="0" style="max-width:680px;width:100%;background:#081321;border:1px solid #193451;border-radius:20px;overflow:hidden;"><tr><td style="padding:26px 24px;background:#0b1929;border-bottom:1px solid #193451;"><div style="font-size:10px;letter-spacing:3px;color:#5f87ab;font-weight:800;">QUANTBET // INTRADAY INTELLIGENCE</div><div style="font-size:25px;font-weight:900;margin-top:7px;">🚨 STRONG SIGNAL ALERT</div><div style="font-size:12px;color:#7f9ab8;margin-top:7px;">{generated_at:%d.%m.%Y · %H:%M} · T-6H SCANNER · {len(strong)} QUALIFIED</div></td></tr><tr><td style="padding:18px 20px;">{''.join(cards) or '<div style="padding:18px;color:#7f9ab8;">No strong signal crossed the alert threshold.</div>'}</td></tr><tr><td style="padding:14px 20px 22px;color:#718aa4;font-size:10px;line-height:1.7;">Alert threshold: EV ≥ 10%, probability edge ≥ 5pp, stake ≥ 300 RSD. Existing ledger dedupe remains authoritative; this alert does not change model selection.</td></tr></table></td></tr></table></body></html>'''
    subject = f"🚨 QuantBet STRONG SIGNAL: {len(strong)} · {generated_at:%H:%M}"
    return subject, body


def send_strong_signal_email(subject: str, html_body: str, settings: Settings) -> bool:
    if not settings.gmail_user or not settings.gmail_app_pass or not settings.email_to:
        print("⚠️ Gmail secrets nisu podešeni; strong-signal alert je sačuvan bez slanja emaila.")
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
        print(f"⚠️ Strong-signal email nije poslat: {exc}")
        return False
