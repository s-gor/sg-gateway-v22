from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

CORE = Path('deploy/update-from-github-core.sh')
TEST = Path('tests/test_naiveproxy_core_update_repair_02208.py')
WORKFLOW = Path('.github/workflows/move-naive-repair-after-verify.yml')
SELF = Path('.github/patch_move_naive_repair_after_verify.py')

body = CORE.read_text(encoding='utf-8')
old_deploy = '  migrate_panel_wsgi_service\n  repair_naiveproxy_runtime_if_needed\n}\n\nrestart_panel() {'
new_deploy = '  migrate_panel_wsgi_service\n}\n\nrestart_panel() {'
if old_deploy not in body:
    raise SystemExit('expected deploy_source NaiveProxy repair call not found')
body = body.replace(old_deploy, new_deploy, 1)

old_main = '  run_stage 7 "Проверка HTTPS, credentials, Nginx и runtime" verify_final\n  bind_panel_update_state\n'
new_main = '  run_stage 7 "Проверка HTTPS, credentials, Nginx и runtime" verify_final\n\n  # Repair a runtime that was already missing before this Update only after\n  # all pre-existing protected runtime has passed the immutability checks.\n  # The global ERR trap is still active here, so a failed repair rolls the\n  # entire Update back to the Safety Backup.\n  repair_naiveproxy_runtime_if_needed\n  bind_panel_update_state\n'
if old_main not in body:
    raise SystemExit('expected main stage-7 tail not found')
body = body.replace(old_main, new_main, 1)
CORE.write_text(body, encoding='utf-8')

source = TEST.read_text(encoding='utf-8')
addition = r'''

def test_core_repairs_missing_naiveproxy_only_after_protected_runtime_verification():
    source = Path("deploy/update-from-github-core.sh").read_text(encoding="utf-8")
    deploy_start = source.index("deploy_source() {")
    deploy_end = source.index("\nrestart_panel() {", deploy_start)
    deploy_body = source[deploy_start:deploy_end]
    assert "repair_naiveproxy_runtime_if_needed" not in deploy_body

    stage7 = source.index('run_stage 7 "Проверка HTTPS, credentials, Nginx и runtime" verify_final')
    repair = source.index("repair_naiveproxy_runtime_if_needed", stage7)
    bind = source.index("bind_panel_update_state", stage7)
    finished = source.index("UPDATE_FINISHED=1", stage7)
    assert stage7 < repair < bind < finished
'''
if 'test_core_repairs_missing_naiveproxy_only_after_protected_runtime_verification' not in source:
    TEST.write_text(source.rstrip() + addition + '\n', encoding='utf-8')

subprocess.run(['bash', '-n', str(CORE)], check=True)

WORKFLOW.unlink(missing_ok=True)
SELF.unlink(missing_ok=True)

subprocess.run(['git', 'add', '-A'], check=True)
tracked = subprocess.check_output(['git', 'ls-files'], text=True).splitlines()
tracked = [p for p in tracked if p != 'SOURCE-SHA256SUMS' and Path(p).exists()]
rows = [f"{hashlib.sha256(Path(p).read_bytes()).hexdigest()}  {p}" for p in sorted(tracked)]
Path('SOURCE-SHA256SUMS').write_text('\n'.join(rows) + '\n', encoding='utf-8')
subprocess.run(['git', 'add', 'SOURCE-SHA256SUMS'], check=True)
subprocess.run(['git', 'config', 'user.name', 'github-actions[bot]'], check=True)
subprocess.run(['git', 'config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com'], check=True)
subprocess.run(['git', 'commit', '-m', 'fix: repair NaiveProxy after protected runtime verification'], check=True)
subprocess.run(['git', 'push', 'origin', 'HEAD:fix/02208-clients-keys-dormant-restore'], check=True)
