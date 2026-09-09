from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = {
    "index.html": "overview",
    "production.html": "production",
    "strong-signals.html": "strong",
    "near-misses.html": "near",
    "history.html": "history",
}
REQUIRED_JSON = {
    "bets.json": list,
    "ledger_meta.json": dict,
    "strong_signals.json": list,
    "strong_signal_ledger.json": list,
    "strong_signals_portfolio.json": dict,
    "near_misses.json": list,
}
STATUS_VALUES = {"PENDING", "WIN", "LOSS", "SKIPPED", "SETTLED", "VOID", "REVIEW"}
TERMINAL = {"WIN", "LOSS", "VOID", "REVIEW"}


def load_json(name: str):
    path = ROOT / name
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def records(name: str):
    value = load_json(name)
    if not isinstance(value, list):
        raise TypeError(f"{name}: expected JSON array")
    return value


def validate_record_shape(name: str, rows: list[object], required: set[str]):
    ids: set[str] = set()
    for index, row in enumerate(rows):
        assert isinstance(row, dict), f"{name}[{index}]: expected object"
        missing = sorted(required - row.keys())
        assert not missing, f"{name}[{index}]: missing {missing}"
        record_id = row.get("id")
        if record_id is not None:
            assert str(record_id) not in ids, (
                f"{name}[{index}]: duplicate id {record_id}"
            )
            ids.add(str(record_id))
        status = row.get("status")
        if status is not None:
            assert str(status).upper() in STATUS_VALUES, (
                f"{name}[{index}]: unknown status {status!r}"
            )
        for key in ("odd", "opening_odd", "closing_odd", "closing_5m_odd"):
            value = row.get(key)
            if value is not None:
                assert isinstance(value, (int, float)) and value > 1.0, (
                    f"{name}[{index}]: invalid {key}={value!r}"
                )


def main() -> int:
    for name, expected_type in REQUIRED_JSON.items():
        value = load_json(name)
        assert value is not None, f"missing public artifact: {name}"
        assert isinstance(value, expected_type), (
            f"{name}: expected {expected_type.__name__}"
        )

    bets = records("bets.json")
    strong = records("strong_signals.json")
    ledger = records("strong_signal_ledger.json")
    near = records("near_misses.json")
    portfolio = load_json("strong_signals_portfolio.json")
    meta = load_json("ledger_meta.json")

    validate_record_shape("bets.json", bets, {"id"})
    validate_record_shape(
        "strong_signals.json",
        strong,
        {"id", "signal_class", "not_a_production_bet", "virtual_portfolio", "status"},
    )
    validate_record_shape("strong_signal_ledger.json", ledger, {"id"})
    validate_record_shape("near_misses.json", near, {"id", "signal_class", "status"})

    assert isinstance(meta, dict)
    assert isinstance(portfolio, dict)
    assert portfolio.get("production") is False
    assert float(portfolio.get("initial_bank", 0)) == 10000.0
    assert len(str(portfolio.get("virtual_portfolio", "STRONG_SIGNALS_VIRTUAL"))) > 0

    assert len(strong) == len(ledger), (
        "Strong Signal public dataset diverges from canonical ledger"
    )
    assert all(
        str(x.get("signal_class", "")).upper() == "STRONG_SIGNAL" for x in strong
    )
    assert all(x.get("not_a_production_bet") is True for x in strong)
    assert all(x.get("virtual_portfolio") == "STRONG_SIGNALS_VIRTUAL" for x in strong)
    for row in strong:
        terminal = str(row.get("status", "")).upper() in TERMINAL
        assert bool(row.get("virtual_settled")) == terminal, (
            f"Strong status/settlement mismatch for {row.get('id')}"
        )
        profit = float(row.get("virtual_profit") or 0.0)
        assert profit == (float(row.get("profit") or 0.0) if terminal else 0.0), (
            f"Strong P/L contamination for {row.get('id')}"
        )

    for name, page_key in PAGES.items():
        text = (ROOT / name).read_text(encoding="utf-8")
        assert f'<body data-page="{page_key}">' in text, (
            f"{name}: missing page identity"
        )
        assert 'aria-current="page"' in text and 'class="active"' in text, (
            f"{name}: missing active navigation"
        )
        assert "./assets/qb-dashboard.css" in text
        assert 'meta name="viewport" content="width=device-width,initial-scale=1"' in text

    js = (ROOT / "assets" / "qb-dashboard.js").read_text(encoding="utf-8")
    strong_js = (ROOT / "assets" / "strong-signals.js").read_text(encoding="utf-8")
    subprocess.run(
        ["node", "--check", str(ROOT / "assets" / "qb-dashboard.js")],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["node", "--check", str(ROOT / "assets" / "strong-signals.js")],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "function renderStrong" in js
    assert "renderBucket" in js
    assert "const production = bets =>" in js
    assert "const lifecycle" in js
    assert "const clv" in js
    assert "n === 0" in js and "Even" in js
    assert "fetch('./' + name + '?v=' + Date.now()" in js
    assert "slice(0,200)" in js
    assert "slice().reverse().slice(0,200)" in js
    assert not re.search(r"<script[^>]+src=[^>]*\\.json", js, re.IGNORECASE)
    assert "strong_signals.json" in strong_js
    assert "strong_signals_portfolio.json" in strong_js
    assert "STRONG SIGNAL" in strong_js
    assert "Promise.all" in strong_js
    strong_page = (ROOT / "strong-signals.html").read_text(encoding="utf-8")
    assert "./assets/strong-signals.js?v=20260909-1" in strong_page
    print(
        f"PASS public dashboard contract: bets={len(bets)} strong={len(strong)} near={len(near)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
