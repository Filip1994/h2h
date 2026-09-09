from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_intraday_scanner_is_24_7_and_preserves_writer_concurrency():
    workflow = (ROOT / ".github/workflows/intraday.yml").read_text(encoding="utf-8")
    assert 'cron: "*/30 * * * *"' in workflow
    assert 'timezone: "Europe/Belgrade"' in workflow
    assert "group: quantbet-ledger" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "INTRADAY_MODE: \"true\"" in workflow


def test_intraday_run_persists_truthful_health_and_does_not_change_threshold_contract():
    workflow = (ROOT / ".github/workflows/intraday.yml").read_text(encoding="utf-8")
    health = (ROOT / "tools/intraday_health.py").read_text(encoding="utf-8")
    assert "intraday_health.json" in workflow
    assert "--run-status" in workflow
    assert '"ERROR"' in health
    assert '"RUNNING"' in health
    assert '"NO SIGNALS"' in health
    assert '"Europe/Belgrade"' in health
    assert 'STRONG_SIGNAL_MIN_EV: "0.10"' in workflow
    assert 'STRONG_SIGNAL_MIN_EDGE_PP: "0.05"' in workflow


def test_intraday_workflow_keeps_accounting_outputs_separate():
    workflow = (ROOT / ".github/workflows/intraday.yml").read_text(encoding="utf-8")
    for filename in (
        "bets.json",
        "intraday_alerts.json",
        "intraday_watchlist_state.json",
        "strong_signals.json",
        "intraday_health.json",
    ):
        assert filename in workflow
