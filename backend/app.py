"""
VyaparVoice AI - Hardened Multi-Tenant Flask Web & Agentic REST API Server
Enforces:
- Signed HTTP-only session authentication & server-side shop_id/role authorization
- CSRF token validation on authenticated mutations
- Sliding-window rate limiting on sensitive endpoints
- Strict Content-Security-Policy & security headers
- Gemini Live ephemeral token minting (/api/live/session)
- Confirmation-before-commit & Idempotency-Key support
"""

import os
import secrets
import time
from collections import defaultdict, deque
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, session

try:
    from database import (
        init_db,
        get_full_state,
        get_customer_history,
        record_customer_payment,
        delete_customer,
        add_manual_customer,
        authenticate_shop,
        get_demo_shop_for_login,
        register_shop,
        get_all_shops,
        get_shop_by_id,
        restock_product,
        add_product,
        DEMO_SHOP_IDS,
    )
    from agent_engine import (
        process_voice_utterance,
        confirm_order_draft,
        approve_hitl_override,
        rollback_transaction,
        create_gemini_live_session,
    )
except ImportError:
    from backend.database import (
        init_db,
        get_full_state,
        get_customer_history,
        record_customer_payment,
        delete_customer,
        add_manual_customer,
        authenticate_shop,
        get_demo_shop_for_login,
        register_shop,
        get_all_shops,
        get_shop_by_id,
        restock_product,
        add_product,
        DEMO_SHOP_IDS,
    )
    from backend.agent_engine import (
        process_voice_utterance,
        confirm_order_draft,
        approve_hitl_override,
        rollback_transaction,
        create_gemini_live_session,
    )

init_db()

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

app = Flask(__name__, static_folder=FRONTEND_DIR)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = bool(os.environ.get("VERCEL") or os.environ.get("HTTPS_ONLY"))


# -------------------------------------------------------------
# Sliding-Window Rate Limiter & Security Headers
# -------------------------------------------------------------
_RATE_BUCKETS = defaultdict(deque)


def check_rate_limit(bucket_name: str, max_requests: int = 30, window_sec: int = 60) -> bool:
    if os.environ.get("DISABLE_RATE_LIMIT_FOR_TESTS") == "1":
        return True
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "local").split(",")[0].strip()
    key = f"{bucket_name}:{ip}"
    now = time.time()
    q = _RATE_BUCKETS[key]
    while q and q[0] < now - window_sec:
        q.popleft()
    if len(q) >= max_requests:
        return False
    q.append(now)
    return True


def _ensure_csrf():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def require_auth(require_csrf: bool = False):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            shop_id = session.get("shop_id")
            if not shop_id:
                return jsonify({"status": "error", "message": "Authentication required. Kripya login karein."}), 401

            # Never trust browser-supplied shop_id if it differs from authenticated session
            req_shop_id = request.args.get("shop_id")
            if not req_shop_id and request.is_json:
                body = request.get_json(silent=True) or {}
                req_shop_id = body.get("shop_id")
            if req_shop_id and req_shop_id != shop_id:
                return jsonify({"status": "error", "message": "Forbidden: Cross-shop access denied."}), 403

            if require_csrf and request.method in ("POST", "PUT", "PATCH", "DELETE"):
                sent_csrf = request.headers.get("X-CSRF-Token", "")
                if not sent_csrf or sent_csrf != session.get("csrf_token"):
                    return jsonify({"status": "error", "message": "Invalid or missing CSRF token."}), 403

            return fn(*args, **kwargs)
        return wrapper
    return decorator


@app.after_request
def apply_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "microphone=(self), camera=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.tailwindcss.com https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.tailwindcss.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data:; "
        "connect-src 'self' wss://generativelanguage.googleapis.com https://generativelanguage.googleapis.com; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none';"
    )
    return response


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


# -------------------------------------------------------------
# Authentication & Session Endpoints
# -------------------------------------------------------------

@app.route("/api/auth/me", methods=["GET"])
@app.route("/auth/me", methods=["GET"])
def auth_me():
    shop_id = session.get("shop_id")
    if not shop_id:
        return jsonify({"status": "unauthenticated", "authenticated": False, "demo_shops": get_all_shops()}), 200
    shop = get_shop_by_id(shop_id)
    if not shop:
        session.clear()
        return jsonify({"status": "unauthenticated", "authenticated": False, "demo_shops": get_all_shops()}), 200
    return jsonify({
        "status": "success",
        "authenticated": True,
        "shop": shop,
        "csrf_token": _ensure_csrf(),
        "state": get_full_state(shop_id),
    })


@app.route("/api/auth/demo-login", methods=["POST"])
@app.route("/auth/demo-login", methods=["POST"])
def auth_demo_login():
    """Creates an authenticated session for one of the seeded synthetic demo shops."""
    if not check_rate_limit("auth_demo", 25, 60):
        return jsonify({"status": "error", "message": "Too many login attempts. Please wait."}), 429
    data = request.get_json(silent=True) or {}
    shop_id = str(data.get("shop_id", "SHOP-001")).strip()
    shop = get_demo_shop_for_login(shop_id)
    if not shop:
        return jsonify({"status": "error", "message": "Invalid demo shop ID."}), 400

    session.clear()
    session["shop_id"] = shop["id"]
    session["owner_name"] = shop["owner_name"]
    session["role"] = shop.get("role", "owner")
    csrf = _ensure_csrf()

    return jsonify({
        "status": "success",
        "message": f"Demo session active: {shop['shop_name']}",
        "shop": shop,
        "csrf_token": csrf,
        "state": get_full_state(shop["id"]),
    })


@app.route("/api/auth/login", methods=["POST"])
@app.route("/auth/login", methods=["POST"])
def auth_login():
    if not check_rate_limit("auth_login", 15, 60):
        return jsonify({"status": "error", "message": "Too many login attempts. Please wait."}), 429
    data = request.get_json(silent=True) or {}
    email_or_phone = str(data.get("email_or_phone", "")).strip()
    password = str(data.get("password", ""))

    if not email_or_phone or not password:
        return jsonify({"status": "error", "message": "Email/Phone aur Password dalein."}), 400

    shop = authenticate_shop(email_or_phone, password)
    if not shop:
        return jsonify({"status": "error", "message": "Galat credentials. Kripya check karein."}), 401

    session.clear()
    session["shop_id"] = shop["id"]
    session["owner_name"] = shop["owner_name"]
    session["role"] = shop.get("role", "owner")
    csrf = _ensure_csrf()

    return jsonify({
        "status": "success",
        "message": f"Swagat hai, {shop['owner_name']}!",
        "shop": shop,
        "csrf_token": csrf,
        "state": get_full_state(shop["id"]),
    })


@app.route("/api/auth/register", methods=["POST"])
@app.route("/auth/register", methods=["POST"])
def auth_register():
    if not check_rate_limit("auth_register", 10, 60):
        return jsonify({"status": "error", "message": "Too many registration attempts. Please wait."}), 429
    data = request.get_json(silent=True) or {}
    shop_name = str(data.get("shop_name", "")).strip()
    owner_name = str(data.get("owner_name", "")).strip()
    email = str(data.get("email", "")).strip()
    phone = str(data.get("phone", "")).strip()
    password = str(data.get("password", ""))
    location = str(data.get("location", "India")).strip()

    if not shop_name or not owner_name or not password:
        return jsonify({"status": "error", "message": "Dukan ka naam, apna naam aur kam se kam 8-character password zaroori hai."}), 400

    res = register_shop(shop_name, owner_name, email, phone, password, location)
    if res.get("status") == "success":
        shop = res["shop"]
        session.clear()
        session["shop_id"] = shop["id"]
        session["owner_name"] = shop["owner_name"]
        session["role"] = "owner"
        csrf = _ensure_csrf()
        return jsonify({
            "status": "success",
            "message": f"Dukan '{shop_name}' safaltapoorvak ban gayi!",
            "shop": shop,
            "csrf_token": csrf,
            "state": get_full_state(shop["id"]),
        })
    return jsonify(res), 400


@app.route("/api/auth/logout", methods=["POST"])
@app.route("/auth/logout", methods=["POST"])
@require_auth(require_csrf=True)
def auth_logout():
    session.clear()
    return jsonify({"status": "success", "message": "Logged out safely."})


@app.route("/api/auth/shops", methods=["GET"])
@app.route("/auth/shops", methods=["GET"])
def list_demo_shops():
    return jsonify({"status": "success", "shops": get_all_shops()})


# -------------------------------------------------------------
# Gemini Live Audio Session Endpoint
# -------------------------------------------------------------

@app.route("/api/live/session", methods=["POST"])
@app.route("/live/session", methods=["POST"])
@require_auth(require_csrf=True)
def live_session():
    if not check_rate_limit("live_session", 20, 60):
        return jsonify({"status": "error", "message": "Rate limit exceeded for live audio sessions."}), 429
    data = request.get_json(silent=True) or {}
    language = str(data.get("language", "hi-IN")).strip()
    if language not in ("hi-IN", "en-IN"):
        language = "hi-IN"
    res = create_gemini_live_session(language=language)
    return jsonify(res), 200


# -------------------------------------------------------------
# Authenticated & Isolated Shop Operations
# -------------------------------------------------------------

@app.route("/api/state", methods=["GET"])
@app.route("/state", methods=["GET"])
@require_auth(require_csrf=False)
def get_state():
    shop_id = session["shop_id"]
    return jsonify({"status": "success", "data": get_full_state(shop_id)})


@app.route("/api/customer-history/<customer_id>", methods=["GET"])
@app.route("/customer-history/<customer_id>", methods=["GET"])
@require_auth(require_csrf=False)
def customer_history(customer_id):
    shop_id = session["shop_id"]
    history = get_customer_history(customer_id, shop_id=shop_id)
    if not history:
        return jsonify({"status": "error", "message": "Grahak is shop mein nahi mila"}), 404
    return jsonify({"status": "success", "data": history})


@app.route("/api/record-payment", methods=["POST"])
@app.route("/record-payment", methods=["POST"])
@require_auth(require_csrf=True)
def record_payment():
    shop_id = session["shop_id"]
    actor = session.get("owner_name", "ShopOwner")
    data = request.get_json(silent=True) or {}
    cust_id = str(data.get("customer_id", "")).strip()
    note = str(data.get("note", "Cash Payment via Passbook")).strip()[:160]
    idem_key = request.headers.get("Idempotency-Key") or data.get("idempotency_key")

    try:
        amount = float(data.get("amount", 0))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Invalid payment amount."}), 400

    res = record_customer_payment(cust_id, shop_id=shop_id, amount=amount, note=note, actor=actor, idempotency_key=idem_key)
    code = 200 if res.get("status") == "success" else 400
    return jsonify({"status": res.get("status"), "result": res, "state": get_full_state(shop_id)}), code


@app.route("/api/customer/delete", methods=["POST"])
@app.route("/customer/delete", methods=["POST"])
@require_auth(require_csrf=True)
def delete_customer_endpoint():
    shop_id = session["shop_id"]
    actor = session.get("owner_name", "ShopOwner")
    data = request.get_json(silent=True) or {}
    cust_id = str(data.get("customer_id", "")).strip()
    if not cust_id:
        return jsonify({"status": "error", "message": "Customer ID is required"}), 400
    res = delete_customer(cust_id, shop_id=shop_id, actor=actor)
    code = 200 if res.get("status") == "success" else 404
    return jsonify({"status": res.get("status"), "result": res, "state": get_full_state(shop_id)}), code


@app.route("/api/customer/add", methods=["POST"])
@app.route("/customer/add", methods=["POST"])
@require_auth(require_csrf=True)
def add_customer_endpoint():
    shop_id = session["shop_id"]
    actor = session.get("owner_name", "ShopOwner")
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()[:100]
    phone = str(data.get("phone", "")).strip()[:20]
    location = str(data.get("location", "Local")).strip()[:100]
    try:
        credit_limit = max(0.0, float(data.get("credit_limit", 20000)))
        initial_dues = max(0.0, float(data.get("initial_dues", 0.0)))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Invalid numeric values."}), 400

    if not name:
        return jsonify({"status": "error", "message": "Grahak ka naam zaroori hai."}), 400

    res = add_manual_customer(shop_id, name, phone, location, credit_limit, initial_dues, actor=actor)
    return jsonify({"status": "success", "result": res, "state": get_full_state(shop_id)})


@app.route("/api/execute-voice", methods=["POST"])
@app.route("/execute-voice", methods=["POST"])
@require_auth(require_csrf=True)
def execute_voice():
    if not check_rate_limit("execute_voice", 60, 60):
        return jsonify({"status": "error", "message": "Rate limit exceeded."}), 429
    shop_id = session["shop_id"]
    actor = session.get("owner_name", "ShopOwner")
    data = request.get_json(silent=True) or {}
    transcript = str(data.get("transcript", "")).strip()[:500]
    idem_key = request.headers.get("Idempotency-Key") or data.get("idempotency_key")
    force_dup = bool(data.get("force_duplicate", False))

    if not transcript:
        return jsonify({"status": "error", "message": "Transcript is empty"}), 400

    result = process_voice_utterance(transcript, shop_id=shop_id, actor=actor, idempotency_key=idem_key, force_duplicate=force_dup)
    return jsonify({"status": "success", "result": result, "state": get_full_state(shop_id)})


@app.route("/api/confirm-draft", methods=["POST"])
@app.route("/confirm-draft", methods=["POST"])
@require_auth(require_csrf=True)
def confirm_draft_endpoint():
    shop_id = session["shop_id"]
    actor = session.get("owner_name", "ShopOwner")
    data = request.get_json(silent=True) or {}
    draft_id = str(data.get("draft_id", "")).strip()
    idem_key = request.headers.get("Idempotency-Key") or data.get("idempotency_key")
    if not draft_id:
        return jsonify({"status": "error", "message": "draft_id is required"}), 400

    res = confirm_order_draft(draft_id, shop_id=shop_id, actor=actor, idempotency_key=idem_key)
    return jsonify({"status": "success", "result": res, "state": get_full_state(shop_id)})


@app.route("/api/hitl-decision", methods=["POST"])
@app.route("/hitl-decision", methods=["POST"])
@require_auth(require_csrf=True)
def hitl_decision():
    if session.get("role") != "owner":
        return jsonify({"status": "error", "message": "Only an authenticated shop owner/approver can authorize over-limit orders."}), 403
    shop_id = session["shop_id"]
    actor = session.get("owner_name", "AuthenticatedOwner")
    data = request.get_json(silent=True) or {}
    approved = bool(data.get("approved", False))
    draft_id = data.get("draft_id")
    note = str(data.get("note", "Owner Verified Override")).strip()[:160]
    idem_key = request.headers.get("Idempotency-Key") or data.get("idempotency_key")

    res = approve_hitl_override(approved, note, shop_id=shop_id, draft_id=draft_id, actor=actor, idempotency_key=idem_key)
    return jsonify({"status": "success", "result": res, "state": get_full_state(shop_id)})


@app.route("/api/rollback", methods=["POST"])
@app.route("/rollback", methods=["POST"])
@require_auth(require_csrf=True)
def rollback():
    shop_id = session["shop_id"]
    actor = session.get("owner_name", "ShopOwner")
    data = request.get_json(silent=True) or {}
    order_id = data.get("order_id")
    res = rollback_transaction(order_id=order_id, shop_id=shop_id, actor=actor)
    return jsonify({"status": "success", "result": res, "state": get_full_state(shop_id)})


@app.route("/api/product/restock", methods=["POST"])
@app.route("/product/restock", methods=["POST"])
@require_auth(require_csrf=True)
def product_restock():
    shop_id = session["shop_id"]
    actor = session.get("owner_name", "ShopOwner")
    data = request.get_json(silent=True) or {}
    sku = str(data.get("sku", "")).strip()
    try:
        add_qty = int(data.get("add_qty", 0))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Invalid quantity."}), 400
    res = restock_product(shop_id, sku, add_qty, actor=actor)
    code = 200 if res.get("status") == "success" else 400
    return jsonify({"status": res.get("status"), "result": res, "state": get_full_state(shop_id)}), code


@app.route("/api/product/add", methods=["POST"])
@app.route("/product/add", methods=["POST"])
@require_auth(require_csrf=True)
def product_add():
    shop_id = session["shop_id"]
    actor = session.get("owner_name", "ShopOwner")
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    unit = str(data.get("unit", "peti")).strip()
    category = str(data.get("category", "General")).strip()
    try:
        price = float(data.get("price_per_unit", 0))
        stock = int(data.get("stock", 0))
        min_stock = int(data.get("min_stock", 10))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Invalid numeric fields."}), 400
    res = add_product(shop_id, name, unit, price, stock, min_stock, category, actor=actor)
    code = 200 if res.get("status") == "success" else 400
    return jsonify({"status": res.get("status"), "result": res, "state": get_full_state(shop_id)}), code


@app.route("/api/reset", methods=["POST"])
@app.route("/reset", methods=["POST"])
@require_auth(require_csrf=True)
def reset():
    """Restores ONLY seeded synthetic demo shops (SHOP-001/002). Never deletes real user shops."""
    if not check_rate_limit("reset_demo", 10, 60):
        return jsonify({"status": "error", "message": "Rate limit exceeded."}), 429
    shop_id = session["shop_id"]
    if shop_id not in DEMO_SHOP_IDS:
        return jsonify({"status": "error", "message": "Demo reset is only allowed on synthetic demo shops; real shop data cannot be wiped."}), 403

    init_db(force_reset=True)
    return jsonify({
        "status": "success",
        "message": "Synthetic demo shops (SHOP-001 & SHOP-002) restored. Real accounts untouched.",
        "state": get_full_state(shop_id),
    })


@app.route("/api/health", methods=["GET"])
@app.route("/health", methods=["GET"])
def health():
    has_gemini = bool(os.environ.get("GEMINI_API_KEY", "").strip() and os.environ.get("GEMINI_API_KEY") != "your_gemini_api_key_here")
    return jsonify({
        "status": "ok",
        "app": "VyaparVoice AI",
        "gemini_live_configured": has_gemini,
        "whatsapp_integration": "MOCK_OUTBOX",
    })


@app.route("/api/index.py", methods=["GET", "POST", "OPTIONS"])
@app.route("/api/index", methods=["GET", "POST", "OPTIONS"])
def vercel_entrypoint_dispatcher():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200
    return jsonify({"status": "ok", "app": "VyaparVoice AI"}), 200


@app.route("/<path:path>", methods=["GET", "POST", "OPTIONS"])
def static_files(path):
    if path.startswith("api/"):
        return jsonify({"status": "error", "message": f"API endpoint not found: /{path}"}), 404
    file_path = os.path.join(FRONTEND_DIR, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return send_from_directory(FRONTEND_DIR, path)
    return send_from_directory(FRONTEND_DIR, "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 VyaparVoice AI running on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
