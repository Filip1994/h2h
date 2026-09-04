from datetime import UTC, datetime

import pytest

from quantbot.markets import extract_best_quotes
from quantbot.types import Market


def bookmaker(
    bookmaker_id: int, over: float, under: float, yes: float, no: float
) -> dict:
    return {
        "id": bookmaker_id,
        "name": f"BM {bookmaker_id}",
        "bets": [
            {
                "name": "Goals Over/Under",
                "values": [
                    {"value": "Over 2.5", "odd": str(over)},
                    {"value": "Under 2.5", "odd": str(under)},
                ],
            },
            {
                "name": "Both Teams Score",
                "values": [
                    {"value": "Yes", "odd": str(yes)},
                    {"value": "No", "odd": str(no)},
                ],
            },
        ],
    }


def test_extracts_best_paired_quote_and_devigs() -> None:
    raw = [
        {
            "bookmakers": [
                bookmaker(8, 1.85, 2.00, 1.75, 2.10),
                bookmaker(11, 1.90, 1.95, 1.70, 2.20),
            ]
        }
    ]
    quotes = extract_best_quotes(
        raw,
        bookmaker_priority=(8, 11),
        allow_any_bookmaker=False,
        captured_at=datetime.now(UTC),
    )
    over = quotes[Market.OVER_25]
    assert over.bookmaker_id == 11
    assert over.odd == 1.90
    assert over.opposite_odd == 1.95
    expected = (1 / 1.90) / ((1 / 1.90) + (1 / 1.95))
    assert over.devig_probability == pytest.approx(expected)


def test_requires_both_sides_of_market() -> None:
    raw = [
        {
            "bookmakers": [
                {
                    "id": 8,
                    "name": "BM",
                    "bets": [
                        {
                            "name": "Goals Over/Under",
                            "values": [{"value": "Over 2.5", "odd": "1.9"}],
                        }
                    ],
                }
            ]
        }
    ]
    quotes = extract_best_quotes(
        raw,
        bookmaker_priority=(8,),
        allow_any_bookmaker=False,
        captured_at=datetime.now(UTC),
    )
    assert Market.OVER_25 not in quotes
