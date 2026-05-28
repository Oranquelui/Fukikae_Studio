import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional

from fukikae_studio.ai.provider_guard import ensure_xai_provider

DEFAULT_XAI_BASE_URL = "https://api.x.ai/v1"
DEFAULT_XAI_TEXT_MODEL = "grok-4.3"
DEFAULT_XAI_STT_LANGUAGE = "auto"
DEFAULT_XAI_TTS_VOICE = "d0cb9ff07d95"
DEFAULT_XAI_TTS_LANGUAGE = "ja"

ENV_KEY_ALIASES = {
    "XAI_API_KEY": "XAI_API_KEY",
    "XAIKEY": "XAI_API_KEY",
    "XAI_MODEL": "XAI_TEXT_MODEL",
    "XAI_TEXT_MODEL": "XAI_TEXT_MODEL",
    "XAI_BASE_URL": "XAI_BASE_URL",
    "XAI_STT_LANGUAGE": "XAI_STT_LANGUAGE",
    "XAI_TTS_VOICE": "XAI_TTS_VOICE",
    "XAI_TTS_LANGUAGE": "XAI_TTS_LANGUAGE",
}


class MissingConfigError(RuntimeError):
    """Raised when required local configuration is missing."""


def load_env_file(path: Path) -> dict:
    values = {}
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        normalized_key = _normalize_env_key(key)
        if normalized_key is None:
            continue
        values[normalized_key] = _strip_env_value(value)
    return values


@dataclass(frozen=True)
class XAIConfig:
    api_key: str = field(repr=False)
    base_url: str = DEFAULT_XAI_BASE_URL
    text_model: str = DEFAULT_XAI_TEXT_MODEL
    stt_language: str = DEFAULT_XAI_STT_LANGUAGE
    tts_voice: str = DEFAULT_XAI_TTS_VOICE
    tts_language: str = DEFAULT_XAI_TTS_LANGUAGE
    provider: str = "xai"

    def __post_init__(self) -> None:
        if not self.api_key:
            raise MissingConfigError("XAI_API_KEY is required; value is not displayed.")
        object.__setattr__(self, "provider", ensure_xai_provider(self.provider))
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "XAIConfig":
        source = os.environ if env is None else env
        api_key = source.get("XAI_API_KEY", "").strip()
        if not api_key:
            raise MissingConfigError("XAI_API_KEY is required; value is not displayed.")
        return cls(
            api_key=api_key,
            base_url=source.get("XAI_BASE_URL", DEFAULT_XAI_BASE_URL) or DEFAULT_XAI_BASE_URL,
            text_model=_model_or_default(source.get("XAI_TEXT_MODEL", DEFAULT_XAI_TEXT_MODEL)),
            stt_language=source.get("XAI_STT_LANGUAGE", DEFAULT_XAI_STT_LANGUAGE) or DEFAULT_XAI_STT_LANGUAGE,
            tts_voice=source.get("XAI_TTS_VOICE", DEFAULT_XAI_TTS_VOICE) or DEFAULT_XAI_TTS_VOICE,
            tts_language=source.get("XAI_TTS_LANGUAGE", DEFAULT_XAI_TTS_LANGUAGE) or DEFAULT_XAI_TTS_LANGUAGE,
            provider="xai",
        )


def _normalize_env_key(key: str) -> Optional[str]:
    compact = "".join(char for char in key.strip().upper() if char.isalnum())
    alias_lookup = {"".join(char for char in item.upper() if char.isalnum()): value for item, value in ENV_KEY_ALIASES.items()}
    return alias_lookup.get(compact)


def _strip_env_value(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    return stripped


def _model_or_default(value: Optional[str]) -> str:
    model = (value or DEFAULT_XAI_TEXT_MODEL).strip()
    if not model or any(char.isspace() for char in model):
        return DEFAULT_XAI_TEXT_MODEL
    return model
