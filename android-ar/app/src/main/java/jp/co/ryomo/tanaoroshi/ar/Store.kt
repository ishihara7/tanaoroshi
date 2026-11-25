package jp.co.ryomo.tanaoroshi.ar

import android.content.Context
import org.json.JSONObject

/** 登録した備品の位置（フロア図上。x：東、y：北。単位はm）と、その誤差の見積もり。 */
data class Placed(val name: String, val x: Double, val y: Double, val errM: Double)

/** アンカーの定義。facingDeg：QRを読むとき向く方向（北を0°とした時計回り）。 */
data class AnchorDef(val token: String, val name: String, val x: Double, val y: Double, val facingDeg: Double)

/** 設定。アンカーAを原点とし、アンカーBの位置と、2つのアンカーの壁の向きを持つ。 */
data class Settings(
    val bx: Double = 20.0,
    val by: Double = 0.0,
    val facingA: Double = 0.0,
    val facingB: Double = 0.0,
    /** カメラ映像の向きを、強制する値（0〜3）。-1なら、端末の画面の向きを、そのまま使う */
    val cameraRot: Int = -1,
    /** アンカーBも使うか。通常は、アンカーA（原点）だけで足りる */
    val useB: Boolean = false,
) {
    fun anchors(): List<AnchorDef> = buildList {
        add(AnchorDef("Awest", "アンカーA", 0.0, 0.0, facingA))
        if (useB) add(AnchorDef("Aeast", "アンカーB", bx, by, facingB))
    }
}

/** 端末への保存（設定と、登録した備品）。 */
class Store(context: Context) {
    private val prefs = context.getSharedPreferences("tanaoroshi", Context.MODE_PRIVATE)

    fun loadSettings(): Settings {
        val d = Settings()
        return Settings(
            bx = prefs.getFloat("bx", d.bx.toFloat()).toDouble(),
            by = prefs.getFloat("by", d.by.toFloat()).toDouble(),
            facingA = prefs.getFloat("facingA", d.facingA.toFloat()).toDouble(),
            facingB = prefs.getFloat("facingB", d.facingB.toFloat()).toDouble(),
            cameraRot = prefs.getInt("cameraRot", d.cameraRot),
            useB = prefs.getBoolean("useB", d.useB),
        )
    }

    fun saveSettings(s: Settings) {
        prefs.edit()
            .putFloat("bx", s.bx.toFloat()).putFloat("by", s.by.toFloat())
            .putFloat("facingA", s.facingA.toFloat()).putFloat("facingB", s.facingB.toFloat())
            .putInt("cameraRot", s.cameraRot).putBoolean("useB", s.useB)
            .apply()
    }

    /** 棚卸で、QRを読んで確かめた備品（トークン）。 */
    fun loadConfirmed(): Set<String> = prefs.getStringSet("confirmed", emptySet())?.toSet() ?: emptySet()

    fun saveConfirmed(tokens: Set<String>) {
        prefs.edit().putStringSet("confirmed", tokens).apply()
    }

    /** この端末のデータを、すべて消す（備品・棚卸の進み具合・設定）。 */
    fun clearAll() {
        prefs.edit().clear().apply()
    }

    fun loadRegistry(): LinkedHashMap<String, Placed> {
        val out = LinkedHashMap<String, Placed>()
        try {
            val json = JSONObject(prefs.getString("registry", "{}") ?: "{}")
            for (key in json.keys()) {
                val o = json.getJSONObject(key)
                out[key] = Placed(o.getString("name"), o.getDouble("x"), o.getDouble("y"), o.getDouble("errM"))
            }
        } catch (e: Exception) {
            // 読めなければ、空から始める
        }
        return out
    }

    fun saveRegistry(reg: Map<String, Placed>) {
        val json = JSONObject()
        for ((k, p) in reg) {
            json.put(k, JSONObject().put("name", p.name).put("x", p.x).put("y", p.y).put("errM", p.errM))
        }
        prefs.edit().putString("registry", json.toString()).apply()
    }
}
