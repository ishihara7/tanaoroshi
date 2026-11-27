import math

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import FloorModel
from app.routers import admin_models
from tests.test_auth import client, login, make_user  # noqa: F401

FLOOR = 97  # テスト用の階（実データと重ならない）

PLY = (b"ply\nformat binary_little_endian 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\n"
       b"end_header\n" + bytes(12))


@pytest.fixture()
def cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr(admin_models, "MODEL_DIR", tmp_path)  # 実際の var/models は触らない
    yield
    with Session(get_engine()) as s:
        s.execute(delete(FloorModel).where(FloorModel.floor == FLOOR))
        s.commit()


def csrf_of(client):  # noqa: F811
    html = client.get("/admin/models").text
    return html.split('name="csrf_token" value="')[1].split('"')[0]


def upload(client, name="x.ply", data=PLY):  # noqa: F811
    return client.post("/admin/models/upload", data={"floor": FLOOR, "csrf_token": csrf_of(client)},
                       files={"file": (name, data)}, follow_redirects=False)


def admin(client, make_user):  # noqa: F811
    login(client, make_user(role="admin"))


def test_models_require_admin(client, make_user):  # noqa: F811
    login(client, make_user())
    assert client.get("/admin/models", follow_redirects=False).status_code == 303
    assert client.get(f"/admin/models/{FLOOR}/model.ply", follow_redirects=False).status_code == 303


def test_upload_view_and_file(client, make_user, cleanup):  # noqa: F811
    admin(client, make_user)
    r = upload(client)
    assert r.status_code == 303 and r.headers["location"] == f"/admin/models/{FLOOR}"
    page = client.get(f"/admin/models/{FLOOR}")
    assert page.status_code == 200 and "model.ply" in page.text
    f = client.get(f"/admin/models/{FLOOR}/model.ply")
    assert f.status_code == 200 and f.content == PLY
    assert client.get(f"/admin/models/{FLOOR}/model.splat").status_code == 404


def test_upload_rejects_bad_files(client, make_user, cleanup):  # noqa: F811
    admin(client, make_user)
    assert upload(client, "x.txt").status_code == 400
    assert upload(client, "x.ply", b"not a ply file").status_code == 400
    assert upload(client, "x.ply", b"").status_code == 400


def test_upload_requires_csrf(client, make_user, cleanup):  # noqa: F811
    admin(client, make_user)
    r = client.post("/admin/models/upload", data={"floor": FLOOR, "csrf_token": "wrong"}, files={"file": ("x.ply", PLY)})
    assert r.status_code == 400
    assert client.get(f"/admin/models/{FLOOR}", follow_redirects=False).status_code == 303  # 登録されていない


def test_align_save_and_reload(client, make_user, cleanup):  # noqa: F811
    admin(client, make_user)
    upload(client)
    tok = csrf_of(client)
    body = {"y_sign": -1, "floor_y": 0.5, "pairs": [
        {"anchor": "A1", "mx": 1, "my": 0.5, "mz": 2}, {"anchor": "A2", "mx": 3, "my": 0.5, "mz": 5}],
        "transform": {"s": 2.5, "theta": math.pi / 2, "tx": 1.0, "ty": -2.0, "rms": 0.03}}
    r = client.post(f"/admin/models/{FLOOR}/align", json=body, headers={"X-CSRF-Token": tok})
    assert r.status_code == 200
    with Session(get_engine()) as s:
        m = s.get(FloorModel, FLOOR)
        assert (m.y_sign, m.floor_y, m.scale, round(m.theta_deg, 6), m.tx, m.ty) == (-1, 0.5, 2.5, 90.0, 1.0, -2.0)
    # 画面に、保存した状態が入る
    assert '"ySign": -1' in client.get(f"/admin/models/{FLOOR}").text.replace("&#34;", '"')


def test_align_rejects_bad_input(client, make_user, cleanup):  # noqa: F811
    admin(client, make_user)
    upload(client)
    tok = csrf_of(client)
    url, h = f"/admin/models/{FLOOR}/align", {"X-CSRF-Token": tok}
    good_pairs = [{"anchor": "A1", "mx": 1, "my": 0, "mz": 2}, {"anchor": "A2", "mx": 3, "my": 0, "mz": 5}]
    t = {"s": 1, "theta": 0, "tx": 0, "ty": 0, "rms": 0}
    assert client.post(url, json={"y_sign": 1, "floor_y": 0, "pairs": [], "transform": None}, headers={"X-CSRF-Token": "bad"}).status_code == 400
    assert client.post(url, json={"y_sign": 2, "floor_y": 0}, headers=h).status_code == 400            # 向きが不正
    assert client.post(url, json={"y_sign": 1, "floor_y": "x"}, headers=h).status_code == 400          # 数値でない
    assert client.post(url, json={"y_sign": 1, "floor_y": 0, "pairs": good_pairs[:1], "transform": t}, headers=h).status_code == 400  # 対応点が1つ
    assert client.post(url, json={"y_sign": 1, "floor_y": 0, "pairs": good_pairs, "transform": {**t, "s": 0}}, headers=h).status_code == 400
    raw = ('{"y_sign": 1, "floor_y": 0, "pairs": [{"anchor":"A1","mx":1,"my":0,"mz":2},{"anchor":"A2","mx":3,"my":0,"mz":5}],'
           ' "transform": {"s":1,"theta":0,"tx":Infinity,"ty":0,"rms":0}}')
    assert client.post(url, content=raw, headers={**h, "Content-Type": "application/json"}).status_code == 400  # 無限大
    assert client.post(url, json={"y_sign": 1, "floor_y": 0, "pairs": [{"anchor": "A", "mx": "a"}], "transform": None}, headers=h).status_code == 400
    assert client.post(url, content="[1]", headers={**h, "Content-Type": "application/json"}).status_code == 400
    assert client.post("/admin/models/96/align", json={"y_sign": 1, "floor_y": 0}, headers=h).status_code == 404


def test_delete_removes_model_and_file(client, make_user, cleanup):  # noqa: F811
    admin(client, make_user)
    upload(client)
    assert (admin_models.MODEL_DIR / f"floor_{FLOOR}.ply").exists()
    client.post(f"/admin/models/{FLOOR}/delete", data={"csrf_token": csrf_of(client)}, follow_redirects=False)
    assert not (admin_models.MODEL_DIR / f"floor_{FLOOR}.ply").exists()
    assert client.get(f"/admin/models/{FLOOR}", follow_redirects=False).status_code == 303


def test_view_with_inventory_result_and_link(client, make_user, cleanup):  # noqa: F811
    """結果ページに、3Dへのリンクが出る。3D画面は、棚卸の結果を表示できる。"""
    from app.models import Inventory
    admin(client, make_user)
    upload(client)
    with Session(get_engine()) as s:
        inv = Inventory(status="closed")
        s.add(inv)
        s.commit()
        inv_id = inv.id
    try:
        assert f"/admin/models/{FLOOR}?inv={inv_id}" in client.get(f"/admin/inventories/{inv_id}").text
        page = client.get(f"/admin/models/{FLOOR}?inv={inv_id}")
        assert page.status_code == 200 and "結果を表示しています" in page.text
        assert client.get(f"/admin/models/{FLOOR}?inv=99999999").status_code == 200  # 存在しない棚卸は、予定の表示
    finally:
        with Session(get_engine()) as s:
            s.execute(delete(Inventory).where(Inventory.id == inv_id))
            s.commit()


def test_result_items_statuses(cleanup):
    """棚卸の結果を、札にする：確認済み・場所違い・未確認（予定の位置）・想定外。別の階は出ない。"""
    from datetime import datetime
    from app.models import ArItem, Inventory, InventoryRecord
    with Session(get_engine()) as s:
        inv = Inventory(status="open")
        s.add(inv)
        s.add_all([ArItem(token="TXa", name="確認", floor=FLOOR, x=1, y=1), ArItem(token="TXb", name="場所違い", floor=FLOOR, x=2, y=2),
                   ArItem(token="TXc", name="未確認", floor=FLOOR, x=3, y=3, err_m=0.6),
                   ArItem(token="TXd", name="別の階", floor=FLOOR + 1, x=4, y=4)])
        s.commit()
        n = 0
        for tok, x, y, moved in [("TXa", 1.1, 1.2, False), ("TXb", 5.0, 6.0, True), ("TXz", 7.0, 8.0, False)]:
            n += 1
            s.add(InventoryRecord(client_id=f"tx-{inv.id}-{n}", inventory_id=inv.id, kind="read", token=tok, floor=FLOOR, x=x, y=y,
                                  moved=moved, user_id=0, read_at=datetime(2026, 1, 1, 0, n)))
        s.commit()
        try:
            got = {i["token"]: i for i in admin_models._result_items(s, inv, FLOOR)}
        finally:
            s.execute(delete(InventoryRecord).where(InventoryRecord.inventory_id == inv.id))
            s.execute(delete(ArItem).where(ArItem.token.like("TX%")))
            s.execute(delete(Inventory).where(Inventory.id == inv.id))
            s.commit()
    assert {k: (v["status"], v["x"], v["y"]) for k, v in got.items()} == {
        "TXa": ("ok", 1.1, 1.2), "TXb": ("moved", 5.0, 6.0), "TXc": ("missed", 3, 3), "TXz": ("unexpected", 7.0, 8.0)}
    assert got["TXc"]["err_m"] == 0.6
