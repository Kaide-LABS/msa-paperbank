# In-house plumbing

Set `PROVIDER=local` for filesystem storage and plain PostgreSQL, or
`PROVIDER=minio` for MinIO storage. Configure `STORAGE_ROOT`, or MinIO with
`MINIO_ENDPOINT`, `MINIO_BUCKET`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, and
`MINIO_SECURE`.

The backend signs `/download` URLs with `URL_SIGNING_KEY`. URLs expire after
900 seconds by default and reject expiry or any key/signature change.
`DOWNLOAD_BASE_URL` controls the public origin. Use `DATABASE_URL` for
PostgreSQL and `TOOL_API_TOKEN` for the bearer-protected retrieval endpoint.
Secrets may instead be files under `SECRETS_DIR`; do not commit secret values.
