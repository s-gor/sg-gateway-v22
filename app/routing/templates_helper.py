from __future__ import annotations

import json
import sys

from app.routing.templates import (
    RoutingTemplateError,
    root_apply_candidate,
    root_rollback_latest,
)


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if action == "apply":
            payload = root_apply_candidate()
        elif action == "rollback":
            payload = root_rollback_latest()
        else:
            raise RoutingTemplateError("Допустимые действия: apply, rollback")
    except Exception as exc:
        print(json.dumps({"ok": False, "message": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
