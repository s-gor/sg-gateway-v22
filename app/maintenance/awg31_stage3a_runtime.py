from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from app.maintenance.awg31_stage3a_common import (
    AWG3_GO_FILE,
    AWG3_GO_SHA256,
    AWG3_TOOLS_FILE,
    AWG3_TOOLS_SHA256,
    AWG31_GO_FILE,
    AWG31_GO_SHA256,
    AWG31_TOOLS_FILE,
    AWG31_TOOLS_SHA256,
    DEPLOY_FILES,
)

_RUNTIME_CACHE: dict[tuple[str, str, str], Path] = {}


class RuntimeMixin:
    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _verified_source(self, filename: str, expected: str) -> Path:
        path = self.source_vendor / filename
        if not path.is_file():
            raise FileNotFoundError(path)
        actual = self._sha256(path)
        if actual != expected:
            raise RuntimeError(f"SHA-256 mismatch for {filename}: {actual}")
        return path

    def _copy_install_media(self, work: Path) -> tuple[Path, Path]:
        staged_vendor = work / "prefix/vendor/cores"
        staged_deploy = work / "prefix/deploy"
        staged_vendor.mkdir(parents=True)
        staged_deploy.mkdir(parents=True)
        artifacts = (
            (AWG3_TOOLS_FILE, AWG3_TOOLS_SHA256),
            (AWG3_GO_FILE, AWG3_GO_SHA256),
            (AWG31_TOOLS_FILE, AWG31_TOOLS_SHA256),
            (AWG31_GO_FILE, AWG31_GO_SHA256),
        )
        for filename, digest in artifacts:
            source = self._verified_source(filename, digest)
            target = staged_vendor / filename
            shutil.copy2(source, target)
            if self._sha256(target) != digest:
                raise RuntimeError(f"staged SHA-256 mismatch for {filename}")
        for filename in DEPLOY_FILES:
            source = self.source_deploy / filename
            if not source.is_file():
                raise FileNotFoundError(source)
            target = staged_deploy / filename
            shutil.copy2(source, target)
            os.chmod(target, 0o644 if filename.endswith(".service") else 0o755)
        return staged_vendor, staged_deploy

    @staticmethod
    def _run_build(command: list[str]) -> None:
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        if completed.returncode:
            detail = (completed.stderr or completed.stdout or "build failed").strip()
            raise RuntimeError(f"{' '.join(command)}: {detail}")

    def _build_runtime(
        self,
        *,
        work: Path,
        vendor: Path,
        tools_file: str,
        go_file: str,
        tools_sha: str,
        go_sha: str,
        name: str,
    ) -> Path:
        cache_key = (name, tools_sha, go_sha)
        cached = _RUNTIME_CACHE.get(cache_key)
        runtime = work / f"{name}-runtime"
        if cached is not None and cached.is_dir():
            shutil.copytree(cached, runtime)
            return runtime
        extraction = work / f"{name}-source"
        install_root = work / f"{name}-install"
        extraction.mkdir()
        with tarfile.open(vendor / tools_file, "r:gz") as archive:
            archive.extractall(extraction, filter="data")
        candidates = [item for item in extraction.iterdir() if item.is_dir()]
        if len(candidates) != 1 or not (candidates[0] / "src").is_dir():
            raise RuntimeError(f"invalid {name} tools archive layout")
        source = candidates[0] / "src"
        self._run_build(["make", "-C", str(source), "PLATFORM=linux", "clean"])
        self._run_build(["make", "-C", str(source), "PLATFORM=linux"])
        self._run_build(
            [
                "make",
                "-C",
                str(source),
                "PLATFORM=linux",
                "install",
                f"DESTDIR={install_root}",
                "PREFIX=/usr",
                "WITH_WGQUICK=yes",
                "WITH_BASHCOMPLETION=no",
                "WITH_SYSTEMDUNITS=no",
            ]
        )
        runtime_bin = runtime / "bin"
        runtime_bin.mkdir(parents=True)
        for filename in ("awg", "awg-quick"):
            built = install_root / "usr/bin" / filename
            if not built.is_file() or not os.access(built, os.X_OK):
                raise RuntimeError(f"{name} build did not create executable {filename}")
            shutil.copy2(built, runtime_bin / filename)
            os.chmod(runtime_bin / filename, 0o755)
        go = vendor / go_file
        if self._sha256(go) != go_sha:
            raise RuntimeError(f"staged SHA-256 mismatch for {go_file}")
        shutil.copy2(go, runtime_bin / "amneziawg-go")
        os.chmod(runtime_bin / "amneziawg-go", 0o755)
        (runtime / "SOURCE-SHA256SUMS").write_text(
            f"{tools_sha}  {tools_file}\n{go_sha}  {go_file}\n", encoding="utf-8"
        )
        version = subprocess.run(
            [str(runtime_bin / "awg"), "--version"],
            text=True,
            capture_output=True,
            check=False,
        )
        if version.returncode:
            raise RuntimeError(version.stderr or f"cannot run {name} awg")
        cache_root = Path(tempfile.mkdtemp(prefix=f"sg-gateway-{name}-runtime-cache-")) / "runtime"
        shutil.copytree(runtime, cache_root)
        _RUNTIME_CACHE[cache_key] = cache_root
        return runtime
