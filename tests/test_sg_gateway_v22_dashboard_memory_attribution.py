from pathlib import Path

import app.main as main


def _write_process(
    proc_root: Path,
    pid: int,
    command: list[str],
    rss_kib: int,
) -> None:
    process_dir = proc_root / str(pid)
    process_dir.mkdir(parents=True)
    process_dir.joinpath("cmdline").write_bytes(
        b"\0".join(part.encode("utf-8") for part in command) + b"\0"
    )
    process_dir.joinpath("status").write_text(
        f"Name:\ttest\nVmRSS:\t{rss_kib} kB\n",
        encoding="utf-8",
    )


def test_sg_gateway_rss_excludes_unrelated_python_processes(tmp_path: Path) -> None:
    proc_root = tmp_path / "proc"
    app_root = tmp_path / "opt" / "sg-gateway"
    python = str(app_root / ".venv" / "bin" / "python")
    waitress = str(app_root / ".venv" / "bin" / "waitress-serve")

    _write_process(
        proc_root,
        101,
        [python, waitress, "--port=18080", "app.production:app"],
        90_000,
    )
    _write_process(
        proc_root,
        102,
        [python, waitress, "--port=8090", "sg_hostd.app:app"],
        35_000,
    )
    _write_process(
        proc_root,
        103,
        ["/usr/bin/python3", "-u", "/usr/sbin/waagent", "-daemon"],
        31_000,
    )
    _write_process(
        proc_root,
        104,
        ["/usr/bin/python3", "-u", "bin/WALinuxAgent.egg", "-run-exthandlers"],
        36_000,
    )
    _write_process(
        proc_root,
        105,
        [python, str(app_root / "scripts" / "maintenance.py")],
        12_000,
    )

    assert main._sg_gateway_process_rss(proc_root, app_root) == 125_000 * 1024


def test_sg_gateway_rss_returns_zero_when_proc_is_unavailable(tmp_path: Path) -> None:
    assert main._sg_gateway_process_rss(
        tmp_path / "missing-proc",
        tmp_path / "opt" / "sg-gateway",
    ) == 0


def test_dashboard_uses_scoped_sg_gateway_process_accounting() -> None:
    source = Path(main.__file__).read_text(encoding="utf-8")

    assert "panel_rss = _sg_gateway_process_rss()" in source
    assert '_process_rss(("python", "waitress"))' not in source
