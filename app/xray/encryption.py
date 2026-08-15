from __future__ import annotations

import base64
import re


_PREFIX = "mlkem768x25519plus"
_APPEARANCES = {"native", "xorpub", "random"}
_SERVER_SESSION_RE = re.compile(r"^(?:\d+|\d+-\d+)s$")
_CLIENT_SESSIONS = {"0rtt", "1rtt"}
_TRIPLE_RE = re.compile(r"^(\d+)-(\d+)-(\d+)$")
_BASE64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_BASE64_ANY_RE = re.compile(r"^[A-Za-z0-9_+/=-]+$")
_DEFAULT_PADDING = ("100-111-1111", "75-0-111", "50-0-3333")


class VlessEncryptionError(ValueError):
    pass


def _decode_base64url(value: str) -> bytes:
    if not value or not _BASE64URL_RE.fullmatch(value):
        raise VlessEncryptionError("Некорректный base64url-параметр VLESS Encryption")
    padded = value + "=" * ((4 - len(value) % 4) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise VlessEncryptionError(
            "Некорректный base64url-параметр VLESS Encryption"
        ) from exc



def _normalise_key_material(value: object) -> tuple[str, bytes]:
    text = str(value or "").strip()
    if not text or not _BASE64_ANY_RE.fullmatch(text):
        raise VlessEncryptionError("Некорректный ML-KEM-768 key material")
    padded = text + "=" * ((4 - len(text) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise VlessEncryptionError("Некорректный ML-KEM-768 key material") from exc
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("="), raw

def _parse_triple(value: str, *, first_padding: bool = False) -> tuple[int, int, int]:
    match = _TRIPLE_RE.fullmatch(value)
    if not match:
        raise VlessEncryptionError(f"Некорректный padding/delay блок: {value}")
    probability, minimum, maximum = (int(item) for item in match.groups())
    if not 0 <= probability <= 100 or minimum < 0 or maximum < minimum:
        raise VlessEncryptionError(f"Некорректный padding/delay диапазон: {value}")
    if first_padding and (probability != 100 or minimum <= 0):
        raise VlessEncryptionError(
            "Первый padding VLESS Encryption должен иметь вероятность 100% "
            "и положительную минимальную длину"
        )
    return probability, minimum, maximum


def _parse(value: object) -> tuple[str, str]:
    """Return ``(role, auth_kind)`` for a complete Preview 33 value.

    Preview 33 deliberately accepts only an explicit full configuration with
    ML-KEM-768 authentication.  The short X25519 pair accidentally selected by
    Preview 31/32 is rejected even though its prefix/session blocks look valid.
    """
    text = str(value or "").strip()
    parts = text.split(".")
    if len(parts) < 7 or parts[0].lower() != _PREFIX:
        raise VlessEncryptionError("Неполный формат VLESS Encryption")
    if parts[1].lower() not in _APPEARANCES:
        raise VlessEncryptionError("Неподдерживаемый appearance VLESS Encryption")

    session = parts[2].lower()
    if session in _CLIENT_SESSIONS:
        role = "client"
    elif _SERVER_SESSION_RE.fullmatch(session):
        role = "server"
    else:
        raise VlessEncryptionError("Неподдерживаемый session VLESS Encryption")

    padding = parts[3:-1]
    if not padding or len(padding) % 2 == 0:
        raise VlessEncryptionError(
            "VLESS Encryption должен содержать явную последовательность padding/delay/padding"
        )
    for index, block in enumerate(padding):
        _parse_triple(block, first_padding=index == 0)

    auth = _decode_base64url(parts[-1])
    # ``xray mlkem768`` returns a compact Seed for the server and a much larger
    # Client/encapsulation key for the client.  This semantic distinction is
    # what prevents an X25519 pair from being accepted again.
    if role == "server":
        if not 32 <= len(auth) <= 128:
            raise VlessEncryptionError("Server decryption does not contain an ML-KEM-768 Seed")
        auth_kind = "mlkem768-seed"
    else:
        if len(auth) < 128:
            raise VlessEncryptionError("Client encryption does not contain an ML-KEM-768 Client key")
        auth_kind = "mlkem768-client"
    return role, auth_kind


def value_role(value: object) -> str:
    """Return ``client``/``server`` for a strict full ML-KEM-768 value."""
    try:
        role, _auth_kind = _parse(value)
    except VlessEncryptionError:
        return "invalid"
    return role


def build_mlkem_pair(seed: object, client: object) -> tuple[str, str]:
    """Build a full explicit VLESS Encryption pair from ``xray mlkem768``.

    Returns ``(client encryption, server decryption)``.
    """
    seed_text, seed_raw = _normalise_key_material(seed)
    client_text, client_raw = _normalise_key_material(client)
    if not 32 <= len(seed_raw) <= 128:
        raise VlessEncryptionError("xray mlkem768 вернул некорректный Seed")
    if len(client_raw) < 128:
        raise VlessEncryptionError("xray mlkem768 вернул некорректный Client key")

    padding = ".".join(_DEFAULT_PADDING)
    encryption = f"{_PREFIX}.native.0rtt.{padding}.{client_text}"
    decryption = f"{_PREFIX}.native.600s.{padding}.{seed_text}"
    # Validate the exact strings that will be written to secrets/database.
    if value_role(encryption) != "client" or value_role(decryption) != "server":
        raise VlessEncryptionError("Не удалось собрать корректную ML-KEM-768 пару")
    return encryption, decryption


def normalize_pair(encryption: object, decryption: object) -> tuple[str, str, bool]:
    """Return ``(client encryption, server decryption, swapped)``.

    Only a complete explicit ML-KEM-768 pair is accepted.  Preview 31/32
    short/X25519 values therefore trigger regeneration during installation.
    """
    client = str(encryption or "").strip()
    server = str(decryption or "").strip()
    client_role = value_role(client)
    server_role = value_role(server)

    if client_role == "client" and server_role == "server":
        return client, server, False
    if client_role == "server" and server_role == "client":
        return server, client, True
    raise VlessEncryptionError(
        "Некорректная ML-KEM-768 пара VLESS Encryption: требуется полный "
        "клиентский 0rtt/1rtt Client key и серверный 600s Seed с явным padding."
    )


def client_value_ready(value: object) -> bool:
    text = str(value or "").strip()
    return "PLACEHOLDER" not in text.upper() and value_role(text) == "client"


def server_value_ready(value: object) -> bool:
    text = str(value or "").strip()
    return "PLACEHOLDER" not in text.upper() and value_role(text) == "server"
