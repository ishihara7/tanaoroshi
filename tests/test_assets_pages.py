import json
import random
import re
from datetime import timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Asset, Floor, Scan, User, utcnow
from tests.test_auth import client, login, make_user  # noqa: F401（フィクスチャを再利用）

FLOOR_BUILDING = "テスト棟_attention"


@pytest.fixture()
def cleanup():
    yield
    with Session(get_engine()) as s:
        s.execute(delete(Scan).where(Scan.asset_no.like("9997%")))
        s.execute(delete(Asset).where(Asset.asset_no.like("9997%")))
        s.execute(delete(Floor).where(Floor.building == FLOOR_BUILDING))
        s.commit()


def add_asset(name="レーダー用ノートPC", **kw):
    no = "9997" + f"{random.randint(0, 999999):06d}"
    with Session(get_engine()) as s:
        s.add(Asset(asset_no=no, name=name, tag_token="R" + f"{random.randint(0, 10**11 - 1):011d}", **kw))
        s.commit()
    return no


def test_search_by_name_and_number_hides_disposed(client, make_user, cleanup):  # noqa: F811
    login(client, make_user())
    no = add_asset("検索テスト用モニター")
    gone = add_asset("検索テスト用の廃棄品", is_active=False)
    assert no in client.get("/assets?q=検索テスト用モニター").text
    assert no in client.get(f"/assets?q={no[-6:]}").text
    page = client.get("/assets?q=検索テスト用").text
    assert no in page and gone not in page


def test_search_requires_login(client):  # noqa: F811
    r = client.get("/assets", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")


def test_detail_shows_history_with_display_name(client, make_user, cleanup):  # noqa: F811
    uid = make_user()
    login(client, uid)
    no = add_asset(last_seen_at=utcnow(), current_lat=36.0, current_lon=139.0, current_accuracy_m=17)
    with Session(get_engine()) as s:
        user_id = s.scalar(select(User.id).where(User.login_id == uid))
        s.add(Scan(asset_no=no, user_id=user_id, latitude=36.0, longitude=139.0, accuracy_m=17))
        s.commit()
    page = client.get(f"/assets/{no}").text
    assert "テスト太郎" in page and "約17m" in page and f"/assets/{no}/radar" in page


def test_detail_of_disposed_asset_is_hidden_from_users(client, make_user, cleanup):  # noqa: F811
    login(client, make_user("user"))
    no = add_asset(is_active=False)
    r = client.get(f"/assets/{no}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/assets"


def test_radar_page_embeds_position_only_as_numbers(client, make_user, cleanup):  # noqa: F811
    login(client, make_user())
    no = add_asset("<script>alert(1)</script>のPC", current_lat=36.29258, current_lon=139.37613, current_accuracy_m=17)
    page = client.get(f"/assets/{no}/radar").text
    assert "<script>alert(1)" not in page  # 名称は無害化される
    data = json.loads(re.search(r'id="radar-data">(.*?)</script>', page, re.S).group(1))
    assert data == {"lat": 36.29258, "lon": 139.37613, "accuracy": 17}
    assert "/static/radar.js" in page


def test_radar_page_without_position(client, make_user, cleanup):  # noqa: F811
    login(client, make_user())
    no = add_asset()
    page = client.get(f"/assets/{no}/radar").text
    data = json.loads(re.search(r'id="radar-data">(.*?)</script>', page, re.S).group(1))
    assert data["lat"] is None


def test_attention_lists(client, make_user, cleanup):  # noqa: F811
    login(client, make_user())
    old = add_asset("古い備品", last_seen_at=utcnow() - timedelta(days=120), current_lat=36.0, current_lon=139.0)
    fresh = add_asset("新しい備品", last_seen_at=utcnow(), current_lat=36.0, current_lon=139.0)
    nopos = add_asset("位置なし備品", last_seen_at=utcnow())
    page = client.get("/attention").text
    stale_part = page.split("位置の記録がない備品")[0]
    assert old in stale_part and fresh not in stale_part
    assert nopos in page.split("位置の記録がない備品")[1].split("建物の外")[0]


def test_attention_outside_building_needs_aligned_floor(client, make_user, cleanup):  # noqa: F811
    login(client, make_user())
    inside = add_asset("建物内", last_seen_at=utcnow(), current_lat=36.2930, current_lon=139.3765)
    outside = add_asset("建物外", last_seen_at=utcnow(), current_lat=36.5000, current_lon=139.5000)
    with Session(get_engine()) as s:
        s.add(Floor(building=FLOOR_BUILDING, floor_label="1F", tl_lat=36.2940, tl_lon=139.3750, br_lat=36.2920, br_lon=139.3780))
        s.commit()
    part = client.get("/attention").text.split("建物の外にある可能性")[1]
    assert outside in part and inside not in part
