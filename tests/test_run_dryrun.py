import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_run_dry_run_exits_zero():
    proc = subprocess.run(
        [sys.executable, "run.py", "--dry-run"], cwd=ROOT, capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    assert "planned_runs=" in proc.stdout
