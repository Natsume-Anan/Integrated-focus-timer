package com.obliphur.oit.ui

import android.Manifest
import android.content.Intent
import android.net.VpnService
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Snackbar
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.obliphur.oit.OitApp
import com.obliphur.oit.core.tr
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private val app get() = OitApp.instance
    private val pageRequest = MutableStateFlow<String?>(null)

    private val vpnLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        app.applyNet(true)
    }
    private val notifLauncher = registerForActivityResult(ActivityResultContracts.RequestPermission()) {}

    fun requestVpn() {
        val i = VpnService.prepare(this)
        if (i != null) vpnLauncher.launch(i) else app.applyNet(true)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        com.obliphur.oit.service.CoreService.start(this)
        if (Build.VERSION.SDK_INT >= 33) notifLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        if (savedInstanceState == null && !app.core.settings.devMode && VpnService.prepare(this) != null) requestVpn()
        // 每次打开应用时检查更新 (MECHANICS 16)
        if (savedInstanceState == null) app.checkUpdateOnOpen()
        pageRequest.value = intent?.getStringExtra("page")
        setContent { Root(this, pageRequest) }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        intent.getStringExtra("page")?.let { pageRequest.value = it }
    }

    /** 有人在操作本机 (设备同步: 整点提示音只在最后操作的设备上响). */
    override fun onUserInteraction() {
        super.onUserInteraction()
        app.core.lastOp = System.currentTimeMillis()
    }

    override fun onResume() {
        super.onResume()
        app.foreground = true
        app.core.tick()
        if (app.updateRetry && app.core.settings.bool("UPDATE_CHECK")) {
            app.updateRetry = false
            app.checkUpdate(auto = true)
        }
    }

    override fun onPause() {
        app.foreground = false
        app.core.saveAll()
        super.onPause()
    }
}

val PAGES = listOf(
    "timer" to "⏱  Timer", "net" to "🌐  Network", "rules" to "🛡  Rules", "log" to "📝  Hour Log",
    "cal" to "📅  Calendar", "stats" to "📊  Statistics", "settings" to "⚙  Settings", "reset" to "🔄  Reset",
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun Root(act: MainActivity, pageRequest: MutableStateFlow<String?>) {
    val app = OitApp.instance
    val v by app.version.collectAsState()
    val notices by app.notices.collectAsState()
    val core = app.core
    val theme = core.settings.str("THEME")
    val fs = core.settings.str("FONT_SCALE").toFloatOrNull() ?: 1f
    var page by rememberSaveable { mutableStateOf("timer") }
    var settingsTab by rememberSaveable { mutableStateOf("basic") }
    val drawer = rememberDrawerState(DrawerValue.Closed)
    val scope = rememberCoroutineScope()
    val snack = remember { SnackbarHostState() }
    var snackKind by remember { mutableStateOf("info") }
    val req by pageRequest.collectAsState()

    fun go(p: String) {
        val parts = p.split(":")
        page = parts[0]
        if (parts.size > 1) settingsTab = parts[1]
    }
    LaunchedEffect(req) { req?.let { go(it); pageRequest.value = null } }
    LaunchedEffect(Unit) { app.navRequests.collect { go(it) } }
    LaunchedEffect(Unit) {
        app.toasts.collect {
            snackKind = it.kind
            launch { snack.showSnackbar(it.text, duration = if (it.long) SnackbarDuration.Long else SnackbarDuration.Short) }
        }
    }

    OitTheme(theme, fs) {
        CompositionLocalProvider(LocalTick provides v) {
            val o = LocalOit.current
            fun navLabel(key: String, base: String): String = when (key) {
                "log" -> if (!core.dm.hourEnabled) "$base  (off)" else base + if (core.dm.awaitingSlot() != null) " ●" else ""
                "settings" -> base + (if (core.settings.pending.isNotEmpty()) "  ⏳${core.settings.pending.size}" else "") +
                    (if (core.settings.devMode) "  🛠" else "")
                else -> base
            }
            ModalNavigationDrawer(drawerState = drawer, drawerContent = {
                ModalDrawerSheet(drawerContainerColor = o.card) {
                    Text("OIT", fontWeight = FontWeight.Bold, fontSize = 20.sp, color = o.text,
                        modifier = Modifier.padding(20.dp))
                    HorizontalDivider(color = o.border)
                    Spacer(Modifier.height(8.dp))
                    for ((key, label) in PAGES) {
                        val on = key == page
                        Text(navLabel(key, tr(label)), color = if (on) o.accent else o.text, fontSize = 16.sp,
                            fontWeight = if (on) FontWeight.Bold else FontWeight.Normal,
                            modifier = Modifier.fillMaxWidth().clickable {
                                page = key; scope.launch { drawer.close() }
                            }.padding(horizontal = 24.dp, vertical = 14.dp))
                    }
                }
            }) {
                Scaffold(
                    containerColor = o.bg,
                    topBar = {
                        TopAppBar(
                            title = { Text(navLabel(page, tr(PAGES.first { it.first == page }.second))) },
                            navigationIcon = {
                                TextButton({ scope.launch { drawer.open() } }) { Text("☰", fontSize = 22.sp, color = o.text) }
                            },
                            colors = TopAppBarDefaults.topAppBarColors(containerColor = o.bg, titleContentColor = o.text),
                        )
                    },
                    snackbarHost = {
                        SnackbarHost(snack) { d ->
                            val c = when (snackKind) { "success" -> o.success; "warn" -> o.warn; else -> o.accent }
                            Snackbar(d, containerColor = o.card, contentColor = o.text, actionColor = c,
                                shape = RoundedCornerShape(8.dp), modifier = Modifier.padding(8.dp))
                        }
                    },
                ) { pad ->
                    Column(Modifier.padding(pad).fillMaxSize()) {
                        if (app.vpnNeedsPermission && !core.settings.devMode) {
                            Row(Modifier.fillMaxWidth().background(o.dangerBg).padding(horizontal = 16.dp, vertical = 8.dp),
                                verticalAlignment = Alignment.CenterVertically) {
                                Text(tr("断网功能已停止"), color = o.danger, modifier = Modifier.weight(1f))
                                DangerButton(tr("授予 VPN 权限")) { act.requestVpn() }
                            }
                        } else if (com.obliphur.oit.service.OitVpnService.leak && !core.settings.devMode) {
                            Row(Modifier.fillMaxWidth().background(o.dangerBg).padding(horizontal = 16.dp, vertical = 8.dp),
                                verticalAlignment = Alignment.CenterVertically) {
                                Text(tr("断网未生效"), color = o.danger, modifier = Modifier.weight(1f))
                                DangerButton(tr("重新建立 VPN")) { com.obliphur.oit.service.OitVpnService.rebuild(act) }
                            }
                        }
                        val scroll = rememberScrollState()
                        val scrollable = page != "log" && page != "stats"
                        Column(if (scrollable) Modifier.verticalScroll(scroll) else Modifier.fillMaxSize()) {
                            when (page) {
                                "timer" -> TimerScreen()
                                "net" -> NetScreen()
                                "rules" -> RulesScreen { go(it) }
                                "log" -> HourLogScreen { go(it) }
                                "cal" -> CalendarScreen()
                                "stats" -> StatsScreen()
                                "settings" -> SettingsScreen(settingsTab, { settingsTab = it }, act)
                                "reset" -> ResetScreen()
                            }
                        }
                    }
                }
            }
            notices.firstOrNull()?.let { n ->
                AlertDialog(
                    onDismissRequest = { core.closeNotice(n.id, null) },
                    title = { Text(n.title) },
                    text = { Text(n.message) },
                    confirmButton = {
                        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            for (b in n.buttons.sortedBy { it.primary }) {
                                TextButton({
                                    core.closeNotice(n.id, b.action)
                                    n.page?.let { p -> if (b.action != "ok") go(p) }
                                }) { Text(b.label, color = if (b.primary) o.accent else o.dim) }
                            }
                        }
                    },
                    containerColor = o.bg,
                )
            }
        }
    }
}
