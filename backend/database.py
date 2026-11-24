"""
VyaparVoice AI - Unified Database Engine
Seamlessly connects to Neon PostgreSQL (from DATABASE_URL in .env) with SQLite local fallback.
Supports:
- Multi-Shop Tenancy (Shop Owner accounts, isolated dashboards)
- Products, Inventory & SKUs
- Customer Bahi-Khata Ledgers
- Orders with PAID (✅) vs DUES (⏳) Status
- Double-entry Passbook Ledger Statements
"""

import os
import json
import re
import uuid
from datetime import datetime
from decimal import Decimal

def _clean_row(row):
    if not row:
        return None
    d = dict(row)   
    for k, v in d.items():
        if isinstance(v, Decimal):
            d[k] = float(v)
    return d

# Load .env file
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

INITIAL_SHOPS = [
    {
        "id": "SHOP-001",
        "shop_name": "Gupta Wholesale & Distribution Mart",
        "owner_name": "Sunil Gupta",
        "email": "gupta@vyapar.com",
        "phone": "+91 99223 88441",
        "password": "password123",
        "location": "Sadar Bazar, Delhi"
    },
    {
        "id": "SHOP-002",
        "shop_name": "Ramesh Kirana & General Store",
        "owner_name": "Ramesh Kumar",
        "email": "ramesh@vyapar.com",
        "phone": "+91 98112 00000",
        "password": "password123",
        "location": "Gandhi Nagar, Delhi"
    }
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
        "phone": "+91 98112 34567",
        "location": "Laxmi Nagar, Delhi",
        "credit_limit": 50000,
        "current_balance": 18400,
        "status": "active",
        "notes": "Regular buyer. Prompt on 15-day cycle."
    },
    {
        "id": "CUST-102",
        "name": "Verma Ji Bakery & Mart",
        "contact_person": "Anil Verma",
        "phone": "+91 98765 43210",
        "location": "Gandhi Nagar Market, Delhi",
        "credit_limit": 25000,
        "current_balance": 22500,
        "status": "warning",
        "notes": "Exceeds ₹20,000 threshold. Samaan nahi denge pehle purana paisa dijiye!"
    },
    {
        "id": "CUST-103",
        "name": "Gupta Retail Corner",
        "contact_person": "Sunil Gupta",
        "phone": "+91 99223 88441",
        "location": "Karol Bagh, Delhi",
        "credit_limit": 100000,
        "current_balance": 8500,
        "status": "trusted",
        "notes": "High volume trader. Trusted account."
    },
    {
        "id": "CUST-104",
        "name": "Aggarwal Daily Needs",
        "contact_person": "Mukesh Aggarwal",
        "phone": "+91 98100 12345",
        "location": "Sector 7, Rohini, Delhi",
        "credit_limit": 40000,
        "current_balance": 0,
        "status": "pristine",
        "notes": "Zero balance. Clean credit."
    }
]

# Database Wrapper to handle query differences between Postgres (%s) and SQLite (?)
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
            # Convert SQLite '?' placeholders to Postgres '%s'
            return sql.replace("?", "%s")
        return sql

    def execute(self, sql, params=()):
        formatted_sql = self._format_sql(sql)
        self._cur.execute(formatted_sql, params)
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        return _clean_row(row)

    def fetchall(self):
        rows = self._cur.fetchall()
        return [_clean_row(r) for r in rows]

    def commit(self):
        self.conn.commit()

    def cursor(self):
        return self

    def close(self):
        try:
            self._cur.close()
        except Exception:
            pass
        try:
            self.conn.close()
        except Exception:
            pass

def get_db():
    global IS_POSTGRES
    if IS_POSTGRES:
        try:
            pg_conn = psycopg2.connect(DATABASE_URL)
            return DBWrapper(pg_conn, is_pg=True)
        except Exception as e:
            print("⚠️ Neon PostgreSQL connection error, falling back to SQLite:", e)
    
    import sqlite3
    sq_conn = sqlite3.connect(SQLITE_FILE)
    sq_conn.row_factory = sqlite3.Row
    return DBWrapper(sq_conn, is_pg=False)

# Backward-compatible alias for agent_engine
get_db_connection = get_db

def init_db(force_reset=False):
    """Initializes tables and seeds initial data in Neon PostgreSQL or SQLite."""
    db = get_db()

    if db.is_pg:
        # PostgreSQL Schema
        db.execute("""
        CREATE TABLE IF NOT EXISTS shops (
            id VARCHAR(64) PRIMARY KEY,
            shop_name TEXT NOT NULL,
            owner_name TEXT NOT NULL,
            email TEXT UNIQUE,
            phone TEXT,
            password TEXT NOT NULL,
            location TEXT,
            created_at TEXT NOT NULL
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
            approved_by TEXT
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
        """)
        db.commit()
    else:
        # SQLite Schema
        db.execute("""
        CREATE TABLE IF NOT EXISTS shops (
            id TEXT PRIMARY KEY,
            shop_name TEXT NOT NULL,
            owner_name TEXT NOT NULL,
            email TEXT UNIQUE,
            phone TEXT,
            password TEXT NOT NULL,
            location TEXT,
            created_at TEXT NOT NULL
        )
        """)
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
        )
        """)
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
        )
        """)
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
            approved_by TEXT
        )
        """)
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
        )
        """)
        db.commit()

    # Seed Shops if empty
    db.execute("SELECT COUNT(*) as cnt FROM shops")
    row = db.fetchone()
    count = row["cnt"] if row else 0
    if count == 0:
        for s in INITIAL_SHOPS:
            db.execute("""
                INSERT INTO shops (id, shop_name, owner_name, email, phone, password, location, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (s["id"], s["shop_name"], s["owner_name"], s["email"], s["phone"], s["password"], s["location"], datetime.now().isoformat()))
        db.commit()

    # Seed Products for SHOP-001 & SHOP-002 if empty
    db.execute("SELECT COUNT(*) as cnt FROM products")
    row = db.fetchone()
    count = row["cnt"] if row else 0
    if count == 0:
        for shop_id in ["SHOP-001", "SHOP-002"]:
            for p in INITIAL_PRODUCTS:
                db.execute("""
                    INSERT INTO products (sku, shop_id, name, category, unit, price_per_unit, stock, min_stock)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (p["sku"], shop_id, p["name"], p["category"], p["unit"], p["price_per_unit"], p["stock"], p["min_stock"]))
        db.commit()

    # Seed Customers for SHOP-001 if empty
    db.execute("SELECT COUNT(*) as cnt FROM customers WHERE shop_id = ?", ("SHOP-001",))
    row = db.fetchone()
    count = row["cnt"] if row else 0
    if count == 0:
        for c in INITIAL_CUSTOMERS:
            db.execute("""
                INSERT INTO customers (id, shop_id, name, contact_person, phone, location, credit_limit, current_balance, status, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (c["id"], "SHOP-001", c["name"], c["contact_person"], c["phone"], c["location"], c["credit_limit"], c["current_balance"], c["status"], c["notes"]))

        sample_items = json.dumps([{"sku": "SKU-PARLE", "name": "Parle-G Glucose Biscuits", "quantity": 10, "unit": "peti", "price_per_unit": 920, "item_total": 9200}])
        db.execute("""
            INSERT INTO orders (id, shop_id, customer_id, customer_name, items_json, total_amount, payment_mode, payment_status, status, created_at, approved_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("ORD-INITIAL-01", "SHOP-001", "CUST-101", "Sharma General Store", sample_items, 9200, "credit", "DUES", "Dispatched", datetime.now().isoformat(), "Opening"))
        
        db.execute("""
            INSERT INTO orders (id, shop_id, customer_id, customer_name, items_json, total_amount, payment_mode, payment_status, status, created_at, approved_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("ORD-INITIAL-02", "SHOP-001", "CUST-104", "Aggarwal Daily Needs", sample_items, 4600, "cash", "PAID", "Dispatched", datetime.now().isoformat(), "Cash Sale"))

        db.execute("""
            INSERT INTO ledger_entries (shop_id, customer_id, order_id, entry_type, amount, previous_balance, new_balance, description, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("SHOP-001", "CUST-101", "ORD-INITIAL-01", "DEBIT", 9200, 9200, 18400, "Initial Goods Dispatched (Challan #ORD-INITIAL-01)", datetime.now().isoformat()))
        db.commit()

    db.close()

# -------------------------------------------------------------
# Shop Owner Auth & Operations
# -------------------------------------------------------------

def authenticate_shop(email_or_phone: str, password: str):
    db = get_db()
    q = email_or_phone.strip().lower()
    shop = db.execute("SELECT * FROM shops WHERE LOWER(email) = ? OR phone = ?", (q, email_or_phone.strip())).fetchone()
    db.close()
    if not shop:
        return None
    if shop["password"] == password:
        shop.pop("password", None)
        return shop
    return None

def register_shop(shop_name: str, owner_name: str, email: str, phone: str, password: str, location: str = "India"):
    db = get_db()
    # Unique Shop ID with UUID to guarantee no primary key collisions
    unique_suffix = uuid.uuid4().hex[:6].upper()
    new_shop_id = f"SHOP-{datetime.now().strftime('%y%m%d')}-{unique_suffix}"
    created_at = datetime.now().isoformat()

    # Fallback unique email if empty to satisfy PostgreSQL UNIQUE constraint
    clean_email = email.strip().lower() if email and email.strip() else f"{new_shop_id.lower()}@vyapar.in"

    try:
        db.execute("""
            INSERT INTO shops (id, shop_name, owner_name, email, phone, password, location, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (new_shop_id, shop_name.strip(), owner_name.strip(), clean_email, phone.strip(), password, location, created_at))

        for p in INITIAL_PRODUCTS:
            db.execute("""
                INSERT INTO products (sku, shop_id, name, category, unit, price_per_unit, stock, min_stock)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (p["sku"], new_shop_id, p["name"], p["category"], p["unit"], p["price_per_unit"], p["stock"], p["min_stock"]))

        db.commit()
        shop = db.execute("SELECT * FROM shops WHERE id = ?", (new_shop_id,)).fetchone()
        db.close()
        shop.pop("password", None)
        return {"status": "success", "shop": shop}
    except Exception as e:
        db.close()
        return {"status": "error", "message": f"Registration error: {str(e)}"}

def get_all_shops():
    db = get_db()
    shops = db.execute("SELECT id, shop_name, owner_name, email, phone, location FROM shops ORDER BY id ASC").fetchall()
    db.close()
    return shops

def get_shop_by_id(shop_id: str):
    db = get_db()
    shop = db.execute("SELECT id, shop_name, owner_name, email, phone, location FROM shops WHERE id = ?", (shop_id,)).fetchone()
    db.close()
    return shop

def get_all_products(shop_id: str = "SHOP-001"):
    db = get_db()
    products = db.execute("SELECT * FROM products WHERE shop_id = ? ORDER BY name ASC", (shop_id,)).fetchall()
    db.close()
    return products

def get_all_customers(shop_id: str = "SHOP-001"):
    db = get_db()
    customers = db.execute("SELECT * FROM customers WHERE shop_id = ? ORDER BY current_balance DESC", (shop_id,)).fetchall()
    db.close()
    return customers

def get_all_orders(shop_id: str = "SHOP-001"):
    db = get_db()
    rows = db.execute("SELECT * FROM orders WHERE shop_id = ? ORDER BY created_at DESC LIMIT 25", (shop_id,)).fetchall()
    orders = []
    for r in rows:
        d = dict(r)
        d["items"] = json.loads(d["items_json"])
        orders.append(d)
    db.close()
    return orders

def get_customer_history(customer_id: str, shop_id: str = "SHOP-001"):
    db = get_db()
    cust = db.execute("SELECT * FROM customers WHERE id = ? AND shop_id = ?", (customer_id, shop_id)).fetchone()
    if not cust:
        db.close()
        return None
    orders = db.execute("SELECT * FROM orders WHERE customer_id = ? AND shop_id = ? ORDER BY created_at DESC LIMIT 15", (customer_id, shop_id)).fetchall()
    orders_list = []
    for o in orders:
        od = dict(o)
        od["items"] = json.loads(od["items_json"])
        orders_list.append(od)
    ledger = db.execute("SELECT * FROM ledger_entries WHERE customer_id = ? AND shop_id = ? ORDER BY id DESC LIMIT 25", (customer_id, shop_id)).fetchall()
    db.close()
    return {
        "customer": cust,
        "recent_orders": orders_list,
        "ledger": ledger,
        "is_over_20k": cust["current_balance"] > 20000
    }

def create_or_get_customer(name: str, shop_id: str = "SHOP-001", phone: str = "", credit_limit: float = 20000):
    db = get_db()
    name_clean = name.strip()

    existing = db.execute("SELECT * FROM customers WHERE shop_id = ? AND (LOWER(name) LIKE ? OR LOWER(contact_person) LIKE ?)", 
                          (shop_id, f"%{name_clean.lower()}%", f"%{name_clean.lower()}%")).fetchone()
    if existing:
        db.close()
        return existing, False

    new_id = f"CUST-{datetime.now().strftime('%y%m%d')}-{uuid.uuid4().hex[:4].upper()}"
    phone_clean = phone.strip() or "+91 98000 00000"
    created_at = datetime.now().isoformat()
    db.execute("""
        INSERT INTO customers (id, shop_id, name, contact_person, phone, location, credit_limit, current_balance, status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (new_id, shop_id, name_clean, name_clean, phone_clean, "Local Grahak", credit_limit, 0.0, "new", f"Auto-created on {datetime.now().strftime('%d %b %Y')}"))

    db.execute("""
        INSERT INTO ledger_entries (shop_id, customer_id, order_id, entry_type, amount, previous_balance, new_balance, description, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (shop_id, new_id, None, "OPENING_BALANCE", 0.0, 0.0, 0.0, "New Bahi-Khata ledger created via voice", created_at))

    db.commit()
    new_cust = db.execute("SELECT * FROM customers WHERE id = ?", (new_id,)).fetchone()
    db.close()
    return new_cust, True

def delete_customer(customer_id: str, shop_id: str):
    """
    Permanently erases a customer and all their ledger/passbook reports for the shop.
    Just like Khatabook's delete/erase khata.
    """
    db = get_db()
    cust = db.execute("SELECT * FROM customers WHERE id = ? AND shop_id = ?", (customer_id, shop_id)).fetchone()
    if not cust:
        db.close()
        return {"status": "error", "message": "Grahak nahi mila."}
    
    # 1. Delete all ledger entries
    db.execute("DELETE FROM ledger_entries WHERE customer_id = ? AND shop_id = ?", (customer_id, shop_id))
    # 2. Delete all orders
    db.execute("DELETE FROM orders WHERE customer_id = ? AND shop_id = ?", (customer_id, shop_id))
    # 3. Delete customer record
    db.execute("DELETE FROM customers WHERE id = ? AND shop_id = ?", (customer_id, shop_id))
    db.commit()
    db.close()
    return {"status": "success", "message": f"{cust['name']} ka bahi-khata aur saare reports safaltapoorvak erase/delete kar diye gaye hain."}

def add_manual_customer(shop_id: str, name: str, phone: str = "", location: str = "Local", credit_limit: float = 20000, initial_dues: float = 0.0):
    """
    Manually adds a customer from the Khatabook UI with optional opening dues.
    """
    db = get_db()
    name_clean = name.strip()
    if not name_clean:
        db.close()
        return {"status": "error", "message": "Grahak ka naam zaroori hai."}

    new_id = f"CUST-{datetime.now().strftime('%y%m%d')}-{uuid.uuid4().hex[:4].upper()}"
    phone_clean = phone.strip() or "+91 98000 00000"
    created_at = datetime.now().isoformat()
    init_bal = float(initial_dues)

    db.execute("""
        INSERT INTO customers (id, shop_id, name, contact_person, phone, location, credit_limit, current_balance, status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (new_id, shop_id, name_clean, name_clean, phone_clean, location.strip() or "Local", credit_limit, init_bal, "active", f"Manual Entry on {datetime.now().strftime('%d %b %Y')}"))

    if init_bal > 0:
        db.execute("""
            INSERT INTO ledger_entries (shop_id, customer_id, order_id, entry_type, amount, previous_balance, new_balance, description, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (shop_id, new_id, None, "OPENING_BALANCE", init_bal, 0.0, init_bal, "Purana Bakaya (Opening Dues Balance)", created_at))
    else:
        db.execute("""
            INSERT INTO ledger_entries (shop_id, customer_id, order_id, entry_type, amount, previous_balance, new_balance, description, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (shop_id, new_id, None, "OPENING_BALANCE", 0.0, 0.0, 0.0, "Naya Bahi-Khata Khata Shuru", created_at))

    db.commit()
    new_cust = db.execute("SELECT * FROM customers WHERE id = ?", (new_id,)).fetchone()
    db.close()
    return {"status": "success", "customer": new_cust}

def record_customer_payment(customer_id: str, shop_id: str, amount: float, note: str = "Cash received via voice"):
    db = get_db()
    cust = db.execute("SELECT * FROM customers WHERE id = ? AND shop_id = ?", (customer_id, shop_id)).fetchone()
    if not cust:
        db.close()
        return {"status": "error", "message": "Grahak nahi mila."}

    prev_balance = float(cust["current_balance"])
    new_balance = max(0.0, prev_balance - amount)
    now_ts = datetime.now().isoformat()

    db.execute("""
        INSERT INTO ledger_entries (shop_id, customer_id, order_id, entry_type, amount, previous_balance, new_balance, description, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (shop_id, customer_id, None, "PAYMENT_RECEIVED", amount, prev_balance, new_balance, f"Payment Received: {note}", now_ts))

    db.execute("UPDATE customers SET current_balance = ? WHERE id = ? AND shop_id = ?", (new_balance, customer_id, shop_id))
    db.commit()
    db.close()

    return {
        "status": "success",
        "customer_name": cust["name"],
        "amount_paid": amount,
        "previous_balance": prev_balance,
        "new_balance": new_balance,
        "timestamp": now_ts,
        "message": f"{cust['name']} ka ₹{amount:,.0f} payment jama ho gaya. Naya bakaya: ₹{new_balance:,.0f}"
    }

def get_full_state(shop_id: str = "SHOP-001"):
    shop = get_shop_by_id(shop_id) or INITIAL_SHOPS[0]
    customers = get_all_customers(shop_id)
    products = get_all_products(shop_id)
    orders = get_all_orders(shop_id)

    total_dues = sum(float(c["current_balance"]) for c in customers)
    total_sales = sum(float(o["total_amount"]) for o in orders if o["status"] != "Cancelled")
    paid_count = sum(1 for o in orders if o.get("payment_status") == "PAID")
    dues_count = sum(1 for o in orders if o.get("payment_status") == "DUES")

    return {
        "shop": shop,
        "products": products,
        "customers": customers,
        "recent_orders": orders,
        "stats": {
            "total_receivables": total_dues,
            "total_sales": total_sales,
            "total_grahak": len(customers),
            "orders_count": len(orders),
            "paid_orders": paid_count,
            "dues_orders": dues_count
        }
    }
