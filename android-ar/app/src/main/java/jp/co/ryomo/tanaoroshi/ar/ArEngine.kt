package jp.co.ryomo.tanaoroshi.ar

import android.app.Activity
import android.opengl.GLES11Ext
import android.opengl.GLES20
import android.opengl.GLSurfaceView
import com.google.ar.core.ArCoreApk
import com.google.ar.core.Config
import com.google.ar.core.Session
import com.google.ar.core.TrackingState
import com.google.ar.core.exceptions.NotYetAvailableException
import com.google.zxing.BarcodeFormat
import com.google.zxing.BinaryBitmap
import com.google.zxing.DecodeHintType
import com.google.zxing.PlanarYUVLuminanceSource
import com.google.zxing.common.HybridBinarizer
import com.google.zxing.qrcode.QRCodeReader
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer
import java.util.concurrent.Executors
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10
import kotlin.math.hypot

/** QRを読んだ瞬間の、カメラの位置と向き（ARの世界座標）。 */
class PoseSnapshot(val px: Double, val pz: Double, val fx: Double, val fz: Double)

/** いまの状態（GLスレッドが更新し、画面が読む）。 */
class Live(
    val tracking: Boolean,
    val trackingNote: String,
    /** アンカーのQRを読んでいれば、フロア図上の位置と向き。なければ null */
    val mapX: Double?,
    val mapY: Double?,
    val bearing: Double?,
    val walkedM: Double,
    /** 追跡が途切れたことがある（アンカーを読み直すまで、位置を信用できない） */
    val lostTracking: Boolean,
)

/**
 * ARCoreを動かし、カメラ映像を出し、QRを読み、フロア図上の位置を計算する。
 * ARCoreは、GLスレッドで update() を呼ぶ必要がある（GLSurfaceView.Renderer を兼ねる）。
 */
class ArEngine(
    private val activity: Activity,
    private val onQr: (text: String, pose: PoseSnapshot) -> Unit,
) : GLSurfaceView.Renderer {

    private var session: Session? = null
    private var installRequested = false

    @Volatile var live = Live(false, "ARを準備しています…", null, null, null, 0.0, false)
        private set

    @Volatile private var reference: ArReference? = null

    // GLスレッドの内部状態
    private var textureId = 0
    private var textureSet = false
    private var viewWidth = 1
    private var viewHeight = 1
    private var viewportChanged = true
    private var lastX = 0.0
    private var lastZ = 0.0
    private var hasLast = false
    private var walked = 0.0
    private var lost = false
    private var lastFx = 0.0
    private var lastFz = -1.0
    private var lastLogAt = 0L
    /** 確認用：ARCoreに伝える画面の向き（0〜3）を、強制する。-1なら、本来の値を使う */
    @Volatile var rotationOverride = -1
        set(value) {
            field = value
            viewportChanged = true // 次のフレームで、ARCoreに、画面の向きを伝え直す
        }

    // 背景（カメラ映像）
    private var program = 0
    private var posAttr = 0
    private var texAttr = 0
    private val quadCoords: FloatBuffer = floatBuffer(floatArrayOf(-1f, -1f, -1f, 1f, 1f, -1f, 1f, 1f))
    private val quadTexCoords: FloatBuffer = floatBuffer(FloatArray(8))

    // QRの読み取り（別スレッド）
    private val decoder = Executors.newSingleThreadExecutor()
    @Volatile private var decoding = false
    private var lastDecodeAt = 0L
    private var lastText = ""
    private var lastTextAt = 0L

    /** アンカーのQRを読んだ瞬間のカメラの位置と向きを、そのアンカーの座標に結びつける。 */
    fun setReference(pose: PoseSnapshot, anchorX: Double, anchorY: Double, thetaDeg: Double) {
        reference = ArReference(pose.px, pose.pz, pose.fx, pose.fz, anchorX, anchorY, thetaDeg)
        walked = 0.0
        lost = false
    }

    fun hasReference(): Boolean = reference != null

    /** 現在位置を、フロア図上の座標にする（QRを読んだ時点のカメラの位置から）。 */
    fun mapAt(pose: PoseSnapshot): Pair<Double, Double>? = reference?.toMap(pose.px, pose.pz)

    /** @return 準備できたら true */
    fun resume(): String? {
        if (session == null) {
            when (ArCoreApk.getInstance().requestInstall(activity, !installRequested)) {
                ArCoreApk.InstallStatus.INSTALL_REQUESTED -> {
                    installRequested = true
                    return "ARCoreのインストールを求めています。"
                }
                ArCoreApk.InstallStatus.INSTALLED -> Unit
            }
            try {
                session = Session(activity).also { s ->
                    s.configure(Config(s).apply {
                        updateMode = Config.UpdateMode.LATEST_CAMERA_IMAGE
                        planeFindingMode = Config.PlaneFindingMode.DISABLED
                        lightEstimationMode = Config.LightEstimationMode.DISABLED
                        focusMode = Config.FocusMode.AUTO
                    })
                }
                textureSet = false
                viewportChanged = true
            } catch (e: Exception) {
                return "ARを開始できません：${e.javaClass.simpleName} ${e.message ?: ""}"
            }
        }
        return try {
            session?.resume()
            null
        } catch (e: Exception) {
            session = null
            "ARを再開できません：${e.javaClass.simpleName} ${e.message ?: ""}"
        }
    }

    fun pause() {
        session?.pause()
    }

    // ---------------- GLSurfaceView.Renderer ----------------

    override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
        GLES20.glClearColor(0f, 0f, 0f, 1f)
        val tex = IntArray(1)
        GLES20.glGenTextures(1, tex, 0)
        textureId = tex[0]
        GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, textureId)
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_WRAP_S, GLES20.GL_CLAMP_TO_EDGE)
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_WRAP_T, GLES20.GL_CLAMP_TO_EDGE)
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_MIN_FILTER, GLES20.GL_LINEAR)
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_MAG_FILTER, GLES20.GL_LINEAR)
        textureSet = false

        val vs = compile(GLES20.GL_VERTEX_SHADER, VERTEX)
        val fs = compile(GLES20.GL_FRAGMENT_SHADER, FRAGMENT)
        program = GLES20.glCreateProgram().also {
            GLES20.glAttachShader(it, vs)
            GLES20.glAttachShader(it, fs)
            GLES20.glLinkProgram(it)
        }
        posAttr = GLES20.glGetAttribLocation(program, "a_Position")
        texAttr = GLES20.glGetAttribLocation(program, "a_TexCoord")
        viewportChanged = true
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
            val rotation = if (rotationOverride >= 0) rotationOverride else activity.windowManager.defaultDisplay.rotation
            s.setDisplayGeometry(rotation, viewWidth, viewHeight)
            viewportChanged = false
        }
        val frame = try {
            s.update()
        } catch (e: Exception) {
            return
        }

        // 背景（カメラ映像）
        // 画面の向き・大きさに合わせて、映像の切り出し位置を、毎フレーム計算する（変わったときだけだと、ずれることがあった）
        quadCoords.position(0)
        quadTexCoords.position(0)
        frame.transformDisplayUvCoords(quadCoords, quadTexCoords)
        if (System.currentTimeMillis() - lastLogAt > 2000) {
            lastLogAt = System.currentTimeMillis()
            val t = FloatArray(8); quadTexCoords.position(0); quadTexCoords.get(t); quadTexCoords.position(0)
            @Suppress("DEPRECATION")
            val rot = activity.windowManager.defaultDisplay.rotation
            android.util.Log.d("ArEngine", "view=${viewWidth}x${viewHeight} rot=$rot tex=${t.joinToString(",") { "%.2f".format(it) }}")
        }
        drawBackground()

        val camera = frame.camera
        if (camera.trackingState != TrackingState.TRACKING) {
            hasLast = false
            if (reference != null) lost = true
            live = Live(false, "追跡できていません（${camera.trackingFailureReason}）。模様のある壁や床に向けて、ゆっくり動かしてください。",
                null, null, null, walked, lost)
            return
        }
        val pose = camera.pose
        val px = pose.tx().toDouble()
        val pz = pose.tz().toDouble()
        val f = pose.rotateVector(floatArrayOf(0f, 0f, -1f))
        val fh = hypot(f[0].toDouble(), f[2].toDouble())
        if (fh > 0.2) { // カメラが真上や真下を向いているときは、向きを更新しない
            lastFx = f[0] / fh
            lastFz = f[2] / fh
        }

        if (hasLast) {
            val step = hypot(px - lastX, pz - lastZ)
            if (step < 1.0) walked += step // 追跡が飛んだときの、ありえない距離は足さない
        }
        lastX = px; lastZ = pz; hasLast = true

        val ref = reference
        live = if (ref == null) {
            Live(true, "追跡できています。アンカーのQRを読み取ってください。", null, null, null, 0.0, false)
        } else {
            val (mx, my) = ref.toMap(px, pz)
            Live(true, "", mx, my, ref.bearingOf(lastFx, lastFz), walked, lost)
        }

        maybeDecode(frame, PoseSnapshot(px, pz, lastFx, lastFz))
    }

    // ---------------- QR ----------------

    private fun maybeDecode(frame: com.google.ar.core.Frame, pose: PoseSnapshot) {
        val now = System.currentTimeMillis()
        if (decoding || now - lastDecodeAt < 200) return
        val image = try {
            frame.acquireCameraImage()
        } catch (e: NotYetAvailableException) {
            return
        } catch (e: Exception) {
            return
        }
        lastDecodeAt = now
        val w = image.width
        val h = image.height
        val data = ByteArray(w * h)
        try {
            val plane = image.planes[0] // Y（明るさ）だけで足りる
            val buf = plane.buffer
            val rowStride = plane.rowStride
            for (row in 0 until h) {
                buf.position(row * rowStride)
                buf.get(data, row * w, w)
            }
        } finally {
            image.close()
        }
        decoding = true
        decoder.execute {
            try {
                val source = PlanarYUVLuminanceSource(data, w, h, 0, 0, w, h, false)
                val bitmap = BinaryBitmap(HybridBinarizer(source))
                val hints = mapOf(
                    DecodeHintType.TRY_HARDER to true,
                    DecodeHintType.POSSIBLE_FORMATS to listOf(BarcodeFormat.QR_CODE),
                )
                val text = QRCodeReader().decode(bitmap, hints).text
                val t = System.currentTimeMillis()
                // 同じQRが映り続けても、4秒は続けて渡さない
                if (text != lastText || t - lastTextAt > 4000) {
                    lastText = text
                    lastTextAt = t
                    onQr(text, pose)
                }
            } catch (e: Exception) {
                // QRが映っていないフレームは、読み取れなくて当然
            } finally {
                decoding = false
            }
        }
    }

    // ---------------- 背景の描画 ----------------

    private fun drawBackground() {
        GLES20.glDisable(GLES20.GL_DEPTH_TEST)
        GLES20.glDepthMask(false)
        GLES20.glUseProgram(program)
        GLES20.glActiveTexture(GLES20.GL_TEXTURE0)
        GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, textureId)
        quadCoords.position(0)
        quadTexCoords.position(0)
        GLES20.glVertexAttribPointer(posAttr, 2, GLES20.GL_FLOAT, false, 0, quadCoords)
        GLES20.glVertexAttribPointer(texAttr, 2, GLES20.GL_FLOAT, false, 0, quadTexCoords)
        GLES20.glEnableVertexAttribArray(posAttr)
        GLES20.glEnableVertexAttribArray(texAttr)
        GLES20.glDrawArrays(GLES20.GL_TRIANGLE_STRIP, 0, 4)
        GLES20.glDisableVertexAttribArray(posAttr)
        GLES20.glDisableVertexAttribArray(texAttr)
        GLES20.glDepthMask(true)
        GLES20.glEnable(GLES20.GL_DEPTH_TEST)
    }

    private fun compile(type: Int, src: String): Int {
        val id = GLES20.glCreateShader(type)
        GLES20.glShaderSource(id, src)
        GLES20.glCompileShader(id)
        return id
    }

    companion object {
        private const val VERTEX = """
            attribute vec4 a_Position;
            attribute vec2 a_TexCoord;
            varying vec2 v_TexCoord;
            void main() {
                gl_Position = a_Position;
                v_TexCoord = a_TexCoord;
            }
        """
        private const val FRAGMENT = """
            #extension GL_OES_EGL_image_external : require
            precision mediump float;
            varying vec2 v_TexCoord;
            uniform samplerExternalOES sTexture;
            void main() {
                gl_FragColor = texture2D(sTexture, v_TexCoord);
            }
        """

        private fun floatBuffer(values: FloatArray): FloatBuffer =
            ByteBuffer.allocateDirect(values.size * 4).order(ByteOrder.nativeOrder()).asFloatBuffer().apply {
                put(values)
                position(0)
            }
    }
}
