import random
import re

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Asset
from app.services.qr import QUIET_ZONE_MODULES, label_qr, make_qr, qr_svg_file
from tests.test_auth import client, login, make_user, token  # noqa: F401（フィクスチャを再利用）


@pytest.fixture()
def admin(client, make_user):  # noqa: F811
    login(client, make_user("admin"))
    yield client
    with Session(get_engine()) as s:
        s.execute(delete(Asset).where(Asset.asset_no.like("9995%")))
        s.commit()


def add_asset(no=None, name="ラベル用ノートPC", **kw):
    no = no or "9995" + f"{random.randint(0, 999999):06d}"
    token_ = "L" + f"{random.randint(0, 10**11 - 1):011d}"
    with Session(get_engine()) as s:
        s.add(Asset(asset_no=no, name=name, tag_token=token_, **kw))
        s.commit()
    return no, token_


def print_labels(c, nos, size="30", show_name="1"):
    data = {"nos": nos, "size_mm": size, "csrf_token": token(c, "/admin/labels")}
    if show_name:
        data["show_name"] = show_name
    return c.post("/admin/labels/print", data=data)


# ---- QRの生成（純粋な計算）----
URL = "https://example.azurewebsites.net/i/AbCdEf123456"


def test_label_size_includes_quiet_zone():
    q = label_qr(URL, 30)
    assert q.modules >= 21 and "<svg" in q.svg
    # QR本体が30mmなら、周囲に4マスずつの余白が付き、全体は30mmより大きい
    assert q.total_mm == pytest.approx(30 * (q.modules + 2 * QUIET_ZONE_MODULES) / q.modules, abs=0.01)
    assert q.total_mm > 30


def test_label_svg_scales_with_css():
    """SVGが viewBox を持ち、固定の width/height を持たないこと（持つと、CSSの大きさ指定でQRが拡大縮小されない）。"""
    svg = label_qr(URL, 30).svg
    head = re.match(r"<svg[^>]*>", svg).group(0)
    assert "viewBox=" in head and "width=" not in head and "height=" not in head


def test_each_module_is_at_least_half_a_millimeter_at_recommended_size():
    long_url = "https://rs-mobi-tana-d0b6edb0c2f8a2hf.japanwest-01.azurewebsites.net/i/AbCdEf123456"
    q = label_qr(long_url, 30)
    assert 30 / q.modules >= 0.5  # 現在のURLでも、30mmなら1マス0.5mm以上（読み取りの目安）


def decode_png(url: str, scale: int = 8) -> str:
    """QRを画像にして、実際に読み取る（スマホのカメラと同じ手順の確認）。"""
    import io

    zxingcpp = pytest.importorskip("zxingcpp")
    from PIL import Image

    buf = io.BytesIO()
    make_qr(url).save(buf, kind="png", scale=scale, border=QUIET_ZONE_MODULES)
    results = zxingcpp.read_barcodes(Image.open(io.BytesIO(buf.getvalue())))
    assert len(results) == 1
    return results[0].text


def test_qr_can_actually_be_read_back():
    assert decode_png(URL) == URL
    # 現在のホスト名（約83文字）でも、読み取れる
    long_url = "https://rs-mobi-tana-d0b6edb0c2f8a2hf.japanwest-01.azurewebsites.net/i/AbCdEf123456"
    assert decode_png(long_url) == long_url
    # 印刷では1マスが約0.5mm（300dpiで約6ドット）。小さく印刷した場合の目安として、1マス6ピクセルでも読める
    assert decode_png(long_url, scale=6) == long_url


def test_qr_svg_file_is_valid():
    assert qr_svg_file(URL).startswith(b"<?xml")


# ---- 画面 ----
def test_single_qr_endpoint_matches_the_tag_url(admin):
    no, tok = add_asset()
    r = admin.get(f"/admin/assets/{no}/qr.svg")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml")
    # テストクライアントのホストは testserver。そのURLを符号化したQRと、完全に一致する
    assert r.content == qr_svg_file(f"https://testserver/i/{tok}")
    assert no.encode() not in r.content  # 管理番号は、QRの中身に含まれない
    page = admin.get(f"/admin/assets/{no}").text
    assert f"/admin/assets/{no}/qr.svg" in page


def test_label_page_lists_assets_and_sizes(admin):
    no, _ = add_asset()
    page = admin.get("/admin/labels").text
    assert no in page and "20mm" in page and "30mm（推奨）" in page and "50mm" in page


def test_print_page_contains_qr_and_asset_number(admin):
    a, ta = add_asset(name="印刷対象A")
    b, _ = add_asset(name="印刷対象B")
    c, _ = add_asset(name="選ばない備品")
    r = print_labels(admin, [a, b])
    assert r.status_code == 200
    html = r.text
    assert a in html and b in html and c not in html  # 選んだものだけ
    assert html.count('class="label"') == 2 and html.count("<svg") == 2
    assert "印刷対象A" in html and "選ばない備品" not in html
    assert "@page { size: A4" in html


def test_name_is_not_printed_by_default(admin):
    """名称の印刷は、初期状態ではオフ（チェックを入れたときだけ印刷する）。"""
    page = admin.get("/admin/labels").text
    box = re.search(r'<input type="checkbox" name="show_name"[^>]*>', page).group(0)
    assert "checked" not in box
    a, _ = add_asset(name="既定では印刷されない名称")
    # チェックなし（フォームの既定のまま送信）：QRと管理番号だけ
    data = {"nos": [a], "size_mm": "30", "cut": "grid", "csrf_token": token(admin, "/admin/labels")}
    html = admin.post("/admin/labels/print", data=data).text
    assert a in html and "既定では印刷されない名称" not in html and html.count("<svg") == 1


def test_print_page_without_names(admin):
    a, _ = add_asset(name="名称は印刷しない")
    html = print_labels(admin, [a], show_name="").text
    assert a in html and "名称は印刷しない" not in html


def test_print_page_size_changes_the_label_width(admin):
    a, _ = add_asset()
    w = {}
    for size in ("20", "50"):
        html = print_labels(admin, [a], size=size).text
        w[size] = float(re.search(r"repeat\(\d+, ([0-9.]+)mm\)", html).group(1))  # 1枚分の幅（余白込み）
    assert w["20"] < w["50"]
    assert w["50"] > 50  # 余白の分だけ、本体より大きい


def print_with_cut(c, nos, cut):
    data = {"nos": nos, "size_mm": "30", "show_name": "1", "cut": cut, "csrf_token": token(c, "/admin/labels")}
    return c.post("/admin/labels/print", data=data)


def test_cut_lines_modes(admin):
    nos = [add_asset()[0] for _ in range(5)]
    grid = print_with_cut(admin, nos, "grid").text
    # 裁断用：隙間なしの格子に、行・列を貫く点線（外枠の上と左、各ラベルの右と下）
    assert "display: grid" in grid and "border-right: 0.2mm dashed" in grid and "border-bottom: 0.2mm dashed" in grid
    assert "border-top: 0.2mm dashed" in grid and "gap: 3mm" not in grid
    cols = int(re.search(r"repeat\((\d+),", grid).group(1))
    cell = float(re.search(r"repeat\(\d+, ([0-9.]+)mm\)", grid).group(1))
    assert cols * cell <= 190 and (cols + 1) * cell > 190  # 用紙の幅（190mm）に入る最大の列数
    box = print_with_cut(admin, nos, "box").text
    assert "border: 0.2mm dashed" in box and "display: grid" not in box
    none = print_with_cut(admin, nos, "none").text
    assert "dashed" not in none
    assert print_with_cut(admin, nos, "wavy").status_code == 400  # 不正な指定


def test_cut_grid_cells_have_the_same_size_even_with_different_names(admin):
    short, _ = add_asset(name="短い")
    long_, _ = add_asset(name="とても長い名称のノートパソコン（会議室の貸出用、予備機、2024年度購入、保証あり）")
    html = print_with_cut(admin, [short, long_], "grid").text
    assert len(set(re.findall(r"grid-auto-rows: ([0-9.]+)mm", html))) == 1  # 行の高さが固定（点線が、そろう）


def test_print_excludes_disposed_and_validates_input(admin):
    a, _ = add_asset()
    gone, _ = add_asset(is_active=False)
    html = print_labels(admin, [a, gone]).text
    assert a in html and gone not in html
    assert print_labels(admin, [a], size="33").status_code == 400  # 選択肢にない大きさ
    assert print_labels(admin, []).status_code == 400  # 1つも選んでいない
    bad = admin.post("/admin/labels/print", data={"nos": [a], "size_mm": "30", "csrf_token": "wrong"})
    assert bad.status_code == 400


def test_label_pages_are_admin_only(client, make_user):  # noqa: F811
    login(client, make_user("user"))
    for path in ["/admin/labels", "/admin/assets/0000000000/qr.svg"]:
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/"
