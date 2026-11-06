// 「漫画ページ」ノードに、見本画像からコマ割りを選ぶ画面と、コマの内容ノードの自動増減を付ける。
// ComfyUI-MossPanelDataset（MIT, sepiablue-ai）の選択画面を P-H3 用に移植したもの。
import { app } from '../../scripts/app.js';
import { api } from '../../scripts/api.js';

const TYPE = 'PH3MangaPage', PANEL = 'PH3MangaPanel';
const FAVORITES = 'ph3manga.favorites.v1';
const isJa = () => String(app.ui?.settings?.getSettingValue?.('Comfy.Locale') ?? navigator.language ?? '').startsWith('ja');
const tr = (ja, en) => isJa() ? ja : en;
const el = (tag, text, cls) => { const n = document.createElement(tag); if (text) n.textContent = text; if (cls) n.className = cls; return n; };
const favorites = () => { try { return new Set(JSON.parse(localStorage.getItem(FAVORITES) || '[]')); } catch { return new Set(); } };
const saveFavorites = v => { try { localStorage.setItem(FAVORITES, JSON.stringify([...v])); } catch { } };
const clone = v => JSON.parse(JSON.stringify(v));
const linkAt = (node, slot) => node.getInputLink?.(slot) ?? node.graph?.links?.[node.inputs[slot]?.link];
const slotOf = (node, name) => (node.inputs ?? []).findIndex(s => s.name === name);
let catalogPromise;
function catalog(force = false) {
    if (force || !catalogPromise) catalogPromise = api.fetchApi('/ph3_manga/catalog').then(r => { if (!r.ok) throw Error(tr('コマ割り一覧を読み込めません。', 'Could not load the layout list.')); return r.json(); })
        .then(d => d.layouts).catch(e => { catalogPromise = null; throw e; });
    return catalogPromise;
}
const findEntry = (entries, value) => entries.find(e => e.id === value || e.name === value || e.name_en === value);
const panelTitle = (entry, i) => { const ja = entry.positions?.[i - 1], en = entry.positions_en?.[i - 1];
    return tr(ja ? `${i}コマ目（${ja}）` : `${i}コマ目`, en ? `Panel ${i} (${en})` : `Panel ${i}`); };
const createNode = type => { const LG = globalThis.LiteGraph ?? globalThis.comfyAPI?.litegraph?.LiteGraph; return LG?.createNode?.(type); };

function snapshot(node) {
    return { nodeId: node.id, title: node.title, pos: Array.from(node.pos), size: Array.from(node.size),
        widgets: Object.fromEntries((node.widgets ?? []).filter(w => w.name && w.value !== undefined).map(w => [w.name, clone(w.value)])) };
}
function restore(node, saved) {
    if (!saved) return;
    for (const w of node.widgets ?? []) if (Object.hasOwn(saved.widgets, w.name)) w.value = clone(saved.widgets[w.name]);
    node.pos = [...saved.pos]; node.size = [...saved.size];
}

// コマ数に合わせてコマの内容ノードを増減する。減らしたコマの入力は退避し、戻すと復元する。
function applyLayout(node, entry) {
    const graph = node.graph, count = entry.count;
    node.properties ??= {};
    const stash = node.properties.ph3RetiredPanels ??= {};
    graph.beforeChange?.();
    try {
        for (let i = count + 1; i <= 6; i++) {
            const slot = slotOf(node, `コマ${i}`); if (slot < 0) continue;
            const link = linkAt(node, slot); if (!link) continue;
            const panel = graph.getNodeById(link.origin_id);
            if (panel?.type === PANEL) stash[i] = snapshot(panel);
            node.disconnectInput(slot);
            if (panel?.type === PANEL && (panel.outputs ?? []).every(o => !o.links?.length)) graph.remove(panel);
        }
        for (let i = 1; i <= count; i++) {
            const slot = slotOf(node, `コマ${i}`);
            if (slot < 0) throw Error(tr(`コマ${i}の入力がありません。ComfyUIを再起動してください。`, `Input for panel ${i} is missing. Restart ComfyUI.`));
            const existing = linkAt(node, slot);
            let panel = existing && graph.getNodeById(existing.origin_id);
            if (!panel) {
                panel = createNode(PANEL);
                if (!panel) throw Error(tr('コマの内容ノードを作れません。', 'Could not create a panel content node.'));
                graph.add(panel); restore(panel, stash[i]);
                if (!stash[i]) { const last = graph.getNodeById(linkAt(node, slotOf(node, `コマ${i - 1}`))?.origin_id); panel.pos = last ? [last.pos[0], last.pos[1] + last.size[1] + 60] : [node.pos[0] - 520, node.pos[1]]; }
                panel.connect(0, node, slot);
                delete stash[i];
            }
            if (panel.type === PANEL) panel.title = panelTitle(entry, i);
        }
        node.widgets.find(w => w.name === 'コマ割り').value = entry.name;
        graph.setDirtyCanvas?.(true, true);
    } finally { graph.afterChange?.(); }
}

function style() {
    if (document.getElementById('ph3-picker-style')) return;
    const s = el('style'); s.id = 'ph3-picker-style';
    s.textContent = `.ph3p-dialog{width:min(1300px,94vw);max-height:90vh;padding:0;border:1px solid #64748b;border-radius:12px;background:#f4f6f9;color:#172033;font:15px/1.6 system-ui}.ph3p-dialog::backdrop{background:#0009}.ph3p-top{position:sticky;top:0;background:#f4f6f9;z-index:2;padding:14px 18px;border-bottom:1px solid #cbd5e1}.ph3p-title{display:flex;justify-content:space-between;align-items:center}.ph3p-title h2{font-size:21px;margin:0}.ph3p-filters{display:flex;gap:12px;flex-wrap:wrap;margin-top:12px;align-items:center}.ph3p-dialog button,.ph3p-dialog select,.ph3p-dialog input{font:inherit}.ph3p-dialog button,.ph3p-dialog select{padding:6px 12px;border:1px solid #aeb9c8;border-radius:6px;background:white;color:#172033;cursor:pointer}.ph3p-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(175px,1fr));gap:14px;padding:18px;overflow:auto}.ph3p-card{background:white;border:1px solid #d4dbe5;border-radius:8px;overflow:hidden}.ph3p-dialog .ph3p-pick{display:block;border:0;border-radius:0;padding:9px;width:100%;text-align:left}.ph3p-pick img{display:block;width:100%;aspect-ratio:2/3;object-fit:contain;background:white}.ph3p-name{display:block;font-size:13px;margin-top:7px;min-height:42px}.ph3p-foot{display:flex;justify-content:space-between;align-items:center;padding:4px 8px 8px;font-size:12px;color:#526074}.ph3p-preview{width:100%;display:flex;flex-direction:column;align-items:center;padding:5px;box-sizing:border-box;color:var(--input-text,#ddd);font:12px/1.5 system-ui}.ph3p-preview img{display:block;width:100%;height:180px;object-fit:contain}.ph3p-preview p{margin:4px;text-align:center}`;
    document.head.append(s);
}

function preview(node, entry) {
    const box = node._ph3Preview; if (!box) return;
    box.replaceChildren();
    if (!entry) { box.append(el('p', tr('画像からコマ割りを選んでください。', 'Choose a layout from the images.'))); return; }
    const img = el('img'); img.src = api.apiURL(entry.preview); img.alt = entry.name; box.append(img);
    box.append(el('p', tr(`${entry.name}／${entry.count}コマ`, `${entry.name_en} / ${entry.count} panels`)));
    node.setDirtyCanvas?.(true, true);
}

async function select(node, entry) { applyLayout(node, entry); preview(node, entry); app.canvas?.setDirty(true, true); }

async function openPicker(node) {
    style();
    let entries; try { entries = await catalog(true); } catch (e) { alert(e.message); return; }
    const dialog = el('dialog', null, 'ph3p-dialog'), top = el('div', null, 'ph3p-top'), title = el('div', null, 'ph3p-title');
    title.append(el('h2', tr('漫画のコマ割りを選ぶ', 'Choose a manga panel layout')));
    const close = el('button', tr('閉じる', 'Close')); close.onclick = () => dialog.close(); title.append(close); top.append(title);
    const filters = el('div', null, 'ph3p-filters');
    const makeSelect = (name, values) => { const l = el('label', name + ' '), s = el('select'); for (const [v, t] of values) { const o = el('option', t); o.value = v; s.append(o); } l.append(s); filters.append(l); return s; };
    const count = makeSelect(tr('コマ数', 'Panels'), [['', tr('すべて', 'All')], ...[2, 3, 4, 5, 6].map(n => [String(n), tr(`${n}コマ`, `${n} panels`)])]);
    const kind = makeSelect(tr('種類', 'Type'), [['normal', tr('通常・直線', 'Standard / straight')], ['diagonal', tr('斜め', 'Diagonal')], ['special', tr('特殊', 'Special')], ['', tr('すべて', 'All')]]);
    const current = findEntry(entries, node.widgets.find(w => w.name === 'コマ割り')?.value);
    count.value = current ? String(current.count) : '';
    const favLabel = el('label'), fav = el('input'); fav.type = 'checkbox'; favLabel.append(fav, document.createTextNode(' ' + tr('お気に入りのみ', 'Favorites only'))); filters.append(favLabel);
    const search = el('input'); search.placeholder = tr('名前で検索', 'Search by name'); filters.append(search);
    const total = el('span'); filters.append(total); top.append(filters);
    top.append(el('p', tr('画像を選ぶと今のワークフローへ反映します。コマの内容は保持し、減るコマは退避します。', 'Picking applies the layout. Panel contents are kept; removed panels are stashed.')));
    const grid = el('div', null, 'ph3p-grid'); dialog.append(top, grid); document.body.append(dialog);
    let stars = favorites();
    const render = () => {
        grid.replaceChildren();
        const q = search.value.toLowerCase();
        const list = entries.filter(e => (!count.value || e.count === Number(count.value)) && (!kind.value || (kind.value === 'normal' ? ['normal', 'straight'].includes(e.kind) : e.kind === kind.value))
            && (!fav.checked || stars.has(e.id)) && (!q || `${e.name} ${e.name_en}`.toLowerCase().includes(q)));
        total.textContent = tr(`${list.length}件`, `${list.length} found`);
        for (const entry of list) {
            const card = el('article', null, 'ph3p-card'), pick = el('button', null, 'ph3p-pick'); pick.type = 'button';
            const img = el('img'); img.src = api.apiURL(entry.preview); img.loading = 'lazy'; img.alt = entry.name;
            pick.append(img, el('span', tr(entry.name, entry.name_en), 'ph3p-name'));
            pick.onclick = async () => { try { await select(node, entry); dialog.close(); } catch (e) { alert(e.message); } };
            const foot = el('div', null, 'ph3p-foot'); foot.append(el('span', tr(`${entry.count}コマ・${entry.category}`, `${entry.count} panels · ${entry.category_en}`)));
            const star = el('button', stars.has(entry.id) ? '★' : '☆'); star.type = 'button';
            star.onclick = () => { stars.has(entry.id) ? stars.delete(entry.id) : stars.add(entry.id); saveFavorites(stars); render(); };
            foot.append(star); card.append(pick, foot); grid.append(card);
        }
    };
    for (const c of [count, kind, fav, search]) c.addEventListener('input', render);
    dialog.addEventListener('close', () => dialog.remove(), { once: true }); render(); dialog.showModal();
}

function install(node) {
    if (node._ph3PickerInstalled) return; node._ph3PickerInstalled = true; style();
    node.addWidget('button', tr('画像からコマ割りを選ぶ', 'Choose a layout from images'), null, () => openPicker(node), { serialize: false });
    const box = el('div', null, 'ph3p-preview'); node._ph3Preview = box;
    for (const ev of ['pointerdown', 'mousedown', 'dblclick', 'keydown', 'click']) box.addEventListener(ev, e => e.stopPropagation());
    node.addDOMWidget(tr('コマ割りの見本', 'Layout preview'), 'custom', box, { serialize: false, hideOnZoom: false, getMinHeight: () => 225, getMaxHeight: () => 260 });
    node.setSize([Math.max(node.size[0], 390), Math.max(node.size[1], 420)]);
    const widget = node.widgets.find(w => w.name === 'コマ割り');
    if (widget) {
        const previous = widget.callback;
        widget.callback = function (value, ...args) {
            previous?.call(this, value, ...args);
            catalog().then(entries => { const e = findEntry(entries, value); if (e) return select(node, e); }).catch(err => console.warn(err));
        };
        catalog().then(entries => preview(node, findEntry(entries, widget.value))).catch(() => preview(node, null));
    }
}

app.registerExtension({
    name: 'PH3Manga.LayoutPicker',
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== TYPE) return;
        const old = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) { const r = old?.apply(this, args); install(this); return r; };
    },
    loadedGraphNode(node) { if (node.type === TYPE) install(node); },
});
