package jp.co.ryomo.tanaoroshi.ar

import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.roundToInt
import kotlin.math.sin

/**
 * ARの座標（ARCoreの世界座標）と、フロア図上の座標（x：東、y：北。単位はm）の対応づけ。
 *
 * ARCoreの世界座標は、Yが上、水平面がX-Z。向きは、起動のたびに変わる。
 * そこで、アンカーのQRを読んだ瞬間を基準にする：
 *   - その瞬間のカメラの位置（p0）が、アンカーの座標に当たる
 *   - その瞬間にカメラが向いていた水平方向（f0）が、壁に正対した向き（北を0°とした時計回りで thetaDeg）に当たる
 */
class ArReference(
    val p0x: Double,
    val p0z: Double,
    f0x: Double,
    f0z: Double,
    val anchorX: Double,
    val anchorY: Double,
    val thetaDeg: Double,
) {
    /** 基準点で向いていた水平方向（長さ1） */
    val f0x: Double
    val f0z: Double

    init {
        val len = hypot(f0x, f0z)
        this.f0x = if (len > 1e-9) f0x / len else 0.0
        this.f0z = if (len > 1e-9) f0z / len else -1.0
    }

    private val sinT = sin(Math.toRadians(thetaDeg))
    private val cosT = cos(Math.toRadians(thetaDeg))

    /** ARの水平位置（px, pz）を、フロア図上の座標（x：東、y：北）にする。 */
    fun toMap(px: Double, pz: Double): Pair<Double, Double> {
        val dx = px - p0x
        val dz = pz - p0z
        val forward = dx * f0x + dz * f0z // 基準点で向いていた方向への成分
        val right = -dx * f0z + dz * f0x // その右手側への成分
        // 地図上で、前は (sinθ, cosθ)、右は (cosθ, -sinθ)
        return Pair(
            anchorX + forward * sinT + right * cosT,
            anchorY + forward * cosT - right * sinT,
        )
    }

    /** ARの水平方向（fx, fz）を、フロア図上の方位（北を0°とした時計回り、0〜360）にする。 */
    fun bearingOf(fx: Double, fz: Double): Double {
        val forward = fx * f0x + fz * f0z
        val right = -fx * f0z + fz * f0x
        val east = forward * sinT + right * cosT
        val north = forward * cosT - right * sinT
        return normalizeDeg(Math.toDegrees(atan2(east, north)))
    }
}

fun normalizeDeg(deg: Double): Double = ((deg % 360.0) + 360.0) % 360.0

/** 2点間の距離（m）と、方位（北を0°とした時計回り）。 */
fun distanceAndBearing(fromX: Double, fromY: Double, toX: Double, toY: Double): Pair<Double, Double> {
    val dx = toX - fromX
    val dy = toY - fromY
    return Pair(hypot(dx, dy), normalizeDeg(Math.toDegrees(atan2(dx, dy))))
}

private val LABELS = listOf("北", "北東", "東", "南東", "南", "南西", "西", "北西")

/** 方位を、8方位の言葉にする。 */
fun compassLabel(deg: Double): String = LABELS[(normalizeDeg(deg) / 45.0).roundToInt() % 8]

/** 誤差の見積もり。まだ実測していない仮の値（実際に歩いて、調整する）。 */
object ErrorModel {
    const val ANCHOR_ERR_M = 0.5 // アンカーのQRを読んだ直後の誤差（カメラとQRの距離ぶん）
    const val RATE = 0.02 // 歩いた距離に対する、誤差の増え方
    fun estimate(walkedM: Double): Double = ANCHOR_ERR_M + RATE * walkedM
    fun combined(a: Double, b: Double): Double = hypot(a, b)
}

/** QR（またはNFC）のURLから、アンカーか備品かを見分ける。 */
data class TagRef(val isAnchor: Boolean, val token: String)

private val TAG_URL = Regex("^https?://[^/\\s]+/(a|i)/([A-Za-z0-9_-]{1,40})/?(?:[?#].*)?$")

fun parseTagUrl(text: String): TagRef? {
    val m = TAG_URL.matchEntire(text.trim()) ?: return null
    return TagRef(m.groupValues[1] == "a", m.groupValues[2])
}
