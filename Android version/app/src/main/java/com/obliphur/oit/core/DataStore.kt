package com.obliphur.oit.core

import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.time.LocalDate
import java.time.LocalDateTime

data class FocusSeg(val kind: String, val start: LocalDateTime, val end: LocalDateTime)

/**
 * 学习时长, 整点记录, 专注 / 休息时间段, 应用使用时间. 对应桌面版 data_manager.py.
 */
class DataStore(val dir: File, private val fillWindow: () -> Double, private val autoText: () -> String) {
    var resetting = false

    private val studyFile = File(dir, "study_log.json")
    private val hourFile = File(dir, "hour_log.json")
    private val focusFile = File(dir, "focus_log.json")
    private val windowFile = File(dir, "window_usage.json")

    val study = HashMap<String, Double>()
    val hourDays = HashMap<String, HashMap<String, String>>()
    var hourCursor: LocalDateTime? = null
    var hourEnabled = true
    var todayDate: String = LocalDate.now().key()
    /** 正在等待填写的那一小时 (开始时刻). */
    var promptSlot: LocalDateTime? = null
    val focus = mutableListOf<FocusSeg>()
    val windowDays = HashMap<String, HashMap<String, Double>>()
    /** 设备同步: 其他设备的账 (MECHANICS 15), 显示合计用. */
    var peers: () -> List<JSONObject> = { emptyList() }
    private var windowDirty = false

    init {
        dir.mkdirs()
        loadStudy()
        pruneStudy()
        loadHours()
        loadFocus()
        loadWindows()
    }

    // ---- 学习时长 ----

    private fun loadStudy() {
        study.clear()
        val o = Store.readObj(studyFile) ?: return
        for (k in o.keys()) study[k] = o.dbl(k)
    }

    private fun saveStudy() {
        if (resetting) return
        Store.write(studyFile, JSONObject(study as Map<*, *>))
    }

    private fun studyAll(day: String): Double =
        (study[day] ?: 0.0) + peers().sumOf { it.optJSONObject("study")?.optDouble(day, 0.0)?.takeIf { v -> !v.isNaN() } ?: 0.0 }

    fun todayHours() = studyAll(todayDate)
    fun yesterdayHours() = studyAll(LocalDate.parse(todayDate).minusDays(1).key())

    /** 一段专注计入学习时长; 跨过零点的按时间比例拆到两天. */
    fun addStudySession(start: LocalDateTime, end: LocalDateTime, minutes: Double) {
        if (minutes <= 0) return
        val sd = start.toLocalDate().key()
        val ed = end.toLocalDate().key()
        if (sd == ed) {
            study[sd] = (study[sd] ?: 0.0) + minutes / 60.0
        } else {
            val midnight = start.floorDay().plusDays(1)
            val first = secondsBetween(start, midnight)
            val second = secondsBetween(midnight, end)
            val total = first + second
            if (total > 0) {
                study[sd] = (study[sd] ?: 0.0) + minutes * (first / total) / 60.0
                study[ed] = (study[ed] ?: 0.0) + minutes * (second / total) / 60.0
            } else {
                study[sd] = (study[sd] ?: 0.0) + minutes / 60.0
            }
        }
        saveStudy()
    }

    fun pruneStudy() {
        val (a, b) = monthPrefixes()
        if (study.keys.removeAll { it.take(7) != a && it.take(7) != b }) saveStudy()
    }

    fun monthStudy(prefix: String): Map<String, Double> {
        val days = study.keys.filter { it.startsWith(prefix) }.toMutableSet()
        for (l in peers()) l.optJSONObject("study")?.keys()?.forEach { if (it.startsWith(prefix)) days.add(it) }
        return days.associateWith { studyAll(it) }
    }

    /** 其他设备的专注 / 休息时间段. */
    private fun peerFocus(): List<FocusSeg> = peers().flatMap { l ->
        val arr = l.optJSONArray("focus") ?: return@flatMap emptyList()
        arr.objects().mapNotNull { r ->
            val s = runCatching { LocalDateTime.parse(r.optString("s"), Fmt.TS) }.getOrNull()
            val e = runCatching { LocalDateTime.parse(r.optString("e"), Fmt.TS) }.getOrNull()
            if (s != null && e != null && e.isAfter(s)) FocusSeg(r.optString("k"), s, e) else null
        }
    }

    // ---- 专注计时: 每一段专注 / 休息的起止时刻, 只留最近 7 天 ----

    private fun focusFloor() = LocalDateTime.now().floorDay().minusDays(6)

    private fun loadFocus() {
        focus.clear()
        val arr = Store.readObj(focusFile)?.optJSONArray("sessions") ?: JSONArray()
        for (r in arr.objects()) {
            val s = runCatching { LocalDateTime.parse(r.optString("s"), Fmt.TS) }.getOrNull() ?: continue
            val e = runCatching { LocalDateTime.parse(r.optString("e"), Fmt.TS) }.getOrNull() ?: continue
            val k = r.optString("k")
            if ((k == "study" || k == "break") && e.isAfter(s)) focus.add(FocusSeg(k, s, e))
        }
        focus.removeAll { !it.end.isAfter(focusFloor()) }
    }

    private fun saveFocus() {
        if (resetting) return
        focus.removeAll { !it.end.isAfter(focusFloor()) }
        Store.write(focusFile, JSONObject().put("sessions", JSONArray(focus.map {
            JSONObject().put("k", it.kind).put("s", it.start.format(Fmt.TS)).put("e", it.end.format(Fmt.TS))
        })))
    }

    fun addFocusSession(kind: String, start: LocalDateTime?, end: LocalDateTime?) {
        if (start == null || end == null || secondsBetween(start, end) < 1) return
        focus.add(FocusSeg(kind, start.withNano(0), end.withNano(0)))
        saveFocus()
    }

    /** 某一天 24 个小时各自的 (专注秒数, 休息秒数). live: 正在进行的一段 (kind, start). */
    fun focusHours(day: LocalDate, live: Pair<String, LocalDateTime>?): List<Pair<Double, Double>> {
        val d0 = day.atStartOfDay()
        val st = DoubleArray(24)
        val rs = DoubleArray(24)
        val segs = (focus + peerFocus()).toMutableList()
        if (live != null) segs.add(FocusSeg(live.first, live.second, LocalDateTime.now()))
        for (s in segs) {
            if (!s.end.isAfter(d0) || !s.start.isBefore(d0.plusDays(1))) continue
            for (h in 0 until 24) {
                val h0 = d0.plusHours(h.toLong())
                val h1 = h0.plusHours(1)
                val a = if (s.start.isAfter(h0)) s.start else h0
                val b = if (s.end.isBefore(h1)) s.end else h1
                val sec = secondsBetween(a, b)
                if (sec > 0) if (s.kind == "study") st[h] += sec else rs[h] += sec
            }
        }
        // 理论上不会重叠; 万一重叠, 专注优先, 一小时最多 3600 秒
        return (0 until 24).map {
            val a = minOf(3600.0, st[it])
            a to minOf(3600.0 - a, rs[it])
        }
    }

    // ---- 应用使用时间: {日期: {包名: 秒}}, "" 是空白 ----

    private fun loadWindows() {
        windowDays.clear()
        val days = Store.readObj(windowFile)?.optJSONObject("days") ?: return
        for (ds in days.keys()) {
            val d = days.optJSONObject(ds) ?: continue
            val m = HashMap<String, Double>()
            for (n in d.keys()) {
                val v = d.dbl(n)
                if (v > 0) m[n] = v
            }
            if (m.isNotEmpty()) windowDays[ds] = m
        }
        pruneWindows()
    }

    private fun pruneWindows() {
        val (a, b) = monthPrefixes()
        windowDays.keys.removeAll { it.take(7) != a && it.take(7) != b }
    }

    /** 把截止到 end 的这 seconds 秒记给 name; 跨过零点的部分记到前一天. */
    fun addWindowTime(name: String, seconds: Double, end: LocalDateTime = LocalDateTime.now()) {
        if (seconds <= 0) return
        var start = end.minusNanos((seconds * 1e9).toLong())
        while (start.isBefore(end)) {
            val next = start.floorDay().plusDays(1)
            val cut = if (end.isBefore(next)) end else next
            val day = windowDays.getOrPut(start.toLocalDate().key()) { HashMap() }
            day[name] = (day[name] ?: 0.0) + secondsBetween(start, cut)
            start = cut
        }
        windowDirty = true
    }

    fun windowSeconds(prefix: String): Map<String, Double> {
        val out = HashMap<String, Double>()
        for ((ds, day) in windowDays) if (ds.startsWith(prefix))
            for ((n, s) in day) out[n] = (out[n] ?: 0.0) + s
        for (l in peers()) {
            val days = l.optJSONObject("window") ?: continue
            for (ds in days.keys()) if (ds.startsWith(prefix)) {
                val d = days.optJSONObject(ds) ?: continue
                for (n in d.keys()) out[n] = (out[n] ?: 0.0) + d.optDouble(n, 0.0)
            }
        }
        return out
    }

    fun saveWindows(force: Boolean = false) {
        if (resetting || !(windowDirty || force)) return
        pruneWindows()
        val days = JSONObject()
        for ((ds, day) in windowDays) {
            val o = JSONObject()
            for ((n, s) in day) o.put(n, Math.round(s * 10) / 10.0)
            days.put(ds, o)
        }
        if (Store.write(windowFile, JSONObject().put("days", days))) windowDirty = false
    }

    // ---- 整点记录 ----

    private fun loadHours() {
        hourDays.clear()
        val o = Store.readObj(hourFile)
        if (o != null) {
            val days = o.optJSONObject("days") ?: JSONObject()
            for (ds in days.keys()) {
                val d = days.optJSONObject(ds) ?: continue
                val m = HashMap<String, String>()
                for (h in d.keys()) m[h] = d.optString(h)
                hourDays[ds] = m
            }
            hourCursor = parseIso(o.optString("cursor", ""))
        }
        pruneHours()
    }

    private fun pruneHours() {
        val (a, b) = monthPrefixes()
        hourDays.keys.removeAll { it.take(7) != a && it.take(7) != b }
    }

    fun saveHours() {
        if (resetting) return
        pruneHours()
        val days = JSONObject()
        for ((ds, d) in hourDays) days.put(ds, JSONObject(d as Map<*, *>))
        Store.write(hourFile, JSONObject().put("enabled", hourEnabled)
            .put("cursor", hourCursor?.iso() ?: JSONObject.NULL).put("days", days))
    }

    fun hourActivitySeconds(prefix: String): Map<String, Double> =
        tallyItems(hourDays.filterKeys { it.startsWith(prefix) }.values.flatMap { d -> d.values.map { it to 3600.0 } })

    fun applyHourEnabled(enabled: Boolean) {
        if (enabled == hourEnabled) return
        hourEnabled = enabled
        if (enabled) hourCursor = LocalDateTime.now().floorHour() else promptSlot = null
        saveHours()
    }

    fun hourText(date: String, hour: Int): String = hourDays[date]?.get(hour.toString()) ?: ""

    fun setHourText(date: String, hour: Int, text: String) {
        val d = hourDays.getOrPut(date) { HashMap() }
        if (text.isNotEmpty()) d[hour.toString()] = text else d.remove(hour.toString())
        saveHours()
    }

    /** 超过补填时限还没填写的小时自动记录; 关闭期间的小时最早只补到昨天 23:00. */
    fun finalizeHours() {
        val now = LocalDateTime.now()
        val floor = now.floorHour()
        val today0 = now.floorDay()
        val cur = hourCursor
        if (cur == null) {
            hourCursor = floor
            saveHours()
            return
        }
        var c = if (cur.isBefore(today0.minusHours(1))) today0.minusHours(1) else cur
        if (!hourEnabled) {
            if (c.isBefore(floor)) c = floor
            if (c != cur) { hourCursor = c; saveHours() }
            return
        }
        var changed = c != cur
        while (!c.plusHours(1).plusSec(fillWindow()).isAfter(now)) {
            val ds = c.toLocalDate().key()
            if (hourText(ds, c.hour).isEmpty()) hourDays.getOrPut(ds) { HashMap() }[c.hour.toString()] = autoText()
            c = c.plusHours(1)
            changed = true
        }
        hourCursor = c
        if (changed) saveHours()
    }

    fun awaitingSlot(): LocalDateTime? {
        if (!hourEnabled) return null
        val s = promptSlot ?: return null
        if (!LocalDateTime.now().isBefore(s.plusHours(1).plusSec(fillWindow()))
            || hourText(s.toLocalDate().key(), s.hour).isNotEmpty()) {
            promptSlot = null
            return null
        }
        return s
    }

    /** 设备同步: 子端第一次绑定时, 自己的历史换成母端的. */
    fun clearHistoryForSync() {
        study.clear(); saveStudy()
        focus.clear(); saveFocus()
        windowDays.clear(); saveWindows(force = true)
    }

    /** 重置: 删除本程序留下的全部数据. */
    fun eraseAll() {
        dir.listFiles()?.forEach { it.deleteRecursively() }
    }
}
