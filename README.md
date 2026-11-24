# VyaparVoice AI (व्यापार-वाणी)
### Voice-Driven Agentic Workflow Automation for Indian Commerce & MSME Kirana

> **India's First Real-Time, Voice-First AI Bahi-Khata & Wholesale Billing System**  
> Built for the **Voice-Driven Agentic Workflow Automation** Challenge.

---

## 🌟 Short Project Description

**VyaparVoice AI (व्यापार-वाणी)** is a real-time, voice-first agentic workflow platform built for India’s 63 million+ kirana stores, wholesale traders, and MSME distributors. Instead of manually typing or flipping through paper diaries, shopkeepers speak naturally in **vernacular Hindi or code-switched Hinglish** (*"Sharma ji ko 2 peti Parle-G cash mein"*). In under **400ms**, VyaparVoice autonomously deducts warehouse stock, verifies bahi-khata credit policies, blocks dispatches if unpaid dues exceed **₹20,000**, generates printable **PAID ✓ / DUES ⏳** invoices, and dispatches instant WhatsApp receipts to customers.

---

## 🚀 Key Innovations & Capabilities

| Feature | Description |
| :--- | :--- |
| **🎙️ Sub-Second Voice AI** | Direct live microphone audio streaming with sub-400ms round-trip latency and animated waveform telemetry. |
| **🇮🇳 Vernacular & Hinglish Fluency** | Interprets regional trade terminology (*"20 peti"*, *"bori"*, *"katta"*, *"udhaari"*, *"challan"*). |
| **⚡ Multi-Tool Orchestration** | Chained execution in 1 transaction: `resolve_customer` $\to$ `check_inventory` $\to$ `check_credit_policy` $\to$ `commit_order_and_ledger` $\to$ `generate_whatsapp_challan`. |
| **🛑 ₹20,000 Credit Safety Shield** | Hard credit limit enforcement — halts automated dispatch when customer dues exceed ₹20,000 to prevent bad debt. |
| **🔄 Mid-Sentence Barge-in (Interruption)** | Supports live spoken corrections (*"Ruko ruko! Good Day cancel karo, 15 peti Marie Gold kardo!"*). |
| **📒 Khatabook-Style Bahi-Khata & Erase** | Digital passbooks with transaction history, cash payments, and 1-click **Delete/Erase Customer Khata** feature. |
| **🏪 Multi-Tenant Shop Dashboards** | Each shopkeeper gets an isolated private dashboard upon registration; all records are safely synced to cloud **Neon PostgreSQL**. |
| **📱 100% Mobile Responsive** | Native mobile bottom navigation bar (Home, Billing, Khata, Stock, Orders) optimized for one-handed smartphone use. |

---

## ☁️ Vercel Deployment Guide

VyaparVoice is pre-configured for instant **Vercel Serverless** deployment:
- `api/index.py`: Serverless WSGI Python entry point for Flask.
- `requirements.txt`: Lightweight production dependencies (`Flask`, `psycopg2-binary`, `requests`, `python-dotenv`).
- `vercel.json`: Edge routing rules mapping `/api/*` to Python serverless and `/*` to the responsive static frontend.
- `DATABASE_URL`: Cloud-hosted Neon Serverless PostgreSQL with SSL.

### Deploy in 3 Steps:
1. **Push to GitHub**:
   ```bash
   git init
   git add .
   git commit -m "Initial commit for VyaparVoice"
   git branch -M main
   git remote add origin https://github.com/<your-username>/vyaparvoice.git
   git push -u origin main
   ```
2. **Import in Vercel**:
   - Go to [Vercel Dashboard](https://vercel.com/new).
   - Click **Import** on your GitHub repository.
3. **Set Environment Variables**:
   In the Vercel project configuration, add:
   - `DATABASE_URL` = your Neon PostgreSQL connection string (from `.env`).
   - `GEMINI_API_KEY` = your Gemini API key.
   - `SECRET_KEY` = any random secret string.
4. Click **Deploy**! Your app will be live globally on a `.vercel.app` URL.

---

## 💻 Running Locally

### Option A: 1-Click Launch (Windows)
Double-click `start.bat` in the project root.

### Option B: Command Line
```bash
python backend/app.py
```
Open your browser at: **`http://localhost:5000`**
