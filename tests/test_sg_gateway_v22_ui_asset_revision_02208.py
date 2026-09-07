from __future__ import annotations

from pathlib import Path

from flask import Flask

from app.web.assets import frontend_asset_revision, static_asset


def _write(root: Path, name: str, content: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_frontend_asset_revision_is_deterministic_and_content_derived(tmp_path):
    _write(tmp_path, "a.css", "body { color: red; }\n")
    _write(tmp_path, "nested/b.js", "console.log('b');\n")
    _write(tmp_path, "ignored.txt", "one\n")

    first = frontend_asset_revision(tmp_path)
    second = frontend_asset_revision(tmp_path)

    assert first == second
    assert len(first) == 16
    assert all(char in "0123456789abcdef" for char in first)

    _write(tmp_path, "ignored.txt", "two\n")
    assert frontend_asset_revision(tmp_path) == first

    _write(tmp_path, "a.css", "body { color: blue; }\n")
    assert frontend_asset_revision(tmp_path) != first


def test_frontend_asset_revision_depends_on_relative_path_as_well_as_bytes(tmp_path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    _write(left, "a.css", "same\n")
    _write(right, "b.css", "same\n")

    assert frontend_asset_revision(left) != frontend_asset_revision(right)


def test_static_asset_uses_one_shared_revision_query_parameter(tmp_path):
    static_root = tmp_path / "static"
    _write(static_root, "app.css", "body{}\n")

    app = Flask(__name__, static_folder=str(static_root), static_url_path="/static")
    with app.test_request_context("/"):
        url = static_asset("app.css", static_root=static_root)

    assert url == f"/static/app.css?v={frontend_asset_revision(static_root)}"
