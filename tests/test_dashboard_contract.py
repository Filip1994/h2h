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


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_dashboard_has_one_shared_design_system_and_all_primary_sectors():
    css = read("assets/qb-dashboard.css")
    js = read("assets/qb-dashboard.js")
    assert ".shell" in css and ".lifecycle" in css and ".clv" in css
    assert "QB.productionCard" in js and "QB.signalCard" in js and "QB.lifecycle" in js
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
    assert "QB.status=" in js


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
    assert "status||'PENDING'" in js


def test_history_preserves_accounting_buckets_and_does_not_invent_lifecycle():
    js = read("assets/qb-dashboard.js")
    assert "signal_class:'PRODUCTION'" in js
    assert "signal_class:'STRONG_SIGNAL'" in js
    assert "signal_class:'NEAR_MISS'" in js
    assert "x.opening_captured_at" in js
    assert "x.closing_captured_at" in js
    assert "Unavailable" in js


def test_obsolete_competing_preview_is_removed():
    assert not (ROOT / "dashboard_preview.html").exists()
