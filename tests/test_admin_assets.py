import random
import re

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Asset
from tests.test_auth import client, login, make_user, token  # noqa: F401（フィクスチャを再利用）


@pytest.fixture()
def admin_client(client, make_user):  # noqa: F811
    login(client, make_user("admin"))
    yield client
    with Session(get_engine()) as s:
        s.execute(delete(Asset).where(Asset.asset_no.like("9999%")))
        s.commit()


def new_asset_no() -> str:
    return "9999" + f"{random.randint(0, 999999):06d}"


def create_asset(c, asset_no, name="テストPC"):
    t = token(c, "/admin/assets")
    return c.post("/admin/assets", data={"asset_no": asset_no, "name": name, "note": "", "csrf_token": t},
                  follow_redirects=False)


def test_asset_create_keeps_leading_zeros_and_issues_token(admin_client):
    no = "9999000001"
    r = create_asset(admin_client, no)
    assert r.status_code == 303
    with Session(get_engine()) as s:
        a = s.get(Asset, no)
        assert a.asset_no == no and len(a.tag_token) == 12 and a.is_active
        assert no not in a.tag_token
    page = admin_client.get(f"/admin/assets/{no}").text
    url = re.search(r"<code[^>]*>(https?://[^<]+)</code>", page).group(1)
    # URLのコピーボタン（コピー対象は、URLを表示している要素）
    assert 'id="tag-url"' in page and 'data-copy-target="tag-url"' in page and "/static/copy.js" in page
    assert admin_client.get("/static/copy.js").status_code == 200
    assert url.endswith("/i/" + a.tag_token) and no not in url  # URLに管理番号は含まれない


def test_asset_validation_and_duplicate(admin_client):
    no = new_asset_no()
    assert create_asset(admin_client, no).status_code == 303
    assert create_asset(admin_client, no).status_code == 400  # 重複
    # 半角英数字の1〜20文字だけが有効。ハイフン・空白・全角・日本語・21文字は不可
    for bad in ["", "AB-12", "AB 12", "ＡＢ１２", "１２３４５６７８９０", "あいう", "A" * 21]:
        assert create_asset(admin_client, bad).status_code == 400
    assert create_asset(admin_client, new_asset_no(), name="").status_code == 400


def test_asset_no_accepts_alphanumeric_1_to_20_chars(admin_client):
    for ok in ["9999A", "9999ab12CD", "9999" + "z" * 16]:  # 5文字、10文字、20文字
        assert create_asset(admin_client, ok).status_code == 303, ok
    with Session(get_engine()) as s:
        assert s.get(Asset, "9999ab12CD").asset_no == "9999ab12CD"  # 入力どおりに保存・表示する


def test_asset_no_is_case_insensitive(admin_client):
    no = "9999Ab" + "".join(random.choices("xyz", k=4))
    assert create_asset(admin_client, no).status_code == 303
    assert create_asset(admin_client, no.upper()).status_code == 400  # 大文字違いは、重複
    assert create_asset(admin_client, no.lower()).status_code == 400
    # 大文字・小文字を変えたURLでも、同じ備品が開ける
    assert admin_client.get(f"/admin/assets/{no.lower()}").status_code == 200
    assert admin_client.get(f"/assets/{no.upper()}").status_code == 200
    assert no in admin_client.get(f"/assets?q={no.lower()}").text


def test_asset_update_name_and_note(admin_client):
    no = new_asset_no()
    create_asset(admin_client, no, name="変更前")
    t = token(admin_client, f"/admin/assets/{no}")
    r = admin_client.post(f"/admin/assets/{no}", data={"name": "変更後", "note": "備考です", "csrf_token": t}, follow_redirects=False)
    assert r.status_code == 303
    with Session(get_engine()) as s:
        a = s.get(Asset, no)
        assert (a.name, a.note) == ("変更後", "備考です")
    bad = admin_client.post(f"/admin/assets/{no}", data={"name": "", "note": "", "csrf_token": t})
    assert bad.status_code == 400


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


def test_asset_pages_are_admin_only(client, make_user):  # noqa: F811
    login(client, make_user("user"))
    r = client.get("/admin/assets", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"


def test_floor_plans_and_categories_are_removed(admin_client):
    """フロア図と種別の機能は、なくなっている（ページも、画面の項目も、ナビゲーションも）。"""
    for path in ["/admin/floors", "/admin/categories", "/floors/1/image"]:
        assert admin_client.get(path, follow_redirects=False).status_code == 404, path
    no = new_asset_no()
    create_asset(admin_client, no)
    for page in (admin_client.get("/admin/assets").text, admin_client.get(f"/admin/assets/{no}").text,
                 admin_client.get("/assets").text, admin_client.get(f"/assets/{no}").text):
        assert "種別" not in page and "category" not in page
        assert "フロア図" not in page and "/admin/floors" not in page
    assert "建物の外" not in admin_client.get("/attention").text  # フロア図が前提の判定も、なくなっている
