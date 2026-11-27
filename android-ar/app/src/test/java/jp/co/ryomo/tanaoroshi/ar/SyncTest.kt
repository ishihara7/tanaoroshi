package jp.co.ryomo.tanaoroshi.ar

import com.sun.net.httpserver.HttpExchange
import com.sun.net.httpserver.HttpServer
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.net.InetSocketAddress

/** メモリ上の保存先（実機では Store）。 */
private class MemStorage : SyncStorage {
    var outbox: List<Op> = emptyList()
    override fun loadOutbox() = outbox
    override fun updateOutbox(change: (List<Op>) -> List<Op>): List<Op> = change(outbox).also { outbox = it }
    override var lastFinishedInventoryId: Int? = null
}

/** サーバーの代わり（ログイン・予定・記録・終了を、決まった形で返す）。呼ばれた内容を、記録する。 */
private class FakeServer {
    val calls = mutableListOf<String>()
    val cookieSeen = mutableListOf<String?>()
    val authorizations = mutableListOf<String>()
    val receivedIds = mutableSetOf<String>()
    var inventoryId: Int? = 5
    var refuseRecordsWith = 0 // 0以外なら、記録の送信をそのコードで断る
    var refuseItemsWith = 0
    private val server: HttpServer = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
    val url get() = "http://127.0.0.1:${server.address.port}"

    init {
        server.createContext("/") { ex ->
            val body = ex.requestBody.readBytes().toString(Charsets.UTF_8)
            val key = "${ex.requestMethod} ${ex.requestURI.path}"
            calls += key
            cookieSeen += ex.requestHeaders.getFirst("Cookie")
            ex.requestHeaders.getFirst("Authorization")?.let { authorizations += it }
            val authed = ex.requestHeaders.getFirst("Cookie")?.contains("session=ok") == true ||
                ex.requestHeaders.getFirst("Authorization") == "Bearer DEVTOKEN1"
            when {
                key == "GET /login" -> {
                    ex.responseHeaders.add("Set-Cookie", "session=anon; path=/; HttpOnly")
                    reply(ex, 200, """<input type="hidden" name="csrf_token" value="TOK123">""", "text/html")
                }
                key == "POST /login" -> if (body.contains("login_id=taro") && body.contains("password=pw%21") && body.contains("csrf_token=TOK123")) {
                    ex.responseHeaders.add("Set-Cookie", "session=ok; path=/; HttpOnly")
                    ex.responseHeaders.add("Location", "/")
                    reply(ex, 303, "")
                } else reply(ex, 400, "bad", "text/html")
                key == "POST /api/ar/enroll" -> if (JSONObject(body).optString("code") == "validcode0123456789") {
                    reply(ex, 200, """{"token":"DEVTOKEN1","login_id":"taro"}""")
                } else reply(ex, 400, """{"detail":"設定用のQRが、無効です。"}""")
                !authed -> reply(ex, 401, """{"detail":"ログインしてください。"}""")
                key == "GET /api/ar/plan" -> reply(ex, 200, plan())
                ex.requestHeaders.getFirst("X-CSRF-Token") != "CSRF1" -> reply(ex, 403, """{"detail":"画面の有効期限が切れました。"}""")
                key.startsWith("PUT /api/ar/items/") || key.startsWith("DELETE /api/ar/items/") ->
                    if (refuseItemsWith != 0) reply(ex, refuseItemsWith, """{"detail":"断りました"}""") else reply(ex, 200, "{}")
                key == "POST /api/ar/records" -> if (refuseRecordsWith != 0) reply(ex, refuseRecordsWith, """{"detail":"x"}""") else {
                    val recs = JSONObject(body).getJSONArray("records")
                    val results = (0 until recs.length()).map {
                        val id = recs.getJSONObject(it).getString("client_id")
                        JSONObject().put("client_id", id).put("status", if (receivedIds.add(id)) "ok" else "duplicate")
                    }
                    reply(ex, 200, JSONObject().put("results", org.json.JSONArray(results)).toString())
                }
                key.endsWith("/finish") || key.endsWith("/undo-finish") -> reply(ex, 200, """{"ok":true}""")
                else -> reply(ex, 404, "{}")
            }
        }
        server.start()
    }

    private fun plan() = JSONObject(
        """{"csrf":"CSRF1","anchors":[{"token":"Aabc","name":"1階入口","floor":1,"x_m":0.0,"y_m":0.0,"facing_deg":90.0},
            {"token":"Adef","name":"2階入口","floor":2,"x_m":1.0,"y_m":2.0,"facing_deg":null}],
           "items":[{"token":"Tnote01","asset_no":"A001","name":"ノートPC","floor":1,"x":3.0,"y":4.0,"err_m":0.5,
                     "located":true,"missed_last":false,"was_unexpected":false}],
           "assets":[{"token":"Tnote01","asset_no":"A001","name":"ノートPC"},{"token":"Tproj01","asset_no":"A002","name":"プロジェクター"}],
           "inventory":${inventoryId?.let { """{"id":$it}""" } ?: "null"}}""",
    ).toString()

    private fun reply(ex: HttpExchange, code: Int, text: String, type: String = "application/json") {
        val bytes = text.toByteArray()
        ex.responseHeaders.add("Content-Type", "$type; charset=utf-8")
        ex.sendResponseHeaders(code, if (code == 303) -1 else bytes.size.toLong())
        if (code != 303) ex.responseBody.use { it.write(bytes) }
        ex.close()
    }

    fun stop() = server.stop(0)
    fun count(key: String) = calls.count { it == key }
}

class SyncTest {
    private lateinit var server: FakeServer
    private lateinit var storage: MemStorage
    private var plans = mutableListOf<ServerPlan>()
    private var statuses = mutableListOf<SyncStatus>()
    private var settings = Settings(serverUrl = "", loginId = "taro", password = "pw!")

    private fun controller() = SyncController(
        storage, { settings }, { it() }, { plans += it }, { statuses += it }, newItemErrM = { 0.5 },
    )

    private fun rec(id: String) = RecordOp(id, "read", "Tnote01", "qr", 1, 1.0, 2.0, false, "E1", 1000L)

    @Before
    fun setUp() {
        server = FakeServer()
        storage = MemStorage()
        settings = settings.copy(serverUrl = server.url)
    }

    @After
    fun tearDown() = server.stop()

    @Test
    fun 送信待ちを順に送り_終わったら予定を受け取る() {
        storage.outbox = listOf(PutItemOp("p", "Tnote01", "PC", 1, 3.0, 4.0, 0.5), rec("r1"), rec("r2"), FinishOp("f"))
        controller().runOnce()
        assertTrue(storage.outbox.isEmpty())
        assertEquals(SyncState.OK, statuses.last().state)
        assertEquals(1, server.count("POST /api/ar/records")) // 記録は、まとめて1回
        assertEquals(1, server.count("POST /api/ar/inventories/5/finish"))
        assertEquals(5, storage.lastFinishedInventoryId)
        // 予定・アンカーを受け取れている
        val p = plans.last()
        assertEquals("ノートPC", p.items.single().placed.name)
        assertEquals("A001", p.items.single().placed.assetNo)
        assertEquals(listOf("Aabc", "Adef"), p.anchors.map { it.token })
        assertEquals(90.0, p.anchors[0].facingDeg)
        assertNull(p.anchors[1].facingDeg)
        assertEquals(5, p.inventoryId)
        // 台帳（管理対象のタグ）も、受け取れている
        assertEquals(listOf(LedgerAsset("Tnote01", "A001", "ノートPC"), LedgerAsset("Tproj01", "A002", "プロジェクター")), p.ledger)
    }

    @Test
    fun サーバーに届かなければ_残して_あとで再送する() {
        storage.outbox = listOf(rec("r1"))
        server.stop()
        controller().runOnce()
        assertEquals(1, storage.outbox.size)
        assertEquals(SyncState.OFFLINE, statuses.last().state)
        assertEquals(1, statuses.last().pending)
        assertTrue(plans.isEmpty())
        // 復旧したあと（同じ保存先で、新しいサーバー）、送られる
        setUp()
        storage.outbox = listOf(rec("r1"))
        controller().runOnce()
        assertTrue(storage.outbox.isEmpty())
    }

    @Test
    fun 同じ記録を再送しても_サーバーは二重にしない() {
        storage.outbox = listOf(rec("r1"))
        controller().runOnce()
        storage.outbox = listOf(rec("r1")) // 通信が切れて、送れたか分からなかったので、もう一度
        controller().runOnce()
        assertEquals(1, server.receivedIds.size)
        assertTrue(storage.outbox.isEmpty())
    }

    @Test
    fun サーバーに断られた操作は_捨てて先へ進む() {
        server.refuseItemsWith = 400
        storage.outbox = listOf(PutItemOp("p", "bad", "x", 1, 0.0, 0.0, 0.0), rec("r1"))
        controller().runOnce()
        assertTrue(storage.outbox.isEmpty())
        assertEquals(1, statuses.last().dropped)
        assertEquals(1, server.receivedIds.size) // 後ろの記録は、送られた
    }

    @Test
    fun サーバーの不具合は_残して_あとで再送する() {
        server.refuseRecordsWith = 503
        storage.outbox = listOf(rec("r1"))
        controller().runOnce()
        assertEquals(1, storage.outbox.size)
        assertEquals(SyncState.ERROR, statuses.last().state)
        assertEquals(0, statuses.last().dropped)
    }

    @Test
    fun ログインできなければ_送らずに残す() {
        settings = settings.copy(password = "wrong")
        storage.outbox = listOf(rec("r1"))
        controller().runOnce()
        assertEquals(SyncState.AUTH_ERROR, statuses.last().state)
        assertEquals(1, storage.outbox.size)
        assertEquals(0, server.count("POST /api/ar/records"))
    }

    @Test
    fun 設定がなければ_何も送らない() {
        settings = Settings()
        storage.outbox = listOf(rec("r1"))
        controller().runOnce()
        assertEquals(SyncState.NOT_CONFIGURED, statuses.last().state)
        assertEquals(0, server.calls.size)
        assertEquals(1, storage.outbox.size)
    }

    @Test
    fun 開いている棚卸がなければ_終えるは何もせず消える() {
        server.inventoryId = null
        storage.outbox = listOf(FinishOp("f"))
        controller().runOnce()
        assertTrue(storage.outbox.isEmpty())
        assertEquals(0, server.calls.count { it.endsWith("/finish") })
        assertNull(storage.lastFinishedInventoryId)
    }

    @Test
    fun 取り消しを送ると_終えた棚卸のIDを忘れる() {
        storage.lastFinishedInventoryId = 5
        storage.outbox = listOf(UndoOp("u", 5))
        controller().runOnce()
        assertEquals(1, server.count("POST /api/ar/inventories/5/undo-finish"))
        assertNull(storage.lastFinishedInventoryId)
    }

    @Test
    fun 送信中に増えた操作も_送り切る() {
        storage.outbox = listOf(rec("r1"))
        val c = controller()
        c.runOnce()
        storage.updateOutbox { it + rec("r2") }
        c.runOnce()
        assertTrue(storage.outbox.isEmpty())
        assertEquals(setOf("r1", "r2"), server.receivedIds)
        assertFalse(statuses.isEmpty())
    }

    // ---- 端末の合言葉（QRで設定） ----

    @Test
    fun 合言葉があれば_ログインせずに送る() {
        settings = Settings(serverUrl = server.url, authToken = "DEVTOKEN1")
        storage.outbox = listOf(rec("r1"))
        controller().runOnce()
        assertEquals(SyncState.OK, statuses.last().state)
        assertTrue(storage.outbox.isEmpty())
        assertEquals(0, server.count("GET /login"))
        assertEquals(0, server.count("POST /login"))
        assertTrue(server.authorizations.all { it == "Bearer DEVTOKEN1" })
    }

    @Test
    fun 合言葉が無効なら_登録のやり直しを案内する() {
        settings = Settings(serverUrl = server.url, authToken = "WRONG")
        storage.outbox = listOf(rec("r1"))
        controller().runOnce()
        assertEquals(SyncState.AUTH_ERROR, statuses.last().state)
        assertTrue(statuses.last().message.contains("設定し直して"))
        assertEquals(1, storage.outbox.size)
    }

    @Test
    fun 合言葉があれば_IDとパスワードがなくても_設定済み() {
        settings = Settings(serverUrl = server.url, authToken = "DEVTOKEN1", loginId = "", password = "")
        controller().runOnce()
        assertEquals(SyncState.OK, statuses.last().state)
    }

    @Test
    fun 合言葉だけでURLがなければ_未設定() {
        settings = Settings(serverUrl = "", authToken = "DEVTOKEN1")
        controller().runOnce()
        assertEquals(SyncState.NOT_CONFIGURED, statuses.last().state)
    }

    @Test
    fun 設定コードを合言葉に引き換える() {
        assertEquals("DEVTOKEN1", ApiClient(server.url).enroll("validcode0123456789"))
    }

    @Test
    fun 無効な設定コードは_サーバーのメッセージ付きで断られる() {
        try {
            ApiClient(server.url).enroll("expiredcode000000000")
            org.junit.Assert.fail("例外が出るはず")
        } catch (e: AuthException) {
            assertEquals("設定用のQRが、無効です。", e.message)
        }
    }
}
