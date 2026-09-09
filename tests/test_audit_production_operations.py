from tools.audit_production_operations import count_state_outcomes


def test_count_state_outcomes_returns_integer_for_string_outcomes():
    fixtures = {
        "1": {"last_outcome": "WIN"},
        "2": {"last_outcome": "LOSS"},
        "3": {"last_outcome": ""},
        "4": {"last_outcome": None},
        "5": {"status": "PENDING"},
        "6": "malformed",
    }
    result = count_state_outcomes(fixtures)
    assert result == 2
    assert isinstance(result, int)


def test_count_state_outcomes_handles_non_mapping_input():
    assert count_state_outcomes(None) == 0
    assert count_state_outcomes([]) == 0
