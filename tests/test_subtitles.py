import json

import pytest

from fukikae_studio.media.subtitles import build_ass, build_srt, build_webvtt
from fukikae_studio.pipeline.assemble import write_subtitle_artifacts


def japanese_segments():
    return [
        {
            "id": "seg_0001",
            "source_start_ms": 0,
            "source_end_ms": 2400,
            "source_text": "Hello, welcome to the demo.",
            "target_text": "こんにちは、デモへようこそ。",
        },
        {
            "id": "seg_0002",
            "source_start_ms": 2500,
            "source_end_ms": 4900,
            "source_text": "Let's begin.",
            "target_text": "始めましょう。",
        },
    ]


def test_build_srt_uses_target_text_and_comma_timestamps():
    assert build_srt(japanese_segments()) == (
        "1\n"
        "00:00:00,000 --> 00:00:02,400\n"
        "こんにちは、デモへようこそ。\n"
        "\n"
        "2\n"
        "00:00:02,500 --> 00:00:04,900\n"
        "始めましょう。\n"
    )


def test_build_webvtt_uses_segment_ids_and_dot_timestamps():
    assert build_webvtt(japanese_segments()) == (
        "WEBVTT\n"
        "\n"
        "seg_0001\n"
        "00:00:00.000 --> 00:00:02.400\n"
        "こんにちは、デモへようこそ。\n"
        "\n"
        "seg_0002\n"
        "00:00:02.500 --> 00:00:04.900\n"
        "始めましょう。\n"
    )


def test_build_ass_uses_sage_green_box_above_existing_lower_subtitles():
    ass = build_ass(japanese_segments())

    assert "[V4+ Styles]" in ass
    assert "Style: FukiKaeBox" in ass
    assert "&H40748B6E" in ass
    assert "MarginV" in ass
    assert "220" in ass
    assert "こんにちは、デモへようこそ。" in ass
    assert "Dialogue:" in ass


def test_subtitles_prefer_dub_timing_when_present():
    segments = [
        {
            "id": "seg_0001",
            "source_start_ms": 1000,
            "source_end_ms": 3000,
            "dub_start_ms": 1250,
            "dub_end_ms": 2750,
            "target_text": "調整済み字幕",
        }
    ]

    assert "00:00:01,250 --> 00:00:02,750" in build_srt(segments)


def test_write_subtitle_artifacts_outputs_srt_and_webvtt(tmp_path):
    project_dir = tmp_path / "demo"

    write_subtitle_artifacts(project_dir, japanese_segments())

    assembly_dir = project_dir / "assembly"
    assert (assembly_dir / "japanese_subtitles.srt").read_text(encoding="utf-8").startswith("1\n")
    assert (assembly_dir / "japanese_subtitles.vtt").read_text(encoding="utf-8").startswith("WEBVTT\n")
    assert (assembly_dir / "japanese_subtitles.ass").read_text(encoding="utf-8").startswith("[Script Info]\n")
    manifest = json.loads((assembly_dir / "subtitle_manifest.json").read_text(encoding="utf-8"))
    assert manifest == {
        "schema_version": "0.1",
        "language": "ja",
        "formats": {
            "srt": "assembly/japanese_subtitles.srt",
            "webvtt": "assembly/japanese_subtitles.vtt",
            "ass": "assembly/japanese_subtitles.ass",
        },
    }


def test_write_subtitle_artifacts_refuses_overwrite_by_default(tmp_path):
    project_dir = tmp_path / "demo"
    assembly_dir = project_dir / "assembly"
    assembly_dir.mkdir(parents=True)
    (assembly_dir / "japanese_subtitles.srt").write_text("existing\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        write_subtitle_artifacts(project_dir, japanese_segments(), overwrite=False)
