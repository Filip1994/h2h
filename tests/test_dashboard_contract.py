import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
PAGES = [
    "index.html",
    "production.html",
    "strong-signals.html",
    "near-misses.html",
    "history.html",
]
NAV_PAGES = [
    "./",
    "./production.html",
    "./strong-signals.html",
    "./near-misses.html",
    "./history.html",
]
PAGE_KEYS = {
    "index.html": "overview",
    "production.html": "production",
    "strong-signals.html": "strong",
    "near-misses.html": "near",
    "history.html": "history",
}


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_dashboard_has_one_shared_design_system_and_all_primary_sectors():
    css = read("assets/qb-dashboard.css")
    js = read("assets/qb-dashboard.js")
    assert ".shell" in css and ".lifecycle" in css and ".clv" in css
    assert (
        "const productionCard" in js
        and "const signalCard" in js
        and "const lifecycle" in js
    )
    for page in PAGES:
        text = read(page)
        assert "./assets/qb-dashboard.css" in text
        assert "./assets/qb-dashboard.js" in text
        for href in NAV_PAGES:
            assert f'href="{href}"' in text


def test_dashboard_is_mobile_first_and_avoids_page_level_overflow():
    css = read("assets/qb-dashboard.css")
    assert "@media(max-width:520px)" in css
    assert ".shell{padding:0 13px}" in css
    assert "overflow-x:auto" in css
    viewport = 'meta name="viewport" content="width=device-width,initial-scale=1"'
    for page in PAGES:
        text = read(page)
        assert viewport in text
        assert "width:100vw" not in text


def test_dashboard_keeps_production_and_observational_semantics_explicit():
    production = read("production.html")
    assert "PRODUCTION · PAPER BET" in production
    strong = read("strong-signals.html")
    near = read("near-misses.html")
    assert "NOT A PRODUCTION BET" in strong
    assert "NOT A BET" in near


def test_dashboard_zero_pick_contract_and_truthful_state_labels():
    overview = read("index.html")
    production = read("production.html")
    js = read("assets/qb-dashboard.js")
    for text in (overview, production):
        assert 'id="bank"' in text
        assert 'id="pnl"' in text
        assert 'id="roi"' in text
        assert "data-generation" in text
        assert "data-capture" in text
    for state in (
        "RUNNING",
        "NO SIGNALS",
        "NO ELIGIBLE FIXTURES",
        "STALE",
        "NO DATA",
        "ERROR",
    ):
        assert state in js
    assert "const status =" in js


def test_dashboard_pages_have_explicit_sector_identity_and_active_navigation():
    for page, key in PAGE_KEYS.items():
        text = read(page)
        assert f'<body data-page="{key}">' in text
        assert 'class="active"' in text
        assert f'data-page="{key}"' in text
        assert 'aria-current="page"' in text

    strong = read("strong-signals.html")
    assert "STRONG SIGNALS · ISOLATED SECTOR" in strong
    assert "VIRTUAL / COUNTERFACTUAL · 10,000 RSD BASE" in strong
    assert "sector-frame" in strong


def test_strong_page_cannot_fall_through_to_production_overview_accounting():
    strong = read("strong-signals.html")
    js = read("assets/qb-dashboard.js")
    assert '<body data-page="strong">' in strong
    assert "VIRTUAL / COUNTERFACTUAL · 10,000 RSD BASE" in strong
    assert "renderStrong" in js
    assert "strong_signals_portfolio.json" in js
    assert "strong_signals.json" in js


def test_strong_and_near_pages_have_active_and_history_contract():
    strong = read("strong-signals.html")
    near = read("near-misses.html")
    js = read("assets/qb-dashboard.js")
    for page in (strong, near):
        assert "ACTIVE" in page
        assert "HISTORY" in page
        assert 'id="active-cards"' in page
        assert 'id="history-cards"' in page
    assert "renderBucket" in js
    assert "const isActive = x =>" in js
    assert "String(x?.status || 'PENDING').toUpperCase()" in js


def test_history_preserves_accounting_buckets_and_does_not_invent_lifecycle():
    js = read("assets/qb-dashboard.js")
    assert "const production = bets =>" in js
    assert "const signalCard =" in js
    assert "x.opening_odd" in js
    assert "x.closing_odd" in js
    assert "Unavailable" in js
    assert "renderStrong" in js
    assert "renderBucket" in js


def test_signal_history_exposes_real_outcome_profit_and_counterfactual_semantics():
    js = read("assets/qb-dashboard.js")
    assert "const outcome = x" in js
    assert "WIN" in js and "LOSS" in js and "PENDING" in js
    assert "const resultBlock = x" in js
    assert "OUTCOME" in js and "P/L" in js
    assert "NOT A PRODUCTION BET" in js
    assert "x.settled_at" in js
    assert "x.result" in js


def test_overview_snapshot_excludes_stale_production_matches():
    overview = read("index.html")
    assert 'id="current-summary"' in overview
    assert 'id="summary"' not in overview
    assert "status || '').toUpperCase() === 'PENDING'" in overview
    assert "liveWindow = 4 * 60 * 60 * 1000" in overview
    assert "Nema aktivnih ili predstojećih Production odluka." in overview


def test_high_volume_observational_buckets_use_compact_list_layout():
    css = read("assets/qb-dashboard.css")
    near = read("near-misses.html")
    strong = read("strong-signals.html")
    js = read("assets/qb-dashboard.js")
    assert 'class="cards signal-list"' in near
    assert 'class="cards signal-list"' in strong
    assert ".signal-list{display:flex;flex-direction:column" in css
    assert ".overview-snapshot{display:flex;flex-direction:column" in css
    assert "signal-row" in js
    assert "fixtureTeams" in js
    assert "home_name" in js
    assert "away_name" in js


def test_obsolete_competing_preview_is_removed():
    assert not (ROOT / "dashboard_preview.html").exists()


def test_public_dashboard_contract_executes_against_current_generated_data():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "validate_public_dashboard.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
