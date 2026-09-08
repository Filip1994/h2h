from pathlib import Path


WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "settlement-watchdog.yml"


def test_watchdog_keeps_monitor_as_only_settlement_executor():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "gh workflow run monitor.yml --ref main" in text
    assert "python tools/settle_alerts.py" not in text
    assert "python main.py monitor" not in text


def test_watchdog_has_health_gate_and_recovery_verification():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "python tools/settlement_health.py --max-age-minutes 30" in text
    assert "recovery_needed" in text
    assert "Recovery monitor run failed." in text
    assert "Recovery monitor did not complete within 6 minutes." in text


def test_watchdog_preserves_separate_concurrency_and_monitor_is_responsible_for_ledger_lock():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert 'group: quantbet-settlement-watchdog' in text
    assert 'contents: read' in text
