from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
import qrcode
import qrcode.image.svg

from app.clients.qr import build_qr_svg


ROOT = Path(__file__).resolve().parents[1]
SVG = "{http://www.w3.org/2000/svg}"


def _texts(svg: str) -> list[str]:
    root = ET.fromstring(svg)
    return ["".join(item.itertext()) for item in root.findall(f"{SVG}text")]


def _raw_qr_svg(payload: str) -> str:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=2,
    )
    qr.add_data(payload, optimize=0)
    qr.make(fit=True)
    image = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    buffer = BytesIO()
    image.save(buffer)
    return buffer.getvalue().decode("utf-8")


def test_subscription_qr_has_two_line_caption_by_default() -> None:
    svg = build_qr_svg("https://vpn.example/sub/token")
    assert _texts(svg) == ["SG · ПОДПИСКА", "Все назначенные профили"]


def test_subscription_qr_can_omit_embedded_caption() -> None:
    svg = build_qr_svg(
        "https://vpn.example/sub/token",
        include_caption=False,
    )
    root = ET.fromstring(svg)
    view_box = [float(value) for value in root.attrib["viewBox"].split()]

    assert _texts(svg) == []
    assert view_box[3] == view_box[2]
    assert root.find(f"{SVG}rect") is None


def test_subscription_endpoints_request_captionless_qr() -> None:
    source = (
        ROOT / "app/clients/sg_subscription_http_v4.py"
    ).read_text(encoding="utf-8")

    assert "build_qr_svg(url, include_caption=False)" in source


def test_subscription_qr_modals_have_distinct_top_titles() -> None:
    template = (
        ROOT / "app/web/templates/_sg_subscription_dual.html"
    ).read_text(encoding="utf-8")

    assert template.count('class="sg-smart-qr-meta"') == 2
    assert """<strong>Универсальная подписка</strong>
              <small>Сканируйте в приложении</small>""" in template
    assert """<strong>SG подписка</strong>
              <small>Сканируйте в приложении</small>""" in template


@pytest.mark.parametrize(
    ("payload", "profile_name"),
    [
        ("# SG-Gateway AmneziaWG\n[Interface]\n", "AmneziaWG 2.0"),
        ("# SG-Gateway AmneziaWG 3.0\n[Interface]\n", "AmneziaWG 3.0"),
        ("awg31://import/v1/example", "AmneziaWG 3.1"),
        (
            "vless://id@example.com:443?type=tcp&security=reality#test",
            "VLESS Reality TCP",
        ),
        (
            "vless://id@example.com:443?type=xhttp&security=reality#test",
            "VLESS XHTTP Reality",
        ),
        (
            "vless://id@example.com:443?type=xhttp&security=tls#test",
            "VLESS XHTTP TLS",
        ),
        ("hysteria2://example", "Hysteria 2"),
        ("mieru://example", "Mieru"),
        ('{"profiles": [{"protocol": "mieru"}]}', "Mieru JSON"),
        ("anytls://example", "AnyTLS"),
        ("tuic://example", "TUIC v5"),
    ],
)
def test_single_qr_names_profile(payload: str, profile_name: str) -> None:
    svg = build_qr_svg(payload)
    assert _texts(svg) == ["SG · ОДИНОЧНЫЙ ПРОФИЛЬ", profile_name]


def test_caption_extends_canvas() -> None:
    root = ET.fromstring(build_qr_svg("tuic://example"))
    view_box = [float(value) for value in root.attrib["viewBox"].split()]
    height = float(root.attrib["height"].removesuffix("mm"))

    assert height == view_box[3]
    assert view_box[3] > view_box[2]
    assert root.find(f"{SVG}rect") is not None


def test_caption_does_not_change_encoded_qr_matrix() -> None:
    payload = "vless://id@example.com:443?type=xhttp&security=reality#test"
    raw_root = ET.fromstring(_raw_qr_svg(payload))
    captioned_root = ET.fromstring(build_qr_svg(payload))

    raw_path = raw_root.find(f"{SVG}path")
    captioned_path = captioned_root.find(f"{SVG}path")
    assert raw_path is not None
    assert captioned_path is not None
    assert captioned_path.attrib["d"] == raw_path.attrib["d"]
