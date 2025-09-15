from fastapi import FastAPI, Request, Depends, Form, HTTPException, Header
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from typing import Optional
import sqlite3
import pathlib
import datetime
import os
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv


BASE_DIR = pathlib.Path(__file__).parent
DB_PATH = BASE_DIR / "app.db"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id INTEGER NOT NULL,
            author TEXT DEFAULT 'Anonymous',
            content TEXT NOT NULL,
            rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
            created_at TEXT NOT NULL,
            FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE CASCADE
        )
        """
    )
    # Add rating column if it doesn't exist (for existing databases)
    try:
        cur.execute("ALTER TABLE feedback ADD COLUMN rating INTEGER DEFAULT 3")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists
    conn.commit()
    conn.close()


app = FastAPI(title="Pod Kapotom - Real Feedback")


# Static and templates
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Sessions for simple admin auth
load_dotenv()
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret-change-me")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)


class ServiceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: Optional[str] = ""


class ServiceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=200)
    description: Optional[str] = None


def admin_auth(x_admin_token: Optional[str] = Header(default=None)):
    # Simple header token auth for demo; replace with proper auth in production
    expected = "secret-admin-token"
    if x_admin_token != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


def is_admin(request: Request) -> bool:
    return bool(request.session.get("is_admin") is True)


def fetch_all_services():
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT id, name, description FROM services ORDER BY name ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def fetch_services_with_ratings():
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT s.id, s.name, s.description, 
               COALESCE(AVG(f.rating), 0) as avg_rating,
               COUNT(f.id) as review_count
        FROM services s 
        LEFT JOIN feedback f ON s.id = f.service_id 
        GROUP BY s.id, s.name, s.description
        ORDER BY avg_rating DESC, review_count DESC
        """
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def fetch_top_services(limit=6):
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT s.id, s.name, s.description, 
               COALESCE(AVG(f.rating), 0) as avg_rating,
               COUNT(f.id) as review_count
        FROM services s 
        LEFT JOIN feedback f ON s.id = f.service_id 
        GROUP BY s.id, s.name, s.description
        HAVING review_count > 0
        ORDER BY avg_rating DESC, review_count DESC
        LIMIT ?
        """,
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def fetch_service_with_feedback(service_id: int):
    conn = get_db_connection()
    svc = conn.execute(
        "SELECT id, name, description FROM services WHERE id = ?",
        (service_id,),
    ).fetchone()
    if not svc:
        conn.close()
        return None, []
    feedback = conn.execute(
        (
            "SELECT id, author, content, rating, created_at "
            "FROM feedback WHERE service_id = ? "
            "ORDER BY id DESC"
        ),
        (service_id,),
    ).fetchall()
    conn.close()
    return dict(svc), [dict(fb) for fb in feedback]


@app.on_event("startup")
def on_startup():
    # Ensure directories exist
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    (STATIC_DIR / "css").mkdir(parents=True, exist_ok=True)
    (STATIC_DIR / "js").mkdir(parents=True, exist_ok=True)
    init_db()


# Pages
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    services = fetch_all_services()
    top_services = fetch_top_services(6)
    return templates.TemplateResponse(
        "home.html",
        {"request": request, "services": services, "top_services": top_services},
    )


@app.get("/services", response_class=HTMLResponse)
def services_page(request: Request, search: Optional[str] = None, min_rating: Optional[str] = None):
    # Normalize rating: treat empty string as None
    parsed_min_rating: Optional[float] = None
    if isinstance(min_rating, str) and min_rating.strip() != "":
        try:
            parsed_min_rating = float(min_rating)
        except ValueError:
            parsed_min_rating = None
    
    if search or parsed_min_rating is not None:
        # Filtered search
        conn = get_db_connection()
        query = """
        SELECT s.id, s.name, s.description, 
               COALESCE(AVG(f.rating), 0) as avg_rating,
               COUNT(f.id) as review_count
        FROM services s 
        LEFT JOIN feedback f ON s.id = f.service_id 
        WHERE 1=1
        """
        params = []
        if search:
            query += " AND s.name LIKE ?"
            params.append(f"%{search}%")
        if parsed_min_rating is not None:
            query += " GROUP BY s.id, s.name, s.description HAVING avg_rating >= ?"
            params.append(parsed_min_rating)
        else:
            query += " GROUP BY s.id, s.name, s.description"
        query += " ORDER BY avg_rating DESC, review_count DESC"
        
        rows = conn.execute(query, params).fetchall()
        conn.close()
        services = [dict(r) for r in rows]
    else:
        services = fetch_services_with_ratings()
    
    return templates.TemplateResponse(
        "services.html",
        {"request": request, "services": services, "search": search, "min_rating": parsed_min_rating},
    )


@app.get("/services/{service_id}", response_class=HTMLResponse)
def service_detail(service_id: int, request: Request):
    service, feedback = fetch_service_with_feedback(service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    services = fetch_all_services()
    return templates.TemplateResponse(
        "service_detail.html",
        {
            "request": request,
            "service": service,
            "feedback": feedback,
            "services": services,
        },
    )


@app.get("/about", response_class=HTMLResponse)
def about(request: Request):
    services = fetch_all_services()
    return templates.TemplateResponse(
        "about.html",
        {"request": request, "services": services},
    )


# Feedback submission (from floating modal form)
@app.post("/feedback")
def submit_feedback(
    service_id: int = Form(...),
    content: str = Form(...),
    author: Optional[str] = Form(default="Anonymous"),
    rating: int = Form(...),
):
    content = (content or "").strip()
    author = (author or "Anonymous").strip() or "Anonymous"
    if not content:
        raise HTTPException(status_code=400, detail="Content is required")
    if not (1 <= rating <= 5):
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")
    # Ensure service exists
    conn = get_db_connection()
    svc = conn.execute(
        "SELECT id FROM services WHERE id = ?",
        (service_id,),
    ).fetchone()
    if not svc:
        conn.close()
        raise HTTPException(status_code=404, detail="Service not found")
    now = datetime.datetime.utcnow().isoformat()
    conn.execute(
        (
            "INSERT INTO feedback("
            "service_id, author, content, rating, created_at"
            ") VALUES (?, ?, ?, ?, ?)"
        ),
        (service_id, author, content, rating, now),
    )
    conn.commit()
    conn.close()
    # Redirect back to the service detail page
    return RedirectResponse(url=f"/services/{service_id}", status_code=303)


# Admin CRUD for services (simple header token auth)
@app.post("/admin/services", dependencies=[Depends(admin_auth)])
def admin_create_service(payload: ServiceCreate):
    now = datetime.datetime.utcnow().isoformat()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        (
            "INSERT INTO services("
            "name, description, created_at, updated_at"
            ") VALUES (?, ?, ?, ?)"
        ),
        (payload.name.strip(), (payload.description or "").strip(), now, now),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {
        "id": new_id,
        "name": payload.name,
        "description": payload.description or "",
    }


@app.put("/admin/services/{service_id}", dependencies=[Depends(admin_auth)])
def admin_update_service(service_id: int, payload: ServiceUpdate):
    conn = get_db_connection()
    existing = conn.execute(
        "SELECT id, name, description FROM services WHERE id = ?",
        (service_id,),
    ).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Service not found")
    name = (
        payload.name.strip()
        if isinstance(payload.name, str)
        else existing["name"]
    )
    description = (
        payload.description.strip()
        if isinstance(payload.description, str)
        else existing["description"]
    )
    now = datetime.datetime.utcnow().isoformat()
    conn.execute(
        (
            "UPDATE services SET name = ?, description = ?, "
            "updated_at = ? WHERE id = ?"
        ),
        (name, description, now, service_id),
    )
    conn.commit()
    conn.close()
    return {
        "id": service_id,
        "name": name,
        "description": description,
    }


@app.delete("/admin/services/{service_id}", dependencies=[Depends(admin_auth)])
def admin_delete_service(service_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM services WHERE id = ?",
        (service_id,),
    )
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Service not found")
    return {"status": "deleted", "id": service_id}


# Admin web UI
@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    return templates.TemplateResponse(
        "admin_login.html",
        {"request": request, "services": fetch_all_services()},
    )


@app.post("/admin/login")
def admin_login(request: Request, password: str = Form(...)):
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Wrong password")
    request.session["is_admin"] = True
    return RedirectResponse(url="/admin/services", status_code=303)


@app.post("/admin/logout")
def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


def require_admin(request: Request):
    if not is_admin(request):
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/admin/services", response_class=HTMLResponse)
def admin_services_page(request: Request):
    if not is_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    return templates.TemplateResponse(
        "admin_services.html",
        {
            "request": request,
            "services": fetch_all_services(),
        },
    )


@app.post("/admin/services/new")
def admin_create_service_form(
    request: Request,
    name: str = Form(...),
    description: str = Form("")
):
    require_admin(request)
    payload = ServiceCreate(name=name, description=description)
    now = datetime.datetime.utcnow().isoformat()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        (
            "INSERT INTO services("
            "name, description, created_at, updated_at"
            ") VALUES (?, ?, ?, ?)"
        ),
        (payload.name.strip(), (payload.description or "").strip(), now, now),
    )
    conn.commit()
    conn.close()
    return RedirectResponse(url="/admin/services", status_code=303)


@app.post("/admin/services/{service_id}/edit")
def admin_update_service_form(
    service_id: int,
    request: Request,
    name: str = Form(...),
    description: str = Form("")
):
    require_admin(request)
    now = datetime.datetime.utcnow().isoformat()
    conn = get_db_connection()
    conn.execute(
        (
            "UPDATE services SET name = ?, description = ?, "
            "updated_at = ? WHERE id = ?"
        ),
        (name.strip(), (description or "").strip(), now, service_id),
    )
    conn.commit()
    conn.close()
    return RedirectResponse(url="/admin/services", status_code=303)


@app.post("/admin/services/{service_id}/delete")
def admin_delete_service_form(service_id: int, request: Request):
    require_admin(request)
    conn = get_db_connection()
    conn.execute("DELETE FROM services WHERE id = ?", (service_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/admin/services", status_code=303)


@app.get("/admin/feedback", response_class=HTMLResponse)
def admin_feedback_page(request: Request):
    if not is_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    conn = get_db_connection()
    rows = conn.execute(
        (
            "SELECT f.id, f.author, f.content, f.rating, f.created_at, f.service_id, s.name AS service_name "
            "FROM feedback f JOIN services s ON s.id = f.service_id "
            "ORDER BY f.id DESC"
        )
    ).fetchall()
    conn.close()
    feedback = [dict(r) for r in rows]
    return templates.TemplateResponse(
        "admin_feedback.html",
        {"request": request, "services": fetch_all_services(), "feedback": feedback},
    )


@app.post("/admin/feedback/{feedback_id}/delete")
def admin_delete_feedback(feedback_id: int, request: Request):
    require_admin(request)
    conn = get_db_connection()
    conn.execute("DELETE FROM feedback WHERE id = ?", (feedback_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/admin/feedback", status_code=303)
