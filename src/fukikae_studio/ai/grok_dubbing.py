import json
from typing import Iterable, List, Mapping, Optional, Protocol

from fukikae_studio.ai.prompts import build_dubbing_prompt, default_dubbing_style
from fukikae_studio.pipeline.language_artifacts import normalize_target_language

RESPONSES_ENDPOINT = "/responses"


class JSONClient(Protocol):
    def post_json(self, path: str, payload: Mapping[str, object]) -> object:
        ...


class DubbingScriptError(ValueError):
    """Raised when Grok dubbing output violates the segment contract."""


def build_grok_dubbing_payload(
    source_segments: Iterable[Mapping[str, object]],
    model: str = "grok-4.3",
    target_lang: str = "ja",
    style: Optional[str] = None,
    repair_instruction: str = "",
) -> dict:
    language = normalize_target_language(target_lang)
    dubbing_style = style or default_dubbing_style(language)
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": "You are the xAI-only dubbing script adapter for FukiKae Studio.",
            },
            {
                "role": "user",
                "content": build_dubbing_prompt(source_segments, target_lang=language, style=dubbing_style),
            },
        ],
    }
    if repair_instruction:
        payload["input"].append({"role": "user", "content": repair_instruction})
    return payload


def parse_grok_dubbing_response(response: Mapping[str, object], expected_segment_ids: Iterable[str]) -> List[dict]:
    output_text = _extract_output_text(response)
    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise DubbingScriptError("Grok dubbing response was not strict JSON") from exc
    segments = payload.get("segments")
    if not isinstance(segments, list):
        raise DubbingScriptError("Grok dubbing response must contain a segments list")
    _validate_segment_ids(segments, expected_segment_ids)
    _validate_complete_target_text(segments)
    return [dict(segment) for segment in segments]


def generate_dubbing_script(
    client: JSONClient,
    source_segments: Iterable[Mapping[str, object]],
    model: str = "grok-4.3",
    target_lang: str = "ja",
    style: Optional[str] = None,
    max_repair_attempts: int = 1,
) -> List[dict]:
    language = normalize_target_language(target_lang)
    dubbing_style = style or default_dubbing_style(language)
    source_segment_list = list(source_segments)
    expected_segment_ids = [str(item["id"]) for item in source_segment_list]
    last_error: Optional[DubbingScriptError] = None
    for attempt in range(max_repair_attempts + 1):
        payload = build_grok_dubbing_payload(
            source_segment_list,
            model=model,
            target_lang=language,
            style=dubbing_style,
            repair_instruction=_repair_instruction(last_error) if attempt > 0 else "",
        )
        response = client.post_json(RESPONSES_ENDPOINT, payload)
        if not isinstance(response, Mapping):
            raise DubbingScriptError("Grok dubbing response must be an object")
        try:
            return parse_grok_dubbing_response(response, expected_segment_ids=expected_segment_ids)
        except DubbingScriptError as exc:
            if "unfinished Japanese fragment" not in str(exc) or attempt >= max_repair_attempts:
                raise
            last_error = exc
    raise DubbingScriptError("Grok dubbing response repair failed")


def _extract_output_text(response: Mapping[str, object]) -> str:
    output_text = response.get("output_text")
    if isinstance(output_text, str):
        return output_text
    output = response.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, Mapping):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for content_item in content:
                if not isinstance(content_item, Mapping):
                    continue
                if content_item.get("type") == "output_text" and isinstance(content_item.get("text"), str):
                    return str(content_item["text"])
    raise DubbingScriptError("Grok dubbing response did not include output_text")


def _validate_segment_ids(segments: List[object], expected_segment_ids: Iterable[str]) -> None:
    expected = [str(segment_id) for segment_id in expected_segment_ids]
    actual = []
    for segment in segments:
        if not isinstance(segment, Mapping):
            raise DubbingScriptError("Each dubbing segment must be an object")
        actual.append(str(segment.get("id")))
    missing = [segment_id for segment_id in expected if segment_id not in actual]
    extra = [segment_id for segment_id in actual if segment_id not in expected]
    if missing or extra:
        parts = []
        if missing:
            parts.append(f"missing segment IDs: {', '.join(missing)}")
        if extra:
            parts.append(f"extra segment IDs: {', '.join(extra)}")
        raise DubbingScriptError("; ".join(parts))


def _validate_complete_target_text(segments: List[object]) -> None:
    dangling_endings = ("が", "は", "を", "に", "で", "と", "の", "から", "ため", "そして")
    for segment in segments:
        if not isinstance(segment, Mapping):
            continue
        text = str(segment.get("target_text", "")).strip()
        if any(text.endswith(ending) for ending in dangling_endings):
            raise DubbingScriptError(
                f"Segment {segment.get('id', '<unknown>')} target_text is an unfinished Japanese fragment"
            )


def _repair_instruction(error: Optional[DubbingScriptError]) -> str:
    detail = str(error) if error is not None else "unfinished Japanese fragment"
    return (
        "Repair only the invalid dubbing script. Return the full strict JSON again with the same segment IDs. "
        f"Fix this validation error: {detail}. "
        "Every target_text must be a complete Japanese utterance and must not end with dangling particles."
    )
