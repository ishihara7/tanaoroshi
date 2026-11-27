package jp.co.ryomo.tanaoroshi.ar

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RouteTest {
    private fun p(t: String, x: Double, y: Double) = RoutePoint(t, x, y)

    @Test
    fun 空なら空() {
        assertTrue(RoutePlanner.plan(0.0, 0.0, emptyList()).isEmpty())
    }

    @Test
    fun 一直線なら近い順() {
        val order = RoutePlanner.plan(0.0, 0.0, listOf(p("c", 30.0, 0.0), p("a", 10.0, 0.0), p("b", 20.0, 0.0)))
        assertEquals(listOf("a", "b", "c"), order.map { it.token })
    }

    @Test
    fun すべての点を1回ずつ通る() {
        val pts = (0 until 12).map { p("t$it", (it * 7 % 11).toDouble(), (it * 5 % 13).toDouble()) }
        val order = RoutePlanner.plan(0.0, 0.0, pts)
        assertEquals(pts.map { it.token }.toSet(), order.map { it.token }.toSet())
        assertEquals(pts.size, order.size)
    }

    @Test
    fun 最近傍法より長くならない() {
        // 最近傍法だと遠回りになる並び（2-optで縮む）
        val pts = listOf(p("a", 1.0, 0.0), p("b", 2.5, 3.0), p("c", 4.0, 0.2), p("d", 5.5, 3.1), p("e", 7.0, 0.0))
        val greedy = RoutePlanner.length(0.0, 0.0, pts.sortedBy { it.x }) // 比較の目安
        val planned = RoutePlanner.length(0.0, 0.0, RoutePlanner.plan(0.0, 0.0, pts))
        assertTrue(planned <= greedy + 1e-9)
    }
}
