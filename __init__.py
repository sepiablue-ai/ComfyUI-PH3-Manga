"""ComfyUI-PH3-Manga: layout guides and Japanese lettering for P-H3."""
from .nodes import PH3MangaBalloonGuide, PH3MangaLayout, PH3MangaLettering

NODE_CLASS_MAPPINGS = {
    "PH3MangaLayout": PH3MangaLayout,
    "PH3MangaBalloonGuide": PH3MangaBalloonGuide,
    "PH3MangaLettering": PH3MangaLettering,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "PH3MangaLayout": "P-H3 Manga · Panel Layout / コマ割り",
    "PH3MangaBalloonGuide": "P-H3 Manga · Balloon Guide / 吹き出しガイド",
    "PH3MangaLettering": "P-H3 Manga · Japanese Lettering / 日本語写植",
}
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
