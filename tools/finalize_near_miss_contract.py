# fmt: off
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from tools.build_near_miss_lifecycle import build

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    rows = build(ROOT)
    for row in rows:
        row["selection"] = row.get("market")
        row["observation_odd"] = row.get("near_miss_odd")
        row["observation_opposite_odd"] = row.get("near_miss_opposite_odd")
        row["observation_captured_at"] = row.get("near_miss_captured_at")
        row["lifecycle_status"] = row.get("status")
        pick = row.get("pick_odd")
        close = row.get("closing_odd")
        if pick is not None and close is not None:
            try:
                pick_value = float(pick)
                close_value = float(close)
                if pick_value > 1 and close_value > 1:
                    row["clv_odds_pct"] = round((pick_value / close_value) - 1.0, 6)
                    row["clv_status"] = "COMPUTABLE"
            except (TypeError, ValueError):
                pass
        if row.get("clv_odds_pct") is None:
            row["clv_status"] = "NOT_COMPUTABLE"
    (ROOT / "near_misses.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"near_misses": len(rows), "checked_at": datetime.now(UTC).isoformat()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
# fmt: on
