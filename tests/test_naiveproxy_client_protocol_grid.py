from __future__ import annotations

import re

from flask import Response

import app.naiveproxy.http as naive_http


_PROTOCOLS = (
    "xray",
    "hysteria2",
    "tuic",
    "mieru",
    "mihomo",
    "singbox",
    "shadowsocks",
    "trojan",
)


def _picker(css_class: str, *, include_naiveproxy: bool) -> str:
    card_class = "dv16-protocol" if css_class == "dv16-protocol-list" else "cv10-protocol"
    values = list(_PROTOCOLS)
    if include_naiveproxy:
        values.append("naiveproxy")
    options = "".join(
        f'<label class="{card_class}"><input type="checkbox" name="protocols" '
        f'value="{value}"><span><strong>{value}</strong></span></label>'
        for value in values
    )
    return f'<fieldset class="{css_class}">{options}</fieldset>'


def _values(fieldset: str) -> list[str]:
    return re.findall(r'name="protocols"[^>]*value="([^"]+)"', fieldset)


def test_naiveproxy_protocol_picker_grid_is_exactly_3x3_without_duplicates(monkeypatch):
    monkeypatch.setattr(
        naive_http,
        "tls_overview",
        lambda: {"https_ready": True},
    )

    source = (
        '<form name="client-edit">'
        + _picker("cv10-protocols", include_naiveproxy=False)
        + _picker("dv16-protocol-list", include_naiveproxy=True)
        + "</form>"
    )
    response = Response(source, mimetype="text/html")

    updated = naive_http._inject_naiveproxy_protocol_option(response).get_data(as_text=True)
    fieldsets = re.findall(
        r'<fieldset\b[^>]*class="[^"]*(?:cv10-protocols|dv16-protocol-list)[^"]*"[^>]*>'
        r'.*?</fieldset>',
        updated,
        flags=re.DOTALL,
    )

    assert len(fieldsets) == 2
    for fieldset in fieldsets:
        values = _values(fieldset)
        assert len(values) == 9
        assert values.count("naiveproxy") == 1
