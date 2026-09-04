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
