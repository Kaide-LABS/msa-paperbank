import subprocess
import shutil
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = ("umm" + "ah", "my-project:africa-south1:" + "paperbank", "DB_PASSWORD=" + "secret")

def test_backup_restore_scripts_are_safe_and_valid():
    if shutil.which("sh") is None:
        pytest.skip("POSIX sh is unavailable on this host")
    for name in ("backup.sh", "restore.sh"):
        path = ROOT / "scripts" / name
        assert path.exists()
        assert subprocess.run(["sh", "-n", str(path)], capture_output=True).returncode == 0
        text = path.read_text()
        assert "/backups" in text
        assert "cloudsql" in text and "PROVIDER" in text
        assert not any(value in text for value in FORBIDDEN)

def test_docs_cover_operations():
    readme = (ROOT / "README.md").read_text().lower()
    runbook = (ROOT / "RUNBOOK.md").read_text().lower()
    assert all(word in readme for word in ("docker compose up", "backup", "minio"))
    assert all(word in runbook for word in ("nightly", "restore", "https", "caddy", "nginx", "webhook"))
