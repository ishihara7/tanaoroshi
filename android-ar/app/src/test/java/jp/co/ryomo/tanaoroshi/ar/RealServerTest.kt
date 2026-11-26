package jp.co.ryomo.tanaoroshi.ar

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test

private class MemStore : SyncStorage {
    var outbox: List<Op> = emptyList()
    override fun loadOutbox() = outbox
    override fun updateOutbox(change: (List<Op>) -> List<Op>): List<Op> = change(outbox).also { outbox = it }
    override var lastFinishedInventoryId: Int? = null
}

/**
 * 本物のサーバー（FastAPI）につないで、通信の流れを確かめる。普段は飛ばす。
 * 実行するとき：サーバーを起動し、環境変数 TANAOROSHI_E2E_URL・TANAOROSHI_E2E_USER・TANAOROSHI_E2E_PASSWORD を設定する。
 * 注意：サーバーの ar_items・inventories に、データが入る（テスト用のDBで実行すること）。
 */
class RealServerTest {
    private val url = System.getenv("TANAOROSHI_E2E_URL")
    private val user = System.getenv("TANAOROSHI_E2E_USER")
    private val pw = System.getenv("TANAOROSHI_E2E_PASSWORD")

    @Test
    fun 登録_読む_終える_取り消しまでが_本物のサーバーで通る() {
        assumeTrue(url != null && user != null && pw != null)
        val store = MemStore()
        val statuses = mutableListOf<SyncStatus>()
        var plan: ServerPlan? = null
        val settings = Settings(serverUrl = url!!, loginId = user!!, password = pw!!, employeeNo = "E1001")
        val c = SyncController(store, { settings }, { it() }, { plan = it }, { statuses += it })

        fun run(vararg ops: Op) {
            store.outbox = store.outbox + ops
            c.runOnce()
            assertEquals(statuses.last().message, SyncState.OK, statuses.last().state)
            assertTrue(store.outbox.isEmpty())
        }

        // 登録（備品登録モード）
        run(PutItemOp("p1", "E2eTagA", "テスト備品A", 1, 1.0, 1.0, 0.5), PutItemOp("p2", "E2eTagB", "テスト備品B", 1, 2.0, 2.0, 0.5))
        assertEquals(setOf("E2eTagA", "E2eTagB"), plan!!.items.map { it.token }.toSet())
        // 棚卸：Aを読む・Bを読んで取り消す・予定にないCを読む
        fun read(id: String, token: String, kind: String = "read") =
            RecordOp(id, kind, token, "qr", 1, 1.0, 1.0, false, "E1001", System.currentTimeMillis())
        run(read("e2e0000000000001", "E2eTagA"), read("e2e0000000000002", "E2eTagB"), read("e2e0000000000003", "E2eTagB", "unconfirm"), read("e2e0000000000004", "E2eTagC"))
        assertTrue(plan!!.inventoryId != null)
        // 終える：Bは前回未確認、Cは予定に加わる
        run(FinishOp("f1"))
        val after = plan!!.items.associateBy { it.token }
        assertTrue(after.getValue("E2eTagB").placed.missedLast)
        assertTrue(!after.getValue("E2eTagA").placed.missedLast)
        assertTrue(after.getValue("E2eTagC").placed.wasUnexpected)
        assertEquals(null, plan!!.inventoryId)
        // 取り消し：Cが予定から消え、開いた棚卸が戻る
        val finished = store.lastFinishedInventoryId!!
        run(UndoOp("u1", finished))
        assertEquals(setOf("E2eTagA", "E2eTagB"), plan!!.items.map { it.token }.toSet())
        assertEquals(finished, plan!!.inventoryId)
        // 後片づけ：登録した備品を消す
        run(DeleteItemOp("d1", "E2eTagA"), DeleteItemOp("d2", "E2eTagB"))
    }
}
