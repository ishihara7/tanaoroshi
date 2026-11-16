"""GPS座標とフロア図上の位置の変換。

フロア図は「北が上」の画像として扱い、左上と右下の緯度経度を基準にする（線形に対応づける）。
フロアの広さ（数百m以内）では、この近似で十分。
"""
from dataclasses import dataclass

from app.models import Floor


@dataclass(frozen=True)
class MapPosition:
    x_ratio: float  # 0〜1（左が0）
    y_ratio: float  # 0〜1（上が0）
    inside: bool  # 図の範囲内（余白を含む）か


def to_map_position(floor: Floor, lat: float, lon: float, margin: float = 0.1) -> MapPosition | None:
    """緯度経度を、図上の割合（0〜1）に変換する。位置合わせ未登録なら None。

    margin：図の範囲の外側に許す余白（図の幅・高さに対する割合）。範囲外なら inside=False（建物外の可能性）。
    """
    if not floor.is_aligned:
        return None
    dlon = floor.br_lon - floor.tl_lon
    dlat = floor.tl_lat - floor.br_lat
    if dlon == 0 or dlat == 0:
        return None
    x = (lon - floor.tl_lon) / dlon
    y = (floor.tl_lat - lat) / dlat
    inside = -margin <= x <= 1 + margin and -margin <= y <= 1 + margin
    return MapPosition(x_ratio=x, y_ratio=y, inside=inside)


def accuracy_in_ratio(floor: Floor, accuracy_m: float, lat: float) -> tuple[float, float] | None:
    """誤差（m）を、図上の割合（横・縦）に変換する。誤差の円を描くのに使う。"""
    if not floor.is_aligned:
        return None
    import math

    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat))
    width_m = abs(floor.br_lon - floor.tl_lon) * m_per_deg_lon
    height_m = abs(floor.tl_lat - floor.br_lat) * m_per_deg_lat
    if width_m == 0 or height_m == 0:
        return None
    return accuracy_m / width_m, accuracy_m / height_m


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """2点間の距離（m）。"""
    import math

    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """1点目から2点目への方位（度）。北が0、時計回り。"""
    import math

    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360
