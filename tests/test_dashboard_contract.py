import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
PAGES = ["index.html", "production.html", "strong-signals.html", "near-misses.html", "history.html"]
NAV_PAGES = ["./", "./production.html", "./strong-signals.html", "./near-misses.html", "./history.html"]
PAGE_KEYS = {"index.html":"overview","production.html":"production","strong-signals.html":"strong","near-misses.html":"near","history.html":"history"}


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_dashboard_has_one_shared_design_system_and_all_primary_sectors():
    css, js = read("assets/qb-dashboard.css"), read("assets/qb-dashboard.js")
    assert ".shell" in css and ".lifecycle" in css and ".clv" in css
    assert "const productionCard" in js and "const signalCard" in js and "const canonicalLifecycle" in js
    for page in PAGES:
        text = read(page)
        assert "./assets/qb-dashboard.css" in text
        if page == "strong-signals.html":
            assert re.search(r'\./assets/strong-signals\.js(?:\?[^"\']*)?', text)
            assert (ROOT / "assets" / "strong-signals.js").is_file()
        else:
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
        assert viewport in text and "width:100vw" not in text


def test_dashboard_zero_pick_contract_and_truthful_state_labels():
    overview, production, js = read("index.html"), read("production.html"), read("assets/qb-dashboard.js")
    for text in (overview, production):
        assert all(token in text for token in ('id="bank"', 'id="pnl"', 'id="roi"', 'data-generation', 'data-capture'))
    for state in ("RUNNING","NO SIGNALS","NO ELIGIBLE FIXTURES","STALE","NO DATA","ERROR"):
        assert state in js
    assert "const status =" in js


def test_dashboard_pages_have_explicit_sector_identity_and_active_navigation():
    for page, key in PAGE_KEYS.items():
        text = read(page)
        assert f'<body data-page="{key}">' in text and 'class="active"' in text and f'data-page="{key}"' in text and 'aria-current="page"' in text
    assert "STRONG SIGNALS · ISOLATED SECTOR" in read("strong-signals.html")
    assert "VIRTUAL / COUNTERFACTUAL · 10,000 RSD BASE" in read("strong-signals.html")
    assert "sector-frame" in read("strong-signals.html")


def test_strong_page_cannot_fall_through_to_production_overview_accounting():
    strong, js = read("strong-signals.html"), read("assets/strong-signals.js")
    assert '<body data-page="strong">' in strong and "VIRTUAL / COUNTERFACTUAL · 10,000 RSD BASE" in strong
    assert "Promise.all([load('strong_signals.json'), load('strong_signals_portfolio.json')])" in js
    assert "strong_signals.json" in js and "strong_signals_portfolio.json" in js and "strong_signal" in js.lower()


def test_strong_and_near_pages_have_active_and_history_contract():
    strong, near, js = read("strong-signals.html"), read("near-misses.html"), read("assets/qb-dashboard.js")
    for page in (strong, near):
        assert "ACTIVE" in page and "HISTORY" in page and 'id="active-cards"' in page and 'id="history-cards"' in page
    assert "renderBucket" in js and "const isActive =" in js


def test_history_preserves_accounting_buckets_and_uses_canonical_lifecycle():
    js = read("assets/qb-dashboard.js")
    assert "const production = bets =>" in js and "const signalCard =" in js
    assert "l.first_seen?.odd" in js and "l.closing?.odd" in js and "Unavailable" in js
    assert "renderStrong" in js and "renderBucket" in js and "canonical-lifecycle" in js


def test_lifecycle_presentation_contains_all_four_stages_and_timeline():
    js, css = read("assets/qb-dashboard.js"), read("assets/qb-dashboard.css")
    for stage in ("FIRST SEEN", "PICK", "LIVE", "CLOSE"):
        assert stage in js
    assert "lifecycle-timeline" in js and ".canonical-lifecycle" in css and ".lifecycle-timeline" in css


def test_browser_only_loads_static_generated_artifacts():
    js = read("assets/qb-dashboard.js")
    assert "fetch('./' + name" in js
    assert "https://" not in js
    assert "/odds" not in js


def test_obsolete_competing_preview_is_removed():
    assert not (ROOT / "dashboard_preview.html").exists()


def test_public_dashboard_contract_executes_against_current_generated_data():
    build = subprocess.run([sys.executable, str(ROOT / "tools" / "build_public_signal_buckets.py")], cwd=ROOT, capture_output=True, text=True, check=False)
    assert build.returncode == 0, build.stdout + build.stderr
    result = subprocess.run([sys.executable, str(ROOT / "tools" / "validate_public_dashboard.py")], cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
