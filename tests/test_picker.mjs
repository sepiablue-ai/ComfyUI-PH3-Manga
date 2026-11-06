import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const source = await readFile(new URL('../web/picker.js',import.meta.url),'utf8');
let resolveCatalog;
const app={registerExtension(){},canvas:{setDirty(){}}};
const api={apiURL:v=>v,fetchApi:()=>new Promise(resolve=>{resolveCatalog=resolve;})};
globalThis.ph3PickerTest={app,api};
const rewritten=source.replace(/import \{ app \}[^;]+;/,'const {app}=globalThis.ph3PickerTest;').replace(/import \{ api \}[^;]+;/,'const {api}=globalThis.ph3PickerTest;')+'\nexport {applyLayout,select,install};';
const {applyLayout,select,install}=await import(`data:text/javascript;base64,${Buffer.from(rewritten).toString('base64')}`);
const entries=[2,3,4].map(count=>({id:`layout${count}`,name:`${count}コマ`,count,positions:[],positions_en:[],panel_boxes:Array.from({length:count},(_,i)=>[0,i/count,1,(i+1)/count])}));
function fixture(format='object') {
    let id=20,lid=0;
    const graph={_nodes:[],links:format==='map'?new Map():{},setDirtyCanvas(){},beforeChange(){},afterChange(){},getNodeById(id){return this._nodes.find(n=>String(n.id)===String(id));},add(n){n.id=++id;n.graph=this;this._nodes.push(n);},remove(n){this._nodes=this._nodes.filter(v=>v!==n);}};
    const get=k=>graph.links instanceof Map?graph.links.get(k):graph.links[k];
    const put=(k,v)=>graph.links instanceof Map?graph.links.set(k,v):(graph.links[k]=v);
    function scene(type='PH3MangaScene') {return {type,widgets:[{name:'場面',value:'場面'}],pos:[0,0],size:[100,100],outputs:[{links:[]}],connect(out,target,slot){const l=++lid;put(l,format==='array'?[l,this.id,out,target.id,slot]:{id:l,origin_id:this.id,origin_slot:out,target_id:target.id,target_slot:slot});this.outputs[out].links.push(l);target.inputs[slot].link=l;}};}
    globalThis.LiteGraph={createNode:scene};
    const editor={id:9,type:'PH3MangaBalloonEditor',graph,widgets:[{name:'コマ割り',value:entries[1].name},{name:'編集データ',value:JSON.stringify([{id:'first',panel:1,bbox:[10,100,200,300],tail:[200,220],text:'一番'},{id:'third-a',panel:3,bbox:[700,100,800,300],text:'三番前'},{id:'third-b',panel:3,bbox:[700,500,800,700],text:'三番後'}])}],properties:{ph3Layout:entries[1].id,ph3PanelBoxes:entries[1].panel_boxes},_ph3Refresh(){this.refreshed=(this.refreshed||0)+1;},addWidget(){},addDOMWidget(){},setSize(){},size:[400,400]};
    const story={id:4,type:'PH3MangaStory',graph,widgets:[],properties:{},pos:[0,0],inputs:[{name:'構成と話者',link:100},...Array.from({length:6},(_,i)=>({name:`コマ${i+1}`,link:null}))],disconnectInput(slot){const l=get(this.inputs[slot].link);const origin=graph.getNodeById(Array.isArray(l)?l[1]:l.origin_id);if(origin)origin.outputs[0].links=origin.outputs[0].links.filter(v=>v!==this.inputs[slot].link);this.inputs[slot].link=null;}};
    put(100,format==='array'?[100,9,3,4,0]:{origin_id:9,target_id:4});
    graph._nodes.push(editor,story);
    for(let i=1;i<=3;i++){const n=scene();graph.add(n);n.widgets[0].value=`場面${i}`;n.connect(0,story,i);}
    return {editor,story,graph};
}
for(const format of ['object','array','map'])test(`${format}形式の接続でもコマ数と配置を同期し、退避セリフを順序ごと復元する`,()=>{
    const {editor,story,graph}=fixture(format);
    applyLayout(editor,entries[0]);
    assert.equal(editor.widgets[0].value,'2コマ');
    assert.equal(graph._nodes.filter(n=>n.type==='PH3MangaScene').length,2);
    assert.equal(JSON.parse(editor.widgets[1].value).length,1);
    applyLayout(editor,entries[1]);
    assert.equal(graph._nodes.filter(n=>n.type==='PH3MangaScene').length,3);
    assert.deepEqual(JSON.parse(editor.widgets[1].value).map(i=>i.id),['first','third-a','third-b']);
    const thirdLink=graph.links instanceof Map?graph.links.get(story.inputs[3].link):graph.links[story.inputs[3].link];
    const third=graph.getNodeById(Array.isArray(thirdLink)?thirdLink[1]:thirdLink.origin_id);
    assert.equal(third.widgets[0].value,'場面3');assert.ok(editor.refreshed>=2);
});
test('一覧取得中に連続変更しても最後のコマ割りだけを適用する',async()=>{
    globalThis.document={getElementById:()=>true,createElement:()=>({addEventListener(){},append(){},replaceChildren(){}})};
    const {editor,graph}=fixture();install(editor);
    const w=editor.widgets[0];w.callback(entries[0].name);w.callback(entries[2].name);
    resolveCatalog({ok:true,json:async()=>({layouts:entries})});
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal(w.value,'4コマ');assert.equal(editor.properties.ph3Layout,'layout4');
    assert.equal(graph._nodes.filter(n=>n.type==='PH3MangaScene').length,4);
});
