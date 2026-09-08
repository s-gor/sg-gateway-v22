from pathlib import Path
import hashlib

exports = Path('app/clients/exports.py')
text = exports.read_text(encoding='utf-8')
old = '''    if engine != "sgclient":
        try:
            settings = get_connection_settings(engine)
        except (KeyError, LookupError):
            return False
        if not settings.enabled:
            return False
'''
new = '''    if engine != "sgclient":
        try:
            if engine in {"anytls", "tuic"}:
                # AnyTLS and TUIC v5 are sing-box subprofiles managed by the
                # Mihomo Connection.  Their readiness flags live in
                # mihomo.config_json; there are no standalone connection rows.
                settings = get_connection_settings("mihomo")
                profile_enabled = bool(settings.config.get(f"{engine}_enabled"))
                if not settings.enabled or not profile_enabled:
                    return False
            else:
                settings = get_connection_settings(engine)
                if not settings.enabled:
                    return False
        except (KeyError, LookupError):
            return False
'''
if old not in text:
    raise SystemExit('expected export readiness block not found')
exports.write_text(text.replace(old, new, 1), encoding='utf-8')

tests = Path('tests/test_clients_keys_dormant_restore_02208.py')
t = tests.read_text(encoding='utf-8')
addition = r'''

@pytest.mark.parametrize(
    ("engine", "flag"),
    (("anytls", "anytls_enabled"), ("tuic", "tuic_enabled")),
)
def test_singbox_subprofile_export_readiness_uses_mihomo_connection(
    engine: str,
    flag: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AnyTLS/TUIC readiness comes from Mihomo config, not nonexistent rows."""

    client = SimpleNamespace(id=1, enabled=True)
    device = SimpleNamespace(id=7, enabled=True)
    deployment = SimpleNamespace(status="applied", config_json='{}')
    calls: list[str] = []

    monkeypatch.setattr(exports, "_resolve_device", lambda client, device=None: device)
    monkeypatch.setattr(
        exports,
        "_deployments",
        lambda client, device=None: {engine: deployment},
    )

    def settings(requested_engine: str):
        calls.append(requested_engine)
        if requested_engine != "mihomo":
            raise AssertionError(f"unexpected connection lookup: {requested_engine}")
        return SimpleNamespace(enabled=True, config={flag: True}, host="", port=0)

    monkeypatch.setattr(exports, "get_connection_settings", settings)

    assert exports.is_export_ready(client, engine, device) is True
    assert calls == ["mihomo"]


@pytest.mark.parametrize(
    ("engine", "flag"),
    (("anytls", "anytls_enabled"), ("tuic", "tuic_enabled")),
)
def test_singbox_subprofile_export_stays_dormant_when_profile_flag_is_off(
    engine: str,
    flag: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SimpleNamespace(id=1, enabled=True)
    device = SimpleNamespace(id=7, enabled=True)
    deployment = SimpleNamespace(status="applied", config_json='{}')

    monkeypatch.setattr(exports, "_resolve_device", lambda client, device=None: device)
    monkeypatch.setattr(
        exports,
        "_deployments",
        lambda client, device=None: {engine: deployment},
    )
    monkeypatch.setattr(
        exports,
        "get_connection_settings",
        lambda requested_engine: SimpleNamespace(
            enabled=True,
            config={flag: False},
            host="",
            port=0,
        ) if requested_engine == "mihomo" else (_ for _ in ()).throw(
            AssertionError(f"unexpected connection lookup: {requested_engine}")
        ),
    )

    assert exports.is_export_ready(client, engine, device) is False
'''
if 'test_singbox_subprofile_export_readiness_uses_mihomo_connection' in t:
    raise SystemExit('tests already patched')
tests.write_text(t.rstrip() + addition + '\n', encoding='utf-8')

# Refresh only paths already covered by SOURCE-SHA256SUMS, so temporary
# workflow/helper files never enter the release integrity manifest.
manifest = Path('SOURCE-SHA256SUMS')
lines = manifest.read_text(encoding='utf-8').splitlines()
out = []
for line in lines:
    if not line.strip() or line.lstrip().startswith('#'):
        out.append(line)
        continue
    parts = line.split(None, 1)
    if len(parts) != 2:
        out.append(line)
        continue
    _, raw_path = parts
    path = raw_path.strip()
    p = Path(path)
    if not p.is_file():
        out.append(line)
        continue
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    out.append(f'{digest}  {path}')
manifest.write_text('\n'.join(out) + '\n', encoding='utf-8')
