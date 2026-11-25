package jp.co.ryomo.tanaoroshi.ar

import android.content.Context
import org.json.JSONObject

/** 登録した備品の位置（フロア図上。x：東、y：北。単位はm）と、その誤差の見積もり。 */
data class Placed(val name: String, val x: Double, val y: Double, val errM: Double, val floor: Int = 1)

/** 階の表示。アンカーの記号つき（1階＝A、2階＝B、3階＝C）。 */
fun floorLabel(floor: Int): String = "${floor}階（${"ABC".getOrElse(floor - 1) { '?' }}）"

/** アンカーの定義。floor：そのアンカーがある階。facingDeg：QRを読むとき向く方向（北を0°とした時計回り）。 */
data class AnchorDef(val token: String, val name: String, val floor: Int, val x: Double, val y: Double, val facingDeg: Double)

/** 設定。アンカーA・B・Cは、それぞれ1階・2階・3階の原点。壁の向きを、階ごとに持つ。 */
data class Settings(
    val facingA: Double = 0.0,
    val facingB: Double = 0.0,
    val facingC: Double = 0.0,
    /** カメラ映像の向きを、強制する値（0〜3）。-1なら、端末の画面の向きを、そのまま使う */
    val cameraRot: Int = -1,
) {
    fun anchors(): List<AnchorDef> = listOf(
        AnchorDef("A", "1階のアンカー（A）", 1, 0.0, 0.0, facingA),
        AnchorDef("B", "2階のアンカー（B）", 2, 0.0, 0.0, facingB),
        AnchorDef("C", "3階のアンカー（C）", 3, 0.0, 0.0, facingC),
    )
}

/** 端末への保存（設定と、登録した備品）。 */
class Store(context: Context) {
    private val prefs = context.getSharedPreferences("tanaoroshi", Context.MODE_PRIVATE)

    fun loadSettings(): Settings {
        val d = Settings()
        return Settings(
            facingA = prefs.getFloat("facingA", d.facingA.toFloat()).toDouble(),
            facingB = prefs.getFloat("facingB", d.facingB.toFloat()).toDouble(),
            facingC = prefs.getFloat("facingC", d.facingC.toFloat()).toDouble(),
            cameraRot = prefs.getInt("cameraRot", d.cameraRot),
        )
    }

    fun saveSettings(s: Settings) {
        prefs.edit()
            .putFloat("facingA", s.facingA.toFloat()).putFloat("facingB", s.facingB.toFloat())
            .putFloat("facingC", s.facingC.toFloat())
            .putInt("cameraRot", s.cameraRot)
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
                out[key] = Placed(o.getString("name"), o.getDouble("x"), o.getDouble("y"), o.getDouble("errM"), o.optInt("floor", 1))
            }
        } catch (e: Exception) {
            // 読めなければ、空から始める
        }
        return out
    }

    fun saveRegistry(reg: Map<String, Placed>) {
        val json = JSONObject()
        for ((k, p) in reg) {
            json.put(k, JSONObject().put("name", p.name).put("x", p.x).put("y", p.y).put("errM", p.errM).put("floor", p.floor))
        }
        prefs.edit().putString("registry", json.toString()).apply()
    }
}
