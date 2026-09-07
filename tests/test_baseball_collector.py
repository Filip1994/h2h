from quantbot.baseball.collector import compact_odds


def test_compact_odds_keeps_local_bookmakers_and_target_markets() -> None:
    payload = [
        {
            "bookmakers": [
                {
                    "name": "bet365",
                    "bets": [
                        {
                            "name": "Moneyline",
                            "values": [{"value": "Home", "odd": "1.90"}],
                        },
                        {
                            "name": "Player Strikeouts",
                            "values": [{"value": "Over 5.5", "odd": "1.95"}],
                        },
                    ],
                },
                {
                    "name": "OtherBook",
                    "bets": [
                        {
                            "name": "Moneyline",
                            "values": [{"value": "Away", "odd": "2.10"}],
                        },
                        {
                            "name": "Unrelated",
                            "values": [{"value": "X", "odd": "9.00"}],
                        },
                    ],
                },
            ]
        }
    ]
    result = compact_odds(payload)
    assert "bet365" in result["bookmaker_names"]
    assert "OtherBook" in result["bookmaker_names"]
    bet365 = next(item for item in result["bookmakers"] if item["name"] == "bet365")
    assert {item["name"] for item in bet365["markets"]} == {
        "Moneyline",
        "Player Strikeouts",
    }
    other = next(item for item in result["bookmakers"] if item["name"] == "OtherBook")
    assert [item["name"] for item in other["markets"]] == ["Moneyline"]
