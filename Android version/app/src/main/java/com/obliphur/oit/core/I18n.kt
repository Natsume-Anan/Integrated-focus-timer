package com.obliphur.oit.core

/**
 * 界面文字以中文为键, 英文在 [EnStrings.MAP] 里 (同桌面版 i18n.py).
 * 占位符写成 {name}, 由 tr 的参数填入.
 */
object I18n {
    @Volatile
    var lang: String = "zh"
    val isEn get() = lang == "en"
}

fun tr(zh: String, vararg args: Pair<String, Any?>): String {
    var text = if (I18n.isEn) EnStrings.MAP[zh] ?: zh else zh
    for ((k, v) in args) text = text.replace("{$k}", v.toString())
    return text
}
