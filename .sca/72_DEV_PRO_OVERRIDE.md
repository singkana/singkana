# 開発者モード（Dev Pro Override）

## 概要

開発者がProの体験を自分で踏めるようにする「開発者モード」機能。
本番Stripe課金はそのまま維持しつつ、開発者だけProモードを強制ONできる。

**セキュリティ強化（v2）**：
- **URLトークン → Cookie移行**: 初回アクセス時にCookieに保存し、URLからトークンを消去
- **キャッシュ禁止**: Pro判定が混ざる事故を防止
- **本番環境での物理的無効化**: 本番ドメインでは常に無効化
- **ログでのトークンマスク**: デバッグ情報でトークンをマスク
- **Cookie属性の完全設定**: HttpOnly, SameSite, Path, Secure
- **Dev Pro OFFエンドポイント**: `/dev/logout` で即座に無効化

**3段ロックで安全設計**：
1. 環境変数でDevモード許可（デフォルトOFF）
2. 秘密トークン一致が必須（URLまたはCookieから）
3. 許可IP制限（推奨）
4. **本番ドメインチェック**（追加）

---

## 設定手順

### 1. `.env` ファイルに追加（ローカル開発）

```bash
# 開発者モード有効化（ローカル開発用）
SINGKANA_DEV_PRO=1

# 秘密トークン（長いランダム文字列を生成）
SINGKANA_DEV_PRO_TOKEN=your-super-secret-random-token-here-min-32-chars

# 許可IP（カンマ区切り、127.0.0.1 と ::1 はローカル）
SINGKANA_DEV_PRO_ALLOW_IPS=127.0.0.1,::1
```

### 2. トークン生成（推奨）

```bash
# Pythonで生成
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# または openssl
openssl rand -hex 32
```

### 3. 本番環境での注意

**本番では必ず `SINGKANA_DEV_PRO=0` または未設定にすること。**

さらに、本番ドメイン（`singkana.com`）では、環境変数の設定に関わらず開発者モードは自動的に無効化されます。

staging環境でのみ有効化することを推奨。

---

## 使い方

### ローカル開発

1. `.env` ファイルに上記設定を追加
2. アプリを再起動
3. ブラウザで以下のURLにアクセス（初回のみ）：

```
http://127.0.0.1:5000/?dev_pro=your-super-secret-random-token-here
```

**重要**: 初回アクセス時に自動的にCookieに保存され、URLからトークンが消去されます（302リダイレクト）。以降はCookieだけで判定されるため、URLにトークンを含める必要はありません。

### Dev Pro OFF（開発者モードを無効化）

以下のURLにアクセスすると、開発者モードのCookieが削除され、Freeプランに戻ります：

```
http://127.0.0.1:5000/dev/logout
```

### VPS（本番）での使用

**⚠️ 本番環境では開発者モードは自動的に無効化されます。**

本番ドメイン（`singkana.com`）では、`is_pro_override()` が常に `False` を返します。

staging環境でのみ使用することを推奨します。

---

## 動作確認

### 1. 開発者モードバッジの表示

ヘッダーに「開発者モードバッジ」が表示されれば成功。

### 2. Pro機能の利用

- `/api/me` で `plan: "pro"` が返る
- `/api/convert` で `natural` / `precise` モードが使える
- UIでPro専用機能が有効化される

### 3. Cookieの確認

ブラウザの開発者ツール（F12）→ Application → Cookies で以下を確認：

- `sk_dev_pro` Cookieが存在する
- `HttpOnly` 属性が設定されている
- `SameSite=Lax` が設定されている
- `Path=/` が設定されている
- ローカルHTTPの場合: `Secure` は `False`
- 本番HTTPSの場合: `Secure` は `True`

### 4. キャッシュ禁止ヘッダーの確認

ネットワークタブで `/api/me` または `/api/convert` のレスポンスヘッダーを確認：

- `Cache-Control: no-store, no-cache, must-revalidate, private`
- `Pragma: no-cache`
- `Expires: 0`

---

## セキュリティ注意事項

### ✅ 安全な運用

- **本番では `SINGKANA_DEV_PRO=0` または未設定**
- **トークンは長いランダム文字列（32文字以上推奨）**
- **IP制限を必ず設定（`127.0.0.1` のみでも可）**
- **トークンは `.env` に保存（Git管理外）**
- **Cookieは `HttpOnly` で設定（JSから読めない）**
- **本番ドメインでは自動的に無効化**

### ⚠️ 危険な設定

- ❌ 本番で `SINGKANA_DEV_PRO=1` を設定
- ❌ トークンを短くする（例: `test123`）
- ❌ IP制限を設定しない（`SINGKANA_DEV_PRO_ALLOW_IPS` を空にする）
- ❌ トークンをGitにコミット
- ❌ Cookieに `HttpOnly` を付けない

---

## 実装詳細

### セキュリティ強化（v2）

#### 1. URLトークン → Cookie移行

- **初回アクセス**: `/?dev_pro=TOKEN` でアクセス
- **検証**: サーバーで3段ロックを通過した場合、Cookieに保存
- **リダイレクト**: 302で `/?` にリダイレクト（URLからトークンを消去）
- **以降**: Cookieだけで判定（URLにトークンは不要）

これにより、以下への漏洩リスクを削減：
- ブラウザ履歴
- リファラ（外部リンク）
- 解析ツール（GA等）
- スクリーンショット共有

#### 2. キャッシュ禁止

すべてのAPIレスポンスに以下のヘッダーを追加：

```
Cache-Control: no-store, no-cache, must-revalidate, private
Pragma: no-cache
Expires: 0
```

**注意**: 各ヘッダーは個別に設定（連結しない）

これにより、FreeユーザーがProレスポンスを受ける事故を防止。

#### 3. 本番環境での物理的無効化

```python
def is_pro_override() -> bool:
    # 本番ドメインでは常にFalse
    host = request.host.lower()
    if "singkana.com" in host and not host.startswith("staging.") and not host.startswith("dev."):
        return False
    # 以下、3段ロック...
```

本番ドメインでは、環境変数の設定に関わらず開発者モードは無効化されます。

#### 4. ログでのトークンマスク

デバッグ情報では、トークンは最初の10文字のみ表示：

```python
"dev_pro_token_value": token[:10] + "..."
"request_token": req_token[:10] + "..."
"cookie_token": cookie_token[:10] + "..."
```

#### 5. Cookie属性の完全設定

```python
resp.set_cookie(
    COOKIE_NAME_DEV_PRO,
    dev_pro_token,
    max_age=60 * 60 * 24 * 7,  # 7日間有効
    httponly=True,              # JSから読めない
    samesite="Lax",             # CSRF対策
    secure=COOKIE_SECURE,       # HTTPSのときだけ（ローカルHTTPではFalse）
    path="/",                   # 全ページ有効
)
```

#### 6. Dev Pro OFFエンドポイント

`/dev/logout` にアクセスすると、開発者モードのCookieが削除され、Freeプランに戻ります：

```python
@app.get("/dev/logout")
def dev_logout():
    resp = redirect("/")
    resp.set_cookie(
        COOKIE_NAME_DEV_PRO,
        "",
        max_age=0,  # 即時削除
        path="/",
        httponly=True,
        samesite="Lax",
        secure=COOKIE_SECURE,
    )
    return resp
```

### 3段ロックの仕組み

```python
def is_pro_override() -> bool:
    """開発者モード（3段ロック）: すべて満たした場合のみTrue"""
    # 本番環境での物理的無効化
    host = request.host.lower()
    if "singkana.com" in host and not host.startswith("staging.") and not host.startswith("dev."):
        return False
    
    if not _dev_pro_enabled():      # ロック1: 環境変数
        return False
    if not _dev_pro_token_ok():     # ロック2: トークン一致（URLまたはCookie）
        return False
    if not _dev_pro_ip_ok():        # ロック3: IP制限
        return False
    return True
```

### IP制限のproxy対応

`_client_ip()` 関数は、Nginx経由の場合に `X-Forwarded-For` ヘッダーを優先します：

```python
def _client_ip() -> str:
    # X-Forwarded-For を優先（Nginx経由の場合）
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        # 最初のIPを取得（複数ある場合）
        return forwarded.split(",")[0].strip()
    # 直接接続の場合
    return (getattr(request, "remote_addr", None) or "").strip()
```

### 上書きのタイミング

`@app.before_request` で `g.user_plan` を上書き：

```python
# URLトークンを受けたらCookieに保存してリダイレクト
if dev_pro_token and 検証OK:
    resp = redirect("/")
    resp.set_cookie(COOKIE_NAME_DEV_PRO, token, ...)
    return resp

# 以降はCookieだけで判定
if is_pro_override():
    g.user_plan = "pro"
    g.dev_pro_override = True
```

### APIレスポンス

`/api/me` で開発者モードの状態を返す：

```json
{
  "ok": true,
  "user_id": "sk_...",
  "plan": "pro",
  "dev_pro_override": true,
  "debug": {
    "dev_pro_enabled": true,
    "dev_pro_token_match": true,
    "cookie_token": "Smf1FJf5pR...",
    "is_pro_override": true
  },
  "time": "2026-01-14T..."
}
```

---

## トラブルシューティング

### バッジが表示されない

1. `.env` ファイルが正しく読み込まれているか確認
2. URLパラメータ `?dev_pro=TOKEN` が正しいか確認
3. IPアドレスが `SINGKANA_DEV_PRO_ALLOW_IPS` に含まれているか確認
4. ブラウザのコンソールでエラーを確認
5. Cookieが正しく設定されているか確認（Application → Cookies）

### Pro機能が使えない

1. `/api/me` のレスポンスで `plan: "pro"` を確認
2. `dev_pro_override: true` を確認
3. アプリを再起動して設定を反映
4. `/dev/logout` で一度無効化してから、再度有効化

### Cookieが保存されない

1. ローカルHTTPの場合: `Secure=False` が設定されているか確認
2. ブラウザのCookie設定を確認
3. プライベートモード/シークレットモードを試す

### IP制限で弾かれる

- Nginx経由の場合、`X-Forwarded-For` ヘッダーからIPを取得
- 直接接続の場合、`request.remote_addr` を使用
- 必要に応じて `_client_ip()` 関数を調整

---

## 最終チェックリスト

以下がすべて通れば「完了」：

- ✅ 初回 `/?dev_pro=TOKEN` → **即 `/` に302**（URLから消える）
- ✅ 2回目 `/` 直叩きで **Pro継続**
- ✅ Cookieが **HttpOnly/SameSite/Path** 付き
- ✅ `/api/me` `/api/convert` のレスポンスに **no-store系ヘッダー**が載ってる
- ✅ `Host=singkana.com` だと **絶対にdev_proが効かない**
- ✅ Dev Pro OFF（`/dev/logout`）で即Freeに戻る

---

## 関連ファイル

- `app_web.py`: 開発者モードの実装
- `index.html`: 開発者モードバッジの表示
- `.env`: 設定値（Git管理外）

---

## まとめ

開発者モードは **「開発者がProの体験を自分で踏める」** ための機能。

**本番では必ず無効化**し、staging環境でのみ使用することを推奨。

3段ロック + 本番ドメインチェック + Cookie移行 + キャッシュ禁止により、設定ミスがあっても被害が出ない設計になっている。
