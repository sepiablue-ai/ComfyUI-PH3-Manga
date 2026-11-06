"""ComfyUI-PH3-Manga: layout guides and Japanese lettering for P-H3."""
from .nodes import PH3MangaBalloonGuide, PH3MangaLayout, PH3MangaLettering
from .page import PH3MangaPage, PH3MangaPanel

NODE_CLASS_MAPPINGS = {
    "PH3MangaPage": PH3MangaPage,
    "PH3MangaPanel": PH3MangaPanel,
    "PH3MangaLayout": PH3MangaLayout,
    "PH3MangaBalloonGuide": PH3MangaBalloonGuide,
    "PH3MangaLettering": PH3MangaLettering,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "PH3MangaPage": "P-H3 Manga · Page / 漫画ページ（コマ割り・人物・コマ）",
    "PH3MangaPanel": "P-H3 Manga · Panel content / コマの内容",
    "PH3MangaLayout": "P-H3 Manga · Panel Layout / コマ割り",
    "PH3MangaBalloonGuide": "P-H3 Manga · Balloon Guide / 吹き出しガイド",
    "PH3MangaLettering": "P-H3 Manga · Japanese Lettering / 日本語写植",
}
WEB_DIRECTORY = "./web"
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]

try:
    from server import PromptServer
except ModuleNotFoundError as error:
    if error.name != "server":
        raise
else:
    if not getattr(PromptServer.instance, "_ph3_manga_routes", False):
        from .picker_api import register_routes
        register_routes(PromptServer.instance.routes)
        PromptServer.instance._ph3_manga_routes = True
