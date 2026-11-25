package jp.co.ryomo.tanaoroshi.ar

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class HeadingTest {
    private val eps = 1e-6

    @Test
    fun 角度の差は_プラスマイナス180に収まる() {
        assertEquals(10.0, signedDiffDeg(370.0), eps)
        assertEquals(-10.0, signedDiffDeg(350.0), eps)
        assertEquals(180.0, signedDiffDeg(180.0), eps)
        assertEquals(-170.0, signedDiffDeg(190.0), eps)
    }

    @Test
    fun 座標系が保たれていれば_食い違いは小さい() {
        // 追跡できている間、ARの向き = ジャイロ + 100°。ジャイロが40°回ったら、ARの向きも40°回る
        val offset = 100.0
        val gyroNow = 70.0 + 40.0
        val arYawNow = gyroNow + offset + 3.0 // ドリフト3°
        assertEquals(3.0, yawMismatchDeg(arYawNow, gyroNow, offset), eps)
        assertTrue(Math.abs(yawMismatchDeg(arYawNow, gyroNow, offset)) < FRAME_RESET_DEG)
    }

    @Test
    fun 座標系がリセットされたら_食い違いが大きい() {
        // ARの座標系が、90°回って再開した
        val offset = 100.0
        val gyroNow = 110.0
        val arYawNow = gyroNow + offset + 90.0
        assertTrue(Math.abs(yawMismatchDeg(arYawNow, gyroNow, offset)) > FRAME_RESET_DEG)
    }

    @Test
    fun 方角は_ジャイロが回った量だけ変わる() {
        // 途切れる前は東（90°）を向いていた。途切れている間に、ジャイロが右へ60°回った
        assertEquals(150.0, bearingAfterLoss(90.0, 200.0, 260.0), eps)
        // 左へ120°回った（北をまたぐ）
        assertEquals(330.0, bearingAfterLoss(90.0, 200.0, 80.0), eps)
        // 回っていなければ、同じ
        assertEquals(90.0, bearingAfterLoss(90.0, 200.0, 200.0), eps)
    }

    @Test
    fun ジャイロの角が_360をまたいでも_回転量は正しい() {
        // 350° → 10° は、右へ20°
        assertEquals(110.0, bearingAfterLoss(90.0, 350.0, 10.0), eps)
    }
}
