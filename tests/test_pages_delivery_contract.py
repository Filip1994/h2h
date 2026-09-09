from pathlib import Path

PAGES = Path(__file__).parents[1] / ".github" / "workflows" / "pages.yml"


EXPECTED_PRODUCERS = {
    "QuantBet intraday strong-signal scanner",
    "QuantBet adaptive watchlist monitor",
    "Monitor odds and settle ledgers",
    "QuantBet T-5 closing odds capture",
    "QuantBet CLV persistence",
    "Daily QuantBet bulletin",
    "QuantBet closing-day bulletin",
    "Skip pending bet",
}


def test_pages_covers_all_public_data_producers():
    text = PAGES.read_text(encoding="utf-8")
    for producer in EXPECTED_PRODUCERS:
        assert f"      - {producer}" in text


def test_pages_does_not_gate_workflow_run_on_upstream_success():
    text = PAGES.read_text(encoding="utf-8")
    assert "if: ${{ always() }}" in text
    assert "github.event.workflow_run.conclusion == 'success'" not in text


def test_pages_publishes_freshness_manifest_and_canonical_data():
    text = PAGES.read_text(encoding="utf-8")
    assert "cp bets.json ledger_meta.json _site/" in text
    assert "deployment_meta.json" in text
    assert "source_sha" in text
    assert "sha256" in text
    assert "bulletin_health.json" in text


def test_pages_has_hourly_safety_deploy():
    text = PAGES.read_text(encoding="utf-8")
    assert 'cron: "17 * * * *"' in text
