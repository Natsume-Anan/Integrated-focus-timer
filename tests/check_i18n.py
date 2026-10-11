

import ast
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import i18n

HAN = re.compile(r'[\u4e00-\u9fff]')


EN_VALUE_ALLOWED = (
    "中文",
    "Instant. Interface language",
)





EN_KEY_ALLOWED = (
    "⏱  Timer", "🌐  Network", "🛡  Rules", "📝  Hour Log",
    "📅  Calendar", "⚙  Settings", "🗑  Uninstall",
    "⏱  Focus Timer",
    "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun",
    "API Key", "Base URL", "WAV 音频",
    "hosts: {err}",
)

FILES = [
    "app.py", "net_guard.py", "data_manager.py",
    "settings_manager.py", "config.py", "toast.py",
    "pages/widgets.py", "pages/calendar_page.py", "pages/hour_log_page.py",
    "pages/settings_page.py",
]



ALLOWED = {

    "app.py": ("开发者模式已开启:本程序不会断网",),


    "net_guard.py": ("__selftest__",),
    "settings_manager.py": ("__selftest__",),

    "pages/calendar_page.py": ("1 月", "2 月", "3 月", "4 月", "5 月", "6 月",
                               "7 月", "8 月", "9 月", "10 月", "11 月", "12 月"),
}


SKIP_FUNCS = {"_selftest", "_log_notice", "_log_report"}


def _docstring_ids(tree):
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) \
               and isinstance(body[0].value, ast.Constant) \
               and isinstance(body[0].value.value, str):
                out.add(id(body[0].value))
    return out


def _owners(tree):
    owner = {}

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.stack = []

        def visit_FunctionDef(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Constant(self, node):
            if isinstance(node.value, str):
                owner[id(node)] = self.stack[-1] if self.stack else "<module>"

    Visitor().visit(tree)
    return owner


def check(path, rel):
    src = io.open(path, encoding="utf-8").read()
    try:
        tree = ast.parse(src, path)
    except SyntaxError as e:
        return [f"  {rel}: 语法错误 {e}"], 0

    docs = _docstring_ids(tree)
    owner = _owners(tree)
    allow = ALLOWED.get(rel, ())


    tr_args = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
           and node.func.id == "tr":
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    tr_args.add(id(arg))


    joined = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    joined.add(id(sub))
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            for side in (node.left, node.right):
                if isinstance(side, ast.Constant) and isinstance(side.value, str):
                    joined.add(id(side))


    en_norm = {re.sub(r'\s+', '', k) for k in i18n.EN}

    problems, ok = [], 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        text = node.value
        if not HAN.search(text) or id(node) in docs:
            continue
        if any(a in text for a in allow):
            continue
        func = owner.get(id(node), "<module>")
        if func in SKIP_FUNCS:
            continue
        if id(node) in tr_args:
            ok += 1
            continue
        if re.sub(r'\s+', '', text) in en_norm:
            ok += 1
            continue
        kind = ("拼接/f-string 里的中文(整句进不了对照表)"
                if id(node) in joined else "未使用 tr()")
        one = text.replace("\n", "\\n")
        if len(one) > 90:
            one = one[:90] + " …"
        problems.append(f"  {rel}:{node.lineno}: [{kind}] {func}(): {one}")
    return problems, ok


def check_table():
    problems = []
    for key, value in i18n.EN.items():

        if HAN.search(value) and not any(a in value for a in EN_VALUE_ALLOWED):
            one = value.replace("\n", "\\n")
            problems.append(f"  i18n.EN[{key!r}] 的中文译文里含中文: {one[:70]}")

        if not HAN.search(key):
            has_ascii_word = re.search(r'[A-Za-z]{3,}', key)
            if has_ascii_word and not any(key == a for a in EN_KEY_ALLOWED):
                problems.append(
                    f"  i18n.EN 的键 {key!r} 不含中文 —— 对照表的键必须是中文原文"
                    "(很可能把方向写反了)")
    return problems


def main():
    verbose = "-v" in sys.argv
    all_problems, total_ok = [], 0
    all_problems += check_table()
    for rel in FILES:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue
        problems, ok = check(path, rel)
        all_problems += problems
        total_ok += ok

    if verbose:
        print(f"对照表键值对: {len(i18n.EN)} 条")
        print(f"已正确使用 tr() / 已进对照表的中文字面量: {total_ok} 条")
    if all_problems:
        print("发现 i18n 问题:")
        print("\n".join(all_problems))
        print()
        print("提示:整句请先交给 tr() 再 .format(...);带数值的中文模板"
              "必须写进 i18n.EN 的键里,不要在源码里先拼好整句。")
        return 1
    print(f"i18n 静态检查通过 ✓(共核对 {total_ok} 条中文文案)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
