// 備品所在管理システムの Azure 環境（現在の構成を再現する）。
// 使い方は infra/README.md を参照。既存の環境には、この定義を適用しないこと（名前が重複する）。
targetScope = 'resourceGroup'

@description('Web App の名前。ホスト名の一部になる（タグのURLに使うため、変更するとタグが無効になる）')
param webAppName string

@description('App Service プランの名前')
param planName string = 'plan-${webAppName}'

@description('SQL サーバーの名前（小文字・数字・ハイフン。全世界で一意）')
param sqlServerName string

@description('SQL データベースの名前')
param sqlDatabaseName string = 'tanaoroshi'

@description('SQL の管理者ログイン')
param sqlAdminLogin string

@secure()
@description('SQL の管理者パスワード（リポジトリに書かない。デプロイ時に指定する）')
param sqlAdminPassword string

@secure()
@description('セッション署名用の長いランダム文字列（リポジトリに書かない）')
param secretKey string

@secure()
@description('座標の暗号化の鍵（43文字、base64url）。リポジトリに書かない。失うと座標が読めなくなるため、別の場所にも控える')
param coordEncryptionKey string

@description('App Service のリージョン（Japan East で B1 が使えなかったため、現在は Japan West）')
param appLocation string = 'japanwest'

@description('SQL のリージョン')
param dataLocation string = 'japaneast'

@description('開発PCなど、SQL に接続を許可する固定IP（空なら追加しない）')
param clientIp string = ''

// ---------- App Service ----------
resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: planName
  location: appLocation
  kind: 'linux'
  sku: { name: 'B1', tier: 'Basic' }
  properties: { reserved: true }
}

// ---------- Azure SQL ----------
resource sqlServer 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: sqlServerName
  location: dataLocation
  properties: {
    administratorLogin: sqlAdminLogin
    administratorLoginPassword: sqlAdminPassword
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
  }
}

resource sqlDb 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  parent: sqlServer
  name: sqlDatabaseName
  location: dataLocation
  sku: { name: 'Basic', tier: 'Basic' }
}

// 「Azure サービスを許可」（0.0.0.0）。広いため、本番化までに Web App の送信元IPだけに絞ること
resource allowAzure 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = {
  parent: sqlServer
  name: 'AllowAllWindowsAzureIps'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}

resource allowClient 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = if (!empty(clientIp)) {
  parent: sqlServer
  name: 'client-ip'
  properties: { startIpAddress: clientIp, endIpAddress: clientIp }
}

// ---------- Web App ----------
resource webApp 'Microsoft.Web/sites@2023-12-01' = {
  name: webAppName
  location: appLocation
  kind: 'app,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.14'
      appCommandLine: 'gunicorn -k uvicorn.workers.UvicornWorker app.main:app'
      minTlsVersion: '1.2'
      ftpsState: 'FtpsOnly'
      appSettings: [
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'true' }
        { name: 'DB_SERVER', value: sqlServer.properties.fullyQualifiedDomainName }
        { name: 'DB_NAME', value: sqlDatabaseName }
        { name: 'DB_USER', value: sqlAdminLogin }
        { name: 'DB_PASSWORD', value: sqlAdminPassword }
        { name: 'SECRET_KEY', value: secretKey }
        { name: 'COORD_ENCRYPTION_KEY', value: coordEncryptionKey }
      ]
    }
  }
}

output webAppHostName string = webApp.properties.defaultHostName
output webAppPrincipalId string = webApp.identity.principalId
output sqlServerFqdn string = sqlServer.properties.fullyQualifiedDomainName
