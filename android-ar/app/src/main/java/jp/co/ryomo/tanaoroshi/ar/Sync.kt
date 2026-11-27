package jp.co.ryomo.tanaoroshi.ar

import java.io.IOException
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/** NOT_CONFIGURED：サーバーの設定がない／SYNCING：送信中／OK：送り終えた／OFFLINE：通信できない（あとで再送）／AUTH_ERROR：ログインできない／ERROR：サーバーの不具合など */
enum class SyncState { NOT_CONFIGURED, IDLE, SYNCING, OK, OFFLINE, AUTH_ERROR, ERROR }

data class SyncStatus(
    val state: SyncState = SyncState.IDLE,
    /** 送信待ちの件数 */
    val pending: Int = 0,
    val lastOkMs: Long? = null,
    val message: String = "",
    /** サーバーに断られて、送らずに捨てた操作の数（この起動中の合計） */
    val dropped: Int = 0,
)

/** 送信待ちの保存先（実機では Store。テストでは、メモリ上のもの）。 */
interface SyncStorage {
    fun loadOutbox(): List<Op>

    /** 送信待ちを、読んで、書き換えて、保存する（画面の操作と、裏の送信が、同時に触っても壊れないように、まとめて行う）。 */
    fun updateOutbox(change: (List<Op>) -> List<Op>): List<Op>

    /** 最後に、サーバーで終えた棚卸のID（「終える」の取り消しに使う）。 */
    var lastFinishedInventoryId: Int?
}

/**
 * 送信待ちを、順にサーバーへ送る（裏のスレッドで、1つずつ）。電波がなければ、残して、あとで再送する。
 * 送り終えたら、サーバーの予定を取り直して、onPlan に渡す（画面側で、反映する）。
 *
 * 操作は、端末に保存した順に送る。サーバーに断られた操作（4xx）は、再送しても直らないので、捨てて、件数に数える。
 * サーバーの不具合（5xx）と、通信の失敗は、残して、あとで再送する。
 */
class SyncController(
    private val store: SyncStorage,
    private val settings: () -> Settings,
    private val postUi: (() -> Unit) -> Unit,
    private val onPlan: (ServerPlan) -> Unit,
    private val onStatus: (SyncStatus) -> Unit,
    private val newItemErrM: () -> Double = { ErrorModel.ANCHOR_ERR_M },
    private val clientFactory: (Settings) -> ApiClient = { ApiClient(it.serverUrl, it.authToken.ifEmpty { null }) },
    private val now: () -> Long = System::currentTimeMillis,
) {
    private val executor = Executors.newSingleThreadExecutor { r -> Thread(r, "sync").apply { isDaemon = true } }
    private val running = AtomicBoolean(false)
    private val again = AtomicBoolean(false)

    @Volatile
    private var lastOkMs: Long? = null

    @Volatile
    private var dropped = 0

    /** 送信を始める（すでに動いていれば、終わったあとに、もう一度動く）。 */
    fun kick() {
        again.set(true)
        if (running.compareAndSet(false, true)) {
            executor.execute {
                try {
                    while (again.getAndSet(false)) runOnce()
                } finally {
                    running.set(false)
                    if (again.get()) kick()
                }
            }
        }
    }

    private fun publish(state: SyncState, message: String = "") {
        val s = SyncStatus(state, store.loadOutbox().size, lastOkMs, message, dropped)
        postUi { onStatus(s) }
    }

    /** 1回の送信。テストから呼べるように公開している。 */
    fun runOnce() {
        val s = settings()
        val hasToken = s.authToken.isNotEmpty()
        if (s.serverUrl.isBlank() || (!hasToken && (s.loginId.isBlank() || s.password.isEmpty()))) {
            return publish(SyncState.NOT_CONFIGURED, "設定の「QRで設定する」で、管理画面のQRを読み取ってください。")
        }
        publish(SyncState.SYNCING)
        try {
            val client = clientFactory(s)
            if (!hasToken) client.login(s.loginId, s.password) // 端末の合言葉があれば、ログインは要らない
            client.getPlan() // CSRFトークンを受け取る
            while (true) {
                val batch = Outbox.nextBatch(store.loadOutbox())
                if (batch.isEmpty()) break
                send(client, batch)
                store.updateOutbox { Outbox.remove(it, batch.map { op -> op.id }.toSet()) }
                publish(SyncState.SYNCING)
            }
            val plan = client.getPlan()
            lastOkMs = now()
            postUi { onPlan(plan) }
            publish(SyncState.OK)
        } catch (e: AuthException) {
            publish(SyncState.AUTH_ERROR, e.message ?: "ログインできません。")
        } catch (e: ApiException) {
            publish(SyncState.ERROR, e.message ?: "サーバーの不具合です。")
        } catch (e: IOException) {
            publish(SyncState.OFFLINE, "通信できません。電波が戻ったら、送ります。")
        } catch (e: Exception) {
            publish(SyncState.ERROR, "送信できません：${e.javaClass.simpleName}")
        }
    }

    /** 1件（記録なら、まとめて）を送る。サーバーに断られた（4xx）ときは、捨てて、先へ進む。 */
    private fun send(client: ApiClient, batch: List<Op>) {
        when (val op = batch.first()) {
            is PutItemOp -> discardIfRefused { client.putItem(op) }
            is DeleteItemOp -> discardIfRefused { client.deleteItem(op) }
            is RecordOp -> {
                val results = client.postRecords(batch.filterIsInstance<RecordOp>())
                dropped += results.count { it.status == "error" }
            }
            is FinishOp -> {
                // 開いている棚卸（読んだ記録が1件でもあれば、ある）。なければ、終えるものがない
                val inv = client.getPlan().inventoryId
                if (inv != null) {
                    discardIfRefused {
                        client.finish(inv, newItemErrM())
                        store.lastFinishedInventoryId = inv
                    }
                }
            }
            is UndoOp -> discardIfRefused {
                client.undoFinish(op.inventoryId)
                if (store.lastFinishedInventoryId == op.inventoryId) store.lastFinishedInventoryId = null
            }
        }
    }

    private fun discardIfRefused(block: () -> Unit) {
        try {
            block()
        } catch (e: ApiException) {
            if (e.code >= 500) throw e
            dropped++
        }
    }
}
