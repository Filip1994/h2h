import json

import pytest

from quantbot.quota import (
    GlobalQuotaExceeded,
    GlobalQuotaGovernor,
    GlobalQuotaStateError,
)


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


def test_existing_ledger_capacity_cannot_be_overwritten(tmp_path) -> None:
    path = tmp_path / "quota.json"
    governor = GlobalQuotaGovernor(path, daily_capacity=3, safety_reserve=1)
    reservation = governor.reserve("daily", "fixtures")
    governor.consume(reservation)

    mismatched = GlobalQuotaGovernor(path, daily_capacity=4, safety_reserve=1)
    with pytest.raises(GlobalQuotaStateError, match="CONFIG_MISMATCH"):
        mismatched.snapshot()

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["daily_capacity"] == 3
    assert payload["consumed"] == 1


def test_existing_ledger_reserve_cannot_be_overwritten(tmp_path) -> None:
    path = tmp_path / "quota.json"
    governor = GlobalQuotaGovernor(path, daily_capacity=10, safety_reserve=2)
    governor.reserve("daily", "fixtures")

    mismatched = GlobalQuotaGovernor(path, daily_capacity=10, safety_reserve=3)
    with pytest.raises(GlobalQuotaStateError, match="CONFIG_MISMATCH"):
        mismatched.reserve("watchlist", "odds")


def test_corrupt_existing_ledger_fails_closed(tmp_path) -> None:
    path = tmp_path / "quota.json"
    path.write_text("{not-json", encoding="utf-8")
    governor = GlobalQuotaGovernor(path, daily_capacity=10, safety_reserve=2)
    with pytest.raises(GlobalQuotaStateError, match="STATE_INVALID"):
        governor.snapshot()
