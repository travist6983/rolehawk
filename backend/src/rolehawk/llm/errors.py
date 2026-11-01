from __future__ import annotations


class LLMError(Exception):
    """Base class. `user_message` is safe to show in the UI."""

    user_message = "The AI request failed."


class LLMNotConfiguredError(LLMError):
    user_message = "Connect Claude in Settings (add an Anthropic API key) to use this feature."


class LLMAuthError(LLMNotConfiguredError):
    user_message = "Anthropic rejected the API key. Check it in Settings."


class LLMPermissionError(LLMAuthError):
    """403: the key is real but not allowed to call the model (a restricted workspace)."""

    user_message = (
        "This API key isn't allowed to use Claude. Create a new key on the Claude Platform."
    )


class LLMBillingError(LLMError):
    """The account has no credit or a payment problem (402, or a 400 about the balance)."""

    user_message = (
        "Your Claude account is out of credit. Add credit under Billing on the Claude Platform, "
        "then try again."
    )


class LLMAccountLimitError(LLMError):
    """The spend limit set in the Claude Console, or the account tier's cap, was reached."""

    user_message = (
        "Your Claude account reached the spend limit set on the Claude Platform. Raise it under "
        "Billing, then try again."
    )


class LLMUnavailableError(LLMError):
    """Transient: rate limits, overload, network. The SDK has already retried."""

    user_message = "Claude is busy or unreachable right now. Try again in a minute."


class LLMRateLimitError(LLMUnavailableError):
    user_message = (
        "Anthropic is limiting how fast your account can send requests. Try again in a minute."
    )


class LLMOverloadedError(LLMUnavailableError):
    user_message = "Claude is busy right now. Try again in a few minutes."


class LLMConnectionError(LLMUnavailableError):
    user_message = "Couldn't reach Anthropic. Check your internet connection and try again."


class LLMRefusalError(LLMError):
    user_message = "Claude declined this request."

    def __init__(self, category: str | None, explanation: str | None = None) -> None:
        super().__init__(f"refusal (category={category}): {explanation or ''}".strip())
        self.category = category
        self.explanation = explanation


class LLMTruncatedError(LLMError):
    user_message = "The AI response was cut off before it finished."


_BUG_REPORT = (
    "This is a RoleHawk bug, not a problem with your key or account. Please report it at "
    "https://github.com/travist6983/rolehawk/issues"
)


def _detail(text: str, limit: int = 300) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


class LLMRequestError(LLMError):
    """A 400 Claude rejected for its shape (not billing): RoleHawk built a bad request."""

    def __init__(self, api_message: str) -> None:
        super().__init__(api_message)
        self.api_message = api_message
        self.user_message = (
            f'Claude rejected the request RoleHawk sent: "{_detail(api_message)}". {_BUG_REPORT}'
        )


class LLMSchemaError(LLMRequestError):
    """Caught before sending: the structured-output schema is over the API's limits."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.user_message = (
            f"RoleHawk asked Claude for an answer in a shape it can't produce. {_BUG_REPORT}"
        )


class LLMTooLargeError(LLMError):
    user_message = (
        "That's more text than Claude can read in one request. Upload just your resume, or a "
        "shorter file, and try again."
    )


class LLMModelNotFoundError(LLMError):
    def __init__(self, api_message: str) -> None:
        super().__init__(api_message)
        self.user_message = (
            f'Claude couldn\'t find the model this feature uses ("{_detail(api_message)}"). '
            "Pick another model under Model in Settings, then try again."
        )


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
