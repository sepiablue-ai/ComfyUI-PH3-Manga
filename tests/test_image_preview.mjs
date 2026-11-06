import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const source = await readFile(new URL('../web/image_preview.js', import.meta.url), 'utf8');
const { loadPreview } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const image = () => ({hidden:false, src:'old', removeAttribute(name){delete this[name];}});
const candidate = name => ({url:name,label:name});
function loader(existing) {
    return class { set src(value) { queueMicrotask(() => existing.includes(value) ? this.onload() : this.onerror()); } };
}
test('生成前はコマ割り画像を表示する', async () => {
    const target=image(); let result;
    await loadPreview(target,[candidate('layout')],v=>result=v,loader(['layout']));
    assert.equal(target.src,'layout'); assert.equal(target.hidden,false); assert.equal(result.label,'layout');
});
test('保存画像がない場合はコマ割り画像へ切り替える', async () => {
    const target=image();
    await loadPreview(target,[candidate('raw'),candidate('layout')],()=>{},loader(['layout']));
    assert.equal(target.src,'layout'); assert.equal(target.hidden,false);
});
test('生成後は保存画像を優先する', async () => {
    const target=image();
    await loadPreview(target,[candidate('raw'),candidate('layout')],()=>{},loader(['raw','layout']));
    assert.equal(target.src,'raw'); assert.equal(target.hidden,false);
});
test('両方の読み込みに失敗しても壊れた画像を表示しない', async () => {
    const target=image(); let result=true;
    await loadPreview(target,[candidate('raw'),candidate('layout')],v=>result=v,loader([]));
    assert.equal(target.hidden,true); assert.equal(target.src,undefined); assert.equal(result,null);
});
test('遅れて完了した古い画像で新しい選択を上書きしない', async () => {
    const pending=new Map();
    class DeferredImage { set src(value){pending.set(value,this);} }
    const target=image();
    const first=loadPreview(target,[candidate('old')],()=>{},DeferredImage);
    const second=loadPreview(target,[candidate('new')],()=>{},DeferredImage);
    pending.get('new').onload(); await second;
    pending.get('old').onload(); await first;
    assert.equal(target.src,'new');
});
