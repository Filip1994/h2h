from __future__ import annotations

import subprocess
import sys


# ... existing file content unchanged above ...


def test_obsolete_competing_preview_is_removed():
    assert not (ROOT / "dashboard_preview.html").exists()


def test_public_dashboard_contract_executes_against_current_generated_data():
    build = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "build_public_signal_buckets.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "validate_public_dashboard.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
