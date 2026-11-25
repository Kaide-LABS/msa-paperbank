"""Plain PostgreSQL SQLAlchemy engine provider."""
from __future__ import annotations


class PostgresEngineProvider:
    def __init__(self, settings) -> None:
        self._settings = settings
        self._engine = None

    def create_engine(self):
        from sqlalchemy import create_engine

        url = self._settings.database_url
        if not url:
            raise ValueError("database_url is required for the local provider")
        # pg8000 is already part of the project's supported PostgreSQL stack;
        # selecting it avoids SQLAlchemy's psycopg2 default without connecting.
        if url.startswith("postgresql://"):
            url = "postgresql+pg8000://" + url[len("postgresql://"):]
        self._engine = create_engine(
            url, pool_size=2, max_overflow=2, pool_pre_ping=True, pool_recycle=1800
        )
        return self._engine

    def dispose(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
