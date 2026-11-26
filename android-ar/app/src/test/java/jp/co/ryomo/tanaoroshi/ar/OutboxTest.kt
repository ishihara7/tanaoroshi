package jp.co.ryomo.tanaoroshi.ar

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class OutboxTest {
    private fun rec(id: String, token: String = "a") = RecordOp(id, "read", token, "qr", 1, 1.0, 2.0, false, "E1", 1000L)

    // ---- 「棚卸を終える」の取り消し ----

    @Test
    fun 送っていない終えるは_取り除くだけ() {
        val q = listOf(rec("r1"), FinishOp("f1"))
        assertEquals(listOf<Op>(rec("r1")), Outbox.undoFinish(q, lastFinishedInventoryId = 7, newId = "u1"))
    }

    @Test
    fun 送ったあとなら_取り消しを送る() {
        val q = listOf<Op>(rec("r1"))
        assertEquals(listOf(rec("r1"), UndoOp("u1", 7)), Outbox.undoFinish(q, 7, "u1"))
    }

    @Test
    fun 棚卸のIDが分からなければ_取り消しは送らない() {
        assertTrue(Outbox.undoFinish(emptyList(), null, "u1").isEmpty())
    }

    @Test
    fun 終えるが複数あれば_最後の1つを取り除く() {
        val q = listOf(FinishOp("f1"), rec("r1"), FinishOp("f2"))
        assertEquals(listOf(FinishOp("f1"), rec("r1")), Outbox.undoFinish(q, 7, "u1"))
    }

    // ---- 送る単位 ----

    @Test
    fun 連続する記録は_まとめて送る() {
        val q = listOf(rec("1"), rec("2"), rec("3"), FinishOp("f"), rec("4"))
        assertEquals(listOf("1", "2", "3"), Outbox.nextBatch(q).map { it.id })
    }

    @Test
    fun 記録は_上限の件数で区切る() {
        val q = (1..5).map { rec("r$it") }
        assertEquals(2, Outbox.nextBatch(q, maxRecords = 2).size)
    }

    @Test
    fun 記録以外は_1件ずつ送る() {
        val q = listOf(PutItemOp("p", "a", "A", 1, 0.0, 0.0, 0.5), rec("r1"))
        assertEquals(listOf("p"), Outbox.nextBatch(q).map { it.id })
    }

    @Test
    fun 空なら空() {
        assertTrue(Outbox.nextBatch(emptyList()).isEmpty())
    }

    @Test
    fun 送った分だけ取り除く() {
        val q = listOf(rec("1"), rec("2"), rec("3"))
        assertEquals(listOf("3"), Outbox.remove(q, setOf("1", "2")).map { it.id })
    }

    // ---- 端末への保存（JSON） ----

    @Test
    fun すべての操作が_JSONで往復できる() {
        val ops = listOf<Op>(
            PutItemOp("p", "Tnote01", "ノートPC", 2, 3.5, -4.0, 0.8),
            DeleteItemOp("d", "Tnote01"),
            rec("r1"),
            RecordOp("r2", "unconfirm", "b", "manual", null, null, null, true, "", 2000L),
            FinishOp("f"),
            UndoOp("u", 9),
        )
        assertEquals(ops, ops.map { opFromJson(it.toJson())!! })
    }

    @Test
    fun 読めない操作は_無視する() {
        assertNull(opFromJson(org.json.JSONObject("""{"t":"unknown","id":"x"}""")))
        assertNull(opFromJson(org.json.JSONObject("""{"t":"fin"}""")))
    }
}
