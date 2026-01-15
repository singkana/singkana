# SingKANA Webアプリ本体（Flask）
# Canonical – DarkLP + Paywall Gate + Stripe Checkout (minimal, stable)
# Updated: 2026-01-12

from __future__ import annotations

import os
import re
import sqlite3
import datetime
import traceback
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import (
    Flask,
    request,
    jsonify,
    send_from_directory,
    Response,
    g,
)

BASE_DIR = Path(__file__).resolve().parent
APP_NAME = "SingKANA"

# ---- Optional .env (dev only) ----
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    load_dotenv = None

if load_dotenv:
    load_dotenv(BASE_DIR / ".env")

# engine
import singkana_engine as engine

app = Flask(__name__)

# --- DEBUG HOOK (local only) ---------------------------------
import logging
logging.basicConfig(level=logging.DEBUG)

app.config["PROPAGATE_EXCEPTIONS"] = True

@app.errorhandler(Exception)
def _debug_any_exception(e):
    app.logger.exception("Unhandled exception: %s", e)
    raise  # let debugger/console see the original traceback
# -------------------------------------------------------------

# -------------------------
# helpers
# -------------------------
def _utc_iso() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"

def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()

def _json_error(code: int, error: str, message: str = "", **extra: Any):
    payload: Dict[str, Any] = {"ok": False, "error": error, "code": error}
    if message:
        payload["message"] = message
    payload.update(extra)
    return jsonify(payload), code

# ---- Limits / Policy ----
MAX_JSON_BYTES = int(os.getenv("MAX_JSON_BYTES", "200000"))  # 200KB default
FREE_ALLOWED_MODES = {"basic", "natural"}  # Freeで許す display_mode

# ---- Dev Pro Override (3段ロック) ----
def _client_ip() -> str:
    """クライアントIPを取得（信頼できるproxy経由の場合のみX-Forwarded-Forを採用）"""
    remote_addr = (getattr(request, "remote_addr", None) or "").strip()
    if not remote_addr:
        return ""
    
    # 信頼できるproxyのIP（Nginx経由の場合、remote_addrは127.0.0.1やprivate subnet）
    # ローカル開発: 127.0.0.1, ::1
    # Nginx経由: 127.0.0.1, 10.x.x.x, 172.16-31.x.x, 192.168.x.x
    trusted_proxy_ips = {"127.0.0.1", "::1"}
    
    # RFC1918 private IP ranges をチェック（ipaddressモジュール使用）
    try:
        import ipaddress
        ip = ipaddress.ip_address(remote_addr)
        is_private = ip.is_private
    except (ValueError, AttributeError):
        # IPアドレスのパースに失敗した場合、文字列prefixで判定（フォールバック）
        is_private = (
            remote_addr.startswith("10.") or
            remote_addr.startswith("192.168.") or
            any(remote_addr.startswith(f"172.{i}.") for i in range(16, 32))
        )
    
    # remote_addrが信頼できるproxyのIPの場合のみ、X-Forwarded-Forを採用
    if remote_addr in trusted_proxy_ips or is_private:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            # 最初のIPを取得（複数ある場合）
            return forwarded.split(",")[0].strip()
    
    # 直接接続または信頼できないproxyの場合
    return remote_addr

def _origin_ok() -> bool:
    """Origin/Refererチェック（CSRF対策）"""
    origin = (request.headers.get("Origin") or "").strip()
    referer = (request.headers.get("Referer") or "").strip()
    
    # 許可リストを環境変数から取得（デフォルト値も設定）
    allowed_str = _env("ALLOWED_ORIGINS", "").strip()
    if allowed_str:
        allowed_origins = {x.strip() for x in allowed_str.split(",") if x.strip()}
    else:
        # デフォルト許可リスト
        allowed_origins = {
            "https://singkana.com",
            "https://www.singkana.com",
            "http://127.0.0.1:5000",
            "http://localhost:5000",
        }
        # APP_BASE_URLも追加
        base_url = _env("APP_BASE_URL", "").strip()
        if base_url:
            base_url = base_url.rstrip("/")
            allowed_origins.add(base_url)
            # www付きも追加（https://の場合）
            if base_url.startswith("https://") and not base_url.startswith("https://www."):
                www_url = base_url.replace("https://", "https://www.", 1)
                allowed_origins.add(www_url)
    
    # 1) Originがあるなら、それを厳格に見る（CORS/CSRFの基本）
    if origin:
        origin_normalized = origin.rstrip("/")
        if origin_normalized in allowed_origins:
            return True
        # 完全一致しない場合、urlparseで正規化して再チェック
        try:
            parsed = urlparse(origin)
            base = f"{parsed.scheme}://{parsed.netloc}"
            if base in allowed_origins:
                return True
        except Exception:
            pass
    
    # 2) Originが無い場合のみ、Refererで補助（ブラウザ/状況による）
    if referer:
        try:
            parsed = urlparse(referer)
            base = f"{parsed.scheme}://{parsed.netloc}"
            if base in allowed_origins:
                return True
        except Exception:
            pass
    
    # 3) 両方無い、または一致しない場合はNG
    return False

def _dev_pro_enabled() -> bool:
    """ロック1: 環境変数でDevモード許可（デフォルトOFF）"""
    return os.getenv("SINGKANA_DEV_PRO", "0") == "1"

def _dev_pro_token_ok() -> bool:
    """ロック2: 秘密トークン一致が必須（URLから）またはCookieフラグ（2回目以降）"""
    token = os.getenv("SINGKANA_DEV_PRO_TOKEN", "").strip()
    if not token:
        return False
    
    # まずURLパラメータをチェック（初回アクセス時）
    req_token = (request.args.get("dev_pro") or "").strip()
    if req_token and req_token == token:
        return True
    
    # Cookieをチェック（2回目以降: Cookieにはフラグ "1" が入っている）
    cookie_flag = (request.cookies.get(COOKIE_NAME_DEV_PRO) or "").strip()
    if cookie_flag == "1":
        # Cookieにフラグがある場合、環境変数とIP制限で再検証
        # （Cookieにトークン本体を入れないため、環境変数とIP制限で安全性を確保）
        return True
    
    return False

def _dev_pro_ip_ok() -> bool:
    """ロック3: 許可IP制限"""
    allow_ips = os.getenv("SINGKANA_DEV_PRO_ALLOW_IPS", "").strip()
    if not allow_ips:
        return False
    allow_set = {x.strip() for x in allow_ips.split(",") if x.strip()}
    client_ip = _client_ip()
    return client_ip in allow_set

def _dev_pro_host_ok() -> bool:
    """本番ドメインチェック: 本番ドメインでは常にFalse"""
    host = request.host.lower()
    if "singkana.com" in host and not host.startswith("staging.") and not host.startswith("dev."):
        return False
    return True

def is_pro_override() -> bool:
    """開発者モード（3段ロック）: すべて満たした場合のみTrue"""
    if not _dev_pro_host_ok():  # 本番ドメインチェック
        return False
    if not _dev_pro_enabled():  # ロック1: 環境変数
        return False
    if not _dev_pro_token_ok():  # ロック2: トークン一致（URLから）またはCookieフラグ（2回目以降）
        return False
    if not _dev_pro_ip_ok():  # ロック3: IP制限
        return False
    return True

def _require_json() -> Optional[Tuple[Dict[str, Any], Optional[Response]]]:
    if request.content_length is not None and request.content_length > MAX_JSON_BYTES:
        return {}, _json_error(413, "payload_too_large", "リクエストが大きすぎます。", max_bytes=MAX_JSON_BYTES)

    data = request.get_json(silent=True)
    if data is None:
        return {}, _json_error(400, "bad_json", "リクエスト形式が正しくありません。")
    if not isinstance(data, dict):
        return {}, _json_error(400, "bad_json", "リクエスト形式が正しくありません。")
    return data, None

def _get_meta(data: Dict[str, Any]) -> Dict[str, Any]:
    meta = data.get("meta")
    return meta if isinstance(meta, dict) else {}

def _get_display_mode(meta: Dict[str, Any]) -> str:
    return str(meta.get("display_mode") or "basic").strip().lower()

def _stripe_import():
    try:
        import stripe  # type: ignore
        return stripe, None
    except Exception as e:
        return None, str(e)

def _stripe_required_env() -> Dict[str, str]:
    return {
        "STRIPE_SECRET_KEY": _env("STRIPE_SECRET_KEY"),
        "STRIPE_PUBLISHABLE_KEY": _env("STRIPE_PUBLISHABLE_KEY"),
        "STRIPE_PRICE_PRO_MONTHLY": _env("STRIPE_PRICE_PRO_MONTHLY"),
        "STRIPE_PRICE_PRO_YEARLY": _env("STRIPE_PRICE_PRO_YEARLY"),
        "APP_BASE_URL": _env("APP_BASE_URL"),
    }

# ======================================================================
# Identity + DB (Sovereign Billing Layer minimal)
# ======================================================================
COOKIE_NAME_UID = "sk_uid"
COOKIE_NAME_DEV_PRO = "sk_dev_pro"  # 開発者モード用Cookie
UID_RE = re.compile(r"^sk_[0-9A-HJKMNP-TV-Z]{26}$")  # ULID base32 26 chars
COOKIE_SECURE = _env("COOKIE_SECURE", "1") == "1"     # 本番=1 / ローカルhttp検証=0
DB_PATH = _env("SINGKANA_DB_PATH", str(BASE_DIR / "singkana.db"))

def _db():
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        # SQLite WALモードを有効化（性能＆ロック耐性向上）
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        g.db = conn
    return g.db

@app.teardown_appcontext
def _close_db(exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()

def _init_db():
    conn = sqlite3.connect(DB_PATH)
    # WALモードは_db()で設定（接続生成時に1回）
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            plan TEXT NOT NULL DEFAULT 'free',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id TEXT PRIMARY KEY,
            stripe_customer_id TEXT,
            stripe_subscription_id TEXT,
            status TEXT,
            current_period_end INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS waitlist (
            email TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notified INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

_init_db()

def _send_waitlist_confirmation_email(email: str) -> bool:
    """先行登録完了メールを送信"""
    try:
        # SMTP設定を環境変数から取得
        smtp_enabled = _env("SMTP_ENABLED", "0") == "1"
        if not smtp_enabled:
            app.logger.info(f"SMTP disabled, skipping confirmation email to {email}")
            return False
        
        smtp_host = _env("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(_env("SMTP_PORT", "587"))
        smtp_user = _env("SMTP_USER", "")
        smtp_password = _env("SMTP_PASSWORD", "")
        from_email = _env("SMTP_FROM", smtp_user or "singkana.official@gmail.com")
        
        if not smtp_user or not smtp_password:
            app.logger.warning("SMTP credentials not configured, skipping email")
            return False
        
        # メール本文
        subject = "SingKANA Pro先行登録完了"
        body_text = f"""SingKANA Pro先行登録ありがとうございます！

以下のメールアドレスで先行登録を受け付けました：
{email}

準備が整い次第、Proプランの優先案内をお送りします。
今しばらくお待ちください。

---
SingKANA
https://singkana.com
"""
        body_html = f"""<html>
<head></head>
<body style="font-family: sans-serif; line-height: 1.6; color: #333;">
  <h2 style="color: #a78bfa;">SingKANA Pro先行登録完了</h2>
  <p>SingKANA Pro先行登録ありがとうございます！</p>
  <p>以下のメールアドレスで先行登録を受け付けました：</p>
  <p style="background: #f5f5f5; padding: 10px; border-radius: 4px;"><strong>{email}</strong></p>
  <p>準備が整い次第、Proプランの優先案内をお送りします。<br>今しばらくお待ちください。</p>
  <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
  <p style="color: #666; font-size: 12px;">
    SingKANA<br>
    <a href="https://singkana.com" style="color: #a78bfa;">https://singkana.com</a>
  </p>
</body>
</html>"""
        
        # メール作成
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = email
        
        part1 = MIMEText(body_text, "plain", "utf-8")
        part2 = MIMEText(body_html, "html", "utf-8")
        msg.attach(part1)
        msg.attach(part2)
        
        # SMTP送信
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        
        app.logger.info(f"Waitlist confirmation email sent to {email}")
        return True
    except Exception as e:
        app.logger.exception(f"Failed to send confirmation email to {email}: {e}")
        # メール送信失敗は登録自体は成功とする（非同期処理推奨だが、今は同期的に）
        return False

def _generate_user_id() -> str:
    # dependency: pip install ulid-py
    import ulid
    return f"sk_{ulid.new()}"

def _ensure_user_exists(conn, user_id: str):
    conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()

def _set_plan(conn, user_id: str, plan: str):
    conn.execute("UPDATE users SET plan=? WHERE user_id=?", (plan, user_id))
    conn.commit()

@app.before_request
def _identity_and_plan_bootstrap():
    try:
        # 開発者モード: URLトークンを受けたらCookieに保存してリダイレクト
        dev_pro_token = request.args.get("dev_pro", "").strip()
        if dev_pro_token:
            # トークンを検証
            expected_token = os.getenv("SINGKANA_DEV_PRO_TOKEN", "").strip()
            if expected_token and dev_pro_token == expected_token and _dev_pro_ip_ok():
                # 検証OK: Cookieにフラグ "1" を保存してリダイレクト（URLからトークンを消す）
                # 注意: Cookieにはトークン本体ではなくフラグを保存（セキュリティ強化）
                from flask import redirect, url_for
                resp = redirect(request.path or "/")
                resp.set_cookie(
                    COOKIE_NAME_DEV_PRO,
                    "1",  # トークン本体ではなくフラグを保存
                    max_age=60 * 60 * 24 * 7,  # 7日間有効
                    httponly=True,
                    samesite="Lax",
                    secure=COOKIE_SECURE,
                    path="/",  # 全ページ有効
                )
                return resp
        
        uid = request.cookies.get(COOKIE_NAME_UID)
        if (not uid) or (not UID_RE.match(uid)):
            uid = _generate_user_id()
            g._set_uid_cookie = uid
        else:
            g._set_uid_cookie = None

        g.user_id = uid

        conn = _db()
        _ensure_user_exists(conn, uid)
        row = conn.execute("SELECT plan FROM users WHERE user_id=?", (uid,)).fetchone()
        g.user_plan = (row["plan"] if row else "free")
        
        # 開発者モード: Pro上書き（3段ロック通過時のみ）
        if is_pro_override():
            g.user_plan = "pro"
            g.dev_pro_override = True
        else:
            g.dev_pro_override = False
    except Exception as e:
        app.logger.exception("Error in _identity_and_plan_bootstrap: %s", e)
        raise

@app.after_request
def _identity_cookie_commit(resp):
    uid = getattr(g, "_set_uid_cookie", None)
    if uid:
        resp.set_cookie(
            COOKIE_NAME_UID,
            uid,
            max_age=60 * 60 * 24 * 365 * 5,
            httponly=True,
            samesite="Lax",
            secure=COOKIE_SECURE,
        )
    resp.headers["X-SingKANA-Plan"] = getattr(g, "user_plan", "free")
    
    # キャッシュ禁止ヘッダー（Pro判定が混ざる事故を防ぐ）
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    
    # Varyヘッダー: Cookieの値によってレスポンスが変わることを明示（CDN/中間キャッシュ対策）
    # 既存のVaryヘッダーがある場合は結合、ない場合は新規設定
    existing_vary = resp.headers.get("Vary", "")
    if existing_vary:
        vary_set = {v.strip() for v in existing_vary.split(",") if v.strip()}
        vary_set.add("Cookie")
        resp.headers["Vary"] = ", ".join(sorted(vary_set))
    else:
        resp.headers["Vary"] = "Cookie"
    
    return resp

@app.get("/dev/logout")
def dev_logout():
    """開発者モードをOFFにする（Cookie削除）"""
    # Host/IP制限を適用（外部からの嫌がらせを防ぐ）
    # is_pro_override()と同じガード条件で統一
    if not is_pro_override():
        from flask import abort
        abort(403)  # Forbidden
    
    from flask import redirect
    resp = redirect("/")
    # Cookieを削除（Max-Age=0で即時削除）
    resp.set_cookie(
        COOKIE_NAME_DEV_PRO,
        "",
        max_age=0,
        path="/",
        httponly=True,
        samesite="Lax",
        secure=COOKIE_SECURE,
    )
    return resp

@app.get("/api/me")
def api_me():
    # デバッグ用: 開発者モードの状態を確認（常に返す）
    dev_pro_env = os.getenv("SINGKANA_DEV_PRO", "0")
    debug_info = {
        "dev_pro_env_value": dev_pro_env,
        "dev_pro_enabled": dev_pro_env == "1",
        "dev_pro_token_set": bool(os.getenv("SINGKANA_DEV_PRO_TOKEN", "")),
        "dev_pro_token_value": os.getenv("SINGKANA_DEV_PRO_TOKEN", "")[:10] + "..." if os.getenv("SINGKANA_DEV_PRO_TOKEN") else "",
        "dev_pro_token_match": _dev_pro_token_ok(),
        "request_token": (request.args.get("dev_pro") or "")[:10] + "..." if request.args.get("dev_pro") else "",
        "cookie_flag": request.cookies.get(COOKIE_NAME_DEV_PRO, ""),  # Cookieにはフラグ "1" が入っている
        "client_ip": _client_ip(),
        "allowed_ips": os.getenv("SINGKANA_DEV_PRO_ALLOW_IPS", ""),
        "ip_ok": _dev_pro_ip_ok(),
        "is_pro_override": is_pro_override(),
        "dotenv_loaded": load_dotenv is not None,
    }
    
    return jsonify({
        "ok": True,
        "user_id": getattr(g, "user_id", ""),
        "plan": getattr(g, "user_plan", "free"),
        "dev_pro_override": getattr(g, "dev_pro_override", False),  # UI表示用
        "time": _utc_iso(),
        "debug": debug_info,  # デバッグ情報（常に返す）
    })

# ======================================================================
# API: 歌詞変換（Canonical）
# ======================================================================

@app.route("/api/convert", methods=["POST"])
def api_convert():
    data, err = _require_json()
    if err:
        return err

    lyrics = (data.get("text") or data.get("lyrics") or "").strip()
    if not lyrics:
        return _json_error(400, "empty_lyrics", "Lyrics text is required.")

    meta = _get_meta(data)
    display_mode = _get_display_mode(meta)

    # ★統治：planで決める（Freeはbasicのみ）
    # 開発者モードで上書きされている場合はPro扱い
    user_plan = getattr(g, "user_plan", "free")
    if user_plan != "pro" and display_mode not in FREE_ALLOWED_MODES:
        # 念のため開発者モードを再チェック（二重防御）
        if not is_pro_override():
            return _json_error(
                402,
                "payment_required",
                "This mode is available on Pro plan.",
                requested_mode=display_mode,
                required_plan="pro",
                user_plan=user_plan,
                allowed_free_modes=sorted(list(FREE_ALLOWED_MODES)),
            )

    try:
        # 上下比較UI用: standard と singkana の両方を返す
        if hasattr(engine, "convert_lyrics_with_comparison"):
            result = engine.convert_lyrics_with_comparison(lyrics)
        elif hasattr(engine, "convertLyrics"):
            # 旧API互換: 通常の変換結果を standard と singkana の両方に設定
            old_result = engine.convertLyrics(lyrics)
            result = [
                {"en": item.get("en", ""), "standard": item.get("kana", ""), "singkana": item.get("kana", "")}
                for item in old_result
            ]
        elif hasattr(engine, "convert_lyrics"):
            # 旧API互換: 通常の変換結果を standard と singkana の両方に設定
            old_result = engine.convert_lyrics(lyrics)
            result = [
                {"en": item.get("en", ""), "standard": item.get("kana", ""), "singkana": item.get("kana", "")}
                for item in old_result
            ]
        else:
            result = [{"en": lyrics, "standard": lyrics, "singkana": lyrics}]
    except Exception as e:
        traceback.print_exc()
        return _json_error(
            500,
            "engine_error",
            "Conversion failed.",
            detail=str(e),
        )

    return jsonify({"ok": True, "result": result})

# --- Romaji (Phase 1 MVP) -----------------------------------------------
from pykakasi import kakasi  # noqa: E402

# pykakasi v3 API (setMode/getConverter deprecated)
_kks = kakasi()

def to_romaji(text: str) -> str:
    """Convert Japanese text to romaji while preserving line breaks."""
    lines = text.splitlines()
    out = []
    for line in lines:
        if not line.strip():
            out.append("")
            continue
        # v3 API: convert() returns List[Dict[str, str]]
        # Each dict contains 'orig', 'hira', 'kana', 'hepburn', etc.
        result = _kks.convert(line)
        # Join hepburn values, preserving spaces from original text
        romaji = ''.join(r.get('hepburn', r.get('orig', '')) for r in result)
        out.append(romaji.strip())
    return "\n".join(out)

@app.route("/api/romaji", methods=["POST"])
def api_romaji():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()

    if not text:
        return jsonify({"ok": False, "error": "empty_text"}), 400

    return jsonify({"ok": True, "romaji": to_romaji(text)})

# ======================================================================
# Billing: config + checkout + webhook
# ======================================================================

@app.get("/api/billing/config")
def api_billing_config():
    envs = _stripe_required_env()
    required_keys = list(envs.keys())
    present = {k: bool(envs[k]) for k in required_keys}

    publishable_key = envs["STRIPE_PUBLISHABLE_KEY"] if present["STRIPE_PUBLISHABLE_KEY"] else ""

    return jsonify({
        "ok": True,
        "required_env": required_keys,
        "present": present,
        "publishable_key_present": present["STRIPE_PUBLISHABLE_KEY"],
        "publishable_key": publishable_key,
        "price_pro_month_present": present["STRIPE_PRICE_PRO_MONTHLY"],
        "price_pro_year_present": present["STRIPE_PRICE_PRO_YEARLY"],
        "app_base_url": envs["APP_BASE_URL"],
        "server_time": _utc_iso(),
    })

@app.post("/api/billing/webhook")
def stripe_webhook():
    # Stripe署名検証
    secret = _env("STRIPE_WEBHOOK_SECRET")
    if not secret:
        return _json_error(500, "webhook_not_configured", "STRIPE_WEBHOOK_SECRET is missing.")

    stripe, import_err = _stripe_import()
    if stripe is None:
        return _json_error(501, "stripe_sdk_missing", "stripe package is not installed.", detail=import_err)

    payload = request.get_data()
    sig = request.headers.get("Stripe-Signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig, secret)
    except Exception as e:
        return _json_error(400, "bad_webhook", "Invalid webhook signature or payload.", detail=str(e))

    # まずは「届いた」証拠を残す
    try:
        etype = event.get("type")
        eid = event.get("id")
        app.logger.info("stripe_webhook received type=%s id=%s", etype, eid)
    except Exception:
        pass

    # --- minimal handling ---
    etype = event.get("type")

    # 1) 決済完了（最短でProへ）
    if etype == "checkout.session.completed":
        session = event["data"]["object"]

        user_id = (
            session.get("client_reference_id")
            or (session.get("metadata") or {}).get("user_id")
        )

        customer_id = session.get("customer")
        subscription_id = session.get("subscription")

        if user_id:
            conn = _db()
            _set_plan(conn, user_id, "pro")
            conn.execute(
                """
                INSERT INTO subscriptions
                  (user_id, stripe_customer_id, stripe_subscription_id, status, current_period_end)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                  stripe_customer_id=excluded.stripe_customer_id,
                  stripe_subscription_id=excluded.stripe_subscription_id,
                  status=excluded.status,
                  current_period_end=excluded.current_period_end,
                  updated_at=CURRENT_TIMESTAMP
                """,
                (user_id, customer_id, subscription_id, "active", None),
            )
            conn.commit()

    # 2) 解約・失効（安全側に倒してfreeへ）
    elif etype in ("customer.subscription.deleted", "customer.subscription.paused"):
        sub = event["data"]["object"]
        user_id = (sub.get("metadata") or {}).get("user_id")
        if user_id:
            conn = _db()
            _set_plan(conn, user_id, "free")
            conn.execute(
                """
                INSERT INTO subscriptions
                  (user_id, stripe_subscription_id, status, current_period_end)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                  stripe_subscription_id=excluded.stripe_subscription_id,
                  status=excluded.status,
                  current_period_end=excluded.current_period_end,
                  updated_at=CURRENT_TIMESTAMP
                """,
                (user_id, sub.get("id"), sub.get("status"), None),
            )
            conn.commit()

    return jsonify({"ok": True})

@app.route("/api/waitlist", methods=["POST"])
def api_waitlist():
    """先行登録（メールアドレス受付）"""
    # Originチェック（CSRF対策）
    if not _origin_ok():
        origin = request.headers.get("Origin", "")
        referer = request.headers.get("Referer", "")
        app.logger.warning(f"Waitlist: Invalid origin/referer - Origin: {origin}, Referer: {referer}")
        return _json_error(403, "invalid_origin", "このページからのみ登録できます。")
    
    # レート制限（IPごと、1分に5回まで）
    client_ip = _client_ip()
    if client_ip:
        try:
            conn = _db()
            # レート制限テーブルを確実に作成
            conn.execute("""
                CREATE TABLE IF NOT EXISTS waitlist_rate_limit (
                    ip TEXT,
                    created_at TEXT,
                    PRIMARY KEY (ip, created_at)
                )
            """)
            
            now = datetime.datetime.now()
            one_min_ago = now - datetime.timedelta(minutes=1)
            
            # 過去1分間のリクエスト数をカウント
            try:
                count = conn.execute("""
                    SELECT COUNT(*) FROM waitlist_rate_limit 
                    WHERE ip = ? AND created_at > ?
                """, (client_ip, one_min_ago.isoformat())).fetchone()[0]
            except Exception:
                # テーブルが存在しない場合など
                count = 0
            
            if count >= 5:
                return _json_error(429, "rate_limited", "送信が多すぎます。1分ほど待って再度お試しください。", retry_after=60)
            
            # レート制限テーブルに記録（ミリ秒精度で衝突を回避）
            import time
            now_iso = now.isoformat() + f".{int(time.time() * 1000) % 1000:03d}"
            conn.execute("INSERT INTO waitlist_rate_limit (ip, created_at) VALUES (?, ?)", 
                        (client_ip, now_iso))
            # 古いレコードを削除（1時間以上前）
            one_hour_ago = now - datetime.timedelta(hours=1)
            conn.execute("DELETE FROM waitlist_rate_limit WHERE created_at < ?", 
                        (one_hour_ago.isoformat(),))
            conn.commit()
        except Exception as e:
            app.logger.warning(f"Rate limit tracking failed: {e}")
            # レート制限の記録に失敗しても続行（ただしログに記録）
    
    data, err = _require_json()
    if err:
        # _require_jsonは既にJSONエラーを返すが、念のため確認
        return err
    
    # メール正規化（strip + lower）
    email = (data.get("email") or "").strip().lower()
    if not email:
        return _json_error(400, "empty_email", "メールアドレスを入力してください。")
    
    # メールアドレスの形式チェック（簡易）
    if "@" not in email or "." not in email.split("@")[1]:
        return _json_error(400, "invalid_email", "メールアドレスの形式が正しくありません。")
    
    try:
        conn = _db()
        # 重複チェック（DBのUNIQUE制約も効くが、事前チェックでUX向上）
        existing = conn.execute("SELECT email FROM waitlist WHERE email=?", (email,)).fetchone()
        if existing:
            return jsonify({"ok": True, "message": "既に登録済みです。案内までお待ちください。", "already_registered": True})
        
        # 登録（DBのUNIQUE制約で最終防御）
        conn.execute("INSERT INTO waitlist (email) VALUES (?)", (email,))
        conn.commit()
        
        # 完了メールを送信（非同期推奨だが、今は同期的に。失敗しても登録は成功）
        try:
            _send_waitlist_confirmation_email(email)
        except Exception as e:
            app.logger.warning(f"Email sending failed (registration succeeded): {e}")
        
        return jsonify({"ok": True, "message": "登録完了しました。準備が整い次第、優先的にご案内いたします。"})
    except sqlite3.IntegrityError:
        # UNIQUE制約違反（同時リクエストなど）
        return jsonify({"ok": True, "message": "既に登録済みです。案内までお待ちください。", "already_registered": True})
    except Exception as e:
        app.logger.exception("Waitlist registration failed: %s", e)
        return _json_error(500, "registration_failed", "登録に失敗しました。しばらくしてから再度お試しください。")

@app.post("/api/billing/checkout")
def api_billing_checkout():
    data, err = _require_json()
    if err:
        return err

    plan = str(data.get("plan") or "pro_month").strip().lower()

    envs = _stripe_required_env()
    secret = envs["STRIPE_SECRET_KEY"]
    base = (envs["APP_BASE_URL"] or "https://singkana.com").rstrip("/")

    if plan in ("pro_month", "pro_monthly", "month", "monthly"):
        price_id = envs["STRIPE_PRICE_PRO_MONTHLY"]
    elif plan in ("pro_year", "pro_yearly", "year", "yearly", "annual"):
        price_id = envs["STRIPE_PRICE_PRO_YEARLY"]
    else:
        return _json_error(400, "bad_plan", "Invalid plan.", plan=plan)

    success_url = _env("STRIPE_SUCCESS_URL", f"{base}/?checkout=success")
    cancel_url  = _env("STRIPE_CANCEL_URL",  f"{base}/?checkout=cancel")

    missing = []
    if not secret: missing.append("STRIPE_SECRET_KEY")
    if not envs["APP_BASE_URL"]: missing.append("APP_BASE_URL")
    if plan.startswith("pro_month") and not envs["STRIPE_PRICE_PRO_MONTHLY"]: missing.append("STRIPE_PRICE_PRO_MONTHLY")
    if plan.startswith("pro_year") and not envs["STRIPE_PRICE_PRO_YEARLY"]: missing.append("STRIPE_PRICE_PRO_YEARLY")

    if missing:
        return _json_error(
            400,
            "stripe_not_configured",
            "Stripe env is missing.",
            missing=missing,
            plan=plan,
        )

    stripe, import_err = _stripe_import()
    if stripe is None:
        return _json_error(501, "stripe_sdk_missing", "stripe package is not installed.", detail=import_err)

    try:
        stripe.api_key = secret

        # user_id をStripeへ紐付け（Webhookで取り出すための鍵）
        uid = getattr(g, "user_id", "")

        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            allow_promotion_codes=True,
            client_reference_id=uid,
            metadata={"user_id": uid},
        )
        return jsonify({"ok": True, "url": session.url, "id": session.id, "plan": plan})
    except Exception as e:
        traceback.print_exc()
        return _json_error(500, "stripe_error", "Failed to create checkout session.", detail=str(e))

# ======================================================================
# Static files / Screens
# ======================================================================
@app.get("/")
def index() -> Response:
    try:
        return send_from_directory(str(BASE_DIR), "index.html")
    except Exception as e:
        app.logger.exception("Error serving index.html: %s", e)
        raise

@app.get("/singkana_core.js")
def singkana_core_js() -> Response:
    resp = send_from_directory(
        str(BASE_DIR),
        "singkana_core.js",
        mimetype="application/javascript; charset=utf-8",
    )
    resp.headers["Content-Type"] = "application/javascript; charset=utf-8"
    return resp

@app.get("/paywall_gate.js")
def serve_paywall_gate_js():
    return send_from_directory(str(BASE_DIR), "paywall_gate.js")

@app.get("/assets/<path:filename>")
def assets_files(filename):
    return send_from_directory(str(BASE_DIR / "assets"), filename)

@app.get("/terms.html")
def terms_html():
    """利用規約ページ"""
    try:
        return send_from_directory(str(BASE_DIR), "terms.html")
    except Exception as e:
        app.logger.exception("Error serving terms.html: %s", e)
        return _json_error(500, "file_not_found", "利用規約ページが見つかりません。"), 500

@app.get("/privacy.html")
def privacy_html():
    """プライバシーポリシーページ"""
    try:
        return send_from_directory(str(BASE_DIR), "privacy.html")
    except Exception as e:
        app.logger.exception("Error serving privacy.html: %s", e)
        return _json_error(500, "file_not_found", "プライバシーポリシーページが見つかりません。"), 500

# ======================================================================
# Health
# ======================================================================
@app.get("/healthz")
def healthz():
    return jsonify({
        "ok": True,
        "service": APP_NAME,
        "time": _utc_iso(),
    })

@app.get("/health")
def health():
    """Health check endpoint with sanitized status (no secrets exposed)."""
    import os
    
    checks = {}
    status = "ok"
    http_status = 200
    
    # DB path configuration check
    db_path = _env("SINGKANA_DB_PATH", "")
    checks["db_path_configured"] = bool(db_path)
    
    # DB file existence check
    db_exists = False
    if db_path:
        db_exists = os.path.exists(db_path)
    checks["db_exists"] = db_exists
    
    # DB writability check
    db_writable = False
    if db_exists:
        db_writable = os.access(db_path, os.W_OK)
    checks["db_writable"] = db_writable
    
    # API keys presence check (values not exposed)
    checks["openai_key_present"] = bool(_env("OPENAI_API_KEY", ""))
    checks["stripe_key_present"] = bool(_env("STRIPE_SECRET_KEY", ""))
    
    # Critical checks: if any fails, return 500
    critical_checks = [
        checks["db_path_configured"],
        checks["db_exists"],
        checks["db_writable"],
    ]
    
    if not all(critical_checks):
        status = "degraded"
        http_status = 500
    
    response = {
        "status": status,
        "app": APP_NAME,
        "env": "prod",  # VPS固定
        "checks": checks,
    }
    
    return jsonify(response), http_status
