"""テーブル定義。"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Unicode, UnicodeText
from sqlalchemy.orm import Mapped, mapped_column

from app.crypto import EncryptedFloat
from app.db import Base


def utcnow() -> datetime:
    """UTCの現在時刻（タイムゾーンなし。DBにはUTCで保存する）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    """ログインユーザー。管理者が1人ずつ発行する。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    login_id: Mapped[str] = mapped_column(String(30), unique=True)  # 英数字のみなのでVARCHARでよい
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(10), default="user")  # admin | user
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Asset(Base):
    """備品。管理番号は既存の資産番号（半角英数字1〜20文字。大文字・小文字は区別しない）。タグのURLには、管理番号ではなく tag_token を使う。"""

    __tablename__ = "assets"

    asset_no: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(Unicode(100))
    tag_token: Mapped[str] = mapped_column(String(20), unique=True)
    note: Mapped[str] = mapped_column(Unicode(500), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # 廃棄したら False（台帳から非表示）
    # 最新の所在（記録時に更新する）
    current_lat: Mapped[float | None] = mapped_column(EncryptedFloat("assets.current_lat"), nullable=True)
    current_lon: Mapped[float | None] = mapped_column(EncryptedFloat("assets.current_lon"), nullable=True)
    current_accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Scan(Base):
    """備品タグのタッチ記録。追記のみ（更新・削除しない）。位置が取れなかったときは、位置はNULL。"""

    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_no: Mapped[str] = mapped_column(String(20), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    employee_no: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)  # 記録した人の社員番号（旧データは空）
    latitude: Mapped[float | None] = mapped_column(EncryptedFloat("scans.latitude"), nullable=True)
    longitude: Mapped[float | None] = mapped_column(EncryptedFloat("scans.longitude"), nullable=True)
    accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    altitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str] = mapped_column(Unicode(200), default="")
    user_agent: Mapped[str] = mapped_column(Unicode(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Anchor(Base):
    """屋内の位置の基準点（壁や柱に貼るNFCタグ／QR）。座標は、フロア図上のメートル（x：東、y：北）。
    アプリは、アンカーを読み取った時点で、自分の位置をこの座標に合わせる。"""

    __tablename__ = "anchors"

    anchor_token: Mapped[str] = mapped_column(String(20), primary_key=True)  # タグのURLに使う（推測されにくい文字列）
    name: Mapped[str] = mapped_column(Unicode(100))  # 例：2F 東階段前
    floor: Mapped[int] = mapped_column(Integer)  # 階（地下は負の数）
    x_m: Mapped[float] = mapped_column(Float)
    y_m: Mapped[float] = mapped_column(Float)
    z_m: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")  # QRを貼った高さ（床から、m）。高さの基準
    # QRを読むとき、利用者が向く方向（壁に正対する向き）。北を0°とした時計回り。コンパスの向きの較正に使う。未設定ならNULL
    facing_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ArItem(Base):
    """AR棚卸の「予定」の1件。備品のタグ（token）ごとに、階とフロア図上の位置を持つ。

    棚卸を終えるたびに、今回の結果で更新される（結果が、次回の予定になる）。
    """

    __tablename__ = "ar_items"

    token: Mapped[str] = mapped_column(String(40), primary_key=True)
    asset_no: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)  # 台帳にあれば、その管理番号
    name: Mapped[str] = mapped_column(Unicode(100))
    floor: Mapped[int] = mapped_column(Integer, default=1)
    x: Mapped[float] = mapped_column(Float, default=0.0)
    y: Mapped[float] = mapped_column(Float, default=0.0)
    z: Mapped[float | None] = mapped_column(Float, nullable=True)  # 床からの高さ（m）。分からなければ空
    err_m: Mapped[float] = mapped_column(Float, default=0.0)
    located: Mapped[bool] = mapped_column(Boolean, default=True)  # 位置が分かっているか（想定外を位置なしで読んだら False）
    missed_last: Mapped[bool] = mapped_column(Boolean, default=False)  # 前回の棚卸で、確かめられなかった
    was_unexpected: Mapped[bool] = mapped_column(Boolean, default=False)  # 前回の棚卸で、予定にないのに読まれた
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Inventory(Base):
    """棚卸の1回分。開いている（open）のは、常に1つだけ。終える（closed）と、結果が予定に反映される。"""

    __tablename__ = "inventories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(10), default="open")  # open | closed
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 終えたユーザーのID
    summary_json: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)  # 終えたときの件数
    before_json: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)  # 終える前の予定（取り消し用・結果表示用）


class InventoryRecord(Base):
    """棚卸で、備品のQRを読んだ（または手入力した）記録。追記のみ。client_id で、再送しても二重にならない。"""

    __tablename__ = "inventory_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[str] = mapped_column(String(40), unique=True)  # 端末で作る一意のID
    inventory_id: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(10))  # read：読んだ／unconfirm：未確認に戻した
    token: Mapped[str] = mapped_column(String(40), index=True)
    method: Mapped[str] = mapped_column(String(10), default="qr")  # qr | manual
    floor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    x: Mapped[float | None] = mapped_column(Float, nullable=True)
    y: Mapped[float | None] = mapped_column(Float, nullable=True)
    z: Mapped[float | None] = mapped_column(Float, nullable=True)  # 床からの高さ（m）
    moved: Mapped[bool] = mapped_column(Boolean, default=False)  # 端末の判定：予定と違う場所で読んだ
    user_id: Mapped[int] = mapped_column(Integer)
    employee_no: Mapped[str | None] = mapped_column(String(20), nullable=True)
    read_at: Mapped[datetime] = mapped_column(DateTime)  # 端末の時刻（UTC）
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DeviceToken(Base):
    """棚卸アプリの端末ごとの合言葉（トークン）。パスワードの代わりに、端末に保存する。DBには、ハッシュだけを保存する。"""

    __tablename__ = "device_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # SHA-256（16進）
    label: Mapped[str] = mapped_column(Unicode(100), default="")  # 端末の名前（管理画面で見分けるため）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 無効にした時刻（紛失したとき）


class EnrollCode(Base):
    """端末の登録用の、短時間・1回だけ使えるコード。管理画面のQRに入る。DBには、ハッシュだけを保存する。"""

    __tablename__ = "enroll_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    label: Mapped[str] = mapped_column(Unicode(100), default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FloorModel(Base):
    """階ごとの3Dモデル（3DGS）。モデルの座標とフロア図の座標を合わせる変換も、ここに持つ。
    変換：フロア図の座標 = 縮尺 × 回転 × モデルの地面の座標 + 移動（static/model_align.js と同じ式）。
    モデルのファイルは、var/models/ にある。"""

    __tablename__ = "floor_models"

    floor: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(60))  # var/models/ の中の名前（floor_<階>.<拡張子>）
    original_name: Mapped[str] = mapped_column(Unicode(200), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    y_sign: Mapped[int] = mapped_column(Integer, default=1)  # 1：Y軸が上／-1：下
    floor_y: Mapped[float] = mapped_column(Float, default=0.0)  # 床の高さ（モデルのY）
    scale: Mapped[float | None] = mapped_column(Float, nullable=True)  # 空なら、まだ合わせていない
    theta_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    tx: Mapped[float | None] = mapped_column(Float, nullable=True)
    ty: Mapped[float | None] = mapped_column(Float, nullable=True)
    rms_m: Mapped[float | None] = mapped_column(Float, nullable=True)  # 合わせたときの、ずれ（m）
    pairs_json: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)  # 対応点（編集を続けられるように）
    aligned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
