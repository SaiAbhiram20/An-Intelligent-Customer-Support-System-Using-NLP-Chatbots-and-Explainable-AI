# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend (Python/Flask)
```bash
# Activate virtualenv (Windows)
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Run the Flask API server (port 5000)
python app.py

# Run all tests
pytest test_app.py -v

# Run a single test class or function
pytest test_app.py::TestSentiment -v
pytest test_app.py::TestAPI::test_chat -v
```

### Frontend (React/Vite)
```bash
cd frontend
npm install
npm run dev      # dev server at http://localhost:5173
npm run build
npm run lint
```

### Database Setup (first time)
```powershell
powershell -ExecutionPolicy Bypass -File ".\setup_db.ps1" -DB_PORT 9403 -DB_PASSWORD "YourPassword"
```

## Architecture

This is a **custom NLP customer support chatbot** — no external AI/ML libraries. All intelligence is hand-coded.

### Backend (`app.py` + `db_service.py`)

The `/api/chat` endpoint runs every message through a sequential pipeline:

```
preprocess() → analyze_sentiment() → classify_intent() → extract_ids()
    → gather_db_context() → build_genuine_response() → compute_confidence() → evaluate_handoff()
```

- **`preprocess`**: Lowercases, strips punctuation, tokenizes
- **`analyze_sentiment`**: Lexicon-based with negation (`NEGATORS`) and intensification (`INTENSIFIERS`) handling
- **`classify_intent`**: Keyword-coverage scoring across 10 intent categories (`INTENT_KEYWORDS`)
- **`extract_ids`**: Regex extracts `ORD-`, `CUST-`, `TXN-`, `SUB-` prefixed IDs from free text
- **`gather_db_context`**: Queries PostgreSQL for all referenced entities; also runs `check_refund_eligibility` when intent is `refund`/`billing`
- **`build_genuine_response`**: Branches on which entities were found (order > transaction > customer > subscription > no-data); empathy prefix added when `sentiment.intensity > 0.2` and label is `negative`
- **`compute_confidence`**: 5-factor weighted score: Intent Match (30%) + Intent Clarity (20%) + Query Specificity (15%) + Sentiment Alignment (10%) + **Data Verification (25%)**. The DB verification factor is the key differentiator — verified responses score ~25pts higher.
- **`evaluate_handoff`**: Triggers if score < 35 or frustration intensity > 0.6

**`db_service.py`** uses a `psycopg2.pool.ThreadedConnectionPool` (2–10 connections). The `@db_operation` decorator wraps all query functions to return `None` on failure instead of raising, so the app degrades gracefully without a DB connection. `get_order_by_id` performs 3 sequential queries (order + items + latest transaction).

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Returns DB status and version |
| POST | `/api/chat` | Main NLP pipeline; body: `{"message": "...", "session_id": "..."}` |
| POST | `/api/feedback` | Logs feedback JSON |

### Frontend (`frontend/src/App.jsx`)

React 19 + Vite. Has a **"Live API" toggle** (top-right):
- Unchecked (default): uses hardcoded mock data (no backend needed)
- Checked: calls Flask at `http://localhost:5000`

Both servers must run simultaneously for Live API mode.

### Database Schema (`schema.sql`)

PostgreSQL with UUID internal PKs and human-readable business IDs:
- `customers` → `CUST-XXXXXX`
- `orders` → `ORD-XXXXXX` (has `order_items` child table)
- `transactions` → `TXN-XXXXXX` (linked to both orders and subscriptions)
- `subscriptions` → `SUB-XXXXXX`

All tables use an `update_timestamp()` trigger for `updated_at`. The `orders.status` and `transactions.status` columns use PostgreSQL CHECK constraints — valid values are defined in `schema.sql`.

### Environment (`.env`)

Required variables: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `PORT`, `FLASK_ENV`. The app starts and serves chat requests even without a DB connection — it just won't do data verification (confidence scores will be lower).

## Testing Notes

Tests in `test_app.py` import NLP functions directly from `app.py` and use Flask's `test_client`. Most tests do **not** require a live database — only `TestAPI::test_chat_with_order_id` would return a meaningful DB result if connected. The `@db_operation` decorator ensures DB tests fail gracefully when the pool is uninitialized.

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"` to keep the graph current
