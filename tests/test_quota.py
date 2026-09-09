from quantbot.quota import GlobalQuotaExceeded, GlobalQuotaGovernor


def test_global_quota_reserve_and_consume_reconcile(tmp_path) -> None:
    governor = GlobalQuotaGovernor(
        tmp_path / "quota.json", daily_capacity=3, safety_reserve=1
    )
    first = governor.reserve("daily", "fixtures")
    second = governor.reserve("watchlist", "odds")
    snapshot = governor.snapshot()
    assert snapshot["reserved"] == 2
    assert snapshot["remaining_unallocated"] == 1
    try:
        governor.reserve("daily", "odds")
    except GlobalQuotaExceeded:
        pass
    else:
        raise AssertionError("protected reserve must not be consumed by optional work")
    governor.consume(first)
    governor.consume(second)
    snapshot = governor.snapshot()
    assert snapshot["consumed"] == 2
    assert snapshot["reserved"] == 0
    assert snapshot["remaining_unallocated"] == 1
    assert snapshot["consumed_by_workflow"] == {"daily": 1, "watchlist": 1}
