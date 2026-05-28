#!/usr/bin/env python3
# pyright: reportMissingImports=false
"""Run a fixture-backed local beta smoke test for FukiKae Studio.

The script creates synthetic media, runs the local fixture-backed pipeline,
validates the report, and prints a compact ffprobe stream summary. It does not
read API keys, `.env`, or make network calls.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from fukikae_studio.pipeline.local_run import run_fixture_pipeline  # noqa: E402


DEFAULT_STT_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "sample_stt_response.json"
DEFAULT_DUBBING_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "sample_dubbing_response.json"


def build_sample_video_command(output_path: Path) -> list[str]:
    """Build the FFmpeg command for a tiny synthetic source MP4."""

    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=320x180:rate=25",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000",
        "-t",
        "5",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(output_path),
    ]


def build_fixture_audio_command(output_path: Path) -> list[str]:
    """Build the FFmpeg command for a tiny synthetic TTS fixture WAV."""

    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=880:duration=0.8:sample_rate=16000",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ]


def summarize_streams(ffprobe_payload: Mapping[str, Any]) -> list[dict[str, object]]:
    """Return a stable, compact stream summary from ffprobe JSON."""

    summary: list[dict[str, object]] = []
    for stream in ffprobe_payload.get("streams", []):
        if not isinstance(stream, Mapping):
            continue
        tags = stream.get("tags", {})
        if not isinstance(tags, Mapping):
            tags = {}
        summary.append(
            {
                "index": stream.get("index"),
                "type": stream.get("codec_type"),
                "codec": stream.get("codec_name"),
                "language": tags.get("language", "und"),
            }
        )
    return summary


def validate_beta_report(report: Mapping[str, Any]) -> None:
    """Raise a clear error if the local beta validation report is not complete."""

    if report.get("status") != "complete":
        raise RuntimeError(f"Validation status was not complete: {report.get('status')!r}")
    missing = list(report.get("missing_required_artifacts", []))
    if missing:
        raise RuntimeError(f"Validation report has missing artifacts: {missing}")
    if report.get("final_output_exists") is not True:
        raise RuntimeError("Validation report says final output does not exist")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a fixture-backed local beta smoke test. This creates synthetic "
            "media, calls the local pipeline, and does not use live xAI/Grok APIs."
        )
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        help="Work directory for generated smoke artifacts. Defaults to a temp directory under /tmp.",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep generated artifacts after the smoke test finishes.",
    )
    parser.add_argument(
        "--stt-fixture-response",
        type=Path,
        default=DEFAULT_STT_FIXTURE,
        help="Sanitized STT fixture JSON. Defaults to tests/fixtures/sample_stt_response.json.",
    )
    parser.add_argument(
        "--dubbing-fixture-response",
        type=Path,
        default=DEFAULT_DUBBING_FIXTURE,
        help="Sanitized dubbing fixture JSON. Defaults to tests/fixtures/sample_dubbing_response.json.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    workdir, created_temp = _prepare_workdir(args.workdir)
    project_dir = workdir / "project"
    source_video = workdir / "source.mp4"
    fixture_audio = workdir / "fixture.wav"

    try:
        _require_command("ffmpeg")
        _require_command("ffprobe")
        _run(build_sample_video_command(source_video))
        _run(build_fixture_audio_command(fixture_audio))

        result = run_fixture_pipeline(
            project_dir,
            source_video=source_video,
            stt_fixture_response=args.stt_fixture_response,
            dubbing_fixture_response=args.dubbing_fixture_response,
            fixture_audio=fixture_audio,
            overwrite=True,
            execute_ffmpeg=True,
            subtitle_output="soft",
        )
        validation = dict(result.get("validation", {}))
        validate_beta_report(validation)

        final_output = project_dir / str(validation.get("final_output", "output/dubbed.ja.mp4"))
        streams = summarize_streams(_ffprobe(final_output))
        _print_success(workdir, project_dir, final_output, validation, streams)
        return 0
    finally:
        if created_temp and not args.keep:
            shutil.rmtree(workdir, ignore_errors=True)
            print("Artifacts removed. Re-run with --keep to inspect generated files.")


def _prepare_workdir(requested: Optional[Path]) -> tuple[Path, bool]:
    if requested is None:
        path = Path(tempfile.mkdtemp(prefix="fukikae-beta-smoke."))
        return path, True
    path = requested.expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path, False


def _require_command(command: str) -> None:
    if shutil.which(command) is None:
        raise RuntimeError(f"Required command was not found on PATH: {command}")


def _run(command: Sequence[str]) -> None:
    subprocess.run(list(command), check=True)


def _ffprobe(path: Path) -> Mapping[str, Any]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(path)],
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    if not isinstance(payload, Mapping):
        raise RuntimeError("ffprobe returned a non-object JSON payload")
    return payload


def _print_success(
    workdir: Path,
    project_dir: Path,
    final_output: Path,
    validation: Mapping[str, Any],
    streams: Sequence[Mapping[str, object]],
) -> None:
    print(f"Workdir: {workdir}")
    print(f"Project directory: {project_dir}")
    print(f"Validation report: {project_dir / 'validation' / 'local_test_report.json'}")
    print(f"Validation status: {validation.get('status')}")
    print(f"Final output: {final_output}")
    print(f"Final output exists: {str(final_output.exists()).lower()}")
    print("Stream summary:")
    for stream in streams:
        print(
            "  - "
            f"index={stream.get('index')} "
            f"type={stream.get('type')} "
            f"codec={stream.get('codec')} "
            f"language={stream.get('language')}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
