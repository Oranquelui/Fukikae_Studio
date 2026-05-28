import json
from pathlib import Path

from fukikae_studio.ai.xai_tts import TTS_ENDPOINT, build_tts_payload, synthesize_tts_audio
from fukikae_studio.config import XAIConfig
from fukikae_studio.ai.xai_client import XAIClient
from fukikae_studio.pipeline.synthesize_voice import synthesize_voice_segments

DUBBING_SEGMENTS_PATH = Path(__file__).parent / "fixtures" / "sample_dubbing_response.json"


def load_dubbing_segments():
    response = json.loads(DUBBING_SEGMENTS_PATH.read_text(encoding="utf-8"))
    return json.loads(response["output_text"])["segments"]


def test_build_tts_payload_defaults_to_japanese_language_and_voice():
    payload = build_tts_payload("こんにちは", voice="eve", language="ja")

    assert payload == {"text": "こんにちは", "voice_id": "eve", "language": "ja"}


def test_synthesize_tts_audio_uses_xai_tts_endpoint_and_returns_raw_bytes():
    captured = []

    def fake_transport(request):
        captured.append(request)
        return 200, b"fake-audio-bytes"

    client = XAIClient(XAIConfig(api_key="unit-test-api-key"), transport=fake_transport)

    audio = synthesize_tts_audio(client, text="こんにちは", voice="eve", language="ja")

    assert audio == b"fake-audio-bytes"
    assert captured[0].full_url.endswith(TTS_ENDPOINT)
    assert json.loads(captured[0].data.decode("utf-8")) == {
        "text": "こんにちは",
        "voice_id": "eve",
        "language": "ja",
    }


def test_synthesize_voice_segments_writes_audio_files_and_manifest(tmp_path):
    project_dir = tmp_path / "demo"
    segments = load_dubbing_segments()

    def fake_audio(segment):
        return f"audio:{segment['id']}".encode("utf-8")

    durations = {"seg_0001": 2200, "seg_0002": 1300}

    manifest = synthesize_voice_segments(
        project_dir,
        dubbing_segments=segments,
        synthesize_audio=fake_audio,
        duration_probe_ms=lambda path, segment: durations[segment["id"]],
        voice="eve",
        language="ja",
    )

    assert manifest["schema_version"] == "0.1"
    assert manifest["provider"] == "xai"
    assert manifest["endpoint"] == "/v1/tts"
    assert manifest["language"] == "ja"
    assert manifest["voice"] == "eve"
    assert manifest["segments"] == [
        {
            "id": "seg_0001",
            "text": "こんにちは、デモへようこそ。",
            "output_audio": "tts/segment_0001.wav",
            "duration_ms": 2200,
            "target_slot_start_ms": 0,
            "target_slot_end_ms": 2400,
        },
        {
            "id": "seg_0002",
            "text": "始めましょう。",
            "output_audio": "tts/segment_0002.wav",
            "duration_ms": 1300,
            "target_slot_start_ms": 2500,
            "target_slot_end_ms": 4900,
        },
    ]
    assert (project_dir / "tts" / "segment_0001.wav").read_bytes() == b"audio:seg_0001"
    assert json.loads((project_dir / "tts" / "xai_tts_manifest.json").read_text(encoding="utf-8")) == manifest
