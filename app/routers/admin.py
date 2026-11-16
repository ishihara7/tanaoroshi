"""管理者向け：ユーザー管理（ID発行、パスワード初期化、有効／無効）。"""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.db import get_session
from app.models import User
from app.templating import templates

router = APIRouter(prefix="/admin")


def _render(request: Request, session: Session, admin: User, *, error=None, issued=None, status=200):
    users = session.scalars(select(User).order_by(User.id)).all()
    return templates.TemplateResponse(
        request,
        "admin_users.html",
        {"user": admin, "users": users, "error": error, "issued": issued},
        status_code=status,
    )


@router.get("/users", response_class=HTMLResponse)
def users_page(request: Request, admin: User = Depends(auth.require_admin), session: Session = Depends(get_session)):
    return _render(request, session, admin)


@router.post("/users")
def create_user(
    request: Request,
    login_id: str = Form(""),
    role: str = Form("user"),
    csrf_token: str = Form(""),
    admin: User = Depends(auth.require_admin),
    session: Session = Depends(get_session),
):
    if not auth.check_csrf(request, csrf_token):
        return _render(request, session, admin, error="画面の有効期限が切れました。もう一度お試しください。", status=400)
    login_id = login_id.strip().lower()
    if not auth.LOGIN_ID_RE.match(login_id):
        return _render(request, session, admin, error="ログインIDは、英数字・ハイフン・アンダースコアの3〜30文字にしてください。", status=400)
    if role not in ("admin", "user"):
        return _render(request, session, admin, error="権限の指定が正しくありません。", status=400)
    if session.scalar(select(User.id).where(User.login_id == login_id)):
        return _render(request, session, admin, error="そのログインIDは、すでに使われています。", status=400)

    temp = auth.generate_temp_password()
    session.add(User(login_id=login_id, role=role,
                     password_hash=auth.hash_password(temp), must_change_password=True))
    session.commit()
    # 初期パスワードは、この画面にだけ一度表示する（保存しない）
    return _render(request, session, admin, issued={"login_id": login_id, "password": temp, "action": "発行"})


@router.post("/users/{user_id}/reset")
def reset_password(
    user_id: int,
    request: Request,
    csrf_token: str = Form(""),
    admin: User = Depends(auth.require_admin),
    session: Session = Depends(get_session),
):
    target = session.get(User, user_id)
    if not auth.check_csrf(request, csrf_token) or target is None:
        return _render(request, session, admin, error="操作できませんでした。もう一度お試しください。", status=400)
    temp = auth.generate_temp_password()
    target.password_hash = auth.hash_password(temp)
    target.must_change_password = True
    target.failed_count = 0
    target.locked_until = None
    session.commit()
    return _render(request, session, admin, issued={"login_id": target.login_id, "password": temp, "action": "初期化"})


@router.post("/users/{user_id}/toggle")
def toggle_active(
    user_id: int,
    request: Request,
    csrf_token: str = Form(""),
    admin: User = Depends(auth.require_admin),
    session: Session = Depends(get_session),
):
    target = session.get(User, user_id)
    if not auth.check_csrf(request, csrf_token) or target is None:
        return _render(request, session, admin, error="操作できませんでした。もう一度お試しください。", status=400)
    if target.id == admin.id:
        return _render(request, session, admin, error="自分自身は無効にできません。", status=400)
    target.is_active = not target.is_active
    session.commit()
    return RedirectResponse("/admin/users", status_code=303)
