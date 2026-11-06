# 日本語フォント / Japanese fonts

WindowsとmacOSでは、OS標準の日本語フォントを `auto` で使うため、通常はここに置く必要はありません。日本語フォントのないLinuxや、別のフォントを使いたい場合は、使用権のある日本語フォント（`.ttf` / `.ttc` / `.otf` / `.otc`）をこのフォルダに置き、ComfyUIを再起動してください。フォントは同梱しません。`kana_font` と `kanji_font` にファイル名を指定できます。`auto` はこのフォルダとインストール済みの日本語フォントを検索します。別の場所を使う場合は環境変数 `PH3_MANGA_FONT_DIR` も指定できます。

On Windows and macOS, `auto` uses the OS's standard Japanese fonts, so you usually do not need to put anything here. On Linux without a Japanese font, or to use a different font, place a Japanese font you are licensed to use (`.ttf` / `.ttc` / `.otf` / `.otc`) here and restart ComfyUI. Fonts are not bundled. Enter the filename in `kana_font` and `kanji_font`, or use `auto` to search this directory and installed Japanese fonts. Set `PH3_MANGA_FONT_DIR` to search an additional directory.

日本語に対応するフォントの例 / Examples with Japanese support:

- [Noto CJK](https://github.com/notofonts/noto-cjk)
- [Noto Japanese](https://github.com/notofonts/noto-cjk/blob/main/README.md)
