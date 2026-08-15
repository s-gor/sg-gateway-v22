# sg-hostd

`sg-hostd` is the privileged helper used by the unprivileged SG-Gateway panel.
It exposes only explicitly implemented operations and listens locally.

Responsibilities include validated runtime application, service operations and
other host-level tasks that cannot be performed by the panel service account.
The panel must not execute arbitrary shell commands through this boundary.
