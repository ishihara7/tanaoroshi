"""タグのページの自動記録の判定（static/tag_logic.js）を Node.js で検証する。"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js が必要です")
JS = Path(__file__).resolve().parent.parent / "app" / "static" / "tag_logic.js"


def auto(nav_type: str) -> bool:
    script = f"const T = require({json.dumps(str(JS))}); console.log(JSON.stringify(T.shouldAutoRecord({json.dumps(nav_type)})));"
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", check=True, timeout=30)
    return json.loads(out.stdout)


def test_only_a_fresh_navigation_records_automatically():
    assert auto("navigate") is True  # タグにタッチして開いた
    for t in ["reload", "back_forward", "prerender", "", "unknown"]:
        assert auto(t) is False, t  # 再読み込み・戻る・タブの復元などでは、記録しない
