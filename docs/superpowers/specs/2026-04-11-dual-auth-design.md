# Dual Authentication Design — Chat + Dashboard

**Date:** 2026-04-11  
**Status:** Approved  

---

## Overview

Add two independent authentication gates to the chatbot application:

1. **User Auth** — required to access the chat interface
2. **Admin Auth** — required to access the Analytics Dashboard (separate credentials, modal overlay)

Both use JWT tokens stored in `localStorage` under separate keys. Sessions are fully independent — logging out of one does not affect the other.

---

## Architecture

```
Landing Page (LoginPage — two tabs)
├── [User Access tab]  → POST /api/user-login  → chat_token (localStorage)
└── [Admin Access tab] → POST /api/login        → admin_token (localStorage)

App routing:
  chat_token missing  → show LoginPage (User tab pre-selected)
  chat_token present  → show Chat view
    └── Dashboard tab clicked + admin_token missing  → show DashboardLoginModal overlay
    └── Dashboard tab clicked + admin_token present  → show Dashboard view

Logout:
  Chat logout      → clears chat_token  → returns to LoginPage
  Dashboard logout → clears admin_token → closes modal, returns to Chat view
```

---

## Backend

### New endpoint: `POST /api/user-login`

```python
@app.route('/api/user-login', methods=['POST'])
def user_login():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No credentials provided"}), 400
    username = data.get("username", "")
    password = data.get("password", "")
    if (username == os.environ.get("USER_USERNAME") and
            password == os.environ.get("USER_PASSWORD")):
        token = jwt.encode(
            {"sub": username, "role": "user", "exp": datetime.utcnow() + timedelta(hours=8)},
            os.environ["JWT_SECRET_KEY"],
            algorithm="HS256"
        )
        return jsonify({"token": token})
    return jsonify({"error": "Invalid credentials"}), 401
```

### New `.env` variables

```
USER_USERNAME=<choose>
USER_PASSWORD=<choose>
```

### Unchanged

- `POST /api/login` (admin)
- `@token_required` decorator
- `GET /api/analytics` (admin-only)
- `GET /api/retrain_feedback` (admin-only)

---

## Frontend (`App.jsx`)

### State changes

```js
// Replace single token state with two independent tokens
const [chatToken, setChatToken]   = useState(() => localStorage.getItem("chat_token") || null);
const [adminToken, setAdminToken] = useState(() => localStorage.getItem("admin_token") || null);
const [showDashboardLogin, setShowDashboardLogin] = useState(false);
```

### Routing logic

```js
if (!chatToken) return <LoginPage onChatSuccess={handleChatLogin} onAdminSuccess={handleAdminLogin} />;
```

### Modified: `LoginPage`

- Two tabs: **User Access** (default) and **Admin Access**
- User Access tab → calls `/api/user-login` → `onChatSuccess(token)`
- Admin Access tab → calls `/api/login` → `onAdminSuccess(token)` (admin can also use chat)
- Reuses existing error banner pattern for invalid credentials

### New: `DashboardLoginModal`

- Rendered as an overlay on top of the chat view (not full page)
- Admin credentials form → calls `POST /api/login`
- On success: stores `admin_token`, closes modal, switches `view` to `"dashboard"`
- Cancel button: dismisses modal, stays in chat view
- Reuses existing glassmorphism card style

### Modified: Dashboard tab click handler

```js
function handleDashboardClick() {
  if (!adminToken) { setShowDashboardLogin(true); return; }
  setView("dashboard");
}
```

### Logout handlers

```js
function handleChatLogout() {
  localStorage.removeItem("chat_token");
  setChatToken(null);
  setView("chat");
  setShowDashboardLogin(false);
}

function handleDashboardLogout() {
  localStorage.removeItem("admin_token");
  setAdminToken(null);
  setView("chat");
}
```

---

## Error Handling & Edge Cases

| Scenario | Behaviour |
|---|---|
| Chat token expires mid-session | 401 from `/api/chat` clears `chat_token`, redirects to `LoginPage` |
| Admin token expires mid-dashboard | 401 from analytics clears `admin_token`, shows `DashboardLoginModal` again |
| Backend down (mock mode) | Skip fetch; accept any non-empty credentials; generate fake local token |
| `USER_USERNAME`/`USER_PASSWORD` not set in `.env` | `os.environ.get()` returns `None`; comparison always fails; 401 returned — no crash |
| Chat logout while dashboard modal open | Clears `chat_token`, dismisses modal, returns to `LoginPage` |
| Dashboard logout | Clears `admin_token` only; chat session preserved; `view` → `"chat"` |

---

## Token Storage

| Key | Scope | Expiry |
|---|---|---|
| `chat_token` | localStorage | 8h JWT |
| `admin_token` | localStorage | 8h JWT |

Both use the same `JWT_SECRET_KEY`. Roles are embedded in the JWT payload (`role: "user"` vs `role: "admin"`) but not verified server-side for the chat endpoint (the `/api/chat` endpoint remains unauthenticated — user auth is frontend-only).

---

## Out of Scope

- Password reset / forgot password flow
- Multi-user user accounts (single shared user credential)
- Role-based content differences within the chat view
- Refresh tokens / sliding sessions
