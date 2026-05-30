import json
from pathlib import Path

import pytest

from fukikae_studio.media.ffmpeg import MediaPathError
from fukikae_studio.media.final_mux import (
    build_burned_subtitle_mux_command,
    build_final_mux_command,
    build_project_final_mux_command,
)
from fukikae_studio.pipeline.assemble import assemble_project, write_final_mux_plan


def test_final_mux_command_copies_video_replaces_audio_and_embeds_soft_subtitles():
    command = build_final_mux_command(
        source_video=Path("input/source.mp4"),
        narration_audio=Path("assembly/narration_track.wav"),
        subtitles_srt=Path("assembly/japanese_subtitles.srt"),
        output_mp4=Path("output/dubbed.ja.mp4"),
    )

    assert command == [
        "ffmpeg",
        "-nostdin",
        "-n",
        "-i",
        "input/source.mp4",
        "-i",
        "assembly/narration_track.wav",
        "-i",
        "assembly/japanese_subtitles.srt",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-map",
        "2:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-c:s",
        "mov_text",
        "-metadata:s:s:0",
        "language=jpn",
        "-disposition:s:0",
        "default",
        "output/dubbed.ja.mp4",
    ]
    assert "yt-dlp" not in command


def test_final_mux_command_uses_english_subtitle_metadata_when_requested():
    command = build_final_mux_command(
        source_video=Path("input/source.mp4"),
        narration_audio=Path("assembly/narration_track.wav"),
        subtitles_srt=Path("assembly/english_subtitles.srt"),
        output_mp4=Path("output/dubbed.en.mp4"),
        subtitle_language="eng",
    )

    assert "language=eng" in command
    assert "language=jpn" not in command
    assert command[-1] == "output/dubbed.en.mp4"


def test_final_mux_command_requires_explicit_overwrite():
    command = build_final_mux_command(
        source_video=Path("input/source.mp4"),
        narration_audio=Path("assembly/narration_track.wav"),
        subtitles_srt=Path("assembly/japanese_subtitles.srt"),
        output_mp4=Path("output/dubbed.ja.mp4"),
        overwrite=True,
    )

    assert "-y" in command
    assert "-n" not in command


def test_burned_subtitle_mux_command_uses_png_overlay_filter_and_reencodes_video():
    command = build_burned_subtitle_mux_command(
        source_video=Path("input/source.mp4"),
        narration_audio=Path("assembly/narration_track.wav"),
        subtitle_overlays=[
            {
                "image": Path("assembly/subtitle_overlays/seg_0001.png"),
                "start_ms": 760,
                "end_ms": 7550,
            }
        ],
        output_mp4=Path("output/dubbed.ja.burned.mp4"),
        duration_ms=69800,
        overwrite=True,
    )

    assert command[:4] == ["ffmpeg", "-nostdin", "-y", "-i"]
    assert "-vf" not in command
    assert "subtitles=" not in " ".join(command)
    assert "-loop" in command
    assert "assembly/subtitle_overlays/seg_0001.png" in command
    assert "-filter_complex" in command
    filter_complex = command[command.index("-filter_complex") + 1]
    assert "overlay=x=0:y=0:enable='between(t,0.760,7.550)':shortest=1:eof_action=pass:repeatlast=0" in filter_complex
    assert command[command.index("-t") + 1] == "69.800"
    assert "-c:v" in command
    assert "libx264" in command
    assert command[-1] == "output/dubbed.ja.burned.mp4"


def test_burned_subtitle_mux_command_uses_video_mapping_when_no_overlays():
    command = build_burned_subtitle_mux_command(
        source_video=Path("input/source.mp4"),
        narration_audio=Path("assembly/narration_track.wav"),
        subtitle_overlays=[],
        output_mp4=Path("output/dubbed.ja.burned.mp4"),
    )

    assert "-filter_complex" not in command
    assert command[command.index("-map") + 1] == "0:v:0"


def test_project_final_mux_refuses_output_outside_project(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()

    with pytest.raises(MediaPathError) as exc_info:
        build_project_final_mux_command(project_dir, output_mp4=tmp_path / "outside.mp4")

    assert "inside project" in str(exc_info.value)


def test_write_final_mux_plan_outputs_inspectable_command_plan(tmp_path):
    project_dir = tmp_path / "demo"

    plan = write_final_mux_plan(project_dir)

    plan_path = project_dir / "assembly" / "final_mux_plan.json"
    written = json.loads(plan_path.read_text(encoding="utf-8"))
    assert written == plan
    assert written["schema_version"] == "0.1"
    assert written["strategy"] == "copy_video_replace_audio_soft_subtitles"
    assert written["output"] == str(project_dir / "output" / "dubbed.ja.mp4")
    assert written["command"][-1] == str(project_dir / "output" / "dubbed.ja.mp4")


def test_write_final_mux_plan_outputs_language_specific_english_paths(tmp_path):
    project_dir = tmp_path / "demo"

    plan = write_final_mux_plan(project_dir, language="en")

    assert plan["inputs"]["subtitles_srt"] == str(project_dir / "assembly" / "english_subtitles.srt")
    assert plan["output"] == str(project_dir / "output" / "dubbed.en.mp4")
    assert "language=eng" in plan["command"]


def test_write_final_mux_plan_refuses_overwrite_by_default(tmp_path):
    project_dir = tmp_path / "demo"
    assembly_dir = project_dir / "assembly"
    assembly_dir.mkdir(parents=True)
    (assembly_dir / "final_mux_plan.json").write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError):
        write_final_mux_plan(project_dir, overwrite=False)


def test_assemble_project_writes_final_mux_artifacts_from_tts_and_script_inputs(tmp_path):
    project_dir = tmp_path / "demo"
    tts_dir = project_dir / "tts"
    script_dir = project_dir / "script"
    tts_dir.mkdir(parents=True)
    script_dir.mkdir(parents=True)
    (tts_dir / "xai_tts_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "language": "ja",
                "segments": [
                    {
                        "id": "seg_0001",
                        "text": "こんにちは",
                        "output_audio": "tts/segment_0001.wav",
                        "duration_ms": 1000,
                        "target_slot_start_ms": 0,
                        "target_slot_end_ms": 1200,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (script_dir / "japanese_dubbing_segments.json").write_text(
        json.dumps(
            [
                {
                    "id": "seg_0001",
                    "source_start_ms": 0,
                    "source_end_ms": 1200,
                    "target_text": "こんにちは",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    manifest = assemble_project(project_dir)

    assembly_dir = project_dir / "assembly"
    assert manifest["artifacts"]["final_mux_plan"] == "assembly/final_mux_plan.json"
    assert (assembly_dir / "narration_timeline.json").exists()
    assert (assembly_dir / "mix_plan.json").exists()
    assert (assembly_dir / "japanese_subtitles.srt").exists()
    final_plan = json.loads((assembly_dir / "final_mux_plan.json").read_text(encoding="utf-8"))
    assert final_plan["output"] == str(project_dir / "output" / "dubbed.ja.mp4")


def test_assemble_project_writes_english_subtitle_and_output_artifacts(tmp_path):
    project_dir = tmp_path / "demo"
    tts_dir = project_dir / "tts"
    script_dir = project_dir / "script"
    tts_dir.mkdir(parents=True)
    script_dir.mkdir(parents=True)
    (tts_dir / "xai_tts_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "language": "en",
                "segments": [
                    {
                        "id": "seg_0001",
                        "text": "Welcome.",
                        "output_audio": "tts/segment_0001.wav",
                        "duration_ms": 1000,
                        "target_slot_start_ms": 0,
                        "target_slot_end_ms": 1200,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (script_dir / "english_dubbing_segments.json").write_text(
        json.dumps(
            [
                {
                    "id": "seg_0001",
                    "source_start_ms": 0,
                    "source_end_ms": 1200,
                    "target_text": "Welcome.",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    manifest = assemble_project(project_dir)

    assembly_dir = project_dir / "assembly"
    assert manifest["artifacts"]["subtitles_srt"] == "assembly/english_subtitles.srt"
    assert (assembly_dir / "english_subtitles.srt").exists()
    assert not (assembly_dir / "japanese_subtitles.srt").exists()
    final_plan = json.loads((assembly_dir / "final_mux_plan.json").read_text(encoding="utf-8"))
    assert final_plan["output"] == str(project_dir / "output" / "dubbed.en.mp4")
