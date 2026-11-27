package jp.co.ryomo.tanaoroshi.ar

import com.google.zxing.BarcodeFormat
import com.google.zxing.BinaryBitmap
import com.google.zxing.DecodeHintType
import com.google.zxing.EncodeHintType
import com.google.zxing.PlanarYUVLuminanceSource
import com.google.zxing.common.HybridBinarizer
import com.google.zxing.qrcode.QRCodeReader
import com.google.zxing.qrcode.QRCodeWriter
import com.google.zxing.qrcode.decoder.ErrorCorrectionLevel
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.cos
import kotlin.math.sin

/**
 * QRが、カメラの向きに対して、傾いていても読めるか。
 * アプリ（ArEngine）と同じ設定（TRY_HARDER・QRコードのみ）で、回転させたQRを読む。
 */
class QrRotationTest {
    private val url = "https://tanaoroshi.example.com/i/Tnote01"

    /** QRを、size×size の輝度（0＝黒、255＝白）にして、中心まわりに angleDeg 回転させた、大きな画像にする。 */
    private fun rotatedImage(angleDeg: Double, size: Int = 480, canvas: Int = 900): ByteArray {
        val hints = mapOf(EncodeHintType.ERROR_CORRECTION to ErrorCorrectionLevel.M, EncodeHintType.MARGIN to 4)
        val m = QRCodeWriter().encode(url, BarcodeFormat.QR_CODE, size, size, hints)
        val out = ByteArray(canvas * canvas) { 255.toByte() } // 背景は白
        val a = Math.toRadians(angleDeg)
        val c = cos(a)
        val s = sin(a)
        val cx = canvas / 2.0
        val cy = canvas / 2.0
        val qc = size / 2.0
        for (y in 0 until canvas) for (x in 0 until canvas) {
            // 出力の画素に対応する、元のQRの位置（逆回転）
            val dx = x - cx
            val dy = y - cy
            val sx = c * dx + s * dy + qc
            val sy = -s * dx + c * dy + qc
            out[y * canvas + x] = sample(m, sx - 0.5, sy - 0.5, size).toByte()
        }
        return blur(out, canvas)
    }

    /** 元のQRの (x, y) の明るさを、周りの4画素から、なめらかに求める（回転で、輪郭がギザギザにならないように）。 */
    private fun sample(m: com.google.zxing.common.BitMatrix, x: Double, y: Double, size: Int): Int {
        fun v(ix: Int, iy: Int) = if (ix in 0 until size && iy in 0 until size) (if (m[ix, iy]) 0.0 else 255.0) else 255.0
        val x0 = Math.floor(x).toInt()
        val y0 = Math.floor(y).toInt()
        val fx = x - x0
        val fy = y - y0
        val top = v(x0, y0) * (1 - fx) + v(x0 + 1, y0) * fx
        val bottom = v(x0, y0 + 1) * (1 - fx) + v(x0 + 1, y0 + 1) * fx
        return (top * (1 - fy) + bottom * fy).toInt()
    }

    /** カメラの映像に近づけるため、輪郭を少しぼかす（完全にくっきりした画像は、読み取りの癖が出やすい）。 */
    private fun blur(src: ByteArray, w: Int): ByteArray {
        val out = ByteArray(src.size)
        for (y in 0 until w) for (x in 0 until w) {
            var sum = 0
            var n = 0
            for (dy in -1..1) for (dx in -1..1) {
                val xx = x + dx
                val yy = y + dy
                if (xx in 0 until w && yy in 0 until w) { sum += src[yy * w + xx].toInt() and 0xff; n++ }
            }
            out[y * w + x] = (sum / n).toByte()
        }
        return out
    }

    private fun decode(angleDeg: Double, canvas: Int = 900): String? {
        val data = rotatedImage(angleDeg, canvas = canvas)
        val bitmap = BinaryBitmap(HybridBinarizer(PlanarYUVLuminanceSource(data, canvas, canvas, 0, 0, canvas, canvas, false)))
        val hints = mapOf(DecodeHintType.TRY_HARDER to true, DecodeHintType.POSSIBLE_FORMATS to listOf(BarcodeFormat.QR_CODE))
        return try {
            QRCodeReader().decode(bitmap, hints).text
        } catch (e: Exception) {
            null
        }
    }

    @Test
    fun 上向きでも_横向きでも_逆さでも_読める() {
        for (angle in listOf(0.0, 90.0, 180.0, 270.0)) {
            assertEquals("角度 $angle", url, decode(angle))
        }
    }

    @Test
    fun 斜めに傾いていても読める() {
        for (angle in listOf(15.0, 30.0, 45.0, 60.0, 120.0, 200.0, 315.0)) {
            assertEquals("角度 $angle", url, decode(angle))
        }
    }

    @Test
    fun ほぼどの角度でも読める() {
        // 5度刻みで、1周する。合成画像は、画素の並びとの相性で、特定の角度だけ読めないことがある（実機は、映像が毎フレーム少し違うので、次のフレームで読める）
        val failed = (0 until 360 step 5).map { it.toDouble() }.filter { decode(it) != url }
        assertTrue("読めなかった角度が多すぎます：$failed", failed.size <= 3)
    }
}
