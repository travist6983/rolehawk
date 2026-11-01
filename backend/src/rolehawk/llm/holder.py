from __future__ import annotations

import threading

from rolehawk.llm.anthropic_provider import AnthropicProvider, KeySource, resolve_api_key
from rolehawk.llm.errors import LLMNotConfiguredError
from rolehawk.llm.provider import LLMProvider
from rolehawk.llm.types import Usage
from rolehawk.logging_setup import register_secret


class ProviderHolder:
    """Builds the provider from the keychain on demand and rebuilds it when the key changes.
    An `override` (tests, offline dev) always wins."""

    def __init__(self, override: LLMProvider | None = None) -> None:
        self._override = override
        self._lock = threading.Lock()
        self._key: str | None = None
        self._source: KeySource = "none"
        self._provider: LLMProvider | None = None
        self._loaded = False

    def _load(self) -> None:
        key, source = resolve_api_key()
        if key and key != self._key:
            register_secret(key)
            self._provider = AnthropicProvider(key)
        elif not key:
            self._provider = None
        self._key, self._source, self._loaded = key, source, True

    def get(self) -> LLMProvider | None:
        if self._override is not None:
            return self._override
        with self._lock:
            if not self._loaded:
                self._load()
            return self._provider

    def key_source(self) -> KeySource | str:
        if self._override is not None:
            return self._override.name
        with self._lock:
            if not self._loaded:
                self._load()
            return self._source

    async def probe_key(self, key: str | None = None) -> Usage:
        """One tiny real call with `key`, or with the stored key when None. No retries, so a
        problem is reported in seconds. Raises rolehawk.llm.errors types."""
        if self._override is not None:
            return await self._override.check()
        if key is None:
            key, _source = resolve_api_key()
            if key is None:
                raise LLMNotConfiguredError("no Anthropic API key configured")
        return await AnthropicProvider(key, max_retries=0, timeout=20.0).check()

    def provider_name(self) -> str:
        return self._override.name if self._override is not None else AnthropicProvider.name

    def invalidate(self) -> None:
        """Call after the stored key changes."""
        with self._lock:
            self._loaded = False
