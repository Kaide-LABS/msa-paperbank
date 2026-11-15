# Object-key rename

Migration `007_object_key_rename.sql` renames the database columns `gcs_object` to
`object_key` and `papers.served_object` to `served_object_key`. It is idempotent
and includes the exact inverse statements in its header for rollback planning.

The ORM exposes the neutral column attributes while keeping `gcs_object` and
`served_object` as SQLAlchemy synonyms, so existing Python callers continue to
work. Settings use `object_store_bucket`, `media_prefix`, and
`contribution_prefix`; both these names and the old `GCS_BUCKET`,
`MEDIA_GCS_PREFIX`, and `CONTRIBUTION_GCS_PREFIX` environment variables resolve.
If both names are set, the neutral name wins.

Review the target database and backups before applying or reversing migration
007. Do not run it against GCP production as part of this phase.
