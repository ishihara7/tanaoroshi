-- フロア図と備品の種別の機能を削除したため、使わなくなったテーブルと列を削除する（後片付け）。
-- アプリは、これらが残っていても、動作に影響しない（備品の2列は、空でもよい列）。急がない。
-- 実行前に、必ずバックアップを取る（Azure SQL の自動バックアップがあること、必要なら備品をCSV出力する）。
-- 削除されるデータ：フロア図の登録内容（floors）、種別の一覧（categories）、備品の種別・フロアの値。元に戻せない。
BEGIN TRAN;

DROP TABLE IF EXISTS floors;
DROP TABLE IF EXISTS categories;
ALTER TABLE assets DROP COLUMN IF EXISTS category_id;
ALTER TABLE assets DROP COLUMN IF EXISTS current_floor_id;

COMMIT;
