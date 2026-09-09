from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_shared_clv_contract_treats_exact_zero_as_even() -> None:
    js = (ROOT / "assets" / "qb-dashboard.js").read_text(encoding="utf-8")
    assert "if (n === 0) return {value:'0.00%',label:'Even',cls:'neutral'};" in js
    assert "label:n > 0 ? 'Beat Close' : 'Lost to Close'" in js


def test_strong_signal_page_treats_exact_zero_as_even() -> None:
    html = (ROOT / "strong-signals.html").read_text(encoding="utf-8")
    assert "if (p === 0) return ['0.00%','neutral','Even'];" in html
    assert "p > 0 ? 'Beat Close' : 'Lost to Close'" in html
