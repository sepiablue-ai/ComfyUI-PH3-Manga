# 第三者の素材・ライブラリ / Third-party materials and libraries

## コマ割り / Panel layouts

`data/layouts.json` と `data/layouts/` は [ComfyUI-MossPanelDataset](https://github.com/sepiablue-ai/ComfyUI-MossPanelDataset) のコマ割りデータを整理して収録しています。MIT License、Copyright (c) 2026 sepiablue-ai。ライセンス全文は [LICENSE](LICENSE) に保持しています。人物画像・構図の作例・モデルは含みません。

`data/layouts.json` and `data/layouts/` contain a streamlined copy of the panel layout data from [ComfyUI-MossPanelDataset](https://github.com/sepiablue-ai/ComfyUI-MossPanelDataset), under the MIT License, Copyright (c) 2026 sepiablue-ai. The complete notice is retained in [LICENSE](LICENSE). Character images, composition examples and model weights are not included.

`web/picker.js` のコマ割り選択画面は、同じ ComfyUI-MossPanelDataset（MIT License、Copyright (c) 2026 sepiablue-ai）の選択画面を移植したものです。 / The layout picker in `web/picker.js` is ported from the same project.

## 外部の実行環境 / External runtime

- [ComfyUI](https://github.com/Comfy-Org/ComfyUI): このパッケージとは別のライセンスで配布される実行環境です。The runtime is distributed separately under its own license.
- [P-H3-Image-Comfy](https://huggingface.co/PrunaAI/P-H3-Image-Comfy): モデルは同梱しません。利用条件はモデルの [LICENSE](https://huggingface.co/PrunaAI/P-H3-Image-Comfy/blob/main/LICENSE) を参照してください。Model weights are not bundled; their license is separate from this node pack's MIT License.
- [BudouX](https://github.com/google/budoux): 日本語の文節区切りに利用します。Japanese phrase segmentation; installed as a dependency.
- フォントは同梱しません。利用者が各フォントのライセンスに従って用意します。Fonts are not bundled and remain subject to their respective licenses.
