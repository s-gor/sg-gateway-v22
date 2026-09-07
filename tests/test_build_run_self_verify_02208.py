from pathlib import Path


ROOT = Path(__file__).parents[1]
BUILD_RUN = ROOT / "build-run.sh"


def test_build_run_verifies_bare_output_filename_without_path_lookup():
    source = BUILD_RUN.read_text(encoding="utf-8")

    assert 'bash "$OUT" --verify-only' in source
    assert '\n"$OUT" --verify-only\n' not in source
