"""画像の保存先。接続文字列があれば Azure Blob、なければローカルのフォルダ（var/uploads）。"""
from pathlib import Path

from app.config import load_settings

LOCAL_DIR = Path(__file__).resolve().parent.parent / "var" / "uploads"
MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def media_type_of(name: str) -> str:
    return MEDIA_TYPES.get(Path(name).suffix.lower(), "application/octet-stream")


def _container():
    from azure.storage.blob import BlobServiceClient

    s = load_settings()
    return BlobServiceClient.from_connection_string(s.storage_connection_string).get_container_client(s.storage_container)


def save(name: str, data: bytes) -> None:
    if load_settings().storage_connection_string:
        from azure.storage.blob import ContentSettings

        _container().upload_blob(
            name, data, overwrite=True, content_settings=ContentSettings(content_type=media_type_of(name))
        )
        return
    path = LOCAL_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def load(name: str) -> bytes | None:
    """保存した画像を返す。なければ None。"""
    if load_settings().storage_connection_string:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            return _container().download_blob(name).readall()
        except ResourceNotFoundError:
            return None
    path = LOCAL_DIR / name
    return path.read_bytes() if path.is_file() else None
