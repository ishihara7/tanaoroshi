package jp.co.ryomo.tanaoroshi.ar

import org.json.JSONObject

/**
 * サーバーへ送る、送信待ちの操作。端末に保存し、電波が戻ったら、順に送る。
 * どの操作にも一意の id がある（送信が済んだものを、id で取り除くため）。
 */
sealed interface Op {
    val id: String
}

/** 備品登録モード：備品の階と位置を、予定として登録する。 */
data class PutItemOp(
    override val id: String, val token: String, val name: String, val floor: Int, val x: Double, val y: Double, val errM: Double,
) : Op

data class DeleteItemOp(override val id: String, val token: String) : Op

/**
 * 棚卸で読んだ（または手入力した）記録。id は、そのままサーバーの client_id になる（再送しても、二重にならない）。
 * kind：read（読んだ）／unconfirm（未確認に戻した）。method：qr／manual。
 */
data class RecordOp(
    override val id: String, val kind: String, val token: String, val method: String,
    val floor: Int?, val x: Double?, val y: Double?, val moved: Boolean, val employeeNo: String, val readAtMs: Long,
) : Op

/** 棚卸を終える（サーバーで確定する）。 */
data class FinishOp(override val id: String) : Op

/** 終えた棚卸の取り消し。inventoryId：終えたときの、サーバーの棚卸ID。 */
data class UndoOp(override val id: String, val inventoryId: Int) : Op

object Outbox {
    /** 「棚卸を終える」の取り消し。まだ送っていない「終える」があれば、それを取り除くだけでよい（サーバーは、何も知らない）。 */
    fun undoFinish(queue: List<Op>, lastFinishedInventoryId: Int?, newId: String): List<Op> {
        val i = queue.indexOfLast { it is FinishOp }
        if (i >= 0) return queue.toMutableList().also { it.removeAt(i) }
        return if (lastFinishedInventoryId != null) queue + UndoOp(newId, lastFinishedInventoryId) else queue
    }

    /** 先頭から、同じ種類の記録を、まとめて取り出す（1回の通信で送る件数の上限つき）。記録でなければ、1件だけ。 */
    fun nextBatch(queue: List<Op>, maxRecords: Int = 200): List<Op> {
        val head = queue.firstOrNull() ?: return emptyList()
        if (head !is RecordOp) return listOf(head)
        return queue.takeWhile { it is RecordOp }.take(maxRecords)
    }

    fun remove(queue: List<Op>, ids: Set<String>): List<Op> = queue.filter { it.id !in ids }
}

// ---- 端末への保存（JSON） ----

fun Op.toJson(): JSONObject = when (this) {
    is PutItemOp -> JSONObject().put("t", "put").put("id", id).put("token", token).put("name", name).put("floor", floor)
        .put("x", x).put("y", y).put("errM", errM)
    is DeleteItemOp -> JSONObject().put("t", "del").put("id", id).put("token", token)
    is RecordOp -> JSONObject().put("t", "rec").put("id", id).put("kind", kind).put("token", token).put("method", method)
        .putOpt("floor", floor).putOpt("x", x).putOpt("y", y).put("moved", moved).put("emp", employeeNo).put("at", readAtMs)
    is FinishOp -> JSONObject().put("t", "fin").put("id", id)
    is UndoOp -> JSONObject().put("t", "undo").put("id", id).put("inv", inventoryId)
}

fun opFromJson(o: JSONObject): Op? {
    val id = o.optString("id")
    if (id.isEmpty()) return null
    fun dbl(k: String): Double? = if (o.has(k) && !o.isNull(k)) o.getDouble(k) else null
    return when (o.optString("t")) {
        "put" -> PutItemOp(id, o.getString("token"), o.optString("name"), o.getInt("floor"), o.getDouble("x"), o.getDouble("y"), o.optDouble("errM", 0.0))
        "del" -> DeleteItemOp(id, o.getString("token"))
        "rec" -> RecordOp(
            id, o.getString("kind"), o.getString("token"), o.optString("method", "qr"),
            if (o.has("floor") && !o.isNull("floor")) o.getInt("floor") else null, dbl("x"), dbl("y"),
            o.optBoolean("moved", false), o.optString("emp"), o.getLong("at"),
        )
        "fin" -> FinishOp(id)
        "undo" -> UndoOp(id, o.getInt("inv"))
        else -> null
    }
}
