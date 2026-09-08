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
