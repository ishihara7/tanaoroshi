-- 管理番号を、半角英数字1〜20文字（旧：10文字まで）に広げる。データは残す。
-- 対象：assets.asset_no（主キー）、scans.asset_no（索引つき）。Alembic 導入までの、手動の変更記録。
-- 実行前に、バックアップ（Azure SQL の自動バックアップ）があることを確認する。
BEGIN TRAN;

-- scans：索引を外して、列を広げ、索引を作り直す
DROP INDEX IF EXISTS ix_scans_asset_no ON scans;
ALTER TABLE scans ALTER COLUMN asset_no VARCHAR(20) NOT NULL;
CREATE INDEX ix_scans_asset_no ON scans (asset_no);

-- assets：主キー制約の名前は自動生成のため、調べてから外す
DECLARE @pk sysname = (SELECT name FROM sys.key_constraints WHERE parent_object_id = OBJECT_ID('assets') AND type = 'PK');
DECLARE @drop nvarchar(400) = N'ALTER TABLE assets DROP CONSTRAINT ' + QUOTENAME(@pk);
EXEC sp_executesql @drop;
ALTER TABLE assets ALTER COLUMN asset_no VARCHAR(20) NOT NULL;
ALTER TABLE assets ADD CONSTRAINT PK_assets PRIMARY KEY (asset_no);

COMMIT;
