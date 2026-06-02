"""Secret redaction capability.

HRM-9: Masks secrets in logs, screenshots, HTML snapshots, and state files.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any


class Redactor:
    """Mask secrets in text and data structures.

    Usage:
        redactor = Redactor(["my-password", "sk-abc123"])
        safe = redactor.redact_text("user logged in with my-password")
        # → "user logged in with ***REDACTED***"
    """

    def __init__(self, secrets: Iterable[str]) -> None:
        self._secrets: list[str] = [str(s) for s in secrets if s]
        self._mask = "***REDACTED***"

    def redact_text(self, text: str) -> str:
        """Replace all known secrets in a string."""
        result = text
        for secret in self._secrets:
            if secret:
                result = result.replace(secret, self._mask)
        return result

    def redact_fields(
        self, 
        data: dict[str, Any], 
        secret_fields: set[str],
    ) -> dict[str, Any]:
        """Return a copy of data with secret fields masked.

        Args:
            data: Original key-value map.
            secret_fields: Set of field names that are secret.

        Returns:
            New dict with secrets replaced by ***REDACTED***.
        """
        if not secret_fields:
            return dict(data)
        
        result = {}
        for key, value in data.items():
            if key in secret_fields:
                result[key] = self._mask
            else:
                result[key] = value
        return result

    def add_secrets_from_fields(
        self,
        fields: dict[str, Any],
        secret_fields: set[str],
    ) -> None:
        """Add current values of secret fields to the redaction set."""
        for name in secret_fields:
            value = fields.get(name)
            if value and str(value) not in self._secrets:
                self._secrets.append(str(value))

    @property
    def mask(self) -> str:
        return self._mask
