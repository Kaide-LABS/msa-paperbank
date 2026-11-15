"""File- and environment-backed secret providers for self-hosted deployments."""
from __future__ import annotations

import os
from pathlib import Path


class EnvSecretsProvider:
    def get(self, ref: str) -> str:
        try:
            return os.environ[ref]
        except KeyError as exc:
            raise RuntimeError(f"secret environment variable is missing: {ref}") from exc


class FileSecretsProvider:
    def __init__(self, secrets_dir: str | Path) -> None:
        self._root = Path(secrets_dir).resolve()

    def get(self, ref: str) -> str:
        path = (self._root / ref).resolve()
        if path != self._root and self._root not in path.parents:
            raise ValueError("secret reference escapes secrets directory")
        try:
            return path.read_text(encoding="utf-8").rstrip("\n")
        except FileNotFoundError as exc:
            raise RuntimeError(f"secret file is missing: {ref}") from exc
