package jp.co.ryomo.tanaoroshi.ar

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class InventoryTest {
    private fun placed(x: Double = 0.0, y: Double = 0.0, floor: Int = 1) = Placed("備品", x, y, 0.5, floor)

    private fun state(
        items: List<PlacedItem>,
        confirmed: Set<String> = emptySet(),
        moved: Map<String, MovedAt> = emptyMap(),
        unexpected: Map<String, Unexpected> = emptyMap(),
    ) = InventoryState(items, confirmed, moved, unexpected)

    private fun item(token: String, p: Placed = placed()) = PlacedItem(token, p)

    // ---- 場所違いの判定 ----

    @Test
    fun 同じ階でしきい値より近ければ場所違いではない() {
        val j = Inventory.judgeMoved(placed(10.0, 10.0), 1, 11.0, 10.0)
        assertFalse(j.isMoved)
        assertEquals(1.0, j.gapM!!, 1e-9)
    }

    @Test
    fun 同じ階でしきい値ちょうどなら場所違い() {
        assertTrue(Inventory.judgeMoved(placed(0.0, 0.0), 1, 3.0, 0.0).isMoved)
    }

    @Test
    fun しきい値は変えられる() {
        assertTrue(Inventory.judgeMoved(placed(0.0, 0.0), 1, 2.0, 0.0, thresholdM = 1.5).isMoved)
        assertFalse(Inventory.judgeMoved(placed(0.0, 0.0), 1, 2.0, 0.0, thresholdM = 5.0).isMoved)
    }

    @Test
    fun 階が違えば位置に関係なく場所違い() {
        val j = Inventory.judgeMoved(placed(0.0, 0.0, floor = 2), 1, 0.0, 0.0)
        assertTrue(j.isMoved)
        assertTrue(j.otherFloor)
        assertNull(j.gapM)
    }

    @Test
    fun 階が違えば位置が取れなくても場所違い() {
        assertTrue(Inventory.judgeMoved(placed(floor = 3), 1, null, null).isMoved)
    }

    @Test
    fun 階が分からなければ判定しない() {
        assertFalse(Inventory.judgeMoved(placed(floor = 2), null, 0.0, 0.0).isMoved)
    }

    @Test
    fun 位置が取れなければ同じ階は判定しない() {
        assertFalse(Inventory.judgeMoved(placed(), 1, null, null).isMoved)
    }

    @Test
    fun 登録に位置がない備品は距離で判定しない() {
        val p = placed().copy(located = false)
        assertFalse(Inventory.judgeMoved(p, 1, 50.0, 50.0).isMoved)
    }

    // ---- 未確認に戻す ----

    @Test
    fun 未確認に戻すと場所違いの記録も消える() {
        val s = state(
            listOf(item("a"), item("b")),
            confirmed = setOf("a", "b"),
            moved = mapOf("a" to MovedAt("a", 1, 9.0, 9.0)),
        )
        val r = Inventory.unconfirm(s, "a")
        assertEquals(setOf("b"), r.confirmed)
        assertTrue(r.moved.isEmpty())
    }

    // ---- 棚卸を終える ----

    @Test
    fun 確かめた備品は前回の印が消え_位置はそのまま() {
        val p = placed(5.0, 6.0).copy(missedLast = true, wasUnexpected = true)
        val (r, _) = Inventory.finish(state(listOf(item("a", p)), confirmed = setOf("a")), 0.5)
        val a = r.items.single().placed
        assertFalse(a.missedLast)
        assertFalse(a.wasUnexpected)
        assertEquals(5.0, a.x, 0.0)
        assertEquals(6.0, a.y, 0.0)
    }

    @Test
    fun 確かめなかった備品は位置はそのままで前回未確認になる() {
        val (r, sum) = Inventory.finish(state(listOf(item("a", placed(5.0, 6.0)))), 0.5)
        val a = r.items.single().placed
        assertTrue(a.missedLast)
        assertEquals(5.0, a.x, 0.0)
        assertEquals(1, sum.missed)
    }

    @Test
    fun 場所違いの備品は読んだ階と位置に更新される() {
        val s = state(
            listOf(item("a", placed(0.0, 0.0, 1))),
            confirmed = setOf("a"),
            moved = mapOf("a" to MovedAt("a", 2, 7.0, 8.0)),
        )
        val (r, sum) = Inventory.finish(s, 0.5)
        val a = r.items.single().placed
        assertEquals(2, a.floor)
        assertEquals(7.0, a.x, 0.0)
        assertEquals(8.0, a.y, 0.0)
        assertEquals(1, sum.checkedMoved)
    }

    @Test
    fun 場所違いでも位置が取れていなければ場所は更新しない() {
        val s = state(
            listOf(item("a", placed(1.0, 2.0, 1))),
            confirmed = setOf("a"),
            moved = mapOf("a" to MovedAt("a", 2, null, null)),
        )
        val a = Inventory.finish(s, 0.5).first.items.single().placed
        assertEquals(1, a.floor)
        assertEquals(1.0, a.x, 0.0)
    }

    @Test
    fun 想定外は新しい予定に加わる() {
        val s = state(listOf(item("a")), unexpected = mapOf("z" to Unexpected("z", "新しい備品", 2, 3.0, 4.0)))
        val (r, sum) = Inventory.finish(s, 0.7)
        val z = r.items.first { it.token == "z" }.placed
        assertTrue(z.located)
        assertTrue(z.wasUnexpected)
        assertEquals(2, z.floor)
        assertEquals(0.7, z.errM, 0.0)
        assertEquals(1, sum.unexpected)
    }

    @Test
    fun 位置が取れなかった想定外は階だけで加わる() {
        val s = state(emptyList(), unexpected = mapOf("z" to Unexpected("z", "新しい備品", 2, null, null)))
        val z = Inventory.finish(s, 0.7).first.items.single().placed
        assertFalse(z.located)
        assertEquals(2, z.floor)
    }

    @Test
    fun すでに予定にある想定外は重複して加えない() {
        val s = state(listOf(item("z")), unexpected = mapOf("z" to Unexpected("z", "x", 1, 0.0, 0.0)))
        assertEquals(1, Inventory.finish(s, 0.5).first.items.size)
    }

    @Test
    fun 終えると確認済み_場所違い_想定外は空になる() {
        val s = state(
            listOf(item("a")),
            confirmed = setOf("a"),
            moved = mapOf("a" to MovedAt("a", 1, 9.0, 9.0)),
            unexpected = mapOf("z" to Unexpected("z", "x", 1, null, null)),
        )
        val r = Inventory.finish(s, 0.5).first
        assertTrue(r.confirmed.isEmpty())
        assertTrue(r.moved.isEmpty())
        assertTrue(r.unexpected.isEmpty())
    }

    @Test
    fun 件数の集計() {
        val s = state(
            listOf(item("a"), item("b"), item("c")),
            confirmed = setOf("a", "b"),
            moved = mapOf("b" to MovedAt("b", 1, 9.0, 9.0)),
            unexpected = mapOf("z" to Unexpected("z", "x", 1, null, null)),
        )
        val sum = Inventory.finish(s, 0.5).second
        assertEquals(FinishSummary(checked = 2, checkedMoved = 1, missed = 1, unexpected = 1), sum)
    }

    @Test
    fun 終えても元の状態は変わらない_取り消しに使える() {
        // 取り消しは、終える前の状態をそのまま保持して戻す
        val before = state(listOf(item("a")), confirmed = setOf("a"))
        val (after, _) = Inventory.finish(before, 0.5)
        assertNotNull(after)
        assertEquals(setOf("a"), before.confirmed)
        assertEquals(1, before.items.size)
        assertFalse(before.items.single().placed.missedLast)
    }

    @Test
    fun 場所違いで確かめた備品は_読んだ高さに更新し_そうでなければ予定の高さのまま() {
        val a = Placed("A", 1.0, 1.0, 0.5, 1, z = 0.4)
        val b = Placed("B", 2.0, 2.0, 0.5, 1, z = 1.2)
        val s = state(
            listOf(item("a", a), item("b", b)), confirmed = setOf("a", "b"),
            moved = mapOf("a" to MovedAt("a", 2, 5.0, 6.0, 1.5)),
        )
        val (r, _) = Inventory.finish(s, 0.5)
        assertEquals(1.5, r.items.first { it.token == "a" }.placed.z!!, 1e-9)
        assertEquals(1.2, r.items.first { it.token == "b" }.placed.z!!, 1e-9)
    }

    @Test
    fun 想定外の備品は_読んだ高さを持つ() {
        val s = state(emptyList(), unexpected = mapOf("u" to Unexpected("u", "未登録", 1, 3.0, 4.0, 0.9)))
        val (r, _) = Inventory.finish(s, 0.5)
        assertEquals(0.9, r.items.single().placed.z!!, 1e-9)
    }
}
