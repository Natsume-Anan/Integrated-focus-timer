
import ast
import builtins
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = [
    "main.py", "app.py", "config.py", "net_guard.py", "data_manager.py",
    "settings_manager.py",
    "pages/__init__.py", "pages/widgets.py", "pages/calendar_page.py",
    "pages/hour_log_page.py", "pages/settings_page.py",
]

BUILTINS = set(dir(builtins)) | {
    "__file__", "__name__", "__doc__", "__package__", "__spec__", "__loader__",
    "WindowsError", "self", "cls", "staticmethod", "classmethod", "property",
}


def bound_names(node, acc):
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del)):
            acc.add(child.id)
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            acc.add(child.name)
            args = getattr(child, "args", None)
            if args:
                for a in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs):
                    acc.add(a.arg)
                if args.vararg:
                    acc.add(args.vararg.arg)
                if args.kwarg:
                    acc.add(args.kwarg.arg)
        elif isinstance(child, ast.Import):
            for a in child.names:
                acc.add((a.asname or a.name).split(".")[0])
        elif isinstance(child, ast.ImportFrom):
            for a in child.names:
                acc.add(a.asname or a.name)
        elif isinstance(child, ast.ExceptHandler) and child.name:
            acc.add(child.name)
        elif isinstance(child, ast.comprehension):
            for t in ast.walk(child.target):
                if isinstance(t, ast.Name):
                    acc.add(t.id)


def check(path):
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src, path)
    module_names = set()
    bound_names(tree, module_names)
    problems = []

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.stack = [set()]

        def _push(self, node):
            local = set()
            bound_names(node, local) if False else None

            for stmt in getattr(node, "body", []):
                for t in ast.walk(stmt):
                    if isinstance(t, ast.Name) and isinstance(t.ctx, ast.Store):
                        local.add(t.id)
                    elif isinstance(t, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        local.add(t.name)
                    elif isinstance(t, ast.Import):
                        for a in t.names:
                            local.add((a.asname or a.name).split(".")[0])
                    elif isinstance(t, ast.ImportFrom):
                        for a in t.names:
                            local.add(a.asname or a.name)
                    elif isinstance(t, ast.ExceptHandler) and t.name:
                        local.add(t.name)
                    elif isinstance(t, (ast.For, ast.AsyncFor)):
                        for n in ast.walk(t.target):
                            if isinstance(n, ast.Name):
                                local.add(n.id)
                    elif isinstance(t, (ast.With, ast.AsyncWith)):
                        for item in t.items:
                            if item.optional_vars is not None:
                                for n in ast.walk(item.optional_vars):
                                    if isinstance(n, ast.Name):
                                        local.add(n.id)
                    elif isinstance(t, ast.comprehension):
                        for n in ast.walk(t.target):
                            if isinstance(n, ast.Name):
                                local.add(n.id)
                self.stack[-1] |= local
            self.stack.append(set())
            for a in getattr(node, "args", None) and (
                list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs)
            ) or []:
                self.stack[-1].add(a.arg)
            if getattr(node, "args", None) and node.args.vararg:
                self.stack[-1].add(node.args.vararg.arg)
            if getattr(node, "args", None) and node.args.kwarg:
                self.stack[-1].add(node.args.kwarg.arg)
            for stmt in getattr(node, "body", []):
                self.visit(stmt)
            self.stack.pop()

        def visit_FunctionDef(self, node):
            self.visit(node.args)
            self._push(node)

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, node):
            self._push(node)

        def visit_Name(self, node):
            if not isinstance(node.ctx, ast.Load):
                return
            name = node.id
            if name in BUILTINS or name in module_names:
                return
            for scope in reversed(self.stack):
                if name in scope:
                    return
            problems.append((node.lineno, name))

    Visitor().visit(tree)
    seen = set()
    out = []
    for lineno, name in problems:
        key = (lineno, name)
        if key in seen:
            continue
        seen.add(key)
        out.append(f"  {path}:{lineno}: 可能是未定义的名字 `{name}`")
    return out


def main():
    all_problems = []
    for rel in FILES:
        p = os.path.join(ROOT, rel)
        if os.path.exists(p):
            all_problems += check(p)
    if all_problems:
        print("\n".join(all_problems))
        return 1
    print("未发现可疑的未定义名字 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
