import importlib.util
import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE_SCRIPT = REPO_ROOT / "scripts" / "local_beta_smoke.py"


def load_smoke_module():
    spec = importlib.util.spec_from_file_location("local_beta_smoke", SMOKE_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_local_beta_smoke_builds_synthetic_media_commands_without_network():
    smoke = load_smoke_module()

    video_command = smoke.build_sample_video_command(Path("/tmp/source.mp4"))
    audio_command = smoke.build_fixture_audio_command(Path("/tmp/fixture.wav"))

    assert video_command[:4] == ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    assert "testsrc=size=320x180:rate=25" in video_command
    assert "sine=frequency=440:sample_rate=48000" in video_command
    assert str(Path("/tmp/source.mp4")) == video_command[-1]
    assert audio_command[:4] == ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    assert "sine=frequency=880:duration=0.8:sample_rate=16000" in audio_command
    assert str(Path("/tmp/fixture.wav")) == audio_command[-1]
    assert not any(token.startswith("http") for token in video_command + audio_command)


def test_local_beta_smoke_summarizes_ffprobe_streams():
    smoke = load_smoke_module()

    summary = smoke.summarize_streams(
        {
            "streams": [
                {"index": 0, "codec_type": "video", "codec_name": "h264", "tags": {"language": "und"}},
                {"index": 1, "codec_type": "audio", "codec_name": "aac", "tags": {"language": "jpn"}},
                {"index": 2, "codec_type": "subtitle", "codec_name": "mov_text", "tags": {"language": "jpn"}},
            ]
        }
    )

    assert summary == [
        {"index": 0, "type": "video", "codec": "h264", "language": "und"},
        {"index": 1, "type": "audio", "codec": "aac", "language": "jpn"},
        {"index": 2, "type": "subtitle", "codec": "mov_text", "language": "jpn"},
    ]


def test_local_beta_smoke_validates_complete_report_and_final_output():
    smoke = load_smoke_module()

    smoke.validate_beta_report(
        {
            "status": "complete",
            "missing_required_artifacts": [],
            "final_output_exists": True,
        }
    )


def test_local_beta_smoke_preserves_requested_absolute_workdir_for_readable_output():
    smoke = load_smoke_module()
    requested = Path("/tmp/fukikae-smoke-readable-path-test")
    shutil.rmtree(requested, ignore_errors=True)

    workdir, created_temp = smoke._prepare_workdir(requested)

    try:
        assert workdir == requested
        assert created_temp is False
    finally:
        shutil.rmtree(requested, ignore_errors=True)
