from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional

from fukikae_studio.media.ffmpeg import assert_inside_project


def build_narration_mix_command(
    project_dir: Path,
    timeline: Mapping[str, object],
    output_wav: Optional[Path] = None,
    overwrite: bool = False,
) -> List[str]:
    project = Path(project_dir)
    clips = _timeline_clips(timeline)
    if not clips:
        raise ValueError("Narration timeline must contain at least one clip")

    output = output_wav or project / "assembly" / "narration_track.wav"
    assert_inside_project(project, output)

    command = ["ffmpeg", "-nostdin", "-y" if overwrite else "-n"]
    delay_filters = []
    labels = []
    for index, clip in enumerate(clips):
        audio_path = project / str(clip["audio"])
        assert_inside_project(project, audio_path)
        command.extend(["-i", str(audio_path)])
        delay_ms = _required_int(clip["start_ms"])
        label = f"a{index}"
        filters = []
        atempo = float(clip.get("atempo", 1.0))
        if atempo > 1.0:
            filters.extend(_atempo_filter_chain(atempo))
        filters.append(f"adelay={delay_ms}|{delay_ms}")
        delay_filters.append(f"[{index}:a]{','.join(filters)}[{label}]")
        labels.append(f"[{label}]")

    mix_filter = f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest[mix]"
    command.extend(
        [
            "-filter_complex",
            ";".join(delay_filters + [mix_filter]),
            "-map",
            "[mix]",
            "-c:a",
            "pcm_s16le",
            str(output),
        ]
    )
    return command


def _timeline_clips(timeline: Mapping[str, object]) -> Iterable[Mapping[str, object]]:
    clips = timeline.get("clips", [])
    if not isinstance(clips, list):
        return []
    return [clip for clip in clips if isinstance(clip, Mapping)]


def _required_int(value: Any) -> int:
    return int(value)


def _atempo_filter_chain(factor: float) -> List[str]:
    remaining = factor
    filters = []
    while remaining > 2.0:
        filters.append("atempo=2.0000")
        remaining /= 2.0
    filters.append(f"atempo={remaining:.4f}")
    return filters
