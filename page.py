"""コマ割り・人物（最大3人）・コマごとの内容から、P-H3 の指示文と吹き出しの初期配置を作るノード。
入力の形は ComfyUI-MossPanelDataset（コマの内容ノードを各コマへつなぐ）にそろえている。
セリフは P-H3 には渡さず（文字は描かせない）、吹き出しの初期配置と写植に使う。"""
import json
import re

import numpy as np
import torch
from PIL import Image

from .lettering import MAX_ROWS, layout_columns
from .nodes import CATEGORY, DATA, layouts

SLOTS = ["人物1", "人物2", "人物3"]
ACTORS = {
    "人物1のみ": ["人物1"], "人物2のみ": ["人物2"], "人物1と人物2": ["人物1", "人物2"], "人物なし": [],
    "人物3のみ": ["人物3"], "人物1と人物3": ["人物1", "人物3"], "人物2と人物3": ["人物2", "人物3"],
    "人物1と人物2と人物3": SLOTS.copy(),
}
NARRATION = "画面外・ナレーション（尾なし）"
SPEAKERS = ["セリフなし", "人物1", "人物2", "人物3", NARRATION]
GUIDE_W, GUIDE_H = 1024, 1536  # 同梱コマ割り画像の大きさ。吹き出しの初期配置はこの座標で返す
GUIDE_FONT = 0.018  # 写植の文字の大きさ（ページ高さ比）の初期値。吹き出しの大きさの見積もりに使う
INNER = 0.70  # 吹き出しガイドの inner_ratio の初期値


def both(ja, en):
    return f"{ja}\n{en}"


def layout_names():
    return [row["name"] for row in sorted(layouts().values(), key=lambda r: (len(r["panels"]), r["id"]))]


def find_layout(value):
    for row in layouts().values():
        if value in (row["id"], row["name"], row.get("name_en")):
            return row
    raise ValueError(both(f"コマ割り「{value}」が見つかりません。", f'Layout "{value}" was not found.'))


class PH3MangaPanel:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "場面": ("STRING", {"multiline": True, "default": "",
                              "tooltip": "このコマの場面を英語で。人物は「人物1」または「Character 1」（Person 1・character1 も可）と書くと、参照画像の番号に置き換わります。吹き出しのことは書かなくてかまいません。"}),
            "登場人物": (list(ACTORS),),
            "話者1": (SPEAKERS,), "セリフ1": ("STRING", {"multiline": True, "default": ""}),
            "話者2": (SPEAKERS,), "セリフ2": ("STRING", {"multiline": True, "default": ""}),
        }, "optional": {
            "話者3": (SPEAKERS, {"default": "セリフなし"}), "セリフ3": ("STRING", {"multiline": True, "default": ""}),
        }}

    RETURN_TYPES = ("PH3_MANGA_PANEL",)
    RETURN_NAMES = ("コマ",)
    FUNCTION = "build"
    CATEGORY = CATEGORY
    DESCRIPTION = "1コマ分の場面・登場人物・セリフ。「漫画ページ」ノードのコマ1〜6へつなぎます。"

    def build(self, **kw):
        scene = kw["場面"].strip()
        if not scene:
            raise ValueError(both("「場面」が空です。このコマの場面を英語で入力してください。", '"場面" (scene) is empty. Describe this panel in English.'))
        actors = ACTORS[kw["登場人物"]]
        lines = []
        for i in (1, 2, 3):
            speaker, text = kw.get(f"話者{i}", "セリフなし"), kw.get(f"セリフ{i}", "")
            if speaker == "セリフなし":
                if text.strip():
                    raise ValueError(both(f"「セリフ{i}」に本文がありますが、「話者{i}」が「セリフなし」です。話す人物を選ぶか、セリフ{i}を空にしてください。",
                                          f'Line {i} has text but speaker {i} is "セリフなし" (no dialogue).'))
                continue
            if not text.strip():
                raise ValueError(both(f"「話者{i}」を選んでいますが、「セリフ{i}」が空です。", f"Speaker {i} is set but line {i} is empty."))
            if speaker != NARRATION and speaker not in actors:
                raise ValueError(both(f"「話者{i}」の{speaker}は、このコマの登場人物（{kw['登場人物']}）にいません。登場人物に入れるか、話者を変えてください。",
                                      f"Speaker {i} ({speaker}) is not among this panel's characters."))
            lines.append({"speaker": speaker, "text": text.strip()})
        return ({"scene": scene, "actors": actors, "lines": lines},)


def picture_labels(present):
    """人物スロット → 「the character from <Picture N>」。<Picture 1> はコマ割りのガイド。"""
    return {slot: f"the character from <Picture {n}>" for n, slot in enumerate(present, 2)}


def scene_text(scene, labels):
    """場面の人物名を参照画像の番号に置き換える。「人物1」「人物１」「Character 1」「character1」「Person 1」のどれでも書ける。"""
    for slot, label in labels.items():
        n = slot[-1]
        wide = chr(ord(n) + 0xFEE0)  # 全角数字
        scene = re.sub(rf"人物[{n}{wide}](?![0-9０-９])|(?<![A-Za-z])(?:character|person)[ _-]?{n}(?![0-9])", label, scene, flags=re.IGNORECASE)
    return scene


def place_balloons(panel_box, lines):
    """1コマ分の吹き出しの初期配置（ガイド座標の px）。右から左へ読む順に、コマの上側へ少しずつずらして並べる。
    大きさはセリフの列数・字数から見積もる（写植は枠に合わせて縮むので、ここは目安）。"""
    x0, y0, x1, y1 = panel_box[0] * GUIDE_W, panel_box[1] * GUIDE_H, panel_box[2] * GUIDE_W, panel_box[3] * GUIDE_H
    pw, ph = x1 - x0, y1 - y0
    fs = GUIDE_FONT * GUIDE_H
    pad = fs * 0.6
    text_h = max(fs, (ph * 0.62 - pad) * INNER)  # 吹き出しの高さはコマの62%まで。入らなければ列を増やす
    sizes = []
    for line in lines:
        size, cols = layout_columns(line["text"], 1e6, text_h, fs)
        rows = min(max(map(len, cols)), MAX_ROWS)
        sizes.append([len(cols) * size * 1.18 / INNER + pad, rows * size / INNER + pad])
    if not sizes:
        return []
    margin, gap = pw * 0.04, pw * 0.03
    scale = min(1.0, (pw - 2 * margin - gap * (len(sizes) - 1)) / sum(w for w, _ in sizes))
    n = len(sizes)
    out, right = [], x1 - margin
    for k, (line, (w, h)) in enumerate(zip(lines, sizes)):
        w, h = w * scale, h * scale
        # コマの幅を n 等分した枠の中央に置く（2つなら右端寄りと左端寄り）。前の吹き出しとは重ねない
        slot_cx = x1 - margin - (pw - 2 * margin) * (k + 0.5) / n if n > 1 else x1 - margin - w / 2
        x = min(slot_cx - w / 2, right - w)
        x = max(x, x0 + margin)
        y = y0 + ph * 0.05 + ph * 0.06 * k
        right = x - gap
        tail = None
        if line["speaker"] != NARRATION:  # 尾は下へ短く、少しコマの中央寄りへ
            tx = x + w / 2 + (pw * 0.03 if x + w / 2 < x0 + pw / 2 else -pw * 0.03)
            ty = min(y + h + h * 0.18, y1 - ph * 0.04)
            tail = [round(tx / GUIDE_W * 1000), round(ty / GUIDE_H * 1000)]
        out.append({"x": round(x), "y": round(y), "width": round(w), "height": round(h),
                    "metadata": {"type": "text", "text": line["text"], "desc": json.dumps({"tail": tail}), "palette": []}})
    return out


TEMPLATE = """subject_definitions:
<Picture 1> is the source manga layout with exactly {panels} panels and {balloons} empty white speech balloons.
{pictures}
summary:
[keyframe completion] Fill the {panels} panels with a finished monochrome Japanese manga story. Retain the panel frames and all {balloons} empty balloons.
retention_analysis:
<Picture 1>: partially_preserved - keep the panel borders, white margins and all {balloons} blank balloons with their positions, sizes and tails.
{retention}
detailed_description:
Strictly black, white and gray ink manga with screentones. Read panels from right to left, top to bottom.
{body}
Draw around and behind the existing empty white balloons. Keep every balloon blank and in place. Do not add lettering, captions, sound effects, page numbers or extra balloons. Nothing crosses the panel frames. A static single page.
overall_soundscape:
N/A
non_diegetic_music:
N/A"""


def left_to_right_order(row):
    """コマ番号（右から読む順）を、段ごとに左から数えた順に並べたもの。段は縦の範囲が半分以上重なるコマどうし。"""
    boxes = [p["bbox"] for p in row["panels"]]
    tiers = []
    for i in sorted(range(len(boxes)), key=lambda i: (boxes[i][1] + boxes[i][3]) / 2):
        y0, y1 = boxes[i][1], boxes[i][3]
        for tier in tiers:
            t0, t1 = min(boxes[j][1] for j in tier), max(boxes[j][3] for j in tier)
            if min(y1, t1) - max(y0, t0) > 0.5 * min(y1 - y0, t1 - t0):
                tier.append(i); break
        else:
            tiers.append([i])
    return [i for tier in tiers for i in sorted(tier, key=lambda i: boxes[i][0])]


def geometry_contract(row):
    boxes = [p["bbox"] for p in row["panels"]]
    if len(boxes) == 3 and abs(boxes[0][1]-boxes[1][1]) < .02 and abs(boxes[0][3]-boxes[1][3]) < .02 and boxes[2][1] > boxes[0][1]+.2:
        x = round((min(boxes[0][2],boxes[1][2])+max(boxes[0][0],boxes[1][0]))*500)
        y = round((max(boxes[0][3],boxes[1][3])+boxes[2][1])*500)
        # 通常03は中央の余白を含めて x=500, y=500。
        x = round(x/10)*10; y = round(y/10)*10
        return (f"MANDATORY PAGE GEOMETRY: Exactly TWO horizontal tiers: the TOP tier contains TWO tall panels SIDE BY SIDE separated by a vertical border at x={x}, and the BOTTOM tier contains ONE full-width panel. The horizontal divider is at y={y}. Coordinates are on a page scale 0-1000. DO NOT draw three stacked full-width horizontal strips. Copy the panel borders from <Picture 1> exactly.")
    rectangles = []
    for i, b in enumerate(boxes, 1):
        x0,y0,x1,y1 = (round(v*1000) for v in b)
        rectangles.append(f"Panel region {i}: left={x0}, top={y0}, right={x1}, bottom={y1}.")
    return "MANDATORY PAGE GEOMETRY: Copy the panel borders from <Picture 1> exactly. Rectangles use page coordinates 0-1000. Adjacent rectangles with the same top are SIDE BY SIDE. Never rearrange the panels into equal horizontal strips. " + " ".join(rectangles)


def compile_page(row, present, panels, ltr_order=True, edited_balloons=None):
    labels = picture_labels(present)
    contents, balloons = [], []
    for i, (spec, panel) in enumerate(zip(row["panels"], panels), 1):
        placed = (place_balloons(spec["bbox"], panel["lines"]) if edited_balloons is None
                  else [b for b in edited_balloons if b["panel"] == i])
        balloons += placed
        who = [labels[s] for s in panel["actors"]]
        cast = (f" Characters: {', '.join(who)}." if who else " No people are visible.")
        if placed:
            order = "; ".join("narration (tailless)" if l["speaker"] == NARRATION else f"spoken by {labels[l['speaker']]}" for l in panel["lines"])
            talk = f" Keep its {len(placed)} empty balloon{'s' if len(placed) > 1 else ''}."
            if edited_balloons is None:
                talk += f" From right to left: {order}."
            else:
                for b in placed:
                    y0, x0, y1, x1 = b["bbox"]
                    speaker = "off-panel narration (tailless)" if b["speaker"] == NARRATION else labels[b["speaker"]]
                    talk += f" The balloon centered at page coordinates ({(x0+x1)/2:.1f}, {(y0+y1)/2:.1f}) on a 0-1000 scale belongs to {speaker}."
            if any(l["speaker"] != NARRATION for l in panel["lines"]):
                talk += " Each speaker is drawn below their own balloon, which points to them with its tail."
        else:
            talk = " There is no balloon in this panel."
        contents.append(f"{scene_text(panel['scene'], labels)}{cast}{talk}")
    # P-H3 は k 番目の説明を「段ごとに左から数えて k 番目のコマ」に描く。見出し（番号と位置の言葉）は番号順のまま、
    # 中身だけを左から数えた順に並べ替えて、右から読む順のコマへ正しく入るようにする（ltr_order）。
    order = left_to_right_order(row) if ltr_order else list(range(len(panels)))
    body = [f"Panel {i} ({spec['position']}): {contents[j]}" for i, (spec, j) in enumerate(zip(row["panels"], order), 1)]
    pictures = "\n".join(f"<Picture {n}> is the reference image of character {s[-1]}." for n, s in enumerate(present, 2))
    retention = "\n".join(f"<Picture {n}>: attribute_transfer - character {s[-1]}'s face, hairstyle and clothing." for n, s in enumerate(present, 2))
    prompt = geometry_contract(row) + "\n" + TEMPLATE.format(panels=len(panels), balloons=len(balloons), pictures=pictures, retention=retention, body="\n".join(body))
    return prompt, balloons


class PH3MangaPage:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "コマ割り": (layout_names(), {"tooltip": "「画像からコマ割りを選ぶ」ボタンで見本から選べます。選ぶとコマの内容ノードが自動で増減します。"}),
            "人物1": ("IMAGE", {"tooltip": "人物1の参照画像（<Picture 2> になります）"}),
            "コマ1": ("PH3_MANGA_PANEL",), "コマ2": ("PH3_MANGA_PANEL",),
        }, "optional": {
            "人物2": ("IMAGE",), "人物3": ("IMAGE",),
            **{f"コマ{i}": ("PH3_MANGA_PANEL",) for i in (3, 4, 5, 6)},
            "左から埋める癖を補正": ("BOOLEAN", {"default": True, "tooltip": "P-H3 は説明を段ごとに左のコマから描くため、同じ段に複数のコマがあると左右が入れ替わります。オンにすると、見出しはそのまま中身だけ並べ替えて渡します。"}),
        }}

    RETURN_TYPES = ("IMAGE", "INT", "INT", "STRING", "STRING", "IMAGE", "IMAGE", "IMAGE")
    RETURN_NAMES = ("コマ割り画像", "width", "height", "P-H3の指示文", "吹き出しの初期配置", "参照1", "参照2", "参照3")
    FUNCTION = "build"
    CATEGORY = CATEGORY
    DESCRIPTION = "コマ割り・人物（最大3人）・コマの内容から、P-H3 の指示文と、吹き出しの初期配置（Create Bounding Boxes 用）を作ります。"

    def build(self, **kw):
        row = find_layout(kw["コマ割り"])
        count = len(row["panels"])
        supplied = {i for i in range(1, 7) if kw.get(f"コマ{i}") is not None}
        if supplied != set(range(1, count + 1)):
            raise ValueError(both(f"選んだコマ割りは{count}コマです。コマ1〜コマ{count}に「コマの内容」を1つずつつなぎ、それ以外は外してください。",
                                  f"The layout has {count} panels. Connect panel content to panel 1..{count} only."))
        images = {s: kw.get(s) for s in SLOTS}
        if images["人物3"] is not None and images["人物2"] is None:
            raise ValueError(both("人物3を使うときは人物2の画像もつないでください（参照画像の番号を詰めるため）。", "Connect character 2 before character 3."))
        present = [s for s in SLOTS if images[s] is not None]
        panels = [kw[f"コマ{i}"] for i in range(1, count + 1)]
        for i, p in enumerate(panels, 1):
            missing = [s for s in p["actors"] if s not in present]
            if missing:
                raise ValueError(both(f"{i}コマ目の登場人物に{missing[0]}がいますが、{missing[0]}の画像がつながっていません。",
                                      f"Panel {i} uses {missing[0]}, but its image is not connected."))
        prompt, balloons = compile_page(row, present, panels, kw.get("左から埋める癖を補正", True))
        with Image.open(DATA / "layouts" / f"{row['id']}.webp") as source:
            page = torch.from_numpy(np.asarray(source.convert("RGB"), dtype=np.float32) / 255.0)[None]
        width, height = (round(d * 1.625 / 32) * 32 for d in (GUIDE_W, GUIDE_H))  # 1664×2496（約4.15MP）
        return (page, width, height, prompt, json.dumps(balloons, ensure_ascii=False),
                images["人物1"], images["人物2"], images["人物3"])
