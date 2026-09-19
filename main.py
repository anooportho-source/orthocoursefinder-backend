from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from collectors import collect_all
import os, sqlite3, time, hashlib, secrets
from pathlib import Path

APP_VERSION = "4.0"
DB_PATH = os.getenv("DATABASE_PATH", str(Path(__file__).with_name("courses.db")))
ADMIN_KEY = os.getenv("ADMIN_KEY", "")
CACHE_SECONDS = int(os.getenv("CACHE_SECONDS", "1800"))

app = FastAPI(title="OrthoCourseFinder API", version=APP_VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])
_cache = {"at": 0.0, "items": []}

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            specialty TEXT,
            city TEXT,
            country TEXT,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            price TEXT,
            format TEXT,
            organiser TEXT,
            url TEXT NOT NULL,
            source TEXT,
            course_type TEXT,
            audience_json TEXT,
            verification_status TEXT NOT NULL DEFAULT 'pending',
            last_seen INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """)
        conn.commit()

init_db()

def require_admin(request: Request):
    if not ADMIN_KEY:
        raise HTTPException(503, "ADMIN_KEY is not configured")
    supplied = request.headers.get("X-Admin-Key") or request.query_params.get("key") or ""
    if not secrets.compare_digest(supplied, ADMIN_KEY):
        raise HTTPException(401, "Invalid admin key")


def upsert_collected(items):
    import json
    now = int(time.time())
    with db() as conn:
        for c in items:
            old = conn.execute("SELECT verification_status FROM courses WHERE id=?", (c["id"],)).fetchone()
            status = old[0] if old else "pending"
            conn.execute("""
              INSERT INTO courses (id,title,specialty,city,country,start_date,end_date,price,format,organiser,url,source,course_type,audience_json,verification_status,last_seen,created_at,updated_at)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,specialty=excluded.specialty,city=excluded.city,country=excluded.country,
                start_date=excluded.start_date,end_date=excluded.end_date,price=excluded.price,format=excluded.format,
                organiser=excluded.organiser,url=excluded.url,source=excluded.source,course_type=excluded.course_type,
                audience_json=excluded.audience_json,last_seen=excluded.last_seen,updated_at=excluded.updated_at
            """, (
                c["id"], c["title"], c.get("specialty","General Orthopaedics"), c.get("city",""), c.get("country",""),
                c["start_date"], c.get("end_date", c["start_date"]), c.get("price","See organiser"), c.get("format","In person"),
                c.get("organiser",""), c["url"], c.get("source","collector"), c.get("course_type","Education Event"),
                json.dumps(c.get("audience", ["All career stages"])), status, now, now, now
            ))
        conn.commit()


def fetch_db(verified_only=True):
    import json
    q = "SELECT * FROM courses"
    args = []
    if verified_only:
        q += " WHERE verification_status='verified'"
    q += " ORDER BY start_date, title"
    with db() as conn:
        rows = conn.execute(q, args).fetchall()
    out=[]
    for r in rows:
        d=dict(r)
        d["audience"] = json.loads(d.pop("audience_json") or "[]")
        d["live"] = True
        out.append(d)
    return out

@app.get("/health")
def health():
    with db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
        verified = conn.execute("SELECT COUNT(*) FROM courses WHERE verification_status='verified'").fetchone()[0]
    return {"ok": True, "version": APP_VERSION, "courses": total, "verified": verified}

@app.post("/api/refresh")
def refresh_courses(request: Request):
    require_admin(request)
    items = collect_all()
    upsert_collected(items)
    _cache["at"] = time.time(); _cache["items"] = items
    return {"ok": True, "collected": len(items)}

@app.get("/api/courses")
def courses(verified_only: bool = True, force: bool = False):
    now = time.time()
    if force and ADMIN_KEY:
        items = collect_all(); upsert_collected(items)
    elif not fetch_db(False):
        items = collect_all(); upsert_collected(items)
    return fetch_db(verified_only=verified_only)

ADMIN_HTML = """
<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>OrthoCourseFinder Admin</title>
<style>body{font-family:system-ui;margin:24px;background:#f7f7f9;color:#17171a}table{width:100%;border-collapse:collapse;background:white}th,td{padding:10px;border-bottom:1px solid #ddd;text-align:left;vertical-align:top}.pending{color:#9a6700}.verified{color:#177245}.rejected{color:#b42318}button{padding:7px 10px;margin:2px}a{color:#2457d6}.bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:14px}</style></head>
<body><h1>Course verification</h1><div class='bar'><a href='/admin?key={{KEY}}&status=pending'>Pending</a><a href='/admin?key={{KEY}}&status=verified'>Verified</a><a href='/admin?key={{KEY}}&status=rejected'>Rejected</a><form method='post' action='/api/refresh?key={{KEY}}'><button>Refresh sources</button></form></div>
<table><tr><th>Course</th><th>Date</th><th>Source</th><th>Status</th><th>Action</th></tr>{{ROWS}}</table></body></html>
"""

@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request, status: str = "pending"):
    require_admin(request)
    status = status if status in {"pending","verified","rejected"} else "pending"
    with db() as conn:
        rows = conn.execute("SELECT * FROM courses WHERE verification_status=? ORDER BY start_date,title", (status,)).fetchall()
    chunks=[]
    key = request.query_params.get("key", "")
    for r in rows:
        actions = f"""<form style='display:inline' method='post' action='/admin/set?key={key}'><input type='hidden' name='id' value='{r['id']}'><button name='status' value='verified'>Verify</button><button name='status' value='rejected'>Reject</button><button name='status' value='pending'>Pending</button></form>"""
        chunks.append(f"<tr><td><b>{r['title']}</b><br>{r['organiser']} · {r['city']}, {r['country']}<br><a href='{r['url']}'>official page</a></td><td>{r['start_date']}–{r['end_date']}</td><td>{r['source']}</td><td class='{r['verification_status']}'>{r['verification_status']}</td><td>{actions}</td></tr>")
    return ADMIN_HTML.replace("{{KEY}}", key).replace("{{ROWS}}", "".join(chunks) or "<tr><td colspan='5'>No courses in this queue.</td></tr>")

@app.post("/admin/set")
def admin_set(request: Request, id: str = Form(...), status: str = Form(...)):
    require_admin(request)
    if status not in {"pending","verified","rejected"}:
        raise HTTPException(400, "Bad status")
    with db() as conn:
        conn.execute("UPDATE courses SET verification_status=?,updated_at=? WHERE id=?", (status,int(time.time()),id)); conn.commit()
    key = request.query_params.get("key", "")
    return RedirectResponse(url=f"/admin?key={key}&status=pending", status_code=303)
