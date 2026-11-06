// 編集画面用の座標計算。ページ全体を0〜1000とする。
export const NARRATION = '画面外・ナレーション（尾なし）';
export const clamp = (v, min = 0, max = 1000) => Math.max(min, Math.min(max, v));
export const clone = value => JSON.parse(JSON.stringify(value));
export function textBox(item, ratio) {
    if (item.text_bbox) return [...item.text_bbox];
    const [y0, x0, y1, x1] = item.bbox, dx = (x1 - x0) * (1 - ratio) / 2, dy = (y1 - y0) * (1 - ratio) / 2;
    return [y0 + dy, x0 + dx, y1 - dy, x1 - dx];
}
export function shortTail(bbox) {
    const [y0, x0, y1, x1] = bbox;
    // xとyのページ比率が違うため、実寸の短辺に対して長さを決める。
    return [(x0 + x1) / 2 + (x1 - x0) * 0.12, clamp(y1 + Math.min((x1 - x0) * 2 / 3, y1 - y0) * 0.22)];
}
export function moveItem(item, dx, dy, textOnly = false, ratio = .7) {
    const box = textOnly ? textBox(item, ratio) : item.bbox;
    dx = clamp(dx, -box[1], 1000 - box[3]); dy = clamp(dy, -box[0], 1000 - box[2]);
    const moved = [box[0] + dy, box[1] + dx, box[2] + dy, box[3] + dx];
    if (textOnly) item.text_bbox = moved;
    else {
        item.bbox = moved;
        if (item.tail) item.tail = [clamp(item.tail[0] + dx), clamp(item.tail[1] + dy)];
        if (item.text_bbox) item.text_bbox = item.text_bbox.map((v, i) => clamp(v + (i % 2 ? dx : dy)));
    }
}
export function resizeItem(item, x, y, textOnly = false, ratio = .7) {
    const box = textOnly ? textBox(item, ratio) : [...item.bbox];
    box[2] = clamp(y, box[0] + 8, 1000); box[3] = clamp(x, box[1] + 8, 1000);
    if (textOnly) item.text_bbox = box; else item.bbox = box;
}
export function newBalloon(panel, box) {
    const [x0, y0, x1, y1] = box.map(v => v * 1000);
    const w = Math.min(160, (x1 - x0) * .3), h = Math.min(180, (y1 - y0) * .6);
    const bbox = [y0 + 15, x1 - w - 15, y0 + 15 + h, x1 - 15];
    return { id: crypto.randomUUID(), panel, bbox, speaker: '人物1', text: '', tail: shortTail(bbox) };
}
export function tailPoints(item) {
    if (!item.tail || item.speaker === NARRATION) return null;
    const [y0, x0, y1, x1] = item.bbox, cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, rx = (x1 - x0) / 2, ry = (y1 - y0) / 2;
    const [tx, ty] = item.tail, angle = Math.atan2((ty - cy) / ry, (tx - cx) / rx);
    return [-.12, .12].map(a => [cx + rx * Math.cos(angle + a), cy + ry * Math.sin(angle + a)]).concat([[tx, ty]]);
}
