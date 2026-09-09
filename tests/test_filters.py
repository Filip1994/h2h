from quantbot.filters import eligibility_decision, is_allowed_match


def allowed(country: str, league_id: int, league: str) -> bool:
    return is_allowed_match(country, league, "Home FC", "Away FC", league_id=league_id)


def test_england_tiers_are_exactly_one_and_two() -> None:
    assert allowed("England", 39, "Premier League")
    assert allowed("England", 40, "Championship")
    assert not allowed("England", 41, "League One")
    assert not allowed("England", 42, "League Two")
    assert not allowed("England", 43, "National League")


def test_non_african_tier_one_and_two_are_allowed() -> None:
    assert allowed("Spain", 140, "La Liga")
    assert allowed("Spain", 141, "Segunda Division")
    assert allowed("Germany", 78, "Bundesliga")
    assert allowed("Germany", 79, "2. Bundesliga")
    assert allowed("Brazil", 71, "Serie A")
    assert allowed("Brazil", 72, "Serie B")
    assert allowed("Japan", 98, "J1 League")
    assert allowed("Japan", 99, "J2 League")


def test_tier_three_and_unknown_fail_closed() -> None:
    decision = eligibility_decision(
        "Spain", 999001, "Third Division", "Home FC", "Away FC"
    )
    assert not decision.eligible
    assert decision.reason == "UNKNOWN_LEAGUE_TIER"
    assert not allowed("Spain", 141001, "Segunda B")


def test_missing_tier_and_missing_league_id_fail_closed() -> None:
    decision = eligibility_decision(
        "England", None, "Premier League", "Home FC", "Away FC"
    )
    assert not decision.eligible
    assert decision.reason == "UNKNOWN_LEAGUE_TIER"


def test_africa_is_blocked_except_egypt_and_morocco() -> None:
    assert not allowed("Nigeria", 999101, "Premier League")
    assert not allowed("Tanzania", 999102, "Premier League")
    assert not allowed("South Africa", 999103, "Premier Soccer League")
    assert allowed("Egypt", 233, "Premier League")
    assert allowed("Egypt", 234, "Second League")
    assert allowed("Morocco", 200, "Botola Pro")
    assert allowed("Morocco", 201, "Botola 2")
    assert not allowed("Egypt", 999104, "Third Division")
    assert not allowed("Morocco", 999105, "Botola 3")


def test_youth_reserve_amateur_and_b_team_exclusions_remain_blocked() -> None:
    assert not allowed("England", 39, "U21 Premier League")
    assert not is_allowed_match(
        "Spain", "La Liga", "Real Madrid B", "Getafe", league_id=140
    )
    assert not is_allowed_match(
        "Germany", "Bundesliga", "Bayern Munich II", "Augsburg", league_id=78
    )
    assert not is_allowed_match("France", "Ligue 1", "Nice", "Lyon", league_id=61)


def test_exact_country_name_fallback_is_deterministic() -> None:
    assert is_allowed_match("England", "Premier League", "Arsenal", "Chelsea")
    assert is_allowed_match("England", "Championship", "Birmingham", "Leeds")
    assert not is_allowed_match("England", "League One", "Birmingham", "Leeds")
    assert not is_allowed_match("England", "Unknown League", "Birmingham", "Leeds")


def test_production_and_collector_share_identical_gate_outcomes() -> None:
    cases = [
        ("England", 39, "Premier League", True),
        ("England", 41, "League One", False),
        ("Spain", 999001, "Unknown League", False),
        ("Tanzania", 999002, "Premier League", False),
        ("Egypt", 233, "Premier League", True),
        ("Egypt", 999003, "Third Division", False),
        ("Morocco", 200, "Botola Pro", True),
        ("Morocco", 999004, "Botola 3", False),
    ]
    for country, league_id, league, expected in cases:
        decision = eligibility_decision(
            country, league_id, league, "Home FC", "Away FC"
        )
        collector_gate = is_allowed_match(
            country, league, "Home FC", "Away FC", league_id=league_id
        )
        assert decision.eligible is expected
        assert collector_gate is expected


def test_optional_country_exclusion_is_exact() -> None:
    assert not is_allowed_match(
        "Brazil", "Serie A", "Flamengo", "Bahia", ("brazil",), league_id=71
    )
    assert not is_allowed_match(
        "Brazilian State", "Serie A", "Flamengo", "Bahia", ("brazil",)
    )
