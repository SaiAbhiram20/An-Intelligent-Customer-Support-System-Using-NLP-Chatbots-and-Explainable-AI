# Intelligent Customer Support System v2.0
## NLP + Chatbots + Explainable AI + Transparent Confidence Scoring

### With Database Integration & Genuine Response Generation

---

## What's New in v2.0

| Feature | v1.0 | v2.0 |
|---------|------|------|
| Responses | Pre-written/canned | **Genuine** — built from real DB data |
| Database | None | **PostgreSQL** with orders, customers, transactions, subscriptions |
| Confidence Factors | 4 factors | **5 factors** (added Data Verification at 25%) |
| ID Extraction | None | **Auto-extracts** ORD, CUST, TXN, SUB IDs from messages |
| Response Source | Static knowledge base | **Dynamic** — different for each order/customer |
| Intent Categories | 5 | **10** (added order_status, refund, subscription, greeting, thanks, farewell) |

---

## Project Structure

```
ASE/
├── app.py                          # Flask API + NLP pipeline + genuine response generator
├── db_service.py                   # Connection pool + all DB queries
├── schema.sql                      # PostgreSQL table definitions
├── sample_data.sql                 # Sample data (7 customers, 6 orders, 7 transactions)
├── setup_db.ps1                    # Windows database setup script
├── test_app.py                     # 35+ test cases
├── requirements.txt                # Python dependencies
├── .env                            # Environment config (DB host, port, credentials)
├── .env.example                    # Template .env (safe to commit)
├── __init__.py
├── App.jsx                         # React UI source (standalone or copy to frontend)
└── frontend/                       # Vite React project
    ├── src/
    │   └── App.jsx                 # React UI with DB verification badges
    ├── package.json
    └── vite.config.js
```

> **Note:** All backend files (`app.py`, `db_service.py`, schema, etc.) live in the project **root** directory — there is no `backend/` or `database/` subfolder.

---

## Step-by-Step Setup

### STEP 1: Install PostgreSQL

Download from: https://www.postgresql.org/download/windows/

During installation:
- Remember your password
- Note your port number (default: `5432`, yours may differ — e.g. `9403`)
- Add PostgreSQL bin to PATH when prompted

Verify it works:
```powershell
psql --version
```

### STEP 2: Create the Database

```powershell
cd C:\Users\user\Downloads\ASE
powershell -ExecutionPolicy Bypass -File ".\setup_db.ps1" -DB_PORT 9403 -DB_PASSWORD "YourPassword"
```

> **Tip:** Pass your actual PostgreSQL port and password as parameters. The script defaults to port `9403` and password `postgres`.

This script:
1. Tests your PostgreSQL connection
2. Creates the `customer_support` database
3. Creates all tables (customers, orders, order_items, transactions, subscriptions)
4. Loads sample data
5. Shows you the sample IDs for testing

**If the script fails with an execution policy error**, run:
```powershell
powershell -ExecutionPolicy Bypass -File ".\setup_db.ps1"
```

**If you prefer to run manually:**
```powershell
$env:PGPASSWORD = "YourPassword"
psql -U postgres -p 9403 -c "CREATE DATABASE customer_support;"
psql -U postgres -p 9403 -d customer_support -f schema.sql
psql -U postgres -p 9403 -d customer_support -f sample_data.sql
```

### STEP 3: Create .env File

In the project root (`ASE/`), create `.env`:
```
# Database Configuration
DB_HOST=localhost
DB_PORT=9403
DB_NAME=customer_support
DB_USER=postgres
DB_PASSWORD=YourPasswordHere

# Flask
PORT=5000
FLASK_ENV=development
```

> **Important:** Update `DB_PORT` and `DB_PASSWORD` to match your PostgreSQL installation. The port may be `5432` (default) or another value like `9403`.

### STEP 4: Set Up Python Environment

```powershell
cd C:\Users\user\Downloads\ASE

# Create virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

> **Note:** If you get an execution policy error with `Activate.ps1`, run:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```

### STEP 5: Run the Backend

```powershell
python app.py
```

You should see:
```
✅ Database connected — full data verification enabled
 * Running on http://0.0.0.0:5000
```

### STEP 6: Test with PowerShell

```powershell
# Health check
Invoke-WebRequest -Uri http://localhost:5000/api/health | Select-Object -ExpandProperty Content

# Chat with order ID
$body = '{"message": "What is the status of order ORD-100001?"}'
Invoke-WebRequest -Uri http://localhost:5000/api/chat -Method POST -Body $body -ContentType "application/json" | Select-Object -ExpandProperty Content
```

### STEP 7: Set Up Frontend

The React frontend needs its own dev server (Flask only serves the API).

```powershell
cd C:\Users\user\Downloads\ASE\frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser.

> **Toggle "Live API"** checkbox in the top-right corner of the UI:
> - ☐ Unchecked (default) → uses built-in mock data (no backend needed)
> - ☑ Checked → connects to Flask backend at `http://localhost:5000`

You need **both** servers running simultaneously for Live API mode:
- Terminal 1: `python app.py` (in `ASE/`)
- Terminal 2: `npm run dev` (in `ASE/frontend/`)

### STEP 8: Run Tests

```powershell
cd C:\Users\user\Downloads\ASE
.\venv\Scripts\Activate.ps1
pytest test_app.py -v
```

---

## Sample Test Data

### Customers
| ID | Name | Subscription |
|----|------|-------------|
| CUST-001001 | Sarah Johnson | Pro ($29.99/mo) |
| CUST-001002 | Mike Chen | Basic ($9.99/mo) |
| CUST-001003 | Emily Rodriguez | Pro (cancelled) |
| CUST-001004 | David Wilson | Enterprise ($99.99/yr) |
| CUST-001005 | Lisa Martinez | Free |
| CUST-001006 | James Brown | Basic (paused) |

### Orders
| ID | Customer | Status | Total | Scenario |
|----|----------|--------|-------|----------|
| ORD-100001 | Sarah | delivered | $161.99 | Happy customer, delivered early |
| ORD-100002 | Mike | delivered | $92.38 | Wants refund (eligible, within 30 days) |
| ORD-100003 | Emily | in_transit | $215.99 | Delayed by weather |
| ORD-100004 | David | processing | $377.99 | New order, hasn't shipped |
| ORD-100005 | David | delivered | $70.78 | Old order (refund expired) |
| ORD-100006 | Lisa | cancelled | $148.38 | Cancelled before shipping |
| ORD-100007 | James | returned | $269.99 | Returned, outside refund window |

### Transactions
| ID | Type | Amount | Refund? |
|----|------|--------|---------|
| TXN-200001 | charge | $29.99 | Eligible |
| TXN-200002 | charge | $92.38 | Eligible |
| TXN-200003 | charge | $215.99 | Eligible |

---

## Test Messages to Try

| Message | What Happens |
|---------|-------------|
| `What is the status of ORD-100001?` | Looks up order → "Delivered, Wireless Headphones" |
| `I want a refund for ORD-100002` | Checks eligibility → "Eligible, $92.38" |
| `I want a refund for ORD-100007` | Checks eligibility → "Outside 30-day window" |
| `Where is ORD-100003?` | Shows tracking → "In transit, FedEx, weather delay" |
| `Show me customer CUST-001004` | Pulls profile → orders, subscription, email |
| `Check TXN-200001` | Shows transaction details |
| `I need a refund` (no ID) | Asks for order ID, lower confidence |
| `I'm extremely frustrated, terrible service` | Empathy prefix + high frustration → handoff |
| `hello` | Greeting with instructions |
| `xyzzy quantum` | Unknown intent → very low confidence → handoff |
| `ORD-999999` | ID not found error |

---

## How Confidence Scoring Works (5 Factors)

```
Final Score = (Intent Match × 30%) + (Clarity × 20%) + (Specificity × 15%) + (Sentiment × 10%) + (DB Verification × 25%)
```

| Factor | Weight | What It Measures |
|--------|--------|-----------------|
| Intent Match Strength | 30% | How well keywords match support categories |
| Intent Clarity | 20% | Gap between top intent and runner-up |
| Query Specificity | 15% | How much detail the user provided |
| Sentiment Alignment | 10% | Whether emotion fits the intent |
| **Data Verification** | **25%** | **Whether response is backed by real DB data** |

The **Data Verification** factor is what makes this system unique — when the AI can verify its response against actual database records, confidence jumps significantly. This means:

- "I want a refund" → ~35% confidence (no data to verify)
- "I want a refund for ORD-100002" → ~75% confidence (verified against DB)

---

## API Response Structure

```json
{
  "response": "Hi Sarah! Order ORD-100001 was delivered...",
  "response_meta": {
    "source": "db_order_delivered",
    "data_verified": true,
    "data_used": ["order:ORD-100001"]
  },
  "confidence": {
    "score": 65.2,
    "level": "medium",
    "description": "Moderately confident...",
    "factors": [ /* 5 factors with explanations */ ],
    "missing_information": []
  },
  "explainability": {
    "intent": { "detected": "order_status", "all_candidates": [...] },
    "sentiment": { "label": "neutral", "score": 0 },
    "database": {
      "ids_extracted": { "order_id": "ORD-100001" },
      "lookups_performed": ["Looked up order ORD-100001"],
      "data_found": true
    }
  },
  "handoff": { "recommended": false }
}
```

---

## Key Differentiators for Your Thesis

1. **Genuine Responses**: Every response is dynamically built from real database data — not pre-written templates
2. **Transparent Confidence Scoring**: Users see exactly why the AI is confident or uncertain, with a 5-factor breakdown
3. **Data Verification as Trust Signal**: The 25% "Data Verification" factor openly shows whether the response is backed by verified data
4. **Explainable AI**: Full breakdown of intent matching, sentiment analysis, database lookups, and confidence factors
5. **Proactive Human Handoff**: Automatically recommends human agents when confidence is low or frustration is high
6. **Missing Information Detection**: Tells users exactly what additional information would improve the response
