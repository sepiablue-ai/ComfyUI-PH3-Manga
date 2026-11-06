"""Find user-supplied or installed Japanese fonts without machine-specific paths."""
import os
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

FONT_DIRECTORY = Path(__file__).resolve().parent / "fonts"
SUFFIXES = {".ttf", ".ttc", ".otf", ".otc"}


def font_directories():
    paths = [FONT_DIRECTORY]
    if os.environ.get("PH3_MANGA_FONT_DIR"):
        paths.append(Path(os.environ["PH3_MANGA_FONT_DIR"]).expanduser())
    if os.environ.get("WINDIR"):
        paths.append(Path(os.environ["WINDIR"]) / "Fonts")
    paths.extend([
        Path("/usr/share/fonts"), Path("/usr/local/share/fonts"),
        Path.home() / ".local/share/fonts", Path.home() / ".fonts",
        Path("/System/Library/Fonts"), Path("/Library/Fonts"),
        Path.home() / "Library/Fonts",
    ])
    return paths


@lru_cache(maxsize=1)
def available_fonts():
    result = {}
    for directory in font_directories():
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.suffix.lower() in SUFFIXES:
                result.setdefault(path.name.lower(), path)
    return result


def resolve_font(selection="auto", role="kana"):
    fonts = available_fonts()
    if selection.strip().lower() != "auto":
        name = selection.strip()
        if name.lower() in fonts:
            return str(fonts[name.lower()])
        path = Path(name).expanduser()
        if path.is_file() and path.suffix.lower() in SUFFIXES:
            return str(path)
        raise ValueError(f"Font '{selection}' was not found. Add a Japanese font to this node pack's fonts folder.")
    preferred = (["yumindb.ttf", "notoserifcjk-bold.ttc", "notoserifcjk-regular.ttc", "notoserifjp-regular.ttf", "ipam.ttf"]
                 if role == "kana" else
                 ["yugothb.ttc", "notosanscjk-bold.ttc", "notosanscjk-regular.ttc", "notosansjp-regular.ttf", "ipag.ttf"])
    for name in preferred:
        if name in fonts:
            return str(fonts[name])
    for name, path in fonts.items():
        compact = name.replace("-", "").replace("_", "").replace(" ", "")
        if any(tag in compact for tag in ("cjk", "notosansjp", "notoserifjp", "hiragino", "ヒラギノ", "yumin", "yugoth", "ipaex", "ipag", "ipam")):
            return str(path)
    raise ValueError("No Japanese font found. Put Noto Sans CJK JP or Noto Serif CJK JP in the fonts folder, then restart ComfyUI.")


@lru_cache(maxsize=64)
def load_font(path, size):
    return ImageFont.truetype(str(path), max(1, int(size)))
