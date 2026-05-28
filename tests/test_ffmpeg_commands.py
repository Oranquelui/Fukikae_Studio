from pathlib import Path

import pytest

from fukikae_studio.media.extract_audio import (
    build_extract_audio_command,
    build_project_audio_extraction_command,
)
from fukikae_studio.media.audio_mix import build_narration_mix_command
from fukikae_studio.media.ffmpeg import MediaPathError, MediaToolError, require_media_tool
from fukikae_studio.media.metadata import build_ffprobe_metadata_command


def test_ffprobe_metadata_command_is_json_and_read_only():
    command = build_ffprobe_metadata_command(Path("input/source.mp4"))

    assert command == [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        "input/source.mp4",
    ]


def test_ffmpeg_audio_extraction_command_is_stt_ready_and_non_overwriting():
    command = build_extract_audio_command(
        Path("input/source.mp4"),
        Path("media/source_audio_for_stt.wav"),
    )

    assert command == [
        "ffmpeg",
        "-nostdin",
        "-n",
        "-i",
        "input/source.mp4",
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        "media/source_audio_for_stt.wav",
    ]
    assert "yt-dlp" not in command


def test_ffmpeg_audio_extraction_requires_explicit_overwrite():
    command = build_extract_audio_command(
        Path("input/source.mp4"),
        Path("media/source_audio_for_stt.wav"),
        overwrite=True,
    )

    assert "-y" in command
    assert "-n" not in command


def test_project_audio_extraction_refuses_output_outside_project(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    source_video = project_dir / "input" / "source.mp4"
    outside_output = tmp_path / "outside.wav"

    with pytest.raises(MediaPathError) as exc_info:
        build_project_audio_extraction_command(project_dir, source_video, outside_output)

    assert "inside project" in str(exc_info.value)


def test_media_tool_check_reports_missing_executable_without_shelling_out():
    with pytest.raises(MediaToolError) as exc_info:
        require_media_tool("definitely-missing-tool", which=lambda name: None)

    assert "definitely-missing-tool" in str(exc_info.value)
    assert "not found" in str(exc_info.value).lower()


def test_audio_mix_command_applies_atempo_before_delay_when_timeline_requires_fit(tmp_path):
    project_dir = tmp_path / "demo"
    (project_dir / "tts").mkdir(parents=True)
    (project_dir / "tts" / "segment_0001.mp3").write_bytes(b"fake")

    command = build_narration_mix_command(
        project_dir,
        {
            "clips": [
                {
                    "audio": "tts/segment_0001.mp3",
                    "start_ms": 760,
                    "atempo": 1.2649,
                }
            ]
        },
    )

    filter_graph = command[command.index("-filter_complex") + 1]
    assert "[0:a]atempo=1.2649,adelay=760|760[a0]" in filter_graph
