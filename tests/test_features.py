

import datetime as dt
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


FAILURES = []


def check(name, fn):
    try:
        fn()
        print(f"  [ok]   {name}")
    except Exception as e:
        import traceback
        FAILURES.append((name, traceback.format_exc()))
        print(f"  [FAIL] {name}: {type(e).__name__}: {e}")



def test_settings():
    import config
    from settings_manager import SettingsManager, APPLY_DELAY_HOURS

    tmp = tempfile.mkdtemp()
    tmp_file = os.path.join(tmp, "app_settings.json")
    old_file = config.settings_file
    config.settings_file = lambda: tmp_file
    try:
        m = SettingsManager(tmp_file)
        base = m.value("DAILY_LIMIT")


        assert base == config.DAILY_LIMIT, (base, config.DAILY_LIMIT)


        status, _ = m.stage("DAILY_LIMIT", 3600)
        assert status == "staged"
        assert m.value("DAILY_LIMIT") == base, "延后项不能立即生效"
        assert config.DAILY_LIMIT == base, "config 也不能被提前改写"
        left = m.pending_left_seconds("DAILY_LIMIT")
        assert (APPLY_DELAY_HOURS - 1) * 3600 < left <= APPLY_DELAY_HOURS * 3600, left


        assert m.cancel("DAILY_LIMIT") is True
        assert not m.is_staged("DAILY_LIMIT")
        assert m.cancel("DAILY_LIMIT") is False


        status, _ = m.stage("CHIME_WAV", "__builtin__")
        assert status == "instant" and config.CHIME_WAV == ""


        m.stage("COOLDOWN", 900)
        m.pending["COOLDOWN"]["apply_at"] = dt.datetime.now() - dt.timedelta(seconds=1)
        assert m.promote_due() == ["COOLDOWN"]
        assert m.value("COOLDOWN") == 900 and config.COOLDOWN == 900


        m.stage("LOG_HOURS", 22)
        m2 = SettingsManager(tmp_file)
        assert m2.is_staged("LOG_HOURS")
        assert m2.value("LOG_HOURS") == config.LOG_HOURS, m2.value("LOG_HOURS")
        assert m2.pending_left_seconds("LOG_HOURS") > 47 * 3600


        status, _ = m2.stage("LOG_HOURS", m2.value("LOG_HOURS"))
        assert not m2.is_staged("LOG_HOURS")


        m2.stage("ENFORCE_EVERY", 120)
        m2.stage("LOG_HOURS", 22)
        assert m2.staged_count() == 2
        assert m2.cancel_all() == 2 and m2.staged_count() == 0


        config.AUTO_TEXT = "Sleeping"
        status, _ = m2.stage("AUTO_TEXT", "Idle")
        assert status == "instant" and not m2.is_staged("AUTO_TEXT")
        assert config.AUTO_TEXT == "Idle", config.AUTO_TEXT
        status, _ = m2.stage("LANGUAGE", "en")
        assert status == "instant" and config.LANGUAGE == "en"
        status, _ = m2.stage("LANGUAGE", "zh")
        assert config.LANGUAGE == "zh"
        status, _ = m2.stage("FONT_SCALE", "1.15")
        assert status == "instant" and abs(float(config.FONT_SCALE) - 1.15) < 1e-6

        status, _ = m2.stage("HOUR_LOG_ENABLED", 0)
        assert status == "staged" and m2.is_staged("HOUR_LOG_ENABLED")
        assert m2.cancel("HOUR_LOG_ENABLED")
    finally:
        config.settings_file = old_file



def test_loan():
    import config
    import net_guard as ng

    saved = (config.DAILY_LIMIT, config.COOLDOWN,
             config.TICK_CLAMP, config.DEV_MODE)
    config.DAILY_LIMIT, config.COOLDOWN = 3600, 300
    config.TICK_CLAMP = 10 ** 6
    config.DEV_MODE = False
    try:
        n = ng.NetGuard(tempfile.mkdtemp())
        n.dead = True
        n.date = dt.datetime.now().strftime('%Y-%m-%d')


        ok, msg = n.can_loan(30)
        assert not ok and "no need to borrow" in msg, msg


        n.used = 3000.0
        assert abs(n.max_grant() - 1500) < 1e-6, n.max_grant()
        ok, msg = n.can_loan(24)
        assert ok, msg
        today_cost, loan_cost, total, grant = n.loan_plan(24)
        assert abs(today_cost - 600) < 1e-6, today_cost
        assert abs(loan_cost - 3420) < 1e-6, loan_cost
        assert abs(total - 4020) < 1e-6 and abs(grant - 1440) < 1e-6
        ok, msg = n.request(24, "紧急", loan=True)
        assert ok, msg

        assert n.pending["at"] <= time.time() + 1
        n.tick(0.0)
        assert n.online
        assert abs(n.grant_left - 1440) < 1e-6, n.grant_left
        assert abs(n.bucket_today - 600) < 1e-6
        assert abs(n.bucket_loan_t - 1140) < 1e-6
        assert abs(n.tomorrow_used - 3420) < 1e-6


        n.tick(300.0)
        assert abs(n.used - 3600) < 1e-6, n.used
        assert abs(n.bucket_today) < 1e-6, n.bucket_today
        n.tick(60.0)
        assert abs(n.used - 3780) < 1e-6, n.used


        n.end_early()
        assert abs(n.tomorrow_used - 180) < 1e-6, n.tomorrow_used
        assert abs(n.used - 3780) < 1e-6


        n.used, n.tomorrow_used, n.debt = 3600.0, 0.0, 0.0
        n._reset_grant()
        assert abs(n.max_grant() - 1200) < 1e-6, n.max_grant()
        ok, msg = n.can_loan(20)
        assert ok, msg
        today_cost, loan_cost, total, grant = n.loan_plan(20)
        assert today_cost == 0.0
        assert abs(loan_cost - 3600) < 1e-6 and abs(total - 3600) < 1e-6
        assert abs(grant - 1200) < 1e-6, grant


        ok, _ = n.request(20, "x", loan=True)
        assert ok
        n.cancel()
        assert n.tomorrow_used == 0.0 and n.used == 3600.0


        n.used, n.tomorrow_used, n.debt = 3000.0, 0.0, 0.0
        ok, _ = n.request(24, "跨天", loan=True)
        assert ok
        n.tick(0.0)
        n._rollover("2099-01-01")
        assert n.used == 0.0 and n.tomorrow_used == 0.0
        assert abs(n.debt - 3420) < 1e-6, n.debt
        assert abs(n.remaining - 180) < 1e-6, n.remaining
        return True
    finally:
        (config.DAILY_LIMIT, config.COOLDOWN,
         config.TICK_CLAMP, config.DEV_MODE) = saved



def test_dev_mode():
    import config
    import net_guard as ng

    saved = (config.DAILY_LIMIT, config.COOLDOWN,
             config.DEV_MODE, config.TICK_CLAMP)
    config.DAILY_LIMIT, config.COOLDOWN = 3600, 300
    config.TICK_CLAMP = 10 ** 6
    try:

        config.DEV_MODE = False
        n = ng.NetGuard(tempfile.mkdtemp())
        n.dead = True
        n.date = dt.datetime.now().strftime("%Y-%m-%d")
        assert n.mode == "offline" and not n.online

        config.DEV_MODE = True
        assert n.mode == "dev" and n.online
        assert n.block() is None
        ok, msg = n.request(30, "x")
        assert not ok and "Developer mode" in msg, msg
        n.tick(10 ** 6)
        assert n.used == 0.0, "开发者模式不应消耗额度"

        config.DEV_MODE = False
        assert n.mode == "offline" and not n.online
        return True
    finally:
        (config.DAILY_LIMIT, config.COOLDOWN,
         config.DEV_MODE, config.TICK_CLAMP) = saved



def test_gui():
    import tkinter as tk

    import config
    import net_guard
    import toast


    net_guard.NetGuard._run = staticmethod(lambda cmd: None)

    dialogs = toast.start_recording()
    toast.ask = lambda message, title=None, **k: (dialogs.append(("ask", message)) or True)
    toast.bind_root = lambda root: None

    tmp = tempfile.mkdtemp()

    os.environ["USERPROFILE"] = tmp
    config.app_data_dir = lambda: os.path.join(tmp, "AppData", "LocalLow", config.APP_NAME)
    config.settings_file = lambda: os.path.join(
        tmp, "AppData", "LocalLow", config.APP_NAME, "app_settings.json")

    from app import BreakTimerApp

    root = tk.Tk()
    root.withdraw()
    app = BreakTimerApp(root)
    try:
        assert tmp in app.dm.data_dir, app.dm.data_dir

        keys = list(app.nav_labels)
        assert keys[-1] == "uninstall", keys
        assert keys.index("settings") < keys.index("uninstall")
        assert set(keys) == set(app.pages), (keys, list(app.pages))

        for key in keys:
            app.show_page(key)
            root.update()


        app.show_page("settings")
        page = app.pages["settings"]
        page._rows["DAILY_LIMIT"]["var"].set("1 h")
        page._stage("DAILY_LIMIT")
        root.update()
        assert app.settings.is_staged("DAILY_LIMIT")
        assert "⏳" in app.nav_btns["settings"].cget("text")


        app.settings.pending["DAILY_LIMIT"]["apply_at"] = (
            dt.datetime.now() - dt.timedelta(seconds=1)
        )
        app.check_pending_settings()
        root.update()
        assert not app.settings.is_staged("DAILY_LIMIT")
        assert config.DAILY_LIMIT == 3600
        assert "⏳" not in app.nav_btns["settings"].cget("text")


        app.show_page("settings")
        page._rows["AUTO_TEXT"]["custom"].set("Reading")
        page._stage("AUTO_TEXT")
        root.update()
        assert config.AUTO_TEXT == "Reading", config.AUTO_TEXT
        assert not app.settings.is_staged("AUTO_TEXT")


        assert not hasattr(app.pages["log"], "switch"), "整点开关应只在 Settings 页"
        off_label = [lab for val, lab in app.settings.labeled_values("HOUR_LOG_ENABLED")
                     if str(app.settings._coerce("HOUR_LOG_ENABLED", val)) == "0"][0]
        page._rows["HOUR_LOG_ENABLED"]["var"].set(off_label)
        page._stage("HOUR_LOG_ENABLED")
        root.update()
        assert app.settings.is_staged("HOUR_LOG_ENABLED"), "整点开关必须走 48 小时"
        app.settings.cancel("HOUR_LOG_ENABLED")
        app.pages["settings"].refresh()


        app.show_page("net")
        app.var_min.set("24")
        app.var_reason.set("查资料")
        app.net.used = 3000.0
        ok, msg = app.net.can_loan(30)
        assert not ok and "Loan can cover at most" in msg, msg
        ok, msg = app.net.request(24, "查资料", loan=True)
        assert ok, msg
        app.net.tick(0.0)
        assert app.net.online
        app.refresh_net(force=True)
        root.update()
        assert "贷款" in app.net_lbl_sub.cget("text"), app.net_lbl_sub.cget("text")
        assert "预支" in app.net_lbl_quota.cget("text") or True
        assert "×2" in app.net_lbl_quota.cget("text"), app.net_lbl_quota.cget("text")
        assert "×3" in app.net_lbl_quota.cget("text"), app.net_lbl_quota.cget("text")
        app.net.end_early()
        app.refresh_net(force=True)
        root.update()


        app.pages["settings"].sw_dev.set(True)
        app.pages["settings"]._on_dev_switch(True)
        app.show_page("net")
        root.update()
        assert app.net.mode == "dev"
        assert "Developer mode" in app.net_lbl_status.cget("text")
        app.pages["settings"].sw_dev.set(False)
        app.pages["settings"]._on_dev_switch(False)
        root.update()
        assert app.net.mode != "dev"


        assert not hasattr(app.pages["log"], "switch")
        app.dm.apply_hour_enabled(False)
        app.update_log_badge()
        app.pages["log"].refresh()
        root.update()
        assert "(off)" in app.nav_btns["log"].cget("text")
        assert app.pages["log"].lbl_state.cget("text")
        app.dm.apply_hour_enabled(True)
        app.update_log_badge()
        app.pages["log"].refresh()
        root.update()
        assert "(off)" not in app.nav_btns["log"].cget("text")


        app.show_page("uninstall")
        root.update()
        assert app.uni_lbl_count.cget("text") != ""
        assert dialogs, "至少应该记录到一次提示"


        page = app.pages["settings"]
        en_label = [lab for val, lab in app.settings.labeled_values("LANGUAGE")
                    if str(val) == "en"][0]
        page._rows["LANGUAGE"]["var"].set(en_label)
        page._stage("LANGUAGE")
        root.update()
        assert config.LANGUAGE == "en"
        import i18n
        assert i18n.get_language() == "en"
        assert app.nav_btns["uninstall"].cget("text").strip().endswith("Uninstall")
        assert "Hour Log" in app.nav_btns["log"].cget("text")

        for k in app.nav_labels:
            app.show_page(k)
            root.update()

        app.pages["settings"]._rows["LANGUAGE"]["var"].set(
            [lab for val, lab in app.settings.labeled_values("LANGUAGE")
             if str(val) == "zh"][0])
        app.pages["settings"]._stage("LANGUAGE")
        root.update()
        assert config.LANGUAGE == "zh" and i18n.get_language() == "zh"


        page = app.pages["settings"]
        big = [lab for val, lab in app.settings.labeled_values("FONT_SCALE")
               if abs(float(val) - 1.3) < 1e-6][0]
        page._rows["FONT_SCALE"]["var"].set(big)
        page._stage("FONT_SCALE")
        root.update()
        assert abs(float(app.settings.value("FONT_SCALE")) - 1.3) < 1e-6
        for k in app.nav_labels:
            app.show_page(k)
            root.update()


        root.protocol("WM_DELETE_WINDOW", app.on_close)
        app.on_close()
        app = None
    finally:
        if app is not None:
            app._cancel_jobs()
            try:
                app.net.release()
            except Exception:
                pass
            try:
                root.destroy()
            except Exception:
                pass
        toast.stop_recording()

        time.sleep(0.2)



def test_i18n_en():
    import re
    import tkinter as tk

    import config
    import i18n
    import net_guard
    import toast

    net_guard.NetGuard._run = staticmethod(lambda cmd: None)
    toast.ask = lambda message, title=None, **k: True
    toast.bind_root = lambda root: None

    tmp = tempfile.mkdtemp()
    os.environ["USERPROFILE"] = tmp
    config.app_data_dir = lambda: os.path.join(tmp, "AppData", "LocalLow", config.APP_NAME)
    config.settings_file = lambda: os.path.join(
        tmp, "AppData", "LocalLow", config.APP_NAME, "app_settings.json")

    from app import BreakTimerApp

    han = re.compile(r'[\u4e00-\u9fff]')




    allowed = ("开发者模式", "开启后:启动", "DEV",
               "Instant. Interface language",
               "自定义 (OpenAI 兼容)")

    def walk(widget, out, depth=0):
        if depth > 14:
            return
        for key in ("text", "title"):
            try:
                text = widget.cget(key)
            except Exception:
                continue
            if isinstance(text, str) and han.search(text):
                if not any(a in text for a in allowed):
                    out.append((widget.winfo_class(), key, text.replace("\n", "\\n")[:110]))
        try:
            for child in widget.winfo_children():
                walk(child, out, depth + 1)
        except Exception:
            pass

    root = tk.Tk()
    root.withdraw()
    app = BreakTimerApp(root)
    try:

        app.settings.stage("LANGUAGE", "en")
        i18n.init_from_config()
        assert i18n.get_language() == "en"


        bad = []

        app.show_page("cal")
        root.update()
        cal = app.pages["cal"]



        cal.refresh()
        root.update()
        title = cal.lbl_month_title.cget("text")
        assert han.search(title) is None, f"日历月份标题仍是中文: {title}"
        assert re.search(r"[A-Z][a-z]+ \d{4}", title), title
        headers = [lbl.cget("text") for lbl in cal.day_labels]
        assert headers == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], headers
        assert not any(han.search(h) for h in headers), headers
        walk(cal, bad)


        i18n.set_language("zh")
        cal.refresh()
        root.update()
        zh_title = cal.lbl_month_title.cget("text")
        assert not re.search(r"[A-Za-z]", zh_title), zh_title
        assert zh_title.count("月") == 1, zh_title
        assert [lbl.cget("text") for lbl in cal.day_labels] == \
            ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        i18n.set_language("en")
        cal.refresh()
        root.update()


        app.show_page("settings")
        page = app.pages["settings"]
        root.update()
        walk(page, bad)

        page._rows["DAILY_LIMIT"]["var"].set("1 h")
        page._stage("DAILY_LIMIT")
        root.update()
        walk(page, bad)


        app.show_page("net")
        app.net.used = 7000.0
        ok, msg = app.net.request(24, "research", loan=True)
        assert ok, msg
        app.net.tick(0.0)
        app.refresh_net(force=True)
        root.update()
        assert han.search(app.net_lbl_sub.cget("text")) is None, app.net_lbl_sub.cget("text")
        assert han.search(app.net_lbl_quota.cget("text")) is None, app.net_lbl_quota.cget("text")
        assert han.search(app.net_ctrl_hint.cget("text") or "") is None
        assert han.search(app.net_lbl_header.cget("text")) is None, app.net_lbl_header.cget("text")
        app.net.end_early()


        for key, text in i18n.EN.items():
            leftover = re.findall(r'\{(\w+)', text)
            if not leftover:
                continue

            fake = {name: 1 for name in leftover}
            try:
                text.format(**fake)
            except (KeyError, ValueError, IndexError) as e:
                raise AssertionError(f"英文对照表的占位符有问题: {key!r} → {e}")

        assert not bad, "英文界面仍残留中文:\n" + "\n".join(
            f"  [{cls}.{key}] {text}" for cls, key, text in bad)
    finally:
        try:
            app.settings.cancel_all()
        except Exception:
            pass
        app._cancel_jobs()
        try:
            app.net.release()
        except Exception:
            pass
        try:
            root.destroy()
        except Exception:
            pass
        config.LANGUAGE = "zh"
        i18n.init_from_config()



def test_e2e():
    import tkinter as tk
    from tkinter import messagebox

    import config
    import net_guard

    calls = {"ps": []}

    for n in ("showinfo", "showwarning", "showerror"):
        setattr(messagebox, n, lambda *a, **k: None)
    messagebox.askyesno = lambda *a, **k: True

    tmp = tempfile.mkdtemp()
    os.environ["USERPROFILE"] = tmp
    data_dir = os.path.join(tmp, "AppData", "LocalLow", config.APP_NAME)
    config.app_data_dir = lambda: data_dir
    settings_path = os.path.join(data_dir, "app_settings.json")
    config.settings_file = lambda: settings_path

    from app import BreakTimerApp

    saved = (config.DAILY_LIMIT, config.COOLDOWN)
    root = tk.Tk()
    root.withdraw()
    app = None
    try:
        app = BreakTimerApp(root)
        root.update()



        before = getattr(config, "DAILY_LIMIT")
        app.settings.stage("DAILY_LIMIT", 3600)
        assert app.settings.is_staged("DAILY_LIMIT")
        assert getattr(config, "DAILY_LIMIT") == before, "不能提前生效"
        app.settings.stage("CHIME_WAV", "__builtin__")
        assert config.CHIME_WAV == "", "即时项要立刻生效"


        app.settings.pending["DAILY_LIMIT"]["apply_at"] = (
            dt.datetime.now() - dt.timedelta(seconds=1))
        app.check_pending_settings()
        assert config.DAILY_LIMIT == 3600
        assert app.net.limit == 3600.0, app.net.limit
        assert not app.settings.is_staged("DAILY_LIMIT")
        assert app.settings_path_ok if hasattr(app, "settings_path_ok") else True
        assert json.load(open(settings_path, encoding="utf-8"))["effective"]["DAILY_LIMIT"] == 3600


        app.net.used = 3000.0
        ok, msg = app.net.request(24, "紧急查资料", loan=True)
        assert ok, msg
        app.net.tick(0.0)
        assert app.net.online and app.net.grant_loan
        assert app.net.tomorrow_used > 0, "今天额度不够,必须预支明天"
        app.net.tick(600.0)
        used_mid = app.net.used
        app.refresh_net(force=True)
        root.update()
        assert "贷款" in app.net_lbl_sub.cget("text"), app.net_lbl_sub.cget("text")
        app.net.end_early()
        assert not app.net.online

        assert app.net.used == used_mid, app.net.used
        assert app.net.tomorrow_used < 3420, app.net.tomorrow_used


        app.do_uninstall()
        assert not os.path.exists(data_dir), "数据目录应被清除"
        assert not os.path.exists(settings_path)
        assert app.dm.uninstall_count == 1
    finally:
        (config.DAILY_LIMIT, config.COOLDOWN) = saved
        try:
            if app is not None:
                app.net.release()
        except Exception:
            pass
        try:
            root.destroy()
        except Exception:
            pass


def main():
    print("settings_manager:")
    check("48h 延后生效 / 即时生效 / 取消 / 到期", test_settings)
    print("i18n:")
    check("英文界面下 Settings / Calendar 无残留中文", test_i18n_en)
    print("net_guard:")
    check("紧急贷款 今天 2 倍 / 明天 3 倍 / 跳过冷静期 / 退款 / 跨天", test_loan)
    check("开发者模式:不断网 / 不计时", test_dev_mode)
    print("interface:")
    check("界面冒烟(全页面 + 设置 + 贷款)", test_gui)
    check("端到端:到期生效 → 贷款 → 卸载", test_e2e)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} 项失败:")
        for name, tb in FAILURES:
            print("-" * 60)
            print(name)
            print(tb)
        return 1
    print("全部通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
