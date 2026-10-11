
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = [
    "main.py", "app.py", "config.py", "net_guard.py", "data_manager.py",
    "settings_manager.py",
    "pages/__init__.py", "pages/widgets.py", "pages/calendar_page.py",
    "pages/hour_log_page.py", "pages/settings_page.py",
    "tests/test_features.py", "tests/check_names.py", "tests/check_i18n.py",
]


def check(path):
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src, path)
    imported = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imported[(a.asname or a.name.split(".")[0])] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name == "*":
                    continue
                imported[(a.asname or a.name)] = node.lineno
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            pass

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            cur = node
            while isinstance(cur, ast.Attribute):
                cur = cur.value
            if isinstance(cur, ast.Name):
                used.add(cur.id)
    out = []
    for name, lineno in sorted(imported.items(), key=lambda kv: kv[1]):
        if name not in used and name not in src.split("import")[0]:
            out.append(f"  {path}:{lineno}: 未使用的导入 `{name}`")
    return out


def main():
    problems = []
    for rel in FILES:
        p = os.path.join(ROOT, rel)
        if os.path.exists(p):
            problems += check(p)
    print("\n".join(problems) if problems else "没有发现未使用的导入 ✓")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
