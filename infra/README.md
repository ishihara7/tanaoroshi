# Azure 環境の定義（Bicep）

[main.bicep](main.bicep) は、現在の環境（App Service B1、Azure SQL Basic）を再現する定義です。

> **注意**：現在の環境は、ポータルで手作業で作成したものです。**既存の環境に、この定義を適用しないでください**（名前が重複し、設定が上書きされます）。新しい環境（検証用、本番用、作り直し）を作るときに使います。

## 構文の確認（Azure には変更なし）
```powershell
az bicep build --file infra/main.bicep --stdout > $null
```

## 新しい環境を作る
1. リソース グループを作る
   ```powershell
   az group create -n <リソースグループ名> -l japanwest
   ```
2. 変更内容を、事前に確認する（**実行前に、必ず確認する**）
   ```powershell
   az deployment group what-if -g <リソースグループ名> -f infra/main.bicep `
     -p webAppName=<10文字以内> sqlServerName=<一意の名前> `
        sqlAdminLogin=<管理者名> sqlAdminPassword=<強いパスワード> secretKey=<長いランダム文字列> coordEncryptionKey=<座標の暗号化の鍵（43文字）>
   ```
3. 問題なければ、`what-if` を `create` に変えて実行する（課金が発生する）。
4. アプリのコードは、別にデプロイする（[運用手順書](../docs/運用手順書.md)の「デプロイ」）。

## 注意点
- **パスワード、`secretKey`、`coordEncryptionKey` は、ファイルやコマンド履歴に残さない**。`coordEncryptionKey` は、失うと座標が読めなくなるため、別の場所にも控える（パラメータの対話入力、または Key Vault を使う）。
- Web App の名前は、タグのURLの一部になる。**タグを書き込んだ後は、変更できない**。
- SQL のファイアウォールは、現在は「Azure サービスを許可」。本番化までに、Web App の送信元IPだけに絞る。
