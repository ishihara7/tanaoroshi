package jp.co.ryomo.tanaoroshi.ar

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.sin
import kotlin.math.sqrt

/** ARの水平方向（fx, fz）の向きを、ARの-Z（カメラの初期の前）を0°とした時計回りの角度にする。 */
fun arYawDeg(fx: Double, fz: Double): Double = Math.toDegrees(atan2(fx, -fz))

/**
 * ARCoreの追跡が途切れている間の、橋渡し。歩数とジャイロの向き（磁力計は使わない）で、進んだぶんを見積もる。
 *
 * 向きは、ジャイロの相対的な向き。追跡できている間は、ARの向きとの差（offset）を保ち続け、
 * 途切れたら、その差を固定して、ジャイロの向きをARの向きに直して使う。
 */
class PdrBridge(context: Context) : SensorEventListener {
    private val manager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    private val lock = Any()

    @Volatile private var headingDeg = Double.NaN
    @Volatile private var offsetDeg = Double.NaN
    @Volatile private var bridging = false

    // 区間の、ARの座標での進んだぶん
    private var dx = 0.0
    private var dz = 0.0
    private var steps = 0

    // 歩数の検出
    private var gravityLp = 9.8
    private var prev1 = 0.0
    private var prev2 = 0.0
    private var lastStepAt = 0L

    /** 使えるセンサーがあるか */
    var available = false
        private set

    fun start() {
        val rot = manager.getDefaultSensor(Sensor.TYPE_GAME_ROTATION_VECTOR)
            ?: manager.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)
        val acc = manager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
        available = rot != null && acc != null
        if (rot != null) manager.registerListener(this, rot, SensorManager.SENSOR_DELAY_GAME)
        if (acc != null) manager.registerListener(this, acc, SensorManager.SENSOR_DELAY_GAME)
    }

    fun stop() {
        manager.unregisterListener(this)
    }

    /** 追跡できているフレームごとに呼ぶ。ARの向きと、ジャイロの向きの差を、更新する。 */
    fun calibrate(arYaw: Double) {
        val h = headingDeg
        if (!h.isNaN()) offsetDeg = normalizeDeg(arYaw - h)
    }

    /** 追跡が途切れた瞬間に呼ぶ。 */
    fun begin() {
        synchronized(lock) { dx = 0.0; dz = 0.0; steps = 0 }
        bridging = !offsetDeg.isNaN()
    }

    /** 追跡が戻ったときに呼ぶ。途切れていた間に進んだぶん（ARの座標のdx, dz）と、歩数を返す。 */
    fun end(): Triple<Double, Double, Int> {
        bridging = false
        return synchronized(lock) { Triple(dx, dz, steps) }
    }

    fun stepsSoFar(): Int = synchronized(lock) { steps }

    override fun onSensorChanged(e: SensorEvent) {
        when (e.sensor.type) {
            Sensor.TYPE_GAME_ROTATION_VECTOR, Sensor.TYPE_ROTATION_VECTOR -> {
                val r = FloatArray(9)
                SensorManager.getRotationMatrixFromVector(r, e.values)
                // 端末の-Z（カメラの向き）を、世界の座標にする
                val x = -r[2].toDouble()
                val y = -r[5].toDouble()
                if (hypot(x, y) > 0.2) headingDeg = normalizeDeg(Math.toDegrees(atan2(x, y)))
            }
            Sensor.TYPE_ACCELEROMETER -> detectStep(e)
        }
    }

    private fun detectStep(e: SensorEvent) {
        val mag = sqrt((e.values[0] * e.values[0] + e.values[1] * e.values[1] + e.values[2] * e.values[2]).toDouble())
        gravityLp += 0.1 * (mag - gravityLp)
        val hp = mag - gravityLp
        val peak = prev1 > STEP_THRESHOLD && prev1 > prev2 && prev1 >= hp
        val nowMs = e.timestamp / 1_000_000L
        if (peak && nowMs - lastStepAt > STEP_MIN_INTERVAL_MS) {
            lastStepAt = nowMs
            addStep()
        }
        prev2 = prev1
        prev1 = hp
    }

    private fun addStep() {
        if (!bridging) return
        val h = headingDeg
        val o = offsetDeg
        if (h.isNaN() || o.isNaN()) return
        val yaw = Math.toRadians(h + o)
        synchronized(lock) {
            dx += sin(yaw) * STRIDE_M
            dz += -cos(yaw) * STRIDE_M
            steps++
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit

    companion object {
        const val STRIDE_M = 0.7
        private const val STEP_THRESHOLD = 1.5 // 重力を除いた加速度の山（m/s²）
        private const val STEP_MIN_INTERVAL_MS = 350L

        fun distanceOf(dx: Double, dz: Double) = abs(hypot(dx, dz))
    }
}
