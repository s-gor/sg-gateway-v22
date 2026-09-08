from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORTABLE = ROOT / "hostd/sg_hostd/clients_keys_portable_restore_patch.py"
AWG3 = ROOT / "hostd/sg_hostd/awg3_runtime.py"

def test_portable_restore_reconciles_awg23_before_global_apply() -> None:
    text = PORTABLE.read_text(encoding="utf-8")
    start = text.index("def _apply_portable_clients_runtime_required")
    end = text.index("\n\n@contextmanager", start)
    body = text[start:end]
    repair = body.index("cr._repair_deployment_configs()")
    awg2 = body.index("cr._apply_awg()")
    awg3 = body.index("apply_awg3()")
    global_apply = body.index("cr.apply_all_clients()")
    assert repair < awg2 < awg3 < global_apply

def test_awg3_refetches_rows_after_repair_before_render() -> None:
    text = AWG3.read_text(encoding="utf-8")
    start = text.index("def apply_awg3()")
    body = text[start:]
    repair = body.index("_repair_configs(secrets)")
    refetch = body.index("rows = cr._deployment_rows(ENGINE)", repair)
    render = body.index("body = _render(rows, secrets)", repair)
    assert repair < refetch < render
