import pytest

from fukikae_studio.pipeline.language_artifacts import (
    burned_output_artifact,
    dubbing_segments_artifact,
    normalize_target_language,
    soft_output_artifact,
    subtitle_artifacts,
)
from fukikae_studio.pipeline.subtitle_output import final_output_for_subtitle_output


def test_language_artifacts_keep_japanese_paths_backward_compatible():
    assert normalize_target_language("ja") == "ja"
    assert dubbing_segments_artifact("ja") == "script/japanese_dubbing_segments.json"
    assert subtitle_artifacts("ja") == {
        "srt": "assembly/japanese_subtitles.srt",
        "webvtt": "assembly/japanese_subtitles.vtt",
        "ass": "assembly/japanese_subtitles.ass",
    }
    assert soft_output_artifact("ja") == "output/dubbed.ja.mp4"
    assert burned_output_artifact("ja") == "output/dubbed.ja.burned.mp4"


def test_language_artifacts_support_english_paths():
    assert normalize_target_language(" EN ") == "en"
    assert dubbing_segments_artifact("en") == "script/english_dubbing_segments.json"
    assert subtitle_artifacts("en") == {
        "srt": "assembly/english_subtitles.srt",
        "webvtt": "assembly/english_subtitles.vtt",
        "ass": "assembly/english_subtitles.ass",
    }
    assert soft_output_artifact("en") == "output/dubbed.en.mp4"
    assert burned_output_artifact("en") == "output/dubbed.en.burned.mp4"


def test_final_output_for_subtitle_output_is_language_specific():
    assert final_output_for_subtitle_output("both", target_lang="en") == "output/dubbed.en.burned.mp4"
    assert final_output_for_subtitle_output("burned", target_lang="en") == "output/dubbed.en.burned.mp4"
    assert final_output_for_subtitle_output("soft", target_lang="en") == "output/dubbed.en.mp4"


def test_normalize_target_language_rejects_unsupported_values():
    with pytest.raises(ValueError):
        normalize_target_language("fr")
