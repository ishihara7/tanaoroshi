package jp.co.ryomo.tanaoroshi.ar

import kotlin.math.hypot

/** 棚卸の状態（予定・確認済み・場所違い・想定外）。Android に依存しない、純粋なデータ。 */
data class InventoryState(
    val items: List<PlacedItem>,
    val confirmed: Set<String>,
    val moved: Map<String, MovedAt>,
    val unexpected: Map<String, Unexpected>,
)

/** 場所違いの判定の結果。gapM は、同じ階で位置が取れたときの、登録位置との差（m）。 */
data class MovedJudgement(val isMoved: Boolean, val otherFloor: Boolean, val gapM: Double?)

/** 「棚卸を終える」の結果の件数。 */
data class FinishSummary(val checked: Int, val checkedMoved: Int, val missed: Int, val unexpected: Int)

object Inventory {
    /**
     * 場所違いの判定。
     * ・階が分かっていて、登録の階と違えば、無条件で場所違い（階はアンカーで確定している情報）
     * ・同じ階で位置が取れていて、登録位置から thresholdM 以上離れていれば、場所違い
     * ・階が分からない、または位置が取れないときは、判定できないので、場所違いにしない
     */
    fun judgeMoved(
        placed: Placed, curFloor: Int?, posX: Double?, posY: Double?, thresholdM: Double = MOVED_THRESHOLD_M,
    ): MovedJudgement {
        val otherFloor = curFloor != null && placed.floor != curFloor
        val gap = if (posX != null && posY != null && !otherFloor && placed.located) hypot(posX - placed.x, posY - placed.y) else null
        return MovedJudgement(otherFloor || (gap != null && gap >= thresholdM), otherFloor, gap)
    }

    /** 確かめた備品を、未確認に戻す（場所違いの記録も消す）。 */
    fun unconfirm(s: InventoryState, token: String): InventoryState =
        s.copy(confirmed = s.confirmed - token, moved = s.moved - token)

    /**
     * 棚卸を終える。今回の結果が、次回の予定になる。
     * ・確かめた備品：前回の印を消す。場所違いで位置が取れていれば、読んだ階・位置に更新する
     * ・確かめなかった備品：場所はそのままで、「前回未確認」の印を付ける
     * ・予定にないのに読んだ備品：新しい予定に加える（位置が取れていなければ、階だけ）
     * 終えたあとの状態は、確認済み・場所違い・想定外が、空になる。
     * @param newItemErrM 位置が取れた想定外の備品に付ける、位置の誤差の見積もり（m）
     */
    fun finish(s: InventoryState, newItemErrM: Double): Pair<InventoryState, FinishSummary> {
        val extra = s.unexpected.values.filter { u -> s.items.none { it.token == u.token } }
        val next = s.items.map { item ->
            val p = item.placed
            if (item.token in s.confirmed) {
                val m = s.moved[item.token]
                val at = if (m != null && m.x != null && m.y != null) p.copy(x = m.x, y = m.y, z = m.z, floor = m.floor, located = true) else p
                item.copy(placed = at.copy(missedLast = false, wasUnexpected = false))
            } else {
                item.copy(placed = p.copy(missedLast = true))
            }
        } + extra.map {
            val located = it.x != null && it.y != null
            PlacedItem(
                it.token,
                Placed(it.name, it.x ?: 0.0, it.y ?: 0.0, if (located) newItemErrM else 0.0, it.floor, located, wasUnexpected = true, z = it.z),
            )
        }
        val summary = FinishSummary(
            checked = s.items.count { it.token in s.confirmed },
            checkedMoved = s.items.count { it.token in s.confirmed && it.token in s.moved },
            missed = s.items.count { it.token !in s.confirmed },
            unexpected = extra.size,
        )
        return InventoryState(next, emptySet(), emptyMap(), emptyMap()) to summary
    }
}
