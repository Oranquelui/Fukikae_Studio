import json
import shutil
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence
import subprocess

from fukikae_studio.ai.grok_dubbing import build_grok_dubbing_payload, parse_grok_dubbing_response
from fukikae_studio.ai.xai_stt import STT_ENDPOINT, build_stt_fields, normalize_stt_response
from fukikae_studio.media.audio_mix import build_narration_mix_command
from fukikae_studio.media.ffmpeg import require_media_tool
from fukikae_studio.media.final_mux import build_burned_subtitle_mux_command, build_project_final_mux_command
from fukikae_studio.media.subtitle_overlay import render_subtitle_overlay_images
from fukikae_studio.pipeline.adapt_script import write_dubbing_artifacts
from fukikae_studio.pipeline.assemble import assemble_project
from fukikae_studio.pipeline.stt import write_stt_artifacts
from fukikae_studio.pipeline.subtitle_output import (
    DEFAULT_SUBTITLE_OUTPUT,
    final_output_for_subtitle_output,
    normalize_subtitle_output,
)
from fukikae_studio.pipeline.synthesize_voice import synthesize_voice_segments
from fukikae_studio.config import DEFAULT_XAI_TTS_VOICE

REQUIRED_LOCAL_TEST_ARTIFACTS = (
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
)

FINAL_OUTPUT_ARTIFACT = "output/dubbed.ja.mp4"
MediaRunner = Callable[[Sequence[str]], None]


def init_project(
    project_dir: Path,
    source_video: Path,
    source_lang: str = "auto",
    target_lang: str = "ja",
    overwrite: bool = False,
) -> dict:
    project = Path(project_dir)
    source = Path(source_video)
    if not source.exists():
        raise FileNotFoundError(f"Source video was not found: {source}")

    input_dir = project / "input"
    destination = input_dir / "source.mp4"
    manifest_path = project / "project.json"
    _ensure_can_write([destination, manifest_path], overwrite=overwrite)

    input_dir.mkdir(parents=True, exist_ok=True)
    if source.resolve(strict=False) != destination.resolve(strict=False):
        shutil.copyfile(source, destination)

    manifest = {
        "schema_version": "0.1",
        "source_lang": source_lang,
        "target_lang": target_lang,
        "input": {
            "source_video": "input/source.mp4",
            "original_filename": source.name,
        },
    }
    _write_json(manifest_path, manifest)
    return manifest


def validate_project(project_dir: Path, overwrite: bool = False, final_output_artifact: str = FINAL_OUTPUT_ARTIFACT) -> dict:
    project = Path(project_dir)
    missing = [relative for relative in REQUIRED_LOCAL_TEST_ARTIFACTS if not (project / relative).exists()]
    final_output_exists = (project / final_output_artifact).exists()
    status = "failed" if missing else "complete" if final_output_exists else "ready_for_final_mux"
    report = {
        "schema_version": "0.1",
        "status": status,
        "required_artifacts": list(REQUIRED_LOCAL_TEST_ARTIFACTS),
        "missing_required_artifacts": missing,
        "final_output": final_output_artifact,
        "final_output_exists": final_output_exists,
    }
    validation_dir = project / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    _write_json_guarded(validation_dir / "local_test_report.json", report, overwrite=overwrite)
    return report


def run_fixture_pipeline(
    project_dir: Path,
    source_video: Path,
    stt_fixture_response: Path,
    dubbing_fixture_response: Path,
    fixture_audio: Path,
    source_lang: str = "auto",
    target_lang: str = "ja",
    voice: str = DEFAULT_XAI_TTS_VOICE,
    overwrite: bool = False,
    execute_ffmpeg: bool = False,
    media_runner: Optional[MediaRunner] = None,
    subtitle_output: str = DEFAULT_SUBTITLE_OUTPUT,
) -> dict:
    project = Path(project_dir)
    init_manifest = init_project(
        project,
        source_video=source_video,
        source_lang=source_lang,
        target_lang=target_lang,
        overwrite=overwrite,
    )

    raw_stt_response = _load_json(Path(stt_fixture_response))
    normalized_segments = normalize_stt_response(
        raw_stt_response,
        source_lang=source_lang,
        target_lang=target_lang,
    )
    write_stt_artifacts(
        project,
        request_metadata={"endpoint": STT_ENDPOINT, "fields": build_stt_fields(source_lang)},
        raw_response=raw_stt_response,
        normalized_segments=normalized_segments,
    )

    raw_dubbing_response = _load_json(Path(dubbing_fixture_response))
    dubbing_segments = parse_grok_dubbing_response(
        raw_dubbing_response,
        expected_segment_ids=[str(segment["id"]) for segment in normalized_segments],
    )
    write_dubbing_artifacts(
        project,
        request_payload=build_grok_dubbing_payload(normalized_segments),
        raw_response=raw_dubbing_response,
        dubbing_segments=dubbing_segments,
    )

    fixture_audio_bytes = Path(fixture_audio).read_bytes()
    tts_manifest = synthesize_voice_segments(
        project,
        dubbing_segments=dubbing_segments,
        synthesize_audio=lambda segment: fixture_audio_bytes,
        duration_probe_ms=lambda path, segment: _duration_ms_from_segment(segment),
        voice=voice,
        language=target_lang,
    )
    assembly_manifest = assemble_project(project, overwrite=overwrite)
    output_mode = normalize_subtitle_output(subtitle_output)
    if execute_ffmpeg:
        _execute_media_render(project, overwrite=overwrite, media_runner=media_runner, subtitle_output=output_mode)
    validation = validate_project(
        project,
        overwrite=overwrite,
        final_output_artifact=final_output_for_subtitle_output(output_mode),
    )
    return {
        "project": str(project),
        "init": init_manifest,
        "tts": tts_manifest,
        "assembly": assembly_manifest,
        "validation": validation,
    }


def _execute_media_render(
    project: Path,
    overwrite: bool,
    media_runner: Optional[MediaRunner],
    subtitle_output: str = DEFAULT_SUBTITLE_OUTPUT,
) -> None:
    if media_runner is None:
        require_media_tool("ffmpeg")
    timeline = _load_json(project / "assembly" / "narration_timeline.json")
    (project / "assembly").mkdir(parents=True, exist_ok=True)
    (project / "output").mkdir(parents=True, exist_ok=True)
    output_mode = normalize_subtitle_output(subtitle_output)
    _run_media_command(
        build_narration_mix_command(project, timeline, overwrite=overwrite),
        media_runner=media_runner,
    )
    if output_mode in {"both", "soft"}:
        _run_media_command(
            build_project_final_mux_command(project, overwrite=overwrite),
            media_runner=media_runner,
        )
    if output_mode in {"both", "burned"}:
        video_size = (1280, 720) if media_runner is not None else _probe_video_size(project / "input" / "source.mp4")
        subtitle_overlays = render_subtitle_overlay_images(
            _load_json(project / "script" / "japanese_dubbing_segments.json"),
            output_dir=project / "assembly" / "subtitle_overlays",
            video_size=video_size,
            overwrite=overwrite,
        )
        video_duration_ms = None if media_runner is not None else _probe_media_duration_ms(project / "input" / "source.mp4")
        _run_media_command(
            build_burned_subtitle_mux_command(
                source_video=project / "input" / "source.mp4",
                narration_audio=project / "assembly" / "narration_track.wav",
                subtitle_overlays=subtitle_overlays,
                output_mp4=project / "output" / "dubbed.ja.burned.mp4",
                duration_ms=video_duration_ms,
                overwrite=overwrite,
            ),
            media_runner=media_runner,
        )


def _run_media_command(command: Sequence[str], media_runner: Optional[MediaRunner]) -> None:
    if media_runner is not None:
        media_runner(command)
        return
    subprocess.run(list(command), check=True)


def _probe_media_duration_ms(path: Path) -> int:
    require_media_tool("ffprobe")
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    return int(round(float(result.stdout.strip()) * 1000))


def _probe_video_size(path: Path) -> tuple[int, int]:
    require_media_tool("ffprobe")
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(path),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    streams = payload.get("streams") or []
    if not streams:
        raise RuntimeError(f"No video stream found: {path}")
    return int(streams[0]["width"]), int(streams[0]["height"])


def _duration_ms_from_segment(segment: Mapping[str, object]) -> int:
    if segment.get("estimated_duration_ms") is not None:
        return _required_int(segment["estimated_duration_ms"])
    return _required_int(segment["source_end_ms"]) - _required_int(segment["source_start_ms"])


def _required_int(value: Any) -> int:
    return int(value)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _ensure_can_write(paths: Iterable[Path], overwrite: bool) -> None:
    if overwrite:
        return
    for path in paths:
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite existing artifact: {path}")


def _write_json_guarded(path: Path, payload: object, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing artifact: {path}")
    _write_json(path, payload)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
