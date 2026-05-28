from typing import Mapping, Protocol

from fukikae_studio.config import DEFAULT_XAI_TTS_VOICE

TTS_ENDPOINT = "/tts"
TTS_MANIFEST_ENDPOINT = "/v1/tts"
BUILTIN_TTS_VOICES = (
    {
        "voice_id": "d0cb9ff07d95",
        "name": "Sakura",
        "language": "ja",
        "gender": "female",
    },
    {
        "voice_id": "b1a7441b97a1",
        "name": "Ren",
        "language": "ja",
        "gender": "male",
    },
    {
        "voice_id": "eve",
        "name": "Eve",
        "language": "multilingual",
        "gender": "female",
    },
)


class BytesJSONClient(Protocol):
    def post_json_bytes(self, path: str, payload: Mapping[str, object]) -> bytes:
        ...


def build_tts_payload(text: str, voice: str = DEFAULT_XAI_TTS_VOICE, language: str = "ja") -> dict:
    return {"text": text, "voice_id": voice, "language": language}


def synthesize_tts_audio(
    client: BytesJSONClient,
    text: str,
    voice: str = DEFAULT_XAI_TTS_VOICE,
    language: str = "ja",
) -> bytes:
    return client.post_json_bytes(TTS_ENDPOINT, build_tts_payload(text=text, voice=voice, language=language))
