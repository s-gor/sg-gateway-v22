"""Unified client domain.

AWG31 is wired through the repository, exports, access-card module and the
application factory. AWG2/AWG3 are retired product engines; legacy backup rows
remain durable but are filtered from active repository reads.
"""

from app.clients import repository as _repository
from app.clients.retired_awg import install as _install_retired_awg

_install_retired_awg(_repository)

del _install_retired_awg
del _repository
