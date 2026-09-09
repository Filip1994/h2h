from pathlib import Path

ROOT = Path(__file__).parents[1]
PAGES = ["index.html", "production.html", "strong-signals.html", "near-misses.html", "history.html"]
NAV_PAGES = ["./", "./production.html", "./strong-signals.html", "./near-misses.html", "./history.html"]


def test_dashboard_has_one_shared_design_system_and_all_primary_sectors():
    css = (ROOT / "assets/qb-dashboard.css").read_text(encoding="utf-8")
    js = (ROOT / "assets/qb-dashboard.js").read_text(encoding="utf-8")
    assert ".shell" in css and ".lifecycle" in css and ".clv" in css
    assert "QB.productionCard" in js and "QB.signalCard" in js and "QB.lifecycle" in js
    for page in PAGES:
        text = (ROOT / page).read_text(encoding="utf-8")
        assert './assets/qb-dashboard.css' in text
        assert './assets/qb-dashboard.js' in text
        for href in NAV_PAGES:
            assert f'href="{href}"' in text


def test_dashboard_is_mobile_first_and_avoids_page_level_overflow():
    css = (ROOT / "assets/qb-dashboard.css").read_text(encoding="utf-8")
    assert "@media(max-width:520px)" in css
    assert ".shell{padding:0 13px}" in css
    assert "overflow-x:auto" in css
    for page in PAGES:
        text = (ROOT / page).read_text(encoding="utf-8")
        assert 'meta name="viewport" content="width=device-width,initial-scale=1"' in text
        assert "width:100vw" not in text


def test_dashboard_keeps_production_and_observational_semantics_explicit():
    assert "PRODUCTION · PAPER BET" in (ROOT / "production.html").read_text(encoding="utf-8")
    strong = (ROOT / "strong-signals.html").read_text(encoding="utf-8")
    near = (ROOT / "near-misses.html").read_text(encoding="utf-8")
    assert "NOT A PRODUCTION BET" in strong
    assert "NOT A BET" in near


def test_obsolete_competing_preview_is_removed():
    assert not (ROOT / "dashboard_preview.html").exists()
