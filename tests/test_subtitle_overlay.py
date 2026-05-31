import json
from pathlib import Path

from PIL import Image

from fukikae_studio.media.subtitle_overlay import SAGE_GREEN_RGBA, _wrap_paragraph, render_subtitle_overlay_images


class FixedWidthDraw:
    def textlength(self, text, font):
        return len(text)


def test_render_subtitle_overlay_images_writes_sage_green_pngs_and_manifest(tmp_path):
    output_dir = tmp_path / "overlays"

    overlays = render_subtitle_overlay_images(
        [
            {
                "id": "seg_0001",
                "source_start_ms": 760,
                "source_end_ms": 7550,
                "target_text": "ウクライナ国家反汚職局NABUは、正式な協力を要請しました",
            }
        ],
        output_dir=output_dir,
        video_size=(640, 360),
    )

    assert overlays == [
        {
            "id": "seg_0001",
            "image": output_dir / "seg_0001.png",
            "start_ms": 760,
            "end_ms": 7550,
        }
    ]
    assert (output_dir / "seg_0001.png").exists()
    manifest = json.loads((output_dir / "subtitle_overlay_manifest.json").read_text(encoding="utf-8"))
    assert manifest["style"]["box_rgba"] == list(SAGE_GREEN_RGBA)
    assert manifest["style"]["box_rgba"][3] == 255
    assert manifest["style"]["margin_bottom_ratio"] == 0.12
    assert manifest["overlays"][0]["image"] == str(output_dir / "seg_0001.png")


def test_render_subtitle_overlay_images_places_box_over_existing_lower_subtitle_band(tmp_path):
    output_dir = tmp_path / "overlays"

    render_subtitle_overlay_images(
        [
            {
                "id": "seg_0001",
                "source_start_ms": 760,
                "source_end_ms": 7550,
                "target_text": "別の資金洗浄事件の容疑者として裁判所に出廷しました",
            }
        ],
        output_dir=output_dir,
        video_size=(640, 360),
    )

    image = Image.open(output_dir / "seg_0001.png")
    alpha_bbox = image.getchannel("A").getbbox()

    assert alpha_bbox is not None
    assert alpha_bbox[3] - alpha_bbox[1] >= int(360 * 0.12)
    assert alpha_bbox[1] <= int(360 * 0.70)
    assert alpha_bbox[3] >= int(360 * 0.86)


def test_render_subtitle_overlay_images_keeps_one_line_box_tall_enough_to_cover_existing_caption(tmp_path):
    output_dir = tmp_path / "overlays"

    render_subtitle_overlay_images(
        [
            {
                "id": "seg_0001",
                "source_start_ms": 760,
                "source_end_ms": 7550,
                "target_text": "別の資金洗浄事件の容疑者として裁判所に出廷しました",
            }
        ],
        output_dir=output_dir,
        video_size=(1280, 720),
    )

    image = Image.open(output_dir / "seg_0001.png")
    alpha_bbox = image.getchannel("A").getbbox()

    assert alpha_bbox is not None
    assert alpha_bbox[3] - alpha_bbox[1] >= int(720 * 0.20)


def test_render_subtitle_overlay_images_places_portrait_box_over_existing_caption_band(tmp_path):
    output_dir = tmp_path / "overlays"

    render_subtitle_overlay_images(
        [
            {
                "id": "seg_0001",
                "source_start_ms": 7590,
                "source_end_ms": 9930,
                "target_text": "少し焼きすぎて縮んでしまいました。",
            }
        ],
        output_dir=output_dir,
        video_size=(576, 1024),
    )

    image = Image.open(output_dir / "seg_0001.png")
    alpha_bbox = image.getchannel("A").getbbox()

    assert alpha_bbox is not None
    assert alpha_bbox[1] <= int(1024 * 0.70)
    assert alpha_bbox[3] >= int(1024 * 0.86)


def test_english_subtitle_wrapping_keeps_words_intact():
    lines = _wrap_paragraph(
        FixedWidthDraw(),
        "no leak of personal information",
        font=None,
        max_width=12,
    )

    assert lines == ["no leak of", "personal", "information"]
