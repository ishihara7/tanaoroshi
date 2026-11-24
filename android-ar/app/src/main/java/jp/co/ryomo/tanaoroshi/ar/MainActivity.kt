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

/**
 * 備品の位置を、ARの追跡で記録し、探す。
 *   登録：アンカーのQRを読む → 歩く → 備品のQRを読む（そのときの位置を登録）
 *   探す：アンカーのQRを読む → 備品を選ぶ → 矢印と距離に従って歩く
 */
class MainActivity : Activity() {

    private lateinit var engine: ArEngine
    private lateinit var glView: GLSurfaceView
    private lateinit var content: LinearLayout
    private lateinit var store: Store

    private var screen = Screen.HOME
    private var settings = Settings()
    private val registry = LinkedHashMap<String, Placed>()
    private var targetToken: String? = null
    private var message = ""
    private var messageOk = true

    // 画面ごとの、更新される部品
    private var statusView: TextView? = null
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
        val scroll = ScrollView(this).apply { addView(content) }
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(0xFFF4F6F8.toInt())
            setPadding(0, dp(40), 0, 0)
            addView(glView, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 1))
            addView(scroll, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
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
                ?: return say("登録されていないアンカーです。", false)
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
        statusView = null; messageView = null; arrowView = null
        distanceView = null; bearingView = null; errorView = null
        val camHeight = when (s) {
            Screen.REGISTER -> dp(340)
            Screen.SEARCH -> dp(180)
            else -> 1
        }
        glView.layoutParams = (glView.layoutParams as LinearLayout.LayoutParams).apply { height = camHeight }
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

    private fun header(text: String, back: Screen = Screen.HOME) {
        content.addView(button("‹ 戻る", primary = false) { show(back) }.apply {
            layoutParams = LinearLayout.LayoutParams(dp(120), dp(48))
        })
        content.addView(title(text))
    }

    private fun buildHome() {
        content.addView(title("備品の位置").apply { textSize = 30f; gravity = Gravity.CENTER; setPadding(0, dp(24), 0, dp(24)) })
        content.addView(note("登録済み ${registry.size}件"))
        content.addView(button("登録する") { show(Screen.REGISTER) })
        content.addView(button("探す", enabled = registry.isNotEmpty()) { show(Screen.SEARCH) })
        if (registry.isEmpty()) content.addView(note("探すには、先に、備品を登録してください。"))
        content.addView(button("設定", primary = false) { show(Screen.SETTINGS) })
    }

    private fun buildRegister() {
        header("登録")
        statusView = note("").also { content.addView(it) }
        messageView = TextView(this).apply {
            textSize = 18f
            setTypeface(null, Typeface.BOLD)
            text = message
            setTextColor(if (messageOk) 0xFF065F46.toInt() else 0xFFB45309.toInt())
        }.also { content.addView(it) }
        content.addView(note(
            if (engine.hasReference()) "歩いて、備品のQRを読んでください。"
            else "最初に、アンカーのQRを、壁に正対して読んでください。",
        ))
        content.addView(title("登録した備品（${registry.size}件）").apply { textSize = 17f })
        for ((_, p) in registry) {
            content.addView(note("・${p.name}　東%.1f 北%.1f（±%.1f m）".format(p.x, p.y, p.errM)))
        }
        content.addView(button("完了して、探す", enabled = registry.isNotEmpty()) { show(Screen.SEARCH) })
    }

    private fun buildSearch() {
        header("探す")
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
        fun field(label: String, value: Double): EditText {
            content.addView(note(label))
            return EditText(this).apply {
                inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL or InputType.TYPE_NUMBER_FLAG_SIGNED
                setText(value.toString())
                textSize = 18f
            }.also { content.addView(it) }
        }
        content.addView(note("アンカーAを原点にします。QRは、AがWest、BがEastです。"))
        val bx = field("アンカーB：東へ（m）。西はマイナス", settings.bx)
        val by = field("アンカーB：北へ（m）。南はマイナス", settings.by)
        val fa = field("アンカーAの壁に正対する向き（°、北が0、東が90）", settings.facingA)
        val fb = field("アンカーBの壁に正対する向き（°）", settings.facingB)
        content.addView(button("保存する") {
            fun num(e: EditText, d: Double) = e.text.toString().toDoubleOrNull() ?: d
            settings = Settings(num(bx, settings.bx), num(by, settings.by), num(fa, settings.facingA), num(fb, settings.facingB))
            store.saveSettings(settings)
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
