package jp.co.ryomo.tanaoroshi.ar

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.opengl.GLES11Ext
import android.opengl.GLES20
import android.opengl.GLSurfaceView
import android.os.Bundle
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import com.google.ar.core.ArCoreApk
import com.google.ar.core.Config
import com.google.ar.core.Pose
import com.google.ar.core.Session
import com.google.ar.core.TrackingState
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10
import kotlin.math.hypot
import kotlin.math.sqrt

/**
 * 試作：ARCoreの追跡だけを使って、「基準点」からの移動量を数字で出す。
 *
 * 「基準点にする」を押した位置を原点にして、そこから、
 *   前（押したときに向いていた方向）に何m、右に何m、高さが何m 動いたかを出す。
 * カメラの映像は出さない（ARCoreを動かすために、1ピクセルのGLSurfaceViewだけ置く）。
 */
class MainActivity : Activity(), GLSurfaceView.Renderer {

    private var session: Session? = null
    private var installRequested = false

    private lateinit var glView: GLSurfaceView
    private lateinit var readout: TextView

    // GLスレッドで使う
    private var textureId = 0
    private var textureSet = false
    private var viewWidth = 1
    private var viewHeight = 1
    private var viewportChanged = false

    // ボタン（UIスレッド）→ GLスレッドへの合図
    @Volatile private var markRequested = false
    private var reference: Pose? = null
    private var refForwardX = 0f
    private var refForwardZ = -1f

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        glView = GLSurfaceView(this).apply {
            preserveEGLContextOnPause = true
            setEGLContextClientVersion(2)
            setRenderer(this@MainActivity)
            renderMode = GLSurfaceView.RENDERMODE_CONTINUOUSLY
        }
        readout = TextView(this).apply {
            textSize = 26f
            gravity = Gravity.CENTER
            text = "ARを準備しています…"
        }
        val markButton = Button(this).apply {
            text = "基準点にする（ここを原点に）"
            textSize = 20f
            setOnClickListener { markRequested = true }
        }
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 96, 32, 32)
            addView(readout, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
            addView(markButton, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 200))
            addView(glView, LinearLayout.LayoutParams(1, 1)) // ARCoreを動かすための、1ピクセル
        }
        setContentView(root)
    }

    override fun onResume() {
        super.onResume()
        if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.CAMERA), 1)
            return
        }
        if (session == null) {
            when (ArCoreApk.getInstance().requestInstall(this, !installRequested)) {
                ArCoreApk.InstallStatus.INSTALL_REQUESTED -> {
                    installRequested = true
                    return
                }
                ArCoreApk.InstallStatus.INSTALLED -> Unit
            }
            try {
                session = Session(this).also { s ->
                    s.configure(Config(s).apply {
                        updateMode = Config.UpdateMode.LATEST_CAMERA_IMAGE
                        planeFindingMode = Config.PlaneFindingMode.DISABLED
                        lightEstimationMode = Config.LightEstimationMode.DISABLED
                    })
                }
                textureSet = false
                viewportChanged = true
            } catch (e: Exception) {
                readout.text = "ARを開始できません：${e.javaClass.simpleName}\n${e.message ?: ""}"
                return
            }
        }
        try {
            session?.resume()
        } catch (e: Exception) {
            readout.text = "ARを再開できません：${e.javaClass.simpleName}\n${e.message ?: ""}"
            session = null
            return
        }
        glView.onResume()
    }

    override fun onPause() {
        super.onPause()
        glView.onPause()
        session?.pause()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (grantResults.firstOrNull() != PackageManager.PERMISSION_GRANTED) {
            readout.text = "カメラの許可が必要です。設定で、許可してください。"
        }
    }

    // ---------------- GLSurfaceView.Renderer（GLスレッド） ----------------

    override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
        GLES20.glClearColor(0f, 0f, 0f, 1f)
        val tex = IntArray(1)
        GLES20.glGenTextures(1, tex, 0)
        textureId = tex[0]
        GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, textureId)
        textureSet = false
    }

    override fun onSurfaceChanged(gl: GL10?, width: Int, height: Int) {
        GLES20.glViewport(0, 0, width, height)
        viewWidth = width
        viewHeight = height
        viewportChanged = true
    }

    override fun onDrawFrame(gl: GL10?) {
        GLES20.glClear(GLES20.GL_COLOR_BUFFER_BIT)
        val s = session ?: return
        if (!textureSet) {
            s.setCameraTextureName(textureId)
            textureSet = true
        }
        if (viewportChanged) {
            @Suppress("DEPRECATION")
            val rotation = windowManager.defaultDisplay.rotation
            s.setDisplayGeometry(rotation, viewWidth, viewHeight)
            viewportChanged = false
        }
        val frame = try {
            s.update()
        } catch (e: Exception) {
            return
        }
        val camera = frame.camera
        if (camera.trackingState != TrackingState.TRACKING) {
            show("追跡できていません（${camera.trackingState}）\n${camera.trackingFailureReason}\n\nカメラを、模様のある壁や床に向けて、ゆっくり動かしてください。")
            return
        }
        val pose = camera.pose

        if (markRequested) {
            markRequested = false
            reference = pose
            // 基準点で向いていた方向（水平面に投影）。以降、「前」はこの向き
            val f = pose.rotateVector(floatArrayOf(0f, 0f, -1f)) // カメラの前方（OpenGLの規約：-Z）
            val len = hypot(f[0], f[2])
            if (len > 1e-3f) {
                refForwardX = f[0] / len
                refForwardZ = f[2] / len
            }
        }
        val ref = reference
        if (ref == null) {
            show("追跡できています。\nアンカーのQRの前に立って、\n「基準点にする」を押してください。")
            return
        }
        val dx = pose.tx() - ref.tx()
        val dy = pose.ty() - ref.ty()
        val dz = pose.tz() - ref.tz()
        // 前＝基準点で向いていた方向、右＝その右手側（世界は、Yが上の右手系）
        val forward = dx * refForwardX + dz * refForwardZ
        val right = dx * (-refForwardZ) + dz * refForwardX
        val horizontal = sqrt(forward * forward + right * right)
        show(
            "前　%+.2f m\n右　%+.2f m\n高さ %+.2f m\n\n水平の距離　%.2f m".format(forward, right, dy, horizontal),
        )
    }

    private fun show(text: String) {
        runOnUiThread { readout.text = text }
    }
}
