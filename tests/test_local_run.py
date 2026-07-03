import json
import os
import subprocess
import sys
from pathlib import Path

from fukikae_studio.pipeline.local_run import init_project, run_fixture_pipeline, validate_project


def test_init_project_copies_source_video_and_writes_manifest(tmp_path):
    source_video = tmp_path / "source.mov"
    source_video.write_bytes(b"fake-video")
    project_dir = tmp_path / "demo"

    manifest = init_project(
        project_dir,
        source_video=source_video,
        source_lang="en",
        target_lang="ja",
    )

    assert manifest == {
        "schema_version": "0.1",
        "source_lang": "en",
        "target_lang": "ja",
        "input": {
            "source_video": "input/source.mp4",
            "original_filename": "source.mov",
        },
    }
    assert (project_dir / "input" / "source.mp4").read_bytes() == b"fake-video"
    assert json.loads((project_dir / "project.json").read_text(encoding="utf-8")) == manifest


def test_init_project_refuses_to_overwrite_by_default(tmp_path):
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"new-video")
    project_dir = tmp_path / "demo"
    (project_dir / "input").mkdir(parents=True)
    (project_dir / "input" / "source.mp4").write_bytes(b"existing-video")

    try:
        init_project(project_dir, source_video=source_video)
    except FileExistsError as exc:
        assert "Refusing to overwrite" in str(exc)
    else:
        raise AssertionError("init_project should refuse to overwrite existing source video")

    assert (project_dir / "input" / "source.mp4").read_bytes() == b"existing-video"


def test_validate_project_reports_ready_for_local_mux_plan(tmp_path):
    project_dir = tmp_path / "demo"
    for relative_path in [
        "input/source.mp4",
        "stt/normalized_segments.json",
        "script/japanese_dubbing_segments.json",
        "tts/xai_tts_manifest.json",
        "assembly/narration_timeline.json",
        "assembly/mix_plan.json",
        "assembly/japanese_subtitles.srt",
        "assembly/japanese_subtitles.vtt",
        "assembly/subtitle_manifest.json",
        "assembly/final_mux_plan.json",
        "assembly/assembly_manifest.json",
    ]:
        path = project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

    report = validate_project(project_dir)

    assert report["schema_version"] == "0.1"
    assert report["status"] == "ready_for_final_mux"
    assert report["missing_required_artifacts"] == []
    assert report["final_output_exists"] is False
    assert json.loads((project_dir / "validation" / "local_test_report.json").read_text(encoding="utf-8")) == report


def test_run_fixture_pipeline_creates_locally_testable_project(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    source_video = tmp_path / "source.mp4"
    fixture_audio = tmp_path / "fixture.wav"
    source_video.write_bytes(b"fake-video")
    fixture_audio.write_bytes(b"fake-audio")
    project_dir = tmp_path / "demo"

    result = run_fixture_pipeline(
        project_dir,
        source_video=source_video,
        stt_fixture_response=repo_root / "tests" / "fixtures" / "sample_stt_response.json",
        dubbing_fixture_response=repo_root / "tests" / "fixtures" / "sample_dubbing_response.json",
        fixture_audio=fixture_audio,
        source_lang="auto",
        target_lang="ja",
        voice="eve",
    )

    assert result["validation"]["status"] == "ready_for_final_mux"
    assert (project_dir / "input" / "source.mp4").read_bytes() == b"fake-video"
    assert (project_dir / "stt" / "normalized_segments.json").exists()
    assert (project_dir / "script" / "japanese_dubbing_segments.json").exists()
    request = json.loads((project_dir / "script" / "grok_dubbing_request.json").read_text(encoding="utf-8"))
    request_prompt = request["input"][1]["content"]
    assert '"target_text": null' in request_prompt
    assert '"target_text": "こんにちは、デモへようこそ。"' not in request_prompt
    assert (project_dir / "tts" / "segment_0001.wav").read_bytes() == b"fake-audio"
    assert (project_dir / "assembly" / "assembly_manifest.json").exists()
    final_plan = json.loads((project_dir / "assembly" / "final_mux_plan.json").read_text(encoding="utf-8"))
    assert final_plan["output"] == str(project_dir / "output" / "dubbed.ja.mp4")


def test_run_fixture_pipeline_executes_media_commands_and_reports_complete(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    source_video = tmp_path / "source.mp4"
    fixture_audio = tmp_path / "fixture.wav"
    source_video.write_bytes(b"fake-video")
    fixture_audio.write_bytes(b"fake-audio")
    project_dir = tmp_path / "demo"
    commands = []

    def fake_media_runner(command):
        commands.append(command)
        output_path = Path(command[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"rendered-media")

    result = run_fixture_pipeline(
        project_dir,
        source_video=source_video,
        stt_fixture_response=repo_root / "tests" / "fixtures" / "sample_stt_response.json",
        dubbing_fixture_response=repo_root / "tests" / "fixtures" / "sample_dubbing_response.json",
        fixture_audio=fixture_audio,
        execute_ffmpeg=True,
        media_runner=fake_media_runner,
    )

    assert result["validation"]["status"] == "complete"
    assert result["validation"]["final_output"] == "output/dubbed.ja.burned.mp4"
    assert len(commands) == 3
    assert commands[0][0] == "ffmpeg"
    assert any("amix=inputs=2" in part for part in commands[0])
    assert commands[0][-1] == str(project_dir / "assembly" / "narration_track.wav")
    assert commands[1][-1] == str(project_dir / "output" / "dubbed.ja.mp4")
    assert commands[2][-1] == str(project_dir / "output" / "dubbed.ja.burned.mp4")


def test_run_fixture_pipeline_can_render_burned_subtitle_output_only(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    source_video = tmp_path / "source.mp4"
    fixture_audio = tmp_path / "fixture.wav"
    source_video.write_bytes(b"fake-video")
    fixture_audio.write_bytes(b"fake-audio")
    project_dir = tmp_path / "demo"
    commands = []

    def fake_media_runner(command):
        commands.append(command)
        output_path = Path(command[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"rendered-media")

    result = run_fixture_pipeline(
        project_dir,
        source_video=source_video,
        stt_fixture_response=repo_root / "tests" / "fixtures" / "sample_stt_response.json",
        dubbing_fixture_response=repo_root / "tests" / "fixtures" / "sample_dubbing_response.json",
        fixture_audio=fixture_audio,
        execute_ffmpeg=True,
        media_runner=fake_media_runner,
        subtitle_output="burned",
        subtitle_style={
            "background_color": "#102030",
            "font_color": "#F4EBDD",
            "font_size": 58,
        },
    )

    assert result["validation"]["status"] == "complete"
    assert result["validation"]["final_output"] == "output/dubbed.ja.burned.mp4"
    assert len(commands) == 2
    assert commands[-1][-1] == str(project_dir / "output" / "dubbed.ja.burned.mp4")
    assert all(command[-1] != str(project_dir / "output" / "dubbed.ja.mp4") for command in commands)
    overlay_manifest = json.loads(
        (project_dir / "assembly" / "subtitle_overlays" / "subtitle_overlay_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert overlay_manifest["style"]["background_color"] == "#102030"
    assert overlay_manifest["style"]["font_color"] == "#F4EBDD"
    assert overlay_manifest["style"]["font_size"] == 58


def test_run_fixture_pipeline_can_render_subtitles_without_tts_or_dubbed_audio(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    source_video = tmp_path / "source.mp4"
    fixture_audio = tmp_path / "fixture.wav"
    source_video.write_bytes(b"fake-video")
    fixture_audio.write_bytes(b"fake-audio")
    project_dir = tmp_path / "demo"
    commands = []

    def fake_media_runner(command):
        commands.append(command)
        output_path = Path(command[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"rendered-media")

    result = run_fixture_pipeline(
        project_dir,
        source_video=source_video,
        stt_fixture_response=repo_root / "tests" / "fixtures" / "sample_stt_response.json",
        dubbing_fixture_response=repo_root / "tests" / "fixtures" / "sample_dubbing_response.json",
        fixture_audio=fixture_audio,
        execute_ffmpeg=True,
        media_runner=fake_media_runner,
        subtitle_output="soft",
        processing_mode="subtitles",
    )

    assert result["validation"]["status"] == "complete"
    assert result["validation"]["final_output"] == "output/subtitled.ja.mp4"
    assert not (project_dir / "tts" / "xai_tts_manifest.json").exists()
    assert not (project_dir / "assembly" / "narration_timeline.json").exists()
    assert (project_dir / "assembly" / "japanese_subtitles.srt").exists()
    assert len(commands) == 1
    assert commands[0][-1] == str(project_dir / "output" / "subtitled.ja.mp4")
    assert "0:a:0?" in commands[0]


def test_run_command_executes_fixture_pipeline_and_prints_validation_report(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src") + os.pathsep + env.get("PYTHONPATH", "")
    source_video = tmp_path / "source.mp4"
    fixture_audio = tmp_path / "fixture.wav"
    source_video.write_bytes(b"fake-video")
    fixture_audio.write_bytes(b"fake-audio")
    project_dir = tmp_path / "demo"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fukikae_studio",
            "run",
            "--video",
            str(source_video),
            "--project",
            str(project_dir),
            "--fixture-stt-response",
            str(repo_root / "tests" / "fixtures" / "sample_stt_response.json"),
            "--fixture-dubbing-response",
            str(repo_root / "tests" / "fixtures" / "sample_dubbing_response.json"),
            "--fixture-audio",
            str(fixture_audio),
        ],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    report_path = project_dir / "validation" / "local_test_report.json"
    assert result.stdout.strip() == str(report_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "ready_for_final_mux"
