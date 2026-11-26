package jp.co.ryomo.tanaoroshi.ar

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class MapperTest {
    private val eps = 1e-6

    // ARCoreの既定：-Z方向を向いている。アンカーの座標は (10, 20)
    private fun ref(thetaDeg: Double) = ArReference(0.0, 0.0, 0.0, -1.0, 10.0, 20.0, thetaDeg)

    @Test
    fun 北を向いて読んだとき_前に進むと北へ_右へ進むと東へ() {
        val r = ref(0.0)
        val (x1, y1) = r.toMap(0.0, -5.0) // 前（-Z）へ5m
        assertEquals(10.0, x1, eps); assertEquals(25.0, y1, eps)
        val (x2, y2) = r.toMap(3.0, 0.0) // 右（+X）へ3m
        assertEquals(13.0, x2, eps); assertEquals(20.0, y2, eps)
    }

    @Test
    fun 東を向いて読んだとき_前に進むと東へ_右へ進むと南へ() {
        val r = ref(90.0)
        val (x1, y1) = r.toMap(0.0, -5.0)
        assertEquals(15.0, x1, eps); assertEquals(20.0, y1, eps)
        val (x2, y2) = r.toMap(3.0, 0.0)
        assertEquals(10.0, x2, eps); assertEquals(17.0, y2, eps)
    }

    @Test
    fun ARの向きが違っても_基準点で向いていた方向が壁の向きになる() {
        // ARの世界で、+X方向を向いて読んだ。壁は南向き（180°）
        val r = ArReference(1.0, 2.0, 1.0, 0.0, 0.0, 0.0, 180.0)
        val (x, y) = r.toMap(1.0 + 4.0, 2.0) // 前（+X）へ4m → 南へ4m
        assertEquals(0.0, x, eps); assertEquals(-4.0, y, eps)
    }

    @Test
    fun 方位() {
        val r = ref(90.0)
        assertEquals(90.0, r.bearingOf(0.0, -1.0), eps) // 基準と同じ向き＝壁の向き
        assertEquals(180.0, r.bearingOf(1.0, 0.0), eps) // 右を向く＝東向きの右＝南
        assertEquals(0.0, r.bearingOf(-1.0, 0.0), eps) // 左を向く＝北
    }

    @Test
    fun 距離と方位() {
        val (d, b) = distanceAndBearing(0.0, 0.0, 3.0, 4.0)
        assertEquals(5.0, d, eps)
        assertEquals(36.8699, b, 1e-3)
        assertEquals(270.0, distanceAndBearing(0.0, 0.0, -5.0, 0.0).second, eps)
        assertEquals("北東", compassLabel(45.0))
        assertEquals("北", compassLabel(350.0))
    }

    @Test
    fun タグのURL() {
        assertEquals(TagRef(true, "Aeast"), parseTagUrl("https://example.com/a/Aeast"))
        assertEquals(TagRef(false, "T123"), parseTagUrl(" http://192.168.0.5:8000/i/T123?x=1 "))
        assertNull(parseTagUrl("hello"))
        assertNull(parseTagUrl("https://example.com/x/abc"))
        assertNotNull(parseTagUrl("https://example.com/a/A1/"))
        assertTrue(ErrorModel.estimate(10.0) > ErrorModel.estimate(0.0))
    }
}

class SetupUrlTest {
    private val code = "abcDEF0123456789_-abcDEF0123456789"

    @Test
    fun 設定用のQRから_サーバーと設定コードを読み取る() {
        val r = parseSetupUrl("https://tanaoroshi.azurewebsites.net/setup/$code")!!
        assertEquals("https://tanaoroshi.azurewebsites.net", r.server)
        assertEquals(code, r.code)
    }

    @Test
    fun ポート付きのHTTPも読み取れる() {
        val r = parseSetupUrl("  http://192.168.128.100:8765/setup/$code/ ")!!
        assertEquals("http://192.168.128.100:8765", r.server)
    }

    @Test
    fun 設定用でないURLは読み取らない() {
        assertEquals(null, parseSetupUrl("https://example.com/i/Tnote01"))
        assertEquals(null, parseSetupUrl("https://example.com/a/Aabc"))
        assertEquals(null, parseSetupUrl("https://example.com/setup/short"))
        assertEquals(null, parseSetupUrl("https://example.com/setup/$code?x=1"))
        assertEquals(null, parseSetupUrl("ftp://example.com/setup/$code"))
        assertEquals(null, parseSetupUrl("設定"))
    }

    @Test
    fun 備品とアンカーのQRは_設定用として扱わない() {
        assertEquals(null, parseTagUrl("https://example.com/setup/$code"))
    }
}
