from __future__ import annotations

import logging

from offerbound.keychain import RedactingFilter, stored_secret_values

_redactor = RedactingFilter()


def configure_logging(level: int = logging.INFO) -> None:
    """Root logging where every handler redacts stored secrets and known token shapes."""
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for secret in stored_secret_values():
        _redactor.add(secret)
    for handler in logging.getLogger().handlers:
        if _redactor not in handler.filters:
            handler.addFilter(_redactor)


def register_secret(value: str) -> None:
    """Redact a runtime secret (such as the session token) from all log output."""
    _redactor.add(value)
