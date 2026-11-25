package jp.co.ryomo.tanaoroshi.ar

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlin.math.hypot

enum class Screen { HOME, REGISTER, SEARCH, SETTINGS }

/** 備品の名前（仮）。ここにないトークンは、トークンをそのまま名前にする。 */
private val ASSET_NAMES = mapOf(
    "Tnote01" to "会議室のノートPC",
    "Tproj01" to "プロジェクター",
    "Tmon01" to "モニター",
)

/** 見えている特徴点が、これ以下だと、壁や床ばかりと見なして警告する */
const val LOW_POINTS = 25

/** 登録した備品の1件（画面に出す用）。 */
data class PlacedItem(val token: String, val placed: Placed)

/**
 * 画面の状態と、QRを読んだときの処理。
 * 画面（Compose）は、ここの状態を読むだけにして、ARの処理には触れない。
 */
class AppModel(
    private val engine: ArEngine,
    private val store: Store,
    private val haptic: () -> Unit,
) {
    var screen by mutableStateOf(Screen.HOME)
        private set
    var settings by mutableStateOf(store.loadSettings())
        private set
    var targetToken by mutableStateOf<String?>(null)
        private set
    var message by mutableStateOf("")
        private set
    var messageOk by mutableStateOf(true)
        private set

    /** 100ミリ秒ごとに、ARの状態が入る */
    var live by mutableStateOf(engine.live)
        private set
    var hasRef by mutableStateOf(false)
        private set

    /** 登録した備品（登録順）。変更は、この中で行う */
    val items = mutableStateListOf<PlacedItem>().apply {
        store.loadRegistry().forEach { (k, v) -> add(PlacedItem(k, v)) }
    }

    /** このセッションで、QRを読んで、実物を確かめた備品（登録した直後も含む）。それ以外は「未確認」のゴースト */
    var confirmed by mutableStateOf<Set<String>>(emptySet())
        private set

    /** 巡回モード：未確認の備品を、短い順路で、順に案内する */
    var routeMode by mutableStateOf(false)
        private set

    /** 巡回の、これから行く順（先頭が、いまの目的地） */
    var route by mutableStateOf<List<RoutePoint>>(emptyList())
        private set

    /** 巡回を始めたときの、未確認の件数（「2 / 5」の表示用） */
    var routeTotal by mutableStateOf(0)
        private set

    fun go(s: Screen) {
        screen = s
    }

    fun tick() {
        live = engine.live
        hasRef = engine.hasReference()
    }

    fun say(text: String, ok: Boolean = true) {
        message = text
        messageOk = ok
    }

    fun clearMessage() {
        message = ""
    }

    fun selectTarget(token: String) {
        targetToken = token
        routeMode = false
    }

    /** いまの位置（分からなければ、アンカーA＝原点）から、未確認の備品を巡る順路を作り直す */
    private fun replan(fromX: Double? = null, fromY: Double? = null) {
        val l = engine.live
        val x = fromX ?: l.mapX ?: 0.0
        val y = fromY ?: l.mapY ?: 0.0
        val pts = items.filter { it.token !in confirmed }.map { RoutePoint(it.token, it.placed.x, it.placed.y) }
        route = RoutePlanner.plan(x, y, pts)
        targetToken = route.firstOrNull()?.token
    }

    fun startRoute() {
        routeMode = true
        val n = items.count { it.token !in confirmed }
        routeTotal = n
        replan()
        if (n == 0) say("未確認の備品はありません。すべて確かめ済みです。")
    }

    fun stopRoute() {
        routeMode = false
        route = emptyList()
    }

    /** 確かめ直したい（全部を、未確認に戻す） */
    fun resetConfirmed() {
        confirmed = emptySet()
        if (routeMode) startRoute()
    }

    private fun confirm(token: String, atX: Double, atY: Double) {
        confirmed = confirmed + token
        if (routeMode) {
            // 備品の場所に着いている。そこから、残りの順路を、作り直す
            replan(atX, atY)
        }
    }

    /** 巡回の、残りの距離（m）。いまの位置から */
    fun routeRemainingM(): Double? {
        val l = live
        val x = l.mapX ?: return null
        val y = l.mapY ?: return null
        return RoutePlanner.length(x, y, route)
    }

    fun target(): Placed? = targetToken?.let { t -> items.firstOrNull { it.token == t }?.placed }

    fun saveSettings(s: Settings) {
        settings = s
        store.saveSettings(s)
        engine.rotationOverride = s.cameraRot
        say("設定を保存しました。")
    }

    fun removeItem(token: String) {
        items.removeAll { it.token == token }
        confirmed = confirmed - token
        if (targetToken == token) targetToken = null
        if (routeMode) startRoute()
        persist()
    }

    fun clearItems() {
        items.clear()
        confirmed = emptySet()
        targetToken = null
        stopRoute()
        persist()
    }

    private fun persist() {
        store.saveRegistry(LinkedHashMap<String, Placed>().also { m -> items.forEach { m[it.token] = it.placed } })
    }

    private fun register(token: String, p: Placed) {
        val i = items.indexOfFirst { it.token == token }
        if (i >= 0) items[i] = PlacedItem(token, p) else items.add(PlacedItem(token, p))
        persist()
    }

    // ---------------- QR ----------------

    fun handleQr(text: String, pose: PoseSnapshot) {
        if (screen != Screen.REGISTER && screen != Screen.SEARCH) return
        val ref = parseTagUrl(text) ?: return say("このQRは、このアプリのタグではありません。", false)

        if (ref.isAnchor) {
            val a = settings.anchors().find { it.token == ref.token }
                ?: return say(
                    if (ref.token == "Aeast") "アンカーBは、使わない設定です。アンカーAのQRを読んでください（Bは、設定の詳細で、使えるようにできます）。"
                    else "このアンカー（${ref.token}）は、登録されていません。アンカーAのQR（Awest）を読んでください。",
                    false,
                )
            val notes = mutableListOf<String>()
            // 診断：これまでの追跡で出した位置と、アンカーの本当の位置の差（ARの精度の目安）
            val l = engine.live
            val before = engine.mapAt(pose)
            if (before != null && !l.lostTracking) {
                val gap = hypot(before.first - a.x, before.second - a.y)
                notes += "ARの推定と、アンカーの位置の差：%.2f m（%.0f m歩行）".format(gap, l.walkedM)
            }
            engine.setReference(pose, a.x, a.y, a.facingDeg)
            haptic()
            say((listOf("${a.name} に位置を合わせました。") + notes).joinToString("\n"))
            return
        }

        if (!engine.hasReference()) return say("先に、アンカーのQRを読み取ってください。", false)
        val pos = engine.mapAt(pose) ?: return
        val l = engine.live
        val name = ASSET_NAMES[ref.token] ?: ref.token
        val err = ErrorModel.estimate(l.walkedM)

        if (screen == Screen.REGISTER) {
            if (l.lostTracking) {
                // 追跡が途切れたあとは、位置を信用できない。登録済みの備品なら、それを目印に立て直す
                val known = items.firstOrNull { it.token == ref.token }?.placed
                return if (known != null) {
                    engine.correctPosition(pose, known.x, known.y)
                    haptic()
                    say("「$name」（登録済み）を目印に、位置を合わせ直しました。続けて、次の備品へ進めます。")
                } else {
                    say("追跡が途切れていて、位置を信用できません。アンカー、または登録済みの備品のQRを読んで、位置を合わせ直してください。", false)
                }
            }
            register(ref.token, Placed(name, pos.first, pos.second, err))
            confirmed = confirmed + ref.token
            haptic()
            say("「$name」を登録しました（誤差 ±%.1f m）。".format(err))
        } else {
            val placed = items.firstOrNull { it.token == ref.token }?.placed
                ?: return say("「$name」は、まだ登録されていません。", false)
            val gap = hypot(pos.first - placed.x, pos.second - placed.y)
            haptic()
            val wasRoute = routeMode
            confirm(ref.token, placed.x, placed.y)
            val next = if (wasRoute) route.firstOrNull() else null
            say(
                "「$name」を確かめました。登録位置との差：%.2f m".format(gap) +
                    when {
                        !wasRoute -> ""
                        next != null -> "\n次は「${items.firstOrNull { it.token == next.token }?.placed?.name}」へ。"
                        else -> "\nすべての備品を確かめました。"
                    },
            )
        }
    }
}
