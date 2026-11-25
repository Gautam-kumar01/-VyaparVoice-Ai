"""
VyaparVoice AI - Multi-Tenant Flask Web & Agentic REST API Server
Supports Shopkeeper Login, Register, Shop Switcher, and Isolated Operations.
"""

import os
import sys
from flask import Flask, request, jsonify, send_from_directory
try:
    from database import (
        init_db, 
        get_full_state, 
        get_customer_history, 
        record_customer_payment,
        delete_customer,
        add_manual_customer,
        authenticate_shop,
        register_shop,
        get_all_shops,
        get_shop_by_id
    )
    from agent_engine import process_voice_utterance, approve_hitl_override, rollback_transaction
except ImportError:
    from backend.database import (
        init_db, 
        get_full_state, 
        get_customer_history, 
        record_customer_payment,
        delete_customer,
        add_manual_customer,
        authenticate_shop,
        register_shop,
        get_all_shops,
        get_shop_by_id
    )
    from backend.agent_engine import process_voice_utterance, approve_hitl_override, rollback_transaction

# Ensure database is initialized
init_db()

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

app = Flask(__name__, static_folder=FRONTEND_DIR)

@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")

# -------------------------------------------------------------
# Shop Owner Authentication Endpoints
# -------------------------------------------------------------

@app.route("/api/auth/login", methods=["POST"])
@app.route("/auth/login", methods=["POST"])
def auth_login():
    """Authenticates a shop owner by email/phone and password."""
    data = request.get_json() or {}
    email_or_phone = data.get("email_or_phone", "").strip()
    password = data.get("password", "").strip()

    if not email_or_phone or not password:
        return jsonify({"status": "error", "message": "Email/Phone aur Password dalein."}), 400

    shop = authenticate_shop(email_or_phone, password)
    if not shop:
        return jsonify({"status": "error", "message": "Galat credentials. Kripya check karein."}), 401

    state = get_full_state(shop["id"])
    return jsonify({
        "status": "success",
        "message": f"Swagat hai, {shop['owner_name']}!",
        "shop": shop,
        "state": state
    })

@app.route("/api/auth/register", methods=["POST"])
@app.route("/auth/register", methods=["POST"])
def auth_register():
    """Registers a new shopkeeper account and creates their private dashboard."""
    data = request.get_json() or {}
    shop_name = data.get("shop_name", "").strip()
    owner_name = data.get("owner_name", "").strip()
    email = data.get("email", "").strip()
    phone = data.get("phone", "").strip()
    password = data.get("password", "").strip()
    location = data.get("location", "India").strip()

    if not shop_name or not owner_name or not password:
        return jsonify({"status": "error", "message": "Dukan ka naam, apna naam aur password zaroori hai."}), 400

    res = register_shop(shop_name, owner_name, email, phone, password, location)
    if res.get("status") == "success":
        shop = res["shop"]
        state = get_full_state(shop["id"])
        return jsonify({
            "status": "success",
            "message": f"Dukan '{shop_name}' safaltapoorvak ban gayi!",
            "shop": shop,
            "state": state
        })
    return jsonify(res), 400

@app.route("/api/auth/shops", methods=["GET"])
@app.route("/auth/shops", methods=["GET"])
def list_demo_shops():
    """Returns available shops for easy 1-click demo switching."""
    shops = get_all_shops()
    return jsonify({"status": "success", "shops": shops})

# -------------------------------------------------------------
# Shop Data & Agentic Operational Endpoints
# -------------------------------------------------------------

@app.route("/api/state", methods=["GET"])
@app.route("/state", methods=["GET"])
def get_state():
    """Returns real-time inventory, bahi-khata ledgers, and orders for the shop."""
    shop_id = request.args.get("shop_id", "SHOP-001")
    try:
        state = get_full_state(shop_id)
        return jsonify({"status": "success", "data": state})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/customer-history/<customer_id>", methods=["GET"])
@app.route("/customer-history/<customer_id>", methods=["GET"])
def customer_history(customer_id):
    """Returns passbook statement, items taken, and PAID/DUES status."""
    shop_id = request.args.get("shop_id", "SHOP-001")
    try:
        history = get_customer_history(customer_id, shop_id=shop_id)
        if not history:
            return jsonify({"status": "error", "message": "Grahak nahi mila"}), 404
        return jsonify({"status": "success", "data": history})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/record-payment", methods=["POST"])
@app.route("/record-payment", methods=["POST"])
def record_payment():
    """Records customer payment entry."""
    data = request.get_json() or {}
    cust_id = data.get("customer_id")
    shop_id = data.get("shop_id", "SHOP-001")
    amount = float(data.get("amount", 0))
    note = data.get("note", "Cash Payment via Passbook")

    try:
        res = record_customer_payment(cust_id, shop_id=shop_id, amount=amount, note=note)
        fresh_state = get_full_state(shop_id)
        return jsonify({"status": "success", "result": res, "state": fresh_state})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/customer/delete", methods=["POST"])
@app.route("/customer/delete", methods=["POST"])
def delete_customer_endpoint():
    """Permanently deletes/erases a customer and their records for the shop."""
    data = request.get_json() or {}
    cust_id = data.get("customer_id")
    shop_id = data.get("shop_id", "SHOP-001")
    if not cust_id:
        return jsonify({"status": "error", "message": "Customer ID is required"}), 400
    try:
        res = delete_customer(cust_id, shop_id=shop_id)
        fresh_state = get_full_state(shop_id)
        return jsonify({"status": "success", "result": res, "state": fresh_state})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/customer/add", methods=["POST"])
@app.route("/customer/add", methods=["POST"])
def add_customer_endpoint():
    """Manually adds a new customer profile and ledger."""
    data = request.get_json() or {}
    shop_id = data.get("shop_id", "SHOP-001")
    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip()
    location = data.get("location", "Local").strip()
    credit_limit = float(data.get("credit_limit", 20000))
    initial_dues = float(data.get("initial_dues", 0.0))

    if not name:
        return jsonify({"status": "error", "message": "Grahak ka naam zaroori hai."}), 400

    try:
        res = add_manual_customer(shop_id, name, phone, location, credit_limit, initial_dues)
        fresh_state = get_full_state(shop_id)
        return jsonify({"status": "success", "result": res, "state": fresh_state})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/execute-voice", methods=["POST"])
@app.route("/execute-voice", methods=["POST"])
def execute_voice():
    """
    Core agentic execution endpoint.
    Expects JSON: { "transcript": "...", "shop_id": "SHOP-001" }
    """
    data = request.get_json() or {}
    transcript = data.get("transcript", "").strip()
    shop_id = data.get("shop_id", "SHOP-001")

    if not transcript:
        return jsonify({"status": "error", "message": "Transcript is empty"}), 400

    try:
        result = process_voice_utterance(transcript, shop_id=shop_id)
        fresh_state = get_full_state(shop_id)
        return jsonify({
            "status": "success",
            "result": result,
            "state": fresh_state
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/hitl-decision", methods=["POST"])
@app.route("/hitl-decision", methods=["POST"])
def hitl_decision():
    """Approves or rejects a transaction requiring human-in-the-loop authorization."""
    data = request.get_json() or {}
    approved = data.get("approved", False)
    shop_id = data.get("shop_id", "SHOP-001")
    note = data.get("note", "Manager Voice PIN Authorized")

    try:
        res = approve_hitl_override(approved, note, shop_id=shop_id)
        fresh_state = get_full_state(shop_id)
        return jsonify({
            "status": "success",
            "result": res,
            "state": fresh_state
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/rollback", methods=["POST"])
@app.route("/rollback", methods=["POST"])
def rollback():
    """Reverses the last committed transaction for this shop."""
    data = request.get_json() or {}
    shop_id = data.get("shop_id", "SHOP-001")
    try:
        res = rollback_transaction(shop_id=shop_id)
        fresh_state = get_full_state(shop_id)
        return jsonify({
            "status": "success",
            "result": res,
            "state": fresh_state
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/reset", methods=["POST"])
@app.route("/reset", methods=["POST"])
def reset():
    """Resets database to clean initial benchmark state."""
    data = request.get_json() or {}
    shop_id = data.get("shop_id", "SHOP-001")
    try:
        init_db(force_reset=True)
        fresh_state = get_full_state(shop_id)
        return jsonify({
            "status": "success",
            "message": "Demo database successfully reset to clean initial state.",
            "state": fresh_state
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/health", methods=["GET"])
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "app": "VyaparVoice AI"})

@app.route("/<path:path>", methods=["GET", "POST", "OPTIONS"])
def static_files(path):
    if (
        path.startswith("api/") or 
        path.startswith("execute-voice") or 
        path.startswith("state") or 
        path.startswith("auth/") or 
        path.startswith("customer") or
        path.startswith("record-payment")
    ):
        return jsonify({
            "status": "error",
            "message": f"API endpoint not found: /{path}",
            "environ_keys": {k: str(v) for k, v in request.environ.items() if "URI" in k or "PATH" in k or "ROUTE" in k or "VERCEL" in k or "URL" in k or "MATCH" in k or "HEADER" in k}
        }), 404
    file_path = os.path.join(FRONTEND_DIR, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return send_from_directory(FRONTEND_DIR, path)
    return send_from_directory(FRONTEND_DIR, "index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 VyaparVoice AI running on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
