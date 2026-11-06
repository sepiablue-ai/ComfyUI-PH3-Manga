// 存在する画像だけを表示し、保存画像がなければコマ割り画像へ切り替える。
// 遅れて完了した古い要求で、新しく選んだ画像を上書きしない。
export async function loadPreview(image, candidates, onLoaded, ImageType = Image) {
    const request = Symbol();
    image._ph3PreviewRequest = request;
    image.hidden = true;
    image.removeAttribute('src');
    for (const candidate of candidates) {
        const source = new ImageType();
        const loaded = await new Promise(resolve => {
            source.onload = () => resolve(true);
            source.onerror = () => resolve(false);
            source.src = candidate.url;
        });
        if (image._ph3PreviewRequest !== request) return;
        if (!loaded) continue;
        image.src = candidate.url;
        image.alt = candidate.label;
        image.hidden = false;
        onLoaded(candidate);
        return;
    }
    if (image._ph3PreviewRequest === request) onLoaded(null);
}
