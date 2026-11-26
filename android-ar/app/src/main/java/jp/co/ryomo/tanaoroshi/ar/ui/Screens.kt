package jp.co.ryomo.tanaoroshi.ar.ui

import android.app.AlertDialog
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.positionInRoot
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import jp.co.ryomo.tanaoroshi.ar.AppModel
import jp.co.ryomo.tanaoroshi.ar.ErrorModel
import jp.co.ryomo.tanaoroshi.ar.LOW_POINTS
import jp.co.ryomo.tanaoroshi.ar.Screen
import jp.co.ryomo.tanaoroshi.ar.Settings
import jp.co.ryomo.tanaoroshi.ar.SyncState
import jp.co.ryomo.tanaoroshi.ar.SyncStatus
import jp.co.ryomo.tanaoroshi.ar.compassLabel
import jp.co.ryomo.tanaoroshi.ar.distanceAndBearing
import jp.co.ryomo.tanaoroshi.ar.floorLabel
import jp.co.ryomo.tanaoroshi.ar.label

/** カメラ映像の縦横比（幅:高さ = 3:4）。切り取らずに、視野の全体を出す。 */
private const val CAMERA_ASPECT = 3f / 4f

/** 横向きのときの、カメラ映像の比率（幅÷高さ）。 */
private const val CAMERA_ASPECT_LANDSCAPE = 4f / 3f

/** 画面の中身の最大幅（タブレットで間延びしないように）。 */
private val CONTENT_MAX_WIDTH = 640.dp

/** カメラ映像の置き場所（ピクセル）。 */
data class CameraRect(val x: Int, val y: Int, val w: Int, val h: Int)

// ---------------- ホーム ----------------

@Composable
fun HomeScreen(model: AppModel) {
    val cs = MaterialTheme.colorScheme
    Box(
        Modifier.fillMaxSize().background(cs.background).windowInsetsPadding(WindowInsets.safeDrawing),
        contentAlignment = Alignment.TopCenter,
    ) {
        Column(
            Modifier.widthIn(max = CONTENT_MAX_WIDTH).fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 16.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("備品の位置", fontSize = 28.sp, fontWeight = FontWeight.Bold, color = cs.onBackground)
                    Text("備品を登録し、棚卸で確かめる", fontSize = 14.sp, color = cs.onSurfaceVariant)
                }
                TextButton(onClick = { model.go(Screen.SETTINGS) }) { Text("設定", fontSize = 16.sp) }
            }
            Spacer(Modifier.height(16.dp))

            AppCard {
                Row(Modifier.padding(20.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("登録済みの備品", fontSize = 14.sp, color = cs.onSurfaceVariant)
                        Row(verticalAlignment = Alignment.Bottom) {
                            Text("${model.items.size}", fontSize = 44.sp, fontWeight = FontWeight.Bold, color = cs.primary)
                            Text(" 件", fontSize = 18.sp, modifier = Modifier.padding(bottom = 8.dp), color = cs.onSurfaceVariant)
                        }
                    }
                    StatusBadge(
                        text = model.floor?.takeIf { model.hasRef }?.let { "${floorLabel(it)}で合わせ済み" } ?: "位置は未設定",
                        tone = if (model.hasRef) Tone.OK else Tone.INFO,
                    )
                }
            }
            Spacer(Modifier.height(12.dp))
            SyncPanel(model)
            Spacer(Modifier.height(16.dp))

            ActionCard(
                title = "備品登録モード",
                body = "アンカーのQR → 備品のQR の順に読んで、備品の位置を記録します。",
                primary = true,
                enabled = true,
            ) { model.go(Screen.REGISTER) }
            Spacer(Modifier.height(12.dp))
            val checked = model.items.count { it.token in model.confirmed }
            ActionCard(
                title = "棚卸モード",
                body = when {
                    model.items.isEmpty() -> "先に、備品を登録してください。"
                    checked == 0 -> "備品のQRを読んで、確かめます。読んでいない備品は、ゴーストで見えます。"
                    else -> "確かめ済み $checked / ${model.items.size} 件。続きから再開します。"
                },
                primary = false,
                enabled = model.items.isNotEmpty(),
            ) { model.go(Screen.INVENTORY) }

            if (model.items.isNotEmpty()) {
                SectionLabel("最近の登録")
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    model.items.takeLast(3).reversed().forEach {
                        AssetRow(it.placed.label(), "%s　東%.1f m　北%.1f m　（±%.1f m）".format(floorLabel(it.placed.floor), it.placed.x, it.placed.y, it.placed.errM))
                    }
                }
            }
        }
    }
}

@Composable
private fun ActionCard(title: String, body: String, primary: Boolean, enabled: Boolean, onClick: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    val bg = if (primary) cs.primary else cs.surface
    val fg = if (primary) cs.onPrimary else cs.onSurface
    Column(
        Modifier
            .fillMaxWidth()
            .background(bg.copy(alpha = if (enabled) 1f else 0.5f), MaterialTheme.shapes.medium)
            .clickable(enabled = enabled, onClick = onClick)
            .padding(horizontal = 20.dp, vertical = 22.dp),
    ) {
        Text(title, fontSize = 22.sp, fontWeight = FontWeight.Bold, color = fg)
        Spacer(Modifier.height(4.dp))
        Text(body, fontSize = 14.sp, color = fg.copy(alpha = 0.85f))
    }
}

// ---------------- カメラ付きの画面の枠 ----------------

/**
 * 上：戻る・題名・追跡の状態。その下：カメラ映像（3:4）。残り：操作の部分（スクロール）。
 * カメラ映像の置き場所は、onCamera で、外（本物のGLSurfaceView）へ知らせる。
 */
@Composable
private fun CameraShell(
    model: AppModel,
    title: String,
    ghost: Boolean,
    onCamera: (CameraRect) -> Unit,
    content: @Composable () -> Unit,
) {
    val cs = MaterialTheme.colorScheme
    BoxWithConstraints(Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing)) {
        val cameraBox: @Composable (Dp, Dp) -> Unit = { w, h ->
            Box(
                Modifier.size(w, h).onGloballyPositioned {
                    val p = it.positionInRoot()
                    onCamera(CameraRect(p.x.toInt(), p.y.toInt(), it.size.width, it.size.height))
                },
            ) { CameraOverlay(model, ghost) }
        }
        val scrolling: @Composable () -> Unit = {
            Column(
                Modifier.widthIn(max = CONTENT_MAX_WIDTH).fillMaxSize().verticalScroll(rememberScrollState())
                    .padding(horizontal = 16.dp, vertical = 12.dp),
            ) { content() }
        }
        if (maxWidth > maxHeight) {
            // 横向き：左にカメラ（4:3の横長）、右に操作。カメラの場所だけ塗らずに、穴にする（後ろの映像を見せる）
            Row(Modifier.fillMaxSize()) {
                Column(Modifier.weight(1f).fillMaxHeight()) {
                    CameraHeader(model, title)
                    BoxWithConstraints(Modifier.weight(1f).fillMaxWidth()) {
                        val camW: Dp = minOf(maxWidth, maxHeight * CAMERA_ASPECT_LANDSCAPE)
                        val camH: Dp = camW / CAMERA_ASPECT_LANDSCAPE
                        val padTop: Dp = (maxHeight - camH) / 2
                        val padLeft: Dp = (maxWidth - camW) / 2
                        Column(Modifier.fillMaxSize()) {
                            Box(Modifier.fillMaxWidth().height(padTop).background(cs.background))
                            Row(Modifier.fillMaxWidth().height(camH)) {
                                Box(Modifier.width(padLeft).fillMaxHeight().background(cs.background))
                                cameraBox(camW, camH)
                                Box(Modifier.weight(1f).fillMaxHeight().background(cs.background))
                            }
                            Box(Modifier.weight(1f).fillMaxWidth().background(cs.background))
                        }
                    }
                }
                Box(Modifier.weight(1f).fillMaxHeight().background(cs.background), contentAlignment = Alignment.TopCenter) { scrolling() }
            }
        } else {
            // 縦向き：上にカメラ（3:4の縦長）、下に操作
            val camH: Dp = minOf(maxHeight * 0.42f, maxWidth / CAMERA_ASPECT)
            val camW: Dp = camH * CAMERA_ASPECT
            Column(Modifier.fillMaxSize()) {
                CameraHeader(model, title)
                // カメラの左右は、背景色で塗り、中央は、穴（映像が見える）にする
                Row(Modifier.fillMaxWidth().height(camH)) {
                    Box(Modifier.weight(1f).fillMaxHeight().background(cs.background))
                    cameraBox(camW, camH)
                    Box(Modifier.weight(1f).fillMaxHeight().background(cs.background))
                }
                Box(Modifier.weight(1f).fillMaxWidth().background(cs.background), contentAlignment = Alignment.TopCenter) { scrolling() }
            }
        }
    }
}

/** 戻るボタン・題名・追跡の状態。 */
@Composable
private fun CameraHeader(model: AppModel, title: String) {
    val cs = MaterialTheme.colorScheme
    Row(
        Modifier.fillMaxWidth().background(cs.background).padding(horizontal = 8.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.width(120.dp), contentAlignment = Alignment.CenterStart) { TextButton(onClick = { model.go(Screen.HOME) }) { Text("‹ 戻る", fontSize = 16.sp) } }
        Text(title, fontSize = 20.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f), textAlign = TextAlign.Center)
        Box(Modifier.width(120.dp), contentAlignment = Alignment.CenterEnd) { TrackingBadge(model) }
    }
}

@Composable
private fun TrackingBadge(model: AppModel) {
    val l = model.live
    // 幅の狭い所に置くので、短い言葉にする
    when {
        !l.tracking -> StatusBadge("追跡中断", Tone.WARN)
        l.lostTracking -> StatusBadge("要再合わせ", Tone.WARN)
        else -> StatusBadge("追跡中", Tone.OK)
    }
}

/** カメラ映像の上に重ねる情報（歩いた距離・特徴点の警告）。 */
@Composable
private fun CameraOverlay(model: AppModel, ghost: Boolean) {
    val l = model.live
    val gx = l.mapX
    val gy = l.mapY
    val gb = l.bearing
    if (ghost && gx != null && gy != null && gb != null && l.tracking && model.mapItems.isNotEmpty()) {
        GhostMarkers(model.mapItems, model.confirmed, gx, gy, gb, model.targetToken)
    }
    Box(Modifier.fillMaxSize().padding(8.dp)) {
        if (l.mapX != null && l.mapY != null) {
            Text(
                "%.0f m歩行　±%.1f m".format(l.walkedM, ErrorModel.estimate(l.walkedM)),
                modifier = Modifier.align(Alignment.BottomStart).background(androidx.compose.ui.graphics.Color(0x99000000), MaterialTheme.shapes.small)
                    .padding(horizontal = 10.dp, vertical = 4.dp),
                color = androidx.compose.ui.graphics.Color.White,
                fontSize = 12.sp,
            )
        }
        if (l.tracking && l.points in 0..LOW_POINTS) {
            StatusBadge("特徴が少ない", Tone.WARN, Modifier.align(Alignment.TopStart))
        }
        // いまの階（アンカーを読むと決まる）
        val f = model.floor
        StatusBadge(
            if (f != null) floorLabel(f) else "階は未確定",
            if (f != null) Tone.INFO else Tone.WARN,
            Modifier.align(Alignment.TopEnd),
        )
    }
}

/** 追跡の状態を、文章で（失敗の理由や、やり直しの案内）。 */
@Composable
private fun TrackingNote(model: AppModel) {
    val l = model.live
    val text = when {
        !l.tracking -> l.trackingNote
        l.lostTracking -> "追跡が途切れました。アンカー、または登録済みの備品のQRを読んで、位置を合わせ直してください。"
        l.points in 0..LOW_POINTS -> "壁や床ばかり映っています。棚・机・柱など、模様のあるものが映るように向けてください。"
        l.mapX == null -> l.trackingNote
        else -> ""
    }
    if (text.isNotBlank()) {
        Text(text, fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(vertical = 6.dp))
    }
}

// ---------------- 登録 ----------------

@Composable
fun RegisterScreen(model: AppModel, onCamera: (CameraRect) -> Unit) {
    CameraShell(model, "備品登録", ghost = false, onCamera = onCamera) {
        Stepper(
            steps = listOf(
                "アンカーのQRを、壁に向かって正対して読む",
                "歩いて、備品に近づく",
                "備品のQRを読む（そのときの位置が登録される）",
                "次の備品へ。全部終わったら「完了して、棚卸へ」",
            ),
            current = if (!model.hasRef) 0 else 1,
        )
        TrackingNote(model)
        MessageBanner(model.message, model.messageOk, Modifier.padding(top = 8.dp))

        SectionLabel("登録した備品（${model.items.size}件）")
        if (model.items.isEmpty()) {
            Text("まだありません。備品のQRを読むと、ここに並びます。", fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            model.items.forEach {
                AssetRow(
                    name = it.placed.label(),
                    detail = "%s　東%.1f m　北%.1f m　（±%.1f m）".format(floorLabel(it.placed.floor), it.placed.x, it.placed.y, it.placed.errM),
                ) { TextButton(onClick = { model.removeItem(it.token) }) { Text("削除", color = MaterialTheme.colorScheme.error) } }
            }
        }
        Spacer(Modifier.height(16.dp))
        PrimaryButton("完了して、棚卸へ", enabled = model.items.isNotEmpty()) { model.go(Screen.INVENTORY) }
    }
}

// ---------------- 棚卸 ----------------

@Composable
fun InventoryScreen(model: AppModel, onCamera: (CameraRect) -> Unit) {
    val cs = MaterialTheme.colorScheme
    val l = model.live
    val target = model.target()
    val total = model.floorItems.size
    val checked = model.floorItems.count { it.token in model.confirmed }
    CameraShell(model, "棚卸", ghost = true, onCamera = onCamera) {
        // 進み具合
        AppCard {
            Column(Modifier.fillMaxWidth().padding(16.dp)) {
                Text(
                    model.floor?.let { "${floorLabel(it)}の棚卸" } ?: "階は未確定（アンカーを読んでください）",
                    fontSize = 14.sp, color = cs.onSurfaceVariant,
                )
                Row(verticalAlignment = Alignment.Bottom) {
                    Text("$checked", fontSize = 36.sp, fontWeight = FontWeight.Bold, color = if (checked == total && total > 0) LocalStatusColors.current.success else cs.primary)
                    Text(" / $total 件 確認済み", fontSize = 16.sp, color = cs.onSurfaceVariant, modifier = Modifier.padding(bottom = 6.dp).weight(1f))
                    if (checked > 0) TextButton(onClick = { model.resetConfirmed() }) { Text("最初から") }
                }
                Spacer(Modifier.height(6.dp))
                LinearProgressIndicator(
                    progress = { if (total == 0) 0f else checked.toFloat() / total },
                    modifier = Modifier.fillMaxWidth().height(8.dp),
                    color = if (checked == total && total > 0) LocalStatusColors.current.success else cs.primary,
                    trackColor = cs.surfaceVariant,
                )
                if (checked == total && total > 0) {
                    Spacer(Modifier.height(8.dp))
                    StatusBadge("棚卸は完了です", Tone.OK)
                }
            }
        }
        Spacer(Modifier.height(12.dp))
        Stepper(
            steps = listOf(
                "アンカーのQRを読んで、位置を合わせる（ゴーストが見えるようになる）",
                "備品のQRを、1つずつ読む（読んだ備品は緑になる）",
                "赤く点滅するゴースト（未確認）の場所へ歩く",
                "すべて緑になれば、棚卸は完了",
            ),
            current = when {
                total > 0 && checked == total -> 3
                !model.hasRef -> 0
                checked == 0 -> 1
                else -> 2
            },
        )
        TrackingNote(model)
        MessageBanner(model.message, model.messageOk, Modifier.padding(top = 8.dp))

        RoutePanel(model)
        ManualPanel(model)

        SectionLabel("備品の一覧（タップで、矢印と距離の案内）")
        if (model.floorItems.isEmpty()) Text("登録した備品がありません。備品登録モードで、先に登録してください。", fontSize = 14.sp, color = cs.onSurfaceVariant)
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            model.floorItems.forEach {
                AssetRow(
                    name = it.placed.label(),
                    detail = if (it.placed.located) "%s　東%.1f m　北%.1f m".format(floorLabel(it.placed.floor), it.placed.x, it.placed.y)
                    else "${floorLabel(it.placed.floor)}　位置は不明",
                    selected = it.token == model.targetToken,
                    onClick = { model.selectTarget(it.token) },
                ) {
                    Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        if (it.token in model.confirmed) StatusBadge("確認済み", Tone.OK) else StatusBadge("未確認", Tone.WARN)
                        if (it.token in model.confirmed) TextButton(onClick = { model.unconfirmItem(it.token) }) { Text("未確認に戻す", fontSize = 12.sp) }
                        if (it.token in model.moved) StatusBadge("場所違い", Tone.ERROR)
                        if (it.placed.missedLast && it.token !in model.confirmed) StatusBadge("前回未確認", Tone.WARN)
                        if (it.placed.wasUnexpected) StatusBadge("前回 想定外", Tone.INFO)
                    }
                }
            }
        }

        FinishPanel(model)

        // 案内（矢印・距離）
        val x = l.mapX
        val y = l.mapY
        val b = l.bearing
        val ready = target != null && x != null && y != null && b != null && l.tracking
        Spacer(Modifier.height(16.dp))
        AppCard {
            Column(Modifier.fillMaxWidth().padding(20.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                if (ready) {
                    val (dist, bearing) = distanceAndBearing(x!!, y!!, target!!.x, target.y)
                    ArrowCompass(angleDeg = (bearing - b!!).toFloat(), active = true, modifier = Modifier.size(220.dp))
                    Spacer(Modifier.height(8.dp))
                    Text(
                        (if (dist < 2.0) "%.1f m" else "約 %.1f m").format(dist),
                        fontSize = 48.sp, fontWeight = FontWeight.Bold, color = cs.primary,
                    )
                    Text(
                        if (dist < 2.0) "近くです。QRを探してください。" else "${compassLabel(bearing)}（${Math.round(bearing)}°）",
                        fontSize = 18.sp, color = cs.onSurface,
                    )
                    val err = ErrorModel.combined(ErrorModel.estimate(l.walkedM) + if (l.lostTracking) 5.0 else 0.0, target.errM)
                    Text("誤差の目安 ±%.1f m".format(err), fontSize = 13.sp, color = cs.onSurfaceVariant)
                } else {
                    ArrowCompass(angleDeg = 0f, active = false, modifier = Modifier.size(160.dp))
                    Spacer(Modifier.height(8.dp))
                    Text(
                        when {
                            target == null -> "一覧から備品を選ぶと、矢印で案内します。"
                            x == null -> "アンカーのQRを読み取ってください。"
                            else -> "追跡できていません。"
                        },
                        fontSize = 16.sp, color = cs.onSurfaceVariant,
                    )
                }
            }
        }
        if (x != null && y != null && b != null && model.mapItems.isNotEmpty()) {
            SectionLabel("ゴースト表示（上から見た図）")
            AppCard {
                Column(Modifier.fillMaxWidth().padding(16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    GhostRadar(model.mapItems, model.confirmed, x, y, b, model.targetToken, model.route, Modifier.size(260.dp))
                    Text(
                        "上が、いま向いている方向。赤の点滅は、まだ確かめていない備品。緑は、確かめた備品。",
                        fontSize = 12.sp, color = cs.onSurfaceVariant, modifier = Modifier.padding(top = 8.dp),
                    )
                }
            }
        }
        Text(
            "位置がずれたら、アンカーのQRを読み直してください。備品のQRを読むと、その備品が確かめ済みになります。",
            fontSize = 13.sp, color = cs.onSurfaceVariant, modifier = Modifier.padding(top = 12.dp),
        )
    }
}

// ---------------- 設定 ----------------

@Composable
fun SettingsScreen(model: AppModel) {
    val cs = MaterialTheme.colorScheme
    val s = model.settings
    val context = LocalContext.current
    var facingA by remember { mutableStateOf(s.facingA.toString()) }
    var facingB by remember { mutableStateOf(s.facingB.toString()) }
    var facingC by remember { mutableStateOf(s.facingC.toString()) }
    var camRot by remember { mutableStateOf(s.cameraRot.toString()) }
    var serverUrl by remember { mutableStateOf(s.serverUrl) }
    var loginId by remember { mutableStateOf(s.loginId) }
    var password by remember { mutableStateOf(s.password) }
    var employeeNo by remember { mutableStateOf(s.employeeNo) }
    var threshold by remember { mutableStateOf(s.movedThresholdM.toString()) }
    var manualLogin by remember { mutableStateOf(false) }
    var advanced by remember { mutableStateOf(false) }

    Box(
        Modifier.fillMaxSize().background(cs.background).windowInsetsPadding(WindowInsets.safeDrawing),
        contentAlignment = Alignment.TopCenter,
    ) {
        Column(Modifier.widthIn(max = CONTENT_MAX_WIDTH).fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                TextButton(onClick = { model.go(Screen.HOME) }) { Text("‹ 戻る", fontSize = 16.sp) }
                Text("設定", fontSize = 20.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f), textAlign = TextAlign.Center)
                Spacer(Modifier.width(72.dp))
            }
            SectionLabel("サーバー")
            Text("棚卸の記録を送り、予定とアンカーを受け取ります。電波がないときは、端末に溜めて、あとで送ります。", fontSize = 14.sp, color = cs.onSurfaceVariant)
            Spacer(Modifier.height(8.dp))
            if (s.authToken.isNotEmpty()) {
                StatusBadge("この端末は、登録済みです", Tone.OK)
                Text(s.serverUrl, fontSize = 13.sp, color = cs.onSurfaceVariant, modifier = Modifier.padding(top = 4.dp, bottom = 8.dp))
            }
            PrimaryButton(if (s.authToken.isNotEmpty()) "QRで設定し直す" else "QRで設定する") { model.go(Screen.SETUP) }
            Text(
                "PCで管理画面の「端末」→「QRを表示」を開き、そのQRを読み取ります。サーバーのアドレスとログインの設定が、自動で入ります。",
                fontSize = 13.sp, color = cs.onSurfaceVariant, modifier = Modifier.padding(top = 6.dp, bottom = 8.dp),
            )
            if (s.authToken.isNotEmpty()) {
                SecondaryButton("この端末の登録を解除する") { model.clearDeviceToken() }
                Spacer(Modifier.height(8.dp))
            }
            SecondaryButton(if (manualLogin) "IDとパスワードでの設定を閉じる" else "IDとパスワードで設定する") { manualLogin = !manualLogin }
            if (manualLogin) {
                Spacer(Modifier.height(8.dp))
                TextField("サーバーのURL", "例：https://xxxx.azurewebsites.net", serverUrl, KeyboardType.Uri) { serverUrl = it }
                TextField("ログインID", null, loginId, KeyboardType.Ascii) { loginId = it }
                TextField("パスワード", "この端末に保存されます。QRでの設定なら、パスワードは保存されません", password, KeyboardType.Password, hide = true) { password = it }
            }
            TextField("社員番号（記録した人）", "半角英数字。空でも構いません", employeeNo, KeyboardType.Ascii) { employeeNo = it }
            SyncPanel(model)

            SectionLabel("場所違いの判定")
            NumberField("しきい値（m）", "同じ階で、登録位置からこれ以上離れて読むと、場所違い。階が違えば、常に場所違い", threshold) { threshold = it }

            SectionLabel("アンカー（階ごと）")
            Text(
                if (model.serverAnchors.isNotEmpty()) "サーバーのアンカー（${model.serverAnchors.size}件）を使います。向きは、サーバーの管理画面で設定します。以下は、サーバーのアンカーがないときだけ使います。"
                else "A＝1階、B＝2階、C＝3階。階を移ったら、その階のアンカーを読み直します。",
                fontSize = 14.sp, color = cs.onSurfaceVariant,
            )
            Spacer(Modifier.height(8.dp))
            NumberField("1階（A）：壁に正対する向き（°）", "北が0、東が90。分からなければ0のままで構いません", facingA) { facingA = it }
            NumberField("2階（B）：壁に正対する向き（°）", null, facingB) { facingB = it }
            NumberField("3階（C）：壁に正対する向き（°）", null, facingC) { facingC = it }

            SectionLabel("詳細")
            SecondaryButton(if (advanced) "詳細設定を閉じる" else "詳細設定（カメラ）を開く") { advanced = !advanced }
            if (advanced) {
                Spacer(Modifier.height(8.dp))
                NumberField("カメラ映像の向きの強制", "-1は自動。映像が横向きや逆さのときだけ、0〜3を試す", camRot) { camRot = it }
            }

            Spacer(Modifier.height(20.dp))
            PrimaryButton("保存する") {
                fun num(t: String, d: Double) = t.toDoubleOrNull() ?: d
                model.saveSettings(
                    Settings(
                        facingA = num(facingA, s.facingA), facingB = num(facingB, s.facingB), facingC = num(facingC, s.facingC),
                        cameraRot = num(camRot, s.cameraRot.toDouble()).toInt().coerceIn(-1, 3),
                        serverUrl = serverUrl.trim(), loginId = loginId.trim(), password = password, employeeNo = employeeNo.trim(),
                        // IDとパスワードを入れたときは、QRで受け取った端末の合言葉は、使わない（どちらか1つ）
                        authToken = if (manualLogin && password.isNotEmpty()) "" else s.authToken,
                        movedThresholdM = num(threshold, s.movedThresholdM).coerceIn(0.5, 50.0),
                    ),
                )
                model.go(Screen.HOME)
            }
            Spacer(Modifier.height(12.dp))
            SectionLabel("データ")
            Text(
                "試用で入れたデータを、まとめて消して、初めて使うときの状態に戻します。",
                fontSize = 13.sp, color = cs.onSurfaceVariant, modifier = Modifier.padding(bottom = 8.dp),
            )
            DangerButton("すべてのデータを消す") {
                AlertDialog.Builder(context)
                    .setTitle("すべてのデータを消しますか？")
                    .setMessage(
                        "この端末の、次のデータが消えます。元に戻せません。\n" +
                            "・登録した備品（${model.items.size}件）\n" +
                            "・棚卸の進み具合（確認済み ${model.confirmed.size}件）\n" +
                            "・サーバーに送っていない記録（${model.syncStatus.pending}件）\n" +
                            "・設定（アンカーの向きなど）\n" +
                            "・アンカーで合わせた位置",
                    )
                    .setNegativeButton("やめる", null)
                    .setPositiveButton("すべて消す") { _, _ -> model.clearAllData() }
                    .show()
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun NumberField(label: String, hint: String?, value: String, onChange: (String) -> Unit) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label) },
        supportingText = hint?.let { { Text(it) } },
        singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
        modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
        shape = MaterialTheme.shapes.small,
    )
}


// ---------------- 巡回（棚卸しの順路） ----------------

/** 未確認の備品を、短い順路で巡る。QRで確かめると、次の備品へ自動で進む。 */
@Composable
private fun RoutePanel(model: AppModel) {
    val cs = MaterialTheme.colorScheme
    val unconfirmed = model.floorItems.count { it.token !in model.confirmed }
    SectionLabel("棚卸し（巡回）")
    AppCard {
        Column(Modifier.fillMaxWidth().padding(16.dp)) {
            if (!model.routeMode) {
                Text(
                    if (unconfirmed == 0) "すべて確かめ済みです。" else "未確認の備品が ${unconfirmed}件 あります。近い順に、短い道のりで巡れます。",
                    fontSize = 14.sp, color = cs.onSurface,
                )
                Spacer(Modifier.height(10.dp))
                PrimaryButton("巡回を始める", enabled = unconfirmed > 0) { model.startRoute() }
                if (model.confirmed.isNotEmpty()) {
                    Spacer(Modifier.height(8.dp))
                    SecondaryButton("確認済みを、未確認に戻す") { model.resetConfirmed() }
                }
            } else {
                val done = model.routeTotal - model.route.size
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("$done / ${model.routeTotal} 件", fontSize = 22.sp, fontWeight = FontWeight.Bold, color = cs.primary, modifier = Modifier.weight(1f))
                    model.routeRemainingM()?.let { Text("残り 約%.0f m".format(it), fontSize = 14.sp, color = cs.onSurfaceVariant) }
                }
                Spacer(Modifier.height(10.dp))
                if (model.route.isEmpty()) {
                    StatusBadge("すべて確かめました", Tone.OK)
                } else {
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        model.route.forEachIndexed { i, p ->
                            val name = model.items.firstOrNull { it.token == p.token }?.placed?.label() ?: p.token
                            Text(
                                "${i + 1}. $name",
                                fontSize = if (i == 0) 16.sp else 14.sp,
                                fontWeight = if (i == 0) FontWeight.Bold else FontWeight.Normal,
                                color = if (i == 0) cs.primary else cs.onSurfaceVariant,
                            )
                        }
                    }
                }
                Spacer(Modifier.height(10.dp))
                SecondaryButton("巡回をやめる") { model.stopRoute() }
            }
        }
    }
}


// ---------------- 棚卸の結果と、終了 ----------------

/** 今回の結果（確認済み・未確認・想定外・場所違い）と、「棚卸を終える」。終えると、今回の結果が次回の予定になる。 */
@Composable
private fun FinishPanel(model: AppModel) {
    val cs = MaterialTheme.colorScheme
    val context = androidx.compose.ui.platform.LocalContext.current
    val checked = model.items.count { it.token in model.confirmed }
    val missed = model.items.size - checked
    val movedItems = model.items.filter { it.token in model.moved }
    SectionLabel("今回の結果")
    AppCard {
        Column(Modifier.fillMaxWidth().padding(16.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                StatusBadge("確認済み $checked", Tone.OK)
                StatusBadge("未確認 $missed", Tone.WARN)
                StatusBadge("想定外 ${model.unexpected.size}", Tone.INFO)
                StatusBadge("場所違い ${movedItems.size}", Tone.ERROR)
            }
            if (model.unexpected.isNotEmpty()) {
                Spacer(Modifier.height(10.dp))
                Text("想定外（予定にないのに読んだ）", fontSize = 13.sp, color = cs.onSurfaceVariant)
                model.unexpected.values.forEach {
                    Text("・${it.name}（${floorLabel(it.floor)}）" + if (it.x == null) "　位置は不明" else "", fontSize = 14.sp, color = cs.onSurface)
                }
            }
            if (movedItems.isNotEmpty()) {
                Spacer(Modifier.height(10.dp))
                Text("場所違い（予定と違う階・位置で読んだ）", fontSize = 14.sp, color = cs.onSurfaceVariant)
                movedItems.forEach {
                    val m = model.moved.getValue(it.token)
                    Text(
                        "・${it.placed.label()}：${floorLabel(it.placed.floor)} → ${floorLabel(m.floor)}",
                        fontSize = 14.sp, color = cs.onSurface,
                    )
                }
            }
            if (model.canUndoFinish) {
                Spacer(Modifier.height(12.dp))
                SecondaryButton("「棚卸を終える」を取り消す") { model.undoFinish() }
            }
            Spacer(Modifier.height(12.dp))
            PrimaryButton("棚卸を終える", enabled = model.items.isNotEmpty()) {
                AlertDialog.Builder(context)
                    .setTitle("棚卸を終えますか？")
                    .setMessage(
                        "確認済み ${checked}件、未確認 ${missed}件、想定外 ${model.unexpected.size}件、場所違い ${movedItems.size}件。\n\n" +
                            "今回の結果が、次回の予定になります。\n" +
                            "・未確認の備品は、場所はそのままで「前回未確認」になります\n" +
                            "・想定外の備品は、予定に加わります\n" +
                            "・場所違いの備品は、読んだ場所に更新されます",
                    )
                    .setNegativeButton("やめる", null)
                    .setPositiveButton("終える") { _, _ -> model.finishInventory() }
                    .show()
            }
        }
    }
}


// ---------------- サーバーとの同期 ----------------

/** 同期の状態（送信待ちの件数・結果）と、「今すぐ送る」。 */
@Composable
private fun SyncPanel(model: AppModel) {
    val cs = MaterialTheme.colorScheme
    val st: SyncStatus = model.syncStatus
    val (label, tone) = when (st.state) {
        SyncState.NOT_CONFIGURED -> "サーバー未設定" to Tone.INFO
        SyncState.IDLE -> (if (st.pending > 0) "送信待ち ${st.pending}件" else "送信待ちなし") to (if (st.pending > 0) Tone.WARN else Tone.INFO)
        SyncState.SYNCING -> "送信中…（残り ${st.pending}件）" to Tone.INFO
        SyncState.OK -> (if (st.pending > 0) "送信待ち ${st.pending}件" else "同期済み") to (if (st.pending > 0) Tone.WARN else Tone.OK)
        SyncState.OFFLINE -> "オフライン（送信待ち ${st.pending}件）" to Tone.WARN
        SyncState.AUTH_ERROR -> "ログインできません（送信待ち ${st.pending}件）" to Tone.ERROR
        SyncState.ERROR -> "送信できません（送信待ち ${st.pending}件）" to Tone.ERROR
    }
    AppCard {
        Column(Modifier.fillMaxWidth().padding(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                StatusBadge(label, tone)
                Spacer(Modifier.weight(1f))
                TextButton(onClick = { model.syncNow() }, enabled = st.state != SyncState.SYNCING) { Text("今すぐ送る") }
            }
            if (st.message.isNotEmpty() && st.state != SyncState.OK) {
                Text(st.message, fontSize = 13.sp, color = cs.onSurfaceVariant)
            }
            if (st.dropped > 0) {
                Text("サーバーに断られて、送らなかった操作が ${st.dropped}件 あります。", fontSize = 13.sp, color = cs.error)
            }
        }
    }
}

/** QRが読めない備品を、管理番号の手入力で確かめる。備品の場所まで行って、入力する。 */
@Composable
private fun ManualPanel(model: AppModel) {
    val cs = MaterialTheme.colorScheme
    var no by remember { mutableStateOf("") }
    SectionLabel("QRが読めない備品（手入力）")
    AppCard {
        Column(Modifier.fillMaxWidth().padding(16.dp)) {
            Text("備品の場所まで行って、台帳の管理番号を入力してください。いまの位置が、その備品の場所として記録されます。", fontSize = 13.sp, color = cs.onSurfaceVariant)
            Spacer(Modifier.height(8.dp))
            TextField("管理番号", null, no, KeyboardType.Ascii) { no = it }
            PrimaryButton("確認済みにする", enabled = no.isNotBlank()) {
                model.confirmManual(no)
                no = ""
            }
        }
    }
}

@Composable
private fun TextField(label: String, hint: String?, value: String, type: KeyboardType, hide: Boolean = false, onChange: (String) -> Unit) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label) },
        supportingText = hint?.let { { Text(it) } },
        singleLine = true,
        visualTransformation = if (hide) PasswordVisualTransformation() else androidx.compose.ui.text.input.VisualTransformation.None,
        keyboardOptions = KeyboardOptions(keyboardType = type),
        modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
        shape = MaterialTheme.shapes.small,
    )
}


// ---------------- QRで設定 ----------------

/** 管理画面の「端末の登録」のQRを読んで、サーバーの設定と、この端末の合言葉を受け取る。 */
@Composable
fun SetupScreen(model: AppModel, onCamera: (CameraRect) -> Unit) {
    val cs = MaterialTheme.colorScheme
    CameraShell(model, "QRで設定", ghost = false, onCamera = onCamera) {
        Text("PCで管理画面を開き、「端末」→「QRを表示」を選びます。表示されたQRを、上のカメラに映してください。", fontSize = 15.sp, color = cs.onSurface)
        Text("QRは、発行から10分以内に、1回だけ使えます。", fontSize = 13.sp, color = cs.onSurfaceVariant, modifier = Modifier.padding(top = 6.dp))
        MessageBanner(model.message, model.messageOk, Modifier.padding(top = 8.dp))
        Spacer(Modifier.height(12.dp))
        SecondaryButton("設定画面へ戻る") { model.go(Screen.SETTINGS) }
    }
}
