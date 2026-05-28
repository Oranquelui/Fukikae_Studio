DEFAULT_SUBTITLE_OUTPUT = "both"
SUBTITLE_OUTPUT_CHOICES = ("both", "burned", "soft")


def normalize_subtitle_output(value: object) -> str:
    mode = str(value or DEFAULT_SUBTITLE_OUTPUT).strip().lower()
    if mode not in SUBTITLE_OUTPUT_CHOICES:
        choices = ", ".join(SUBTITLE_OUTPUT_CHOICES)
        raise ValueError(f"Invalid subtitle output mode: {mode or '<empty>'}. Choose one of: {choices}")
    return mode


def final_output_for_subtitle_output(value: object) -> str:
    mode = normalize_subtitle_output(value)
    if mode in {"both", "burned"}:
        return "output/dubbed.ja.burned.mp4"
    return "output/dubbed.ja.mp4"
