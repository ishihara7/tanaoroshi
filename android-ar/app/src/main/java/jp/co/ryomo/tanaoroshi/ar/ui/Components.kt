package jp.co.ryomo.tanaoroshi.ar.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** 大きな主ボタン（手袋や片手でも押せる、56dp 以上の高さ）。 */
@Composable
fun PrimaryButton(label: String, modifier: Modifier = Modifier, enabled: Boolean = true, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.fillMaxWidth().heightIn(min = 56.dp),
        shape = MaterialTheme.shapes.medium,
    ) { Text(label, fontSize = 17.sp, fontWeight = FontWeight.Bold) }
}

@Composable
fun SecondaryButton(label: String, modifier: Modifier = Modifier, enabled: Boolean = true, onClick: () -> Unit) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.fillMaxWidth().heightIn(min = 52.dp),
        shape = MaterialTheme.shapes.medium,
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
    ) { Text(label, fontSize = 16.sp, fontWeight = FontWeight.Medium) }
}

@Composable
fun DangerButton(label: String, modifier: Modifier = Modifier, enabled: Boolean = true, onClick: () -> Unit) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.fillMaxWidth().heightIn(min = 52.dp),
        shape = MaterialTheme.shapes.medium,
        colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.error),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.error.copy(alpha = 0.5f)),
    ) { Text(label, fontSize = 16.sp, fontWeight = FontWeight.Medium) }
}

@Composable
fun SectionLabel(text: String, modifier: Modifier = Modifier) {
    Text(
        text,
        modifier = modifier.padding(top = 20.dp, bottom = 8.dp),
        style = MaterialTheme.typography.labelLarge,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        fontWeight = FontWeight.Bold,
    )
}

@Composable
fun AppCard(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Card(
        modifier = modifier.fillMaxWidth(),
        shape = MaterialTheme.shapes.medium,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
    ) { content() }
}

enum class Tone { OK, WARN, INFO, ERROR }

/** 状態を、色と短い言葉で示す丸いバッジ。 */
@Composable
fun StatusBadge(text: String, tone: Tone, modifier: Modifier = Modifier) {
    val sc = LocalStatusColors.current
    val cs = MaterialTheme.colorScheme
    val (bg, fg) = when (tone) {
        Tone.OK -> sc.successContainer to sc.onSuccessContainer
        Tone.WARN -> sc.warnContainer to sc.onWarnContainer
        Tone.INFO -> cs.primaryContainer to cs.onPrimaryContainer
        Tone.ERROR -> cs.error.copy(alpha = 0.15f).compositeOver(cs.surface) to cs.error
    }
    Surface(modifier = modifier, shape = CircleShape, color = bg) {
        Row(Modifier.padding(horizontal = 12.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(8.dp).background(fg, CircleShape))
            Spacer(Modifier.width(8.dp))
            Text(text, color = fg, fontSize = 13.sp, fontWeight = FontWeight.Bold, maxLines = 1, softWrap = false)
        }
    }
}

private fun Color.compositeOver(background: Color): Color {
    val a = alpha
    return Color(red * a + background.red * (1 - a), green * a + background.green * (1 - a), blue * a + background.blue * (1 - a))
}

/** メッセージ（成功は緑、注意は橙）。 */
@Composable
fun MessageBanner(text: String, ok: Boolean, modifier: Modifier = Modifier) {
    if (text.isBlank()) return
    val sc = LocalStatusColors.current
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = MaterialTheme.shapes.small,
        color = if (ok) sc.successContainer else sc.warnContainer,
    ) {
        Text(
            text,
            Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
            color = if (ok) sc.onSuccessContainer else sc.onWarnContainer,
            fontSize = 15.sp,
            fontWeight = FontWeight.Medium,
        )
    }
}

/** 手順の進み具合。済み＝✓、いま＝強調、これから＝薄く。 */
@Composable
fun Stepper(steps: List<String>, current: Int, modifier: Modifier = Modifier) {
    val cs = MaterialTheme.colorScheme
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        steps.forEachIndexed { i, text ->
            val done = i < current
            val now = i == current
            Row(
                Modifier
                    .fillMaxWidth()
                    .background(if (now) cs.primaryContainer else Color.Transparent, MaterialTheme.shapes.small)
                    .padding(horizontal = 10.dp, vertical = if (now) 10.dp else 6.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box(
                    Modifier.size(26.dp).background(
                        when {
                            done -> LocalStatusColors.current.success
                            now -> cs.primary
                            else -> cs.surfaceVariant
                        },
                        CircleShape,
                    ),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        if (done) "✓" else "${i + 1}",
                        color = if (done || now) Color.White else cs.onSurfaceVariant,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Bold,
                    )
                }
                Spacer(Modifier.width(12.dp))
                Text(
                    text,
                    fontSize = if (now) 16.sp else 14.sp,
                    fontWeight = if (now) FontWeight.Bold else FontWeight.Normal,
                    color = when {
                        now -> cs.onPrimaryContainer
                        done -> cs.onSurfaceVariant
                        else -> cs.onSurfaceVariant.copy(alpha = 0.75f)
                    },
                )
            }
        }
    }
}

/** 備品の方向を指す矢印。angleDeg：画面の上を0°とした、時計回りの角度。 */
@Composable
fun ArrowCompass(angleDeg: Float, active: Boolean, modifier: Modifier = Modifier) {
    val ring = MaterialTheme.colorScheme.outline
    val arrow = if (active) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline
    val dot = MaterialTheme.colorScheme.onSurfaceVariant
    Canvas(modifier) {
        val c = Offset(size.width / 2f, size.height / 2f)
        val r = minOf(c.x, c.y) - 4.dp.toPx()
        drawCircle(ring, r, c, style = Stroke(width = 3.dp.toPx()))
        drawCircle(ring, r / 2f, c, style = Stroke(width = 2.dp.toPx()))
        if (active) {
            rotate(angleDeg, c) {
                val path = Path().apply {
                    moveTo(c.x, c.y - r * 0.85f)
                    lineTo(c.x - r * 0.24f, c.y + r * 0.12f)
                    lineTo(c.x, c.y - r * 0.02f)
                    lineTo(c.x + r * 0.24f, c.y + r * 0.12f)
                    close()
                }
                drawPath(path, arrow)
            }
        }
        drawCircle(dot, 5.dp.toPx(), c)
    }
}

/** 備品の1行。選べる場合は、全体が押せる。 */
@Composable
fun AssetRow(name: String, detail: String, selected: Boolean = false, onClick: (() -> Unit)? = null, trailing: @Composable () -> Unit = {}) {
    val cs = MaterialTheme.colorScheme
    Row(
        Modifier
            .fillMaxWidth()
            .background(if (selected) cs.primaryContainer else cs.surface, MaterialTheme.shapes.small)
            .let { if (onClick != null) it.clickable(onClick = onClick) else it }
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(name, fontSize = 16.sp, fontWeight = FontWeight.Bold, color = if (selected) cs.onPrimaryContainer else cs.onSurface)
            Text(detail, fontSize = 13.sp, color = cs.onSurfaceVariant)
        }
        trailing()
    }
}
