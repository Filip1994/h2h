from __future__ import annotations

from pathlib import Path

from tools.build_public_signal_buckets import build

ROOT = Path(__file__).resolve().parents[1]


def build_public_strong_signals(root: Path = ROOT) -> list[dict]:
    """Compatibility wrapper; Strong Signals now use the isolated canonical builder."""
    strong, _ = build(root)
    return strong


if __name__ == "__main__":
    data = build_public_strong_signals()
    print(f"public strong signals: {len(data)}")
