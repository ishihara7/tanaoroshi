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

/** 角度の差を、-180〜180 にする。 */
fun signedDiffDeg(deg: Double): Double {
    val d = normalizeDeg(deg)
    return if (d > 180.0) d - 360.0 else d
}

/**
 * 追跡が戻ったとき、ARCoreの座標系が変わったか（リセットされたか）を調べる。
 * 追跡できている間は、ARの向きとジャイロの向きの差（offset）が一定に保たれる。
 * 復帰後にその差が大きく変わっていたら、座標系が変わったと見なす。
 * @return 食い違い（度、-180〜180）
 */
fun yawMismatchDeg(arYawNow: Double, gyroNow: Double, offset: Double): Double =
    signedDiffDeg(arYawNow - (gyroNow + offset))

/** 座標系が変わったとみなす、向きの食い違い（度）。ジャイロのドリフト（数十秒で数度）より、十分大きく取る */
const val FRAME_RESET_DEG = 20.0

/** 途切れる前の方角に、途切れている間にジャイロが回った量を足して、いまの方角にする。ARCoreの座標系には頼らない。 */
fun bearingAfterLoss(bearingBefore: Double, gyroAtLoss: Double, gyroNow: Double): Double =
    normalizeDeg(bearingBefore + signedDiffDeg(gyroNow - gyroAtLoss))

/**
 * 2つの目印の間を歩いたとき、ARで測った移動の向き（地図上の方位に直したもの）と、
 * 目印の登録位置から求めた向きの差を、回転の補正量（度）として返す。
 * 近すぎる・距離が合わない・差が大きすぎるときは、信用できないので null。
 */
fun rotationCorrectionDeg(
    arBearing: Double, arDistM: Double,
    fromX: Double, fromY: Double, toX: Double, toY: Double,
): Double? {
    val (mapDist, mapBearing) = distanceAndBearing(fromX, fromY, toX, toY)
    if (mapDist < MIN_FIX_BASE_M || arDistM < MIN_FIX_BASE_M) return null
    val ratio = arDistM / mapDist
    if (ratio < 0.6 || ratio > 1.6) return null
    val delta = signedDiffDeg(mapBearing - arBearing)
    return if (Math.abs(delta) > MAX_FIX_DEG) null else delta
}

/** 向きを直すのに必要な、2つの目印の最小の間隔（m）。近いと、位置の誤差で向きが大きく狂う */
const val MIN_FIX_BASE_M = 2.0

/** 一度に直す向きの上限（度）。これより大きい食い違いは、目印の取り違えなどと見なす */
const val MAX_FIX_DEG = 45.0

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

/** 管理画面の「端末の登録」のQR。server：サーバーのアドレス（http(s)://ホスト:ポート）、code：設定コード。 */
data class SetupRef(val server: String, val code: String)

private val SETUP_URL = Regex("^(https?://[^/\\s]+)/setup/([A-Za-z0-9_-]{16,64})/?$")

fun parseSetupUrl(text: String): SetupRef? {
    val m = SETUP_URL.matchEntire(text.trim()) ?: return null
    return SetupRef(m.groupValues[1], m.groupValues[2])
}

fun parseTagUrl(text: String): TagRef? {
    val m = TAG_URL.matchEntire(text.trim()) ?: return null
    return TagRef(m.groupValues[1] == "a", m.groupValues[2])
}
