import json
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence

from fukikae_studio.ai.grok_dubbing import build_grok_dubbing_payload, generate_dubbing_script_with_response
from fukikae_studio.ai.xai_stt import STT_ENDPOINT, build_stt_fields, normalize_stt_response, transcribe_audio_bytes
from fukikae_studio.ai.xai_tts import synthesize_tts_audio
from fukikae_studio.config import DEFAULT_XAI_TTS_VOICE
from fukikae_studio.media.audio_mix import build_narration_mix_command
from fukikae_studio.media.extract_audio import build_project_audio_extraction_command
from fukikae_studio.media.ffmpeg import require_media_tool
from fukikae_studio.media.final_mux import (
    build_burned_subtitle_mux_command,
    build_burned_subtitle_only_mux_command,
    build_project_final_mux_command,
    build_project_subtitle_only_final_mux_command,
)
from fukikae_studio.media.subtitle_style import SubtitleStyleInput
from fukikae_studio.media.subtitle_overlay import render_subtitle_overlay_images
from fukikae_studio.pipeline.adapt_script import write_dubbing_artifacts
from fukikae_studio.pipeline.assemble import assemble_project, assemble_subtitle_only_project
from fukikae_studio.pipeline.language_artifacts import (
    burned_output_artifact,
    dubbing_segments_path,
    normalize_target_language,
    subtitle_only_burned_output_artifact,
)
from fukikae_studio.pipeline.local_run import init_project, validate_project
from fukikae_studio.pipeline.processing_mode import DEFAULT_PROCESSING_MODE, is_subtitle_only_mode, normalize_processing_mode
from fukikae_studio.pipeline.stt import write_stt_artifacts
from fukikae_studio.pipeline.subtitle_output import (
    DEFAULT_SUBTITLE_OUTPUT,
    final_output_for_subtitle_output,
    normalize_subtitle_output,
)
from fukikae_studio.pipeline.synthesize_voice import synthesize_voice_segments

MediaRunner = Callable[[Sequence[str]], None]
DurationProbe = Callable[[Path, Mapping[str, object]], int]
VideoSizeProbe = Callable[[Path], tuple[int, int]]


class LiveXAIClient(Protocol):
    def post_multipart(self, path: str, fields: Mapping[str, object], files: Mapping[str, tuple]) -> object:
        ...

    def post_json(self, path: str, payload: Mapping[str, object]) -> object:
        ...

    def post_json_bytes(self, path: str, payload: Mapping[str, object]) -> bytes:
        ...


def run_live_pipeline(
    project_dir: Path,
    source_video: Path,
    client: LiveXAIClient,
    text_model: str,
    source_lang: str = "auto",
    target_lang: str = "ja",
    voice: str = DEFAULT_XAI_TTS_VOICE,
    overwrite: bool = False,
    execute_ffmpeg: bool = False,
    media_runner: Optional[MediaRunner] = None,
    duration_probe_ms: Optional[DurationProbe] = None,
    subtitle_output: str = DEFAULT_SUBTITLE_OUTPUT,
    processing_mode: str = DEFAULT_PROCESSING_MODE,
    subtitle_style: SubtitleStyleInput = None,
) -> dict:
    project = Path(project_dir)
    target_language = normalize_target_language(target_lang)
    output_processing_mode = normalize_processing_mode(processing_mode)
    init_manifest = init_project(
        project,
        source_video=source_video,
        source_lang=source_lang,
        target_lang=target_language,
        overwrite=overwrite,
    )

    audio_path = project / "media" / "source_audio_for_stt.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    _run_media_command(
        build_project_audio_extraction_command(project, output_wav=audio_path, overwrite=overwrite),
        media_runner=media_runner,
    )

    raw_stt_response = transcribe_audio_bytes(
        client,
        filename=audio_path.name,
        audio_bytes=audio_path.read_bytes(),
        source_lang=source_lang,
    )
    if not isinstance(raw_stt_response, Mapping):
        raise RuntimeError("xAI STT response must be an object")
    normalized_segments = normalize_stt_response(
        raw_stt_response,
        source_lang=source_lang,
        target_lang=target_language,
    )
    write_stt_artifacts(
        project,
        request_metadata={"endpoint": STT_ENDPOINT, "fields": build_stt_fields(source_lang)},
        raw_response=raw_stt_response,
        normalized_segments=normalized_segments,
    )

    dubbing_segments, raw_dubbing_response = generate_dubbing_script_with_response(
        client,
        normalized_segments,
        model=text_model,
        target_lang=target_language,
        quality_review=target_language == "en",
    )
    write_dubbing_artifacts(
        project,
        request_payload=build_grok_dubbing_payload(normalized_segments, model=text_model, target_lang=target_language),
        raw_response=raw_dubbing_response,
        dubbing_segments=dubbing_segments,
        target_lang=target_language,
    )

    tts_manifest = None
    if is_subtitle_only_mode(output_processing_mode):
        assembly_manifest = assemble_subtitle_only_project(
            project,
            target_lang=target_language,
            overwrite=overwrite,
            subtitle_style=subtitle_style,
        )
    else:
        duration_probe = duration_probe_ms or probe_audio_duration_ms
        tts_manifest = synthesize_voice_segments(
            project,
            dubbing_segments=dubbing_segments,
            synthesize_audio=lambda segment: synthesize_tts_audio(
                client,
                text=str(segment["target_text"]),
                voice=voice,
                language=target_language,
            ),
            duration_probe_ms=duration_probe,
            voice=voice,
            language=target_language,
            output_extension="mp3",
        )
        assembly_manifest = assemble_project(project, overwrite=overwrite, subtitle_style=subtitle_style)
    output_mode = normalize_subtitle_output(subtitle_output)
    if execute_ffmpeg:
        _execute_media_render(
            project,
            overwrite=overwrite,
            media_runner=media_runner,
            subtitle_output=output_mode,
            target_lang=target_language,
            processing_mode=output_processing_mode,
            subtitle_style=subtitle_style,
        )
    validation = validate_project(
        project,
        overwrite=overwrite,
        final_output_artifact=final_output_for_subtitle_output(
            output_mode,
            target_lang=target_language,
            processing_mode=output_processing_mode,
        ),
        target_lang=target_language,
        processing_mode=output_processing_mode,
    )
    return {
        "project": str(project),
        "init": init_manifest,
        "tts": tts_manifest,
        "assembly": assembly_manifest,
        "validation": validation,
    }


def probe_audio_duration_ms(path: Path, segment: Mapping[str, object]) -> int:
    return probe_media_duration_ms(path)


def probe_media_duration_ms(path: Path) -> int:
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


def probe_video_size(path: Path) -> tuple[int, int]:
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


def _execute_media_render(
    project: Path,
    overwrite: bool,
    media_runner: Optional[MediaRunner],
    video_size_probe: Optional[VideoSizeProbe] = None,
    subtitle_output: str = DEFAULT_SUBTITLE_OUTPUT,
    target_lang: object = "ja",
    processing_mode: object = DEFAULT_PROCESSING_MODE,
    subtitle_style: SubtitleStyleInput = None,
) -> None:
    target_language = normalize_target_language(target_lang)
    output_processing_mode = normalize_processing_mode(processing_mode)
    (project / "assembly").mkdir(parents=True, exist_ok=True)
    (project / "output").mkdir(parents=True, exist_ok=True)
    output_mode = normalize_subtitle_output(subtitle_output)
    if is_subtitle_only_mode(output_processing_mode):
        _execute_subtitle_only_media_render(
            project,
            overwrite=overwrite,
            media_runner=media_runner,
            video_size_probe=video_size_probe,
            subtitle_output=output_mode,
            target_lang=target_language,
            subtitle_style=subtitle_style,
        )
        return
    timeline = _load_json(project / "assembly" / "narration_timeline.json")
    _run_media_command(
        build_narration_mix_command(project, timeline, overwrite=overwrite),
        media_runner=media_runner,
    )
    if output_mode in {"both", "soft"}:
        _run_media_command(
            build_project_final_mux_command(project, target_lang=target_language, overwrite=overwrite),
            media_runner=media_runner,
        )
    if output_mode in {"both", "burned"}:
        video_size = (1280, 720) if media_runner is not None and video_size_probe is None else (
            video_size_probe or probe_video_size
        )(project / "input" / "source.mp4")
        subtitle_overlays = render_subtitle_overlay_images(
            _load_json(dubbing_segments_path(project, target_language)),
            output_dir=project / "assembly" / "subtitle_overlays",
            video_size=video_size,
            overwrite=overwrite,
            subtitle_style=subtitle_style,
        )
        video_duration_ms = None if media_runner is not None else probe_media_duration_ms(project / "input" / "source.mp4")
        _run_media_command(
            build_burned_subtitle_mux_command(
                source_video=project / "input" / "source.mp4",
                narration_audio=project / "assembly" / "narration_track.wav",
                subtitle_overlays=subtitle_overlays,
                output_mp4=project / burned_output_artifact(target_language),
                duration_ms=video_duration_ms,
                overwrite=overwrite,
            ),
            media_runner=media_runner,
        )


def _execute_subtitle_only_media_render(
    project: Path,
    overwrite: bool,
    media_runner: Optional[MediaRunner],
    video_size_probe: Optional[VideoSizeProbe] = None,
    subtitle_output: str = DEFAULT_SUBTITLE_OUTPUT,
    target_lang: object = "ja",
    subtitle_style: SubtitleStyleInput = None,
) -> None:
    target_language = normalize_target_language(target_lang)
    output_mode = normalize_subtitle_output(subtitle_output)
    if output_mode in {"both", "soft"}:
        _run_media_command(
            build_project_subtitle_only_final_mux_command(project, target_lang=target_language, overwrite=overwrite),
            media_runner=media_runner,
        )
    if output_mode in {"both", "burned"}:
        video_size = (1280, 720) if media_runner is not None and video_size_probe is None else (
            video_size_probe or probe_video_size
        )(project / "input" / "source.mp4")
        subtitle_overlays = render_subtitle_overlay_images(
            _load_json(dubbing_segments_path(project, target_language)),
            output_dir=project / "assembly" / "subtitle_overlays",
            video_size=video_size,
            overwrite=overwrite,
            subtitle_style=subtitle_style,
        )
        video_duration_ms = None if media_runner is not None else probe_media_duration_ms(project / "input" / "source.mp4")
        _run_media_command(
            build_burned_subtitle_only_mux_command(
                source_video=project / "input" / "source.mp4",
                subtitle_overlays=subtitle_overlays,
                output_mp4=project / subtitle_only_burned_output_artifact(target_language),
                duration_ms=video_duration_ms,
                overwrite=overwrite,
            ),
            media_runner=media_runner,
        )


def _run_media_command(command: Sequence[str], media_runner: Optional[MediaRunner]) -> None:
    if media_runner is not None:
        media_runner(command)
        return
    require_media_tool(command[0])
    subprocess.run(list(command), check=True)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
