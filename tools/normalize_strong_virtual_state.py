from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {"WIN", "LOSS", "VOID", "REVIEW", "SETTLED"}
FILES = ("strong_signal_ledger.json", "strong_signals.json")


def normalize(path: Path) -> int:
    if not path.exists():
        return 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("signals", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return 0
    changed = 0
    for row in rows:
        if not isinstance(row, dict) or row.get("virtual_settled") is True:
            continue
        status = str(row.get("status") or "PENDING").upper()
        if status in TERMINAL:
            row["production_status"] = row.get("production_status") or row.get("status")
            if row.get("profit") not in (None, 0, 0.0):
                row["production_profit"] = row.get("production_profit") or row.get("profit")
            if row.get("result") is not None:
                row["production_result"] = row.get("production_result") or row.get("result")
            if row.get("settled_at") is not None:
                row["production_settled_at"] = row.get("production_settled_at") or row.get("settled_at")
            if row.get("settlement_type") is not None:
                row["production_settlement_type"] = row.get("production_settlement_type") or row.get("settlement_type")
            row["status"] = "PENDING"
            row["profit"] = 0.0
            row["virtual_profit"] = 0.0
            row["virtual_settled"] = False
            changed += 1
    if changed:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


if __name__ == "__main__":
    changed = sum(normalize(ROOT / name) for name in FILES)
    print(json.dumps({"normalized_rows": changed}))
