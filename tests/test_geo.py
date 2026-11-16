import os

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.skipif(not os.environ.get("DB_NAME"), reason="DB未設定（.envを作成）")


def test_geo_save_and_list():
    with TestClient(app) as client:  # startupでテーブルを作成
        res = client.post("/test/geo", json={
            "label": "pytest", "latitude": 35.0, "longitude": 139.0, "accuracy_m": 12.5, "altitude": None,
        })
        assert res.status_code == 200
        page = client.get("/test/geo?id=pytest")
        assert page.status_code == 200
        assert "pytest" in page.text


def test_geo_rejects_bad_latitude():
    with TestClient(app) as client:
        res = client.post("/test/geo", json={"latitude": 999, "longitude": 0})
        assert res.status_code == 422
