# 申し送り：備品所在管理システム（NFCタグ × Azure）

Claude Code への作業依頼書です。最初にこのファイルを最後まで読み、「0. 進め方のルール」に従って作業してください。

---

## 0. 進め方のルール

- 作業は「7. 開発フェーズ」の順に、**小さい単位で**進める。各ステップの終わりに、動作確認の方法と次にやることを報告する。
- **Azureリソースの作成・変更・削除、課金が発生する操作は、実行前に必ず確認を取る**（コマンドを提示して承認を待つ）。
- 秘密情報（DB接続文字列、パスワード、キー）はリポジトリに含めない。`.env`（ローカル）とApp Serviceのアプリ設定で管理し、`.env.example` だけをコミットする。
- 仕様が不明な点は推測で実装せず、「10. 未決事項」に追記して質問する。
- コード・コメント・画面の文言は日本語（変数名・関数名は英語）。
- テストは `pytest` で書き、各フェーズで主要な処理のテストを追加する。

---

## 1. 背景と目的

- 社内備品の所在がすぐに分からなくなり、棚卸のたびに探し回っている。原因は、移動の記録が手間で残らないこと。
- 備品と場所にNFCタグを貼り、スマホで **「場所タグ → 備品タグ」の順にタッチ** するだけで所在を記録できるようにする。
- 記録した所在は**建物のフロア図上**に表示し、棚卸では「あるはずなのに未確認の物」「別の場所にある物」を自動で抽出する。
- 上司への提案は承認済みで、NFCタグも購入済み。これからPoC（1フロアでの試行）向けのシステムを構築する。

## 2. 前提条件

| 項目 | 内容 |
|---|---|
| 管理対象 | 約300〜1,000点。大半がノートPC・モニター・LANハブ（スイッチ） |
| 管理番号 | **10桁**（先頭0あり得る → 必ず**文字列**で扱う） |
| 社用スマホ | **iPhone中心**。棚卸の連続スキャン用・タグ書き込み用に**Android 1台**を用意 |
| 位置の単位 | 場所タグを貼った単位（部屋・棚）。フロア図上のX・Yと階数を場所に持たせる |
| GPS | 補助情報として毎回記録する（屋内では10〜数十mずれる、階数は判別不可） |
| NFCタグ | NTAG系。購入品は504バイト品（NTAG215相当と思われる・要確認）。金属対応品にNTAG210（48バイト）が混ざる可能性に備え、**URLは48バイト以内に収まる長さ**にする |
| 開発環境 | VS Code + Claude Code |

## 3. 技術スタック（決定事項）

| 区分 | 採用 |
|---|---|
| 言語 | Python（App Serviceが対応する最新版。3.14が使えるなら3.14、無理なら3.13。**着手時に対応状況を確認すること**） |
| Webフレームワーク | FastAPI |
| 画面 | Jinja2テンプレートによるサーバーサイドレンダリング＋最小限のJavaScript（スマホ優先のレスポンシブ） |
| ORM / マイグレーション | SQLAlchemy 2.x / Alembic |
| DB | **Azure SQL Database**（Basic想定）。ドライバは `pyodbc` ＋ ODBC Driver 18 |
| ファイル保存 | Azure Blob Storage（フロア図画像・備品写真） |
| ホスティング | Azure App Service（Linux, B1想定, 東日本リージョン） |
| 認証 | **簡易ログイン（社内で発行したID＋パスワード）**。Entra IDは使わない |
| IaC | Bicep（`infra/` 配下）＋ Azure CLI でデプロイ |
| ローカルDB | SQL Server の Docker コンテナ（`mcr.microsoft.com/mssql/server`）。方言差を避けるため SQLite は使わない |

## 4. 画面とURL設計

### 4.1 NFCタグに書き込むURL（変更不可になる前提で設計）

タグは最後にロックするため、**URLの形式とドメインは後から変えられない**。短く固定的な形式にする。

| 種類 | URL | 例 |
|---|---|---|
| 備品タグ | `https://{ドメイン}/i/{管理番号10桁}` | `/i/1234567890` |
| 場所タグ | `https://{ドメイン}/l/{場所ID10桁}` | `/l/0000000123` |

- ドメインは `*.azurewebsites.net` ではなく、**社内で長く使えるカスタムドメイン**を推奨（未決事項）。決まるまではタグをロックしない。
- `https://` はNDEFのURIプレフィックスで1バイトに圧縮されるため、`ドメイン + /i/ + 10桁` が約45バイト以内なら NTAG210 にも収まる。

### 4.2 iPhone（URL起動）の動き

iPhoneのSafariは Web NFC 非対応。タグをかざすと通知 → タップでURLが開く方式で動かす。

1. **場所タグ `/l/{id}` を開いた時**：セッションに「現在地＝その場所」と時刻を保存し、「◯◯にいます。備品タグをタッチしてください」と表示。
2. **備品タグ `/i/{id}` を開いた時**：
   - 現在地が**有効期限内（初期値10分、設定で変更可）**なら、その場所で所在を記録。
   - 期限切れ・未設定なら、「場所タグをタッチしてください」と表示し、場所一覧から選んで記録することもできるようにする。
   - 同時に Geolocation API で位置情報（緯度・経度・誤差・高度）を取得して送信。拒否・タイムアウト時は位置情報なしで記録する。
   - 記録後、備品名・記録した場所・「持ち出し／返却」ボタンを表示。
3. タグをかざすたびにログインを求めないよう、**セッションCookieは長め（例：30日、設定可）**にする（`Secure`、`HttpOnly`、`SameSite=Lax`）。

### 4.3 Android専用画面（Chrome の Web NFC）

- **連続スキャン画面**（棚卸用）：ページを開いたまま `NDEFReader.scan()` で次々に読み取る。場所タグを読んだら現在地を切り替え、備品タグは即時記録して画面に一覧表示。
- **タグ書き込み画面**：台帳から未発行の管理番号を取得 → かざして `NDEFReader.write()` で URL を書き込み → 成功したらタグのUID（`serialNumber`）と管理番号をひも付けて保存。
- Web NFC 非対応のブラウザでは、「この画面はAndroidのChromeで開いてください」と表示する。

### 4.4 画面一覧

| 画面 | 利用者 | 内容 |
|---|---|---|
| ログイン | 全員 | ID＋パスワード |
| 備品タグ着地ページ `/i/{id}` | 全員 | 所在記録、持ち出し・返却 |
| 場所タグ着地ページ `/l/{id}` | 全員 | 現在地の設定、その場所の備品一覧 |
| 備品検索 | 全員 | 管理番号・名称・種別で検索、現在地・履歴を表示 |
| フロア図 | 全員 | 階を選ぶと場所ごとにピン（件数）表示。クリックで備品一覧。定位置外の物は色を変える |
| 要確認リスト | 全員 | 定位置と違う物／長期未確認（初期値90日）／返却期限切れ／GPSが他の建物を示した記録 |
| 棚卸 | 全員 | 場所単位で開始 → スキャン → 「未確認」「他の場所の物」を一覧 → 完了 |
| 連続スキャン（Android） | 担当者 | 4.3参照 |
| タグ書き込み（Android） | 管理者 | 4.3参照 |
| 備品管理 | 管理者 | 登録・編集・廃棄、CSV取込・出力、写真登録 |
| 場所・フロア管理 | 管理者 | フロア図画像のアップロード、図をクリックして場所の位置を登録 |
| ユーザー管理 | 管理者 | ID発行、パスワード初期化、権限（一般／管理者） |

## 5. データモデル（初期案）

座標はフロア図画像のサイズに依存しないよう、**0〜1の割合（x_ratio, y_ratio）**で保存する。

```
users            : id, login_id(unique), display_name, password_hash, role(admin|user), is_active, created_at
floors           : id, building, floor_label(例 "3F"), sort_order, image_blob_path, image_width, image_height
locations        : id(CHAR(10)), floor_id, name(例 "会議室A"), x_ratio, y_ratio, is_active
assets           : asset_no(CHAR(10) PK), name, category(ノートPC|モニター|LANハブ|その他), maker, model, serial_no,
                   home_location_id, current_location_id, last_seen_at,
                   status(保管|使用中|貸出中|修理|廃棄), holder_name, due_date,
                   photo_blob_path, tag_uid, tag_type, note, created_at, updated_at
scans            : id, asset_no, location_id(null可), scan_type(move|inventory|checkout|return),
                   latitude, longitude, accuracy_m, altitude, user_id, user_agent, created_at
inventory_sessions: id, location_id, started_by, started_at, finished_at
inventory_results : session_id, asset_no, result(found|missing|unexpected)
settings         : key, value   （場所の有効時間、長期未確認の日数、Cookie期限など）
```

- `scans` は追記のみ（更新・削除しない）。`assets.current_location_id` と `last_seen_at` は記録時に更新する。
- 「定位置外」＝ `current_location_id != home_location_id`。

## 6. Azure構成

| リソース | SKU（想定） | 用途 |
|---|---|---|
| リソースグループ | - | 一式をまとめる（名前は未決事項） |
| App Service プラン | Linux B1 | Webアプリ |
| App Service（Web App） | Python | FastAPI（gunicorn + uvicorn worker）。**HTTPSのみ** |
| Azure SQL Database | Basic | 台帳・履歴 |
| Storage Account | Standard LRS | Blob：フロア図・写真（非公開コンテナ、アプリ経由で配信） |
| Application Insights | 従量 | ログ・エラー監視（任意） |

- App Service から Blob へは **マネージドID** でアクセスする（キーを使わない）。
- SQL の接続情報は App Service のアプリ設定に置く（可能ならマネージドIDでの接続も検討）。
- 起動コマンド例：`gunicorn -k uvicorn.workers.UvicornWorker app.main:app`
- 位置情報 API は HTTPS が必須。ローカル確認はスマホから `localhost` にアクセスできないため、**開発用の App Service か、HTTPSトンネル**を使う方法を提示すること。

## 7. 開発フェーズ

### Phase 0：準備・技術検証
1. リポジトリ構成の作成（下記8章）、`README.md`、`.env.example`、ローカルのSQL Serverコンテナ起動手順。
2. **位置情報テストページ**：`/test/geo?id=xxx` で緯度・経度・誤差・高度を表示し、DBに保存。社内各フロアでの誤差を測るために使う。
3. App Service で Python 3.14（または3.13）＋ ODBC Driver 18 ＋ Azure SQL へ接続できることを確認。

### Phase 1：MVP（PoCで使う最小構成）
1. ログイン・ユーザー管理（パスワードは argon2 でハッシュ化、ログイン試行の回数制限、CSRF対策）
2. 備品・場所・フロアのCRUD、備品のCSV取込（既存台帳から移行）
3. 場所タグ／備品タグの着地ページ（4.2の動き）とスキャン記録
4. フロア図画面（ピン表示、件数、定位置外の色分け）
5. 備品検索と移動履歴

### Phase 2：棚卸と運用機能
1. 棚卸機能（場所単位、未確認・他の場所の物の一覧）
2. Android連続スキャン画面・タグ書き込み画面（UIDのひも付け）
3. 要確認リスト
4. 持ち出し・返却、返却期限切れの表示（通知手段は未決事項）
5. CSV出力（台帳・棚卸結果）

### Phase 3：本番化
1. Bicep による環境構築の整備、デプロイ手順書（または GitHub Actions）
2. バックアップ・ログの確認、運用手順書（タグの書き込み・ロック手順を含む）

## 8. リポジトリ構成（案）

```
app/
  main.py            # FastAPI起動
  config.py          # 設定（環境変数）
  db.py, models.py   # SQLAlchemy
  auth.py            # ログイン・セッション
  routers/           # tags.py(/i,/l), assets.py, floors.py, inventory.py, admin.py, api.py
  services/          # 所在記録・棚卸判定などのロジック
  templates/         # Jinja2
  static/            # CSS, JS（nfc.js, geo.js, floormap.js）
alembic/
infra/               # Bicep
tests/
docs/                # この申し送り、運用手順
.env.example
requirements.txt
README.md
```

## 9. セキュリティと注意点

- タグのURLは誰でも読めるため、**ログインしていない人には備品情報を見せない**（ログイン画面へ誘導し、ログイン後に元のURLへ戻す）。
- タグのなりすまし対策として、Android で読み取った場合は UID と管理番号の組み合わせを照合し、不一致なら警告を記録する（iPhoneのURL起動ではUIDは取得できない）。
- タグのロックは**ドメインとURL形式が確定してから**行う。ロックは元に戻せない。
- 高度（altitude）は取得できないことが多く精度も低いため、表示はするが判定には使わない。
- 個人の位置情報を扱うことになるため、取得するのは**スキャンした瞬間の1回だけ**とし、継続的な追跡はしない。

## 10. 未決事項（ユーザーに確認が必要）

- [ ] カスタムドメイン名（タグに書き込むURL。ロック前に確定が必要）
- [ ] 購入したタグの正確な型番（NTAG215 か。金属対応品の型番）
- [ ] 場所IDの採番ルール（10桁でよいか、建物・階をIDに含めるか）
- [ ] 既存の備品台帳の形式（Excelの列構成）→ CSV取込の仕様に反映
- [ ] 備品の種別一覧（ノートPC・モニター・LANハブ・その他でよいか）
- [ ] 返却期限切れなどの通知手段（メール／Teams／画面表示のみ）
- [ ] Azure のサブスクリプション・リソースグループ名・命名規則
- [ ] 管理者になる人、初期ユーザーの発行方法
- [ ] PoC対象のフロアと、フロア図画像の形式（PDF／PNG）

## 11. 参考

- 位置の記録方法は「場所タグ方式（採用）」と「GPS方式」の2案を比較済み。屋内ではGPSで部屋や階を特定できないため、場所タグ方式を採用し、GPSは補助として記録する。
- 棚卸の連続読み取りと書き込みは Web NFC（Android版Chromeのみ対応）を使う。
- 提案資料：`備品所在管理システム提案.pptx`
