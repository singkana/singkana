# SingKANA Webアプリ本体（Flask）
# - /               : index.html
# - /terms.html     : 利用規約
# - /privacy.html   : プライバシーポリシー
# - /singkana_core.js : 歌詞変換エンジン（フロント用 JS）
# - /api/convert    : 歌詞 → EN/KA 変換（サーバー版エンジン）
# - /api/feedback   : フィードバック保存（JSONL＋Discord）
# - /admin/feedback : フィードバック簡易ビュー

from __future__ import annotations

import os
import json
import datetime
import traceback
import html
from pathlib import Path
import urllib.request
import urllib.error

from flask import (
    Flask,
    request,
    jsonify,
    send_from_directory,
    Response,
    current_app,
)

# .env から環境変数を読む（あれば）
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # ImportError 含む
    load_dotenv = None

import singkana_engine as engine


# ===== 基本設定 =========================================================

BASE_DIR = Path(__file__).resolve().parent
APP_NAME = "SingKANA"

if load_dotenv:
    # /var/www/singkana/.env を読む（なければ何もしない）
    load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)

FEEDBACK_PATH = BASE_DIR / "docs" / "feedback.jsonl"


def _get_discord_webhook_url() -> str:
    """
    Discord Webhook URL を環境変数から取得。
    - systemd Environment= でも .env でも OK
    - 前後の空白は削る
    """
    url = os.environ.get("SINGKANA_FEEDBACK_WEBHOOK", "") or ""
    return url.strip()


# ===== 画面ルーティング =================================================


@app.route("/singkana_core.js")
def singkana_core_js() -> Response:
    """歌詞変換 JS コアを返す（UTF-8 明示）"""
    resp = send_from_directory(
        str(BASE_DIR),
        "singkana_core.js",
        mimetype="application/javascript; charset=utf-8",
    )
    resp.headers["Content-Type"] = "application/javascript; charset=utf-8"
    return resp


@app.route("/")
def index() -> Response:
    # トップページ（LP＋スタジオ一体型 index.html）
    return send_from_directory(str(BASE_DIR), "index.html")


@app.route("/terms.html")
def terms() -> Response:
    # 利用規約ページ
    return send_from_directory(str(BASE_DIR), "terms.html")


@app.route("/privacy.html")
def privacy() -> Response:
    # プライバシーポリシーページ
    return send_from_directory(str(BASE_DIR), "privacy.html")


@app.route("/favicon.ico")
def favicon() -> Response:
    # favicon があれば返す（無ければ 404 でよい）
    try:
        return send_from_directory(str(BASE_DIR), "favicon.ico")
    except Exception:
        return Response("", status=404)


# ===== API: 歌詞変換（サーバーサイドエンジン） ==========================


@app.route("/api/convert", methods=["POST"])
def api_convert() -> Response:
    """歌詞を受け取り、サーバー側エンジンで変換して返す"""

    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        data = {}

    lyrics = (
        data.get("lyrics")
        or data.get("text")
        or request.form.get("lyrics", "")
        or request.form.get("text", "")
    )

    if not lyrics:
        return jsonify({"ok": False, "error": "empty_lyrics"}), 400

    try:
        # singkana_engine 側の convertLyrics / convert_lyrics どちらにも対応
        if hasattr(engine, "convertLyrics"):
            result = engine.convertLyrics(lyrics)
        elif hasattr(engine, "convert_lyrics"):
            result = engine.convert_lyrics(lyrics)
        else:
            raise RuntimeError("singkana_engine: no convert function")
    except Exception as e:
        traceback.print_exc()
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "engine_error",
                    "detail": str(e),
                }
            ),
            500,
        )

    return jsonify({"ok": True, "result": result})


# ===== API: フィードバック保存 =========================================


def _ensure_feedback_dir() -> None:
    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)


def _post_feedback_to_discord(record: dict) -> None:
    """
    docs/feedback.jsonl に書いた record を元に、
    Discord Webhook に embed 形式で投げる。
    - URL は環境変数 SINGKANA_FEEDBACK_WEBHOOK から取得
    - URL が空なら何もせずログだけ残して終了
    """
    url = _get_discord_webhook_url()
    if not url:
        current_app.logger.info(
            "Discord webhook skipped: SINGKANA_FEEDBACK_WEBHOOK is empty"
        )
        return

    # record から必要なフィールドを抜き出し
    song = (record.get("song") or "").strip()
    line_no = record.get("lineNo") or record.get("line_no")
    en_text = (record.get("en") or "").strip()
    kana_text = (record.get("kana") or "").strip()
    note = (record.get("note") or record.get("text") or "").strip()
    error_msg = (record.get("error") or "").strip()
    engine_ver = (record.get("engine_version") or "js-core-v1.x").strip()
    ip = record.get("ip") or ""
    ts = record.get("created_at") or record.get("ts") or ""

    # Discord embed の description 行を組み立て
    desc_lines: list[str] = []
    if ts:
        desc_lines.append(f"Time: {ts}")
    if engine_ver:
        desc_lines.append(f"Engine: {engine_ver}")
    if ip:
        desc_lines.append(f"IP: {ip}")
    if desc_lines:
        desc_lines.append("")

    if song:
        desc_lines.append(f"Song: {song}")
    if line_no is not None:
        desc_lines.append(f"Line: #{line_no}")
    if en_text:
        desc_lines.append(f"EN: {en_text}")
    if kana_text:
        desc_lines.append(f"KANA: {kana_text}")
    if note:
        desc_lines.append(f"NOTE: {note}")
    if error_msg:
        desc_lines.append(f"ERROR: {error_msg}")

    embeds = []
    if desc_lines:
        embeds.append(
            {
                "title": "SingKANA Feedback",
                "description": "\n".join(desc_lines),
                "color": 0x6366F1,
            }
        )

    payload_json = json.dumps(
        {"content": "", "embeds": embeds or None},
        ensure_ascii=False,
    ).encode("utf-8")

    # どの URL / ペイロード長で投げているかログに出す
    current_app.logger.info(
        "Discord webhook POST: url_head=%s len=%d payload_len=%d",
        url[:80],
        len(url),
        len(payload_json),
    )

    req = urllib.request.Request(
        url,
        data=payload_json,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            current_app.logger.info(
                "Discord webhook response: status=%s",
                getattr(resp, "status", "unknown"),
            )
    except urllib.error.HTTPError as e:
        current_app.logger.error(
            "Discord feedback webhook failed (HTTPError): %s %s", e.code, e.reason
        )
    except Exception as e:
        current_app.logger.error(f"Discord feedback webhook failed: {e}")


@app.route("/api/feedback", methods=["POST"])
def api_feedback() -> Response:
    """
    ユーザーのフィードバックを JSONL に追記し、
    （環境変数があれば）Discord にも通知する。
    """
    try:
        payload = request.get_json(silent=True) or {}
    except Exception:
        payload = {}

    # 共通メタ
    ts = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    ua = request.headers.get("User-Agent", "")

    # 歌詞行などの情報
    song = (payload.get("song") or request.form.get("song") or "").strip()
    line_no = payload.get("lineNo") or payload.get("line_no")
    en_text = (payload.get("en") or request.form.get("en") or "").strip()
    kana_text = (payload.get("kana") or request.form.get("kana") or "").strip()

    # メインのフィードバック本文
    note = (
        payload.get("note")
        or payload.get("text")
        or request.form.get("note")
        or request.form.get("text")
        or ""
    )
    note = str(note).strip()

    error_msg = (payload.get("error") or "").strip()
    engine_ver = (payload.get("engine_version") or "js-core-v1.x").strip()
    client_side = bool(payload.get("client_side", True))

    if not (note or en_text or kana_text):
        return jsonify({"ok": False, "error": "empty_feedback"}), 400

    record = {
        "created_at": ts,
        "ip": ip,
        "ua": ua,
        "song": song,
        "lineNo": line_no,
        "en": en_text,
        "kana": kana_text,
        "note": note,
        "error": error_msg,
        "engine_version": engine_ver,
        "client_side": client_side,
        # 旧形式との互換のために残す
        "text": note,
        "meta": {
            "song": song,
            "lineNo": line_no,
            "client_side": client_side,
            "engine_version": engine_ver,
        },
    }

    # ===== JSONL へ追記 =====
    try:
        _ensure_feedback_dir()
        with FEEDBACK_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        traceback.print_exc()
        return (
            jsonify({"ok": False, "error": "write_failed", "detail": str(e)}),
            500,
        )

    # ===== Discord へ送信（設定されていれば） =====
    try:
        _post_feedback_to_discord(record)
    except Exception:
        # 通知失敗しても本体は成功扱い
        traceback.print_exc()

    return jsonify({"ok": True})


# ===== 管理用: フィードバック簡易ビュー ================================


@app.route("/admin/feedback")
def admin_feedback() -> Response:
    """
    フィードバック簡易ビュー（JSONL → HTMLテーブル）
    - 新フォーマット（created_at / en / kana / note ...）と旧フォーマット(ts/meta構造)両方に対応
    """
    entries: list[dict] = []

    if FEEDBACK_PATH.exists():
        try:
            with FEEDBACK_PATH.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        obj = {"_raw": line, "_error": "JSONDecodeError"}
                    entries.append(obj)
        except Exception as e:
            body = f"""<!DOCTYPE html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <title>SingKANA Feedback Admin</title>
    <style>
      body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
             background:#050816; color:#f5f5ff; padding:24px; }}
      .error {{ color:#ff6b81; font-weight:bold; }}
      a {{ color:#7dd3fc; }}
    </style>
  </head>
  <body>
    <h1>SingKANA Feedback Admin</h1>
    <p class="error">フィードバック読み込みエラー: {html.escape(str(e))}</p>
    <p>ファイル: {html.escape(str(FEEDBACK_PATH))}</p>
  </body>
</html>"""
            return Response(body, mimetype="text/html; charset=utf-8")

    # 新しい順に
    entries = list(reversed(entries))

    rows_html: list[str] = []
    for idx, item in enumerate(entries, start=1):
        if "_raw" in item:
            created = ""
            song = ""
            line_no = ""
            en_text = "(raw)"
            kana_text = item.get("_raw", "")
            note = item.get("_error", "")
            ip = ""
            ua = ""
        else:
            meta = item.get("meta") or {}
            created = (
                item.get("created_at")
                or item.get("ts")
                or meta.get("ts")
                or ""
            )
            song = (
                item.get("song")
                or meta.get("song")
                or ""
            )
            line_no = (
                item.get("lineNo")
                or item.get("line_no")
                or meta.get("lineNo")
                or meta.get("line_no")
                or ""
            )
            en_text = (
                item.get("en")
                or item.get("original")
                or meta.get("en")
                or ""
            )
            kana_text = (
                item.get("kana")
                or item.get("converted")
                or meta.get("kana")
                or ""
            )
            note = (
                item.get("note")
                or item.get("text")
                or meta.get("note")
                or ""
            )
            ip = item.get("ip", "")
            ua = item.get("ua", "")

        row = (
            "      <tr>"
            f"<td>{idx}</td>"
            f"<td class='ts'>{html.escape(str(created))}</td>"
            f"<td>{html.escape(str(song))}</td>"
            f"<td>{html.escape(str(line_no))}</td>"
            f"<td class='en'>{html.escape(str(en_text))}</td>"
            f"<td class='kana'>{html.escape(str(kana_text))}</td>"
            f"<td class='note'>{html.escape(str(note))}</td>"
            f"<td>{html.escape(str(ip))}</td>"
            f"<td class='ua'>{html.escape(str(ua))}</td>"
            "</tr>"
        )
        rows_html.append(row)

    html_rows = (
        "\n".join(rows_html)
        if rows_html
        else "      <tr><td colspan='9'>(no data)</td></tr>"
    )

    template = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8" />
  <title>SingKANA Feedback Admin</title>
  <style>
    body {{
      margin: 0;
      padding: 1.5rem;
      background: #020617;
      color: #e5e7eb;
      font-family: system-ui, -apple-system, BlinkMacSystemFont,
                   "Segoe UI", sans-serif, "Noto Sans JP";
    }}
    h1 {{
      margin: 0 0 0.75rem;
      font-size: 1.4rem;
    }}
    .path {{
      font-size: 0.8rem;
      color: #9ca3af;
      margin-bottom: 1rem;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      font-size: 0.8rem;
    }}
    th, td {{
      border: 1px solid #374151;
      padding: 0.35rem 0.5rem;
      vertical-align: top;
    }}
    th {{
      background: #111827;
      position: sticky;
      top: 0;
      z-index: 1;
    }}
    tr:nth-child(even) td {{
      background: #020617;
    }}
    tr:nth-child(odd) td {{
      background: #030712;
    }}
    .ts {{ white-space: nowrap; }}
    .ua {{
      max-width: 260px;
      word-break: break-all;
      color: #9ca3af;
    }}
    .en, .kana, .note {{
      max-width: 360px;
      white-space: pre-wrap;
      word-break: break-word;
    }}
  </style>
</head>
<body>
  <h1>SingKANA Feedback Admin</h1>
  <div class="path">ファイル: __PATH__ （{count}件）</div>
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>ts</th>
        <th>song</th>
        <th>line</th>
        <th>EN</th>
        <th>KANA</th>
        <th>note / error</th>
        <th>ip</th>
        <th>ua</th>
      </tr>
    </thead>
    <tbody>
__ROWS__
    </tbody>
  </table>
</body>
</html>
"""

    html_out = template.replace("__PATH__", html.escape(str(FEEDBACK_PATH)))
    html_out = html_out.format(count=len(entries))
    html_out = html_out.replace("__ROWS__", html_rows)

    return Response(html_out, mimetype="text/html; charset=utf-8")


# ===== エントリポイント（ローカル開発用） ==============================


if __name__ == "__main__":
    # 開発用サーバー（本番は gunicorn＋nginx 経由）
    app.run(host="0.0.0.0", port=5000, debug=True)
