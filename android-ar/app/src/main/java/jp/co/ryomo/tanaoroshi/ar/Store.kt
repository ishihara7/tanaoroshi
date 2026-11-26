package jp.co.ryomo.tanaoroshi.ar

import android.content.Context
import org.json.JSONObject

/** 登録した備品の位置（フロア図上。x：東、y：北。単位はm）と、その誤差の見積もり。 */
data class Placed(
    val name: String, val x: Double, val y: Double, val errM: Double, val floor: Int = 1,
    /** 位置が分かっているか。想定外を、位置が取れないまま読んだときは false（階だけ分かる） */
    val located: Boolean = true,
    /** 前回の棚卸で、確かめられなかった */
    val missedLast: Boolean = false,
    /** 前回の棚卸で、予定にないのに読まれた */
    val wasUnexpected: Boolean = false,
    /** 台帳の管理番号（手入力で確かめるときに使う）。台帳にない備品は null */
    val assetNo: String? = null,
)

/** 一覧に出す名前。台帳の管理番号があれば、「管理番号　名称」。 */
fun Placed.label(): String = assetNo?.let { "$it　$name" } ?: name

/** 棚卸で、予定にないのに読んだ備品。位置が取れなければ x・y は null。 */
data class Unexpected(val token: String, val name: String, val floor: Int, val x: Double?, val y: Double?)

/** 棚卸で、予定と違う場所（階・位置）で読んだ備品。位置が取れなければ x・y は null。 */
data class MovedAt(val token: String, val floor: Int, val x: Double?, val y: Double?)

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
    /** サーバーのURL（例：https://xxxx.azurewebsites.net）。空なら、同期しない */
    val serverUrl: String = "",
    val loginId: String = "",
    val password: String = "",
    /** 端末の合言葉（管理画面のQRで設定する）。あれば、ログインID・パスワードの代わりに使う */
    val authToken: String = "",
    /** 記録した人の社員番号（半角英数字。空でもよい） */
    val employeeNo: String = "",
    /** 同じ階で、登録位置からこれ以上離れて読んだら「場所違い」（m） */
    val movedThresholdM: Double = MOVED_THRESHOLD_M,
) {
    fun anchors(): List<AnchorDef> = listOf(
        AnchorDef("A", "1階のアンカー（A）", 1, 0.0, 0.0, facingA),
        AnchorDef("B", "2階のアンカー（B）", 2, 0.0, 0.0, facingB),
        AnchorDef("C", "3階のアンカー（C）", 3, 0.0, 0.0, facingC),
    )
}

/** 端末への保存（設定と、登録した備品）。 */
class Store(context: Context) : SyncStorage {
    private val prefs = context.getSharedPreferences("tanaoroshi", Context.MODE_PRIVATE)

    fun loadSettings(): Settings {
        val d = Settings()
        return Settings(
            facingA = prefs.getFloat("facingA", d.facingA.toFloat()).toDouble(),
            facingB = prefs.getFloat("facingB", d.facingB.toFloat()).toDouble(),
            facingC = prefs.getFloat("facingC", d.facingC.toFloat()).toDouble(),
            cameraRot = prefs.getInt("cameraRot", d.cameraRot),
            serverUrl = prefs.getString("serverUrl", d.serverUrl) ?: "",
            loginId = prefs.getString("loginId", d.loginId) ?: "",
            password = prefs.getString("password", d.password) ?: "",
            authToken = prefs.getString("authToken", d.authToken) ?: "",
            employeeNo = prefs.getString("employeeNo", d.employeeNo) ?: "",
            movedThresholdM = prefs.getFloat("movedThresholdM", d.movedThresholdM.toFloat()).toDouble(),
        )
    }

    fun saveSettings(s: Settings) {
        prefs.edit()
            .putFloat("facingA", s.facingA.toFloat()).putFloat("facingB", s.facingB.toFloat())
            .putFloat("facingC", s.facingC.toFloat())
            .putInt("cameraRot", s.cameraRot)
            .putString("serverUrl", s.serverUrl).putString("loginId", s.loginId).putString("password", s.password).putString("authToken", s.authToken)
            .putString("employeeNo", s.employeeNo).putFloat("movedThresholdM", s.movedThresholdM.toFloat())
            .apply()
    }

    /** 棚卸で、QRを読んで確かめた備品（トークン）。 */
    fun loadConfirmed(): Set<String> = prefs.getStringSet("confirmed", emptySet())?.toSet() ?: emptySet()

    fun saveConfirmed(tokens: Set<String>) {
        prefs.edit().putStringSet("confirmed", tokens).apply()
    }

    // ---- サーバーへの送信待ち・サーバーから取得した写し ----

    private val outboxLock = Any()

    override fun loadOutbox(): List<Op> = synchronized(outboxLock) { readOutbox() }

    private fun readOutbox(): List<Op> = try {
        val a = org.json.JSONArray(prefs.getString("outbox", "[]") ?: "[]")
        (0 until a.length()).mapNotNull { opFromJson(a.getJSONObject(it)) }
    } catch (e: Exception) {
        emptyList()
    }

    /** 送信待ちを、読んで、書き換えて、保存する（画面の操作と、裏の送信が、同時に触っても壊れないように、まとめて行う）。 */
    override fun updateOutbox(change: (List<Op>) -> List<Op>): List<Op> = synchronized(outboxLock) {
        val next = change(readOutbox())
        val a = org.json.JSONArray()
        next.forEach { a.put(it.toJson()) }
        prefs.edit().putString("outbox", a.toString()).apply()
        next
    }

    /** 最後に、サーバーで終えた棚卸のID（「終える」の取り消しに使う）。 */
    override var lastFinishedInventoryId: Int?
        get() = if (prefs.contains("lastFinishedInv")) prefs.getInt("lastFinishedInv", 0) else null
        set(v) {
            prefs.edit().apply { if (v == null) remove("lastFinishedInv") else putInt("lastFinishedInv", v) }.apply()
        }

    /** サーバーから取得した台帳の備品（管理対象のタグ）。オフラインでも、登録の可否を判断できるように、写しを持つ。 */
    fun loadLedger(): List<LedgerAsset> = try {
        val a = org.json.JSONArray(prefs.getString("ledger", "[]") ?: "[]")
        (0 until a.length()).map {
            val o = a.getJSONObject(it)
            LedgerAsset(o.getString("t"), o.getString("n"), o.getString("m"))
        }
    } catch (e: Exception) {
        emptyList()
    }

    fun saveLedger(list: List<LedgerAsset>) {
        val a = org.json.JSONArray()
        list.forEach { a.put(JSONObject().put("t", it.token).put("n", it.assetNo).put("m", it.name)) }
        prefs.edit().putString("ledger", a.toString()).apply()
    }

    /** サーバーから取得したアンカー（オフラインでも使えるように、写しを持つ）。 */
    fun loadAnchors(): List<ServerAnchor> = try {
        val a = org.json.JSONArray(prefs.getString("anchors", "[]") ?: "[]")
        (0 until a.length()).map {
            val o = a.getJSONObject(it)
            ServerAnchor(
                o.getString("token"), o.getString("name"), o.getInt("floor"), o.getDouble("x"), o.getDouble("y"),
                if (o.isNull("facing")) null else o.getDouble("facing"),
            )
        }
    } catch (e: Exception) {
        emptyList()
    }

    fun saveAnchors(list: List<ServerAnchor>) {
        val a = org.json.JSONArray()
        list.forEach {
            a.put(JSONObject().put("token", it.token).put("name", it.name).put("floor", it.floor).put("x", it.xM).put("y", it.yM).putOpt("facing", it.facingDeg))
        }
        prefs.edit().putString("anchors", a.toString()).apply()
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
                out[key] = Placed(
                    o.getString("name"), o.getDouble("x"), o.getDouble("y"), o.getDouble("errM"), o.optInt("floor", 1),
                    o.optBoolean("located", true), o.optBoolean("missedLast", false), o.optBoolean("wasUnexpected", false),
                    if (o.has("assetNo") && !o.isNull("assetNo")) o.getString("assetNo") else null,
                )
            }
        } catch (e: Exception) {
            // 読めなければ、空から始める
        }
        return out
    }

    fun saveRegistry(reg: Map<String, Placed>) {
        val json = JSONObject()
        for ((k, p) in reg) {
            json.put(k, JSONObject().put("name", p.name).put("x", p.x).put("y", p.y).put("errM", p.errM).put("floor", p.floor)
                .put("located", p.located).put("missedLast", p.missedLast).put("wasUnexpected", p.wasUnexpected)
                .putOpt("assetNo", p.assetNo))
        }
        prefs.edit().putString("registry", json.toString()).apply()
    }

    /** 今回の棚卸で、予定にないのに読んだ備品と、予定と違う場所で読んだ備品。 */
    fun loadUnexpected(): LinkedHashMap<String, Unexpected> {
        val out = LinkedHashMap<String, Unexpected>()
        try {
            val json = JSONObject(prefs.getString("unexpected", "{}") ?: "{}")
            for (k in json.keys()) {
                val o = json.getJSONObject(k)
                out[k] = Unexpected(k, o.getString("name"), o.getInt("floor"), o.optDoubleOrNull("x"), o.optDoubleOrNull("y"))
            }
        } catch (e: Exception) {
        }
        return out
    }

    fun saveUnexpected(m: Map<String, Unexpected>) {
        val json = JSONObject()
        for ((k, u) in m) {
            json.put(k, JSONObject().put("name", u.name).put("floor", u.floor).putOpt("x", u.x).putOpt("y", u.y))
        }
        prefs.edit().putString("unexpected", json.toString()).apply()
    }

    fun loadMoved(): LinkedHashMap<String, MovedAt> {
        val out = LinkedHashMap<String, MovedAt>()
        try {
            val json = JSONObject(prefs.getString("moved", "{}") ?: "{}")
            for (k in json.keys()) {
                val o = json.getJSONObject(k)
                out[k] = MovedAt(k, o.getInt("floor"), o.optDoubleOrNull("x"), o.optDoubleOrNull("y"))
            }
        } catch (e: Exception) {
        }
        return out
    }

    fun saveMoved(m: Map<String, MovedAt>) {
        val json = JSONObject()
        for ((k, v) in m) json.put(k, JSONObject().put("floor", v.floor).putOpt("x", v.x).putOpt("y", v.y))
        prefs.edit().putString("moved", json.toString()).apply()
    }

    private fun JSONObject.optDoubleOrNull(key: String): Double? = if (has(key) && !isNull(key)) getDouble(key) else null
}
