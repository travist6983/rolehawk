from __future__ import annotations

import threading

from offerbound.llm.anthropic_provider import AnthropicProvider, KeySource, resolve_api_key
from offerbound.llm.provider import LLMProvider
from offerbound.logging_setup import register_secret


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

    async def validate_key(self, key: str) -> None:
        """Make one cheap authenticated call with a candidate key before storing it."""
        if self._override is not None:
            await self._override.check()
            return
        await AnthropicProvider(key, max_retries=1, timeout=20.0).check()

    def invalidate(self) -> None:
        """Call after the stored key changes."""
        with self._lock:
            self._loaded = False
