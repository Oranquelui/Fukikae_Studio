from fukikae_studio.pipeline.language_artifacts import (
    burned_output_artifact,
    soft_output_artifact,
    subtitle_only_burned_output_artifact,
    subtitle_only_soft_output_artifact,
)
from fukikae_studio.pipeline.processing_mode import DEFAULT_PROCESSING_MODE, is_subtitle_only_mode

DEFAULT_SUBTITLE_OUTPUT = "both"
SUBTITLE_OUTPUT_CHOICES = ("both", "burned", "soft")


def normalize_subtitle_output(value: object) -> str:
    mode = str(value or DEFAULT_SUBTITLE_OUTPUT).strip().lower()
    if mode not in SUBTITLE_OUTPUT_CHOICES:
        choices = ", ".join(SUBTITLE_OUTPUT_CHOICES)
        raise ValueError(f"Invalid subtitle output mode: {mode or '<empty>'}. Choose one of: {choices}")
    return mode


def final_output_for_subtitle_output(
    value: object,
    target_lang: object = "ja",
    processing_mode: object = DEFAULT_PROCESSING_MODE,
) -> str:
    mode = normalize_subtitle_output(value)
    if is_subtitle_only_mode(processing_mode):
        if mode in {"both", "burned"}:
            return subtitle_only_burned_output_artifact(target_lang)
        return subtitle_only_soft_output_artifact(target_lang)
    if mode in {"both", "burned"}:
        return burned_output_artifact(target_lang)
    return soft_output_artifact(target_lang)
