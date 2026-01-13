# Favicon ファイル配置場所

## 必要なファイル

以下のファイルをこのディレクトリに配置してください：

```
/assets/favicon/
├─ favicon.ico        (32x32 / 16x16 マルチ)
├─ favicon-32.png     (32x32)
├─ favicon-16.png     (16x16)
├─ apple-touch.png    (180x180)
```

## 元画像から作成するサイズ

元画像（512x512）から以下のサイズを作成：

1. **favicon.ico**: 16x16 + 32x32 をマルチICO形式でまとめる
2. **favicon-32.png**: 32x32
3. **favicon-16.png**: 16x16
4. **apple-touch.png**: 180x180

## 注意事項

- 角丸は元画像で完璧なので、加工不要
- 背景透明はそのままでOK
- キャッシュ対策が必要な場合は、HTMLで `?v=1` などのクエリを付ける

## 作成ツール（参考）

- **オンライン**: https://realfavicongenerator.net/
- **コマンドライン**: ImageMagick, Pillow (Python)
