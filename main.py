"""
Village Information Portal - FastAPI version.

This replaces the original Flask app. Key mapping from Flask -> FastAPI:
  - @app.route(...)                  -> @app.get/@app.post/@app.put/@app.delete(...)
  - render_template(...)             -> Jinja2Templates().TemplateResponse(...)
  - request.json                     -> Pydantic model as a function parameter
  - flask_login (@login_required)    -> Depends(get_current_admin) (see auth.py)
  - flash messages (server session)  -> query string flag read in the login page
  - SQLAlchemy via flask_sqlalchemy   -> plain SQLAlchemy session via Depends(get_db)

Run locally with:  uvicorn main:app --reload
"""
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv()  # reads .env into os.environ before anything else initializes

from fastapi import FastAPI, Depends, Request, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import init_db, get_db, Admin, Service, Event, Announcement, Complaint
from auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_admin,
    COOKIE_NAME,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from schemas import (
    ServiceIn, ServiceOut,
    EventIn, EventOut,
    AnnouncementIn, AnnouncementOut,
    ComplaintIn, ComplaintOut, PublicComplaintIn,
    SuccessOut,
)

app = FastAPI(title="Village Information Portal")

# Static files (css/js) - same role as Flask's /static
app.mount("/static", StaticFiles(directory="static"), name="static")

# Jinja2 templates - same templates folder convention as Flask
templates = Jinja2Templates(directory="templates")


@app.on_event("startup")
def on_startup():
    """Creates tables and a default admin user, mirroring the original create_admin()."""
    init_db()
    db = next(get_db())
    try:
        admin = db.query(Admin).filter(Admin.username == "admin").first()
        if not admin:
            admin = Admin(username="admin", password_hash=hash_password("admin123"))
            db.add(admin)
            db.commit()
            print("=" * 40)
            print("Admin user created!")
            print("Username: admin")
            print("Password: admin123")
            print("=" * 40)
    finally:
        db.close()


# ===== PUBLIC PAGE =====

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    services = db.query(Service).all()
    events = db.query(Event).all()
    announcements = db.query(Announcement).all()
    complaints = db.query(Complaint).all()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "services": services,
            "events": events,
            "announcements": announcements,
            "complaints": complaints,
        },
    )


# ===== ADMIN AUTH =====

@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request, error: str = None):
    return templates.TemplateResponse(
        "admin_login.html",
        {"request": request, "error": error},
    )


@app.post("/admin/login")
async def admin_login_submit(
    request: Request,
    db: Session = Depends(get_db),
):
    return await _process_login(request, db)


async def _process_login(request: Request, db: Session):
    form_data = await request.form()
    username = form_data.get("username")
    password = form_data.get("password")

    admin = db.query(Admin).filter(Admin.username == username).first()

    if admin and verify_password(password, admin.password_hash):
        token = create_access_token(
            data={"sub": admin.username},
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        )
        response = RedirectResponse(url="/admin/dashboard", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            httponly=True,
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            samesite="lax",
            # secure=True,  # uncomment once served over HTTPS in production
        )
        return response
    else:
        return RedirectResponse(
            url="/admin/login?error=Invalid+credentials",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@app.get("/admin/logout")
def admin_logout():
    response = RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(COOKIE_NAME)
    return response


# ===== ADMIN DASHBOARD =====

@app.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
):
    services = db.query(Service).all()
    events = db.query(Event).all()
    announcements = db.query(Announcement).all()
    complaints = db.query(Complaint).all()

    stats = {
        "services": len(services),
        "events": len(events),
        "announcements": len(announcements),
        "complaints": len(complaints),
        "pending_complaints": db.query(Complaint).filter(Complaint.status == "Pending").count(),
    }

    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "services": services,
            "events": events,
            "announcements": announcements,
            "complaints": complaints,
            "stats": stats,
            "current_user": current_admin,
        },
    )


# ===== PUBLIC COMPLAINT SUBMISSION (no auth) =====

@app.post("/api/public/complaints", response_model=SuccessOut)
def public_add_complaint(payload: PublicComplaintIn, db: Session = Depends(get_db)):
    try:
        complaint = Complaint(
            title=payload.title,
            description=payload.description,
            location=payload.location or "",
            status="Pending",
            date=datetime.utcnow().strftime("%Y-%m-%d"),
        )
        db.add(complaint)
        db.commit()
        db.refresh(complaint)
        return SuccessOut(success=True, id=complaint.id, message="Complaint submitted successfully!")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


# ===== SERVICES API (admin only) =====

@app.post("/api/services", response_model=SuccessOut)
def add_service(payload: ServiceIn, db: Session = Depends(get_db), _: Admin = Depends(get_current_admin)):
    service = Service(**payload.dict())
    db.add(service)
    db.commit()
    db.refresh(service)
    return SuccessOut(success=True, id=service.id)


@app.get("/api/services/{service_id}", response_model=ServiceOut)
def get_service(service_id: int, db: Session = Depends(get_db), _: Admin = Depends(get_current_admin)):
    service = db.query(Service).get(service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return service


@app.put("/api/services/{service_id}", response_model=SuccessOut)
def update_service(service_id: int, payload: ServiceIn, db: Session = Depends(get_db), _: Admin = Depends(get_current_admin)):
    service = db.query(Service).get(service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    service.title = payload.title
    service.description = payload.description
    service.contact = payload.contact or ""
    service.is_emergency = payload.is_emergency or False
    service.updated_at = datetime.utcnow()
    db.commit()
    return SuccessOut(success=True)


@app.delete("/api/services/{service_id}", response_model=SuccessOut)
def delete_service(service_id: int, db: Session = Depends(get_db), _: Admin = Depends(get_current_admin)):
    service = db.query(Service).get(service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    db.delete(service)
    db.commit()
    return SuccessOut(success=True)


# ===== EVENTS API (admin only) =====

@app.post("/api/events", response_model=SuccessOut)
def add_event(payload: EventIn, db: Session = Depends(get_db), _: Admin = Depends(get_current_admin)):
    event = Event(**payload.dict())
    db.add(event)
    db.commit()
    db.refresh(event)
    return SuccessOut(success=True, id=event.id)


@app.get("/api/events/{event_id}", response_model=EventOut)
def get_event(event_id: int, db: Session = Depends(get_db), _: Admin = Depends(get_current_admin)):
    event = db.query(Event).get(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@app.put("/api/events/{event_id}", response_model=SuccessOut)
def update_event(event_id: int, payload: EventIn, db: Session = Depends(get_db), _: Admin = Depends(get_current_admin)):
    event = db.query(Event).get(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    event.title = payload.title
    event.description = payload.description
    event.date = payload.date
    event.location = payload.location or ""
    event.updated_at = datetime.utcnow()
    db.commit()
    return SuccessOut(success=True)


@app.delete("/api/events/{event_id}", response_model=SuccessOut)
def delete_event(event_id: int, db: Session = Depends(get_db), _: Admin = Depends(get_current_admin)):
    event = db.query(Event).get(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    db.delete(event)
    db.commit()
    return SuccessOut(success=True)


# ===== ANNOUNCEMENTS API (admin only) =====

@app.post("/api/announcements", response_model=SuccessOut)
def add_announcement(payload: AnnouncementIn, db: Session = Depends(get_db), _: Admin = Depends(get_current_admin)):
    announcement = Announcement(**payload.dict())
    db.add(announcement)
    db.commit()
    db.refresh(announcement)
    return SuccessOut(success=True, id=announcement.id)


@app.get("/api/announcements/{announcement_id}", response_model=AnnouncementOut)
def get_announcement(announcement_id: int, db: Session = Depends(get_db), _: Admin = Depends(get_current_admin)):
    announcement = db.query(Announcement).get(announcement_id)
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return announcement


@app.put("/api/announcements/{announcement_id}", response_model=SuccessOut)
def update_announcement(announcement_id: int, payload: AnnouncementIn, db: Session = Depends(get_db), _: Admin = Depends(get_current_admin)):
    announcement = db.query(Announcement).get(announcement_id)
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")
    announcement.title = payload.title
    announcement.content = payload.content
    announcement.date = payload.date
    announcement.is_important = payload.is_important or False
    announcement.updated_at = datetime.utcnow()
    db.commit()
    return SuccessOut(success=True)


@app.delete("/api/announcements/{announcement_id}", response_model=SuccessOut)
def delete_announcement(announcement_id: int, db: Session = Depends(get_db), _: Admin = Depends(get_current_admin)):
    announcement = db.query(Announcement).get(announcement_id)
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")
    db.delete(announcement)
    db.commit()
    return SuccessOut(success=True)


# ===== COMPLAINTS API (admin only) =====

@app.post("/api/complaints", response_model=SuccessOut)
def add_complaint(payload: ComplaintIn, db: Session = Depends(get_db), _: Admin = Depends(get_current_admin)):
    complaint = Complaint(
        title=payload.title,
        description=payload.description,
        location=payload.location or "",
        status=payload.status or "Pending",
        date=datetime.utcnow().strftime("%Y-%m-%d"),
    )
    db.add(complaint)
    db.commit()
    db.refresh(complaint)
    return SuccessOut(success=True, id=complaint.id)


@app.get("/api/complaints/{complaint_id}", response_model=ComplaintOut)
def get_complaint(complaint_id: int, db: Session = Depends(get_db), _: Admin = Depends(get_current_admin)):
    complaint = db.query(Complaint).get(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return complaint


@app.put("/api/complaints/{complaint_id}", response_model=SuccessOut)
def update_complaint(complaint_id: int, payload: ComplaintIn, db: Session = Depends(get_db), _: Admin = Depends(get_current_admin)):
    complaint = db.query(Complaint).get(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    complaint.title = payload.title
    complaint.description = payload.description
    complaint.location = payload.location or ""
    complaint.status = payload.status or complaint.status
    complaint.updated_at = datetime.utcnow()
    db.commit()
    return SuccessOut(success=True)


@app.delete("/api/complaints/{complaint_id}", response_model=SuccessOut)
def delete_complaint(complaint_id: int, db: Session = Depends(get_db), _: Admin = Depends(get_current_admin)):
    complaint = db.query(Complaint).get(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    db.delete(complaint)
    db.commit()
    return SuccessOut(success=True)


# ===== EXCEPTION HANDLER: redirect to login on auth failure =====
# get_current_admin raises an HTTPException with a Location header for page routes;
# this turns that into an actual redirect response instead of a raw JSON error,
# matching Flask-Login's default browser-friendly behavior.

@app.exception_handler(HTTPException)
async def auth_redirect_handler(request: Request, exc: HTTPException):
    if exc.status_code == status.HTTP_303_SEE_OTHER and "Location" in (exc.headers or {}):
        return RedirectResponse(url=exc.headers["Location"], status_code=status.HTTP_303_SEE_OTHER)
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


if __name__ == "__main__":
    import uvicorn
    print()
    print("Starting Village Information Portal (FastAPI)...")
    print("Visit: http://localhost:8000")
    print("Admin Login: http://localhost:8000/admin/login")
    print("API docs: http://localhost:8000/docs")
    print("=" * 50)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
