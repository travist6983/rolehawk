"""Secrets in the OS keychain via `keyring`, plus log redaction. Secrets never touch disk."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from enum import StrEnum

import keyring
import keyring.errors

SERVICE = "rolehawk"
# Keychain service used before the rename. Secrets stored there are still read, and
# deleting a secret clears both, so a pre-rename install keeps its API key.
LEGACY_SERVICE = "offerbound"
REDACTED = "[REDACTED]"

# Well-known token shapes, redacted even if not stored in this keychain.
_TOKEN_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\b(?:ntn|secret)_[A-Za-z0-9]{20,}"),
]


class SecretName(StrEnum):
    ANTHROPIC_API_KEY = "anthropic_api_key"
    GMAIL_APP_PASSWORD = "gmail_app_password"  # noqa: S105 - a key name, not a secret
    NOTION_TOKEN = "notion_token"  # noqa: S105
    ADZUNA_APP_ID = "adzuna_app_id"
    ADZUNA_APP_KEY = "adzuna_app_key"
    USAJOBS_API_KEY = "usajobs_api_key"


def get_secret(name: SecretName) -> str | None:
    value = keyring.get_password(SERVICE, name.value)
    if value is None:
        value = keyring.get_password(LEGACY_SERVICE, name.value)
    return value


def set_secret(name: SecretName, value: str) -> None:
    if not value:
        raise ValueError("secret value must be non-empty")
    keyring.set_password(SERVICE, name.value, value)


def delete_secret(name: SecretName) -> bool:
    deleted = False
    for service in (SERVICE, LEGACY_SERVICE):
        try:
            keyring.delete_password(service, name.value)
        except keyring.errors.PasswordDeleteError:
            continue
        deleted = True
    return deleted


def has_secret(name: SecretName) -> bool:
    return get_secret(name) is not None


def stored_secret_values() -> list[str]:
    values: list[str] = []
    for name in SecretName:
        try:
            value = get_secret(name)
        except keyring.errors.KeyringError:
            continue
        if value:
            values.append(value)
    return values


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    for secret in sorted((s for s in secrets if len(s) >= 4), key=len, reverse=True):
        text = text.replace(secret, REDACTED)
    for pattern in _TOKEN_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


class RedactingFilter(logging.Filter):
    """Rewrites each log record's message with known secrets and token shapes removed."""

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self._secrets = list(secrets)

    def add(self, secret: str) -> None:
        self._secrets.append(secret)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        cleaned = redact(message, self._secrets)
        if cleaned != message:
            record.msg, record.args = cleaned, None
        return True
