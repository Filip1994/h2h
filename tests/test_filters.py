from quantbot.filters import is_allowed_match


def test_excludes_youth_reserve_and_amateur() -> None:
    assert not is_allowed_match("England", "U21 Premier League", "Arsenal", "Chelsea")
    assert not is_allowed_match("Spain", "La Liga", "Real Madrid B", "Getafe")
    assert not is_allowed_match(
        "Germany", "Regionalliga", "Bayern Munich II", "Augsburg"
    )
    assert not is_allowed_match("France", "Reserve League", "Nice", "Lyon")
    assert not is_allowed_match("USA", "MLS Next Pro", "Austin", "Dallas")


def test_does_not_treat_ii_inside_word_as_reserve() -> None:
    assert is_allowed_match("Finland", "Veikkausliiga", "Ilves", "HJK")
    assert is_allowed_match("England", "Championship", "Birmingham", "Leeds")


def test_optional_country_exclusion_is_exact() -> None:
    assert not is_allowed_match("Brazil", "Serie A", "Flamengo", "Bahia", ("brazil",))
    assert is_allowed_match(
        "Brazilian State", "Serie A", "Flamengo", "Bahia", ("brazil",)
    )


def test_tier_one_and_two_are_allowed() -> None:
    assert is_allowed_match("England", "Premier League", "Arsenal", "Chelsea")
    assert is_allowed_match("England", "Championship", "Leeds", "Birmingham")
    assert is_allowed_match("Italy", "Serie A", "Inter", "Milan")
    assert is_allowed_match("Italy", "Serie B", "Bari", "Palermo")


def test_tier_three_four_and_five_are_blocked() -> None:
    assert not is_allowed_match(
        "England", "National League", "York City", "Oldham Athletic"
    )
    assert not is_allowed_match("England", "League Two", "AFC Wimbledon", "Crewe")
    assert not is_allowed_match("Germany", "3. Liga", "Dynamo Dresden", "Aue")
    assert not is_allowed_match("Spain", "Primera División RFEF - Group 1", "A", "B")


def test_unknown_and_missing_tier_are_blocked() -> None:
    assert not is_allowed_match("England", "Some Unknown League", "A", "B")
    assert not is_allowed_match(None, None, "A", "B")
    assert not is_allowed_match(
        "Nowhere", "Provider League", "A", "B", league_tier=None
    )


def test_provider_tier_is_deterministic() -> None:
    assert is_allowed_match("Nowhere", "Provider League", "A", "B", league_tier=1)
    assert is_allowed_match("Nowhere", "Provider League", "A", "B", league_tier=2)
    assert not is_allowed_match("Nowhere", "Provider League", "A", "B", league_tier=3)
    assert not is_allowed_match(
        "Nowhere", "Provider League", "A", "B", league_tier="unknown"
    )
