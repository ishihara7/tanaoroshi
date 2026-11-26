package jp.co.ryomo.tanaoroshi.ar.ui

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import jp.co.ryomo.tanaoroshi.ar.PlacedItem
import jp.co.ryomo.tanaoroshi.ar.distanceAndBearing
import jp.co.ryomo.tanaoroshi.ar.shortLabel
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.sin

/** 備品の1つを、いまの位置・向きから見たもの。 */
private class Seen(val item: PlacedItem, val distM: Double, val relDeg: Double, val confirmed: Boolean)

/** 角度の差を、-180〜180 にする。 */
private fun wrap(deg: Double): Double {
    var d = deg % 360.0
    if (d > 180) d -= 360
    if (d < -180) d += 360
    return d
}

private fun seen(items: List<PlacedItem>, confirmed: Set<String>, x: Double, y: Double, headingDeg: Double) =
    items.map {
        val (d, b) = distanceAndBearing(x, y, it.placed.x, it.placed.y)
        Seen(it, d, wrap(b - headingDeg), it.token in confirmed)
    }

@Composable
private fun pulse(): Float {
    val t = rememberInfiniteTransition(label = "ghost")
    val a by t.animateFloat(
        initialValue = 0.35f, targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(800, easing = LinearEasing), RepeatMode.Reverse), label = "pulse",
    )
    return a
}

/** カメラ映像の上に重ねる、ゴースト。視野（左右 ±27°）の中にある備品を、向きに合わせた横位置に出す。 */
@Composable
fun GhostMarkers(
    items: List<PlacedItem>, confirmed: Set<String>,
    x: Double, y: Double, headingDeg: Double,
    targetToken: String?,
    labelMode: jp.co.ryomo.tanaoroshi.ar.LabelMode = jp.co.ryomo.tanaoroshi.ar.LabelMode.NAME,
    modifier: Modifier = Modifier,
) {
    val sc = LocalStatusColors.current
    val blink = pulse()
    val all = seen(items, confirmed, x, y, headingDeg)
    val half = 27.0
    BoxWithConstraints(modifier.fillMaxSize()) {
        val w = maxWidth
        val inView = all.filter { abs(it.relDeg) <= half }
        inView.forEach { s ->
            // 端に寄りすぎると、チップが切れて、端の件数表示と重なる。内側に収める
            val fx = (0.5 + s.relDeg / (2 * half)).toFloat().coerceIn(0.28f, 0.72f)
            // 遠いほど、少し上（地平線寄り）に出す。近いほど大きく
            val near = (1.0 - (s.distM / 15.0)).coerceIn(0.0, 1.0).toFloat()
            val color = if (s.confirmed) sc.success else MaterialTheme.colorScheme.error
            val isTarget = s.item.token == targetToken
            Box(
                Modifier
                    .align(Alignment.Center)
                    .offset(x = w * (fx - 0.5f), y = (-10).dp + 30.dp * (near - 0.5f))
                    .alpha(if (s.confirmed) 0.9f else blink)
                    .background(color.copy(alpha = 0.78f), MaterialTheme.shapes.small)
                    .padding(horizontal = (6 + 6 * near).dp, vertical = (3 + 3 * near).dp),
            ) {
                Text(
                    (if (isTarget) "★ " else "") + s.item.placed.shortLabel(labelMode) + "  %.0f m".format(s.distM),
                    color = Color.White, fontSize = (10 + 3 * near).sp, fontWeight = FontWeight.Bold,
                )
            }
        }
        // 視野の外にあるものは、左右の端に、件数で知らせる
        val left = all.count { it.relDeg < -half }
        val right = all.count { it.relDeg > half }
        if (left > 0) EdgeCount("◀ $left", Modifier.align(Alignment.CenterStart))
        if (right > 0) EdgeCount("$right ▶", Modifier.align(Alignment.CenterEnd))
    }
}

@Composable
private fun EdgeCount(text: String, modifier: Modifier) {
    Text(
        text,
        modifier = modifier.padding(4.dp).background(Color(0x99000000), MaterialTheme.shapes.small).padding(horizontal = 8.dp, vertical = 4.dp),
        color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.Bold,
    )
}

/**
 * 上から見た図。自分が中央で、向いている方向が上。
 * 確かめていない備品は、赤く点滅する（ゴースト）。確かめた備品は、緑の実線。
 */
@Composable
fun GhostRadar(
    items: List<PlacedItem>, confirmed: Set<String>,
    x: Double, y: Double, headingDeg: Double,
    targetToken: String?,
    route: List<jp.co.ryomo.tanaoroshi.ar.RoutePoint>,
    modifier: Modifier = Modifier,
) {
    val cs = MaterialTheme.colorScheme
    val sc = LocalStatusColors.current
    val blink = pulse()
    val all = seen(items, confirmed, x, y, headingDeg)
    // 一番遠い備品が入るように、縮尺を決める（最小 5 m）
    val range = (all.maxOfOrNull { it.distM } ?: 5.0).coerceAtLeast(5.0) * 1.15
    Canvas(modifier) {
        val c = Offset(size.width / 2f, size.height / 2f)
        val r = minOf(c.x, c.y) - 8.dp.toPx()
        drawCircle(cs.outline, r, c, style = Stroke(1.5.dp.toPx()))
        drawCircle(cs.outlineVariant, r / 2f, c, style = Stroke(1.dp.toPx()))

        fun pos(distM: Double, relDeg: Double): Offset {
            val rad = Math.toRadians(relDeg)
            val k = (distM / range).toFloat() * r
            return Offset(c.x + k * sin(rad).toFloat(), c.y - k * cos(rad).toFloat())
        }

        // 巡回の順路（これから行く順）
        if (route.isNotEmpty()) {
            var prev = c
            route.forEach { p ->
                val (d, b) = distanceAndBearing(x, y, p.x, p.y)
                val q = pos(d, wrap(b - headingDeg))
                drawLine(cs.primary.copy(alpha = 0.6f), prev, q, strokeWidth = 2.dp.toPx())
                prev = q
            }
        }

        all.forEach { s ->
            val o = pos(s.distM, s.relDeg)
            val isTarget = s.item.token == targetToken
            if (s.confirmed) {
                drawCircle(sc.success, 7.dp.toPx(), o)
            } else {
                drawCircle(cs.error.copy(alpha = 0.25f * blink), 11.dp.toPx(), o)
                drawCircle(cs.error.copy(alpha = blink), 7.dp.toPx(), o, style = Stroke(2.dp.toPx()))
            }
            if (isTarget) drawCircle(cs.primary, 13.dp.toPx(), o, style = Stroke(2.5.dp.toPx()))
        }

        // 自分（上向きの三角）
        val t = 9.dp.toPx()
        val tri = androidx.compose.ui.graphics.Path().apply {
            moveTo(c.x, c.y - t * 1.3f); lineTo(c.x - t, c.y + t); lineTo(c.x + t, c.y + t); close()
        }
        drawPath(tri, cs.primary)
    }
}
