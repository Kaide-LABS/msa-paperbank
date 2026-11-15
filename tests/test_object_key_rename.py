from pathlib import Path

from app.db import ImageBatchItem, Paper, PendingPaper


def test_orm_synonyms_preserve_old_attributes():
    assert Paper.gcs_object.property.key == "object_key"
    assert Paper.served_object.property.key == "served_object_key"
    assert PendingPaper.gcs_object.property.key == "object_key"
    assert ImageBatchItem.gcs_object.property.key == "object_key"


def test_migration_is_registered_and_reversible():
    sql = Path("migrations/007_object_key_rename.sql").read_text(encoding="utf-8")
    assert "object_key" in sql and "gcs_object" in sql
    assert "exact inverse" in sql.lower()
    assert "migrations/007_object_key_rename.sql" in Path("apply_migrations.py").read_text(encoding="utf-8")
