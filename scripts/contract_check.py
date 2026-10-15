#!/usr/bin/env python3
"""contract_check.py — verify frontend/backend API route agreement (stdlib only).

Compares:
  1. ROUTES KNOWN = master-contract route list (CONTRACT_ROUTES below)
                   + routes actually parsed from backend code
                     (ast-parse of backend/api/*.py and backend/main.py for
                      @router.get/post/put/delete/patch(...) decorators)
  2. ROUTES CALLED = "/api/..." paths grepped from frontend source
                     (fetch("/api/..."), axios.*, api.ts wrappers;
                      skips node_modules, .next, build output)

Prints three lists:
  MATCHED        frontend calls a known route (method+path)
  BACKEND-ONLY   known route (contract or backend code) with no frontend caller
  FRONTEND-ONLY  frontend calls a path that is neither in the contract nor in backend code

Path params are normalized: {id}, ${id}, :id  ->  {}

Exit 0 always (mismatches are expected while backend/frontend are built in
parallel); CI may gate on FRONTEND-ONLY separately if desired.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BACKEND = REPO / "backend"
FRONTEND = REPO / "frontend"

# ----------------------------------------------------------------------------
# 1. Master-contract routes (method, path). Source: platform contract.
# ----------------------------------------------------------------------------
CONTRACT_ROUTES = [
    ("GET", "/api/health"),
    ("GET", "/api/ready"),
    ("GET", "/api/auth/me"),
    ("POST", "/api/videos/upload"),
    ("GET", "/api/videos"),
    ("GET", "/api/videos/{id}"),
    ("DELETE", "/api/videos/{id}"),
    ("GET", "/api/jobs/{id}"),
    ("GET", "/api/jobs/{id}/stream"),
    ("GET", "/api/results/{job_id}"),
    ("POST", "/api/feedback"),
    ("POST", "/api/reports/bug"),
    ("POST", "/api/reports/feature"),
    ("GET", "/api/admin/overview"),
    ("GET", "/api/admin/jobs"),
    ("GET", "/api/admin/providers"),
    ("GET", "/api/admin/feedback"),
    ("GET", "/api/admin/analytics"),
    ("GET", "/api/admin/errors"),
    ("POST", "/api/workers/register"),
    ("POST", "/api/workers/{id}/heartbeat"),
    ("GET", "/api/workers/tasks/next"),
]

HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}


def canon(path: str) -> str:
    """Normalize path params: {id}, ${id}, :id -> {} ; strip trailing slash."""
    path = re.sub(r"\$\{[^}]*\}", "{}", path)
    path = re.sub(r"\$\{[^}]*$", "{}", path)  # unclosed trailing interpolation
    path = re.sub(r"(?<!/)\{\}$", "", path)  # bare trailing {} from a nested template
    path = re.sub(r"\{[^}]*\}", "{}", path)
    path = re.sub(r":[A-Za-z_][A-Za-z0-9_]*", "{}", path)
    path = path.split("?")[0].split("#")[0]
    path = path.rstrip(".")  # trailing sentence period from comments
    if len(path) > 1:
        path = path.rstrip("/")
    return path


# ----------------------------------------------------------------------------
# 2. Parse backend routes via ast
# ----------------------------------------------------------------------------
def parse_backend_routes() -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    py_files = list((BACKEND / "api").glob("*.py")) if (BACKEND / "api").is_dir() else []
    main_py = BACKEND / "main.py"
    if main_py.is_file():
        py_files.append(main_py)

    for f in py_files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, OSError):
            continue
        # collect APIRouter(prefix=...) / include_router(..., prefix=...) per file
        prefixes: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                tgt = node.targets[0]
                if isinstance(tgt, ast.Name) and isinstance(node.value, ast.Call):
                    func = node.value.func
                    fname = getattr(func, "attr", None) or getattr(func, "id", "")
                    if fname in ("APIRouter", "FastAPI"):
                        for kw in node.value.keywords:
                            if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                                prefixes[tgt.id] = str(kw.value.value)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call):
                    continue
                func = dec.func
                if not isinstance(func, ast.Attribute):
                    continue
                method = func.attr.lower()
                if method not in HTTP_METHODS:
                    continue
                if not dec.args or not isinstance(dec.args[0], ast.Constant):
                    continue
                raw_path = str(dec.args[0].value)
                router_name = func.value.id if isinstance(func.value, ast.Name) else ""
                prefix = prefixes.get(router_name, "")
                # include_router prefix on app: try module-level include_router calls
                routes.add((method.upper(), canon(prefix + raw_path)))
        # include_router(app-level) prefixes: app.include_router(x, prefix="/api/y")
        for node in ast.walk(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                func = node.value.func
                if isinstance(func, ast.Attribute) and func.attr == "include_router":
                    for kw in node.value.keywords:
                        if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                            pre = str(kw.value.value)
                            # re-prefix routes found without prefix in this file
                            extra = {
                                (m, canon(pre + p)) for (m, p) in routes
                                if not p.startswith(canon(pre))
                            }
                            routes |= extra
    return {(m, p) for (m, p) in routes if p.startswith("/api")}


# ----------------------------------------------------------------------------
# 3. Grep frontend for /api/... calls
# ----------------------------------------------------------------------------
FRONTEND_EXTS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
SKIP_DIRS = {"node_modules", ".next", "dist", "build", "out", ".git"}
# Lookbehind excludes file paths in comments (backend/api/...) — the char
# before /api/ must not be a word char, slash, dot, or dash.
API_RE = re.compile(r"(?<![A-Za-z0-9_./-])/api/(?:\$\{[^}]*\}|[A-Za-z0-9_\-\./\{\}:$])+")
# Trailing unclosed interpolation (e.g. `/api/admin/jobs${status`) -> {}.


def parse_frontend_calls() -> set[str]:
    calls: set[str] = set()
    if not FRONTEND.is_dir():
        return calls
    for f in FRONTEND.rglob("*"):
        if not f.is_file() or f.suffix not in FRONTEND_EXTS:
            continue
        if any(part in SKIP_DIRS for part in f.parts):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in API_RE.finditer(text):
            calls.add(canon(m.group(0)))
    return calls


# ----------------------------------------------------------------------------
# 4. Compare & report
# ----------------------------------------------------------------------------
def main() -> None:
    backend_routes = parse_backend_routes()
    contract_set = {(m.upper(), canon(p)) for (m, p) in CONTRACT_ROUTES}
    known = contract_set | backend_routes
    known_paths = {p for (_, p) in known}
    backend_only_paths = {p for (_, p) in backend_routes}
    calls = parse_frontend_calls()

    matched, backend_only, frontend_only = [], [], []
    for path in sorted(known_paths):
        methods = sorted({m for (m, p) in known if p == path})
        src = "backend+contract" if path in backend_only_paths and any(
            p == path for (_, p) in contract_set) else (
            "backend" if path in backend_only_paths else "contract")
        entry = f"{'/'.join(methods):22s} {path}   [{src}]"
        if path in calls:
            matched.append(entry)
        else:
            backend_only.append(entry)
    for path in sorted(calls - known_paths):
        frontend_only.append(path)

    print("=" * 70)
    print(f"MATCHED ({len(matched)}): frontend calls a known route")
    print("=" * 70)
    print("\n".join(matched) if matched else "  (none)")
    print()
    print("=" * 70)
    print(f"BACKEND-ONLY ({len(backend_only)}): known route, no frontend caller found")
    print("=" * 70)
    print("\n".join(backend_only) if backend_only else "  (none)")
    print()
    print("=" * 70)
    print(f"FRONTEND-ONLY ({len(frontend_only)}): frontend calls unknown route")
    print("=" * 70)
    print("\n".join(frontend_only) if frontend_only else "  (none)")
    print()
    print(f"[info] backend code parsed: {len(backend_routes)} routes; "
          f"contract: {len(contract_set)} routes; frontend calls: {len(calls)} paths.")


if __name__ == "__main__":
    main()
