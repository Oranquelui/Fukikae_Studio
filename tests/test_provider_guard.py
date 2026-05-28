import pytest

from fukikae_studio.ai.provider_guard import ProviderPolicyError, ensure_xai_provider


@pytest.mark.parametrize("provider", ["xai", "XAI", " xai "])
def test_xai_provider_is_accepted_and_normalized(provider):
    assert ensure_xai_provider(provider) == "xai"


@pytest.mark.parametrize(
    "provider",
    [
        "openai",
        "soniox",
        "supertone",
        "supertonic",
        "elevenlabs",
        "anthropic",
        "google",
        "azure",
        "",
        None,
    ],
)
def test_non_xai_provider_is_rejected_without_echoing_input(provider):
    with pytest.raises(ProviderPolicyError) as exc_info:
        ensure_xai_provider(provider)

    message = str(exc_info.value)
    assert "xAI" in message
    assert "only" in message.lower()
    if provider:
        assert provider not in message
