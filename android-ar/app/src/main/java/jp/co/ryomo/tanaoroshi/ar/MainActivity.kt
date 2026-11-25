package jp.co.ryomo.tanaoroshi.ar

import android.Manifest
import android.content.pm.PackageManager
import android.opengl.GLSurfaceView
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.HapticFeedbackConstants
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.viewinterop.AndroidView
import jp.co.ryomo.tanaoroshi.ar.ui.CameraRect
import jp.co.ryomo.tanaoroshi.ar.ui.HomeScreen
import jp.co.ryomo.tanaoroshi.ar.ui.RegisterScreen
import jp.co.ryomo.tanaoroshi.ar.ui.InventoryScreen
import jp.co.ryomo.tanaoroshi.ar.ui.SettingsScreen
import jp.co.ryomo.tanaoroshi.ar.ui.TanaoroshiTheme

/**
 * 備品の位置を、ARの追跡で記録し、探す。
 *   登録：アンカーのQRを読む → 歩く → 備品のQRを読む（そのときの位置を登録）
 *   探す：アンカーのQRを読む → 備品を選ぶ → 矢印と距離に従って歩く
 *
 * 画面は Compose。ARCore の描画先（GLSurfaceView）は、1つだけ作って、画面の裏に置き続ける
 * （画面を切り替えても、追跡が切れない）。
 */
class MainActivity : ComponentActivity() {

    private lateinit var engine: ArEngine
    private lateinit var glView: GLSurfaceView
    private lateinit var model: AppModel

    private val handler = Handler(Looper.getMainLooper())
    private val ticker = object : Runnable {
        override fun run() {
            model.tick()
            handler.postDelayed(this, 100)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val store = Store(this)

        engine = ArEngine(this) { text, pose -> runOnUiThread { model.handleQr(text, pose) } }
        engine.rotationOverride = intent.getIntExtra("rot", store.loadSettings().cameraRot) // adbからの指定が、あれば優先
        glView = GLSurfaceView(this).apply {
            preserveEGLContextOnPause = true
            setEGLContextClientVersion(2)
            setEGLConfigChooser(8, 8, 8, 8, 16, 0)
            setRenderer(engine)
            renderMode = GLSurfaceView.RENDERMODE_CONTINUOUSLY
        }
        model = AppModel(engine, store) {
            glView.performHapticFeedback(
                if (Build.VERSION.SDK_INT >= 30) HapticFeedbackConstants.CONFIRM else HapticFeedbackConstants.KEYBOARD_TAP,
            )
        }

        setContent {
            TanaoroshiTheme { AppRoot(model, glView) }
        }
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
        if (error != null) model.say(error, false)
        glView.onResume()
        handler.post(ticker)
    }

    override fun onPause() {
        super.onPause()
        handler.removeCallbacks(ticker)
        glView.onPause()
        engine.pause()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) startAr()
        else model.say("カメラの許可が必要です。設定で、許可してください。", false)
    }
}

/**
 * 一番下に、カメラ（GLSurfaceView）。その上に、画面を重ねる。
 * 登録・探す の画面は、カメラの場所だけ透明にして、映像を見せる。ホーム・設定 は、全面を覆う。
 */
@Composable
private fun AppRoot(model: AppModel, glView: GLSurfaceView) {
    var cam by remember { mutableStateOf<CameraRect?>(null) }
    val density = LocalDensity.current
    Box(Modifier.fillMaxSize()) {
        val r = cam
        if (r != null) {
            AndroidView(
                factory = { glView },
                modifier = Modifier
                    .offset { IntOffset(r.x, r.y) }
                    .size(with(density) { r.w.toDp() }, with(density) { r.h.toDp() }),
            )
        }
        when (model.screen) {
            Screen.HOME -> HomeScreen(model)
            Screen.REGISTER -> RegisterScreen(model) { cam = it }
            Screen.INVENTORY -> InventoryScreen(model) { cam = it }
            Screen.SETTINGS -> SettingsScreen(model)
        }
    }
}
