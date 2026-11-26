import uuid

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Anchor
from tests.test_auth import client, login, make_user  # noqa: F401


@pytest.fixture()
def anchors():
    """テスト用アンカー（トークンは TA で始める）。終了時に削除する。"""
    tok = "TA" + uuid.uuid4().hex[:8]
    off = "TB" + uuid.uuid4().hex[:8]
    with Session(get_engine()) as s:
        s.add(Anchor(anchor_token=tok, name="2F 東階段前", floor=2, x_m=12.5, y_m=3.0, facing_deg=90.0))
        s.add(Anchor(anchor_token=off, name="廃止", floor=1, x_m=0, y_m=0, is_active=False))
        s.commit()
    yield {"ok": tok, "off": off}
    with Session(get_engine()) as s:
        s.execute(delete(Anchor).where(Anchor.anchor_token.like("T[AB]%")))
        s.commit()


def test_anchor_requires_login(client, anchors):  # noqa: F811
    r = client.get(f"/api/anchors/{anchors['ok']}", follow_redirects=False)
    assert r.status_code == 303


def test_get_anchor(client, make_user, anchors):  # noqa: F811
    login(client, make_user())
    r = client.get(f"/api/anchors/{anchors['ok']}")
    assert r.status_code == 200
    assert r.json() == {"token": anchors["ok"], "name": "2F 東階段前", "floor": 2, "x_m": 12.5, "y_m": 3.0, "facing_deg": 90.0}


def test_inactive_or_unknown_anchor_is_404(client, make_user, anchors):  # noqa: F811
    login(client, make_user())
    assert client.get(f"/api/anchors/{anchors['off']}").status_code == 404
    assert client.get("/api/anchors/nothing").status_code == 404


def test_list_anchors_only_active(client, make_user, anchors):  # noqa: F811
    login(client, make_user())
    tokens = [a["token"] for a in client.get("/api/anchors").json()["anchors"]]
    assert anchors["ok"] in tokens and anchors["off"] not in tokens


def test_anchor_page(client, make_user, anchors):  # noqa: F811
    path = f"/a/{anchors['ok']}"
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login?next=")  # 未ログインはログインへ
    login(client, make_user(), next_=path)
    page = client.get(path)
    assert page.status_code == 200 and "2F 東階段前" in page.text
    assert client.get(f"/a/{anchors['off']}").status_code == 404
