import csv
import json
from pathlib import Path
from typing import Iterable, Mapping

from fukikae_studio.pipeline.language_artifacts import dubbing_segments_path, normalize_target_language

CSV_FIELDS = [
    "id",
    "source_start_ms",
    "source_end_ms",
    "speaker",
    "source_text",
    "target_text",
    "reading_hint",
    "style_notes",
    "estimated_duration_ms",
    "priority",
]


def write_dubbing_artifacts(
    project_dir: Path,
    request_payload: Mapping[str, object],
    raw_response: Mapping[str, object],
    dubbing_segments: Iterable[Mapping[str, object]],
    target_lang: object = "ja",
) -> None:
    script_dir = Path(project_dir) / "script"
    script_dir.mkdir(parents=True, exist_ok=True)
    target_language = normalize_target_language(target_lang)
    segment_list = [dict(segment) for segment in dubbing_segments]
    _write_json(script_dir / "grok_dubbing_request.json", request_payload)
    _write_json(script_dir / "grok_dubbing_response.json", raw_response)
    _write_json(dubbing_segments_path(project_dir, target_language), segment_list)
    _write_csv(script_dir / "dubbing_script.csv", segment_list)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_csv(path: Path, segments: Iterable[Mapping[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for segment in segments:
            writer.writerow({field: segment.get(field, "") for field in CSV_FIELDS})
