import re
from typing import Iterable, Optional

from fukikae_studio.transcript.segments import Segment

_LANG_RE = re.compile(r"^(auto|[a-z]{2}(-[A-Z]{2})?)$")


class SegmentValidationError(ValueError):
    """Raised when normalized transcript segments are malformed."""


def validate_segments(segments: Iterable[Segment]) -> None:
    previous_end: Optional[int] = None
    for segment in segments:
        _validate_single_segment(segment)
        if previous_end is not None and segment.source_start_ms < previous_end:
            raise SegmentValidationError(f"{segment.id}: overlap with previous segment")
        previous_end = segment.source_end_ms


def _validate_single_segment(segment: Segment) -> None:
    if segment.source_end_ms <= segment.source_start_ms:
        raise SegmentValidationError(f"{segment.id}: invalid timing")
    if not segment.source_text.strip():
        raise SegmentValidationError(f"{segment.id}: source_text is required")
    if not _LANG_RE.match(segment.target_lang):
        raise SegmentValidationError(f"{segment.id}: invalid target_lang")
    if not _LANG_RE.match(segment.source_lang):
        raise SegmentValidationError(f"{segment.id}: invalid source_lang")
