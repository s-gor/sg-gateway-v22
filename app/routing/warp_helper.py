from __future__ import annotations

import contextlib
import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from app.routing.runtime import (
    RoutingRuntimeError,
    apply_full_config,
    build_full_config,
    load_managed_fragment,
    restart_xray,
    service_is_active,
    set_xray_config_permissions,
    xray_config_path,
    xray_test_config,
)
from app.routing.warp import (
    WGCF_VERSION,
    WarpError,
    account_json_path,
    account_path,
    export_document,
    outbound,
    overview,
    parse_xray_outbound,
    profile_path,
    profile_ready,
    routing_uses_warp,
    save_state,
    scrubbed_profile,
    set_last_test,
    state_dir,
    state_path,
    xray_json_path,
)

WGCF_BIN = Path("/usr/local/bin/wgcf-cli")
XRAY_BIN = Path("/usr/local/bin/xray")
WGCF_BASE_URL = f"https://github.com/ArchiveNetwork/wgcf-cli/releases/download/{WGCF_VERSION}"


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 180,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise WarpError(detail or f"Команда завершилась с кодом {result.returncode}")
    return result


def _asset_name() -> str:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return "wgcf-cli-linux-64.tar.zstd"
    if machine in {"aarch64", "arm64"}:
        return "wgcf-cli-linux-arm64-v8a.tar.zstd"
    raise WarpError(f"Архитектура {machine} не поддерживается wgcf-cli")


def _download(url: str, target: Path, *, timeout: int = 180) -> None:
    curl = shutil.which("curl")
    if not curl:
        raise WarpError("Для установки WARP требуется curl")
    target.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            curl,
            "-fL",
            "--retry",
            "3",
            "--connect-timeout",
            "20",
            "--max-time",
            str(timeout),
            "-o",
            str(target),
            url,
        ],
        timeout=timeout + 30,
    )


def _wgcf_version_output() -> str:
    for arguments in (["version"], ["--version"]):
        try:
            result = _run([str(WGCF_BIN), *arguments], timeout=15)
        except WarpError:
            continue
        output = (result.stdout or result.stderr or "").strip()
        if output:
            return output
    return ""


def _install_wgcf() -> str:
    if WGCF_BIN.is_file():
        output = _wgcf_version_output()
        if WGCF_VERSION.lstrip("v") in output or WGCF_VERSION in output:
            return output

    if not shutil.which("unzstd"):
        raise WarpError(
            "Не найден unzstd. Повторно запустите полный установщик SG-Gateway."
        )
    asset = _asset_name()
    with tempfile.TemporaryDirectory(prefix="sg-gateway-wgcf-cli-") as directory:
        root = Path(directory)
        archive = root / asset
        digest = root / f"{asset}.dgst"
        _download(f"{WGCF_BASE_URL}/{asset}", archive)
        _download(f"{WGCF_BASE_URL}/{asset}.dgst", digest)
        expected = ""
        for line in digest.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("SHA2-256="):
                expected = line.split("=", 1)[1].strip().lower()
                break
        if len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
            raise WarpError("Файл контрольной суммы wgcf-cli имеет неверный формат")
        actual = hashlib.sha256(archive.read_bytes()).hexdigest()
        if actual != expected:
            raise WarpError("SHA-256 wgcf-cli не совпадает с опубликованной суммой")
        _run(
            ["tar", "--use-compress-program=unzstd", "-xf", str(archive), "-C", str(root)],
            timeout=90,
        )
        candidates = [path for path in root.rglob("wgcf-cli") if path.is_file()]
        if not candidates:
            raise WarpError("В архиве не найден бинарный файл wgcf-cli")
        binary = candidates[0]
        temporary = WGCF_BIN.with_name(WGCF_BIN.name + ".new")
        shutil.copy2(binary, temporary)
        temporary.chmod(0o755)
        os.replace(temporary, WGCF_BIN)

    output = _wgcf_version_output()
    if not output:
        raise WarpError("Установленный wgcf-cli не запускается")
    return output


def _generate_candidate(workdir: Path) -> tuple[bytes, dict]:
    workdir.mkdir(parents=True, exist_ok=True)
    os.chmod(workdir, 0o700)
    _run([str(WGCF_BIN), "register"], cwd=workdir, timeout=180)
    _run([str(WGCF_BIN), "generate", "--xray"], cwd=workdir, timeout=180)
    account = workdir / "wgcf.json"
    xray_outbound = workdir / "wgcf.xray.json"
    if not account.is_file() or not xray_outbound.is_file():
        raise WarpError("wgcf-cli не создал wgcf.json или wgcf.xray.json")
    try:
        json.loads(account.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WarpError("wgcf-cli создал некорректный wgcf.json") from exc
    document = parse_xray_outbound(xray_outbound)
    return account.read_bytes(), document


def _restore_file(path: Path, content: bytes | None, mode: int) -> None:
    if content is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".warp-restore")
    temporary.write_bytes(content)
    if path == xray_config_path():
        set_xray_config_permissions(temporary)
    else:
        os.chmod(temporary, mode)
    os.replace(temporary, path)


def _write_secret(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(path.name + ".new")
    temporary.write_bytes(content)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _write_outbound(path: Path, document: dict) -> None:
    _write_secret(
        path,
        (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )


@contextlib.contextmanager
def _temporary_warp_context(root: Path):
    old_dir = os.environ.get("SG_GATEWAY_WARP_STATE_DIR")
    old_state = os.environ.get("SG_GATEWAY_WARP_STATE_PATH")
    os.environ["SG_GATEWAY_WARP_STATE_DIR"] = str(root / "warp")
    os.environ["SG_GATEWAY_WARP_STATE_PATH"] = str(root / "warp-state.json")
    try:
        yield
    finally:
        if old_dir is None:
            os.environ.pop("SG_GATEWAY_WARP_STATE_DIR", None)
        else:
            os.environ["SG_GATEWAY_WARP_STATE_DIR"] = old_dir
        if old_state is None:
            os.environ.pop("SG_GATEWAY_WARP_STATE_PATH", None)
        else:
            os.environ["SG_GATEWAY_WARP_STATE_PATH"] = old_state


def _validate_exact_candidate(account: bytes, document: dict) -> tuple[str, str]:
    """Test generated WARP credentials before any live state is changed."""
    with tempfile.TemporaryDirectory(prefix="sg-gateway-warp-candidate-") as directory:
        root = Path(directory)
        with _temporary_warp_context(root):
            _write_secret(account_json_path(), account)
            _write_outbound(xray_json_path(), document)
            save_state(
                enabled=True,
                profile_ready=True,
                profile=scrubbed_profile(),
                wgcf_version=WGCF_VERSION,
            )
            config = build_full_config(load_managed_fragment())
            status, message = xray_test_config(config)
            if status == "error":
                raise WarpError(message)
            return status, message


def _live_paths() -> tuple[Path, ...]:
    return (
        account_json_path(),
        xray_json_path(),
        account_path(),
        profile_path(),
        state_path(),
    )


def _snapshot(paths: tuple[Path, ...]) -> dict[Path, bytes | None]:
    return {path: path.read_bytes() if path.is_file() else None for path in paths}


def _restore_snapshot(snapshot: dict[Path, bytes | None]) -> None:
    for path, content in snapshot.items():
        mode = 0o644 if path == state_path() else 0o600
        _restore_file(path, content, mode)


def _persist_and_apply(account: bytes, document: dict, *, event: str) -> tuple[str, str]:
    paths = _live_paths()
    old_files = _snapshot(paths)
    config_path = xray_config_path()
    old_config = config_path.read_bytes() if config_path.is_file() else None
    was_active = service_is_active()
    try:
        root = state_dir()
        root.mkdir(parents=True, exist_ok=True)
        os.chmod(root, 0o700)
        _write_secret(account_json_path(), account)
        _write_outbound(xray_json_path(), document)
        # The new ArchiveNetwork JSON pair supersedes the old INI profile.
        account_path().unlink(missing_ok=True)
        profile_path().unlink(missing_ok=True)
        save_state(
            enabled=True,
            profile_ready=True,
            profile=scrubbed_profile(),
            wgcf_version=WGCF_VERSION,
            **{event: time.time()},
        )
        config = build_full_config(load_managed_fragment())
        status, message = xray_test_config(config)
        if status == "error":
            raise WarpError(message)
        apply_status, apply_message = apply_full_config(config, restart_if_active=True)
        return apply_status, apply_message or message
    except Exception:
        _restore_snapshot(old_files)
        _restore_file(config_path, old_config, 0o600)
        if was_active and old_config is not None:
            restart_xray(required=False)
        raise


def install() -> dict:
    # Idempotent behavior is important for full-installer retries.
    if profile_ready():
        if overview().get("enabled"):
            return {
                "ok": True,
                "message": "WARP уже создан и активен.",
                "overview": overview(),
            }
        return enable()

    version_output = _install_wgcf()
    with tempfile.TemporaryDirectory(prefix="sg-gateway-warp-register-") as directory:
        account, document = _generate_candidate(Path(directory))
        _validate_exact_candidate(account, document)
        _persist_and_apply(account, document, event="installed_at")
    return {
        "ok": True,
        "message": "WARP создан и активирован.",
        "wgcf": version_output,
        "overview": overview(),
    }


def recreate() -> dict:
    version_output = _install_wgcf()
    with tempfile.TemporaryDirectory(prefix="sg-gateway-warp-recreate-") as directory:
        account, document = _generate_candidate(Path(directory))
        _validate_exact_candidate(account, document)
        _persist_and_apply(account, document, event="regenerated_at")
    return {
        "ok": True,
        "message": "WARP пересоздан и активирован.",
        "wgcf": version_output,
        "overview": overview(),
    }


def _apply_enabled_state(enable_value: bool) -> dict:
    old_state = state_path().read_bytes() if state_path().is_file() else None
    config_path = xray_config_path()
    old_config = config_path.read_bytes() if config_path.is_file() else None
    was_active = service_is_active()
    try:
        if enable_value and not profile_ready():
            raise WarpError("Сначала создайте WARP")
        if enable_value:
            # Enable the public/runtime state before parsing managed rules so
            # existing explicit WARP rules remain fail-closed but valid.
            save_state(
                enabled=True,
                profile_ready=True,
                profile=scrubbed_profile(),
                wgcf_version=WGCF_VERSION,
            )
            fragment = load_managed_fragment()
        else:
            fragment = load_managed_fragment()
            if routing_uses_warp(fragment):
                raise WarpError("Сначала замените правила WARP на Direct или Block")
            save_state(
                enabled=False,
                profile_ready=profile_ready(),
                profile=scrubbed_profile(),
                wgcf_version=WGCF_VERSION,
            )
        config = build_full_config(fragment)
        status, message = xray_test_config(config)
        if status == "error":
            raise WarpError(message)
        apply_status, apply_message = apply_full_config(config, restart_if_active=True)
        return {
            "ok": True,
            "message": apply_message or message,
            "validation": apply_status,
        }
    except Exception:
        _restore_file(state_path(), old_state, 0o644)
        _restore_file(config_path, old_config, 0o600)
        if was_active and old_config is not None:
            restart_xray(required=False)
        raise


def enable() -> dict:
    payload = _apply_enabled_state(True)
    payload["message"] = "WARP активирован. " + payload.get("message", "")
    payload["overview"] = overview()
    return payload


def disable() -> dict:
    payload = _apply_enabled_state(False)
    payload["message"] = "WARP выключен. " + payload.get("message", "")
    payload["overview"] = overview()
    return payload


def remove() -> dict:
    fragment = load_managed_fragment()
    if routing_uses_warp(fragment):
        raise WarpError("Удаление запрещено: активная маршрутизация использует WARP")
    old_files = _snapshot(_live_paths())
    config_path = xray_config_path()
    old_config = config_path.read_bytes() if config_path.is_file() else None
    was_active = service_is_active()
    try:
        save_state(enabled=False, profile_ready=profile_ready(), profile=scrubbed_profile())
        config = build_full_config(fragment)
        status, message = xray_test_config(config)
        if status == "error":
            raise WarpError(message)
        apply_full_config(config, restart_if_active=True)
        for path in _live_paths():
            path.unlink(missing_ok=True)
    except Exception:
        _restore_snapshot(old_files)
        _restore_file(config_path, old_config, 0o600)
        if was_active and old_config is not None:
            restart_xray(required=False)
        raise
    return {"ok": True, "message": "WARP и локальные реквизиты удалены."}


def export_json() -> dict:
    return {
        "ok": True,
        "message": "WARP JSON подготовлен.",
        "document": export_document(),
    }


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test() -> dict:
    warp_outbound = outbound(require_enabled=False)
    if warp_outbound is None:
        raise WarpError("WARP-профиль не готов")
    if not XRAY_BIN.is_file():
        raise WarpError("Xray не установлен")
    curl = shutil.which("curl")
    if not curl:
        raise WarpError("Для проверки WARP требуется curl")

    port = _free_port()
    config = {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "warp-test-socks",
                "listen": "127.0.0.1",
                "port": port,
                "protocol": "socks",
                "settings": {"udp": True},
            }
        ],
        "outbounds": [warp_outbound, {"tag": "block", "protocol": "blackhole"}],
        "routing": {"domainStrategy": "AsIs", "rules": []},
    }
    status, message = xray_test_config(config)
    if status == "error":
        raise WarpError(message)

    with tempfile.TemporaryDirectory(prefix="sg-gateway-warp-test-") as directory:
        config_path = Path(directory) / "config.json"
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        process = subprocess.Popen(
            [str(XRAY_BIN), "run", "-config", str(config_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                    if probe.connect_ex(("127.0.0.1", port)) == 0:
                        break
                if process.poll() is not None:
                    error = (process.stderr.read() if process.stderr else "").strip()
                    raise WarpError(error or "Тестовый Xray завершился раньше времени")
                time.sleep(0.2)
            else:
                raise WarpError("Тестовый SOCKS WARP не запустился")

            trace = _run(
                [
                    curl,
                    "-fsS",
                    "--max-time",
                    "20",
                    "--socks5-hostname",
                    f"127.0.0.1:{port}",
                    "https://www.cloudflare.com/cdn-cgi/trace",
                ],
                timeout=30,
            ).stdout
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    values: dict[str, str] = {}
    for line in trace.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    warp_mode = values.get("warp", "")
    ip = values.get("ip", "")
    ok = warp_mode in {"on", "plus"}
    result_message = (
        f"WARP {warp_mode}, IP {ip}"
        if ok
        else f"Cloudflare trace не подтвердил WARP (warp={warp_mode or 'unknown'})"
    )
    set_last_test(ok=ok, message=result_message, ip=ip, warp=warp_mode)
    if not ok:
        raise WarpError(result_message)
    return {"ok": True, "message": result_message, "ip": ip, "warp": warp_mode}


def main(argv: list[str]) -> int:
    actions = {
        "install": install,
        "recreate": recreate,
        "enable": enable,
        "disable": disable,
        "remove": remove,
        "test": test,
        "export-json": export_json,
    }
    action = argv[1] if len(argv) > 1 else ""
    handler = actions.get(action)
    if handler is None:
        print(json.dumps({"ok": False, "message": "Unknown WARP action"}, ensure_ascii=False))
        return 2
    try:
        payload = handler()
    except (WarpError, RoutingRuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"ok": False, "message": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
