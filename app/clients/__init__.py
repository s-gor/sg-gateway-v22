"""Unified client domain with the independent AWG31 lifecycle installed."""

from importlib import import_module

from app.clients.awg31_lifecycle import install as _install_awg31_lifecycle

_install_awg31_lifecycle(import_module("app.clients.repository"))
from app.clients.awg31_stage2 import install as _install_awg31_stage2

_install_awg31_stage2()
del _install_awg31_stage2
