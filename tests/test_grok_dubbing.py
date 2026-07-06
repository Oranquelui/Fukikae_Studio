import json
from pathlib import Path

import pytest

from fukikae_studio.ai.grok_dubbing import (
    DubbingScriptError,
    build_grok_dubbing_payload,
    build_grok_dubbing_review_payload,
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


def test_prompt_supports_english_dubbing_for_japanese_source_video():
    prompt = build_dubbing_prompt(load_segments(), target_lang="en", style="natural-english-dub")

    assert "target_lang=en" in prompt
    assert "natural English dubbing" in prompt
    assert "complete English utterance" in prompt
    assert "dangling Japanese particles" not in prompt


def test_prompt_requires_faithful_segment_translation_not_news_summary():
    prompt = build_dubbing_prompt(
        [
            {
                "id": "seg_0001",
                "source_start_ms": 1200,
                "source_end_ms": 3600,
                "speaker": "SPEAKER_00",
                "source_lang": "ja",
                "source_text": "この度は大変申し訳ございませんでした。",
                "target_lang": "en",
            }
        ],
        target_lang="en",
        style="natural-english-dub",
    )

    assert "Translate each source_text faithfully" in prompt
    assert "Do not summarize the clip" in prompt
    assert "Do not rewrite the segment as news narration" in prompt
    assert "first person apology" in prompt
    assert "I am truly sorry for this." in prompt


def test_prompt_requires_english_news_translation_to_preserve_numbers_denials_and_roles():
    prompt = build_dubbing_prompt(
        [
            {
                "id": "seg_0001",
                "source_start_ms": 1200,
                "source_end_ms": 3600,
                "speaker": "SPEAKER_00",
                "source_lang": "ja",
                "source_text": "去年11月時点の全市民およそ11万5千人の個人情報が含まれる業務用PC83台のうち1台が盗まれました。",
                "target_lang": "en",
            },
            {
                "id": "seg_0002",
                "source_start_ms": 3600,
                "source_end_ms": 6200,
                "speaker": "SPEAKER_00",
                "source_lang": "ja",
                "source_text": "4月の時点では個人情報の流出はないと説明していました。",
                "target_lang": "en",
            },
        ],
        target_lang="en",
        style="natural-english-dub",
    )

    assert "broadcast-news English" in prompt
    assert "about 115,000 residents" in prompt
    assert "83 work computers" in prompt
    assert "no leak of personal information" in prompt
    assert "Do not replace spoken content with a role label" in prompt


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


def test_parse_grok_response_allows_target_fragment_when_source_segment_is_also_unfinished():
    response = {
        "output_text": json.dumps(
            {
                "segments": [
                    {
                        "id": "seg_0008",
                        "source_start_ms": 7000,
                        "source_end_ms": 8200,
                        "source_text": "Investigators said Mendic",
                        "target_text": "調査当局はメンディッチが",
                    }
                ]
            },
            ensure_ascii=False,
        )
    }

    parsed = parse_grok_dubbing_response(response, expected_segment_ids=["seg_0008"])

    assert parsed[0]["target_text"] == "調査当局はメンディッチが"


def test_parse_grok_response_rejects_empty_target_text():
    response = {
        "output_text": json.dumps(
            {
                "segments": [
                    {
                        "id": "seg_0001",
                        "source_start_ms": 0,
                        "source_end_ms": 1200,
                        "source_text": "ないと説明していました",
                        "target_text": "",
                    }
                ]
            },
            ensure_ascii=False,
        )
    }

    with pytest.raises(DubbingScriptError) as exc_info:
        parse_grok_dubbing_response(response, expected_segment_ids=["seg_0001"])

    assert "empty target_text" in str(exc_info.value)


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


def test_build_review_payload_compares_source_and_candidate_segments():
    source_segments = [
        {
            "id": "seg_0001",
            "source_start_ms": 0,
            "source_end_ms": 2200,
            "speaker": "SPEAKER_00",
            "source_text": "この度は大変申し訳ございませんでした。",
        }
    ]
    candidate_segments = [
        {
            "id": "seg_0001",
            "source_start_ms": 0,
            "source_end_ms": 2200,
            "speaker": "SPEAKER_00",
            "source_text": "この度は大変申し訳ございませんでした。",
            "target_text": "Matsumoto City Mayor.",
        }
    ]

    payload = build_grok_dubbing_review_payload(source_segments, candidate_segments, target_lang="en")
    prompt = payload["input"][1]["content"]

    assert payload["model"] == "grok-4.3"
    assert "Review and repair" in prompt
    assert "Matsumoto City Mayor." in prompt
    assert "この度は大変申し訳ございませんでした。" in prompt
    assert "role label" in prompt
    assert "I am truly sorry for this." in prompt


def test_generate_dubbing_script_can_run_english_quality_review_before_tts():
    source_segments = [
        {
            "id": "seg_0001",
            "source_start_ms": 0,
            "source_end_ms": 2200,
            "speaker": "SPEAKER_00",
            "source_text": "この度は大変申し訳ございませんでした。",
        }
    ]
    first_response = {
        "output_text": json.dumps(
            {
                "segments": [
                    {
                        "id": "seg_0001",
                        "source_start_ms": 0,
                        "source_end_ms": 2200,
                        "speaker": "SPEAKER_00",
                        "source_text": "この度は大変申し訳ございませんでした。",
                        "target_text": "Matsumoto City Mayor.",
                        "estimated_duration_ms": 1200,
                    }
                ]
            },
            ensure_ascii=False,
        )
    }
    reviewed_response = {
        "output_text": json.dumps(
            {
                "segments": [
                    {
                        "id": "seg_0001",
                        "source_start_ms": 0,
                        "source_end_ms": 2200,
                        "speaker": "SPEAKER_00",
                        "source_text": "この度は大変申し訳ございませんでした。",
                        "target_text": "I am truly sorry for this.",
                        "estimated_duration_ms": 1500,
                    }
                ]
            },
            ensure_ascii=False,
        )
    }
    client = FakeXAIClient([first_response, reviewed_response])

    result = generate_dubbing_script(client, source_segments, target_lang="en", quality_review=True)

    assert result[0]["target_text"] == "I am truly sorry for this."
    assert len(client.calls) == 2
    assert "Review and repair" in client.calls[1]["payload"]["input"][1]["content"]


def test_generate_dubbing_script_repairs_empty_review_target_text():
    source_segments = [
        {
            "id": "seg_0001",
            "source_start_ms": 0,
            "source_end_ms": 1300,
            "speaker": "SPEAKER_00",
            "source_text": "ないと説明していました",
        }
    ]
    first_response = {
        "output_text": json.dumps(
            {
                "segments": [
                    {
                        "id": "seg_0001",
                        "source_start_ms": 0,
                        "source_end_ms": 1300,
                        "speaker": "SPEAKER_00",
                        "source_text": "ないと説明していました",
                        "target_text": "The city said there was no leak.",
                        "estimated_duration_ms": 1200,
                    }
                ]
            },
            ensure_ascii=False,
        )
    }
    empty_review_response = {
        "output_text": json.dumps(
            {
                "segments": [
                    {
                        "id": "seg_0001",
                        "source_start_ms": 0,
                        "source_end_ms": 1300,
                        "speaker": "SPEAKER_00",
                        "source_text": "ないと説明していました",
                        "target_text": "",
                        "estimated_duration_ms": 0,
                    }
                ]
            },
            ensure_ascii=False,
        )
    }
    repaired_review_response = {
        "output_text": json.dumps(
            {
                "segments": [
                    {
                        "id": "seg_0001",
                        "source_start_ms": 0,
                        "source_end_ms": 1300,
                        "speaker": "SPEAKER_00",
                        "source_text": "ないと説明していました",
                        "target_text": "The city said there was no leak.",
                        "estimated_duration_ms": 1200,
                    }
                ]
            },
            ensure_ascii=False,
        )
    }
    client = FakeXAIClient([first_response, empty_review_response, repaired_review_response])

    result = generate_dubbing_script(client, source_segments, target_lang="en", quality_review=True)

    assert result[0]["target_text"] == "The city said there was no leak."
    assert len(client.calls) == 3
    assert "empty target_text" in client.calls[2]["payload"]["input"][-1]["content"]


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
