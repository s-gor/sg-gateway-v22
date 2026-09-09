from __future__ import annotations

import json

from app.maintenance.retire_legacy_awg import retire_legacy_awg


def bootstrap_idle_awg3() -> dict[str, object]:
    """Compatibility entrypoint for the historical post-update AWG3 hook.

    AWG3.0 is retired in 22.08 maintenance. Keep the module/function name so
    existing updater code can call it safely, but perform EOL cleanup instead
    of creating or starting an AWG3.0 runtime.
    """

    return retire_legacy_awg()


def main() -> int:
    result = bootstrap_idle_awg3()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
