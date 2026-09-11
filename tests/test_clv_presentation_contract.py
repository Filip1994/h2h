from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_shared_clv_contract_treats_exact_zero_as_even() -> None:
    js = (ROOT / "assets" / "qb-dashboard.js").read_text(encoding="utf-8")
    assert "if (n === 0) return {value:'0.00%',label:'Even',cls:'neutral'};" in js
    assert "label:n > 0 ? 'Beat Close' : 'Lost to Close'" in js


def test_shared_dashboard_loader_bypasses_browser_cached_json() -> None:
    js = (ROOT / "assets" / "qb-dashboard.js").read_text(encoding="utf-8")
    assert "fetch('./' + name + '?v=' + Date.now(), {cache:'no-store'})" in js
