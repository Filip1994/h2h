from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from quantbot.markets import ALLOWED_BOOKMAKER_IDS

BETS = ROOT / "bets.json"


def main() -> int:
    rows = json.loads(BETS.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise SystemExit("bets.json must contain a list")

    changed = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("status", "PENDING")).upper() != "PENDING":
            continue
        try:
            bookmaker_id = int(row.get("bookmaker_id"))
        except (TypeError, ValueError):
            bookmaker_id = None
        if bookmaker_id in ALLOWED_BOOKMAKER_IDS:
            continue
        row["status"] = "CANCELLED"
        row["profit"] = 0.0
        row["outcome"] = None
        row["cancellation_reason"] = "PRODUCTION_BOOKMAKER_OUTSIDE_HARD_WHITELIST"
        changed += 1

    if changed:
        BETS.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Production pick validation: cancelled_invalid={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
