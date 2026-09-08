from pathlib import Path


def test_cloud_init_exit2_done_is_degraded_complete_not_fatal() -> None:
    source = (Path(__file__).resolve().parents[1] / "deploy" / "install-from-github.sh").read_text(encoding="utf-8")
    assert "cloud_init_rc == 2" in source
    assert "status:[[:space:]]*done" in source
    assert "completed with recoverable errors; continuing" in source


def test_cloud_init_other_nonzero_status_remains_fatal() -> None:
    source = (Path(__file__).resolve().parents[1] / "deploy" / "install-from-github.sh").read_text(encoding="utf-8")
    degraded = source.index("cloud_init_rc == 2")
    fatal = source.index("cloud-init did not finish successfully", degraded)
    assert fatal > degraded
