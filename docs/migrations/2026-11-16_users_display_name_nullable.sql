-- ユーザーの「表示名」を廃止したため、列を、空でもよい列にする（データは削除しない）。
-- 新しいコードは、この列を使わない。古いコードは、この列がNULLでなければ、登録ができないため、先にこのSQLを実行する。
-- 古いコードと新しいコードのどちらでも動く、安全な変更（列の削除は、あとで、必要なら行う）。
IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'users' AND COLUMN_NAME = 'display_name' AND IS_NULLABLE = 'NO')
    ALTER TABLE users ALTER COLUMN display_name NVARCHAR(50) NULL;

-- 【後日・任意】列そのものを削除する（旧コードを使わなくなってから）。表示名の値は、削除される。
-- ALTER TABLE users DROP COLUMN display_name;
