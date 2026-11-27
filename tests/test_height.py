"""高さ（床からのm）の記録：アンカーの高さ、備品の高さ、棚卸の記録の高さ。実データには触れない（TH で始まるものだけ作って消す）。"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Anchor, ArItem, Asset, Inventory, InventoryRecord
from app.services import inventories as svc
from app.services.inventory_logic import Item, Read, derive, finish
from tests.test_auth import client, login, make_user  # noqa: F401

T0 = datetime(2026, 1, 1)


# ---- 純粋な計算（棚卸を終えたあとの予定）----
def read(id, token, minutes=0, **kw):
    return Read(id=id, token=token, kind="read", read_at=T0 + timedelta(minutes=minutes), **kw)


def no_desc(_token):
    return None, "x"


def test_finish_moves_height_with_the_new_position():
    items = [Item("a", "A", floor=1, x=1, y=1, z=0.4), Item("b", "B", floor=1, x=2, y=2, z=1.2)]
    d = derive(items, [read(1, "a", floor=2, x=5.0, y=6.0, z=1.5, moved=True), read(2, "b", floor=1, x=2.1, y=2.0, z=0.3)])
    nxt, _ = finish(items, d, no_desc)
    a, b = {i.token: i for i in nxt}["a"], {i.token: i for i in nxt}["b"]
    assert (a.floor, a.x, a.y, a.z) == (2, 5.0, 6.0, 1.5)  # 場所違い：読んだ位置と高さに更新
    assert b.z == 1.2  # 場所違いでなければ、予定のまま


def test_finish_unexpected_keeps_height_only_when_located():
    d = derive([], [read(1, "u", floor=1, x=3.0, y=4.0, z=0.9), read(2, "v", floor=1)])
    nxt, _ = finish([], d, no_desc)
    by = {i.token: i for i in nxt}
    assert by["u"].located and by["u"].z == 0.9
    assert not by["v"].located and by["v"].z is None  # 位置が取れていなければ、高さもなし


def test_missed_item_keeps_its_height():
    items = [Item("a", "A", z=1.1)]
    nxt, _ = finish(items, derive(items, []), no_desc)
    assert nxt[0].z == 1.1 and nxt[0].missed_last


# ---- DB・API ----
@pytest.fixture()
def tidy():
    def wipe():
        with Session(get_engine()) as s:
            ids = s.scalars(select(Inventory.id).where(Inventory.started_at == T0)).all()
            s.execute(delete(InventoryRecord).where(InventoryRecord.token.like("TH%")))
            s.execute(delete(Inventory).where(Inventory.id.in_(ids)))
            s.execute(delete(ArItem).where(ArItem.token.like("TH%")))
            s.execute(delete(Asset).where(Asset.asset_no.like("TH%")))
            s.execute(delete(Anchor).where(Anchor.name.like("TH%")))
            s.commit()
    wipe()
    yield
    wipe()


def test_item_height_roundtrip_in_plan(client, make_user, tidy):  # noqa: F811
    with Session(get_engine()) as s:
        s.add(Asset(asset_no="TH0001", name="TH 備品", tag_token="THtok0001"))
        s.commit()
    login(client, make_user("user"))
    csrf = client.get("/api/ar/plan").json()["csrf"]
    h = {"X-CSRF-Token": csrf}
    r = client.put("/api/ar/items/THtok0001", json={"floor": 1, "x": 1.0, "y": 2.0, "z": 1.35}, headers=h)
    assert r.status_code == 200 and r.json()["z"] == 1.35
    got = {i["token"]: i for i in client.get("/api/ar/plan").json()["items"]}["THtok0001"]
    assert got["z"] == 1.35
    # 高さなしで登録し直すと、高さは空になる（古いアプリとも互換）
    r = client.put("/api/ar/items/THtok0001", json={"floor": 1, "x": 1.0, "y": 2.0}, headers=h)
    assert r.status_code == 200 and r.json()["z"] is None
    # 範囲外は断る
    assert client.put("/api/ar/items/THtok0001", json={"floor": 1, "x": 1.0, "y": 2.0, "z": 1000}, headers=h).status_code == 422


def test_record_height_is_validated_and_stored(client, make_user, tidy):  # noqa: F811
    login(client, make_user("user"))
    csrf = client.get("/api/ar/plan").json()["csrf"]
    bad = {"client_id": "TH-bad-0001", "token": "THtok0002", "read_at": "2026-01-01T00:00:00Z", "z": 1000}
    res = client.post("/api/ar/records", json={"records": [bad]}, headers={"X-CSRF-Token": csrf}).json()["results"]
    assert res[0]["status"] == "error"  # 範囲外の高さは、その記録だけ、受け取らない
    # 保存した高さが、棚卸の結果に出る
    with Session(get_engine()) as s:
        inv = Inventory(status="closed", started_at=T0)
        s.add(inv)
        s.commit()
        s.add(InventoryRecord(client_id="TH-ok-0001", inventory_id=inv.id, kind="read", token="THtok0003", floor=1, x=1, y=2, z=0.8,
                              moved=False, user_id=0, read_at=T0))
        s.commit()
        assert [r.z for r in svc.reads_of(s, inv.id)] == [0.8]


def test_anchor_height_form_and_plan(client, make_user, tidy):  # noqa: F811
    login(client, make_user("admin"))
    html = client.get("/admin/anchors").text
    csrf = html.split('name="csrf_token" value="')[1].split('"')[0]
    form = {"name": "TH 入口", "floor": "1", "x": "0", "y": "0", "z": "1.4", "facing_deg": "", "csrf_token": csrf}
    r = client.post("/admin/anchors", data=form, follow_redirects=False)
    assert r.status_code == 303
    plan = {a["name"]: a for a in client.get("/api/ar/plan").json()["anchors"]}
    assert plan["TH 入口"]["z_m"] == 1.4
    # 高さを省くと0（床）。範囲外は断る
    r = client.post("/admin/anchors", data={**form, "name": "TH 低い", "z": ""}, follow_redirects=False)
    assert r.status_code == 303
    assert {a["name"]: a for a in client.get("/api/ar/plan").json()["anchors"]}["TH 低い"]["z_m"] == 0.0
    assert client.post("/admin/anchors", data={**form, "name": "TH 高すぎ", "z": "500"}).status_code == 400
