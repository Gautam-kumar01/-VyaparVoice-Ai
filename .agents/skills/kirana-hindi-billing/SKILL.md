---
name: kirana-hindi-billing
description: >-
  Teaches the AI agent how to create bills in Hindi/Hinglish for an Indian kirana
  or wholesale shop, enforce credit limits and confirmation-before-commit, and
  accurately track, alert, and restock godown inventory.
---

# Kirana Shop Hindi Billing & Stock Tracking Skill (किराना वॉइस बिलिंग और स्टॉक गाइड)

Yeh skill AI agent ko batati hai ki ek Indian kirana ya wholesale dukan (VyaparVoice AI) ke liye **Hindi / Hinglish mein surakshit (safe) bill kaise banana hai** aur **godown stock kaise track karna hai**.

---

## 1. Bhasha aur Trade Shabd Samajhna (Hindi / Hinglish NLU Rules)

Shopkeeper aam bolchal ki Hindi ya Hinglish mein bolta hai. Agent ko yeh trade terms aur units sahi tarah map karne chahiye:

| Bolchal ke Shabd (Spoken Terms) | Meaning / Action |
| :--- | :--- |
| `peti`, `पेटी`, `bori`, `बोरी`, `katta`, `कट्टा`, `tin`, `टिन` | Wholesale packaging units |
| `ek`, `do`, `teen`, `paanch`, `das`, `bees` (`एक`, `दो`, `पाँच`, `दस`) | Numeric quantities (`1, 2, 3, 5, 10, 20`) |
| `cash`, `nakad`, `नकद`, `upi`, `paid`, `turant` | Payment mode = `cash` (`PAID`) |
| `udhar`, `credit`, `khate me`, `उधार`, `खाते में` | Payment mode = `credit` (`DUES`) |
| `jama`, `जमा`, `paisa diya`, `payment received` | Customer payment collection (`CREDIT_PAYMENT`) |
| `ruko`, `nahi`, `badlo`, `change`, `रुको`, `बदलो` | Spoken correction / barge-in on current draft |
| `cancel`, `undo`, `galti ho gayi`, `रद्द` | Cancel draft or compensating rollback |

**Mandatory Security Rule:** Price, total, credit limit, aur `shop_id` hamesha **server-side database** se hi lein — browser se aaye price ya total par kabhi bharosa na karein.

---

## 2. Hindi mein Bill Banane ka 5-Step Surakshit Workflow

Kisi bhi order ke liye seedha database update **NA karein**. Hamesha **Preview → Confirm → Commit** flow follow karein:

### Step 1: Grahak (Customer) ki Pehchan
- Active `shop_id` ke andar `resolve_customer_candidates` se customer match karein.
- Agar **0 match** ya **1 se zyada match** hon, toh ruk jayein (`NEEDS_CLARIFICATION`) aur Hindi mein saaf poochhein:
  > *"Grahak ka naam clear nahi hua. Kripya registered grahak ka poora naam bolein."*

### Step 2: Product aur Stock Check
- Product alias (jaise `parle` / `पार्ले` → `SKU-PARLE`, `atta` / `आटा` → `SKU-ATTA`) se SKU resolve karein.
- Agar item ambiguous ho (jaise sirf `"biscuit"` bola gaya ho, brand ya quantity missing ho), toh turant clarification maangein.
- Server par check karein ki `available_stock >= requested_quantity`.
- Agar stock kam ho (`INSUFFICIENT_STOCK`), toh bill na banayein aur bolein:
  > *"Maaf kijiye, [Product] ka stock sirf [X] [unit] bacha hai, aapne [Y] maanga hai."*

### Step 3: Duplicate aur Credit Limit Check
- **Duplicate Guard:** Agar pichle 90 seconds mein wahi customer, wahi items, aur wahi payment mode commit hua ho, toh ruk kar confirm karein (`NEEDS_CLARIFICATION`).
- **Credit Limit Guard (HITL):** Agar `payment_mode == "credit"` aur `current_balance + total_amount > credit_limit`:
  - Order ko **`PENDING_APPROVAL`** status mein save karein.
  - Stock ya khata update **NA karein**.
  - Spoken confirmation se isse bypass nahi kiya ja sakta — authenticated shop owner ko `/api/hitl-decision` se approve karna hoga.

### Step 4: Read-Back aur Explicit Confirmation (`PREVIEW_CONFIRMATION`)
- `order_drafts` table mein draft (`PENDING_CONFIRMATION`) save karein.
- Shopkeeper ko poora hisab Hindi mein padh kar sunayein aur dikhayein:
  > *"Read-Back: [Customer Name] ke liye [Qty] [Unit] [Item], kul rakam ₹[Total], payment mode [Cash/Credit]. Kya main yeh order pakka kar doon? Abhi stock ya khata update nahi hua hai."*
- Jab user **"Haan confirm karo"** bole ya **Confirm & Commit** button dabaye, tabhi Step 5 chalayein.

### Step 5: Atomic Commit, Mock WhatsApp Receipt aur Audit Log
- Single database transaction (`confirm_order_draft` + `Idempotency-Key`) mein:
  1. `products.stock` ghatayein (`stock - quantity`).
  2. `orders` table mein `PAID` ya `DUES` order insert karein.
  3. `ledger_entries` mein `DEBIT` entry likhein aur `customers.current_balance` update karein.
  4. `whatsapp_outbox` mein receipt queue karein (clearly labeled `MOCK_OUTBOX` jab tak live WhatsApp API connected na ho).
  5. `audit_logs` mein action record karein.
- Agar beech mein koi bhi step fail ho, toh poora transaction `rollback()` karein.

---

## 3. Spoken Correction (Barge-In) aur Safe Cancellation

- **Order Badalna (Correction):** Agar active draft maujood hai aur shopkeeper bole *"Ruko! 5 nahi 8 peti cash me kardo"*, toh `_apply_draft_correction` se draft update karein, stock/credit limit dobara check karein, aur naya Read-Back sunayein.
- **Order Cancel / Galti Sudharna (Compensating Action):** Committed order ko delete karne ke bajaye `rollback_transaction` chalayein:
  - Order ka status `Cancelled` karein.
  - Product ka stock wapas jodein (`stock + quantity`).
  - Ledger mein `COMPENSATING_REVERSAL` entry daalein aur `audit_logs` update karein.

---

## 4. Godown Stock Track aur Manage Karne ke Niyam

1. **Real-Time Deduction:** Stock sirf `confirm_order_draft` commit hone par hi kam hota hai (draft ya clarification state mein kabhi nahi).
2. **Low-Stock Alert Threshold:** Har product ka `min_stock` set hota hai. Jab `stock <= min_stock` ho (jaise Maggi 12 <= 15), toh UI aur stats mein **Low Stock Alert** highlight karein.
3. **Restocking (`POST /api/product/restock`):**
   - Naya maal godown mein aane par authenticated owner `sku` aur positive `add_qty` bhej kar stock badha sakta hai.
   - Har restock `PRODUCT_RESTOCKED` ke roop mein `audit_logs` mein darj hota hai.
4. **Naya Product Jodna (`POST /api/product/add`):**
   - Shopkeeper naya item (`name`, `unit`, `price_per_unit`, `stock`, `min_stock`) apni isolated shop inventory mein add kar sakta hai.

---

## 5. Backend API & Tool Reference

| Endpoint / Tool | Method | Auth + CSRF | Purpose |
| :--- | :--- | :--- | :--- |
| `/api/live/session` | `POST` | Yes | Mints short-lived Gemini Live ephemeral token (never exposes `GEMINI_API_KEY`) |
| `/api/execute-voice` | `POST` | Yes | Parses Hindi/Hinglish utterance, checks stock/credit, creates `PENDING_CONFIRMATION` or `PENDING_APPROVAL` draft |
| `/api/confirm-draft` | `POST` | Yes + `Idempotency-Key` | Atomically commits confirmed draft, deducts stock, updates ledger, queues `MOCK_OUTBOX` receipt |
| `/api/hitl-decision` | `POST` | Yes (Owner role) | Approves or rejects an over-limit `PENDING_APPROVAL` order |
| `/api/rollback` | `POST` | Yes | Cancels committed order, restores stock, writes `COMPENSATING_REVERSAL` ledger entry |
| `/api/product/restock` | `POST` | Yes | Adds `add_qty` to existing SKU stock and writes `audit_logs` |
| `/api/product/add` | `POST` | Yes | Adds a new product SKU to the authenticated shop's inventory |
| `/api/record-payment` | `POST` | Yes + `Idempotency-Key` | Records `CREDIT_PAYMENT` and lowers customer balance |

---

## 6. Edge-Case Decision Matrix (Safety Guardrails)

| Condition | Agent Action | DB Mutation? |
| :--- | :--- | :--- |
| Low confidence / noisy input (`"???"`) | Return `NEEDS_CLARIFICATION` and ask shopkeeper to repeat | **No** |
| Ambiguous customer or missing quantity | Return `NEEDS_CLARIFICATION` with matching options | **No** |
| Requested qty > available stock | Return `INSUFFICIENT_STOCK` with exact available count | **No** |
| Identical order within 90 seconds | Return `NEEDS_CLARIFICATION` warning about suspected duplicate | **No** |
| Credit order exceeds `credit_limit` | Save `PENDING_APPROVAL` draft; require authenticated owner approval | **No** |
| Partial DB failure during commit | Execute `db.rollback()` and return `TRANSACTION_ROLLED_BACK` | **Rolled Back** |

---

## 7. Quick Reference: End-to-End Example Conversation

- **Shopkeeper:** *"Sharma ji ko 5 peti Parle-G cash me bhej do"*
- **Agent (Preview):** *"Read-Back: Sharma General Store ke liye 5 peti Parle-G, kul ₹4,600, Cash (PAID). Kya main yeh order pakka kar doon?"*
- **Shopkeeper (Correction):** *"Ruko! 5 nahi 8 peti credit me kardo"*
- **Agent (Updated Preview):** *"Samajh gaya, update kar diya. 8 peti Parle-G, kul ₹7,360, Credit (DUES). Kya main confirm kar doon?"*
- **Shopkeeper (Confirm):** *"Haan confirm karo"*
- **Agent (Committed):** *"Order #ORD-... pakka ho gaya! Stock 8 peti kam ho gaya aur Sharma ji ke khate mein ₹7,360 jud gaye."*
