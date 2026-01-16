# SingKANA デプロイ手順

## ローカル → VPS デプロイフロー

### 前提条件
- GitHub Private Repo が作成済み
- VPS に SSH アクセス可能
- VPS に Git がインストール済み

---

## ローカル側（開発環境）

### 1. 変更をコミット

```bash
git add .
git commit -m "変更内容の説明"
```

### 2. GitHubにプッシュ

```bash
git push origin main
```

---

## VPS側（本番環境）

### 初回セットアップ（1回だけ）

詳細は [.sca/40_VPS_DEPLOY.md](.sca/40_VPS_DEPLOY.md) を参照。

### 通常のデプロイ（以後これだけ）

**deployユーザーで実行：**

```bash
cd /var/www/singkana
git pull
sudo systemctl restart singkana
sudo systemctl status singkana --no-pager
```

### 本番投入前チェック（推奨）

```bash
cd /var/www/singkana
bash check_production_readiness.sh
```

**8番だけ見たい場合（例）**:

```bash
cd /var/www/singkana
bash check_production_readiness.sh | sed -n '/^8\\./,/^9\\./p'
```

**それ以外は禁止。**

---

## 重要なルール

1. **VPSでは編集しない**（pullして再起動するだけ）
2. **コードはGit管理**
3. **秘密情報・DB・ログ・アップロードはGit管理しない**
4. **git pull と systemctl restart 以外は実行しない**

---

## トラブルシューティング

詳細は [.sca/40_VPS_DEPLOY.md](.sca/40_VPS_DEPLOY.md) の「トラブルシューティング」セクションを参照。
