import json
from pathlib import Path

from tools.build_public_current_odds import build


def test_current_odds_uses_latest_pre_kickoff_exact_bookmaker(tmp_path: Path) -> None:
    (tmp_path / "bets.json").write_text(
        json.dumps(
            [
                {
                    "event_id": 10,
                    "market": "OVER_2_5",
                    "bookmaker_id": 8,
                    "bookmaker": "Bet365",
                    "status": "PENDING",
                }
            ]
        )
    )
    (tmp_path / "strong_signals.json").write_text("[]")
    data = tmp_path / "data"
    data.mkdir()
    (data / "market_timing_snapshots.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "fixture_id": 10,
                        "market": "OVER_2_5",
                        "bookmaker_id": 8,
                        "bookmaker": "Bet365",
                        "odd": 2.1,
                        "captured_at": "2026-09-09T10:00:00+00:00",
                        "kickoff": "2026-09-09T12:00:00+00:00",
                        "observation_id": "old",
                    }
                ),
                json.dumps(
                    {
                        "fixture_id": 10,
                        "market": "OVER_2_5",
                        "bookmaker_id": 11,
                        "bookmaker": "1xBet",
                        "odd": 2.5,
                        "captured_at": "2026-09-09T11:00:00+00:00",
                        "kickoff": "2026-09-09T12:00:00+00:00",
                        "observation_id": "wrong-book",
                    }
                ),
                json.dumps(
                    {
                        "fixture_id": 10,
                        "market": "OVER_2_5",
                        "bookmaker_id": 8,
                        "bookmaker": "Bet365",
                        "odd": 2.2,
                        "captured_at": "2026-09-09T11:30:00+00:00",
                        "kickoff": "2026-09-09T12:00:00+00:00",
                        "observation_id": "new",
                    }
                ),
            ]
        )
    )
    result = build(tmp_path)
    item = result["items"][0]
    assert item["current_odds"] == 2.2
    assert item["current_observation_id"] == "new"
    assert item["bookmaker_id"] == 8
