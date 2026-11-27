"""座標合わせの試作用に、ダミーの3DGS（.ply）を作る。実際の撮影データがなくても、画面を試せる。

部屋（東西12m × 南北8m）に、床・壁・棚・柱を置く。柱は、フロア図の (0,0) (10,0) (10,6) (0,6) に立つ（色つき）。
実際のモデルと同じく、縮尺・向き・位置は、でたらめにずらしてある（Y軸が上）。

使い方：python tools/make_dummy_ply.py [出力先]   既定は var/models/dummy_floor.ply
管理画面の「3Dモデル」から、このファイルを、階を選んでアップロードする。
アンカーを、フロア図の上の4つの柱の位置に登録すると、座標合わせを試せる。
"""
import math
import random
import struct
import sys
from pathlib import Path

SCALE = 0.37          # フロア図の1m → モデルの0.37
ROT_DEG = 53.0        # モデルの向き（Y軸まわり）
OFFSET = (2.5, 0.8, -4.0)  # モデルの原点のずれ


def to_model(x: float, y: float, h: float):
    """フロア図の (x東, y北, 高さh) → モデルの座標（Y軸が上）。"""
    ux, uz = x * SCALE, -y * SCALE  # 北が -Z
    c, s = math.cos(math.radians(ROT_DEG)), math.sin(math.radians(ROT_DEG))
    return (c * ux - s * uz + OFFSET[0], h * SCALE + OFFSET[1], s * ux + c * uz + OFFSET[2])


def rgb_to_dc(v: float) -> float:
    return (v - 0.5) / 0.28209479177387814


def main():
    rnd = random.Random(7)
    pts = []  # (x, y, h, (r, g, b), size_m)

    def add(x, y, h, col, size=0.07):
        j = lambda: rnd.uniform(-0.01, 0.01)
        pts.append((x + j(), y + j(), h + j(), col, size))

    W, D, H = 12.0, 8.0, 2.6
    # 床（市松模様）
    for i in range(0, int(W / 0.1) + 1):
        for k in range(0, int(D / 0.1) + 1):
            x, y = i * 0.1 - 0.0, k * 0.1
            on = (int(x) + int(y)) % 2 == 0
            add(x - 1.0, y - 1.0, 0.0, (0.72, 0.72, 0.74) if on else (0.55, 0.57, 0.62), 0.07)
    # 壁（南・西・北）
    for t in [i * 0.12 for i in range(int(W / 0.12) + 1)]:
        for h in [k * 0.12 for k in range(int(H / 0.12) + 1)]:
            add(t - 1.0, -1.0, h, (0.93, 0.92, 0.88), 0.09)
            add(t - 1.0, D - 1.0, h, (0.9, 0.92, 0.95), 0.09)
    for t in [i * 0.12 for i in range(int(D / 0.12) + 1)]:
        for h in [k * 0.12 for k in range(int(H / 0.12) + 1)]:
            add(-1.0, t - 1.0, h, (0.95, 0.9, 0.9), 0.09)
    # 棚（箱）
    def box(x0, y0, x1, y1, h1, col):
        for _ in range(int((x1 - x0) * (y1 - y0) * 700) + 400):
            add(rnd.uniform(x0, x1), rnd.uniform(y0, y1), h1, col, 0.06)
        for _ in range(int(((x1 - x0) + (y1 - y0)) * h1 * 500)):
            e = rnd.choice([0, 1, 2, 3])
            x = rnd.uniform(x0, x1) if e < 2 else (x0 if e == 2 else x1)
            y = (y0 if e == 0 else y1) if e < 2 else rnd.uniform(y0, y1)
            add(x, y, rnd.uniform(0, h1), tuple(c * 0.85 for c in col), 0.06)
    box(2.0, 1.5, 4.5, 2.2, 1.8, (0.55, 0.38, 0.22))
    box(2.0, 4.2, 4.5, 4.9, 1.8, (0.55, 0.38, 0.22))
    box(7.0, 2.8, 8.0, 3.4, 0.75, (0.35, 0.45, 0.6))
    # 角の柱（基準点）
    for (x, y), col in zip([(0, 0), (10, 0), (10, 6), (0, 6)],
                           [(1, 0.2, 0.2), (0.2, 0.75, 0.3), (0.2, 0.4, 1), (1, 0.8, 0.1)]):
        for _ in range(500):
            a, r = rnd.uniform(0, math.tau), rnd.uniform(0, 0.12)
            add(x + r * math.cos(a), y + r * math.sin(a), rnd.uniform(0, 1.6), col, 0.05)

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "var" / "models" / "dummy_floor.ply"
    out.parent.mkdir(parents=True, exist_ok=True)
    qw, qx, qy, qz = 1.0, 0.0, 0.0, 0.0  # 回転は単位（球は、向きがなくてよい）
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        f"element vertex {len(pts)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property float nx\nproperty float ny\nproperty float nz\n"
        "property float f_dc_0\nproperty float f_dc_1\nproperty float f_dc_2\n"
        "property float opacity\n"
        "property float scale_0\nproperty float scale_1\nproperty float scale_2\n"
        "property float rot_0\nproperty float rot_1\nproperty float rot_2\nproperty float rot_3\n"
        "end_header\n"
    )
    with out.open("wb") as f:
        f.write(header.encode("ascii"))
        for x, y, h, col, size in pts:
            mx, my, mz = to_model(x, y, h)
            ls = math.log(size * SCALE)  # スケールは対数
            f.write(struct.pack("<17f", mx, my, mz, 0, 0, 0, *(rgb_to_dc(c) for c in col),
                                4.0,  # 不透明度（ロジット。ほぼ不透明）
                                ls, ls, ls, qw, qx, qy, qz))
    print(f"{out}  ガウス {len(pts)} 個 / {out.stat().st_size / 1e6:.1f} MB")
    print(f"本当の変換：縮尺 1m = {SCALE}、回転 {ROT_DEG}度、柱の位置（フロア図）(0,0) (10,0) (10,6) (0,6)")


if __name__ == "__main__":
    main()
