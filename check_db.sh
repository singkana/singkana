#!/bin/bash
# SingKANA DB確認スクリプト

echo "=== SingKANA DB確認 ==="
echo ""

# 1. 環境変数の確認
echo "1. 環境変数確認:"
echo "   SINGKANA_DB_PATH: ${SINGKANA_DB_PATH:-未設定（デフォルト: /var/www/singkana/singkana.db）}"
echo ""

# 2. 想定されるDBパスを確認
echo "2. 想定されるDBパスの確認:"
DB_PATHS=(
    "/var/www/singkana/singkana.db"
    "/var/lib/singkana/singkana.db"
    "$(pwd)/singkana.db"
)

for path in "${DB_PATHS[@]}"; do
    if [ -f "$path" ]; then
        echo "   ✓ 存在: $path"
        echo "     サイズ: $(ls -lh "$path" | awk '{print $5}')"
        echo "     更新日時: $(ls -l "$path" | awk '{print $6, $7, $8}')"
    else
        echo "   ✗ 不存在: $path"
    fi
done
echo ""

# 3. systemdの環境変数を確認
echo "3. systemdサービスの環境変数:"
if systemctl is-active --quiet singkana; then
    echo "   サービスは起動中"
    sudo systemctl show singkana | grep -E "EnvironmentFile|SINGKANA_DB_PATH" || echo "   環境変数が見つかりません"
else
    echo "   サービスは停止中"
fi
echo ""

# 4. secrets.envの確認
echo "4. secrets.envの確認:"
if [ -f "/etc/singkana/secrets.env" ]; then
    echo "   ✓ ファイル存在: /etc/singkana/secrets.env"
    if sudo grep -q "SINGKANA_DB_PATH" /etc/singkana/secrets.env; then
        echo "   ✓ SINGKANA_DB_PATHが設定されています:"
        sudo grep "SINGKANA_DB_PATH" /etc/singkana/secrets.env
    else
        echo "   ✗ SINGKANA_DB_PATHが設定されていません"
    fi
else
    echo "   ✗ ファイル不存在: /etc/singkana/secrets.env"
fi
echo ""

# 5. 実際のDBファイルを探す
echo "5. 実際のDBファイルを検索:"
find /var/www/singkana -name "*.db" -type f 2>/dev/null | head -5
find /var/lib -name "singkana.db" -type f 2>/dev/null | head -5
echo ""

# 6. アプリログでDBパスを確認
echo "6. アプリログでDB関連のエラーを確認:"
sudo journalctl -u singkana -n 50 --no-pager | grep -i "db\|database\|sqlite" | tail -5 || echo "   ログが見つかりません"
echo ""

echo "=== 確認完了 ==="
