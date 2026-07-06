import json
from typing import Iterable, List, Mapping, Optional, Protocol

from fukikae_studio.ai.prompts import build_dubbing_prompt, default_dubbing_style
from fukikae_studio.pipeline.language_artifacts import normalize_target_language

RESPONSES_ENDPOINT = "/responses"
JAPANESE_DANGLING_ENDINGS = ("が", "は", "を", "に", "で", "と", "の", "から", "ため", "そして")
SOURCE_COMPLETE_ENDINGS = (".", "!", "?", "。", "！", "？", "」", "』", '"', "'", ")", "）")


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


def build_grok_dubbing_review_payload(
    source_segments: Iterable[Mapping[str, object]],
    candidate_segments: Iterable[Mapping[str, object]],
    model: str = "grok-4.3",
    target_lang: str = "ja",
    style: Optional[str] = None,
    repair_instruction: str = "",
) -> dict:
    language = normalize_target_language(target_lang)
    dubbing_style = style or default_dubbing_style(language)
    review_input = {
        "target_lang": language,
        "style": dubbing_style,
        "source_segments": list(source_segments),
        "candidate_segments": list(candidate_segments),
    }
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": "You are the xAI-only dubbing translation quality reviewer for FukiKae Studio.",
            },
            {
                "role": "user",
                "content": _build_review_prompt(review_input),
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
    quality_review: bool = False,
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
            dubbing_segments = parse_grok_dubbing_response(response, expected_segment_ids=expected_segment_ids)
            if quality_review:
                return review_dubbing_script(
                    client,
                    source_segment_list,
                    dubbing_segments,
                    model=model,
                    target_lang=language,
                    style=dubbing_style,
                )
            return dubbing_segments
        except DubbingScriptError as exc:
            if not _is_repairable_dubbing_error(exc) or attempt >= max_repair_attempts:
                raise
            last_error = exc
    raise DubbingScriptError("Grok dubbing response repair failed")


def review_dubbing_script(
    client: JSONClient,
    source_segments: Iterable[Mapping[str, object]],
    candidate_segments: Iterable[Mapping[str, object]],
    model: str = "grok-4.3",
    target_lang: str = "ja",
    style: Optional[str] = None,
    max_repair_attempts: int = 1,
) -> List[dict]:
    source_segment_list = list(source_segments)
    candidate_segment_list = list(candidate_segments)
    expected_segment_ids = [str(item["id"]) for item in source_segment_list]
    last_error: Optional[DubbingScriptError] = None
    for attempt in range(max_repair_attempts + 1):
        payload = build_grok_dubbing_review_payload(
            source_segment_list,
            candidate_segment_list,
            model=model,
            target_lang=target_lang,
            style=style,
            repair_instruction=_repair_instruction(last_error) if attempt > 0 else "",
        )
        response = client.post_json(RESPONSES_ENDPOINT, payload)
        if not isinstance(response, Mapping):
            raise DubbingScriptError("Grok dubbing review response must be an object")
        try:
            return parse_grok_dubbing_response(response, expected_segment_ids=expected_segment_ids)
        except DubbingScriptError as exc:
            if not _is_repairable_dubbing_error(exc) or attempt >= max_repair_attempts:
                raise
            last_error = exc
    raise DubbingScriptError("Grok dubbing review repair failed")


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
    for segment in segments:
        if not isinstance(segment, Mapping):
            continue
        text = str(segment.get("target_text", "")).strip()
        if not text:
            raise DubbingScriptError(f"Segment {segment.get('id', '<unknown>')} has empty target_text")
        if _has_dangling_japanese_ending(text) and _source_segment_looks_complete(segment):
            raise DubbingScriptError(
                f"Segment {segment.get('id', '<unknown>')} target_text is an unfinished Japanese fragment"
            )


def _has_dangling_japanese_ending(text: str) -> bool:
    return any(text.endswith(ending) for ending in JAPANESE_DANGLING_ENDINGS)


def _source_segment_looks_complete(segment: Mapping[str, object]) -> bool:
    source_text = segment.get("source_text")
    if not isinstance(source_text, str) or not source_text.strip():
        return True
    return source_text.strip().endswith(SOURCE_COMPLETE_ENDINGS)


def _is_repairable_dubbing_error(error: DubbingScriptError) -> bool:
    detail = str(error)
    return "unfinished Japanese fragment" in detail or "empty target_text" in detail


def _repair_instruction(error: Optional[DubbingScriptError]) -> str:
    detail = str(error) if error is not None else "unfinished Japanese fragment"
    return (
        "Repair only the invalid dubbing script. Return the full strict JSON again with the same segment IDs. "
        f"Fix this validation error: {detail}. "
        "Every target_text must be non-empty and complete. Japanese target_text must not end with dangling particles."
    )


def _build_review_prompt(review_input: Mapping[str, object]) -> str:
    target_lang = str(review_input["target_lang"])
    target_name = "English" if target_lang == "en" else "Japanese"
    payload_json = json.dumps(review_input, ensure_ascii=False, indent=2)
    return f"""Review and repair the candidate {target_name} dubbing script.

Rules:
- Compare every candidate target_text against the matching source segment source_text.
- Preserve segment IDs exactly; do not add, drop, merge, or rename IDs.
- Return the full corrected strict JSON with top-level key "segments".
- Keep timing fields, speaker, and source_text from the candidate unless they are missing.
- Fix mistranslations, omissions, hallucinated facts, role label substitutions, title-card/chyron substitutions,
  number errors, dropped negation, and broken responsibility wording.
- Do not replace spoken content with a role label, title card, chyron, speaker name, or location label.
- If source_text is a first person apology, target_text must remain a first person apology. For example,
  "この度は大変申し訳ございませんでした。" should be rendered like "I am truly sorry for this.", not as a
  role label such as "Matsumoto City Mayor."
- For Japanese news source text, use concise broadcast-news English while preserving exact facts:
  約11万5千人 -> about 115,000 residents; 業務用PC83台 -> 83 work computers;
  個人情報の流出はない -> no leak of personal information.
- Keep target_text concise enough for spoken dubbing.

Review input:
{payload_json}
"""
