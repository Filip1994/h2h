from pathlib import Path

WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "daily.yml"


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_normal_push_precedes_send() -> None:
    text = _workflow()
    assert "for attempt in 1 2 3; do" in text
    assert "if git push; then" in text
    assert "git fetch origin main" in text
    assert "git rebase origin/main" in text
    assert text.index("git push") < text.index("Send committed bulletin")


def test_reconciliation_is_bounded() -> None:
    text = _workflow()
    assert 'if [ "$attempt" -eq 3 ]; then' in text
    assert "Unable to push reconciled ledger after 3 attempts" in text


def test_rebase_conflict_aborts_before_send() -> None:
    text = _workflow()
    assert "git rebase --abort || true" in text
    assert "Ledger reconciliation conflict; bulletin will not be sent." in text
    assert text.index("git rebase --abort") < text.index("Send committed bulletin")


def test_no_force_push() -> None:
    text = _workflow()
    assert "git push --force" not in text
    assert "git push -f" not in text


def test_success_marker_follows_email() -> None:
    text = _workflow()
    send = text.index("Send committed bulletin")
    marker = text.index("Write canonical success marker")
    assert send < marker
    assert "python main.py send-report" in text[send:marker]


def test_daily_schedule_is_continuous_and_not_hourly_business_window() -> None:
    text = _workflow()
    assert 'cron: "*/30 * * * *"' in text
    assert 'cron: "*/5 * * * *"' not in text
    assert "06-23" not in text


def test_shared_ledger_lock_is_job_level_not_workflow_level() -> None:
    text = _workflow()
    assert "jobs:\n  generate:\n    concurrency:" in text
    assert "group: quantbet-ledger" in text
    assert "# Do not put the whole workflow in the shared ledger concurrency group." in text


def test_guard_is_rechecked_after_lock_to_prevent_duplicate_bulletins() -> None:
    text = _workflow()
    assert "Re-check today's bulletin health after acquiring ledger lock" in text
    assert "python tools/bulletin_health.py --guard" in text
    assert "generate=false" in text
    gate = text.index("id: gate")
    generation = text.index("Generate committed bulletin source")
    assert gate < generation


def test_manual_dispatch_is_only_a_force_override() -> None:
    text = _workflow()
    assert 'FORCE_BULLETIN: ${{ github.event_name == \'workflow_dispatch\' && inputs.force || false }}' in text
    assert 'if [ "$FORCE_BULLETIN" = "true" ]; then' in text


def test_scheduled_path_does_not_depend_on_manual_dispatch() -> None:
    text = _workflow()
    schedule = text.index("schedule:")
    dispatch = text.index("workflow_dispatch:")
    assert schedule < text.index("jobs:")
    assert dispatch < schedule
    assert "Force a new bulletin" in text
