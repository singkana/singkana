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
    payload: Dict[str, Any] = {"ok": False, "error": error}
    if message:
        payload["message"] = message
    payload.update(extra)
    return jsonify(payload), code

# ---- Limits / Policy ----
MAX_JSON_BYTES = int(os.getenv("MAX_JSON_BYTES", "200000"))  # 200KB default
FREE_ALLOWED_MODES = {"basic"}  # Freeで許す display_mode

def _require_json() -> Optional[Tuple[Dict[str, Any], Optional[Response]]]:
    if request.content_length is not None and request.content_length > MAX_JSON_BYTES:
        return {}, _json_error(413, "payload_too_large", "Request body is too large.", max_bytes=MAX_JSON_BYTES)

    data = request.get_json(silent=True)
    if data is None:
        return {}, _json_error(400, "bad_json", "Invalid or missing JSON body.")
    if not isinstance(data, dict):
        return {}, _json_error(400, "bad_json", "JSON body must be an object.")
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
UID_RE = re.compile(r"^sk_[0-9A-HJKMNP-TV-Z]{26}$")  # ULID base32 26 chars
COOKIE_SECURE = _env("COOKIE_SECURE", "1") == "1"     # 本番=1 / ローカルhttp検証=0
DB_PATH = _env("SINGKANA_DB_PATH", str(BASE_DIR / "singkana.db"))

def _db():
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db

@app.teardown_appcontext
def _close_db(exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()

def _init_db():
    conn = sqlite3.connect(DB_PATH)
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
    conn.commit()
    conn.close()

_init_db()

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
    return resp

@app.get("/api/me")
def api_me():
    return jsonify({
        "ok": True,
        "user_id": getattr(g, "user_id", ""),
        "plan": getattr(g, "user_plan", "free"),
        "time": _utc_iso(),
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
    if getattr(g, "user_plan", "free") != "pro" and display_mode not in FREE_ALLOWED_MODES:
        return _json_error(
            402,
            "payment_required",
            "This mode is available on Pro plan.",
            requested_mode=display_mode,
            required_plan="pro",
            user_plan=getattr(g, "user_plan", "free"),
            allowed_free_modes=sorted(list(FREE_ALLOWED_MODES)),
        )

    try:
        if hasattr(engine, "convertLyrics"):
            result = engine.convertLyrics(lyrics)
        elif hasattr(engine, "convert_lyrics"):
            result = engine.convert_lyrics(lyrics)
        else:
            result = [{"en": lyrics, "kana": lyrics}]
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

_kks = kakasi()
_kks.setMode("J", "a")  # Kanji -> romaji
_kks.setMode("H", "a")  # Hiragana -> romaji
_kks.setMode("K", "a")  # Katakana -> romaji
_kks.setMode("r", "Hepburn")
_kks.setMode("s", True)  # add spaces (roughly)
_romaji_converter = _kks.getConverter()

def to_romaji(text: str) -> str:
    """Convert Japanese text to romaji while preserving line breaks."""
    lines = text.splitlines()
    out = []
    for line in lines:
        if not line.strip():
            out.append("")
            continue
        out.append(_romaji_converter.do(line).strip())
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
