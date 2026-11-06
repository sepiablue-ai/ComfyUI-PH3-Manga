"""同梱コマ割りの一覧と見本画像を ComfyUI の画面へ配信する（選択画面用）。"""
import re

from .nodes import DATA, layouts

CATEGORY = {"straight": ("直線", "Straight"), "diagonal": ("斜め", "Diagonal"), "special": ("特殊", "Special")}


def position_ja(text):
    """コマ位置の英語表記のうち、よく使う形だけ日本語にする（それ以外は空 → 「Nコマ目」だけ表示）。"""
    if m := re.match(r"tier (\d+), (?:panel )?(\d+) from the right", text):
        return f"{m[1]}段目・右から{m[2]}"
    if m := re.match(r"tier (\d+), full-width", text):
        return f"{m[1]}段目・横いっぱい"
    if m := re.match(r"vertical strip (\d+) from the right", text):
        return f"縦長・右から{m[1]}"
    if m := re.match(r"wide band (\d+) from the top", text):
        return f"横長・上から{m[1]}"
    return ""


def catalog_items():
    items = []
    for row in layouts().values():
        kind = "normal" if row["id"].startswith("normal_") else row["id"].split("_")[2]
        ja, en = ("通常", "Standard") if kind == "normal" else CATEGORY.get(kind, (kind, kind))
        items.append({"id": row["id"], "name": row["name"], "name_en": row.get("name_en", row["name"]), "count": len(row["panels"]),
                      "kind": kind, "category": ja, "category_en": en,
                      "positions": [position_ja(p["position"]) for p in row["panels"]],
                      "panel_boxes": [p["bbox"] for p in row["panels"]],
                      "positions_en": [p["position"].split(", occupying")[0] for p in row["panels"]], "preview": f"/ph3_manga/preview/{row['id']}"})
    order = {"normal": 0, "straight": 1, "diagonal": 2, "special": 3}
    return sorted(items, key=lambda i: (order.get(i["kind"], 4), i["count"], i["id"]))


def register_routes(routes):
    from aiohttp import web

    @routes.get("/ph3_manga/catalog")
    async def catalog(request):
        return web.json_response({"layouts": catalog_items()})

    @routes.get("/ph3_manga/preview/{ident}")
    async def preview(request):
        ident = request.match_info["ident"]
        if not re.fullmatch(r"[A-Za-z0-9_]{1,100}", ident) or ident not in layouts():
            raise web.HTTPNotFound()
        return web.FileResponse(DATA / "layouts" / f"{ident}.webp", headers={"Content-Type": "image/webp"})

    @routes.get("/ph3_manga/layout/{ident}")
    async def layout(request):
        row = layouts().get(request.match_info["ident"])
        if row is None:
            raise web.HTTPNotFound()
        return web.json_response(row)

