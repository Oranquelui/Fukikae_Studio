class ProviderPolicyError(ValueError):
    """Raised when a requested AI provider is outside the xAI-only policy."""


def ensure_xai_provider(provider: object) -> str:
    """Return the normalized provider when it is allowed.

    Error messages intentionally do not echo the rejected value because provider
    configuration may be assembled near secret-bearing settings.
    """
    normalized = "" if provider is None else str(provider).strip().lower()
    if normalized == "xai":
        return "xai"
    raise ProviderPolicyError("xAI is the only supported AI provider for FukiKae Studio.")
