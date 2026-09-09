from pathlib import Path

ROOT = Path(__file__).parents[1]
PAGES = ["index.html", "production.html", "strong-signals.html", "near-misses.html", "history.html"]
NAV_PAGES = ["./", "./production.html", "./strong-signals.html", "./near-misses.html", "./history.html"]
PAGE_KEYS = {"index.html":"overview","production.html":"production","strong-signals.html":"strong","near-misses.html":"near","history.html":"history"}

def read(name: str) -> str: return (ROOT / name).read_text(encoding="utf-8")

def test_dashboard_has_one_shared_design_system_and_all_primary_sectors():
    css, js = read("assets/qb-dashboard.css"), read("assets/qb-dashboard.js")
    assert ".shell" in css and ".lifecycle" in css and ".clv" in css
    assert "const productionCard" in js and "const signalCard" in js and "const lifecycle" in js
    for page in PAGES:
        text=read(page); assert "./assets/qb-dashboard.css" in text and "./assets/qb-dashboard.js" in text
        for href in NAV_PAGES: assert f'href="{href}"' in text

def test_dashboard_is_mobile_first_and_avoids_page_level_overflow():
    css=read("assets/qb-dashboard.css"); assert "@media(max-width:520px)" in css and ".shell{padding:0 13px}" in css and "overflow-x:auto" in css
    viewport='meta name="viewport" content="width=device-width,initial-scale=1"'
    for page in PAGES: text=read(page); assert viewport in text and "width:100vw" not in text

def test_dashboard_keeps_production_and_observational_semantics_explicit():
    production=read("production.html"); assert "PRODUCTION · PAPER BET" in production
    strong,near=read("strong-signals.html"),read("near-misses.html"); assert "NOT A PRODUCTION BET" in strong and "NOT A BET" in near

def test_dashboard_zero_pick_contract_and_truthful_state_labels():
    overview,production,js=read("index.html"),read("production.html"),read("assets/qb-dashboard.js")
    for text in (overview,production):
        assert 'id="bank"' in text and 'id="pnl"' in text and 'id="roi"' in text and "data-generation" in text and "data-capture" in text
    for state in ("RUNNING","NO SIGNALS","NO ELIGIBLE FIXTURES","STALE","NO DATA","ERROR"): assert state in js
    assert "const status =" in js

def test_dashboard_pages_have_explicit_sector_identity_and_active_navigation():
    for page,key in PAGE_KEYS.items():
        text=read(page); assert f'<body data-page="{key}">' in text and 'class="active"' in text and f'data-page="{key}"' in text and 'aria-current="page"' in text
    strong=read("strong-signals.html"); assert "STRONG SIGNALS · ISOLATED SECTOR" in strong and "VIRTUAL / COUNTERFACTUAL · 10,000 RSD BASE" in strong and "sector-frame" in strong

def test_strong_page_cannot_fall_through_to_production_overview_accounting():
    strong=read("strong-signals.html"); assert '<body data-page="strong">' in strong and "const INITIAL_BANK = 10000" in strong and "virtualProfit" in strong and "strong_signals_portfolio.json" in strong

def test_strong_and_near_pages_have_active_and_history_contract():
    strong,near,js=read("strong-signals.html"),read("near-misses.html"),read("assets/qb-dashboard.js")
    for page in (strong,near): assert "ACTIVE" in page and "HISTORY" in page and 'id="active-cards"' in page and 'id="history-cards"' in page
    assert "renderBucket" in js and "String(x.status || 'PENDING')" in js

def test_history_preserves_accounting_buckets_and_does_not_invent_lifecycle():
    js=read("assets/qb-dashboard.js")
    for token in ("signal_class:'PRODUCTION'","signal_class:'STRONG_SIGNAL'","signal_class:'NEAR_MISS'","x.opening_odd","x.opening_captured_at","x.closing_odd","x.closing_captured_at","Unavailable"): assert token in js

def test_signal_history_exposes_real_outcome_profit_and_counterfactual_semantics():
    js=read("assets/qb-dashboard.js")
    for token in ("const outcome = x","WIN","LOSS","PENDING","const resultBlock = x","OUTCOME","P/L","NOT A PRODUCTION BET","x.settled_at","x.result"): assert token in js

def test_overview_snapshot_excludes_stale_production_matches():
    overview=read("index.html"); assert 'id="current-summary"' in overview and 'id="summary"' not in overview and "status || '').toUpperCase() === 'PENDING'" in overview and "liveWindow = 4 * 60 * 60 * 1000" in overview and "Nema aktivnih ili predstojećih Production odluka." in overview

def test_high_volume_observational_buckets_use_compact_list_layout():
    css,near,strong,js=read("assets/qb-dashboard.css"),read("near-misses.html"),read("strong-signals.html"),read("assets/qb-dashboard.js")
    assert 'class="cards signal-list"' in near and 'class="cards signal-list"' in strong
    assert ".signal-list{display:flex;flex-direction:column" in css
    assert ".overview-snapshot{display:flex;flex-direction:column" in css
    assert "signal-row" in js and "x.match" in js and "signal-row-match" in js
    assert "teams" in js

def test_obsolete_competing_preview_is_removed(): assert not (ROOT / "dashboard_preview.html").exists()
