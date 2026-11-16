"""レーダーの計算（static/radar_math.js）を Node.js で検証する。"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js が必要です")
JS = Path(__file__).resolve().parent.parent / "app" / "static" / "radar_math.js"


def run_js(expr: str):
    script = f"const M = require({json.dumps(str(JS))}); console.log(JSON.stringify({expr}));"
    # Windows の既定の文字コード（cp932）ではなく、Node.js の出力のUTF-8で読む
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", check=True, timeout=30)
    return json.loads(out.stdout)


def test_known_values():
    assert run_js("M.distanceM(36,139,36,139.001)") == pytest.approx(90, abs=1)  # 経度0.001度は約90m
    assert run_js("M.bearingDeg(36,139,36.001,139)") == pytest.approx(0, abs=0.01)  # 真北
    assert run_js("M.bearingDeg(36,139,36,139.001)") == pytest.approx(90, abs=0.1)  # 東
    assert run_js("M.bearingDeg(36,139,35.999,139)") == pytest.approx(180, abs=0.01)  # 南
    assert run_js("M.bearingDeg(36,139,36,138.999)") == pytest.approx(270, abs=0.1)  # 西


def test_names_and_formatting():
    assert run_js("[M.compassName(0), M.compassName(45), M.compassName(90), M.compassName(359), M.compassName(200)]") == ["北", "北東", "東", "北", "南"]
    assert run_js("[M.relativeName(0), M.relativeName(90), M.relativeName(180), M.relativeName(270), M.relativeName(-90)]") == ["前", "右", "後ろ", "左", "左"]
    assert run_js("[M.formatDistance(42.4), M.formatDistance(999), M.formatDistance(1500)]") == ["約42m", "約999m", "約1.5km"]
    assert run_js("M.combinedAccuracy(15, 20)") == pytest.approx(25)


def test_scale_keeps_target_inside():
    assert run_js("[M.scaleFor(5), M.scaleFor(50), M.scaleFor(90), M.scaleFor(99999)]") == [10, 100, 200, 10000]


def test_judge_states():
    me = "{lat:36,lon:139,accuracy:16}"
    unknown = run_js(f"M.judge({me}, {{lat:null,lon:null,accuracy:null}})")
    assert unknown["state"] == "unknown"
    near = run_js(f"M.judge({me}, {{lat:36.0001,lon:139,accuracy:17}})")  # 約11m、誤差は約23m
    assert near["state"] == "within"
    far = run_js(f"M.judge({me}, {{lat:36,lon:139.002,accuracy:17}})")  # 約180m
    assert far["state"] == "ok" and far["bearing"] == pytest.approx(90, abs=0.1)
