DEFAULT_PROCESSING_MODE = "dubbing"
PROCESSING_MODE_CHOICES = ("dubbing", "subtitles")


def normalize_processing_mode(value: object) -> str:
    mode = str(value or DEFAULT_PROCESSING_MODE).strip().lower()
    if mode not in PROCESSING_MODE_CHOICES:
        choices = ", ".join(PROCESSING_MODE_CHOICES)
        raise ValueError(f"Invalid processing mode: {mode or '<empty>'}. Choose one of: {choices}")
    return mode


def is_subtitle_only_mode(value: object) -> bool:
    return normalize_processing_mode(value) == "subtitles"
