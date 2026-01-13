# ファビコン作成ガイド

## 方法1: オンラインツール（推奨・最も簡単）

### RealFaviconGenerator を使用

1. **サイトにアクセス**
   - https://realfavicongenerator.net/ を開く

2. **画像をアップロード**
   - 「Select your Favicon image」をクリック
   - 元画像（512x512のSiロゴ）を選択

3. **設定を確認**
   - iOS用: Apple touch icon を有効化
   - Android用: 必要に応じて設定
   - その他はデフォルトでOK

4. **生成・ダウンロード**
   - 「Generate your Favicons and HTML code」をクリック
   - ZIPファイルをダウンロード

5. **ファイルを配置**
   - ZIPを解凍
   - 以下のファイルを `/assets/favicon/` に配置：
     - `favicon.ico`
     - `favicon-32x32.png` → `favicon-32.png` にリネーム
     - `favicon-16x16.png` → `favicon-16.png` にリネーム
     - `apple-touch-icon.png` → `apple-touch.png` にリネーム

---

## 方法2: Python + Pillow（コマンドライン）

### 前提条件
```powershell
# 仮想環境を有効化
.\.venv\Scripts\Activate.ps1

# Pillowをインストール（未インストールの場合）
pip install Pillow
```

### スクリプトを作成

`create_favicons.py` を作成：

```python
from PIL import Image
import os

# 元画像のパス（512x512のSiロゴ）
SOURCE_IMAGE = "path/to/your/512x512_logo.png"
OUTPUT_DIR = "assets/favicon"

# 出力ディレクトリを作成
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 元画像を読み込み
img = Image.open(SOURCE_IMAGE)

# 各サイズを作成
sizes = {
    "favicon-16.png": 16,
    "favicon-32.png": 32,
    "apple-touch.png": 180,
}

for filename, size in sizes.items():
    resized = img.resize((size, size), Image.Resampling.LANCZOS)
    output_path = os.path.join(OUTPUT_DIR, filename)
    resized.save(output_path, "PNG")
    print(f"Created: {output_path}")

# favicon.ico を作成（16x16 + 32x32 マルチ）
ico_sizes = [16, 32]
ico_images = []
for size in ico_sizes:
    resized = img.resize((size, size), Image.Resampling.LANCZOS)
    ico_images.append(resized)

ico_path = os.path.join(OUTPUT_DIR, "favicon.ico")
ico_images[0].save(
    ico_path,
    format="ICO",
    sizes=[(s, s) for s in ico_sizes]
)
print(f"Created: {ico_path}")
```

### 実行
```powershell
python create_favicons.py
```

---

## 方法3: ImageMagick（Windows）

### インストール
1. https://imagemagick.org/script/download.php からダウンロード
2. インストール時に「Add to PATH」を選択

### コマンド実行
```powershell
cd C:\Users\SingKANA_β

# 元画像のパスを指定
$source = "path\to\your\512x512_logo.png"

# 各サイズを作成
magick $source -resize 16x16 assets\favicon\favicon-16.png
magick $source -resize 32x32 assets\favicon\favicon-32.png
magick $source -resize 180x180 assets\favicon\apple-touch.png

# favicon.ico を作成（16x16 + 32x32）
magick $source -resize 16x16 favicon-16.ico
magick $source -resize 32x32 favicon-32.ico
magick favicon-16.ico favicon-32.ico assets\favicon\favicon.ico
```

---

## 方法4: 画像編集ソフト（GIMP、Photoshopなど）

1. 元画像（512x512）を開く
2. 各サイズにリサイズ：
   - 16x16 → `favicon-16.png`
   - 32x32 → `favicon-32.png`
   - 180x180 → `apple-touch.png`
3. エクスポート時にPNG形式を選択
4. `favicon.ico` は専用ツールで作成（RealFaviconGenerator推奨）

---

## 推奨方法

**最も簡単**: 方法1（RealFaviconGenerator）
- ブラウザで完結
- すべてのサイズを自動生成
- HTMLコードも生成される（既に実装済みなので不要）

**自動化したい**: 方法2（Python + Pillow）
- スクリプト化可能
- 再生成が簡単

---

## 配置後の確認

1. **ブラウザで確認**
   - `http://localhost:5000` を開く
   - タブのファビコンを確認

2. **キャッシュクリア**
   - 反映されない場合: `Ctrl + Shift + R`（強制リロード）
   - または、HTMLのリンクに `?v=1` を追加

3. **ヘッダーロゴ確認**
   - ページ上部のロゴ画像を確認
