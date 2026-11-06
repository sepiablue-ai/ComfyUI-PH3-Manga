# ComfyUI-PH3-Manga

参照画像のキャラクターで漫画ページを描き、吹き出しの配置から日本語の写植までをComfyUIのワークフローで行うカスタムノードです。

## できること

- **コマ割りを選ぶ**：2〜6コマ、196種類の空コマ割りを同梱しています。
- **参照キャラとシーンから漫画を生成する**：P-H3-Imageへキャラ画像とコマごとの説明を渡します。同梱の生成ワークフローは3コマ・2人の例です。
- **吹き出しを編集する**：ComfyUI標準の `Create Bounding Boxes` で位置・大きさを調整し、尾の先端も指定できます。空の吹き出しを描いたガイドを生成モデルへの入力にします。
- **日本語を縦書きで写植する**：セリフ、明示した改行、ルビ、縦書きの句読点、簡易禁則、`！？` などの縦中横に対応します。かなと漢字に別々のフォントを指定できます。
- **作画を維持して写植をやり直す**：既存ページに文字だけを入れる専用ワークフローも用意しています。

写植はフォントによる文字描画です。セリフとルビはP-H3やMOSSが生成する文字ではありません。吹き出しガイドも入力用の図形です。P-H3が最終的に描く吹き出しの形・位置やキャラの一致を保証するものではありません。

[English README](README.en.md)

## 導入方法

### 1. ComfyUIを用意する

[ComfyUI](https://github.com/Comfy-Org/ComfyUI) のP-H3-Image対応版を使用してください。生成例には `PH3ImageConditioning`、`MiniMaxH3SigmaShift`、`CreateBoundingBoxes`、`StringFormat` が必要です。ノードが不足する場合は、既存環境を保護したうえでComfyUIを更新してください。

### 2. カスタムノードを配置する

このリポジトリのフォルダを `ComfyUI/custom_nodes/ComfyUI-PH3-Manga` として配置します。別の `ComfyUI-MossPanelDataset` の導入は不要です。

**ComfyUIを実行しているPython環境**で、次を実行してください。システム全体のPythonへインストールする必要はありません。

```bash
python -m pip install -r ComfyUI/custom_nodes/ComfyUI-PH3-Manga/requirements.txt
```

ComfyUI同梱のPythonを使う構成では、`python` をその実行ファイルに読み替えてください。追加依存のBudouXは日本語の文節区切りに使います。PyTorch・NumPy・PillowはComfyUIの環境を使用します。

### 3. 日本語フォントを用意する

写植に使用する日本語フォントを本パッケージの `fonts/` に置きます。利用権のある `.ttf`・`.ttc`・`.otf`・`.otc` を使用してください。[Noto CJK](https://github.com/notofonts/noto-cjk) などを利用できます。フォントファイル自体は同梱していません。

`kana_font` と `kanji_font` は、`auto` なら同梱用フォルダとインストール済みの日本語フォントから選択します。Windowsではインストール済みの游明朝・游ゴシックも候補になります。固定した組版が必要な場合は、両方に同じフォントファイル名を明示してください。別ディレクトリを探す場合は `PH3_MANGA_FONT_DIR` も指定できます。

### 4. P-H3のモデルを配置する

漫画生成を使う場合は、[PrunaAI/P-H3-Image-Comfy](https://huggingface.co/PrunaAI/P-H3-Image-Comfy) からモデルを用意します。同梱の生成例は次のファイル名を使用します。

| 種類 | 配置先（ComfyUIからの相対パス） | ファイル名 |
|---|---|---|
| 本体 | `models/diffusion_models/` | `p-h3-image_int8_convrot.safetensors` |
| テキストエンコーダー | `models/text_encoders/` | `p-h3-image_text_encoder_int8_convrot.safetensors` |
| VAE | `models/vae/` | `p-h3-image_vae_int8_convrot.safetensors` |

別の対応精度を使用する場合は、各ローダーで手元のファイルを選び直してください。この例はLoRA込みのP-H3本体を使い、プロンプト拡張モデルは使用しません。**既存ページへの写植だけなら、P-H3モデルは不要です。**

### 5. 再起動してワークフローを開く

ComfyUIを再起動し、`example_workflows/` のJSONを画面へドラッグしてください。

| ワークフロー | 用途 |
|---|---|
| [01_generate_and_letter.json](example_workflows/01_generate_and_letter.json) | キャラ参照2枚と3コマのシーン説明から、空吹き出し付きの漫画を生成し、写植する |
| [02_letter_existing_page.json](example_workflows/02_letter_existing_page.json) | 自分で用意した漫画ページへ、セリフとルビを写植する |

キャラ画像・入力ページは同梱していません。各 `LoadImage` で利用する画像をアップロードしてください。

## 使い方

### 生成してから写植する

1. `Panel Layout / コマ割り` でレイアウトを選びます。出力画像は同梱テンプレート、`width`・`height` は生成先の解像度です。縦横比を維持し、生成寸法を32の倍数に揃えます。
2. キャラA・Bの画像を読み込み、3つの「シーン説明」に各コマの場面を入力します。これは利用者が書くプロンプトです。画像参照は `<Picture 1>` が吹き出しガイド、`<Picture 2>` がキャラA、`<Picture 3>` がキャラBです。
3. 生成前の `Create Bounding Boxes` で各吹き出しの枠を動かし、種類を `text` にしてセリフを入力します。枠は楕円の外接矩形です。尾の指定は次項を参照してください。
4. 実行します。ガイドと参照画像をP-H3へ渡し、生成ページにフォントで写植します。文字なしの生成画像と写植後の画像は別々に保存します。
5. 生成後の文字領域を調整したい場合は、後段の `Create Bounding Boxes` を編集します。作画を再生成せず安定して写植を調整する場合は、文字なしの画像を `02_letter_existing_page.json` へ読み込んでください。

**生成例のシーン説明は3コマ分です。** 別のコマ数のレイアウトへ変更するときは、説明文と吹き出しの数・配置も合わせて変更してください。196種類の選択だけでシナリオが自動的に増減する機能ではありません。

### 吹き出しの尾と文字領域

各枠の説明欄 `desc` に、ページ全体を0〜1000にした座標で尾の先端を指定します。

```json
{"tail": [500, 400]}
```

順番は `[x, y]`、原点は左上です。尾のない吹き出しは `{}` または `{"tail": null}` にします。位置はページを基準とし、コマや吹き出しを動かした後は尾の座標も調整してください。

`Balloon Guide` の `inner_ratio` は楕円の内側で文字に使う範囲、`line_width` は入力ガイドの線幅です。初期JSONにはピクセル単位の `{x,y,width,height,metadata}` または標準の要素形式 `{bbox,text,type,desc}` を使用できます。要素形式の `bbox` は **0〜1000の `[ymin,xmin,ymax,xmax]`** で、尾とは座標の並びが異なります。

### 写植とルビ

- 枠の `text` が描画するセリフです。明示した改行は縦書きの列の区切りになり、そのまま保持します。改行を入れない場合はBudouXで文節を区切って自動的に折り返します。
- `font_size` はページ高さに対する文字サイズの上限です。枠に収まらない場合は縮小します。
- `ruby` に語句と読みのJSON対応表を入力すると、対応する語の右にルビを添えます。

```json
{"雨": "あめ", "一緒": "いっしょ"}
```

ルビを付ける語は同じ列に収めてください。改行や自動折り返しで語が列をまたぐと、その語のルビは付きません。組版は簡易的なもので、複雑な縦書き約物・欧文・出版用の完全な組版規則を網羅するものではありません。

文字なしのP-H3出力を編集して吹き出しを描き直す処理はありません。ガイドが生成結果で変形した場合は、入力ガイドやプロンプトを見直すか、文字領域を生成結果に合わせて調整してください。

## ライセンス・クレジット

このノードのコードと同梱のコマ割りは [MIT License](LICENSE) です。コマ割りの出典は [ComfyUI-MossPanelDataset](https://github.com/sepiablue-ai/ComfyUI-MossPanelDataset) です。[第三者の素材・ライブラリ](THIRD_PARTY_NOTICES.md) も参照してください。

P-H3モデルには別途 [MiniMax H3 Community License](https://huggingface.co/PrunaAI/P-H3-Image-Comfy/blob/main/LICENSE) が適用されます。モデル・フォント・入力画像の条件はそれぞれ確認してください。

Powered by MiniMax H3
