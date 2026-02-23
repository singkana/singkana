# SingKANA Webアプリ本体（Flask）
# Canonical – DarkLP + Paywall Gate + Stripe Checkout (minimal, stable)
# Updated: 2026-01-12

from __future__ import annotations

import os
import re
import sqlite3
import datetime
import traceback
import time
import secrets
import json
import hashlib
import hmac
import io
import html
import math
import threading
import struct
import wave
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr, formatdate, make_msgid

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
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))

# --- Logging -------------------------------------------------
import logging
logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO))

# 外部ライブラリ（Stripe/HTTP）の生ログを抑制（URLやレスポンスbodyがログに残る事故を防ぐ）
logging.getLogger("stripe").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# 本番で常時ONにすると 404/405 なども巻き込んで運用が荒れるので、
# 明示的に環境変数で有効化されたときだけ使う。
if os.getenv("FLASK_DEBUG_HOOK", "0") == "1":
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
    # timezone-aware (avoid datetime.utcnow() deprecation)
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()

def _json_error(code: int, error: str, message: str = "", **extra: Any):
    payload: Dict[str, Any] = {"ok": False, "error": error, "code": error}
    if message:
        payload["message"] = message
    payload.update(extra)
    return jsonify(payload), code

def _escape_html(text: str) -> str:
    return html.escape(text or "", quote=True)

def _render_kana_html(kana_raw: str) -> str:
    """Escape then wrap marks as spans (safe HTML only)."""
    s = _escape_html(kana_raw or "")
    out: list[str] = []
    in_elision = False
    for ch in s:
        if ch == "(":
            if not in_elision:
                in_elision = True
                out.append('<span class="mk mk-paren">(</span><span class="mk mk-eli">')
            else:
                out.append("(")
            continue
        if ch == ")":
            if in_elision:
                in_elision = False
                out.append('</span><span class="mk mk-paren">)</span>')
            else:
                out.append(")")
            continue
        if ch == "˘":
            out.append('<span class="mk mk-breath">˘</span><span class="mk-gap"></span>')
            continue
        if ch == "↑":
            out.append('<span class="mk mk-up">↑</span>')
            continue
        if ch == "↓":
            out.append('<span class="mk mk-down">↓</span>')
            continue
        if ch == "～":
            out.append('<span class="mk mk-liaison">～</span>')
            continue
        out.append(ch)
    if in_elision:
        out.append("</span>")
    return "".join(out)

def _generate_qr_data_uri(url: str) -> str:
    """Generate a QR code as a base64 data URI (SVG). Returns empty string on failure."""
    try:
        import segno
        import io
        import base64
        qr = segno.make(url, error="L")
        buf = io.BytesIO()
        qr.save(buf, kind="svg", scale=2, border=1, dark="#999")
        svg_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/svg+xml;base64,{svg_b64}"
    except Exception:
        return ""

def _render_sheet_html(title: str, artist: str, lines: list[dict[str, str]]) -> str:
    tpl_path = (BASE_DIR / "singkana_sheet.html")
    if not tpl_path.exists():
        raise FileNotFoundError("singkana_sheet.html not found")
    tpl = tpl_path.read_text(encoding="utf-8")
    if "{{#lines}}" not in tpl or "{{/lines}}" not in tpl:
        raise ValueError("Template missing lines block")
    before, rest = tpl.split("{{#lines}}", 1)
    block, after = rest.split("{{/lines}}", 1)

    # QR code for footer
    site_url = _app_base_url() or "https://singkana.com"
    qr_uri = _generate_qr_data_uri(site_url)

    header_map = {
        "{{title}}": _escape_html(title or ""),
        "{{artist}}": _escape_html(artist or ""),
        "{{qr_data_uri}}": qr_uri,
        "{{site_url}}": _escape_html(site_url),
    }
    for k, v in header_map.items():
        before = before.replace(k, v)
        after = after.replace(k, v)

    rows: list[str] = []
    for line in lines:
        orig = _escape_html((line.get("orig") or "").strip())
        kana_raw = (line.get("kana") or "").strip()
        kana_html = _render_kana_html(kana_raw)
        row = block.replace("{{orig}}", orig)
        row = row.replace("{{{kana_html}}}", kana_html)
        row = row.replace("{{kana_html}}", kana_html)
        rows.append(row)

    return before + "".join(rows) + after

# ---- Limits / Policy ----
MAX_JSON_BYTES = int(os.getenv("MAX_JSON_BYTES", "200000"))  # 200KB default

# ローマ字変換の無料制限
ROMAJI_FREE_MAX_CHARS = int(os.getenv("ROMAJI_FREE_MAX_CHARS", "500"))  # 無料プランでの最大文字数

# Coach V0（ユーザー録音のみ）
COACH_MAX_AUDIO_BYTES = int(os.getenv("COACH_MAX_AUDIO_BYTES", str(20 * 1024 * 1024)))  # 20MB
COACH_MAX_SECONDS = int(os.getenv("COACH_MAX_SECONDS", "60"))

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
            "https://en.singkana.com",
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
    if req_token and hmac.compare_digest(req_token, token):
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

def _parse_csv_set(raw: str) -> set[str]:
    return {x.strip() for x in (raw or "").split(",") if x.strip()}

def _uid_trace_enabled() -> bool:
    return os.getenv("SINGKANA_UID_TRACE", "0") == "1"

def _uid_trace_targets() -> set[str]:
    return _parse_csv_set(os.getenv("SINGKANA_UID_TRACE_TARGET_UIDS", ""))

def _uid_trace_paths() -> set[str]:
    return _parse_csv_set(os.getenv("SINGKANA_UID_TRACE_PATHS", ""))

def _uid_trace_raw_ua() -> bool:
    return os.getenv("SINGKANA_UID_TRACE_RAW_UA", "0") == "1"

def _internal_allow_uids() -> set[str]:
    return _parse_csv_set(os.getenv("SINGKANA_INTERNAL_ALLOW_UIDS", ""))

def is_internal_uid(uid: str) -> bool:
    return bool(uid) and uid in _internal_allow_uids()

def _internal_allow_ips() -> set[str]:
    return _parse_csv_set(os.getenv("SINGKANA_INTERNAL_ALLOW_IPS", ""))

def _internal_hmac_secret() -> str:
    return (os.getenv("SINGKANA_INTERNAL_HMAC_SECRET", "") or "").strip()

def _internal_sig_max_age_days() -> int:
    try:
        return int(os.getenv("SINGKANA_INTERNAL_SIG_MAX_AGE_DAYS", "90") or "90")
    except Exception:
        return 90

def _ip_allowed_for_internal(ip: str) -> bool:
    if not ip:
        return False
    allow = _internal_allow_ips()
    if not allow:
        return False
    try:
        import ipaddress
        ip_obj = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for token in allow:
        try:
            if "/" in token:
                if ip_obj in ipaddress.ip_network(token, strict=False):
                    return True
            else:
                if ip_obj == ipaddress.ip_address(token):
                    return True
        except ValueError:
            continue
    return False

def _internal_cookie_sig(uid: str, ts: int) -> str:
    secret = _internal_hmac_secret()
    if not secret:
        return ""
    msg = f"{uid}:{ts}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()

def _valid_internal_cookie(uid: str, cookie_val: str) -> bool:
    # format: v1.<ts>.<hexsig>
    if not cookie_val:
        return False
    parts = cookie_val.split(".")
    if len(parts) != 3 or parts[0] != "v1":
        return False
    try:
        ts = int(parts[1])
    except ValueError:
        return False
    if ts <= 0:
        return False
    max_days = _internal_sig_max_age_days()
    if max_days > 0 and (int(time.time()) - ts) > (max_days * 86400):
        return False
    expect = _internal_cookie_sig(uid, ts)
    if not expect:
        return False
    return hmac.compare_digest(expect, parts[2])

def is_internal_request(uid: str) -> bool:
    # internalはUID allowlist必須 + (IP allowlist または 署名cookie) の二段階
    if not is_internal_uid(uid):
        return False
    if _ip_allowed_for_internal(_client_ip()):
        return True
    cookie_val = (request.cookies.get(COOKIE_NAME_INTERNAL) or "").strip()
    return _valid_internal_cookie(uid, cookie_val)

def _log_uid_trace(stage: str, status: int | None = None) -> None:
    if not _uid_trace_enabled():
        return
    uid = getattr(g, "user_id", "") or ""
    if not uid:
        return
    targets = _uid_trace_targets()
    if targets and uid not in targets:
        return
    p = (request.path or "").strip()
    paths = _uid_trace_paths()
    if paths and p not in paths:
        return
    ua = request.headers.get("User-Agent", "") or ""
    ua_out = ua if _uid_trace_raw_ua() else hashlib.sha256(ua.encode("utf-8")).hexdigest()[:16]
    app.logger.info(
        "uid_trace stage=%s uid=%s method=%s path=%s status=%s ip=%s ua=%s",
        stage, uid, request.method, p, status if status is not None else "-", _client_ip(), ua_out
    )

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

def _effective_mode_from_plan(plan: str) -> str:
    """方針固定: Free=basic / Pro=natural"""
    return "natural" if str(plan or "").lower() == "pro" else "basic"

def _is_hard_case_lyrics(text: str) -> bool:
    """
    内部ブースト判定（V1最小版）。
    - 長文
    - 英字と日本語の混在
    - 括弧の多用
    """
    t = str(text or "")
    if len(t) > 800:
        return True
    has_ascii = re.search(r"[A-Za-z]", t) is not None
    has_jp = re.search(r"[ぁ-んァ-ン一-龯]", t) is not None
    if has_ascii and has_jp:
        return True
    if (t.count("(") + t.count("（")) > 2:
        return True
    return False

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
        "STRIPE_WEBHOOK_SECRET": _env("STRIPE_WEBHOOK_SECRET"),
        "APP_BASE_URL": _env("APP_BASE_URL"),
    }

# ======================================================================
# Identity + DB (Sovereign Billing Layer minimal)
# ======================================================================
COOKIE_NAME_UID = "sk_uid"
COOKIE_NAME_DEV_PRO = "sk_dev_pro"  # 開発者モード用Cookie
COOKIE_NAME_INTERNAL = "sk_internal"  # 内部権限署名Cookie
COOKIE_NAME_REF = "sk_ref"          # ref_code cookie（流入計測）
UID_RE = re.compile(r"^sk_[0-9A-HJKMNP-TV-Z]{26}$")  # ULID base32 26 chars
COOKIE_SECURE = _env("COOKIE_SECURE", "1") == "1"     # 本番=1 / ローカルhttp検証=0
DB_PATH = _env("SINGKANA_DB_PATH", str(BASE_DIR / "singkana.db"))
# 引き継ぎコード（ログイン無し運用のための「端末移行」）
TRANSFER_CODE_TTL_SEC = int(_env("TRANSFER_CODE_TTL_SEC", "600"))  # 10分
TRANSFER_CODE_LEN = int(_env("TRANSFER_CODE_LEN", "10"))
TRANSFER_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"  # 0/O, 1/I/L 等を除外
# One-shot PDF
SHEET_ONESHOT_JPY = int(_env("SHEET_ONESHOT_JPY", "300"))      # ¥300
SHEET_DRAFT_TTL_SEC = int(_env("SHEET_DRAFT_TTL_SEC", "1800")) # 30分
SHEET_TOKEN_TTL_SEC = int(_env("SHEET_TOKEN_TTL_SEC", "600"))  # 10分
SHEET_TOKEN_LEN = int(_env("SHEET_TOKEN_LEN", "32"))
SHEET_MAX_PARALLEL = int(_env("SHEET_MAX_PARALLEL", "2"))
_SHEET_SEM = threading.BoundedSemaphore(max(1, SHEET_MAX_PARALLEL))

# ref_code
REF_CODE_LEN = int(_env("REF_CODE_LEN", "6"))
REF_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
REF_CODE_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{4,12}$")

# UGC
UGC_RETENTION_DAYS = int(_env("UGC_RETENTION_DAYS", "7"))
UGC_STATIC_DIR = (BASE_DIR / "static" / "ugc").resolve()

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
            ref_code TEXT,
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
            cancel_at_period_end INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS transfer_codes (
            code TEXT PRIMARY KEY,
            owner_user_id TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            used_at INTEGER,
            used_by_user_id TEXT,
            used_by_ip TEXT
        )
    """)

    
    # schema migration: add cancel_at_period_end if existing DB is old
    cols = {r[1] for r in conn.execute("PRAGMA table_info(subscriptions)")}
    if "cancel_at_period_end" not in cols:
        conn.execute("ALTER TABLE subscriptions ADD COLUMN cancel_at_period_end INTEGER DEFAULT 0")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS waitlist (
            email TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notified INTEGER DEFAULT 0
        )
    """)

    # schema migration: add ref_code if existing DB is old
    user_cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    if "ref_code" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN ref_code TEXT")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_ref_code ON users(ref_code)")

    # UGC assets (generated image/scripts)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ugc_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            asset_type TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            file_path TEXT,
            text TEXT,
            created_at INTEGER NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ugc_assets_user_created ON ugc_assets(user_id, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ugc_assets_hash ON ugc_assets(content_hash)")

    # UGC posts (optional user-submitted URLs)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ugc_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            post_url TEXT NOT NULL,
            ref_code TEXT,
            status TEXT NOT NULL DEFAULT 'new',
            created_at INTEGER NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ugc_posts_created ON ugc_posts(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ugc_posts_ref_code ON ugc_posts(ref_code)")

    # events (lightweight product analytics; no PII)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            name TEXT NOT NULL,
            ref_code TEXT,
            meta_json TEXT,
            created_at INTEGER NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_name_created ON events(name, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ref_created ON events(ref_code, created_at)")

    # One-shot PDF draft + token
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sheet_drafts (
            draft_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT,
            artist TEXT,
            payload_json TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            consumed_at INTEGER,
            stripe_session_id TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sheet_drafts_user_created ON sheet_drafts(user_id, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sheet_drafts_expires ON sheet_drafts(expires_at)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sheet_pdf_tokens (
            token_hash TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            draft_id TEXT NOT NULL,
            stripe_session_id TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            used_at INTEGER,
            used_by_ip TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sheet_pdf_tokens_user ON sheet_pdf_tokens(user_id, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sheet_pdf_tokens_expires ON sheet_pdf_tokens(expires_at)")

    # GPT発音補正のキャッシュ
    conn.execute("""
        CREATE TABLE IF NOT EXISTS gpt_kana_cache (
            lyrics_hash TEXT PRIMARY KEY,
            result_json TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)

    conn.commit()
    conn.close()

_init_db()

def _now_ts() -> int:
    return int(time.time())

def _normalize_transfer_code(s: str) -> str:
    return "".join([c for c in (s or "").upper().strip() if c.isalnum()])

def _gen_transfer_code() -> str:
    return "".join(secrets.choice(TRANSFER_CODE_ALPHABET) for _ in range(max(6, TRANSFER_CODE_LEN)))

def _set_uid_cookie_on_response(resp, uid: str):
    resp.set_cookie(
        COOKIE_NAME_UID,
        uid,
        max_age=60 * 60 * 24 * 365 * 5,
        httponly=True,
        samesite="Lax",
        secure=COOKIE_SECURE,
        path="/",
    )
    return resp

def _set_ref_cookie_on_response(resp, ref_code: str):
    # ref計測用: httpOnlyではなくても良いが、最小実装としてhttpOnlyで保持（JSで読む必要なし）
    resp.set_cookie(
        COOKIE_NAME_REF,
        ref_code,
        max_age=60 * 60 * 24 * 30,  # 30日
        httponly=True,
        samesite="Lax",
        secure=COOKIE_SECURE,
        path="/",
    )
    return resp

def _normalize_ref_code(s: str) -> str:
    return "".join([c for c in (s or "").upper().strip() if c.isalnum()])

def _gen_ref_code() -> str:
    return "".join(secrets.choice(REF_CODE_ALPHABET) for _ in range(max(4, REF_CODE_LEN)))

def _ensure_ref_code(conn, user_id: str) -> str:
    row = conn.execute("SELECT ref_code FROM users WHERE user_id=?", (user_id,)).fetchone()
    cur = (row["ref_code"] if row else None)
    if cur and isinstance(cur, str) and REF_CODE_RE.match(cur):
        return cur

    # generate + ensure uniqueness
    for _i in range(20):
        code = _gen_ref_code()
        try:
            conn.execute("UPDATE users SET ref_code=? WHERE user_id=?", (code, user_id))
            conn.commit()
            # unique index enforces collision safety; but UPDATE won't throw.
            # Verify no duplicates.
            dup = conn.execute("SELECT user_id FROM users WHERE ref_code=? LIMIT 2", (code,)).fetchall()
            if len(dup) == 1 and dup[0]["user_id"] == user_id:
                return code
        except sqlite3.IntegrityError:
            continue
        except Exception:
            continue

    # last resort: deterministic-ish (still no PII)
    fallback = hashlib.sha256(user_id.encode("utf-8")).hexdigest().upper()[0:6]
    try:
        conn.execute("UPDATE users SET ref_code=? WHERE user_id=?", (fallback, user_id))
        conn.commit()
    except Exception:
        pass
    return fallback

def _ref_cookie_value() -> str:
    v = (request.cookies.get(COOKIE_NAME_REF) or "").strip().upper()
    return v if REF_CODE_RE.match(v) else ""

def _track_event(name: str, ref_code: str = "", meta: Optional[Dict[str, Any]] = None):
    # no PII, keep meta small
    try:
        now = _now_ts()
        uid = getattr(g, "user_id", "") or ""
        rc = (ref_code or "").strip().upper()
        if rc and not REF_CODE_RE.match(rc):
            rc = ""
        mj = ""
        if meta:
            # cap keys/values lightly
            safe = {}
            for k, v in meta.items():
                if not isinstance(k, str):
                    continue
                if len(k) > 64:
                    continue
                if isinstance(v, (str, int, float, bool)) or v is None:
                    sv = v
                else:
                    sv = str(v)
                if isinstance(sv, str) and len(sv) > 300:
                    sv = sv[:300]
                safe[k] = sv
            mj = json.dumps(safe, ensure_ascii=False, separators=(",", ":"))
        conn = _db()
        conn.execute(
            "INSERT INTO events (user_id, name, ref_code, meta_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (uid, name, rc or None, mj or None, now),
        )
        conn.commit()
    except Exception:
        # analytics must never break product
        pass

def _send_waitlist_confirmation_email(email: str) -> bool:
    """先行登録完了メールを送信"""
    try:
        def _is_ascii(s: str) -> bool:
            try:
                s.encode("ascii")
                return True
            except Exception:
                return False

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

        # SMTP AUTH は基本ASCII前提。非ASCIIが混ざると smtplib が UnicodeEncodeError で落ちるので、
        # ここで検知してスキップ（登録自体は成功扱い）。
        if (not _is_ascii(smtp_user)) or (not _is_ascii(smtp_password)):
            app.logger.warning(
                "SMTP credentials contain non-ASCII characters; skipping email. "
                "Check /etc/singkana/secrets.env (SMTP_USER/SMTP_PASSWORD)."
            )
            return False
        
        app.logger.info(f"Attempting to send waitlist confirmation email to {email} via {smtp_host}:{smtp_port}")
        
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
  <p style="background: #f5f5f5; padding: 10px; border-radius: 4px;"><strong>{html.escape(email)}</strong></p>
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
        # ヘッダ（Subject/From等）はASCII前提で落ちやすいので明示的にUTF-8へ
        msg["Subject"] = str(Header(subject, "utf-8"))
        # 到達率対策: Gmail SMTPなら From は SMTP_USER と一致させるのが安全（DMARC整合）
        effective_from = (smtp_user or from_email).strip()
        if smtp_user and from_email and smtp_user.strip().lower() != from_email.strip().lower():
            app.logger.warning("SMTP_FROM differs from SMTP_USER; using SMTP_USER for deliverability.")
        display_name = str(Header("SingKANA", "utf-8"))
        msg["From"] = formataddr((display_name, effective_from))
        msg["To"] = email
        msg["Reply-To"] = effective_from
        msg["Date"] = formatdate(localtime=True)
        # Message-ID はiCloud到達率で効くことがある（Gmail側でも生成されるが明示しておく）
        domain = effective_from.split("@", 1)[1] if "@" in effective_from else None
        msg["Message-ID"] = make_msgid(domain=domain)
        
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
    # ensure ref_code exists (best-effort)
    try:
        _ensure_ref_code(conn, user_id)
    except Exception:
        pass

def _set_plan(conn, user_id: str, plan: str) -> None:
    """users.plan を更新する。commit は呼び出し側で1回だけ行う（トランザクションの一貫性のため）。"""
    if is_internal_uid(user_id):
        app.logger.info("skip_plan_update_for_internal uid=%s requested_plan=%s", user_id, plan)
        return
    conn.execute("UPDATE users SET plan=? WHERE user_id=?", (plan, user_id))

def _plan_from_subscription(status: str | None, current_period_end: int | None) -> str:
    """
    単一ルール（Webhook / before_request 共通）
    - Pro: status in ("active","trialing") かつ current_period_end が存在し、かつ current_period_end > now
    - それ以外は Free（期限切れ・未払い・キャンセル・不明・None 含む）
    """
    if status not in ("active", "trialing"):
        return "free"
    if current_period_end is None:
        return "free"  # None=pro は永続Pro化事故を招くので禁止
    now = int(time.time())
    return "pro" if current_period_end > now else "free"

def _safe_int(value) -> Optional[int]:
    """Stripe由来の値を int に正規化（None/空/不正値は None）"""
    if value is None:
        return None
    try:
        s = str(value).strip()
        if s == "":
            return None
        return int(float(s))
    except Exception:
        return None

def _normalize_sheet_lines(lines: Any) -> list[dict[str, str]]:
    if not isinstance(lines, list):
        return []
    safe_lines: list[dict[str, str]] = []
    for item in lines:
        if not isinstance(item, dict):
            continue
        orig = str(item.get("orig") or "").strip()
        kana = str(item.get("kana") or "").strip()
        if not orig and not kana:
            continue
        safe_lines.append({"orig": orig, "kana": kana})
    return safe_lines

def _extract_sheet_payload(data: Dict[str, Any]) -> tuple[str, str, list[dict[str, str]], Optional[Response]]:
    title = str(data.get("title") or "").strip()
    artist = str(data.get("artist") or "").strip()
    safe_lines = _normalize_sheet_lines(data.get("lines"))
    if not safe_lines:
        return title, artist, [], _json_error(400, "bad_input", "lines is empty.")
    return title, artist, safe_lines, None

def _hash_sheet_token(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()

def _gen_sheet_token() -> str:
    raw_len = max(24, SHEET_TOKEN_LEN)
    return secrets.token_urlsafe(raw_len)

def _create_sheet_checkout_session(conn, user_id: str, title: str, artist: str, safe_lines: list[dict[str, str]]):
    envs = _stripe_required_env()
    secret = envs["STRIPE_SECRET_KEY"]
    base = (envs["APP_BASE_URL"] or "https://singkana.com").rstrip("/")
    success_url = _env("STRIPE_SHEET_SUCCESS_URL", f"{base}/?sheet_checkout=success&session_id={{CHECKOUT_SESSION_ID}}")
    cancel_url = _env("STRIPE_SHEET_CANCEL_URL", f"{base}/?sheet_checkout=cancel")
    if not secret:
        return None, _json_error(400, "stripe_not_configured", "Stripe env is missing.", missing=["STRIPE_SECRET_KEY"])

    stripe, import_err = _stripe_import()
    if stripe is None:
        return None, _json_error(501, "stripe_sdk_missing", "stripe package is not installed.", detail=import_err)

    now = _now_ts()
    expires_at = now + max(300, SHEET_DRAFT_TTL_SEC)
    draft_id = f"sd_{secrets.token_hex(12)}"
    payload = json.dumps({"title": title, "artist": artist, "lines": safe_lines}, ensure_ascii=False)

    conn.execute(
        """
        INSERT INTO sheet_drafts (draft_id, user_id, title, artist, payload_json, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (draft_id, user_id, title, artist, payload, now, expires_at),
    )
    conn.commit()

    try:
        stripe.api_key = secret
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{
                "price_data": {
                    "currency": "jpy",
                    "unit_amount": max(100, SHEET_ONESHOT_JPY),
                    "product_data": {"name": "SingKANA PDF Sheet (One-shot)"},
                },
                "quantity": 1,
            }],
            success_url=success_url,
            cancel_url=cancel_url,
            allow_promotion_codes=False,
            client_reference_id=user_id,
            metadata={
                "purpose": "sheet_pdf_oneshot",
                "draft_id": draft_id,
                "user_id": user_id,
            },
        )
        conn.execute("UPDATE sheet_drafts SET stripe_session_id=? WHERE draft_id=?", (session.id, draft_id))
        conn.commit()
        return {
            "draft_id": draft_id,
            "checkout_url": session.url,
            "checkout_id": session.id,
            "expires_at": expires_at,
            "amount_jpy": max(100, SHEET_ONESHOT_JPY),
        }, None
    except Exception as e:
        app.logger.exception("sheet checkout creation failed: %s", e)
        return None, _json_error(500, "stripe_error", "Failed to create one-shot checkout session.")

@app.before_request
def _identity_and_plan_bootstrap():
    # ---- fast path: do not touch DB for cheap endpoints ----
    # 監視/プロキシ/ブラウザが投げるHEAD/OPTIONSでDBに触る必要はない
    if request.method in ("HEAD", "OPTIONS"):
        return None

    p = (request.path or "").strip()
    if p in ("/healthz", "/robots.txt"):
        return None
    if p == "/favicon.ico":
        return None
    if p in ("/romaji", "/romaji/"):
        return None
    if p in ("/en", "/en/"):
        return None
    if p.startswith("/en/"):
        return None
    if p.startswith("/assets/"):
        return None
    if p in ("/singkana_core.js", "/paywall_gate.js", "/terms.html", "/privacy.html"):
        return None
    # /api/romaji のGET/HEADは監視/事前問い合わせ用（DB不要）
    if p == "/api/romaji" and request.method in ("GET", "HEAD"):
        return None
    # ---------------------------------------------------------
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

        # 最終安全弁: pro→free のみ。g.user_plan が pro のときだけ subscriptions を参照（条件一致時だけ更新）
        if getattr(g, "user_plan", "free") == "pro":
            sub_row = conn.execute(
                "SELECT status, current_period_end FROM subscriptions WHERE user_id=?",
                (uid,),
            ).fetchone()
            if sub_row:
                safe_plan = _plan_from_subscription(sub_row["status"], sub_row["current_period_end"])
                if safe_plan == "free":
                    g.user_plan = "free"
                    _set_plan(conn, uid, "free")
                    conn.commit()

        # ref capture: ?ref=XXXX (landing / shared links)
        try:
            ref = _normalize_ref_code(str(request.args.get("ref") or ""))
            if ref and REF_CODE_RE.match(ref):
                g._set_ref_cookie = ref
                _track_event("ref_landing", ref_code=ref)
            else:
                g._set_ref_cookie = None
        except Exception:
            g._set_ref_cookie = None
        
        # 開発者モード + 内部UID: 実行時オーバーライド（DB planは変更しない）
        internal_override = is_internal_request(uid)
        dev_override = is_pro_override()
        g.dev_pro_override = bool(internal_override or dev_override)
        g.internal_uid_override = bool(internal_override)
        if g.dev_pro_override:
            g.user_plan = "pro"
        g.effective_plan = "pro" if g.dev_pro_override else getattr(g, "user_plan", "free")

        # モード方針をここで確定（全エンドポイント共通）
        g.effective_mode = _effective_mode_from_plan(getattr(g, "effective_plan", "free"))
        _log_uid_trace("before")
    except Exception as e:
        app.logger.exception("Error in _identity_and_plan_bootstrap: %s", e)
        raise

@app.after_request
def _identity_cookie_commit(resp):
    # ---- cheap endpoints: do not add Cookie/Vary/cache-control noise ----
    # before_request でDBを触らない系（監視/静的/プローブ）は、
    # Vary: Cookie 等でキャッシュが割れたりログが汚れるのを避ける。
    p = (request.path or "").strip()
    is_cheap = (
        request.method in ("HEAD", "OPTIONS")
        or p in ("/healthz", "/robots.txt")
        or p == "/favicon.ico"
        or p in ("/romaji", "/romaji/")
        or p in ("/en", "/en/")
        or p.startswith("/en/")
        or p.startswith("/assets/")
        or p in ("/singkana_core.js", "/paywall_gate.js", "/terms.html", "/privacy.html")
        or (p == "/api/romaji" and request.method in ("GET", "HEAD"))
    )

    if is_cheap:
        # /api/romaji のHEADは監視が見るので JSON に統一
        if p == "/api/romaji" and request.method == "HEAD":
            resp.headers["Content-Type"] = "application/json; charset=utf-8"

        # JSONレスポンスのcharsetを明示（環境/ログ表示の文字化け対策）
        ct = resp.headers.get("Content-Type", "") or ""
        if ct.startswith("application/json") and "charset=" not in ct.lower():
            resp.headers["Content-Type"] = f"{ct}; charset=utf-8" if ct else "application/json; charset=utf-8"

        return resp

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
    ref = getattr(g, "_set_ref_cookie", None)
    if ref:
        _set_ref_cookie_on_response(resp, ref)
    resp.headers["X-SingKANA-Plan"] = getattr(g, "effective_plan", getattr(g, "user_plan", "free"))
    
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

    # JSONレスポンスのcharsetを明示（環境/ログ表示の文字化け対策）
    ct = resp.headers.get("Content-Type", "") or ""
    if ct.startswith("application/json") and "charset=" not in ct.lower():
        # FlaskはUTF-8前提だが、明示しておくと運用が楽
        resp.headers["Content-Type"] = f"{ct}; charset=utf-8" if ct else "application/json; charset=utf-8"

    _log_uid_trace("after", resp.status_code)
    return resp

def _app_base_url() -> str:
    base = (_env("APP_BASE_URL") or "").strip().rstrip("/")
    if base:
        return base
    # fallback: request.host_url includes trailing slash
    try:
        return (request.host_url or "").rstrip("/")
    except Exception:
        return "https://singkana.com"

def _ugc_static_url(filename: str) -> str:
    return f"{_app_base_url()}/static/ugc/{filename}"

def _ugc_cleanup_old_files():
    # best-effort cleanup; do not fail requests
    try:
        if not UGC_STATIC_DIR.exists():
            return
        cutoff = time.time() - (max(1, UGC_RETENTION_DAYS) * 86400)
        for p in UGC_STATIC_DIR.glob("*.png"):
            try:
                st = p.stat()
                if st.st_mtime < cutoff:
                    p.unlink(missing_ok=True)
            except Exception:
                continue
    except Exception:
        pass

def _pillow_import():
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore
        return Image, ImageDraw, ImageFont, None
    except Exception as e:
        return None, None, None, str(e)

def _find_font_path() -> Optional[Path]:
    # Prefer Noto Sans JP (if installed), fallback to DejaVu.
    candidates = [
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansJP-Regular.otf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansJP-Regular.otf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for p in candidates:
        try:
            if p.exists():
                return p
        except Exception:
            continue
    return None

def _ugc_render_image_1080x1920(
    hook: str,
    before_text: str,
    after_text: str,
    share_url: str,
) -> bytes:
    Image, ImageDraw, ImageFont, err = _pillow_import()
    if Image is None:
        raise RuntimeError(f"Pillow not available: {err}")

    W, H = 1080, 1920
    img = Image.new("RGB", (W, H), (11, 18, 32))
    draw = ImageDraw.Draw(img)

    # background accents
    draw.rectangle([0, 0, W, H], fill=(11, 18, 32))
    draw.ellipse([-260, -260, 520, 520], fill=(110, 65, 240))
    draw.ellipse([W - 520, 120, W + 260, 900], fill=(236, 72, 153))

    font_path = _find_font_path()
    if font_path:
        font_title = ImageFont.truetype(str(font_path), 56)
        font_h = ImageFont.truetype(str(font_path), 42)
        font_b = ImageFont.truetype(str(font_path), 34)
        font_s = ImageFont.truetype(str(font_path), 26)
        font_xs = ImageFont.truetype(str(font_path), 22)
    else:
        font_title = ImageFont.load_default()
        font_h = ImageFont.load_default()
        font_b = ImageFont.load_default()
        font_s = ImageFont.load_default()
        font_xs = ImageFont.load_default()

    # helper: wrap
    def wrap(text: str, max_chars: int) -> str:
        t = (text or "").strip()
        if not t:
            return ""
        lines = []
        for raw in t.splitlines():
            s = raw.strip()
            while len(s) > max_chars:
                lines.append(s[:max_chars])
                s = s[max_chars:]
            if s:
                lines.append(s)
        return "\n".join(lines[:8])

    hook = wrap(hook or "この歌詞、歌えない", 18)
    before_text = wrap(before_text, 24)
    after_text = wrap(after_text, 24)

    # header
    pad = 72
    draw.text((pad, 80), "SingKANA", font=font_h, fill=(255, 255, 255))
    draw.text((pad, 150), hook, font=font_title, fill=(255, 255, 255))

    # cards
    def card(y0: int, title: str, body: str, accent: tuple[int, int, int]):
        x0, x1 = pad, W - pad
        y1 = y0 + 520
        draw.rounded_rectangle([x0, y0, x1, y1], radius=28, fill=(2, 6, 23), outline=(255, 255, 255), width=2)
        draw.rounded_rectangle([x0, y0, x1, y0 + 12], radius=10, fill=accent)
        draw.text((x0 + 28, y0 + 28), title, font=font_b, fill=(226, 232, 240))
        draw.text((x0 + 28, y0 + 84), body or "—", font=font_s, fill=(226, 232, 240))

    card(520, "Before", before_text, (148, 163, 184))
    card(1120, "After (SingKANA)", after_text, (167, 139, 250))

    # footer
    footer = (share_url or "").strip()
    if footer:
        footer = footer[:80]
    draw.text((pad, H - 90), footer, font=font_xs, fill=(203, 213, 225))
    draw.text((W - pad - 240, H - 90), "singkana.com", font=font_xs, fill=(203, 213, 225))

    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()

def _ugc_make_scripts(before_label: str, after_label: str, share_url: str) -> Dict[str, str]:
    before_label = (before_label or "Before").strip()
    after_label = (after_label or "After").strip()
    share_url = (share_url or "").strip()
    cta = f"👉 使ってみて：{share_url}" if share_url else "👉 singkana.com"
    return {
        "6s": f"（2秒）「この歌詞、歌えない」\n（2秒）{before_label}\n（2秒）{after_label}\n{cta}",
        "8s": f"（2秒）「英語の歌、発音が詰む」\n（2秒）{before_label}\n（2秒）{after_label}\n（2秒）{cta}",
        "15s": f"（2秒）フック：「この歌詞、歌えない」\n（4秒）Before：{before_label}\n（5秒）After：{after_label}\n（4秒）CTA：{cta}",
    }

def _content_hash_for_ugc(user_id: str, before_text: str, after_text: str, hook: str) -> str:
    raw = json.dumps(
        {"u": user_id, "b": before_text, "a": after_text, "h": hook},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _admin_allowed() -> bool:
    token = _env("SINGKANA_ADMIN_TOKEN", "")
    if not token:
        # 本番ではADMIN_TOKEN必須。未設定時はローカルループバックのみ許可
        ip = _client_ip()
        return ip in ("127.0.0.1", "::1")
    req = (request.args.get("token") or request.headers.get("X-Admin-Token") or "").strip()
    if not req:
        return False
    return hmac.compare_digest(req, token)

@app.get("/static/ugc/<path:filename>")
def ugc_static(filename: str) -> Response:
    # serve generated UGC images
    try:
        return send_from_directory(str(UGC_STATIC_DIR), filename)
    except Exception as e:
        app.logger.exception("Error serving ugc static %s: %s", filename, e)
        return _json_error(404, "not_found", "not found")

@app.get("/api/me/ref")
def api_me_ref():
    uid = getattr(g, "user_id", "") or ""
    if not uid:
        return _json_error(400, "no_user", "User identity missing.")
    conn = _db()
    ref_code = _ensure_ref_code(conn, uid)
    share_url = f"{_app_base_url()}/?ref={ref_code}"
    return jsonify({"ok": True, "ref_code": ref_code, "share_url": share_url})

# ======================================================================
# Feedback: JSONL保存 + Discord Webhook通知
# ======================================================================
FEEDBACK_PATH = BASE_DIR / "docs" / "feedback.jsonl"

def _get_discord_webhook_url() -> str:
    return (_env("SINGKANA_FEEDBACK_WEBHOOK", "") or "").strip()

def _post_feedback_to_discord(record: dict) -> None:
    url = _get_discord_webhook_url()
    if not url:
        app.logger.info("Discord webhook skipped: SINGKANA_FEEDBACK_WEBHOOK is empty")
        return
    import urllib.request
    song = (record.get("song") or "").strip()
    note = (record.get("note") or record.get("text") or "").strip()
    ts = record.get("created_at") or ""
    engine_ver = (record.get("engine_version") or "").strip()
    desc_lines = []
    if ts:
        desc_lines.append(f"Time: {ts}")
    if engine_ver:
        desc_lines.append(f"Engine: {engine_ver}")
    if song:
        desc_lines.append(f"Song: {song}")
    if note:
        desc_lines.append(f"Note: {note}")
    embeds = [{"title": "SingKANA Feedback", "description": "\n".join(desc_lines), "color": 0x6366F1}] if desc_lines else []
    payload_json = json.dumps({"content": "", "embeds": embeds or None}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=payload_json, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            app.logger.info("Discord webhook response: status=%s", getattr(resp, "status", "unknown"))
    except Exception as e:
        app.logger.error("Discord feedback webhook failed: %s", e)

_feedback_timestamps: dict = {}  # IP -> list of timestamps

@app.post("/api/feedback")
def api_feedback():
    if not _origin_ok():
        return _json_error(403, "invalid_origin", "このページからのみ送信できます。")

    # レート制限: 1IPあたり5分間に3回まで
    ip = _client_ip()
    now = time.time()
    window = 300
    max_per_window = 3
    ts_list = _feedback_timestamps.get(ip, [])
    ts_list = [t for t in ts_list if now - t < window]
    if len(ts_list) >= max_per_window:
        return _json_error(429, "feedback_rate_limit", "送信回数の上限に達しました。しばらくしてから再度お試しください。")
    ts_list.append(now)
    _feedback_timestamps[ip] = ts_list

    data, err = _require_json()
    if err:
        return err
    text = str(data.get("text") or "").strip()
    if not text:
        return _json_error(400, "empty_feedback", "テキストが空です。")
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    song = str(meta.get("song") or "").strip()[:200]
    engine_ver = str(meta.get("engine_version") or "").strip()[:50]
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ip = _client_ip()
    record = {
        "created_at": ts,
        "ip": ip,
        "song": song,
        "note": text[:2000],
        "engine_version": engine_ver,
        "user_id": getattr(g, "user_id", "") or "",
    }
    try:
        FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
        with FEEDBACK_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        app.logger.exception("feedback write failed: %s", e)
        return _json_error(500, "write_failed", "フィードバックの保存に失敗しました。")
    try:
        _post_feedback_to_discord(record)
    except Exception:
        pass  # 通知失敗しても本体は成功扱い
    _track_event("feedback_submit", meta={"song": song[:60]})
    return jsonify({"ok": True})

@app.post("/api/events")
def api_events():
    # lightweight tracking for UI actions
    if not _origin_ok():
        return _json_error(403, "invalid_origin", "このページからのみ送信できます。")
    data, err = _require_json()
    if err:
        return err
    name = str(data.get("name") or "").strip()
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else None
    allowed = (
        name.startswith("ugc_")
        or name.startswith("sheet_")
        or name in ("convert_success", "cta_pdf_clicked", "cta_sheet_clicked", "preset_selected")
    )
    if not allowed:
        return _json_error(400, "bad_event", "invalid event name")
    _track_event(name, ref_code=_ref_cookie_value(), meta=meta)
    return jsonify({"ok": True})

def _analyze_breath_candidates_wav_bytes(
    wav_bytes: bytes,
    *,
    silence_db: float = -35.0,
    frame_ms: int = 20,
    hop_ms: int = 10,
    min_silence_ms: int = 250,
    min_gap_sec: float = 0.40,
    skip_first_sec: float = 0.20,
    max_candidates: int = 40,
) -> Dict[str, Any]:
    """WAV(PCM16)の無音区間からブレス候補を返す軽量解析。"""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        channels = int(wf.getnchannels() or 0)
        sample_width = int(wf.getsampwidth() or 0)
        sample_rate = int(wf.getframerate() or 0)
        n_frames = int(wf.getnframes() or 0)
        pcm = wf.readframes(n_frames)

    if sample_width != 2:
        raise ValueError(f"unsupported sample_width={sample_width} (need 16-bit PCM)")
    if channels not in (1, 2):
        raise ValueError(f"unsupported channels={channels} (need mono/stereo)")
    if sample_rate <= 0:
        raise ValueError("invalid sample_rate")

    expected_bytes = n_frames * channels * sample_width
    if len(pcm) < expected_bytes:
        raise ValueError("truncated wav pcm")

    total_samples = n_frames * channels
    samples = struct.unpack("<" + ("h" * total_samples), pcm[: expected_bytes])

    # ステレオは単純平均でモノラル化
    if channels == 2:
        mono = [int((samples[i] + samples[i + 1]) / 2) for i in range(0, len(samples), 2)]
    else:
        mono = list(samples)
    if not mono:
        raise ValueError("empty_audio")

    duration_sec = len(mono) / float(sample_rate)
    frame_len = max(1, int(sample_rate * frame_ms / 1000))
    hop_len = max(1, int(sample_rate * hop_ms / 1000))
    full_scale = 32768.0
    eps = 1e-12

    def _rms_dbfs(seg: list[int]) -> float:
        s2 = 0.0
        for v in seg:
            fv = float(v) / full_scale
            s2 += fv * fv
        rms = math.sqrt((s2 / max(1, len(seg))) + eps)
        return 20.0 * math.log10(rms + eps)

    db_series: list[tuple[float, float]] = []
    max_start = max(0, len(mono) - frame_len)
    for start in range(0, max_start + 1, hop_len):
        seg = mono[start : start + frame_len]
        t = start / float(sample_rate)
        db_series.append((t, _rms_dbfs(seg)))
    if not db_series:
        db_series = [(0.0, _rms_dbfs(mono))]

    min_silence_sec = max(0.0, min_silence_ms / 1000.0)
    silence_segments: list[dict[str, float]] = []
    in_silence = False
    sil_start = 0.0
    for t, db in db_series:
        is_silence = db <= silence_db
        if is_silence and not in_silence:
            in_silence = True
            sil_start = t
        elif (not is_silence) and in_silence:
            in_silence = False
            sil_end = t
            if (sil_end - sil_start) >= min_silence_sec:
                silence_segments.append({"start": round(sil_start, 3), "end": round(sil_end, 3)})
    if in_silence:
        sil_end = db_series[-1][0] + (frame_len / float(sample_rate))
        if (sil_end - sil_start) >= min_silence_sec:
            silence_segments.append({"start": round(sil_start, 3), "end": round(sil_end, 3)})

    candidates: list[float] = []
    last_t = -1e9
    for seg in silence_segments:
        t = float(seg.get("start", 0.0))
        if t < skip_first_sec:
            continue
        if (t - last_t) < min_gap_sec:
            continue
        candidates.append(round(t, 2))
        last_t = t
        if len(candidates) >= max_candidates:
            break

    db_min = min((db for _, db in db_series), default=0.0)
    db_max = max((db for _, db in db_series), default=0.0)
    return {
        "duration_sec": round(duration_sec, 3),
        "breath_candidates_sec": candidates,
        "silence_segments": silence_segments,
        "stats": {
            "sr_hz": sample_rate,
            "channels": channels,
            "silence_db": float(silence_db),
            "frame_ms": int(frame_ms),
            "hop_ms": int(hop_ms),
            "min_silence_ms": int(min_silence_ms),
            "dbfs_min": round(db_min, 1),
            "dbfs_max": round(db_max, 1),
        },
    }

@app.post("/api/coach/analyze")
def api_coach_analyze():
    """Coach P1: WAV(PCM16)録音を無音検出し、ブレス候補を返す。"""
    if not _origin_ok():
        return _json_error(403, "invalid_origin", "このページからのみ送信できます。")

    user_plan = getattr(g, "user_plan", "free")
    if user_plan != "pro" and not is_pro_override():
        return _json_error(
            402,
            "payment_required",
            "Coach機能はProで利用できます。",
            required_plan="pro",
            checkout_path="/api/billing/checkout",
        )

    if request.content_length is not None and request.content_length > (COACH_MAX_AUDIO_BYTES + 200_000):
        return _json_error(
            413,
            "payload_too_large",
            "録音データが大きすぎます。",
            max_bytes=COACH_MAX_AUDIO_BYTES,
        )

    audio = request.files.get("audio")
    if not audio:
        return _json_error(400, "bad_input", "audioファイルが必要です。")

    mimetype = str(audio.mimetype or "").lower().strip()
    allowed_mimes = {
        "audio/wav",
        "audio/x-wav",
        "audio/wave",
        "application/octet-stream",  # 一部ブラウザ互換
    }
    if mimetype and mimetype not in allowed_mimes:
        return _json_error(400, "unsupported_media_type", "対応していない音声形式です。", mime=mimetype)

    raw = audio.read() or b""
    if not raw:
        return _json_error(400, "bad_input", "音声データが空です。")
    if len(raw) > COACH_MAX_AUDIO_BYTES:
        return _json_error(
            413,
            "payload_too_large",
            "録音データが大きすぎます。",
            max_bytes=COACH_MAX_AUDIO_BYTES,
        )

    if not (len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WAVE"):
        return _json_error(
            400,
            "unsupported_media_type",
            "現時点のCoach解析はWAV(PCM16)のみ対応です。",
            mime=mimetype or "unknown",
        )

    try:
        silence_db = float(request.form.get("silence_db", -35.0))
    except Exception:
        return _json_error(400, "bad_input", "silence_db は数値で指定してください。")
    try:
        min_silence_ms = int(request.form.get("min_silence_ms", 250))
    except Exception:
        return _json_error(400, "bad_input", "min_silence_ms は整数で指定してください。")

    try:
        result = _analyze_breath_candidates_wav_bytes(
            raw,
            silence_db=silence_db,
            min_silence_ms=min_silence_ms,
        )
    except Exception as e:
        app.logger.warning("coach_analyze_failed: %s", str(e))
        return _json_error(400, "analysis_failed", "録音の解析に失敗しました。", detail=str(e))

    duration_sec = float(result.get("duration_sec") or 0.0)
    if duration_sec > (COACH_MAX_SECONDS + 2):
        return _json_error(
            400,
            "duration_too_long",
            f"録音は{COACH_MAX_SECONDS}秒以内にしてください。",
            max_seconds=COACH_MAX_SECONDS,
            duration_sec=duration_sec,
        )

    analysis_id = f"coach_{secrets.token_hex(8)}"

    _track_event(
        "coach_analyze",
        ref_code=_ref_cookie_value(),
        meta={
            "mime": mimetype or "unknown",
            "bytes": len(raw),
            "duration_sec": duration_sec,
            "candidate_count": len(result.get("breath_candidates_sec") or []),
        },
    )
    return jsonify({"ok": True, "analysis_id": analysis_id, "analysis": result})

@app.post("/api/ugc/generate")
def api_ugc_generate():
    if not _origin_ok():
        return _json_error(403, "invalid_origin", "このページからのみ生成できます。")
    data, err = _require_json()
    if err:
        return err

    uid = getattr(g, "user_id", "") or ""
    if not uid:
        return _json_error(400, "no_user", "User identity missing.")

    before_text = str(data.get("before_text") or "").strip()
    after_text = str(data.get("after_text") or "").strip()
    hook = str(data.get("hook") or "このローマ字、歌えない").strip()
    if not before_text or not after_text:
        return _json_error(400, "bad_input", "before_text / after_text are required.")

    conn = _db()
    ref_code = _ensure_ref_code(conn, uid)
    share_url = f"{_app_base_url()}/?ref={ref_code}"

    # cleanup (best-effort)
    _ugc_cleanup_old_files()

    h = _content_hash_for_ugc(uid, before_text, after_text, hook)
    now = _now_ts()

    # dedupe: same user + same content_hash + image asset
    row = conn.execute(
        "SELECT file_path FROM ugc_assets WHERE user_id=? AND asset_type=? AND content_hash=? ORDER BY id DESC LIMIT 1",
        (uid, "image_1080x1920", h),
    ).fetchone()
    if row and row["file_path"]:
        image_url = _ugc_static_url(Path(row["file_path"]).name)
        scripts = _ugc_make_scripts("Before", "After (SingKANA)", share_url)
        return jsonify({"ok": True, "image_url": image_url, "scripts": scripts, "ref_code": ref_code, "share_url": share_url})

    # render image
    try:
        UGC_STATIC_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    try:
        png = _ugc_render_image_1080x1920(hook, before_text, after_text, share_url)
    except Exception as e:
        return _json_error(500, "ugc_generate_failed", "UGC生成に失敗しました。")

    # filename
    short = uid.replace("sk_", "")[:6]
    fname = f"ugc_{now}_{short}_{h[:10]}.png"
    fpath = (UGC_STATIC_DIR / fname)
    try:
        fpath.write_bytes(png)
    except Exception as e:
        return _json_error(500, "ugc_write_failed", "UGC画像の保存に失敗しました。")

    # persist assets
    try:
        conn.execute(
            "INSERT INTO ugc_assets (user_id, asset_type, content_hash, file_path, text, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (uid, "image_1080x1920", h, str(fpath), None, now),
        )
        scripts = _ugc_make_scripts("Before", "After (SingKANA)", share_url)
        conn.execute(
            "INSERT INTO ugc_assets (user_id, asset_type, content_hash, file_path, text, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (uid, "script_6s", h, None, scripts["6s"], now),
        )
        conn.execute(
            "INSERT INTO ugc_assets (user_id, asset_type, content_hash, file_path, text, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (uid, "script_8s", h, None, scripts["8s"], now),
        )
        conn.execute(
            "INSERT INTO ugc_assets (user_id, asset_type, content_hash, file_path, text, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (uid, "script_15s", h, None, scripts["15s"], now),
        )
        conn.commit()
    except Exception:
        pass

    _track_event("ugc_asset_generate", ref_code=_ref_cookie_value(), meta={"asset_type": "image_1080x1920"})

    image_url = _ugc_static_url(fname)
    scripts = _ugc_make_scripts("Before", "After (SingKANA)", share_url)
    return jsonify({"ok": True, "image_url": image_url, "scripts": scripts, "ref_code": ref_code, "share_url": share_url})

@app.post("/api/ugc/submit")
def api_ugc_submit():
    if not _origin_ok():
        return _json_error(403, "invalid_origin", "このページからのみ送信できます。")
    data, err = _require_json()
    if err:
        return err

    uid = getattr(g, "user_id", "") or ""
    if not uid:
        return _json_error(400, "no_user", "User identity missing.")

    platform = str(data.get("platform") or "other").strip().lower()
    post_url = str(data.get("post_url") or "").strip()
    if platform not in ("tiktok", "ig", "yt", "other"):
        platform = "other"
    try:
        u = urlparse(post_url)
        if u.scheme not in ("http", "https") or not u.netloc:
            return _json_error(400, "bad_url", "URLの形式が正しくありません。")
    except Exception:
        return _json_error(400, "bad_url", "URLの形式が正しくありません。")

    conn = _db()
    ref_code = ""
    try:
        ref_code = _ensure_ref_code(conn, uid)
    except Exception:
        ref_code = ""

    now = _now_ts()
    conn.execute(
        "INSERT INTO ugc_posts (user_id, platform, post_url, ref_code, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (uid, platform, post_url, ref_code or None, "new", now),
    )
    conn.commit()
    _track_event("ugc_post_submit", ref_code=_ref_cookie_value(), meta={"platform": platform})
    return jsonify({"ok": True})

@app.get("/admin/ugc")
def admin_ugc():
    if not _admin_allowed():
        return _json_error(403, "forbidden", "admin only")
    conn = _db()
    rows = conn.execute(
        "SELECT id, platform, post_url, ref_code, status, created_at FROM ugc_posts ORDER BY created_at DESC LIMIT 500"
    ).fetchall()
    def _h(s: str) -> str:
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    out = []
    out.append("<!doctype html><meta charset='utf-8'><title>UGC Posts</title>")
    out.append("<style>body{font-family:system-ui,Segoe UI,Roboto,Arial;margin:24px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:8px;font-size:12px}th{background:#f5f5f5;text-align:left}</style>")
    out.append("<h2>UGC投稿一覧</h2>")
    out.append("<p><a href='/admin/dashboard'>dashboard</a></p>")
    out.append("<table><thead><tr><th>id</th><th>platform</th><th>post_url</th><th>ref_code</th><th>status</th><th>created_at</th></tr></thead><tbody>")
    for r in rows:
        out.append("<tr>")
        out.append(f"<td>{r['id']}</td>")
        out.append(f"<td>{_h(r['platform'] or '')}</td>")
        url = _h(r["post_url"] or "")
        out.append(f"<td><a href='{url}' target='_blank' rel='noopener'>{url}</a></td>")
        out.append(f"<td>{_h(r['ref_code'] or '')}</td>")
        out.append(f"<td>{_h(r['status'] or '')}</td>")
        out.append(f"<td>{int(r['created_at'] or 0)}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return Response("\n".join(out), mimetype="text/html; charset=utf-8")

@app.get("/admin/feedback")
def admin_feedback():
    if not _admin_allowed():
        return _json_error(403, "forbidden", "admin only")
    entries = []
    if FEEDBACK_PATH.exists():
        try:
            with FEEDBACK_PATH.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        entries.append({"_raw": line})
        except Exception as e:
            return Response(f"Error reading feedback: {e}", mimetype="text/plain", status=500)
    entries.reverse()
    def _h(s):
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    out = []
    out.append("<!doctype html><meta charset='utf-8'><title>Feedback Admin</title>")
    out.append("<style>body{font-family:system-ui,Segoe UI,Roboto,Arial;margin:24px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:8px;font-size:12px;vertical-align:top}th{background:#f5f5f5;text-align:left}.note{max-width:400px;white-space:pre-wrap;word-break:break-word}</style>")
    out.append(f"<h2>フィードバック一覧（{len(entries)}件）</h2>")
    out.append("<p><a href='/admin/dashboard'>dashboard</a></p>")
    out.append("<table><thead><tr><th>#</th><th>日時</th><th>曲名</th><th>内容</th><th>Engine</th><th>User</th></tr></thead><tbody>")
    for i, e in enumerate(entries, 1):
        ts = _h(str(e.get("created_at") or ""))
        song = _h(str(e.get("song") or ""))
        note = _h(str(e.get("note") or e.get("text") or e.get("_raw") or ""))
        engine = _h(str(e.get("engine_version") or ""))
        uid = _h(str(e.get("user_id") or "")[:12])
        out.append(f"<tr><td>{i}</td><td>{ts}</td><td>{song}</td><td class='note'>{note}</td><td>{engine}</td><td>{uid}</td></tr>")
    out.append("</tbody></table>")
    return Response("\n".join(out), mimetype="text/html; charset=utf-8")

@app.get("/admin/dashboard")
def admin_dashboard():
    if not _admin_allowed():
        return _json_error(403, "forbidden", "admin only")
    conn = _db()
    # last 14 days funnel counts
    now = _now_ts()
    start = now - (14 * 86400)
    names = ["ugc_panel_open", "ugc_asset_generate", "ugc_link_copy", "convert_success", "subscribe", "ugc_post_submit"]
    # group by day (YYYY-MM-DD) in JST-like by localtime of server; good enough for v1
    rows = conn.execute(
        """
        SELECT name, date(datetime(created_at, 'unixepoch')) AS d, COUNT(*) AS c
        FROM events
        WHERE created_at >= ? AND name IN (%s)
        GROUP BY name, d
        ORDER BY d DESC
        """ % (",".join(["?"] * len(names))),
        (start, *names),
    ).fetchall()
    by_day = {}
    for r in rows:
        d = r["d"] or ""
        by_day.setdefault(d, {})[r["name"]] = int(r["c"] or 0)

    days = sorted(by_day.keys(), reverse=True)
    def cell(d: str, name: str) -> int:
        return int(by_day.get(d, {}).get(name, 0))

    out = []
    out.append("<!doctype html><meta charset='utf-8'><title>UGC Dashboard</title>")
    out.append("<style>body{font-family:system-ui,Segoe UI,Roboto,Arial;margin:24px}table{border-collapse:collapse}th,td{border:1px solid #ddd;padding:8px;font-size:12px}th{background:#f5f5f5;text-align:left}</style>")
    out.append("<h2>UGCファネル（日次 / 直近14日）</h2>")
    out.append("<p><a href='/admin/ugc'>ugc posts</a> | <a href='/admin/feedback'>feedback</a></p>")
    out.append("<table><thead><tr><th>day</th>")
    for n in names:
        out.append(f"<th>{n}</th>")
    out.append("</tr></thead><tbody>")
    for d in days:
        out.append("<tr>")
        out.append(f"<td>{d}</td>")
        for n in names:
            out.append(f"<td>{cell(d,n)}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return Response("\n".join(out), mimetype="text/html; charset=utf-8")

@app.get("/favicon.ico")
def favicon_ico():
    """Google等が最初に取りに来る favicon.ico を200で返す"""
    fav_dir = BASE_DIR / "assets" / "favicon"
    return send_from_directory(str(fav_dir), "favicon.ico", mimetype="image/x-icon")

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

@app.get("/api/internal/enable")
def api_internal_enable():
    # key不一致は存在秘匿のため404
    key = (request.args.get("key") or "").strip()
    expected = (os.getenv("SINGKANA_INTERNAL_ENABLE_KEY", "") or "").strip()
    if not key or not expected or not hmac.compare_digest(key, expected):
        return ("not found", 404)

    uid = getattr(g, "user_id", "") or (request.cookies.get(COOKIE_NAME_UID) or "")
    if not is_internal_uid(uid):
        return _json_error(403, "forbidden", "internal uid only")

    ts = int(time.time())
    sig = _internal_cookie_sig(uid, ts)
    if not sig:
        return _json_error(500, "misconfigured", "SINGKANA_INTERNAL_HMAC_SECRET is missing.")

    max_days = _internal_sig_max_age_days()
    val = f"v1.{ts}.{sig}"
    resp = jsonify({"ok": True, "uid": uid, "max_age_days": max_days})
    resp.set_cookie(
        COOKIE_NAME_INTERNAL,
        val,
        max_age=(max_days * 86400 if max_days > 0 else None),
        httponly=True,
        samesite="Lax",
        secure=COOKIE_SECURE,
        path="/",
    )
    return resp

@app.get("/api/me")
def api_me():
    # subscription snapshot (best-effort; do not fail /api/me if schema is old)
    sub_info = None
    try:
        conn = _db()
        row = conn.execute(
            """
            SELECT stripe_customer_id, stripe_subscription_id, status, current_period_end, cancel_at_period_end
            FROM subscriptions
            WHERE user_id=?
            """,
            (getattr(g, "user_id", ""),),
        ).fetchone()
        if row:
            sub_info = {
                "stripe_customer_id_present": bool(row["stripe_customer_id"]),
                "stripe_subscription_id_present": bool(row["stripe_subscription_id"]),
                "status": row["status"],
                "current_period_end": row["current_period_end"],
                "cancel_at_period_end": bool(row["cancel_at_period_end"]),
            }
    except Exception:
        sub_info = None

    result = {
        "ok": True,
        "user_id": getattr(g, "user_id", ""),
        "plan": getattr(g, "user_plan", "free"),
        "effective_plan": getattr(g, "effective_plan", getattr(g, "user_plan", "free")),
        "effective_mode": getattr(g, "effective_mode", _effective_mode_from_plan(getattr(g, "effective_plan", getattr(g, "user_plan", "free")))),
        "dev_pro_override": getattr(g, "dev_pro_override", False),
        "subscription": sub_info,
        "time": _utc_iso(),
    }

    # デバッグ情報は admin のみに返す（本番では非公開）
    if _admin_allowed():
        result["debug"] = {
            "dev_pro_enabled": os.getenv("SINGKANA_DEV_PRO", "0") == "1",
            "is_pro_override": is_pro_override(),
            "ip_ok": _dev_pro_ip_ok(),
            "client_ip": _client_ip(),
        }

    return jsonify(result)

# ======================================================================
# Static: robots.txt
# ======================================================================

@app.route("/robots.txt", methods=["GET"])
def robots_txt():
    """robots.txtを返す（SEO対策、404エラー回避）"""
    return Response("User-agent: *\nDisallow:", mimetype="text/plain")

# ======================================================================
# API: 歌詞変換（Canonical）
# ======================================================================

@app.route("/api/convert", methods=["POST"])
def api_convert():
    if not _origin_ok():
        return _json_error(403, "origin_rejected", "Origin not allowed.")
    data, err = _require_json()
    if err:
        return err

    lyrics = (data.get("text") or data.get("lyrics") or "").strip()
    if not lyrics:
        return _json_error(400, "empty_lyrics", "Lyrics text is required.")
    MAX_LYRICS_CHARS = 10000
    if len(lyrics) > MAX_LYRICS_CHARS:
        return _json_error(400, "lyrics_too_long", f"Lyrics must be under {MAX_LYRICS_CHARS} characters.")

    meta = _get_meta(data)
    requested_mode = _get_display_mode(meta)  # 互換受理（実処理では使わない）
    user_plan = getattr(g, "user_plan", "free")
    effective_mode = getattr(g, "effective_mode", _effective_mode_from_plan(user_plan))
    hard_case = (effective_mode == "natural") and _is_hard_case_lyrics(lyrics)
    processing_mode = "natural_boost" if hard_case else effective_mode

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
        )

    # Pro専用: hard_case時のみ内部ブースト（UIには非公開）
    is_pro = (user_plan == "pro") or is_pro_override()
    gpt_applied = False
    if is_pro and processing_mode == "natural_boost" and hasattr(engine, "gpt_refine_kana"):
        openai_key = _env("OPENAI_API_KEY", "")
        if openai_key:
            # キャッシュ確認
            lyrics_hash = hashlib.sha256(f"{processing_mode}\n{lyrics}".encode("utf-8")).hexdigest()[:32]
            conn = _db()
            _GPT_CACHE_TTL_SEC = 7 * 24 * 3600  # 7日
            cached = conn.execute(
                "SELECT result_json FROM gpt_kana_cache WHERE lyrics_hash=? AND created_at > ?",
                (lyrics_hash, _now_ts() - _GPT_CACHE_TTL_SEC),
            ).fetchone()
            if cached:
                try:
                    result = json.loads(cached["result_json"])
                    gpt_applied = True
                    app.logger.info("gpt_refine_kana: cache hit hash=%s", lyrics_hash[:8])
                except Exception:
                    pass
            if not gpt_applied:
                try:
                    result = engine.gpt_refine_kana(result, api_key=openai_key)
                    gpt_applied = True
                    # キャッシュ保存
                    try:
                        conn.execute(
                            "INSERT OR REPLACE INTO gpt_kana_cache (lyrics_hash, result_json, created_at) VALUES (?, ?, ?)",
                            (lyrics_hash, json.dumps(result, ensure_ascii=False), _now_ts()),
                        )
                        conn.commit()
                    except Exception:
                        pass
                    app.logger.info("gpt_refine_kana: applied hash=%s", lyrics_hash[:8])
                except Exception as e:
                    app.logger.warning("gpt_refine_kana failed, using rule-based: %s", e)

    # 計測: convert_success（ref cookieがあれば紐付け）
    _track_event("convert_success", ref_code=_ref_cookie_value(), meta={
        "endpoint": "/api/convert",
        "requested_mode": requested_mode,
        "effective_mode": effective_mode,
        "processing_mode": processing_mode,
        "hard_case": hard_case,
        "gpt_applied": gpt_applied,
        "plan": user_plan,
    })
    return jsonify({
        "ok": True,
        "result": result,
        "gpt_applied": gpt_applied,
        "requested_mode": requested_mode,
        "effective_mode": effective_mode,
        "processing_mode": processing_mode,
        "hard_case": hard_case,
    })

# --- Romaji (Phase 1 MVP: 歌うためのローマ字) ----------------------------
from pykakasi import kakasi  # noqa: E402

# pykakasi v3 API (setMode/getConverter deprecated)
_kks = kakasi()

def _optimize_romaji_for_singing(romaji: str) -> str:
    """
    歌唱向けにローマ字を最適化する。
    - 音節の区切りを明確に（適切な位置にスペース）
    - 長音（ー）を明確に（oo, uu など）
    - 促音（っ）を適切に処理
    - 歌いやすさを優先
    """
    if not romaji:
        return romaji
    
    # 1. 長音記号（ー）の処理：前の母音に応じて適切に展開
    # 例：おー → oo, あー → aa, えー → ee, いー → ii, うー → uu
    # ただし、既に連続母音になっている場合はそのまま
    
    # 2. 促音（っ）の処理：pykakasiが既に適切に処理しているが、念のため確認
    # 例：いっしょ → issho（既に処理済み）
    
    # 3. 音節区切りの最適化：子音+母音のペアを基本単位として、適切にスペースを入れる
    # ただし、過度にスペースを入れすぎると読みにくくなるので、バランスを取る
    # 基本的にはpykakasiの出力を尊重しつつ、明らかに区切った方が歌いやすい箇所のみ調整
    
    # 4. 大文字小文字の統一：歌詞として見やすく（文頭のみ大文字、他は小文字）
    lines = romaji.splitlines()
    optimized_lines = []
    
    for line in lines:
        if not line.strip():
            optimized_lines.append("")
            continue
        
        # 基本的にはpykakasiの出力をそのまま使用
        # 将来的にリズム・伸ばし・息継ぎを最適化する余地を残す
        optimized = line.strip()
        
        # 簡易的な最適化：連続する子音の前にスペースを入れる（歌いやすさ向上）
        # 例：shinjite → shin jite（ただし、これは過度に分割しすぎる可能性があるので慎重に）
        # 現時点では、pykakasiの出力を尊重
        
        optimized_lines.append(optimized)
    
    return "\n".join(optimized_lines)

def to_romaji(text: str, for_singing: bool = True) -> str:
    """
    日本語テキストをローマ字に変換する。
    
    Args:
        text: 変換する日本語テキスト
        for_singing: Trueの場合、歌唱向けに最適化（デフォルト）
    
    Returns:
        ローマ字変換されたテキスト（改行は保持）
    """
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
        
        if for_singing:
            romaji = _optimize_romaji_for_singing(romaji)
        
        out.append(romaji.strip())
    return "\n".join(out)

@app.route("/api/romaji", methods=["GET", "HEAD"])
def api_romaji_probe():
    """監視/事前問い合わせ用（HEADが500になるのを防ぐ）"""
    # HEADはボディ無しで200（ただしContent-TypeはGETに寄せておく）
    if request.method == "HEAD":
        return Response("", status=200, mimetype="application/json")
    return jsonify(ok=True, method="GET", hint="POST JSON {text} to convert"), 200

@app.route("/api/romaji", methods=["POST"])
def api_romaji():
    """
    日本語→ローマ字変換API（歌うためのローマ字）
    無料プランでは文字数制限あり。
    """
    if not _origin_ok():
        return _json_error(403, "origin_rejected", "Origin not allowed.")
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()

    if not text:
        return _json_error(400, "empty_text", "テキストを入力してください。")

    # 無料制限チェック
    user_plan = getattr(g, "user_plan", "free")
    text_length = len(text)
    
    # 開発者モードで上書きされている場合はPro扱い
    is_pro = (user_plan == "pro") or is_pro_override()
    
    if not is_pro and text_length > ROMAJI_FREE_MAX_CHARS:
        return _json_error(
            402,
            "payment_required",
            f"無料プランでは{ROMAJI_FREE_MAX_CHARS}文字まで変換できます。Proプランでは無制限です。",
            text_length=text_length,
            free_limit=ROMAJI_FREE_MAX_CHARS,
            required_plan="pro",
            user_plan=user_plan,
        )
    
    try:
        romaji_result = to_romaji(text, for_singing=True)
        
        return jsonify({
            "ok": True,
            "romaji": romaji_result,
            "meta": {
                "text_length": text_length,
                "plan": user_plan,
                "is_pro": is_pro,
                "free_limit": ROMAJI_FREE_MAX_CHARS if not is_pro else None,
            }
        })
    except Exception as e:
        app.logger.exception(f"Romaji conversion failed: {e}")
        return _json_error(
            500,
            "conversion_error",
            "ローマ字変換に失敗しました。",
        )

# ======================================================================
# PDF Sheet: 歌唱用カンペの生成（Playwright）
# ======================================================================
@app.post("/api/sheet/pdf")
def api_sheet_pdf():
    if not _origin_ok():
        return _json_error(403, "invalid_origin", "このページからのみ生成できます。")

    data, err = _require_json()
    if err:
        return err

    uid = getattr(g, "user_id", "") or ""
    user_plan = getattr(g, "user_plan", "free")
    is_pro = (user_plan == "pro") or is_pro_override()
    title = ""
    artist = ""
    safe_lines: list[dict[str, str]] = []
    token_row = None
    token_hash = ""

    if is_pro:
        title, artist, safe_lines, payload_err = _extract_sheet_payload(data)
        if payload_err:
            return payload_err
    else:
        sheet_token = str(data.get("sheet_token") or "").strip()
        if not sheet_token:
            if not uid:
                return _json_error(400, "no_user", "User identity missing.")
            title_tmp, artist_tmp, safe_lines_tmp, payload_err = _extract_sheet_payload(data)
            if payload_err:
                return payload_err
            conn = _db()
            now = _now_ts()
            try:
                conn.execute("DELETE FROM sheet_drafts WHERE expires_at < ?", (now - 60,))
                conn.execute("DELETE FROM sheet_pdf_tokens WHERE expires_at < ?", (now - 60,))
                conn.commit()
            except Exception:
                pass
            result, checkout_err = _create_sheet_checkout_session(conn, uid, title_tmp, artist_tmp, safe_lines_tmp)
            if checkout_err:
                return checkout_err
            _track_event("sheet_paywall_402", meta={"draft_id": result["draft_id"], "amount_jpy": result["amount_jpy"]})
            return _json_error(
                402,
                "payment_required",
                "PDF出力はProまたはOne-Shot購入が必要です。決済完了後に自動でダウンロードされます。",
                required_plan="pro_or_sheet_oneshot",
                checkout_url=result["checkout_url"],
                checkout_id=result["checkout_id"],
                draft_id=result["draft_id"],
                amount_jpy=result["amount_jpy"],
            )
        token_hash = _hash_sheet_token(sheet_token)
        conn = _db()
        now = _now_ts()
        token_row = conn.execute(
            """
            SELECT token_hash, user_id, draft_id, expires_at, used_at
            FROM sheet_pdf_tokens
            WHERE token_hash=?
            """,
            (token_hash,),
        ).fetchone()
        if not token_row:
            return _json_error(401, "invalid_sheet_token", "sheet_token が無効です。")
        if token_row["used_at"]:
            return _json_error(409, "sheet_token_used", "このsheet_tokenは使用済みです。")
        if int(token_row["expires_at"] or 0) < now:
            return _json_error(410, "sheet_token_expired", "sheet_token の有効期限が切れました。")
        if uid and token_row["user_id"] and token_row["user_id"] != uid:
            return _json_error(403, "sheet_token_user_mismatch", "このsheet_tokenは別ユーザー向けです。")

        draft_row = conn.execute(
            "SELECT title, artist, payload_json, expires_at FROM sheet_drafts WHERE draft_id=?",
            (token_row["draft_id"],),
        ).fetchone()
        if not draft_row:
            return _json_error(404, "sheet_draft_missing", "購入データが見つかりません。")
        if int(draft_row["expires_at"] or 0) < now:
            return _json_error(410, "sheet_draft_expired", "購入データの有効期限が切れました。")
        try:
            payload = json.loads(draft_row["payload_json"] or "{}")
            title = str(payload.get("title") or draft_row["title"] or "").strip()
            artist = str(payload.get("artist") or draft_row["artist"] or "").strip()
            safe_lines = _normalize_sheet_lines(payload.get("lines"))
        except Exception:
            safe_lines = []
        if not safe_lines:
            return _json_error(500, "sheet_draft_invalid", "購入データの形式が不正です。")

    try:
        html_str = _render_sheet_html(title, artist, safe_lines)
    except FileNotFoundError:
        return _json_error(500, "template_missing", "Sheet template is missing.")
    except Exception as e:
        return _json_error(500, "template_error", "Failed to render sheet template.")

    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as e:
        return _json_error(501, "playwright_missing", "Playwright is not installed.")

    acquired = _SHEET_SEM.acquire(blocking=False)
    if not acquired:
        return _json_error(429, "pdf_busy", "混雑中です。少し待ってから再試行してください。")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page()
            page.set_content(html_str, wait_until="load")
            page.emulate_media(media="print")
            pdf_bytes = page.pdf(format="A4", print_background=True, prefer_css_page_size=True)
            page.close()
            browser.close()
    except Exception as e:
        app.logger.exception("Sheet PDF generation failed: %s", e)
        return _json_error(500, "pdf_failed", "PDF生成に失敗しました。")
    finally:
        _SHEET_SEM.release()

    if token_row is not None:
        try:
            conn = _db()
            conn.execute(
                "UPDATE sheet_pdf_tokens SET used_at=?, used_by_ip=? WHERE token_hash=? AND used_at IS NULL",
                (_now_ts(), _client_ip(), token_hash),
            )
            conn.commit()
        except Exception as e:
            app.logger.warning("Failed to mark sheet token as used: %s", e)

    filename = "singkana_sheet.pdf"
    if title:
        safe = re.sub(r"[\\\/:*?\"<>|]+", "_", title).strip("_")
        if safe:
            filename = f"{safe}_singkana.pdf"

    _track_event("sheet_pdf_download_ok", meta={
        "title": (title or "")[:60],
        "via": "token" if token_row is not None else "pro",
        "pdf_size": len(pdf_bytes),
    })
    resp = Response(pdf_bytes, mimetype="application/pdf")
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    return resp

@app.post("/api/sheet/checkout")
def api_sheet_checkout():
    if not _origin_ok():
        return _json_error(403, "invalid_origin", "このページからのみ決済を開始できます。")

    if getattr(g, "user_plan", "free") == "pro" or is_pro_override():
        return _json_error(409, "already_pro", "Proユーザーは決済不要です。")

    uid = getattr(g, "user_id", "") or ""
    if not uid:
        return _json_error(400, "no_user", "User identity missing.")

    data, err = _require_json()
    if err:
        return err
    title, artist, safe_lines, payload_err = _extract_sheet_payload(data)
    if payload_err:
        return payload_err

    conn = _db()
    now = _now_ts()
    try:
        conn.execute("DELETE FROM sheet_drafts WHERE expires_at < ?", (now - 60,))
        conn.execute("DELETE FROM sheet_pdf_tokens WHERE expires_at < ?", (now - 60,))
        conn.commit()
    except Exception:
        pass

    result, checkout_err = _create_sheet_checkout_session(conn, uid, title, artist, safe_lines)
    if checkout_err:
        return checkout_err
    return jsonify({
        "ok": True,
        "url": result["checkout_url"],
        "id": result["checkout_id"],
        "draft_id": result["draft_id"],
        "expires_at": result["expires_at"],
        "amount_jpy": result["amount_jpy"],
    })

@app.get("/api/sheet/claim")
def api_sheet_claim():
    session_id = str(request.args.get("session_id") or "").strip()
    if not session_id:
        return _json_error(400, "bad_session_id", "session_id is required.")
    # Stripe session ID は "cs_live_" or "cs_test_" + 英数字のみ（最大 66 文字）
    # 不正な値で Stripe API を叩くと resource_missing / invalid_request エラーが蓄積する
    if not re.fullmatch(r"cs_(live|test)_[A-Za-z0-9]{10,66}", session_id):
        return _json_error(400, "bad_session_id", "Invalid session_id format.")
    sid_head = session_id[:12]
    app.logger.info("sheet_claim requested session=%s", sid_head)

    uid = getattr(g, "user_id", "") or ""
    if not uid:
        return _json_error(400, "no_user", "User identity missing.")

    envs = _stripe_required_env()
    secret = envs["STRIPE_SECRET_KEY"]
    if not secret:
        return _json_error(400, "stripe_not_configured", "Stripe env is missing.", missing=["STRIPE_SECRET_KEY"])

    stripe, import_err = _stripe_import()
    if stripe is None:
        return _json_error(501, "stripe_sdk_missing", "stripe package is not installed.", detail=import_err)

    try:
        stripe.api_key = secret
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception as e:
        app.logger.warning("sheet_claim stripe retrieve failed session=%s detail=%s", sid_head, str(e))
        return _json_error(400, "stripe_session_error", "Failed to verify checkout session.")

    payment_status = str(getattr(session, "payment_status", "") or "")
    mode = str(getattr(session, "mode", "") or "")
    status = str(getattr(session, "status", "") or "")
    livemode = bool(getattr(session, "livemode", False))
    app.logger.info(
        "sheet_claim stripe session=%s status=%s payment_status=%s mode=%s livemode=%s",
        sid_head,
        status,
        payment_status,
        mode,
        livemode,
    )
    metadata = getattr(session, "metadata", {}) or {}
    draft_id = str(metadata.get("draft_id") or "")
    uid_meta = str(metadata.get("user_id") or "")
    if uid_meta and uid_meta != uid:
        _track_event("sheet_claim_fail", meta={"reason": "session_user_mismatch", "session_id_head": sid_head})
        return _json_error(403, "session_user_mismatch", "この決済は別ユーザー向けです。")
    if mode != "payment":
        _track_event("sheet_claim_fail", meta={"reason": "bad_session_mode", "session_id_head": sid_head})
        return _json_error(400, "bad_session_mode", "One-shot決済セッションではありません。")
    if payment_status != "paid":
        _track_event("sheet_claim_fail", meta={"reason": "payment_not_completed", "session_id_head": sid_head, "payment_status": payment_status})
        return _json_error(402, "payment_not_completed", "決済完了を確認できませんでした。", payment_status=payment_status)
    if not draft_id:
        _track_event("sheet_claim_fail", meta={"reason": "draft_missing", "session_id_head": sid_head})
        return _json_error(400, "draft_missing", "決済メタデータが不足しています。")

    conn = _db()
    now = _now_ts()
    draft_row = conn.execute(
        """
        SELECT draft_id, user_id, expires_at
        FROM sheet_drafts
        WHERE draft_id=?
        """,
        (draft_id,),
    ).fetchone()
    if not draft_row:
        return _json_error(404, "sheet_draft_missing", "購入データが見つかりません。")
    if draft_row["user_id"] != uid:
        return _json_error(403, "draft_user_mismatch", "この購入データは別ユーザー向けです。")
    if int(draft_row["expires_at"] or 0) < now:
        return _json_error(410, "sheet_draft_expired", "購入データの有効期限が切れました。")

    token = _gen_sheet_token()
    token_hash = _hash_sheet_token(token)
    expires_at = now + max(60, SHEET_TOKEN_TTL_SEC)
    conn.execute(
        """
        INSERT OR REPLACE INTO sheet_pdf_tokens
        (token_hash, user_id, draft_id, stripe_session_id, created_at, expires_at, used_at, used_by_ip)
        VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)
        """,
        (token_hash, uid, draft_id, session_id, now, expires_at),
    )
    conn.commit()
    _track_event("sheet_claim_ok", meta={"draft_id": draft_id, "session_id_head": sid_head})
    return jsonify({
        "ok": True,
        "sheet_token": token,
        "expires_at": expires_at,
        "draft_id": draft_id,
    })

# ======================================================================
# Billing: config + checkout + webhook
# ======================================================================

@app.get("/api/billing/config")
def api_billing_config():
    if not _origin_ok():
        return _json_error(403, "origin_rejected", "Origin not allowed.")
    envs = _stripe_required_env()
    publishable_key = envs["STRIPE_PUBLISHABLE_KEY"] or ""

    return jsonify({
        "ok": True,
        "publishable_key": publishable_key,
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
        return _json_error(400, "bad_webhook", "Invalid webhook signature or payload.")

    # まずは「届いた」証拠を残す
    try:
        etype = event.get("type")
        eid = event.get("id")
        app.logger.info("stripe_webhook received type=%s id=%s", etype, eid)
    except Exception:
        pass

    # --- minimal handling ---
    etype = event.get("type")

    # 1) Checkout完了（最短でProへ / user_id紐付け）
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
                  (user_id, stripe_customer_id, stripe_subscription_id, status, current_period_end, cancel_at_period_end)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                  stripe_customer_id=COALESCE(excluded.stripe_customer_id, subscriptions.stripe_customer_id),
                  stripe_subscription_id=COALESCE(excluded.stripe_subscription_id, subscriptions.stripe_subscription_id),
                  updated_at=CURRENT_TIMESTAMP
                """,
                # subscription_id / customer_id がこの時点で未確定なことがあるため、
                # ここでは「到達した事実」を保存し、確定情報は subscription.created/updated で上書きする。
                (user_id, customer_id, subscription_id, "checkout_completed", None, 0),
            )
            conn.commit()

    # 2) サブスク作成/更新（Pro確定・解約予約/ステータス遷移を拾う）
    elif etype in ("customer.subscription.created", "customer.subscription.updated"):
        sub = event["data"]["object"]

        sub_id = sub.get("id")
        customer_id = sub.get("customer")
        status = sub.get("status")
        current_period_end = _safe_int(sub.get("current_period_end"))
        cancel_at_period_end = 1 if sub.get("cancel_at_period_end") else 0

        user_id = (sub.get("metadata") or {}).get("user_id")
        conn = _db()

        # metadataに無い場合はDBから逆引き（保険）
        if not user_id:
            row = conn.execute(
                """
                SELECT user_id FROM subscriptions
                WHERE stripe_subscription_id=? OR stripe_customer_id=?
                """,
                (sub_id, customer_id),
            ).fetchone()
            user_id = (row["user_id"] if row else None)

        if user_id:
            # current_period_end が無い場合は Stripe API から補完（取得できれば上書き）
            if current_period_end is None and sub_id:
                secret_key = _env("STRIPE_SECRET_KEY")
                if secret_key:
                    try:
                        stripe.api_key = secret_key
                        full_sub = stripe.Subscription.retrieve(sub_id)
                        current_period_end = _safe_int(full_sub.get("current_period_end"))
                        status = full_sub.get("status") or status
                    except Exception as e:
                        app.logger.warning("stripe_webhook: failed to retrieve subscription %s: %s", sub_id, e)
            # 1) 先に subscriptions を upsert（DB を正とする）
            conn.execute(
                """
                INSERT INTO subscriptions
                  (user_id, stripe_customer_id, stripe_subscription_id, status, current_period_end, cancel_at_period_end)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                  stripe_customer_id=excluded.stripe_customer_id,
                  stripe_subscription_id=excluded.stripe_subscription_id,
                  status=excluded.status,
                  current_period_end=COALESCE(excluded.current_period_end, subscriptions.current_period_end),
                  cancel_at_period_end=excluded.cancel_at_period_end,
                  updated_at=CURRENT_TIMESTAMP
                """,
                (user_id, customer_id, sub_id, status, current_period_end, cancel_at_period_end),
            )
            # 2) 単一ルールで plan を1回だけ決定し、users.plan を1回だけ更新
            new_plan = _plan_from_subscription(status, current_period_end)
            _set_plan(conn, user_id, new_plan)
            conn.commit()

    # 3) 解約・失効（安全側に倒してfreeへ）
    elif etype in ("customer.subscription.deleted", "customer.subscription.paused"):
        sub = event["data"]["object"]
        sub_id = sub.get("id")
        customer_id = sub.get("customer")
        status = sub.get("status")
        current_period_end = _safe_int(sub.get("current_period_end"))
        cancel_at_period_end = 1 if sub.get("cancel_at_period_end") else 0

        user_id = (sub.get("metadata") or {}).get("user_id")
        conn = _db()

        # metadataに無い場合はDBから逆引き（保険）
        if not user_id:
            row = conn.execute(
                """
                SELECT user_id FROM subscriptions
                WHERE stripe_subscription_id=? OR stripe_customer_id=?
                """,
                (sub_id, customer_id),
            ).fetchone()
            user_id = (row["user_id"] if row else None)

        if user_id:
            # 1) 先に subscriptions を upsert
            conn.execute(
                """
                INSERT INTO subscriptions
                  (user_id, stripe_customer_id, stripe_subscription_id, status, current_period_end, cancel_at_period_end)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                  stripe_customer_id=excluded.stripe_customer_id,
                  stripe_subscription_id=excluded.stripe_subscription_id,
                  status=excluded.status,
                  current_period_end=COALESCE(excluded.current_period_end, subscriptions.current_period_end),
                  cancel_at_period_end=excluded.cancel_at_period_end,
                  updated_at=CURRENT_TIMESTAMP
                """,
                (user_id, customer_id, sub_id, status, current_period_end, cancel_at_period_end),
            )
            # 2) deleted/paused は無条件 free、1回だけ _set_plan（必ず if user_id 内）
            _set_plan(conn, user_id, "free")
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
    if not _origin_ok():
        return _json_error(403, "origin_rejected", "Origin not allowed.")
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
            subscription_data={"metadata": {"user_id": uid}},
        )
        return jsonify({"ok": True, "url": session.url, "id": session.id, "plan": plan})
    except Exception as e:
        app.logger.exception("billing checkout creation failed: %s", e)
        return _json_error(500, "stripe_error", "Failed to create checkout session.")


@app.post("/api/billing/portal")
def api_billing_portal():
    if not _origin_ok():
        return _json_error(403, "origin_rejected", "Origin not allowed.")
    data, err = _require_json()
    if err:
        return err

    envs = _stripe_required_env()
    secret = envs["STRIPE_SECRET_KEY"]
    if not secret:
        return _json_error(
            400,
            "stripe_not_configured",
            "Stripe env is missing.",
            missing=["STRIPE_SECRET_KEY"],
        )

    stripe, import_err = _stripe_import()
    if stripe is None:
        return _json_error(501, "stripe_sdk_missing", "stripe package is not installed.", detail=import_err)

    uid = getattr(g, "user_id", "")
    if not uid:
        return _json_error(400, "no_user", "User identity missing.")

    # subscriptions から customer_id を取得（SSOT）
    conn = _db()
    row = conn.execute(
        "SELECT stripe_customer_id FROM subscriptions WHERE user_id=?",
        (uid,),
    ).fetchone()

    customer_id = (row["stripe_customer_id"] if row and row["stripe_customer_id"] else "")
    if not customer_id:
        return _json_error(
            402,
            "payment_required",
            "Billing portal is available after purchase.",
            user_plan=getattr(g, "user_plan", "free"),
        )

    base = (_env("APP_BASE_URL") or "https://singkana.com").rstrip("/")
    return_url = _env("STRIPE_PORTAL_RETURN_URL", f"{base}/?portal=return")

    try:
        stripe.api_key = secret
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return jsonify({"ok": True, "url": session.url})
    except Exception as e:
        app.logger.exception("Failed to create billing portal session: %s", e)
        return _json_error(500, "stripe_error", "Failed to create billing portal session.")

# ======================================================================
# Transfer: 引き継ぎコード（Proの購入状態を別ブラウザへ移す）
# ======================================================================
@app.post("/api/transfer/issue")
def api_transfer_issue():
    if getattr(g, "user_plan", "free") != "pro":
        return _json_error(402, "payment_required", "Transfer code is available on Pro plan only.")

    uid = getattr(g, "user_id", "")
    if not uid:
        return _json_error(400, "no_user", "User identity missing.")

    now = _now_ts()
    expires_at = now + max(60, TRANSFER_CODE_TTL_SEC)

    conn = _db()
    try:
        conn.execute("DELETE FROM transfer_codes WHERE expires_at < ?", (now - 60,))
        conn.commit()
    except Exception:
        pass

    for _i in range(5):
        code = _gen_transfer_code()
        try:
            conn.execute(
                "INSERT INTO transfer_codes (code, owner_user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (code, uid, now, expires_at),
            )
            conn.commit()
            app.logger.info("transfer_issue: owner_user_id=%s expires_at=%s", uid, expires_at)
            return jsonify({"ok": True, "code": code, "expires_at": expires_at})
        except sqlite3.IntegrityError:
            continue

    return _json_error(500, "transfer_issue_failed", "Failed to issue transfer code.")

@app.post("/api/transfer/claim")
def api_transfer_claim():
    data, err = _require_json()
    if err:
        return err

    code = _normalize_transfer_code(str(data.get("code") or ""))
    if not code or len(code) < 6:
        return _json_error(400, "bad_code", "引き継ぎコードが短すぎます。")

    now = _now_ts()
    conn = _db()
    row = conn.execute(
        "SELECT owner_user_id, expires_at, used_at FROM transfer_codes WHERE code=?",
        (code,),
    ).fetchone()

    if not row:
        return _json_error(404, "invalid_code", "引き継ぎコードが見つかりません。")

    owner_user_id = row["owner_user_id"]
    expires_at = int(row["expires_at"] or 0)

    if expires_at and now > expires_at:
        return _json_error(410, "expired_code", "引き継ぎコードの有効期限が切れました。")

    if row["used_at"]:
        return _json_error(409, "already_used", "この引き継ぎコードは使用済みです。")

    used_by_uid = getattr(g, "user_id", "") or ""
    used_by_ip = _client_ip()
    conn.execute(
        "UPDATE transfer_codes SET used_at=?, used_by_user_id=?, used_by_ip=? WHERE code=? AND used_at IS NULL",
        (now, used_by_uid, used_by_ip, code),
    )
    conn.commit()

    resp = jsonify({"ok": True, "user_id": owner_user_id, "message": "引き継ぎが完了しました。再読み込みします。"})
    _set_uid_cookie_on_response(resp, owner_user_id)
    return resp

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

@app.get("/romaji")
@app.get("/romaji/")
def romaji_en() -> Response:
    """English: Romaji for Singing Japanese (PH entry)"""
    try:
        return send_from_directory(str(BASE_DIR / "romaji"), "index.html")
    except Exception as e:
        app.logger.exception("Error serving romaji/index.html: %s", e)
        raise


@app.get("/en")
def en_redirect() -> Response:
    """Force trailing slash to avoid relative-path resolution bugs (e.g. ./style.css -> /style.css)."""
    from flask import redirect
    return redirect("/en/", code=301)


@app.get("/en/")
def en_landing() -> Response:
    """English LP (isolated under /en/ to avoid mixing with JP assets/CSS)."""
    try:
        return send_from_directory(str(BASE_DIR / "en"), "index.html")
    except Exception as e:
        app.logger.exception("Error serving en/index.html: %s", e)
        raise


@app.get("/en/<path:filename>")
def en_static(filename: str) -> Response:
    """Serve EN static assets (e.g. /en/style.css)."""
    try:
        return send_from_directory(str(BASE_DIR / "en"), filename)
    except Exception as e:
        app.logger.exception("Error serving en asset %s: %s", filename, e)
        raise

@app.get("/guide")
def guide_redirect() -> Response:
    from flask import redirect
    return redirect("/guide/features.html", code=301)

@app.get("/guide/")
def guide_index_redirect() -> Response:
    from flask import redirect
    return redirect("/guide/features.html", code=301)

@app.get("/guide/features.html")
def guide_features() -> Response:
    try:
        return send_from_directory(str(BASE_DIR / "guide"), "features.html")
    except Exception as e:
        app.logger.exception("Error serving guide/features.html: %s", e)
        return _json_error(500, "file_not_found", "機能ガイドページが見つかりません。"), 500

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

@app.get("/tokusho")
@app.get("/tokusho/")
@app.get("/tokusho.html")
def tokusho_html():
    """特定商取引法に基づく表記"""
    try:
        return send_from_directory(str(BASE_DIR), "tokusho.html")
    except Exception as e:
        app.logger.exception("Error serving tokusho.html: %s", e)
        return _json_error(500, "file_not_found", "特定商取引法ページが見つかりません。"), 500

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

# ===== エントリポイント（ローカル開発用） ==============================

if __name__ == "__main__":
    # 開発用サーバー（本番は gunicorn＋nginx 経由）
    app.run(host="127.0.0.1", port=5000, debug=True)
