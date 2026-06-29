# Village Information Portal — FastAPI Edition

A small village/panchayat information site: public pages for services, events,
announcements, and complaint submission, plus an admin dashboard to manage all of it.

This is a **rewrite of the original Flask app to FastAPI**. Same database
shape, same templates, same JS — but the backend now runs on FastAPI +
Uvicorn instead of Flask, with JWT cookie auth instead of Flask-Login.

---

## 1. What changed from Flask → FastAPI

| Flask piece | FastAPI replacement |
|---|---|
| `Flask`, `@app.route` | `FastAPI()`, `@app.get/post/put/delete` |
| `flask_sqlalchemy` (`db.Model`) | plain `SQLAlchemy` `Base`/`Session` (`database.py`) |
| `flask_login` (`@login_required`, `UserMixin`) | JWT cookie + `Depends(get_current_admin)` (`auth.py`) |
| `flask_bcrypt` | `passlib[bcrypt]` |
| `render_template()` | `Jinja2Templates().TemplateResponse()` |
| `request.json` | Pydantic models (`schemas.py`) — auto-validated, auto-documented |
| `request.form` | `await request.form()` |
| `flash()` / session messages | `?error=...` query param read by the login template |
| dev server (`app.run`) | ASGI server: `uvicorn` |
| — | **Free interactive API docs** at `/docs` and `/redoc` (FastAPI generates these automatically) |

The HTML/CSS/JS you already had needed almost no changes — `main.js` was
already plain `fetch()` calls, and the Jinja2 template syntax (`{% for %}`,
`{{ }}`, filters like `.lower()`) is identical in both frameworks. The only
template that changed meaningfully is `admin_login.html`, since Flask's
`url_for()` and `flash()` don't exist outside Flask — they're replaced with
plain `/admin/login` paths and a query-string error message.

---

## 2. Project structure

```
village-portal/
├── main.py              # FastAPI app + all routes
├── database.py          # SQLAlchemy engine, session, models (Admin, Service, Event, Announcement, Complaint)
├── auth.py              # Password hashing + JWT cookie auth (replaces Flask-Login)
├── schemas.py            # Pydantic request/response models
├── requirements.txt
├── .env.example          # copy to .env and fill in real values
├── templates/
│   ├── index.html         # public homepage
│   ├── admin_login.html
│   └── admin_dashboard.html
└── static/
    ├── css/style.css
    └── js/main.js
```

---

## 3. Run it from scratch (local machine)

### Step 1 — Install Python
You need **Python 3.10+**. Check with:
```bash
python3 --version
```

### Step 2 — Get the project folder
Unzip the project, then open a terminal inside it:
```bash
cd village-portal
```

### Step 3 — Create a virtual environment (recommended)
```bash
python3 -m venv venv

# activate it:
source venv/bin/activate        # macOS/Linux
venv\Scripts\activate           # Windows (cmd/powershell)
```

### Step 4 — Install dependencies
```bash
pip install -r requirements.txt
```

### Step 5 — Configure environment variables
```bash
cp .env.example .env
```
Open `.env` and set a real `SECRET_KEY`. Generate one with:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
Paste the output as the value of `SECRET_KEY` in `.env`.

### Step 6 — Run the server
```bash
uvicorn main:app --reload
```
You should see the "Admin user created!" message on first run (username
`admin`, password `admin123` — **change this immediately**, see §5).

Visit:
- Public site: http://localhost:8000
- Admin login: http://localhost:8000/admin/login
- Interactive API docs (auto-generated): http://localhost:8000/docs

---

## 4. How the pieces talk to each other

1. **Public visitor** hits `/` → FastAPI queries the DB for services, events,
   announcements, complaints → renders `index.html` with that data, same as
   Flask did.
2. **Complaint form** on the homepage posts JSON to `/api/public/complaints`
   (no login needed) → validated by `PublicComplaintIn` → saved → JSON
   response read by the inline `<script>` in `index.html`.
3. **Admin login** posts a form to `/admin/login` → password checked with
   `passlib` → on success, a signed JWT is set in an `HttpOnly` cookie →
   browser is redirected to `/admin/dashboard`.
4. **Dashboard and all `/api/...` admin routes** depend on
   `get_current_admin`, which reads that cookie, verifies the JWT signature
   and expiry, and loads the matching `Admin` row. No cookie or a bad/expired
   one → redirected back to `/admin/login`.
5. **Dashboard's add/edit/delete buttons** (in `main.js` /
   `admin_dashboard.html`'s inline script) call the same `/api/services`,
   `/api/events`, `/api/announcements`, `/api/complaints` endpoints as
   before — same URLs, same JSON shapes, so the existing JS didn't need
   logic changes.

---

## 5. Before you put this in front of real users

- **Change the default admin password.** Log in with `admin` / `admin123`
  once, then add a small one-off script or shell into the DB to update the
  password hash — or extend `main.py` with a "change password" admin route.
  Don't ship the default credentials live.
- **Set a real `SECRET_KEY`** in `.env` — never use the placeholder value in
  production. Anyone who has it can forge admin login tokens.
- **Switch SQLite → Postgres** for anything beyond a single small village
  site (see §7) — SQLite is fine for development and very low traffic, but
  doesn't handle concurrent writes well and most hosts wipe its disk on
  redeploy.
- **Serve over HTTPS** and uncomment `secure=True` on the cookie in
  `auth.py`'s `set_cookie` call once you're behind HTTPS, so the cookie is
  never sent over plain HTTP.
- **Restrict CORS** if you ever split frontend and backend onto different
  domains (right now everything is served from the same FastAPI app, so this
  isn't needed yet).

---

## 6. Useful commands during development

```bash
# Run with auto-reload on code changes
uvicorn main:app --reload

# Run on a specific port
uvicorn main:app --reload --port 8080

# See and try every endpoint interactively
# (open in browser after starting the server)
http://localhost:8000/docs
```

---

## 7. Deploying it — where and how

You have three good free/cheap options. All work the same general way:
push your code to GitHub, connect the host to that repo, set environment
variables, deploy.

### Option A — Render.com (easiest, good free tier for small sites)
1. Push this project to a GitHub repository.
2. Go to https://render.com → New → **Web Service** → connect your repo.
3. Settings:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables in the Render dashboard (Environment tab):
   - `SECRET_KEY` = (your generated secret)
   - `DATABASE_URL` = (see note below on Postgres)
5. Deploy. Render gives you a free `https://yourapp.onrender.com` URL with
   HTTPS already set up.
6. **Database note:** Render's free filesystem is *not persistent* — a
   SQLite file will be wiped on every redeploy/restart. For anything you
   care about, add Render's free Postgres add-on and set `DATABASE_URL` to
   the connection string it gives you. No code changes needed — the
   `DATABASE_URL` env var already controls this in `database.py`.

### Option B — Railway.app (very similar workflow, also has free Postgres)
1. Push to GitHub.
2. https://railway.app → New Project → Deploy from GitHub repo.
3. Railway auto-detects Python; if it doesn't pick up the start command,
   add a `Procfile` with:
   ```
   web: uvicorn main:app --host 0.0.0.0 --port $PORT
   ```
4. Add a Postgres database from Railway's plugin marketplace (one click),
   copy the `DATABASE_URL` it generates into your service's variables.
5. Set `SECRET_KEY` in the Variables tab.
6. Deploy — Railway gives you a public HTTPS URL.

### Option C — A VPS (DigitalOcean, Hetzner, AWS Lightsail) — more control
1. Spin up a small Ubuntu droplet/instance.
2. SSH in, install Python, clone your repo.
3. Install dependencies in a venv as in §3.
4. Run the app behind a process manager, e.g.:
   ```bash
   pip install gunicorn
   gunicorn main:app -w 2 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
   ```
5. Put Nginx in front of it as a reverse proxy, and use Certbot
   (`sudo certbot --nginx`) for a free HTTPS certificate.
6. Use `systemd` (or `pm2`/`supervisor`) to keep the app running and
   restart it on crash/reboot.

For a single village's site, **Option A (Render) with their free Postgres
add-on** is the least amount of ongoing work.

---

## 8. Quick troubleshooting

- **"ModuleNotFoundError" on startup** → you forgot to activate the venv or
  run `pip install -r requirements.txt`.
- **Login redirects back to the login page even with correct password** →
  check that `SECRET_KEY` in `.env` didn't change between when the user
  logged in and now (changing it invalidates all existing tokens — that's
  expected and fine, just log in again).
- **Data disappears after redeploy on Render/Railway free tier** → you're
  still on SQLite; switch to their free Postgres add-on (§7).
- **CSS/JS not loading** → confirm the app was started from inside the
  `village-portal/` folder so the relative `static/` and `templates/` paths
  resolve correctly.
