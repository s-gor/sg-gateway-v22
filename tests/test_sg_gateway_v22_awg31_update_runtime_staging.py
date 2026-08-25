from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from app.clients import repository as _repository  # noqa: F401


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "deploy/update-from-github-core.sh"
FILES = {
    "amneziawg-tools-3.0.20260805.tar.gz": "090f9383532822a756d078890b447e00af7f46bd30a10f9f47c46d633d807b19",
    "amneziawg-go-linux-amd64-v3.0.0": "131110027db6d5dc0e35b19eb5b8a2692676081366c34112088dc68bbb050bcd",
    "amneziawg-tools-3.1.20260812.tar.gz": "f18592c499c893b1b87b15de9e707ce265585cf2536698975b6ede8156d14ada",
    "amneziawg-go-linux-amd64-v3.1.20260814": "375bc2645df09498aa30215e3b3a09a97626a8e929f409e0edef6564fb8e3110",
}


def _run_function(tmp_path: Path, body: str, *, env: dict[str, str] | None = None):
    merged = os.environ.copy()
    merged.update(env or {})
    merged["SG_GATEWAY_UPDATE_CORE_LIBRARY_ONLY"] = "1"
    return subprocess.run(
        ["bash", "-c", f'source "$1"\n{body}', "test", str(CORE)],
        cwd=tmp_path,
        env=merged,
        text=True,
        capture_output=True,
        check=False,
    )


def _source_tree(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    (source / "vendor/cores").mkdir(parents=True)
    shutil.copytree(ROOT / "deploy", source / "deploy")
    for filename in FILES:
        shutil.copy2(ROOT / "vendor/cores" / filename, source / "vendor/cores" / filename)
    return source


def test_runtime_stage_contains_exactly_four_sha_verified_files(tmp_path: Path) -> None:
    source = _source_tree(tmp_path)
    stage = tmp_path / "stage"
    completed = _run_function(
        tmp_path,
        'stage_runtime_sources "$SOURCE" "$STAGE"',
        env={"SOURCE": str(source), "STAGE": str(stage)},
    )

    assert completed.returncode == 0, completed.stderr
    staged = sorted(path.name for path in (stage / "vendor/cores").iterdir())
    assert staged == sorted(FILES)
    assert {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (stage / "vendor/cores").iterdir()
    } == FILES


def test_runtime_stage_ignores_unrelated_vendor_payloads(tmp_path: Path) -> None:
    source = _source_tree(tmp_path)
    (source / "vendor/cores/large-unrelated-core.zip").write_bytes(b"not staged")
    stage = tmp_path / "stage"
    completed = _run_function(
        tmp_path,
        'stage_runtime_sources "$SOURCE" "$STAGE"',
        env={"SOURCE": str(source), "STAGE": str(stage)},
    )

    assert completed.returncode == 0, completed.stderr
    assert not (stage / "vendor/cores/large-unrelated-core.zip").exists()


def test_missing_runtime_file_stops_staging_without_prefix_fallback(tmp_path: Path) -> None:
    source = _source_tree(tmp_path)
    missing = next(iter(FILES))
    (source / "vendor/cores" / missing).unlink()
    prefix = tmp_path / "old-prefix"
    shutil.copytree(ROOT / "vendor/cores", prefix / "vendor/cores")
    completed = _run_function(
        tmp_path,
        'stage_runtime_sources "$SOURCE" "$STAGE"',
        env={
            "SOURCE": str(source),
            "STAGE": str(tmp_path / "stage"),
            "SG_GATEWAY_PREFIX": str(prefix),
        },
    )

    assert completed.returncode != 0
    assert missing in completed.stderr


def test_bad_runtime_sha_stops_staging(tmp_path: Path) -> None:
    source = _source_tree(tmp_path)
    damaged = next(iter(FILES))
    (source / "vendor/cores" / damaged).write_bytes(b"damaged")
    completed = _run_function(
        tmp_path,
        'stage_runtime_sources "$SOURCE" "$STAGE"',
        env={"SOURCE": str(source), "STAGE": str(tmp_path / "stage")},
    )

    assert completed.returncode != 0
    assert "SHA-256 mismatch" in completed.stderr


def test_light_checkout_uses_exact_runtime_whitelist(tmp_path: Path) -> None:
    source = tmp_path / "light-source"
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=ROOT, text=True
    ).strip()
    completed = _run_function(
        tmp_path,
        'TEMP_DIR="$WORK"; SOURCE_DIR="$SOURCE"; SOURCE_COMMIT="$COMMIT"; prepare_source_light',
        env={
            "WORK": str(tmp_path),
            "SOURCE": str(source),
            "COMMIT": commit,
            "SG_GATEWAY_GIT_URL": f"file://{ROOT}",
            "SG_GATEWAY_GITHUB_BRANCH": branch,
        },
    )

    assert completed.returncode == 0, completed.stderr
    assert sorted(path.name for path in (source / "vendor/cores").iterdir()) == sorted(FILES)
    assert not any((source / name).exists() for name in ("assets", "data", "docs", "tests", ".github"))
