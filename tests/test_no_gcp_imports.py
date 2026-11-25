"""Mechanical final-phase gate: the tracked runtime has no GCP adapter imports."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def _python_files():
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(("runs/", ".osa/", "msa-paperbank/", "cutover/")):
            continue
        yield path

def test_no_gcp_import_families():
    bad = ("google.cloud", "google.genai", "google-genai", "vertexai", "cloud_sql", "cloud-sql-connector")
    offenders = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(any(token in name for token in bad) for name in names):
                offenders.append(str(path.relative_to(ROOT)))
    assert not offenders

def test_requirements_have_no_gcp_packages():
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    for package in ("google-genai", "google-cloud-storage", "cloud-sql-python-connector", "google-cloud-secret-manager", "vertexai"):
        assert package not in text

def test_removed_provider_rejected():
    from types import SimpleNamespace
    from app.providers import get_embedder, get_engine_provider, get_object_store, get_secrets_provider
    settings = SimpleNamespace(provider="gcp")
    for factory in (get_embedder, get_engine_provider, get_object_store, get_secrets_provider):
        try:
            factory(settings)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{factory.__name__} accepted removed provider")
