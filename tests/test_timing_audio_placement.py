import json
from pathlib import Path

import pytest

from fukikae_studio.media.timing import build_narration_timeline, build_audio_mix_plan
from fukikae_studio.pipeline.assemble import write_timeline_artifacts


def manifest_with_segments(segments):
    return {
        "schema_version": "0.1",
        "provider": "xai",
        "endpoint": "/v1/tts",
        "language": "ja",
        "voice": "eve",
        "segments": segments,
    }


def test_timeline_places_exact_fit_clip_on_source_start():
    manifest = manifest_with_segments(
        [
            {
                "id": "seg_0001",
                "text": "こんにちは",
                "output_audio": "tts/segment_0001.wav",
                "duration_ms": 2400,
                "target_slot_start_ms": 0,
                "target_slot_end_ms": 2400,
            }
        ]
    )

    timeline = build_narration_timeline(manifest)

    assert timeline["clips"][0] == {
        "id": "seg_0001",
        "audio": "tts/segment_0001.wav",
        "start_ms": 0,
        "end_ms": 2400,
        "slot_end_ms": 2400,
        "raw_duration_ms": 2400,
        "effective_duration_ms": 2400,
        "atempo": 1.0,
        "status": "fits",
        "delay_filter": "adelay=0|0",
    }
    assert timeline["warnings"] == []


def test_timeline_allows_shorter_clip_and_preserves_slot_start():
    manifest = manifest_with_segments(
        [
            {
                "id": "seg_0001",
                "text": "短い",
                "output_audio": "tts/segment_0001.wav",
                "duration_ms": 1200,
                "target_slot_start_ms": 0,
                "target_slot_end_ms": 2400,
            }
        ]
    )

    clip = build_narration_timeline(manifest)["clips"][0]

    assert clip["start_ms"] == 0
    assert clip["end_ms"] == 1200
    assert clip["status"] == "fits"


def test_timeline_flags_long_clip_spillover_when_it_does_not_overlap_next_segment():
    manifest = manifest_with_segments(
        [
            {"id": "seg_0001", "text": "長い", "output_audio": "tts/segment_0001.wav", "duration_ms": 1200, "target_slot_start_ms": 0, "target_slot_end_ms": 1000},
            {"id": "seg_0002", "text": "次", "output_audio": "tts/segment_0002.wav", "duration_ms": 500, "target_slot_start_ms": 1500, "target_slot_end_ms": 2200},
        ]
    )

    timeline = build_narration_timeline(manifest)

    assert timeline["clips"][0]["status"] == "spillover"
    assert "seg_0001 exceeds source slot" in timeline["warnings"][0]


def test_timeline_tempo_fits_when_long_clip_would_overlap_next_segment():
    manifest = manifest_with_segments(
        [
            {"id": "seg_0001", "text": "長すぎる", "output_audio": "tts/segment_0001.wav", "duration_ms": 1800, "target_slot_start_ms": 0, "target_slot_end_ms": 1000},
            {"id": "seg_0002", "text": "次", "output_audio": "tts/segment_0002.wav", "duration_ms": 500, "target_slot_start_ms": 1500, "target_slot_end_ms": 2200},
        ]
    )

    timeline = build_narration_timeline(manifest)

    assert timeline["clips"][0]["status"] == "tempo_fit"
    assert timeline["clips"][0]["end_ms"] == 1500
    assert timeline["warnings"] == []


def test_timeline_allows_last_clip_to_spill_past_slot_without_tempo_fit():
    manifest = manifest_with_segments(
        [
            {"id": "seg_0001", "text": "最後", "output_audio": "tts/segment_0001.wav", "duration_ms": 1800, "target_slot_start_ms": 0, "target_slot_end_ms": 1000},
        ]
    )

    timeline = build_narration_timeline(manifest)

    clip = timeline["clips"][0]
    assert clip["status"] == "spillover"
    assert clip["end_ms"] == 1800
    assert clip["atempo"] == 1.0
    assert "seg_0001 exceeds source slot" in timeline["warnings"][0]


def test_timeline_fits_long_clip_to_next_segment_with_atempo():
    manifest = manifest_with_segments(
        [
            {"id": "seg_0001", "text": "長すぎる", "output_audio": "tts/segment_0001.wav", "duration_ms": 1800, "target_slot_start_ms": 0, "target_slot_end_ms": 1000},
            {"id": "seg_0002", "text": "次", "output_audio": "tts/segment_0002.wav", "duration_ms": 500, "target_slot_start_ms": 1500, "target_slot_end_ms": 2200},
        ]
    )

    timeline = build_narration_timeline(manifest)

    clip = timeline["clips"][0]
    assert clip["status"] == "tempo_fit"
    assert clip["end_ms"] == 1500
    assert clip["atempo"] == 1.2
    assert clip["delay_filter"] == "atempo=1.2000,adelay=0|0"
    assert timeline["warnings"] == []


def test_audio_mix_plan_is_inspectable_and_uses_delays():
    manifest = manifest_with_segments(
        [
            {"id": "seg_0001", "text": "A", "output_audio": "tts/segment_0001.wav", "duration_ms": 1000, "target_slot_start_ms": 0, "target_slot_end_ms": 1000},
            {"id": "seg_0002", "text": "B", "output_audio": "tts/segment_0002.wav", "duration_ms": 1000, "target_slot_start_ms": 1500, "target_slot_end_ms": 2500},
        ]
    )
    timeline = build_narration_timeline(manifest)

    plan = build_audio_mix_plan(timeline)

    assert plan["inputs"] == ["tts/segment_0001.wav", "tts/segment_0002.wav"]
    assert plan["filters"] == ["adelay=0|0", "adelay=1500|1500"]
    assert plan["output"] == "assembly/narration_track.wav"


def test_write_timeline_artifacts_refuses_overwrite_by_default(tmp_path):
    project_dir = tmp_path / "demo"
    assembly_dir = project_dir / "assembly"
    assembly_dir.mkdir(parents=True)
    existing = assembly_dir / "narration_timeline.json"
    existing.write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError):
        write_timeline_artifacts(project_dir, {"clips": [], "warnings": []}, overwrite=False)
