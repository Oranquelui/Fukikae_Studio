import json
import re
from pathlib import Path
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple

from fukikae_studio.media.subtitle_style import SubtitleStyle, SubtitleStyleInput, normalize_subtitle_style
from fukikae_studio.media.subtitles import _segment_timing_ms, _target_text

_DEFAULT_SUBTITLE_STYLE = normalize_subtitle_style()
SAGE_GREEN_RGBA = _DEFAULT_SUBTITLE_STYLE.background_rgba()
TEXT_RGBA = _DEFAULT_SUBTITLE_STYLE.font_rgba()
SHADOW_RGBA = (0, 0, 0, 160)
SUBTITLE_BOTTOM_MARGIN_RATIO = 0.12
SUBTITLE_MIN_BOX_HEIGHT_RATIO = 0.20

FONT_CANDIDATES = (
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/System/Library/Fonts/Apple Symbols.ttf",
)


def render_subtitle_overlay_images(
    segments: Iterable[Mapping[str, object]],
    output_dir: Path,
    video_size: Tuple[int, int],
    overwrite: bool = False,
    subtitle_style: SubtitleStyleInput = None,
) -> List[dict]:
    image_module, image_draw_module, image_font_module = _load_pillow()
    style = normalize_subtitle_style(subtitle_style)
    width, height = video_size
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    overlays = []

    for segment in segments:
        segment_id = str(segment["id"])
        start_ms, end_ms = _segment_timing_ms(segment)
        image_path = output / f"{segment_id}.png"
        if image_path.exists() and not overwrite:
            raise FileExistsError(f"Refusing to overwrite existing subtitle overlay: {image_path}")
        image = image_module.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = image_draw_module.Draw(image)
        _draw_subtitle_box(
            draw=draw,
            image_font_module=image_font_module,
            text=_target_text(segment),
            width=width,
            height=height,
            subtitle_style=style,
        )
        image.save(image_path)
        overlays.append({"id": segment_id, "image": image_path, "start_ms": start_ms, "end_ms": end_ms})

    manifest = {
        "schema_version": "0.1",
        "video_size": [width, height],
        "style": {
            **style.to_manifest(),
            "box_rgba": list(style.background_rgba()),
            "text_rgba": list(style.font_rgba()),
            "margin_bottom_ratio": SUBTITLE_BOTTOM_MARGIN_RATIO,
        },
        "overlays": [
            {**overlay, "image": str(overlay["image"])}
            for overlay in overlays
        ],
    }
    (output / "subtitle_overlay_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return overlays


def _draw_subtitle_box(
    draw: object,
    image_font_module: object,
    text: str,
    width: int,
    height: int,
    subtitle_style: SubtitleStyle,
) -> None:
    max_text_width = int(width * 0.82)
    base_font_size = subtitle_style.font_size
    minimum_font_size = max(16, int(subtitle_style.font_size * 0.72))
    font, lines = _fit_text(image_font_module, draw, text, max_text_width, base_font_size, minimum_font_size)
    rendered_font_size = int(getattr(font, "size", subtitle_style.font_size))
    line_spacing = max(4, int(rendered_font_size * 0.18))
    text_block = "\n".join(lines)
    text_bbox = draw.multiline_textbbox((0, 0), text_block, font=font, spacing=line_spacing)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    padding_x = max(18, int(width * 0.018))
    padding_y = max(10, int(height * 0.014))
    box_width = min(width - 32, text_width + padding_x * 2)
    box_height = max(text_height + padding_y * 2, int(height * SUBTITLE_MIN_BOX_HEIGHT_RATIO))
    x = (width - box_width) // 2
    bottom_margin = max(24, int(height * SUBTITLE_BOTTOM_MARGIN_RATIO))
    y = max(24, height - bottom_margin - box_height)
    radius = min(8, padding_y)

    draw.rounded_rectangle(
        (x, y, x + box_width, y + box_height),
        radius=radius,
        fill=subtitle_style.background_rgba(),
    )
    text_x = x + (box_width - text_width) // 2
    text_y = y + (box_height - text_height) // 2 - text_bbox[1]
    draw.multiline_text(
        (text_x + 2, text_y + 2),
        text_block,
        font=font,
        fill=SHADOW_RGBA,
        spacing=line_spacing,
        align="center",
    )
    draw.multiline_text(
        (text_x, text_y),
        text_block,
        font=font,
        fill=subtitle_style.font_rgba(),
        spacing=line_spacing,
        align="center",
    )


def _fit_text(
    image_font_module: object,
    draw: object,
    text: str,
    max_width: int,
    base_font_size: int,
    minimum_font_size: int,
) -> Tuple[object, Sequence[str]]:
    for font_size in range(base_font_size, minimum_font_size - 1, -2):
        font = _load_font(image_font_module, font_size)
        lines = _wrap_text(draw, text, font, max_width)
        if len(lines) <= 2:
            return font, lines
    font = _load_font(image_font_module, minimum_font_size)
    return font, _wrap_text(draw, text, font, max_width)


def _wrap_text(draw: object, text: str, font: object, max_width: int) -> List[str]:
    paragraphs = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines: List[str] = []
    for paragraph in paragraphs:
        stripped = paragraph.strip()
        if not stripped:
            continue
        lines.extend(_wrap_paragraph(draw, stripped, font, max_width))
    return lines or [""]


def _wrap_paragraph(draw: object, text: str, font: object, max_width: int) -> List[str]:
    if re.search(r"\s", text):
        return _wrap_spaced_paragraph(draw, text, font, max_width)
    return _wrap_unspaced_text(draw, text, font, max_width)


def _wrap_spaced_paragraph(draw: object, text: str, font: object, max_width: int) -> List[str]:
    lines: List[str] = []
    current = ""
    for word in text.split():
        candidate = word if not current else f"{current} {word}"
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        if draw.textlength(word, font=font) <= max_width:
            current = word
        else:
            split_word_lines = _wrap_unspaced_text(draw, word, font, max_width)
            lines.extend(split_word_lines[:-1])
            current = split_word_lines[-1] if split_word_lines else ""
    if current:
        lines.append(current)
    return lines


def _wrap_unspaced_text(draw: object, text: str, font: object, max_width: int) -> List[str]:
    lines: List[str] = []
    current = ""
    for character in text:
        candidate = current + character
        if current and draw.textlength(candidate, font=font) > max_width:
            lines.append(current.rstrip())
            current = character.lstrip()
        else:
            current = candidate
    if current:
        lines.append(current.rstrip())
    return lines


def _load_font(image_font_module: object, font_size: int) -> object:
    for font_path in FONT_CANDIDATES:
        path = Path(font_path)
        if path.exists():
            return image_font_module.truetype(str(path), font_size)
    return image_font_module.load_default()


def _load_pillow() -> Tuple[object, object, object]:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise RuntimeError("Pillow is required to render burned subtitle overlays. Install project dependencies.") from exc
    return Image, ImageDraw, ImageFont
