import re
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional, Protocol, Tuple

from fukikae_studio.transcript.segments import Segment

STT_ENDPOINT = "/stt"


class MultipartClient(Protocol):
    def post_multipart(
        self,
        path: str,
        fields: Mapping[str, object],
        files: Mapping[str, Tuple[str, bytes, str]],
    ) -> object:
        ...


def build_stt_fields(source_lang: str = "auto", diarize: bool = True, formatted: bool = True) -> dict:
    fields = {}
    if formatted and source_lang and source_lang != "auto":
        fields["format"] = "true"
    if diarize:
        fields["diarize"] = "true"
    if source_lang and source_lang != "auto":
        fields["language"] = source_lang
    return fields


def transcribe_audio_bytes(
    client: MultipartClient,
    filename: str,
    audio_bytes: bytes,
    source_lang: str = "auto",
    content_type: str = "audio/wav",
) -> object:
    fields = build_stt_fields(source_lang=source_lang)
    files = {"file": (filename, audio_bytes, content_type)}
    return client.post_multipart(STT_ENDPOINT, fields=fields, files=files)


def normalize_stt_response(
    response: Mapping[str, object],
    source_lang: str = "auto",
    target_lang: str = "ja",
) -> List[dict]:
    raw_segments_value = response.get("segments")
    if isinstance(raw_segments_value, list):
        raw_segments = raw_segments_value
    else:
        raw_segments = _single_segment_from_words(response.get("words") or [])
    normalized = []
    for index, segment in enumerate(raw_segments, start=1):
        start_ms = _seconds_to_ms(segment["start"])
        end_ms = _seconds_to_ms(segment["end"])
        normalized.append(
            Segment(
                id=f"seg_{index:04d}",
                source_start_ms=start_ms,
                source_end_ms=end_ms,
                speaker=_format_speaker(segment.get("speaker")),
                source_lang=source_lang,
                source_text=str(segment.get("text", "")).strip(),
                target_lang=target_lang,
                target_text=None,
                dub_start_ms=start_ms,
                dub_end_ms=end_ms,
                tts_audio_path=None,
                timing_strategy="fit_to_source_segment",
                status="stt_complete",
            ).to_dict()
        )
    return normalized


def build_stt_batch_plan(audio_paths: Iterable[Path], source_lang: str = "auto") -> List[dict]:
    return [
        {"audio_path": str(path), "source_lang": source_lang, "endpoint": STT_ENDPOINT}
        for path in audio_paths
    ]


WORD_SEGMENT_PAUSE_SECONDS = 0.8
WORD_SEGMENT_MAX_SECONDS = 7.0


def _single_segment_from_words(words: object) -> List[dict]:
    if not isinstance(words, list) or not words:
        return []
    segments = []
    current = [words[0]]
    for word in words[1:]:
        previous = current[-1]
        if (
            _word_gap_seconds(previous, word) > WORD_SEGMENT_PAUSE_SECONDS
            or _word_span_seconds(current[0], word) > WORD_SEGMENT_MAX_SECONDS
        ):
            segments.append(_segment_from_word_group(current))
            current = [word]
        else:
            current.append(word)
    segments.append(_segment_from_word_group(current))
    return segments


def _segment_from_word_group(words: List[object]) -> dict:
    return {
        "start": words[0]["start"],
        "end": words[-1]["end"],
        "text": _join_word_texts(words),
        "speaker": words[0].get("speaker") if isinstance(words[0], Mapping) else None,
    }


def _join_word_texts(words: List[object]) -> str:
    texts = [_word_text(word) for word in words]
    texts = [text for text in texts if text]
    if _looks_like_cjk_word_sequence(texts):
        return "".join(texts).strip()
    return " ".join(texts).strip()


def _looks_like_cjk_word_sequence(texts: List[str]) -> bool:
    if not texts:
        return False
    cjk_tokens = sum(1 for text in texts if re.search(r"[\u3040-\u30ff\u3400-\u9fff]", text))
    return cjk_tokens > len(texts) / 2


def _word_gap_seconds(previous: object, current: object) -> float:
    if not isinstance(previous, Mapping) or not isinstance(current, Mapping):
        return 0.0
    return float(current["start"]) - float(previous["end"])


def _word_span_seconds(first: object, current: object) -> float:
    if not isinstance(first, Mapping) or not isinstance(current, Mapping):
        return 0.0
    return float(current["end"]) - float(first["start"])


def _word_text(word: object) -> str:
    if not isinstance(word, Mapping):
        return ""
    return str(word.get("text") or word.get("word") or "").strip()


def _seconds_to_ms(value: Any) -> int:
    return int(round(float(value) * 1000))


def _format_speaker(value: Optional[object]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, int):
        return f"SPEAKER_{value:02d}"
    text = str(value).strip()
    if text.upper().startswith("SPEAKER_"):
        return text.upper()
    if text.isdigit():
        return f"SPEAKER_{int(text):02d}"
    return text
