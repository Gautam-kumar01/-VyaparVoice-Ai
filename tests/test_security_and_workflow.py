import os
import sys
import tempfile
import pytest

# Force isolated SQLite DB for tests BEFORE importing backend modules
TEST_DB_FILE = os.path.join(tempfile.gettempdir(), "vyaparvoice_test_suite.db")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_FILE}"
os.environ["DISABLE_RATE_LIMIT_FOR_TESTS"] = "1"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-only"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import backend.database as db_mod
db_mod.SQLITE_FILE = TEST_DB_FILE
db_mod.IS_POSTGRES = False

from backend.app import app


@pytest.fixture(autouse=True)
def fresh_db():
    if os.path.exists(TEST_DB_FILE):
        os.remove(TEST_DB_FILE)
    db_mod.init_db(force_reset=False)
    yield
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except OSError:
            pass


def demo_login(client, shop_id="SHOP-001"):
    resp = client.post("/api/auth/demo-login", json={"shop_id": shop_id})
    assert resp.status_code == 200
    data = resp.get_json()
    return data["csrf_token"], data["state"]


def test_unauthenticated_and_csrf_protection():
    client = app.test_client()
    assert client.get("/api/state").status_code == 401
    assert client.post("/api/execute-voice", json={"transcript": "test"}).status_code == 401

    csrf, _ = demo_login(client, "SHOP-001")
    # Missing CSRF header must return 403
    no_csrf = client.post("/api/execute-voice", json={"transcript": "Sharma ji ko 2 peti Parle-G cash me bhej do"})
    assert no_csrf.status_code == 403

    # With valid CSRF header succeeds
    ok = client.post(
        "/api/execute-voice",
        json={"transcript": "Sharma ji ko 2 peti Parle-G cash me bhej do"},
        headers={"X-CSRF-Token": csrf},
    )
    assert ok.status_code == 200


def test_cross_shop_authorization_and_isolation():
    client1 = app.test_client()
    csrf1, _ = demo_login(client1, "SHOP-001")

    # Attempt to read or write SHOP-002 from SHOP-001 session -> 403 Forbidden
    r_get = client1.get("/api/state?shop_id=SHOP-002")
    assert r_get.status_code == 403

    r_post = client1.post(
        "/api/execute-voice",
        json={"transcript": "test", "shop_id": "SHOP-002"},
        headers={"X-CSRF-Token": csrf1},
    )
    assert r_post.status_code == 403

    # SHOP-001 cannot fetch SHOP-002's customer CUST-201
    r_cust = client1.get("/api/customer-history/CUST-201")
    assert r_cust.status_code == 404


def test_secure_registration_and_safe_demo_reset():
    client = app.test_client()
    # Weak password rejected
    bad_reg = client.post("/api/auth/register", json={
        "shop_name": "Real Kirana",
        "owner_name": "Real Owner",
        "phone": "9999988888",
        "password": "123",
    })
    assert bad_reg.status_code == 400

    # Strong password succeeds & hashes password
    good_reg = client.post("/api/auth/register", json={
        "shop_name": "Real Kirana",
        "owner_name": "Real Owner",
        "email": "real@kirana.test",
        "phone": "9999988888",
        "password": "StrongPassword!99",
    })
    assert good_reg.status_code == 200
    real_shop_id = good_reg.get_json()["shop"]["id"]

    # Verify stored password is hashed, not plaintext
    conn = db_mod.get_db()
    row = conn.execute("SELECT password FROM shops WHERE id = ?", (real_shop_id,)).fetchone()
    conn.close()
    assert row["password"] != "StrongPassword!99"
    assert row["password"].startswith(("scrypt:", "pbkdf2:"))

    # Real shop cannot call demo reset
    csrf_real = good_reg.get_json()["csrf_token"]
    reset_real = client.post("/api/reset", json={}, headers={"X-CSRF-Token": csrf_real})
    assert reset_real.status_code == 403

    # Demo shop reset succeeds and does NOT delete real shop
    demo_client = app.test_client()
    csrf_demo, _ = demo_login(demo_client, "SHOP-001")
    reset_demo = demo_client.post("/api/reset", json={}, headers={"X-CSRF-Token": csrf_demo})
    assert reset_demo.status_code == 200
    assert db_mod.get_shop_by_id(real_shop_id) is not None


def test_confirmation_before_commit_correction_and_idempotency():
    client = app.test_client()
    csrf, initial_state = demo_login(client, "SHOP-001")
    parle_before = next(p["stock"] for p in initial_state["products"] if p["sku"] == "SKU-PARLE")

    # Step 1: Order utterance creates draft only (NO stock mutation)
    r1 = client.post(
        "/api/execute-voice",
        json={"transcript": "Sharma ji ko 5 peti Parle-G cash me bhej do"},
        headers={"X-CSRF-Token": csrf},
    )
    res1 = r1.get_json()["result"]
    assert res1["intent"] == "PREVIEW_CONFIRMATION"
    draft_id = res1["draft"]["id"]
    parle_after_preview = next(p["stock"] for p in r1.get_json()["state"]["products"] if p["sku"] == "SKU-PARLE")
    assert parle_after_preview == parle_before

    # Step 2: Spoken correction updates draft to 8 peti credit without committing
    r2 = client.post(
        "/api/execute-voice",
        json={"transcript": "Ruko! 5 nahi 8 peti credit me kardo"},
        headers={"X-CSRF-Token": csrf},
    )
    res2 = r2.get_json()["result"]
    assert res2["draft"]["items"][0]["quantity"] == 8
    assert res2["draft"]["payment_mode"] == "credit"
    parle_after_corr = next(p["stock"] for p in r2.get_json()["state"]["products"] if p["sku"] == "SKU-PARLE")
    assert parle_after_corr == parle_before

    # Step 3: Explicit confirm commits atomically with Idempotency-Key
    idem_key = "idem-order-confirm-001"
    r3 = client.post(
        "/api/confirm-draft",
        json={"draft_id": draft_id},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": idem_key},
    )
    res3 = r3.get_json()["result"]
    assert res3["intent"] == "ORDER_COMMITTED"
    assert res3["whatsapp_outbox_mode"] == "MOCK_OUTBOX"
    parle_after_commit = next(p["stock"] for p in r3.get_json()["state"]["products"] if p["sku"] == "SKU-PARLE")
    assert parle_after_commit == parle_before - 8

    # Step 4: Duplicate confirm with same Idempotency-Key does NOT double-deduct stock
    r4 = client.post(
        "/api/confirm-draft",
        json={"draft_id": draft_id},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": idem_key},
    )
    assert r4.get_json()["result"].get("idempotent_replay") is True
    parle_after_dup = next(p["stock"] for p in r4.get_json()["state"]["products"] if p["sku"] == "SKU-PARLE")
    assert parle_after_dup == parle_before - 8


def test_credit_limit_enforcement_and_hitl_approval():
    client = app.test_client()
    csrf, initial_state = demo_login(client, "SHOP-001")
    goodday_before = next(p["stock"] for p in initial_state["products"] if p["sku"] == "SKU-GOODDAY")

    # Verma Ji has 22,500 balance vs 25,000 limit; 5 peti Good Day (6,400) exceeds limit
    r1 = client.post(
        "/api/execute-voice",
        json={"transcript": "Verma ji ko 5 peti Good Day credit me bhej do"},
        headers={"X-CSRF-Token": csrf},
    )
    res1 = r1.get_json()["result"]
    assert res1["intent"] == "PENDING_HUMAN_APPROVAL"
    draft_id = res1["draft"]["id"]

    # Spoken confirmation alone cannot bypass HITL
    r_bypass = client.post(
        "/api/execute-voice",
        json={"transcript": "haan confirm karo"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r_bypass.get_json()["result"]["intent"] == "PENDING_HUMAN_APPROVAL"
    assert next(p["stock"] for p in r_bypass.get_json()["state"]["products"] if p["sku"] == "SKU-GOODDAY") == goodday_before

    # Authenticated owner approves via HITL endpoint
    r_hitl = client.post(
        "/api/hitl-decision",
        json={"approved": True, "draft_id": draft_id, "note": "Owner Verified"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r_hitl.get_json()["result"]["intent"] == "ORDER_COMMITTED"
    assert next(p["stock"] for p in r_hitl.get_json()["state"]["products"] if p["sku"] == "SKU-GOODDAY") == goodday_before - 5


def test_clarification_and_rollback_on_partial_failure():
    client = app.test_client()
    csrf, initial_state = demo_login(client, "SHOP-001")
    parle_before = next(p["stock"] for p in initial_state["products"] if p["sku"] == "SKU-PARLE")

    # Ambiguous / noisy input
    r_amb = client.post(
        "/api/execute-voice",
        json={"transcript": "kuch biscuit bhej do ???"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r_amb.get_json()["result"]["intent"] == "NEEDS_CLARIFICATION"

    # Duplicate suspicion check against seeded ORD-INITIAL-01 (10 peti Parle-G credit for Sharma)
    r_dup = client.post(
        "/api/execute-voice",
        json={"transcript": "Sharma ji ko 10 peti Parle-G credit me bhej do"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r_dup.get_json()["result"]["intent"] == "NEEDS_CLARIFICATION"

    # Valid preview (4 peti Parle-G), then simulate stock drop before confirm -> rollback cleanly
    r_prev = client.post(
        "/api/execute-voice",
        json={"transcript": "Sharma ji ko 4 peti Parle-G credit me bhej do"},
        headers={"X-CSRF-Token": csrf},
    )
    draft_id = r_prev.get_json()["result"]["draft"]["id"]

    # Force stock below 4 to trigger failure mid-transaction
    conn = db_mod.get_db()
    conn.execute("UPDATE products SET stock = 2 WHERE sku = 'SKU-PARLE' AND shop_id = 'SHOP-001'")
    conn.commit()
    conn.close()

    r_fail = client.post(
        "/api/confirm-draft",
        json={"draft_id": draft_id},
        headers={"X-CSRF-Token": csrf},
    )
    assert r_fail.get_json()["result"]["intent"] == "TRANSACTION_ROLLED_BACK"
    # Stock must remain 2 (not negative, no partial deduction) and customer balance unchanged (18,400)
    sharma = next(c for c in r_fail.get_json()["state"]["customers"] if c["id"] == "CUST-101")
    assert sharma["current_balance"] == 18400
    assert next(p["stock"] for p in r_fail.get_json()["state"]["products"] if p["sku"] == "SKU-PARLE") == 2


def test_xss_safety_and_security_headers():
    client = app.test_client()
    csrf, _ = demo_login(client, "SHOP-001")

    # Security headers & CSP present
    home_resp = client.get("/")
    assert "Content-Security-Policy" in home_resp.headers
    assert home_resp.headers.get("X-Frame-Options") == "DENY"
    assert home_resp.headers.get("X-Content-Type-Options") == "nosniff"

    # Check frontend app.js has zero .innerHTML assignments
    app_js_path = os.path.join(ROOT_DIR, "frontend", "app.js")
    with open(app_js_path, "r", encoding="utf-8") as f:
        app_js = f.read()
    assert ".innerHTML" not in app_js

    # XSS payload in customer name does not execute or break API
    r_xss = client.post(
        "/api/customer/add",
        json={"name": "<script>alert('xss')</script>", "phone": "9000000000"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r_xss.status_code == 200
    assert any(c["name"] == "<script>alert('xss')</script>" for c in r_xss.get_json()["state"]["customers"])


def test_product_add_and_restock_with_isolation():
    client = app.test_client()
    csrf, initial_state = demo_login(client, "SHOP-001")
    parle_before = next(p["stock"] for p in initial_state["products"] if p["sku"] == "SKU-PARLE")

    r_restock = client.post(
        "/api/product/restock",
        json={"sku": "SKU-PARLE", "add_qty": 20},
        headers={"X-CSRF-Token": csrf},
    )
    assert r_restock.status_code == 200
    assert next(p["stock"] for p in r_restock.get_json()["state"]["products"] if p["sku"] == "SKU-PARLE") == parle_before + 20

    r_add = client.post(
        "/api/product/add",
        json={"name": "Haldiram Bhujia", "unit": "peti", "price_per_unit": 1500, "stock": 15},
        headers={"X-CSRF-Token": csrf},
    )
    assert r_add.status_code == 200
    assert any(p["name"] == "Haldiram Bhujia" for p in r_add.get_json()["state"]["products"])

    # Cross-shop restock attempt rejected (403)
    r_cross = client.post(
        "/api/product/restock",
        json={"sku": "SKU-PARLE", "add_qty": 10, "shop_id": "SHOP-002"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r_cross.status_code == 403
