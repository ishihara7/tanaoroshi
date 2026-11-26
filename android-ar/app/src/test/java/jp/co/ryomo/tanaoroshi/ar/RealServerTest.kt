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
    fun 台帳にないタグは登録できず_棚卸で想定外になる_本物のサーバーで() {
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

        // 台帳にないタグは、登録を断られる（捨てられて、件数に数えられる）
        run(PutItemOp("p1", "E2eNotInLedger", "管理対象外", 1, 1.0, 1.0, 0.5))
        assertEquals(1, statuses.last().dropped)
        assertTrue(plan!!.items.none { it.token == "E2eNotInLedger" })
        assertTrue(plan!!.ledger.none { it.token == "E2eNotInLedger" })
        // 棚卸で読むと、想定外になり、終えると、「前回 想定外」の備品として予定に加わる
        run(RecordOp("e2e0000000000001", "read", "E2eNotInLedger", "qr", 1, 1.0, 1.0, false, "E1001", System.currentTimeMillis()))
        run(FinishOp("f1"))
        val added = plan!!.items.single { it.token == "E2eNotInLedger" }.placed
        assertTrue(added.wasUnexpected)
        assertEquals(null, added.assetNo)
        // 取り消すと、予定から消える
        run(UndoOp("u1", store.lastFinishedInventoryId!!))
        assertTrue(plan!!.items.none { it.token == "E2eNotInLedger" })
    }
}
