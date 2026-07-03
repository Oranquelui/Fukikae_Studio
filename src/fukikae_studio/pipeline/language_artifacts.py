from pathlib import Path

SUPPORTED_TARGET_LANGUAGES = ("ja", "en")

LANGUAGE_FILE_LABELS = {
    "ja": "japanese",
    "en": "english",
}

SUBTITLE_METADATA_LANGUAGES = {
    "ja": "jpn",
    "en": "eng",
}


def normalize_target_language(value: object) -> str:
    language = str(value or "ja").strip().lower()
    if language not in SUPPORTED_TARGET_LANGUAGES:
        choices = ", ".join(SUPPORTED_TARGET_LANGUAGES)
        raise ValueError(f"Invalid target language: {language or '<empty>'}. Choose one of: {choices}")
    return language


def language_file_label(target_lang: object) -> str:
    return LANGUAGE_FILE_LABELS[normalize_target_language(target_lang)]


def subtitle_metadata_language(target_lang: object) -> str:
    return SUBTITLE_METADATA_LANGUAGES[normalize_target_language(target_lang)]


def dubbing_segments_artifact(target_lang: object) -> str:
    return f"script/{language_file_label(target_lang)}_dubbing_segments.json"


def dubbing_segments_path(project_dir: Path, target_lang: object) -> Path:
    return Path(project_dir) / dubbing_segments_artifact(target_lang)


def subtitle_artifacts(target_lang: object) -> dict[str, str]:
    label = language_file_label(target_lang)
    return {
        "srt": f"assembly/{label}_subtitles.srt",
        "webvtt": f"assembly/{label}_subtitles.vtt",
        "ass": f"assembly/{label}_subtitles.ass",
    }


def soft_output_artifact(target_lang: object) -> str:
    language = normalize_target_language(target_lang)
    return f"output/dubbed.{language}.mp4"


def burned_output_artifact(target_lang: object) -> str:
    language = normalize_target_language(target_lang)
    return f"output/dubbed.{language}.burned.mp4"


def subtitle_only_soft_output_artifact(target_lang: object) -> str:
    language = normalize_target_language(target_lang)
    return f"output/subtitled.{language}.mp4"


def subtitle_only_burned_output_artifact(target_lang: object) -> str:
    language = normalize_target_language(target_lang)
    return f"output/subtitled.{language}.burned.mp4"
