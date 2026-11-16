"""タグ画面（tag.js）の、社員番号の入力と記録のタイミングを、ブラウザを模した環境（Node.js）で確かめる。"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js が必要です")
HARNESS = Path(__file__).resolve().parent / "js" / "tag_flow_harness.js"


def run(scenario: str) -> dict:
    out = subprocess.run(["node", str(HARNESS), scenario], capture_output=True, text=True, encoding="utf-8", check=True, timeout=30)
    return json.loads(out.stdout)


def test_remembered_employee_no_is_sent_automatically_when_position_is_ready():
    r = run("remembered")
    assert len(r["calls"]) == 1
    body = r["calls"][0]["body"]
    assert body["employee_no"] == "E1001" and body["latitude"] == 36.29 and body["accuracy_m"] == 8
    assert r["calls"][0]["url"] == "/i/TOKEN123/scan"
    assert r["stages"][0]["status"] == "status is-ok"  # 記録できた（緑）
    assert r["stored"] == "E1001"


def test_without_a_remembered_number_it_waits_for_input_and_the_button():
    r = run("not_remembered")
    first, typed, pressed = r["stages"]
    assert first["calls"] == 0 and first["status"] == "status is-wait" and first["buttonDisabled"] is True  # 位置は取れたが、入力待ち
    assert typed["calls"] == 0 and typed["buttonDisabled"] is False  # 入力の途中で、勝手に送信しない
    assert pressed["calls"] == 1 and pressed["status"] == "status is-ok"
    assert r["calls"][0]["body"]["employee_no"] == "E77"
    assert r["stored"] == "E77"  # 次回から、自動で入る


def test_typing_while_the_position_is_being_found_does_not_send_by_itself():
    """記憶がなく、位置を調べている最中に番号を打ち始めても、位置が取れた時点で、勝手に送信しない（入力の途中かもしれない）。"""
    r = run("typed_early")
    after_position, pressed = r["stages"]
    assert after_position["calls"] == 0 and after_position["status"] == "status is-wait"
    assert after_position["buttonDisabled"] is False  # 入力済みなので、押せる
    assert pressed["calls"] == 1 and r["calls"][0]["body"]["employee_no"] == "E7"


def test_invalid_employee_no_is_never_sent():
    r = run("invalid_number")
    assert r["calls"] == [] and r["stages"][-1]["buttonDisabled"] is True
    assert r["stored"] == ""


def test_reload_does_not_record_automatically():
    r = run("reload")
    assert r["calls"] == []
    assert "再読み込みのため、記録していません" in r["stages"][0]["text"]
