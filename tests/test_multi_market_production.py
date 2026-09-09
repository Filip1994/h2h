from quantbot.storage import BetStore


def test_blocking_is_scoped_to_fixture_and_market(settings) -> None:
    store = BetStore(settings.bets_file)
    store.save(
        [
            {
                "id": "fixture-1-home",
                "event_id": 1,
                "market": "HOME",
                "status": "PENDING",
            }
        ]
    )

    appended = store.append_unique_fixtures(
        [
            {
                "id": "fixture-1-draw",
                "event_id": 1,
                "market": "DRAW",
                "status": "PENDING",
            },
            {
                "id": "fixture-1-home-duplicate",
                "event_id": 1,
                "market": "HOME",
                "status": "PENDING",
            },
        ]
    )

    assert [item["id"] for item in appended] == ["fixture-1-draw"]
