package com.obliphur.oit.service

import java.net.InetAddress

/** 从 VPN 读到的一个 UDP 包 (IPv4 或 IPv6). */
class UdpPacket(
    val v6: Boolean,
    val src: ByteArray, val dst: ByteArray,
    val srcPort: Int, val dstPort: Int,
    val payload: ByteArray,
) {
    val srcAddr: InetAddress get() = InetAddress.getByAddress(src)
    val dstAddr: InetAddress get() = InetAddress.getByAddress(dst)
}

/** 只处理发往 VPN 里假 DNS 地址的 UDP 包; 其余一律丢弃 (返回 null). */
object Packets {
    private fun u16(b: ByteArray, i: Int) = ((b[i].toInt() and 0xff) shl 8) or (b[i + 1].toInt() and 0xff)

    fun parseUdp(b: ByteArray, len: Int): UdpPacket? {
        if (len < 20) return null
        return when (b[0].toInt() ushr 4) {
            4 -> {
                val ihl = (b[0].toInt() and 0x0f) * 4
                if (ihl < 20 || len < ihl + 8 || b[9].toInt() != 17) return null
                val frag = u16(b, 6) and 0x3fff        // 分片的包不处理
                if (frag != 0) return null
                val total = minOf(len, u16(b, 2))
                val ulen = u16(b, ihl + 4)
                val end = minOf(total, ihl + ulen)
                if (end < ihl + 8) return null
                UdpPacket(false, b.copyOfRange(12, 16), b.copyOfRange(16, 20),
                    u16(b, ihl), u16(b, ihl + 2), b.copyOfRange(ihl + 8, end))
            }
            6 -> {
                if (len < 48 || b[6].toInt() != 17) return null
                val plen = u16(b, 4)
                val end = minOf(len, 40 + plen)
                if (end < 48) return null
                UdpPacket(true, b.copyOfRange(8, 24), b.copyOfRange(24, 40),
                    u16(b, 40), u16(b, 42), b.copyOfRange(48, end))
            }
            else -> null
        }
    }

    private fun sum(data: ByteArray, off: Int, len: Int, start: Long = 0): Long {
        var s = start
        var i = off
        while (i + 1 < off + len) {
            s += u16(data, i).toLong(); i += 2
        }
        if (i < off + len) s += (data[i].toLong() and 0xff) shl 8
        return s
    }

    private fun fold(s0: Long): Int {
        var s = s0
        while (s ushr 16 != 0L) s = (s and 0xffff) + (s ushr 16)
        return (s.inv() and 0xffff).toInt()
    }

    private fun put16(b: ByteArray, i: Int, v: Int) {
        b[i] = (v ushr 8).toByte(); b[i + 1] = v.toByte()
    }

    /** 回给发起查询的应用: 源 / 目的地址和端口对调. */
    fun buildReply(q: UdpPacket, payload: ByteArray): ByteArray {
        val src = q.dst
        val dst = q.src
        val udpLen = 8 + payload.size
        val hdr = if (q.v6) 40 else 20
        val out = ByteArray(hdr + udpLen)
        if (q.v6) {
            out[0] = 0x60
            put16(out, 4, udpLen)
            out[6] = 17
            out[7] = 64
            System.arraycopy(src, 0, out, 8, 16)
            System.arraycopy(dst, 0, out, 24, 16)
        } else {
            out[0] = 0x45
            put16(out, 2, out.size)
            put16(out, 6, 0x4000)
            out[8] = 64
            out[9] = 17
            System.arraycopy(src, 0, out, 12, 4)
            System.arraycopy(dst, 0, out, 16, 4)
            put16(out, 10, fold(sum(out, 0, 20)))
        }
        put16(out, hdr, q.dstPort)
        put16(out, hdr + 2, q.srcPort)
        put16(out, hdr + 4, udpLen)
        System.arraycopy(payload, 0, out, hdr + 8, payload.size)
        // UDP 校验和: 伪首部 + UDP 首部 + 数据 (IPv6 必须有)
        var ps = sum(src, 0, src.size) + sum(dst, 0, dst.size)
        ps += 17L + udpLen.toLong()
        var c = fold(sum(out, hdr, udpLen, ps))
        if (c == 0) c = 0xffff
        put16(out, hdr + 6, c)
        return out
    }
}

/** DNS 报文的最小解析: 只取第一个问题的域名. */
object Dns {
    /** 问题部分结束的位置 (header + question), 解析失败返回 -1. */
    private fun questionEnd(m: ByteArray): Int {
        if (m.size < 12) return -1
        val qd = ((m[4].toInt() and 0xff) shl 8) or (m[5].toInt() and 0xff)
        if (qd < 1) return -1
        var i = 12
        while (i < m.size) {
            val l = m[i].toInt() and 0xff
            if (l == 0) { i += 1; break }
            if (l and 0xc0 != 0) return -1
            i += 1 + l
        }
        i += 4
        return if (i <= m.size) i else -1
    }

    fun qname(m: ByteArray): String? {
        if (questionEnd(m) < 0) return null
        val sb = StringBuilder()
        var i = 12
        while (true) {
            val l = m[i].toInt() and 0xff
            if (l == 0) break
            if (sb.isNotEmpty()) sb.append('.')
            for (j in 1..l) sb.append((m[i + j].toInt() and 0xff).toChar())
            i += 1 + l
        }
        return sb.toString().lowercase()
    }

    /** 拦截: 回一个 NXDOMAIN (不带 SOA, 解析器不会缓存这个否定结果). */
    fun nxdomain(m: ByteArray): ByteArray? {
        val end = questionEnd(m)
        if (end < 0) return null
        val r = m.copyOf(end)
        r[2] = ((r[2].toInt() and 0x79) or 0x80).toByte()     // QR=1, 保留 opcode 与 RD, AA=TC=0
        r[3] = 0x83.toByte()                                    // RA=1, RCODE=3
        for (k in 6 until 12) r[k] = 0                          // AN / NS / AR = 0
        return r
    }
}
