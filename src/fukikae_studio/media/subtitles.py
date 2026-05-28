from typing import Any, Iterable, Mapping, Optional, Tuple

ASS_SAGE_GREEN_BOX = "&H40748B6E"
ASS_TEXT_WHITE = "&H00FFFFFF"


def build_srt(segments: Iterable[Mapping[str, object]]) -> str:
    cues = []
    for index, segment in enumerate(segments, start=1):
        start_ms, end_ms = _segment_timing_ms(segment)
        cues.append(
            "\n".join(
                [
                    str(index),
                    f"{_format_timestamp(start_ms, ',')} --> {_format_timestamp(end_ms, ',')}",
                    _target_text(segment),
                    "",
                ]
            )
        )
    return "\n".join(cues)


def build_webvtt(segments: Iterable[Mapping[str, object]]) -> str:
    cues = []
    for segment in segments:
        start_ms, end_ms = _segment_timing_ms(segment)
        cues.append(
            "\n".join(
                [
                    str(segment["id"]),
                    f"{_format_timestamp(start_ms, '.')} --> {_format_timestamp(end_ms, '.')}",
                    _target_text(segment),
                    "",
                ]
            )
        )
    if not cues:
        return "WEBVTT\n"
    return "WEBVTT\n\n" + "\n".join(cues)


def build_ass(segments: Iterable[Mapping[str, object]]) -> str:
    header = f"""[Script Info]
Title: FukiKae Studio Japanese subtitles
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: FukiKaeBox,Hiragino Sans,44,{ASS_TEXT_WHITE},{ASS_TEXT_WHITE},&H00000000,{ASS_SAGE_GREEN_BOX},1,0,0,0,100,100,0,0,3,8,0,2,120,120,220,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    rows = []
    for segment in segments:
        start_ms, end_ms = _segment_timing_ms(segment)
        text = _target_text(segment).replace("\n", r"\N")
        rows.append(
            f"Dialogue: 0,{_format_ass_timestamp(start_ms)},{_format_ass_timestamp(end_ms)},"
            f"FukiKaeBox,,0,0,0,,{text}"
        )
    return header + "\n".join(rows) + ("\n" if rows else "")


def _segment_timing_ms(segment: Mapping[str, object]) -> Tuple[int, int]:
    start_ms = _optional_int(segment.get("dub_start_ms"))
    end_ms = _optional_int(segment.get("dub_end_ms"))
    if start_ms is None:
        start_ms = _required_int(segment["source_start_ms"])
    if end_ms is None:
        end_ms = _required_int(segment["source_end_ms"])
    if start_ms < 0 or end_ms <= start_ms:
        raise ValueError(f"Invalid subtitle timing for segment {segment.get('id', '<unknown>')}")
    return start_ms, end_ms


def _target_text(segment: Mapping[str, object]) -> str:
    text = segment.get("target_text")
    if text is None or str(text).strip() == "":
        raise ValueError(f"Missing target_text for subtitle segment {segment.get('id', '<unknown>')}")
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cleaned = [line.strip() for line in lines if line.strip()]
    return "\n".join(cleaned)


def _format_timestamp(milliseconds: int, separator: str) -> str:
    total_ms = _required_int(milliseconds)
    if total_ms < 0:
        raise ValueError("Subtitle timestamp cannot be negative")
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{millis:03d}"


def _format_ass_timestamp(milliseconds: int) -> str:
    total_ms = _required_int(milliseconds)
    if total_ms < 0:
        raise ValueError("Subtitle timestamp cannot be negative")
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    centiseconds = millis // 10
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def _required_int(value: Any) -> int:
    return int(value)


def _optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    return int(value)
