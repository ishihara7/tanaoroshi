-- 高さの記録：アンカー（QRを貼った高さ）、予定（備品の高さ）、棚卸の記録（読んだ高さ）。すべて、床からの高さ（m）
-- 何度流しても安全（すでにあれば、何もしない）。既存の行は、アンカーは 0（床）、備品と記録は NULL（高さ不明）になる。
IF COL_LENGTH('anchors', 'z_m') IS NULL
    ALTER TABLE anchors ADD z_m FLOAT NOT NULL CONSTRAINT DF_anchors_z_m DEFAULT 0;
IF COL_LENGTH('ar_items', 'z') IS NULL
    ALTER TABLE ar_items ADD z FLOAT NULL;
IF COL_LENGTH('inventory_records', 'z') IS NULL
    ALTER TABLE inventory_records ADD z FLOAT NULL;
