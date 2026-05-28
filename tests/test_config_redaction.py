from pathlib import Path

import pytest

from fukikae_studio.config import DEFAULT_XAI_BASE_URL, DEFAULT_XAI_TTS_VOICE, MissingConfigError, XAIConfig, load_env_file
from fukikae_studio.logging_redaction import redact_secrets


def test_load_config_requires_api_key_without_printing_env_values():
    with pytest.raises(MissingConfigError) as exc_info:
        XAIConfig.from_env({})

    message = str(exc_info.value)
    assert "XAI_API_KEY" in message
    assert "secret" not in message.lower()


def test_config_defaults_are_xai_only_and_repr_redacts_api_key():
    config = XAIConfig.from_env({"XAI_API_KEY": "unit-test-secret"})

    assert config.provider == "xai"
    assert config.base_url == DEFAULT_XAI_BASE_URL
    assert config.text_model == "grok-4.3"
    assert config.tts_voice == DEFAULT_XAI_TTS_VOICE
    assert config.tts_voice == "d0cb9ff07d95"
    assert config.tts_language == "ja"
    assert "unit-test-secret" not in repr(config)


def test_load_env_file_normalizes_grok_key_aliases_without_shell_source(tmp_path):
    env_file = tmp_path / "env.local."
    env_file.write_text(
        "\n".join(
            [
                "Xai_API_Key=unit-test-secret value with spaces",
                "Xai_model=grok-test-model",
                "export XAI_TTS_VOICE=eve",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    env = load_env_file(env_file)

    assert env == {
        "XAI_API_KEY": "unit-test-secret value with spaces",
        "XAI_TEXT_MODEL": "grok-test-model",
        "XAI_TTS_VOICE": "eve",
    }


def test_config_ignores_env_model_values_that_are_not_model_ids():
    config = XAIConfig.from_env(
        {
            "XAI_API_KEY": "unit-test-secret",
            "XAI_TEXT_MODEL": "Speech to Text",
        }
    )

    assert config.text_model == "grok-4.3"


def test_redact_secrets_removes_bearer_tokens_and_env_assignments():
    text = "Authorization: Bearer unit-test-secret XAI_API_KEY=unit-test-secret"

    redacted = redact_secrets(text, secrets=["unit-test-secret"])

    assert "unit-test-secret" not in redacted
    assert "<redacted>" in redacted


def test_env_example_contains_only_empty_placeholders():
    env_example = Path(".env.example").read_text(encoding="utf-8")

    expected_names = {
        "XAI_API_KEY",
        "XAI_BASE_URL",
        "XAI_TEXT_MODEL",
        "XAI_STT_LANGUAGE",
        "XAI_TTS_VOICE",
        "XAI_TTS_LANGUAGE",
    }
    lines = [line for line in env_example.splitlines() if line and not line.startswith("#")]

    assert {line.split("=", 1)[0] for line in lines} == expected_names
    assert all(line.endswith("=") for line in lines)
