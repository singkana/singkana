# SingKANA 実装サマリー（2026年1月14日）

## 概要
先行登録（waitlist）機能の完全実装と、セキュリティ・UX改善を実施しました。

---

## 実装内容

### 1. 先行登録API（`/api/waitlist`）の実装

#### セキュリティ機能
- **Originチェック（CSRF対策）**
  - `_origin_ok()`関数でOrigin/Refererを検証
  - 許可リスト：`https://singkana.com`, `https://www.singkana.com`, `http://127.0.0.1:5000`, `http://localhost:5000`
  - 環境変数`ALLOWED_ORIGINS`でカスタマイズ可能（カンマ区切り）
  - サブドメイン（例：`en.singkana.com`）を追加する場合は`ALLOWED_ORIGINS`に追加
  - 403エラー時は日本語メッセージ「このページからのみ登録できます。」

- **レート制限**
  - IPごとに1分間に5回まで
  - `waitlist_rate_limit`テーブルで記録
  - 1時間以上前のレコードを自動削除
  - 429エラー時は日本語メッセージ「送信が多すぎます。1分ほど待って再度お試しください。」

- **メール正規化**
  - `strip().lower()`で正規化
  - 重複判定の精度向上

- **DBユニーク制約**
  - `email`をPRIMARY KEYとして設定
  - `sqlite3.IntegrityError`をキャッチして「登録済み」として処理
  - 同時リクエスト時の競合に対応

#### エラーハンドリング
- **すべてのエラーをJSONで返す**
  - `_json_error()`関数で統一
  - `ok: false`, `code: "error_code"`, `message: "日本語メッセージ"`形式
  - HTTPステータスコードとJSONメッセージの両方でエラーを伝達

- **エラーメッセージの日本語化**
  - 403: 「このページからのみ登録できます。」
  - 429: 「送信が多すぎます。1分ほど待って再度お試しください。」
  - 400: 「メールアドレスを入力してください。」「メールアドレスの形式が正しくありません。」
  - 500: 「登録に失敗しました。しばらくしてから再度お試しください。」

- **登録済みの処理**
  - 200ステータスで`{"ok": true, "already_registered": true}`を返す
  - フロント側で成功として表示（緑色）

#### メール送信機能
- **完了メールの自動送信**
  - `_send_waitlist_confirmation_email()`関数を実装
  - SMTP設定は環境変数で管理
  - テキスト版とHTML版の両方を含むマルチパートメール
  - **メール送信失敗でも登録は成功（ログに記録）**

- **SMTP設定（環境変数）**
  ```bash
  SMTP_ENABLED=1
  SMTP_HOST=smtp.gmail.com
  SMTP_PORT=587
  SMTP_USER=singkana.official@gmail.com
  SMTP_PASSWORD=アプリパスワード
  SMTP_FROM=singkana.official@gmail.com
  ```

- **運用上の注意**
  - **SMTPは任意機能**。`SMTP_ENABLED=0`でも登録機能は正常動作
  - GmailのSMTP（アプリパスワード）は突然弾かれることがある
  - **本番ではSendGrid/Mailgun等の外部メールプロバイダへの差し替えを推奨**
  - ログには「SMTP disabled」または「SMTP failed」が明確に記録される

---

### 2. 利用規約・プライバシーポリシーの実装

#### ファイル作成
- `terms.html` - 利用規約（ダークテーマ対応）
- `privacy.html` - プライバシーポリシー（ダークテーマ対応）

#### 内容
- **利用規約**
  - Free/Proプランの説明
  - Stripe決済に関する条項
  - 自動更新・解約について
  - 先行登録機能の説明
  - レート制限に関する禁止事項

- **プライバシーポリシー**
  - 取得する情報（メールアドレス、決済情報、ユーザーID等）
  - 情報の利用目的
  - 情報の保存期間
  - 第三者提供について（Stripe）
  - Cookieの使用目的
  - ユーザーの権利（開示・訂正・削除）
  - お問い合わせ先（singkana.official@gmail.com）

#### ルート追加
- `/terms.html` - 利用規約ページ
- `/privacy.html` - プライバシーポリシーページ

#### アンカーリンク対応
- `index.html`に`#terms`と`#privacy`セクションを追加
- ハッシュリンクで表示されるJavaScriptを実装
- `http://127.0.0.1:5000/#privacy`や`http://127.0.0.1:5000/#terms`でアクセス可能

---

### 3. フロント側の改善

#### エラーハンドリング
- HTTPステータスコードのチェック
- JSONパースエラーの適切な処理
- エラーメッセージの表示改善

#### UX改善
- **429エラー時の10秒disable**
  - 通常は2秒、429エラー時は10秒間ボタンを無効化
  - 連打防止とサーバー負荷軽減

- **登録済みの成功表示**
  - `already_registered: true`の場合、緑色で成功メッセージを表示
  - 心理的摩擦の軽減

- **SNSフォローボタンの追加**
  - 登録成功時にX（Twitter）フォローボタンを表示
  - 「Xで進捗も告知します（任意）」のメッセージ
  - モーダルは5秒後に自動クローズ（SNSボタンを見せる時間を確保）

#### リンク設計
- **フッター・モーダル内のリンクは `/terms.html` と `/privacy.html` を正とする**
  - 独立ページとして固定（DOM変更の影響を受けない）
  - `target="_blank"`で新規タブで開く
- **`#terms` / `#privacy` アンカーは内部ナビ用として補助的に利用可能**
  - LP内のスムーズスクロール用
  - ただし規約・PPは独立ページを優先

---

### 4. データベース

#### テーブル構造
- **waitlist**
  - `email` (TEXT PRIMARY KEY) - メールアドレス
  - `created_at` (TIMESTAMP) - 登録日時
  - `notified` (INTEGER DEFAULT 0) - 通知済みフラグ

- **waitlist_rate_limit**
  - `ip` (TEXT) - IPアドレス
  - `created_at` (TEXT) - リクエスト日時（ミリ秒精度で衝突回避）
  - PRIMARY KEY (ip, created_at)

#### 保存先
- 環境変数`SINGKANA_DB_PATH`で指定（デフォルト: `singkana.db`）
- VPSでは`/var/lib/singkana/singkana.db`を推奨

#### SQLite設定（WALモード）
- **WALモードを有効化**（`PRAGMA journal_mode=WAL;`）
- **同期モードをNORMALに設定**（`PRAGMA synchronous=NORMAL;`）
- これにより性能向上とロック耐性が向上（`database is locked`エラーの発生率が下がる）

#### 権限設定（重要）
- **DBディレクトリの所有者は、systemdサービスの実行ユーザーに合わせる**
- 確認方法：
  ```bash
  systemctl cat singkana | grep "^User="
  ```
- 例：`User=www-data` の場合
  ```bash
  sudo chown www-data:www-data /var/lib/singkana
  ```
- **注意**: `www-data`固定は危険。サービスの実行ユーザーが異なる場合に失敗する

---

## エラーレスポンス形式（統一）

### 成功
```json
{"ok": true, "message": "登録完了しました。準備が整い次第、優先的にご案内いたします。"}
```

### 登録済み（200）
```json
{"ok": true, "message": "既に登録済みです。案内までお待ちください。", "already_registered": true}
```

### エラー（403/429/400/500）
```json
{"ok": false, "error": "invalid_origin", "code": "invalid_origin", "message": "このページからのみ登録できます。"}
```

---

## 確認項目

### 本番環境での確認
1. **正常登録**: `200` + `{"ok": true}`
2. **登録済み**: `200` + `already_registered: true`
3. **ミス入力**: `400`（空/形式）
4. **連打**: `429`
5. **Origin事故**: `403`
6. **サーバー事故**: `500`

### DB確認コマンド
```bash
# DBファイルの確認
ls -la /var/lib/singkana/singkana.db

# 登録されたメールアドレスの確認
sqlite3 /var/lib/singkana/singkana.db "SELECT email, created_at FROM waitlist ORDER BY created_at DESC LIMIT 10;"
```

### メール送信の確認
```bash
# ログで確認
sudo journalctl -u singkana -n 100 --no-pager | grep -i "email\|smtp"
```

---

## 環境変数設定（VPS）

`/etc/singkana/secrets.env`に以下を追加：

```bash
# DB設定
SINGKANA_DB_PATH=/var/lib/singkana/singkana.db

# SMTP設定（Gmailの場合）
SMTP_ENABLED=1
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=singkana.official@gmail.com
SMTP_PASSWORD=アプリパスワード
SMTP_FROM=singkana.official@gmail.com

# Origin許可リスト（オプション）
ALLOWED_ORIGINS=https://singkana.com,https://www.singkana.com
```

---

## コミット履歴

主要なコミット：
- セキュリティ強化: 先行登録APIにレート制限・Originチェック・DBユニーク制約対応
- Originチェック修正: urlparseで正規化、www付きドメイン対応、環境変数対応
- 先行登録エラーハンドリング改善、利用規約・プライバシーポリシーをSingKANA仕様に更新
- 先行登録API: エラーメッセージを日本語化、すべてのエラーケースでJSONを返すように統一
- 先行登録改善: codeフィールド追加、429時10秒disable、already_registeredで成功表示、SNSフォローボタン追加
- 利用規約・プライバシーポリシーのルート追加、先行登録完了メール送信機能を実装
- index.htmlに#termsと#privacyのアンカーセクションを追加、ハッシュリンクで表示されるように実装

---

## 次のステップ

1. **VPSでのデプロイ**
   ```bash
   sudo -iu deploy bash -lc 'cd /var/www/singkana && git pull'
   sudo systemctl restart singkana
   ```

2. **DBディレクトリの作成と権限設定**
   ```bash
   # ディレクトリ作成
   sudo mkdir -p /var/lib/singkana
   
   # サービスの実行ユーザーを確認
   SERVICE_USER=$(systemctl cat singkana | grep "^User=" | cut -d= -f2)
   echo "Service user: $SERVICE_USER"
   
   # 実行ユーザーに合わせて権限設定
   sudo chown $SERVICE_USER:$SERVICE_USER /var/lib/singkana
   sudo chmod 755 /var/lib/singkana
   ```

3. **環境変数の設定**
   - `/etc/singkana/secrets.env`にSMTP設定を追加

4. **動作確認**
   - 先行登録フォームの動作確認
   - メール送信の確認
   - エラーメッセージの確認

---

---

## 運用上の重要事項（P0: 必須確認）

### 1. 規約・プライバシーポリシーのリンク設計
- **リンクは常に `/terms.html` / `/privacy.html` を正とする**
- アンカー（`#terms` / `#privacy`）は内部ナビ用として補助的に利用可能
- 理由：独立ページはDOM変更の影響を受けず、安定性が高い

### 2. DBファイルの権限設定
- **サービスの実行ユーザーに合わせて権限を設定すること**
- `www-data`固定は危険。実行ユーザーが異なる場合に失敗する
- 確認：`systemctl cat singkana | grep "^User="`

### 3. SMTPの運用リスク
- **SMTPは任意機能**。失敗しても登録は成功する
- GmailのSMTPは突然弾かれることがある
- **本番ではSendGrid/Mailgun等の外部メールプロバイダへの差し替えを推奨**
- ログに「SMTP disabled / failed」が明確に記録される

---

## 改善提案（P1: 強く推奨）

### レート制限テーブルのPK設計
- 現在：`PRIMARY KEY (ip, created_at)` で秒精度
- 改善：ミリ秒精度を追加して同一秒内の衝突を回避（実装済み）

### データ保持期間と削除機能
- プライバシーポリシーに「削除依頼はメールで」と明記済み
- 将来的に管理コマンド `DELETE FROM waitlist WHERE email=?` を用意すると運用が楽

### サブドメイン対応
- `ALLOWED_ORIGINS`に`https://en.singkana.com`等を追加可能
- 環境変数で柔軟に対応可能

---

## 本番投入前チェックリスト（最終確認）

以下の項目がすべて **YES** なら本番投入可能です。

### 必須チェック項目

- [ ] `/var/lib/singkana` の **所有者が service user**（SQLiteはディレクトリへの書き込み権限が必須）
- [ ] `waitlist` 登録 → DBに即反映
- [ ] 登録完了メールが届く（GmailでOK、SMTP無効でも登録は成功）
- [ ] 登録済み再送 → 緑表示（200 + `already_registered: true`）
- [ ] 連打 → 429 + 日本語メッセージ
- [ ] 別ドメイン叩き → 403 + 日本語メッセージ
- [ ] `/terms.html` / `/privacy.html` が **独立ページとして読める**
- [ ] `systemctl restart singkana` 後も正常起動
- [ ] `/healthz` エンドポイントが正常応答（200）

### チェックスクリプトの実行

```bash
cd /var/www/singkana
git pull
chmod +x check_production_readiness.sh
./check_production_readiness.sh
```

このスクリプトで上記のチェック項目を自動確認できます。

### チェックスクリプトのP0検証項目（必須）

`check_production_readiness.sh`は以下の4つのP0検証を実装しています：

1. **P0-A: systemdの実行ユーザーを取得して権限を照合**
   - `systemctl show -p User singkana`で実行ユーザーを取得
   - そのユーザーが`/var/lib/singkana`の所有者か確認
   - root扱いの場合は警告

2. **P0-B: DBディレクトリに対して実際に書き込みテスト**
   - 権限の見た目だけでなく、実際に`.wal/.shm`が作れることを確認
   - サービスユーザーで`touch`テストを実行
   - SQLiteのWALモードが有効か確認

3. **P0-C: `/api/waitlist`に対してローカルからヘルスチェック**
   - 200が返るか確認
   - JSONが返るか確認
   - `ok`がbooleanであるか確認

4. **P0-D: secrets.envがsystemdに読み込まれているか**
   - `systemctl show singkana | grep EnvironmentFile`で確認
   - ログから環境変数が読み込まれているか確認

---

## 完了

先行登録機能は本番運用可能な状態になりました。
上記のP0（必須確認）3点と本番投入前チェックリストを確認すれば、安全に本番投入できます。