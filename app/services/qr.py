"""QRコードの生成（印刷用のラベルと、備品の編集画面で使う）。

QRに入れるのは、管理番号ではなく、タグ用のURL（/i/{トークン}）。NFCタグに書き込むURLと同じ。
"""
import io
from dataclasses import dataclass

import segno

QUIET_ZONE_MODULES = 4  # QRの周囲に必要な白い余白（4マス分）。足りないと、読み取れない
ERROR_LEVEL = "m"  # 誤り訂正 M（約15%まで復元）


@dataclass(frozen=True)
class LabelQr:
    svg: str  # HTMLに埋め込めるSVG（大きさはCSSで指定する）
    modules: int  # QR本体の1辺のマス数
    total_mm: float  # 余白を含めた1辺の長さ（mm）


def make_qr(url: str) -> segno.QRCode:
    return segno.make(url, error=ERROR_LEVEL, micro=False)


def label_qr(url: str, body_mm: float) -> LabelQr:
    """QR本体の1辺が body_mm（mm）になるQRを作る。余白は、その外側に付く。"""
    qr = make_qr(url)
    modules = qr.symbol_size(border=0)[0]
    module_mm = body_mm / modules
    # omitsize：固定の width/height を付けず、viewBox だけにする（CSSで指定した大きさに、QR全体が拡大縮小される）
    svg = qr.svg_inline(border=QUIET_ZONE_MODULES, scale=1, dark="#000", light="#fff", omitsize=True)
    return LabelQr(svg=svg, modules=modules, total_mm=round((modules + 2 * QUIET_ZONE_MODULES) * module_mm, 2))


def qr_svg_file(url: str) -> bytes:
    """単体のSVGファイル（保存・他のソフトでの利用向け）。"""
    buf = io.BytesIO()
    make_qr(url).save(buf, kind="svg", scale=10, border=QUIET_ZONE_MODULES)
    return buf.getvalue()
