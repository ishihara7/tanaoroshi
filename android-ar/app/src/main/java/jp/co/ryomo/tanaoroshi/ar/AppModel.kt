package jp.co.ryomo.tanaoroshi.ar

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlin.math.hypot

/** HOME：モードの選択。REGISTER：備品登録モード。INVENTORY：棚卸モード。 */
enum class Screen { HOME, REGISTER, INVENTORY, SETTINGS }

/** 備品の名前（仮）。ここにないトークンは、トークンをそのまま名前にする。 */
private val ASSET_NAMES = mapOf(
    "Tnote01" to "会議室のノートPC",
    "Tproj01" to "プロジェクター",
    "Tmon01" to "モニター",
    "Tpc01" to "デスクトップPC",
    "Tprn01" to "プリンター",
    "Tcab01" to "キャビネット",
    "Twb01" to "ホワイトボード",
)

/** 見えている特徴点が、これ以下だと、壁や床ばかりと見なして警告する */
const val LOW_POINTS = 25

/** 同じ階で、登録位置からこれ以上離れて読んだら「場所違い」。ARの誤差を見込んだ仮の値（実機で調整する） */
const val MOVED_THRESHOLD_M = 3.0

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

    /** いまいる階。アンカーを読んだ階（読むまでは null）。階を移ったら、その階のアンカーを読み直す */
    var floor by mutableStateOf<Int?>(null)
        private set

    /** いまの階の備品（階が分からないうちは、すべて）。ゴースト・巡回・進み具合は、これを対象にする */
    val floorItems: List<PlacedItem>
        get() = floor?.let { f -> items.filter { it.placed.floor == f } } ?: items.toList()

    /** 棚卸で、QRを読んで、実物を確かめた備品。それ以外は「未確認」のゴーストとして見える（端末に保存する） */
    var confirmed by mutableStateOf(store.loadConfirmed())
        private set

    private fun updateConfirmed(tokens: Set<String>) {
        confirmed = tokens
        store.saveConfirmed(tokens)
    }

    /** 今回の棚卸で、予定にないのに読んだ備品（端末に保存する） */
    var unexpected by mutableStateOf<Map<String, Unexpected>>(store.loadUnexpected())
        private set

    /** 今回の棚卸で、予定と違う場所（階・位置）で読んだ備品（端末に保存する） */
    var moved by mutableStateOf<Map<String, MovedAt>>(store.loadMoved())
        private set

    private fun updateUnexpected(m: Map<String, Unexpected>) {
        unexpected = m
        store.saveUnexpected(m)
    }

    private fun updateMoved(m: Map<String, MovedAt>) {
        moved = m
        store.saveMoved(m)
    }

    /** ゴースト・巡回の対象（位置が分かっている、いまの階の備品） */
    val mapItems: List<PlacedItem>
        get() = floorItems.filter { it.placed.located }

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

    private var seenRecovery = 0

    fun tick() {
        live = engine.live
        hasRef = engine.hasReference()
        // 追跡が戻ったときの、向きの補正の結果を知らせる（実機で、座標が変わるのかを確かめられるように）
        val rc = engine.recoveryCount
        if (rc != seenRecovery) {
            seenRecovery = rc
            if (screen == Screen.REGISTER || screen == Screen.INVENTORY) say(engine.recoveryNote)
        }
    }

    fun say(text: String, ok: Boolean = true) {
        message = text
        messageOk = ok
    }

    fun clearMessage() {
        message = ""
    }

    fun selectTarget(token: String) {
        if (items.firstOrNull { it.token == token }?.placed?.located == false) return say("位置が分からない備品です。案内はできません。", false)
        targetToken = token
        routeMode = false
    }

    /** いまの位置（分からなければ、アンカーA＝原点）から、未確認の備品を巡る順路を作り直す */
    private fun replan(fromX: Double? = null, fromY: Double? = null) {
        val l = engine.live
        val x = fromX ?: l.mapX ?: 0.0
        val y = fromY ?: l.mapY ?: 0.0
        val pts = mapItems.filter { it.token !in confirmed }.map { RoutePoint(it.token, it.placed.x, it.placed.y) }
        route = RoutePlanner.plan(x, y, pts)
        targetToken = route.firstOrNull()?.token
    }

    fun startRoute() {
        routeMode = true
        val n = floorItems.count { it.token !in confirmed }
        routeTotal = n
        replan()
        if (n == 0) say("未確認の備品はありません。すべて確かめ済みです。")
    }

    fun stopRoute() {
        routeMode = false
        route = emptyList()
    }

    /** 棚卸を、最初からやり直す（全部を、未確認に戻す） */
    fun resetConfirmed() {
        updateConfirmed(emptySet())
        updateMoved(emptyMap())
        updateUnexpected(emptyMap())
        say("棚卸を、最初からやり直します。")
        if (routeMode) startRoute()
    }

    private fun confirm(token: String, atX: Double, atY: Double) {
        updateConfirmed(confirmed + token)
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
        updateConfirmed(confirmed - token)
        updateMoved(moved - token)
        if (targetToken == token) targetToken = null
        if (routeMode) startRoute()
        persist()
    }

    /**
     * この端末のデータを、すべて消して、初めて使うときの状態に戻す。
     * 備品、棚卸の進み具合、設定、アンカーで合わせた位置、が対象。
     */
    fun clearAllData() {
        store.clearAll()
        items.clear()
        confirmed = emptySet()
        moved = emptyMap()
        unexpected = emptyMap()
        lastFinish = null
        targetToken = null
        floor = null
        stopRoute()
        settings = Settings()
        engine.rotationOverride = settings.cameraRot
        engine.clearReference()
        say("すべてのデータを消しました。", true)
        screen = Screen.HOME
    }

    /**
     * 棚卸を終える。今回の結果が、次回の予定になる。
     * 確かめた備品は、前回未確認の印を消す（場所違いなら、読んだ場所に更新）。
     * 確かめられなかった備品は、場所はそのままで「前回未確認」の印を付ける。
     * 予定にないのに読んだ備品は、新しい予定に加える（位置が取れていなければ、階だけ）。
     */
    fun finishInventory() {
        val before = snapshot()
        val (after, sum) = Inventory.finish(before, ErrorModel.estimate(engine.live.walkedM))
        lastFinish = before
        apply(after)
        targetToken = null
        stopRoute()
        say("棚卸を終えました。確認 ${sum.checked}件（うち場所違い ${sum.checkedMoved}件）、未確認 ${sum.missed}件、想定外 ${sum.unexpected}件。次回の予定にしました。")
    }

    /** 直前に「棚卸を終える」を押す前の状態（取り消し用。直後の1回だけ。端末を閉じると消える） */
    private var lastFinish by mutableStateOf<InventoryState?>(null)

    val canUndoFinish: Boolean get() = lastFinish != null

    /** 「棚卸を終える」を取り消す。終える前の状態（予定・確認済み・場所違い・想定外）に戻す。 */
    fun undoFinish() {
        val before = lastFinish ?: return
        apply(before)
        lastFinish = null
        targetToken = null
        stopRoute()
        say("「棚卸を終える」を取り消しました。終える前の状態に戻しました。")
    }

    /** 確かめた備品を、未確認に戻す（間違えて読んだとき）。場所違いの記録も消える。 */
    fun unconfirmItem(token: String) {
        if (token !in confirmed) return
        apply(Inventory.unconfirm(snapshot(), token))
        if (routeMode) startRoute()
        say("「${items.firstOrNull { it.token == token }?.placed?.name ?: token}」を、未確認に戻しました。")
    }

    private fun snapshot() = InventoryState(items.toList(), confirmed, moved, unexpected)

    private fun apply(s: InventoryState) {
        items.clear()
        items.addAll(s.items)
        persist()
        updateConfirmed(s.confirmed)
        updateMoved(s.moved)
        updateUnexpected(s.unexpected)
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
        if (screen != Screen.REGISTER && screen != Screen.INVENTORY) return
        val ref = parseTagUrl(text) ?: return say("このQRは、このアプリのタグではありません。", false)

        if (ref.isAnchor) {
            val a = settings.anchors().find { it.token == ref.token }
                ?: return say(
                    "このアンカー（${ref.token}）は、登録されていません。アンカーは、A（1階）・B（2階）・C（3階）です。",
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
            val moved = floor != null && floor != a.floor
            engine.setReference(pose, a.x, a.y, a.facingDeg)
            floor = a.floor
            targetToken = null
            if (routeMode) startRoute()
            haptic()
            say((listOf("${a.name} に位置を合わせました。" + if (moved) "${a.floor}階に移りました。" else "") + notes).joinToString("\n"))
            return
        }

        val l = engine.live
        val name = ASSET_NAMES[ref.token] ?: ref.token

        if (screen == Screen.REGISTER) {
            if (!engine.hasReference()) return say("先に、アンカーのQRを読み取ってください。", false)
            val pos = engine.mapAt(pose) ?: return
            val err = ErrorModel.estimate(l.walkedM)
            if (l.lostTracking) {
                // 追跡が途切れたあとは、位置を信用できない。登録済みの備品なら、それを目印に立て直す
                val known = items.firstOrNull { it.token == ref.token }?.placed
                return if (known != null) {
                    engine.fixAtKnownPoint(pose, known.x, known.y)
                    haptic()
                    say("「$name」（登録済み）を目印に、位置を合わせ直しました。続けて、次の備品へ進めます。")
                } else {
                    say("追跡が途切れていて、位置を信用できません。アンカー、または登録済みの備品のQRを読んで、位置を合わせ直してください。", false)
                }
            }
            val f = floor ?: 1
            register(ref.token, Placed(name, pos.first, pos.second, err, f))
            haptic()
            say("「$name」を${f}階に登録しました（誤差 ±%.1f m）。".format(err))
            return
        }

        // 棚卸：備品のQRを読んだら、確かめた備品にする。アンカーを読む前でも、確かめることはできる
        lastFinish = null // 新しく読んだら、前の「棚卸を終える」は取り消せない
        val posNow = if (engine.hasReference() && !l.lostTracking) engine.mapAt(pose) else null
        val placed = items.firstOrNull { it.token == ref.token }?.placed
        if (placed == null) {
            // 予定にない備品。登録はせず、「想定外」として記録する（位置が取れなければ階だけ）
            val first = ref.token !in unexpected
            updateUnexpected(unexpected + (ref.token to Unexpected(ref.token, name, floor ?: 1, posNow?.first, posNow?.second)))
            haptic()
            return say("「$name」は、予定にありません。想定外として記録しました。" + if (first) "" else "（記録済み）", false)
        }
        // 別の階の備品は、位置の目印にしない（座標が別）。確かめることだけはできる
        val j = Inventory.judgeMoved(placed, floor, posNow?.first, posNow?.second)
        val otherFloor = j.otherFloor
        val already = ref.token in confirmed
        val gap = j.gapM
        val isMoved = j.isMoved
        updateMoved(
            if (isMoved) moved + (ref.token to MovedAt(ref.token, floor ?: placed.floor, posNow?.first, posNow?.second))
            else moved - ref.token,
        )
        val gapText = if (gap != null) "　登録位置との差：%.2f m".format(gap) else ""
        val movedText = when {
            !isMoved -> ""
            otherFloor -> "\n登録は${placed.floor}階です。場所違いとして記録しました。"
            else -> "\n登録位置から %.1f m 以上離れています。場所違いとして記録しました。".format(MOVED_THRESHOLD_M)
        }
        // 備品を読むたびに、その場所を目印に、位置と向きを合わせ直す（前の目印から2m以上歩いていれば、向きも直る）。場所違いは、目印にしない
        val fixNote = if (engine.hasReference() && !otherFloor && !isMoved) engine.fixAtKnownPoint(pose, placed.x, placed.y) else null
        haptic()
        val wasRoute = routeMode
        confirm(ref.token, placed.x, placed.y)
        val left = floorItems.count { it.token !in confirmed }
        val next = if (wasRoute) route.firstOrNull() else null
        say(
            (if (already) "「$name」は、確かめ済みです。" else "「$name」を確かめました。") + gapText + movedText +
                (if (fixNote != null) "\n$fixNote" else "") +
                when {
                    left == 0 -> "\nすべての備品を確かめました。棚卸は完了です。"
                    next != null -> "\n次は「${items.firstOrNull { it.token == next.token }?.placed?.name}」へ。"
                    else -> "\n残り ${left}件。"
                },
        )
    }
}
