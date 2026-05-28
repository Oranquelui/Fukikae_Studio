import json
from pathlib import Path

import pytest

from fukikae_studio.ai.schemas import NORMALIZED_SEGMENT_FIELDS, SEGMENT_SCHEMA_VERSION
from fukikae_studio.transcript.segments import Segment, dump_segments_json, load_segments_json
from fukikae_studio.transcript.validation import SegmentValidationError, validate_segments

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_segments.json"


def test_segment_schema_contract_is_versioned_and_names_required_fields():
    assert SEGMENT_SCHEMA_VERSION == "0.1"
    assert NORMALIZED_SEGMENT_FIELDS[:6] == (
        "id",
        "source_start_ms",
        "source_end_ms",
        "speaker",
        "source_lang",
        "source_text",
    )
    assert "target_lang" in NORMALIZED_SEGMENT_FIELDS


def test_valid_segment_parsing_defaults_target_language_and_dub_timing():
    segment = Segment.from_dict(
        {
            "id": "seg_0001",
            "source_start_ms": 0,
            "source_end_ms": 1200,
            "source_text": "Hello",
        }
    )

    assert segment.target_lang == "ja"
    assert segment.dub_start_ms == 0
    assert segment.dub_end_ms == 1200
    assert segment.to_dict()["status"] == "stt_complete"


def test_load_and_dump_segments_json_round_trip_fixture():
    segments = load_segments_json(FIXTURE_PATH)

    validate_segments(segments)
    dumped = dump_segments_json(segments)
    data = json.loads(dumped)

    assert len(data) == 2
    assert data[0]["id"] == "seg_0001"
    assert data[0]["target_lang"] == "ja"


@pytest.mark.parametrize(
    "bad_segment, expected_message",
    [
        (
            {"id": "seg_bad_time", "source_start_ms": 1000, "source_end_ms": 1000, "source_text": "Bad"},
            "timing",
        ),
        (
            {"id": "seg_missing_text", "source_start_ms": 0, "source_end_ms": 1000, "source_text": ""},
            "source_text",
        ),
        (
            {
                "id": "seg_bad_lang",
                "source_start_ms": 0,
                "source_end_ms": 1000,
                "source_text": "Bad",
                "target_lang": "japanese",
            },
            "target_lang",
        ),
    ],
)
def test_segment_validation_identifies_bad_segment_ids(bad_segment, expected_message):
    segment = Segment.from_dict(bad_segment)

    with pytest.raises(SegmentValidationError) as exc_info:
        validate_segments([segment])

    message = str(exc_info.value)
    assert bad_segment["id"] in message
    assert expected_message in message


def test_segment_validation_rejects_overlapping_segments():
    first = Segment.from_dict({"id": "seg_0001", "source_start_ms": 0, "source_end_ms": 1500, "source_text": "A"})
    second = Segment.from_dict({"id": "seg_0002", "source_start_ms": 1200, "source_end_ms": 2000, "source_text": "B"})

    with pytest.raises(SegmentValidationError) as exc_info:
        validate_segments([first, second])

    assert "seg_0002" in str(exc_info.value)
    assert "overlap" in str(exc_info.value)
