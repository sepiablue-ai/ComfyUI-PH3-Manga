"""Standalone manga layout, balloon-guide and lettering nodes."""
import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFilter

from .fonts import resolve_font
from .lettering import draw_text_in_box

DATA = Path(__file__).resolve().parent / "data"
CATEGORY = "P-H3 Manga"


@lru_cache(maxsize=1)
def layouts():
    document = json.loads((DATA / "layouts.json").read_text(encoding="utf-8"))
    return {row["id"]: row for row in document["layouts"]}


def image_shape(image):
    if image.ndim != 4 or image.shape[-1] != 3 or image.shape[0] < 1:
        raise ValueError("Expected an RGB IMAGE batch [batch, height, width, 3].")
    return int(image.shape[1]), int(image.shape[2])


def normalized_box(element):
    try:
        y0, x0, y1, x1 = (float(v) for v in element["bbox"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Each element needs bbox=[ymin,xmin,ymax,xmax] in 0–1000 coordinates.") from exc
    if not all(math.isfinite(v) and 0 <= v <= 1000 for v in (y0, x0, y1, x1)) or y1 <= y0 or x1 <= x0:
        raise ValueError("Bounding boxes must have positive width and height and stay within 0–1000.")
    return y0, x0, y1, x1


class PH3MangaLayout:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"layout": (sorted(layouts()),)}, "optional": {
            "megapixels": ("FLOAT", {"default": 4.153344, "min": 0.25, "max": 8.5, "step": 0.25}),
        }}

    RETURN_TYPES = ("IMAGE", "INT", "INT", "INT", "STRING")
    RETURN_NAMES = ("page", "width", "height", "panel_count", "layout_info")
    FUNCTION = "run"
    CATEGORY = CATEGORY

    def run(self, layout, megapixels=4.153344):
        if layout not in layouts():
            raise ValueError(f"Unknown layout: {layout}")
        with Image.open(DATA / "layouts" / f"{layout}.webp") as source:
            pixels = np.asarray(source.convert("RGB"), dtype=np.float32) / 255.0
        h, w = pixels.shape[:2]
        if not math.isfinite(megapixels) or not 0.25 <= megapixels <= 8.5:
            raise ValueError("megapixels must be between 0.25 and 8.5.")
        scale = (megapixels * 1_000_000 / (w * h)) ** 0.5
        width, height = (max(32, round(d * scale / 32) * 32) for d in (w, h))
        row = layouts()[layout]
        return (torch.from_numpy(pixels.copy())[None], width, height, len(row["panels"]), json.dumps(row, ensure_ascii=False))


class PH3MangaBalloonGuide:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE",), "elements": ("ARRAY",),
            "inner_ratio": ("FLOAT", {"default": 0.70, "min": 0.3, "max": 0.9, "step": 0.01}),
            "line_width": ("INT", {"default": 2, "min": 1, "max": 8})}}

    RETURN_TYPES = ("IMAGE", "ARRAY")
    RETURN_NAMES = ("guide", "text_elements")
    FUNCTION = "run"
    CATEGORY = CATEGORY

    def run(self, image, elements, inner_ratio, line_width):
        h, w = image_shape(image)
        if not 0 < inner_ratio <= 1 or not 1 <= line_width <= 8:
            raise ValueError("inner_ratio must be in (0,1] and line_width in [1,8].")
        s = 3
        mask = Image.new("L", (w * s, h * s), 0)
        draw = ImageDraw.Draw(mask)
        texts = []
        for element in elements or []:
            y0, x0, y1, x1 = normalized_box(element)
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
            def xy(x, y):
                return x * w * s / 1000, y * h * s / 1000
            draw.ellipse((*xy(x0, y0), *xy(x1, y1)), fill=255)
            try:
                description = json.loads(element.get("desc") or "{}")
                tail = description.get("tail")
            except (ValueError, AttributeError, TypeError) as exc:
                raise ValueError('Balloon desc must be a JSON object, e.g. {"tail":[500,400]} or {}.') from exc
            if tail is not None:
                if not isinstance(tail, list) or len(tail) != 2 or not all(isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 1000 for v in tail):
                    raise ValueError("tail must be [x,y] in 0–1000 coordinates, or null.")
                tx, ty = tail
                angle = math.atan2((ty - cy) / ry, (tx - cx) / rx)
                points = [xy(cx + rx * math.cos(angle + a), cy + ry * math.sin(angle + a)) for a in (-0.12, 0.12)]
                draw.polygon([points[0], xy(tx, ty), points[1]], fill=255)
            texts.append({**element, "bbox": [cy - ry * inner_ratio, cx - rx * inner_ratio, cy + ry * inner_ratio, cx + rx * inner_ratio]})
        outer = mask.filter(ImageFilter.MaxFilter(line_width * s * 2 + 1))
        # Only the balloon masks are supersampled; the page itself is never resampled, so every pixel
        # outside the balloon outlines stays bit-identical to the input layout.
        def coverage(m):
            a = np.asarray(m.resize((w, h), Image.Resampling.BOX), dtype=np.float32) / 255
            return torch.from_numpy(a)[None, :, :, None].to(image.device, image.dtype)
        ink, fill = coverage(outer), coverage(mask)
        return image * (1 - ink) * (1 - fill) + fill, texts


class PH3MangaLettering:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE",),
            "kana_font": ("STRING", {"default": "auto", "tooltip": "auto, a font filename in fonts/, or a font file path"}),
            "kanji_font": ("STRING", {"default": "auto", "tooltip": "auto, a font filename in fonts/, or a font file path"}),
            "font_size": ("FLOAT", {"default": 0.016, "min": 0.005, "max": 0.05, "step": 0.001})},
            "optional": {"elements": ("ARRAY",), "ruby": ("STRING", {"default": "{}", "multiline": True})}}

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "info")
    FUNCTION = "run"
    CATEGORY = CATEGORY

    def run(self, image, kana_font, kanji_font, font_size, elements=None, ruby="{}"):
        h, w = image_shape(image)
        readings = parse_ruby(ruby)
        items = text_items(elements)
        if not items:
            return image, "[]"
        fonts, fs = lettering_style(h, kana_font, kanji_font, font_size)
        result, info = [], []
        for frame in image:
            page = Image.fromarray((frame.cpu().numpy() * 255).clip(0, 255).astype(np.uint8))
            info = letter_page(page, items, fonts, fs, readings)
            result.append(torch.from_numpy(np.asarray(page, dtype=np.float32) / 255))
        return torch.stack(result), json.dumps(info, ensure_ascii=False, indent=1)


def parse_ruby(ruby):
    try:
        readings = json.loads(ruby)
    except (ValueError, TypeError) as exc:
        raise ValueError('ruby must be a JSON object such as {"雨":"あめ"}.') from exc
    if not isinstance(readings, dict) or any(not isinstance(k, str) or not k or not isinstance(v, str) or not v for k, v in readings.items()):
        raise ValueError("Ruby entries must map non-empty words to non-empty readings.")
    return readings


def text_items(elements):
    return [e for e in (elements or []) if isinstance(e, dict) and e.get("type", "text") == "text" and isinstance(e.get("text"), str) and e["text"].strip()]


def lettering_style(h, kana_font, kanji_font, font_size):
    if not isinstance(font_size, (int, float)) or not math.isfinite(font_size) or not 0.005 <= font_size <= 0.05:
        raise ValueError("font_size must be between 0.005 and 0.05.")
    return (resolve_font(kana_font, "kana"), resolve_font(kanji_font, "kanji")), max(8, round(h * font_size))


def letter_page(page, items, fonts, fs, readings):
    """page（PIL画像）に写植する。ノードの出力と編集画面の見本は、どちらもこの関数で描く。"""
    w, h = page.size
    info = []
    for element in items:
        y0, x0, y1, x1 = normalized_box(element)
        box = x0 * w / 1000, y0 * h / 1000, x1 * w / 1000, y1 * h / 1000
        if min(box[2] - box[0], box[3] - box[1]) < 4:
            raise ValueError("A text box is too small to render; enlarge it in Create Bounding Boxes.")
        used, columns = draw_text_in_box(page, element["text"], box, fs, fonts, readings)
        info.append({"text": element["text"], "box_px": [round(v) for v in box], "font_px": used, "columns": columns})
    return info
