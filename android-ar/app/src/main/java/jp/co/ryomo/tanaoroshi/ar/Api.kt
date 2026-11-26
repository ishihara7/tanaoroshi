package jp.co.ryomo.tanaoroshi.ar

import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.time.Instant

/** サーバーのアンカー（位置合わせの基準点）。向きは、未設定なら null。 */
data class ServerAnchor(val token: String, val name: String, val floor: Int, val xM: Double, val yM: Double, val facingDeg: Double?)

/** サーバーの予定。端末は、これを写しとして持つ。inventoryId：開いている棚卸（なければ null）。 */
data class ServerPlan(val csrf: String, val anchors: List<ServerAnchor>, val items: List<PlacedItem>, val inventoryId: Int?)

/** ログインが必要、または、ログインし直しが必要（401・CSRFの期限切れ・ID/パスワードの誤り）。 */
class AuthException(message: String) : Exception(message)

/** サーバーが、操作を断った（4xx・5xx）。code：HTTPのステータス。 */
class ApiException(val code: Int, message: String) : Exception(message)

/** 記録1件の送信結果。status：ok／duplicate／error。 */
data class RecordResult(val clientId: String, val status: String, val message: String)

/**
 * サーバー（FastAPI）との通信。ログインは、既存の画面と同じ（Cookie のセッション＋CSRF）。
 * ネットワークの失敗は IOException。1つのインスタンスは、1つのスレッドから使う。
 */
class ApiClient(baseUrl: String, private val timeoutMs: Int = 15000) {
    private val base = baseUrl.trim().trimEnd('/')
    private val cookies = LinkedHashMap<String, String>()
    private var csrf = ""

    private class Resp(val code: Int, val body: String, val location: String?)

    private fun request(method: String, path: String, body: ByteArray? = null, contentType: String? = null, withCsrf: Boolean = false): Resp {
        val c = URL(base + path).openConnection() as HttpURLConnection
        try {
            c.requestMethod = method
            c.connectTimeout = timeoutMs
            c.readTimeout = timeoutMs
            c.instanceFollowRedirects = false
            c.setRequestProperty("Accept", "application/json, text/html")
            if (cookies.isNotEmpty()) c.setRequestProperty("Cookie", cookies.entries.joinToString("; ") { "${it.key}=${it.value}" })
            if (withCsrf) c.setRequestProperty("X-CSRF-Token", csrf)
            if (body != null) {
                c.doOutput = true
                c.setRequestProperty("Content-Type", contentType ?: "application/json")
                c.outputStream.use { it.write(body) }
            }
            val code = c.responseCode
            // ヘッダー名の大文字・小文字は、サーバーによって違う（uvicorn は小文字）ので、区別せずに探す
            c.headerFields.filterKeys { it.equals("Set-Cookie", ignoreCase = true) }.values.flatten().forEach { line ->
                val pair = line.substringBefore(';')
                val k = pair.substringBefore('=').trim()
                val v = pair.substringAfter('=', "").trim()
                if (k.isNotEmpty()) if (v.isEmpty()) cookies.remove(k) else cookies[k] = v
            }
            val stream = if (code >= 400) c.errorStream else c.inputStream
            val text = stream?.use { String(it.readBytes(), Charsets.UTF_8) } ?: ""
            return Resp(code, text, c.getHeaderField("Location"))
        } finally {
            c.disconnect()
        }
    }

    private fun check(r: Resp): Resp {
        if (r.code == 401) throw AuthException("ログインが切れました。")
        if (r.code in 200..299) return r
        val msg = try { JSONObject(r.body).optString("detail", "") } catch (e: Exception) { "" }
        if (r.code == 403 && msg.contains("画面の有効期限")) throw AuthException("画面の有効期限が切れました。")
        throw ApiException(r.code, msg.ifEmpty { "サーバーが、操作を受け付けませんでした（${r.code}）。" })
    }

    /** ログインする（ID・パスワードの誤りは AuthException）。 */
    fun login(loginId: String, password: String) {
        cookies.clear()
        val page = request("GET", "/login")
        if (page.code != 200) throw ApiException(page.code, "サーバーに接続できません（${page.code}）。")
        val token = Regex("name=\"csrf_token\" value=\"([^\"]+)\"").find(page.body)?.groupValues?.get(1)
            ?: throw ApiException(500, "ログイン画面を読み取れませんでした。サーバーのURLを確認してください。")
        fun enc(s: String) = URLEncoder.encode(s, "UTF-8")
        val form = "login_id=${enc(loginId)}&password=${enc(password)}&next=${enc("/")}&csrf_token=${enc(token)}"
        val r = request("POST", "/login", form.toByteArray(), "application/x-www-form-urlencoded")
        if (r.code != 303) throw AuthException("IDまたはパスワードが違います。")
        if (r.location?.endsWith("/account/password") == true) throw AuthException("先に、Webでパスワードを変更してください。")
    }

    /** 予定・アンカー・開いている棚卸を取得する（CSRFトークンも、ここで受け取る）。 */
    fun getPlan(): ServerPlan {
        val o = JSONObject(check(request("GET", "/api/ar/plan")).body)
        csrf = o.getString("csrf")
        val anchors = o.getJSONArray("anchors").let { a ->
            (0 until a.length()).map {
                val x = a.getJSONObject(it)
                ServerAnchor(
                    x.getString("token"), x.getString("name"), x.getInt("floor"), x.getDouble("x_m"), x.getDouble("y_m"),
                    if (x.isNull("facing_deg")) null else x.getDouble("facing_deg"),
                )
            }
        }
        val items = o.getJSONArray("items").let { a ->
            (0 until a.length()).map {
                val x = a.getJSONObject(it)
                PlacedItem(
                    x.getString("token"),
                    Placed(
                        x.getString("name"), x.getDouble("x"), x.getDouble("y"), x.getDouble("err_m"), x.getInt("floor"),
                        x.getBoolean("located"), x.getBoolean("missed_last"), x.getBoolean("was_unexpected"),
                        if (x.isNull("asset_no")) null else x.getString("asset_no"),
                    ),
                )
            }
        }
        val inv = if (o.isNull("inventory")) null else o.getJSONObject("inventory").getInt("id")
        return ServerPlan(csrf, anchors, items, inv)
    }

    fun putItem(op: PutItemOp) {
        val body = JSONObject().put("floor", op.floor).put("x", op.x).put("y", op.y).put("err_m", op.errM).put("name", op.name)
        check(request("PUT", "/api/ar/items/${op.token}", body.toString().toByteArray(), withCsrf = true))
    }

    fun deleteItem(op: DeleteItemOp) {
        check(request("DELETE", "/api/ar/items/${op.token}", withCsrf = true))
    }

    /** 記録をまとめて送る。記録ごとの結果を返す。 */
    fun postRecords(ops: List<RecordOp>): List<RecordResult> {
        val arr = JSONArray()
        for (r in ops) {
            arr.put(
                JSONObject().put("client_id", r.id).put("kind", r.kind).put("token", r.token).put("method", r.method)
                    .putOpt("floor", r.floor).putOpt("x", r.x).putOpt("y", r.y).put("moved", r.moved)
                    .put("employee_no", r.employeeNo).put("read_at", Instant.ofEpochMilli(r.readAtMs).toString()),
            )
        }
        val body = JSONObject().put("records", arr).toString().toByteArray()
        val res = JSONObject(check(request("POST", "/api/ar/records", body, withCsrf = true)).body).getJSONArray("results")
        return (0 until res.length()).map {
            val x = res.getJSONObject(it)
            RecordResult(x.optString("client_id"), x.optString("status"), x.optString("message"))
        }
    }

    fun finish(inventoryId: Int, errM: Double) {
        check(request("POST", "/api/ar/inventories/$inventoryId/finish?err_m=$errM", ByteArray(0), withCsrf = true))
    }

    fun undoFinish(inventoryId: Int) {
        check(request("POST", "/api/ar/inventories/$inventoryId/undo-finish", ByteArray(0), withCsrf = true))
    }
}

/** ネットワークの失敗（電波がない・サーバーに届かない）。あとで、再送する。 */
fun isNetworkFailure(e: Throwable) = e is IOException
