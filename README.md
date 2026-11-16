# 備品所在管理システム（NFCタグ × Azure）

備品のNFCタグ（またはQRコード）をiPhoneで読み取ると、GPS位置を記録し、レーダー画面で、備品がある方向と距離を確認できるシステム（PoC）。

- 要件：[docs/要件定義書.md](docs/要件定義書.md)
- 運用手順書（セットアップ、タグの書き込み、日常の使い方、デプロイ）：[docs/運用手順書.md](docs/運用手順書.md)
- Azure 環境の定義（Bicep）：[infra/README.md](infra/README.md)
- 元の依頼書：[HANDOFF_備品所在管理システム.md](HANDOFF_備品所在管理システム.md)

## 技術スタック
Python 3.14 / FastAPI / Jinja2 / SQLAlchemy 2.x / SQL Server（ローカルはSQL Server Express、本番はAzure SQL Database）

## ローカルでの起動

### 1. 仮想環境と依存パッケージ
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt   # 開発・テスト用（本番は requirements.txt）
```

### 2. 設定ファイル
`.env.example` をコピーして `.env` を作り、値を入れる（`.env` はコミットしない）。
```powershell
Copy-Item .env.example .env
```
ローカルDBは SQL Server Express（`localhost\SQLEXPRESS`、Windows認証）を使う。

### 3. ローカルDBの作成
```powershell
sqlcmd -S "localhost\SQLEXPRESS" -E -C -Q "CREATE DATABASE tanaoroshi_dev"
```

### 4. 起動とテスト
```powershell
uvicorn app.main:app --reload
# http://localhost:8000/health
pytest
```

## スマホでの確認（位置情報はHTTPS必須）
位置情報APIはHTTPSでのみ動く。スマホから `localhost` には届かないため、次のどちらかで確認する。
- Azure の開発用 App Service にデプロイして確認する
- HTTPSトンネル（例：Dev Tunnels、ngrok）でローカルを公開する

## Azure
- リソース グループ：`rg-tanaoroshi`（App Service：Japan West、SQL：Japan East）
- 環境変数は App Service の「アプリ設定」に登録する（名前は `.env.example` と同じ）
- 起動コマンド：`gunicorn -k uvicorn.workers.UvicornWorker app.main:app`

## 注意
- 秘密情報（DBパスワード、接続文字列、SECRET_KEY）は、リポジトリに含めない。
- NFCタグはPoC中はロックしない（ドメイン確定前のため）。
