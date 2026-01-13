#!/usr/bin/env python3
# SingKANA スタック健康診断スクリプト
# - Gunicorn / nginx / Flask / JS 配信 / Feedback をまとめてチェック

import subprocess
import textwrap
import json

ROOT_URL = "http://127.0.0.1"
LOCAL_JS = "singkana_core.js"
REMOTE_JS = f"{ROOT_URL}/singkana_core.js"
ADMIN_FEEDBACK_URL = f"{ROOT_URL}/admin/feedback"
API_FEEDBACK_URL = f"{ROOT_URL}/api/feedback"


def run(cmd, title=None, capture=False):
    """シェルコマンドを叩いて結果を表示"""
    if title:
        print("=" * 10, title, "=" * 10)
    if isinstance(cmd, str):
        shell = True
    else:
        shell = False
    try:
        result = subprocess.run(
            cmd,
            shell=shell,
            check=False,
            text=True,
            capture_output=True,
        )
    except Exception as e:
        print(f"[NG] コマンド実行エラー: {e}")
        return None

    if result.returncode == 0:
        print("[OK] returncode =", result.returncode)
    else:
        print("[NG] returncode =", result.returncode)

    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print("--- stderr ---")
        print(result.stderr.strip())

    if capture:
        return result
    return None


def curl_head(url, title):
    run(["curl", "-I", url], title=title)


def md5_of(data: bytes) -> str:
    import hashlib

    return hashlib.md5(data).hexdigest()


def check_js_diff():
    print("=" * 10, "5. JS file diff (disk vs served)", "=" * 10)

    # ローカル JS を読む
    try:
        with open(LOCAL_JS, "rb") as f:
            local_bytes = f.read()
    except FileNotFoundError:
        print(f"[NG] ローカル JS が見つかりません: {LOCAL_JS}")
        return

    # curl で nginx 経由の JS を取得
    res = subprocess.run(
        ["curl", "-s", REMOTE_JS],
        check=False,
        capture_output=True,
    )
    if res.returncode != 0:
        print("[NG] curl で JS を取得できませんでした")
        print(res.stderr.decode(errors="ignore"))
        return

    remote_bytes = res.stdout

    local_md5 = md5_of(local_bytes)
    remote_md5 = md5_of(remote_bytes)

    print("Local JS :", LOCAL_JS)
    print("  md5 =", local_md5)
    print("Remote JS:", REMOTE_JS)
    print("  md5 =", remote_md5)

    if local_md5 == remote_md5:
        print("[OK] JS on disk == JS served by nginx（キャッシュずれなし）")
    else:
        print("[NG] ローカルと配信 JS が一致していません（どこかで古いファイルを配信中）")

    # 先頭数行だけ比較表示
    print("\n----- Local JS first lines -----")
    print(b"\n".join(local_bytes.splitlines()[:10]).decode(errors="ignore"))
    print("\n----- Remote JS first lines -----")
    print(b"\n".join(remote_bytes.splitlines()[:10]).decode(errors="ignore"))


def main():
    print("========== 1. Gunicorn / systemd status (singkana.service) ==========")
    run(["systemctl", "status", "singkana.service", "-n", "20", "--no-pager"])

    print("\n========== 2. app_web.py syntax check ==========")
    # venv が有効な前提（/var/www/singkana で `source venv/bin/activate` 済み）
    run(["python", "-m", "py_compile", "app_web.py"], title="app_web.py syntax")

    print("\n========== 3. Nginx config & process ==========")
    run(["nginx", "-t"], title="nginx -t OK?")
    run(
        "ss -ltnp | grep -E '(:80|:443)'",
        title="listen on :80 / :443",
    )

    print("\n========== 4. HTTP check via 127.0.0.1 ==========")
    curl_head(f"{ROOT_URL}/", "→ root:")
    curl_head(f"{ROOT_URL}/singkana_core.js", "→ singkana_core.js header:")
    curl_head(ADMIN_FEEDBACK_URL, "→ /admin/feedback header:")
    # Feedback API は POST なので、軽くダミー POST
    print("\n---- /api/feedback 簡易 POST テスト ----")
    dummy = {
        "text": "diagnostic",
        "user_agent": "check_stack.py",
        "extra": "this is a health check entry",
    }
    run(
        ["curl", "-s", "-o", "-", "-w", "\n%{http_code}\n",
         "-H", "Content-Type: application/json",
         "-X", "POST",
         "-d", json.dumps(dummy),
         API_FEEDBACK_URL],
        title="POST /api/feedback",
    )

    check_js_diff()

    print("\n========== Done ==========")


if __name__ == "__main__":
    main()
