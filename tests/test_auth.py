import re
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import auth
from app.db import get_engine
from app.main import app
from app.models import User, utcnow

PW = "correct-horse-battery"


@pytest.fixture()
def client():
    with TestClient(app, base_url="https://testserver") as c:
        yield c


@pytest.fixture()
def make_user():
    """テスト用ユーザーを作り、終了時に削除する（ログインIDは t_ で始める）。"""
    created = []

    def _make(role="user", must_change=False, active=True, password=PW):
        login_id = "t_" + uuid.uuid4().hex[:10]
        with Session(get_engine()) as s:
            s.add(User(login_id=login_id, display_name="テスト太郎", role=role, is_active=active,
                       password_hash=auth.hash_password(password), must_change_password=must_change))
            s.commit()
        created.append(login_id)
        return login_id

    yield _make
    with Session(get_engine()) as s:
        s.execute(delete(User).where(User.login_id.like("t\\_%", escape="\\")))
        s.commit()


def token(client, path="/login"):
    html = client.get(path).text
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def login(client, login_id, password=PW, next_="/"):
    return client.post("/login", data={"login_id": login_id, "password": password, "next": next_,
                                        "csrf_token": token(client)}, follow_redirects=False)


# ---- パスワード ----
def test_password_hash_roundtrip():
    h = auth.hash_password(PW)
    assert h != PW and auth.verify_password(h, PW)
    assert not auth.verify_password(h, "wrong")
    assert not auth.verify_password(None, PW)  # 存在しないユーザー


def test_password_rules():
    assert auth.validate_new_password("short", "u1")
    assert auth.validate_new_password("abcdefghijkl", "abcdefghijkl")  # IDと同じ
    assert auth.validate_new_password(PW, "u1") is None


def test_safe_next_blocks_open_redirect():
    assert auth.safe_next("/admin/users") == "/admin/users"
    assert auth.safe_next("//evil.example") == "/"
    assert auth.safe_next("https://evil.example") == "/"
    assert auth.safe_next("/\\evil.example") == "/"
    assert auth.safe_next(None) == "/"


# ---- ログイン ----
def test_login_success_and_redirect_back(client, make_user):
    uid = make_user()
    r = client.get("/i/anything", follow_redirects=False)  # 未ログイン → ログイン画面へ（/i は未実装でも対象外）
    assert r.status_code in (303, 404)
    r = login(client, uid, next_="/account/password")
    assert r.status_code == 303 and r.headers["location"] == "/account/password"
    assert client.get("/").status_code == 200


def test_login_wrong_password_and_unknown_user_look_same(client, make_user):
    uid = make_user()
    a = login(client, uid, "wrong-password-123")
    b = login(client, "t_no_such_user")
    assert a.status_code == b.status_code == 400
    assert a.text == b.text


def test_login_requires_csrf(client, make_user):
    uid = make_user()
    r = client.post("/login", data={"login_id": uid, "password": PW, "csrf_token": "bad"}, follow_redirects=False)
    assert r.status_code == 400


def test_lockout_after_5_failures(client, make_user):
    uid = make_user()
    for _ in range(auth.MAX_FAILS):
        assert login(client, uid, "wrong-password-123").status_code == 400
    # 正しいパスワードでもロック中は入れない
    assert login(client, uid).status_code == 400
    with Session(get_engine()) as s:
        u = s.scalar(select(User).where(User.login_id == uid))
        assert u.locked_until > utcnow()
        u.locked_until = utcnow() - timedelta(minutes=1)  # ロック時間が過ぎた状態
        s.commit()
    assert login(client, uid).status_code == 303


def test_inactive_user_cannot_login(client, make_user):
    uid = make_user(active=False)
    assert login(client, uid).status_code == 400


def test_protected_page_redirects_to_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login?next=")


def test_logout(client, make_user):
    uid = make_user()
    login(client, uid)
    r = client.post("/logout", data={"csrf_token": token(client, "/")}, follow_redirects=False)
    assert r.status_code == 303
    assert client.get("/", follow_redirects=False).status_code == 303


# ---- 初期パスワードの変更 ----
def test_must_change_password_flow(client, make_user):
    uid = make_user(must_change=True)
    login(client, uid)
    r = client.get("/", follow_redirects=False)
    assert r.headers["location"] == "/account/password"
    new_pw = "another-long-password"
    r = client.post("/account/password", data={
        "current_password": PW, "new_password": new_pw, "confirm_password": new_pw,
        "csrf_token": token(client, "/account/password")}, follow_redirects=False)
    assert r.status_code == 303
    assert client.get("/", follow_redirects=False).status_code == 200


def test_password_change_rejects_weak_or_mismatch(client, make_user):
    uid = make_user()
    login(client, uid)
    t = token(client, "/account/password")
    for new, confirm in [("short", "short"), ("another-long-password", "different-long-password")]:
        r = client.post("/account/password", data={"current_password": PW, "new_password": new,
                                                    "confirm_password": confirm, "csrf_token": t})
        assert r.status_code == 400


# ---- 管理者 ----
def test_non_admin_cannot_open_user_admin(client, make_user):
    login(client, make_user("user"))
    r = client.get("/admin/users", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"


def test_admin_creates_user_and_issues_temp_password(client, make_user):
    login(client, make_user("admin"))
    new_id = "t_" + uuid.uuid4().hex[:8]
    r = client.post("/admin/users", data={"login_id": new_id, "display_name": "新人 花子", "role": "user",
                                           "csrf_token": token(client, "/admin/users")})
    assert r.status_code == 200 and new_id in r.text and "二度と表示されません" in r.text
    temp = re.search(r"<code>([^<]+)</code>", r.text).group(1)
    with Session(get_engine()) as s:
        u = s.scalar(select(User).where(User.login_id == new_id))
        assert u.must_change_password and u.display_name == "新人 花子"
        assert u.password_hash != temp and auth.verify_password(u.password_hash, temp)
    # 同じIDの二重登録、不正なIDは拒否
    t = token(client, "/admin/users")
    assert client.post("/admin/users", data={"login_id": new_id, "display_name": "x", "csrf_token": t}).status_code == 400
    assert client.post("/admin/users", data={"login_id": "日本語", "display_name": "x", "csrf_token": t}).status_code == 400


def test_admin_reset_and_toggle(client, make_user):
    login(client, make_user("admin"))
    target = make_user("user")
    with Session(get_engine()) as s:
        tid = s.scalar(select(User.id).where(User.login_id == target))
    t = token(client, "/admin/users")
    r = client.post(f"/admin/users/{tid}/reset", data={"csrf_token": t})
    assert r.status_code == 200 and "初期化しました" in r.text
    r = client.post(f"/admin/users/{tid}/toggle", data={"csrf_token": t}, follow_redirects=False)
    assert r.status_code == 303
    with Session(get_engine()) as s:
        u = s.get(User, tid)
        assert u.is_active is False and u.must_change_password is True


def test_admin_cannot_disable_self(client, make_user):
    me = make_user("admin")
    login(client, me)
    with Session(get_engine()) as s:
        my_id = s.scalar(select(User.id).where(User.login_id == me))
    r = client.post(f"/admin/users/{my_id}/toggle", data={"csrf_token": token(client, "/admin/users")})
    assert r.status_code == 400
