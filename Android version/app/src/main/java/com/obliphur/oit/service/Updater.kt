package com.obliphur.oit.service

import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import android.provider.Settings
import androidx.core.content.FileProvider
import com.obliphur.oit.BuildConfig
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/**
 * 从 GitHub 检查 / 下载更新 (MECHANICS 16), 和桌面版 updater.py 同一个仓库, 同一套版本号规则.
 * 安装包取发布里的 .apk 附件; 安装由系统的安装界面完成 (需要用户确认).
 * 走手机本身的网络 (Wi-Fi / 移动数据), 不经过 OIT 自己的 VPN, 所以任何断网方式下都能检查.
 */
class Updater(private val ctx: Context) {
    companion object {
        const val REPO = "Obliphur/Obliphur-s-Integrated-Terminal"
        const val API_LATEST = "https://api.github.com/repos/$REPO/releases/latest"
        const val RELEASES_PAGE = "https://github.com/$REPO/releases"
        val ALLOWED_HOSTS = setOf("api.github.com", "github.com", "codeload.github.com",
            "objects.githubusercontent.com", "release-assets.githubusercontent.com")
        const val MAX_DOWNLOAD = 150L * 1024 * 1024

        fun parseVersion(text: String?): List<Int>? {
            val nums = Regex("\\d+").findAll(text ?: "").map { it.value.toInt() }.take(3).toList()
            if (nums.isEmpty()) return null
            return nums + List(3 - nums.size) { 0 }
        }

        /** 名称里有 "1.2" 这样的版本号就用名称的, 否则用标签的. */
        fun releaseVersion(rel: JSONObject): List<Int>? {
            val name = rel.optString("name")
            val tag = rel.optString("tag_name")
            val vn = parseVersion(name)
            return if (vn != null && Regex("\\d+\\.\\d+").containsMatchIn(name)) vn else parseVersion(tag) ?: vn
        }

        fun newer(a: List<Int>, b: List<Int>): Boolean {
            for (i in 0 until 3) if (a[i] != b[i]) return a[i] > b[i]
            return false
        }

        fun text(v: List<Int>?) = v?.joinToString(".") ?: "?"

        /** 发布里的安卓安装包: 优先名字里带 release / android 的 .apk. */
        fun pickApk(rel: JSONObject): String? {
            val assets = rel.optJSONArray("assets") ?: return null
            val apks = (0 until assets.length()).mapNotNull { assets.optJSONObject(it) }
                .filter { it.optString("name").lowercase().endsWith(".apk") }
            val best = apks.firstOrNull { it.optString("name").lowercase().let { n -> "release" in n || "android" in n } } ?: apks.firstOrNull()
            return best?.optString("browser_download_url")
        }
    }

    /** idle / checking / latest / available / noapk / downloading / ready / error */
    @Volatile var state = "idle"
        private set
    @Volatile var latest: List<Int>? = null
        private set
    @Volatile var error = ""
        private set
    private var release: JSONObject? = null
    private var apk: File? = null
    val current: List<Int> = parseVersion(BuildConfig.VERSION_NAME) ?: listOf(0, 0, 0)
    val latestText get() = text(latest)

    /** 手机本身的网络 (不是 VPN); 找不到就用默认网络. */
    private fun connect(url: URL): HttpURLConnection {
        val cm = ctx.getSystemService(ConnectivityManager::class.java)
        @Suppress("DEPRECATION")
        val net = cm.allNetworks.firstOrNull { n ->
            cm.getNetworkCapabilities(n)?.let {
                !it.hasTransport(NetworkCapabilities.TRANSPORT_VPN) && it.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            } == true
        }
        return (try { net?.openConnection(url) } catch (e: Exception) { null } ?: url.openConnection()) as HttpURLConnection
    }

    /** 只连 GitHub 的 https 地址; 跳转也只能跳到 GitHub. */
    private fun open(start: String, timeoutMs: Int): HttpURLConnection {
        var url = start
        repeat(6) {
            val u = URL(url)
            if (u.protocol != "https" || u.host.lowercase() !in ALLOWED_HOSTS) throw IllegalStateException("only GitHub https addresses are allowed")
            val c = connect(u)
            c.instanceFollowRedirects = false
            c.connectTimeout = timeoutMs
            c.readTimeout = timeoutMs
            c.setRequestProperty("User-Agent", "OIT/${BuildConfig.VERSION_NAME}")
            c.setRequestProperty("Accept", "application/vnd.github+json")
            val code = c.responseCode
            if (code in 300..399) {
                url = URL(u, c.getHeaderField("Location") ?: throw IllegalStateException("HTTP $code")).toString()
                c.disconnect()
                return@repeat
            }
            if (code != 200) { c.disconnect(); throw IllegalStateException("HTTP $code") }
            return c
        }
        throw IllegalStateException("too many redirects")
    }

    fun check(done: () -> Unit) {
        if (state == "checking" || state == "downloading") return
        state = "checking"
        Thread {
            try {
                val c = open(API_LATEST, 20_000)
                val rel = c.inputStream.use { JSONObject(it.readBytes().toString(Charsets.UTF_8)) }
                c.disconnect()
                val v = releaseVersion(rel) ?: throw IllegalStateException("no version number in the release")
                release = rel
                latest = v
                error = ""
                state = when {
                    !newer(v, current) -> "latest"
                    pickApk(rel) == null -> "noapk"
                    else -> "available"
                }
            } catch (e: Exception) {
                error = e.message ?: e.javaClass.simpleName
                state = "error"
            }
            done()
        }.start()
    }

    fun download(done: () -> Unit) {
        val rel = release ?: return
        if (state != "available") return
        val url = pickApk(rel) ?: return
        state = "downloading"
        Thread {
            try {
                val dir = File(ctx.cacheDir, "updates").apply { mkdirs() }
                dir.listFiles()?.forEach { it.delete() }
                val f = File(dir, "OIT-${text(latest)}.apk")
                val c = open(url, 60_000)
                var total = 0L
                c.inputStream.use { inp ->
                    f.outputStream().use { out ->
                        val buf = ByteArray(65536)
                        while (true) {
                            val n = inp.read(buf)
                            if (n < 0) break
                            total += n
                            if (total > MAX_DOWNLOAD) throw IllegalStateException("download too large")
                            out.write(buf, 0, n)
                        }
                    }
                }
                c.disconnect()
                apk = f
                error = ""
                state = "ready"
            } catch (e: Exception) {
                error = e.message ?: e.javaClass.simpleName
                state = "error"
            }
            done()
        }.start()
    }

    /** 打开系统的安装界面. 还没允许 OIT 安装应用时先打开那个设置页. */
    fun install() {
        val f = apk ?: return
        if (!ctx.packageManager.canRequestPackageInstalls()) {
            ctx.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${ctx.packageName}"))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            return
        }
        val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", f)
        ctx.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    fun openReleasePage() {
        ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(RELEASES_PAGE)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }
}
