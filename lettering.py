"""Japanese vertical lettering and ruby layout."""
from .fonts import load_font as _font

ROTATE_CH = set("ー―－…‥〜～「」『』（）()-")  # 縦書きで90度回す
SMALL_CH = set("ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ")  # 右上へ寄せる
PUNCT_CH = set("、。，．")  # 右上へ大きく寄せる
NO_HEAD = set("、。」』）！？!?…‥ーっゃゅょァィゥェォッャュョぁぃぅぇぉ")  # 列の頭に置かない
MAX_ROWS = 7  # 1列の最大文字数


def _cells(text):
    """縦書きの1文字ずつの並び。「！？」「!?」は1マスに横並び（縦中横）。改行は列の区切り。"""
    out, i = [], 0
    while i < len(text):
        two = text[i:i + 2]
        if two in ("！？", "!?", "！！", "!!", "？！", "?!"):
            out.append(two); i += 2
        else:
            out.append(text[i]); i += 1
    return out


def _columns(text):
    cols = []
    for part in text.split("\n"):
        cells = _cells(part.strip())
        if not cells:
            continue
        n = -(-len(cells) // MAX_ROWS)
        per = -(-len(cells) // n)
        chunk = [cells[k:k + per] for k in range(0, len(cells), per)]
        for k in range(1, len(chunk)):  # 簡易禁則: 列頭の句読点・小書きは前の列へ
            while chunk[k] and chunk[k][0] in NO_HEAD:
                chunk[k - 1].append(chunk[k].pop(0))
        cols += [c for c in chunk if c]
    return cols


def ruby_spans(col, word):
    """列 col（マスの並び）の中で word が占める (先頭のマス番号, マス数) を返す。
    縦中横は2字で1マスなので、文字の位置ではなくマスの位置で数える。マスの途中で始まる・終わる一致は除く。"""
    line, starts = "".join(col), {}
    pos = 0
    for row, cell in enumerate(col):
        starts[pos] = row
        pos += len(cell)
    starts[pos] = len(col)
    spans, start = [], 0
    while (start := line.find(word, start)) >= 0:
        end = start + len(word)
        if start in starts and end in starts:
            spans.append((starts[start], starts[end] - starts[start]))
        start = end
    return spans


def _is_kana(ch):
    return all("\u3040" <= c <= "\u30ff" or c in "、。！？!?…‥ー〜～「」『』（）" for c in ch)


def _phrases(text):
    """BudouX（日本語の文節区切り）で文を文節に分ける。入っていなければ1文字ずつ。"""
    try:
        import budoux
        parser = _phrases.parser = getattr(_phrases, "parser", None) or budoux.load_default_japanese_parser()
        return [_cells(p) for p in parser.parse(text)]
    except ImportError:
        return [[c] for c in _cells(text)]


def _pack(phrases, limit):
    """文節を、1列 limit 字以内に詰めて列にする（文節の途中では区切らない。1文節が長すぎるときだけ字で切る）。"""
    cols, cur = [], []
    for ph in phrases:
        while len(ph) > limit:
            if cur:
                cols.append(cur); cur = []
            cols.append(ph[:limit]); ph = ph[limit:]
        if len(cur) + len(ph) > limit and cur:
            cols.append(cur); cur = []
        cur = cur + ph
    if cur:
        cols.append(cur)
    for k in range(1, len(cols)):  # 簡易禁則: 列頭の句読点・小書きは前の列へ
        while cols[k] and cols[k][0] in NO_HEAD:
            cols[k - 1].append(cols[k].pop(0))
    return [c for c in cols if c]


def layout_columns(text, bw, bh, fs_max, column_width=1.18):
    """枠（幅 bw・高さ bh）に入る縦書きの列と文字の大きさを決める。明示の改行はそこで必ず区切る。
    1列の字数を変えて試し、文字がいちばん大きくなる組み方を選ぶ。"""
    parts = [p.strip() for p in text.split("\n") if p.strip()]
    if len(parts) > 1:
        cols = [_cells(p) for p in parts]
        fs = min(fs_max, bw / (len(cols) * column_width), bh / max(map(len, cols)))
        return fs, cols
    best = None
    longest = max(len(_cells(p)) for p in parts)
    # 文節は途中で切らない（字を小さくして収める）。1列は最大 MAX_ROWS 字で、それより長い文節だけ字で切る
    shortest = min(max(len(ph) for p in parts for ph in _phrases(p)), MAX_ROWS)
    for limit in range(shortest, max(shortest, min(longest, MAX_ROWS)) + 1):
        cols = [c for p in parts for c in _pack(_phrases(p), limit)]
        rows = max(len(c) for c in cols)
        fs = min(fs_max, bw / (len(cols) * column_width), bh / rows)
        if best is None or fs > best[0] + 1e-6 or (abs(fs - best[0]) <= 1e-6 and len(cols) < len(best[1])):  # 同じ大きさなら列の少ない方
            best = (fs, cols)
    return best


def draw_text_in_box(page, text, box, fs, fonts, ruby=None):
    """page(PIL RGB) の box=(x0,y0,x1,y1) の中に、縦書きのセリフだけを描く（吹き出しは描かない）。
    文節で改行し（BudouX）、枠に収まる最大の大きさ（上限 fs）で、枠の中央に置く。2倍で描いて縮小する。返り値は使った文字の大きさ（px）と列。"""
    from PIL import Image as PImage, ImageDraw
    bw, bh = box[2] - box[0], box[3] - box[1]
    spacing = 1.6 if ruby else 1.18
    fs, cols = layout_columns(text, bw, bh, fs, spacing)
    rows = max(len(c) for c in cols)
    colw = fs * spacing
    tw, th = len(cols) * colw, rows * fs
    S = 2
    W, H = int(bw) + 4, int(bh) + 4
    layer = PImage.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    td = ImageDraw.Draw(layer)
    f_s = int(fs * S)
    right = (W / 2 + tw / 2) * S
    top = (H / 2 - th / 2) * S
    for i, col in enumerate(cols):
        x = right - (i + 0.5) * colw * S
        for r, ch in enumerate(col):
            y = top + (r + 0.5) * f_s
            font = _font(fonts[0] if _is_kana(ch) else fonts[1], f_s)
            if len(ch) == 2:  # 縦中横
                td.text((x, y), ch, font=_font(fonts[1], int(f_s * 0.62)), fill=(0, 0, 0, 255), anchor="mm")
            elif ch in ROTATE_CH:
                g = PImage.new("RGBA", (f_s * 2, f_s * 2), (0, 0, 0, 0))
                ImageDraw.Draw(g).text((f_s, f_s), ch, font=font, fill=(0, 0, 0, 255), anchor="mm")
                layer.alpha_composite(g.rotate(-90), (int(x - f_s), int(y - f_s)))
            elif ch in PUNCT_CH:
                # 横書きグリフの余白を除き、縦書きの仮想ボディ右上へ置く。
                glyph = PImage.new("RGBA", (f_s * 3, f_s * 3), (0, 0, 0, 0))
                ImageDraw.Draw(glyph).text((f_s, f_s), ch, font=font, fill=(0, 0, 0, 255), anchor="mm")
                ink = glyph.getchannel("A").getbbox()
                if ink:
                    layer.alpha_composite(glyph.crop(ink), (round(x + f_s * 0.12), round(y - f_s * 0.45)))
            elif ch in SMALL_CH:
                td.text((x + f_s * 0.1, y - f_s * 0.1), ch, font=font, fill=(0, 0, 0, 255), anchor="mm")
            else:
                td.text((x, y), ch, font=font, fill=(0, 0, 0, 255), anchor="mm")
    if ruby:
        rf = _font(fonts[0], max(8, round(f_s * 0.36)))
        for i, col in enumerate(cols):
            for word, reading in ruby.items():
                for row, n in ruby_spans(col, word):
                    rh = min(f_s * 0.4, n * f_s / len(reading))
                    yy = top + row * f_s + (n * f_s - len(reading) * rh) / 2
                    xx = right - (i + 0.5) * colw * S + f_s * 0.64
                    for j, ch in enumerate(reading):
                        td.text((xx, yy + (j + 0.5) * rh), ch, font=rf, fill=(0,0,0,255), anchor='mm')
    layer = layer.resize((W, H), PImage.LANCZOS)
    page.paste(layer.convert("RGB"), (int(box[0] - 2), int(box[1] - 2)), layer.getchannel("A"))
    return round(fs, 1), ["".join(c) for c in cols]
