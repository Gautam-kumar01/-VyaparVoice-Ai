"""
VyaparVoice AI - Unified & Hardened Database Engine
Connects to Neon PostgreSQL (from DATABASE_URL in .env) with SQLite local fallback.
Supports:
- Multi-Shop Tenancy with salted password hashes & role metadata
- Products, Inventory & SKUs
- Customer Bahi-Khata Ledgers (synthetic demo data)
- Order Drafts (Pending Confirmation & Pending HITL Approval)
- Orders with PAID / DUES / CANCELLED status & Idempotency Keys
- Immutable Audit Logs & Explicit Mock WhatsApp Outbox
"""

import os
import json
import uuid
from datetime import datetime
from decimal import Decimal
from werkzeug.security import generate_password_hash, check_password_hash

# Load .env file if present
ENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
if os.path.exists(ENV_PATH):
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
    except Exception:
        pass

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///vyaparvoice.db")
SQLITE_FILE = os.path.join(os.path.dirname(__file__), "vyaparvoice.db")

IS_POSTGRES = DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://")
if IS_POSTGRES:
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        IS_POSTGRES = False


def _clean_row(row):
    if not row:
        return None
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, Decimal):
            d[k] = float(v)
    return d


def mask_phone(phone: str) -> str:
    """Masks phone numbers for safe public/demo display."""
    if not phone:
        return "Not provided"
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    if len(digits) < 4:
        return "***"
    return f"+91 {digits[-10:-8]}*** **{digits[-3:]}"


DEMO_SHOP_IDS = ("SHOP-001", "SHOP-002")

INITIAL_SHOPS = [
    {
        "id": "SHOP-001",
        "shop_name": "Gupta Wholesale & Distribution Mart (Demo)",
        "owner_name": "Sunil Gupta",
        "email": "gupta.demo@vyaparvoice.example",
        "phone": "+91 90000 00101",
        "password_hash": generate_password_hash("DemoShop#001!"),
        "location": "Sadar Bazar, Delhi (Synthetic Demo)",
        "role": "owner",
        "is_demo": 1,
    },
    {
        "id": "SHOP-002",
        "shop_name": "Ramesh Kirana & General Store (Demo)",
        "owner_name": "Ramesh Kumar",
        "email": "ramesh.demo@vyaparvoice.example",
        "phone": "+91 90000 00102",
        "password_hash": generate_password_hash("DemoShop#002!"),
        "location": "Gandhi Nagar, Delhi (Synthetic Demo)",
        "role": "owner",
        "is_demo": 1,
    },
]

INITIAL_PRODUCTS = [
    {"sku": "SKU-PARLE", "name": "Parle-G Glucose Biscuits (Pack of 24)", "category": "Biscuits", "unit": "peti", "price_per_unit": 920, "stock": 65, "min_stock": 15},
    {"sku": "SKU-GOODDAY", "name": "Britannia Good Day Butter (Pack of 20)", "category": "Biscuits", "unit": "peti", "price_per_unit": 1280, "stock": 35, "min_stock": 10},
    {"sku": "SKU-MARIE", "name": "Marie Gold Tea Time (Pack of 20)", "category": "Biscuits", "unit": "peti", "price_per_unit": 1050, "stock": 80, "min_stock": 20},
    {"sku": "SKU-MAGGI", "name": "Maggi 2-Minute Masala Noodles (70g x 96)", "category": "Instant Food", "unit": "peti", "price_per_unit": 1350, "stock": 12, "min_stock": 15},
    {"sku": "SKU-ATTA", "name": "Aashirvaad Shudh Chakki Atta (10kg x 5)", "category": "Staples", "unit": "bori", "price_per_unit": 2100, "stock": 45, "min_stock": 10},
    {"sku": "SKU-SALT", "name": "Tata Salt Crystal (1kg x 50)", "category": "Staples", "unit": "katta", "price_per_unit": 950, "stock": 50, "min_stock": 15},
    {"sku": "SKU-OIL", "name": "Fortune Sunlite Refined Oil (15L Tin)", "category": "Edible Oil", "unit": "tin", "price_per_unit": 1850, "stock": 28, "min_stock": 8},
]

INITIAL_CUSTOMERS = [
    {
        "id": "CUST-101",
        "name": "Sharma General Store",
        "contact_person": "Rakesh Sharma",
        "phone": "+91 90000 01101",
        "location": "Laxmi Nagar, Delhi",
        "credit_limit": 50000,
        "current_balance": 18400,
        "status": "active",
        "notes": "Synthetic demo account. Regular buyer.",
    },
    {
        "id": "CUST-102",
        "name": "Verma Ji Bakery & Mart",
        "contact_person": "Anil Verma",
        "phone": "+91 90000 01102",
        "location": "Gandhi Nagar Market, Delhi",
        "credit_limit": 25000,
        "current_balance": 22500,
        "status": "warning",
        "notes": "Synthetic demo account near ₹25,000 limit; triggers approval on credit orders.",
    },
    {
        "id": "CUST-103",
        "name": "Gupta Retail Corner",
        "contact_person": "Sunil Gupta",
        "phone": "+91 90000 01103",
        "location": "Karol Bagh, Delhi",
        "credit_limit": 100000,
        "current_balance": 8500,
        "status": "trusted",
        "notes": "Synthetic demo account. High-limit trader.",
    },
    {
        "id": "CUST-104",
        "name": "Aggarwal Daily Needs",
        "contact_person": "Mukesh Aggarwal",
        "phone": "+91 90000 01104",
        "location": "Sector 7, Rohini, Delhi",
        "credit_limit": 40000,
        "current_balance": 0,
        "status": "pristine",
        "notes": "Synthetic demo account. Zero balance.",
    },
]


class DBWrapper:
    def __init__(self, raw_conn, is_pg=False):
        self.conn = raw_conn
        self.is_pg = is_pg
        if self.is_pg:
            self._cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            self._cur = self.conn.cursor()

    def _format_sql(self, sql):
        if self.is_pg:
            return sql.replace("?", "%s")
        return sql

    def execute(self, sql, params=()):
        self._cur.execute(self._format_sql(sql), params)
        return self

    def fetchone(self):
        return _clean_row(self._cur.fetchone())

    def fetchall(self):
        return [_clean_row(r) for r in self._cur.fetchall()]

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()

    def cursor(self):
        return self


def get_db():
    global IS_POSTGRES
    if IS_POSTGRES:
        try:
            pg_conn = psycopg2.connect(DATABASE_URL)
            return DBWrapper(pg_conn, is_pg=True)
        except Exception as e:
            print("⚠️ Neon PostgreSQL connection error, falling back to SQLite:", e)

    import sqlite3
    sq_conn = sqlite3.connect(SQLITE_FILE, isolation_level="DEFERRED")
    sq_conn.row_factory = sqlite3.Row
    return DBWrapper(sq_conn, is_pg=False)


get_db_connection = get_db


def _ensure_column(db, table: str, column: str, col_def: str):
    """Safely adds missing columns for backward compatibility with existing DBs."""
    try:
        if db.is_pg:
            db.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_def}")
            db.commit()
        else:
            cols = [r["name"] for r in db.execute(f"PRAGMA table_info({table})").fetchall()]
            if column not in cols:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
                db.commit()
    except Exception:
        db.rollback()


def _seed_demo_data(db):
    """Seeds only the synthetic demo shops (SHOP-001, SHOP-002) without touching real shops."""
    now = datetime.now().isoformat()

    for s in INITIAL_SHOPS:
        existing = db.execute("SELECT id FROM shops WHERE id = ?", (s["id"],)).fetchone()
        if not existing:
            db.execute("""
                INSERT INTO shops (id, shop_name, owner_name, email, phone, password, location, created_at, role, is_demo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (s["id"], s["shop_name"], s["owner_name"], s["email"], s["phone"], s["password_hash"], s["location"], now, s["role"], s["is_demo"]))
        else:
            db.execute("""
                UPDATE shops SET shop_name = ?, owner_name = ?, location = ?, is_demo = 1, role = 'owner'
                WHERE id = ?
            """, (s["shop_name"], s["owner_name"], s["location"], s["id"]))

    for shop_id in DEMO_SHOP_IDS:
        for p in INITIAL_PRODUCTS:
            existing_p = db.execute("SELECT sku FROM products WHERE sku = ? AND shop_id = ?", (p["sku"], shop_id)).fetchone()
            if existing_p:
                db.execute("""
                    UPDATE products SET name = ?, category = ?, unit = ?, price_per_unit = ?, stock = ?, min_stock = ?
                    WHERE sku = ? AND shop_id = ?
                """, (p["name"], p["category"], p["unit"], p["price_per_unit"], p["stock"], p["min_stock"], p["sku"], shop_id))
            else:
                db.execute("""
                    INSERT INTO products (sku, shop_id, name, category, unit, price_per_unit, stock, min_stock)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (p["sku"], shop_id, p["name"], p["category"], p["unit"], p["price_per_unit"], p["stock"], p["min_stock"]))

    # Seed Customers for SHOP-001 (and a lightweight set for SHOP-002)
    for c in INITIAL_CUSTOMERS:
        db.execute("""
            INSERT INTO customers (id, shop_id, name, contact_person, phone, location, credit_limit, current_balance, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (c["id"], "SHOP-001", c["name"], c["contact_person"], c["phone"], c["location"], c["credit_limit"], c["current_balance"], c["status"], c["notes"]))

    db.execute("""
        INSERT INTO customers (id, shop_id, name, contact_person, phone, location, credit_limit, current_balance, status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("CUST-201", "SHOP-002", "Mohan Kirana Corner", "Mohan Lal", "+91 90000 02201", "Gandhi Nagar, Delhi", 30000, 4500, "active", "Synthetic demo account for Shop 2."))

    sample_items = json.dumps([{"sku": "SKU-PARLE", "name": "Parle-G Glucose Biscuits (Pack of 24)", "quantity": 10, "unit": "peti", "price_per_unit": 920, "item_total": 9200}])
    db.execute("""
        INSERT INTO orders (id, shop_id, customer_id, customer_name, items_json, total_amount, payment_mode, payment_status, status, created_at, approved_by, idempotency_key)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("ORD-INITIAL-01", "SHOP-001", "CUST-101", "Sharma General Store", sample_items, 9200, "credit", "DUES", "Dispatched", now, "Demo Seed", "seed-01"))

    db.execute("""
        INSERT INTO orders (id, shop_id, customer_id, customer_name, items_json, total_amount, payment_mode, payment_status, status, created_at, approved_by, idempotency_key)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("ORD-INITIAL-02", "SHOP-001", "CUST-104", "Aggarwal Daily Needs", sample_items, 4600, "cash", "PAID", "Dispatched", now, "Demo Seed", "seed-02"))

    db.execute("""
        INSERT INTO ledger_entries (shop_id, customer_id, order_id, entry_type, amount, previous_balance, new_balance, description, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("SHOP-001", "CUST-101", "ORD-INITIAL-01", "DEBIT", 9200, 9200, 18400, "Initial Goods Dispatched (Challan #ORD-INITIAL-01)", now))

    db.commit()


def init_db(force_reset=False):
    """Initializes tables and seeds synthetic demo data. force_reset only resets seeded demo shops."""
    db = get_db()

    if db.is_pg:
        db.execute("""
        CREATE TABLE IF NOT EXISTS shops (
            id VARCHAR(64) PRIMARY KEY,
            shop_name TEXT NOT NULL,
            owner_name TEXT NOT NULL,
            email TEXT UNIQUE,
            phone TEXT,
            password TEXT NOT NULL,
            location TEXT,
            created_at TEXT NOT NULL,
            role VARCHAR(32) DEFAULT 'owner',
            is_demo INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS products (
            sku VARCHAR(64) NOT NULL,
            shop_id VARCHAR(64) NOT NULL,
            name TEXT NOT NULL,
            category TEXT,
            unit VARCHAR(32) NOT NULL,
            price_per_unit NUMERIC NOT NULL,
            stock INTEGER NOT NULL,
            min_stock INTEGER NOT NULL,
            PRIMARY KEY (sku, shop_id)
        );
        CREATE TABLE IF NOT EXISTS customers (
            id VARCHAR(64) PRIMARY KEY,
            shop_id VARCHAR(64) NOT NULL,
            name TEXT NOT NULL,
            contact_person TEXT,
            phone TEXT,
            location TEXT,
            credit_limit NUMERIC NOT NULL,
            current_balance NUMERIC NOT NULL,
            status TEXT,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS orders (
            id VARCHAR(64) PRIMARY KEY,
            shop_id VARCHAR(64) NOT NULL,
            customer_id VARCHAR(64) NOT NULL,
            customer_name TEXT NOT NULL,
            items_json TEXT NOT NULL,
            total_amount NUMERIC NOT NULL,
            payment_mode VARCHAR(32) NOT NULL,
            payment_status VARCHAR(32) NOT NULL,
            status VARCHAR(32) NOT NULL,
            created_at TEXT NOT NULL,
            approved_by TEXT,
            idempotency_key VARCHAR(128)
        );
        CREATE TABLE IF NOT EXISTS ledger_entries (
            id SERIAL PRIMARY KEY,
            shop_id VARCHAR(64) NOT NULL,
            customer_id VARCHAR(64) NOT NULL,
            order_id VARCHAR(64),
            entry_type VARCHAR(64) NOT NULL,
            amount NUMERIC NOT NULL,
            previous_balance NUMERIC NOT NULL,
            new_balance NUMERIC NOT NULL,
            description TEXT NOT NULL,
            timestamp TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS order_drafts (
            id VARCHAR(64) PRIMARY KEY,
            shop_id VARCHAR(64) NOT NULL,
            customer_id VARCHAR(64) NOT NULL,
            customer_name TEXT NOT NULL,
            items_json TEXT NOT NULL,
            total_amount NUMERIC NOT NULL,
            payment_mode VARCHAR(32) NOT NULL,
            status VARCHAR(32) NOT NULL,
            requires_approval INTEGER DEFAULT 0,
            reason TEXT,
            spoken_summary TEXT,
            idempotency_key VARCHAR(128),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS idempotency_records (
            shop_id VARCHAR(64) NOT NULL,
            idempotency_key VARCHAR(128) NOT NULL,
            endpoint VARCHAR(64) NOT NULL,
            response_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (shop_id, idempotency_key)
        );
        CREATE TABLE IF NOT EXISTS audit_logs (
            id SERIAL PRIMARY KEY,
            shop_id VARCHAR(64) NOT NULL,
            actor TEXT NOT NULL,
            action VARCHAR(64) NOT NULL,
            entity_type VARCHAR(64) NOT NULL,
            entity_id VARCHAR(64),
            details_json TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS whatsapp_outbox (
            id VARCHAR(64) PRIMARY KEY,
            shop_id VARCHAR(64) NOT NULL,
            order_id VARCHAR(64),
            customer_id VARCHAR(64),
            recipient_masked TEXT NOT NULL,
            message_text TEXT NOT NULL,
            mode VARCHAR(32) NOT NULL,
            status VARCHAR(32) NOT NULL,
            created_at TEXT NOT NULL
        );
        """)
        db.commit()
    else:
        db.execute("""
        CREATE TABLE IF NOT EXISTS shops (
            id TEXT PRIMARY KEY,
            shop_name TEXT NOT NULL,
            owner_name TEXT NOT NULL,
            email TEXT UNIQUE,
            phone TEXT,
            password TEXT NOT NULL,
            location TEXT,
            created_at TEXT NOT NULL,
            role TEXT DEFAULT 'owner',
            is_demo INTEGER DEFAULT 0
        )""")
        db.execute("""
        CREATE TABLE IF NOT EXISTS products (
            sku TEXT NOT NULL,
            shop_id TEXT NOT NULL,
            name TEXT NOT NULL,
            category TEXT,
            unit TEXT NOT NULL,
            price_per_unit REAL NOT NULL,
            stock INTEGER NOT NULL,
            min_stock INTEGER NOT NULL,
            PRIMARY KEY (sku, shop_id)
        )""")
        db.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id TEXT PRIMARY KEY,
            shop_id TEXT NOT NULL,
            name TEXT NOT NULL,
            contact_person TEXT,
            phone TEXT,
            location TEXT,
            credit_limit REAL NOT NULL,
            current_balance REAL NOT NULL,
            status TEXT,
            notes TEXT
        )""")
        db.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            shop_id TEXT NOT NULL,
            customer_id TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            items_json TEXT NOT NULL,
            total_amount REAL NOT NULL,
            payment_mode TEXT NOT NULL,
            payment_status TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            approved_by TEXT,
            idempotency_key TEXT
        )""")
        db.execute("""
        CREATE TABLE IF NOT EXISTS ledger_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id TEXT NOT NULL,
            customer_id TEXT NOT NULL,
            order_id TEXT,
            entry_type TEXT NOT NULL,
            amount REAL NOT NULL,
            previous_balance REAL NOT NULL,
            new_balance REAL NOT NULL,
            description TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )""")
        db.execute("""
        CREATE TABLE IF NOT EXISTS order_drafts (
            id TEXT PRIMARY KEY,
            shop_id TEXT NOT NULL,
            customer_id TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            items_json TEXT NOT NULL,
            total_amount REAL NOT NULL,
            payment_mode TEXT NOT NULL,
            status TEXT NOT NULL,
            requires_approval INTEGER DEFAULT 0,
            reason TEXT,
            spoken_summary TEXT,
            idempotency_key TEXT,
            created_at TEXT NOT NULL
        )""")
        db.execute("""
        CREATE TABLE IF NOT EXISTS idempotency_records (
            shop_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            response_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (shop_id, idempotency_key)
        )""")
        db.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id TEXT NOT NULL,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT,
            details_json TEXT,
            created_at TEXT NOT NULL
        )""")
        db.execute("""
        CREATE TABLE IF NOT EXISTS whatsapp_outbox (
            id TEXT PRIMARY KEY,
            shop_id TEXT NOT NULL,
            order_id TEXT,
            customer_id TEXT,
            recipient_masked TEXT NOT NULL,
            message_text TEXT NOT NULL,
            mode TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        db.commit()

    # Ensure backward-compatible columns exist on pre-existing DBs
    _ensure_column(db, "shops", "role", "TEXT DEFAULT 'owner'")
    _ensure_column(db, "shops", "is_demo", "INTEGER DEFAULT 0")
    _ensure_column(db, "orders", "idempotency_key", "TEXT")

    if force_reset:
        # SAFE RESET: Only purge and re-seed synthetic demo shops (SHOP-001, SHOP-002).
        # Real registered shops and their customers/orders are NEVER deleted.
        for demo_id in DEMO_SHOP_IDS:
            for tbl in ("whatsapp_outbox", "audit_logs", "idempotency_records", "order_drafts", "ledger_entries", "orders", "customers", "products"):
                db.execute(f"DELETE FROM {tbl} WHERE shop_id = ?", (demo_id,))
        db.commit()
        _seed_demo_data(db)
        db.close()
        return

    # Initial seed if demo shops are absent
    cnt_row = db.execute("SELECT COUNT(*) as cnt FROM shops WHERE id IN (?, ?)", DEMO_SHOP_IDS).fetchone()
    if not cnt_row or cnt_row["cnt"] == 0:
        _seed_demo_data(db)
    else:
        # Ensure existing demo shops have hashed passwords & is_demo=1
        for s in INITIAL_SHOPS:
            row = db.execute("SELECT id, password FROM shops WHERE id = ?", (s["id"],)).fetchone()
            if row and not str(row["password"]).startswith(("scrypt:", "pbkdf2:")):
                db.execute("UPDATE shops SET password = ?, is_demo = 1, role = 'owner' WHERE id = ?", (s["password_hash"], s["id"]))
        db.commit()

    db.close()


def log_audit(db, shop_id: str, actor: str, action: str, entity_type: str, entity_id: str = None, details: dict = None):
    """Writes an immutable audit entry using the caller's DB transaction or a standalone connection."""
    now = datetime.now().isoformat()
    db.execute("""
        INSERT INTO audit_logs (shop_id, actor, action, entity_type, entity_id, details_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (shop_id, actor, action, entity_type, entity_id, json.dumps(details or {}, default=str), now))


def authenticate_shop(email_or_phone: str, password: str):
    db = get_db()
    q = email_or_phone.strip().lower()
    shop = db.execute("SELECT * FROM shops WHERE LOWER(email) = ? OR phone = ?", (q, email_or_phone.strip())).fetchone()
    if not shop:
        db.close()
        return None

    stored_pw = str(shop.get("password", ""))
    valid = False
    if stored_pw.startswith(("scrypt:", "pbkdf2:")):
        valid = check_password_hash(stored_pw, password)
    elif stored_pw and stored_pw == password:
        # Legacy plaintext row upgrade on successful login
        valid = True
        db.execute("UPDATE shops SET password = ? WHERE id = ?", (generate_password_hash(password), shop["id"]))
        db.commit()

    db.close()
    if valid:
        shop.pop("password", None)
        return shop
    return None


def get_demo_shop_for_login(shop_id: str):
    """Allows 1-click demo session login ONLY for explicitly marked synthetic demo shops."""
    if shop_id not in DEMO_SHOP_IDS:
        return None
    db = get_db()
    shop = db.execute(
        "SELECT id, shop_name, owner_name, email, phone, location, role, is_demo FROM shops WHERE id = ? AND is_demo = 1",
        (shop_id,),
    ).fetchone()
    db.close()
    return shop


def register_shop(shop_name: str, owner_name: str, email: str, phone: str, password: str, location: str = "India"):
    if len(password or "") < 8:
        return {"status": "error", "message": "Password kam se kam 8 characters ka hona chahiye."}

    db = get_db()
    unique_suffix = uuid.uuid4().hex[:6].upper()
    new_shop_id = f"SHOP-{datetime.now().strftime('%y%m%d')}-{unique_suffix}"
    created_at = datetime.now().isoformat()
    clean_email = email.strip().lower() if email and email.strip() else f"{new_shop_id.lower()}@vyapar.local"
    pw_hash = generate_password_hash(password)

    try:
        db.execute("""
            INSERT INTO shops (id, shop_name, owner_name, email, phone, password, location, created_at, role, is_demo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (new_shop_id, shop_name.strip(), owner_name.strip(), clean_email, phone.strip(), pw_hash, location.strip() or "India", created_at, "owner", 0))

        for p in INITIAL_PRODUCTS:
            db.execute("""
                INSERT INTO products (sku, shop_id, name, category, unit, price_per_unit, stock, min_stock)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (p["sku"], new_shop_id, p["name"], p["category"], p["unit"], p["price_per_unit"], p["stock"], p["min_stock"]))

        log_audit(db, new_shop_id, owner_name.strip(), "SHOP_REGISTERED", "shop", new_shop_id, {"shop_name": shop_name.strip()})
        db.commit()
        shop = db.execute("SELECT id, shop_name, owner_name, email, phone, location, role, is_demo FROM shops WHERE id = ?", (new_shop_id,)).fetchone()
        db.close()
        return {"status": "success", "shop": shop}
    except Exception as e:
        db.rollback()
        db.close()
        return {"status": "error", "message": f"Registration failed: {str(e)}"}


def get_all_shops():
    """Returns only public synthetic demo shops for the demo switcher."""
    db = get_db()
    shops = db.execute(
        "SELECT id, shop_name, owner_name, location, is_demo FROM shops WHERE is_demo = 1 ORDER BY id ASC"
    ).fetchall()
    db.close()
    return shops


def get_shop_by_id(shop_id: str):
    db = get_db()
    shop = db.execute(
        "SELECT id, shop_name, owner_name, email, phone, location, role, is_demo FROM shops WHERE id = ?",
        (shop_id,),
    ).fetchone()
    db.close()
    return shop


def get_all_products(shop_id: str):
    db = get_db()
    rows = db.execute("SELECT * FROM products WHERE shop_id = ? ORDER BY name ASC", (shop_id,)).fetchall()
    db.close()
    return rows


def get_all_customers(shop_id: str):
    db = get_db()
    rows = db.execute("SELECT * FROM customers WHERE shop_id = ? ORDER BY current_balance DESC, name ASC", (shop_id,)).fetchall()
    db.close()
    is_demo = shop_id in DEMO_SHOP_IDS
    for r in rows:
        if is_demo:
            r["phone_display"] = mask_phone(r.get("phone", ""))
            r["phone"] = r["phone_display"]
        else:
            r["phone_display"] = r.get("phone", "")
    return rows


def get_all_orders(shop_id: str):
    db = get_db()
    rows = db.execute("SELECT * FROM orders WHERE shop_id = ? ORDER BY created_at DESC LIMIT 30", (shop_id,)).fetchall()
    db.close()
    for d in rows:
        try:
            d["items"] = json.loads(d["items_json"])
        except Exception:
            d["items"] = []
    return rows


def get_pending_drafts(shop_id: str):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM order_drafts WHERE shop_id = ? AND status IN ('PENDING_CONFIRMATION', 'PENDING_APPROVAL') ORDER BY created_at DESC LIMIT 10",
        (shop_id,),
    ).fetchall()
    db.close()
    for d in rows:
        try:
            d["items"] = json.loads(d["items_json"])
        except Exception:
            d["items"] = []
    return rows


def get_whatsapp_outbox(shop_id: str):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM whatsapp_outbox WHERE shop_id = ? ORDER BY created_at DESC LIMIT 15",
        (shop_id,),
    ).fetchall()
    db.close()
    return rows


def get_audit_logs(shop_id: str):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM audit_logs WHERE shop_id = ? ORDER BY id DESC LIMIT 25",
        (shop_id,),
    ).fetchall()
    db.close()
    return rows


def get_customer_history(customer_id: str, shop_id: str):
    db = get_db()
    cust = db.execute("SELECT * FROM customers WHERE id = ? AND shop_id = ?", (customer_id, shop_id)).fetchone()
    if not cust:
        db.close()
        return None
    if shop_id in DEMO_SHOP_IDS:
        cust["phone"] = mask_phone(cust.get("phone", ""))
    orders = db.execute("SELECT * FROM orders WHERE customer_id = ? AND shop_id = ? ORDER BY created_at DESC", (customer_id, shop_id)).fetchall()
    for od in orders:
        try:
            od["items"] = json.loads(od["items_json"])
        except Exception:
            od["items"] = []
    ledger = db.execute("SELECT * FROM ledger_entries WHERE customer_id = ? AND shop_id = ? ORDER BY id DESC", (customer_id, shop_id)).fetchall()
    db.close()
    return {"customer": cust, "orders": orders, "ledger": ledger}


def create_or_get_customer(name: str, shop_id: str, phone: str = "", credit_limit: float = 20000.0):
    db = get_db()
    existing = db.execute("SELECT * FROM customers WHERE LOWER(name) = LOWER(?) AND shop_id = ?", (name.strip(), shop_id)).fetchone()
    if existing:
        db.close()
        return existing, False

    cust_id = f"CUST-{uuid.uuid4().hex[:6].upper()}"
    db.execute("""
        INSERT INTO customers (id, shop_id, name, contact_person, phone, location, credit_limit, current_balance, status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (cust_id, shop_id, name.strip(), name.strip(), phone or "", "Local Market", credit_limit, 0.0, "active", "Auto-created via voice counter"))
    log_audit(db, shop_id, "VoiceAgent", "CUSTOMER_CREATED", "customer", cust_id, {"name": name.strip()})
    db.commit()
    created = db.execute("SELECT * FROM customers WHERE id = ? AND shop_id = ?", (cust_id, shop_id)).fetchone()
    db.close()
    return created, True


def delete_customer(customer_id: str, shop_id: str, actor: str = "ShopOwner"):
    db = get_db()
    cust = db.execute("SELECT id, name FROM customers WHERE id = ? AND shop_id = ?", (customer_id, shop_id)).fetchone()
    if not cust:
        db.close()
        return {"status": "error", "message": "Customer not found in this shop."}

    db.execute("DELETE FROM ledger_entries WHERE customer_id = ? AND shop_id = ?", (customer_id, shop_id))
    db.execute("DELETE FROM orders WHERE customer_id = ? AND shop_id = ?", (customer_id, shop_id))
    db.execute("DELETE FROM order_drafts WHERE customer_id = ? AND shop_id = ?", (customer_id, shop_id))
    db.execute("DELETE FROM customers WHERE id = ? AND shop_id = ?", (customer_id, shop_id))
    log_audit(db, shop_id, actor, "CUSTOMER_DELETED", "customer", customer_id, {"name": cust["name"]})
    db.commit()
    db.close()
    return {"status": "success", "deleted_id": customer_id}


def add_manual_customer(shop_id: str, name: str, phone: str = "", location: str = "Local", credit_limit: float = 20000.0, initial_dues: float = 0.0, actor: str = "ShopOwner"):
    db = get_db()
    cust_id = f"CUST-{uuid.uuid4().hex[:6].upper()}"
    status = "warning" if initial_dues > credit_limit else "active"
    db.execute("""
        INSERT INTO customers (id, shop_id, name, contact_person, phone, location, credit_limit, current_balance, status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (cust_id, shop_id, name.strip(), name.strip(), phone.strip(), location.strip(), float(credit_limit), float(initial_dues), status, "Added via Shop Dashboard"))

    if initial_dues > 0:
        db.execute("""
            INSERT INTO ledger_entries (shop_id, customer_id, order_id, entry_type, amount, previous_balance, new_balance, description, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (shop_id, cust_id, "OPENING", "DEBIT", float(initial_dues), 0.0, float(initial_dues), "Opening Udhar Balance", datetime.now().isoformat()))

    log_audit(db, shop_id, actor, "CUSTOMER_ADDED", "customer", cust_id, {"name": name.strip(), "initial_dues": float(initial_dues)})
    db.commit()
    created = db.execute("SELECT * FROM customers WHERE id = ? AND shop_id = ?", (cust_id, shop_id)).fetchone()
    db.close()
    return created


def record_customer_payment(customer_id: str, shop_id: str, amount: float, note: str = "Cash Payment Received", actor: str = "ShopOwner", idempotency_key: str = None):
    if amount <= 0:
        return {"status": "error", "message": "Payment amount must be greater than zero."}

    db = get_db()
    if idempotency_key:
        cached = db.execute(
            "SELECT response_json FROM idempotency_records WHERE shop_id = ? AND idempotency_key = ?",
            (shop_id, idempotency_key),
        ).fetchone()
        if cached:
            db.close()
            resp = json.loads(cached["response_json"])
            resp["idempotent_replay"] = True
            return resp

    cust = db.execute("SELECT * FROM customers WHERE id = ? AND shop_id = ?", (customer_id, shop_id)).fetchone()
    if not cust:
        db.close()
        return {"status": "error", "message": "Customer not found in this shop."}

    prev_balance = float(cust["current_balance"])
    new_balance = max(0.0, prev_balance - float(amount))
    now = datetime.now().isoformat()

    try:
        db.execute("UPDATE customers SET current_balance = ?, status = ? WHERE id = ? AND shop_id = ?",
                   (new_balance, "warning" if new_balance > float(cust["credit_limit"]) else "active", customer_id, shop_id))
        db.execute("""
            INSERT INTO ledger_entries (shop_id, customer_id, order_id, entry_type, amount, previous_balance, new_balance, description, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (shop_id, customer_id, None, "CREDIT_PAYMENT", float(amount), prev_balance, new_balance, note, now))

        resp = {
            "status": "success",
            "customer_name": cust["name"],
            "previous_balance": prev_balance,
            "paid_amount": float(amount),
            "new_balance": new_balance,
        }
        log_audit(db, shop_id, actor, "PAYMENT_RECORDED", "customer", customer_id, resp)
        if idempotency_key:
            db.execute("""
                INSERT INTO idempotency_records (shop_id, idempotency_key, endpoint, response_json, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (shop_id, idempotency_key, "record_payment", json.dumps(resp), now))
        db.commit()
        db.close()
        return resp
    except Exception as e:
        db.rollback()
        db.close()
        return {"status": "error", "message": f"Payment failed: {str(e)}"}


def restock_product(shop_id: str, sku: str, add_qty: int, actor: str = "ShopOwner"):
    if add_qty <= 0:
        return {"status": "error", "message": "Restock quantity must be positive."}
    db = get_db()
    prod = db.execute("SELECT * FROM products WHERE sku = ? AND shop_id = ?", (sku, shop_id)).fetchone()
    if not prod:
        db.close()
        return {"status": "error", "message": "Product not found in this shop."}
    new_stock = int(prod["stock"]) + int(add_qty)
    db.execute("UPDATE products SET stock = ? WHERE sku = ? AND shop_id = ?", (new_stock, sku, shop_id))
    log_audit(db, shop_id, actor, "PRODUCT_RESTOCKED", "product", sku, {"added": int(add_qty), "new_stock": new_stock})
    db.commit()
    db.close()
    return {"status": "success", "sku": sku, "new_stock": new_stock}


def add_product(shop_id: str, name: str, unit: str, price_per_unit: float, stock: int, min_stock: int = 10, category: str = "General", actor: str = "ShopOwner"):
    if not name.strip() or price_per_unit <= 0 or stock < 0:
        return {"status": "error", "message": "Valid product name, positive price, and non-negative stock required."}
    db = get_db()
    sku = f"SKU-{uuid.uuid4().hex[:5].upper()}"
    db.execute("""
        INSERT INTO products (sku, shop_id, name, category, unit, price_per_unit, stock, min_stock)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (sku, shop_id, name.strip()[:120], category.strip()[:40] or "General", unit.strip()[:24] or "peti", float(price_per_unit), int(stock), int(min_stock)))
    log_audit(db, shop_id, actor, "PRODUCT_ADDED", "product", sku, {"name": name.strip(), "stock": int(stock)})
    db.commit()
    db.close()
    return {"status": "success", "sku": sku}


def get_full_state(shop_id: str):
    shop = get_shop_by_id(shop_id)
    products = get_all_products(shop_id)
    customers = get_all_customers(shop_id)
    orders = get_all_orders(shop_id)
    drafts = get_pending_drafts(shop_id)
    outbox = get_whatsapp_outbox(shop_id)
    audit_logs = get_audit_logs(shop_id)

    total_receivables = sum(float(c["current_balance"]) for c in customers)
    low_stock_count = sum(1 for p in products if int(p["stock"]) <= int(p["min_stock"]))
    paid_orders_count = sum(1 for o in orders if o["payment_status"] == "PAID" and o["status"] != "Cancelled")
    dues_orders_count = sum(1 for o in orders if o["payment_status"] == "DUES" and o["status"] != "Cancelled")
    total_cash_sales = sum(float(o["total_amount"]) for o in orders if o["payment_status"] == "PAID" and o["status"] != "Cancelled")
    total_credit_sales = sum(float(o["total_amount"]) for o in orders if o["payment_status"] == "DUES" and o["status"] != "Cancelled")

    return {
        "shop": shop,
        "products": products,
        "customers": customers,
        "recent_orders": orders,
        "pending_drafts": drafts,
        "whatsapp_outbox": outbox,
        "audit_logs": audit_logs,
        "stats": {
            "total_receivables": total_receivables,
            "low_stock_count": low_stock_count,
            "total_orders": len(orders),
            "paid_orders_count": paid_orders_count,
            "dues_orders_count": dues_orders_count,
            "total_cash_sales": total_cash_sales,
            "total_credit_sales": total_credit_sales,
            "total_customers": len(customers),
            "pending_approvals_count": sum(1 for d in drafts if d["status"] == "PENDING_APPROVAL"),
            "pending_confirmations_count": sum(1 for d in drafts if d["status"] == "PENDING_CONFIRMATION"),
        },
    }
