from datetime import UTC, datetime

from quantbot.reporting import build_email


def test_build_email_uses_futuristic_inline_layout(settings) -> None:
    class Analytics:
        roi = 0.042
        current_bank = 50210.0
        win_rate = 0.75
        completed_count = 4
        current_drawdown = 0.01

    class Result:
        analytics = Analytics()
        api_requests = 12
        new_bets = ({
            "id": "123_OVER_2_5",
            "kickoff": "2026-09-07T18:00:00+00:00",
            "match": "Team A vs Team B",
            "league": "Test League",
            "market_display": "Ukupno Golova - Više 2.5",
            "odd": 2.10,
            "model_probability": 0.61,
            "decision_probability": 0.59,
            "expected_value": 0.239,
            "stake": 450,
        },)

    subject, body = build_email(Result(), settings, datetime(2026, 9, 7, 10, 0, tzinfo=UTC))
    assert "DAILY BULLETIN" in body
    assert "QUANTBET // INTELLIGENCE FEED" in body
    assert "Team A vs Team B" in body
    assert "450 RSD" in body
    assert "NO QUALIFIED PICKS" not in body
    assert subject.startswith("⚡ QuantBet PAPER:")
