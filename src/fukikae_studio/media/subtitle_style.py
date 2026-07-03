import re
from dataclasses import dataclass
from typing import Mapping, Optional, Union

DEFAULT_SUBTITLE_BACKGROUND_COLOR = "#748B6E"
DEFAULT_SUBTITLE_FONT_COLOR = "#FFFFFF"
DEFAULT_SUBTITLE_FONT_SIZE = 44
MIN_SUBTITLE_FONT_SIZE = 18
MAX_SUBTITLE_FONT_SIZE = 96
ASS_BACKGROUND_ALPHA = 0x40

_HEX_COLOR_PATTERN = re.compile(r"^#?[0-9A-Fa-f]{6}$")


@dataclass(frozen=True)
class SubtitleStyle:
    background_color: str = DEFAULT_SUBTITLE_BACKGROUND_COLOR
    font_color: str = DEFAULT_SUBTITLE_FONT_COLOR
    font_size: int = DEFAULT_SUBTITLE_FONT_SIZE

    def to_manifest(self) -> dict:
        return {
            "background_color": self.background_color,
            "font_color": self.font_color,
            "font_size": self.font_size,
        }

    def background_rgba(self) -> tuple[int, int, int, int]:
        return (*_hex_to_rgb(self.background_color), 255)

    def font_rgba(self) -> tuple[int, int, int, int]:
        return (*_hex_to_rgb(self.font_color), 255)

    def ass_background_color(self) -> str:
        return _ass_color(self.background_color, alpha=ASS_BACKGROUND_ALPHA)

    def ass_font_color(self) -> str:
        return _ass_color(self.font_color, alpha=0)


SubtitleStyleInput = Optional[Union[SubtitleStyle, Mapping[str, object]]]


def normalize_subtitle_style(
    subtitle_style: SubtitleStyleInput = None,
    *,
    background_color: Optional[object] = None,
    font_color: Optional[object] = None,
    font_size: Optional[object] = None,
) -> SubtitleStyle:
    if isinstance(subtitle_style, SubtitleStyle):
        base_background = subtitle_style.background_color
        base_font = subtitle_style.font_color
        base_size = subtitle_style.font_size
    elif isinstance(subtitle_style, Mapping):
        base_background = subtitle_style.get("background_color", DEFAULT_SUBTITLE_BACKGROUND_COLOR)
        base_font = subtitle_style.get("font_color", DEFAULT_SUBTITLE_FONT_COLOR)
        base_size = subtitle_style.get("font_size", DEFAULT_SUBTITLE_FONT_SIZE)
    elif subtitle_style is None:
        base_background = DEFAULT_SUBTITLE_BACKGROUND_COLOR
        base_font = DEFAULT_SUBTITLE_FONT_COLOR
        base_size = DEFAULT_SUBTITLE_FONT_SIZE
    else:
        raise TypeError("subtitle_style must be a SubtitleStyle, mapping, or None")

    if background_color is not None:
        base_background = background_color
    if font_color is not None:
        base_font = font_color
    if font_size is not None:
        base_size = font_size

    return SubtitleStyle(
        background_color=_normalize_hex_color(base_background, field_name="subtitle background color"),
        font_color=_normalize_hex_color(base_font, field_name="subtitle font color"),
        font_size=_normalize_font_size(base_size),
    )


def _normalize_hex_color(value: object, field_name: str) -> str:
    raw = str(value or "").strip()
    if not _HEX_COLOR_PATTERN.match(raw):
        raise ValueError(f"Invalid {field_name}: {raw or '<empty>'}. Use #RRGGBB.")
    if not raw.startswith("#"):
        raw = f"#{raw}"
    return raw.upper()


def _normalize_font_size(value: object) -> int:
    try:
        size = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Subtitle font size must be a number.") from exc
    if size < MIN_SUBTITLE_FONT_SIZE or size > MAX_SUBTITLE_FONT_SIZE:
        raise ValueError(
            f"Subtitle font size must be between {MIN_SUBTITLE_FONT_SIZE} and {MAX_SUBTITLE_FONT_SIZE}."
        )
    return size


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    normalized = _normalize_hex_color(color, field_name="subtitle color")
    return int(normalized[1:3], 16), int(normalized[3:5], 16), int(normalized[5:7], 16)


def _ass_color(color: str, alpha: int = 0) -> str:
    red, green, blue = _hex_to_rgb(color)
    return f"&H{alpha:02X}{blue:02X}{green:02X}{red:02X}"
