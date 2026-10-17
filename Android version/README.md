# OIT · Android version

OIT 的 Android 版. 各项功能按照仓库根目录的 `MECHANICS.md` 实现; Android 上做法不同或做不到的地方见 `MECHANICS.md` 第 14 节.

## 平台

| 项目 | 选择 |
| --- | --- |
| 语言 / 界面 | Kotlin + Jetpack Compose (Material 3) |
| 最低系统 | Android 10 (API 29), 目标 API 35 |
| 断网 | `VpnService` (本地 VPN, 不经过任何服务器) |
| 常驻 | 前台服务, 每秒推进一次; 设备睡眠时用闹钟按时叫醒 |
| 应用使用时间 | `UsageStatsManager` |
| 锁定应用 (应用名单) | 使用情况访问 + 显示在其他应用上层 (盖层 + 回到桌面) |
| API Key 加密 | Android Keystore (AES-GCM) |
| 第三方依赖 | 只有 AndroidX / Compose / kotlinx-coroutines |

## 设备同步

Rules 页的 🔗 设备同步可以和同一局域网里的另一台手机或电脑 (桌面版 OIT) 绑定, 共用联网额度, 同步设置 / 计时器状态 / 整点记录 / 统计 (规则页的名单不同步). 两端都要是 Proxy 断网方式. 规则见 `MECHANICS.md` 第 15 节.

## 页面

和桌面版一样: ⏱ 计时器 / 🌐 联网 / 🛡 规则 / 📝 整点记录 / 📅 日历 / 📊 统计 / ⚙ 设置 / 🔄 重置 (英文界面下显示英文), 从左上角 ☰ 打开.

## 构建

需要 JDK 17+ 和 Android SDK (platform 35, build-tools 35).

```bash
cd "Android version"
./gradlew assembleDebug        # 调试版
./gradlew assembleRelease      # 正式版
./gradlew testDebugUnitTest    # 核心逻辑的单元测试
```

没有 `local.properties` 时, 用环境变量 `ANDROID_HOME` 指向 SDK.
安装包在 `app/build/outputs/apk/`.

## 第一次打开

1. 允许通知 (提醒和运行状态都靠通知).
2. 允许 VPN 连接 (断网靠它). 没给权限时页面顶部会一直显示红条.
3. 设置 → 基本设置: 解除电池优化, 防止系统在后台杀掉 OIT.
4. 设置 → 应用: 授予"使用情况访问权限" (应用使用时间统计要用).
5. 设置 → 整点记录: 允许精确闹钟 (整点提示音准点响).

## 代码结构

```
app/src/main/java/com/obliphur/oit/
  core/      和平台无关的机制: 设置与冷静期, 名单, 额度, 计时器, 数据文件, 英文文字
  service/   VPN (断网 / DNS 过滤), 前台服务, 通知, 闹钟, 提示音, 前台应用
  ai/        AI 名单建议
  ui/        Compose 页面
```

`core/EnStrings.kt` 由脚本从桌面版 `i18n.py` 的译文和新增的译文生成; 新增界面文字时把中文原文写进 `tr("…")`, 再补上英文.
