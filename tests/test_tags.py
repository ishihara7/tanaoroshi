import random
import re

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Asset, Scan
from tests.test_auth import client, login, make_user  # noqa: F401（フィクスチャを再利用）


@pytest.fixture()
def asset():
    """テスト用の備品（管理番号は 9998 で始める）。終了時に、備品とスキャン記録を削除する。"""
    no = "9998" + f"{random.randint(0, 999999):06d}"
    token = "T" + f"{random.randint(0, 10**11 - 1):011d}"
    with Session(get_engine()) as s:
        s.add(Asset(asset_no=no, name="会議室のノートPC", tag_token=token))
        s.commit()
    yield {"no": no, "token": token}
    with Session(get_engine()) as s:
        s.execute(delete(Scan).where(Scan.asset_no.like("9998%")))
        s.execute(delete(Asset).where(Asset.asset_no.like("9998%")))
        s.commit()


def csrf_of(client, path):
    return re.search(r'name="csrf" content="([^"]+)"', client.get(path).text).group(1)


def post_scan(client, token, csrf, body):
    return client.post(f"/i/{token}/scan", json=body, headers={"X-CSRF-Token": csrf})


def get_asset(no):
    with Session(get_engine()) as s:
        return s.get(Asset, no)


def count_scans(no):
    with Session(get_engine()) as s:
        return len(s.scalars(select(Scan).where(Scan.asset_no == no)).all())


def test_tag_page_requires_login_and_returns_after_login(client, make_user, asset):  # noqa: F811
    path = f"/i/{asset['token']}"
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login?next=")
    uid = make_user()
    r = login(client, uid, next_=path)
    assert r.headers["location"] == path  # ログイン後に、元のタグのURLへ戻る
    page = client.get(path)
    assert page.status_code == 200 and "会議室のノートPC" in page.text


def test_unknown_or_disposed_tag_is_404_after_login(client, make_user, asset):  # noqa: F811
    login(client, make_user())
    assert client.get("/i/no-such-token").status_code == 404
    with Session(get_engine()) as s:
        s.get(Asset, asset["no"]).is_active = False
        s.commit()
    assert client.get(f"/i/{asset['token']}").status_code == 404


def test_scan_records_position_and_updates_asset(client, make_user, asset):  # noqa: F811
    login(client, make_user())
    csrf = csrf_of(client, f"/i/{asset['token']}")
    r = post_scan(client, asset["token"], csrf, {"latitude": 36.29258, "longitude": 139.37613, "accuracy_m": 17, "altitude": 46})
    assert r.status_code == 200 and r.json() == {"ok": True, "deduped": False, "position": True}
    a = get_asset(asset["no"])
    assert (a.current_lat, a.current_lon, a.current_accuracy_m) == (36.29258, 139.37613, 17)
    assert a.last_seen_at is not None and count_scans(asset["no"]) == 1


def test_scan_without_position_updates_only_last_seen(client, make_user, asset):  # noqa: F811
    login(client, make_user())
    csrf = csrf_of(client, f"/i/{asset['token']}")
    r = post_scan(client, asset["token"], csrf, {"error_message": "コード1：許可されていません"})
    assert r.json()["position"] is False
    a = get_asset(asset["no"])
    assert a.current_lat is None and a.last_seen_at is not None
    with Session(get_engine()) as s:
        scan = s.scalar(select(Scan).where(Scan.asset_no == asset["no"]))
        assert scan.latitude is None and "許可されていません" in scan.error_message


def test_failed_position_does_not_overwrite_previous_position(client, make_user, asset):  # noqa: F811
    login(client, make_user())
    csrf = csrf_of(client, f"/i/{asset['token']}")
    post_scan(client, asset["token"], csrf, {"latitude": 36.0, "longitude": 139.0, "accuracy_m": 10})
    with Session(get_engine()) as s:  # 連続読み込みのまとめ処理を避けるため、直前の記録を過去にする
        from datetime import timedelta
        from app.models import utcnow
        for sc in s.scalars(select(Scan).where(Scan.asset_no == asset["no"])):
            sc.created_at = utcnow() - timedelta(minutes=5)
        s.commit()
    post_scan(client, asset["token"], csrf, {"error_message": "時間切れ"})
    a = get_asset(asset["no"])
    assert (a.current_lat, a.current_lon) == (36.0, 139.0)  # 前回の位置が残る
    assert count_scans(asset["no"]) == 2


def test_repeated_scan_within_seconds_is_deduped(client, make_user, asset):  # noqa: F811
    login(client, make_user())
    csrf = csrf_of(client, f"/i/{asset['token']}")
    post_scan(client, asset["token"], csrf, {"latitude": 36.0, "longitude": 139.0})
    r = post_scan(client, asset["token"], csrf, {"latitude": 36.0, "longitude": 139.0})
    assert r.json()["deduped"] is True and count_scans(asset["no"]) == 1


def test_scan_rejects_bad_csrf_and_bad_values(client, make_user, asset):  # noqa: F811
    login(client, make_user())
    csrf = csrf_of(client, f"/i/{asset['token']}")
    assert post_scan(client, asset["token"], "wrong", {"latitude": 36.0, "longitude": 139.0}).status_code == 403
    assert post_scan(client, asset["token"], csrf, {"latitude": 999, "longitude": 139.0}).status_code == 422
    assert post_scan(client, asset["token"], csrf, {"latitude": 36.0, "longitude": 139.0, "accuracy_m": -1}).status_code == 422
    assert count_scans(asset["no"]) == 0


def test_scan_requires_login(client, asset):  # noqa: F811
    r = client.post(f"/i/{asset['token']}/scan", json={"latitude": 36.0, "longitude": 139.0}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")
