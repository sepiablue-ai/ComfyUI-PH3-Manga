import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const source = await readFile(new URL('../web/balloon_geometry.js', import.meta.url), 'utf8');
const { moveItem, resizeItem, textBox, shortTail } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

test('吹き出しを動かすと尻尾も同じ量だけ動く', () => {
    const i = {bbox:[100,200,300,400],tail:[350,340]};
    moveItem(i,25,30); assert.deepEqual(i.bbox,[130,225,330,425]); assert.deepEqual(i.tail,[375,370]);
});
test('文字領域だけの移動・拡大では吹き出しと尻尾を変更しない', () => {
    const i = {bbox:[100,200,300,400],tail:[350,340]};
    moveItem(i,10,15,true,.7); resizeItem(i,450,400,true,.7);
    assert.deepEqual(i.bbox,[100,200,300,400]); assert.deepEqual(i.tail,[350,340]);
    assert.deepEqual(textBox(i,.7),[145,240,400,450]);
});
test('ページ外へのドラッグを制限する', () => {
    const i = {bbox:[100,200,300,400],tail:[350,340]};
    moveItem(i,1000,-1000); assert.deepEqual(i.bbox,[0,800,200,1000]);
    assert.deepEqual(i.tail,[950,240]);
});
test('細い吹き出しの初期尻尾は実寸の短辺より短い', () => {
    const bbox = [100,200,400,240], tail = shortTail(bbox);
    assert.ok((tail[1]-400)*1.5 < 40*.25);
});
