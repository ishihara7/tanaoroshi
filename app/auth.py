"""認証：パスワード、セッション、CSRF、ログイン試行制限。"""
import re
import secrets
from urllib.parse import quote

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User

MAX_FAILS = 5  # 連続失敗の上限
LOCK_MINUTES = 15  # ロック時間
MIN_PASSWORD_LEN = 12
LOGIN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{3,30}$")

_hasher = PasswordHasher()
# 存在しないIDでも検証にかかる時間を揃えるためのダミー
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


class RedirectRequired(Exception):
    """処理を中断して別のURLへ移動させる。"""

    def __init__(self, url: str):
        self.url = url


# ---- パスワード ----
def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def generate_temp_password() -> str:
    """初期パスワード（16文字程度）。管理者に一度だけ表示する。"""
    return secrets.token_urlsafe(12)


def validate_new_password(password: str, login_id: str) -> str | None:
    """問題があればメッセージ、なければ None。"""
    if len(password) < MIN_PASSWORD_LEN:
        return f"パスワードは{MIN_PASSWORD_LEN}文字以上にしてください。"
    if password.lower() == login_id.lower():
        return "パスワードにログインIDと同じ文字列は使えません。"
    return None


# ---- CSRF（セッションに保存したトークンをフォームで送り返す）----
def get_csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


def check_csrf(request: Request, token: str | None) -> bool:
    expected = request.session.get("csrf")
    return bool(expected and token) and secrets.compare_digest(expected, token or "")


# ---- ログイン後の戻り先（オープンリダイレクト対策）----
def safe_next(url: str | None) -> str:
    if url and url.startswith("/") and not url.startswith("//") and "\\" not in url:
        return url
    return "/"


# ---- 依存関数 ----
def current_user(request: Request, session: Session = Depends(get_session)) -> User:
    """ログイン済みのユーザーを返す。未ログインならログイン画面へ。"""
    uid = request.session.get("uid")
    user = session.get(User, uid) if uid else None
    if user is None or not user.is_active:
        request.session.clear()
        target = request.url.path + (("?" + request.url.query) if request.url.query else "")
        raise RedirectRequired("/login?next=" + quote(target, safe=""))
    if user.must_change_password and request.url.path not in ("/account/password", "/logout"):
        raise RedirectRequired("/account/password")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise RedirectRequired("/")
    return user


# ---- アプリ（JSON API）向け：リダイレクトではなく、401・403 を返す ----
def api_user(request: Request, session: Session = Depends(get_session)) -> User:
    """アプリ（JSON API）のユーザー。端末トークン（Authorization: Bearer）か、ログインのセッションで確かめる。"""
    from app.services import devices  # 循環参照を避けるため、ここで読み込む

    header = request.headers.get("authorization", "")
    if header[:7].lower() == "bearer ":
        user = devices.user_for_token(session, header[7:].strip())
        if user is None:
            raise HTTPException(401, "この端末の登録が無効です。設定し直してください。")
        request.state.bearer = True
    else:
        uid = request.session.get("uid")
        user = session.get(User, uid) if uid else None
        if user is None or not user.is_active:
            request.session.clear()
            raise HTTPException(401, "ログインしてください。")
    if user.must_change_password:
        raise HTTPException(403, "先にパスワードを変更してください。")
    return user


def api_csrf(request: Request) -> None:
    """更新系のAPIで、X-CSRF-Token ヘッダーを確かめる。端末トークンの通信は、ブラウザが勝手に付けるものではないので、不要。"""
    if getattr(request.state, "bearer", False):
        return
    if not check_csrf(request, request.headers.get("x-csrf-token")):
        raise HTTPException(403, "画面の有効期限が切れました。取得し直してください。")
