from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
T = (ROOT / "app/web/templates/operation_job.html").read_text(encoding="utf-8")


def test_02208_operation_job_assets_semantics_and_polling_contract() -> None:
    assert "{% block page_styles %}" in T
    assert "{% block head %}" not in T
    assert "static_asset('sg-ui-operation-job-v22-08.css')" in T
    assert not (ROOT / "app/web/static/sg-operation-job-v13.css").exists()
    assert (ROOT / "app/web/static/sg-ui-operation-job-v22-08.css").exists()
    for marker in ('data-sg-ui-page="operation-job"', 'data-sg-section="operation-head"', 'data-sg-section="operation-terminal"', 'data-sg-section="operation-actions"', 'sg-ui-page', 'sg-ui-page-head', 'sg-ui-actions'):
        assert marker in T, marker
    for marker in ('data-kind="{{ job.kind }}"', 'data-restart-expected=', 'data-target-url=', 'data-status-url=', 'id="opjob-log"', 'id="opjob-status"', 'id="opjob-target"', 'id="opjob-refresh"', 'id="opjob-return-gateway"', "fetch(root.dataset.statusUrl", "window.setTimeout(update", "window.location.replace"):
        assert marker in T, marker
    assert "url_for('operation_job_status', job_id=job.job_id)" in T
