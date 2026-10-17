package com.obliphur.oit.core

import com.obliphur.oit.sync.MainRunner
import com.obliphur.oit.sync.PairRequest
import com.obliphur.oit.sync.SealError
import com.obliphur.oit.sync.SyncCrypto
import com.obliphur.oit.sync.SyncLocal
import com.obliphur.oit.sync.SyncService
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.math.BigInteger
import java.nio.file.Files
import java.util.concurrent.Executors

class SyncTest {
    @Test
    fun cryptoMatchesDesktop() {
        // 和 devsync.py 自检里的固定输入 / 输出一样: 两端算法逐字节一致
        val k = ByteArray(32) { it.toByte() }
        val env = SyncCrypto.seal(k, "dev", JSONObject().put("a", 1), ByteArray(16), 1700000000000)
        assertEquals("pHEJdtrTcg==", env.getString("ct"))
        assertEquals("a9ee146998cf5a913f1e5d4756f3b151789ed6e8e0b04b367bf1712d19ff8b24", env.getString("mac"))
        assertEquals("338005", SyncCrypto.pairCode(k))
        assertEquals("0d2c6ab660f97893d7b57f47872f0ac4b773568d34c7596a216691d2ed4dcc93",
            SyncCrypto.hex(SyncCrypto.shared(BigInteger.valueOf(5), "80")))
        val (xa, pa) = SyncCrypto.keypair()
        val (xb, pb) = SyncCrypto.keypair()
        val ka = SyncCrypto.shared(xa, pb.toString(16))
        assertTrue(ka.contentEquals(SyncCrypto.shared(xb, pa.toString(16))))
        val e2 = SyncCrypto.seal(ka, "a", JSONObject().put("x", "你好"))
        assertEquals("你好", SyncCrypto.unseal(ka, e2).getString("x"))
        try { SyncCrypto.unseal(ka, e2); fail("replay") } catch (_: SealError) {}
        try { SyncCrypto.unseal(ka, JSONObject(e2.toString()).put("mac", "00")); fail("mac") } catch (_: SealError) {}
    }

    private class Fake(val name: String) : SyncLocal {
        var mode = "proxy"
        val docs = linkedMapOf<String, MutableMap<String, Any?>>(
            "settings" to linkedMapOf("DAILY_LIMIT" to JSONObject().put("value", 7200.0).put("pending", JSONObject.NULL)),
            "hours" to linkedMapOf(), "rules" to linkedMapOf("black_domains" to JSONArray()), "timer" to linkedMapOf())
        var used = 0.0
        var cleared = 0
        val requests = mutableListOf<PairRequest>()
        override fun netMode() = mode
        override fun autoText() = "Sleeping"
        override fun ledger(): JSONObject = JSONObject().put("net", JSONObject().put("date", "2026-01-01").put("used", used))
        @Synchronized override fun docs(): Map<String, Map<String, Any?>> = docs.mapValues { LinkedHashMap(it.value) }
        @Synchronized override fun apply(doc: String, changes: Map<String, Any?>) {
            for ((k, v) in changes) if (v == null) docs[doc]!!.remove(k) else docs[doc]!![k] = v
        }
        override fun clearHistory() { cleared++ }
        override fun status(): JSONObject = JSONObject().put("timer", "idle").put("net", "offline")
        override fun pairRequest(req: PairRequest) { synchronized(requests) { requests.add(req) } }
        override fun changed() {}
    }

    private fun waitFor(ms: Long = 10_000, cond: () -> Boolean) {
        val end = System.currentTimeMillis() + ms
        while (System.currentTimeMillis() < end) { if (cond()) return; Thread.sleep(50) }
        fail("timeout")
    }

    /** 和桌面版 devsync.py 互通 (需要先在本机跑起 interop_peer.py, 并设置 OIT_INTEROP=1). */
    @Test
    fun interopWithDesktop() {
        if (System.getenv("OIT_INTEROP") != "1") return
        val main = Executors.newSingleThreadExecutor()
        var mainThread: Thread? = null
        main.submit { mainThread = Thread.currentThread() }.get()
        val runner = MainRunner({ main.execute(it) }, { Thread.currentThread() === mainThread })
        val l = Fake("Android")
        l.docs["hours"]!!["2026-01-01/7"] = "旧数据"
        val s = SyncService(Files.createTempDirectory("i").toFile(), l, runner, defaultName = "Android", httpPort0 = 18080, udpPort = 18081)
        try {
            s.start()
            assertEquals("windows", s.hello("127.0.0.1", 18070).getString("platform"))
            s.startPairing("127.0.0.1", 18070, motherIsMe = false)       // PC 是母端
            waitFor(20_000) { s.outgoing?.state == "accepted" && l.cleared == 1 }
            // 用 PC 的内容初始化
            assertEquals(5400.0, (l.docs["settings"]!!["DAILY_LIMIT"] as JSONObject).getDouble("value"), 0.0)
            assertEquals(mapOf("2026-01-01/8" to "来自PC"), l.docs["hours"]!!.toMap())
            assertEquals(900.0, SyncService.peerNet(s.peerLedgers(), "2026-01-01")[0], 0.0)
            // 再从 Android 改一项, 同步给 PC
            Thread.sleep(5)
            runner.call { l.apply("hours", mapOf("2026-01-01/9" to "来自安卓")) }
            l.used = 300.0
            assertTrue(s.syncWith(s.peers().keys.first()))
        } finally {
            s.stop(); main.shutdownNow()
        }
    }

    @Test
    fun pairAndSync() {
        // 两个实例共用一个"界面线程"
        val main = Executors.newSingleThreadExecutor()
        var mainThread: Thread? = null
        main.submit { mainThread = Thread.currentThread() }.get()
        val runner = MainRunner({ main.execute(it) }, { Thread.currentThread() === mainThread })
        val la = Fake("A")
        val lb = Fake("B")
        la.docs["settings"]!!["DAILY_LIMIT"] = JSONObject().put("value", 3600.0).put("pending", JSONObject.NULL)
        la.docs["hours"]!!["2026-01-01/9"] = "学习"
        lb.docs["hours"]!!["2026-01-01/10"] = "游戏"
        val sa = SyncService(Files.createTempDirectory("a").toFile(), la, runner, defaultName = "A", httpPort0 = 18050, udpPort = 18051)
        val sb = SyncService(Files.createTempDirectory("b").toFile(), lb, runner, defaultName = "B", httpPort0 = 18060, udpPort = 18061)
        try {
            sa.start(); sb.start()
            assertEquals(sb.myId, sa.hello("127.0.0.1", sb.port).getString("id"))
            // B 是子端 (A 为母端)
            sa.startPairing("127.0.0.1", sb.port, true)
            waitFor { synchronized(lb.requests) { lb.requests.isNotEmpty() } && sa.outgoing?.state == "waiting" }
            val req = lb.requests.last()
            assertEquals(sa.outgoing!!.code, req.code)
            runner.call { sb.answerPairing(req.token, true) }
            waitFor { sa.outgoing?.state == "accepted" && lb.cleared == 1 && sb.peers()[sa.myId]?.optBoolean("init") == false }
            assertEquals(0, la.cleared)
            assertEquals(3600.0, (lb.docs["settings"]!!["DAILY_LIMIT"] as JSONObject).getDouble("value"), 0.0)
            assertEquals(mapOf("2026-01-01/9" to "学习"), lb.docs["hours"]!!.toMap())
            assertFalse("子端的旧数据不能传给母端", la.docs["hours"]!!.containsKey("2026-01-01/10"))
            // 之后: 新的修改覆盖旧的, 账互相转交; 自动记录让位给自己填写的
            Thread.sleep(5)
            runner.call { lb.apply("hours", mapOf("2026-01-01/11" to "吃饭")) }
            lb.used = 600.0
            runner.call { la.apply("rules", mapOf("black_domains" to JSONArray().put("bilibili.com"))) }
            assertTrue(sb.syncWith(sa.myId))
            assertEquals("吃饭", la.docs["hours"]!!["2026-01-01/11"])
            assertEquals("bilibili.com", (lb.docs["rules"]!!["black_domains"] as JSONArray).getString(0))
            assertEquals(600.0, SyncService.peerNet(sa.peerLedgers(), "2026-01-01")[0], 0.0)
            runner.call { la.apply("hours", mapOf("2026-01-01/12" to "写作业")); lb.apply("hours", mapOf("2026-01-01/12" to "Sleeping")) }
            assertTrue(sa.syncWith(sb.myId))
            assertEquals("写作业", lb.docs["hours"]!!["2026-01-01/12"])
            runner.call { la.apply("hours", mapOf("2026-01-01/9" to null)) }
            assertTrue(sa.syncWith(sb.myId))
            assertFalse(lb.docs["hours"]!!.containsKey("2026-01-01/9"))
            // 解除绑定: 对方也解除
            runner.call { sa.unpair(sb.myId) }
            waitFor { sb.peers().isEmpty() }
        } finally {
            sa.stop(); sb.stop(); main.shutdownNow()
        }
    }
}
