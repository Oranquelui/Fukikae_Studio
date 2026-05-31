import json
from pathlib import Path

from fukikae_studio.ai.xai_stt import (
    STT_ENDPOINT,
    build_stt_batch_plan,
    build_stt_fields,
    normalize_stt_response,
    transcribe_audio_bytes,
)
from fukikae_studio.pipeline.stt import write_stt_artifacts

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_stt_response.json"


def load_fixture():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


class FakeXAIClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post_multipart(self, path, fields, files):
        self.calls.append({"path": path, "fields": fields, "files": files})
        return self.response


def test_build_stt_fields_supports_auto_and_explicit_source_language():
    assert build_stt_fields(source_lang="auto") == {"diarize": "true"}
    assert build_stt_fields(source_lang="en") == {
        "format": "true",
        "diarize": "true",
        "language": "en",
    }


def test_transcribe_audio_bytes_uses_xai_stt_endpoint_and_multipart_file():
    client = FakeXAIClient(load_fixture())

    response = transcribe_audio_bytes(
        client,
        filename="source_audio_for_stt.wav",
        audio_bytes=b"fake-wav",
        source_lang="en",
    )

    assert response["text"].startswith("Hello")
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["path"] == STT_ENDPOINT
    assert call["fields"]["language"] == "en"
    assert call["fields"]["diarize"] == "true"
    assert call["files"]["file"] == ("source_audio_for_stt.wav", b"fake-wav", "audio/wav")


def test_normalize_stt_response_to_internal_segments_with_ms_timing_and_speakers():
    segments = normalize_stt_response(load_fixture(), source_lang="auto", target_lang="ja")

    assert segments == [
        {
            "id": "seg_0001",
            "source_start_ms": 0,
            "source_end_ms": 2400,
            "speaker": "SPEAKER_00",
            "source_lang": "auto",
            "source_text": "Hello, welcome to the demo.",
            "target_lang": "ja",
            "target_text": None,
            "dub_start_ms": 0,
            "dub_end_ms": 2400,
            "tts_audio_path": None,
            "timing_strategy": "fit_to_source_segment",
            "status": "stt_complete",
        },
        {
            "id": "seg_0002",
            "source_start_ms": 2500,
            "source_end_ms": 4900,
            "speaker": "SPEAKER_00",
            "source_lang": "auto",
            "source_text": "Let's begin.",
            "target_lang": "ja",
            "target_text": None,
            "dub_start_ms": 2500,
            "dub_end_ms": 4900,
            "tts_audio_path": None,
            "timing_strategy": "fit_to_source_segment",
            "status": "stt_complete",
        },
    ]


def test_normalize_stt_response_supports_word_key_fallback():
    segments = normalize_stt_response(
        {
            "words": [
                {"word": "Hello", "start": 0.0, "end": 0.4, "speaker": 0},
                {"word": "world", "start": 0.5, "end": 0.9, "speaker": 0},
            ]
        },
        source_lang="en",
        target_lang="ja",
    )

    assert segments[0]["source_text"] == "Hello world"
    assert segments[0]["source_start_ms"] == 0
    assert segments[0]["source_end_ms"] == 900


def test_normalize_stt_response_joins_japanese_word_tokens_without_spaces():
    segments = normalize_stt_response(
        {
            "words": [
                {"text": "個", "start": 0.0, "end": 0.1, "speaker": 0},
                {"text": "人", "start": 0.1, "end": 0.2, "speaker": 0},
                {"text": "情", "start": 0.2, "end": 0.3, "speaker": 0},
                {"text": "報", "start": 0.3, "end": 0.4, "speaker": 0},
                {"text": "の", "start": 0.4, "end": 0.5, "speaker": 0},
                {"text": "流", "start": 0.5, "end": 0.6, "speaker": 0},
                {"text": "出", "start": 0.6, "end": 0.7, "speaker": 0},
                {"text": "は", "start": 0.7, "end": 0.8, "speaker": 0},
                {"text": "ない", "start": 0.8, "end": 1.0, "speaker": 0},
            ]
        },
        source_lang="ja",
        target_lang="en",
    )

    assert segments[0]["source_text"] == "個人情報の流出はない"


def test_normalize_stt_response_groups_words_by_speech_pause():
    segments = normalize_stt_response(
        {
            "words": [
                {"word": "Hello", "start": 0.0, "end": 0.4, "speaker": 0},
                {"word": "world.", "start": 0.5, "end": 0.9, "speaker": 0},
                {"word": "Next", "start": 2.0, "end": 2.3, "speaker": 0},
                {"word": "line.", "start": 2.4, "end": 2.8, "speaker": 0},
            ]
        }
    )

    assert [segment["source_text"] for segment in segments] == ["Hello world.", "Next line."]
    assert segments[0]["source_end_ms"] == 900
    assert segments[1]["source_start_ms"] == 2000


def test_normalize_stt_response_groups_words_by_max_duration_without_long_pause():
    words = [
        {"word": f"w{i}", "start": i * 0.5, "end": i * 0.5 + 0.2, "speaker": 0}
        for i in range(20)
    ]

    segments = normalize_stt_response({"words": words})

    assert len(segments) > 1
    assert all((segment["source_end_ms"] - segment["source_start_ms"]) <= 7500 for segment in segments)


def test_batch_stt_plan_represents_multiple_audio_jobs():
    plan = build_stt_batch_plan([Path("a.wav"), Path("b.wav")], source_lang="en")

    assert plan == [
        {"audio_path": "a.wav", "source_lang": "en", "endpoint": STT_ENDPOINT},
        {"audio_path": "b.wav", "source_lang": "en", "endpoint": STT_ENDPOINT},
    ]


def test_write_stt_artifacts_persists_sanitized_request_response_and_segments(tmp_path):
    project_dir = tmp_path / "demo"
    raw_response = load_fixture()
    normalized_segments = normalize_stt_response(raw_response)

    write_stt_artifacts(
        project_dir,
        request_metadata={
            "endpoint": STT_ENDPOINT,
            "headers": {"Authorization": "Bearer unit-test-secret"},
            "fields": build_stt_fields("en"),
        },
        raw_response=raw_response,
        normalized_segments=normalized_segments,
        secrets=["unit-test-secret"],
    )

    request_text = (project_dir / "stt" / "xai_stt_request.json").read_text(encoding="utf-8")
    segments = json.loads((project_dir / "stt" / "normalized_segments.json").read_text(encoding="utf-8"))

    assert "Authorization" not in request_text
    assert "unit-test-secret" not in request_text
    assert (project_dir / "stt" / "xai_stt_response.json").exists()
    assert segments[0]["id"] == "seg_0001"
