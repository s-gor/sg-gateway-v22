from __future__ import annotations

import tarfile
from pathlib import Path


def test_print_awg2_vendor_kernel_metadata() -> None:
    archive = Path('vendor/cores/amneziawg-linux-kernel-module-1.0.20260329-2.tar.gz')
    with tarfile.open(archive, 'r:gz') as tar:
        rows = []
        for member in tar.getmembers():
            if member.isfile() and (member.name.endswith('/version.h') or member.name.endswith('/dkms.conf')):
                fh = tar.extractfile(member)
                if fh is not None:
                    rows.append(f'===== {member.name} =====\n' + fh.read().decode('utf-8', errors='replace'))
    assert False, '\n'.join(rows)
