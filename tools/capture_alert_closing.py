from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from quantbot.alert_lifecycle import capture_alert_closing_quotes
from quantbot.config import Settings

settings = Settings.from_env(ROOT)
print(f"Alert T-5 snapshots captured: {capture_alert_closing_quotes(settings)}")
