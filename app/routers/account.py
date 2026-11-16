"""ログイン、ログアウト、トップ、パスワード変更。"""
from datetime import timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.db import get_session
from app.models import User, utcnow
from app.templating import templates

router = APIRouter()

LOGIN_ERROR = "IDまたはパスワードが違うか、ログインできない状態です。しばらくしてからもう一度お試しください。"


@router.get("/", response_class=HTMLResponse)
def home(request: Request, user: User = Depends(auth.current_user)):
    return templates.TemplateResponse(request, "home.html", {"user": user})


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/"):
    return templates.TemplateResponse(request, "login.html", {"next": auth.safe_next(next), "error": None})


@router.post("/login")
def login(
    request: Request,
    login_id: str = Form(""),
    password: str = Form(""),
    next: str = Form("/"),
    csrf_token: str = Form(""),
    session: Session = Depends(get_session),
):
    def fail(status: int = 400):
        return templates.TemplateResponse(
            request, "login.html", {"next": auth.safe_next(next), "error": LOGIN_ERROR}, status_code=status
        )

    if not auth.check_csrf(request, csrf_token):
        return fail()

    user = session.scalar(select(User).where(User.login_id == login_id.strip().lower()))
    now = utcnow()
    locked = bool(user and user.locked_until and user.locked_until > now)
    ok = auth.verify_password(user.password_hash if user else None, password)

    if user is None or locked or not user.is_active or not ok:
        # 失敗は常に同じメッセージ（IDの有無・ロックの有無を知らせない）
        if user is not None and not locked and user.is_active:
            user.failed_count += 1
            if user.failed_count >= auth.MAX_FAILS:
                user.locked_until = now + timedelta(minutes=auth.LOCK_MINUTES)
                user.failed_count = 0
            session.commit()
        return fail()

    user.failed_count = 0
    user.locked_until = None
    session.commit()
    request.session.clear()  # セッション固定化の対策：ログイン時に作り直す
    request.session["uid"] = user.id
    return RedirectResponse(auth.safe_next(next), status_code=303)


@router.post("/logout")
def logout(request: Request, csrf_token: str = Form("")):
    if auth.check_csrf(request, csrf_token):
        request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/account/password", response_class=HTMLResponse)
def password_page(request: Request, user: User = Depends(auth.current_user)):
    return templates.TemplateResponse(request, "password.html", {"user": user, "error": None})


@router.post("/account/password")
def password_change(
    request: Request,
    current_password: str = Form(""),
    new_password: str = Form(""),
    confirm_password: str = Form(""),
    csrf_token: str = Form(""),
    user: User = Depends(auth.current_user),
    session: Session = Depends(get_session),
):
    def fail(msg: str):
        return templates.TemplateResponse(request, "password.html", {"user": user, "error": msg}, status_code=400)

    if not auth.check_csrf(request, csrf_token):
        return fail("画面の有効期限が切れました。もう一度お試しください。")
    if not auth.verify_password(user.password_hash, current_password):
        return fail("現在のパスワードが違います。")
    if new_password != confirm_password:
        return fail("新しいパスワードが一致しません。")
    if new_password == current_password:
        return fail("現在と同じパスワードは使えません。")
    problem = auth.validate_new_password(new_password, user.login_id)
    if problem:
        return fail(problem)

    user.password_hash = auth.hash_password(new_password)
    user.must_change_password = False
    session.commit()
    return RedirectResponse("/", status_code=303)
