from __future__ import annotations

import base64
import hashlib
import hmac
import os
from functools import wraps

from flask import redirect, request, session, url_for

from app.config import load_config


PUBLIC_ENDPOINTS = {
    "login",
    "login_post",
    "health",
    "static",
    "recovery",
    "download_diagnostics",
    "subscription_feed",
    "sg_subscription_v1",
}


def is_authenticated() -> bool:
    return session.get("authenticated") is True


def _verify_pbkdf2_sha256(password: str, encoded: str) -> bool:
    try:
        scheme, rounds_text, salt_text, digest_text = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        rounds = int(rounds_text)
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
    except (TypeError, ValueError, UnicodeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return hmac.compare_digest(actual, expected)


# SG-Gateway 021.7 - Security password change fix 1
def _password_state_path():
    return load_config().data_dir / "security" / "admin-password.hash"

def _encode_password(password: str) -> str:
    rounds = 310000
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return "$".join((
        "pbkdf2_sha256",
        str(rounds),
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    ))

def set_password(password: str):
    path = _password_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(_encode_password(password) + "\n", encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
    return path

def password_is_default() -> bool:
    path = _password_state_path()
    try:
        if path.is_file() and path.read_text(encoding="utf-8").strip():
            return False
    except OSError:
        pass
    config = load_config()
    return not config.admin_password_hash and config.admin_password == "admin"

def verify_password(password: str) -> bool:
    path = _password_state_path()
    try:
        stored = path.read_text(encoding="utf-8").strip() if path.is_file() else ""
    except OSError:
        stored = ""
    if stored:
        return _verify_pbkdf2_sha256(password, stored)
    config = load_config()
    if config.admin_password_hash:
        return _verify_pbkdf2_sha256(password, config.admin_password_hash)
    expected = config.admin_password
    return hmac.compare_digest(password.encode("utf-8"), expected.encode("utf-8"))


def login_user() -> None:
    session["authenticated"] = True


def logout_user() -> None:
    session.clear()


def require_auth(handler):
    @wraps(handler)
    def wrapper(*args, **kwargs):
        if is_authenticated():
            return handler(*args, **kwargs)
        return redirect(url_for("login", next=request.path))

    return wrapper


def should_skip_auth(endpoint: str | None) -> bool:
    if endpoint is None:
        return False
    return endpoint in PUBLIC_ENDPOINTS or endpoint.startswith("static")
