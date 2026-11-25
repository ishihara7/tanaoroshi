package jp.co.ryomo.tanaoroshi.ar

import kotlin.math.hypot

/** 巡る点（備品）。x：東、y：北（m）。 */
data class RoutePoint(val token: String, val x: Double, val y: Double)

/**
 * 棚卸しの順路。いまの位置から、全部の点を1回ずつ通る、短い道順を作る（最後に戻らない）。
 * 最近傍法で、まず順番を作り、2-opt（途中の区間をひっくり返すと短くなるなら、そうする）で縮める。
 * 備品は、せいぜい数十件なので、これで十分に短くなる。
 */
object RoutePlanner {

    fun plan(startX: Double, startY: Double, points: List<RoutePoint>): List<RoutePoint> {
        if (points.size <= 2) return nearestFirst(startX, startY, points)
        var order = nearestFirst(startX, startY, points)
        var best = length(startX, startY, order)
        var improved = true
        while (improved) {
            improved = false
            for (i in 0 until order.size - 1) {
                for (j in i + 1 until order.size) {
                    val cand = order.subList(0, i) + order.subList(i, j + 1).reversed() + order.subList(j + 1, order.size)
                    val len = length(startX, startY, cand)
                    if (len < best - 1e-9) {
                        order = cand
                        best = len
                        improved = true
                    }
                }
            }
        }
        return order
    }

    /** いまの位置から、順路を歩いたときの、合計の距離（m）。 */
    fun length(startX: Double, startY: Double, order: List<RoutePoint>): Double {
        var x = startX
        var y = startY
        var sum = 0.0
        for (p in order) {
            sum += hypot(p.x - x, p.y - y)
            x = p.x
            y = p.y
        }
        return sum
    }

    private fun nearestFirst(startX: Double, startY: Double, points: List<RoutePoint>): List<RoutePoint> {
        val left = points.toMutableList()
        val out = ArrayList<RoutePoint>(points.size)
        var x = startX
        var y = startY
        while (left.isNotEmpty()) {
            val next = left.minBy { hypot(it.x - x, it.y - y) }
            left.remove(next)
            out.add(next)
            x = next.x
            y = next.y
        }
        return out
    }
}
