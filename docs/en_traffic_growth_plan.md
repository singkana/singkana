# en.singkana.com 流入改善プラン（2026-04-26）

## 0. 現状の課題（ページ観察ベース）

- メイン訴求が「体験価値（自然に歌える）」中心で、検索意図に直結するクエリ（例: `anime song romaji converter`）ごとの専用導線が弱い。
- `/en/` のトップ1ページで説明が完結しており、**検索流入の受け皿となる下層ページ**が不足している。
- Waitlist CTA はあるが、流入初期で最も強い「今すぐ使える」導線（ユースケース別LP）を増やす余地がある。

## 1. 最優先（2週間）: 既存ページのCVR改善

### 1-1. ファーストビューを「検索語」に寄せる

- H1直下に、以下のような検索語対応コピーを追加。
  - `Anime Song Romaji Converter`
  - `Japanese Lyrics Pronunciation Guide for Singers`
- CTAの文言をA/Bテスト。
  - A: Try Romaji Free
  - B: Convert Japanese Lyrics Free
  - C: Generate Singable Romaji

### 1-2. 不安解消ブロック追加

- 「できること / できないこと」を明示。
  - できる: 歌唱向けローマ字・発音ガイド
  - できない: 音源同期・カラオケタイミング
- 返金/無料枠/商用利用可否などのFAQを折りたたみで追加。

### 1-3. コンバージョン計測の整備（必須）

- GTMで最低限以下イベントを実装。
  - `cta_try_romaji_click`
  - `cta_tester_apply_click`
  - `waitlist_submit_success`
  - `scroll_50` / `scroll_90`
- 週次で見る指標。
  - LP→ツール遷移率
  - Waitlist登録率
  - 国別CVR（US/PH/ID/BRなど）

## 2. 中優先（1〜2か月）: SEO流入チャネルの拡張

### 2-1. 下層ページ（プログラマティックSEOではなく高品質手動）を作る

以下の3クラスタで、まず各5本（合計15本）公開。

1) **Intent: 変換ツール探し**
- Best anime lyrics romaji converter
- How to read Japanese song lyrics in romaji

2) **Intent: 発音学習**
- Japanese pronunciation for singers
- Long vowels / small tsu / ん の歌唱時ルール

3) **Intent: クリエイター用途**
- Romaji lyrics for covers on YouTube/TikTok
- Copyright-safe workflow (lyrics handling policy)

### 2-2. テンプレ構成（全記事共通）

- 結論（3行）
- つまずきポイント（例: し/shi, つ/tsu）
- 歌唱向けにどう崩すか
- 実例（短文）
- ツールCTA
- FAQ + 内部リンク

### 2-3. 技術SEO

- `FAQPage` / `HowTo` の構造化データを該当ページへ。
- XMLサイトマップを `/en/` 配下ページを含めて更新。
- ページごとに canonical / hreflang を厳密化。

## 3. 高インパクト（並行）: “検索以外”の再現性ある流入

### 3-1. UGC導線（TikTok / Shorts）

- 15〜30秒のフォーマットを固定。
  - 冒頭3秒: 原文→読めない問題
  - 中盤: SingKANA変換結果
  - 終盤: 歌ってみた1フレーズ
- 1動画1CTA（固定）: `Try the converter in bio`

### 3-2. コラボ導線

- マイクロインフルエンサー（登録者1万〜20万）に「1曲だけ無償支援」。
- 提供価値は「歌詞の歌唱用ローマ字整形 + 発音コメント」。
- 成果指標: 概要欄クリック率、7日後の指名検索増加。

### 3-3. コミュニティ配布

- Reddit/Discord向けに「教育コンテンツ型投稿」を実施。
- 直接宣伝ではなく、`JP lyrics pronunciation cheat sheet` を配布し自然導線化。

## 4. 90日KPI（目安）

- Organic sessions: +80%
- `/en/` → `/en/romaji/` クリック率: 12% → 20%
- Waitlist CVR: 2.5% → 5%
- 指名検索（SingKANA）: +50%

## 5. 実行順（迷ったらこの順）

1. 計測イベント実装（GTM）
2. FVコピーA/Bテスト
3. FAQ追加
4. 検索意図別の下層記事15本
5. UGC週3本運用
6. マイクロインフルエンサー月5件

## 6. すぐ着手するタスク（今週）

- [ ] `/en/` ヒーローに検索意図コピーを1行追加
- [ ] CTA文言を2案追加し実験フラグ化
- [ ] FAQセクション新設（5問）
- [ ] GTMイベント4種追加
- [ ] 記事3本（converter / pronunciation / cover workflow）を公開

