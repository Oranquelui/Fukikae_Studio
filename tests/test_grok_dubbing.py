import json
from pathlib import Path

import pytest

from fukikae_studio.ai.grok_dubbing import (
    DubbingScriptError,
    build_grok_dubbing_payload,
    generate_dubbing_script,
    parse_grok_dubbing_response,
)
from fukikae_studio.ai.prompts import build_dubbing_prompt, build_timing_guided_segments
from fukikae_studio.pipeline.adapt_script import write_dubbing_artifacts

SEGMENTS_PATH = Path(__file__).parent / "fixtures" / "sample_segments.json"
DUBBING_RESPONSE_PATH = Path(__file__).parent / "fixtures" / "sample_dubbing_response.json"


def load_segments():
    return json.loads(SEGMENTS_PATH.read_text(encoding="utf-8"))


def load_response():
    return json.loads(DUBBING_RESPONSE_PATH.read_text(encoding="utf-8"))


class FakeXAIClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post_json(self, path, payload):
        self.calls.append({"path": path, "payload": payload})
        if isinstance(self.response, list):
            return self.response.pop(0)
        return self.response


def test_prompt_requires_japanese_natural_dub_strict_json_and_preserved_ids():
    prompt = build_dubbing_prompt(load_segments(), target_lang="ja", style="natural-japanese-dub")

    assert "target_lang=ja" in prompt
    assert "natural Japanese dubbing" in prompt
    assert "strict JSON" in prompt
    assert "preserve segment IDs" in prompt
    assert "seg_0001" in prompt
    assert "seg_0002" in prompt


def test_prompt_adds_timing_guidance_to_each_source_segment():
    guided = build_timing_guided_segments(
        [
            {
                "id": "seg_0001",
                "source_start_ms": 1000,
                "source_end_ms": 3000,
                "source_text": "This is a compact source line.",
            }
        ]
    )

    assert guided[0]["slot_duration_ms"] == 2000
    assert guided[0]["target_max_duration_ms"] == 1840
    assert guided[0]["timing_pressure"] == "tight"


def test_prompt_instructs_grok_to_shorten_translation_before_tts_tempo_fitting():
    prompt = build_dubbing_prompt(load_segments(), target_lang="ja", style="natural-japanese-dub")

    assert "slot_duration_ms" in prompt
    assert "target_max_duration_ms" in prompt
    assert "timing_pressure" in prompt
    assert "estimated_duration_ms <= target_max_duration_ms" in prompt
    assert "shorten the Japanese translation before TTS tempo fitting" in prompt
    assert "Do not leave target_text as an unfinished fragment" in prompt
    assert "complete Japanese utterance" in prompt
    assert "Never end target_text with dangling Japanese particles" in prompt


def test_build_payload_uses_responses_endpoint_shape_and_grok_model():
    payload = build_grok_dubbing_payload(load_segments(), model="grok-4.3")

    assert payload["model"] == "grok-4.3"
    assert payload["input"][0]["role"] == "system"
    assert "xAI-only" in payload["input"][0]["content"]
    assert payload["input"][1]["role"] == "user"
    assert "seg_0001" in payload["input"][1]["content"]


def test_parse_grok_response_to_japanese_dubbing_segments_and_validate_ids():
    parsed = parse_grok_dubbing_response(load_response(), expected_segment_ids=["seg_0001", "seg_0002"])

    assert parsed[0]["id"] == "seg_0001"
    assert parsed[0]["target_text"] == "こんにちは、デモへようこそ。"
    assert parsed[0]["estimated_duration_ms"] == 2400
    assert parsed[1]["target_text"] == "始めましょう。"


def test_parse_grok_response_supports_official_responses_output_shape():
    output_text = json.dumps(
        {
            "segments": [
                {"id": "seg_0001", "target_text": "こんにちは。"},
                {"id": "seg_0002", "target_text": "始めましょう。"},
            ]
        },
        ensure_ascii=False,
    )
    response = {
        "output": [
            {
                "content": [
                    {
                        "type": "output_text",
                        "text": output_text,
                    }
                ]
            }
        ]
    }

    parsed = parse_grok_dubbing_response(response, expected_segment_ids=["seg_0001", "seg_0002"])

    assert parsed[0]["target_text"] == "こんにちは。"


def test_parse_grok_response_rejects_missing_or_extra_segment_ids():
    response = {"output_text": '{"segments":[{"id":"seg_0001","target_text":"こんにちは"}]}'}

    with pytest.raises(DubbingScriptError) as exc_info:
        parse_grok_dubbing_response(response, expected_segment_ids=["seg_0001", "seg_0002"])

    assert "seg_0002" in str(exc_info.value)


def test_parse_grok_response_rejects_unfinished_japanese_fragments():
    response = {
        "output_text": json.dumps(
            {
                "segments": [
                    {
                        "id": "seg_0001",
                        "source_start_ms": 0,
                        "source_end_ms": 1200,
                        "target_text": "調査当局はメンディッチが",
                    }
                ]
            },
            ensure_ascii=False,
        )
    }

    with pytest.raises(DubbingScriptError) as exc_info:
        parse_grok_dubbing_response(response, expected_segment_ids=["seg_0001"])

    assert "unfinished Japanese fragment" in str(exc_info.value)


def test_generate_dubbing_script_uses_xai_client_only():
    client = FakeXAIClient(load_response())

    result = generate_dubbing_script(client, load_segments(), model="grok-4.3")

    assert result[0]["id"] == "seg_0001"
    assert len(client.calls) == 1
    assert client.calls[0]["path"] == "/responses"
    assert client.calls[0]["payload"]["model"] == "grok-4.3"


def test_generate_dubbing_script_retries_once_for_unfinished_japanese_fragments():
    bad_response = {
        "output_text": json.dumps(
            {"segments": [{"id": "seg_0001", "target_text": "調査当局はメンディッチが"}]},
            ensure_ascii=False,
        )
    }
    repaired_response = {
        "output_text": json.dumps(
            {"segments": [{"id": "seg_0001", "target_text": "調査当局はメンディッチの出国を確認しました。"}]},
            ensure_ascii=False,
        )
    }
    client = FakeXAIClient([bad_response, repaired_response])

    result = generate_dubbing_script(client, [{"id": "seg_0001", "source_start_ms": 0, "source_end_ms": 1200}])

    assert result[0]["target_text"] == "調査当局はメンディッチの出国を確認しました。"
    assert len(client.calls) == 2
    assert "Repair only the invalid dubbing script" in client.calls[1]["payload"]["input"][-1]["content"]


def test_write_dubbing_artifacts_outputs_json_and_csv(tmp_path):
    project_dir = tmp_path / "demo"
    segments = parse_grok_dubbing_response(load_response(), expected_segment_ids=["seg_0001", "seg_0002"])

    write_dubbing_artifacts(
        project_dir,
        request_payload=build_grok_dubbing_payload(load_segments()),
        raw_response=load_response(),
        dubbing_segments=segments,
    )

    script_dir = project_dir / "script"
    assert (script_dir / "grok_dubbing_request.json").exists()
    assert (script_dir / "grok_dubbing_response.json").exists()
    assert json.loads((script_dir / "japanese_dubbing_segments.json").read_text(encoding="utf-8"))[0]["id"] == "seg_0001"
    csv_text = (script_dir / "dubbing_script.csv").read_text(encoding="utf-8")
    assert "seg_0001" in csv_text
    assert "こんにちは、デモへようこそ。" in csv_text
