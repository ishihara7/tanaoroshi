-- 位置の記録に、社員番号の列を追加する（記録した人の社員番号。氏名は扱わない）。
-- 旧データ（社員番号が入力される前の記録）は、NULL のまま。データは削除しない。
-- 実行前に、バックアップ（Azure SQL の自動バックアップ）があることを確認する。
-- 順番：このSQLを実行してから、新しいコードをデプロイする（古いコードは、この列があっても動く）。
BEGIN TRAN;

IF COL_LENGTH('scans', 'employee_no') IS NULL
    ALTER TABLE scans ADD employee_no VARCHAR(20) NULL;

-- 同じバッチで、追加した列を参照できないため、索引は動的SQLで作る
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_scans_employee_no' AND object_id = OBJECT_ID('scans'))
    EXEC sp_executesql N'CREATE INDEX ix_scans_employee_no ON scans (employee_no)';

COMMIT;
