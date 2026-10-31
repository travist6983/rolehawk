from __future__ import annotations


class LLMError(Exception):
    """Base class. `user_message` is safe to show in the UI."""

    user_message = "The AI request failed."


class LLMNotConfiguredError(LLMError):
    user_message = "Connect Claude in Settings (add an Anthropic API key) to use this feature."


class LLMAuthError(LLMNotConfiguredError):
    user_message = "Anthropic rejected the API key. Check it in Settings."


class LLMUnavailableError(LLMError):
    """Transient: rate limits, overload, network. The SDK has already retried."""

    user_message = "Claude is busy or unreachable right now. Try again in a minute."


class LLMRefusalError(LLMError):
    user_message = "Claude declined this request."

    def __init__(self, category: str | None, explanation: str | None = None) -> None:
        super().__init__(f"refusal (category={category}): {explanation or ''}".strip())
        self.category = category
        self.explanation = explanation


class LLMTruncatedError(LLMError):
    user_message = "The AI response was cut off before it finished."


class LLMOutputError(LLMError):
    """The model returned output that didn't match the requested schema."""

    user_message = "The AI returned an unexpected response. Try again."


class SpendCapExceededError(LLMError):
    def __init__(self, month_to_date_usd: float, cap_usd: float) -> None:
        super().__init__(f"monthly cap ${cap_usd:.2f} reached (spent ${month_to_date_usd:.2f})")
        self.month_to_date_usd = month_to_date_usd
        self.cap_usd = cap_usd
        self.user_message = (
            f"Monthly AI spend cap reached (${month_to_date_usd:.2f} of ${cap_usd:.2f}). "
            "Raise the cap in Settings to continue."
        )
