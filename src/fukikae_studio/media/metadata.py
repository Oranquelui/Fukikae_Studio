from pathlib import Path
from typing import List, Optional

from fukikae_studio.media.ffmpeg import assert_inside_project


def build_ffprobe_metadata_command(source_video: Path) -> List[str]:
    return [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(source_video),
    ]


def build_project_ffprobe_metadata_command(project_dir: Path, source_video: Optional[Path] = None) -> List[str]:
    project = Path(project_dir)
    source = source_video or project / "input" / "source.mp4"
    assert_inside_project(project, source)
    return build_ffprobe_metadata_command(source)
