#!/usr/bin/env python3
"""Compile every .py file under app/; exit 1 if anything fails to parse.

Also repairs a known stale-sync bug in app/routers/web.py: an erroneous
backslash before the closing quote on /purchase-orders/new redirect lines
(e.g. ...amount\\",) which causes SyntaxError: unterminated string literal.
"""
from __future__ import annotations

import compileall
import sys
from pathlib import Path


def heal_web_redirect_escapes(web_py: Path) -> bool:
    """Return True if the file was modified."""
    text = web_py.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    changed = False
    for line in lines:
        new = line
        if "purchase-orders/new" in new and "project_id" in new:
            if '\\",' in new:
                new = new.replace('\\",', '",')
            if "\\'," in new and "f'" in new:
                new = new.replace("\\',", "',")
        if new != line:
            changed = True
        out.append(new)
    if changed:
        web_py.write_text("".join(out), encoding="utf-8")
    return changed


def verify_orm_mappers(root: Path) -> bool:
    """Catch SQLAlchemy relationship errors (e.g. AmbiguousForeignKeysError)."""
    try:
        from sqlalchemy.orm import configure_mappers
    except ImportError:
        return True
    sys_path0 = str(root)
    if sys_path0 not in sys.path:
        sys.path.insert(0, sys_path0)
    try:
        import app.models.entities  # noqa: F401 — register mapped classes

        configure_mappers()
    except Exception as e:
        print("SQLAlchemy mapper configuration failed:", e, file=sys.stderr)
        return False
    return True


def main() -> None:
    root = Path(__file__).resolve().parent
    web_py = root / "app" / "routers" / "web.py"
    if web_py.is_file() and heal_web_redirect_escapes(web_py):
        print("healed stray \\ before closing quote in", web_py, file=sys.stderr)
    ok = compileall.compile_dir(root / "app", quiet=1)
    if not ok:
        sys.exit(1)
    if not verify_orm_mappers(root):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
