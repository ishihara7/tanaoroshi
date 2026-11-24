package jp.co.ryomo.tanaoroshi.ar

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.view.View

/** 備品の方向を指す矢印。angleDeg：画面の上を0°とした、時計回りの角度。 */
class ArrowView(context: Context) : View(context) {
    private val ring = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 6f
        color = 0xFFCBD5E1.toInt()
    }
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF1A56DB.toInt() }
    private val dot = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF475569.toInt() }

    var angleDeg: Float = 0f
        set(value) {
            field = value
            invalidate()
        }

    override fun onDraw(canvas: Canvas) {
        val cx = width / 2f
        val cy = height / 2f
        val r = minOf(cx, cy) - 6f
        canvas.drawCircle(cx, cy, r, ring)
        canvas.drawCircle(cx, cy, r / 2f, ring)
        canvas.save()
        canvas.rotate(angleDeg, cx, cy)
        val path = Path().apply {
            moveTo(cx, cy - r * 0.85f) // 先端
            lineTo(cx - r * 0.22f, cy + r * 0.1f)
            lineTo(cx + r * 0.22f, cy + r * 0.1f)
            close()
        }
        canvas.drawPath(path, fill)
        canvas.restore()
        canvas.drawCircle(cx, cy, 10f, dot)
    }
}
