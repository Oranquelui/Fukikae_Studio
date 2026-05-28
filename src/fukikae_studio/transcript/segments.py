import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional

from fukikae_studio.ai.schemas import NORMALIZED_SEGMENT_FIELDS


@dataclass(frozen=True)
class Segment:
    id: str
    source_start_ms: int
    source_end_ms: int
    source_text: str
    speaker: Optional[str] = None
    source_lang: str = "auto"
    target_lang: str = "ja"
    target_text: Optional[str] = None
    dub_start_ms: Optional[int] = None
    dub_end_ms: Optional[int] = None
    tts_audio_path: Optional[str] = None
    timing_strategy: str = "fit_to_source_segment"
    status: str = "stt_complete"

    def __post_init__(self) -> None:
        if self.dub_start_ms is None:
            object.__setattr__(self, "dub_start_ms", self.source_start_ms)
        if self.dub_end_ms is None:
            object.__setattr__(self, "dub_end_ms", self.source_end_ms)

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "Segment":
        return cls(
            id=str(data["id"]),
            source_start_ms=_required_int(data["source_start_ms"]),
            source_end_ms=_required_int(data["source_end_ms"]),
            speaker=_optional_str(data.get("speaker")),
            source_lang=str(data.get("source_lang", "auto")),
            source_text=str(data.get("source_text", "")),
            target_lang=str(data.get("target_lang", "ja")),
            target_text=_optional_str(data.get("target_text")),
            dub_start_ms=_optional_int(data.get("dub_start_ms")),
            dub_end_ms=_optional_int(data.get("dub_end_ms")),
            tts_audio_path=_optional_str(data.get("tts_audio_path")),
            timing_strategy=str(data.get("timing_strategy", "fit_to_source_segment")),
            status=str(data.get("status", "stt_complete")),
        )

    def to_dict(self) -> dict:
        values = {
            "id": self.id,
            "source_start_ms": self.source_start_ms,
            "source_end_ms": self.source_end_ms,
            "speaker": self.speaker,
            "source_lang": self.source_lang,
            "source_text": self.source_text,
            "target_lang": self.target_lang,
            "target_text": self.target_text,
            "dub_start_ms": self.dub_start_ms,
            "dub_end_ms": self.dub_end_ms,
            "tts_audio_path": self.tts_audio_path,
            "timing_strategy": self.timing_strategy,
            "status": self.status,
        }
        return {field: values[field] for field in NORMALIZED_SEGMENT_FIELDS}


def load_segments_json(path: Path) -> List[Segment]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Segment.from_dict(item) for item in data]


def dump_segments_json(segments: Iterable[Segment]) -> str:
    return json.dumps([segment.to_dict() for segment in segments], ensure_ascii=False, indent=2) + "\n"


def _optional_str(value: object) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _required_int(value: Any) -> int:
    return int(value)


def _optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    return int(value)
