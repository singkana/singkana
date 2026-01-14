# 変更履歴 - 2026年1月14日

## 概要

1. **Product Hunt ローンチ設定ドキュメント作成**
2. **上下比較UI実装（Standard vs SingKANA）**
3. **waitlist → Pro 橋渡し文言追加**
4. **変換エンジン改善（母音の伸ばし方・フェイク発音ルール拡張）**

---

## 1. Product Hunt ローンチ設定

### 新規ファイル
- **`.sca/70_PRODUCT_HUNT.md`** (352行)

### 内容
- プロフィール設定（Headline 40文字以内の推奨案）
- プロダクトローンチページ設定（タグライン、説明文、FAQ）
- ローンチ戦略（タイミング、事前準備、フォローアップ）
- メッセージング（コピー）
- チェックリスト

### 推奨Headline（確定）
```
Singable kana converter for anime covers
```
（40文字）

---

## 2. 上下比較UI実装

### 目的
「変換が良くなった」ではなく「差が見えた瞬間」で刺さるUI

### 変更ファイル

#### `singkana_engine.py` (+55行)
- **`_english_to_kana_line_standard()`** 追加
  - Standard変換（最適化なし）
  - フェイク発音ルール、WORD_OVERRIDE、語尾ルールをスキップ
  - 基本的なローマ字→ひらがな変換のみ

- **`convert_lyrics_with_comparison()`** 追加
  - 比較用変換関数
  - 戻り値: `[{"en": "...", "standard": "...", "singkana": "..."}, ...]`

#### `app_web.py` (+21行)
- **`/api/convert`** レスポンス変更
  - `convert_lyrics_with_comparison()` を呼び出し
  - レスポンスに `standard` と `singkana` の両方を含める
  - 旧API互換性を維持

#### `index.html` (+143行)
- **`convertLyrics()`** 変更
  - クライアントサイド一発変換を復活（API呼び出しから変更）
  - 2段比較表示を実装

- **`createComparisonBlock()`** 追加
  - Standard/SingKANAの各ブロックを生成
  - 各ブロックに以下を含める:
    - ラベル（「一般的なカタカナ」/「歌いやすいカタカナ」）
    - コピーボタン
    - 文字数表示
    - 変換結果テキスト

### UI文言
- **Standard**: 「一般的なカタカナ（歌いやすさ最適化なし）」
- **SingKANA**: 「歌いやすいカタカナ（歌唱最適化）」
- **説明**: 「違いが一目で分かります。」

### 実装状況
- ✅ バックエンド: Standard変換関数追加
- ✅ バックエンド: APIレスポンス変更
- ✅ フロント: 2段比較表示実装
- ✅ フロント: コピーボタン、文字数、ラベル追加
- ⚠️ Standard変換: 暫定的にSingKANA版と同じ結果を表示（後で最適化なし版を実装予定）

---

## 3. waitlist → Pro 橋渡し文言追加

### 変更ファイル

#### `index_en_final.html`
- waitlistセクションに「Early users get Pro access」メッセージ追加
  ```html
  🎁 Early users get Pro access when we launch
  Natural & Precise modes, unlimited conversions, and priority support
  ```

#### `index.html`
- Proカードに「早期ユーザー特典」セクション追加
  ```html
  🎁 早期ユーザー特典
  正式リリース前に登録いただいた方には、Proアクセスを特別価格でご提供予定です。
  ```

---

## 4. 変換エンジン改善

### 変更ファイル

#### `singkana_engine.py`
- **WORD_OVERRIDE拡張** (+約50エントリ)
  - 頻出語を追加（`me`, `you`, `we`, `see`, `free`, `feel`, `real`, `dream`, `scream`, `love`, `light`, `night`, `action`, `emotion`, `passion`, `vision` など）

- **フェイク発音ルール拡張** (+約20パターン)
  - 追加の縮約形パターン（`what you` → `wachu`, `that you` → `thatchu`, `'cause` → `cuz`, `'em` → `em` など）

- **語尾ルール追加**
  - `-tion` → `-shon`（`action` → `akushon`）
  - `-sion` → `-shon`（`vision` → `vishon`）
  - `-ed` → `-d`（過去形の簡略化）
  - `-er` → `-a`（比較級の簡略化）

---

## 統計

### 変更ファイル数
- 新規: 2ファイル（`.sca/70_PRODUCT_HUNT.md`, `CHANGELOG_20260114.md`）
- 変更: 4ファイル（`singkana_engine.py`, `app_web.py`, `index.html`, `index_en_final.html`）

### コード変更量
- `singkana_engine.py`: +55行
- `app_web.py`: +21行
- `index.html`: +143行（変更）
- 合計: +219行（追加・変更）

---

## 次のステップ

### 優先度: 高
1. **Standard変換の実装**
   - クライアントサイドで最適化なし版を実装
   - WORD_OVERRIDESなし、フェイク発音ルールなし

2. **動作確認**
   - 上下比較UIの動作確認
   - 一発変換の動作確認

### 優先度: 中
3. **Product Hunt ローンチ準備**
   - スクリーンショット準備（5-10枚）
   - 動画デモ準備（オプション）
   - ローンチ日決定

4. **差分ハイライト機能**（後追い）
   - StandardとSingKANAの違いを色付け表示

---

## コミット推奨メッセージ

```bash
feat: Add comparison UI and Product Hunt setup

- Add Product Hunt launch configuration document
- Implement Standard vs SingKANA comparison UI (2-column display)
- Add waitlist→Pro bridge text to both Japanese and English LPs
- Enhance conversion engine (extend WORD_OVERRIDE, fake pronunciation rules, suffix rules)
- Restore client-side instant conversion (one-click conversion)
- Add copy button, character count, and labels to comparison blocks

Note: Standard conversion currently uses SingKANA result (to be implemented separately)
```

---

## 注意事項

1. **Standard変換**: 現在は暫定的にSingKANA版と同じ結果を表示。後で最適化なし版を実装予定。

2. **クライアントサイド変換**: 一発変換を維持するため、API呼び出しからクライアントサイド変換に戻した。

3. **Product Hunt**: ローンチ準備は `.sca/70_PRODUCT_HUNT.md` を参照。
