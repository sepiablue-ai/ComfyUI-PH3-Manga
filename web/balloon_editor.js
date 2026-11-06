import { app } from '../../scripts/app.js';
import { api } from '../../scripts/api.js';
import { NARRATION, clamp, clone, textBox, shortTail, moveItem, resizeItem, newBalloon, tailPoints } from './balloon_geometry.js';
import { loadPreview } from './image_preview.js';

const EDITOR = 'PH3MangaBalloonEditor';
const widget = (n, name) => n.widgets?.find(w => w.name === name);
const el = (tag, text) => { const n = document.createElement(tag); if (text) n.textContent = text; return n; };
const data = node => JSON.parse(widget(node, '編集データ').value || '[]');
function save(node, items) { widget(node, '編集データ').value = JSON.stringify(items); node.graph?.setDirtyCanvas?.(true, true); }
function hideWidget(w) {
    if (!w) return;
    w.type = 'hidden'; w.computeSize = () => [0, -4];
    if (w.inputEl) w.inputEl.style.display = 'none';
}
let catalogPromise;
function getCatalog() {
    return catalogPromise ??= api.fetchApi('/ph3_manga/catalog').then(response => {
        if (!response.ok) throw Error('コマ割り一覧を取得できません。');
        return response.json();
    }).then(value => value.layouts).catch(error => { catalogPromise = null; throw error; });
}

const LETTERING = 'PH3MangaLettering', LETTERING_DEFAULTS = {kana_font:'auto', kanji_font:'auto', font_size:0.016, ruby:'{}'};
// 見本の文字は、編集ノードの出力をつないだ写植ノードの設定で描く（つないでいなければ写植ノードの初期値）。
function letteringSettings(node) {
    const graph = node.graph, links = graph?.links;
    const linkOf = id => { const l = links?.get?.(id) ?? links?.[id]; return Array.isArray(l) ? {origin_id:l[1]} : l; };
    const target = (graph?._nodes ?? graph?.nodes ?? []).find(n => n.type === LETTERING && n.inputs?.some(input =>
        input.link != null && String(linkOf(input.link)?.origin_id) === String(node.id)));
    if (!target) return {settings:{...LETTERING_DEFAULTS}, connected:false};
    const settings = {};
    for (const [name, fallback] of Object.entries(LETTERING_DEFAULTS)) settings[name] = widget(target, name)?.value ?? fallback;
    return {settings, connected:true};
}

function styles() {
    if (document.getElementById('ph3-balloon-style')) return;
    const s = el('style'); s.id = 'ph3-balloon-style';
    s.textContent = `.ph3b{width:min(1260px,96vw);max-width:96vw;height:92vh;max-height:94vh;padding:16px;border:1px solid #64748b;border-radius:10px;background:#f1f5f9;color:#172033;font:14px/1.6 system-ui;box-sizing:border-box}.ph3b::backdrop{background:#0009}.ph3b h2{margin:0;font-size:20px}.ph3b button,.ph3b select,.ph3b textarea{font:inherit;color:#172033;background:white;border:1px solid #94a3b8;border-radius:5px;padding:5px}.ph3b button{cursor:pointer}.ph3b-head,.ph3b-tools{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:8px}.ph3b-body{display:grid;grid-template-columns:minmax(260px,1fr) 330px;gap:16px;height:calc(100% - 138px)}.ph3b-stage{overflow:auto;background:#cbd5e1;display:flex;justify-content:center;align-items:flex-start}.ph3b canvas{width:100%;max-width:650px;height:auto;touch-action:none;display:block;background:white}.ph3b-side{overflow:auto;display:flex;flex-direction:column;gap:10px}.ph3b-side>*{flex-shrink:0}.ph3b-side label{display:flex;flex-direction:column;gap:3px}.ph3b-list{max-height:160px;overflow:auto;display:flex;flex-direction:column;gap:3px}.ph3b-list button{text-align:left}.ph3b-list button[aria-pressed=true]{background:#dbeafe;border-color:#2563eb}.ph3b-side textarea{height:110px;resize:vertical}.ph3b-hint{margin:4px 0;color:#475569}.ph3b-status{font-weight:600;color:#9a3412;min-height:24px}.ph3b-thumb{width:100%;height:230px;object-fit:contain;background:#eee}.ph3b-empty{color:#64748b}@media(max-width:760px){.ph3b-body{grid-template-columns:1fr 250px}}`;
    document.head.append(s);
}

async function openEditor(node) {
    styles();
    let catalog;
    try { catalog = await getCatalog(); }
    catch (error) { alert(error.message); return; }
    const selectedLayout = widget(node, 'コマ割り').value;
    const layout = catalog.find(r => [r.id, r.name, r.name_en].includes(selectedLayout));
    if (!layout) { alert('コマ割りが見つかりません。'); return; }
    // 変更はダイアログ内で保持し、「変更を保存」でノードへ反映する。
    let items = clone(data(node)), selected = items[0]?.id, background, activeDrag;
    const ratio = widget(node, '文字領域の比率').value;
    const dialog = el('dialog'); dialog.className = 'ph3b';
    const header = el('div'); header.className = 'ph3b-head'; header.append(el('h2', '吹き出し・セリフ・尻尾の編集'));
    const commit = el('button', '変更を保存して閉じる'), cancel = el('button', 'キャンセル');
    commit.onclick = () => { save(node, items); node._ph3Refresh?.(); dialog.close(); };
    cancel.onclick = () => dialog.close(); header.append(commit, cancel);
    const tools = el('div'); tools.className = 'ph3b-tools';
    const mode = el('select'); for (const text of ['吹き出しと尻尾', '文字領域']) { const o = el('option', text); mode.append(o); }
    const status = el('p'); status.className = 'ph3b-status'; tools.append(el('span', '編集対象'), mode);
    const hint = el('p', '吹き出し内をドラッグすると移動、右下の□で拡大縮小、青い●で尻尾の先端を動かせます。'); hint.className = 'ph3b-hint';
    const body = el('div'); body.className = 'ph3b-body'; const stage = el('div'); stage.className = 'ph3b-stage';
    const canvas = el('canvas'); canvas.width = 1024; canvas.height = 1536; const ctx = canvas.getContext('2d'); stage.append(canvas);
    const side = el('div'); side.className = 'ph3b-side';
    const list = el('div'); list.className = 'ph3b-list'; side.append(list);
    const label = (name, control) => { const l = el('label', name); l.append(control); side.append(l); return control; };
    const panel = label('コマ', el('select')); for (let n = 1; n <= layout.count; n++) { const o = el('option', `${n}コマ目`); o.value = n; panel.append(o); }
    const speaker = label('話している人物', el('select')); for (const s of ['人物1', '人物2', '人物3', NARRATION]) speaker.append(el('option', s));
    const text = label('セリフ（改行は縦書きの列区切り）', el('textarea'));
    const tailLabel = el('label'), tail = el('input'); tail.type = 'checkbox'; tailLabel.append(tail, document.createTextNode(' 尻尾を付ける')); side.append(tailLabel);
    const add = el('button', 'このコマに吹き出しを追加'), remove = el('button', '選んだ吹き出しを削除'), shorten = el('button', '尻尾を短い初期位置に戻す'), resetText = el('button', '文字領域を吹き出しの内側に戻す');
    const up = el('button', '読み順を一つ前へ'), down = el('button', '読み順を一つ後へ');
    side.append(add, remove, shorten, resetText, up, down);
    body.append(stage, side); dialog.append(header, tools, hint, status, body); document.body.append(dialog);
    const current = () => items.find(i => i.id === selected);
    const xy = (x, y) => [x * 1.024, y * 1.536];
    function draw() {
        ctx.clearRect(0, 0, 1024, 1536); if (background) ctx.drawImage(background, 0, 0, 1024, 1536);
        for (const item of items) {
            const [y0, x0, y1, x1] = item.bbox;
            {
                ctx.fillStyle = 'white'; ctx.strokeStyle = 'black'; ctx.lineWidth = widget(node, '線の太さ').value;
                // 同じマスクに楕円と尻尾を塗り、内部の境界線は残さない。
                const mask = document.createElement('canvas'); mask.width = 1024; mask.height = 1536;
                const m = mask.getContext('2d'); m.fillStyle = 'white';
                m.beginPath(); m.ellipse(...xy((x0+x1)/2, (y0+y1)/2), (x1-x0)*.512, (y1-y0)*.768, 0, 0, Math.PI*2); m.fill();
                const points = tailPoints(item); if (points) { m.beginPath(); m.moveTo(...xy(...points[0])); m.lineTo(...xy(...points[2])); m.lineTo(...xy(...points[1])); m.closePath(); m.fill(); }
                // Canvasの影を輪郭に使用。これは画面の見本だけで、出力ガイドはPythonノードで作る。
                ctx.save(); ctx.shadowColor = 'black'; ctx.shadowBlur = 0;
                const width = widget(node, '線の太さ').value;
                for (const [dx,dy] of [[-width,0],[width,0],[0,-width],[0,width]]) { ctx.shadowOffsetX = dx; ctx.shadowOffsetY = dy; ctx.drawImage(mask,0,0); }
                ctx.restore(); ctx.drawImage(mask,0,0);
            }
            const b = textBox(item, ratio), chosen = item.id === selected;
            ctx.strokeStyle = chosen ? '#2563eb' : '#64748b'; ctx.lineWidth = chosen ? 3 : 1; ctx.setLineDash([6,5]);
            const box = mode.selectedIndex ? b : item.bbox;
            ctx.strokeRect(box[1]*1.024, box[0]*1.536, (box[3]-box[1])*1.024, (box[2]-box[0])*1.536); ctx.setLineDash([]);
            ctx.font = '18px system-ui'; ctx.fillStyle = '#1d4ed8'; ctx.fillText(`${item.panel}コマ・${items.indexOf(item)+1}`, x0*1.024, Math.max(18,y0*1.536-7));
            if (chosen) {
                ctx.fillStyle = '#2563eb'; ctx.fillRect(box[3]*1.024-7,box[2]*1.536-7,14,14);
                if (!mode.selectedIndex && item.tail && item.speaker !== NARRATION) { ctx.beginPath(); ctx.arc(...xy(...item.tail),10,0,Math.PI*2); ctx.fill(); }
            }
        }
        if (lettered) ctx.drawImage(lettered, 0, 0, 1024, 1536);
        requestLettering();
    }
    // セリフは写植ノードと同じPython処理で描いた透明PNGを重ねる（画面の見本だけ。生成ガイド・モデル出力には使わない）。
    const {settings: lettering, connected} = letteringSettings(node);
    let lettered = null, letteringKey = '', letteringBusy = false, letteringMessage = '';
    // ほかの警告（コマ割り画像の読み込み失敗など）は上書きしない。
    function letteringStatus(text) { if (!status.textContent || status.textContent === letteringMessage) status.textContent = text; letteringMessage = text; }
    async function requestLettering() {
        const body = JSON.stringify({layout: layout.id, items, ratio, ...lettering});
        if (body === letteringKey || letteringBusy) return;
        letteringKey = body; letteringBusy = true;
        try {
            const response = await api.fetchApi('/ph3_manga/lettering_preview', {method:'POST', headers:{'Content-Type':'application/json'}, body});
            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                lettered = null; letteringStatus(`セリフの見本を作れません：${error.error ?? response.status}`);
            } else {
                const image = await createImageBitmap(await response.blob());
                if (body === letteringKey) { lettered = image; letteringStatus(connected ? '' : '写植ノードが未接続のため、セリフの見本は写植ノードの初期設定で表示しています。'); }
            }
        } catch (error) { lettered = null; letteringStatus(`セリフの見本を作れません：${error.message}`); }
        finally { letteringBusy = false; }
        draw();
    }
    function renderList() {
        list.replaceChildren();
        for (const item of items) { const button = el('button', `${item.panel}コマ目・${item.speaker}：${item.text.slice(0,16) || '（空）'}`); button.setAttribute('aria-pressed',item.id === selected); button.onclick = () => { selected = item.id; sync(); }; list.append(button); }
    }
    function sync() {
        const i = current(); for (const c of [speaker,text,tail,remove,shorten,resetText,up,down]) c.disabled = !i;
        if (i) { panel.value = i.panel; speaker.value = i.speaker; text.value = i.text; tail.checked = !!i.tail && i.speaker !== NARRATION; tail.disabled = i.speaker === NARRATION; }
        else text.value = '';
        renderList(); draw();
    }
    text.oninput = () => { if (current()) { current().text = text.value; renderList(); draw(); } };
    panel.onchange = () => { if (current()) { current().panel = Number(panel.value); sync(); } };
    speaker.onchange = () => { const i = current(); if (!i) return; i.speaker = speaker.value; if (i.speaker === NARRATION) i.tail = null; sync(); };
    tail.onchange = () => { if (current()) current().tail = tail.checked ? shortTail(current().bbox) : null; sync(); };
    shorten.onclick = () => { if (current()?.speaker !== NARRATION) current().tail = shortTail(current().bbox); sync(); };
    resetText.onclick = () => { if (current()) delete current().text_bbox; sync(); };
    add.onclick = async () => { const response = await api.fetchApi(`/ph3_manga/layout/${layout.id}`); if (!response.ok) { status.textContent = 'コマの座標を取得できません。'; return; } const row = await response.json(); const i = newBalloon(Number(panel.value),row.panels[Number(panel.value)-1].bbox); items.push(i); selected = i.id; sync(); };
    remove.onclick = () => { items = items.filter(i => i.id !== selected); selected = items[0]?.id; sync(); };
    function reorder(delta) { const index = items.findIndex(i => i.id === selected), next = index + delta; if (index < 0 || next < 0 || next >= items.length) return; [items[index],items[next]] = [items[next],items[index]]; sync(); }
    up.onclick = () => reorder(-1); down.onclick = () => reorder(1);
    const point = event => { const r = canvas.getBoundingClientRect(); return [clamp((event.clientX-r.left)/r.width*1000), clamp((event.clientY-r.top)/r.height*1000)]; };
    const distance = (a,b) => Math.hypot((a[0]-b[0])*1.024,(a[1]-b[1])*1.536);
    canvas.onpointerdown = event => {
        const p = point(event), item = current(), radius = 14 * 1024 / canvas.getBoundingClientRect().width;
        const b = item && (mode.selectedIndex ? textBox(item,ratio) : item.bbox);
        if (item && !mode.selectedIndex && item.tail && distance(p,item.tail) < radius) activeDrag = {kind:'tail',original:clone(item),start:p};
        else if (b && distance(p,[b[3],b[2]]) < radius) activeDrag = {kind:'resize',original:clone(item),start:p};
        else {
            const hit = [...items].reverse().find(i => { const b = mode.selectedIndex ? textBox(i,ratio) : i.bbox; return p[0]>=b[1] && p[0]<=b[3] && p[1]>=b[0] && p[1]<=b[2]; });
            if (hit) { selected = hit.id; activeDrag = {kind:'move',original:clone(hit),start:p}; sync(); }
        }
        if (activeDrag) { event.preventDefault(); canvas.setPointerCapture(event.pointerId); }
    };
    canvas.onpointermove = event => {
        if (!activeDrag) return; const p = point(event), i = current(); Object.assign(i,clone(activeDrag.original));
        if (activeDrag.kind === 'tail') i.tail = p;
        else if (activeDrag.kind === 'resize') resizeItem(i,...p,!!mode.selectedIndex,ratio);
        else moveItem(i,p[0]-activeDrag.start[0],p[1]-activeDrag.start[1],!!mode.selectedIndex,ratio);
        draw();
    };
    canvas.onpointerup = canvas.onpointercancel = () => { activeDrag = null; };
    async function loadBackground() {
        const image = new Image();
        image.onload = () => { background = image; draw(); };
        image.onerror = () => { status.textContent = 'コマ割り画像を読み込めません。'; };
        image.src = api.apiURL(layout.preview);
    }
    mode.onchange = draw;
    dialog.addEventListener('close', () => dialog.remove(), {once:true}); dialog.showModal(); sync(); await loadBackground();
}

function installEditor(node) {
    if (node._ph3BalloonInstalled) return; node._ph3BalloonInstalled = true;
    styles();
    node.title = '漫画の編集';
    hideWidget(widget(node,'編集データ'));
    node.addWidget('button','吹き出し・セリフ・尻尾を編集',null,() => openEditor(node),{serialize:false});
    const box = el('div'), image = el('img'), caption = el('p'); image.className = 'ph3b-thumb'; image.hidden = true; box.append(image,caption);
    node._ph3Caption = caption;
    let refresh = 0;
    node._ph3Refresh = async () => {
        const request = ++refresh;
        let count = 0; try { count = data(node).length; } catch {}
        const description = `${count}個の吹き出し。「吹き出し・セリフ・尻尾を編集」から変更できます。`;
        caption.textContent = description;
        let entries = [];
        try { entries = await getCatalog(); } catch {}
        if (request !== refresh) return;
        const value = widget(node, 'コマ割り')?.value;
        const layout = entries.find(entry => [entry.id, entry.name, entry.name_en].includes(value));
        const candidates = [];
        if (layout) candidates.push({url:api.apiURL(layout.preview), label:'選択中のコマ割り'});
        await loadPreview(image, candidates, loaded => {
            if (request !== refresh) return;
            caption.textContent = `${description} ${loaded ? `${loaded.label}を表示中。` : '画像を読み込めません。ComfyUIとの接続を確認してください。'}`;
        });
    };
    for (const ev of ['pointerdown','mousedown','click','keydown']) box.addEventListener(ev,e=>e.stopPropagation());
    node.addDOMWidget('コマ割りの見本','custom',box,{serialize:false,hideOnZoom:false,getMinHeight:()=>280,getMaxHeight:()=>300});
    node.setSize([Math.max(440,node.size[0]),Math.max(430,node.size[1])]);
    node._ph3Refresh();

}
app.registerExtension({
    name:'PH3Manga.BalloonEditor',
    beforeRegisterNodeDef(nodeType,nodeData) {
        if (nodeData.name !== EDITOR) return;
        const old = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function(...args) { const r=old?.apply(this,args); installEditor(this); return r; };
    },
    loadedGraphNode(node) { if (node.type === EDITOR) { installEditor(node); node.title='漫画の編集'; node._ph3Refresh?.(); } },
    afterConfigureGraph() { for (const node of app.graph?._nodes || []) if (node.type === EDITOR) node._ph3Refresh?.(); },
});
