"""棚卸アプリの端末の登録：設定コード（QR）→ 端末トークン。トークンでの通信、無効化。"""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import Base, get_engine
from app.main import app
from app.models import ArItem, DeviceToken, EnrollCode, User, utcnow
from app.services import devices
from tests.test_auth import client, login, make_user, token  # noqa: F401（フィクスチャを再利用）


def _user_id(login_id):
    with Session(get_engine()) as s:
        return s.scalar(select(User.id).where(User.login_id == login_id))


@pytest.fixture()
def clean_devices():
    """テストで作った端末・設定コード（テスト用ユーザーのもの）を、前後で消す。"""
    Base.metadata.create_all(get_engine())

    def wipe():
        with Session(get_engine()) as s:
            ids = s.scalars(select(User.id).where(User.login_id.like("t\\_%", escape="\\"))).all()
            if ids:
                s.execute(delete(DeviceToken).where(DeviceToken.user_id.in_(ids)))
                s.execute(delete(EnrollCode).where(EnrollCode.user_id.in_(ids)))
            s.execute(delete(DeviceToken).where(~DeviceToken.user_id.in_(select(User.id))))  # 消えたユーザーの分
            s.execute(delete(EnrollCode).where(~EnrollCode.user_id.in_(select(User.id))))
            s.execute(delete(ArItem).where(ArItem.token.like("Dev%")))
            s.commit()
    wipe()
    yield
    wipe()


def issue(session, login_id, label=""):
    return devices.issue_code(session, _user_id(login_id), label)


@pytest.fixture()
def fresh():
    """Cookie を持たない、別のクライアント（アプリの通信と同じ）。"""
    with TestClient(app, base_url="https://testserver") as c:
        yield c


def enroll(c, code):
    return c.post("/api/ar/enroll", json={"code": code})


def test_code_becomes_token_once(make_user, clean_devices, fresh):  # noqa: F811
    uid = make_user()
    with Session(get_engine()) as s:
        code = issue(s, uid, "1階のタブレット")
    r = enroll(fresh, code)
    assert r.status_code == 200 and r.json()["login_id"] == uid and len(r.json()["token"]) >= 40
    assert enroll(fresh, code).status_code == 400  # 1回だけ
    with Session(get_engine()) as s:
        assert s.scalar(select(DeviceToken.label).where(DeviceToken.user_id == _user_id(uid))) == "1階のタブレット"


def test_expired_unknown_and_malformed_codes_are_rejected(make_user, clean_devices, fresh):  # noqa: F811
    uid = make_user()
    with Session(get_engine()) as s:
        code = issue(s, uid)
        s.execute(EnrollCode.__table__.update().values(expires_at=utcnow() - timedelta(minutes=1)))
        s.commit()
    assert enroll(fresh, code).status_code == 400  # 期限切れ
    assert enroll(fresh, "A" * 32).status_code == 400  # 存在しない
    assert enroll(fresh, "short").status_code == 422  # 形が違う
    assert enroll(fresh, "../" + "a" * 20).status_code == 422


def test_code_of_inactive_user_is_rejected(make_user, clean_devices, fresh):  # noqa: F811
    uid = make_user(active=False)
    with Session(get_engine()) as s:
        code = issue(s, uid)
    assert enroll(fresh, code).status_code == 400


def test_only_hashes_are_stored(make_user, clean_devices, fresh):  # noqa: F811
    uid = make_user()
    with Session(get_engine()) as s:
        code = issue(s, uid)
    tok = enroll(fresh, code).json()["token"]
    with Session(get_engine()) as s:
        assert all(code not in h and tok not in h for h in s.scalars(select(EnrollCode.code_hash)).all())
        assert all(tok not in h for h in s.scalars(select(DeviceToken.token_hash)).all())


def bearer(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_token_authenticates_api_without_cookie_or_csrf(make_user, clean_devices, fresh):  # noqa: F811
    uid = make_user()
    with Session(get_engine()) as s:
        code = issue(s, uid)
    tok = enroll(fresh, code).json()["token"]
    with TestClient(app, base_url="https://testserver") as other:  # Cookie のない、新しい接続
        assert other.get("/api/ar/plan", headers=bearer(tok)).status_code == 200
        # 更新も、CSRFヘッダーなしで通る（トークンは、ブラウザが勝手に付けるものではないため）
        r = other.put("/api/ar/items/DevTagA", json={"x": 1, "y": 2}, headers=bearer(tok))
        assert r.status_code == 200
        # 間違ったトークンは、401
        assert other.get("/api/ar/plan", headers=bearer(tok + "x")).status_code == 401
        assert other.get("/api/ar/plan", headers={"Authorization": "Bearer "}).status_code == 401
    with Session(get_engine()) as s:
        assert s.scalar(select(DeviceToken.last_used_at).where(DeviceToken.user_id == _user_id(uid))) is not None


def test_session_login_still_needs_csrf(make_user, clean_devices, client):  # noqa: F811
    login(client, make_user())
    assert client.put("/api/ar/items/DevTagB", json={"x": 1, "y": 2}).status_code == 403


def test_token_of_user_who_must_change_password_is_refused(make_user, clean_devices, fresh):  # noqa: F811
    uid = make_user(must_change=True)
    with Session(get_engine()) as s:
        code = issue(s, uid)
    tok = enroll(fresh, code).json()["token"]
    assert fresh.get("/api/ar/plan", headers=bearer(tok)).status_code == 403


def test_inactive_user_token_stops_working(make_user, clean_devices, fresh):  # noqa: F811
    uid = make_user()
    with Session(get_engine()) as s:
        code = issue(s, uid)
    tok = enroll(fresh, code).json()["token"]
    with Session(get_engine()) as s:
        s.execute(User.__table__.update().where(User.login_id == uid).values(is_active=False))
        s.commit()
    assert fresh.get("/api/ar/plan", headers=bearer(tok)).status_code == 401


# ---- 管理画面 ----
def test_admin_issues_qr_and_revokes_device(make_user, clean_devices, client, fresh):  # noqa: F811
    target = make_user()
    login(client, make_user("admin"))
    page = client.get("/admin/devices")
    assert page.status_code == 200 and target in page.text
    uid = _user_id(target)
    r = client.post("/admin/devices/enroll", data={"user_id": str(uid), "label": "テスト端末",
                                                   "csrf_token": token(client, "/admin/devices")})
    assert r.status_code == 200 and "data:image/svg+xml;base64," in r.text
    assert "no-store" in r.headers["cache-control"]
    with Session(get_engine()) as s:
        assert s.scalar(select(EnrollCode.label).where(EnrollCode.user_id == uid)) == "テスト端末"
    # 端末を登録して、無効にすると、すぐに使えなくなる
    with Session(get_engine()) as s:
        tok = enroll(fresh, issue(s, target)).json()["token"]
        dev_id = s.scalar(select(DeviceToken.id).where(DeviceToken.user_id == uid))
    assert fresh.get("/api/ar/plan", headers=bearer(tok)).status_code == 200
    client.post(f"/admin/devices/{dev_id}/revoke", data={"csrf_token": token(client, "/admin/devices")})
    assert fresh.get("/api/ar/plan", headers=bearer(tok)).status_code == 401
    assert "無効（" in client.get("/admin/devices").text


def test_admin_enroll_rejects_bad_csrf_and_unknown_user(make_user, clean_devices, client):  # noqa: F811
    login(client, make_user("admin"))
    t = token(client, "/admin/devices")
    assert client.post("/admin/devices/enroll", data={"user_id": "1", "csrf_token": "bad"}).status_code == 400
    assert client.post("/admin/devices/enroll", data={"user_id": "999999999", "csrf_token": t}).status_code == 400


def test_non_admin_cannot_use_device_admin(make_user, clean_devices, client):  # noqa: F811
    login(client, make_user("user"))
    for method, path in (("get", "/admin/devices"), ("post", "/admin/devices/enroll"), ("post", "/admin/devices/1/revoke")):
        r = getattr(client, method)(path, follow_redirects=False)
        assert r.status_code in (303, 422), (path, r.status_code)
        if r.status_code == 303:
            assert r.headers["location"] == "/"


def test_setup_landing_page_does_not_use_the_code(make_user, clean_devices, fresh):  # noqa: F811
    uid = make_user()
    with Session(get_engine()) as s:
        code = issue(s, uid)
    assert fresh.get(f"/setup/{code}").status_code == 200  # カメラで読んでも、コードは使われない
    assert enroll(fresh, code).status_code == 200


def test_qr_contains_setup_url_the_app_parses_and_code_redeems(make_user, clean_devices, client, fresh, monkeypatch):  # noqa: F811
    """管理画面のQRに入るURLが、アプリ（SETUP_URL）の形で、そのコードが端末トークンに引き換えられる。"""
    import re

    from app.routers import admin_devices

    seen = {}
    real = admin_devices.qr_svg_file
    monkeypatch.setattr(admin_devices, "qr_svg_file", lambda url: seen.setdefault("url", url) and real(url))
    target = make_user()
    login(client, make_user("admin"))
    client.post("/admin/devices/enroll", data={"user_id": str(_user_id(target)), "label": "",
                                               "csrf_token": token(client, "/admin/devices")},
                headers={"host": "192.168.128.100:8765"})
    m = re.fullmatch(r"(https?://[^/\s]+)/setup/([A-Za-z0-9_-]{16,64})", seen["url"])  # アプリの SETUP_URL と同じ形
    assert m and m.group(1).endswith("192.168.128.100:8765")
    assert enroll(fresh, m.group(2)).status_code == 200
