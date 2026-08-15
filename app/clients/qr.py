from __future__ import annotations

from io import BytesIO


class ClientQrError(ValueError):
    pass


def build_qr_svg(payload: str) -> str:
    """Build an SVG QR suitable for long ML-KEM-768 VLESS links.

    VLESS Encryption adds a large client key to the URL.  Error correction L
    leaves the most QR capacity while retaining normal scanner compatibility.
    """
    value = str(payload or "").strip()
    if not value:
        raise ClientQrError("Нельзя создать QR для пустой конфигурации")

    import qrcode
    import qrcode.image.svg
    from qrcode.exceptions import DataOverflowError

    factory = qrcode.image.svg.SvgPathImage
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=2,
    )
    qr.add_data(value, optimize=0)
    try:
        qr.make(fit=True)
    except (DataOverflowError, ValueError) as exc:
        # qrcode 7.x can report an overflow either as DataOverflowError or as
        # ValueError("Invalid version (was 41, expected 1 to 40)").  Only
        # normalize that known capacity error; unrelated ValueError instances
        # must still surface as programming/configuration errors.
        if isinstance(exc, ValueError) and not isinstance(exc, DataOverflowError):
            if "Invalid version" not in str(exc):
                raise
        raise ClientQrError(
            "Ссылка слишком велика для одного QR-кода; используйте скачивание ссылки"
        ) from exc

    image = qr.make_image(image_factory=factory)
    buffer = BytesIO()
    image.save(buffer)
    return buffer.getvalue().decode("utf-8")
