import json
from pathlib import Path
from typing import Iterable, Mapping

from fukikae_studio.logging_redaction import redact_secrets


def write_stt_artifacts(
    project_dir: Path,
    request_metadata: Mapping[str, object],
    raw_response: Mapping[str, object],
    normalized_segments: Iterable[Mapping[str, object]],
    secrets: Iterable[str] = (),
) -> None:
    stt_dir = Path(project_dir) / "stt"
    stt_dir.mkdir(parents=True, exist_ok=True)
    _write_json(stt_dir / "xai_stt_request.json", _sanitize(request_metadata, secrets=secrets))
    _write_json(stt_dir / "xai_stt_response.json", raw_response)
    _write_json(stt_dir / "normalized_segments.json", list(normalized_segments))


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sanitize(value: object, secrets: Iterable[str]) -> object:
    if isinstance(value, Mapping):
        sanitized = {}
        for key, item in value.items():
            if str(key).lower() == "authorization":
                continue
            sanitized[key] = _sanitize(item, secrets=secrets)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item, secrets=secrets) for item in value]
    if isinstance(value, str):
        return redact_secrets(value, secrets=secrets)
    return value
