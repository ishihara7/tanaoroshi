package jp.co.ryomo.tanaoroshi.ar.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

/** 成功・注意・エラーなど、意味のある色（Material3 の標準にない分）。 */
class StatusColors(
    val success: Color,
    val onSuccessContainer: Color,
    val successContainer: Color,
    val warn: Color,
    val onWarnContainer: Color,
    val warnContainer: Color,
)

private val LightStatus = StatusColors(
    success = Color(0xFF047857), onSuccessContainer = Color(0xFF065F46), successContainer = Color(0xFFD1FAE5),
    warn = Color(0xFFB45309), onWarnContainer = Color(0xFF92400E), warnContainer = Color(0xFFFEF3C7),
)
private val DarkStatus = StatusColors(
    success = Color(0xFF34D399), onSuccessContainer = Color(0xFFA7F3D0), successContainer = Color(0xFF064E3B),
    warn = Color(0xFFFBBF24), onWarnContainer = Color(0xFFFDE68A), warnContainer = Color(0xFF78350F),
)

val LocalStatusColors = staticCompositionLocalOf { LightStatus }

private val LightScheme = lightColorScheme(
    primary = Color(0xFF1A56DB), onPrimary = Color.White,
    primaryContainer = Color(0xFFE0E7FF), onPrimaryContainer = Color(0xFF1E3A8A),
    background = Color(0xFFF4F6F8), onBackground = Color(0xFF111827),
    surface = Color.White, onSurface = Color(0xFF111827),
    surfaceVariant = Color(0xFFE9EDF2), onSurfaceVariant = Color(0xFF4B5563),
    outline = Color(0xFFCBD5E1), outlineVariant = Color(0xFFE2E8F0),
    error = Color(0xFFB91C1C), onError = Color.White,
)
private val DarkScheme = darkColorScheme(
    primary = Color(0xFF8AB4FF), onPrimary = Color(0xFF0B1F4D),
    primaryContainer = Color(0xFF1E3A8A), onPrimaryContainer = Color(0xFFDBE4FF),
    background = Color(0xFF0F1419), onBackground = Color(0xFFE5E7EB),
    surface = Color(0xFF1A2027), onSurface = Color(0xFFE5E7EB),
    surfaceVariant = Color(0xFF262E37), onSurfaceVariant = Color(0xFF9CA3AF),
    outline = Color(0xFF3B4551), outlineVariant = Color(0xFF2B343E),
    error = Color(0xFFF87171), onError = Color(0xFF450A0A),
)

private val AppShapes = Shapes(
    small = RoundedCornerShape(10.dp),
    medium = RoundedCornerShape(16.dp),
    large = RoundedCornerShape(24.dp),
)

@Composable
fun TanaoroshiTheme(content: @Composable () -> Unit) {
    val dark = isSystemInDarkTheme()
    CompositionLocalProvider(LocalStatusColors provides if (dark) DarkStatus else LightStatus) {
        MaterialTheme(
            colorScheme = if (dark) DarkScheme else LightScheme,
            shapes = AppShapes,
            content = content,
        )
    }
}
