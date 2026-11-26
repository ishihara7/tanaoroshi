package jp.co.ryomo.tanaoroshi.ar

import org.junit.Assert.assertEquals
import org.junit.Test

class LabelTest {
    private val withNo = Placed("ノートPC", 0.0, 0.0, 0.5, assetNo = "A001")
    private val noNo = Placed("管理対象外", 0.0, 0.0, 0.5)

    @Test
    fun 名称の表示では_名称を出す() {
        assertEquals("ノートPC", withNo.shortLabel(LabelMode.NAME))
        assertEquals("管理対象外", noNo.shortLabel(LabelMode.NAME))
    }

    @Test
    fun 管理番号の表示では_管理番号を出す() {
        assertEquals("A001", withNo.shortLabel(LabelMode.ASSET_NO))
    }

    @Test
    fun 管理番号がない備品は_管理番号の表示でも名称を出す() {
        assertEquals("管理対象外", noNo.shortLabel(LabelMode.ASSET_NO))
    }

    @Test
    fun 一覧の名前は_管理番号と名称の両方() {
        assertEquals("A001　ノートPC", withNo.label())
        assertEquals("管理対象外", noNo.label())
    }
}
