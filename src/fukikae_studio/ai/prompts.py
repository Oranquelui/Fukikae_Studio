import json
from typing import Iterable, Mapping

from fukikae_studio.pipeline.language_artifacts import normalize_target_language


TIMING_BUFFER_RATIO = 0.92


def build_dubbing_prompt(
    source_segments: Iterable[Mapping[str, object]],
    target_lang: str = "ja",
    style: str = "natural-japanese-dub",
) -> str:
    language = normalize_target_language(target_lang)
    segment_json = json.dumps(build_timing_guided_segments(source_segments), ensure_ascii=False, indent=2)
    language_name = _target_language_name(language)
    guidance = _language_guidance(language)
    return f"""Create a {language_name} dubbing script for FukiKae Studio.

Requirements:
- target_lang={language}
- Use natural {language_name} dubbing style for spoken video narration.
- preserve segment IDs exactly; do not add, drop, or rename IDs.
- Preserve speaker intent and source timing.
- Keep target_text concise enough to fit each source segment.
- Each source segment includes slot_duration_ms, target_max_duration_ms, and timing_pressure.
- Treat target_max_duration_ms as the speaking-time budget; estimated_duration_ms <= target_max_duration_ms.
{guidance}
- Return strict JSON only with top-level key "segments".
- Each item must include: id, source_start_ms, source_end_ms, speaker, source_text,
  target_text, reading_hint, style_notes, estimated_duration_ms, priority.
- style={style}

Source segments:
{segment_json}
"""


def default_dubbing_style(target_lang: object) -> str:
    language = normalize_target_language(target_lang)
    return {
        "ja": "natural-japanese-dub",
        "en": "natural-english-dub",
    }[language]


def _target_language_name(target_lang: str) -> str:
    return {
        "ja": "Japanese",
        "en": "English",
    }[target_lang]


def _language_guidance(target_lang: str) -> str:
    if target_lang == "ja":
        return """- When timing_pressure is tight or very_tight, shorten the Japanese translation before TTS tempo fitting:
  omit filler, avoid literal word-for-word phrasing, prefer compact spoken Japanese, and do not add explanations.
- Do not leave target_text as an unfinished fragment. Even when shortening, every target_text must read as a
  complete Japanese utterance with no dangling modifier, cut-off clause, or trailing unfinished phrase.
- Never end target_text with dangling Japanese particles such as が, は, を, に, で, と, の, から, ため, or そして.
  If source meaning is too long, rewrite into a shorter complete sentence instead of cutting the sentence."""
    return """- When timing_pressure is tight or very_tight, shorten the English adaptation before TTS tempo fitting:
  omit filler, avoid literal word-for-word phrasing, prefer compact spoken English, and do not add explanations.
- Do not leave target_text as an unfinished fragment. Even when shortening, every target_text must read as a
  complete English utterance with no dangling modifier, cut-off clause, or trailing unfinished phrase.
- Prefer clear narration phrasing over subtitles-only phrasing; keep punctuation natural for spoken English."""


def build_timing_guided_segments(source_segments: Iterable[Mapping[str, object]]) -> list[dict]:
    guided_segments = []
    for segment in source_segments:
        guided = dict(segment)
        slot_duration_ms = _segment_duration_ms(segment)
        guided["slot_duration_ms"] = slot_duration_ms
        guided["target_max_duration_ms"] = max(500, int(slot_duration_ms * TIMING_BUFFER_RATIO))
        guided["timing_pressure"] = _timing_pressure(slot_duration_ms)
        guided_segments.append(guided)
    return guided_segments


def _segment_duration_ms(segment: Mapping[str, object]) -> int:
    start_ms = int(segment["source_start_ms"])
    end_ms = int(segment["source_end_ms"])
    return max(1, end_ms - start_ms)


def _timing_pressure(slot_duration_ms: int) -> str:
    if slot_duration_ms <= 1800:
        return "very_tight"
    if slot_duration_ms <= 3200:
        return "tight"
    return "normal"
