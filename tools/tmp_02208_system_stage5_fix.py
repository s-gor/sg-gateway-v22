from __future__ import annotations

import re
from pathlib import Path


def fix_visual_css() -> None:
    path = Path("app/web/static/sg-system-visual-v1.css")
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r"(?ms)^[ \t]*\.sv1-heading[ \t]*\{[^{}]*\}[ \t]*\n?")
    text, count = pattern.subn("", text)
    if count < 1:
        raise RuntimeError("remaining exact .sv1-heading ownership block not found")
    path.write_text(text, encoding="utf-8")
