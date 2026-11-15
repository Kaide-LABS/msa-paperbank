# -*- coding: utf-8 -*-
"""GCP DB-engine adapter (Phase 1).

Reproduces today's `app/db.py` non-test engine construction exactly: a SQLAlchemy
engine whose connections come from the Cloud SQL `Connector` (pg8000 driver), with the
same pool settings. The `Connector` is built lazily on first connection (never at
import / `create_engine`), so importing this module and constructing the provider make
no network call and open no connector until the engine is actually used.

The `DATABASE_URL_TEST` / sqlite branch is NOT handled here; it stays in `app/db.py`.
"""
from __future__ import annotations


class GcpEngineProvider:
    """`EngineProvider` backed by the Cloud SQL Connector."""

    def __init__(self, settings) -> None:
        self._settings = settings
        self._connector = None
        self._engine = None

    def _getconn(self):
        from google.cloud.sql.connector import Connector

        if self._connector is None:
            self._connector = Connector()
        s = self._settings
        return self._connector.connect(
            s.cloud_sql_instance,
            "pg8000",
            user=s.db_user,
            password=s.db_password.get_secret_value(),
            db=s.db_name,
        )

    def create_engine(self):
        from sqlalchemy import create_engine

        self._engine = create_engine(
            "postgresql+pg8000://",
            creator=self._getconn,
            pool_size=2,
            max_overflow=2,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
        return self._engine

    def dispose(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
        if self._connector is not None:
            self._connector.close()
            self._connector = None
