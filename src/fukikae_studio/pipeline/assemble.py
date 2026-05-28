import json
from pathlib import Path
from typing import Iterable, Mapping, Optional

from fukikae_studio.media.final_mux import build_project_final_mux_command
from fukikae_studio.media.subtitles import build_ass, build_srt, build_webvtt
from fukikae_studio.media.timing import build_audio_mix_plan, build_narration_timeline


def write_timeline_artifacts(project_dir: Path, timeline: Mapping[str, object], overwrite: bool = False) -> None:
    assembly_dir = Path(project_dir) / "assembly"
    assembly_dir.mkdir(parents=True, exist_ok=True)
    timeline_path = assembly_dir / "narration_timeline.json"
    mix_plan_path = assembly_dir / "mix_plan.json"
    _write_json_guarded(timeline_path, timeline, overwrite=overwrite)
    _write_json_guarded(mix_plan_path, build_audio_mix_plan(timeline), overwrite=overwrite)


def write_subtitle_artifacts(
    project_dir: Path,
    segments: Iterable[Mapping[str, object]],
    overwrite: bool = False,
    language: str = "ja",
) -> None:
    assembly_dir = Path(project_dir) / "assembly"
    assembly_dir.mkdir(parents=True, exist_ok=True)
    srt_path = assembly_dir / "japanese_subtitles.srt"
    webvtt_path = assembly_dir / "japanese_subtitles.vtt"
    ass_path = assembly_dir / "japanese_subtitles.ass"
    manifest_path = assembly_dir / "subtitle_manifest.json"
    _ensure_can_write([srt_path, webvtt_path, ass_path, manifest_path], overwrite=overwrite)
    segment_list = [dict(segment) for segment in segments]
    srt_text = build_srt(segment_list)
    webvtt_text = build_webvtt(segment_list)
    ass_text = build_ass(segment_list)
    manifest = {
        "schema_version": "0.1",
        "language": language,
        "formats": {
            "srt": "assembly/japanese_subtitles.srt",
            "webvtt": "assembly/japanese_subtitles.vtt",
            "ass": "assembly/japanese_subtitles.ass",
        },
    }
    _write_text(srt_path, srt_text)
    _write_text(webvtt_path, webvtt_text)
    _write_text(ass_path, ass_text)
    _write_json(manifest_path, manifest)


def write_final_mux_plan(
    project_dir: Path,
    source_video: Optional[Path] = None,
    narration_audio: Optional[Path] = None,
    subtitles_srt: Optional[Path] = None,
    output_mp4: Optional[Path] = None,
    overwrite: bool = False,
) -> dict:
    project = Path(project_dir)
    assembly_dir = project / "assembly"
    assembly_dir.mkdir(parents=True, exist_ok=True)
    plan_path = assembly_dir / "final_mux_plan.json"
    command = build_project_final_mux_command(
        project,
        source_video=source_video,
        narration_audio=narration_audio,
        subtitles_srt=subtitles_srt,
        output_mp4=output_mp4,
        overwrite=overwrite,
    )
    output = output_mp4 or project / "output" / "dubbed.ja.mp4"
    plan = {
        "schema_version": "0.1",
        "strategy": "copy_video_replace_audio_soft_subtitles",
        "inputs": {
            "video": str(source_video or project / "input" / "source.mp4"),
            "narration_audio": str(narration_audio or project / "assembly" / "narration_track.wav"),
            "subtitles_srt": str(subtitles_srt or project / "assembly" / "japanese_subtitles.srt"),
        },
        "output": str(output),
        "command": command,
    }
    _write_json_guarded(plan_path, plan, overwrite=overwrite)
    return plan


def assemble_project(project_dir: Path, overwrite: bool = False) -> dict:
    project = Path(project_dir)
    tts_manifest_path = project / "tts" / "xai_tts_manifest.json"
    dubbing_segments_path = project / "script" / "japanese_dubbing_segments.json"
    tts_manifest = json.loads(tts_manifest_path.read_text(encoding="utf-8"))
    dubbing_segments = json.loads(dubbing_segments_path.read_text(encoding="utf-8"))

    timeline = build_narration_timeline(tts_manifest)
    write_timeline_artifacts(project, timeline, overwrite=overwrite)
    write_subtitle_artifacts(
        project,
        dubbing_segments,
        overwrite=overwrite,
        language=str(tts_manifest.get("language", "ja")),
    )
    final_plan = write_final_mux_plan(project, overwrite=overwrite)

    manifest = {
        "schema_version": "0.1",
        "artifacts": {
            "narration_timeline": "assembly/narration_timeline.json",
            "mix_plan": "assembly/mix_plan.json",
            "subtitles_srt": "assembly/japanese_subtitles.srt",
            "subtitles_webvtt": "assembly/japanese_subtitles.vtt",
            "subtitles_ass": "assembly/japanese_subtitles.ass",
            "subtitle_manifest": "assembly/subtitle_manifest.json",
            "final_mux_plan": "assembly/final_mux_plan.json",
        },
        "final_output": final_plan["output"],
    }
    _write_json_guarded(project / "assembly" / "assembly_manifest.json", manifest, overwrite=overwrite)
    return manifest


def _write_json_guarded(path: Path, payload: object, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing artifact: {path}")
    _write_json(path, payload)


def _ensure_can_write(paths: Iterable[Path], overwrite: bool) -> None:
    if overwrite:
        return
    for path in paths:
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite existing artifact: {path}")


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
