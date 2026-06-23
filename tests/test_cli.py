import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_demo_command_runs_end_to_end():
    result = subprocess.run(
        [sys.executable, "-m", "wp2aws", "demo"],
        cwd=REPO_ROOT / "src",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Sizing decision" in result.stdout
    assert "Cost estimate" in result.stdout
    assert "synthetic demo data" in result.stdout


def test_demo_command_exports_tfvars_and_report(tmp_path):
    tfvars_path = tmp_path / "terraform.tfvars"
    report_path = tmp_path / "report.md"
    result = subprocess.run(
        [
            sys.executable, "-m", "wp2aws", "demo",
            "--export-tfvars", str(tfvars_path),
            "--export-report", str(report_path),
        ],
        cwd=REPO_ROOT / "src",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert tfvars_path.exists()
    assert report_path.exists()
    assert "app_min_size" in tfvars_path.read_text()


def test_scan_remote_without_sessions_per_day_fails_clearly():
    result = subprocess.run(
        [sys.executable, "-m", "wp2aws", "scan", "https://example.com"],
        cwd=REPO_ROOT / "src",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "sessions-per-day" in result.stderr


def test_scan_local_without_access_log_warns_but_does_not_crash():
    # This will actually attempt to call `wp` via subprocess and likely fail since
    # there's no real WordPress install in this test environment; it should handle
    # that gracefully (caught and turned into a note) rather than raising.
    result = subprocess.run(
        [sys.executable, "-m", "wp2aws", "scan", "--local"],
        cwd=REPO_ROOT / "src",
        capture_output=True,
        text=True,
    )
    assert "no --access-log provided" in result.stderr
