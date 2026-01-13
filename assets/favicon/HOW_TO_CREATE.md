# ファビコン作成手順（ローカルWindows側）

## ⚠️ 重要：ローカル（Windows）側で実行してください

VPS側ではなく、**ローカル（Windows）の開発環境**で実行します。

---

## 手順1: Pillowをインストール（ローカル）

```powershell
# プロジェクトディレクトリに移動
cd C:\Users\SingKANA_β

# 仮想環境を有効化
.\.venv\Scripts\Activate.ps1

# Pillowをインストール
pip install Pillow
```

---

## 手順2: 元画像を準備

512x512のSiロゴ画像を用意してください。

例:
- `singkana_favicon_image.png`（ユーザーが持っている画像）
- または、他の場所にある画像のフルパス

---

## 手順3: スクリプトを実行（ローカル）

```powershell
# 仮想環境が有効化されていることを確認（プロンプトに (.venv) が表示されている）
python create_favicons.py "C:\Users\SingKANA_β\singkana_favicon_image.png"
```

または、画像がプロジェクトディレクトリにある場合：

```powershell
python create_favicons.py singkana_favicon_image.png
```

---

## 手順4: 生成されたファイルを確認

`assets\favicon\` ディレクトリに以下が生成されます：

- `favicon.ico`
- `favicon-16.png`
- `favicon-32.png`
- `apple-touch.png`

---

## 手順5: Gitにコミット＆プッシュ

```powershell
# 生成されたファイルを追加
git add assets/favicon/*.png assets/favicon/*.ico

# コミット
git commit -m "feat: Add favicon files"

# プッシュ
git push origin main
```

---

## 手順6: VPS側で反映

VPS側で `git pull` して反映：

```bash
# VPS側で実行
sudo -iu deploy bash -lc 'cd /var/www/singkana && git pull'
sudo systemctl restart singkana
```

---

## トラブルシューティング

### Pillowがインストールできない場合

```powershell
# 仮想環境を確認
python --version
where python

# 仮想環境が正しく有効化されているか確認
# プロンプトに (.venv) が表示されているはず
```

### 画像が見つからない場合

```powershell
# 画像ファイルを検索
Get-ChildItem -Path C:\Users\SingKANA_β -Filter *.png -Recurse | Select-Object FullName
```

### 別の方法：オンラインツール

Pythonを使わない場合：

1. https://realfavicongenerator.net/ を開く
2. 元画像をアップロード
3. 生成されたファイルをダウンロード
4. `assets\favicon\` に配置
5. Gitにコミット＆プッシュ
