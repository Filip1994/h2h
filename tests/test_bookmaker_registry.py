from quantbot.bookmaker_registry import bookmaker_identity


def test_verified_registry_returns_logo_for_audited_bookmaker():
    identity = bookmaker_identity(8, "Bet365")
    assert identity["bookmaker"] == "Bet365"
    assert identity["logo_verified"] is True
    assert identity["logo_url"]
    assert identity["logo_source"]


def test_unknown_bookmaker_never_gets_guessed_logo():
    identity = bookmaker_identity(9999, "Unknown Book")
    assert identity["bookmaker"] == "Unknown Book"
    assert identity["logo_verified"] is False
    assert identity["logo_url"] is None
