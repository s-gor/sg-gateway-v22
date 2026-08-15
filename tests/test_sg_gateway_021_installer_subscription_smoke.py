from pathlib import Path


def test_installer_accepts_empty_subscription_as_conflict():
    source = Path("install.sh").read_text(encoding="utf-8")

    assert "response.status_code in (200, 409)" in source
    assert "A fresh offline smoke database has no live Xray/Mihomo listener state" in source
    assert "Treat only missing/broken routes (404/5xx) as an installer failure" in source
    assert "assert response.status_code == 200" not in source.split(
        "protocols/subscription", 1
    )[1].split("stage_systemd_units", 1)[0]


def test_installer_still_requires_client_detail_page_200():
    source = Path("install.sh").read_text(encoding="utf-8")

    assert "detail = client.get(detail_path)" in source
    assert "assert detail.status_code == 200" in source
    assert "if response.status_code == 200:" in source
    assert "empty HTTP 200 response" in source
