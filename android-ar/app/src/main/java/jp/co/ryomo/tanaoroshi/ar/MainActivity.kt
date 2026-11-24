package jp.co.ryomo.tanaoroshi.ar

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.opengl.GLSurfaceView
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import kotlin.math.hypot

private enum class Screen { HOME, REGISTER, SEARCH, SETTINGS }

/** 備品の名前（仮）。ここにないトークンは、トークンをそのまま名前にする。 */
private val ASSET_NAMES = mapOf(
    "Tnote01" to "会議室のノートPC",
    "Tproj01" to "プロジェクター",
    "Tmon01" to "モニター",
)

private const val BLUE = 0xFF1A56DB.toInt()

/** カメラ映像の高さ（dp）。大きすぎると、操作の画面が狭くなる */
private const val CAMERA_HEIGHT_DP = 300

/**
 * 備品の位置を、ARの追跡で記録し、探す。
 *   登録：アンカーのQRを読む → 歩く → 備品のQRを読む（そのときの位置を登録）
 *   探す：アンカーのQRを読む → 備品を選ぶ → 矢印と距離に従って歩く
 */
class MainActivity : Activity() {

    private lateinit var engine: ArEngine
    private lateinit var glView: GLSurfaceView
    private lateinit var content: LinearLayout
    private lateinit var scroll: ScrollView
    private lateinit var store: Store

    private var screen = Screen.HOME
    private var settings = Settings()
    private val registry = LinkedHashMap<String, Placed>()
    private var targetToken: String? = null
    private var message = ""
    private var messageOk = true

    // 画面ごとの、更新される部品
    private var statusView: TextView? = null
    private var stepsView: TextView? = null
    private var messageView: TextView? = null
    private var arrowView: ArrowView? = null
    private var distanceView: TextView? = null
    private var bearingView: TextView? = null
    private var errorView: TextView? = null

    private val handler = Handler(Looper.getMainLooper())
    private val ticker = object : Runnable {
        override fun run() {
            refreshLive()
            handler.postDelayed(this, 100)
        }
    }

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = Store(this)
        settings = store.loadSettings()
        registry.putAll(store.loadRegistry())

        engine = ArEngine(this) { text, pose -> runOnUiThread { handleQr(text, pose) } }
        engine.rotationOverride = intent.getIntExtra("rot", settings.cameraRot) // adbからの指定が、あれば優先
        glView = GLSurfaceView(this).apply {
            preserveEGLContextOnPause = true
            setEGLContextClientVersion(2)
            setEGLConfigChooser(8, 8, 8, 8, 16, 0)
            setRenderer(engine)
            renderMode = GLSurfaceView.RENDERMODE_CONTINUOUSLY
        }
        content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(12), dp(16), dp(24))
        }
        scroll = ScrollView(this).apply { addView(content) }
        // カメラ（AR）は、画面の上に、一定の大きさで置く（途中で大きさを変えない）。
        // 登録・探す では、その下に操作の画面を置き、ホーム・設定 では、全面を操作の画面が覆う。
        val root = FrameLayout(this).apply {
            addView(glView, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(CAMERA_HEIGHT_DP)).apply { gravity = Gravity.TOP })
            addView(scroll, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        }
        setContentView(root)
        show(Screen.HOME)
    }

    override fun onResume() {
        super.onResume()
        if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.CAMERA), 1)
            return
        }
        startAr()
    }

    private fun startAr() {
        val error = engine.resume()
        if (error != null) say(error, false)
        glView.onResume()
        handler.post(ticker)
    }

    override fun onPause() {
        super.onPause()
        handler.removeCallbacks(ticker)
        glView.onPause()
        engine.pause()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) startAr()
        else say("カメラの許可が必要です。設定で、許可してください。", false)
    }

    // ---------------- QR ----------------

    private fun handleQr(text: String, pose: PoseSnapshot) {
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
            val live = engine.live
            val before = engine.mapAt(pose)
            if (before != null && !live.lostTracking) {
                val gap = hypot(before.first - a.x, before.second - a.y)
                notes += "ARの推定と、アンカーの位置の差：%.2f m（%.0f m歩行）".format(gap, live.walkedM)
            }
            engine.setReference(pose, a.x, a.y, a.facingDeg)
            say((listOf("${a.name} に位置を合わせました。") + notes).joinToString("\n"))
            return
        }

        if (!engine.hasReference()) return say("先に、アンカーのQRを読み取ってください。", false)
        val pos = engine.mapAt(pose) ?: return
        val live = engine.live
        val name = ASSET_NAMES[ref.token] ?: ref.token
        val err = ErrorModel.estimate(live.walkedM) + if (live.lostTracking) 5.0 else 0.0

        if (screen == Screen.REGISTER) {
            registry[ref.token] = Placed(name, pos.first, pos.second, err)
            store.saveRegistry(registry)
            say("「$name」を登録しました（誤差 ±%.1f m）。".format(err))
            show(Screen.REGISTER)
        } else {
            val placed = registry[ref.token] ?: return say("「$name」は、まだ登録されていません。", false)
            val gap = hypot(pos.first - placed.x, pos.second - placed.y)
            say("「$name」のQRを読みました。登録位置との差：%.2f m".format(gap))
        }
    }

    // ---------------- 画面 ----------------

    private fun say(text: String, ok: Boolean = true) {
        message = text
        messageOk = ok
        messageView?.let {
            it.text = text
            it.setTextColor(if (ok) 0xFF065F46.toInt() else 0xFFB45309.toInt())
        }
    }

    private fun show(s: Screen) {
        screen = s
        content.removeAllViews()
        statusView = null; stepsView = null; messageView = null; arrowView = null
        distanceView = null; bearingView = null; errorView = null
        val overlay = s == Screen.REGISTER || s == Screen.SEARCH
        scroll.layoutParams = FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.MATCH_PARENT,
        ).apply { topMargin = if (overlay) dp(CAMERA_HEIGHT_DP) else 0 }
        scroll.setBackgroundColor(if (overlay) 0xFFF4F6F8.toInt() else 0xFFF4F6F8.toInt())
        content.setPadding(dp(16), if (overlay) dp(12) else dp(48), dp(16), dp(24))
        when (s) {
            Screen.HOME -> buildHome()
            Screen.REGISTER -> buildRegister()
            Screen.SEARCH -> buildSearch()
            Screen.SETTINGS -> buildSettings()
        }
    }

    private fun title(text: String) = TextView(this).apply {
        this.text = text
        textSize = 22f
        setTypeface(null, Typeface.BOLD)
    }

    private fun note(text: String) = TextView(this).apply {
        this.text = text
        textSize = 14f
        setTextColor(0xFF555555.toInt())
        setPadding(0, dp(4), 0, dp(4))
    }

    private fun button(label: String, primary: Boolean = true, enabled: Boolean = true, onClick: () -> Unit) =
        Button(this).apply {
            text = label
            textSize = 18f
            isAllCaps = false
            this.isEnabled = enabled
            setTextColor(if (primary) Color.WHITE else BLUE)
            setBackgroundColor(if (primary) BLUE else Color.WHITE)
            setOnClickListener { onClick() }
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(64)).apply {
                topMargin = dp(10)
            }
        }

    /** 手順を、番号つきで出す。いまの手順に ▶、済んだものに ✓ を付ける（100ミリ秒ごとに更新）。 */
    private fun stepsCard() = TextView(this).apply {
        textSize = 16f
        setTextColor(0xFF1E3A8A.toInt())
        setBackgroundColor(0xFFE0E7FF.toInt())
        setPadding(dp(14), dp(10), dp(14), dp(10))
        text = stepsText()
    }

    private fun stepsText(): String {
        val hasRef = engine.hasReference()
        val steps: List<String>
        val current: Int
        if (screen == Screen.REGISTER) {
            steps = listOf(
                "アンカーのQRを、壁に向かって正対して読む",
                "歩いて、備品に近づく",
                "備品のQRを読む（そのときの位置が登録される）",
                "次の備品へ。全部終わったら「完了して、探す」",
            )
            current = if (!hasRef) 0 else 1
        } else {
            steps = listOf(
                "アンカーのQRを読んで、位置を合わせる",
                "探す備品を、下から選ぶ",
                "矢印の向きに歩く（距離が減っていく）",
                "着いたら、備品のQRを読んで確かめる",
            )
            current = if (!hasRef) 0 else if (targetToken == null) 1 else 2
        }
        return steps.mapIndexed { i, t ->
            val mark = if (i < current) "✓" else if (i == current) "▶" else "　"
            "$mark ${i + 1}. $t"
        }.joinToString("\n")
    }

    private fun header(text: String, back: Screen = Screen.HOME) {
        content.addView(button("‹ 戻る", primary = false) { show(back) }.apply {
            layoutParams = LinearLayout.LayoutParams(dp(120), dp(48))
        })
        content.addView(title(text))
    }

    private fun buildHome() {
        content.addView(title("備品の位置").apply { textSize = 30f; gravity = Gravity.CENTER; setPadding(0, dp(24), 0, dp(24)) })
        content.addView(note("登録済み ${registry.size}件"))
        content.addView(note("使い方：\n① 「登録する」で、アンカーのQR → 備品のQRの順に読み、備品の位置を登録します。\n② 「探す」で、アンカーのQRを読み、探す備品を選んで、矢印と距離に従って歩きます。"))
        content.addView(button("登録する") { show(Screen.REGISTER) })
        content.addView(button("探す", enabled = registry.isNotEmpty()) { show(Screen.SEARCH) })
        if (registry.isEmpty()) content.addView(note("探すには、先に、備品を登録してください。"))
        content.addView(button("設定", primary = false) { show(Screen.SETTINGS) })
    }

    private fun buildRegister() {
        header("登録")
        stepsView = stepsCard().also { content.addView(it) }
        statusView = note("").also { content.addView(it) }
        messageView = TextView(this).apply {
            textSize = 18f
            setTypeface(null, Typeface.BOLD)
            text = message
            setTextColor(if (messageOk) 0xFF065F46.toInt() else 0xFFB45309.toInt())
        }.also { content.addView(it) }
        content.addView(title("登録した備品（${registry.size}件）").apply { textSize = 17f })
        for ((_, p) in registry) {
            content.addView(note("・${p.name}　東%.1f 北%.1f（±%.1f m）".format(p.x, p.y, p.errM)))
        }
        content.addView(button("完了して、探す", enabled = registry.isNotEmpty()) { show(Screen.SEARCH) })
    }

    private fun buildSearch() {
        header("探す")
        stepsView = stepsCard().also { content.addView(it) }
        statusView = note("").also { content.addView(it) }
        if (registry.isEmpty()) content.addView(note("登録した備品がありません。"))
        for ((token, p) in registry) {
            val selected = token == targetToken
            content.addView(button((if (selected) "▶ " else "") + p.name, primary = selected) {
                targetToken = token
                show(Screen.SEARCH)
            }.apply { layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(52)).apply { topMargin = dp(6) } })
        }
        arrowView = ArrowView(this).also {
            content.addView(it, LinearLayout.LayoutParams(dp(260), dp(260)).apply {
                gravity = Gravity.CENTER_HORIZONTAL; topMargin = dp(12)
            })
        }
        distanceView = TextView(this).apply {
            textSize = 52f; setTypeface(null, Typeface.BOLD); gravity = Gravity.CENTER
        }.also { content.addView(it) }
        bearingView = TextView(this).apply { textSize = 26f; gravity = Gravity.CENTER }.also { content.addView(it) }
        errorView = note("").apply { gravity = Gravity.CENTER }.also { content.addView(it) }
        messageView = TextView(this).apply {
            textSize = 17f
            text = message
            setTextColor(if (messageOk) 0xFF065F46.toInt() else 0xFFB45309.toInt())
        }.also { content.addView(it) }
        content.addView(note("位置がずれたら、アンカーのQRを読み直してください。備品に着いたら、そのQRを読むと、登録位置との差を確かめられます。"))
    }

    private fun buildSettings() {
        header("設定")
        fun field(parent: LinearLayout, label: String, value: Double): EditText {
            parent.addView(note(label))
            return EditText(this).apply {
                inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL or InputType.TYPE_NUMBER_FLAG_SIGNED
                setText(value.toString())
                textSize = 18f
            }.also { parent.addView(it) }
        }
        content.addView(note("アンカーは、1つ（A）で使えます。アンカーAのQRは、Awest です。"))
        val fa = field(content, "アンカーAの壁に正対する向き（°、北が0、東が90）。分からなければ、0のままで構いません", settings.facingA)

        // 詳細（通常は、閉じておく）
        var useB = settings.useB
        val advanced = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            visibility = View.GONE
        }
        val useBButton = button(if (useB) "アンカーBを使う：オン" else "アンカーBを使う：オフ", primary = false) {}
        useBButton.setOnClickListener {
            useB = !useB
            useBButton.text = if (useB) "アンカーBを使う：オン" else "アンカーBを使う：オフ"
        }
        advanced.addView(note("アンカーBは、精度の確認や、広いフロアで、位置を合わせ直すときに使います。Aを原点にした位置を入れます。"))
        advanced.addView(useBButton)
        val bx = field(advanced, "アンカーB：東へ（m）。西はマイナス", settings.bx)
        val by = field(advanced, "アンカーB：北へ（m）。南はマイナス", settings.by)
        val fb = field(advanced, "アンカーBの壁に正対する向き（°）", settings.facingB)
        val cr = field(advanced, "カメラ映像の向きの強制（-1は自動。映像が横向きや逆さのときだけ、0〜3を試す）", settings.cameraRot.toDouble())
        content.addView(button("詳細設定（アンカーB・カメラ）を開く／閉じる", primary = false) {
            advanced.visibility = if (advanced.visibility == View.GONE) View.VISIBLE else View.GONE
        })
        content.addView(advanced)

        content.addView(button("保存する") {
            fun num(e: EditText, d: Double) = e.text.toString().toDoubleOrNull() ?: d
            val rot = num(cr, settings.cameraRot.toDouble()).toInt().coerceIn(-1, 3)
            settings = Settings(
                bx = num(bx, settings.bx), by = num(by, settings.by),
                facingA = num(fa, settings.facingA), facingB = num(fb, settings.facingB),
                cameraRot = rot, useB = useB,
            )
            store.saveSettings(settings)
            engine.rotationOverride = rot
            say("設定を保存しました。")
            show(Screen.HOME)
        })
        content.addView(button("登録した備品を、すべて消す（${registry.size}件）", primary = false, enabled = registry.isNotEmpty()) {
            AlertDialog.Builder(this)
                .setTitle("登録した備品を消しますか？")
                .setMessage("この端末の登録が、すべて消えます。")
                .setNegativeButton("やめる", null)
                .setPositiveButton("消す") { _, _ ->
                    registry.clear(); targetToken = null
                    store.saveRegistry(registry)
                    show(Screen.SETTINGS)
                }.show()
        })
    }

    // ---------------- 100ミリ秒ごとの更新 ----------------

    private fun refreshLive() {
        val l = engine.live
        stepsView?.let { v -> stepsText().let { t -> if (v.text.toString() != t) v.text = t } }
        statusView?.text = when {
            !l.tracking -> l.trackingNote
            l.mapX == null -> l.trackingNote
            else -> "位置　東%.1f m　北%.1f m　／　%.0f m歩行（誤差 ±%.1f m）%s".format(
                l.mapX, l.mapY, l.walkedM, ErrorModel.estimate(l.walkedM),
                if (l.lostTracking) "\n追跡が途切れました。アンカーのQRを読み直してください。" else "",
            )
        }

        if (screen != Screen.SEARCH) return
        val target = targetToken?.let { registry[it] }
        val x = l.mapX; val y = l.mapY; val b = l.bearing
        if (target == null || x == null || y == null || b == null || !l.tracking) {
            arrowView?.visibility = View.INVISIBLE
            distanceView?.text = ""
            bearingView?.text = when {
                target == null -> "探す備品を選んでください。"
                x == null -> "アンカーのQRを読み取ってください。"
                else -> ""
            }
            errorView?.text = ""
            return
        }
        val (dist, bearing) = distanceAndBearing(x, y, target.x, target.y)
        arrowView?.visibility = View.VISIBLE
        arrowView?.angleDeg = (bearing - b).toFloat() // 画面の上＝いま向いている方向
        if (dist < 2.0) {
            distanceView?.text = "%.1f m".format(dist)
            bearingView?.text = "近くです。QRを探してください。"
        } else {
            distanceView?.text = "約 %.1f m".format(dist)
            bearingView?.text = "${compassLabel(bearing)}（${Math.round(bearing)}°）"
        }
        val err = ErrorModel.combined(ErrorModel.estimate(l.walkedM) + if (l.lostTracking) 5.0 else 0.0, target.errM)
        errorView?.text = "誤差の目安 ±%.1f m".format(err)
    }
}
