"""AR棚卸のサーバー側：アンカー、予定、記録の受け取り、棚卸の終了と取り消し、結果ページとCSV。"""
import csv
import io
import os
import random
import re

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import Base, get_engine
from app.models import Anchor, ArItem, Asset, Inventory, InventoryRecord
from tests.test_auth import client, login, make_user, token  # noqa: F401（フィクスチャを再利用）


@pytest.fixture()
def clean():
    """AR棚卸のテーブルを、テストの前後で空にする。

    開発用DBに、実際の棚卸のデータがあるときは、消してしまわないように、テストを飛ばす
    （消してよいときは、環境変数 ALLOW_WIPE_AR=1）。アンカーは、名前が「テスト」で始まるものだけを消す。
    """
    Base.metadata.create_all(get_engine())  # アプリの起動より前に動くので、新しいテーブルを先に作っておく
    with Session(get_engine()) as s:
        has_data = any(s.scalar(select(m).limit(1)) is not None for m in (ArItem, Inventory, InventoryRecord))
    if has_data and os.environ.get("ALLOW_WIPE_AR") != "1":
        pytest.skip("ar_items・inventories に、データがあります（消してよければ ALLOW_WIPE_AR=1）")

    def wipe():
        with Session(get_engine()) as s:
            for m in (InventoryRecord, Inventory, ArItem):
                s.execute(delete(m))
            s.execute(delete(Anchor).where(Anchor.name.like("テスト%")))
            s.execute(delete(Asset).where(Asset.asset_no.like("9997%")))
            s.commit()
    wipe()
    yield
    wipe()


@pytest.fixture()
def api(client, make_user, clean):  # noqa: F811
    login(client, make_user("user"))
    csrf = client.get("/api/ar/plan").json()["csrf"]
    client.headers.update({"X-CSRF-Token": csrf})
    return client


@pytest.fixture()
def admin(client, make_user, clean):  # noqa: F811
    login(client, make_user("admin"))
    return client


def put_item(c, tok, floor=1, x=0.0, y=0.0, **kw):
    return c.put(f"/api/ar/items/{tok}", json={"floor": floor, "x": x, "y": y, **kw})


_n = [0]


def rec(tok, minutes=0, **kw):
    _n[0] += 1
    return {"client_id": f"c{_n[0]:08d}{random.randint(0, 10**6):06d}", "kind": "read", "token": tok,
            "read_at": f"2026-11-26T09:{minutes:02d}:00+09:00", **kw}


def post(c, *records):
    return c.post("/api/ar/records", json={"records": list(records)})


# ---- 認証 ----
def test_api_requires_login_and_csrf(client, clean):  # noqa: F811
    assert client.get("/api/ar/plan").status_code == 401
    assert client.put("/api/ar/items/a", json={"x": 0, "y": 0}).status_code == 401


def test_update_without_csrf_is_rejected(client, make_user, clean):  # noqa: F811
    login(client, make_user("user"))
    assert client.put("/api/ar/items/a1", json={"x": 0, "y": 0}).status_code == 403
    assert client.post("/api/ar/records", json={"records": []}).status_code == 403


# ---- 予定 ----
def test_register_item_and_read_plan(api):
    r = put_item(api, "Tnote01", floor=2, x=3.5, y=4.0, err_m=0.8, name="ノートPC")
    assert r.status_code == 200
    items = api.get("/api/ar/plan").json()["items"]
    assert items[0]["token"] == "Tnote01" and items[0]["floor"] == 2 and items[0]["name"] == "ノートPC"
    # 置き換え。削除もできる
    put_item(api, "Tnote01", floor=3, x=1.0, y=1.0)
    assert api.get("/api/ar/plan").json()["items"][0]["floor"] == 3
    assert api.delete("/api/ar/items/Tnote01").status_code == 200
    assert api.get("/api/ar/plan").json()["items"] == []


def test_register_uses_ledger_name_when_tag_exists(api):
    with Session(get_engine()) as s:
        s.add(Asset(asset_no="9997000001", name="台帳のPC", tag_token="TledgerPC01"))
        s.commit()
    r = put_item(api, "TledgerPC01", name="無視される名前").json()
    assert r["name"] == "台帳のPC" and r["asset_no"] == "9997000001"


def test_invalid_token_is_rejected(api):
    assert put_item(api, "bad token!").status_code in (400, 404)


# ---- 記録の受け取り ----
def test_records_are_idempotent(api):
    put_item(api, "a1")
    r1 = rec("a1")
    first = post(api, r1).json()
    assert first["results"][0]["status"] == "ok"
    again = post(api, r1).json()  # 再送しても、二重にならない
    assert again["results"][0]["status"] == "duplicate"
    with Session(get_engine()) as s:
        assert len(s.scalars(select(InventoryRecord)).all()) == 1
        assert len(s.scalars(select(Inventory)).all()) == 1  # 棚卸は、最初の記録で自動的に始まる


def test_bad_record_does_not_block_good_ones(api):
    put_item(api, "a1")
    out = post(api, {"client_id": "x"}, rec("a1"), rec("")).json()["results"]
    assert [r["status"] for r in out] == ["error", "ok", "error"]


def test_manual_entry_by_asset_no(api):
    with Session(get_engine()) as s:
        s.add(Asset(asset_no="9997000002", name="手入力の備品", tag_token="Tmanual0001"))
        s.commit()
    put_item(api, "Tmanual0001")
    ok = post(api, rec("", asset_no="9997000002", method="manual")).json()["results"][0]
    assert ok["status"] == "ok"
    unknown = post(api, rec("", asset_no="9997999999", method="manual")).json()["results"][0]
    assert unknown["status"] == "error"
    with Session(get_engine()) as s:
        r = s.scalar(select(InventoryRecord))
        assert r.token == "Tmanual0001" and r.method == "manual"


def test_employee_no_is_validated(api):
    put_item(api, "a1")
    assert post(api, rec("a1", employee_no="E1001")).json()["results"][0]["status"] == "ok"
    assert post(api, rec("a1", employee_no="社員１")).json()["results"][0]["status"] == "error"


def test_too_many_records_are_rejected(api):
    assert post(api, *[{"client_id": f"c{i:09d}"} for i in range(501)]).status_code == 422


# ---- 棚卸を終える・取り消し ----
def test_finish_updates_plan_and_undo_restores(api):
    put_item(api, "a1", x=1, y=1)
    put_item(api, "b1", x=2, y=2)
    put_item(api, "c1", x=3, y=3)
    inv = post(api, rec("a1"), rec("b1", 1, floor=2, x=9.0, y=9.0, moved=True), rec("z9", 2, floor=1, x=4.0, y=4.0)).json()["inventory_id"]
    s = api.post(f"/api/ar/inventories/{inv}/finish").json()["summary"]
    assert s == {"checked": 2, "checked_moved": 1, "missed": 1, "unexpected": 1}
    items = {i["token"]: i for i in api.get("/api/ar/plan").json()["items"]}
    assert items["c1"]["missed_last"] and not items["a1"]["missed_last"]
    assert items["b1"]["floor"] == 2 and items["b1"]["x"] == 9.0  # 場所違いは、読んだ場所に更新
    assert items["z9"]["was_unexpected"] and items["z9"]["name"] == "z9"  # 想定外は、予定に加わる
    assert api.get("/api/ar/plan").json()["inventory"] is None
    assert api.post(f"/api/ar/inventories/{inv}/finish").status_code == 409  # 二重に終えられない

    assert api.post(f"/api/ar/inventories/{inv}/undo-finish").status_code == 200
    items = {i["token"]: i for i in api.get("/api/ar/plan").json()["items"]}
    assert set(items) == {"a1", "b1", "c1"} and items["b1"]["floor"] == 1 and not items["c1"]["missed_last"]
    assert api.get("/api/ar/plan").json()["inventory"]["id"] == inv  # 開き直る


def test_undo_is_refused_when_next_inventory_has_records(api):
    put_item(api, "a1")
    inv = post(api, rec("a1")).json()["inventory_id"]
    api.post(f"/api/ar/inventories/{inv}/finish")
    post(api, rec("a1", 5))  # 次の棚卸が、始まった
    assert api.post(f"/api/ar/inventories/{inv}/undo-finish").status_code == 409


def test_undo_discards_empty_next_inventory(api):
    put_item(api, "a1")
    inv = post(api, rec("a1")).json()["inventory_id"]
    api.post(f"/api/ar/inventories/{inv}/finish")
    with Session(get_engine()) as s:  # 記録のない、空の棚卸が開いている状態
        s.add(Inventory(status="open"))
        s.commit()
    assert api.post(f"/api/ar/inventories/{inv}/undo-finish").status_code == 200
    with Session(get_engine()) as s:
        assert [i.status for i in s.scalars(select(Inventory))] == ["open"]


def test_only_latest_finished_inventory_can_be_undone(api):
    put_item(api, "a1")
    first = post(api, rec("a1")).json()["inventory_id"]
    api.post(f"/api/ar/inventories/{first}/finish")
    second = post(api, rec("a1", 5)).json()["inventory_id"]
    api.post(f"/api/ar/inventories/{second}/finish")
    assert api.post(f"/api/ar/inventories/{first}/undo-finish").status_code == 409
    assert api.post(f"/api/ar/inventories/{second}/undo-finish").status_code == 200


def test_unconfirm_record_cancels_in_summary(api):
    put_item(api, "a1")
    inv = post(api, rec("a1", 0), rec("a1", 1, kind="unconfirm")).json()["inventory_id"]
    assert api.post(f"/api/ar/inventories/{inv}/finish").json()["summary"]["checked"] == 0


# ---- アンカー ----
def find_anchor():
    with Session(get_engine()) as s:
        return s.scalar(select(Anchor).where(Anchor.name.like("テスト%")))


def create_anchor(c, name="テスト入口", floor="1", x="0", y="0", facing="90"):
    return c.post("/admin/anchors", data={"name": name, "floor": floor, "x": x, "y": y, "facing_deg": facing,
                                          "csrf_token": token(c, "/admin/anchors")}, follow_redirects=False)


def test_anchor_create_edit_qr_and_plan(admin):
    assert create_anchor(admin).status_code == 303
    a = find_anchor()
    assert re.fullmatch(r"A[0-9a-f]{10}", a.anchor_token) and a.facing_deg == 90.0
    page = admin.get(f"/admin/anchors/{a.anchor_token}").text
    assert f"/a/{a.anchor_token}" in page and "テスト入口" in page
    svg = admin.get(f"/admin/anchors/{a.anchor_token}/qr.svg?download=1")
    assert svg.status_code == 200 and svg.headers["content-type"].startswith("image/svg+xml")
    assert "attachment" in svg.headers["content-disposition"]
    # 更新（向きは0〜360に収める。空欄は未設定）・停止
    t = token(admin, f"/admin/anchors/{a.anchor_token}")
    admin.post(f"/admin/anchors/{a.anchor_token}", data={"name": "テスト入口2", "floor": "-1", "x": "1.5", "y": "2",
                                                         "facing_deg": "450", "csrf_token": t})
    a2 = find_anchor()
    assert (a2.name, a2.floor, a2.x_m, a2.y_m, a2.facing_deg) == ("テスト入口2", -1, 1.5, 2.0, 90.0)
    admin.post(f"/admin/anchors/{a.anchor_token}", data={"name": "テスト入口2", "floor": "1", "x": "0", "y": "0",
                                                         "facing_deg": "", "csrf_token": token(admin, "/admin/anchors")})
    assert find_anchor().facing_deg is None

    def plan_tokens():
        return [x["token"] for x in admin.get("/api/ar/plan").json()["anchors"]]
    assert a.anchor_token in plan_tokens()
    admin.post(f"/admin/anchors/{a.anchor_token}/toggle", data={"csrf_token": token(admin, "/admin/anchors")})
    assert a.anchor_token not in plan_tokens()  # 停止すると、アプリには渡らない


def test_plan_anchor_fields_match_anchor_api(admin):
    create_anchor(admin, x="3", y="4", floor="2")
    a = find_anchor()
    in_plan = next(x for x in admin.get("/api/ar/plan").json()["anchors"] if x["token"] == a.anchor_token)
    assert in_plan == admin.get(f"/api/anchors/{a.anchor_token}").json()  # 既存の取得APIと、同じ形


def test_anchor_validation(admin):
    for bad in ({"name": ""}, {"floor": "0"}, {"floor": "100"}, {"floor": "a"}, {"x": "nan"}, {"x": "99999"}, {"facing": "nan"}):
        assert create_anchor(admin, **bad).status_code == 400, bad
    assert find_anchor() is None


def test_anchor_url_matches_what_the_app_parses(admin):
    """アプリは、/a/ で始まるURLをアンカーとして読む。QRのURLが、その形になっている。"""
    create_anchor(admin)
    a = find_anchor()
    url = re.search(r"<code[^>]*>(https?://[^<]+)</code>", admin.get(f"/admin/anchors/{a.anchor_token}").text).group(1)
    assert re.fullmatch(r"https?://[^/\s]+/(a|i)/([A-Za-z0-9_-]{1,40})/?", url) and "/a/" in url
    assert admin.get(f"/a/{a.anchor_token}").status_code == 200


def test_non_admin_cannot_use_admin_pages(client, make_user, clean):  # noqa: F811
    login(client, make_user("user"))
    for path in ("/admin/anchors", "/admin/inventories"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/"


# ---- 結果ページとCSV ----
def test_result_page_and_csv(client, make_user, clean):  # noqa: F811
    login(client, make_user("user"))
    csrf = client.get("/api/ar/plan").json()["csrf"]
    client.headers.update({"X-CSRF-Token": csrf})
    client.put("/api/ar/items/a1", json={"x": 0, "y": 0, "name": "=PC"})
    client.put("/api/ar/items/b1", json={"x": 0, "y": 0, "name": "プリンター"})
    inv = post(client, rec("a1", employee_no="E1001", floor=1, x=1.0, y=1.0, moved=True), rec("z9", 1, floor=1)).json()["inventory_id"]
    # 一般ユーザーは、結果ページを見られない
    assert client.get(f"/admin/inventories/{inv}", follow_redirects=False).status_code == 303
    client.headers.pop("X-CSRF-Token")
    client.cookies.clear()
    login(client, make_user("admin"))

    assert "進行中" in client.get("/admin/inventories").text
    detail = client.get(f"/admin/inventories/{inv}").text
    assert "確認済み 1件（うち場所違い 1件）／未確認 1件／想定外 1件" in detail
    r = client.get(f"/admin/inventories/{inv}/export.csv")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0][:3] == ["区分", "場所違い", "前回未確認"]
    by_kind = {row[0]: row for row in rows[1:]}
    assert set(by_kind) == {"確認済み", "未確認", "想定外"}
    assert by_kind["確認済み"][1] == "はい" and by_kind["確認済み"][5] == "'=PC"  # 数式として実行されない
    assert by_kind["確認済み"][10] == "E1001"
    assert by_kind["想定外"][4] == "z9"
