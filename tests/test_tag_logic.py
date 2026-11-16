"""タグのページの判定ロジック（static/tag_logic.js）を Node.js で検証する。"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js が必要です")
JS = Path(__file__).resolve().parent.parent / "app" / "static" / "tag_logic.js"


def run_js(expr: str):
    script = f"const T = require({json.dumps(str(JS))}); console.log(JSON.stringify({expr}));"
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", check=True, timeout=30)
    return json.loads(out.stdout)


def test_only_a_fresh_navigation_records_automatically():
    assert run_js('T.shouldAutoRecord("navigate")') is True  # タグにタッチして開いた
    for t in ["reload", "back_forward", "prerender", "", "unknown"]:
        assert run_js(f"T.shouldAutoRecord({json.dumps(t)})") is False, t  # 再読み込み・戻る・タブの復元は記録しない


def test_pick_best_chooses_smallest_accuracy_and_latest_on_tie():
    fixes = "[{lat:1,lon:1,accuracy:65},{lat:2,lon:2,accuracy:16},{lat:3,lon:3,accuracy:30}]"
    assert run_js(f"T.pickBest({fixes})")["lat"] == 2  # 誤差が一番小さい
    tie = "[{lat:1,lon:1,accuracy:16},{lat:2,lon:2,accuracy:16}]"
    assert run_js(f"T.pickBest({tie})")["lat"] == 2  # 同じなら、新しい方
    assert run_js("T.pickBest([])") is None
    assert run_js("T.pickBest([{lat:1,lon:1,accuracy:null},null])") is None  # 誤差が不明なものは使わない


def test_decide_stops_when_accurate_or_time_is_up():
    good = "{lat:1,lon:1,accuracy:8}"
    coarse = "{lat:1,lon:1,accuracy:40}"
    assert run_js(f"T.decide({good}, 1000)") == "finish"  # 誤差10m以下なら、すぐ終える
    assert run_js(f"T.decide({coarse}, 3000)") == "continue"  # 粗いうちは待つ
    assert run_js(f"T.decide({coarse}, 8000)") == "finish"  # 8秒たったら、取れた最良で終える
    assert run_js("T.decide(null, 8000)") == "continue"  # 1件も取れないうちは、待つ
    assert run_js("T.decide(null, 20000)") == "giveup"  # 20秒で、あきらめる


def test_constants():
    assert run_js("[T.TARGET_ACCURACY_M, T.MAX_WAIT_MS, T.HARD_TIMEOUT_MS]") == [10, 8000, 20000]
