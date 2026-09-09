from quantbot.monitor import VOID_STATUSES


def test_postponed_fixture_is_deterministically_void():
    assert "PST" in VOID_STATUSES


def test_finished_and_review_statuses_remain_separate_from_void():
    assert not {"FT", "AET", "PEN"} & VOID_STATUSES
    assert not {"AWD", "WO"} & VOID_STATUSES
