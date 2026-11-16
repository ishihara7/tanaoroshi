r"""Azure へのデプロイ用ZIPを作る（出力先：out/deploy.zip）。

使い方（プロジェクトのフォルダで）：
    .venv\Scripts\python.exe tools\make_deploy_zip.py

含めるもの：requirements.txt と app/ だけ。.env、.venv、tests、.git などの、秘密情報や不要なものは含めない。
"""
import pathlib
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "deploy.zip"


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(ROOT / "requirements.txt", "requirements.txt")
        for p in sorted((ROOT / "app").rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                z.write(p, p.relative_to(ROOT).as_posix())
    names = zipfile.ZipFile(OUT).namelist()
    secret = [n for n in names if ".env" in n]
    if secret:
        print("秘密情報が含まれています:", secret)
        return 1
    print(f"{len(names)}ファイル -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
