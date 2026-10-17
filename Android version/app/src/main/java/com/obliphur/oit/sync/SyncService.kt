package com.obliphur.oit.sync

import com.obliphur.oit.core.numText
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedInputStream
import java.io.File
import java.io.InputStream
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.NetworkInterface
import java.net.ServerSocket
import java.net.Socket
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.locks.ReentrantLock
import kotlin.concurrent.withLock

/** 和本机数据打交道的部分 (Android 实现见 AndroidLocal.kt). 所有方法都在界面线程里调用. */
interface SyncLocal {
    fun netMode(): String
    fun autoText(): String
    fun ledger(): JSONObject
    /** {文档: {项: 值}}, 值是 JSONObject / JSONArray / String / Number / null. */
    fun docs(): Map<String, Map<String, Any?>>
    fun apply(doc: String, changes: Map<String, Any?>)
    fun clearHistory()
    fun status(): JSONObject
    fun pairRequest(req: PairRequest)
    fun changed()
}

/** 在界面线程里执行, 等它做完 (同 devsync.MainRunner). post=null 时直接在当前线程执行 (测试用). */
class MainRunner(private val post: ((Runnable) -> Unit)? = null, private val isMain: () -> Boolean = { false }) {
    fun <T> call(fn: () -> T): T {
        if (post == null || isMain()) return fn()
        val latch = java.util.concurrent.CountDownLatch(1)
        var ok: T? = null
        var err: Throwable? = null
        post.invoke(Runnable {
            try { ok = fn() } catch (e: Throwable) { err = e } finally { latch.countDown() }
        })
        if (!latch.await(8, TimeUnit.SECONDS)) throw IllegalStateException("main thread busy")
        err?.let { throw it }
        @Suppress("UNCHECKED_CAST")
        return ok as T
    }
}

class PairRequest(
    val token: String, val id: String, val name: String, val platform: String,
    val addr: String, val port: Int, val key: ByteArray, val code: String, val mother: String,
) {
    @Volatile var state = "pending"
    val ts = System.currentTimeMillis()
}

class Outgoing(val addr: String, val port: Int) {
    @Volatile var state = "connecting"
    @Volatile var code = ""
    @Volatile var name = ""
    @Volatile var error = ""
}

class Found(val id: String, val name: String, val platform: String, val addr: String, val port: Int,
            val netMode: String, val ts: Long)

/**
 * 设备同步 (MECHANICS 15). 和桌面版 devsync.py 的协议完全一样, 可以互相绑定.
 */
class SyncService(
    dir: File,
    private val local: SyncLocal,
    private val runner: MainRunner,
    private val platform: String = "android",
    defaultName: String = "Android",
    private val httpPort0: Int = HTTP_PORT,
    private val udpPort: Int = UDP_PORT,
) {
    companion object {
        const val PROTO = 1
        const val HTTP_PORT = 17930
        const val UDP_PORT = 17931
        /** 母端每隔这么久向每台子端发一次同步请求. */
        const val SYNC_EVERY_MS = 30_000L
        /** 这么久之内同步过的设备才算"在线" (比较最后操作时间用). */
        const val FRESH_MS = 120_000L
        const val PAIR_TIMEOUT_MS = 120_000L
        /** 设置里每台设备各自决定的项, 不同步. */
        val LOCAL_SETTINGS = setOf("NET_MODE", "FILTER_MODE", "FONT_SCALE", "CHIME_WAV",
            "WINDOW_LIMIT_ENABLED", "WINDOW_LIMIT", "WINDOW_FOCUS_ENABLED", "UPDATE_CHECK", "UPDATE_AUTO")

        /** 值的规范文字: 数字一律按 numText, 对象按键排序 (用来判断改没改过). */
        fun canon(v: Any?): String = when (v) {
            null, JSONObject.NULL -> "null"
            is Boolean -> v.toString()
            is Number -> numText(v.toDouble())
            is String -> JSONObject.quote(v)
            is JSONArray -> (0 until v.length()).joinToString(",", "[", "]") { canon(v.opt(it)) }
            is JSONObject -> v.keys().asSequence().sorted().joinToString(",", "{", "}") { "${JSONObject.quote(it)}:${canon(v.opt(it))}" }
            is Map<*, *> -> v.keys.map { it.toString() }.sorted().joinToString(",", "{", "}") { "${JSONObject.quote(it)}:${canon(v[it])}" }
            is Collection<*> -> v.joinToString(",", "[", "]") { canon(it) }
            else -> JSONObject.quote(v.toString())
        }

        fun hash(v: Any?): String =
            SyncCrypto.hex(MessageDigest.getInstance("SHA-256").digest(canon(v).toByteArray())).take(16)

        val H_NONE = hash(null)

        /** 其他设备今天的联网额度用量之和 (只算日期是今天的). */
        fun peerNet(ledgers: List<JSONObject>, date: String): DoubleArray {
            val out = DoubleArray(4)   // used, bonus, tomorrow_used, debt
            for (l in ledgers) {
                val n = l.optJSONObject("net") ?: continue
                if (n.optString("date") != date) continue
                listOf("used", "bonus", "tomorrow_used", "debt").forEachIndexed { i, k -> out[i] += maxOf(0.0, n.optDouble(k, 0.0)) }
            }
            return out
        }
    }

    private val file = File(dir, "sync_state.json")
    private val lock = ReentrantLock()
    @Volatile var dead = false
    var port: Int = 0
        private set
    private val incoming = HashMap<String, PairRequest>()
    @Volatile var outgoing: Outgoing? = null
        private set
    val found = java.util.concurrent.ConcurrentHashMap<String, Found>()
    private var server: ServerSocket? = null
    private var udp: DatagramSocket? = null
    private val pool = Executors.newCachedThreadPool()
    private val wake = Object()
    @Volatile private var woken = false
    private val state: JSONObject = load()

    init {
        if (state.optJSONObject("device") == null) {
            state.put("device", JSONObject().put("id", SyncCrypto.hex(ByteArray(6).also { SecureRandom().nextBytes(it) }))
                .put("name", defaultName))
            save()
        }
    }

    // ---- 存档 ----

    private fun load(): JSONObject {
        val d = try { JSONObject(file.readText()) } catch (e: Exception) { JSONObject() }
        for (k in listOf("peers", "track", "ledgers", "status")) if (d.optJSONObject(k) == null) d.put(k, JSONObject())
        return d
    }

    private fun save() {
        if (dead) return
        lock.withLock {
            try {
                val tmp = File(file.path + ".tmp")
                tmp.writeText(state.toString())
                if (!tmp.renameTo(file)) { file.delete(); tmp.renameTo(file) }
            } catch (_: Exception) {
            }
        }
    }

    val myId: String get() = state.getJSONObject("device").getString("id")
    val myName: String get() = state.getJSONObject("device").optString("name", "Android")

    fun peers(): Map<String, JSONObject> = lock.withLock {
        val p = state.getJSONObject("peers")
        p.keys().asSequence().associateWith { JSONObject(p.getJSONObject(it).toString()) }
    }

    private fun proxyOk() = try { local.netMode() == "proxy" } catch (e: Exception) { false }

    fun deviceInfo(): JSONObject = JSONObject().put("id", myId).put("name", myName).put("platform", platform)
        .put("port", port).put("net_mode", local.netMode()).put("v", PROTO)

    private fun info(): JSONObject = runner.call { deviceInfo() }

    // ---- 启动 / 停止 ----

    fun start() {
        for (p in httpPort0 until httpPort0 + 10) {
            try {
                server = ServerSocket().apply { reuseAddress = true; bind(InetSocketAddress(p)) }
                port = p
                break
            } catch (_: Exception) {
            }
        }
        server?.let { s -> Thread({ acceptLoop(s) }, "oit-sync-http").apply { isDaemon = true }.start() }
        try {
            udp = DatagramSocket(null).apply {
                reuseAddress = true; broadcast = true; soTimeout = 1000; bind(InetSocketAddress(udpPort))
            }
            Thread({ udpLoop() }, "oit-sync-udp").apply { isDaemon = true }.start()
        } catch (_: Exception) {
            udp = null
        }
        Thread({ syncLoop() }, "oit-sync").apply { isDaemon = true }.start()
    }

    fun stop() {
        dead = true
        syncNow()
        runCatching { server?.close() }
        runCatching { udp?.close() }
        pool.shutdownNow()
    }

    // ---- 发现 ----

    private fun udpLoop() {
        val buf = ByteArray(4096)
        while (!dead) {
            val pk = DatagramPacket(buf, buf.size)
            try {
                udp!!.receive(pk)
            } catch (e: java.net.SocketTimeoutException) {
                continue
            } catch (e: Exception) {
                if (dead) return
                Thread.sleep(1000); continue
            }
            val msg = try { JSONObject(String(pk.data, 0, pk.length, Charsets.UTF_8)) } catch (e: Exception) { continue }
            if (msg.optString("id") == myId) continue
            when (msg.optString("oit")) {
                "discover" -> try {
                    val reply = info().put("oit", "here").toString().toByteArray()
                    udp!!.send(DatagramPacket(reply, reply.size, pk.address, pk.port))
                } catch (_: Exception) {
                }
                "here" -> noteFound(msg, pk.address.hostAddress ?: "")
            }
        }
    }

    fun noteFound(msg: JSONObject, ip: String) {
        val f = Found(msg.optString("id"), msg.optString("name", "?"), msg.optString("platform", "?"), ip,
            msg.optInt("port", HTTP_PORT), msg.optString("net_mode"), System.currentTimeMillis())
        if (f.id.isEmpty()) return
        found[f.id] = f
        lock.withLock {
            state.getJSONObject("peers").optJSONObject(f.id)?.let {
                if (it.optString("addr") != ip || it.optInt("port") != f.port) { it.put("addr", ip).put("port", f.port) }
            }
        }
    }

    private fun broadcastTargets(): Set<InetAddress> {
        val out = mutableSetOf(InetAddress.getByName("255.255.255.255"))
        try {
            for (ni in NetworkInterface.getNetworkInterfaces()) {
                if (!ni.isUp || ni.isLoopback) continue
                for (ia in ni.interfaceAddresses) ia.broadcast?.let { out.add(it) }
            }
        } catch (_: Exception) {
        }
        return out
    }

    /** 广播找一下同一局域网里的 OIT (阻塞 waitMs). */
    fun discover(waitMs: Long = 2500): List<Found> {
        val msg = JSONObject().put("oit", "discover").put("id", myId).put("v", PROTO).toString().toByteArray()
        DatagramSocket().use { s ->
            s.broadcast = true
            s.soTimeout = 300
            for (t in broadcastTargets()) runCatching { s.send(DatagramPacket(msg, msg.size, t, udpPort)) }
            val end = System.currentTimeMillis() + waitMs
            val buf = ByteArray(4096)
            while (System.currentTimeMillis() < end) {
                val pk = DatagramPacket(buf, buf.size)
                try { s.receive(pk) } catch (e: java.net.SocketTimeoutException) { continue } catch (e: Exception) { break }
                val m = try { JSONObject(String(pk.data, 0, pk.length, Charsets.UTF_8)) } catch (e: Exception) { continue }
                if (m.optString("oit") == "here" && m.optString("id") != myId) noteFound(m, pk.address.hostAddress ?: "")
            }
        }
        val now = System.currentTimeMillis()
        return found.values.filter { now - it.ts < 60_000 }
    }

    // ---- HTTP (只实现用得到的那一点) ----

    private fun readLine(i: InputStream): String {
        val sb = StringBuilder()
        while (true) {
            val c = i.read()
            if (c < 0 || c == '\n'.code) break
            if (c != '\r'.code) sb.append(c.toChar())
        }
        return sb.toString()
    }

    private fun readMessage(i: InputStream): Triple<String, Map<String, String>, ByteArray> {
        val first = readLine(i)
        val headers = HashMap<String, String>()
        while (true) {
            val l = readLine(i)
            if (l.isEmpty()) break
            val c = l.indexOf(':')
            if (c > 0) headers[l.substring(0, c).trim().lowercase()] = l.substring(c + 1).trim()
        }
        val n = headers["content-length"]?.toIntOrNull() ?: -1
        val body = if (n >= 0) {
            if (n > 8_000_000) throw IllegalStateException("too large")
            val b = ByteArray(n)
            var off = 0
            while (off < n) {
                val r = i.read(b, off, n - off)
                if (r < 0) break
                off += r
            }
            b
        } else i.readBytes()
        return Triple(first, headers, body)
    }

    private fun http(addr: String, port: Int, method: String, path: String, body: JSONObject?, timeoutMs: Int = 6000): Pair<Int, JSONObject> {
        Socket().use { s ->
            s.connect(InetSocketAddress(addr, port), timeoutMs)
            s.soTimeout = timeoutMs
            val data = body?.toString()?.toByteArray(Charsets.UTF_8) ?: ByteArray(0)
            val head = "$method $path HTTP/1.1\r\nHost: $addr:$port\r\nContent-Type: application/json\r\n" +
                "Content-Length: ${data.size}\r\nConnection: close\r\n\r\n"
            s.getOutputStream().apply { write(head.toByteArray()); write(data); flush() }
            val (status, _, raw) = readMessage(BufferedInputStream(s.getInputStream()))
            val code = status.split(" ").getOrNull(1)?.toIntOrNull() ?: 0
            val obj = try { if (raw.isEmpty()) JSONObject() else JSONObject(String(raw, Charsets.UTF_8)) } catch (e: Exception) { JSONObject() }
            return code to obj
        }
    }

    private fun acceptLoop(s: ServerSocket) {
        while (!dead) {
            val c = try { s.accept() } catch (e: Exception) { if (dead) return else continue }
            try {
                pool.execute { serve(c) }
            } catch (e: Exception) {
                runCatching { c.close() }
            }
        }
    }

    private fun serve(c: Socket) {
        c.use {
            try {
                c.soTimeout = 10_000
                val (first, _, raw) = readMessage(BufferedInputStream(c.getInputStream()))
                val parts = first.split(" ")
                val method = parts.getOrNull(0) ?: ""
                val path = parts.getOrNull(1) ?: ""
                val body = try { if (raw.isEmpty()) JSONObject() else JSONObject(String(raw, Charsets.UTF_8)) } catch (e: Exception) { JSONObject() }
                val ip = c.inetAddress.hostAddress ?: ""
                val (code, out) = when {
                    method == "GET" && path == "/oit/v1/hello" -> 200 to info()
                    method == "GET" && path.startsWith("/oit/v1/pair/") -> pairStatus(path.substringAfterLast('/'))
                    method == "POST" && path == "/oit/v1/pair" -> onPair(body, ip)
                    method == "POST" && path == "/oit/v1/sync" -> onSync(body)
                    method == "POST" && path == "/oit/v1/unpair" -> onUnpair(body)
                    else -> 404 to JSONObject().put("error", "not found")
                }
                val data = out.toString().toByteArray(Charsets.UTF_8)
                val reason = if (code == 200) "OK" else "Error"
                c.getOutputStream().apply {
                    write(("HTTP/1.1 $code $reason\r\nContent-Type: application/json\r\nContent-Length: ${data.size}\r\n" +
                        "Connection: close\r\n\r\n").toByteArray())
                    write(data)
                    flush()
                }
            } catch (_: Exception) {
            }
        }
    }

    fun hello(addr: String, port: Int = HTTP_PORT): JSONObject {
        val (st, d) = http(addr, port, "GET", "/oit/v1/hello", null, 3000)
        if (st != 200) throw IllegalStateException("HTTP $st")
        return d
    }

    // ---- 绑定: 发起方 ----

    fun startPairing(addr: String, port: Int, motherIsMe: Boolean) {
        val o = Outgoing(addr, port)
        outgoing = o
        pool.execute { pairWorker(o, motherIsMe) }
    }

    fun cancelPairing() {
        outgoing?.state = "cancelled"
    }

    private fun pairWorker(o: Outgoing, motherIsMe: Boolean) {
        try {
            if (!runner.call { proxyOk() }) throw IllegalStateException("not-proxy")
            val (x, pub) = SyncCrypto.keypair()
            val req = info().put("pub", pub.toString(16)).put("mother", if (motherIsMe) "me" else "you")
            val (st, d) = http(o.addr, o.port, "POST", "/oit/v1/pair", req)
            if (st != 200) throw IllegalStateException(d.optString("error", "HTTP $st"))
            val k = SyncCrypto.shared(x, d.getString("pub"))
            val token = d.getString("token")
            o.code = SyncCrypto.pairCode(k)
            o.name = d.optString("name", "?")
            o.state = "waiting"
            val deadline = System.currentTimeMillis() + PAIR_TIMEOUT_MS
            while (System.currentTimeMillis() < deadline && o.state == "waiting" && !dead) {
                Thread.sleep(1500)
                val (_, r) = http(o.addr, o.port, "GET", "/oit/v1/pair/$token", null, 4000)
                when (r.optString("state")) {
                    "rejected" -> { o.state = "rejected"; return }
                    "accepted" -> {
                        if (r.optString("proof") != SyncCrypto.acceptProof(k, token)) throw IllegalStateException("bad proof")
                        val peerId = d.getString("id")
                        val mother = if (motherIsMe) myId else peerId
                        runner.call { addPeer(peerId, d.optString("name", "?"), d.optString("platform", "?"), o.addr, o.port, k, mother) }
                        o.state = "accepted"
                        if (mother != myId) syncWith(peerId, init = true)
                        syncNow()
                        return
                    }
                }
            }
            if (o.state == "waiting") o.state = "timeout"
        } catch (e: Exception) {
            o.error = e.message ?: e.javaClass.simpleName
            o.state = "error"
        }
    }

    private fun addPeer(id: String, name: String, platform: String, addr: String, port: Int, k: ByteArray, mother: String) {
        lock.withLock {
            state.getJSONObject("peers").put(id, JSONObject().put("name", name).put("platform", platform)
                .put("addr", addr).put("port", port).put("key", SyncCrypto.hex(k)).put("mother", mother)
                .put("paired_at", System.currentTimeMillis()).put("last_ok", 0).put("last_err", "")
                // 本机是子端: 用母端的内容初始化之前不参加普通同步
                .put("init", mother != myId))
        }
        save()
        local.changed()
    }

    // ---- 绑定: 被请求方 ----

    private fun onPair(body: JSONObject, ip: String): Pair<Int, JSONObject> {
        if (!runner.call { proxyOk() }) return 409 to JSONObject().put("error", "not-proxy")
        if (body.optString("net_mode") != "proxy") return 409 to JSONObject().put("error", "peer-not-proxy")
        val peerId = body.optString("id")
        val (x, pub) = SyncCrypto.keypair()
        val k = try { SyncCrypto.shared(x, body.getString("pub")) } catch (e: Exception) {
            return 400 to JSONObject().put("error", "bad request")
        }
        if (peerId.isEmpty()) return 400 to JSONObject().put("error", "bad request")
        val token = SyncCrypto.hex(ByteArray(8).also { SecureRandom().nextBytes(it) })
        val mother = if (body.optString("mother") == "me") peerId else myId
        val req = PairRequest(token, peerId, body.optString("name", "?"), body.optString("platform", "?"), ip,
            body.optInt("port", HTTP_PORT), k, SyncCrypto.pairCode(k), mother)
        synchronized(incoming) {
            incoming.entries.removeAll { System.currentTimeMillis() - it.value.ts > PAIR_TIMEOUT_MS + 30_000 }
            incoming[token] = req
        }
        runCatching { runner.call { local.pairRequest(req) } }
        return 200 to JSONObject().put("id", myId).put("name", myName).put("platform", platform)
            .put("pub", pub.toString(16)).put("token", token)
    }

    private fun pairStatus(token: String): Pair<Int, JSONObject> {
        val r = synchronized(incoming) { incoming[token] } ?: return 404 to JSONObject().put("state", "unknown")
        val out = JSONObject().put("state", r.state)
        if (r.state == "accepted") out.put("proof", SyncCrypto.acceptProof(r.key, token))
        return 200 to out
    }

    /** 界面线程: 用户在提示窗里接受 / 拒绝了绑定请求. */
    fun answerPairing(token: String, accept: Boolean): Boolean {
        val r = synchronized(incoming) { incoming[token] } ?: return false
        if (r.state != "pending") return false
        if (!accept) { r.state = "rejected"; return true }
        addPeer(r.id, r.name, r.platform, r.addr, r.port, r.key, r.mother)
        r.state = "accepted"
        if (r.mother != myId) pool.execute { syncWith(r.id, init = true) }
        syncNow()
        return true
    }

    // ---- 解除绑定 ----

    fun unpair(peerId: String, notify: Boolean = true) {
        val p = lock.withLock {
            state.getJSONObject("ledgers").remove(peerId)
            state.getJSONObject("status").remove(peerId)
            state.getJSONObject("peers").remove(peerId) as? JSONObject
        }
        save()
        local.changed()
        if (p != null && notify) pool.execute {
            runCatching {
                val env = SyncCrypto.seal(SyncCrypto.unhex(p.getString("key")), myId, JSONObject().put("unpair", true))
                http(p.getString("addr"), p.getInt("port"), "POST", "/oit/v1/unpair", env, 3000)
            }
        }
    }

    private fun onUnpair(env: JSONObject): Pair<Int, JSONObject> {
        val from = env.optString("from")
        val p = peers()[from] ?: return 200 to JSONObject()
        try { SyncCrypto.unseal(SyncCrypto.unhex(p.getString("key")), env) } catch (e: SealError) {
            return 403 to JSONObject().put("error", e.message)
        }
        runner.call { unpair(from, notify = false) }
        return 200 to JSONObject()
    }

    // ---- 文档 ----

    private fun track(doc: String): JSONObject = state.getJSONObject("track").optJSONObject(doc)
        ?: JSONObject().also { state.getJSONObject("track").put(doc, it) }

    /** 本机文档 + 每一项的修改时间. 和上一次相比变了的项, 修改时间记为现在. */
    private fun stamp(localDocs: Map<String, Map<String, Any?>>): Map<String, Map<String, Pair<Long, Any?>>> {
        val now = System.currentTimeMillis()
        val out = HashMap<String, Map<String, Pair<Long, Any?>>>()
        for ((doc, kv) in localDocs) {
            val t = track(doc)
            for ((key, v) in kv) {
                val h = hash(v)
                val cur = t.optJSONArray(key)
                if (cur == null || cur.optString(0) != h) t.put(key, JSONArray().put(h).put(now))
            }
            for (key in t.keys().asSequence().toList()) {
                if (key !in kv && t.getJSONArray(key).optString(0) != H_NONE) t.put(key, JSONArray().put(H_NONE).put(now))
            }
            out[doc] = t.keys().asSequence().associateWith { t.getJSONArray(it).optLong(1) to kv[it] }
        }
        return out
    }

    private fun wins(doc: String, mt: Long, v: Any?, cur: Pair<Long, Any?>): Boolean {
        if (doc == "hours") {
            // 超时自动记录的内容永远让位给自己填写的内容
            val auto = local.autoText()
            val rAuto = v == auto
            val lAuto = cur.second == auto
            val lHas = cur.second != null && cur.second.toString().isNotEmpty()
            val rHas = v != null && v.toString().isNotEmpty()
            if (rAuto && lHas && !lAuto) return false
            if (lAuto && rHas && !rAuto) return true
        }
        return mt > cur.first
    }

    private fun wire(v: Any?): Any = when (v) {
        null -> JSONObject.NULL
        is Map<*, *> -> JSONObject(v)
        is Collection<*> -> JSONArray(v)
        else -> v
    }

    /** 界面线程: 要发给别人的全部内容. */
    fun snapshot(): JSONObject {
        val own = local.ledger().put("rev", System.currentTimeMillis()).put("name", myName).put("platform", platform)
        val st = local.status().put("ts", System.currentTimeMillis())
        val docs = JSONObject()
        lock.withLock {
            for ((doc, kv) in stamp(local.docs())) {
                val o = JSONObject()
                for ((k, p) in kv) o.put(k, JSONArray().put(p.first).put(wire(p.second)))
                docs.put(doc, o)
            }
        }
        save()
        return lock.withLock {
            val ledgers = JSONObject(state.getJSONObject("ledgers").toString()).put(myId, own)
            val status = JSONObject(state.getJSONObject("status").toString()).put(myId, st)
            JSONObject().put("v", PROTO).put("device", deviceInfo()).put("ledgers", ledgers).put("docs", docs).put("status", status)
        }
    }

    private fun unwire(v: Any?): Any? = if (v == null || v == JSONObject.NULL) null else v

    /** 界面线程: 并入别人发来的内容. init=true: 本机是子端, 第一次用母端的内容整体初始化. */
    fun merge(snap: JSONObject?, init: Boolean = false) {
        if (snap == null) return
        if (init) local.clearHistory()
        lock.withLock {
            val led = state.getJSONObject("ledgers")
            snap.optJSONObject("ledgers")?.let { r ->
                for (did in r.keys()) {
                    if (did == myId) continue
                    val l = r.optJSONObject(did) ?: continue
                    if (l.optLong("rev") > (led.optJSONObject(did)?.optLong("rev", -1) ?: -1)) led.put(did, l)
                }
            }
            val sts = state.getJSONObject("status")
            snap.optJSONObject("status")?.let { r ->
                for (did in r.keys()) {
                    if (did == myId) continue
                    val s = r.optJSONObject(did) ?: continue
                    if (s.optLong("ts") > (sts.optJSONObject(did)?.optLong("ts", -1) ?: -1)) sts.put(did, s)
                }
            }
        }
        val localDocs = local.docs()
        val stamped = lock.withLock { stamp(localDocs) }
        val now = System.currentTimeMillis()
        val remote = snap.optJSONObject("docs") ?: JSONObject()
        for (doc in remote.keys()) {
            if (doc !in localDocs) continue
            val entries = remote.optJSONObject(doc) ?: continue
            val mine = stamped[doc] ?: emptyMap()
            val changes = LinkedHashMap<String, Any?>()
            lock.withLock {
                val t = track(doc)
                for (key in entries.keys()) {
                    val e = entries.optJSONArray(key) ?: continue
                    val mt = e.optLong(0)
                    val v = unwire(e.opt(1))
                    val cur = mine[key]
                    if (init || cur == null || wins(doc, mt, v, cur)) {
                        if (cur == null || canon(cur.second) != canon(v)) changes[key] = v
                        t.put(key, JSONArray().put(hash(v)).put(mt))
                    }
                }
                if (init) for ((key, cur) in mine) {
                    if (!entries.has(key) && cur.second != null) {
                        changes[key] = null
                        t.put(key, JSONArray().put(H_NONE).put(now))
                    }
                }
            }
            if (changes.isNotEmpty()) runCatching { local.apply(doc, changes) }
        }
        save()
        local.changed()
    }

    // ---- 同步 ----

    fun syncWith(peerId: String, init: Boolean = false): Boolean {
        val p = peers()[peerId] ?: return false
        if (p.optBoolean("init") && !init) return syncWith(peerId, init = true)
        val k = SyncCrypto.unhex(p.getString("key"))
        return try {
            val snap = runner.call {
                if (init) snapshot().put("docs", JSONObject()).put("ledgers", JSONObject()) else snapshot()
            }
            val env = SyncCrypto.seal(k, myId, JSONObject().put("snap", snap).put("init", init))
            val (st, reply) = http(p.getString("addr"), p.getInt("port"), "POST", "/oit/v1/sync", env, 10_000)
            if (st == 401) throw IllegalStateException("unpaired")
            if (st != 200) throw IllegalStateException(reply.optString("error", "HTTP $st"))
            val body = SyncCrypto.unseal(k, reply)
            runner.call { merge(body.optJSONObject("snap"), init) }
            lock.withLock {
                state.getJSONObject("peers").optJSONObject(peerId)?.let { q ->
                    q.put("last_ok", System.currentTimeMillis()).put("last_err", "")
                    if (init) q.put("init", false)
                    body.optJSONObject("snap")?.optJSONObject("device")?.optString("name")?.takeIf { it.isNotEmpty() }
                        ?.let { q.put("name", it) }
                }
            }
            save()
            true
        } catch (e: Exception) {
            lock.withLock {
                state.getJSONObject("peers").optJSONObject(peerId)?.put("last_err", e.message ?: e.javaClass.simpleName)
            }
            false
        }
    }

    private fun onSync(env: JSONObject): Pair<Int, JSONObject> {
        if (!runner.call { proxyOk() }) return 409 to JSONObject().put("error", "not-proxy")
        val from = env.optString("from")
        val p = peers()[from] ?: return 401 to JSONObject().put("error", "unpaired")
        if (p.optBoolean("init")) return 409 to JSONObject().put("error", "initializing")
        val k = SyncCrypto.unhex(p.getString("key"))
        val body = try { SyncCrypto.unseal(k, env) } catch (e: SealError) {
            return 403 to JSONObject().put("error", e.message)
        }
        val snap = body.optJSONObject("snap") ?: JSONObject()
        if (snap.optJSONObject("device")?.optString("net_mode") != "proxy") return 409 to JSONObject().put("error", "peer-not-proxy")
        val mine = try {
            runner.call { merge(snap); snapshot() }
        } catch (e: Exception) {
            return 503 to JSONObject().put("error", e.message)
        }
        lock.withLock {
            state.getJSONObject("peers").optJSONObject(from)?.put("last_ok", System.currentTimeMillis())?.put("last_err", "")
        }
        return 200 to SyncCrypto.seal(k, myId, JSONObject().put("snap", mine))
    }

    @Volatile private var manual = false

    /** 立即同步一轮; 子端也会主动向母端发一次. */
    fun syncNow() {
        manual = true
        synchronized(wake) { woken = true; wake.notifyAll() }
    }

    private fun syncLoop() {
        var lastDiscover = 0L
        while (!dead) {
            synchronized(wake) {
                if (!woken) wake.wait(SYNC_EVERY_MS)
                woken = false
            }
            if (dead) return
            val wasManual = manual
            manual = false
            if (!runner.call { proxyOk() }) continue
            // 母端向子端发请求; 子端只在还没初始化或按了"立即同步"时向母端发
            val targets = peers().filter { (_, p) -> p.optString("mother") == myId || p.optBoolean("init") || wasManual }.keys
            val failed = targets.filter { !syncWith(it) }
            // 有设备连不上: 地址可能变了, 广播找一下再试一次
            if (failed.isNotEmpty() && System.currentTimeMillis() - lastDiscover > 60_000) {
                lastDiscover = System.currentTimeMillis()
                runCatching { discover(1500) }
                failed.forEach { syncWith(it) }
            }
        }
    }

    // ---- 给本机其他部分用 ----

    fun peerLedgers(): List<JSONObject> = lock.withLock {
        val l = state.getJSONObject("ledgers")
        l.keys().asSequence().filter { it != myId }.mapNotNull { l.optJSONObject(it) }.toList()
    }

    /** 本机是不是最后有人操作的设备 (只比较最近 2 分钟内同步过的设备). 界面线程调用. */
    fun isLatestActive(): Boolean {
        val mine = try { local.status().optLong("last_op") } catch (e: Exception) { return true }
        val now = System.currentTimeMillis()
        return peerStatus().none { now - it.third.optLong("ts") < FRESH_MS && it.third.optLong("last_op") > mine }
    }

    /** 这台设备最近 2 分钟内同步过吗. */
    fun isFresh(id: String): Boolean {
        val now = System.currentTimeMillis()
        return peerStatus().any { it.first == id && now - it.third.optLong("ts") < FRESH_MS }
    }

    /** 其他设备此刻的状态: (设备 id, 名字, 状态). */
    fun peerStatus(): List<Triple<String, String, JSONObject>> = lock.withLock {
        val s = state.getJSONObject("status")
        val l = state.getJSONObject("ledgers")
        s.keys().asSequence().filter { it != myId }.mapNotNull { id ->
            s.optJSONObject(id)?.let { Triple(id, l.optJSONObject(id)?.optString("name") ?: "?", it) }
        }.toList()
    }

    @Suppress("unused")
    private fun awaitPool() = pool.awaitTermination(1, TimeUnit.SECONDS)
}
