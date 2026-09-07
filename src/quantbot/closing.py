from __future__ import annotations

import html
import smtplib
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from .api import APIError, APIFootballClient
from .config import Settings
from .markets import extract_best_quotes
from .parsing import parse_datetime
from .storage import BetStore
from .types import Market


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _money(value: float) -> str:
    return f"{value:,.0f}".replace(",", ".")


def capture_five_minute_closing_quotes(
    settings: Settings, now: datetime | None = None
) -> int:
    """Capture one odds snapshot in the five-minute pre-kickoff window.

    The regular monitor remains responsible for settlement. This dedicated capture
    avoids confusing an earlier two-hour snapshot with the requested T-5 quote.
    """
    now_utc = (now or datetime.now(UTC)).astimezone(UTC)
    store = BetStore(settings.bets_file)
    bets = store.load()
    changed = False
    captured = 0

    for bet in bets:
        if str(bet.get("status", "")).upper() != "PENDING":
            continue
        if bet.get("closing_5m_odd") is not None:
            continue
        try:
            kickoff = parse_datetime(str(bet["kickoff"]))
            fixture_id = int(bet["event_id"])
            bookmaker_id = int(bet["bookmaker_id"])
            market = Market.parse(str(bet["market"]))
        except (KeyError, TypeError, ValueError):
            continue

        seconds_to_kickoff = (kickoff - now_utc).total_seconds()
        if not 120.0 <= seconds_to_kickoff <= 480.0:
            continue

        try:
            raw = APIFootballClient(settings).odds(fixture_id)
        except APIError as exc:
            print(f"⚠️ T-5 closing odds {bet.get('id')}: {exc}")
            continue

        quotes = extract_best_quotes(
            raw,
            bookmaker_priority=(bookmaker_id,),
            allow_any_bookmaker=False,
            captured_at=now_utc,
            only_bookmaker_id=bookmaker_id,
        )
        quote = quotes.get(market)
        if quote is None or not (
            0.0 <= quote.overround <= settings.max_market_overround
        ):
            continue

        bet["closing_5m_odd"] = round(quote.odd, 4)
        bet["closing_5m_opposite_odd"] = round(quote.opposite_odd, 4)
        bet["closing_5m_market_probability_devig"] = round(quote.devig_probability, 6)
        bet["closing_5m_odds_captured_at"] = now_utc.isoformat()
        changed = True
        captured += 1

    if changed:
        store.save(bets)
    return captured


def _row(bet: dict[str, Any]) -> str:
    result = str(bet.get("status", "—"))
    result_class = (
        "#45f0a5" if result == "WIN" else "#ff6670" if result == "LOSS" else "#f5c86b"
    )
    odd = float(bet.get("odd") or 0.0)
    closing = float(bet.get("closing_5m_odd") or bet.get("closing_odd") or 0.0)
    clv = ((odd / closing) - 1.0) * 100.0 if closing > 1.0 else None
    return f"""<tr><td style="padding:12px 10px;border-bottom:1px solid #203b5c;color:#eef7ff;"><b>{_esc(bet.get("match"))}</b><br><span style="font-size:10px;color:#7f9ab8;">{_esc(bet.get("market_display", bet.get("market")))}</span></td><td style="padding:12px 10px;border-bottom:1px solid #203b5c;">{_esc(bet.get("bookmaker", "—"))}</td><td style="padding:12px 10px;border-bottom:1px solid #203b5c;">{odd:.2f}</td><td style="padding:12px 10px;border-bottom:1px solid #203b5c;">{closing:.2f}</td><td style="padding:12px 10px;border-bottom:1px solid #203b5c;color:{result_class};font-weight:800;">{_esc(result)}</td><td style="padding:12px 10px;border-bottom:1px solid #203b5c;">{_money(float(bet.get("profit") or 0))} RSD</td><td style="padding:12px 10px;border-bottom:1px solid #203b5c;">{("+" if clv is not None and clv >= 0 else "") + f"{clv:.2f}%" if clv is not None else "—"}</td></tr>"""


def build_closing_day_email(
    settings: Settings, day: str, bets: list[dict[str, Any]]
) -> tuple[str, str]:
    selected = [
        b
        for b in bets
        if str(b.get("signal_source", ""))
        in {"DAILY_BULLETIN", "INTRADAY_ALERT"}
    ]
    selected.sort(key=lambda b: str(b.get("kickoff", "")))
    rows = "".join(_row(b) for b in selected)
    total_profit = sum(float(b.get("profit") or 0.0) for b in selected)
    wins = sum(str(b.get("status", "")).upper() == "WIN" for b in selected)
    losses = sum(str(b.get("status", "")).upper() == "LOSS" for b in selected)
    title = f"📘 QuantBet Closing Day · {day} · {len(selected)} signala"
    body = f"""<!doctype html><html><body style="margin:0;background:#050b14;color:#eef7ff;font-family:Arial,Helvetica,sans-serif;"><table width="100%" cellspacing="0" cellpadding="0" style="background:#050b14;"><tr><td align="center" style="padding:24px 10px;"><table width="760" cellspacing="0" cellpadding="0" style="max-width:760px;width:100%;background:#081321;border:1px solid #193451;border-radius:18px;overflow:hidden;"><tr><td style="padding:24px;background:#0b1929;border-bottom:1px solid #193451;"><div style="font-size:10px;letter-spacing:3px;color:#5f87ab;font-weight:800;">QUANTBET // CLOSING DAY</div><div style="font-size:24px;font-weight:900;margin-top:6px;">📘 FINAL RESULTS</div><div style="font-size:12px;color:#7f9ab8;margin-top:6px;">{_esc(day)} · all bulletin + intraday signals</div></td></tr><tr><td style="padding:18px 20px;"><table width="100%" cellspacing="0" cellpadding="0"><tr><td style="padding:12px;background:#0d1a2b;">SIGNALS<br><b>{len(selected)}</b></td><td style="padding:12px;background:#0d1a2b;">W / L<br><b>{wins} / {losses}</b></td><td style="padding:12px;background:#0d1a2b;">DAY P&amp;L<br><b>{_money(total_profit)} RSD</b></td></tr></table></td></tr><tr><td style="padding:0 20px 24px;"><table width="100%" cellspacing="0" cellpadding="0" style="font-size:11px;border-collapse:collapse;"><tr><th align="left" style="padding:10px;color:#7f9ab8;border-bottom:1px solid #203b5c;">MATCH / MARKET</th><th align="left" style="padding:10px;color:#7f9ab8;border-bottom:1px solid #203b5c;">BOOK</th><th align="left" style="padding:10px;color:#7f9ab8;border-bottom:1px solid #203b5c;">SIGNAL</th><th align="left" style="padding:10px;color:#7f9ab8;border-bottom:1px solid #203b5c;">T-5</th><th align="left" style="padding:10px;color:#7f9ab8;border-bottom:1px solid #203b5c;">RESULT</th><th align="left" style="padding:10px;color:#7f9ab8;border-bottom:1px solid #203b5c;">P&amp;L</th><th align="left" style="padding:10px;color:#7f9ab8;border-bottom:1px solid #203b5c;">CLV</th></tr>{rows or '<tr><td colspan="7" style="padding:20px;color:#7f9ab8;">No qualifying signals for this day.</td></tr>'}</table></td></tr><tr><td style="padding:14px 20px;background:#06101c;color:#4f6d89;font-size:9px;text-align:center;letter-spacing:1px;">Signal odds = quote captured when the bulletin/alert was generated · T-5 = dedicated five-minute closing snapshot.</td></tr></table></td></tr></table></body></html>"""
    return title, body


def send_html_email(subject: str, html_body: str, settings: Settings) -> bool:
    if not settings.gmail_user or not settings.gmail_app_pass or not settings.email_to:
        print(
            "⚠️ Gmail secrets nisu podešeni; closing report je sačuvan bez slanja emaila."
        )
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
        print(f"⚠️ Closing email nije poslat: {exc}")
        return False
