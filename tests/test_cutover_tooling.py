"""Phase 6 cutover-tooling checks (Part A).

All static/structural or pure-function — no gcloud/gsutil/pg_*/Docker/network (AC 2).
Verifies the cutover scripts exist, are valid POSIX sh, default to dry-run and refuse
real execution without --confirm/sign-off, embed no forbidden secret literal, and that
the prod-touching scripts carry the read-only + sign-off guard. Also checks the
side-by-side harness parses, imports no google.*/app.providers.gcp.* symbol, and
returns per-query agreement from injected fakes; and that the runbook/checklist docs
exist and mention the required steps + sign-off banner.
"""
import ast
import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CUTOVER = ROOT / "cutover"

# Phase 3 forbidden-literal set, assembled from fragments so this test file carries no
# verbatim forbidden literal (the source-hygiene test scans every tracked file).
FORBIDDEN = (
    "umm" + "ah",
    "my-project:africa-south1:" + "paperbank",
    "DB_PASSWORD=" + "secret",
)

SHELL_SCRIPTS = (
    "01_dump_cloudsql.sh",
    "02_copy_bucket.sh",
    "03_restore_selfhosted.sh",
    "04_reembed.sh",
    "05_parity.sh",
)
PROD_TOUCHING = ("01_dump_cloudsql.sh", "02_copy_bucket.sh")


def test_all_cutover_shell_scripts_exist():
    for name in SHELL_SCRIPTS:
        assert (CUTOVER / name).exists(), f"missing cutover/{name}"


@pytest.mark.parametrize("name", SHELL_SCRIPTS)
def test_shell_scripts_are_valid_posix_sh(name):
    if shutil.which("sh") is None:
        pytest.skip("POSIX sh is unavailable on this host")
    result = subprocess.run(["sh", "-n", str(CUTOVER / name)], capture_output=True)
    assert result.returncode == 0, result.stderr.decode()


@pytest.mark.parametrize("name", SHELL_SCRIPTS)
def test_shell_scripts_default_to_dry_run(name):
    text = (CUTOVER / name).read_text(encoding="utf-8")
    assert "--confirm" in text
    assert "DRY RUN" in text
    # The guard must gate real execution: a --confirm check is present and the dry-run
    # branch exits 0 without running the privileged command.
    assert 'CONFIRM=0' in text
    assert "Refusing real execution" in text


@pytest.mark.parametrize("name", SHELL_SCRIPTS)
def test_shell_scripts_embed_no_secret_literal(name):
    text = (CUTOVER / name).read_text(encoding="utf-8")
    assert not any(value in text for value in FORBIDDEN), f"forbidden literal in {name}"


@pytest.mark.parametrize("name", SHELL_SCRIPTS)
def test_shell_scripts_do_not_eval_environment_input(name):
    text = (CUTOVER / name).read_text(encoding="utf-8")
    assert "eval \"$" not in text, f"unsafe eval of environment input in {name}"


@pytest.mark.parametrize("name", PROD_TOUCHING)
def test_prod_touching_scripts_carry_readonly_and_signoff_guard(name):
    text = (CUTOVER / name).read_text(encoding="utf-8")
    # Sign-off marker is consulted...
    assert "SIGNOFF" in text and "docs/SIGNOFF.md" in text
    assert "is_signed_off" in text
    # ...and both --confirm AND sign-off are required to leave dry-run.
    assert 'if [ "$CONFIRM" -ne 1 ] || ! is_signed_off; then' in text
    # Access is read-only (export / rsync without delete).
    assert ("export sql" in text) or ("rsync" in text)


def test_restore_script_reuses_host_guard():
    text = (CUTOVER / "03_restore_selfhosted.sh").read_text(encoding="utf-8")
    assert "cloudsql" in text and "google" in text
    assert "PROVIDER" in text


def test_reembed_and_parity_wrap_shipped_entrypoints():
    reembed = (CUTOVER / "04_reembed.sh").read_text(encoding="utf-8")
    parity = (CUTOVER / "05_parity.sh").read_text(encoding="utf-8")
    assert "python -m app.reembed" in reembed
    assert "python -m app.parity" in parity


# --- side-by-side harness ---------------------------------------------------

def _load_side_by_side():
    path = CUTOVER / "06_side_by_side.py"
    spec = importlib.util.spec_from_file_location("cutover_side_by_side", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_side_by_side_parses_and_imports_no_gcp_symbol():
    path = CUTOVER / "06_side_by_side.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(("google", "app.providers.gcp", "vertexai")):
                    offenders.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.startswith(("google", "app.providers.gcp", "vertexai")):
                offenders.append(mod)
    assert not offenders, f"side-by-side imports GCP symbols: {offenders}"


def test_side_by_side_compare_is_pure_and_reports_agreement():
    module = _load_side_by_side()

    old = {
        "q1": {"found": True, "paper": {"id": 1}},
        "q2": {"found": True, "paper": {"id": 2}},
        "q3": {"found": False, "course_code": "CSC201"},
    }
    new = {
        "q1": {"found": True, "paper": {"id": 1}},   # agree
        "q2": {"found": True, "paper": {"id": 9}},   # disagree
        "q3": {"found": False, "course_code": "CSC201"},  # agree (both none)
    }
    report = module.compare(["q1", "q2", "q3"], lambda q: old[q], lambda q: new[q])
    assert report["total"] == 3
    assert report["agreed"] == 2
    assert report["agreement_rate"] == pytest.approx(2 / 3)
    assert [r["agree"] for r in report["queries"]] == [True, False, True]


def test_side_by_side_embeds_no_secret_literal():
    text = (CUTOVER / "06_side_by_side.py").read_text(encoding="utf-8")
    assert not any(value in text for value in FORBIDDEN)


# --- docs -------------------------------------------------------------------

def test_cutover_runbook_covers_all_steps_and_signoff_banner():
    text = (ROOT / "CUTOVER.md").read_text(encoding="utf-8")
    assert text.strip()
    low = text.lower()
    for word in ("dump", "copy", "restore", "re-embed", "parity", "side-by-side",
                 "webhook", "restore drill"):
        assert word in low, f"CUTOVER.md missing mention of {word}"
    assert "run only after" in low and "sign-off" in low


def test_webhook_move_checklist_exists_and_is_non_empty():
    text = (CUTOVER / "07_webhook_move.md").read_text(encoding="utf-8")
    assert text.strip()
    low = text.lower()
    for word in ("callback url", "verify token", "/webhook", "rollback", "sign-off"):
        assert word in low, f"webhook checklist missing {word}"


def test_signoff_marker_exists_and_is_unsigned_placeholder():
    text = (ROOT / "docs" / "SIGNOFF.md").read_text(encoding="utf-8")
    assert text.strip()
    # Placeholder must NOT present as granted, and must carry no secret.
    assert "## Status: GRANTED" not in text
    assert "## Status: PENDING" in text
    assert not any(value in text for value in FORBIDDEN)
