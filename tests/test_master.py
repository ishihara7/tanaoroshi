import io
import random
import re

import pytest
from PIL import Image
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Asset, Category, Floor
from app.services.geo import accuracy_in_ratio, to_map_position
from tests.test_auth import client, login, make_user, token  # noqa: F401（フィクスチャを再利用）

TEST_BUILDING = "テスト棟_pytest"


@pytest.fixture()
def admin_client(client, make_user):  # noqa: F811
    login(client, make_user("admin"))
    yield client
    with Session(get_engine()) as s:
        s.execute(delete(Asset).where(Asset.asset_no.like("9999%")))
        s.execute(delete(Floor).where(Floor.building == TEST_BUILDING))
        s.execute(delete(Category).where(Category.name.like("pytest\\_%", escape="\\")))
        s.commit()


def png_bytes(w=200, h=100) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "white").save(buf, "PNG")
    return buf.getvalue()


def new_asset_no() -> str:
    return "9999" + f"{random.randint(0, 999999):06d}"


# ---- 位置の変換（純粋な計算）----
def aligned_floor() -> Floor:
    return Floor(building="b", floor_label="1F", tl_lat=36.2940, tl_lon=139.3750, br_lat=36.2920, br_lon=139.3780)


def test_to_map_position_center_and_corners():
    f = aligned_floor()
    c = to_map_position(f, 36.2930, 139.3765)
    assert (round(c.x_ratio, 3), round(c.y_ratio, 3), c.inside) == (0.5, 0.5, True)
    tl = to_map_position(f, 36.2940, 139.3750)
    assert (tl.x_ratio, tl.y_ratio) == (0.0, 0.0)
    br = to_map_position(f, 36.2920, 139.3780)
    assert (round(br.x_ratio, 3), round(br.y_ratio, 3)) == (1.0, 1.0)


def test_to_map_position_outside_and_unaligned():
    f = aligned_floor()
    assert to_map_position(f, 36.3000, 139.4000).inside is False  # 建物外の可能性
    assert to_map_position(f, 36.2941, 139.3749).inside is True  # 余白の範囲内
    assert to_map_position(Floor(building="b", floor_label="1F"), 36.0, 139.0) is None


def test_accuracy_in_ratio():
    rx, ry = accuracy_in_ratio(aligned_floor(), 20.0, 36.293)
    assert 0 < rx < 1 and 0 < ry < 1
    assert accuracy_in_ratio(Floor(building="b", floor_label="1F"), 20.0, 36.0) is None


# ---- 種別 ----
def test_default_categories_are_seeded(admin_client):
    html = admin_client.get("/admin/categories").text
    for name in ["ノートPC", "モニター", "LANハブ", "その他"]:
        assert name in html


def test_category_add_duplicate_and_toggle(admin_client):
    t = token(admin_client, "/admin/categories")
    r = admin_client.post("/admin/categories", data={"name": "pytest_プロジェクター", "csrf_token": t}, follow_redirects=False)
    assert r.status_code == 303
    assert admin_client.post("/admin/categories", data={"name": "pytest_プロジェクター", "csrf_token": t}).status_code == 400
    with Session(get_engine()) as s:
        cid = s.scalar(select(Category.id).where(Category.name == "pytest_プロジェクター"))
    assert admin_client.post(f"/admin/categories/{cid}/toggle", data={"csrf_token": t}, follow_redirects=False).status_code == 303
    with Session(get_engine()) as s:
        assert s.get(Category, cid).is_active is False


# ---- フロア図 ----
def create_floor(c, image=None, label="2F"):
    t = token(c, "/admin/floors")
    return c.post("/admin/floors", data={"building": TEST_BUILDING, "floor_label": label, "sort_order": "1", "csrf_token": t},
                  files={"image": ("plan.png", image or png_bytes(), "image/png")}, follow_redirects=False)


def test_floor_create_and_image_served_only_to_logged_in(admin_client, client):  # noqa: F811
    r = create_floor(admin_client)
    assert r.status_code == 303
    floor_id = int(re.search(r"/admin/floors/(\d+)", r.headers["location"]).group(1))
    img = admin_client.get(f"/floors/{floor_id}/image")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    with Session(get_engine()) as s:
        f = s.get(Floor, floor_id)
        assert (f.image_width, f.image_height) == (200, 100) and not f.is_aligned


def test_floor_image_requires_login(client):  # noqa: F811
    r = client.get("/floors/1/image", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")


def test_floor_rejects_non_image(admin_client):
    t = token(admin_client, "/admin/floors")
    r = admin_client.post("/admin/floors", data={"building": TEST_BUILDING, "floor_label": "3F", "csrf_token": t},
                          files={"image": ("x.png", b"not an image", "image/png")})
    assert r.status_code == 400 and "画像として読み込めません" in r.text


def test_floor_alignment_save_and_validation(admin_client):
    r = create_floor(admin_client)
    fid = int(re.search(r"/admin/floors/(\d+)", r.headers["location"]).group(1))
    base = {"building": TEST_BUILDING, "floor_label": "2F", "sort_order": "1"}

    def post(**kw):
        return admin_client.post(f"/admin/floors/{fid}", data={**base, **kw, "csrf_token": token(admin_client, f"/admin/floors/{fid}")},
                                 follow_redirects=False)

    ok = post(tl_lat="36.2940", tl_lon="139.3750", br_lat="36.2920", br_lon="139.3780")
    assert ok.status_code == 303
    with Session(get_engine()) as s:
        assert s.get(Floor, fid).is_aligned
    assert post(tl_lat="36.2940", tl_lon="139.3750", br_lat="", br_lon="").status_code == 400  # 一部だけ
    assert post(tl_lat="abc", tl_lon="1", br_lat="2", br_lon="3").status_code == 400
    assert post(tl_lat="36.2920", tl_lon="139.3750", br_lat="36.2940", br_lon="139.3780").status_code == 400  # 左上が南
    assert post(tl_lat="", tl_lon="", br_lat="", br_lon="").status_code == 303  # 空なら未登録に戻る
    with Session(get_engine()) as s:
        assert not s.get(Floor, fid).is_aligned


# ---- 備品 ----
def create_asset(c, asset_no, name="テストPC"):
    t = token(c, "/admin/assets")
    return c.post("/admin/assets", data={"asset_no": asset_no, "name": name, "category_id": "", "note": "", "csrf_token": t},
                  follow_redirects=False)


def test_asset_create_keeps_leading_zeros_and_issues_token(admin_client):
    no = "9999000001"
    # 先頭が0のケースを確認するため、別の番号も使う
    r = create_asset(admin_client, no)
    assert r.status_code == 303
    with Session(get_engine()) as s:
        a = s.get(Asset, no)
        assert a.asset_no == no and len(a.tag_token) == 12 and a.is_active
        assert no not in a.tag_token
    page = admin_client.get(f"/admin/assets/{no}").text
    url = re.search(r"<code[^>]*>(https?://[^<]+)</code>", page).group(1)
    assert url.endswith("/i/" + a.tag_token) and no not in url  # URLに管理番号は含まれない


def test_asset_validation_and_duplicate(admin_client):
    no = new_asset_no()
    assert create_asset(admin_client, no).status_code == 303
    assert create_asset(admin_client, no).status_code == 400  # 重複
    for bad in ["123", "12345678901", "abcdefghij", "１２３４５６７８９０"]:
        assert create_asset(admin_client, bad).status_code == 400
    assert create_asset(admin_client, new_asset_no(), name="").status_code == 400


def test_asset_reissue_changes_token(admin_client):
    no = new_asset_no()
    create_asset(admin_client, no)
    with Session(get_engine()) as s:
        old = s.get(Asset, no).tag_token
    admin_client.post(f"/admin/assets/{no}/reissue", data={"csrf_token": token(admin_client, f"/admin/assets/{no}")}, follow_redirects=False)
    with Session(get_engine()) as s:
        assert s.get(Asset, no).tag_token != old


def test_asset_dispose_hides_from_list(admin_client):
    no = new_asset_no()
    create_asset(admin_client, no, name="廃棄テスト機")
    assert no in admin_client.get("/admin/assets").text
    admin_client.post(f"/admin/assets/{no}/dispose", data={"csrf_token": token(admin_client, f"/admin/assets/{no}")}, follow_redirects=False)
    assert no not in admin_client.get("/admin/assets").text
    assert no in admin_client.get("/admin/assets?all=1").text  # 履歴として残る


def test_master_pages_are_admin_only(client, make_user):  # noqa: F811
    login(client, make_user("user"))
    for path in ["/admin/assets", "/admin/floors", "/admin/categories"]:
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/"
