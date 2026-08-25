from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


EXPECTED_RUNTIME_ASSETS = {
    "vendor/cores/amneziawg-tools-3.0.20260805.tar.gz": "090f9383532822a756d078890b447e00af7f46bd30a10f9f47c46d633d807b19",
    "vendor/cores/amneziawg-go-linux-amd64-v3.0.0": "131110027db6d5dc0e35b19eb5b8a2692676081366c34112088dc68bbb050bcd",
    "vendor/cores/amneziawg-tools-3.1.20260812.tar.gz": "f18592c499c893b1b87b15de9e707ce265585cf2536698975b6ede8156d14ada",
    "vendor/cores/amneziawg-go-linux-amd64-v3.1.20260814": "375bc2645df09498aa30215e3b3a09a97626a8e929f409e0edef6564fb8e3110",
}
REQUIRED_AWG31_PRODUCTION_FILES = (
    "hostd/sg_hostd/__init__.py",
    "vendor/cores/SHA256SUMS",
    "vendor/cores/VERSIONS.env",
)


class PackageContractError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_sums(root: Path) -> dict[str, str]:
    sums = root / "SOURCE-SHA256SUMS"
    if not sums.is_file():
        raise PackageContractError("SOURCE-SHA256SUMS is missing")
    result: dict[str, str] = {}
    for line_no, raw in enumerate(sums.read_text(encoding="utf-8").splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", raw)
        if match is None:
            raise PackageContractError(
                f"invalid SOURCE-SHA256SUMS line {line_no}: {raw!r}"
            )
        relative = match.group(2)
        if relative in result:
            raise PackageContractError(f"duplicate SOURCE-SHA256SUMS path: {relative}")
        result[relative] = match.group(1)
    return result


def verify_package_root(root: Path, expected_source_sha: str) -> dict:
    root = Path(root)
    if not re.fullmatch(r"[0-9a-f]{40}", expected_source_sha):
        raise PackageContractError("expected source SHA is not an exact commit SHA")

    metadata_path = root / "PACKAGE-SOURCE.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise PackageContractError("PACKAGE-SOURCE.json is missing or invalid") from exc
    if metadata.get("source_sha") != expected_source_sha:
        raise PackageContractError("package source SHA does not match the expected commit")
    if not re.fullmatch(r"[0-9a-f]{40}", str(metadata.get("source_tree") or "")):
        raise PackageContractError("package source tree is missing or invalid")

    try:
        manifest = json.loads((root / "release-manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise PackageContractError("release-manifest.json is missing or invalid") from exc
    awg31 = manifest.get("awg31")
    if not isinstance(awg31, dict):
        raise PackageContractError("release manifest has no AWG31 package contract")
    runtime_assets = awg31.get("runtime_assets")
    if runtime_assets != EXPECTED_RUNTIME_ASSETS:
        raise PackageContractError("AWG31 runtime asset manifest is not the exact four-file set")
    production = awg31.get("production_files")
    if not isinstance(production, list) or not production:
        raise PackageContractError("AWG31 production file manifest is empty")
    if len(set(production)) != len(production):
        raise PackageContractError("AWG31 production file manifest contains duplicates")
    for relative in REQUIRED_AWG31_PRODUCTION_FILES:
        if relative not in production:
            raise PackageContractError(
                f"required AWG31 production file missing from manifest: {relative}"
            )

    listed = _source_sums(root)
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and path.relative_to(root).as_posix()
        not in {"SOURCE-SHA256SUMS", "PACKAGE-SOURCE.json"}
    }
    missing_from_manifest = sorted(actual - set(listed))
    absent_payload = sorted(set(listed) - actual)
    if missing_from_manifest:
        raise PackageContractError(
            "unexpected package payload: " + ", ".join(missing_from_manifest[:20])
        )
    if absent_payload:
        raise PackageContractError(
            "package payload is missing: " + ", ".join(absent_payload[:20])
        )
    for relative, expected in listed.items():
        actual_sha = _sha256(root / relative)
        if actual_sha != expected:
            raise PackageContractError(
                f"package payload checksum mismatch: {relative}: {actual_sha}"
            )
    for relative in production:
        if relative not in listed or not (root / relative).is_file():
            raise PackageContractError(f"AWG31 production file is missing: {relative}")
    for relative, expected in EXPECTED_RUNTIME_ASSETS.items():
        actual_sha = _sha256(root / relative)
        if actual_sha != expected:
            raise PackageContractError(
                f"AWG31 runtime asset checksum mismatch: {relative}: {actual_sha}"
            )
    return {
        "source_sha": expected_source_sha,
        "source_tree": metadata["source_tree"],
        "runtime_assets": dict(runtime_assets),
        "production_files": len(production),
        "payload_files": len(actual),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("source_sha")
    args = parser.parse_args()
    result = verify_package_root(args.root, args.source_sha)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
