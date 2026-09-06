from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / ".github/workflows/naiveproxy-02207.yml"


def test_naiveproxy_workflow_verifies_direct_dev_02207_pushes() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    push = re.search(r"(?ms)^  push:\n(?P<body>.*?)(?=^  [a-zA-Z_]+:|\Z)", source)
    assert push is not None, "NaiveProxy workflow must define a push trigger"
    assert re.search(r"(?m)^      - dev-02207\s*$", push.group("body")), (
        "Direct commits to dev-02207 must run the full NaiveProxy 22.07 verification workflow"
    )
