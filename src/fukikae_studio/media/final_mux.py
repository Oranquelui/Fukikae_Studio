from pathlib import Path
from typing import Iterable, List, Mapping, Optional, Tuple

from fukikae_studio.media.ffmpeg import assert_inside_project
from fukikae_studio.pipeline.language_artifacts import (
    soft_output_artifact,
    subtitle_artifacts,
    subtitle_metadata_language,
)


def build_final_mux_command(
    source_video: Path,
    narration_audio: Path,
    subtitles_srt: Path,
    output_mp4: Path,
    subtitle_language: str = "jpn",
    overwrite: bool = False,
) -> List[str]:
    overwrite_flag = "-y" if overwrite else "-n"
    return [
        "ffmpeg",
        "-nostdin",
        overwrite_flag,
        "-i",
        str(source_video),
        "-i",
        str(narration_audio),
        "-i",
        str(subtitles_srt),
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
        f"language={subtitle_language}",
        "-disposition:s:0",
        "default",
        str(output_mp4),
    ]


def build_burned_subtitle_mux_command(
    source_video: Path,
    narration_audio: Path,
    subtitle_overlays: Iterable[Mapping[str, object]],
    output_mp4: Path,
    duration_ms: Optional[int] = None,
    overwrite: bool = False,
) -> List[str]:
    overwrite_flag = "-y" if overwrite else "-n"
    overlays = [dict(overlay) for overlay in subtitle_overlays]
    command = [
        "ffmpeg",
        "-nostdin",
        overwrite_flag,
        "-i",
        str(source_video),
        "-i",
        str(narration_audio),
    ]
    for overlay in overlays:
        command.extend(["-loop", "1", "-i", str(overlay["image"])])
    if overlays:
        filter_complex, video_map = _build_subtitle_overlay_filter(overlays)
        command.extend(["-filter_complex", filter_complex, "-map", video_map, "-map", "1:a:0"])
    else:
        command.extend(
            [
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
            ]
        )
    if duration_ms is not None:
        command.extend(["-t", _format_seconds(_required_int(duration_ms))])
    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output_mp4),
        ]
    )
    return command


def _build_subtitle_overlay_filter(overlays: List[Mapping[str, object]]) -> Tuple[str, str]:
    chains = []
    current_label = "0:v"
    for index, overlay in enumerate(overlays):
        input_index = index + 2
        output_label = f"v{index + 1}"
        start = _format_seconds(_required_int(overlay["start_ms"]))
        end = _format_seconds(_required_int(overlay["end_ms"]))
        chains.append(
            f"[{current_label}][{input_index}:v]"
            f"overlay=x=0:y=0:enable='between(t,{start},{end})':shortest=1:eof_action=pass:repeatlast=0"
            f"[{output_label}]"
        )
        current_label = output_label
    return ";".join(chains), f"[{current_label}]"


def _format_seconds(milliseconds: int) -> str:
    return f"{milliseconds / 1000:.3f}"


def _required_int(value: object) -> int:
    return int(value)


def build_project_final_mux_command(
    project_dir: Path,
    source_video: Optional[Path] = None,
    narration_audio: Optional[Path] = None,
    subtitles_srt: Optional[Path] = None,
    output_mp4: Optional[Path] = None,
    target_lang: object = "ja",
    overwrite: bool = False,
) -> List[str]:
    project = Path(project_dir)
    source = source_video or project / "input" / "source.mp4"
    audio = narration_audio or project / "assembly" / "narration_track.wav"
    subtitles = subtitles_srt or project / subtitle_artifacts(target_lang)["srt"]
    output = output_mp4 or project / soft_output_artifact(target_lang)
    assert_inside_project(project, source)
    assert_inside_project(project, audio)
    assert_inside_project(project, subtitles)
    assert_inside_project(project, output)
    return build_final_mux_command(
        source_video=source,
        narration_audio=audio,
        subtitles_srt=subtitles,
        output_mp4=output,
        subtitle_language=subtitle_metadata_language(target_lang),
        overwrite=overwrite,
    )
