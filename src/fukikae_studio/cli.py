import argparse
import json
import shlex
import sys
from pathlib import Path
from typing import Iterable, Optional

from fukikae_studio.ai.grok_dubbing import (
    build_grok_dubbing_payload,
    parse_grok_dubbing_response,
)
from fukikae_studio.ai.xai_stt import STT_ENDPOINT, build_stt_fields, normalize_stt_response
from fukikae_studio.ai.xai_client import XAIClient
from fukikae_studio.config import DEFAULT_XAI_TTS_VOICE, XAIConfig, load_env_file
from fukikae_studio.media.extract_audio import build_project_audio_extraction_command
from fukikae_studio.media.ffmpeg import require_media_tool
from fukikae_studio.media.metadata import build_project_ffprobe_metadata_command
from fukikae_studio.pipeline.assemble import assemble_project
from fukikae_studio.pipeline.adapt_script import write_dubbing_artifacts
from fukikae_studio.pipeline.live_run import run_live_pipeline
from fukikae_studio.pipeline.local_run import init_project, run_fixture_pipeline, validate_project
from fukikae_studio.pipeline.stt import write_stt_artifacts
from fukikae_studio.pipeline.subtitle_output import DEFAULT_SUBTITLE_OUTPUT, SUBTITLE_OUTPUT_CHOICES
from fukikae_studio.pipeline.synthesize_voice import synthesize_voice_segments
from fukikae_studio.web.studio import DEFAULT_HOST, DEFAULT_PORT, default_studio_form_values, run_studio_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fukikae",
        description=(
            "FukiKae Studio xAI-only local video dubbing CLI MVP. "
            "Implemented stages expose deterministic local command plans or fixture-backed artifacts."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    init_parser = subparsers.add_parser("init", help="create a local FukiKae project from a source video")
    init_parser.add_argument("--video", type=Path, required=True, help="local source video to copy into the project")
    init_parser.add_argument("--project", type=Path, required=True, help="local FukiKae project directory")
    init_parser.add_argument("--source-lang", default="auto", help="source language, default: auto")
    init_parser.add_argument("--target-lang", default="ja", help="target language, default: ja")
    init_parser.add_argument("--overwrite", action="store_true", help="allow init artifacts to be overwritten")
    init_parser.set_defaults(func=_init)

    inspect_parser = subparsers.add_parser("inspect", help="print the ffprobe metadata command for a project")
    inspect_parser.add_argument("project", type=Path, help="local FukiKae project directory")
    inspect_parser.set_defaults(func=_inspect)

    extract_parser = subparsers.add_parser(
        "extract-audio",
        help="print the ffmpeg STT-ready audio extraction command for a project",
    )
    extract_parser.add_argument("project", type=Path, help="local FukiKae project directory")
    extract_parser.add_argument("--overwrite", action="store_true", help="allow ffmpeg to overwrite the output WAV")
    extract_parser.set_defaults(func=_extract_audio)

    stt_parser = subparsers.add_parser("stt", help="normalize an xAI STT fixture response for a project")
    stt_parser.add_argument("project", type=Path, help="local FukiKae project directory")
    stt_parser.add_argument(
        "--fixture-response",
        type=Path,
        required=True,
        help="sanitized xAI STT JSON fixture; live calls are disabled in this phase",
    )
    stt_parser.add_argument("--source-lang", default="auto", help="source language, default: auto")
    stt_parser.add_argument("--target-lang", default="ja", help="target language, default: ja")
    stt_parser.set_defaults(func=_stt)

    script_parser = subparsers.add_parser("make-script", help="parse a Grok dubbing fixture response for a project")
    script_parser.add_argument("project", type=Path, help="local FukiKae project directory")
    script_parser.add_argument(
        "--fixture-response",
        type=Path,
        required=True,
        help="sanitized Grok dubbing JSON fixture; live calls are disabled in this phase",
    )
    script_parser.add_argument("--model", default="grok-4.3", help="Grok model name for request artifact metadata")
    script_parser.set_defaults(func=_make_script)

    tts_parser = subparsers.add_parser("tts", help="write TTS fixture audio files and manifest for a project")
    tts_parser.add_argument("project", type=Path, help="local FukiKae project directory")
    tts_parser.add_argument(
        "--fixture-audio",
        type=Path,
        required=True,
        help="local fixture audio bytes reused per segment; live calls are disabled in this phase",
    )
    tts_parser.add_argument(
        "--voice",
        default=DEFAULT_XAI_TTS_VOICE,
        help="xAI TTS voice id for manifest metadata",
    )
    tts_parser.add_argument("--language", default="ja", help="TTS language code, default: ja")
    tts_parser.set_defaults(func=_tts)

    assemble_parser = subparsers.add_parser(
        "assemble",
        help="write assembly artifacts and the final ffmpeg MP4 mux command plan",
    )
    assemble_parser.add_argument("project", type=Path, help="local FukiKae project directory")
    assemble_parser.add_argument("--overwrite", action="store_true", help="allow assembly artifacts to be overwritten")
    assemble_parser.set_defaults(func=_assemble)

    validate_parser = subparsers.add_parser("validate", help="validate local artifacts for fixture-backed testing")
    validate_parser.add_argument("project", type=Path, help="local FukiKae project directory")
    validate_parser.add_argument("--overwrite", action="store_true", help="allow validation report to be overwritten")
    validate_parser.set_defaults(func=_validate)

    run_parser = subparsers.add_parser("run", help="run the fixture-backed local pipeline for a project")
    run_parser.add_argument("--video", type=Path, required=True, help="local source video")
    run_parser.add_argument("--project", type=Path, required=True, help="local FukiKae project directory")
    run_parser.add_argument(
        "--fixture-stt-response",
        type=Path,
        required=True,
        help="sanitized xAI STT JSON fixture; live calls are disabled in this mode",
    )
    run_parser.add_argument(
        "--fixture-dubbing-response",
        type=Path,
        required=True,
        help="sanitized Grok dubbing JSON fixture; live calls are disabled in this mode",
    )
    run_parser.add_argument(
        "--fixture-audio",
        type=Path,
        required=True,
        help="local fixture audio bytes reused per TTS segment; live calls are disabled in this mode",
    )
    run_parser.add_argument("--source-lang", default="auto", help="source language, default: auto")
    run_parser.add_argument("--target-lang", default="ja", help="target language, default: ja")
    run_parser.add_argument(
        "--voice",
        default=DEFAULT_XAI_TTS_VOICE,
        help="xAI TTS voice id for manifest metadata",
    )
    run_parser.add_argument(
        "--execute-ffmpeg",
        action="store_true",
        help="execute local ffmpeg rendering after fixture artifacts are written",
    )
    run_parser.add_argument(
        "--subtitle-output",
        choices=SUBTITLE_OUTPUT_CHOICES,
        default=DEFAULT_SUBTITLE_OUTPUT,
        help="subtitle output to render when executing ffmpeg, default: both",
    )
    run_parser.add_argument("--overwrite", action="store_true", help="allow local run artifacts to be overwritten")
    run_parser.set_defaults(func=_run)

    live_parser = subparsers.add_parser(
        "run-live",
        help="run the live xAI dubbing pipeline for a local video",
    )
    live_parser.add_argument("--video", type=Path, required=True, help="local source video")
    live_parser.add_argument("--project", type=Path, required=True, help="local FukiKae project directory")
    live_parser.add_argument(
        "--env-file",
        type=Path,
        help="local env file with xAI credentials; values are loaded without shell source or logging",
    )
    live_parser.add_argument("--source-lang", default="auto", help="source language, default: auto")
    live_parser.add_argument("--target-lang", default="ja", help="target language, default: ja")
    live_parser.add_argument("--voice", help="xAI TTS voice id; defaults to XAI_TTS_VOICE or Sakura")
    live_parser.add_argument("--model", help="Grok model; defaults to XAI_TEXT_MODEL or grok-4.3")
    live_parser.add_argument(
        "--execute-ffmpeg",
        action="store_true",
        help="execute local ffmpeg rendering after live xAI artifacts are written",
    )
    live_parser.add_argument(
        "--subtitle-output",
        choices=SUBTITLE_OUTPUT_CHOICES,
        default=DEFAULT_SUBTITLE_OUTPUT,
        help="subtitle output to render when executing ffmpeg, default: both",
    )
    live_parser.add_argument("--overwrite", action="store_true", help="allow live run artifacts to be overwritten")
    live_parser.set_defaults(func=_run_live)

    studio_parser = subparsers.add_parser("studio", help="start the localhost Web UI alpha")
    studio_parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"bind host for the local-only web server, default: {DEFAULT_HOST}",
    )
    studio_parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"bind port for the localhost Web UI alpha, default: {DEFAULT_PORT}",
    )
    studio_parser.add_argument("--video", type=Path, help="default local source video path shown in the form")
    studio_parser.add_argument("--project", type=Path, help="default local project directory shown in the form")
    studio_parser.add_argument(
        "--fixture-stt-response",
        type=Path,
        help="default sanitized STT fixture path shown in the fixture-backed form",
    )
    studio_parser.add_argument(
        "--fixture-dubbing-response",
        type=Path,
        help="default sanitized dubbing fixture path shown in the fixture-backed form",
    )
    studio_parser.add_argument("--fixture-audio", type=Path, help="default fixture TTS audio path shown in the form")
    studio_parser.add_argument("--open-browser", action="store_true", help="open the local Web UI in the default browser")
    studio_parser.set_defaults(func=_studio)

    return parser


def _print_command(command: Iterable[str]) -> None:
    print(shlex.join(list(command)))


def _init(args: argparse.Namespace) -> int:
    init_project(
        args.project,
        source_video=args.video,
        source_lang=args.source_lang,
        target_lang=args.target_lang,
        overwrite=args.overwrite,
    )
    print(args.project / "project.json")
    return 0


def _inspect(args: argparse.Namespace) -> int:
    require_media_tool("ffprobe")
    _print_command(build_project_ffprobe_metadata_command(args.project))
    return 0


def _extract_audio(args: argparse.Namespace) -> int:
    require_media_tool("ffmpeg")
    _print_command(build_project_audio_extraction_command(args.project, overwrite=args.overwrite))
    return 0


def _stt(args: argparse.Namespace) -> int:
    raw_response = json.loads(args.fixture_response.read_text(encoding="utf-8"))
    segments = normalize_stt_response(raw_response, source_lang=args.source_lang, target_lang=args.target_lang)
    write_stt_artifacts(
        args.project,
        request_metadata={"endpoint": STT_ENDPOINT, "fields": build_stt_fields(args.source_lang)},
        raw_response=raw_response,
        normalized_segments=segments,
    )
    print(args.project / "stt" / "normalized_segments.json")
    return 0


def _make_script(args: argparse.Namespace) -> int:
    source_segments_path = args.project / "stt" / "normalized_segments.json"
    source_segments = json.loads(source_segments_path.read_text(encoding="utf-8"))
    raw_response = json.loads(args.fixture_response.read_text(encoding="utf-8"))
    dubbing_segments = parse_grok_dubbing_response(
        raw_response,
        expected_segment_ids=[str(segment["id"]) for segment in source_segments],
    )
    write_dubbing_artifacts(
        args.project,
        request_payload=build_grok_dubbing_payload(source_segments, model=args.model),
        raw_response=raw_response,
        dubbing_segments=dubbing_segments,
    )
    print(args.project / "script" / "japanese_dubbing_segments.json")
    return 0


def _tts(args: argparse.Namespace) -> int:
    dubbing_segments_path = args.project / "script" / "japanese_dubbing_segments.json"
    dubbing_segments = json.loads(dubbing_segments_path.read_text(encoding="utf-8"))
    fixture_audio = args.fixture_audio.read_bytes()
    synthesize_voice_segments(
        args.project,
        dubbing_segments=dubbing_segments,
        synthesize_audio=lambda segment: fixture_audio,
        duration_probe_ms=lambda path, segment: 0,
        voice=args.voice,
        language=args.language,
    )
    print(args.project / "tts" / "xai_tts_manifest.json")
    return 0


def _assemble(args: argparse.Namespace) -> int:
    assemble_project(args.project, overwrite=args.overwrite)
    print(args.project / "assembly" / "assembly_manifest.json")
    return 0


def _validate(args: argparse.Namespace) -> int:
    report = validate_project(args.project, overwrite=args.overwrite)
    print(args.project / "validation" / "local_test_report.json")
    return 0 if report["status"] != "failed" else 1


def _run(args: argparse.Namespace) -> int:
    run_fixture_pipeline(
        args.project,
        source_video=args.video,
        stt_fixture_response=args.fixture_stt_response,
        dubbing_fixture_response=args.fixture_dubbing_response,
        fixture_audio=args.fixture_audio,
        source_lang=args.source_lang,
        target_lang=args.target_lang,
        voice=args.voice,
        overwrite=args.overwrite,
        execute_ffmpeg=args.execute_ffmpeg,
        subtitle_output=args.subtitle_output,
    )
    print(args.project / "validation" / "local_test_report.json")
    return 0


def _run_live(args: argparse.Namespace) -> int:
    config_env = None
    if args.env_file is not None:
        config_env = load_env_file(args.env_file)
    config = XAIConfig.from_env(config_env)
    client = XAIClient(config)
    run_live_pipeline(
        args.project,
        source_video=args.video,
        client=client,
        text_model=args.model or config.text_model,
        source_lang=args.source_lang if args.source_lang != "auto" else config.stt_language,
        target_lang=args.target_lang,
        voice=args.voice or config.tts_voice,
        overwrite=args.overwrite,
        execute_ffmpeg=args.execute_ffmpeg,
        subtitle_output=args.subtitle_output,
    )
    print(args.project / "validation" / "local_test_report.json")
    return 0


def _studio(args: argparse.Namespace) -> int:
    defaults = default_studio_form_values()
    if args.video is not None:
        defaults["video"] = str(args.video)
    if args.project is not None:
        defaults["project"] = str(args.project)
    if args.fixture_stt_response is not None:
        defaults["stt_fixture_response"] = str(args.fixture_stt_response)
    if args.fixture_dubbing_response is not None:
        defaults["dubbing_fixture_response"] = str(args.fixture_dubbing_response)
    if args.fixture_audio is not None:
        defaults["fixture_audio"] = str(args.fixture_audio)
    try:
        run_studio_server(
            host=args.host,
            port=args.port,
            defaults=defaults,
            open_browser=args.open_browser,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args)
