from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
ASSETS = {
    "vendor/cores/amneziawg-tools-3.0.20260805.tar.gz": "090f9383532822a756d078890b447e00af7f46bd30a10f9f47c46d633d807b19",
    "vendor/cores/amneziawg-go-linux-amd64-v3.0.0": "131110027db6d5dc0e35b19eb5b8a2692676081366c34112088dc68bbb050bcd",
    "vendor/cores/amneziawg-tools-3.1.20260812.tar.gz": "f18592c499c893b1b87b15de9e707ce265585cf2536698975b6ede8156d14ada",
    "vendor/cores/amneziawg-go-linux-amd64-v3.1.20260814": "375bc2645df09498aa30215e3b3a09a97626a8e929f409e0edef6564fb8e3110",
}
SOURCE_SHA = "1234567890abcdef1234567890abcdef12345678"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(root: Path) -> None:
    manifest = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))
    awg31 = manifest["awg31"]
    production = awg31["production_files"]
    for relative in production:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if relative in ASSETS:
            shutil.copy2(ROOT / relative, target)
        else:
            target.write_text(f"fixture:{relative}\n", encoding="utf-8")
    (root / "release-manifest.json").parent.mkdir(parents=True, exist_ok=True)
    (root / "release-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    (root / "PACKAGE-SOURCE.json").write_text(
        json.dumps({"source_sha": SOURCE_SHA, "source_tree": "a" * 40}),
        encoding="utf-8",
    )
    files = sorted(
        item
        for item in root.rglob("*")
        if item.is_file() and item.name not in {"SOURCE-SHA256SUMS", "PACKAGE-SOURCE.json"}
    )
    (root / "SOURCE-SHA256SUMS").write_text(
        "".join(f"{_sha(item)}  {item.relative_to(root).as_posix()}\n" for item in files),
        encoding="utf-8",
    )


def test_verify_package_source_accepts_exact_awg31_manifest(tmp_path: Path) -> None:
    from scripts.package_contract import verify_package_root

    _fixture(tmp_path)
    result = verify_package_root(tmp_path, SOURCE_SHA)
    assert result["source_sha"] == SOURCE_SHA
    assert result["runtime_assets"] == ASSETS
    assert result["production_files"] >= len(ASSETS)


@pytest.mark.parametrize("failure", ["missing", "bad-sha", "unexpected"])
def test_verify_package_source_rejects_incomplete_or_tampered_payload(
    tmp_path: Path, failure: str,
) -> None:
    from scripts.package_contract import PackageContractError, verify_package_root

    _fixture(tmp_path)
    target = tmp_path / next(iter(ASSETS))
    if failure == "missing":
        target.unlink()
    elif failure == "bad-sha":
        copied = target.with_suffix(target.suffix + ".copy")
        shutil.copy2(target, copied)
        target.unlink()
        copied.rename(target)
        target.write_bytes(target.read_bytes() + b"corrupt")
    else:
        (tmp_path / "unexpected-private.key").write_text("must fail", encoding="utf-8")

    with pytest.raises(PackageContractError):
        verify_package_root(tmp_path, SOURCE_SHA)


def test_build_embeds_and_reports_exact_source_sha() -> None:
    body = (ROOT / "build-run.sh").read_text(encoding="utf-8")
    assert "PACKAGE-SOURCE.json" in body
    assert "EXPECTED_SOURCE_SHA" in body
    assert '"$EXPECTED_SOURCE_SHA" "$EXPECTED_SOURCE_TREE"' in body
    assert "scripts/package_contract.py" in body
