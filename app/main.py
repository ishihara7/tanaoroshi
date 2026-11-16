"""FastAPI 起動。起動確認用の /health のみ（機能は順次追加する）。"""
from fastapi import FastAPI

app = FastAPI(title="備品所在管理システム")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
