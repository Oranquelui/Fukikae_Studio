from pathlib import Path
from typing import List, Optional

from fukikae_studio.media.ffmpeg import assert_inside_project


def build_extract_audio_command(source_video: Path, output_wav: Path, overwrite: bool = False) -> List[str]:
    overwrite_flag = "-y" if overwrite else "-n"
    return [
        "ffmpeg",
        "-nostdin",
        overwrite_flag,
        "-i",
        str(source_video),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(output_wav),
    ]


def build_project_audio_extraction_command(
    project_dir: Path,
    source_video: Optional[Path] = None,
    output_wav: Optional[Path] = None,
    overwrite: bool = False,
) -> List[str]:
    project = Path(project_dir)
    source = source_video or project / "input" / "source.mp4"
    output = output_wav or project / "media" / "source_audio_for_stt.wav"
    assert_inside_project(project, source)
    assert_inside_project(project, output)
    return build_extract_audio_command(source, output, overwrite=overwrite)
