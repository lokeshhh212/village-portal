"""
Cookie + JWT based authentication, replacing Flask-Login.

Flask-Login kept a server-side session cookie tied to a user_loader callback.
FastAPI has no built-in equivalent, so we issue a signed JWT, store it in an
HttpOnly cookie, and verify it on every protected request via a dependency
(`get_current_admin`). This keeps the "login -> redirect -> protected pages"
flow working the same way it did in Flask.
"""
import os
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import Request, HTTPException, status, Depends
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from database import Admin, get_db

# ===== CONFIG =====
# In production, set SECRET_KEY via an environment variable - never commit a real secret.
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12  # 12 hours, similar to a typical Flask session lifetime
COOKIE_NAME = "access_token"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_admin(request: Request, db: Session = Depends(get_db)) -> Admin:
    """
    Dependency for protected routes. Reads the JWT from the cookie,
    validates it, and loads the matching Admin row - the FastAPI
    equivalent of Flask-Login's @login_required + user_loader.
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/admin/login"})

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise JWTError()
    except JWTError:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/admin/login"})

    admin = db.query(Admin).filter(Admin.username == username).first()
    if admin is None:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/admin/login"})

    return admin


def get_current_admin_optional(request: Request, db: Session = Depends(get_db)) -> Optional[Admin]:
    """Like get_current_admin, but returns None instead of redirecting. Useful for pages
    that render differently for logged-in vs anonymous users without forcing a login."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
    except JWTError:
        return None
    if not username:
        return None
    return db.query(Admin).filter(Admin.username == username).first()
