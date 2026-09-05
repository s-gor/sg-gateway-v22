from __future__ import annotations

from contextlib import contextmanager
from threading import Thread
from typing import Iterator

from flask import Flask
from playwright.sync_api import Page
from werkzeug.serving import make_server


@contextmanager
def serve_app(app: Flask) -> Iterator[str]:
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def login_panel(page: Page, base_url: str, *, password: str) -> None:
    response = page.goto(f"{base_url}/login", wait_until="domcontentloaded")
    assert response is not None and response.ok
    page.locator('input[name="password"]').fill(password)
    page.locator('form[action="/login"] button[type="submit"]').click()
    page.wait_for_url(f"{base_url}/**")


def set_theme(page: Page, theme: str) -> None:
    assert theme in {"dark", "light"}
    page.evaluate(
        """theme => {
          localStorage.setItem('sg-gateway-theme', theme);
          document.documentElement.dataset.theme = theme;
        }""",
        theme,
    )


def rect(page: Page, selector: str) -> dict[str, float]:
    locator = page.locator(selector).first
    locator.wait_for(state="visible")
    box = locator.bounding_box()
    assert box is not None, f"element has no layout box: {selector}"
    return {key: float(box[key]) for key in ("x", "y", "width", "height")}
