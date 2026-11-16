"""座標の暗号化（アプリケーション層）。

DBには、暗号文だけを保存する。鍵は、環境変数 COORD_ENCRYPTION_KEY（32バイトを base64url で表した43文字）。
- 方式：AES-256-GCM（暗号化と改ざんの検出を、同時に行う）
- 同じ値でも、保存のたびに、暗号文が変わる（乱数のnonceを使うため）
- 暗号文に、保存先の列の名前を結びつける（別の列にコピーしても、復号できない）
- 形式："v1:" + base64url(nonce 12バイト + 暗号文 + 認証タグ 16バイト)

鍵を失うと、保存した座標は、二度と読めない。鍵は、別の場所（パスワード管理ツールなど）にも、必ず控えておくこと。
SECRET_KEY（ログイン状態の署名用）とは、別の鍵。
"""
import base64
import os
import struct

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from app.config import load_settings

VERSION = "v1"
KEY_ENV = "COORD_ENCRYPTION_KEY"


def generate_key() -> str:
    """新しい鍵を作る（43文字）。"""
    return base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")


def parse_key(raw: str) -> bytes:
    if not raw:
        raise RuntimeError(f"{KEY_ENV} が設定されていません。座標の暗号化に使う鍵（43文字）を、環境変数（アプリ設定）に設定してください。")
    try:
        key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"{KEY_ENV} の形式が正しくありません（base64urlの43文字）。") from e
    if len(key) != 32:
        raise RuntimeError(f"{KEY_ENV} は、32バイト（base64urlで43文字）の鍵にしてください。")
    return key


def ensure_key() -> None:
    """起動時に呼び、鍵が正しく設定されていなければ、起動させない。"""
    parse_key(load_settings().coord_key)


def encrypt_float(value: float, label: str, key: bytes | None = None) -> str:
    key = key or parse_key(load_settings().coord_key)
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, struct.pack(">d", float(value)), label.encode())
    return f"{VERSION}:" + base64.urlsafe_b64encode(nonce + ciphertext).decode().rstrip("=")


def decrypt_float(text: str, label: str, key: bytes | None = None) -> float:
    key = key or parse_key(load_settings().coord_key)
    prefix = f"{VERSION}:"
    if not text.startswith(prefix):
        raise ValueError("座標を復号できません（暗号化された形式ではありません）。")
    try:
        raw = base64.urlsafe_b64decode(text[len(prefix):] + "=" * (-len(text[len(prefix):]) % 4))
        plain = AESGCM(key).decrypt(raw[:12], raw[12:], label.encode())
        return struct.unpack(">d", plain)[0]
    except (InvalidTag, ValueError, struct.error) as e:
        raise ValueError("座標を復号できません（鍵が違うか、データが壊れています）。") from e


class EncryptedFloat(TypeDecorator):
    """DBには暗号文（文字列）で保存し、アプリでは、普通の数値として扱う。"""

    impl = String(100)
    cache_ok = True

    def __init__(self, label: str):
        super().__init__()
        self.label = label  # 暗号文を結びつける列の名前（例：scans.latitude）

    def process_bind_param(self, value, dialect):
        return None if value is None else encrypt_float(value, self.label)

    def process_result_value(self, value, dialect):
        return None if value is None else decrypt_float(value, self.label)
