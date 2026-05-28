import re
from typing import Iterable, Optional

_BEARER_RE = re.compile(r"(Bearer\s+)([^\s]+)", re.IGNORECASE)
_XAI_API_KEY_ASSIGNMENT_RE = re.compile(r"(XAI_API_KEY\s*=\s*)([^\s]+)", re.IGNORECASE)


def redact_secrets(value: object, secrets: Optional[Iterable[str]] = None) -> str:
    """Return text with common secret shapes redacted."""
    text = "" if value is None else str(value)
    text = _BEARER_RE.sub(r"\1<redacted>", text)
    text = _XAI_API_KEY_ASSIGNMENT_RE.sub(r"\1<redacted>", text)
    for secret in secrets or ():
        if secret:
            text = text.replace(secret, "<redacted>")
    return text
