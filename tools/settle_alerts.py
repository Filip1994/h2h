from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from quantbot.alert_lifecycle import settle_intraday_alerts
from quantbot.config import Settings

settings = Settings.from_env(ROOT)
print(f"Intraday alerts settled: {settle_intraday_alerts(settings)}")
