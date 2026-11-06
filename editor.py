"""一つの編集データから入力ガイド・話者の指示・写植領域を作る。"""
import json
import re

import numpy as np
import torch
from PIL import Image

from .nodes import CATEGORY, DATA, PH3MangaBalloonGuide, normalized_box
from .page import ACTORS, NARRATION, SLOTS, compile_page, find_layout, layout_names

PAGE_W, PAGE_H = 1664, 2496  # 生成・写植するページの寸法

# P-H3のテキストエンコーダー（Qwen3-VL 4B）で日本語の場面を英訳する。
# P-H3用の分割処理は会話形式のテンプレートを付けないため、ここで付ける。
TRANSLATE_PROMPT = ("<|im_start|>user\nTranslate the following Japanese description of one manga panel into natural English "
                    "for an image generation prompt. Translate every detail faithfully; do not add or omit anything. "
                    "Keep the words 人物1, 人物2 and 人物3 exactly as they are. Output only the English translation.\n\n"
                    "{text}<|im_end|>\n<|im_start|>assistant\n")
JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uff66-\uff9f]")  # かな・漢字・半角カナ


def needs_translation(text):
    return bool(JAPANESE.search(re.sub(r"人物[1-3１-３]", "", text)))


def translate_scene(clip, text):
    """日本語を含む場面だけを英訳する（サンプリングなしで、同じ入力なら同じ訳）。"""
    if clip is None or not needs_translation(text):
        return text
    ids = clip.generate(clip.tokenize(TRANSLATE_PROMPT.format(text=text)), do_sample=False, max_length=512,
                        temperature=1.0, top_k=50, top_p=1.0, min_p=0.0, repetition_penalty=1.0, seed=None)
    out = clip.decode(ids).split("<|im_end|>")[0].strip()
    if not out or needs_translation(out):
        raise ValueError(f"場面の英訳に失敗しました。英語で書き直すか、文を短くしてください。\n場面: {text}\n訳: {out}")
    return out


def editor_data(layout, value):
    row = find_layout(layout)
    items = json.loads(value)
    if not isinstance(items, list):
        raise ValueError("吹き出しの編集データは配列にしてください。")
    seen = set()
    for item in items:
        normalized_box(item)
        if not isinstance(item.get("id"), str) or not item["id"] or item["id"] in seen:
            raise ValueError("吹き出しの識別番号が空、または重複しています。")
        seen.add(item["id"])
        if type(item.get("panel")) is not int or not 1 <= item["panel"] <= len(row["panels"]):
            raise ValueError("吹き出しのコマ番号がコマ割りと一致しません。")
        if item.get("speaker") not in [*SLOTS, NARRATION]:
            raise ValueError("吹き出しの話者を選んでください。")
        if not isinstance(item.get("text"), str):
            raise ValueError("セリフは文字列にしてください。")
        if item.get("text_bbox") is not None:
            normalized_box({"bbox": item["text_bbox"]})
    return row, items


def balloon_elements(items):
    return [{"bbox": i["bbox"], "text": i["text"], "type": "text",
             "desc": json.dumps({"tail": None if i["speaker"] == NARRATION else i.get("tail")})} for i in items]


def text_elements(items, ratio):
    """写植に渡す文字領域。指定がなければ吹き出しの内側（PH3MangaBalloonGuide と同じ式）。"""
    texts = []
    for element in balloon_elements(items):
        y0, x0, y1, x1 = element["bbox"]
        cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
        texts.append({**element, "bbox": [cy - ry * ratio, cx - rx * ratio, cy + ry * ratio, cx + rx * ratio]})
    for item, text in zip(items, texts):
        if item.get("text_bbox") is not None:
            text["bbox"] = list(item["text_bbox"])
    return texts


def lettering_preview(layout, value, ratio, kana_font, kanji_font, font_size, ruby):
    """編集画面の見本用に、写植ノードと同じ処理で文字だけを透明PNGへ描く。"""
    import io
    from .nodes import letter_page, lettering_style, parse_ruby, text_items
    if not isinstance(ratio, (int, float)) or not 0.3 <= ratio <= 0.9:
        raise ValueError("文字領域の比率は0.3〜0.9にしてください。")
    _, items = editor_data(layout, value)
    readings = parse_ruby(ruby)
    page = Image.new("RGBA", (PAGE_W, PAGE_H), (0, 0, 0, 0))
    targets = text_items(text_elements(items, ratio))
    info = []
    if targets:
        fonts, fs = lettering_style(PAGE_H, kana_font, kanji_font, font_size)
        info = letter_page(page, targets, fonts, fs, readings)
    buffer = io.BytesIO()
    page.save(buffer, format="PNG")
    return buffer.getvalue(), info


class PH3MangaScene:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "場面": ("STRING", {"multiline": True, "default": "", "tooltip": "場面を英語か日本語で（日本語は「漫画の場面と参照画像」ノードにテキストエンコーダーをつなぐと英訳されます）。参照する人物は「人物1」または「Character 1」（Person 1・character1 も可）と書きます。セリフと話者は吹き出し編集画面で指定します。"}),
            "登場人物": (list(ACTORS),),
        }}

    RETURN_TYPES = ("PH3_MANGA_PANEL",)
    RETURN_NAMES = ("コマ",)
    FUNCTION = "build"
    CATEGORY = CATEGORY

    def build(self, 場面, 登場人物):
        if not 場面.strip():
            raise ValueError("コマの場面を入力してください。")
        return ({"scene": 場面.strip(), "actors": ACTORS[登場人物], "lines": []},)


class PH3MangaBalloonEditor:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "コマ割り": (layout_names(),),
            "編集データ": ("STRING", {"default": "[]", "multiline": True}),
            "文字領域の比率": ("FLOAT", {"default": 0.70, "min": 0.3, "max": 0.9, "step": 0.01}),
            "線の太さ": ("INT", {"default": 2, "min": 1, "max": 8}),
        }}

    RETURN_TYPES = ("IMAGE", "INT", "INT", "STRING", "ARRAY")
    RETURN_NAMES = ("空吹き出しガイド", "width", "height", "構成と話者", "セリフと文字領域")
    FUNCTION = "build"
    CATEGORY = CATEGORY
    DESCRIPTION = "生成前のセリフ・話者・吹き出し・尻尾を一か所で編集します。生成済みページの文字だけ直す場合は、写植専用ワークフローを使用します。"

    def build(self, コマ割り, 編集データ, 文字領域の比率, 線の太さ):
        row, items = editor_data(コマ割り, 編集データ)
        with Image.open(DATA / "layouts" / f"{row['id']}.webp") as source:
            page = torch.from_numpy(np.asarray(source.convert("RGB"), dtype=np.float32) / 255)[None]
        guide, _ = PH3MangaBalloonGuide().run(page, balloon_elements(items), 文字領域の比率, 線の太さ)
        texts = text_elements(items, 文字領域の比率)
        # 本文・文字領域は生成の指示に含めない。
        plan = {"layout": row["id"], "balloons": [
            {k: i.get(k) for k in ("id", "panel", "speaker", "bbox", "tail")} for i in items]}
        return guide, PAGE_W, PAGE_H, json.dumps(plan, ensure_ascii=False), texts


class PH3MangaStory:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "構成と話者": ("STRING", {"forceInput": True}), "人物1": ("IMAGE",),
            "コマ1": ("PH3_MANGA_PANEL",), "コマ2": ("PH3_MANGA_PANEL",),
        }, "optional": {
            "人物2": ("IMAGE",), "人物3": ("IMAGE",),
            **{f"コマ{i}": ("PH3_MANGA_PANEL",) for i in (3, 4, 5, 6)},
            "左から埋める癖を補正": ("BOOLEAN", {"default": True}),
            "テキストエンコーダー": ("CLIP", {"tooltip": "P-H3のテキストエンコーダーをつなぐと、日本語で書いた場面を英訳してからP-H3に渡します。訳は「P-H3の指示文」で確認できます。"}),
        }}

    RETURN_TYPES = ("STRING", "IMAGE", "IMAGE", "IMAGE")
    RETURN_NAMES = ("P-H3の指示文", "参照1", "参照2", "参照3")
    FUNCTION = "build"
    CATEGORY = CATEGORY

    def build(self, **kw):
        plan = json.loads(kw["構成と話者"])
        row = find_layout(plan["layout"])
        count = len(row["panels"])
        if {i for i in range(1, 7) if kw.get(f"コマ{i}") is not None} != set(range(1, count + 1)):
            raise ValueError(f"このコマ割りは{count}コマです。コマ1〜{count}だけに場面ノードをつないでください。")
        images = {s: kw.get(s) for s in SLOTS}
        if images["人物3"] is not None and images["人物2"] is None:
            raise ValueError("人物3を使う場合は人物2の参照画像もつないでください。")
        present = [s for s in SLOTS if images[s] is not None]
        panels = []
        for n in range(1, count + 1):
            p = kw[f"コマ{n}"]
            if any(s not in present for s in p["actors"]):
                raise ValueError(f"{n}コマ目の登場人物の参照画像が足りません。")
            # 同じコマ内は編集画面の一覧の順（追加順）で対応付ける。
            balloons = [b for b in plan["balloons"] if b["panel"] == n]
            for b in balloons:
                if b["speaker"] != NARRATION and b["speaker"] not in p["actors"]:
                    raise ValueError(f"{n}コマ目の話者「{b['speaker']}」を、そのコマの登場人物に入れてください。")
            p = {**p, "scene": translate_scene(kw.get("テキストエンコーダー"), p["scene"])}
            panels.append({**p, "lines": [{"speaker": b["speaker"], "text": ""} for b in balloons]})
        prompt, _ = compile_page(row, present, panels, kw.get("左から埋める癖を補正", True), plan["balloons"])
        return prompt, images["人物1"], images["人物2"], images["人物3"]

