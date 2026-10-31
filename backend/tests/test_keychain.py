import logging

import pytest

from offerbound import keychain
from offerbound.keychain import REDACTED, RedactingFilter, SecretName


def test_round_trip_uses_offerbound_service(isolated_env: object) -> None:
    keychain.set_secret(SecretName.ANTHROPIC_API_KEY, "sk-ant-abc123456789")
    assert keychain.get_secret(SecretName.ANTHROPIC_API_KEY) == "sk-ant-abc123456789"
    assert keychain.has_secret(SecretName.ANTHROPIC_API_KEY)
    store = getattr(isolated_env, "store")  # noqa: B009
    assert ("offerbound", "anthropic_api_key") in store


def test_delete(isolated_env: object) -> None:
    keychain.set_secret(SecretName.NOTION_TOKEN, "value-1234")
    assert keychain.delete_secret(SecretName.NOTION_TOKEN) is True
    assert keychain.delete_secret(SecretName.NOTION_TOKEN) is False
    assert keychain.get_secret(SecretName.NOTION_TOKEN) is None


def test_empty_secret_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        keychain.set_secret(SecretName.GMAIL_APP_PASSWORD, "")


def test_redact_known_values_and_token_shapes() -> None:
    text = "key=hunter2-pass and sk-ant-api03-AAAAAAAAAAAAAAAA done"
    cleaned = keychain.redact(text, ["hunter2-pass"])
    assert "hunter2-pass" not in cleaned
    assert "sk-ant-" not in cleaned
    assert cleaned.count(REDACTED) == 2


def test_logging_filter_redacts_args(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("offerbound.test")
    caplog.handler.addFilter(RedactingFilter(["s3cr3t-value"]))
    with caplog.at_level(logging.INFO, logger="offerbound.test"):
        logger.info("calling with %s", "s3cr3t-value")
    assert "s3cr3t-value" not in caplog.text
    assert REDACTED in caplog.text


def test_stored_secret_values_lists_only_set_secrets() -> None:
    keychain.set_secret(SecretName.USAJOBS_API_KEY, "usa-key-1")
    assert keychain.stored_secret_values() == ["usa-key-1"]


def test_session_token_redacted_from_logs(caplog: pytest.LogCaptureFixture) -> None:
    from offerbound.logging_setup import _redactor, register_secret

    register_secret("launch-token-xyz")
    caplog.handler.addFilter(_redactor)
    with caplog.at_level(logging.INFO, logger="uvicorn.access"):
        logging.getLogger("uvicorn.access").info(
            '"GET /?token=%s HTTP/1.1" 200', "launch-token-xyz"
        )
    assert "launch-token-xyz" not in caplog.text
